"""
Dynamic Table Finder - Finds GGPoker tables and UI elements regardless of screen position.

This module replaces hardcoded template coordinates with dynamic detection using:
1. macOS AppleScript for window position detection
2. OCR-based button detection (PRIMARY - most reliable)
3. Color-based button detection (FALLBACK - HSV color matching)
4. Brightness-based card detection

Usage:
    from sys_core.tools.dynamic_table_finder import DynamicTableFinder

    finder = DynamicTableFinder()
    tables = finder.find_all_tables()

    for table in tables:
        buttons = finder.find_buttons(table)  # Uses OCR + color fallback
        cards = finder.find_cards(table)
"""

import subprocess
import logging
from PIL import ImageGrab, Image
import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logging.warning("pytesseract not installed - OCR button detection disabled")

# Import adaptive learner for self-improvement
from sys_core.tools.adaptive_learner import log_action, report_issue, get_threshold

# Use UNIFIED constants - single source of truth
from sys_core.core.constants import HSV_RANGES, RETINA_SCALE

log = logging.getLogger(__name__)

# Button color ranges - USE UNIFIED CONSTANTS from core/constants.py
# GGSystem buttons:
#   - Fold: Dark gray/charcoal (low saturation, medium value)
#   - Call/Check: Green
#   - Raise/Bet: Orange/gold
BUTTON_COLORS = {
    'fold': {
        'lower': HSV_RANGES['fold']['lower'],
        'upper': HSV_RANGES['fold']['upper'],
        'name': 'Fold'
    },
    'call': {
        'lower': HSV_RANGES['call']['lower'],
        'upper': HSV_RANGES['call']['upper'],
        'name': 'Call'
    },
    'raise': {
        'lower': HSV_RANGES['raise']['lower'],
        'upper': HSV_RANGES['raise']['upper'],
        'name': 'Raise'
    },
}


class TableWindow:
    """Represents a detected GGPoker table window."""

    def __init__(self, name: str, x_pt: int, y_pt: int, w_pt: int, h_pt: int):
        self.name = name
        # Position in macOS POINTS
        self.x_pt = x_pt
        self.y_pt = y_pt
        self.w_pt = w_pt
        self.h_pt = h_pt
        # Position in PIXELS (for screenshot operations)
        self.x_px = x_pt * RETINA_SCALE
        self.y_px = y_pt * RETINA_SCALE
        self.w_px = w_pt * RETINA_SCALE
        self.h_px = h_pt * RETINA_SCALE
        # Cached screenshot of this table
        self._screenshot: Optional[Image.Image] = None

    def __repr__(self):
        return f"TableWindow('{self.name}', pos=({self.x_pt},{self.y_pt}), size={self.w_pt}x{self.h_pt})"

    def is_poker_table(self) -> bool:
        """Check if this is a poker table (not lobby)."""
        # Active poker tables have "Blinds X | Y" in the name
        # e.g., "Spin & Gold $0.25 - Blinds 15 | 30"
        # Prize displays have "Highlight" but NO blinds info
        # e.g., "Highlight for $0.25 x40,000 Table!" - NOT a table!

        # If it has "Blinds", it's definitely an active table
        if 'Blinds' in self.name:
            return True

        # "Highlight" without "Blinds" is just a prize popup, not a table
        if 'Highlight' in self.name:
            return False

        # Other keywords that indicate poker tables
        keywords = ['Spin', 'Gold', 'Rush', 'Cash', 'Hold', 'Omaha', 'NL', 'PLO', 'Jackpot']
        return any(kw in self.name for kw in keywords)

    def capture(self, full_screenshot: Optional[Image.Image] = None) -> Image.Image:
        """Capture this table window from screen."""
        if full_screenshot is None:
            full_screenshot = ImageGrab.grab()

        self._screenshot = full_screenshot.crop((
            self.x_px, self.y_px,
            self.x_px + self.w_px,
            self.y_px + self.h_px
        ))
        return self._screenshot

    def table_px_to_screen_pt(self, x_px: int, y_px: int) -> Tuple[int, int]:
        """Convert table pixel coordinates to screen point coordinates for clicking."""
        screen_x_pt = self.x_pt + x_px // RETINA_SCALE
        screen_y_pt = self.y_pt + y_px // RETINA_SCALE
        return (screen_x_pt, screen_y_pt)


class DynamicTableFinder:
    """Finds GGPoker tables and UI elements dynamically."""

    def __init__(self):
        self._last_screenshot: Optional[Image.Image] = None

    def find_all_tables(self) -> List[TableWindow]:
        """Find all GGPoker windows using macOS AppleScript."""
        script = '''
        tell application "System Events"
            if not (exists process "GGnet") then
                return ""
            end if
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
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=5
            )

            windows = []
            if result.stdout.strip():
                entries = result.stdout.strip().rstrip(';').split(';')
                for entry in entries:
                    if '###' in entry:
                        name, coords_str = entry.split('###')
                        # Fix Unicode minus sign (−) that macOS returns instead of ASCII minus (-)
                        coords_str = coords_str.replace('−', '-').replace('–', '-')
                        coords = coords_str.split(',')
                        x, y, w, h = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
                        windows.append(TableWindow(name.strip(), x, y, w, h))

            log.info(f"Found {len(windows)} GGSystem window(s)")
            return windows

        except subprocess.TimeoutExpired:
            log.error("Timeout finding GGPoker windows")
            return []
        except Exception as e:
            log.error(f"Error finding GGPoker windows: {e}")
            return []

    def find_poker_tables(self) -> List[TableWindow]:
        """Find only poker table windows (exclude lobby)."""
        return [t for t in self.find_all_tables() if t.is_poker_table()]

    def capture_screenshot(self) -> Image.Image:
        """Take a full screenshot and cache it."""
        self._last_screenshot = ImageGrab.grab()
        return self._last_screenshot

    def find_buttons(self, table: TableWindow, screenshot: Optional[Image.Image] = None) -> Dict[str, Dict]:
        """
        Find action buttons by color detection - FULLY DYNAMIC.

        Searches entire bottom half of table, finds all colored contours,
        then uses smart filtering to identify buttons vs slider:
        - Buttons are grouped together horizontally (within ~200px of each other)
        - Slider is isolated and has very wide aspect ratio (>4)
        - Buttons have aspect ratio 1.5-4

        Returns dict with button positions in both table pixels and screen points.
        """
        if screenshot is None:
            screenshot = self._last_screenshot or self.capture_screenshot()

        table_img = table.capture(screenshot)
        img = cv2.cvtColor(np.array(table_img), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h_img, w_img = img.shape[:2]

        # Search ENTIRE bottom half - no hardcoded percentages
        y_start = h_img // 2
        hsv_bottom = hsv[y_start:, :]

        # Collect ALL candidate buttons from color detection
        all_candidates = []

        for btn_key, color_info in BUTTON_COLORS.items():
            mask = cv2.inRange(hsv_bottom, color_info['lower'], color_info['upper'])
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                area = cv2.contourArea(contour)
                if area < 1500:  # Too small
                    continue

                x, y, w, bh = cv2.boundingRect(contour)

                # Basic size filter
                if w < 50 or bh < 20 or w > 400 or bh > 120:
                    continue

                aspect_ratio = w / bh if bh > 0 else 0

                # Slider has very wide aspect ratio (>4), buttons are typically 1.5-4
                if aspect_ratio > 4.5:
                    log.debug(f"Skipping slider-like contour: aspect={aspect_ratio:.1f}, area={area}")
                    continue

                center_x = x + w // 2
                center_y = y_start + y + bh // 2

                all_candidates.append({
                    'btn_key': btn_key,
                    'x': x,
                    'y': y_start + y,
                    'w': w,
                    'h': bh,
                    'center_x': center_x,
                    'center_y': center_y,
                    'area': area,
                    'aspect': aspect_ratio,
                    'color': color_info['name']
                })

        if not all_candidates:
            log.debug("No button candidates found")
            return {}

        # Group candidates by Y position (buttons should be aligned horizontally)
        # Find the most common Y band (within 50px tolerance)
        y_positions = [c['center_y'] for c in all_candidates]

        # Find cluster of buttons (at least 2 near each other in Y)
        best_y_band = None
        best_count = 0
        for y in y_positions:
            count = sum(1 for y2 in y_positions if abs(y2 - y) < 50)
            if count > best_count:
                best_count = count
                best_y_band = y

        # Filter to only buttons in the main Y band
        if best_y_band and best_count >= 2:
            button_candidates = [c for c in all_candidates if abs(c['center_y'] - best_y_band) < 50]
        else:
            # Fallback: use candidates in bottom 30% of table (most likely button area)
            bottom_threshold = h_img * 0.70
            button_candidates = [c for c in all_candidates if c['center_y'] > bottom_threshold]

        if not button_candidates:
            button_candidates = all_candidates  # Use all if filtering removed everything

        # Build result - pick best candidate per button type
        buttons = {}
        for btn_key in ['call', 'raise', 'fold']:
            type_candidates = [c for c in button_candidates if c['btn_key'] == btn_key]
            if type_candidates:
                # Pick largest area
                best = max(type_candidates, key=lambda c: c['area'])
                screen_pt = table.table_px_to_screen_pt(best['center_x'], best['center_y'])
                buttons[btn_key] = {
                    'x_px': best['center_x'],
                    'y_px': best['center_y'],
                    'screen_pt': screen_pt,
                    'w': best['w'],
                    'h': best['h'],
                    'name': best['color'],
                    'area': best['area']
                }
                log.info(f"Found {btn_key} at ({best['center_x']}, {best['center_y']}) -> screen {screen_pt}")

        # If no Call found but we have green candidates, try harder
        if 'call' not in buttons:
            green_candidates = [c for c in all_candidates if c['btn_key'] == 'call']
            if green_candidates:
                # Pick the one lowest on screen (most likely the action button, not UI element)
                best = max(green_candidates, key=lambda c: c['center_y'])
                screen_pt = table.table_px_to_screen_pt(best['center_x'], best['center_y'])
                buttons['call'] = {
                    'x_px': best['center_x'],
                    'y_px': best['center_y'],
                    'screen_pt': screen_pt,
                    'w': best['w'],
                    'h': best['h'],
                    'name': 'Call',
                    'area': best['area']
                }
                log.info(f"Found call (fallback) at ({best['center_x']}, {best['center_y']})")

        # Log button detection to adaptive learner
        log_action('button_detection_color', success=len(buttons) > 0, details={
            'buttons_found': list(buttons.keys()),
            'table_name': table.name[:30] if table.name else 'unknown',
            'method': 'color'
        })

        return buttons

    def find_buttons_ocr(self, table: TableWindow, screenshot: Optional[Image.Image] = None) -> Dict[str, Dict]:
        """
        Find action buttons using OCR (text recognition).

        This is MORE RELIABLE than color detection because it finds buttons by their text
        (Check, Fold, Call, Raise, Bet) regardless of color, size, or position.

        Returns dict with button positions in both table pixels and screen points.
        """
        if not OCR_AVAILABLE:
            log.debug("OCR not available - pytesseract not installed")
            return {}

        if screenshot is None:
            screenshot = self._last_screenshot or self.capture_screenshot()

        table_img = table.capture(screenshot)

        # OCR on the table image
        try:
            data = pytesseract.image_to_data(table_img, output_type=pytesseract.Output.DICT)
        except Exception as e:
            log.warning(f"OCR failed: {e}")
            return {}

        buttons = {}
        button_keywords = {
            'check': ['check'],
            'call': ['call'],
            'fold': ['fold'],
            'raise': ['raise', 'bet'],
            'allin': ['all-in', 'allin', 'all']
        }

        for i, text in enumerate(data['text']):
            text_str = str(text).strip().lower()
            if not text_str or len(text_str) < 3:
                continue

            conf = data['conf'][i]
            if conf < 50:  # Skip low confidence
                continue

            # Check if this text matches any button keyword
            for btn_key, keywords in button_keywords.items():
                if btn_key in buttons:  # Already found this button
                    continue

                for keyword in keywords:
                    if keyword == text_str or (len(keyword) > 3 and keyword in text_str):
                        x = data['left'][i]
                        y = data['top'][i]
                        w = data['width'][i]
                        h = data['height'][i]

                        # Center of the text
                        center_x = x + w // 2
                        center_y = y + h // 2

                        # Convert to screen points
                        screen_pt = table.table_px_to_screen_pt(center_x, center_y)

                        buttons[btn_key] = {
                            'x_px': center_x,
                            'y_px': center_y,
                            'screen_pt': screen_pt,
                            'w': w,
                            'h': h,
                            'name': text_str.capitalize(),
                            'confidence': conf,
                            'source': 'ocr'
                        }
                        log.info(f"OCR found {btn_key} '{text_str}' at ({center_x}, {center_y}) -> screen {screen_pt}")
                        break

        # Log OCR button detection to adaptive learner
        log_action('button_detection_ocr', success=len(buttons) > 0, details={
            'buttons_found': list(buttons.keys()),
            'table_name': table.name[:30] if table.name else 'unknown',
            'method': 'ocr'
        })

        return buttons

    def find_buttons_hybrid(self, table: TableWindow, screenshot: Optional[Image.Image] = None) -> Dict[str, Dict]:
        """
        Find buttons using HYBRID approach: OCR first, then color detection fallback.

        This combines the reliability of OCR with the speed of color detection.
        """
        if screenshot is None:
            screenshot = self._last_screenshot or self.capture_screenshot()

        # Try OCR first (more reliable)
        buttons = self.find_buttons_ocr(table, screenshot)

        if buttons:
            log.info(f"OCR found {len(buttons)} button(s): {list(buttons.keys())}")

            # If OCR found some buttons but missing others, supplement with color
            if len(buttons) < 2:
                color_buttons = self.find_buttons(table, screenshot)
                for key, val in color_buttons.items():
                    if key not in buttons:
                        val['source'] = 'color'
                        buttons[key] = val
                        log.info(f"Color detection added {key}")
        else:
            # OCR found nothing - fall back entirely to color
            log.debug("OCR found no buttons - falling back to color detection")
            buttons = self.find_buttons(table, screenshot)
            for key in buttons:
                buttons[key]['source'] = 'color'

        # Log hybrid button detection to adaptive learner
        sources = set(b.get('source', 'unknown') for b in buttons.values())
        log_action('button_detection_hybrid', success=len(buttons) > 0, details={
            'buttons_found': list(buttons.keys()),
            'table_name': table.name[:30] if table.name else 'unknown',
            'sources_used': list(sources)
        })

        return buttons

    def find_cards_region(self, table: TableWindow, screenshot: Optional[Image.Image] = None) -> Optional[Dict]:
        """
        Find the player's hole cards region by detecting white card faces.

        Returns:
            Dict with 'x', 'y', 'w', 'h' in table pixels, or None if not found.
        """
        if screenshot is None:
            screenshot = self._last_screenshot or self.capture_screenshot()

        table_img = table.capture(screenshot)
        img = cv2.cvtColor(np.array(table_img), cv2.COLOR_RGB2BGR)
        h, w = img.shape[:2]

        # Cards are in bottom-center area (roughly y: 60-88%, x: 35-65%)
        y1, y2 = int(h * 0.60), int(h * 0.88)
        x1, x2 = int(w * 0.35), int(w * 0.65)

        region = img[y1:y2, x1:x2]
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

        # Find bright pixels (card faces are white/light colored)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            # Find bounding box of all card-like contours
            all_points = []
            for contour in contours:
                if cv2.contourArea(contour) > 500:  # Filter noise
                    all_points.append(contour)

            if all_points:
                merged = np.vstack(all_points)
                x, y, cw, ch = cv2.boundingRect(merged)

                # Log card region detection to adaptive learner
                log_action('card_region_detection', success=True, details={
                    'region': {'x': x1 + x, 'y': y1 + y, 'w': cw, 'h': ch},
                    'table_name': table.name[:30] if table.name else 'unknown'
                })

                return {
                    'x': x1 + x,
                    'y': y1 + y,
                    'w': cw,
                    'h': ch
                }

        # Log failure to adaptive learner
        log_action('card_region_detection', success=False, details={
            'table_name': table.name[:30] if table.name else 'unknown',
            'reason': 'no_white_regions' if not contours else 'no_card_sized_regions'
        })

        return None

    def extract_card_corners(self, table: TableWindow, screenshot: Optional[Image.Image] = None) -> Tuple[Optional[Image.Image], Optional[Image.Image]]:
        """
        Extract the top-left corners of both hole cards for recognition.

        Returns:
            Tuple of (left_card_corner, right_card_corner) as PIL Images, or (None, None).
        """
        cards_region = self.find_cards_region(table, screenshot)
        if not cards_region:
            return None, None

        if screenshot is None:
            screenshot = self._last_screenshot or self.capture_screenshot()

        table_img = table.capture(screenshot)

        # The cards region contains both overlapping cards
        # Left card corner is roughly in the left 40% of the region
        # Right card corner is roughly in the middle-right area

        x, y, w, h = cards_region['x'], cards_region['y'], cards_region['w'], cards_region['h']

        # Extract card corners (top-left area of each card where rank+suit are shown)
        corner_w = min(70, w // 3)
        corner_h = min(90, h // 2)

        # Left card corner
        left_corner = table_img.crop((x, y, x + corner_w, y + corner_h))

        # Right card corner (offset to the right)
        right_x = x + w // 2 - corner_w // 2
        right_corner = table_img.crop((right_x, y, right_x + corner_w, y + corner_h))

        return left_corner, right_corner

    def focus_table(self, table: TableWindow) -> bool:
        """Bring the table window to front."""
        script = f'''
        tell application "System Events"
            tell process "GGnet"
                set frontmost to true
                repeat with w in windows
                    if name of w contains "{table.name[:20]}" then
                        perform action "AXRaise" of w
                        return true
                    end if
                end repeat
            end tell
        end tell
        return false
        '''
        try:
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=3)
            return 'true' in result.stdout.lower()
        except:
            return False


def click_button(button_info: Dict, table: TableWindow = None):
    """
    Click a button found by find_buttons().

    Args:
        button_info: Dict from find_buttons() containing 'screen_pt'
        table: Optional TableWindow to focus first
    """
    from pynput.mouse import Button, Controller
    import time

    mouse = Controller()

    if table:
        # Focus the table window first
        script = '''
        tell application "System Events"
            tell process "GGnet" to set frontmost to true
        end tell
        '''
        subprocess.run(['osascript', '-e', script], capture_output=True)
        time.sleep(0.1)

    x, y = button_info['screen_pt']
    mouse.position = (x, y)
    time.sleep(0.05)
    mouse.click(Button.left)
    log.info(f"Clicked {button_info.get('name', 'button')} at ({x}, {y})")


# Convenience functions
def find_and_click_fold():
    """Quick function to find and click the Fold button on any visible table."""
    finder = DynamicTableFinder()
    tables = finder.find_poker_tables()

    if not tables:
        log.warning("No poker tables found")
        return False

    screenshot = finder.capture_screenshot()

    for table in tables:
        buttons = finder.find_buttons(table, screenshot)
        if 'fold' in buttons:
            click_button(buttons['fold'], table)
            return True

    log.warning("No Fold button found on any table")
    return False


if __name__ == '__main__':
    # Test the dynamic finder
    logging.basicConfig(level=logging.DEBUG)

    finder = DynamicTableFinder()
    tables = finder.find_all_tables()

    print(f"\nFound {len(tables)} window(s):")
    for t in tables:
        print(f"  {t}")

    print("\nSystem tables only:")
    for t in finder.find_poker_tables():
        print(f"  {t}")

        screenshot = finder.capture_screenshot()
        buttons = finder.find_buttons(t, screenshot)
        print(f"    Buttons: {list(buttons.keys())}")

        cards = finder.find_cards_region(t, screenshot)
        print(f"    Cards: {cards}")
