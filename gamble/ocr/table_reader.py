"""Full autonomous table reader — reads complete game state from a screenshot.

Detects cards, buttons (fold/call/raise), pot, stacks, blinds, and board cards.
Works regardless of table size using percentage-based regions and color detection.

Usage:
    from gamble.ocr.table_reader import read_table
    state = read_table(table_pil_image, window_name="Spin & Gold $0.25 - Blinds 15 | 30")

The returned GameState contains everything needed to make a decision.
"""

import logging
import re
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from gamble.ocr.card_reader import read_player_cards
from gamble.ocr.game_state import AvailableAction, GameState, PlayerInfo, Street

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Region definitions (percentage of table image)
# ---------------------------------------------------------------------------

# Button search region (bottom portion of table)
# Actual buttons appear in the bottom ~30% of table
BUTTON_Y_MIN = 0.70
BUTTON_Y_MAX = 0.98
BUTTON_X_MIN = 0.15
BUTTON_X_MAX = 0.98

# Pot display region (top-center)
POT_Y_MIN = 0.22
POT_Y_MAX = 0.42
POT_X_MIN = 0.30
POT_X_MAX = 0.70

# Board cards region (center)
BOARD_Y_MIN = 0.30
BOARD_Y_MAX = 0.55
BOARD_X_MIN = 0.15
BOARD_X_MAX = 0.85

# Player seat regions for 6-max Rush & Cash / Spin & Gold.
# Each entry: (x_center_pct, y_center_pct, stack_width_pct, stack_height_pct)
# The y-center is the stack NUMBER line (below the player name).
# Calibrated from live Rush & Cash screenshot pixel scanning (Mar 7 2026).
# Hero stack is bright cyan (119,204,255); opponents are muted teal (85,135,166).
SEAT_REGIONS_6MAX = [
    (0.500, 0.923, 0.14, 0.035),  # Seat 0: Hero (bottom center)
    (0.068, 0.748, 0.14, 0.035),  # Seat 1: Left-bottom
    (0.115, 0.362, 0.14, 0.035),  # Seat 2: Left-top
    (0.500, 0.253, 0.14, 0.035),  # Seat 3: Top center
    (0.888, 0.362, 0.14, 0.035),  # Seat 4: Right-top
    (0.915, 0.748, 0.14, 0.035),  # Seat 5: Right-bottom
]

# Dealer button detection area (within the felt, away from edges)
DEALER_Y_MIN = 0.30
DEALER_Y_MAX = 0.75
DEALER_X_MIN = 0.10
DEALER_X_MAX = 0.90

# HSV ranges for button colors
BUTTON_HSV = {
    'check': {
        # Bright green check/call buttons: H=35-85, S>100, V>140
        # Green felt has V~85 — V>140 filters it out
        'lower': np.array([35, 100, 140]),
        'upper': np.array([85, 255, 255]),
        'label': 'green',
    },
    'fold': {
        # GGPoker action buttons are ALL dark red/maroon: H=10-16, S=130-200, V=130-200
        # Fold H~12, Call H~13, Raise H~14 — all same color, distinguished by OCR text
        'lower': np.array([0, 80, 90]),
        'upper': np.array([18, 255, 255]),
        'label': 'dark_red',
    },
    'deal_me_in': {
        # Bright red/salmon "Deal Me In" / "I'm Back" buttons
        'lower': np.array([0, 100, 100]),
        'upper': np.array([15, 255, 255]),
        'label': 'red',
    },
    'check_yellow': {
        # Yellow/gold buttons in Battle Royale and other themed tables
        # Fills the gap between dark_red (H<=18) and green (H>=35)
        'lower': np.array([18, 80, 140]),
        'upper': np.array([35, 255, 255]),
        'label': 'yellow',
    },
}

# GGPoker's call button is near-black with faint gray text.
# Too dark for reliable HSV detection — we detect it via OCR instead.

# Minimum button area in pixels (scales with table size)
# Real GGPoker action buttons are ~200x80+ px on a 1230px-wide table = ~2.1% of table area.
# Tiny dark-red blobs (71x66 = 0.6%) are UI decorations / profile borders, NOT buttons.
MIN_BUTTON_AREA_FRAC = 0.005  # 0.5% of table area (was 0.8% — too strict)


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def read_table(
    table_img: Image.Image,
    window_name: str = "",
    window_id: int = 0,
    table_x_pt: int = 0,
    table_y_pt: int = 0,
    table_w_pt: int = 0,
    table_h_pt: int = 0,
    debug_dir: Optional[str] = None,
) -> GameState:
    """
    Main entry point for reading the complete game state from a table screenshot.

    DETECTION PIPELINE:
    1. Fast Button Scan (HSV): Identifies potential buttons in ~3ms using 
       predefined color ranges (Green, Orange, Red, Gray).
    2. Button Verification (OCR): Extracts text from detected buttons to 
       confirm action type ('fold', 'call', 'raise', 'deal_me_in') and amount.
    3. Action Filtering: Determines if it's the bot's turn based on visible 
       poker buttons vs. non-action buttons (sit-back-in, lobby popups).
    4. Card/Board Detection: Uses template matching and color profiles to 
       identify hole cards and community cards ONLY if action is needed.
    5. Financial OCR: Reads pot size and player stacks if they are normalized 
       to Big Blinds (Spin & Gold / Rush & Cash).
    """
    start = time.time()

    W, H = table_img.width, table_img.height
    img = np.array(table_img)
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]

    # 1. Buttons FIRST (fast: ~3ms HSV detection)
    t0 = time.time()
    buttons, button_rects = _detect_buttons(img, W, H)
    t1 = time.time()
    available_actions = []
    scale_x = table_w_pt / W if W > 0 else 0.5
    scale_y = table_h_pt / H if H > 0 else 0.5
    
    for btn_type, info in buttons.items():
        cx_px, cy_px = info['center']
        # Convert pixel center to screen points using actual scale ratio
        screen_x = table_x_pt + int(cx_px * scale_x)
        screen_y = table_y_pt + int(cy_px * scale_y)
        available_actions.append(AvailableAction(
            action_type=btn_type,
            amount=info.get('amount'),
            screen_x_pt=screen_x,
            screen_y_pt=screen_y,
            rel_x=cx_px / W,
            rel_y=cy_px / H,
            confidence=info.get('confidence', 0.8),
        ))

    # Only poker action buttons count as "my turn"
    poker_actions = {'fold', 'call', 'check', 'raise', 'bet', 'all_in'}
    non_action_buttons = {'new_hand', 'deal_me_in', 'show_rabbit', 'im_back'}
    action_types = {a.action_type for a in available_actions}
    # If non-action buttons present, this is post-hand / lobby — not our turn
    if action_types & non_action_buttons:
        is_my_turn = False
    else:
        is_my_turn = bool(action_types & poker_actions)

    has_any_buttons = bool(buttons)

    # 2. Cards + Board — only read if we have buttons (expensive OCR)
    if has_any_buttons:
        my_cards = read_player_cards(table_img, debug_dir=debug_dir)
        board_cards = _detect_board_cards(img, W, H)

        # --- Deduplicate board cards by name ---
        # OCR can misread two different board cards as the same value.
        # A legal board never has duplicate cards.
        if board_cards:
            seen = set()
            unique_board = []
            for card in board_cards:
                if card not in seen:
                    seen.add(card)
                    unique_board.append(card)
                else:
                    log.warning(f"BOARD DEDUP: duplicate '{card}' removed from {board_cards}")
            board_cards = unique_board

        # --- Cross-validate: no card should appear in both hole and board ---
        if my_cards and board_cards:
            overlap = set(my_cards) & set(board_cards)
            if overlap:
                log.warning(f"CARD COLLISION: {overlap} in both hole={my_cards} and board={board_cards}")
                # Remove the conflicting cards from the board (hole cards are more reliable)
                board_cards = [c for c in board_cards if c not in overlap]
    else:
        my_cards = []
        board_cards = []
    cards_face_down = len(my_cards) == 0
    t2 = time.time()

    # 3. Pot — only read if it's our turn
    if is_my_turn:
        pot = _read_pot(img, W, H)
        # SANITY CAP: BB display mode means pot is in BB.
        # In a 6-max game, pot can never exceed ~600 BB (everyone all-in 100 BB).
        # Values > 200 BB are almost certainly OCR misreads (e.g. reading
        # opponent profile "$570.75 Total Winnings" as pot).
        if pot > 200:
            log.warning(f"POT SANITY CAP: {pot:.1f} BB > 200 — OCR misread, capping at 0")
            pot = 0.0
    else:
        pot = 0.0
    t4 = time.time()

    # 5. Blinds from window title
    sb, bb = _parse_blinds(window_name)

    # 6. Call/raise amounts from button OCR
    call_amount = 0.0
    min_raise_amount = 0.0
    has_call = False
    for a in available_actions:
        if a.action_type == 'call':
            has_call = True
            if a.amount:
                # SANITY: call can't exceed 200 BB (same as pot cap)
                if a.amount > 200:
                    log.warning(f"CALL SANITY CAP: {a.amount:.1f} BB > 200 — OCR misread")
                    a.amount = None
                else:
                    call_amount = a.amount
        elif a.action_type == 'raise' and a.amount:
            if a.amount > 200:
                log.warning(f"RAISE SANITY CAP: {a.amount:.1f} BB > 200 — OCR misread")
                a.amount = None
            else:
                min_raise_amount = a.amount

    # --- OCR decimal-drop fix for call/raise amounts ---
    # Tesseract often drops the decimal point: "1.0" -> "10", "2.5" -> "25".
    # We apply the fix here (not in _parse_amount) because we need context:
    # the fix only triggers when the amount is unreasonably large vs pot/BB.
    if bb > 0:
        for btn_type in ('call', 'raise'):
            if btn_type not in buttons:
                continue
            btn_info = buttons[btn_type]
            raw_amount = btn_info.get('amount')
            btn_text = btn_info.get('text', '')
            if raw_amount is None or raw_amount < 10:
                continue
            # Check if this amount looks like a dropped-decimal misread
            # by trying _fix_ocr_missing_decimal on the raw number string
            raw_num_str = str(int(raw_amount)) if raw_amount == int(raw_amount) else str(raw_amount)
            fixed = _fix_ocr_missing_decimal(raw_num_str, btn_text, raw_num_str)
            if fixed is not None:
                fixed_val = float(fixed)
                # Only apply if the fixed value is reasonable relative to BB
                # (0.5 to 10 BB range) AND the raw value was suspiciously large
                # (> 5x BB for a standard call/raise)
                if fixed_val <= 10.0 and raw_amount > bb * 5:
                    log.info(f"OCR decimal fix applied to {btn_type}: "
                             f"{raw_amount} -> {fixed_val} (bb={bb})")
                    btn_info['amount'] = fixed_val  # Update source so step 8d sees corrected value
                    if btn_type == 'call':
                        call_amount = fixed_val
                    else:
                        min_raise_amount = fixed_val

    # If call button exists but all OCR pipelines failed to parse amount,
    # this is a bug — the geometric + robust OCR should always read it.
    # Log ERROR so we can investigate, then use pot-based estimate as safety net.
    if has_call and call_amount == 0.0:
        is_preflop = len(board_cards) == 0
        if pot > 2.0 and is_preflop:
            call_amount = max(round(pot * 0.4, 1), 1.0)
            log.error(f"CALL OCR FAILED (preflop): all pipelines failed, "
                      f"estimating from pot={pot} → call≈{call_amount}")
        elif pot > 0.5 and not is_preflop:
            call_amount = max(round(pot * 0.5, 1), 1.0)
            log.error(f"CALL OCR FAILED (postflop): all pipelines failed, "
                      f"estimating from pot={pot} → call≈{call_amount}")
        else:
            call_amount = 1.0
            log.error(f"CALL OCR FAILED: all pipelines failed, no pot context, "
                      f"using 1 BB — THIS SHOULD NEVER HAPPEN")

    # 7. Street from board cards
    street = _street_from_board(board_cards)

    # 8. Player stacks — only when it's our turn (expensive: 6 OCR calls)
    hero_stack_is_estimated = False
    if is_my_turn:
        players, hero_stack_is_estimated = _read_player_stacks(img, W, H)
    else:
        # Default hero stack so DecisionMaker doesn't think we're broke
        players = [PlayerInfo(seat=0, name="", stack=100.0, current_bet=0.0,
                              is_active=True, is_hero=True)]
        hero_stack_is_estimated = True
    t5 = time.time()

    # 8b. Cross-validate hero stack against opponent stacks.
    # When hero stack OCR fails, estimate from opponents instead of 100 BB.
    if hero_stack_is_estimated and len(players) > 1:
        opp_stacks = [p.stack for p in players if not p.is_hero and p.stack > 0]
        if opp_stacks:
            # Use median opponent stack as reference (more robust than mean)
            opp_stacks_sorted = sorted(opp_stacks)
            median_opp = opp_stacks_sorted[len(opp_stacks_sorted) // 2]
            # Hero probably has a similar stack (within 2x)
            estimated = round(median_opp, 1)
            hero_player = next((p for p in players if p.is_hero), None)
            if hero_player and abs(hero_player.stack - 100.0) < 0.01:
                hero_player.stack = estimated
                log.info(f"Hero stack estimated from opponents: {estimated} "
                         f"(median of {opp_stacks})")

    # 8c. Cross-validate pot against hero stack (decimal-drop detection).
    # If pot > 3x hero stack and pot is a 2-3 digit integer, try decimal fix.
    hero_stk_val = next((p.stack for p in players if p.is_hero), 0)
    if pot > 0 and hero_stk_val > 0 and not hero_stack_is_estimated:
        if pot > hero_stk_val * 3 and pot == int(pot) and pot >= 10:
            raw_pot_str = str(int(pot))
            if len(raw_pot_str) in (2, 3):
                candidate = raw_pot_str[0] + '.' + raw_pot_str[1:]
                try:
                    fixed_pot = float(candidate)
                    if 0.5 <= fixed_pot <= hero_stk_val * 2:
                        log.warning(f"POT DECIMAL FIX: {pot} → {fixed_pot} "
                                    f"(hero_stack={hero_stk_val})")
                        pot = fixed_pot
                except ValueError:
                    pass
    # Even without reliable hero stack, catch extreme values
    elif pot >= 500 and pot == int(pot):
        raw_pot_str = str(int(pot))
        if len(raw_pot_str) == 3:
            candidate = raw_pot_str[0] + '.' + raw_pot_str[1:]
            try:
                fixed_pot = float(candidate)
                if 0.5 <= fixed_pot < 10.0:
                    log.warning(f"POT DECIMAL FIX (no anchor): {pot} → {fixed_pot}")
                    pot = fixed_pot
            except ValueError:
                pass

    # 8d. Double-read confirmation + max_expected validation for call/raise.
    # The 288 BB misread would have been caught if we re-OCR'd with different
    # preprocessing.  Now that hero_stack is known, reject absurd values and
    # double-check large amounts with an independent OCR pass.
    max_expected_amt = hero_stk_val if hero_stk_val > 0 and not hero_stack_is_estimated else 200.0
    for btn_type in ('call', 'raise'):
        if btn_type not in buttons:
            continue
        btn_info = buttons[btn_type]
        amount = btn_info.get('amount')
        if amount is None or amount <= 0:
            continue

        # max_expected: reject amounts > hero stack (or 200 BB fallback)
        if amount > max_expected_amt:
            log.warning(f"MAX_EXPECTED: {btn_type} amount {amount} > max {max_expected_amt}, "
                        f"attempting re-OCR")
            rx, ry, rw, rh = btn_info['rect']
            alt_amount = _reocr_button_region(img, rx, ry, rw, rh)
            if alt_amount is not None and alt_amount <= max_expected_amt:
                log.warning(f"MAX_EXPECTED: re-OCR {btn_type} got {alt_amount}, using it")
                amount = alt_amount
            else:
                log.warning(f"MAX_EXPECTED: re-OCR {btn_type} also bad ({alt_amount}), "
                            f"rejecting — using None")
                amount = None

        # Double-read confirmation: for any amount > 10 BB, re-OCR and compare.
        # A 20% divergence means one read is wrong — use the lower (safer) value.
        if amount is not None and amount > 10:
            rx, ry, rw, rh = btn_info['rect']
            alt_amount = _reocr_button_region(img, rx, ry, rw, rh)
            if alt_amount is not None and abs(amount - alt_amount) / max(amount, 1) > 0.20:
                log.warning(f"DOUBLE-READ MISMATCH {btn_type}: {amount} vs {alt_amount}, "
                            f"using lower")
                amount = min(amount, alt_amount)

        # Write back corrected amount
        if btn_type == 'call':
            call_amount = amount if amount is not None else call_amount
        else:
            min_raise_amount = amount if amount is not None else min_raise_amount
        btn_info['amount'] = amount
        # Also update the AvailableAction
        for a in available_actions:
            if a.action_type == btn_type:
                a.amount = amount

    # 9. Dealer button and position
    dealer_seat, _, _ = _detect_dealer_button(img, W, H)
    hero_seat = 0  # Always seat 0 (bottom center)
    num_active = max(len(players), 2)
    position = _hero_position(hero_seat, dealer_seat, num_active)

    # 10. Count opponents actually in the hand (card back detection)
    #     Only run when it's our turn (postflop needs accurate count for Monte Carlo)
    if is_my_turn and board_cards:
        opponents_in_hand = _count_opponents_in_hand(img, W, H)
    else:
        opponents_in_hand = -1  # unknown (preflop or not our turn)

    t6 = time.time()
    elapsed_ms = (time.time() - start) * 1000
    log.debug(f"  Timing: buttons={int((t1-t0)*1000)}ms cards+board={int((t2-t1)*1000)}ms "
              f"pot={int((t4-t2)*1000)}ms stacks={int((t5-t4)*1000)}ms "
              f"opp_cards={int((t6-t5)*1000)}ms")

    state = GameState(
        window_id=window_id,
        window_name=window_name,
        table_x_pt=table_x_pt,
        table_y_pt=table_y_pt,
        table_w_pt=table_w_pt or W // 2,
        table_h_pt=table_h_pt or H // 2,
        my_cards=my_cards,
        board_cards=board_cards,
        cards_face_down=cards_face_down,
        pot=pot,
        current_street_pot=0.0,
        call_amount=call_amount,
        min_raise_amount=min_raise_amount,
        small_blind=sb,
        big_blind=bb,
        players=players,
        hero_seat=hero_seat,
        dealer_seat=dealer_seat,
        available_actions=available_actions,
        street=street,
        is_my_turn=is_my_turn,
        position=position,
        opponents_in_hand=opponents_in_hand,
        ocr_latency_ms=elapsed_ms,
        ocr_source='python_table_reader',
        hero_stack_is_estimated=hero_stack_is_estimated,
    )

    log.info(f"Table read in {elapsed_ms:.0f}ms: cards={my_cards} board={board_cards} "
             f"buttons={list(buttons.keys())} pot={pot} turn={is_my_turn}")

    if debug_dir:
        _save_debug(img, W, H, buttons, button_rects, board_cards, pot, debug_dir)

    return state


# ---------------------------------------------------------------------------
#  Button detection — HSV color + OCR for amounts
# ---------------------------------------------------------------------------

def _detect_buttons(img: np.ndarray, W: int, H: int, deal_me_in_only: bool = False) -> Tuple[Dict, Dict]:
    """Detect action buttons by HSV color in the bottom region.

    Args:
        img: Table image
        W: Width
        H: Height
        deal_me_in_only: If True, search a larger region specifically for Deal Me In.

    Returns:
        (buttons_dict, rects_dict) where buttons_dict maps action type to info.
    """
    y_min = 0.40 if deal_me_in_only else BUTTON_Y_MIN
    y1 = int(H * y_min)
    y2 = int(H * BUTTON_Y_MAX)
    x1 = int(W * BUTTON_X_MIN)
    x2 = int(W * BUTTON_X_MAX)
    region = img[y1:y2, x1:x2]

    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)

    min_area = int(W * H * MIN_BUTTON_AREA_FRAC)
    if deal_me_in_only:
        min_area = int(W * H * 0.003)  # Use more lenient area for Deal Me In scan

    min_btn_w = W * 0.08   # Real buttons are ~200px on 1230px table = 16% (was 0.10)
    min_btn_h = H * 0.05   # Real buttons are ~80px on 617px table = 13% (was 0.07)

    buttons = {}
    rects = {}
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    small_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    region_w = x2 - x1

    for btn_type, hsv_def in BUTTON_HSV.items():
        if deal_me_in_only and btn_type != 'deal_me_in':
            continue

        mask = cv2.inRange(hsv, hsv_def['lower'], hsv_def['upper'])

        if hsv_def['label'] == 'dark_red':
            # Dark red: skip MORPH_CLOSE to prevent merging adjacent buttons
            # GGPoker fold/call/raise are all the same color and very close
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, small_kernel, iterations=1)
        else:
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)

        # Split abnormally wide dark_red contours (merged buttons)
        button_rects = []
        for c in contours:
            bx, by, bw, bh = cv2.boundingRect(c)
            area = bw * bh
            
            # GGPoker buttons can be smaller than 0.5% in some themes/resolutions.
            # Relax the area constraint for dark_red significantly (0.2%)
            this_min_area = min_area if hsv_def['label'] != 'dark_red' else int(W * H * 0.002)
            
            if area < this_min_area or bw < (min_btn_w * 0.7) or bh < (min_btn_h * 0.7):
                continue

            # If a dark_red contour is wider than 30% of button region,
            # it's likely multiple buttons merged together
            if hsv_def['label'] == 'dark_red' and bw > region_w * 0.30:
                # Try to find gaps by analyzing column-wise mask profile
                sub_mask = mask[by:by + bh, bx:bx + bw]
                col_sum = np.sum(sub_mask > 0, axis=0)  # pixels per column
                max_col = max(col_sum) if len(col_sum) > 0 else 1

                # Find valleys (columns with < 30% of max density)
                threshold = max_col * 0.3
                in_gap = col_sum < threshold
                splits = []
                gap_start = None
                for ci in range(len(in_gap)):
                    if in_gap[ci] and gap_start is None:
                        gap_start = ci
                    elif not in_gap[ci] and gap_start is not None:
                        gap_mid = (gap_start + ci) // 2
                        splits.append(gap_mid)
                        gap_start = None

                if len(splits) >= 2:
                    # Split at the found gaps
                    edges = [0] + splits[:3] + [bw]
                    for si in range(len(edges) - 1):
                        sx = bx + edges[si]
                        sw = edges[si + 1] - edges[si]
                        if sw > min_btn_w:
                            button_rects.append((sx, by, sw, bh))
                    log.debug(f"Split merged {bw}px contour into {len(edges)-1} buttons at gaps {splits}")
                elif bw > region_w * 0.55:
                    # No clear gaps found but very wide — split into 3 equal parts
                    third_w = bw // 3
                    for si in range(3):
                        sx = bx + si * third_w
                        sw = third_w if si < 2 else (bw - 2 * third_w)
                        button_rects.append((sx, by, sw, bh))
                    log.debug(f"Force-split {bw}px contour into 3 equal buttons")
                else:
                    button_rects.append((bx, by, bw, bh))
            else:
                button_rects.append((bx, by, bw, bh))

        for bx, by, bw, bh in button_rects:
            # Absolute pixel coordinates
            abs_x = bx + x1
            abs_y = by + y1
            center = (abs_x + bw // 2, abs_y + bh // 2)

            # OCR the button text to get amount and verify type
            amount, text = _ocr_button_text(img, abs_x, abs_y, bw, bh)
            actual_type = _classify_button_text(text, btn_type)

            if actual_type not in buttons:
                buttons[actual_type] = {
                    'center': center,
                    'rect': (abs_x, abs_y, bw, bh),
                    'amount': amount,
                    'text': text,
                    'confidence': 0.8 if text else 0.5,
                    'color': hsv_def['label'],
                }
                rects[actual_type] = (abs_x, abs_y, bw, bh)

            log.debug(f"Button {actual_type} ({hsv_def['label']}): "
                      f"({abs_x},{abs_y}) {bw}x{bh} text={text!r} amount={amount}")

    # Positional fallback: GGPoker buttons are always left=fold, middle=call/check, right=raise.
    # When OCR fails, multiple buttons get classified as 'fold' by color fallback.
    # If we found 'fold' but have unclassified dark_red buttons, assign by position.
    if ('fold' in buttons or 'check' in buttons) and len(buttons) < 3:
        # Check if we have any 'raise' or 'call' buttons. If not, scan the right-side
        # of the button region more aggressively with OCR.
        if 'raise' not in buttons:
            # GGPoker Raise is usually on the right side: x > 0.60W
            rx1 = int(W * 0.60)
            rx2 = int(W * 0.98)
            ry1 = int(H * 0.82)
            ry2 = int(H * 0.98)
            amount, text = _ocr_button_text(img, rx1, ry1, rx2 - rx1, ry2 - ry1)
            if 'rais' in text.lower() or 'bet' in text.lower() or 'all' in text.lower():
                log.info(f"Aggressive OCR scan found MISSED raise button: {text!r}")
                # Use a default center on the right side if we can't find exact rect
                buttons['raise'] = {
                    'center': (rx1 + (rx2 - rx1) // 2, ry1 + (ry2 - ry1) // 2),
                    'rect': (rx1, ry1, rx2 - rx1, ry2 - ry1),
                    'amount': amount,
                    'text': text,
                    'confidence': 0.6,
                    'color': 'ocr_fallback',
                }
                rects['raise'] = (rx1, ry1, rx2 - rx1, ry2 - ry1)

    if 'fold' in buttons and len(buttons) < 3:
        # Collect all dark_red button candidates sorted left-to-right
        # Use NO morphological close to avoid merging adjacent buttons
        all_dark_btns = []
        for btn_type_key, hsv_def in BUTTON_HSV.items():
            if hsv_def['label'] != 'dark_red':
                continue
            mask2 = cv2.inRange(hsv, hsv_def['lower'], hsv_def['upper'])
            mask2 = cv2.morphologyEx(mask2, cv2.MORPH_OPEN, small_kernel, iterations=1)
            contours2, _ = cv2.findContours(mask2, cv2.RETR_EXTERNAL,
                                            cv2.CHAIN_APPROX_SIMPLE)
            for c in contours2:
                bx2, by2, bw2, bh2 = cv2.boundingRect(c)
                area2 = bw2 * bh2
                if area2 < min_area or bw2 < min_btn_w or bh2 < min_btn_h:
                    continue
                # Split wide merged contours
                if bw2 > region_w * 0.30:
                    sub_mask2 = mask2[by2:by2 + bh2, bx2:bx2 + bw2]
                    col_sum2 = np.sum(sub_mask2 > 0, axis=0)
                    max_col2 = max(col_sum2) if len(col_sum2) > 0 else 1
                    threshold2 = max_col2 * 0.3
                    in_gap2 = col_sum2 < threshold2
                    splits2 = []
                    gap_start2 = None
                    for ci2 in range(len(in_gap2)):
                        if in_gap2[ci2] and gap_start2 is None:
                            gap_start2 = ci2
                        elif not in_gap2[ci2] and gap_start2 is not None:
                            splits2.append((gap_start2 + ci2) // 2)
                            gap_start2 = None
                    if len(splits2) >= 2:
                        edges2 = [0] + splits2[:3] + [bw2]
                        for si2 in range(len(edges2) - 1):
                            sx2 = bx2 + edges2[si2]
                            sw2 = edges2[si2 + 1] - edges2[si2]
                            if sw2 > min_btn_w:
                                all_dark_btns.append((sx2 + x1, by2 + y1, sw2, bh2))
                    elif bw2 > region_w * 0.55:
                        third = bw2 // 3
                        for si2 in range(3):
                            sx2 = bx2 + si2 * third
                            sw2 = third if si2 < 2 else (bw2 - 2 * third)
                            all_dark_btns.append((sx2 + x1, by2 + y1, sw2, bh2))
                    else:
                        all_dark_btns.append((bx2 + x1, by2 + y1, bw2, bh2))
                else:
                    all_dark_btns.append((bx2 + x1, by2 + y1, bw2, bh2))

        all_dark_btns.sort(key=lambda b: b[0])  # Sort left to right

        if len(all_dark_btns) >= 3:
            # GGPoker layout: left=fold, middle=call/check, right=raise
            # Assign by POSITION only — no OCR (saves ~24 Tesseract calls)
            pos_types = ['fold', 'call', 'raise']
            for idx, btn_rect in enumerate(all_dark_btns[-3:]):
                abx, aby, abw, abh = btn_rect
                center = (abx + abw // 2, aby + abh // 2)
                pos_type = pos_types[idx]
                if pos_type not in buttons:
                    # Only OCR the call/raise buttons (need amounts), skip fold
                    amt, txt = None, ""
                    if pos_type in ('call', 'raise'):
                        amt, txt = _ocr_button_text(img, abx, aby, abw, abh)
                    buttons[pos_type] = {
                        'center': center,
                        'rect': btn_rect,
                        'amount': amt,
                        'text': txt,
                        'confidence': 0.6,
                        'color': 'dark_red_positional',
                    }
                    rects[pos_type] = btn_rect
                    log.debug(f"Positional button {pos_type} at {center}")

    # --- Geometric call button detection ---
    # GGPoker layout is ALWAYS: fold (left) | call (middle) | raise (right).
    # The call button is near-black (~RGB 20,16,16), invisible to all HSV ranges.
    # But we ALWAYS detect fold and raise (both caught by dark_red HSV).
    # So compute call's exact position from fold+raise geometry: same Y, same H,
    # X starts at fold's right edge, width = gap between fold and raise.
    has_action = bool(buttons)
    missing_call = 'call' not in buttons and 'check' not in buttons

    if missing_call and 'fold' in buttons and 'raise' in buttons and PYTESSERACT_AVAILABLE:
        fold_r = buttons['fold']['rect']  # (x, y, w, h)
        raise_r = buttons['raise']['rect']

        # Call is between fold's right edge and raise's left edge
        call_x = fold_r[0] + fold_r[2]  # fold right edge
        call_right = raise_r[0]           # raise left edge
        call_w = call_right - call_x
        # Use fold's Y and height (all buttons same row)
        call_y = fold_r[1]
        call_h = fold_r[3]

        if call_w > min_btn_w and call_h > 0:
            # Trim a few pixels of padding between buttons
            trim = max(int(call_w * 0.05), 2)
            call_x += trim
            call_w -= trim * 2

            center = (call_x + call_w // 2, call_y + call_h // 2)

            # OCR this exact region — robust pipeline
            amount, text = _ocr_button_text(img, call_x, call_y, call_w, call_h)
            actual_type = _classify_button_text(text, 'call')
            if actual_type in ('call', 'check', 'all_in'):
                # If amount still None, try digits-only robust OCR
                if amount is None:
                    btn_crop = img[call_y:call_y + call_h, call_x:call_x + call_w]
                    if btn_crop.size > 0:
                        amount = _ocr_amount_robust(btn_crop, 'call_geometric')

                buttons[actual_type] = {
                    'center': center,
                    'rect': (call_x, call_y, call_w, call_h),
                    'amount': amount,
                    'text': text,
                    'confidence': 0.9,  # High confidence — geometric position
                    'color': 'geometric',
                }
                rects[actual_type] = (call_x, call_y, call_w, call_h)
                missing_call = False
                log.info(f"GEOMETRIC call button at ({call_x},{call_y}) "
                         f"{call_w}x{call_h} amount={amount} text={text!r}")

    # Last resort: full-region OCR scan (only if geometric didn't find it)
    missing_raise = 'raise' not in buttons
    if has_action and (missing_call or missing_raise) and PYTESSERACT_AVAILABLE:
        ocr_btn = _find_buttons_by_ocr(img, W, H, x1, y1, x2, y2, buttons)
        if ocr_btn:
            buttons.update(ocr_btn)
            for k, v in ocr_btn.items():
                rects[k] = v['rect']

    return buttons, rects


def _find_buttons_by_ocr(
    img: np.ndarray, W: int, H: int,
    rx1: int, ry1: int, rx2: int, ry2: int,
    already_found: Dict,
) -> Optional[Dict]:
    """Find missing buttons via OCR in the button region.

    GGPoker's call button is near-black with faint gray text,
    too dark for reliable HSV detection.  This also catches raise
    buttons that might be missed by the HSV masks.
    """
    region = img[ry1:ry2, rx1:rx2]
    if region.size == 0:
        return None

    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    scale = 3

    # Try multiple preprocessing pipelines to find ALL button text reliably.
    # Pipeline order: fixed threshold → CLAHE → adaptive.
    text = ""
    for pipeline in ('fixed', 'clahe', 'adaptive'):
        if pipeline == 'fixed':
            _, bw = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)
        elif pipeline == 'clahe':
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
            enhanced = clahe.apply(gray)
            _, bw = cv2.threshold(enhanced, 100, 255, cv2.THRESH_BINARY)
        else:
            bw = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 15, 5)

        big = cv2.resize(bw, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_CUBIC)
        candidate = pytesseract.image_to_string(
            Image.fromarray(big), config='--psm 6 --oem 3'
        ).strip().lower()

        if candidate and len(candidate) > len(text):
            text = candidate
        # If we already found call/raise keywords, stop early
        if any(kw in text for kw in ('call', 'raise', 'check', 'bet')):
            break

    if not text:
        return None

    log.debug(f"Button OCR fallback scan: {text!r}")

    keywords = [
        ('call', 'call'), ('check', 'check'),
        ('raise', 'raise'), ('rais', 'raise'),
        ('bet', 'raise'), ('fold', 'fold'),
    ]

    result = {}
    for keyword, btn_type in keywords:
        if btn_type in already_found or btn_type in result:
            continue
        if keyword not in text:
            continue

        data = pytesseract.image_to_data(
            Image.fromarray(big), config='--psm 6 --oem 3',
            output_type=pytesseract.Output.DICT
        )
        for i, word in enumerate(data['text']):
            if keyword in word.lower() and data['width'][i] > 10:
                tx = data['left'][i] // scale + rx1
                ty = data['top'][i] // scale + ry1
                tw = data['width'][i] // scale
                th = data['height'][i] // scale
                btn_w = max(tw * 3, W // 8)
                btn_h = max(th * 2, H // 15)
                btn_x = max(tx - btn_w // 4, rx1)
                btn_y = max(ty - btn_h // 4, ry1)
                center = (btn_x + btn_w // 2, btn_y + btn_h // 2)

                # Parse amount from the substring AFTER the keyword on the SAME LINE.
                # Multi-line OCR can include numbers from other screen elements.
                kw_pos = text.find(keyword)
                amount_text = text[kw_pos:] if kw_pos >= 0 else text
                amount_text = amount_text.split('\n')[0]  # Same line only
                amount = _parse_amount(amount_text)

                # If amount not found, try focused re-OCR on just this button
                # using multiple preprocessing pipelines and a digits whitelist.
                if amount is None and btn_type in ('call', 'raise'):
                    btn_crop = img[btn_y:btn_y + btn_h, btn_x:btn_x + btn_w]
                    if btn_crop.size > 0:
                        amount = _ocr_amount_robust(btn_crop, btn_type)
                        if amount is not None:
                            log.info(f"Focused re-OCR {btn_type}: → {amount}")

                result[btn_type] = {
                    'center': center,
                    'rect': (btn_x, btn_y, btn_w, btn_h),
                    'amount': amount,
                    'text': text,
                    'confidence': 0.7,
                    'color': 'dark_ocr',
                }
                log.debug(f"OCR fallback found {btn_type} at ({btn_x},{btn_y}) "
                          f"amount={amount}")
                break

    return result if result else None


_BUTTON_KEYWORDS = {'fold', 'fol', 'check', 'chec', 'call', 'cal',
                    'raise', 'rais', 'bet', 'all', 'deal'}

# Digits-only whitelist for amount OCR (no letters → fewer misreads)
_DIGITS_CONFIG = '--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789.,$'


def _ocr_amount_robust(crop: np.ndarray, context: str = "") -> Optional[float]:
    """Robustly OCR a numeric amount from a button/region crop.

    Tries every reasonable preprocessing pipeline:
      1. Fixed thresholds (180 down to 40)
      2. CLAHE contrast enhancement + thresholds
      3. Adaptive thresholding
      4. Per-channel extraction (R, G, B individually)

    Uses a digits-only whitelist to avoid letter misreads (e.g. "l" as "1").
    Returns the first successfully parsed amount, or None.
    """
    if not PYTESSERACT_AVAILABLE or crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    scale = 3
    pad = 10

    def _try_ocr(bw_img: np.ndarray) -> Optional[float]:
        big = cv2.resize(bw_img, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_CUBIC)
        padded = np.full((big.shape[0] + 2 * pad, big.shape[1] + 2 * pad),
                         0, dtype=np.uint8)
        padded[pad:pad + big.shape[0], pad:pad + big.shape[1]] = big
        txt = pytesseract.image_to_string(
            Image.fromarray(padded), config=_DIGITS_CONFIG).strip()
        if txt:
            val = _parse_amount(txt)
            if val is not None:
                log.debug(f"_ocr_amount_robust ({context}): {txt!r} → {val}")
                return val
        return None

    # 1. Fixed thresholds on raw grayscale
    for thresh in (180, 150, 120, 100, 80, 60, 40):
        _, bw = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
        if np.sum(bw > 0) < 10:
            continue
        result = _try_ocr(bw)
        if result is not None:
            return result

    # 2. CLAHE contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)
    for thresh in (140, 100, 70):
        _, bw = cv2.threshold(enhanced, thresh, 255, cv2.THRESH_BINARY)
        if np.sum(bw > 0) < 10:
            continue
        result = _try_ocr(bw)
        if result is not None:
            return result

    # 3. Adaptive thresholding
    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 15, 5)
    result = _try_ocr(adaptive)
    if result is not None:
        return result

    # 4. Per-channel extraction (for colored text on dark backgrounds)
    for ch_idx in range(3):
        ch = crop[:, :, ch_idx]
        for thresh in (120, 80):
            _, bw = cv2.threshold(ch, thresh, 255, cv2.THRESH_BINARY)
            if np.sum(bw > 0) < 10:
                continue
            result = _try_ocr(bw)
            if result is not None:
                return result

    return None


def _reocr_button_region(img: np.ndarray, x: int, y: int, w: int, h: int) -> Optional[float]:
    """Re-OCR a button region with REVERSED threshold order for double-read confirmation.

    Uses different preprocessing than the primary read to get an independent parse:
      - Reversed threshold order (low → high instead of high → low)
      - CLAHE with different clip limit
      - Inverted binary threshold

    Returns parsed amount or None.
    """
    if not PYTESSERACT_AVAILABLE:
        return None

    crop = img[y:y + h, x:x + w]
    if crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    scale = 3
    pad = 10

    def _try(bw_img: np.ndarray) -> Optional[float]:
        big = cv2.resize(bw_img, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_CUBIC)
        padded = np.full((big.shape[0] + 2 * pad, big.shape[1] + 2 * pad),
                         0, dtype=np.uint8)
        padded[pad:pad + big.shape[0], pad:pad + big.shape[1]] = big
        txt = pytesseract.image_to_string(
            Image.fromarray(padded), config=_DIGITS_CONFIG).strip()
        if txt:
            return _parse_amount(txt)
        return None

    # Reversed threshold order (low to high — opposite of _ocr_amount_robust)
    for thresh in (60, 100, 140, 180):
        _, bw = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
        if np.sum(bw > 0) < 10:
            continue
        result = _try(bw)
        if result is not None:
            return result

    # CLAHE with higher clip limit for different contrast response
    clahe = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    for thresh in (100, 150):
        _, bw = cv2.threshold(enhanced, thresh, 255, cv2.THRESH_BINARY)
        result = _try(bw)
        if result is not None:
            return result

    # Inverted binary (white text on dark → catch cases where normal misses)
    _, bw_inv = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
    result = _try(bw_inv)
    if result is not None:
        return result

    return None


def _prepare_for_ocr(gray: np.ndarray, thresh: int,
                     scale: int = 3, pad: int = 10) -> np.ndarray:
    """Binarize, scale up, and pad a grayscale image for Tesseract."""
    _, bw = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
    big = cv2.resize(bw, None, fx=scale, fy=scale,
                     interpolation=cv2.INTER_CUBIC)
    padded = np.full((big.shape[0] + 2 * pad, big.shape[1] + 2 * pad),
                     0, dtype=np.uint8)
    padded[pad:pad + big.shape[0], pad:pad + big.shape[1]] = big
    return padded


def _ocr_button_text(img: np.ndarray, x: int, y: int, w: int, h: int,
                     reverse_thresholds: bool = False,
                     ) -> Tuple[Optional[float], str]:
    """OCR text from a button region. Returns (amount, raw_text).

    FAST version: tries only 2 thresholds + 1 CLAHE fallback (max 3 Tesseract
    calls instead of 8). Exits immediately when any text is found.
    """
    if not PYTESSERACT_AVAILABLE:
        return None, ""

    crop = img[y:y + h, x:x + w]
    if crop.size == 0:
        return None, ""

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    scale = 3
    pad = 10

    # Try just 2 thresholds: high (bright text) and low (dim text)
    for thresh in (180, 110):
        padded = _prepare_for_ocr(gray, thresh, scale, pad)
        text = pytesseract.image_to_string(
            Image.fromarray(padded), config='--psm 6 --oem 3'
        ).strip()

        if text:
            lower = text.lower()
            if any(kw in lower for kw in _BUTTON_KEYWORDS):
                log.debug(f"Button OCR thresh={thresh}: {text!r}")
                amount = _parse_amount(text)
                return amount, text
            # Got text but no keyword — still return it (amount might parse)
            amount = _parse_amount(text)
            if amount is not None:
                return amount, text

    # CLAHE fallback for dark call button (gray text ~147 on black ~20)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)
    padded = _prepare_for_ocr(enhanced, 120, scale, pad)
    text = pytesseract.image_to_string(
        Image.fromarray(padded), config='--psm 6 --oem 3'
    ).strip()

    if text:
        amount = _parse_amount(text)
        return amount, text

    return None, ""


def _classify_button_text(text: str, color_type: str) -> str:
    """Determine actual button type from OCR text, falling back to color."""
    t = text.lower()
    # Non-action buttons — must be checked FIRST
    if 'deal' in t:
        return 'deal_me_in'
    if 'new' in t and 'hand' in t:
        return 'new_hand'
    if 'rabbit' in t or 'show' in t:
        return 'show_rabbit'
    if 'fold' in t or 'fol' in t:
        return 'fold'
    if 'check' in t or 'chec' in t:
        return 'check'
    if 'call' in t or 'cal' in t:
        return 'call'
    if 'raise' in t or 'rais' in t or 'bet' in t:
        return 'raise'
    if 'all' in t and 'in' in t:
        return 'all_in'
    # Fall back to color-based classification
    # Green can be call OR check — default to call (check has no amount)
    # Yellow buttons (Battle Royale theme) default to check
    if color_type == 'check_yellow':
        return 'check'
    return color_type


def _fix_ocr_missing_decimal(raw_num: str, text: str,
                             original_num_token: str = "") -> Optional[str]:
    """Fix OCR misreads where a decimal point is dropped.

    Tesseract often reads "1.0" as "10", "2.5" as "25", "1.00" as "100", etc.
    This is especially common on GGPoker's call/raise button text where the
    amount is rendered with thin decimal characters on a dark background.

    We only apply this heuristic when:
    - The text contains a call/raise keyword (not "all in" which can be large)
    - The number is a pure integer with 2-3 digits (no decimal already present)
    - The original number token in the OCR text had no comma (comma = large real value)
    - Inserting a decimal at position 1 yields a typical poker bet size

    Args:
        raw_num: The number string after comma removal (e.g. "10", "25", "100").
        text: The full OCR text (e.g. "Call 10").
        original_num_token: The number as matched from OCR before comma removal
                           (e.g. "1,200"). If it contained a comma, we skip.

    Returns corrected number string, or None if no correction needed.
    """
    lower = text.lower()

    # Only apply to call/raise/bet buttons, NOT all-in (which can be large)
    is_action_button = any(kw in lower for kw in ('call', 'raise', 'bet', 'rais', 'cal'))
    # Check for "all in" / "all-in" but NOT "call" which contains "all"
    is_all_in = bool(re.search(r'\ball[\s\-]?in\b', lower))
    if not is_action_button or is_all_in:
        return None

    # Only fix pure integers (no decimal already present in the raw number)
    if '.' in raw_num:
        return None

    # If the original OCR token had a comma (e.g. "1,200"), it's a real large
    # value — don't try to insert a decimal.
    if ',' in original_num_token:
        return None

    # Only fix 2-3 digit integers. Single digits are fine, 4+ digits are
    # either legitimately large or comma-formatted (handled above).
    if len(raw_num) < 2 or len(raw_num) > 3:
        return None

    try:
        int_val = int(raw_num)
    except ValueError:
        return None

    if int_val < 10:
        return None

    # Insert decimal after the first digit:
    # "10" -> "1.0", "15" -> "1.5", "25" -> "2.5", "100" -> "1.00", "250" -> "2.50"
    # Also try 4-digit: "1500" -> "15.00" (for larger Spin & Gold stacks)
    candidates_to_try = [
        raw_num[0] + '.' + raw_num[1:],        # "250" -> "2.50" (most common)
    ]
    if len(raw_num) == 4:
        candidates_to_try.append(raw_num[:2] + '.' + raw_num[2:])  # "1500" -> "15.00"

    for candidate in candidates_to_try:
        try:
            cval = float(candidate)
        except ValueError:
            continue
        # Accept any bet that's a typical poker size: 0.5 BB up to 99.99 BB
        if 0.5 <= cval < 100.0:
            log.info(f"OCR decimal fix: '{raw_num}' -> '{candidate}' "
                     f"(corrected={cval:.2f}) in text={text!r}")
            return candidate

    return None


def _parse_amount(text: str, max_expected: Optional[float] = None) -> Optional[float]:
    """Parse a dollar/chip amount from button text like 'Call 30' or 'Raise to 120'.

    Args:
        text: Raw OCR text from button.
        max_expected: If set, reject values exceeding this (OCR misread guard).
    """
    if not text:
        return None

    # Find numbers in the text
    # Handle formats: "30", "$30", "30.50", "1,200", "1.2K", "All-In 500"
    numbers = re.findall(r'[\d,]+(?:\.\d+)?(?:[KkMm])?', text)
    if not numbers:
        return None

    # Take the last number (usually the amount after "Call" / "Raise to")
    original_token = numbers[-1]  # Before comma removal (for decimal-fix check)
    num_str = original_token.replace(',', '')
    if not num_str:
        return None

    multiplier = 1.0
    if num_str[-1] in ('K', 'k'):
        multiplier = 1000.0
        num_str = num_str[:-1]
    elif num_str[-1] in ('M', 'm'):
        multiplier = 1000000.0
        num_str = num_str[:-1]

    # NOTE: OCR decimal-drop fix (e.g. "1.0" read as "10") is NOT applied here
    # because _parse_amount has no context about game state.  Instead, call
    # _fix_ocr_missing_decimal() at the call site when big-blind / pot context
    # is available to decide whether the fix should trigger.

    try:
        value = float(num_str) * multiplier
    except ValueError:
        return None

    if max_expected is not None and value > max_expected:
        log.warning(f"PARSE_AMOUNT: {value} exceeds max_expected {max_expected}, rejecting")
        return None

    return value


# ---------------------------------------------------------------------------
#  Player stack detection — OCR at each seat position
# ---------------------------------------------------------------------------

def _read_player_stacks(img: np.ndarray, W: int, H: int) -> List[PlayerInfo]:
    """Read stack amounts from all 6 seat positions.

    Returns a list of PlayerInfo for seats where a stack amount was found.
    Seat 0 is always hero (bottom center).
    """
    if not PYTESSERACT_AVAILABLE:
        return []

    players = []
    for seat_idx, (cx, cy, sw, sh) in enumerate(SEAT_REGIONS_6MAX):
        x1 = max(int((cx - sw / 2) * W), 0)
        x2 = min(int((cx + sw / 2) * W), W)
        y1 = max(int((cy - sh / 2) * H), 0)
        y2 = min(int((cy + sh / 2) * H), H)
        region = img[y1:y2, x1:x2]
        if region.size == 0:
            continue

        stack = _ocr_stack_value(region)
        if stack is not None and stack > 0:
            players.append(PlayerInfo(
                seat=seat_idx,
                name="",
                stack=stack,
                current_bet=0.0,
                is_active=True,
                is_hero=(seat_idx == 0),
            ))
            log.debug(f"Seat {seat_idx} stack: {stack} "
                      f"({x1},{y1})-({x2},{y2})")

    # Ensure hero (seat 0) is always present — if OCR failed to read the
    # stack, add hero with a default 100 BB so DecisionMaker doesn't trigger
    # "Low funds call everything" with myFunds=0.
    hero_stack_estimated = False
    if not any(p.is_hero for p in players):
        players.insert(0, PlayerInfo(
            seat=0, name="", stack=100.0, current_bet=0.0,
            is_active=True, is_hero=True,
        ))
        hero_stack_estimated = True
        log.debug("Hero stack OCR failed, using default 100 BB (estimated)")

    return players, hero_stack_estimated


# Regions where opponent cards appear (between seat and table center).
# Each entry: (x_center_pct, y_center_pct, width_pct, height_pct) or None.
# Card backs are dark red (H≈0-10, S>80, V=30-120) with the GG logo.
# Calibrated from seat positions: cards are roughly 30% toward table center.
OPPONENT_CARD_REGIONS_6MAX = [
    None,                             # Seat 0: hero — detected separately
    (0.16, 0.68, 0.10, 0.07),        # Seat 1: left-bottom
    (0.22, 0.42, 0.10, 0.07),        # Seat 2: left-top
    (0.50, 0.34, 0.10, 0.07),        # Seat 3: top center
    (0.78, 0.42, 0.10, 0.07),        # Seat 4: right-top
    (0.84, 0.68, 0.10, 0.07),        # Seat 5: right-bottom
]


def _count_opponents_in_hand(img: np.ndarray, W: int, H: int) -> int:
    """Count opponents with visible card backs (actually in the hand).

    GGPoker card backs are dark red (~RGB 80,20,20).
    In HSV: H=0-15, S>60, V=30-130 (darker than buttons which have V>130).
    Only players still in the hand show card backs. Folded seats are empty.

    Returns the number of opponent seats (1-5) with visible card backs.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    opponents_with_cards = 0

    for seat_idx, region_def in enumerate(OPPONENT_CARD_REGIONS_6MAX):
        if region_def is None:
            continue
        cx, cy, rw, rh = region_def
        x1 = max(int((cx - rw / 2) * W), 0)
        x2 = min(int((cx + rw / 2) * W), W)
        y1 = max(int((cy - rh / 2) * H), 0)
        y2 = min(int((cy + rh / 2) * H), H)

        region_hsv = hsv[y1:y2, x1:x2]
        if region_hsv.size == 0:
            continue

        # Dark red card backs: H in [0,15] or [165,180], S>60, V in [30,130]
        h, s, v = region_hsv[:, :, 0], region_hsv[:, :, 1], region_hsv[:, :, 2]
        mask = ((h <= 15) | (h >= 165)) & (s > 60) & (v > 30) & (v < 130)
        dark_red_frac = np.sum(mask) / max(mask.size, 1)

        if dark_red_frac > 0.08:  # >8% dark red pixels = card backs present
            opponents_with_cards += 1
            log.debug(f"Seat {seat_idx}: card backs detected ({dark_red_frac:.1%} dark red)")

    log.debug(f"Opponents in hand (card backs): {opponents_with_cards}")
    return opponents_with_cards


def _ocr_stack_value(region: np.ndarray) -> Optional[float]:
    """OCR a stack value from a small region. Returns the numeric value or None.

    GGPoker stacks are typically cyan text (RGB≈119,204,255) on dark bg.
    Uses a multi-pipeline approach to ensure reliable reads:
      1. Blue channel with fixed thresholds (fast path for cyan)
      2. Green channel and grayscale fallbacks
      3. CLAHE contrast enhancement (catches muted/faded text)
      4. Adaptive thresholding (handles uneven background)

    Optimization: skip OCR entirely if the region has too few bright pixels
    (empty seat / dark felt background).
    """
    # Trim 10% off each side horizontally to remove player badge frame
    # artifacts (rounded bracket shapes) that confuse tesseract.
    h_r, w_r = region.shape[:2]
    side_margin = max(int(w_r * 0.10), 2)
    region = region[:, side_margin:w_r - side_margin]

    # Quick brightness check — skip empty/dark regions.
    # Hero stack is bright cyan (B≈255), opponents are muted teal (B≈166).
    # Check if enough pixels have blue > 80 (well above dark felt ≈30).
    blue_ch = region[:, :, 2]
    if np.sum(blue_ch > 80) < 10:
        green_ch = region[:, :, 1]
        if np.sum(green_ch > 80) < 10:
            return None  # No text in this region — empty seat

    pad = 10

    # Fast path: blue channel at thresh=130 (catches both bright cyan and muted teal)
    # Scale 3 first (fast, "$" recognition reliable). Only retry at scale 4 if
    # scale 3 result looks like a dropped decimal (integer > 100 in a poker game).
    _, bw = cv2.threshold(blue_ch, 130, 255, cv2.THRESH_BINARY)
    if np.sum(bw > 0) >= 15:
        r3 = _ocr_single(bw, 3, pad)
        if r3 is not None:
            # If result is a suspiciously large integer (likely dropped decimal),
            # try scale 4 which handles "." better.
            if r3 == int(r3) and r3 > 100:
                r4 = _ocr_single(bw, 4, pad)
                if r4 is not None and r4 != int(r4):
                    return r4  # Scale 4 found the decimal
            return r3
        # Scale 3 failed entirely — try scale 4
        r4 = _ocr_single(bw, 4, pad)
        if r4 is not None:
            return r4

    # Fallback: green channel (catches opponent muted teal text)
    green_ch = region[:, :, 1]
    _, bw = cv2.threshold(green_ch, 100, 255, cv2.THRESH_BINARY)
    if np.sum(bw > 0) >= 15:
        result = _ocr_single(bw, 3, pad)
        if result is not None:
            return result

    # CLAHE fallback for very faded text
    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)
    _, bw = cv2.threshold(enhanced, 100, 255, cv2.THRESH_BINARY)
    if np.sum(bw > 0) >= 10:
        result = _ocr_single(bw, 3, pad)
        if result is not None:
            return result

    return None


def _ocr_single(bw: np.ndarray, scale: int, pad: int) -> Optional[float]:
    """Run OCR on a single binarized image and parse the amount.

    Uses full charset first (recognizes '$' correctly), falls back to
    digit whitelist if no amount is found.
    """
    big = cv2.resize(bw, None, fx=scale, fy=scale,
                     interpolation=cv2.INTER_CUBIC)
    padded = np.full((big.shape[0] + 2 * pad, big.shape[1] + 2 * pad),
                     0, dtype=np.uint8)
    padded[pad:pad + big.shape[0], pad:pad + big.shape[1]] = big

    img_pil = Image.fromarray(padded)

    # Pass 1: full charset — recognizes "$" correctly, _parse_amount strips it
    text = pytesseract.image_to_string(
        img_pil, config='--psm 7 --oem 3'
    ).strip()
    if text:
        result = _parse_amount(text)
        if result is not None:
            return result

    # Pass 2: digit whitelist — forces numeric interpretation when full charset
    # couldn't find a parseable number (e.g. low contrast causing letter misreads)
    text2 = pytesseract.image_to_string(
        img_pil,
        config=r'--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789.,'
    ).strip()
    if text2:
        return _parse_amount(text2)

    return None


# ---------------------------------------------------------------------------
#  Dealer button detection — yellow circle on the felt
# ---------------------------------------------------------------------------

def _detect_dealer_button(img: np.ndarray, W: int, H: int) -> Tuple[int, float, float]:
    """Find the dealer button (yellow 'D' circle) on the felt.

    Returns (nearest_seat, x_pct, y_pct) or (-1, 0, 0) if not found.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

    # Bright yellow: H=18-40, S>100, V>180
    yellow_mask = cv2.inRange(hsv, np.array([18, 100, 180]),
                              np.array([40, 255, 255]))

    # Only search within the felt area
    felt_mask = np.zeros_like(yellow_mask)
    y1 = int(H * DEALER_Y_MIN)
    y2 = int(H * DEALER_Y_MAX)
    x1 = int(W * DEALER_X_MIN)
    x2 = int(W * DEALER_X_MAX)
    felt_mask[y1:y2, x1:x2] = yellow_mask[y1:y2, x1:x2]

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    felt_mask = cv2.morphologyEx(felt_mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(felt_mask, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)

    # Dealer button is a ~25-45px near-circular blob
    best = None
    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        rect_area = bw * bh
        if rect_area < 200 or bw < 15 or bh < 15:
            continue
        if bw > 60 or bh > 60:
            continue
        aspect = bw / max(bh, 1)
        if aspect < 0.5 or aspect > 2.0:
            continue
        # Circularity: actual area vs bounding box (circle ~0.78)
        fill = area / max(rect_area, 1)
        if fill < 0.4:
            continue
        # Prefer the most circular, well-filled blob
        score = fill * area
        if best is None or score > best[0]:
            best = (score, bx + bw / 2, by + bh / 2)

    if best is None:
        return -1, 0.0, 0.0

    _, dx, dy = best
    dx_pct = dx / W
    dy_pct = dy / H

    # Map to nearest seat
    min_dist = float('inf')
    nearest = -1
    for i, (sx, sy, _, _) in enumerate(SEAT_REGIONS_6MAX):
        dist = ((dx_pct - sx) ** 2 + (dy_pct - sy) ** 2) ** 0.5
        if dist < min_dist:
            min_dist = dist
            nearest = i

    log.debug(f"Dealer button at ({dx_pct:.2f}, {dy_pct:.2f}) -> seat {nearest}")
    return nearest, dx_pct, dy_pct


def _hero_position(hero_seat: int, dealer_seat: int, num_players: int) -> str:
    """Determine hero's position name relative to the dealer.

    Returns one of: 'BTN', 'SB', 'BB', 'UTG', 'MP', 'CO'.
    """
    if dealer_seat < 0 or num_players < 2:
        return 'UNKNOWN'

    # Positions clockwise from dealer: BTN, SB, BB, UTG, MP, CO
    # Distance from dealer to hero (clockwise seats)
    dist = (hero_seat - dealer_seat) % num_players

    if num_players == 2:
        # Heads-up: dealer=SB, other=BB
        return 'SB' if dist == 0 else 'BB'
    elif num_players == 3:
        names = ['BTN', 'SB', 'BB']
    elif num_players == 4:
        names = ['BTN', 'SB', 'BB', 'UTG']
    elif num_players == 5:
        names = ['BTN', 'SB', 'BB', 'UTG', 'CO']
    elif num_players == 6:
        names = ['BTN', 'SB', 'BB', 'UTG', 'MP', 'CO']
    elif num_players == 7:
        names = ['BTN', 'SB', 'BB', 'UTG', 'UTG', 'MP', 'CO']
    elif num_players == 8:
        names = ['BTN', 'SB', 'BB', 'UTG', 'UTG', 'MP', 'MP', 'CO']
    else:  # 9+
        names = ['BTN', 'SB', 'BB', 'UTG', 'UTG', 'MP', 'MP', 'CO', 'CO']

    return names[dist] if dist < len(names) else 'UTG'


# ---------------------------------------------------------------------------
#  Pot detection — OCR in top-center
# ---------------------------------------------------------------------------

def _read_pot(img: np.ndarray, W: int, H: int) -> float:
    """Read pot amount from the top-center of the table.

    GGPoker pot text is yellow/white on green felt ("Total Pot : $X.XX").
    Uses multiple preprocessing pipelines to ensure reliable reads:
      1. Fixed thresholds on grayscale (fast path)
      2. Yellow channel isolation (R+G high, B low — targets yellow text)
      3. CLAHE contrast enhancement
      4. Adaptive thresholding
    """
    if not PYTESSERACT_AVAILABLE:
        return 0.0

    y1 = int(H * POT_Y_MIN)
    y2 = int(H * POT_Y_MAX)
    x1 = int(W * POT_X_MIN)
    x2 = int(W * POT_X_MAX)
    region = img[y1:y2, x1:x2]

    if region.size == 0:
        return 0.0

    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    scale = 2
    pad = 10

    def _try_pot_ocr(bw: np.ndarray, label: str) -> Optional[float]:
        big = cv2.resize(bw, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_CUBIC)
        padded = np.full((big.shape[0] + 2 * pad, big.shape[1] + 2 * pad),
                         0, dtype=np.uint8)
        padded[pad:pad + big.shape[0], pad:pad + big.shape[1]] = big
        text = pytesseract.image_to_string(
            Image.fromarray(padded), config='--psm 6 --oem 3'
        ).strip()
        if not text:
            return None
        # Prefer lines with "pot" or "total"
        for line in text.split('\n'):
            if 'pot' in line.lower() or 'total' in line.lower():
                amount = _parse_amount(line)
                if amount is not None:
                    log.debug(f"Pot OCR ({label}): {line!r} -> {amount}")
                    return amount
        # Fallback: any amount in the text
        amount = _parse_amount(text)
        if amount is not None:
            log.debug(f"Pot OCR fallback ({label}): {text!r} -> {amount}")
            return amount
        return None

    # Pipeline 1: yellow channel (best for GGPoker yellow pot text)
    r_ch, g_ch = region[:, :, 0], region[:, :, 1]
    yellow = ((r_ch.astype(int) + g_ch.astype(int)) // 2).astype(np.uint8)
    _, bw = cv2.threshold(yellow, 140, 255, cv2.THRESH_BINARY)
    result = _try_pot_ocr(bw, 'yellow@140')
    if result is not None:
        return result

    # Pipeline 2: grayscale at 160
    _, bw = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)
    result = _try_pot_ocr(bw, 'gray@160')
    if result is not None:
        return result

    # Pipeline 3: CLAHE fallback
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)
    _, bw = cv2.threshold(enhanced, 120, 255, cv2.THRESH_BINARY)
    result = _try_pot_ocr(bw, 'clahe@120')
    if result is not None:
        return result

    log.warning("Pot OCR: all pipelines failed, returning 0")
    return 0.0


# ---------------------------------------------------------------------------
#  Board card detection — white blobs in center
# ---------------------------------------------------------------------------

def _detect_board_cards(img: np.ndarray, W: int, H: int) -> List[str]:
    """Detect community cards on the board (center of table).

    Supports both deck styles:
      - White cards with colored text (classic)
      - Colored cards with white text (4-color deck)

    Tries colored detection first (more reliable on GGPoker), falls back to white.
    """
    y1 = int(H * BOARD_Y_MIN)
    y2 = int(H * BOARD_Y_MAX)
    x1 = int(W * BOARD_X_MIN)
    x2 = int(W * BOARD_X_MAX)

    # Try colored cards first (GGPoker 4-color deck)
    colored_cards = _detect_board_colored(img, W, H, x1, y1, x2, y2)
    if len(colored_cards) >= 3:
        return colored_cards

    # Fallback: try white cards
    white_cards = _detect_board_white(img, W, H, x1, y1, x2, y2)
    # Return whichever found more
    result = colored_cards if len(colored_cards) > len(white_cards) else white_cards

    if len(result) == 0 and (len(colored_cards) > 0 or len(white_cards) > 0):
        log.warning(f"Board card detection partial: colored={len(colored_cards)} white={len(white_cards)}")
    elif len(result) == 0:
        log.debug(f"Board card detection: no cards found in region x={x1}-{x2} y={y1}-{y2}")

    return result


def _rescue_clubs_from_felt(
    search: np.ndarray, mask: np.ndarray,
    bx: int, by: int, bw: int, bh: int,
    min_card_w: float, min_card_h: float, max_card_w: float,
    x1: int, y1: int,
    candidates: list,
) -> None:
    """Extract club card(s) from an oversized green blob that merged with felt.

    The green card background (H~42 S~105 V~149) passes the clubs HSV mask,
    but so does the green felt when it's brighter than V=120.  The combined
    contour is too wide for the max_card_w check, so the card is missed.

    Strategy: slide a card-width window across the blob and look for columns
    with high white-pixel density (the rank/suit text on the card).
    """
    sub_rgb = search[by:by + bh, bx:bx + bw]
    if sub_rgb.size == 0:
        return

    # White text mask within this blob
    white = np.all(sub_rgb > 180, axis=2)
    col_white = np.sum(white, axis=0).astype(float)

    # Smooth to find peaks (card regions have concentrated white text)
    window = max(int(max_card_w * 0.3), 5)
    if len(col_white) < window:
        return
    smoothed = np.convolve(col_white, np.ones(window) / window, mode='same')

    # Find peaks above a threshold
    threshold = max(smoothed.max() * 0.3, 3)
    above = smoothed > threshold

    # Find contiguous runs of above-threshold columns
    runs = []
    start = None
    for i in range(len(above)):
        if above[i] and start is None:
            start = i
        elif not above[i] and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(above)))

    for rs, re in runs:
        rw = re - rs
        if rw < min_card_w or rw > max_card_w * 1.5:
            continue
        # Estimate card boundaries: expand slightly around the white-text region
        pad = int(rw * 0.3)
        card_x = max(rs - pad, 0)
        card_right = min(re + pad, bw)
        card_w = card_right - card_x
        if card_w < min_card_w or card_w > max_card_w * 1.5:
            continue

        # Verify: must have enough white pixels (rank text)
        card_region = sub_rgb[:, card_x:card_right]
        white_frac = float(np.sum(np.all(card_region > 180, axis=2))) / max(bh * card_w, 1)
        if white_frac < 0.02:
            continue

        aspect = bh / max(card_w, 1)
        if aspect < 0.8 or aspect > 2.5:
            continue

        candidates.append((bx + card_x + x1, by + y1, card_w, bh, 'C'))
        log.info(f"CLUBS FELT-MERGE RESCUE: found card at ({bx + card_x},{by}) "
                 f"{card_w}x{bh} white={white_frac:.3f} in oversized {bw}px blob")


def _detect_board_colored(
    img: np.ndarray, W: int, H: int,
    x1: int, y1: int, x2: int, y2: int,
) -> List[str]:
    """Find board cards by color (4-color deck: blue/red/green/black backgrounds)."""
    from gamble.ocr.card_reader import (
        _read_rank_at, _detect_suit_colored, STYLE_COLORED,
    )

    search = img[y1:y2, x1:x2]
    if search.size == 0:
        return []

    hsv = cv2.cvtColor(search, cv2.COLOR_RGB2HSV)
    h_ch, s_ch, v_ch = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    suit_masks = {
        'D': (h_ch >= 95) & (h_ch <= 125) & (s_ch > 100) & (v_ch > 50),
        'H': ((h_ch < 10) | (h_ch > 168)) & (s_ch > 100) & (v_ch > 120),
        'C': (h_ch >= 30) & (h_ch <= 85) & (s_ch > 60) & (v_ch > 120),
        'S': (v_ch < 55) & (s_ch < 60) & (v_ch > 15),
    }

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (8, 8))
    min_card_h = H * 0.06
    min_card_w = W * 0.03
    max_card_w = W * 0.12

    candidates = []
    for suit, mask in suit_masks.items():
        if int(np.sum(mask)) < 200:
            continue
        binary = mask.astype(np.uint8) * 255
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            bx, by, bw, bh = cv2.boundingRect(c)
            aspect = bh / max(bw, 1)

            # --- Clubs felt-merge rescue ---
            # Green (clubs) card backgrounds often merge with the green felt
            # into one massive blob that fails the max_card_w check.
            # Scan the oversized blob for card-shaped sub-regions with white text.
            if suit == 'C' and bw >= max_card_w and bh > min_card_h:
                _rescue_clubs_from_felt(
                    search, closed, bx, by, bw, bh,
                    min_card_w, min_card_h, max_card_w,
                    x1, y1, candidates,
                )
                continue

            if (bh > min_card_h and bw > min_card_w and bw < max_card_w
                    and 1.0 < aspect < 2.0):
                # For spades: reject oversized dark blobs (table background)
                if suit == 'S':
                    blob_area = bw * bh
                    max_area = W * H * 0.015  # single board card is small
                    if blob_area > max_area:
                        log.debug(f"Board spade blob rejected: area {blob_area}")
                        continue
                    # Require white text pixels
                    blob_rgb = search[by:by + bh, bx:bx + bw]
                    if blob_rgb.size > 0:
                        wf = np.sum(np.all(blob_rgb > 180, axis=2)) / max(blob_area, 1)
                        if wf < 0.03:
                            continue
                candidates.append((bx + x1, by + y1, bw, bh, suit))

    if not candidates:
        return []

    # Filter: board cards are all at roughly the same Y position.
    # Find the dominant Y band by clustering.
    candidates.sort(key=lambda c: c[1])  # sort by y
    if len(candidates) >= 2:
        # Use the median Y as reference
        ys = [c[1] for c in candidates]
        median_y = sorted(ys)[len(ys) // 2]
        # Keep only cards within a reasonable Y band of the median
        y_tolerance = H * 0.05
        candidates = [c for c in candidates
                      if abs(c[1] - median_y) < y_tolerance]

    # Deduplicate overlapping detections (same card detected by multiple suits)
    candidates.sort(key=lambda c: c[0])  # sort by x
    deduped = []
    for cand in candidates:
        cx_center = cand[0] + cand[2] / 2
        overlap = False
        for existing in deduped:
            ex_center = existing[0] + existing[2] / 2
            if abs(cx_center - ex_center) < W * 0.03:
                # Keep the one with larger area
                if cand[2] * cand[3] > existing[2] * existing[3]:
                    deduped.remove(existing)
                    deduped.append(cand)
                overlap = True
                break
        if not overlap:
            deduped.append(cand)

    deduped.sort(key=lambda c: c[0])  # sort left to right
    deduped = deduped[:5]  # max 5 board cards

    board = []
    for bx, by, bw, bh, suit in deduped:
        # Try BOTH corner and center rank, then pick the best.
        # Corner is cleaner (no suit symbol) but very small → OCR struggles.
        # Center is larger but may include the suit symbol → confuses OCR.
        margin_x = max(int(bw * 0.07), 3)
        margin_y = max(int(bh * 0.03), 2)
        corner_w = max(int(bw * 0.45), 15)
        corner_h = max(int(bh * 0.22), 10)
        corner_box = (bx + margin_x, by + margin_y, corner_w, corner_h)
        corner_rank = _read_rank_at(img, corner_box, STYLE_COLORED)

        center_x = bx + int(bw * 0.15)
        center_y = by + int(bh * 0.40)
        center_w = int(bw * 0.70)
        center_h = int(bh * 0.50)
        center_box = (center_x, center_y, center_w, center_h)
        center_rank = _read_rank_at(img, center_box, STYLE_COLORED)

        # Pick the best rank:
        # - If both agree, use that.
        # - If only one succeeded, use it.
        # - If they disagree, prefer corner (less noise) UNLESS corner
        #   returned "10" (common misread of "9" as "0"→"10") and center
        #   returned a single digit — trust center in that case.
        if corner_rank and center_rank:
            if corner_rank == center_rank:
                rank = corner_rank
            elif corner_rank == '10' and center_rank != '10':
                rank = center_rank  # "0"→"10" is often a misread "9"
            else:
                rank = corner_rank  # corner is generally cleaner
        else:
            rank = corner_rank or center_rank

        # Rescue: try an alternate center crop when detection is uncertain.
        # Characters like "J" have descenders the standard crop clips, and
        # corner often misreads "J" as "0"→"10" (the J-hook looks like 0).
        # Start at 25% from left to skip the small corner suit symbol, and
        # use 65% height to capture descenders.
        if not rank or (rank == '10' and not center_rank):
            alt_x = bx + int(bw * 0.25)
            alt_y = by + int(bh * 0.30)
            alt_w = int(bw * 0.70)
            alt_h = int(bh * 0.65)
            alt_rank = _read_rank_at(img, (alt_x, alt_y, alt_w, alt_h),
                                     STYLE_COLORED)
            if alt_rank:
                rank = alt_rank

        # Verify suit from background color of the card body
        body_margin = max(int(bw * 0.08), 3)
        body_box = (bx + body_margin, by + int(bh * 0.2),
                    max(int(bw * 0.6), 15), max(int(bh * 0.6), 15))
        verified_suit = _detect_suit_colored(img, body_box)
        if verified_suit != '?':
            suit = verified_suit

        # Double-check 6↔A confusion: re-read with looser binarization
        # The "6" glyph can lose its bottom loop on red/blue backgrounds
        # when the binarization threshold (min_ch > 170) clips it, making
        # it look like "A" to both template matcher and OCR.
        if rank == 'A':
            rank = _verify_not_six(img, bx, by, bw, bh, rank)

        if rank:
            if rank == '10':
                rank = 'T'
            board.append(f"{rank}{suit}")
            log.debug(f"Board card (colored): {rank}{suit} at ({bx},{by}) {bw}x{bh}")

    return board


def _verify_not_six(img: np.ndarray, bx: int, by: int, bw: int, bh: int,
                    original_rank: str) -> str:
    """Verify a board card read as 'A' isn't actually '6'.

    The '6' glyph loses its bottom loop on red/blue colored backgrounds when
    binarization clips the near-white pixels, making it look like 'A'.

    Strategy: re-binarize with a lower threshold and compare template scores.
    Also check structural features (6 has enclosed bottom loop, A doesn't).
    """
    from gamble.ocr.card_reader import STYLE_COLORED
    from gamble.ocr.rank_templates import get_rank_matcher

    # Re-crop the corner rank region with generous margins
    margin_x = max(int(bw * 0.07), 3)
    margin_y = max(int(bh * 0.03), 2)
    corner_w = max(int(bw * 0.45), 15)
    corner_h = max(int(bh * 0.22), 10)
    rx, ry = bx + margin_x, by + margin_y
    max_y = min(ry + corner_h, img.shape[0])
    max_x = min(rx + corner_w, img.shape[1])
    crop = img[ry:max_y, rx:max_x]
    if crop.size == 0:
        return original_rank

    # Binarize with LOWER threshold (min_ch > 140 instead of 170)
    # This captures more of the glyph's detail on colored backgrounds
    r, g, b = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    min_ch = np.minimum(np.minimum(r, g), b)
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)

    # Try multiple thresholds
    for thresh in [140, 120, 150]:
        is_text = (min_ch > thresh) | (gray > (thresh + 10))
        bin_img = np.where(is_text, np.uint8(0), np.uint8(255))
        _, bin_img = cv2.threshold(bin_img, 127, 255, cv2.THRESH_BINARY)

        matcher = get_rank_matcher()
        result = matcher.match_rank(bin_img)
        if result == '6':
            log.info(f"BOARD 6↔A FIX: '{original_rank}' → '6' at ({bx},{by}) "
                     f"using threshold {thresh}")
            return '6'

    # Structural check: in the bottom 40% of the glyph, "6" has an enclosed
    # circular loop while "A" has open legs. Check the ratio of black pixels
    # in the bottom-center region.
    best_bw = np.where((min_ch > 140) | (gray > 150), np.uint8(0), np.uint8(255))
    _, best_bw = cv2.threshold(best_bw, 127, 255, cv2.THRESH_BINARY)
    h_bw, w_bw = best_bw.shape[:2]
    if h_bw > 8 and w_bw > 6:
        bottom = best_bw[int(h_bw * 0.55):, int(w_bw * 0.2):int(w_bw * 0.8)]
        if bottom.size > 0:
            black_ratio = np.sum(bottom == 0) / bottom.size
            # "6" bottom loop: lots of black pixels (0.25-0.60)
            # "A" open legs: fewer centered black pixels (0.10-0.25)
            if black_ratio > 0.30:
                log.info(f"BOARD 6↔A FIX (structural): '{original_rank}' → '6' "
                         f"at ({bx},{by}) bottom_black={black_ratio:.2f}")
                return '6'

    return original_rank


def _detect_board_white(
    img: np.ndarray, W: int, H: int,
    x1: int, y1: int, x2: int, y2: int,
) -> List[str]:
    """Find board cards by white rectangle detection (classic deck style)."""
    from gamble.ocr.card_reader import _read_rank_at, _detect_suit_at, STYLE_WHITE

    search = img[y1:y2, x1:x2]
    if search.size == 0:
        return []

    white = np.all(search > 160, axis=2).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(white, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)

    min_card_h = H * 0.04
    min_card_w = W * 0.02
    max_card_w = W * 0.08

    card_blobs = []
    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)
        aspect = bh / max(bw, 1)
        if (bh > min_card_h and bw > min_card_w and bw < max_card_w
                and 0.5 < aspect < 3.0):
            card_blobs.append((bx + x1, by + y1, bw, bh))

    if not card_blobs:
        return []

    card_blobs.sort(key=lambda b: b[0])
    card_blobs = card_blobs[:5]

    board = []
    for bx, by, bw, bh in card_blobs:
        rank_w = max(int(bw * 0.45), 10)
        rank_h = max(int(bh * 0.30), 8)
        margin = max(int(bw * 0.05), 1)

        rank_box = (bx + margin, by + margin, rank_w, rank_h)
        rank = _read_rank_at(img, rank_box, STYLE_WHITE)

        suit = _detect_suit_at(img, rank_box)
        if suit == '?':
            suit_y = by + int(bh * 0.30)
            suit_box = (bx + margin, suit_y, int(bw * 0.35), int(bh * 0.18))
            suit = _detect_suit_at(img, suit_box)

        if rank and suit != '?':
            if rank == '10':
                rank = 'T'
            board.append(f"{rank}{suit}")
            log.debug(f"Board card (white): {rank}{suit} at ({bx},{by})")

    return board


# ---------------------------------------------------------------------------
#  Utility
# ---------------------------------------------------------------------------

def _parse_blinds(title: str) -> Tuple[float, float]:
    """Extract blinds from window title.

    Handles formats:
        "Spin & Gold $0.25 - Blinds 15 | 30"
        "Rush & Cash - $0.05 / $0.10"
    """
    # Format: "Blinds X | Y"
    match = re.search(r'Blinds\s+(\d+(?:\.\d+)?)\s*\|\s*(\d+(?:\.\d+)?)', title)
    if match:
        return float(match.group(1)), float(match.group(2))

    # Format: "$X / $Y" (Rush & Cash style)
    match = re.search(r'\$(\d+(?:\.\d+)?)\s*/\s*\$(\d+(?:\.\d+)?)', title)
    if match:
        return float(match.group(1)), float(match.group(2))

    return 0.0, 0.0


def _street_from_board(board_cards: List[str]) -> Street:
    n = len(board_cards)
    if n == 0:
        return Street.PREFLOP
    elif n <= 3:
        # 1-2 cards = partial flop detection by OCR, treat as Flop
        return Street.FLOP
    elif n == 4:
        return Street.TURN
    elif n >= 5:
        return Street.RIVER
    return Street.UNKNOWN


def _save_debug(
    img: np.ndarray, W: int, H: int,
    buttons: Dict, button_rects: Dict,
    board_cards: List[str], pot: float,
    debug_dir: str,
) -> None:
    """Save annotated debug image."""
    import os
    from datetime import datetime

    os.makedirs(debug_dir, exist_ok=True)
    annotated = img.copy()

    # Draw button search region
    by1, by2 = int(H * BUTTON_Y_MIN), int(H * BUTTON_Y_MAX)
    bx1, bx2 = int(W * BUTTON_X_MIN), int(W * BUTTON_X_MAX)
    cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (128, 128, 0), 1)

    # Draw pot region
    py1, py2 = int(H * POT_Y_MIN), int(H * POT_Y_MAX)
    px1, px2 = int(W * POT_X_MIN), int(W * POT_X_MAX)
    cv2.rectangle(annotated, (px1, py1), (px2, py2), (0, 128, 128), 1)

    # Draw detected buttons
    btn_colors = {'call': (0, 255, 0), 'check': (0, 255, 0),
                  'raise': (0, 165, 255), 'fold': (128, 128, 128),
                  'all_in': (0, 0, 255)}
    for btn_type, rect in button_rects.items():
        x, y, w, h = rect
        color = btn_colors.get(btn_type, (255, 255, 0))
        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
        label = f"{btn_type}"
        if btn_type in buttons and buttons[btn_type].get('amount'):
            label += f" {buttons[btn_type]['amount']}"
        cv2.putText(annotated, label, (x, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    # Label
    label = f"Pot={pot} Board={board_cards} Btns={list(buttons.keys())}"
    cv2.putText(annotated, label, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(debug_dir, f'table_debug_{ts}.png')
    Image.fromarray(annotated).save(path)
    log.info(f"Table debug saved: {path}")


# ---------------------------------------------------------------------------
#  CLI test entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(message)s')

    if len(sys.argv) < 2:
        print("Usage: python -m gamble.ocr.table_reader <screenshot.png> [--debug]")
        sys.exit(1)

    debug = '--debug' in sys.argv
    paths = [a for a in sys.argv[1:] if not a.startswith('--')]

    for path in paths:
        img = Image.open(path)
        print(f"\n{path} ({img.width}x{img.height})")

        state = read_table(
            img,
            debug_dir='/tmp/table_debug' if debug else None,
        )

        print(f"  Cards: {state.my_cards}")
        print(f"  Board: {state.board_cards}")
        print(f"  Street: {state.street.value}")
        print(f"  Pot: {state.pot}")
        print(f"  Buttons: {[a.action_type for a in state.available_actions]}")
        print(f"  Amounts: {[(a.action_type, a.amount) for a in state.available_actions]}")
        print(f"  My turn: {state.is_my_turn}")
        print(f"  Latency: {state.ocr_latency_ms:.0f}ms")
