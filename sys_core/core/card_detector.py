"""
UNIFIED CARD DETECTOR - Single Source of Truth for Finding Player Cards

Consolidates functionality from:
- scraper/table_scraper.py (get_my_cards, get_my_cards2, template matching)
- scraper/table_scraper_nn.py (neural network card detection)
- tools/smart_card_detector.py (SmartCardDetector class)
- tools/dynamic_card_detector.py (brightness-based detection)
- tools/auto_player.py (white mask detection)
- tools/ten_table_bot.py (VisualDetector card detection)
- tools/vision_analyzer.py (analyze_cards)
- tools/self_healer.py (heal_card_detection)

This is now THE ONLY card detector. All bots should use this.

Detection Strategy (in order):
1. Template Matching - original approach, works with MongoDB templates
2. White Region Detection - finds white card rectangles on green felt
3. Self-Healing - tries multiple thresholds if standard ones fail

Usage:
    from sys_core.core import CardDetector

    detector = CardDetector()

    # Detect player's hole cards
    cards = detector.detect_player_cards(table_image)
    # Returns: ['AH', 'KS'] or [] if not detected

    # Detect community cards (board)
    board = detector.detect_board_cards(table_image)
    # Returns: ['AS', 'KH', 'QD', 'JC', '10S'] or []
"""

import cv2
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from PIL import Image
from pathlib import Path

from sys_core.core.constants import (
    CARD_WHITE_THRESHOLD_DEFAULT,
    CARD_WHITE_THRESHOLD_MIN,
    CARD_WHITE_THRESHOLD_MAX,
    CARD_REGION_Y_START,
    CARD_REGION_Y_END,
    CARD_REGION_X_START,
    CARD_REGION_X_END,
    CARD_MIN_AREA,
    CARD_MAX_AREA,
    CARD_ASPECT_RATIO_MIN,
    CARD_ASPECT_RATIO_MAX,
    TEMPLATE_MATCH_THRESHOLD,
    RETINA_SCALE,
)

log = logging.getLogger(__name__)


@dataclass
class DetectedCard:
    """Represents a detected card with position and identification."""
    rank: str           # 'A', 'K', 'Q', 'J', '10', '9', ..., '2'
    suit: str           # 'H', 'D', 'C', 'S' (Hearts, Diamonds, Clubs, Spades)
    x_px: int           # X position in table image
    y_px: int           # Y position in table image
    w_px: int           # Width in pixels
    h_px: int           # Height in pixels
    confidence: float   # Detection confidence (0-1)
    method: str         # 'template', 'white_region', 'healed'

    @property
    def code(self) -> str:
        """Return card code like 'AH', 'KS', '10D'."""
        return f"{self.rank}{self.suit}"

    def __repr__(self):
        return f"DetectedCard({self.code}, conf={self.confidence:.2f})"


class CardDetector:
    """
    Unified card detection using multiple strategies.

    Strategy order:
    1. Template Matching (if templates available)
    2. White Region Detection (visual detection)
    3. Self-Healing (try multiple thresholds)
    """

    # Card rank and suit mappings
    RANKS = ['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']
    SUITS = ['H', 'D', 'C', 'S']  # Hearts, Diamonds, Clubs, Spades

    def __init__(self, table_dict: Dict = None, learner=None):
        """
        Initialize the card detector.

        Args:
            table_dict: Optional table configuration from MongoDB with card templates
            learner: Optional UnifiedLearner for adaptive thresholds
        """
        self.table_dict = table_dict
        self.learner = learner
        self.templates = self._load_templates()
        self._white_threshold = self._get_white_threshold()

    def _get_white_threshold(self) -> int:
        """Get white pixel threshold, possibly from learner."""
        if self.learner:
            return self.learner.get_threshold('white_pixel_min', CARD_WHITE_THRESHOLD_DEFAULT)
        return CARD_WHITE_THRESHOLD_DEFAULT

    def _load_templates(self) -> Dict:
        """Load card templates from table_dict or MongoDB."""
        templates = {}

        if self.table_dict:
            # Try to load from table_dict (MongoDB format)
            try:
                from sys_core.tools.mongo_manager import MongoManager
                mongo = MongoManager()

                for rank in self.RANKS:
                    for suit in self.SUITS:
                        card_code = f"{rank.lower()}{suit.lower()}"
                        template = mongo.get_card_template(card_code)
                        if template is not None:
                            templates[card_code.upper()] = template

                if templates:
                    log.info(f"Loaded {len(templates)} card templates from MongoDB")
            except Exception as e:
                log.debug(f"Could not load templates from MongoDB: {e}")

        return templates

    def detect_player_cards(self, table_img, table_window=None) -> List[str]:
        """
        Detect the player's two hole cards.

        Args:
            table_img: PIL Image or numpy array of the table
            table_window: Optional TableWindow for position context

        Returns:
            List of card codes like ['AH', 'KS'], or [] if not detected
        """
        # Convert to numpy if needed
        if isinstance(table_img, Image.Image):
            img = cv2.cvtColor(np.array(table_img), cv2.COLOR_RGB2BGR)
        else:
            img = table_img

        h, w = img.shape[:2]

        # Define search region for player cards (bottom center of table)
        y_start = int(h * CARD_REGION_Y_START)
        y_end = int(h * CARD_REGION_Y_END)
        x_start = int(w * CARD_REGION_X_START)
        x_end = int(w * CARD_REGION_X_END)

        search_region = img[y_start:y_end, x_start:x_end]

        # Strategy 1: Try template matching if templates available
        if self.templates:
            cards = self._detect_by_template(search_region, x_start, y_start)
            if len(cards) == 2:
                log.info(f"Template matching found cards: {[c.code for c in cards]}")
                self._log_success('template', cards)
                return [c.code for c in cards]

        # Strategy 2: Try white region detection
        cards = self._detect_by_white_regions(search_region, x_start, y_start)
        if len(cards) >= 2:
            # Take the two leftmost cards (player's hole cards)
            cards.sort(key=lambda c: c.x_px)
            cards = cards[:2]
            log.info(f"White region detection found cards: {[c.code for c in cards]}")
            self._log_success('white_region', cards)
            return [c.code for c in cards]

        # Strategy 3: Self-healing - try multiple thresholds
        if self.learner:
            cards = self._heal_detection(search_region, x_start, y_start)
            if len(cards) >= 2:
                cards.sort(key=lambda c: c.x_px)
                cards = cards[:2]
                log.info(f"Self-healing found cards: {[c.code for c in cards]}")
                return [c.code for c in cards]

        # Check if cards are face-down (red backs)
        if self._are_cards_face_down(search_region):
            log.info("Cards appear to be face-down (not your turn)")
            return []

        log.warning("Could not detect player cards")
        self._log_failure(table_img)
        return []

    def _detect_by_template(self, search_region: np.ndarray,
                            x_offset: int, y_offset: int) -> List[DetectedCard]:
        """Detect cards using template matching."""
        if not self.templates:
            return []

        detected = []
        gray = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)

        for card_code, template in self.templates.items():
            if template is None:
                continue

            # Ensure template is grayscale
            if len(template.shape) == 3:
                template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            else:
                template_gray = template

            # Template matching
            try:
                result = cv2.matchTemplate(gray, template_gray, cv2.TM_SQDIFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

                if min_val < TEMPLATE_MATCH_THRESHOLD:
                    x, y = min_loc
                    h, w = template_gray.shape[:2]

                    # Parse card code
                    rank = card_code[:-1].upper()
                    suit = card_code[-1].upper()

                    detected.append(DetectedCard(
                        rank=rank,
                        suit=suit,
                        x_px=x + x_offset,
                        y_px=y + y_offset,
                        w_px=w,
                        h_px=h,
                        confidence=1 - min_val,
                        method='template'
                    ))
            except Exception as e:
                log.debug(f"Template matching error for {card_code}: {e}")

        # Remove duplicates (same position)
        detected = self._remove_duplicate_detections(detected)

        return detected

    def _detect_by_white_regions(self, search_region: np.ndarray,
                                  x_offset: int, y_offset: int) -> List[DetectedCard]:
        """
        Detect cards by finding white rectangles on green felt.

        Cards are white with colored rank/suit in corner.
        """
        # Create white mask
        gray = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, self._white_threshold, 255, cv2.THRESH_BINARY)

        # Clean up mask
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detected = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < CARD_MIN_AREA or area > CARD_MAX_AREA:
                continue

            x, y, w, h = cv2.boundingRect(cnt)

            # Check aspect ratio (cards are taller than wide)
            if h == 0:
                continue
            aspect = w / h
            if not (CARD_ASPECT_RATIO_MIN < aspect < CARD_ASPECT_RATIO_MAX):
                continue

            # Extract card region and try to identify
            card_region = search_region[y:y+h, x:x+w]
            rank, suit, confidence = self._identify_card(card_region)

            detected.append(DetectedCard(
                rank=rank or '?',
                suit=suit or '?',
                x_px=x + x_offset,
                y_px=y + y_offset,
                w_px=w,
                h_px=h,
                confidence=confidence,
                method='white_region'
            ))

        return detected

    def _identify_card(self, card_region: np.ndarray) -> Tuple[Optional[str], Optional[str], float]:
        """
        Identify the rank and suit of a card from its image.

        Returns:
            (rank, suit, confidence) or (None, None, 0) if can't identify
        """
        h, w = card_region.shape[:2]
        if h < 30 or w < 20:
            return None, None, 0

        # Extract top-left corner where rank/suit is shown
        corner_h = min(50, h // 2)
        corner_w = min(35, w // 2)
        corner = card_region[5:corner_h, 5:corner_w]

        # Try template matching on the corner
        if self.templates:
            best_match = None
            best_score = TEMPLATE_MATCH_THRESHOLD

            for card_code, template in self.templates.items():
                if template is None:
                    continue

                try:
                    # Resize template to match corner size if needed
                    template_h, template_w = template.shape[:2]
                    if template_h > corner_h or template_w > corner_w:
                        scale = min(corner_h / template_h, corner_w / template_w)
                        template = cv2.resize(template, None, fx=scale, fy=scale)

                    corner_gray = cv2.cvtColor(corner, cv2.COLOR_BGR2GRAY) if len(corner.shape) == 3 else corner
                    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if len(template.shape) == 3 else template

                    result = cv2.matchTemplate(corner_gray, template_gray, cv2.TM_SQDIFF_NORMED)
                    min_val, _, _, _ = cv2.minMaxLoc(result)

                    if min_val < best_score:
                        best_score = min_val
                        best_match = card_code
                except:
                    continue

            if best_match:
                rank = best_match[:-1].upper()
                suit = best_match[-1].upper()
                return rank, suit, 1 - best_score

        # Fallback: try to identify suit by color
        suit = self._identify_suit_by_color(corner)

        return None, suit, 0.5 if suit else 0

    def _identify_suit_by_color(self, region: np.ndarray) -> Optional[str]:
        """Identify suit by dominant color in region."""
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        # GGSystem uses STANDARD 2-COLOR DECK (NOT 4-color!)
        # Hearts = Red, Diamonds = Red
        # Spades = Black, Clubs = Black
        # We detect RED vs BLACK first, then use OCR for specific suit

        # Red (Hearts OR Diamonds)
        red_mask1 = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([10, 255, 255]))
        red_mask2 = cv2.inRange(hsv, np.array([170, 100, 100]), np.array([180, 255, 255]))
        red_count = np.sum(red_mask1 > 0) + np.sum(red_mask2 > 0)

        # Black (Spades OR Clubs)
        black_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 100, 50]))
        black_count = np.sum(black_mask > 0)

        if max(red_count, black_count) < 50:  # Not enough colored pixels
            return None

        # Determine color first
        if red_count > black_count * 1.5:
            # Red suit - default to Hearts (H), could also be Diamonds (D)
            # TODO: Add OCR to distinguish H vs D
            return 'H'
        elif black_count > red_count * 1.5:
            # Black suit - default to Spades (S), could also be Clubs (C)
            # TODO: Add OCR to distinguish S vs C
            return 'S'
        else:
            # Unclear - default to Spades (most common)
            return 'S'

    def _heal_detection(self, search_region: np.ndarray,
                        x_offset: int, y_offset: int) -> List[DetectedCard]:
        """
        Try multiple white thresholds to find cards.

        Updates learner with working threshold if found.
        """
        thresholds_to_try = [200, 180, 160, 140, 120, 100]

        for threshold in thresholds_to_try:
            # Create mask with this threshold
            gray = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            card_candidates = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < CARD_MIN_AREA:
                    continue

                x, y, w, h = cv2.boundingRect(cnt)
                if h == 0:
                    continue

                aspect = w / h
                if CARD_ASPECT_RATIO_MIN < aspect < CARD_ASPECT_RATIO_MAX:
                    card_candidates.append((x, y, w, h))

            # If we found 2+ card-like regions, this threshold works!
            if len(card_candidates) >= 2:
                log.info(f"SELF-HEALING: Found cards at threshold {threshold}")

                # Update learner
                if self.learner:
                    self.learner.set_threshold('white_pixel_min', threshold,
                                              f"Auto-healed: found cards at threshold {threshold}")
                    self._white_threshold = threshold

                # Convert to DetectedCard objects
                detected = []
                for x, y, w, h in card_candidates:
                    card_region = search_region[y:y+h, x:x+w]
                    rank, suit, conf = self._identify_card(card_region)

                    detected.append(DetectedCard(
                        rank=rank or '?',
                        suit=suit or '?',
                        x_px=x + x_offset,
                        y_px=y + y_offset,
                        w_px=w,
                        h_px=h,
                        confidence=conf,
                        method='healed'
                    ))

                return detected

        return []

    def _are_cards_face_down(self, search_region: np.ndarray) -> bool:
        """
        Check if cards appear to be face-down (showing card backs).

        GGSystem card backs are red with a pattern.
        """
        hsv = cv2.cvtColor(search_region, cv2.COLOR_BGR2HSV)

        # Red card back detection
        red_mask = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([10, 255, 255]))
        red_count = np.sum(red_mask > 0)

        h, w = search_region.shape[:2]
        total_pixels = h * w

        # If more than 5% of the search region is red, cards might be face-down
        return (red_count / total_pixels) > 0.05

    def _remove_duplicate_detections(self, cards: List[DetectedCard]) -> List[DetectedCard]:
        """Remove cards detected at the same position."""
        if len(cards) <= 1:
            return cards

        unique = []
        for card in cards:
            is_duplicate = False
            for existing in unique:
                # Check if positions overlap
                dx = abs(card.x_px - existing.x_px)
                dy = abs(card.y_px - existing.y_px)
                if dx < 30 and dy < 30:
                    # Keep the one with higher confidence
                    if card.confidence > existing.confidence:
                        unique.remove(existing)
                        unique.append(card)
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique.append(card)

        return unique

    def _log_success(self, method: str, cards: List[DetectedCard]):
        """Log successful detection."""
        if self.learner:
            self.learner.log_action('card_detection', success=True, details={
                'method': method,
                'cards': [c.code for c in cards],
            })

    def _log_failure(self, img):
        """Log failed detection with screenshot."""
        if self.learner:
            self.learner.log_action('card_detection', success=False, details={
                'threshold': self._white_threshold,
            })

    def detect_board_cards(self, table_img) -> List[str]:
        """
        Detect community cards (flop/turn/river) on the board.

        Args:
            table_img: PIL Image or numpy array of the table

        Returns:
            List of card codes like ['AS', 'KH', 'QD', 'JC', '10S']
        """
        if isinstance(table_img, Image.Image):
            img = cv2.cvtColor(np.array(table_img), cv2.COLOR_RGB2BGR)
        else:
            img = table_img

        h, w = img.shape[:2]

        # Board cards are in the center of the table
        y_start = int(h * 0.30)
        y_end = int(h * 0.55)
        x_start = int(w * 0.20)
        x_end = int(w * 0.80)

        search_region = img[y_start:y_end, x_start:x_end]

        # Use white region detection for board cards
        cards = self._detect_by_white_regions(search_region, x_start, y_start)

        # Sort by x position (left to right)
        cards.sort(key=lambda c: c.x_px)

        return [c.code for c in cards[:5]]  # Max 5 board cards


# Singleton instance
_detector: Optional[CardDetector] = None


def get_card_detector(table_dict=None, learner=None) -> CardDetector:
    """Get singleton CardDetector instance."""
    global _detector
    if _detector is None:
        _detector = CardDetector(table_dict, learner)
    return _detector
