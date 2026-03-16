"""Full autonomous table reader — reads complete game state from a screenshot.

Detects cards, buttons (fold/call/raise), pot, stacks, blinds, and board cards.
Works regardless of table size using percentage-based regions and color detection.

Usage:
    from sys_core.ocr.table_reader import read_table
    state = read_table(table_pil_image, window_name="Spin & Gold $0.25 - Blinds 15 | 30")

The returned GameState contains everything needed to make a decision.
"""

import copy
import logging
import re
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from sys_core.ocr.card_reader import read_player_cards, _pixel_hash_cache
from sys_core.ocr.game_state import AvailableAction, GameState, PlayerInfo, ReadConfidence, Street

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

log = logging.getLogger(__name__)

# --- ULTRA-FAST OCR CACHE ---
# Maps window_id -> {'hash': str, 'cards': List[str]}
_CARD_CACHE = {}
_BOARD_CACHE = {}
# Cache last-known stacks per window to avoid re-OCR on preflop
_STACK_CACHE: Dict[int, List[PlayerInfo]] = {}
# Hash of stack regions for pixel-level change detection
_STACK_HASH_CACHE: Dict[int, int] = {}
# Hash-based pot cache to avoid re-OCR when pot area unchanged
_POT_CACHE: Dict[int, Tuple[int, float]] = {}  # window_id -> (hash, pot_value)
# Per-call OCR cache: cleared at start of each read_table() call
_OCR_CACHE: Dict[Tuple[int, int, int, int], Tuple[Optional[float], str]] = {}
# Button result cache — buttons don't change within a hand frame.
# Hash the button region pixels; if unchanged, reuse cached OCR results.
# window_id -> (pixel_hash, buttons_dict, button_rects_dict)
_BUTTON_CACHE: Dict[int, Tuple[int, Dict, Dict]] = {}
# Position cache: blind text only visible preflop; cache for postflop streets.
# window_id -> (hero_cards_key, sb_seat, bb_seat, position_str)
# hero_cards_key ties the cache to the current hand (cards change → new hand).
_POSITION_CACHE: Dict[int, Tuple[str, int, int, str]] = {}

# ---------------------------------------------------------------------------
#  Region definitions (percentage of table image)
# ---------------------------------------------------------------------------

# Button search region (bottom portion of table)
# Standard buttons are at ~0.85, but we search from 0.50 to catch 
# "Deal Me In", "Are you sure?", and the bet slider area.
BUTTON_Y_MIN = 0.50
BUTTON_Y_MAX = 0.98
BUTTON_X_MIN = 0.30 # Action buttons start around x=0.35 on tournament tables, x=0.50 on Rush & Cash
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
    # (x_center, y_center, width, height) as fractions of table image.
    # Stack text is cyan on dark background, below the player avatar.
    # Re-calibrated Mar 14 2026 from live Rush & Cash 1700x1230 screenshots.
    # Seats 2 & 4 (left-top, right-top) were shifted: x and y adjusted to
    # center on the stack number text instead of the avatar area.
    # Height increased from 0.040 to 0.060 for opponent seats — the thin
    # muted-teal text needs more vertical pixels to avoid clipping character
    # bottoms (which caused "0" → "U", "5" → "J" OCR errors).
    (0.500, 0.930, 0.14, 0.040),  # Seat 0: Hero (bottom center) — bright cyan, 0.040 is fine
    (0.068, 0.765, 0.16, 0.060),  # Seat 1: Left-bottom
    (0.150, 0.370, 0.16, 0.060),  # Seat 2: Left-top  (was x=0.115 y=0.378 h=0.040)
    (0.500, 0.268, 0.16, 0.060),  # Seat 3: Top center
    (0.870, 0.370, 0.16, 0.060),  # Seat 4: Right-top (was x=0.888 y=0.378 h=0.040)
    (0.915, 0.765, 0.16, 0.060),  # Seat 5: Right-bottom
]

# 9-max layout for tournaments (GGMasters, WSOP, etc.)
# Calibrated from $250 Mini Main Event screenshot (Mar 15 2026, 1706x1244).
SEAT_REGIONS_9MAX = [
    (0.500, 0.900, 0.14, 0.040),  # Seat 0: Hero (bottom center)
    (0.180, 0.760, 0.16, 0.060),  # Seat 1: Left-bottom
    (0.060, 0.480, 0.16, 0.060),  # Seat 2: Left-middle
    (0.220, 0.260, 0.16, 0.060),  # Seat 3: Left-top
    (0.500, 0.200, 0.16, 0.060),  # Seat 4: Top center
    (0.780, 0.260, 0.16, 0.060),  # Seat 5: Right-top
    (0.940, 0.480, 0.16, 0.060),  # Seat 6: Right-middle
    (0.780, 0.760, 0.16, 0.060),  # Seat 7: Right-bottom
    (0.500, 0.900, 0.14, 0.040),  # Seat 8: (alias for seat 0 in 8-max)
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
        # GGSystem action buttons are ALL dark red/maroon: H=10-16, S=130-200, V=130-200
        # Fold H~12, Call H~13, Raise H~14 — all same color, distinguished by OCR text
        'lower': np.array([0, 80, 90]),
        'upper': np.array([18, 255, 255]),
        'label': 'dark_red',
    },
    'check_yellow': {
        # Yellow/gold buttons in Battle Royale and other themed tables
        # Fills the gap between dark_red (H<=18) and green (H>=35)
        'lower': np.array([18, 80, 140]),
        'upper': np.array([35, 255, 255]),
        'label': 'yellow',
    },
}

# SEPARATE Deal Me In Range to prevent interference with dark_red action buttons
DEAL_ME_IN_HSV = {
    'deal_me_in': {
        # Bright red/salmon "Deal Me In" / "I'm Back" buttons
        # Tightened S/V minimums: real button is bright (S>120, V>150).
        # UI decorations (profile borders, red accents) are duller (S=80-120, V=80-140).
        'lower': np.array([0, 120, 150]),
        'upper': np.array([12, 255, 255]),
        'label': 'red',
    },
    'deal_me_in_green': {
        # Bright green "Deal Me In" / "I'm Back" buttons (some table themes)
        # Same green range as action buttons but only searched during deal_me_in_only scans,
        # so it won't interfere with normal action button detection.
        # OCR classification will confirm the text says "Deal" before acting.
        'lower': np.array([35, 100, 140]),
        'upper': np.array([85, 255, 255]),
        'label': 'green',
    },
}

# GGSystem's call button is near-black with faint gray text.
# Too dark for reliable HSV detection — we detect it via OCR instead.

# Minimum button area in pixels (scales with table size)
# Real GGSystem action buttons are ~200x80+ px on a 1230px-wide table = ~2.1% of table area.
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

    # Clear per-call OCR cache so stale results don't leak across calls
    global _OCR_CACHE
    _OCR_CACHE = {}

    W, H = table_img.width, table_img.height
    img = np.array(table_img)
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]

    # 1. Buttons FIRST (fast: ~3ms HSV detection)
    # FAST PRE-CHECK: before expensive button OCR, do a quick HSV scan
    # to see if any button-colored pixels exist in the button region.
    # If no colored buttons visible → not our turn → skip ALL OCR.
    t0 = time.time()
    btn_y1, btn_y2 = int(H * 0.82), int(H * 0.98)
    btn_x1, btn_x2 = int(W * 0.40), int(W * 0.98)
    btn_region = img[btn_y1:btn_y2, btn_x1:btn_x2]
    btn_hsv = cv2.cvtColor(btn_region, cv2.COLOR_RGB2HSV)
    # Dark red buttons: H<15 or H>170, S>80, V>60
    red_mask = ((btn_hsv[:,:,0] < 15) | (btn_hsv[:,:,0] > 170)) & \
               (btn_hsv[:,:,1] > 80) & (btn_hsv[:,:,2] > 60)
    red_pixels = int(np.sum(red_mask))
    # Green check buttons: H=35-85, S>100, V>140 (tournament/themed tables)
    green_mask = (btn_hsv[:,:,0] >= 35) & (btn_hsv[:,:,0] <= 85) & \
                 (btn_hsv[:,:,1] > 100) & (btn_hsv[:,:,2] > 140)
    green_pixels = int(np.sum(green_mask))
    # Yellow/gold buttons: H=18-35, S>80, V>140 (Battle Royale, themed tables)
    yellow_mask = (btn_hsv[:,:,0] >= 18) & (btn_hsv[:,:,0] <= 35) & \
                  (btn_hsv[:,:,1] > 80) & (btn_hsv[:,:,2] > 140)
    yellow_pixels = int(np.sum(yellow_mask))
    total_btn_pixels = red_pixels + green_pixels + yellow_pixels
    _has_action_pixels = total_btn_pixels >= 500

    if not _has_action_pixels:
        # No action buttons in the narrow Y=82-98% region.
        # Do a quick secondary scan of the wider bottom half (Y=50-98%)
        # for Deal Me In / I'm Back buttons which can appear higher up.
        dmi_y1, dmi_y2 = int(H * 0.50), int(H * 0.98)
        dmi_x1, dmi_x2 = int(W * 0.10), int(W * 0.90)
        dmi_region = img[dmi_y1:dmi_y2, dmi_x1:dmi_x2]
        dmi_hsv = cv2.cvtColor(dmi_region, cv2.COLOR_RGB2HSV)
        # Green Deal Me In button: H=35-85, S>100, V>140
        dmi_green = (dmi_hsv[:,:,0] >= 35) & (dmi_hsv[:,:,0] <= 85) & \
                    (dmi_hsv[:,:,1] > 100) & (dmi_hsv[:,:,2] > 140)
        # Red/salmon Deal Me In button: H<12, S>120, V>150
        dmi_red = (dmi_hsv[:,:,0] < 12) & \
                  (dmi_hsv[:,:,1] > 120) & (dmi_hsv[:,:,2] > 150)
        dmi_pixels = int(np.sum(dmi_green)) + int(np.sum(dmi_red))
        if dmi_pixels < 500:
            # Truly no buttons anywhere — return minimal state fast (skip all OCR)
            _sb, _bb = _parse_blinds(window_name)
            _gt = _detect_game_type(window_name)
            _tst = _detect_tournament_subtype(window_name)
            return GameState(
                my_cards=[], board_cards=[], available_actions=[],
                pot=0.0, is_my_turn=False, players=[],
                small_blind=_sb, big_blind=_bb,
                dealer_seat=-1, hero_seat=0,
                game_type=_gt, is_tournament=(_gt == 'tournament'),
                tournament_subtype=_tst,
            )
        # Deal Me In pixels found but no action buttons — run Deal Me In detection
        # (pure color, no OCR, ~3ms) and return early with just that button.
        dmi_buttons, dmi_rects = _detect_deal_me_in_color_only(img, W, H)
        if dmi_buttons:
            buttons = dmi_buttons
            button_rects = dmi_rects
            # Skip to action assembly below (no card/board OCR needed for Deal Me In)
        else:
            buttons = {}
            button_rects = {}

    # --- BUTTON CACHE: hash the button region to skip OCR on repeat frames ---
    # Buttons occupy Y=78-98%, X=2-98% (the _detect_buttons search region).
    # Hash a downsampled version for speed (~0.3ms vs 1200ms OCR).
    if _has_action_pixels:
        _btn_cache_y1, _btn_cache_y2 = int(H * 0.78), int(H * 0.98)
        _btn_cache_x1, _btn_cache_x2 = int(W * 0.40), int(W * 0.98)
        _btn_cache_region = img[_btn_cache_y1:_btn_cache_y2, _btn_cache_x1:_btn_cache_x2]
        _btn_cache_hash = hash(_btn_cache_region[::2, ::2].tobytes())
        _cached_btn = _BUTTON_CACHE.get(window_id)
        if _cached_btn and _cached_btn[0] == _btn_cache_hash:
            buttons, button_rects = _cached_btn[1], _cached_btn[2]
            log.debug(f"BUTTON CACHE HIT for window {window_id}")
        else:
            buttons, button_rects = _detect_buttons(img, W, H)
            # Deep copy button dicts so cached values aren't mutated by later code
            _BUTTON_CACHE[window_id] = (_btn_cache_hash,
                                         copy.deepcopy(buttons),
                                         copy.deepcopy(button_rects))
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

    # Turn logic:
    # 1. Must have poker action buttons visible
    # 2. If ONLY non-action buttons are visible (im_back), it's not our turn
    poker_actions = {'fold', 'call', 'check', 'raise', 'bet', 'all_in'}
    non_action_buttons = {'new_hand', 'deal_me_in', 'show_rabbit', 'im_back'}
    action_types = {a.action_type for a in available_actions}
    
    is_my_turn = bool(action_types & poker_actions)
    
    if action_types & non_action_buttons and not (action_types & poker_actions):
        is_my_turn = False

    has_any_buttons = bool(buttons)

    # 2. Cards + Board — only read if we have buttons (expensive OCR)
    my_cards = []
    board_cards = []
    
    if has_any_buttons:
        # --- ULTRA-FAST CACHE LOOKUP ---
        # Hash hole card area
        from sys_core.ocr.card_reader import SEARCH_Y_MIN, SEARCH_Y_MAX, SEARCH_X_MIN, SEARCH_X_MAX
        h1, h2 = int(H*SEARCH_Y_MIN), int(H*SEARCH_Y_MAX)
        w1, w2 = int(W*SEARCH_X_MIN), int(W*SEARCH_X_MAX)
        card_area = img[h1:h2, w1:w2]
        card_hash = hash(card_area.tobytes())
        
        # Hash board area
        bh1, bh2 = int(H*BOARD_Y_MIN), int(H*BOARD_Y_MAX)
        bw1, bw2 = int(W*BOARD_X_MIN), int(W*BOARD_X_MAX)
        board_area = img[bh1:bh2, bw1:bw2]
        board_hash = hash(board_area.tobytes())
        
        cached_cards = _CARD_CACHE.get(window_id)
        cached_board = _BOARD_CACHE.get(window_id)
        
        # Hole card OCR (if hash changed or first time)
        if cached_cards and cached_cards['hash'] == card_hash:
            my_cards = list(cached_cards['cards'])
            log.debug(f"CACHE HIT (cards) for {window_id}")
        else:
            my_cards = read_player_cards(table_img, debug_dir=debug_dir)
            _CARD_CACHE[window_id] = {'hash': card_hash, 'cards': list(my_cards)}
            
        # Board OCR (if hash changed or first time)
        if cached_board and cached_board['hash'] == board_hash:
            board_cards = list(cached_board['cards'])
            log.debug(f"CACHE HIT (board) for {window_id}")
        else:
            board_cards = _detect_board_cards(img, W, H)
            
            # --- Deduplicate board cards by name ---
            if board_cards:
                seen = set()
                unique_board = []
                for card in board_cards:
                    if card not in seen:
                        seen.add(card)
                        unique_board.append(card)
                board_cards = unique_board
            
            _BOARD_CACHE[window_id] = {'hash': board_hash, 'cards': list(board_cards)}

        # --- Cross-validate: no card should appear in both hole and board ---
        if my_cards and board_cards:
            overlap = set(my_cards) & set(board_cards)
            if overlap:
                log.warning(f"CARD COLLISION: {overlap} in both hole={my_cards} and board={board_cards}")
                # Remove the conflicting cards from the board (hole cards are more reliable)
                board_cards = [c for c in board_cards if c not in overlap]
    
    cards_face_down = len(my_cards) == 0
    t2 = time.time()

    # 3. Pot — hash-cached, individual OCR when changed
    pot = 0.0
    stack_hash_key = 0
    if is_my_turn:
        py1, py2 = int(H * POT_Y_MIN), int(H * POT_Y_MAX)
        px1, px2 = int(W * POT_X_MIN), int(W * POT_X_MAX)
        pot_area = img[py1:py2, px1:px2]
        pot_hash = hash(pot_area[::2, ::2].tobytes())
        cached_pot = _POT_CACHE.get(window_id)
        if cached_pot and cached_pot[0] == pot_hash:
            pot = cached_pot[1]
            log.debug(f"POT HASH HIT: reusing {pot}")
        else:
            pot = _read_pot(img, W, H)
            if pot > 600:
                log.warning(f"POT SANITY CAP: {pot:.1f} BB > 600 — using 0")
                pot = 0.0
            _POT_CACHE[window_id] = (pot_hash, pot)

        # 3b. Call/raise amounts — OCR only buttons that need amounts
        for btn_type in ('call', 'raise'):
            if btn_type in buttons and buttons[btn_type].get('amount') is None:
                rx, ry, rw, rh = buttons[btn_type]['rect']
                amount, text = _ocr_button_text(img, rx, ry, rw, rh)
                if amount is not None:
                    buttons[btn_type]['amount'] = amount
                    buttons[btn_type]['text'] = text
                    for a in available_actions:
                        if a.action_type == btn_type:
                            a.amount = amount

        # 3c. Hero stack hash
        hero_cx, hero_cy, hero_sw, hero_sh = SEAT_REGIONS_6MAX[0]
        hx1 = max(int((hero_cx - hero_sw / 2) * W), 0)
        hx2 = min(int((hero_cx + hero_sw / 2) * W), W)
        hy1 = max(int((hero_cy - hero_sh / 2) * H), 0)
        hy2 = min(int((hero_cy + hero_sh / 2) * H), H)
        stack_hash_key = hash(img[hy1:hy2, hx1:hx2][::2, ::2].tobytes())
    t4 = time.time()

    # 5. Blinds from window title
    sb, bb = _parse_blinds(window_name)

    # 5b. Game type and tournament info
    game_type = _detect_game_type(window_name)
    is_tournament = game_type == 'tournament'
    tournament_info = {}
    if is_tournament and is_my_turn:
        tournament_info = _read_tournament_info(img, W, H, window_id=window_id)
    tournament_icm = compute_icm_pressure(
        rank=tournament_info.get('my_rank'),
        total_players=tournament_info.get('total_players'),
        players_paid=tournament_info.get('players_paid'),
        game_type=game_type,
    )

    # 6. Call/raise amounts from button OCR
    call_amount = 0.0
    min_raise_amount = 0.0
    has_call = False
    for a in available_actions:
        if a.action_type == 'call':
            has_call = True
            if a.amount:
                # SANITY: call can't exceed 600 BB (6-max all-in)
                if a.amount > 600:
                    log.warning(f"CALL SANITY CAP: {a.amount:.1f} BB > 600 — OCR misread")
                    a.amount = None
                else:
                    call_amount = a.amount
        elif a.action_type == 'raise' and a.amount:
            if a.amount > 600:
                log.warning(f"RAISE SANITY CAP: {a.amount:.1f} BB > 600 — OCR misread")
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

    # 8. Player stacks — reuse cache aggressively, only full-read once per hand.
    # Stack OCR is the #1 bottleneck (~2300ms). Stacks barely change within a hand.
    hero_stack_is_estimated = False
    if is_my_turn:
        if window_id in _STACK_CACHE and len(_STACK_CACHE[window_id]) > 0:
            # Have cached stacks — reuse them (read hero only for updates)
            hero_players, hero_stack_is_estimated = _read_player_stacks(img, W, H, hero_only=True)
            cached_opps = [p for p in _STACK_CACHE[window_id] if not p.is_hero]
            players = hero_players + cached_opps
            _STACK_CACHE[window_id] = players
            log.debug(f"STACK FAST: hero-only read, {len(cached_opps)} opponents cached")
        else:
            # First read for this window — read all stacks
            players, hero_stack_is_estimated = _read_player_stacks(img, W, H)
            _STACK_CACHE[window_id] = players
            _STACK_HASH_CACHE[window_id] = stack_hash_key
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

    # 8d. Cross-validation for call/raise amounts (NO re-OCR — use logic only).
    # Reject amounts that exceed hero stack or are unreasonably large.
    max_expected_amt = hero_stk_val if hero_stk_val > 0 and not hero_stack_is_estimated else 200.0
    for btn_type in ('call', 'raise'):
        if btn_type not in buttons:
            continue
        btn_info = buttons[btn_type]
        amount = btn_info.get('amount')
        if amount is None or amount <= 0:
            continue

        # Reject amounts > hero stack (or 200 BB fallback)
        if amount > max_expected_amt:
            log.warning(f"MAX_EXPECTED: {btn_type} amount {amount} > max {max_expected_amt}, "
                        f"rejecting")
            amount = None

        # Write back corrected amount
        if btn_type == 'call':
            call_amount = amount if amount is not None else call_amount
        else:
            min_raise_amount = amount if amount is not None else min_raise_amount
        btn_info['amount'] = amount
        for a in available_actions:
            if a.action_type == btn_type:
                a.amount = amount

    # 9. Position detection
    # PRIMARY: Blind chip colors (red=SB, green=BB) on the felt.
    #   99% detection rate across Spin, Cash, Tournament screenshots.
    #   Only visible preflop; postflop chips get collected into pot.
    # CACHE: Position is cached per hand (keyed by hero cards). Postflop
    #   reuses the preflop detection. New cards = new hand = re-detect.
    hero_seat = 0  # Always seat 0 (bottom center)

    # Table size: detect from player count if available, else game type
    num_active_players = len([p for p in players if p.is_active]) if players else 0

    if num_active_players >= 7:
        num_seats = 9  # 7+ players visible → 9-max table
    elif game_type == 'spin':
        num_seats = 3
    elif game_type == 'tournament':
        _wn = window_name.lower() if window_name else ''
        if '6-max' in _wn or '6max' in _wn:
            num_seats = 6
        else:
            num_seats = 9  # Most GGPoker tournaments are 9-max by default
    else:
        num_seats = 6  # Cash games are always 6-max on GGPoker

    # Override with visible player count if it's more informative
    if num_active_players > 0 and num_active_players < num_seats:
        # Players may have busted — use the table layout, not current count
        pass

    # For 3-max (Spin & Go): players sit at physical seats 0, 2, 4
    _spin_seats = [0, 2, 4]

    def _dealer_from_sb(sb_seat):
        """Infer dealer seat from SB seat (dealer is one before SB clockwise)."""
        if num_seats == 3:
            sb_rel = _spin_seats.index(sb_seat) if sb_seat in _spin_seats else -1
            if sb_rel < 0:
                sb_rel = min(range(3), key=lambda i: abs(_spin_seats[i] - sb_seat))
            return (sb_rel - 1) % 3  # Returns relative dealer index
        else:
            return (sb_seat - 1) % num_seats  # Returns physical dealer seat

    def _position_from_dealer(dealer_idx):
        """Compute hero position from dealer index."""
        if num_seats == 3:
            return _hero_position(0, dealer_idx, 3)  # Already relative
        else:
            return _hero_position(hero_seat, dealer_idx, num_seats)

    position = 'UNKNOWN'

    # Hand key for cache: hero cards uniquely identify the current hand.
    # When cards change → new hand → must re-detect blinds.
    _cards_key = '|'.join(sorted(my_cards)) if my_cards else ''
    _cached = _POSITION_CACHE.get(window_id)

    chip_postings = []  # [(amount_bb, seat_idx), ...]
    is_postflop = street in (Street.FLOP, Street.TURN, Street.RIVER)

    if _cached and _cached[0] == _cards_key and _cards_key:
        # Same hand — reuse cached position
        _, sb_seat, bb_seat, position, _cached_postings = _cached
        log.debug(f"POSITION (cached): {position} (SB=seat{sb_seat} BB=seat{bb_seat})")
        # Postflop: detect CURRENT street bets (not blinds) from chip icons
        if is_postflop and is_my_turn:
            _, _, chip_postings = _detect_blinds_from_chips(img, W, H, num_seats)
            log.debug(f"POSTFLOP bets: {chip_postings}")
        else:
            chip_postings = _cached_postings
    elif is_postflop:
        # Postflop but no cache match for this hand.
        # Rush & Cash: stale cache is WRONG (new table every hand) — skip it.
        # Tournaments/Spin: stale cache is valid (same table, positions persist).
        _is_rush = 'rush' in (window_name or '').lower()
        if _cached and _cached[0] and not _is_rush:
            _, sb_seat, bb_seat, position, _ = _cached
            log.info(f"POSITION (stale cache): {position} — postflop, no exact match")
        else:
            sb_seat, bb_seat = -1, -1
            log.warning(f"POSITION: postflop, no cache — UNKNOWN")
        # Still detect current bets even without position
        if is_my_turn:
            _, _, chip_postings = _detect_blinds_from_chips(img, W, H, num_seats)
    else:
        # Preflop — detect blinds from chip icons + text on felt
        sb_seat, bb_seat, chip_postings = _detect_blinds_from_chips(img, W, H, num_seats)
        if sb_seat >= 0 and bb_seat >= 0:
            dealer_idx = _dealer_from_sb(sb_seat)
            position = _position_from_dealer(dealer_idx)
            log.info(f"POSITION (chips): SB=seat{sb_seat} BB=seat{bb_seat} "
                     f"→ dealer={dealer_idx} → {position} (game={game_type})"
                     f" postings={chip_postings}")
            # Cache for postflop streets of this hand
            if _cards_key:
                _POSITION_CACHE[window_id] = (
                    _cards_key, sb_seat, bb_seat, position, chip_postings)
        else:
            # Chips not found — try stale cache (but NOT for Rush & Cash
            # where positions change every hand)
            _is_rush = 'rush' in (window_name or '').lower()
            if _cached and _cached[0] and not _is_rush:
                _, sb_seat, bb_seat, position, chip_postings = _cached
                log.info(f"POSITION (stale cache): {position} — chips not found, "
                         f"reusing last known")
            else:
                log.warning(f"POSITION: No blind chips detected, no cache — UNKNOWN")

    # 9b. Merge chip postings into player bets and identify raiser
    dealer_seat = -1
    preflop_raiser_seat = -1
    preflop_raiser_position = ''

    if sb_seat >= 0:
        dealer_seat = _dealer_from_sb(sb_seat)

    # Set current_bet on each player from chip postings
    for amount, seat_idx in chip_postings:
        for p in players:
            if p.seat == seat_idx:
                p.current_bet = amount
                break

    if not is_postflop and sb_seat >= 0:
        # Preflop: raiser = any posting > 1.0 BB (excluding SB/BB)
        raises = [(amt, seat) for amt, seat in chip_postings
                  if amt > 1.05 and seat != sb_seat and seat != bb_seat]
        if raises:
            raises.sort(key=lambda x: -x[0])  # Largest raise first
            raiser_amt, raiser_seat = raises[0]
            preflop_raiser_seat = raiser_seat
            preflop_raiser_position = _hero_position(
                raiser_seat, dealer_seat, num_seats)
            log.info(f"RAISER: seat{raiser_seat} ({raiser_amt}BB) "
                     f"= {preflop_raiser_position}")
    elif is_postflop and chip_postings:
        # Postflop: log who bet on this street
        for amt, seat in chip_postings:
            pos = _hero_position(seat, dealer_seat, num_seats) if dealer_seat >= 0 else '?'
            log.info(f"STREET BET: seat{seat} ({amt}BB) = {pos}")

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

    # --- Compute confidence scores ---
    # Cards: hash cache hit=1.0, fresh OCR with 2 cards=0.85, cached from prev frame=0.5
    cached_cards_obj = _CARD_CACHE.get(window_id)
    _card_hash_val = card_hash if has_any_buttons else None
    if my_cards and len(my_cards) == 2:
        if cached_cards_obj and _card_hash_val and cached_cards_obj['hash'] == _card_hash_val:
            card_conf = 1.0  # Hash cache hit — image identical
        else:
            card_conf = 0.85  # Fresh OCR detection
    elif my_cards and len(my_cards) == 1:
        card_conf = 0.3  # Partial detection
    else:
        card_conf = 0.0  # No cards

    # Pot: double-read validation happened above; fresh read = 0.8, estimated = 0.3
    if pot > 0 and is_my_turn:
        pot_conf = 0.8
    elif pot > 0:
        pot_conf = 0.3
    else:
        pot_conf = 0.0 if is_my_turn else 1.0  # Not our turn, 0 pot is expected

    # Call amount: cleanly parsed = 0.9, estimated from pot = 0.3
    if call_amount > 0 and has_call:
        # Check if it was estimated (from pot heuristic) vs parsed from button text
        call_was_estimated = (call_amount == max(round((pot or 0) * 0.4, 1), 1.0) or
                              call_amount == max(round((pot or 0) * 0.5, 1), 1.0))
        call_conf = 0.4 if call_was_estimated else 0.9
    elif not has_call:
        call_conf = 1.0  # No call button — 0 is correct
    else:
        call_conf = 0.5  # Call button visible but amount = 0

    # Stacks
    stack_conf = 0.3 if hero_stack_is_estimated else 0.8

    # Buttons: at least one poker button detected
    btn_conf = 0.9 if action_types & poker_actions else (0.5 if has_any_buttons else 0.0)

    confidence = ReadConfidence(
        cards=card_conf,
        pot=pot_conf,
        call_amount=call_conf,
        stacks=stack_conf,
        buttons=btn_conf,
    )

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
        preflop_raiser_seat=preflop_raiser_seat,
        preflop_raiser_position=preflop_raiser_position,
        chip_postings=chip_postings,
        opponents_in_hand=opponents_in_hand,
        game_type=game_type,
        is_tournament=is_tournament,
        tournament_level=tournament_info.get('blind_level'),
        tournament_rank=tournament_info.get('my_rank'),
        tournament_total=tournament_info.get('total_players'),
        tournament_prize=tournament_info.get('first_prize'),
        tournament_players_paid=tournament_info.get('players_paid'),
        icm_pressure=tournament_icm,
        tournament_subtype=_detect_tournament_subtype(window_name),
        ocr_latency_ms=elapsed_ms,
        ocr_source='python_table_reader',
        hero_stack_is_estimated=hero_stack_is_estimated,
        confidence=confidence,
    )

    tourney_str = ''
    if is_tournament and (tournament_info.get('my_rank') or tournament_info.get('blind_level')):
        tourney_str = (f" | TOURNEY: rank={tournament_info.get('my_rank')}"
                       f"/{tournament_info.get('total_players')}"
                       f" level={tournament_info.get('blind_level')}"
                       f" ICM={tournament_icm:.2f}")
    log.info(f"Table read in {elapsed_ms:.0f}ms: cards={my_cards} board={board_cards} "
             f"buttons={list(buttons.keys())} pot={pot} turn={is_my_turn} "
             f"game={game_type}{tourney_str}")

    if debug_dir:
        _save_debug(img, W, H, buttons, button_rects, board_cards, pot, debug_dir)

    return state


# ---------------------------------------------------------------------------
#  Button detection — HSV color + OCR for amounts
# ---------------------------------------------------------------------------

def _detect_buttons(img: np.ndarray, W: int, H: int, deal_me_in_only: bool = False) -> Tuple[Dict, Dict]:
    """Detect action buttons by HSV color in the bottom region.

    OPTIMIZED (Mar 15 2026):
    - deal_me_in_only: Pure HSV color detection, NO OCR (~3ms).
    - Action buttons: Positional assignment (fold=left, call=middle, raise=right).
      OCR only on call+raise for amounts via _batch_ocr_amounts (~200ms total).
      Fold never needs OCR.  Cache handles repeat frames (<1ms).

    Args:
        img: Table image
        W: Width
        H: Height
        deal_me_in_only: If True, search a larger region specifically for Deal Me In.

    Returns:
        (buttons_dict, rects_dict) where buttons_dict maps action type to info.
    """
    # ---- DEAL ME IN FAST PATH: pure color, no OCR ----
    if deal_me_in_only:
        return _detect_deal_me_in_color_only(img, W, H)

    # ---- ACTION BUTTON DETECTION ----
    # Action buttons are at Y=0.78-0.98
    y1 = int(H * 0.78)
    y2 = int(H * BUTTON_Y_MAX)
    x1 = int(W * BUTTON_X_MIN)
    x2 = int(W * BUTTON_X_MAX)
    region = img[y1:y2, x1:x2]

    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)

    min_area = int(W * H * MIN_BUTTON_AREA_FRAC)
    min_btn_w = W * 0.08
    min_btn_h = H * 0.05

    buttons = {}
    rects = {}
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    small_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    region_w = x2 - x1

    # Scan all HSV button color ranges (dark_red, green, yellow)
    for btn_type, hsv_def in BUTTON_HSV.items():
        mask = cv2.inRange(hsv, hsv_def['lower'], hsv_def['upper'])

        if hsv_def['label'] == 'dark_red':
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
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

            this_min_area = min_area if hsv_def['label'] != 'dark_red' else int(W * H * 0.002)

            if area < this_min_area or bw < (min_btn_w * 0.7) or bh < (min_btn_h * 0.7):
                continue

            if hsv_def['label'] == 'dark_red' and bw > region_w * 0.30:
                sub_mask = mask[by:by + bh, bx:bx + bw]
                col_sum = np.sum(sub_mask > 0, axis=0)
                max_col = max(col_sum) if len(col_sum) > 0 else 1

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
                    edges = [0] + splits[:3] + [bw]
                    for si in range(len(edges) - 1):
                        sx = bx + edges[si]
                        sw = edges[si + 1] - edges[si]
                        if sw > min_btn_w:
                            button_rects.append((sx, by, sw, bh))
                    log.debug(f"Split merged {bw}px contour into {len(edges)-1} buttons at gaps {splits}")
                elif bw > region_w * 0.55:
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

        # Collect with absolute coords
        abs_rects = []
        for bx, by, bw, bh in button_rects:
            abs_rects.append((bx + x1, by + y1, bw, bh))

        # POSITIONAL ASSIGNMENT: GGPoker layout is always fold=left, call=middle, raise=right.
        if hsv_def['label'] == 'dark_red' and len(abs_rects) >= 3:
            abs_rects.sort(key=lambda r: r[0])
            _assign_positional_buttons(img, abs_rects[-3:], buttons, rects)
        elif hsv_def['label'] == 'dark_red' and len(abs_rects) == 2:
            # 2 dark_red: left=fold, right=raise. Geometric call fills in the middle.
            abs_rects.sort(key=lambda r: r[0])
            left_btn = abs_rects[0]
            right_btn = abs_rects[1]
            for pos_type, btn_rect in [('fold', left_btn), ('raise', right_btn)]:
                abx, aby, abw, abh = btn_rect
                center = (abx + abw // 2, aby + abh // 2)
                if pos_type not in buttons:
                    buttons[pos_type] = {
                        'center': center,
                        'rect': btn_rect,
                        'amount': None,
                        'text': '',
                        'confidence': 0.5,
                        'color': 'dark_red_positional',
                    }
                    rects[pos_type] = btn_rect
                    log.debug(f"Positional (2-btn) {pos_type} at {center}")
        else:
            # Non-dark_red buttons (green check, yellow) or single dark_red
            for abs_x, abs_y, bw, bh in abs_rects:
                center = (abs_x + bw // 2, abs_y + bh // 2)
                # Green buttons are check/call, yellow are check
                if hsv_def['label'] == 'green':
                    actual_type = 'check'  # Default; OCR only if needed
                elif hsv_def['label'] == 'yellow':
                    actual_type = 'check'
                else:
                    actual_type = btn_type
                if actual_type not in buttons:
                    buttons[actual_type] = {
                        'center': center,
                        'rect': (abs_x, abs_y, bw, bh),
                        'amount': None,
                        'text': '',
                        'confidence': 0.7,
                        'color': hsv_def['label'],
                    }
                    rects[actual_type] = (abs_x, abs_y, bw, bh)
                log.debug(f"Button {actual_type} ({hsv_def['label']}): "
                          f"({abs_x},{abs_y}) {bw}x{bh}")

        # Early exit: if we already have 3 action buttons, stop scanning
        action_found = {b for b in buttons if b in {'fold', 'call', 'check', 'raise', 'bet', 'all_in'}}
        if len(action_found) >= 3:
            log.debug(f"Found {len(action_found)} action buttons, skipping remaining HSV scans")
            break

    # --- Positional fallback: rescan without morph close to separate merged buttons ---
    if ('fold' in buttons or 'check' in buttons) and len(buttons) < 3:
        all_dark_btns = _find_dark_red_buttons_no_merge(hsv, x1, y1, small_kernel,
                                                         min_area, min_btn_w, min_btn_h,
                                                         region_w, W, H)
        if len(all_dark_btns) >= 3:
            _assign_positional_buttons(img, all_dark_btns[-3:], buttons, rects)
        elif len(all_dark_btns) == 2:
            left_btn = all_dark_btns[0]
            right_btn = all_dark_btns[1]
            for pos_type, btn_rect in [('fold', left_btn), ('raise', right_btn)]:
                abx, aby, abw, abh = btn_rect
                center = (abx + abw // 2, aby + abh // 2)
                if pos_type not in buttons:
                    buttons[pos_type] = {
                        'center': center,
                        'rect': btn_rect,
                        'amount': None,
                        'text': '',
                        'confidence': 0.5,
                        'color': 'dark_red_positional',
                    }
                    rects[pos_type] = btn_rect

    # --- Geometric call button detection ---
    # Call button is near-black, invisible to HSV. Compute from fold+raise geometry.
    missing_call = 'call' not in buttons and 'check' not in buttons

    if missing_call and 'fold' in buttons and 'raise' in buttons:
        fold_r = buttons['fold']['rect']
        raise_r = buttons['raise']['rect']

        call_x = fold_r[0] + fold_r[2]  # fold right edge
        call_right = raise_r[0]           # raise left edge
        call_w = call_right - call_x
        call_y = fold_r[1]
        call_h = fold_r[3]

        if call_w > min_btn_w and call_h > 0:
            trim = max(int(call_w * 0.05), 2)
            call_x += trim
            call_w -= trim * 2

            center = (call_x + call_w // 2, call_y + call_h // 2)

            buttons['call'] = {
                'center': center,
                'rect': (call_x, call_y, call_w, call_h),
                'amount': None,
                'text': '',
                'confidence': 0.9,
                'color': 'geometric',
            }
            rects['call'] = (call_x, call_y, call_w, call_h)
            missing_call = False
            log.debug(f"GEOMETRIC call button at ({call_x},{call_y}) {call_w}x{call_h}")

    # --- OCR text-position detection (image_to_data) ---
    # Run OCR when any button was found via low-confidence methods (positional,
    # geometric), or when we're missing call/check/raise. OCR finds ALL buttons
    # by reading their text — the near-black Call is invisible to HSV but has
    # white "Call 1.5 BB" text that OCR reads perfectly.
    _has_low_conf = any(v.get('color') in ('positional', 'geometric', 'dark_red_positional')
                        for v in buttons.values())
    _need_ocr_text = missing_call or _has_low_conf
    if PYTESSERACT_AVAILABLE and buttons and _need_ocr_text:
        ocr_text_buttons = _ocr_button_text_positions(img, x1, y1, x2, y2, W, H)
        if ocr_text_buttons:
            for btn_type, btn_info in ocr_text_buttons.items():
                if btn_type in buttons:
                    # OCR found same button as HSV — update with OCR's center
                    # (more accurate since it's the actual text position)
                    old_center = buttons[btn_type]['center']
                    new_center = btn_info['center']
                    buttons[btn_type]['center'] = new_center
                    buttons[btn_type]['rect'] = btn_info['rect']
                    buttons[btn_type]['amount'] = btn_info.get('amount') or buttons[btn_type].get('amount')
                    buttons[btn_type]['text'] = btn_info.get('text', '')
                    buttons[btn_type]['confidence'] = 0.95
                    buttons[btn_type]['color'] = 'ocr_text'
                    rects[btn_type] = btn_info['rect']
                    log.debug(f"OCR refined {btn_type}: {old_center} -> {new_center}")
                else:
                    # OCR found a button HSV missed (e.g. near-black Call)
                    buttons[btn_type] = btn_info
                    rects[btn_type] = btn_info['rect']
                    log.info(f"OCR found missing {btn_type} at {btn_info['center']}")

            # Remove positional/geometric buttons that OCR didn't confirm.
            # Two cases:
            # 1. OCR found 2+ buttons → it scanned successfully, remove unconfirmed positional buttons
            # 2. OCR found 1 button → check for overlap: if a positional button is at the same
            #    position as an OCR button, they're the same physical button (remove duplicate)
            if len(ocr_text_buttons) >= 2:
                phantom_btns = []
                for btn_type, btn_info in buttons.items():
                    if btn_info.get('color') in ('positional', 'geometric', 'dark_red_positional'):
                        if btn_type not in ocr_text_buttons:
                            phantom_btns.append(btn_type)
                for pb in phantom_btns:
                    log.info(f"Removing phantom {pb} button (OCR didn't confirm it)")
                    del buttons[pb]
                    rects.pop(pb, None)
            # Note: when OCR finds only 1 button, we DON'T remove positional
            # buttons — OCR may have missed some due to low confidence.
            # The positional assignments provide reasonable fallback positions.

    # GGPoker NEVER shows both call AND check simultaneously.
    # If both exist, the OCR-confirmed one is correct; remove the positional one.
    if 'call' in buttons and 'check' in buttons:
        call_conf = buttons['call'].get('confidence', 0)
        check_conf = buttons['check'].get('confidence', 0)
        call_is_ocr = buttons['call'].get('color') == 'ocr_text'
        check_is_ocr = buttons['check'].get('color') == 'ocr_text'
        if check_is_ocr and not call_is_ocr:
            log.info(f"Removing positional 'call' — OCR confirmed 'check' instead")
            del buttons['call']
            rects.pop('call', None)
        elif call_is_ocr and not check_is_ocr:
            log.info(f"Removing positional 'check' — OCR confirmed 'call' instead")
            del buttons['check']
            rects.pop('check', None)
        elif call_conf > check_conf:
            log.info(f"Removing 'check' (conf={check_conf:.2f}) — 'call' has higher conf ({call_conf:.2f})")
            del buttons['check']
            rects.pop('check', None)
        else:
            log.info(f"Removing 'call' (conf={call_conf:.2f}) — 'check' has higher conf ({check_conf:.2f})")
            del buttons['call']
            rects.pop('call', None)

    # --- BATCH OCR: read amounts for call + raise if still missing ---
    # Skip batch OCR if OCR text detection already ran (it already parsed amounts)
    ocr_regions = {}
    for btn_name in ('call', 'raise'):
        if btn_name in buttons and buttons[btn_name].get('amount') is None:
            # Only do batch OCR if this button was NOT found by OCR text detection
            if buttons[btn_name].get('color') != 'ocr_text':
                r = buttons[btn_name]['rect']
                ocr_regions[btn_name] = r

    if ocr_regions:
        batch_results = _batch_ocr_amounts(img, ocr_regions)
        for btn_name, (amount, text) in batch_results.items():
            if btn_name in buttons:
                if text:
                    actual_type = _classify_button_text(text, btn_name)
                    if actual_type != btn_name and actual_type not in buttons:
                        buttons[actual_type] = buttons.pop(btn_name)
                        rects[actual_type] = rects.pop(btn_name, None)
                        buttons[actual_type]['amount'] = amount
                        buttons[actual_type]['text'] = text
                        log.debug(f"OCR reclassified {btn_name} -> {actual_type}: {text!r}")
                    else:
                        buttons[btn_name]['amount'] = amount
                        buttons[btn_name]['text'] = text
                else:
                    buttons[btn_name]['amount'] = amount
                    buttons[btn_name]['text'] = text

    return buttons, rects


def _ocr_button_text_positions(
    img: np.ndarray, rx1: int, ry1: int, rx2: int, ry2: int,
    W: int, H: int,
) -> Dict:
    """Find button text positions using pytesseract image_to_data().

    Runs ONE OCR pass on the button region to find text like
    "Fold", "Call 1.5 BB", "Check", "Raise to 3 BB", "Bet 2 BB".
    Returns dict mapping button type -> {center, rect, amount, text, confidence, color}.

    The button region text is white on colored/dark backgrounds. We use
    grayscale threshold to isolate the text, then image_to_data to get
    word bounding boxes. Each word is checked against button keywords.

    This is the PRIMARY button detection method — it works regardless of
    button background color, including the near-black Call button that
    HSV completely misses.

    ~200ms per call (one pytesseract invocation).
    """
    region = img[ry1:ry2, rx1:rx2]
    if region.size == 0:
        return {}

    rh, rw = region.shape[:2]
    if rw < 50 or rh < 20:
        return {}

    # Preprocess: grayscale -> threshold -> scale up for OCR accuracy
    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    # White text on dark/colored buttons: threshold at 140 catches most text
    _, bw = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)
    # Also try inverted for dark text on light buttons
    _, bw_inv = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY_INV)

    scale = 3
    big = cv2.resize(bw, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    try:
        data = pytesseract.image_to_data(
            Image.fromarray(big), config='--psm 6 --oem 3',
            output_type=pytesseract.Output.DICT,
        )
    except Exception as e:
        log.debug(f"OCR text detection failed: {e}")
        return {}

    # Keywords to match — include partial reads (OCR often clips first/last char)
    # Sorted longest-first to prefer full matches over partial
    BUTTON_KEYWORDS = [
        ('check', 'check'),
        ('chec', 'check'),
        ('heck', 'check'),   # "Check" with C clipped
        ('fold', 'fold'),
        ('fol', 'fold'),
        ('call', 'call'),
        ('cal', 'call'),
        ('all', 'call'),     # "Call" misread as "mall", "1all", etc.
        ('raise', 'raise'),
        ('rais', 'raise'),
        ('aise', 'raise'),   # "Raise" with R clipped
        ('bet', 'raise'),
    ]

    found = {}
    n_words = len(data['text'])
    region_h = ry2 - ry1

    for i in range(n_words):
        word = data['text'][i].strip()
        if not word or len(word) < 3:
            continue
        conf = int(data['conf'][i]) if data['conf'][i] != '-1' else 0
        # Accept very low confidence for button text — OCR on colored/dark
        # backgrounds often gives conf=0 for correct reads (e.g. "heck" for Check).
        # We filter false positives by keyword matching + position (bottom of region).
        word_y = data['top'][i] // scale
        word_in_bottom_half = word_y > region_h * 0.35

        word_lower = word.lower()
        matched_type = None

        for kw, btn_type in BUTTON_KEYWORDS:
            if kw in word_lower:
                # For low-confidence matches, require position in bottom half
                # to filter out player names, chat text, etc.
                if conf < 30 and not word_in_bottom_half:
                    continue
                matched_type = btn_type
                break

        if not matched_type:
            continue

        # Already found this button type with higher confidence? Skip.
        if matched_type in found and found[matched_type]['confidence'] >= max(conf, 1) / 100.0:
            continue

        # Convert from scaled coords back to region coords, then to image coords
        wx = data['left'][i] // scale
        wy = data['top'][i] // scale
        ww = data['width'][i] // scale
        wh = data['height'][i] // scale

        # The text is inside a button. Estimate button bounds:
        # GGPoker buttons are ~200px wide, ~70px tall on a 1700px table.
        # The text is centered in the button. Expand outward from text.
        est_btn_w = max(ww * 2, int(W * 0.10))
        est_btn_h = max(wh * 2, int(H * 0.05))
        btn_x = max(wx + ww // 2 - est_btn_w // 2 + rx1, rx1)
        btn_y = max(wy + wh // 2 - est_btn_h // 2 + ry1, ry1)

        # Center of the text itself (most accurate click target)
        text_center_x = wx + ww // 2 + rx1
        text_center_y = wy + wh // 2 + ry1

        # Parse amount from nearby words on the same line
        amount = None
        line_num = data['line_num'][i] if 'line_num' in data else -1
        line_text_parts = [word]
        for j in range(max(0, i - 2), min(n_words, i + 5)):
            if j == i:
                continue
            if 'line_num' in data and data['line_num'][j] == line_num:
                jword = data['text'][j].strip()
                if jword:
                    line_text_parts.append(jword)
        line_text = ' '.join(line_text_parts)
        amount = _parse_amount(line_text)

        found[matched_type] = {
            'center': (text_center_x, text_center_y),
            'rect': (btn_x, btn_y, est_btn_w, est_btn_h),
            'amount': amount,
            'text': line_text,
            'confidence': conf / 100.0,
            'color': 'ocr_text',
        }
        log.debug(f"OCR text found {matched_type} at ({text_center_x},{text_center_y}) "
                  f"conf={conf} text={line_text!r}")

    # If we didn't find anything with the standard threshold, try with CLAHE
    if not found:
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(gray)
        _, bw2 = cv2.threshold(enhanced, 120, 255, cv2.THRESH_BINARY)
        big2 = cv2.resize(bw2, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        try:
            data2 = pytesseract.image_to_data(
                Image.fromarray(big2), config='--psm 6 --oem 3',
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            return {}

        n_words2 = len(data2['text'])
        for i in range(n_words2):
            word = data2['text'][i].strip()
            if not word or len(word) < 3:
                continue
            conf = int(data2['conf'][i]) if data2['conf'][i] != '-1' else 0

            word_lower = word.lower()
            word_y2 = data2['top'][i] // scale
            word_in_bottom2 = word_y2 > region_h * 0.35
            matched_type = None
            for kw, btn_type in BUTTON_KEYWORDS:
                if kw in word_lower:
                    if conf < 30 and not word_in_bottom2:
                        continue
                    matched_type = btn_type
                    break

            if not matched_type or matched_type in found:
                continue

            wx = data2['left'][i] // scale
            wy = data2['top'][i] // scale
            ww = data2['width'][i] // scale
            wh = data2['height'][i] // scale

            est_btn_w = max(ww * 2, int(W * 0.10))
            est_btn_h = max(wh * 2, int(H * 0.05))
            btn_x = max(wx + ww // 2 - est_btn_w // 2 + rx1, rx1)
            btn_y = max(wy + wh // 2 - est_btn_h // 2 + ry1, ry1)

            text_center_x = wx + ww // 2 + rx1
            text_center_y = wy + wh // 2 + ry1

            line_num = data2['line_num'][i] if 'line_num' in data2 else -1
            line_text_parts = [word]
            for j in range(max(0, i - 2), min(n_words2, i + 5)):
                if j == i:
                    continue
                if 'line_num' in data2 and data2['line_num'][j] == line_num:
                    jword = data2['text'][j].strip()
                    if jword:
                        line_text_parts.append(jword)
            line_text = ' '.join(line_text_parts)
            amount = _parse_amount(line_text)

            found[matched_type] = {
                'center': (text_center_x, text_center_y),
                'rect': (btn_x, btn_y, est_btn_w, est_btn_h),
                'amount': amount,
                'text': line_text,
                'confidence': conf / 100.0,
                'color': 'ocr_text',
            }
            log.debug(f"OCR CLAHE found {matched_type} at ({text_center_x},{text_center_y})")

    if found:
        log.info(f"OCR text detection found: {list(found.keys())}")

    return found


def _detect_deal_me_in_color_only(img: np.ndarray, W: int, H: int) -> Tuple[Dict, Dict]:
    """Detect Deal Me In / I'm Back buttons by color ONLY — no OCR.

    Searches Y=20-98% for red/salmon and green buttons large enough to be
    Deal Me In.  Returns immediately on first match (~3ms total).
    """
    y1 = int(H * 0.20)
    y2 = int(H * BUTTON_Y_MAX)
    x1 = int(W * BUTTON_X_MIN)
    x2 = int(W * BUTTON_X_MAX)
    region = img[y1:y2, x1:x2]

    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)

    min_area = int(W * H * 0.003)
    min_btn_w = W * 0.08
    min_btn_h = H * 0.04
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    buttons = {}
    rects_out = {}

    for btn_type, hsv_def in DEAL_ME_IN_HSV.items():
        mask = cv2.inRange(hsv, hsv_def['lower'], hsv_def['upper'])
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            bx, by, bw, bh = cv2.boundingRect(c)
            area = bw * bh
            if area < min_area or bw < min_btn_w or bh < min_btn_h:
                continue

            abs_x = bx + x1
            abs_y = by + y1
            center = (abs_x + bw // 2, abs_y + bh // 2)

            # Additional validation: Deal Me In buttons are in the center-bottom
            # area of the table.  Reject if too far left/right (avatar decorations).
            center_x_pct = (abs_x + bw // 2) / W
            if center_x_pct < 0.15 or center_x_pct > 0.85:
                continue

            buttons['deal_me_in'] = {
                'center': center,
                'rect': (abs_x, abs_y, bw, bh),
                'amount': None,
                'text': '',
                'confidence': 0.85,
                'color': hsv_def['label'],
            }
            rects_out['deal_me_in'] = (abs_x, abs_y, bw, bh)
            log.debug(f"Deal Me In ({hsv_def['label']}): ({abs_x},{abs_y}) {bw}x{bh}")
            return buttons, rects_out  # First match is enough

    return buttons, rects_out


def _assign_positional_buttons(img: np.ndarray, sorted_rects: list,
                                buttons: Dict, rects: Dict) -> None:
    """Assign fold/call/raise by position (left/middle/right). No OCR for fold.

    Amounts for call and raise are read later via _batch_ocr_amounts in the caller.
    """
    H, W = img.shape[:2]
    min_w = int(W * 0.08)   # Minimum button width
    min_h = int(H * 0.03)   # Minimum button height

    # Filter out rectangles too small or too high to be action buttons.
    # Real action buttons are at Y > 85% of table height.
    # Smaller/higher rectangles are sliders, icons, or UI noise.
    valid_rects = [(x, y, w, h) for x, y, w, h in sorted_rects
                   if w >= min_w and h >= min_h]

    pos_types = ['fold', 'call', 'raise']
    for idx, btn_rect in enumerate(valid_rects):
        if idx >= len(pos_types):
            break
        abx, aby, abw, abh = btn_rect
        center = (abx + abw // 2, aby + abh // 2)
        pos_type = pos_types[idx]
        if pos_type not in buttons:
            buttons[pos_type] = {
                'center': center,
                'rect': (abx, aby, abw, abh),
                'amount': None,
                'text': '',
                'confidence': 0.85,
                'color': 'positional',
            }
            rects[pos_type] = (abx, aby, abw, abh)
        log.debug(f"Button {pos_type} (positional): ({abx},{aby}) {abw}x{abh}")


def _find_dark_red_buttons_no_merge(hsv: np.ndarray, x1: int, y1: int,
                                     small_kernel, min_area: int,
                                     min_btn_w: float, min_btn_h: float,
                                     region_w: int, W: int, H: int) -> list:
    """Re-scan dark_red buttons WITHOUT morph close to avoid merging adjacent buttons.

    Returns list of (abs_x, abs_y, w, h) sorted left-to-right.
    """
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

    all_dark_btns.sort(key=lambda b: b[0])
    return all_dark_btns


def _find_buttons_by_ocr(
    img: np.ndarray, W: int, H: int,
    rx1: int, ry1: int, rx2: int, ry2: int,
    already_found: Dict,
) -> Optional[Dict]:
    """Find missing buttons via OCR in the button region.

    GGSystem's call button is near-black with faint gray text,
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


# ---------------------------------------------------------------------------
#  Batch OCR: combine multiple regions into ONE pytesseract call
# ---------------------------------------------------------------------------

def _batch_ocr_amounts(img: np.ndarray, regions: Dict[str, Tuple[int, int, int, int]],
                       ) -> Dict[str, Tuple[Optional[float], str]]:
    """OCR multiple screen regions in a SINGLE pytesseract call.

    Instead of spawning pytesseract N times (N*200ms), we stack all regions
    into one tall image separated by black bars, run OCR once (~200ms total),
    and split the results back by vertical position.

    Args:
        img: Full table image (RGB numpy array)
        regions: Dict mapping label -> (x, y, w, h) in img coordinates

    Returns:
        Dict mapping label -> (parsed_amount, raw_text)
    """
    if not PYTESSERACT_AVAILABLE or not regions:
        return {k: (None, "") for k in regions}

    scale = 3
    pad = 10
    separator_h = 8 * scale  # Black bar between regions

    # Prepare each region
    prepared = []
    labels_order = []
    row_boundaries = []  # (y_start, y_end) for each region in final image
    current_y = 0

    for label, (x, y, w, h) in regions.items():
        crop = img[y:y + h, x:x + w]
        if crop.size == 0:
            continue

        gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)

        # Use blue channel for stack regions (cyan text), grayscale otherwise
        if label.startswith('stack'):
            blue_ch = crop[:, :, 2]
            _, bw = cv2.threshold(blue_ch, 130, 255, cv2.THRESH_BINARY)
        elif label == 'pot':
            # Yellow pot text: average R+G channels
            r_ch, g_ch = crop[:, :, 0], crop[:, :, 1]
            yellow = ((r_ch.astype(int) + g_ch.astype(int)) // 2).astype(np.uint8)
            _, bw = cv2.threshold(yellow, 140, 255, cv2.THRESH_BINARY)
        else:
            # Button text (white on dark)
            _, bw = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)

        big = cv2.resize(bw, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_CUBIC)
        prepared.append(big)
        labels_order.append(label)
        row_boundaries.append((current_y + pad, current_y + pad + big.shape[0]))
        current_y += big.shape[0] + separator_h

    if not prepared:
        return {k: (None, "") for k in regions}

    # Build combined image: all regions stacked vertically with separators
    max_width = max(p.shape[1] for p in prepared)
    total_height = current_y + 2 * pad
    combined = np.zeros((total_height, max_width + 2 * pad), dtype=np.uint8)

    offset_y = pad
    for p in prepared:
        combined[offset_y:offset_y + p.shape[0], pad:pad + p.shape[1]] = p
        offset_y += p.shape[0] + separator_h

    # ONE pytesseract call for all regions
    text = pytesseract.image_to_string(
        Image.fromarray(combined), config='--psm 6 --oem 3'
    ).strip()

    # Split result lines and assign to regions
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    results = {}
    line_idx = 0
    for label in labels_order:
        if line_idx < len(lines):
            raw = lines[line_idx]
            amount = _parse_amount(raw)
            results[label] = (amount, raw)
            line_idx += 1
        else:
            results[label] = (None, "")

    # Fill in any missing labels
    for label in regions:
        if label not in results:
            results[label] = (None, "")

    log.debug(f"BATCH OCR ({len(regions)} regions, 1 pytesseract call): "
              f"{', '.join(f'{k}={v[0]}' for k, v in results.items())}")
    return results


def _ocr_button_text(img: np.ndarray, x: int, y: int, w: int, h: int,
                     reverse_thresholds: bool = False,
                     ) -> Tuple[Optional[float], str]:
    """OCR text from a button region. Returns (amount, raw_text).

    FAST version: tries only 2 thresholds + 1 CLAHE fallback (max 3 Tesseract
    calls instead of 8). Exits immediately when any text is found.
    """
    # Check per-call cache to avoid redundant Tesseract on same region
    cache_key = (x, y, w, h)
    if cache_key in _OCR_CACHE:
        return _OCR_CACHE[cache_key]

    if not PYTESSERACT_AVAILABLE:
        return None, ""

    crop = img[y:y + h, x:x + w]
    if crop.size == 0:
        return None, ""

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    scale = 3
    pad = 10

    # FAST: Try just 1 threshold first (bright text on dark button).
    # Only fall back to more thresholds if first attempt fails.
    padded = _prepare_for_ocr(gray, 180, scale, pad)
    text = pytesseract.image_to_string(
        Image.fromarray(padded), config='--psm 6 --oem 3'
    ).strip()

    if text:
        lower = text.lower()
        if any(kw in lower for kw in _BUTTON_KEYWORDS):
            log.debug(f"Button OCR thresh=180: {text!r}")
            amount = _parse_amount(text)
            _OCR_CACHE[cache_key] = (amount, text)
            return amount, text
        log.debug(f"Button OCR: ignoring non-keyword text {text!r}")

    # Fallback: CLAHE for dark call button (gray text ~147 on black ~20)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)
    padded = _prepare_for_ocr(enhanced, 120, scale, pad)
    text = pytesseract.image_to_string(
        Image.fromarray(padded), config='--psm 6 --oem 3'
    ).strip()

    if text:
        lower = text.lower()
        if any(kw in lower for kw in _BUTTON_KEYWORDS):
            amount = _parse_amount(text)
            _OCR_CACHE[cache_key] = (amount, text)
            return amount, text

    _OCR_CACHE[cache_key] = (None, "")
    return None, ""


def _classify_button_text(text: str, color_type: str) -> str:
    """Determine actual button type from OCR text, falling back to color."""
    t = text.lower()
    # Non-action buttons — must be checked FIRST
    if 'deal' in t or 'back' in t:
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
    # Map deal_me_in_green -> deal_me_in for engine compatibility
    if color_type == 'deal_me_in_green':
        return 'deal_me_in'
    return color_type


def _fix_ocr_missing_decimal(raw_num: str, text: str,
                             original_num_token: str = "") -> Optional[str]:
    """Fix OCR misreads where a decimal point is dropped.

    Tesseract often reads "1.0" as "10", "2.5" as "25", "1.00" as "100", etc.
    This is especially common on GGSystem's call/raise button text where the
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

def _read_player_stacks(img: np.ndarray, W: int, H: int,
                        hero_only: bool = False) -> List[PlayerInfo]:
    """Read stack amounts from seat positions.

    Args:
        hero_only: If True, only read hero stack (seat 0) for speed.
                   Use when opponent stacks are cached and only hero matters.

    Returns a list of PlayerInfo for seats where a stack amount was found.
    Seat 0 is always hero (bottom center).
    """
    if not PYTESSERACT_AVAILABLE:
        return []

    seats_to_read = [0] if hero_only else range(len(SEAT_REGIONS_6MAX))
    players = []
    for seat_idx in seats_to_read:
        cx, cy, sw, sh = SEAT_REGIONS_6MAX[seat_idx]
        x1 = max(int((cx - sw / 2) * W), 0)
        x2 = min(int((cx + sw / 2) * W), W)
        y1 = max(int((cy - sh / 2) * H), 0)
        y2 = min(int((cy + sh / 2) * H), H)
        region = img[y1:y2, x1:x2]
        if region.size == 0:
            continue

        stack = _ocr_stack_value(region)
        # Sanity: reject stacks > 2000 BB (likely OCR picked up level badge
        # concatenated with stack, e.g. "52101.0" = badge "52" + stack "101.0")
        # Note: 500+ BB is normal for deep-stacked cash games.
        if stack is not None and stack > 2000:
            # Try to extract just the last plausible number
            # e.g. 52101.0 → 101.0, 255100.0 → 100.0
            s_str = f"{stack:.1f}"
            for split_len in (3, 4, 5):  # try splitting off 3-5 digit suffix
                if len(s_str) > split_len + 1:
                    suffix = s_str[-split_len:]
                    try:
                        candidate = float(suffix)
                        if 0.5 <= candidate <= 500:
                            log.debug(f"Seat {seat_idx}: fixed garbled stack "
                                      f"{stack} → {candidate}")
                            stack = candidate
                            break
                    except ValueError:
                        pass
            else:
                log.debug(f"Seat {seat_idx}: rejecting implausible stack {stack}")
                stack = None
        if stack is not None and 0 < stack <= 2000:
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


def _strip_ui_borders(bw: np.ndarray) -> np.ndarray:
    """Remove UI frame borders from a binarized image.

    GGPoker player info boxes have bright rounded-rectangle borders that pass
    the blue channel threshold.  These wide horizontal/vertical lines confuse
    tesseract.  We detect them as rows/columns where >50% of pixels are white
    and zero them out.
    """
    out = bw.copy()
    row_frac = np.mean(out > 0, axis=1)
    for r in range(out.shape[0]):
        if row_frac[r] > 0.50:
            out[r, :] = 0
    col_frac = np.mean(out > 0, axis=0)
    for c in range(out.shape[1]):
        if col_frac[c] > 0.80:
            out[:, c] = 0
    return out


def _ocr_stack_value(region: np.ndarray) -> Optional[float]:
    """OCR a stack value from a small region. Returns the numeric value or None.

    GGSystem stacks are typically cyan text (RGB≈119,204,255) on dark bg.
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
    # Remove UI frame borders: rows/cols where >50% of pixels are white are
    # player info box edges, not text.  Seat 3 (top center) has a bright
    # horizontal border that otherwise confuses tesseract.
    bw = _strip_ui_borders(bw)
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
    bw = _strip_ui_borders(bw)
    if np.sum(bw > 0) >= 15:
        result = _ocr_single(bw, 3, pad)
        if result is not None:
            return result

    # CLAHE fallback for very faded text
    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)
    _, bw = cv2.threshold(enhanced, 100, 255, cv2.THRESH_BINARY)
    bw = _strip_ui_borders(bw)
    if np.sum(bw > 0) >= 10:
        result = _ocr_single(bw, 3, pad)
        if result is not None:
            return result

    return None


def _ocr_single(bw: np.ndarray, scale: int, pad: int) -> Optional[float]:
    """Run OCR on a single binarized image and parse the amount.

    Uses full charset first (recognizes '$' correctly), falls back to
    digit whitelist if no amount is found.  Also tries a top-60% crop
    as a fallback: bottom portions often contain player avatar artifacts
    that confuse tesseract's single-line mode.
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

    # Pass 3: top-60% crop fallback — bottom portions may contain player avatar
    # or UI artifacts that confuse tesseract's single-line layout analysis.
    # Crop to top 60% and retry with PSM 7.
    h_padded = padded.shape[0]
    top_crop = padded[:int(h_padded * 0.6), :]
    if top_crop.size > 0 and np.sum(top_crop > 0) >= 10:
        text3 = pytesseract.image_to_string(
            Image.fromarray(top_crop), config='--psm 7 --oem 3'
        ).strip()
        if text3:
            result3 = _parse_amount(text3)
            if result3 is not None:
                return result3

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


def _detect_blinds_from_chips(img: np.ndarray, W: int, H: int,
                              num_seats: int = 6
                              ) -> Tuple[int, int, List[Tuple[float, int]]]:
    """Detect bet postings on the felt by OCR-ing all "X BB" text.

    Uses a SINGLE pytesseract image_to_data() call on the entire felt area
    to find all "X BB" text with word-level bounding boxes.  This is:
      - Universal: works regardless of chip color (gold, red, green, black)
      - Fast: one OCR call (~300ms) instead of N per-chip calls
      - Accurate: full image context gives pytesseract better results

    Filters out false positives:
      - Stack amounts (>50 BB) — too large to be a posting
      - "Total Pot" text — in the exact center of the table
      - Player names — don't match "X BB" regex pattern

    Returns (sb_seat, bb_seat, all_postings) where all_postings is a list of
    (amount_bb, seat_idx) for every detected posting (blinds + raises/bets).
    Returns (-1, -1, []) if not detected.
    """
    if not PYTESSERACT_AVAILABLE:
        return -1, -1, []

    # Crop felt area — excludes title bar, button bar, edge chrome
    y1, y2 = int(H * 0.28), int(H * 0.75)
    x1, x2 = int(W * 0.08), int(W * 0.88)
    felt = img[y1:y2, x1:x2]

    # Preprocess: HSV saturation filter — white/gray text has LOW saturation
    # and HIGH value, while the green/brown felt has HIGH saturation.
    # This cleanly separates text from felt (9/9 detection, 0 false positives).
    felt_hsv = cv2.cvtColor(felt, cv2.COLOR_RGB2HSV)
    text_mask = cv2.inRange(felt_hsv, np.array([0, 0, 140]),
                            np.array([180, 80, 255]))

    # Single pytesseract call — word-level bounding boxes (no scaling needed)
    data = pytesseract.image_to_data(
        Image.fromarray(text_mask), output_type=pytesseract.Output.DICT,
        config='--psm 11 --oem 3')

    # Collect all detected words with positions
    words = []
    for i, txt in enumerate(data['text']):
        txt = txt.strip()
        if not txt:
            continue
        conf = int(data['conf'][i]) if str(data['conf'][i]) != '-1' else 0
        if conf < 30:
            continue
        # Convert position back to original image coords (undo crop offset)
        wx = data['left'][i] + x1
        wy = data['top'][i] + y1
        ww = data['width'][i]
        wh = data['height'][i]
        cx_pct = (wx + ww / 2) / W
        cy_pct = (wy + wh / 2) / H
        words.append((txt, cx_pct, cy_pct, conf))

    # Find "X BB" patterns using two strategies:
    # 1. Direct match: "0.5BB", "1BB", "2.5BB" as single token
    # 2. Backward search: find "BB" token, look backward for preceding number
    postings = []  # (amount, cx_pct, cy_pct)
    bb_direct = re.compile(r'^(\d+\.?\d*)\s*B+$', re.IGNORECASE)
    num_pattern = re.compile(r'^\d+\.?\d*$')
    used_indices = set()

    for wi, (txt, cx, cy, conf) in enumerate(words):
        # Strategy 1: Direct match — "0.5BB", "1BB", "2.5BB", "3.5BB"
        cleaned = txt.replace(' ', '')
        m = bb_direct.match(cleaned)
        if m:
            amount = float(m.group(1))
            if 0.25 <= amount <= 50:
                if 0.35 < cy < 0.45 and 0.40 < cx < 0.60:
                    continue  # Skip "Total Pot" area
                postings.append((amount, cx, cy))
                used_indices.add(wi)
                continue

        # Strategy 2: "BB" token — search backward for the number
        if txt.upper() in ('BB', 'B8', '88', 'B&'):
            for j in range(wi - 1, max(wi - 3, -1), -1):
                if j in used_indices:
                    continue
                prev_txt, prev_cx, prev_cy, _ = words[j]
                prev_clean = prev_txt.replace(',', '.').replace('O', '0')
                if num_pattern.match(prev_clean) and abs(cy - prev_cy) < 0.03:
                    try:
                        amount = float(prev_clean)
                        if 0.25 <= amount <= 50:
                            mid_cx = (cx + prev_cx) / 2
                            mid_cy = (cy + prev_cy) / 2
                            if 0.35 < mid_cy < 0.45 and 0.40 < mid_cx < 0.60:
                                continue
                            postings.append((amount, mid_cx, mid_cy))
                            used_indices.add(wi)
                            used_indices.add(j)
                            break
                    except ValueError:
                        pass

    # Deduplicate (same posting detected twice)
    unique = []
    for amt, cx, cy in postings:
        is_dup = False
        for amt2, cx2, cy2 in unique:
            if abs(cx - cx2) < 0.05 and abs(cy - cy2) < 0.05:
                is_dup = True
                break
        if not is_dup:
            unique.append((amt, cx, cy))

    # Map each posting to the nearest seat
    seat_layout = SEAT_REGIONS_9MAX[:num_seats] if num_seats > 6 else SEAT_REGIONS_6MAX
    found = []  # (amount, seat_idx, cx_pct, cy_pct)
    for amt, cx, cy in unique:
        min_dist = float('inf')
        nearest = -1
        for i, (sx, sy, _, _) in enumerate(seat_layout):
            dist = ((cx - sx) ** 2 + (cy - sy) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                nearest = i

        if min_dist < 0.40:
            log.debug(f"POSTING: {amt} BB at ({cx:.2f},{cy:.2f}) "
                      f"-> seat {nearest} (dist={min_dist:.3f})")
            found.append((amt, nearest, cx, cy))

    if len(found) < 1:
        log.debug(f"POSTINGS: {len(found)} found — need at least 1")
        return -1, -1, []

    all_postings = [(amt, seat) for amt, seat, _, _ in found]

    # Sort by amount: smallest = SB, next = BB
    found.sort(key=lambda x: x[0])

    if len(found) >= 2:
        sb_seat = found[0][1]
        bb_seat = found[1][1]
        if sb_seat != bb_seat:
            log.debug(f"BLINDS: SB=seat{sb_seat} ({found[0][0]}BB) "
                      f"BB=seat{bb_seat} ({found[1][0]}BB)")
            return sb_seat, bb_seat, all_postings
        # Same seat — take third posting or infer
        if len(found) >= 3 and found[2][1] != sb_seat:
            bb_seat = found[2][1]
            return sb_seat, bb_seat, all_postings
        bb_seat = (sb_seat + 1) % len(SEAT_REGIONS_6MAX)
        return sb_seat, bb_seat, all_postings

    # Only 1 posting found — infer missing blind
    sb_seat = found[0][1]
    bb_seat = (sb_seat + 1) % len(SEAT_REGIONS_6MAX)
    log.debug(f"BLINDS: only 1 posting at seat{sb_seat} ({found[0][0]}BB), "
              f"inferred BB=seat{bb_seat}")
    return sb_seat, bb_seat, all_postings


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

    GGSystem pot text is yellow/white on green felt ("Total Pot : $X.XX").
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

    # Pipeline 1: yellow channel (best for GGSystem yellow pot text)
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

    Tries colored detection first (more reliable on GGSystem), falls back to white.
    """
    y1 = int(H * BOARD_Y_MIN)
    y2 = int(H * BOARD_Y_MAX)
    x1 = int(W * BOARD_X_MIN)
    x2 = int(W * BOARD_X_MAX)

    # Try colored cards first (GGSystem 4-color deck)
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
    from sys_core.ocr.card_reader import (
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
        'C': (h_ch >= 30) & (h_ch <= 95) & (s_ch > 60) & (v_ch > 120),
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
        # ── Hash cache lookup (same cache as hero cards) ─────────
        # Crop the full board card body for hashing.
        card_body_crop = img[by:by+bh, bx:bx+bw]
        if card_body_crop.size > 0:
            cached = _pixel_hash_cache.lookup_fuzzy(card_body_crop)
            if cached and len(cached) >= 2:
                board.append(cached)
                log.debug(f"Board card HASH HIT: {cached} at ({bx},{by}) {bw}x{bh}")
                continue  # Skip OCR entirely

        # ── OCR path (hash cache missed) ─────────────────────────
        # Try BOTH corner and center rank, then pick the best.
        # Corner is cleaner (no suit symbol) but very small -> OCR struggles.
        # Center is larger but may include the suit symbol -> confuses OCR.
        margin_x = max(int(bw * 0.07), 3)
        margin_y = max(int(bh * 0.03), 2)
        corner_w = max(int(bw * 0.45), 15)
        corner_h = max(int(bh * 0.22), 10)
        corner_box = (bx + margin_x, by + margin_y, corner_w, corner_h)
        corner_rank = _read_rank_at(img, corner_box, STYLE_COLORED)

        # Center crop: capture the large central rank numeral ONLY.
        # Start at 25% X to skip the small suit symbol that sits left-of-center,
        # while keeping enough of wide ranks like J.
        # Start at 35% Y to skip the top-left corner rank/suit, end at 70%
        # to EXCLUDE the central suit symbol below the rank number.
        center_x = bx + int(bw * 0.25)
        center_y = by + int(bh * 0.35)
        center_w = int(bw * 0.65)
        center_h = int(bh * 0.35)
        center_box = (center_x, center_y, center_w, center_h)
        center_rank = _read_rank_at(img, center_box, STYLE_COLORED)

        # Pick the best rank:
        # - If both agree, use that.
        # - If only one succeeded, use it.
        # - If they disagree, prefer corner (less noise) UNLESS corner
        #   returned "10" (common misread of "9" as "0"->"10") and center
        #   returned a single digit -- trust center in that case.
        if corner_rank and center_rank:
            if corner_rank == center_rank:
                rank = corner_rank
            elif corner_rank == '10' and center_rank != '10':
                rank = center_rank  # "0"->"10" is often a misread "9"
            else:
                rank = corner_rank  # corner is generally cleaner
        else:
            rank = corner_rank or center_rank

        # Rescue: try an alternate center crop when detection is uncertain.
        # Characters like "J" have descenders the standard crop clips, and
        # corner often misreads "J" as "0"->"10" (the J-hook looks like 0).
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

        # Double-check 6<->A confusion: re-read with looser binarization
        if rank == 'A':
            rank = _verify_not_six(img, bx, by, bw, bh, rank)

        # ── Structural disambiguation for board cards ──────────────
        # Only run when hash cache missed AND OCR produced a result.
        # These heuristics fix common OCR confusions but can themselves
        # cause errors (e.g. the 9->K direction was wrong). The hash
        # cache bypasses all of this once a card is seen once.
        if rank:
            from sys_core.ocr.card_reader import (
                _binarize_white_on_colored, _count_enclosed_loops,
                _disambiguate_10_from_single, _strip_suit_symbol,
                STYLE_COLORED,
            )
            # Corner crop: just the rank character (top-left, no suit symbol)
            struct_x = bx + int(bw * 0.08)
            struct_y = by + int(bh * 0.03)
            struct_w = int(bw * 0.45)
            struct_h = int(bh * 0.20)  # Only top 20% = rank number only
            struct_crop = img[struct_y:struct_y+struct_h, struct_x:struct_x+struct_w]
            if struct_crop.size > 0 and struct_crop.shape[0] >= 5:
                bw_struct = _binarize_white_on_colored(struct_crop)
                _, bw_struct = cv2.threshold(bw_struct, 127, 255, cv2.THRESH_BINARY)
                # Strip suit symbol if any leaked into the crop
                bw_struct = _strip_suit_symbol(bw_struct)
                n_holes = _count_enclosed_loops(bw_struct)

                # 3->A: 3 has 0 holes, A has 1
                # NOTE: 4 also has 1 hole (triangle) -- do NOT use this
                # to change 4->A or A->4. Only 3->A is safe.
                if rank == '3' and n_holes >= 1:
                    log.info(f"BOARD A/3 FIX: rank={rank} but {n_holes} holes -> A")
                    rank = 'A'

                # K->9: K has 0 holes, 9 has 1
                # ONLY safe direction: K->9 (if holes found).
                # The reverse (9->K when 0 holes) was REMOVED because
                # binarization often destroys the 9's loop on small
                # board card crops, causing correct 9 reads to become K.
                if rank == 'K' and n_holes >= 1:
                    log.info(f"BOARD K/9 FIX: rank={rank} but {n_holes} holes -> 9")
                    rank = '9'

                # 8<->5: 8 has 2 holes, 5 has 0
                if rank == '5' and n_holes >= 2:
                    log.info(f"BOARD 8/5 FIX: rank={rank} but {n_holes} holes -> 8")
                    rank = '8'
                elif rank == '8' and n_holes == 0:
                    log.info(f"BOARD 8/5 FIX: rank={rank} but 0 holes -> 5")
                    rank = '5'

                # 10<->J/3/4: 10 has 2 connected components (1 + 0)
                # ONLY apply after suit symbol is stripped
                if rank in ('J', '3', '4'):
                    if _disambiguate_10_from_single(bw_struct):
                        log.info(f"BOARD 10/SINGLE FIX: rank={rank} but 2 components -> 10")
                        rank = '10'

        if rank:
            if rank == '10':
                rank = 'T'
            card_string = f"{rank}{suit}"
            board.append(card_string)
            log.debug(f"Board card (colored): {card_string} at ({bx},{by}) {bw}x{bh}")

            # ── Cache the OCR result for future reads ─────────────
            if card_body_crop.size > 0:
                _pixel_hash_cache.record_with_neighbors(
                    card_body_crop, card_string, confidence=0.85,
                )
        else:
            # Save debug images for board cards where rank detection failed
            try:
                import os, time as _dbg_time
                debug_dir_path = os.path.join(os.path.dirname(__file__), 'debug_failed_templates')
                os.makedirs(debug_dir_path, exist_ok=True)
                ts = int(_dbg_time.time() * 1000)
                card_crop = img[by:by+bh, bx:bx+bw]
                if card_crop.size > 0:
                    cv2.imwrite(f"{debug_dir_path}/{ts}_board_{suit}_crop.png", card_crop)
                    log.warning(f"BOARD RANK FAIL: suit={suit} at ({bx},{by}) {bw}x{bh} -- saved debug")
            except Exception:
                pass

    return board


def _verify_not_six(img: np.ndarray, bx: int, by: int, bw: int, bh: int,
                    original_rank: str) -> str:
    """Verify a board card read as 'A' isn't actually '6'.

    The '6' glyph loses its bottom loop on red/blue colored backgrounds when
    binarization clips the near-white pixels, making it look like 'A'.

    Strategy: re-binarize with a lower threshold and compare template scores.
    Also check structural features (6 has enclosed bottom loop, A doesn't).
    """
    from sys_core.ocr.card_reader import STYLE_COLORED
    from sys_core.ocr.rank_templates import get_rank_matcher

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
    from sys_core.ocr.card_reader import _read_rank_at, _detect_suit_at, STYLE_WHITE

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
#  Tournament info detection
# ---------------------------------------------------------------------------

# Cache tournament info per window to avoid re-OCR every frame
_TOURNAMENT_INFO_CACHE: Dict[int, Tuple[int, dict]] = {}  # window_id -> (hash, info_dict)


def _detect_game_type(window_name: str) -> str:
    """Detect game type from window title.

    Returns:
        'cash' for Rush & Cash / cash games
        'spin' for Spin & Gold
        'tournament' for MTTs and SNGs
        'unknown' if unrecognizable
    """
    name_lower = window_name.lower()

    # Rush & Cash
    if 'rush' in name_lower and 'cash' in name_lower:
        return 'cash'

    # Spin & Gold
    if 'spin' in name_lower or 'gold' in name_lower:
        return 'spin'

    # Tournament indicators: "Buy-in" with high blinds, or explicit tournament keywords
    if any(kw in name_lower for kw in ('tournament', 'tourney', 'mtt', 'sng',
                                        'daily', 'weekly', 'bounty', 'mystery',
                                        'ggmasters', 'million', 'zodiac',
                                        'battle royale', 'omaholic')):
        return 'tournament'

    # "Buy-in $X" pattern with "Blinds N | M" where N >= 25 is likely tournament
    # (cash games have low blinds like 0.5/1.0 or 1/2)
    if 'buy-in' in name_lower or 'buy in' in name_lower:
        blind_match = re.search(r'Blinds\s+(\d+)', window_name)
        if blind_match and int(blind_match.group(1)) >= 25:
            return 'tournament'
        return 'tournament'  # "Buy-in" almost always means tournament

    # Cash game patterns (NLH $X/$Y without Buy-in, or $X/$Y with no tournament keywords)
    if re.search(r'NL\s*H', name_lower) and 'buy' not in name_lower:
        return 'cash'

    # Generic cash: "$X/$Y" without any tournament keyword
    if re.search(r'\$\d+(?:\.\d+)?\s*/\s*\$\d+', window_name) and 'buy' not in name_lower:
        return 'cash'

    return 'unknown'


def _detect_tournament_subtype(window_name: str) -> str:
    """Detect specific tournament subtype from window title.

    Returns one of:
        'hyper'        - Hyper turbo (faster blinds, push/fold earlier)
        'turbo'        - Turbo structure
        'double_stack' - Double stack (deeper stacks)
        'bounty'       - Bounty/knockout tournament (wider calling ranges)
        'spin'         - Spin & Go / Spin & Gold (winner-take-all)
        'regular'      - Standard tournament structure
        'unknown'      - Cannot determine subtype
    """
    name_lower = window_name.lower()

    # Spin & Gold / Spin & Go
    if 'spin' in name_lower or 'gold' in name_lower:
        return 'spin'

    # Hyper turbo (check before turbo — "hyper" is more specific)
    if 'hyper' in name_lower:
        return 'hyper'

    # Turbo
    if 'turbo' in name_lower:
        return 'turbo'

    # Double stack
    if 'double' in name_lower and 'stack' in name_lower:
        return 'double_stack'

    # Bounty / knockout
    if any(kw in name_lower for kw in ('bounty', 'knockout', 'ko ', 'mystery bounty',
                                        'progressive ko')):
        return 'bounty'

    # If it's a tournament but no specific subtype detected
    game_type = _detect_game_type(window_name)
    if game_type == 'tournament':
        return 'regular'

    return 'unknown'


def _read_tournament_info(img: np.ndarray, W: int, H: int, window_id: int = 0) -> dict:
    """Read tournament info bar from the top of the table.

    The tournament info bar is at the very top of the table image (Y=0-8%, X=0-50%).
    It shows:
        - "Level 9" and a countdown timer
        - "Late Reg." and countdown
        - "1st Prize" and "$1,172"
        - "My Rank" and "12 / 546"
        - "Places Paid" count

    Returns:
        dict with keys:
            'blind_level': int or None
            'my_rank': int or None
            'total_players': int or None
            'first_prize': float or None
            'players_paid': int or None
            'raw_text': str (OCR text for debugging)
    """
    if not PYTESSERACT_AVAILABLE:
        return {}

    result = {
        'blind_level': None,
        'my_rank': None,
        'total_players': None,
        'first_prize': None,
        'players_paid': None,
        'raw_text': '',
    }

    # Crop the top info bar region (Y=0 to 8%, X=0 to 60%)
    # Tournament info is in the top-left area
    y_end = int(H * 0.08)
    x_end = int(W * 0.60)
    if y_end < 10 or x_end < 50:
        return result

    info_bar = img[0:y_end, 0:x_end]

    # Hash-based cache: skip OCR if pixels haven't changed
    bar_hash = hash(info_bar[::2, ::2].tobytes())
    cached = _TOURNAMENT_INFO_CACHE.get(window_id)
    if cached and cached[0] == bar_hash:
        return cached[1]

    # Convert to grayscale for OCR
    if len(info_bar.shape) == 3:
        gray = cv2.cvtColor(info_bar, cv2.COLOR_BGR2GRAY)
    else:
        gray = info_bar

    # Threshold to enhance white/light text on dark background
    # Tournament info bar has light text on dark gradient
    _, thresh = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)

    # Scale up for better OCR (info bar text is small)
    scale = 3
    scaled = cv2.resize(thresh, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    try:
        # PSM 6 = assume uniform block of text
        text = pytesseract.image_to_string(scaled, config='--psm 6 --oem 3').strip()
        result['raw_text'] = text
    except Exception as e:
        log.debug(f"Tournament info OCR failed: {e}")
        _TOURNAMENT_INFO_CACHE[window_id] = (bar_hash, result)
        return result

    # Parse blind level: "Level 9", "Level 12", "Lv 9", "Lv. 12"
    level_match = re.search(r'(?:Level|Lv\.?)\s*(\d+)', text, re.IGNORECASE)
    if level_match:
        result['blind_level'] = int(level_match.group(1))

    # Parse rank: "12 / 546", "12/546", "My Rank" nearby then digits
    rank_match = re.search(r'(\d{1,5})\s*/\s*(\d{1,5})', text)
    if rank_match:
        rank_val = int(rank_match.group(1))
        total_val = int(rank_match.group(2))
        # Sanity: rank should be <= total, total >= 2
        if 1 <= rank_val <= total_val and total_val >= 2:
            result['my_rank'] = rank_val
            result['total_players'] = total_val

    # Parse 1st prize: "$1,172", "$500", "$10,000"
    prize_match = re.search(r'\$\s*([\d,]+(?:\.\d{1,2})?)', text)
    if prize_match:
        prize_str = prize_match.group(1).replace(',', '')
        try:
            prize_val = float(prize_str)
            if prize_val >= 1.0:  # Minimum sensible prize
                result['first_prize'] = prize_val
        except ValueError:
            pass

    # Parse places paid: "Places Paid" followed by number, or "Paid: 80"
    paid_match = re.search(r'(?:Places?\s*Paid|Paid)\s*:?\s*(\d+)', text, re.IGNORECASE)
    if paid_match:
        result['players_paid'] = int(paid_match.group(1))

    if result['blind_level'] or result['my_rank']:
        log.info(f"TOURNAMENT INFO: level={result['blind_level']} "
                 f"rank={result['my_rank']}/{result['total_players']} "
                 f"prize=${result['first_prize']} paid={result['players_paid']}")

    _TOURNAMENT_INFO_CACHE[window_id] = (bar_hash, result)
    return result


def compute_icm_pressure(rank: Optional[int],
                         total_players: Optional[int],
                         players_paid: Optional[int],
                         game_type: str = 'unknown') -> float:
    """Compute ICM pressure: 0.0 (no pressure) to 1.0 (extreme pressure).

    Near bubble: high pressure (tighten up significantly)
    Deep in money: medium pressure (still ladder value)
    Final table: highest pressure (each spot = big money jump)
    Early tournament: low pressure (play for chips)

    Special cases:
    - Spin & Gold: 0.0 (winner-take-all, no ladder value)
    - Cash games: 0.0 (no tournament considerations)
    """
    # Spin & Gold = winner-take-all, no ICM
    if game_type == 'spin':
        return 0.0

    # Cash games = no tournament pressure
    if game_type == 'cash':
        return 0.0

    # Need at least rank and total to compute
    if not rank or not total_players or total_players < 2:
        return 0.0

    pct_field_remaining = rank / total_players

    # --- Final table (top ~2% or last 9) ---
    if rank <= 9 or pct_field_remaining <= 0.02:
        return 0.9  # Extreme: each spot = huge prize jump

    # --- Near bubble ---
    if players_paid:
        bubble_distance = rank - players_paid
        if bubble_distance <= 0:
            # Already in the money
            pct_into_money = rank / players_paid if players_paid > 0 else 1.0

            if pct_into_money <= 0.10:
                # Top 10% of paid places (approaching final table)
                return 0.7
            elif pct_into_money <= 0.30:
                # Top 30% of paid places
                return 0.5
            else:
                # Deep in money but not near final table
                return 0.3

        elif bubble_distance <= max(5, int(total_players * 0.01)):
            # Within 5 spots (or 1% of field) of the money
            return 0.8  # Very high bubble pressure

        elif bubble_distance <= max(15, int(total_players * 0.03)):
            # Close to the bubble (within ~3% of field)
            return 0.5

    # --- Early/middle tournament ---
    if pct_field_remaining > 0.50:
        return 0.05  # Very early, almost no ICM considerations
    elif pct_field_remaining > 0.30:
        return 0.1   # Middle stages
    elif pct_field_remaining > 0.15:
        return 0.2   # Approaching money

    return 0.15  # Default moderate pressure


# ---------------------------------------------------------------------------
#  Utility
# ---------------------------------------------------------------------------

def _parse_blinds(title: str) -> Tuple[float, float]:
    """Extract blinds from window title.

    Handles formats:
        "Spin & Gold $0.25 - Blinds 15 | 30"
        "Rush & Cash - $0.05 / $0.10"
    """
    # Format: "Blinds X | Y" (tournament/Spin & Gold chip blinds)
    # GGPoker displays all values in BB mode on screen, so stack=21 BB
    # means 21 big blinds regardless of the chip blind value.
    # Always return 0.5/1.0 BB since the display is normalized.
    match = re.search(r'Blinds\s+(\d+(?:\.\d+)?)\s*\|\s*(\d+(?:\.\d+)?)', title)
    if match:
        return 0.5, 1.0  # BB display mode — always 0.5/1.0 in BB units

    # Format: "$X / $Y" (Rush & Cash style)
    # GGPoker displays all values in BB mode, so blinds are always 0.5/1.0 BB
    # regardless of the dollar stake shown in the window title.
    match = re.search(r'\$(\d+(?:\.\d+)?)\s*/\s*\$(\d+(?:\.\d+)?)', title)
    if match:
        return 0.5, 1.0  # Always 0.5 BB / 1.0 BB in BB display mode

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
        print("Usage: python -m sys_core.ocr.table_reader <screenshot.png> [--debug]")
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
