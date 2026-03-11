"""
Dynamic Mouse Mover - Clicks buttons based on color detection, not templates.

This module replaces MouseMoverTableBased with dynamic button detection.
Works regardless of where the table window is on screen.

Usage:
    from gamble.tools.dynamic_mouse_mover import DynamicMouseMover

    mover = DynamicMouseMover()
    mover.mouse_action("Fold", table_window)  # Click fold on specific table
"""

import logging
import time
import subprocess
from typing import Optional, Dict, Tuple
from pynput.mouse import Button, Controller

from gamble.tools.dynamic_table_finder import (
    DynamicTableFinder,
    TableWindow,
    BUTTON_COLORS
)

log = logging.getLogger(__name__)


class DynamicMouseMover:
    """
    Mouse mover that finds buttons dynamically by color instead of using template coordinates.
    """

    def __init__(self):
        self.finder = DynamicTableFinder()
        self.mouse = Controller()
        self._current_table: Optional[TableWindow] = None
        self._cached_buttons: Dict = {}
        self._last_button_scan = 0
        self.button_cache_ttl = 0.5  # Rescan buttons every 0.5 seconds

    def move_mouse_away_from_buttons_jump(self):
        """Move mouse away from button area to avoid hover effects."""
        # Move to top-right corner of screen (safe area)
        self.mouse.position = (1900, 50)
        log.debug("Moved mouse away from buttons")

    def set_current_table(self, table: TableWindow):
        """Set the table to operate on."""
        self._current_table = table
        self._cached_buttons = {}

    def find_current_table(self) -> Optional[TableWindow]:
        """Find a poker table to operate on."""
        tables = self.finder.find_poker_tables()
        if tables:
            self._current_table = tables[0]  # Use first table found
            return self._current_table
        return None

    def _get_buttons(self, force_refresh: bool = False, use_ocr: bool = True) -> Dict:
        """Get button positions, using cache if fresh enough.

        Args:
            force_refresh: If True, always re-scan buttons
            use_ocr: If True, use OCR+color hybrid detection (more reliable)
        """
        now = time.time()
        if not force_refresh and self._cached_buttons and (now - self._last_button_scan) < self.button_cache_ttl:
            return self._cached_buttons

        if not self._current_table:
            self.find_current_table()

        if self._current_table:
            screenshot = self.finder.capture_screenshot()
            # Use hybrid OCR+color detection for most reliable button finding
            if use_ocr and hasattr(self.finder, 'find_buttons_hybrid'):
                self._cached_buttons = self.finder.find_buttons_hybrid(self._current_table, screenshot)
            else:
                self._cached_buttons = self.finder.find_buttons(self._current_table, screenshot)
            self._last_button_scan = now

        return self._cached_buttons

    def _focus_table(self):
        """Bring the poker table to front."""
        script = '''
        tell application "System Events"
            tell process "GGnet" to set frontmost to true
        end tell
        '''
        subprocess.run(['osascript', '-e', script], capture_output=True)
        time.sleep(0.1)

    def _click(self, x: int, y: int):
        """Click at the given screen POINT coordinates."""
        self._focus_table()
        self.mouse.position = (x, y)
        time.sleep(0.05)
        self.mouse.click(Button.left)
        log.debug(f"Clicked at ({x}, {y})")

    def mouse_action(self, action: str, tlc=None, action_options: dict = None):
        """
        Execute an action (Fold, Call, Raise, Check, etc.)

        This method is compatible with the original MouseMoverTableBased interface,
        but ignores tlc (top-left corner) since we detect buttons dynamically.

        Args:
            action: The action to perform ("Fold", "Call", "Check", "Raise", "Bet", etc.)
            tlc: Ignored (kept for compatibility)
            action_options: Dict with optional keys like 'increases_num' for bet sizing
        """
        action = action.strip()
        log.info(f"Dynamic mouse action: {action}")

        # Map action names to button keys
        action_to_button = {
            'Fold': 'fold',
            'Call': 'call',
            'Call2': 'call',
            'Check': 'check',
            'Raise': 'raise',
            'Bet': 'raise',
            'Bet Bluff': 'raise',
            'Bet half pot': 'raise',
            'Bet pot': 'raise',
            'Bet max': 'raise',
            'BetPlus': 'raise',
        }

        button_key = action_to_button.get(action)
        if not button_key:
            log.warning(f"Unknown action: {action}")
            return

        # Get current buttons
        buttons = self._get_buttons(force_refresh=True)

        if button_key not in buttons:
            # Check might show as Call button (same green color)
            if button_key == 'check' and 'call' in buttons:
                button_key = 'call'
            else:
                log.warning(f"Button '{button_key}' not found. Available: {list(buttons.keys())}")
                return

        button_info = buttons[button_key]
        x, y = button_info['screen_pt']

        log.info(f"Clicking {action} at screen point ({x}, {y})")
        self._click(x, y)

        # For raise/bet actions, may need to confirm amount
        if button_key == 'raise' and action_options:
            # TODO: Handle bet sizing with slider or +/- buttons
            pass


class DynamicClickerMixin:
    """
    Mixin that adds dynamic clicking capability to any class.

    Usage:
        class MyClass(DynamicClickerMixin):
            def do_something(self):
                self.click_fold()
    """

    def __init__(self):
        self._dynamic_mover = DynamicMouseMover()

    def click_fold(self):
        """Click the fold button."""
        self._dynamic_mover.mouse_action("Fold")

    def click_call(self):
        """Click the call button."""
        self._dynamic_mover.mouse_action("Call")

    def click_check(self):
        """Click the check button."""
        self._dynamic_mover.mouse_action("Check")

    def click_raise(self):
        """Click the raise button."""
        self._dynamic_mover.mouse_action("Raise")


def quick_fold():
    """Quick function to fold on any visible table."""
    mover = DynamicMouseMover()
    if mover.find_current_table():
        mover.mouse_action("Fold")
        return True
    return False


def quick_call():
    """Quick function to call on any visible table."""
    mover = DynamicMouseMover()
    if mover.find_current_table():
        mover.mouse_action("Call")
        return True
    return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    print("Testing Dynamic Mouse Mover")
    print("="*50)

    mover = DynamicMouseMover()
    table = mover.find_current_table()

    if table:
        print(f"Found table: {table}")
        buttons = mover._get_buttons(force_refresh=True)
        print(f"Buttons: {list(buttons.keys())}")

        for name, info in buttons.items():
            print(f"  {name}: screen point {info['screen_pt']}")
    else:
        print("No poker table found")
