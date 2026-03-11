"""
UNIFIED WINDOW FINDER - Single Source of Truth for Finding GGPoker Windows

Consolidates functionality from:
- tools/dynamic_table_finder.py (WindowFinder class)
- tools/smart_ui_automation.py (WindowFinder class - different implementation!)
- tools/auto_calibrate.py (WindowFinder class - yet another implementation!)
- tools/ten_table_bot.py (WindowFinder class - copy-paste of dynamic_table_finder)

This is now THE ONLY window finder. All bots should use this.

Usage:
    from gamble.core import WindowFinder, TableWindow

    finder = WindowFinder()

    # Get all GGPoker windows
    all_windows = finder.find_all_windows()

    # Get only poker table windows (excludes lobby)
    poker_tables = finder.find_poker_tables()

    # Get the lobby window
    lobby = finder.find_lobby_window()
"""

import subprocess
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
from PIL import Image, ImageGrab

from gamble.core.constants import (
    RETINA_SCALE,
    GGPOKER_PROCESS_NAME,
    POKER_TABLE_KEYWORDS,
    POKER_TABLE_EXCLUDE,
)

log = logging.getLogger(__name__)


@dataclass
class TableWindow:
    """
    Represents a GGPoker window with position in both POINTS and PIXELS.

    POINTS: macOS coordinate system (for AppleScript, mouse clicks)
    PIXELS: Screenshot coordinate system (for image processing)

    Retina displays: PIXELS = POINTS * 2
    """
    name: str           # Window title
    x_pt: int           # X position in POINTS
    y_pt: int           # Y position in POINTS
    w_pt: int           # Width in POINTS
    h_pt: int           # Height in POINTS

    # Computed pixel values
    @property
    def x_px(self) -> int:
        return self.x_pt * RETINA_SCALE

    @property
    def y_px(self) -> int:
        return self.y_pt * RETINA_SCALE

    @property
    def w_px(self) -> int:
        return self.w_pt * RETINA_SCALE

    @property
    def h_px(self) -> int:
        return self.h_pt * RETINA_SCALE

    @property
    def bounds_pt(self) -> Tuple[int, int, int, int]:
        """Return (x, y, w, h) in POINTS"""
        return (self.x_pt, self.y_pt, self.w_pt, self.h_pt)

    @property
    def bounds_px(self) -> Tuple[int, int, int, int]:
        """Return (x, y, w, h) in PIXELS"""
        return (self.x_px, self.y_px, self.w_px, self.h_px)

    def is_poker_table(self) -> bool:
        """
        Check if this window is an active poker table (not lobby, not popup).

        Active tables have "Blinds X | Y" in the name, e.g.:
        - "Spin & Gold $0.25 - Blinds 15 | 30" -> IS a table
        - "Highlight for $0.25 x40,000 Table!" -> NOT a table (just prize popup)
        - "GGPoker" -> NOT a table (lobby)
        """
        # If it has "Blinds", it's definitely an active table
        if 'Blinds' in self.name:
            return True

        # Exclude known non-table windows
        for exclude in POKER_TABLE_EXCLUDE:
            if exclude in self.name:
                return False

        # Check for other poker table keywords
        return any(kw in self.name for kw in POKER_TABLE_KEYWORDS)

    def is_lobby(self) -> bool:
        """Check if this is the main GGPoker lobby window"""
        return self.name == "GGPoker"

    def capture(self, full_screenshot: Optional[Image.Image] = None) -> Image.Image:
        """
        Capture this window from a full-screen screenshot.

        Args:
            full_screenshot: Optional pre-captured full screen image.
                           If None, will grab new screenshot.

        Returns:
            Cropped image of just this window (in PIXELS).
        """
        if full_screenshot is None:
            full_screenshot = ImageGrab.grab()

        return full_screenshot.crop((
            self.x_px, self.y_px,
            self.x_px + self.w_px,
            self.y_px + self.h_px
        ))

    def table_px_to_screen_pt(self, x_px: int, y_px: int) -> Tuple[int, int]:
        """
        Convert table-relative PIXEL coordinates to screen POINT coordinates.

        Use this when you found something at (x, y) pixels in the table image
        and need to click it on screen.

        Args:
            x_px: X position in table image pixels
            y_px: Y position in table image pixels

        Returns:
            (x_pt, y_pt): Screen coordinates in POINTS for clicking
        """
        screen_x_pt = self.x_pt + x_px // RETINA_SCALE
        screen_y_pt = self.y_pt + y_px // RETINA_SCALE
        return (screen_x_pt, screen_y_pt)

    def __repr__(self):
        return f"TableWindow('{self.name}', pos=({self.x_pt},{self.y_pt}), size={self.w_pt}x{self.h_pt})"


class WindowFinder:
    """
    Find GGPoker windows on macOS using AppleScript.

    This is the UNIFIED implementation that all bots should use.
    """

    def __init__(self):
        self._last_screenshot: Optional[Image.Image] = None

    def find_all_windows(self) -> List[TableWindow]:
        """
        Find all GGPoker windows.

        Returns:
            List of TableWindow objects for all GGPoker windows.
        """
        script = f'''
        tell application "System Events"
            if exists process "{GGPOKER_PROCESS_NAME}" then
                tell process "{GGPOKER_PROCESS_NAME}"
                    set windowList to {{}}
                    repeat with w in windows
                        try
                            set winName to name of w as text
                            set winPos to position of w
                            set winSize to size of w
                            set end of windowList to {{winName, item 1 of winPos, item 2 of winPos, item 1 of winSize, item 2 of winSize}}
                        end try
                    end repeat
                    return windowList
                end tell
            else
                return {{}}
            end if
        end tell
        '''

        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                log.warning(f"AppleScript error: {result.stderr}")
                return []

            output = result.stdout.strip()
            if not output or output == '{}':
                return []

            windows = self._parse_window_list(output)
            log.info(f"Found {len(windows)} GGPoker window(s)")
            return windows

        except subprocess.TimeoutExpired:
            log.error("AppleScript timeout finding windows")
            return []
        except Exception as e:
            log.error(f"Error finding windows: {e}")
            return []

    def _parse_window_list(self, output: str) -> List[TableWindow]:
        """Parse AppleScript output into TableWindow objects."""
        windows = []

        # AppleScript returns: {{name, x, y, w, h}, {name, x, y, w, h}, ...}
        # Remove outer braces and split by "}, {"
        output = output.strip()
        if output.startswith('{'):
            output = output[1:]
        if output.endswith('}'):
            output = output[:-1]

        # Handle empty result
        if not output.strip():
            return []

        # Split into individual window entries
        entries = []
        depth = 0
        current = ""
        for char in output:
            if char == '{':
                depth += 1
                if depth == 1:
                    current = ""
                    continue
            elif char == '}':
                depth -= 1
                if depth == 0:
                    entries.append(current.strip())
                    current = ""
                    continue
            if depth >= 1:
                current += char

        for entry in entries:
            try:
                # Parse: "name, x, y, w, h"
                parts = entry.split(', ')
                if len(parts) >= 5:
                    name = parts[0].strip()

                    # Fix Unicode minus sign that macOS sometimes returns
                    # U+2212 (−) instead of U+002D (-)
                    coords = [p.replace('−', '-').replace('–', '-') for p in parts[1:5]]

                    x = int(coords[0])
                    y = int(coords[1])
                    w = int(coords[2])
                    h = int(coords[3])

                    windows.append(TableWindow(name, x, y, w, h))
            except (ValueError, IndexError) as e:
                log.debug(f"Could not parse window entry '{entry}': {e}")
                continue

        return windows

    def find_poker_tables(self) -> List[TableWindow]:
        """
        Find only active poker table windows (excludes lobby, popups).

        Returns:
            List of TableWindow objects for active poker tables.
        """
        all_windows = self.find_all_windows()
        tables = [w for w in all_windows if w.is_poker_table()]
        log.info(f"Found {len(tables)} poker table(s)")
        return tables

    def find_lobby_window(self) -> Optional[TableWindow]:
        """
        Find the main GGPoker lobby window.

        Returns:
            TableWindow for lobby, or None if not found.
        """
        all_windows = self.find_all_windows()
        for w in all_windows:
            if w.is_lobby():
                return w
        return None

    def capture_screenshot(self) -> Image.Image:
        """Take and cache a full-screen screenshot."""
        self._last_screenshot = ImageGrab.grab()
        return self._last_screenshot

    def get_window_by_name(self, name_contains: str) -> Optional[TableWindow]:
        """Find a window whose name contains the given string."""
        all_windows = self.find_all_windows()
        for w in all_windows:
            if name_contains.lower() in w.name.lower():
                return w
        return None


# Singleton instance for convenience
_finder: Optional[WindowFinder] = None


def get_window_finder() -> WindowFinder:
    """Get the singleton WindowFinder instance."""
    global _finder
    if _finder is None:
        _finder = WindowFinder()
    return _finder
