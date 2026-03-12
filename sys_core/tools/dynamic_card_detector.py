"""
Dynamic Card Detector - Finds and reads player cards using visual detection.

Instead of relying on fixed template coordinates that break when:
- Table window is moved
- Different table type (Rush vs Spin & Gold)
- GGSystem UI updates

This module:
1. Finds the player's card area dynamically by detecting bright card faces
2. Extracts card corners for rank/suit recognition
3. Uses template matching with adaptive thresholds

Usage:
    from sys_core.tools.dynamic_card_detector import DynamicCardDetector

    detector = DynamicCardDetector(table_dict)
    cards = detector.detect_cards(screenshot, table_window)
    # Returns: ['Kh', 'Qs'] or []
"""

import logging
import cv2
import numpy as np
from PIL import Image
from typing import List, Tuple, Optional, Dict
import base64
import io

log = logging.getLogger(__name__)

# Card detection parameters - search ENTIRE bottom half
# Visual detection (white card backgrounds) finds actual positions
CARD_SEARCH_REGION = {
    'y_start': 0.45,  # Start at 45% down (bottom 55% of table)
    'y_end': 1.0,     # End at bottom
    'x_start': 0.0,   # Full width
    'x_end': 1.0,     # Full width
}

# Adaptive thresholds for template matching
CARD_THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]


class DynamicCardDetector:
    """Detects player cards dynamically without fixed coordinates."""

    def __init__(self, table_dict: Dict = None):
        """
        Initialize detector.

        Args:
            table_dict: Template dictionary with card images (optional)
        """
        self.table_dict = table_dict or {}
        self._card_templates = {}
        self._load_card_templates()

    def _load_card_templates(self):
        """Load card templates from table_dict."""
        if not self.table_dict:
            return

        suits = ['h', 'd', 'c', 's']
        values = ['a', 'k', 'q', 'j', 't', '9', '8', '7', '6', '5', '4', '3', '2']

        for value in values:
            for suit in suits:
                card_key = value + suit
                if card_key in self.table_dict:
                    try:
                        img_data = base64.b64decode(self.table_dict[card_key])
                        img = Image.open(io.BytesIO(img_data))
                        # Convert to cv2 and normalize size
                        cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                        # Resize all templates to consistent size
                        cv_img = cv2.resize(cv_img, (30, 45))
                        self._card_templates[card_key.upper()] = cv_img
                    except Exception as e:
                        log.debug(f"Could not load template for {card_key}: {e}")

        log.info(f"Loaded {len(self._card_templates)} card templates")

    def find_card_regions(self, table_img: Image.Image) -> List[Dict]:
        """
        Find regions containing player cards.

        Args:
            table_img: Cropped table image (PIL)

        Returns:
            List of dicts with 'x', 'y', 'w', 'h' for each card found
        """
        img = cv2.cvtColor(np.array(table_img), cv2.COLOR_RGB2BGR)
        h, w = img.shape[:2]

        # Define search region (bottom center of table where player cards are)
        y1 = int(h * CARD_SEARCH_REGION['y_start'])
        y2 = int(h * CARD_SEARCH_REGION['y_end'])
        x1 = int(w * CARD_SEARCH_REGION['x_start'])
        x2 = int(w * CARD_SEARCH_REGION['x_end'])

        region = img[y1:y2, x1:x2]

        # Convert to grayscale and find bright areas (card faces)
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

        # Cards are bright white/cream colored
        _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)

        # Clean up noise
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        cards = []
        for contour in contours:
            area = cv2.contourArea(contour)
            x, y, cw, ch = cv2.boundingRect(contour)

            # Card-like dimensions (taller than wide, reasonable size)
            if area > 3000 and ch > cw * 1.2 and ch < cw * 2.5:
                if cw > 40 and ch > 60 and cw < 150 and ch < 200:
                    cards.append({
                        'x': x1 + x,
                        'y': y1 + y,
                        'w': cw,
                        'h': ch,
                        'area': area
                    })

        # Sort by x position (left to right)
        cards.sort(key=lambda c: c['x'])

        # We expect 2 cards - if we found more, take the 2 largest
        if len(cards) > 2:
            cards.sort(key=lambda c: c['area'], reverse=True)
            cards = cards[:2]
            cards.sort(key=lambda c: c['x'])

        log.debug(f"Found {len(cards)} card regions")
        return cards

    def extract_card_corner(self, table_img: Image.Image, card_region: Dict) -> Image.Image:
        """
        Extract the top-left corner of a card where rank/suit are shown.

        Args:
            table_img: Full table image
            card_region: Dict with x, y, w, h

        Returns:
            PIL Image of the card corner
        """
        x, y, w, h = card_region['x'], card_region['y'], card_region['w'], card_region['h']

        # Extract top-left corner (about 40% width, 50% height)
        corner_w = int(w * 0.45)
        corner_h = int(h * 0.55)

        corner = table_img.crop((x, y, x + corner_w, y + corner_h))
        return corner

    def match_card(self, card_corner: Image.Image) -> Tuple[str, float]:
        """
        Match a card corner against templates.

        Args:
            card_corner: PIL Image of card corner

        Returns:
            Tuple of (card_name, score) e.g., ('KH', 0.15)
        """
        if not self._card_templates:
            return ('', 1.0)

        # Convert to cv2 and resize to match template size
        img = cv2.cvtColor(np.array(card_corner), cv2.COLOR_RGB2BGR)
        img = cv2.resize(img, (30, 45))

        best_match = ''
        best_score = 1.0

        for card_name, template in self._card_templates.items():
            result = cv2.matchTemplate(img, template, cv2.TM_SQDIFF_NORMED)
            min_val, _, _, _ = cv2.minMaxLoc(result)

            if min_val < best_score:
                best_score = min_val
                best_match = card_name

        return (best_match, best_score)

    def detect_cards(self, table_img: Image.Image) -> List[str]:
        """
        Detect player's hole cards.

        Args:
            table_img: Cropped table image

        Returns:
            List of card names e.g., ['KH', 'QS'] or []
        """
        # Find card regions
        card_regions = self.find_card_regions(table_img)

        if len(card_regions) < 2:
            log.debug(f"Found {len(card_regions)} cards, need 2")
            return []

        cards = []
        for i, region in enumerate(card_regions[:2]):
            corner = self.extract_card_corner(table_img, region)
            card_name, score = self.match_card(corner)

            # Use adaptive threshold
            matched = False
            for threshold in CARD_THRESHOLDS:
                if score <= threshold:
                    cards.append(card_name)
                    log.debug(f"Card {i+1}: {card_name} (score: {score:.3f}, threshold: {threshold})")
                    matched = True
                    break

            if not matched:
                log.warning(f"Card {i+1}: No match found (best: {card_name} @ {score:.3f})")

        # Verify we found 2 different cards
        if len(cards) == 2 and cards[0] != cards[1]:
            return cards
        elif len(cards) == 2:
            log.warning(f"Found same card twice: {cards}")
            return []
        else:
            return []

    def detect_cards_ocr(self, table_img: Image.Image) -> List[str]:
        """
        Alternative: Detect cards using OCR on bright regions.

        This is a fallback when template matching fails.
        """
        # TODO: Implement OCR-based detection using pytesseract
        pass


def detect_cards_simple(screenshot: Image.Image, table_window=None) -> List[str]:
    """
    Simple function to detect cards from a screenshot.

    Args:
        screenshot: Full screen PIL Image
        table_window: Optional TableWindow object for cropping

    Returns:
        List of card names
    """
    from sys_core.tools.mongo_manager import MongoManager

    # Get table dict for templates
    mongo = MongoManager()
    table_dict = mongo.get_table("Official GGSystem 6player")

    detector = DynamicCardDetector(table_dict)

    if table_window:
        # Crop to table
        table_img = screenshot.crop((
            table_window.x_px, table_window.y_px,
            table_window.x_px + table_window.w_px,
            table_window.y_px + table_window.h_px
        ))
    else:
        # Assume screenshot is already the table
        table_img = screenshot

    return detector.detect_cards(table_img)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    from PIL import ImageGrab
    from sys_core.tools.dynamic_table_finder import DynamicTableFinder
    from sys_core.tools.mongo_manager import MongoManager

    print("Dynamic Card Detector Test")
    print("=" * 50)

    # Find table
    finder = DynamicTableFinder()
    tables = finder.find_poker_tables()

    if not tables:
        print("No poker table found!")
        exit(1)

    table = tables[0]
    print(f"Table: {table.name}")

    # Get template
    mongo = MongoManager()
    table_dict = mongo.get_table("Official GGSystem 6player")

    # Create detector
    detector = DynamicCardDetector(table_dict)

    # Capture and detect
    screenshot = ImageGrab.grab()
    table_img = table.capture(screenshot)

    # Find card regions
    regions = detector.find_card_regions(table_img)
    print(f"\nCard regions found: {len(regions)}")
    for i, r in enumerate(regions):
        print(f"  Card {i+1}: x={r['x']}, y={r['y']}, {r['w']}x{r['h']}")

    # Detect cards
    cards = detector.detect_cards(table_img)
    print(f"\nDetected cards: {cards}")

    # Save debug image
    table_img.save('/tmp/card_detection_debug.png')
    print(f"\nDebug image saved to /tmp/card_detection_debug.png")
