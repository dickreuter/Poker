"""
Smart Card Detector - Visual Card Recognition for GGSystem

Finds and recognizes hole cards visually instead of relying on fixed coordinates.
Works by:
1. Finding white/cream colored card rectangles
2. Extracting rank (2-A) and suit (CDHS) from each card
3. Using OCR or template matching for recognition

Usage:
    from sys_core.tools.smart_card_detector import SmartCardDetector

    detector = SmartCardDetector()
    cards = detector.detect_cards(screenshot, table_region)
    # Returns: ['AS', 'KH'] or []
"""

import logging
import cv2
import numpy as np
from PIL import Image, ImageGrab
from typing import List, Tuple, Optional, Dict
import os

log = logging.getLogger(__name__)

# Try to import adaptive learner for learned thresholds
try:
    from sys_core.tools.adaptive_learner import get_threshold, log_action
    LEARNER_AVAILABLE = True
except ImportError:
    LEARNER_AVAILABLE = False
    def get_threshold(name, default): return default
    def log_action(*args, **kwargs): pass


class SmartCardDetector:
    """
    Detect and recognize poker cards visually.

    Uses multiple detection strategies:
    1. White region detection (face-up cards)
    2. Template matching against stored card images
    3. Color-based suit detection with OCR for rank

    SELF-LEARNING: Uses learned thresholds from adaptive_learner when available.
    """

    # Suit colors (HSV)
    COLORS = {
        'red': {'lower': np.array([0, 100, 100]), 'upper': np.array([15, 255, 255])},      # Hearts, Diamonds
        'red2': {'lower': np.array([165, 100, 100]), 'upper': np.array([180, 255, 255])},  # Red wraps
        'black': {'lower': np.array([0, 0, 0]), 'upper': np.array([180, 255, 50])},        # Spades, Clubs
        'blue': {'lower': np.array([100, 100, 100]), 'upper': np.array([130, 255, 255])},  # Blue diamonds in 4-color
        'green': {'lower': np.array([35, 100, 100]), 'upper': np.array([85, 255, 255])},   # Green clubs in 4-color
    }

    # Card dimensions (approximate)
    MIN_CARD_WIDTH = 30
    MIN_CARD_HEIGHT = 40
    MAX_CARD_WIDTH = 150
    MAX_CARD_HEIGHT = 200

    def __init__(self, table_dict: Dict = None):
        self.table_dict = table_dict

        # Get learned white_pixel_min threshold (default 120)
        self.white_pixel_min = get_threshold('white_pixel_min', 120)
        log.debug(f"SmartCardDetector using white_pixel_min={self.white_pixel_min} (learned={LEARNER_AVAILABLE})")

        # Build thresholds dynamically based on learned value
        # Start from learned threshold and go down in steps
        self.CARD_BG_THRESHOLDS = self._build_thresholds()

        # Legacy single threshold for compatibility
        self.CARD_BG_LOWER = np.array([0, 0, self.white_pixel_min])
        self.CARD_BG_UPPER = np.array([180, 80, 255])

    def _build_thresholds(self) -> list:
        """Build card background thresholds starting from learned value."""
        base = self.white_pixel_min
        return [
            # Start with learned threshold
            {'lower': np.array([0, 0, base + 40]), 'upper': np.array([180, 40, 255])},
            # A bit more relaxed
            {'lower': np.array([0, 0, base + 20]), 'upper': np.array([180, 60, 255])},
            # At learned threshold
            {'lower': np.array([0, 0, base]), 'upper': np.array([180, 80, 255])},
            # Below learned (catch edge cases)
            {'lower': np.array([0, 0, max(80, base - 20)]), 'upper': np.array([180, 100, 255])},
        ]

    def detect_cards(self, screenshot: Image.Image, table_region: Tuple[int, int, int, int]) -> List[str]:
        """
        Detect hole cards in a table screenshot.

        Uses multiple detection strategies for robustness:
        1. Try multiple white thresholds
        2. Fall back to template matching if visual detection fails

        Args:
            screenshot: Full screen PIL Image
            table_region: (x, y, width, height) of the table

        Returns:
            List of card strings like ['AS', 'KH'] or empty list
        """
        x, y, w, h = table_region

        # DYNAMIC: Search the ENTIRE bottom half of the table
        search_x1 = x
        search_x2 = x + w
        search_y1 = y + int(h * 0.45)  # Bottom 55% of table
        search_y2 = y + h

        # Crop search region
        search_region = screenshot.crop((search_x1, search_y1, search_x2, search_y2))
        img = np.array(search_region)
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

        # Try multiple thresholds from strict to lenient
        best_contours = []
        best_threshold_idx = -1

        for idx, threshold in enumerate(self.CARD_BG_THRESHOLDS):
            mask = cv2.inRange(hsv, threshold['lower'], threshold['upper'])

            # Clean up mask
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Count valid card-sized contours
            valid_contours = [c for c in contours if cv2.contourArea(c) > 800]

            if len(valid_contours) > len(best_contours):
                best_contours = valid_contours
                best_threshold_idx = idx

            # If we found 2+ large white regions, use this threshold
            if len(valid_contours) >= 2:
                log.debug(f"Card detection: Using threshold {idx} (found {len(valid_contours)} candidates)")
                break

        contours = best_contours
        if best_threshold_idx >= 0:
            log.debug(f"Card detection: Best threshold index {best_threshold_idx} with {len(contours)} contours")

        # Collect ALL card-shaped contours
        search_h, search_w = img.shape[:2]
        card_candidates = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 1000:  # Need substantial area for cards
                continue

            cx, cy, cw, ch = cv2.boundingRect(cnt)

            # Cards region should be reasonably sized
            if cw < 50 or ch < 40:
                continue
            if cw > 500 or ch > 300:
                continue

            # Score: prefer bottom-center regions (player's hole cards)
            # Higher Y = lower on screen = player's cards (not community cards)
            center_x = cx + cw // 2
            center_y = cy + ch // 2

            # Horizontal center score (0-1, higher = closer to center)
            x_center_score = 1.0 - abs(center_x - search_w // 2) / (search_w // 2)
            # Vertical bottom score (0-1, higher = lower on screen)
            y_bottom_score = center_y / search_h

            # Combined score: prioritize bottom-center
            score = (y_bottom_score * 0.6) + (x_center_score * 0.4) + (area / 50000)

            card_candidates.append({
                'region': (cx, cy, cw, ch),
                'area': area,
                'score': score
            })

        if not card_candidates:
            log.debug("No card candidates found")
            return []

        # Pick best candidate (highest score = bottom-center, large area)
        best = max(card_candidates, key=lambda c: c['score'])
        best_region = best['region']
        best_area = best['area']

        if not best_region:
            log.debug("No card region found")
            return []

        cx, cy, cw, ch = best_region
        log.debug(f"Found card region: ({cx},{cy}) {cw}x{ch}, area={best_area}")

        # ALWAYS split into left and right cards - we know there are 2 hole cards
        # Left card is first 55% (slight overlap), right card is last 55%
        left_w = int(cw * 0.55)
        right_start = int(cw * 0.45)
        right_w = cw - right_start

        card_regions = [
            (cx, cy, left_w, ch),
            (cx + right_start, cy, right_w, ch)
        ]
        log.debug(f"Split into left ({left_w}px) and right ({right_w}px) cards")

        cards = []
        for i, (rx, ry, rw, rh) in enumerate(card_regions):
            # Extract card image
            card_img = search_region.crop((rx, ry, rx + rw, ry + rh))

            # Try to recognize the card
            card = self._recognize_card(card_img, i)
            if card:
                cards.append(card)
                log.debug(f"Card {i}: {card}")

        return cards

    def _recognize_card(self, card_img: Image.Image, index: int) -> Optional[str]:
        """
        Recognize a single card image.

        Args:
            card_img: PIL Image of just the card
            index: Card index (0=left, 1=right)

        Returns:
            Card string like 'AS' or None
        """
        # Try template matching if we have templates
        if self.table_dict:
            card = self._match_card_template(card_img)
            if card:
                return card

        # Fallback to color-based suit detection + OCR
        return self._recognize_by_features(card_img, index)

    def _match_card_template(self, card_img: Image.Image) -> Optional[str]:
        """Match card against stored templates by searching for template within card image."""
        CARD_VALUES = '23456789TJQKA'
        CARD_SUITES = 'CDHS'

        card_cv = cv2.cvtColor(np.array(card_img), cv2.COLOR_RGB2BGR)
        card_h, card_w = card_cv.shape[:2]

        best_match = None
        best_score = float('inf')

        for value in CARD_VALUES:
            for suit in CARD_SUITES:
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

                    # Template must be smaller than card to search within it
                    if templ_w > card_w or templ_h > card_h:
                        # Scale template down to fit within card
                        scale = min(card_w / templ_w, card_h / templ_h) * 0.8
                        template = cv2.resize(template, (int(templ_w * scale), int(templ_h * scale)))

                    # Search for template WITHIN the card image (correct approach)
                    res = cv2.matchTemplate(card_cv, template, cv2.TM_SQDIFF_NORMED)
                    min_val, _, _, _ = cv2.minMaxLoc(res)

                    if min_val < best_score:
                        best_score = min_val
                        best_match = value + suit

                except Exception as e:
                    log.debug(f"Error matching {card_key}: {e}")
                    continue

        if best_match and best_score < 0.35:
            log.debug(f"Template matched: {best_match} (score: {best_score:.4f})")
            return best_match

        return None

    def _recognize_by_features(self, card_img: Image.Image, index: int) -> Optional[str]:
        """
        Recognize card by visual features (suit color + OCR for rank).
        Uses color detection for suit and OCR for rank.
        """
        img = np.array(card_img)
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

        # Detect suit by color
        # GGPoker uses STANDARD 2-color deck:
        # - Hearts = Red, Diamonds = Red
        # - Spades = Black, Clubs = Black
        # We need to use suit SHAPE detection to distinguish H/D and S/C
        suit = None

        # Check for red (Hearts or Diamonds)
        red_mask = cv2.inRange(hsv, self.COLORS['red']['lower'], self.COLORS['red']['upper'])
        red_mask2 = cv2.inRange(hsv, self.COLORS['red2']['lower'], self.COLORS['red2']['upper'])
        red_total = np.sum(red_mask) + np.sum(red_mask2)

        # Check for black (Spades or Clubs)
        black_mask = cv2.inRange(hsv, self.COLORS['black']['lower'], self.COLORS['black']['upper'])
        black_total = np.sum(black_mask)

        # Determine if red or black suit
        if red_total > black_total * 1.5:  # Clearly red
            # Red suit - need to distinguish Hearts vs Diamonds
            suit = self._distinguish_red_suit(card_img)
            log.debug(f"Detected RED suit -> {suit} (red={red_total}, black={black_total})")
        elif black_total > red_total * 1.5:  # Clearly black
            # Black suit - need to distinguish Spades vs Clubs
            suit = self._distinguish_black_suit(card_img)
            log.debug(f"Detected BLACK suit -> {suit} (red={red_total}, black={black_total})")
        else:
            # Unclear - try OCR on suit symbol
            suit = self._ocr_suit_symbol(card_img)
            log.debug(f"Suit unclear, OCR detected -> {suit} (red={red_total}, black={black_total})")

        # Extract rank using OCR on the top-left corner of the card
        rank = self._extract_rank_with_ocr(card_img)

        if suit:
            result = f"{rank}{suit}"
            log.debug(f"Feature-based detection: rank={rank}, suit={suit} -> {result}")
            return result

        return None

    def _extract_rank_with_ocr(self, card_img: Image.Image) -> str:
        """
        Extract card rank using OCR on the top-left corner where rank appears.

        Args:
            card_img: PIL Image of the full card

        Returns:
            str: Single character rank (2-9, T, J, Q, K, A) or '?' if failed
        """
        try:
            from sys_core.tools.screen_operations import get_card_rank_ocr_multi_threshold

            # Crop the rank corner (top-left area where rank is displayed)
            w, h = card_img.size

            # On GGPoker cards, rank is in top-left corner
            # Crop roughly top 45% height and left 45% width
            rank_x2 = int(w * 0.45)
            rank_y2 = int(h * 0.45)

            # Ensure minimum size
            rank_x2 = max(rank_x2, 20)
            rank_y2 = max(rank_y2, 25)

            rank_region = card_img.crop((0, 0, rank_x2, rank_y2))

            # Use multi-threshold OCR for robustness
            rank = get_card_rank_ocr_multi_threshold(rank_region)

            if rank != '?':
                log.debug(f"OCR extracted rank: {rank}")

            return rank

        except Exception as e:
            log.debug(f"Rank OCR extraction failed: {e}")
            return '?'

    def _distinguish_red_suit(self, card_img: Image.Image) -> str:
        """
        Distinguish Hearts from Diamonds (both are red in 2-color deck).
        Uses OCR to read the suit symbol.
        """
        # Try OCR first
        suit = self._ocr_suit_symbol(card_img)
        if suit in ['H', 'D']:
            return suit
        # Default to Hearts if unclear (more common)
        return 'H'

    def _distinguish_black_suit(self, card_img: Image.Image) -> str:
        """
        Distinguish Spades from Clubs (both are black in 2-color deck).
        Uses OCR to read the suit symbol.
        """
        # Try OCR first
        suit = self._ocr_suit_symbol(card_img)
        if suit in ['S', 'C']:
            return suit
        # Default to Spades if unclear (more common in poker hands)
        return 'S'

    def _ocr_suit_symbol(self, card_img: Image.Image) -> str:
        """
        Use OCR to read the suit symbol from the card.
        Looks for suit symbols: ♠♥♦♣ or text S/H/D/C
        """
        try:
            import pytesseract

            # Crop the suit area (below the rank, typically 30-60% from top, left 40%)
            w, h = card_img.size
            suit_region = card_img.crop((0, int(h * 0.25), int(w * 0.5), int(h * 0.6)))

            # OCR the suit symbol
            text = pytesseract.image_to_string(suit_region, config='--psm 10').strip().upper()

            # Map symbols to letters
            symbol_map = {
                '♠': 'S', '♤': 'S', 'A': 'S',  # Spade variations
                '♥': 'H', '♡': 'H', 'V': 'H',  # Heart variations
                '♦': 'D', '♢': 'D', 'O': 'D',  # Diamond variations
                '♣': 'C', '♧': 'C', '4': 'C',  # Club variations
                'S': 'S', 'H': 'H', 'D': 'D', 'C': 'C'
            }

            for char in text:
                if char in symbol_map:
                    detected_suit = symbol_map[char]
                    log.debug(f"OCR suit symbol: '{char}' -> {detected_suit}")
                    # SELF-LEARNING: Log successful suit detection for future learning
                    self._log_suit_detection(card_img, detected_suit, text)
                    return detected_suit

            log.debug(f"OCR suit failed, text was: '{text}'")
            # SELF-LEARNING: Log failed suit detection
            self._log_suit_detection(card_img, '?', text, success=False)
            return 'S'  # Default to Spades

        except Exception as e:
            log.debug(f"Suit OCR failed: {e}")
            return 'S'  # Default to Spades

    def _log_suit_detection(self, card_img: Image.Image, suit: str, ocr_text: str, success: bool = True):
        """
        SELF-LEARNING: Log suit detection results for analysis and improvement.
        Saves the card image and detection result so we can review errors.
        """
        try:
            from sys_core.tools.adaptive_learner import log_action
            import os
            from datetime import datetime

            # Log the detection
            log_action(
                'suit_detection',
                success=success,
                details={
                    'detected_suit': suit,
                    'ocr_text': ocr_text,
                    'timestamp': datetime.now().isoformat()
                }
            )

            # If detection failed, save the card image for analysis
            if not success:
                debug_dir = '/Users/sebastian/Developer/Gamble/data/learning/suit_errors/'
                os.makedirs(debug_dir, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                card_img.save(f'{debug_dir}/suit_fail_{timestamp}.png')
                log.info(f"SELF-LEARNING: Saved suit detection failure for analysis")

        except Exception as e:
            log.debug(f"Could not log suit detection: {e}")

    def detect_cards_simple(self, screenshot: Image.Image, tlc: Tuple[int, int]) -> List[str]:
        """
        Simple card detection using fixed coordinates relative to TLC.
        This is the fallback method that mirrors the original approach.

        Args:
            screenshot: Cropped table screenshot
            tlc: Top-left corner position

        Returns:
            List of card strings
        """
        # These coordinates work for the current GGSystem layout
        # Cards are at bottom center of table, roughly:
        # Left card: ~38-45% from left, 70-90% from top
        # Right card: ~55-62% from left, 70-90% from top

        width, height = screenshot.size

        left_x1 = int(width * 0.38)
        left_x2 = int(width * 0.48)
        left_y1 = int(height * 0.72)
        left_y2 = int(height * 0.92)

        right_x1 = int(width * 0.52)
        right_x2 = int(width * 0.62)
        right_y1 = int(height * 0.72)
        right_y2 = int(height * 0.92)

        left_card = screenshot.crop((left_x1, left_y1, left_x2, left_y2))
        right_card = screenshot.crop((right_x1, right_y1, right_x2, right_y2))

        cards = []

        # Try to recognize each card
        if self.table_dict:
            left_result = self._match_card_template(left_card)
            if left_result:
                cards.append(left_result)

            right_result = self._match_card_template(right_card)
            if right_result:
                cards.append(right_result)

        return cards


def detect_hole_cards(screenshot: Image.Image, table_region: Tuple[int, int, int, int],
                     table_dict: Dict = None) -> List[str]:
    """
    Convenience function to detect hole cards.

    Args:
        screenshot: Full screen PIL Image
        table_region: Table bounding box
        table_dict: Optional table template for matching

    Returns:
        List of card strings like ['AS', 'KH']
    """
    detector = SmartCardDetector(table_dict)
    return detector.detect_cards(screenshot, table_region)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("Smart Card Detector Test")
    print("=" * 40)

    # Take screenshot
    screenshot = ImageGrab.grab()
    print(f"Screenshot: {screenshot.size}")

    # Find table using smart finder
    from sys_core.tools.smart_table_finder import SmartTableFinder

    finder = SmartTableFinder()
    table = finder.find_active_table(screenshot)

    if not table:
        print("No table found!")
        exit(1)

    print(f"Table at ({table.x}, {table.y}) {table.width}x{table.height}")

    # Try to detect cards
    detector = SmartCardDetector()
    table_region = (table.x, table.y, table.width, table.height)
    cards = detector.detect_cards(screenshot, table_region)

    print(f"\nDetected cards: {cards}")

    # Save debug images
    os.makedirs('/tmp/poker_debug', exist_ok=True)

    # Crop and save card search region for debugging
    x, y, w, h = table_region
    search_x1 = x + int(w * 0.30)
    search_x2 = x + int(w * 0.70)
    search_y1 = y + int(h * 0.55)
    search_y2 = y + int(h * 0.95)

    search_region = screenshot.crop((search_x1, search_y1, search_x2, search_y2))
    search_region.save('/tmp/poker_debug/card_search_debug.png')
    print("\nSaved debug image to /tmp/poker_debug/card_search_debug.png")
