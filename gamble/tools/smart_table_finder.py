"""
Smart Table Finder - Detect GGPoker tables without relying on templates

This module finds poker tables by detecting:
1. Green felt color (the table surface)
2. Card positions (hole cards at bottom center)
3. Button colors (Fold=gray, Call=green, Bet/Raise=orange)

This is more robust than template matching because it adapts to:
- Different GGPoker UI versions
- Tables embedded in lobby windows
- Multiple tables on screen
"""

import logging
import cv2
import numpy as np
from PIL import Image, ImageGrab
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

# Use UNIFIED constants - single source of truth
from gamble.core.constants import HSV_RANGES

log = logging.getLogger(__name__)


@dataclass
class DetectedTable:
    """A detected poker table on screen."""
    x: int
    y: int
    width: int
    height: int
    confidence: float
    has_cards: bool = False
    has_buttons: bool = False
    card_position: Optional[Tuple[int, int]] = None
    button_positions: Optional[Dict[str, Tuple[int, int]]] = None


class SmartTableFinder:
    """
    Find GGPoker tables by visual features instead of template matching.
    """

    # Green felt HSV color range (wider to catch table)
    FELT_COLOR_LOWER = np.array([30, 30, 30])
    FELT_COLOR_UPPER = np.array([90, 255, 220])

    # Minimum table size (in pixels at 2x Retina)
    MIN_TABLE_WIDTH = 800
    MIN_TABLE_HEIGHT = 400
    MIN_TABLE_AREA = 400000  # ~700k is typical table size

    # Button colors - USE UNIFIED CONSTANTS
    # Previously had wrong FOLD_COLOR as RED - GGPoker fold is GRAY
    FOLD_COLOR = {'lower': HSV_RANGES['fold']['lower'], 'upper': HSV_RANGES['fold']['upper']}
    CALL_COLOR = {'lower': HSV_RANGES['call']['lower'], 'upper': HSV_RANGES['call']['upper']}
    BET_COLOR = {'lower': HSV_RANGES['raise']['lower'], 'upper': HSV_RANGES['raise']['upper']}

    def __init__(self):
        self.last_tables = []

    def find_tables(self, screenshot: Image.Image = None) -> List[DetectedTable]:
        """
        Find all poker tables on screen.

        Args:
            screenshot: PIL Image, or None to capture fresh

        Returns:
            List of DetectedTable objects
        """
        if screenshot is None:
            screenshot = ImageGrab.grab()

        img = np.array(screenshot)
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

        # Find green felt areas
        mask = cv2.inRange(hsv, self.FELT_COLOR_LOWER, self.FELT_COLOR_UPPER)

        # Clean up mask
        kernel = np.ones((10, 10), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        tables = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < self.MIN_TABLE_AREA:
                continue

            x, y, w, h = cv2.boundingRect(contour)

            if w < self.MIN_TABLE_WIDTH or h < self.MIN_TABLE_HEIGHT:
                continue

            # Check aspect ratio (tables are oval, wider than tall)
            aspect = w / h if h > 0 else 0
            if aspect < 1.2 or aspect > 2.5:
                continue

            # Check fill ratio (oval fills ~80% of bounding rect)
            rect_area = w * h
            fill_ratio = area / rect_area if rect_area > 0 else 0
            if fill_ratio < 0.5:
                continue

            # Calculate confidence based on area fill
            rect_area = w * h
            fill_ratio = area / rect_area if rect_area > 0 else 0
            confidence = min(fill_ratio * 1.5, 1.0)  # Oval should fill ~70% of rect

            # Expand bounds to include header above and buttons below
            table_x = max(0, x - 20)
            table_y = max(0, y - 80)  # Header above felt
            table_w = min(w + 40, screenshot.width - table_x)
            table_h = min(h + 150, screenshot.height - table_y)  # Buttons below

            table = DetectedTable(
                x=table_x,
                y=table_y,
                width=table_w,
                height=table_h,
                confidence=confidence
            )

            # Check for cards and buttons
            table.has_cards = self._has_hole_cards(img, table)
            table.has_buttons = self._has_action_buttons(hsv, table)

            if table.has_cards:
                table.card_position = self._find_card_position(img, table)

            if table.has_buttons:
                table.button_positions = self._find_button_positions(hsv, table)

            tables.append(table)
            log.info(f"Found table at ({table.x}, {table.y}) {table.width}x{table.height} "
                    f"conf={table.confidence:.2f} cards={table.has_cards} buttons={table.has_buttons}")

        # Sort by confidence
        tables.sort(key=lambda t: t.confidence, reverse=True)
        self.last_tables = tables

        return tables

    def _has_hole_cards(self, img: np.ndarray, table: DetectedTable) -> bool:
        """Check if player's hole cards are visible."""
        # Cards are at bottom center of table
        card_region_x = table.x + table.width // 3
        card_region_y = table.y + int(table.height * 0.65)
        card_region_w = table.width // 3
        card_region_h = int(table.height * 0.25)

        if card_region_y + card_region_h > img.shape[0]:
            return False
        if card_region_x + card_region_w > img.shape[1]:
            return False

        card_region = img[card_region_y:card_region_y+card_region_h,
                        card_region_x:card_region_x+card_region_w]

        # Cards have white/cream background
        hsv = cv2.cvtColor(card_region, cv2.COLOR_RGB2HSV)
        white_mask = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 30, 255]))
        white_ratio = np.sum(white_mask > 0) / white_mask.size

        return white_ratio > 0.05  # At least 5% white pixels

    def _has_action_buttons(self, hsv: np.ndarray, table: DetectedTable) -> bool:
        """Check if action buttons are visible."""
        # Buttons are at very bottom of table
        button_y = table.y + int(table.height * 0.85)
        button_h = int(table.height * 0.15)

        if button_y + button_h > hsv.shape[0]:
            return False

        button_region = hsv[button_y:button_y+button_h, table.x:table.x+table.width]

        # Check for red (fold), green (call), or blue (bet)
        fold_mask = cv2.inRange(button_region, self.FOLD_COLOR['lower'], self.FOLD_COLOR['upper'])
        call_mask = cv2.inRange(button_region, self.CALL_COLOR['lower'], self.CALL_COLOR['upper'])
        bet_mask = cv2.inRange(button_region, self.BET_COLOR['lower'], self.BET_COLOR['upper'])

        # Need at least one button type visible
        fold_ratio = np.sum(fold_mask > 0) / fold_mask.size
        call_ratio = np.sum(call_mask > 0) / call_mask.size
        bet_ratio = np.sum(bet_mask > 0) / bet_mask.size

        return fold_ratio > 0.01 or call_ratio > 0.01 or bet_ratio > 0.01

    def _find_card_position(self, img: np.ndarray, table: DetectedTable) -> Tuple[int, int]:
        """Find exact position of hole cards."""
        card_region_x = table.x + table.width // 3
        card_region_y = table.y + int(table.height * 0.65)
        return (card_region_x, card_region_y)

    def _find_button_positions(self, hsv: np.ndarray, table: DetectedTable) -> Dict[str, Tuple[int, int]]:
        """Find positions of action buttons."""
        buttons = {}

        button_y = table.y + int(table.height * 0.85)
        button_h = int(table.height * 0.15)

        if button_y + button_h > hsv.shape[0]:
            return buttons

        button_region = hsv[button_y:button_y+button_h, table.x:table.x+table.width]

        for name, color in [('fold', self.FOLD_COLOR), ('call', self.CALL_COLOR), ('bet', self.BET_COLOR)]:
            mask = cv2.inRange(button_region, color['lower'], color['upper'])
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                largest = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest)
                # Convert to absolute coordinates
                abs_x = table.x + x + w // 2
                abs_y = button_y + y + h // 2
                buttons[name] = (abs_x, abs_y)

        return buttons

    def find_active_table(self, screenshot: Image.Image = None) -> Optional[DetectedTable]:
        """
        Find the table that needs action (has buttons visible).

        Uses a fallback chain:
        1. AppleScript to find GGPoker windows (most reliable)
        2. Green felt detection (fallback)

        Returns:
            DetectedTable if found, None otherwise
        """
        # Try AppleScript window detection first (most reliable)
        try:
            apples_table = self._find_table_via_applescript()
            if apples_table:
                log.info(f"AppleScript found table at ({apples_table.x}, {apples_table.y})")
                return apples_table
        except Exception as e:
            log.debug(f"AppleScript table detection failed: {e}")

        # Fall back to green felt detection
        tables = self.find_tables(screenshot)

        # Prefer table with buttons (needs action)
        for table in tables:
            if table.has_buttons:
                return table

        # Fall back to table with cards
        for table in tables:
            if table.has_cards:
                return table

        # Return highest confidence table
        return tables[0] if tables else None

    def _find_table_via_applescript(self) -> Optional[DetectedTable]:
        """Find GGPoker table using macOS AppleScript - most reliable method."""
        import subprocess

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

        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=3)

        if not result.stdout.strip():
            return None

        # Parse windows and find poker table
        poker_keywords = ['Spin', 'Gold', 'Rush', 'Cash', 'Hold', 'Omaha', 'Blinds', 'NL', 'PLO']
        entries = result.stdout.strip().rstrip(';').split(';')

        for entry in entries:
            if '###' not in entry:
                continue

            name, coords_str = entry.split('###')
            name = name.strip()

            # Check if this is a poker table (not lobby)
            if not any(kw in name for kw in poker_keywords):
                continue

            # Fix Unicode minus sign (−) that macOS returns instead of ASCII minus (-)
            coords_str = coords_str.replace('−', '-').replace('–', '-')
            coords = coords_str.split(',')
            x_pt, y_pt = int(coords[0]), int(coords[1])
            w_pt, h_pt = int(coords[2]), int(coords[3])

            # Convert from macOS points to pixels (Retina 2x)
            x_px = x_pt * 2
            y_px = y_pt * 2
            w_px = w_pt * 2
            h_px = h_pt * 2

            return DetectedTable(
                x=x_px,
                y=y_px,
                width=w_px,
                height=h_px,
                confidence=1.0,  # AppleScript is definitive
                has_cards=True,  # Assume active table has cards
                has_buttons=True
            )

        return None

    def get_table_region(self, table: DetectedTable) -> Tuple[int, int, int, int]:
        """Get (x, y, width, height) for a table."""
        return (table.x, table.y, table.width, table.height)

    def get_tlc(self, table: DetectedTable) -> Tuple[int, int]:
        """Get top-left corner for compatibility with existing code."""
        return (table.x, table.y)


def find_table_on_screen() -> Optional[Tuple[int, int, int, int]]:
    """
    Convenience function to find the main poker table.

    Returns:
        (x, y, width, height) or None
    """
    finder = SmartTableFinder()
    table = finder.find_active_table()

    if table:
        return finder.get_table_region(table)
    return None


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    print("Smart Table Finder Test")
    print("=" * 40)

    finder = SmartTableFinder()

    print("Taking screenshot...")
    screenshot = ImageGrab.grab()
    print(f"Screen size: {screenshot.size}")

    print("\nFinding tables...")
    tables = finder.find_tables(screenshot)

    if not tables:
        print("No tables found!")
        sys.exit(1)

    print(f"\nFound {len(tables)} table(s):")
    for i, table in enumerate(tables):
        print(f"\n  Table {i}:")
        print(f"    Position: ({table.x}, {table.y})")
        print(f"    Size: {table.width}x{table.height}")
        print(f"    Confidence: {table.confidence:.2f}")
        print(f"    Has cards: {table.has_cards}")
        print(f"    Has buttons: {table.has_buttons}")
        if table.button_positions:
            print(f"    Buttons: {table.button_positions}")

        # Save cropped table
        crop = screenshot.crop((table.x, table.y, table.x + table.width, table.y + table.height))
        crop.save(f'/tmp/poker_debug/smart_table_{i}.png')
        print(f"    Saved to /tmp/poker_debug/smart_table_{i}.png")

    active = finder.find_active_table(screenshot)
    if active:
        print(f"\nActive table: ({active.x}, {active.y}) buttons={active.has_buttons}")
