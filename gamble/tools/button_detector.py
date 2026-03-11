"""
Color-based Button Detection for GGPoker

Detects Fold/Call/Bet buttons by their color signature instead of
relying on hardcoded coordinates from table_dict. This eliminates
the need for manual Y offsets and adapts to different table positions.

Usage:
    from gamble.tools.button_detector import ButtonDetector

    detector = ButtonDetector()
    screenshot = ImageGrab.grab()
    table_region = (tlc_x, tlc_y, width, height)

    fold_pos = detector.find_fold_button(screenshot, table_region)
    call_pos = detector.find_call_button(screenshot, table_region)
    bet_pos = detector.find_bet_button(screenshot, table_region)
"""

import logging
import cv2
import numpy as np
from PIL import Image
from typing import Optional, Tuple, Dict, List

log = logging.getLogger(__name__)


class ButtonDetector:
    """
    Detect GGPoker action buttons by their color signatures.

    GGPoker uses consistent colors for buttons:
    - Fold: Red/Orange (#E05555-ish)
    - Call/Check: Green (#55AA55-ish)
    - Bet/Raise: Blue (#5555E0-ish)
    """

    # HSV color ranges for GGPoker buttons
    # (H: 0-180, S: 0-255, V: 0-255 in OpenCV)
    BUTTON_COLORS = {
        'fold': {
            'lower': np.array([0, 80, 80]),      # Red/orange hue
            'upper': np.array([15, 255, 255]),
            'alt_lower': np.array([165, 80, 80]),  # Red wraps around in HSV
            'alt_upper': np.array([180, 255, 255]),
        },
        'call': {
            'lower': np.array([35, 60, 60]),     # Green hue
            'upper': np.array([85, 255, 255]),
        },
        'check': {
            'lower': np.array([35, 60, 60]),     # Same as call (green)
            'upper': np.array([85, 255, 255]),
        },
        'bet': {
            'lower': np.array([90, 60, 60]),     # Blue hue
            'upper': np.array([130, 255, 255]),
        },
        'raise': {
            'lower': np.array([90, 60, 60]),     # Same as bet (blue)
            'upper': np.array([130, 255, 255]),
        },
    }

    # Minimum button dimensions (in pixels)
    MIN_BUTTON_WIDTH = 40
    MIN_BUTTON_HEIGHT = 20
    MIN_BUTTON_AREA = 800

    # Button aspect ratio range (width/height)
    MIN_ASPECT_RATIO = 1.5
    MAX_ASPECT_RATIO = 6.0

    def __init__(self):
        self.last_positions = {}  # Cache last known positions

    def find_button(self, screenshot, table_region: Tuple[int, int, int, int],
                    button_type: str) -> Optional[Tuple[int, int, int, int]]:
        """
        Find a button by color in the table region.

        Args:
            screenshot: PIL Image or numpy array
            table_region: (x, y, width, height) of the table
            button_type: 'fold', 'call', 'check', 'bet', or 'raise'

        Returns:
            (x, y, width, height) of button center, or None if not found
        """
        if button_type not in self.BUTTON_COLORS:
            log.warning(f"Unknown button type: {button_type}")
            return None

        # Convert to numpy array if needed
        if isinstance(screenshot, Image.Image):
            img = np.array(screenshot)
        else:
            img = screenshot

        # Crop to button search area (bottom 35% of table)
        x, y, w, h = table_region
        button_area_top = int(h * 0.65)
        search_region = img[y + button_area_top:y + h, x:x + w]

        if search_region.size == 0:
            log.warning(f"Empty search region for {button_type}")
            return None

        # Convert to HSV
        hsv = cv2.cvtColor(search_region, cv2.COLOR_RGB2HSV)

        # Create color mask
        color_range = self.BUTTON_COLORS[button_type]
        mask = cv2.inRange(hsv, color_range['lower'], color_range['upper'])

        # Handle red color wrapping in HSV (fold button)
        if 'alt_lower' in color_range:
            alt_mask = cv2.inRange(hsv, color_range['alt_lower'], color_range['alt_upper'])
            mask = cv2.bitwise_or(mask, alt_mask)

        # Morphological operations to clean up mask
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Find best button-shaped contour
        best_button = None
        best_score = 0

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.MIN_BUTTON_AREA:
                continue

            bx, by, bw, bh = cv2.boundingRect(contour)

            # Check dimensions
            if bw < self.MIN_BUTTON_WIDTH or bh < self.MIN_BUTTON_HEIGHT:
                continue

            # Check aspect ratio (buttons are wider than tall)
            aspect = bw / bh if bh > 0 else 0
            if aspect < self.MIN_ASPECT_RATIO or aspect > self.MAX_ASPECT_RATIO:
                continue

            # Score by area (larger = better) and rectangularity
            rect_area = bw * bh
            rectangularity = area / rect_area if rect_area > 0 else 0

            score = area * rectangularity

            if score > best_score:
                best_score = score
                # Convert back to absolute coordinates
                best_button = (
                    x + bx,
                    y + button_area_top + by,
                    bw,
                    bh
                )

        if best_button:
            log.debug(f"Found {button_type} button at {best_button}")
            self.last_positions[button_type] = best_button
        else:
            log.debug(f"Could not find {button_type} button by color")

        return best_button

    def find_fold_button(self, screenshot, table_region: Tuple[int, int, int, int]) -> Optional[Tuple[int, int, int, int]]:
        """Find the Fold button (red/orange)."""
        return self.find_button(screenshot, table_region, 'fold')

    def find_call_button(self, screenshot, table_region: Tuple[int, int, int, int]) -> Optional[Tuple[int, int, int, int]]:
        """Find the Call button (green)."""
        return self.find_button(screenshot, table_region, 'call')

    def find_check_button(self, screenshot, table_region: Tuple[int, int, int, int]) -> Optional[Tuple[int, int, int, int]]:
        """Find the Check button (green, same as call)."""
        return self.find_button(screenshot, table_region, 'check')

    def find_bet_button(self, screenshot, table_region: Tuple[int, int, int, int]) -> Optional[Tuple[int, int, int, int]]:
        """Find the Bet button (blue)."""
        return self.find_button(screenshot, table_region, 'bet')

    def find_raise_button(self, screenshot, table_region: Tuple[int, int, int, int]) -> Optional[Tuple[int, int, int, int]]:
        """Find the Raise button (blue, same as bet)."""
        return self.find_button(screenshot, table_region, 'raise')

    def find_all_buttons(self, screenshot, table_region: Tuple[int, int, int, int]) -> Dict[str, Optional[Tuple[int, int, int, int]]]:
        """
        Find all action buttons in one pass.

        Returns:
            dict with 'fold', 'call', 'bet' keys and position values
        """
        return {
            'fold': self.find_fold_button(screenshot, table_region),
            'call': self.find_call_button(screenshot, table_region),
            'bet': self.find_bet_button(screenshot, table_region),
        }

    def get_button_center(self, button_rect: Tuple[int, int, int, int]) -> Tuple[int, int]:
        """Get center coordinates of a button rectangle."""
        x, y, w, h = button_rect
        return (x + w // 2, y + h // 2)

    def get_click_position(self, button_type: str, screenshot, table_region: Tuple[int, int, int, int],
                           fallback_coords: Optional[Dict] = None) -> Optional[Tuple[int, int]]:
        """
        Get the click position for a button, with fallback to cached or table_dict coords.

        Args:
            button_type: 'fold', 'call', 'check', 'bet', 'raise'
            screenshot: Current screenshot
            table_region: Table bounding box
            fallback_coords: Optional dict with 'x1', 'y1' from table_dict

        Returns:
            (x, y) click position, or None if not found
        """
        # Try color detection first
        button = self.find_button(screenshot, table_region, button_type)

        if button:
            return self.get_button_center(button)

        # Try cached position
        if button_type in self.last_positions:
            log.debug(f"Using cached position for {button_type}")
            return self.get_button_center(self.last_positions[button_type])

        # Fall back to table_dict coordinates
        if fallback_coords:
            log.debug(f"Using fallback coords for {button_type}")
            tlc_x, tlc_y = table_region[0], table_region[1]
            return (
                fallback_coords.get('x1', 0) + tlc_x,
                fallback_coords.get('y1', 0) + tlc_y
            )

        log.warning(f"Could not find {button_type} button position")
        return None


class SmartMouseAction:
    """
    Enhanced mouse action that uses color detection with fallback.

    Replaces the hardcoded offset approach in mouse_mover.py with
    intelligent button detection.
    """

    def __init__(self, table_dict: Dict):
        self.table_dict = table_dict
        self.detector = ButtonDetector()

    def get_action_position(self, decision: str, screenshot, tlc: Tuple[int, int]) -> Optional[Tuple[int, int, int, int]]:
        """
        Get position to click for a given decision.

        Args:
            decision: Action like 'Fold', 'Call', 'Bet', etc.
            screenshot: Current screenshot (in PIXELS)
            tlc: Top-left corner of table (x, y) in POINTS

        Returns:
            (x1, y1, x2, y2) click area in PIXELS, or None if not found

        NOTE: All return values are in PIXELS for Retina displays.
        FastClicker.click_center() will convert to POINTS by dividing by RETINA_SCALE.
        """
        from gamble.tools import constants as const

        # Map decisions to button types
        DECISION_MAP = {
            'Fold': 'fold',
            'Call': 'call',
            'Call2': 'call',
            'Check': 'check',
            'Bet': 'bet',
            'BetPlus': 'bet',
            'Bet Bluff': 'bet',
            'Bet half pot': 'bet',
            'Bet pot': 'bet',
            'Bet max': 'bet',
        }

        button_type = DECISION_MAP.get(decision)
        if not button_type:
            log.warning(f"Unknown decision type: {decision}")
            return None

        # CRITICAL: Convert tlc from POINTS to PIXELS for Retina display
        # The screenshot is in PIXELS, so we need PIXEL coordinates for searching
        tlc_px = (int(tlc[0] * const.RETINA_SCALE), int(tlc[1] * const.RETINA_SCALE))

        # Table region for search (all in PIXELS now)
        table_region = (tlc_px[0], tlc_px[1], const.CROP_WIDTH, const.CROP_HEIGHT)

        # Try to find button by color
        button = self.detector.find_button(screenshot, table_region, button_type)

        if button:
            # Button coordinates are already in PIXELS (relative to screenshot)
            x, y, w, h = button
            return (x, y, x + w, y + h)

        # Fallback to table_dict coordinates
        # table_dict coordinates are in POINTS relative to table top-left
        # We need to convert them to absolute PIXELS
        coord_key = f'mouse_{decision.lower().replace(" ", "_")}'
        if decision == 'Call2':
            coord_key = 'mouse_call2'
        elif decision in ['Bet', 'BetPlus', 'Bet Bluff']:
            coord_key = 'mouse_raise'
        elif decision == 'Bet half pot':
            coord_key = 'mouse_half_pot'
        elif decision == 'Bet pot':
            coord_key = 'mouse_full_pot'
        elif decision == 'Bet max':
            coord_key = 'mouse_all_in'

        if coord_key in self.table_dict:
            coo = self.table_dict[coord_key]
            # table_dict coords are in POINTS, convert to PIXELS
            # Add table position (already in PIXELS) and scale coordinates
            return (
                int((coo['x1'] + tlc[0]) * const.RETINA_SCALE),
                int((coo['y1'] + tlc[1]) * const.RETINA_SCALE),
                int((coo['x2'] + tlc[0]) * const.RETINA_SCALE),
                int((coo['y2'] + tlc[1]) * const.RETINA_SCALE)
            )

        log.warning(f"Could not find position for {decision}")
        return None


def debug_button_colors(screenshot, table_region: Tuple[int, int, int, int], save_path: str = '/tmp/poker_debug'):
    """
    Debug utility to visualize button color detection.
    Saves images showing the color masks for each button type.
    """
    import os
    os.makedirs(save_path, exist_ok=True)

    if isinstance(screenshot, Image.Image):
        img = np.array(screenshot)
    else:
        img = screenshot

    x, y, w, h = table_region
    button_area_top = int(h * 0.65)
    search_region = img[y + button_area_top:y + h, x:x + w]

    # Save search region
    Image.fromarray(search_region).save(f'{save_path}/button_search_region.png')

    hsv = cv2.cvtColor(search_region, cv2.COLOR_RGB2HSV)

    detector = ButtonDetector()

    for button_type, color_range in detector.BUTTON_COLORS.items():
        mask = cv2.inRange(hsv, color_range['lower'], color_range['upper'])
        if 'alt_lower' in color_range:
            alt_mask = cv2.inRange(hsv, color_range['alt_lower'], color_range['alt_upper'])
            mask = cv2.bitwise_or(mask, alt_mask)

        # Apply to original image
        masked = cv2.bitwise_and(search_region, search_region, mask=mask)
        Image.fromarray(masked).save(f'{save_path}/button_mask_{button_type}.png')
        Image.fromarray(mask).save(f'{save_path}/button_mask_{button_type}_bw.png')

    log.info(f"Debug images saved to {save_path}/")


if __name__ == "__main__":
    # Test button detection
    from PIL import ImageGrab
    from gamble.tools import constants as const

    print("Taking screenshot...")
    screenshot = ImageGrab.grab()

    # Assuming table is at default position
    table_region = (14, 850, const.CROP_WIDTH, const.CROP_HEIGHT)

    print("Detecting buttons...")
    detector = ButtonDetector()
    buttons = detector.find_all_buttons(screenshot, table_region)

    for btn_type, pos in buttons.items():
        if pos:
            print(f"  {btn_type}: {pos}")
        else:
            print(f"  {btn_type}: NOT FOUND")

    print("\nSaving debug images...")
    debug_button_colors(screenshot, table_region)
    print("Done! Check /tmp/poker_debug/")
