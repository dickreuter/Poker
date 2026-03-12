"""
AUTO PLAYER - Fully Automatic System Utility
Handles: Table detection, card recognition, button clicking, deal-me-in

Usage:
    python -m sys_core.tools.auto_player

Features:
    - Self-improving via AdaptiveLearner
    - Logs all actions for analysis
    - Dynamic threshold adjustment
"""

import logging
import subprocess
import time
import cv2
import numpy as np
from PIL import ImageGrab, Image
from pynput.mouse import Button, Controller
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Import adaptive learner for self-improvement
from sys_core.tools.adaptive_learner import (
    log_action, report_issue, get_threshold, get_learner, save_screenshot
)

# Import vision analyzer for auto-fixing
from sys_core.tools.vision_analyzer import auto_fix_detection, auto_fix_buttons, auto_fix_cards

# Use UNIFIED constants - single source of truth
from sys_core.core.constants import HSV_RANGES, RETINA_SCALE

log = logging.getLogger(__name__)


@dataclass
class TableWindow:
    name: str
    x_pt: int  # Points (for clicking)
    y_pt: int
    w_pt: int
    h_pt: int

    @property
    def x_px(self): return self.x_pt * RETINA_SCALE
    @property
    def y_px(self): return self.y_pt * RETINA_SCALE
    @property
    def w_px(self): return self.w_pt * RETINA_SCALE
    @property
    def h_px(self): return self.h_pt * RETINA_SCALE


class AutoPlayer:
    """Fully automatic poker player."""

    # Button colors - USE UNIFIED CONSTANTS from core/constants.py
    BUTTON_COLORS = {
        'call': {'lower': HSV_RANGES['call']['lower'], 'upper': HSV_RANGES['call']['upper'], 'name': 'Call/Check'},
        'raise': {'lower': HSV_RANGES['raise']['lower'], 'upper': HSV_RANGES['raise']['upper'], 'name': 'Raise/Bet'},
        'fold': {'lower': HSV_RANGES['fold']['lower'], 'upper': HSV_RANGES['fold']['upper'], 'name': 'Fold'},
    }

    # Deal Me In button - USE UNIFIED CONSTANTS
    DEAL_ME_IN_COLOR = {'lower': HSV_RANGES['deal_me_in']['lower'], 'upper': HSV_RANGES['deal_me_in']['upper']}

    def __init__(self):
        self.mouse = Controller()
        self.running = False
        self.table_dict = None
        self.actions_taken = 0
        self.last_action_time = 0
        # Use adaptive thresholds from learner
        self.action_cooldown = get_threshold('action_cooldown', 1.5)
        self.white_pixel_min = get_threshold('white_pixel_min', 150)
        self.button_area_min = get_threshold('button_area_min', 2000)
        self.card_area_min = get_threshold('card_area_min', 2000)

    def load_templates(self):
        """Load card templates from MongoDB."""
        try:
            from sys_core.tools.mongo_manager import MongoManager
            mongo = MongoManager()
            self.table_dict = mongo.get_table("Official GGSystem 6player")
            if self.table_dict:
                log.info(f"Loaded {len(self.table_dict)} templates")
                return True
        except Exception as e:
            log.warning(f"Could not load templates: {e}")
        return False

    def find_tables(self) -> List[TableWindow]:
        """Find all poker table windows via AppleScript."""
        script = '''
        tell application "System Events"
            if not (exists process "GGnet") then return ""
            tell process "GGnet"
                set output to ""
                repeat with w in windows
                    set winName to name of w as text
                    set winPos to position of w
                    set winSize to size of w
                    set output to output & winName & "###" & (item 1 of winPos as text) & "," & (item 2 of winPos as text) & "," & (item 1 of winSize as text) & "," & (item 2 of winSize as text) & ";"
                end repeat
                return output
            end tell
        end tell
        '''
        try:
            result = subprocess.run(['osascript', '-e', script],
                                    capture_output=True, text=True, timeout=5)
            tables = []
            keywords = ['Spin', 'Gold', 'Rush', 'Cash', 'Hold', 'Omaha', 'Blinds', 'NL', 'PLO']

            for entry in result.stdout.strip().rstrip(';').split(';'):
                if '###' not in entry:
                    continue
                name, coords = entry.split('###')
                name = name.strip()

                # Only include poker tables, not lobby
                if not any(kw in name for kw in keywords):
                    continue

                # Fix Unicode minus sign (−) that macOS returns instead of ASCII minus (-)
                coords = coords.replace('−', '-').replace('–', '-')
                parts = coords.split(',')
                if len(parts) == 4:
                    tables.append(TableWindow(
                        name=name,
                        x_pt=int(parts[0]), y_pt=int(parts[1]),
                        w_pt=int(parts[2]), h_pt=int(parts[3])
                    ))
            return tables
        except Exception as e:
            log.error(f"Error finding tables: {e}")
            return []

    def capture_table(self, table: TableWindow, screenshot: Image.Image) -> Image.Image:
        """Crop table from full screenshot."""
        return screenshot.crop((
            table.x_px, table.y_px,
            table.x_px + table.w_px,
            table.y_px + table.h_px
        ))

    def find_buttons(self, table_img: Image.Image, table: TableWindow) -> Dict[str, Dict]:
        """Find action buttons by color. Logs success/failure for adaptive learning."""
        img = cv2.cvtColor(np.array(table_img), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h_img, w_img = img.shape[:2]

        # Search bottom 35% of table
        y_start = int(h_img * 0.65)
        x_start = int(w_img * 0.15)
        x_end = int(w_img * 0.85)
        search_region = hsv[y_start:, x_start:x_end]

        buttons = {}
        min_area = self.button_area_min  # Use adaptive threshold

        for btn_key, color_info in self.BUTTON_COLORS.items():
            mask = cv2.inRange(search_region, color_info['lower'], color_info['upper'])

            # Clean up mask
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            best = None
            best_area = 0
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > best_area and area > min_area:
                    x, y, w, bh = cv2.boundingRect(contour)
                    # Button should be reasonably sized
                    if 60 < w < 400 and 25 < bh < 150:
                        center_x = x_start + x + w // 2
                        center_y = y_start + y + bh // 2
                        best = (center_x, center_y, w, bh, area)
                        best_area = area

            if best:
                x_px, y_px, w, h, _ = best
                # Convert to screen points for clicking
                screen_x = table.x_pt + x_px // RETINA_SCALE
                screen_y = table.y_pt + y_px // RETINA_SCALE
                buttons[btn_key] = {
                    'x_px': x_px, 'y_px': y_px,
                    'screen_pt': (screen_x, screen_y),
                    'size': (w, h),
                    'name': color_info['name']
                }

        # Log button detection result for learning
        if buttons:
            log_action('button_detection', success=True,
                       details={'buttons': list(buttons.keys()), 'count': len(buttons)},
                       save_on_fail=False)  # Don't screenshot on success
        else:
            log_action('button_detection', success=False,
                       details={'table': table.name, 'search_area': (y_start, x_start, x_end)},
                       screenshot=table_img)  # Save table image for debugging

        return buttons

    def find_deal_me_in(self, table_img: Image.Image, table: TableWindow) -> Optional[Dict]:
        """Find Deal Me In button (red/salmon colored).

        Only triggers if there are NO action buttons visible (fold/call/raise).
        This prevents false positives.
        """
        img = cv2.cvtColor(np.array(table_img), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h_img, w_img = img.shape[:2]

        # Search center area (not bottom where action buttons are)
        y_start = int(h_img * 0.40)
        y_end = int(h_img * 0.70)
        x_start = int(w_img * 0.30)
        x_end = int(w_img * 0.70)
        search_region = hsv[y_start:y_end, x_start:x_end]

        # Look for red/salmon button
        mask = cv2.inRange(search_region, self.DEAL_ME_IN_COLOR['lower'], self.DEAL_ME_IN_COLOR['upper'])

        # Require substantial button size
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 5000:  # Larger minimum area
                x, y, w, bh = cv2.boundingRect(contour)
                # Button must be reasonably sized and shaped
                if 100 < w < 300 and 40 < bh < 100:
                    center_x = x_start + x + w // 2
                    center_y = y_start + y + bh // 2
                    screen_x = table.x_pt + center_x // RETINA_SCALE
                    screen_y = table.y_pt + center_y // RETINA_SCALE
                    log.debug(f"Deal Me In found at ({screen_x}, {screen_y})")
                    return {
                        'screen_pt': (screen_x, screen_y),
                        'name': 'Deal Me In'
                    }
        return None

    def detect_cards(self, table_img: Image.Image) -> List[str]:
        """Detect player's hole cards using TRUE DYNAMIC detection.

        Finds white card rectangles wherever they are on the table,
        extracts them, and matches against templates.
        Uses adaptive thresholds from learner.
        """
        img = np.array(table_img)
        h_img, w_img = img.shape[:2]

        # Search bottom 45% of table (player cards are always at bottom)
        search_y_start = int(h_img * 0.55)
        search_region = img[search_y_start:, :]

        # Use adaptive white pixel threshold
        white_threshold = self.white_pixel_min

        # Find white/cream colored card regions (cards are white/cream)
        white_mask = (
            (search_region[:,:,0] > white_threshold) &
            (search_region[:,:,1] > white_threshold) &
            (search_region[:,:,2] > white_threshold)
        ).astype(np.uint8) * 255

        # Debug: log what we found
        total_white = np.sum(white_mask > 0)
        log.debug(f"Card search: region {search_region.shape}, white pixels: {total_white}")

        # Clean up mask
        kernel = np.ones((5, 5), np.uint8)
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_OPEN, kernel)

        # Find contours of white regions
        contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Find card-shaped contours at bottom center
        card_candidates = []
        search_h, search_w = search_region.shape[:2]

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.card_area_min:  # Use adaptive threshold
                continue

            x, y, cw, ch = cv2.boundingRect(cnt)

            # Cards have various aspect ratios depending on how they're displayed
            if ch == 0:
                continue
            aspect = cw / ch
            # Very relaxed aspect ratio - cards can be wide or tall
            if not (0.3 < aspect < 2.0):
                continue

            # Relaxed size filter - cards can vary significantly
            if cw < 30 or ch < 30 or cw > 300 or ch > 350:
                continue

            log.debug(f"Card candidate: pos=({x},{y}) size={cw}x{ch} aspect={aspect:.2f} area={area}")

            # Score by position - prefer bottom center
            center_x = x + cw // 2
            center_y = y + ch // 2

            # Distance from horizontal center (lower = better)
            x_dist = abs(center_x - search_w // 2) / (search_w // 2)
            # How far down (higher y = lower on screen = better)
            y_score = center_y / search_h

            score = y_score - (x_dist * 0.3) + (area / 20000)

            card_candidates.append({
                'bbox': (x, y + search_y_start, cw, ch),  # Adjust y back to full image coords
                'area': area,
                'score': score,
                'center_x': center_x
            })

        if len(card_candidates) < 2:
            log.info(f"Card detection: Found {len(card_candidates)} candidates (need 2)")
            # Log failure for adaptive learning WITH screenshot
            log_action('card_detection', success=False, details={
                'candidates': len(card_candidates),
                'white_threshold': white_threshold,
                'white_pixels': int(total_white)
            }, screenshot=table_img)  # Save the table image for reference
            return []

        # Sort by score and take top candidates
        card_candidates.sort(key=lambda c: c['score'], reverse=True)

        # Take candidates that are horizontally separated (left and right cards)
        cards = []
        used_centers = []

        for candidate in card_candidates:
            cx = candidate['center_x']
            # Make sure this card is not too close to already selected cards
            too_close = any(abs(cx - uc) < 30 for uc in used_centers)
            if too_close:
                continue

            cards.append(candidate)
            used_centers.append(cx)

            if len(cards) >= 2:
                break

        if len(cards) < 2:
            return []

        # Sort by x position (left card first)
        cards.sort(key=lambda c: c['center_x'])

        # Extract and match each card
        results = []
        for card_info in cards:
            x, y, cw, ch = card_info['bbox']
            card_region = table_img.crop((x, y, x + cw, y + ch))

            matched = self._match_card(card_region)
            if matched:
                results.append(matched)
                log.debug(f"Card at ({x},{y}): {matched}")

        # Log result for adaptive learning
        if len(results) == 2:
            log_action('card_detection', success=True, details={
                'cards': results,
                'white_threshold': self.white_pixel_min
            })
        else:
            log_action('card_detection', success=False, details={
                'matched': len(results),
                'candidates': len(cards),
                'white_threshold': self.white_pixel_min
            })

        return results

    def _match_card(self, card_img: Image.Image) -> Optional[str]:
        """Match a card region against templates."""
        card_cv = cv2.cvtColor(np.array(card_img), cv2.COLOR_RGB2BGR)
        card_h, card_w = card_cv.shape[:2]

        best_match = None
        best_score = float('inf')

        for value in '23456789TJQKA':
            for suit in 'CDHS':
                card_key = value.lower() + suit.lower()
                if card_key not in self.table_dict:
                    continue

                try:
                    template_data = self.table_dict[card_key]
                    if isinstance(template_data, bytes):
                        template = cv2.imdecode(np.frombuffer(template_data, np.uint8), cv2.IMREAD_COLOR)
                    else:
                        continue

                    if template is None:
                        continue

                    templ_h, templ_w = template.shape[:2]

                    # Scale template if needed
                    if templ_w > card_w or templ_h > card_h:
                        scale = min(card_w / templ_w, card_h / templ_h) * 0.8
                        template = cv2.resize(template, (int(templ_w * scale), int(templ_h * scale)))

                    res = cv2.matchTemplate(card_cv, template, cv2.TM_SQDIFF_NORMED)
                    min_val, _, _, _ = cv2.minMaxLoc(res)

                    if min_val < best_score:
                        best_score = min_val
                        best_match = value + suit

                except Exception:
                    continue

        if best_match and best_score < 0.35:
            return best_match
        return None

    def click(self, x: int, y: int, button_name: str = "") -> bool:
        """Click at screen position (points) with verification.

        Returns True if click was verified successful, False otherwise.
        Logs result for adaptive learning.
        """
        # Take pre-click screenshot for verification
        pre_screenshot = ImageGrab.grab()

        # Focus GGSystem
        subprocess.run(['osascript', '-e',
            'tell application "System Events" to tell process "GGnet" to set frontmost to true'],
            capture_output=True, timeout=2)
        time.sleep(0.05)

        self.mouse.position = (x, y)
        time.sleep(0.03)
        self.mouse.click(Button.left)

        # Wait for UI to update
        click_verify_delay = get_threshold('click_verify_delay', 0.3)
        time.sleep(click_verify_delay)

        # Take post-click screenshot
        post_screenshot = ImageGrab.grab()

        # Verify click worked by comparing screenshots
        click_success = self._verify_click(pre_screenshot, post_screenshot, x, y)

        log.info(f"Clicked {button_name} at ({x}, {y}) - verified: {click_success}")
        self.actions_taken += 1
        self.last_action_time = time.time()

        # Log for adaptive learning
        log_action('button_click', success=click_success, details={
            'button': button_name,
            'position': (x, y),
            'verify_delay': click_verify_delay
        })

        # Report repeated failures
        if not click_success:
            learner = get_learner()
            rate = learner.get_success_rate('button_click')
            if rate < 0.5:
                report_issue('button_click',
                    f"Click verification failing often ({rate:.0%}). Button: {button_name} at ({x},{y})",
                    severity='high')

        return click_success

    def _verify_click(self, pre: Image.Image, post: Image.Image, x: int, y: int) -> bool:
        """Compare pre/post screenshots to verify click worked."""
        try:
            # Convert to numpy and compare region around click
            pre_arr = np.array(pre)
            post_arr = np.array(post)

            # Check 100x100 pixel region around click point (in pixels)
            px_x, px_y = x * RETINA_SCALE, y * RETINA_SCALE
            region_size = 100

            x1 = max(0, px_x - region_size)
            y1 = max(0, px_y - region_size)
            x2 = min(pre_arr.shape[1], px_x + region_size)
            y2 = min(pre_arr.shape[0], px_y + region_size)

            pre_region = pre_arr[y1:y2, x1:x2]
            post_region = post_arr[y1:y2, x1:x2]

            # Calculate difference
            diff = np.abs(pre_region.astype(float) - post_region.astype(float))
            mean_diff = np.mean(diff)

            # If significant change, click worked
            return mean_diff > 5.0
        except Exception as e:
            log.warning(f"Click verification error: {e}")
            return True  # Assume success if verification fails

    def decide_action(self, buttons: Dict, cards: List[str]) -> Optional[str]:
        """Decide what action to take.

        ALWAYS take an action if buttons are visible.
        Strategy: Conservative - fold unless we have good cards or it's free.
        """
        if not buttons:
            return None

        # If we can check for free (call visible but no fold), always check
        if 'call' in buttons and 'fold' not in buttons:
            log.info("Free check available - checking")
            return 'call'

        # If we have cards detected, make smart decision
        if cards and len(cards) == 2:
            ranks = [c[0] for c in cards]
            # Premium hands: call/raise
            if any(r in ranks for r in ['A', 'K', 'Q', 'J']):
                if 'raise' in buttons:
                    log.info(f"Premium cards {cards} - raising")
                    return 'raise'
                elif 'call' in buttons:
                    log.info(f"Premium cards {cards} - calling")
                    return 'call'
            # Pairs: call
            if ranks[0] == ranks[1]:
                if 'call' in buttons:
                    log.info(f"Pair {cards} - calling")
                    return 'call'

        # Cards not detected or weak hand - fold if we have to pay
        if 'fold' in buttons:
            log.info("No good cards / cards not detected - folding")
            return 'fold'

        # Fallback: click any available button
        for btn in ['call', 'raise', 'fold']:
            if btn in buttons:
                log.info(f"Fallback action: {btn}")
                return btn

        return None

    def process_table(self, table: TableWindow, screenshot: Image.Image) -> bool:
        """Process a single table with SELF-LEARNING auto-fix."""
        now = time.time()
        if now - self.last_action_time < self.action_cooldown:
            return False

        table_img = self.capture_table(table, screenshot)

        # Find action buttons FIRST
        buttons = self.find_buttons(table_img, table)

        # === SELF-LEARNING: If no buttons found, use vision analyzer to auto-fix ===
        if not buttons:
            log.info("SELF-LEARNING: No buttons found, running vision analyzer...")
            fix_result = auto_fix_buttons(table_img)

            if fix_result.get('fixed'):
                log.info("SELF-LEARNING: Vision analyzer updated thresholds, retrying...")
                # Reload thresholds and retry
                self.button_area_min = get_threshold('button_area_min', 2000)
                buttons = self.find_buttons(table_img, table)

                if buttons:
                    log.info(f"SELF-LEARNING: SUCCESS! Found buttons after auto-fix: {list(buttons.keys())}")
                else:
                    log.warning("SELF-LEARNING: Still no buttons after auto-fix")

        # Only check for Deal Me In if NO action buttons visible
        if not buttons:
            deal_me_in = self.find_deal_me_in(table_img, table)
            if deal_me_in:
                log.info("No buttons - Found 'Deal Me In' - clicking it")
                x, y = deal_me_in['screen_pt']
                self.click(x, y, "Deal Me In")
                return True
            return False

        log.info(f"Buttons found: {list(buttons.keys())}")

        # Try to detect cards
        cards = self.detect_cards(table_img)

        # === SELF-LEARNING: If no cards found and buttons are visible, try auto-fix ===
        if not cards and buttons:
            log.info("SELF-LEARNING: Buttons visible but no cards, running vision analyzer...")
            fix_result = auto_fix_cards(table_img)

            if fix_result.get('fixed'):
                log.info("SELF-LEARNING: Vision analyzer found cards, retrying...")
                # Reload thresholds and retry
                self.white_pixel_min = get_threshold('white_pixel_min', 150)
                cards = self.detect_cards(table_img)

                if cards:
                    log.info(f"SELF-LEARNING: SUCCESS! Found cards after auto-fix: {cards}")
            elif fix_result.get('reason') == 'cards_face_down':
                log.info("SELF-LEARNING: Cards are face-down (not your turn)")

        if cards:
            log.info(f"MY CARDS: {cards}")
        else:
            log.info("Cards not detected")

        # Decide and act
        action = self.decide_action(buttons, cards)
        if action and action in buttons:
            btn = buttons[action]
            x, y = btn['screen_pt']
            card_str = f" (cards: {cards})" if cards else ""
            self.click(x, y, f"{btn['name']}{card_str}")
            return True

        return False

    def run(self):
        """Main loop with adaptive learning."""
        print("=" * 60)
        print("AUTO PLAYER - Starting (with adaptive learning)")
        print("=" * 60)

        self.running = True
        self.load_templates()

        learner = get_learner()
        log.info(f"Adaptive thresholds: cooldown={self.action_cooldown}, "
                 f"white_min={self.white_pixel_min}, button_area={self.button_area_min}")

        while self.running:
            try:
                tables = self.find_tables()

                if not tables:
                    log_action('table_detection', success=False, details={'tables': 0})
                    time.sleep(1)
                    continue
                else:
                    log_action('table_detection', success=True, details={'tables': len(tables)})

                screenshot = ImageGrab.grab()

                for table in tables:
                    try:
                        self.process_table(table, screenshot)
                    except Exception as e:
                        log.warning(f"Error processing table: {e}")
                        report_issue('process_table', str(e), severity='medium')

                time.sleep(0.3)

            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"Error: {e}")
                report_issue('main_loop', str(e), severity='high')
                time.sleep(1)

        # End session and show summary
        summary = learner.end_session()
        print(f"\n{'=' * 60}")
        print(f"Session ended. Actions: {self.actions_taken}")
        print(f"Duration: {summary['duration_seconds']:.0f}s")
        print(f"\nRecommendations:")
        for rec in learner.get_recommendations():
            print(f"  {rec}")
        print(f"{'=' * 60}")


def main():
    from sys_core.tools.helper import init_logger
    init_logger(screenlevel=logging.INFO, filename='auto_player', logdir='log')

    player = AutoPlayer()
    try:
        player.run()
    except KeyboardInterrupt:
        print("\nStopping...")


if __name__ == "__main__":
    main()
