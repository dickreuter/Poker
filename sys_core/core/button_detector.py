"""
UNIFIED BUTTON DETECTOR - Single Source of Truth for Finding Action Buttons

Consolidates functionality from:
- tools/button_detector.py (ButtonDetector class)
- tools/auto_calibrate.py (ButtonDetector class - different HSV ranges!)
- tools/smart_ui_automation.py (ColorDetector class)
- tools/dynamic_table_finder.py (find_buttons, find_buttons_ocr, find_buttons_hybrid)
- tools/vision_analyzer.py (analyze_buttons)
- tools/self_healer.py (heal_button_detection)
- tools/ocr_player.py (find_buttons - OCR based)

This is now THE ONLY button detector. All bots should use this.

Detection Strategy (in order of speed):
1. HSV Color Detection - fastest, works 90% of the time
2. OCR Text Detection - slower but more reliable fallback
3. Self-Healing - if both fail, analyze image and update thresholds

Usage:
    from sys_core.core import ButtonDetector

    detector = ButtonDetector()

    # Find buttons in a table image
    buttons = detector.detect(table_image)
    # Returns: {'call': {'x': 100, 'y': 200, 'w': 80, 'h': 30, 'screen_pt': (150, 300)}, ...}

    # Or with screen coordinates pre-calculated
    buttons = detector.detect(table_image, table_window=my_table)
"""

import cv2
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from PIL import Image

from sys_core.core.constants import (
    HSV_RANGES,
    BUTTON_KEYWORDS,
    BUTTON_REGION_Y_START,
    BUTTON_MIN_AREA,
    BUTTON_MAX_AREA,
    BUTTON_MIN_WIDTH,
    BUTTON_MIN_HEIGHT,
    RETINA_SCALE,
)

log = logging.getLogger(__name__)

# Try to import pytesseract for OCR fallback
try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    log.warning("pytesseract not installed - OCR button detection disabled")


@dataclass
class DetectedButton:
    """Represents a detected button with all coordinate systems."""
    button_type: str    # 'call', 'raise', 'fold', 'deal_me_in'
    x_px: int           # X in table image pixels
    y_px: int           # Y in table image pixels
    w_px: int           # Width in pixels
    h_px: int           # Height in pixels
    confidence: float   # Detection confidence (0-1)
    method: str         # 'color', 'ocr', 'healed'
    screen_pt: Optional[Tuple[int, int]] = None  # Screen click point

    @property
    def center_px(self) -> Tuple[int, int]:
        """Center point in table image pixels."""
        return (self.x_px + self.w_px // 2, self.y_px + self.h_px // 2)

    def to_dict(self) -> Dict:
        """Convert to dictionary for compatibility with old code."""
        return {
            'type': self.button_type,
            'x': self.x_px,
            'y': self.y_px,
            'w': self.w_px,
            'h': self.h_px,
            'x_px': self.x_px,
            'y_px': self.y_px,
            'w_px': self.w_px,
            'h_px': self.h_px,
            'center': self.center_px,
            'confidence': self.confidence,
            'method': self.method,
            'screen_pt': self.screen_pt,
        }


class ButtonDetector:
    """
    Unified button detection using multiple strategies.

    Strategy order:
    1. HSV Color Detection (fast)
    2. OCR Text Detection (fallback)
    3. Self-Healing Analysis (last resort)
    """

    def __init__(self, learner=None):
        """
        Initialize the button detector.

        Args:
            learner: Optional UnifiedLearner instance for adaptive thresholds.
        """
        self.learner = learner
        self._hsv_ranges = self._get_hsv_ranges()

    def _get_hsv_ranges(self) -> Dict:
        """Get HSV ranges, possibly adjusted by learner."""
        ranges = {}
        for btn_type, data in HSV_RANGES.items():
            if self.learner:
                # Try to get learned ranges
                lower = self.learner.get_threshold(f'hsv_{btn_type}_lower', data['lower'])
                upper = self.learner.get_threshold(f'hsv_{btn_type}_upper', data['upper'])
            else:
                lower = data['lower']
                upper = data['upper']

            ranges[btn_type] = {
                'lower': np.array(lower) if not isinstance(lower, np.ndarray) else lower,
                'upper': np.array(upper) if not isinstance(upper, np.ndarray) else upper,
                'color_name': data['color_name'],
            }
        return ranges

    def detect(self, table_img, table_window=None, use_ocr_fallback: bool = True) -> Dict[str, Dict]:
        """
        Detect action buttons in a table image.

        Args:
            table_img: PIL Image or numpy array of the table
            table_window: Optional TableWindow for screen coordinate conversion
            use_ocr_fallback: Whether to try OCR if color detection fails

        Returns:
            Dict mapping button type to button info:
            {
                'call': {'x': 100, 'y': 200, 'w': 80, 'h': 30, 'screen_pt': (150, 300)},
                'fold': {...},
                ...
            }
        """
        # Convert to numpy array if PIL Image
        if isinstance(table_img, Image.Image):
            img = cv2.cvtColor(np.array(table_img), cv2.COLOR_RGB2BGR)
        else:
            img = table_img

        # Strategy 1: HSV Color Detection
        buttons = self._detect_by_color(img)

        # Strategy 2: OCR Fallback
        if not buttons and use_ocr_fallback and HAS_TESSERACT:
            log.info("Color detection found no buttons, trying OCR...")
            buttons = self._detect_by_ocr(img)

        # Strategy 3: Self-Healing (if learner available)
        if not buttons and self.learner:
            log.info("OCR found no buttons, trying self-healing...")
            buttons = self._heal_detection(img)

        # Add screen coordinates if table_window provided
        if buttons and table_window:
            for btn_type, btn_data in buttons.items():
                center_x = btn_data['x'] + btn_data['w'] // 2
                center_y = btn_data['y'] + btn_data['h'] // 2
                btn_data['screen_pt'] = table_window.table_px_to_screen_pt(center_x, center_y)

        # Log results
        if buttons:
            log.info(f"Detected buttons: {list(buttons.keys())}")
        else:
            log.warning("No buttons detected")

        return buttons

    def _detect_by_color(self, img: np.ndarray) -> Dict[str, Dict]:
        """
        Detect buttons by HSV color matching.

        This is the primary detection method - fast and works most of the time.
        """
        h, w = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Only search bottom portion of table where buttons are
        y_start = int(h * BUTTON_REGION_Y_START)
        search_region = hsv[y_start:, :]
        search_bgr = img[y_start:, :]

        buttons = {}

        for btn_type, ranges in self._hsv_ranges.items():
            mask = cv2.inRange(search_region, ranges['lower'], ranges['upper'])

            # Clean up mask
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            best_button = None
            best_area = 0

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < BUTTON_MIN_AREA or area > BUTTON_MAX_AREA:
                    continue

                x, y, bw, bh = cv2.boundingRect(cnt)
                if bw < BUTTON_MIN_WIDTH or bh < BUTTON_MIN_HEIGHT:
                    continue

                # Prefer larger buttons (more likely to be real)
                if area > best_area:
                    best_area = area
                    best_button = {
                        'x': x,
                        'y': y + y_start,  # Adjust back to full image coords
                        'w': bw,
                        'h': bh,
                        'area': area,
                        'method': 'color',
                        'confidence': 0.9,
                    }

            if best_button:
                # Map to standard button type
                if btn_type == 'call':
                    buttons['call'] = best_button
                elif btn_type == 'raise':
                    buttons['raise'] = best_button
                elif btn_type == 'fold':
                    buttons['fold'] = best_button
                elif btn_type == 'deal_me_in':
                    buttons['deal_me_in'] = best_button

                log.info(f"Found {btn_type} at ({best_button['x']}, {best_button['y']})")

        return buttons

    def _detect_by_ocr(self, img: np.ndarray) -> Dict[str, Dict]:
        """
        Detect buttons by reading text with OCR.

        Slower but more reliable when colors are off.
        """
        if not HAS_TESSERACT:
            return {}

        h, w = img.shape[:2]

        # Only search bottom portion
        y_start = int(h * BUTTON_REGION_Y_START)
        search_region = img[y_start:, :]

        # Convert to RGB for tesseract
        rgb = cv2.cvtColor(search_region, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        try:
            data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)
        except Exception as e:
            log.error(f"OCR failed: {e}")
            return {}

        buttons = {}

        for i, text in enumerate(data['text']):
            text_lower = text.lower().strip()
            if not text_lower:
                continue

            # Check which button type this text matches
            for btn_type, keywords in BUTTON_KEYWORDS.items():
                if any(kw in text_lower for kw in keywords):
                    x = data['left'][i]
                    y = data['top'][i] + y_start
                    bw = data['width'][i]
                    bh = data['height'][i]
                    conf = data['conf'][i]

                    # Only use high-confidence matches
                    if conf > 50:
                        buttons[btn_type] = {
                            'x': x,
                            'y': y,
                            'w': bw,
                            'h': bh,
                            'text': text,
                            'method': 'ocr',
                            'confidence': conf / 100.0,
                        }
                        log.info(f"OCR found {btn_type}: '{text}' at ({x}, {y})")
                    break

        return buttons

    def _heal_detection(self, img: np.ndarray) -> Dict[str, Dict]:
        """
        Last-resort detection: analyze the image and find any button-like regions.

        Updates learner thresholds if successful.
        """
        if not self.learner:
            return {}

        h, w = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Search bottom portion
        y_start = int(h * BUTTON_REGION_Y_START)
        search_region = hsv[y_start:, :]

        buttons = {}

        # Try to find ANY colored rectangles that could be buttons
        # Use very broad ranges
        broad_ranges = [
            ('green', np.array([20, 30, 30]), np.array([100, 255, 255])),
            ('orange', np.array([0, 50, 50]), np.array([35, 255, 255])),
            ('gray', np.array([0, 0, 20]), np.array([180, 100, 180])),
        ]

        found_colors = {}

        for color_name, lower, upper in broad_ranges:
            mask = cv2.inRange(search_region, lower, upper)
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 1000:
                    continue

                x, y, bw, bh = cv2.boundingRect(cnt)
                if bw < 40 or bh < 20:
                    continue

                # Sample actual color at center
                cx, cy = x + bw // 2, y + bh // 2
                if cy < search_region.shape[0] and cx < search_region.shape[1]:
                    actual_hsv = search_region[cy, cx].tolist()

                    if color_name not in found_colors:
                        found_colors[color_name] = []
                    found_colors[color_name].append({
                        'x': x,
                        'y': y + y_start,
                        'w': bw,
                        'h': bh,
                        'hsv': actual_hsv,
                        'area': area,
                    })

        # Map colors to button types and update thresholds
        color_to_btn = {'green': 'call', 'orange': 'raise', 'gray': 'fold'}

        for color_name, detections in found_colors.items():
            if not detections:
                continue

            # Use largest detection
            best = max(detections, key=lambda d: d['area'])
            btn_type = color_to_btn.get(color_name)

            if btn_type:
                buttons[btn_type] = {
                    'x': best['x'],
                    'y': best['y'],
                    'w': best['w'],
                    'h': best['h'],
                    'method': 'healed',
                    'confidence': 0.7,
                }

                # Update learner with new HSV values
                hsv_val = best['hsv']
                margin = 20
                new_lower = [max(0, hsv_val[0] - margin), max(0, hsv_val[1] - 50), max(0, hsv_val[2] - 50)]
                new_upper = [min(180, hsv_val[0] + margin), min(255, hsv_val[1] + 50), min(255, hsv_val[2] + 50)]

                self.learner.set_threshold(f'hsv_{btn_type}_lower', new_lower,
                                          f"Auto-healed from detected {color_name} button")
                self.learner.set_threshold(f'hsv_{btn_type}_upper', new_upper,
                                          f"Auto-healed from detected {color_name} button")

                log.info(f"HEALED: Found {btn_type} button, updated HSV thresholds")

        return buttons

    def detect_deal_me_in(self, img, table_window=None) -> Optional[Dict]:
        """
        Specifically detect "Deal Me In" or "I'm Back" button.

        These are red buttons that appear when you're sitting out.
        """
        if isinstance(img, Image.Image):
            img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        h, w = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Search bottom portion
        y_start = int(h * BUTTON_REGION_Y_START)
        search_region = hsv[y_start:, :]

        # Red color range for Deal Me In
        red_lower = HSV_RANGES['deal_me_in']['lower']
        red_upper = HSV_RANGES['deal_me_in']['upper']

        mask = cv2.inRange(search_region, red_lower, red_upper)
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < BUTTON_MIN_AREA:
                continue

            x, y, bw, bh = cv2.boundingRect(cnt)
            if bw < BUTTON_MIN_WIDTH or bh < BUTTON_MIN_HEIGHT:
                continue

            result = {
                'x': x,
                'y': y + y_start,
                'w': bw,
                'h': bh,
                'method': 'color',
            }

            if table_window:
                center_x = result['x'] + result['w'] // 2
                center_y = result['y'] + result['h'] // 2
                result['screen_pt'] = table_window.table_px_to_screen_pt(center_x, center_y)

            log.info(f"Found Deal Me In button at ({result['x']}, {result['y']})")
            return result

        return None


# Singleton instance
_detector: Optional[ButtonDetector] = None


def get_button_detector(learner=None) -> ButtonDetector:
    """Get singleton ButtonDetector instance."""
    global _detector
    if _detector is None:
        _detector = ButtonDetector(learner)
    return _detector
