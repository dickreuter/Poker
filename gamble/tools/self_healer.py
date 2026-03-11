"""
SELF-HEALING DETECTOR - Autonomous Real-Time Fixes

This module makes the bot fix itself when detection fails:
1. Takes screenshot of actual game state
2. Analyzes what's really on screen
3. Auto-adjusts thresholds, colors, regions
4. Updates templates if needed
5. Retries with new parameters

NO MORE WAITING FOR CLAUDE TO FIX THINGS - THE BOT FIXES ITSELF.

Usage:
    from gamble.tools.self_healer import SelfHealer

    healer = SelfHealer()

    # When button detection fails:
    buttons = healer.heal_button_detection(table_screenshot)

    # When card detection fails:
    cards = healer.heal_card_detection(table_screenshot)
"""

import cv2
import json
import logging
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image

from gamble.tools.adaptive_learner import get_learner, log_action, get_threshold

log = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / 'data' / 'learning'
CALIBRATION_FILE = DATA_DIR / 'calibration.json'


class SelfHealer:
    """
    Autonomous self-healing detection system.

    When detection fails, this analyzes the actual screenshot and
    adjusts parameters to make it work - in real-time, no human needed.
    """

    def __init__(self):
        self.learner = get_learner()
        self.calibration = self._load_calibration()
        self.heal_attempts = 0
        self.max_heal_attempts = 5

    def _load_calibration(self) -> Dict:
        """Load saved calibration data."""
        if CALIBRATION_FILE.exists():
            try:
                return json.loads(CALIBRATION_FILE.read_text())
            except:
                pass
        return {
            'button_colors': {},
            'card_regions': {},
            'last_calibrated': None
        }

    def _save_calibration(self):
        """Save calibration data."""
        self.calibration['last_calibrated'] = datetime.now().isoformat()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CALIBRATION_FILE.write_text(json.dumps(self.calibration, indent=2))

    # ========== BUTTON HEALING ==========

    def heal_button_detection(self, screenshot: Image.Image,
                               expected_buttons: List[str] = None) -> Dict[str, Dict]:
        """
        When button detection fails, analyze the screenshot and find buttons anyway.

        Steps:
        1. Sample colors from bottom of screen where buttons should be
        2. Find all colored rectangles
        3. Classify by color (green=call, orange=raise, gray=fold)
        4. Update calibration with found colors
        5. Return button positions
        """
        log.info("SELF-HEALING: Attempting to find buttons...")

        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, w = img.shape[:2]

        # Search bottom 25% where buttons live
        bottom_region = hsv[int(h * 0.75):, :]
        bottom_bgr = img[int(h * 0.75):, :]

        buttons = {}

        # Strategy 1: Find all prominent colored rectangles
        colored_regions = self._find_colored_rectangles(bottom_region, bottom_bgr)

        if colored_regions:
            log.info(f"SELF-HEALING: Found {len(colored_regions)} colored regions")

            # Classify each region by its dominant color
            for region in colored_regions:
                x, y, rw, rh, avg_color = region
                button_type = self._classify_button_color(avg_color)

                if button_type and button_type not in buttons:
                    # Convert to full image coordinates
                    full_y = int(h * 0.75) + y
                    center_x = x + rw // 2
                    center_y = full_y + rh // 2

                    buttons[button_type] = {
                        'x_px': center_x,
                        'y_px': center_y,
                        'w': rw,
                        'h': rh,
                        'color': avg_color.tolist(),
                        'source': 'self_healed'
                    }

                    # Update calibration with this color
                    self._update_button_calibration(button_type, avg_color)
                    log.info(f"SELF-HEALING: Found {button_type} at ({center_x}, {center_y})")

        # Strategy 2: If still missing buttons, try text detection
        if len(buttons) < 2:
            text_buttons = self._find_buttons_by_text(screenshot)
            for btn_type, pos in text_buttons.items():
                if btn_type not in buttons:
                    buttons[btn_type] = pos

        if buttons:
            log_action('self_heal_buttons', success=True, details={
                'buttons_found': list(buttons.keys()),
                'method': 'color_analysis'
            })
        else:
            log_action('self_heal_buttons', success=False, details={
                'reason': 'no_buttons_found'
            })

        return buttons

    def _find_colored_rectangles(self, hsv_region: np.ndarray,
                                   bgr_region: np.ndarray) -> List[Tuple]:
        """Find all prominent colored rectangular regions."""
        rectangles = []

        # Look for saturated colors (S > 50) - buttons are colorful
        # Also look for gray (S < 50, V in 40-150 range) - fold button

        # Method 1: Saturated colors (call=green, raise=orange)
        sat_mask = hsv_region[:, :, 1] > 50
        val_mask = hsv_region[:, :, 2] > 50
        color_mask = (sat_mask & val_mask).astype(np.uint8) * 255

        # Method 2: Gray tones (fold button)
        gray_sat = hsv_region[:, :, 1] < 60
        gray_val = (hsv_region[:, :, 2] > 40) & (hsv_region[:, :, 2] < 160)
        gray_mask = (gray_sat & gray_val).astype(np.uint8) * 255

        for mask in [color_mask, gray_mask]:
            # Clean up mask
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 2000:  # Too small
                    continue

                x, y, w, h = cv2.boundingRect(cnt)

                # Button aspect ratio check (wider than tall, but not too wide)
                aspect = w / h if h > 0 else 0
                if not (1.2 < aspect < 6.0):
                    continue

                # Get average color of this region
                roi = bgr_region[y:y+h, x:x+w]
                avg_color = np.mean(roi, axis=(0, 1))

                rectangles.append((x, y, w, h, avg_color))

        # Sort by x position (left to right: fold, call/check, raise)
        rectangles.sort(key=lambda r: r[0])

        return rectangles

    def _classify_button_color(self, bgr_color: np.ndarray) -> Optional[str]:
        """Classify a BGR color as a button type."""
        b, g, r = bgr_color

        # Convert to HSV for better classification
        hsv = cv2.cvtColor(np.uint8([[bgr_color]]), cv2.COLOR_BGR2HSV)[0][0]
        h, s, v = hsv

        # Green (call/check): H around 35-85, high S
        if 35 <= h <= 85 and s > 50:
            return 'call'

        # Orange (raise/bet): H around 8-25, high S
        if 8 <= h <= 30 and s > 80:
            return 'raise'

        # Gray (fold): Low S, medium V
        if s < 60 and 40 < v < 160:
            return 'fold'

        # Red could also be fold on some themes
        if (h < 10 or h > 160) and s > 50:
            return 'fold'

        return None

    def _update_button_calibration(self, button_type: str, bgr_color: np.ndarray):
        """Update calibration with newly found button color."""
        hsv = cv2.cvtColor(np.uint8([[bgr_color]]), cv2.COLOR_BGR2HSV)[0][0]

        if button_type not in self.calibration['button_colors']:
            self.calibration['button_colors'][button_type] = []

        # Store last 10 color samples for averaging
        samples = self.calibration['button_colors'][button_type]
        samples.append(hsv.tolist())
        if len(samples) > 10:
            samples.pop(0)

        self._save_calibration()

        # Update adaptive thresholds based on learned colors
        self._update_color_thresholds(button_type, samples)

    def _update_color_thresholds(self, button_type: str, samples: List):
        """Update the adaptive thresholds with learned colors."""
        if len(samples) < 3:
            return

        arr = np.array(samples)
        h_min, s_min, v_min = np.min(arr, axis=0)
        h_max, s_max, v_max = np.max(arr, axis=0)

        # Add some margin
        margin = 10
        lower = [max(0, h_min - margin), max(0, s_min - margin), max(0, v_min - margin)]
        upper = [min(180, h_max + margin), min(255, s_max + margin), min(255, v_max + margin)]

        # Update thresholds in adaptive learner
        learner = get_learner()
        learner.set_threshold(f'hsv_{button_type}_lower', lower,
                             f'Auto-calibrated from {len(samples)} samples')
        learner.set_threshold(f'hsv_{button_type}_upper', upper,
                             f'Auto-calibrated from {len(samples)} samples')

        log.info(f"SELF-HEALING: Updated {button_type} color range to {lower} - {upper}")

    def _find_buttons_by_text(self, screenshot: Image.Image) -> Dict[str, Dict]:
        """Fallback: Find buttons by OCR text detection."""
        try:
            import pytesseract
        except ImportError:
            return {}

        buttons = {}

        try:
            data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)

            button_keywords = {
                'check': 'call',
                'call': 'call',
                'fold': 'fold',
                'raise': 'raise',
                'bet': 'raise',
                'all-in': 'raise',
                'allin': 'raise'
            }

            for i, text in enumerate(data['text']):
                text_lower = text.lower().strip()
                if text_lower in button_keywords:
                    btn_type = button_keywords[text_lower]
                    if btn_type not in buttons:
                        x = data['left'][i]
                        y = data['top'][i]
                        w = data['width'][i]
                        h = data['height'][i]

                        buttons[btn_type] = {
                            'x_px': x + w // 2,
                            'y_px': y + h // 2,
                            'w': w,
                            'h': h,
                            'source': 'ocr_healed'
                        }
                        log.info(f"SELF-HEALING: Found {btn_type} via OCR at ({x}, {y})")

        except Exception as e:
            log.debug(f"OCR healing failed: {e}")

        return buttons

    # ========== CARD HEALING ==========

    def heal_card_detection(self, screenshot: Image.Image,
                            table_region: Tuple[int, int, int, int] = None) -> Optional[Dict]:
        """
        When card detection fails, analyze the screenshot and find cards anyway.

        Steps:
        1. Look for white/light rectangles (card faces)
        2. Look for card-back patterns (red/blue with patterns)
        3. Adjust white threshold if cards are slightly darker
        4. Find any text that looks like card values (A, K, Q, J, 10-2)
        5. Update calibration with found regions
        """
        log.info("SELF-HEALING: Attempting to find cards...")

        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        h, w = img.shape[:2]

        # If table region provided, crop to it
        if table_region:
            x, y, tw, th = table_region
            img = img[y:y+th, x:x+tw]
            h, w = img.shape[:2]

        # Search bottom 40% where player cards are
        search_y = int(h * 0.60)
        search_x1 = int(w * 0.30)
        search_x2 = int(w * 0.70)
        search_region = img[search_y:, search_x1:search_x2]

        # Try multiple white thresholds
        thresholds_to_try = [200, 180, 160, 140, 120]

        for thresh in thresholds_to_try:
            cards = self._find_white_cards(search_region, thresh)
            if cards:
                # Update the threshold that worked
                learner = get_learner()
                current_thresh = get_threshold('white_pixel_min', 180)
                if thresh != current_thresh:
                    learner.set_threshold('white_pixel_min', thresh,
                                         f'Auto-adjusted: found cards at threshold {thresh}')
                    log.info(f"SELF-HEALING: Adjusted white_pixel_min from {current_thresh} to {thresh}")

                # Convert coordinates back to full image
                for card in cards:
                    card['x'] += search_x1
                    card['y'] += search_y
                    if table_region:
                        card['x'] += table_region[0]
                        card['y'] += table_region[1]

                log_action('self_heal_cards', success=True, details={
                    'cards_found': len(cards),
                    'threshold_used': thresh
                })

                return {'cards': cards, 'threshold': thresh}

        # Try finding card backs (when cards are face-down)
        card_backs = self._find_card_backs(search_region)
        if card_backs:
            log.info("SELF-HEALING: Found card backs (cards are face-down)")
            log_action('self_heal_cards', success=True, details={
                'cards_found': len(card_backs),
                'type': 'card_backs'
            })
            return {'cards': card_backs, 'type': 'face_down'}

        log_action('self_heal_cards', success=False, details={
            'reason': 'no_cards_found',
            'thresholds_tried': thresholds_to_try
        })

        return None

    def _find_white_cards(self, region: np.ndarray, threshold: int) -> List[Dict]:
        """Find white card-shaped rectangles."""
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

        # Clean up
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        cards = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 1500:  # Too small
                continue

            x, y, w, h = cv2.boundingRect(cnt)

            # Card aspect ratio (taller than wide)
            aspect = h / w if w > 0 else 0
            if not (1.2 < aspect < 2.0):
                continue

            cards.append({
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                'area': area
            })

        # Sort by x position (left card first)
        cards.sort(key=lambda c: c['x'])

        return cards[:2]  # Max 2 hole cards

    def _find_card_backs(self, region: np.ndarray) -> List[Dict]:
        """Find card-back patterns (typically red or blue with designs)."""
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        # Red card backs: H around 0-10 or 160-180
        red_mask1 = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([10, 255, 255]))
        red_mask2 = cv2.inRange(hsv, np.array([160, 100, 100]), np.array([180, 255, 255]))
        red_mask = red_mask1 | red_mask2

        # Blue card backs: H around 100-130
        blue_mask = cv2.inRange(hsv, np.array([100, 100, 100]), np.array([130, 255, 255]))

        combined = red_mask | blue_mask

        # Clean up
        kernel = np.ones((5, 5), np.uint8)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        cards = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 2000:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            aspect = h / w if w > 0 else 0
            if not (1.0 < aspect < 2.5):
                continue

            cards.append({
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                'type': 'back'
            })

        return cards[:2]

    # ========== REGION HEALING ==========

    def heal_search_region(self, screenshot: Image.Image,
                           element_type: str) -> Optional[Tuple[int, int, int, int]]:
        """
        When an element can't be found in expected region, scan the whole screen.

        Returns: (x, y, w, h) of the region where element was found, or None.
        """
        log.info(f"SELF-HEALING: Scanning full screen for {element_type}...")

        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        h, w = img.shape[:2]

        if element_type == 'buttons':
            # Scan for button-colored regions
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

            # Look for green (call) anywhere on screen
            green_mask = cv2.inRange(hsv, np.array([35, 50, 50]), np.array([85, 255, 255]))

            contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > 2000:
                    x, y, bw, bh = cv2.boundingRect(cnt)
                    # Found a green button - return the region around it
                    margin = 200
                    region = (
                        max(0, x - margin),
                        max(0, y - 50),
                        min(w, x + bw + margin * 2),
                        min(h, y + bh + 100)
                    )
                    log.info(f"SELF-HEALING: Found buttons region at {region}")

                    # Update calibration
                    self.calibration['button_regions'] = {
                        'y_start_pct': y / h,
                        'y_end_pct': (y + bh + 50) / h
                    }
                    self._save_calibration()

                    return region

        elif element_type == 'cards':
            # Scan for white rectangles anywhere
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)

            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if 1500 < area < 20000:  # Card-sized
                    x, y, cw, ch = cv2.boundingRect(cnt)
                    aspect = ch / cw if cw > 0 else 0
                    if 1.2 < aspect < 2.0:  # Card aspect ratio
                        margin = 100
                        region = (
                            max(0, x - margin),
                            max(0, y - 50),
                            min(w, x + cw + margin * 2),
                            min(h, y + ch + 100)
                        )
                        log.info(f"SELF-HEALING: Found cards region at {region}")

                        self.calibration['card_regions'] = {
                            'y_start_pct': y / h,
                            'y_end_pct': (y + ch) / h,
                            'x_start_pct': x / w,
                            'x_end_pct': (x + cw) / w
                        }
                        self._save_calibration()

                        return region

        return None

    # ========== FULL AUTO-HEAL ==========

    def auto_heal_table(self, screenshot: Image.Image) -> Dict:
        """
        Comprehensive auto-healing for a table screenshot.

        Tries to find everything and updates calibration.
        Returns dict with all found elements.
        """
        result = {
            'buttons': {},
            'cards': None,
            'healed': False
        }

        # Try to find buttons
        buttons = self.heal_button_detection(screenshot)
        if buttons:
            result['buttons'] = buttons
            result['healed'] = True

        # Try to find cards
        cards = self.heal_card_detection(screenshot)
        if cards:
            result['cards'] = cards
            result['healed'] = True

        if result['healed']:
            log.info(f"SELF-HEALING: Successfully healed - buttons: {list(result['buttons'].keys())}, "
                    f"cards: {'found' if result['cards'] else 'none'}")

        return result


    # ========== AUTONOMOUS SCREEN ANALYSIS ==========

    def analyze_screen(self, screenshot: Image.Image) -> Dict:
        """
        Analyze the entire screen to understand what's displayed and what action to take.

        This is the KEY to full autonomy - the bot looks at the screenshot,
        uses OCR to read text, and decides what to do.

        Returns:
            {
                'screen_type': 'lobby' | 'table' | 'dialog' | 'unknown',
                'action_needed': 'click_register' | 'click_fold' | 'wait' | etc,
                'action_target': {'x': x, 'y': y, 'text': 'Register'},
                'context': {...}  # Additional info found
            }
        """
        log.info("SCREEN ANALYSIS: Analyzing screenshot...")

        result = {
            'screen_type': 'unknown',
            'action_needed': None,
            'action_target': None,
            'context': {}
        }

        try:
            import pytesseract

            # Get full OCR of screen
            ocr_data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)

            # Collect all text and positions
            all_text = []
            text_elements = []

            for i, text in enumerate(ocr_data['text']):
                text = text.strip()
                if text:
                    all_text.append(text.lower())
                    text_elements.append({
                        'text': text,
                        'x': ocr_data['left'][i],
                        'y': ocr_data['top'][i],
                        'w': ocr_data['width'][i],
                        'h': ocr_data['height'][i],
                        'conf': ocr_data['conf'][i]
                    })

            full_text = ' '.join(all_text)
            result['context']['full_text'] = full_text[:500]

            # ===== DETECT SCREEN TYPE =====

            # Check for registration dialog
            if self._is_registration_dialog(full_text, text_elements):
                result['screen_type'] = 'dialog'
                result['context']['dialog_type'] = 'registration'

                # Find "Register" button
                register_btn = self._find_text_button(text_elements, ['register', 'ok', 'play'])
                if register_btn:
                    result['action_needed'] = 'click_register'
                    result['action_target'] = register_btn
                    log.info(f"SCREEN ANALYSIS: Found registration dialog, Register at ({register_btn['x']}, {register_btn['y']})")

            # Check for error/popup dialog
            elif self._is_error_dialog(full_text, text_elements):
                result['screen_type'] = 'dialog'
                result['context']['dialog_type'] = 'error'

                # Find "OK" or "Close" button
                ok_btn = self._find_text_button(text_elements, ['ok', 'close', 'x', 'cancel'])
                if ok_btn:
                    result['action_needed'] = 'click_close'
                    result['action_target'] = ok_btn
                    log.info(f"SCREEN ANALYSIS: Found error dialog, Close at ({ok_btn['x']}, {ok_btn['y']})")

            # Check for poker table with action needed
            elif self._is_poker_table(full_text, text_elements):
                result['screen_type'] = 'table'

                # Find action buttons
                action_btns = self._find_action_buttons(text_elements)
                if action_btns:
                    result['context']['available_actions'] = list(action_btns.keys())
                    # Prioritize: check > call > fold
                    for action in ['check', 'call', 'fold']:
                        if action in action_btns:
                            result['action_needed'] = f'click_{action}'
                            result['action_target'] = action_btns[action]
                            break

            # Check for lobby
            elif self._is_lobby(full_text, text_elements):
                result['screen_type'] = 'lobby'

                # Find "Play Now" button
                play_btn = self._find_text_button(text_elements, ['play now', 'play', 'now'])
                if play_btn:
                    result['action_needed'] = 'click_play_now'
                    result['action_target'] = play_btn

            log.info(f"SCREEN ANALYSIS: type={result['screen_type']}, action={result['action_needed']}")
            log_action('screen_analysis', success=True, details={
                'screen_type': result['screen_type'],
                'action_needed': result['action_needed']
            })

        except ImportError:
            log.warning("SCREEN ANALYSIS: pytesseract not available")
        except Exception as e:
            log.error(f"SCREEN ANALYSIS: Failed - {e}")
            log_action('screen_analysis', success=False, details={'error': str(e)})

        return result

    def _is_registration_dialog(self, full_text: str, elements: List[Dict]) -> bool:
        """Check if screen shows a registration/buy-in dialog."""
        # Must have BOTH buy-in indicator AND register/play button
        buyin_indicators = ['buy-in', 'buyin', 'buy in', 'number of games', 'total buy-in']
        button_indicators = ['register', 'cancel']

        has_buyin = any(ind in full_text for ind in buyin_indicators)
        has_button = any(ind in full_text for ind in button_indicators)

        # Must have both to confirm it's a registration dialog
        # (prevents false positive when just "register" appears in menu)
        return has_buyin and has_button

    def _is_error_dialog(self, full_text: str, elements: List[Dict]) -> bool:
        """Check if screen shows an error/warning dialog."""
        indicators = ['error', 'warning', 'failed', 'unable', 'cannot', 'sorry',
                      'connection', 'timeout', 'try again']
        return any(ind in full_text for ind in indicators)

    def _is_poker_table(self, full_text: str, elements: List[Dict]) -> bool:
        """Check if screen shows a poker table."""
        indicators = ['fold', 'call', 'check', 'raise', 'bet', 'all-in', 'allin',
                      'pot:', 'blinds', 'dealer']
        return sum(1 for ind in indicators if ind in full_text) >= 2

    def _is_lobby(self, full_text: str, elements: List[Dict]) -> bool:
        """Check if screen shows the lobby."""
        indicators = ['spin & gold', 'hold\'em', 'omaha', 'tournament', 'cash game',
                      'play now', 'game lobby', 'ggpoker']
        return any(ind in full_text for ind in indicators)

    def _find_text_button(self, elements: List[Dict], target_texts: List[str]) -> Optional[Dict]:
        """Find a button by its text content."""
        for elem in elements:
            text_lower = elem['text'].lower()
            for target in target_texts:
                if target in text_lower or text_lower in target:
                    if elem['w'] > 20 and elem['h'] > 10:  # Valid button size
                        return {
                            'x': elem['x'] + elem['w'] // 2,
                            'y': elem['y'] + elem['h'] // 2,
                            'text': elem['text'],
                            'confidence': elem['conf']
                        }
        return None

    def _find_action_buttons(self, elements: List[Dict]) -> Dict[str, Dict]:
        """Find poker action buttons."""
        buttons = {}
        action_keywords = {
            'fold': ['fold'],
            'call': ['call'],
            'check': ['check'],
            'raise': ['raise', 'bet'],
            'allin': ['all-in', 'allin', 'all in']
        }

        for elem in elements:
            text_lower = elem['text'].lower()
            for action, keywords in action_keywords.items():
                if any(kw in text_lower for kw in keywords):
                    if action not in buttons:
                        buttons[action] = {
                            'x': elem['x'] + elem['w'] // 2,
                            'y': elem['y'] + elem['h'] // 2,
                            'text': elem['text']
                        }
        return buttons

    def take_autonomous_action(self, screenshot: Image.Image) -> bool:
        """
        Analyze the screen and take appropriate action automatically.

        This is FULL AUTONOMY - the bot decides what to do based on what it sees.

        Returns:
            True if an action was taken, False if no action needed or failed
        """
        analysis = self.analyze_screen(screenshot)

        if not analysis['action_needed'] or not analysis['action_target']:
            log.info("AUTONOMOUS: No action needed")
            return False

        target = analysis['action_target']
        action = analysis['action_needed']

        log.info(f"AUTONOMOUS: Taking action '{action}' at ({target['x']}, {target['y']})")

        # Perform the click
        try:
            # Convert pixel position to points (Retina display)
            x_pt = target['x'] // 2
            y_pt = target['y'] // 2

            import Quartz

            # Focus GGPoker first
            import subprocess
            subprocess.run(['osascript', '-e',
                'tell application "System Events" to tell process "GGnet" to set frontmost to true'],
                capture_output=True, timeout=2)

            import time
            time.sleep(0.05)

            # Click
            down_event = Quartz.CGEventCreateMouseEvent(
                None, Quartz.kCGEventLeftMouseDown,
                (x_pt, y_pt), Quartz.kCGMouseButtonLeft
            )
            up_event = Quartz.CGEventCreateMouseEvent(
                None, Quartz.kCGEventLeftMouseUp,
                (x_pt, y_pt), Quartz.kCGMouseButtonLeft
            )

            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down_event)
            time.sleep(0.03)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up_event)

            log.info(f"AUTONOMOUS: Clicked {action} at ({x_pt}, {y_pt}) points")

            log_action('autonomous_action', success=True, details={
                'action': action,
                'screen_type': analysis['screen_type'],
                'click_position': (x_pt, y_pt),
                'target_text': target.get('text', 'unknown')
            })

            return True

        except Exception as e:
            log.error(f"AUTONOMOUS: Click failed - {e}")
            log_action('autonomous_action', success=False, details={
                'action': action,
                'error': str(e)
            })
            return False


# Singleton instance
_healer = None

def get_healer() -> SelfHealer:
    """Get the singleton self-healer instance."""
    global _healer
    if _healer is None:
        _healer = SelfHealer()
    return _healer


# Convenience functions
def heal_buttons(screenshot: Image.Image) -> Dict[str, Dict]:
    """Quick function to heal button detection."""
    return get_healer().heal_button_detection(screenshot)

def heal_cards(screenshot: Image.Image) -> Optional[Dict]:
    """Quick function to heal card detection."""
    return get_healer().heal_card_detection(screenshot)

def auto_heal(screenshot: Image.Image) -> Dict:
    """Quick function for full auto-heal."""
    return get_healer().auto_heal_table(screenshot)

def analyze_and_act(screenshot: Image.Image) -> bool:
    """Analyze screen with OCR and take autonomous action."""
    return get_healer().take_autonomous_action(screenshot)

def analyze_screen(screenshot: Image.Image) -> Dict:
    """Analyze screen to understand what's displayed."""
    return get_healer().analyze_screen(screenshot)
