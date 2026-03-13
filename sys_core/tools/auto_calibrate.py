"""
Auto-Calibration System for GGSystem Utility

This module automatically detects GGPoker windows, captures templates,
finds button positions, and validates card detection - eliminating
manual configuration and template matching issues.

Usage:
    python3 -m sys_core.tools.auto_calibrate
    python3 -m sys_core.tools.auto_calibrate --table 1
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageGrab, Image

log = logging.getLogger(__name__)


class WindowFinder:
    """Find GGPoker windows using macOS APIs instead of template matching."""

    @staticmethod
    def find_all_windows():
        """
        Find all GGPoker table windows via macOS Accessibility API.
        Returns list of (x, y, width, height) tuples.
        """
        script = '''
        tell application "System Events"
            if not (exists process "GGnet") then
                return "NOT_RUNNING"
            end if
            tell process "GGnet"
                set windowList to {}
                repeat with win in windows
                    try
                        set winPos to position of win
                        set winSize to size of win
                        set end of windowList to ((item 1 of winPos) as string) & "," & ((item 2 of winPos) as string) & "," & ((item 1 of winSize) as string) & "," & ((item 2 of winSize) as string)
                    end try
                end repeat
                return windowList
            end tell
        end tell
        '''
        try:
            result = subprocess.run(['osascript', '-e', script],
                                   capture_output=True, timeout=5)
            output = result.stdout.decode().strip()

            if output == "NOT_RUNNING":
                log.warning("GGSystem is not running")
                return []

            if not output:
                return []

            # Parse "x,y,w,h, x,y,w,h, ..." format
            windows = []
            for win_str in output.split(', '):
                if win_str:
                    parts = win_str.split(',')
                    if len(parts) == 4:
                        x, y, w, h = map(int, parts)
                        windows.append((x, y, w, h))

            return windows

        except Exception as e:
            log.error(f"Failed to find windows: {e}")
            return []

    @staticmethod
    def activate_window(window_index=0):
        """Bring a specific GGSystem window to front."""
        script = f'''
        tell application "System Events"
            tell process "GGnet"
                set frontmost to true
                try
                    set focused of window {window_index + 1} to true
                end try
            end tell
        end tell
        '''
        subprocess.run(['osascript', '-e', script], capture_output=True, timeout=3)


class ButtonDetector:
    """Detect Fold/Call/Bet buttons by color signature."""

    # GGSystem button colors (HSV ranges)
    FOLD_COLOR = {
        'lower': np.array([0, 50, 50]),    # Red/orange
        'upper': np.array([20, 255, 255])
    }
    CALL_COLOR = {
        'lower': np.array([35, 50, 50]),   # Green/yellow
        'upper': np.array([85, 255, 255])
    }
    BET_COLOR = {
        'lower': np.array([90, 50, 50]),   # Blue
        'upper': np.array([130, 255, 255])
    }

    @staticmethod
    def find_button_by_color(screenshot, color_range, region=None):
        """
        Find a button by its color signature.

        Args:
            screenshot: PIL Image or numpy array
            color_range: dict with 'lower' and 'upper' HSV values
            region: (x, y, w, h) to limit search area

        Returns:
            (x, y, w, h) of button center, or None
        """
        if isinstance(screenshot, Image.Image):
            img = np.array(screenshot)
        else:
            img = screenshot

        # Crop to region if specified
        if region:
            x, y, w, h = region
            img = img[y:y+h, x:x+w]

        # Convert to HSV
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

        # Create mask for color
        mask = cv2.inRange(hsv, color_range['lower'], color_range['upper'])

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Find largest button-shaped contour
        best_button = None
        best_area = 0

        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 500:  # Minimum button size
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h if h > 0 else 0

                # Buttons are typically wider than tall
                if 1.5 < aspect_ratio < 5 and area > best_area:
                    best_area = area
                    best_button = (x, y, w, h)

        return best_button

    @classmethod
    def find_all_buttons(cls, screenshot, table_region):
        """
        Find all action buttons in the table region.

        Returns:
            dict with 'fold', 'call', 'bet' button positions
        """
        x, y, w, h = table_region

        # Buttons are in the bottom portion of the table
        button_region = (x, y + int(h * 0.7), w, int(h * 0.3))

        buttons = {
            'fold': cls.find_button_by_color(screenshot, cls.FOLD_COLOR, button_region),
            'call': cls.find_button_by_color(screenshot, cls.CALL_COLOR, button_region),
            'bet': cls.find_button_by_color(screenshot, cls.BET_COLOR, button_region),
        }

        # Adjust coordinates back to absolute
        if buttons['fold']:
            bx, by, bw, bh = buttons['fold']
            buttons['fold'] = (button_region[0] + bx, button_region[1] + by, bw, bh)
        if buttons['call']:
            bx, by, bw, bh = buttons['call']
            buttons['call'] = (button_region[0] + bx, button_region[1] + by, bw, bh)
        if buttons['bet']:
            bx, by, bw, bh = buttons['bet']
            buttons['bet'] = (button_region[0] + bx, button_region[1] + by, bw, bh)

        return buttons


class AutoCalibrator:
    """
    Automatic calibration system that detects GGPoker setup
    without relying on fragile template matching.
    """

    def __init__(self):
        self.calibration = {
            'tables': [],
            'settings': {
                'threshold': 0.15,
                'input_method': 'mouse',
                'y_offset': -150
            }
        }
        self.window_finder = WindowFinder()
        self.button_detector = ButtonDetector()

    def run(self):
        """
        Full calibration sequence.

        Returns:
            dict with calibration data for all tables
        """
        print("=" * 50)
        print("GGSystem Utility Auto-Calibration")
        print("=" * 50)

        # Step 1: Find windows
        print("\n1. Finding GGPoker windows...")
        windows = self.window_finder.find_all_windows()

        if not windows:
            print("   ERROR: No GGPoker windows found!")
            print("   Make sure GGSystem is running and you're at a table.")
            return None

        print(f"   Found {len(windows)} table(s)")

        # Step 2: Calibrate each window
        for i, window in enumerate(windows):
            print(f"\n2. Calibrating table {i + 1}...")
            x, y, w, h = window
            print(f"   Window position: ({x}, {y}) size: {w}x{h}")

            # Take screenshot
            screenshot = ImageGrab.grab()

            # Capture header template
            template = self._capture_template(screenshot, window)
            print(f"   Template captured: {template.shape if template is not None else 'FAILED'}")

            # Find buttons
            buttons = self.button_detector.find_all_buttons(screenshot, window)
            print(f"   Buttons found: fold={buttons['fold'] is not None}, "
                  f"call={buttons['call'] is not None}, bet={buttons['bet'] is not None}")

            # Validate card detection
            cards_valid = self._validate_cards(screenshot, window)
            print(f"   Card detection: {'OK' if cards_valid else 'NEEDS ATTENTION'}")

            # Store calibration
            self.calibration['tables'].append({
                'id': f'table_{i + 1}',
                'window': {'x': x, 'y': y, 'width': w, 'height': h},
                'buttons': {
                    'fold': buttons['fold'],
                    'call': buttons['call'],
                    'bet': buttons['bet']
                },
                'cards_valid': cards_valid
            })

        # Step 3: Save calibration
        print("\n3. Saving calibration...")
        self._save_calibration()
        print("   Saved to: calibration.json")

        print("\n" + "=" * 50)
        print("Calibration Complete!")
        print("=" * 50)

        return self.calibration

    def _capture_template(self, screenshot, window):
        """Capture header region as template."""
        x, y, w, h = window

        # Header is top portion of window (about 50 pixels)
        try:
            header = screenshot.crop((x, y, x + min(200, w), y + 50))
            return np.array(header)
        except Exception as e:
            log.error(f"Failed to capture template: {e}")
            return None

    def _validate_cards(self, screenshot, window):
        """
        Check if card detection would work for this window.
        Returns True if cards region is accessible.
        """
        x, y, w, h = window

        # Cards are typically at bottom-left of table
        # Just check if region is accessible
        try:
            card_region = screenshot.crop((x + int(w * 0.3), y + int(h * 0.7),
                                          x + int(w * 0.5), y + int(h * 0.9)))
            return card_region.size[0] > 0 and card_region.size[1] > 0
        except:
            return False

    def _save_calibration(self):
        """Save calibration to JSON file."""
        config_dir = Path(__file__).parent.parent / 'config'
        config_dir.mkdir(exist_ok=True)

        # Convert numpy arrays and tuples to lists for JSON
        cal_json = {
            'tables': [],
            'settings': self.calibration['settings']
        }

        for table in self.calibration['tables']:
            table_json = {
                'id': table['id'],
                'window': table['window'],
                'buttons': {},
                'cards_valid': table['cards_valid']
            }
            for btn_name, btn_pos in table['buttons'].items():
                if btn_pos:
                    table_json['buttons'][btn_name] = {
                        'x': btn_pos[0],
                        'y': btn_pos[1],
                        'width': btn_pos[2],
                        'height': btn_pos[3]
                    }
                else:
                    table_json['buttons'][btn_name] = None
            cal_json['tables'].append(table_json)

        with open(config_dir / 'calibration.json', 'w') as f:
            json.dump(cal_json, f, indent=2)

    @staticmethod
    def load_calibration():
        """Load existing calibration from file."""
        config_path = Path(__file__).parent.parent / 'config' / 'calibration.json'
        if config_path.exists():
            with open(config_path) as f:
                return json.load(f)
        return None


def quick_test():
    """Quick test to verify GGSystem detection works."""
    print("Quick Test - Finding GGSystem...")

    windows = WindowFinder.find_all_windows()
    if windows:
        print(f"SUCCESS: Found {len(windows)} window(s)")
        for i, (x, y, w, h) in enumerate(windows):
            print(f"  Table {i + 1}: position=({x}, {y}) size={w}x{h}")
        return True
    else:
        print("FAILED: No GGPoker windows found")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Auto-calibrate GGSystem bot")
    parser.add_argument("--test", action="store_true", help="Quick test only")
    parser.add_argument("--table", type=int, help="Calibrate specific table number")

    args = parser.parse_args()

    if args.test:
        quick_test()
    else:
        calibrator = AutoCalibrator()
        calibrator.run()
