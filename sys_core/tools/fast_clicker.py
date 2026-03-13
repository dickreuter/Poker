"""
Fast Clicker - CGEventPost-based mouse control for macOS

Uses Quartz Core Graphics for direct event injection.
Much faster and more reliable than pymouse.

Usage:
    from sys_core.tools.fast_clicker import FastClicker

    clicker = FastClicker()
    clicker.click(x, y)  # Instant click
    clicker.click_with_move(x, y)  # Move then click
"""

import logging
import subprocess
import time
import random

try:
    from Quartz import (
        CGEventCreateMouseEvent,
        CGEventPost,
        CGEventSetIntegerValueField,
        kCGEventMouseMoved,
        kCGEventLeftMouseDown,
        kCGEventLeftMouseUp,
        kCGMouseButtonLeft,
        kCGHIDEventTap,
        kCGMouseEventClickState,
    )
    from Quartz.CoreGraphics import CGPoint
    QUARTZ_AVAILABLE = True
except ImportError:
    QUARTZ_AVAILABLE = False

log = logging.getLogger(__name__)


def activate_ggpoker_window():
    """Bring GGSystem window to front using AppleScript."""
    try:
        # Use direct application activation - more reliable than System Events
        script = '''
        tell application "GGPoker" to activate
        delay 0.2
        '''
        subprocess.run(['osascript', '-e', script], capture_output=True, timeout=3)
        time.sleep(0.1)  # Additional pause for window to fully activate
        return True
    except Exception as e:
        log.warning(f"Failed to activate GGSystem window: {e}")
        return False


def get_retina_scale():
    """Get Retina display scaling factor (2 for Retina, 1 for normal)."""
    try:
        from AppKit import NSScreen
        screen = NSScreen.mainScreen()
        return screen.backingScaleFactor()
    except:
        # Fallback: assume Retina if screen width > 2000
        from PIL import ImageGrab
        screenshot = ImageGrab.grab()
        if screenshot.size[0] > 2000:
            return 2.0
        return 1.0


class FastClicker:
    """
    Fast mouse clicker using macOS Quartz/CGEventPost.

    This bypasses pymouse and directly injects mouse events
    into the system event stream. Much faster and more reliable.

    IMPORTANT: Handles Retina display scaling automatically.
    Input coordinates are PIXEL coordinates from screenshots.
    """

    def __init__(self, min_delay: float = 0.005, max_delay: float = 0.01):
        """
        Args:
            min_delay: Minimum delay between events (seconds)
            max_delay: Maximum delay between events (seconds)
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.retina_scale = get_retina_scale()

        if not QUARTZ_AVAILABLE:
            log.warning("Quartz not available, falling back to pymouse")
            from sys_core import pymouse
            self.mouse = pymouse.PyMouse()
            self.use_quartz = False
        else:
            self.use_quartz = True
            log.debug(f"FastClicker initialized with Quartz CGEventPost (Retina scale: {self.retina_scale})")

    def _random_delay(self):
        """Small random delay for human-like behavior."""
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def _scale_coords(self, x: int, y: int) -> tuple:
        """Scale pixel coordinates to point coordinates for Retina displays."""
        return (x / self.retina_scale, y / self.retina_scale)

    def move(self, x: int, y: int):
        """
        Instantly move mouse to position.

        Args:
            x: X coordinate (PIXEL coordinate from screenshot)
            y: Y coordinate (PIXEL coordinate from screenshot)
        """
        # Scale for Retina display
        scaled_x, scaled_y = self._scale_coords(x, y)

        if self.use_quartz:
            point = CGPoint(scaled_x, scaled_y)
            event = CGEventCreateMouseEvent(None, kCGEventMouseMoved, point, kCGMouseButtonLeft)
            CGEventPost(kCGHIDEventTap, event)
        else:
            self.mouse.move(int(scaled_x), int(scaled_y))

    def click(self, x: int, y: int, button: str = 'left', activate_window: bool = True):
        """
        Click at position (instant teleport + click).

        Args:
            x: X coordinate (PIXEL coordinate from screenshot)
            y: Y coordinate (PIXEL coordinate from screenshot)
            button: 'left' or 'right' (only left supported currently)
            activate_window: Whether to activate GGSystem window first
        """
        # Activate GGSystem window to ensure it receives the click
        if activate_window:
            activate_ggpoker_window()

        # Scale for Retina display
        scaled_x, scaled_y = self._scale_coords(x, y)

        if self.use_quartz:
            point = CGPoint(scaled_x, scaled_y)

            # Move mouse to position first (helps with focus)
            self.move(x, y)  # move() already scales
            time.sleep(0.02)

            # Mouse down
            event_down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(event_down, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, event_down)

            self._random_delay()

            # Mouse up
            event_up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(event_up, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, event_up)

            log.debug(f"FastClick at pixel ({x}, {y}) -> point ({scaled_x:.0f}, {scaled_y:.0f})")
        else:
            self.mouse.move(int(scaled_x), int(scaled_y))
            self._random_delay()
            self.mouse.click(int(scaled_x), int(scaled_y))

    def instant_click(self, x: int, y: int):
        """
        Ultra-fast click with ZERO delays - for tournament grinding.
        Use when speed is critical and human-like behavior is not needed.

        Args:
            x: X coordinate (PIXEL coordinate from screenshot)
            y: Y coordinate (PIXEL coordinate from screenshot)
        """
        scaled_x, scaled_y = self._scale_coords(x, y)

        if self.use_quartz:
            point = CGPoint(scaled_x, scaled_y)
            event_down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, kCGMouseButtonLeft)
            event_up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, kCGMouseButtonLeft)
            CGEventPost(kCGHIDEventTap, event_down)
            CGEventPost(kCGHIDEventTap, event_up)  # No delay!
            log.debug(f"InstantClick at pixel ({x}, {y}) -> point ({scaled_x:.0f}, {scaled_y:.0f})")
        else:
            self.mouse.click(int(scaled_x), int(scaled_y))

    def click_with_move(self, x: int, y: int, move_delay: float = 0.05):
        """
        Move to position, then click (slightly more human-like).

        Args:
            x: X coordinate
            y: Y coordinate
            move_delay: Delay between move and click
        """
        self.move(x, y)
        time.sleep(move_delay + random.uniform(0, 0.02))
        self.click(x, y)

    def click_center(self, x1: int, y1: int, x2: int, y2: int, tolerance_x: int = 5, tolerance_y: int = 5):
        """
        Click in the center of a rectangle with slight randomness.

        Args:
            x1, y1: Top-left corner
            x2, y2: Bottom-right corner
            tolerance_x, tolerance_y: Random offset range
        """
        center_x = (x1 + x2) // 2 + random.randint(-tolerance_x, tolerance_x)
        center_y = (y1 + y2) // 2 + random.randint(-tolerance_y, tolerance_y)
        self.click(center_x, center_y)
        log.debug(f"FastClick center at ({center_x}, {center_y}) from rect ({x1},{y1})-({x2},{y2})")

    def double_click(self, x: int, y: int):
        """
        Double-click at position.
        """
        if self.use_quartz:
            point = CGPoint(x, y)

            # First click
            event_down1 = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(event_down1, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, event_down1)

            time.sleep(0.01)

            event_up1 = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(event_up1, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, event_up1)

            time.sleep(0.05)

            # Second click (clickState = 2 for double-click)
            event_down2 = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(event_down2, kCGMouseEventClickState, 2)
            CGEventPost(kCGHIDEventTap, event_down2)

            time.sleep(0.01)

            event_up2 = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(event_up2, kCGMouseEventClickState, 2)
            CGEventPost(kCGHIDEventTap, event_up2)

            log.debug(f"FastDoubleClick at ({x}, {y})")
        else:
            self.mouse.click(x, y, 1, 2)  # 2 clicks


class FastMouseMover:
    """
    Drop-in replacement for MouseMoverTableBased that uses FastClicker.
    """

    def __init__(self, table_dict):
        self.table_dict = table_dict
        self.clicker = FastClicker()

        # Import button detector for smart detection
        try:
            from sys_core.tools.button_detector import ButtonDetector, SmartMouseAction
            self.button_detector = ButtonDetector()
            self.smart_action = SmartMouseAction(table_dict)
            self.use_smart_detection = True
        except ImportError:
            self.use_smart_detection = False
            log.warning("ButtonDetector not available, using fallback coordinates")

    def mouse_action(self, decision: str, topleftcorner, options=None):
        """
        Execute mouse action for the given decision.

        Args:
            decision: Action to take ('Fold', 'Call', 'Check', 'Bet', etc.)
            topleftcorner: (x, y) of table top-left corner
            options: Additional options for complex actions
        """
        if decision == 'Check Deception':
            decision = 'Check'
        if decision == 'Call Deception':
            decision = 'Call'

        tlx = int(topleftcorner[0])
        tly = int(topleftcorner[1])

        log.info(f"FastMouse action: {decision} at TLC ({tlx}, {tly})")

        # Try smart color-based detection first
        if self.use_smart_detection and decision in ["Fold", "Call", "Check", "Bet", "Bet Bluff"]:
            from PIL import ImageGrab
            screenshot = ImageGrab.grab()
            pos = self.smart_action.get_action_position(decision, screenshot, topleftcorner)
            if pos:
                log.info(f"Smart detection found {decision} at {pos}")
                self.clicker.click_center(pos[0], pos[1], pos[2], pos[3])
                time.sleep(0.1)
                self._move_away()
                return
            else:
                log.warning(f"Smart detection failed for {decision}, using table_dict")

        # Fallback to table_dict coordinates
        self._execute_from_table_dict(decision, tlx, tly, options)
        self._move_away()

    def _execute_from_table_dict(self, decision: str, tlx: int, tly: int, options=None):
        """Execute action using stored coordinates from table_dict."""
        coord_map = {
            'Fold': 'mouse_fold',
            'Call': 'mouse_call',
            'Call2': 'mouse_call2',
            'Check': 'mouse_check',
            'Bet': 'mouse_raise',
            'Bet Bluff': 'mouse_raise',
            'Imback': 'mouse_imback',
            'resume_hand': 'mouse_resume_hand',
        }

        key = coord_map.get(decision)
        if key and key in self.table_dict:
            coo = self.table_dict[key]
            self.clicker.click_center(
                coo['x1'] + tlx, coo['y1'] + tly,
                coo['x2'] + tlx, coo['y2'] + tly
            )
        elif decision == 'BetPlus' and options:
            # Multiple increase clicks then raise
            for _ in range(int(options.get('increases_num', 1))):
                coo = self.table_dict['mouse_increase']
                self.clicker.click_center(
                    coo['x1'] + tlx, coo['y1'] + tly,
                    coo['x2'] + tlx, coo['y2'] + tly
                )
                time.sleep(0.1)
            coo = self.table_dict['mouse_raise']
            self.clicker.click_center(
                coo['x1'] + tlx, coo['y1'] + tly,
                coo['x2'] + tlx, coo['y2'] + tly
            )
        elif decision == 'Bet half pot':
            coo = self.table_dict['mouse_half_pot']
            self.clicker.click_center(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)
            time.sleep(0.1)
            coo = self.table_dict['mouse_raise']
            self.clicker.click_center(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)
        elif decision == 'Bet pot':
            coo = self.table_dict['mouse_full_pot']
            self.clicker.click_center(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)
            time.sleep(0.1)
            coo = self.table_dict['mouse_raise']
            self.clicker.click_center(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)
        elif decision == 'Bet max':
            coo = self.table_dict['mouse_all_in']
            self.clicker.click_center(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)
            time.sleep(0.1)
            coo = self.table_dict['mouse_raise']
            self.clicker.click_center(coo['x1'] + tlx, coo['y1'] + tly, coo['x2'] + tlx, coo['y2'] + tly)
        else:
            log.warning(f"Unknown decision: {decision}")

    def _move_away(self):
        """Move mouse away from buttons after action."""
        x = random.randint(1700, 2000)
        y = random.randint(10, 200)
        self.clicker.move(x, y)
        log.debug(f"Moved mouse away to ({x}, {y})")

    def click_deal_me_in(self, table_region=None):
        """
        Find and click the 'Deal Me In' button (Rush & Cash).

        The button is red/orange, typically in the bottom right of the table.
        Returns True if button was found and clicked.
        """
        from PIL import ImageGrab
        import cv2
        import numpy as np

        screenshot = ImageGrab.grab()
        img = np.array(screenshot)
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

        # "Deal Me In" is red/orange like fold button
        red_lower = np.array([0, 100, 100])
        red_upper = np.array([20, 255, 255])

        mask = cv2.inRange(hsv, red_lower, red_upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Find largest red button in lower portion of screen
        best_button = None
        best_area = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 2000:  # Need substantial size
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            # Button should be in bottom half and button-shaped
            if y > 1500 and w > 50 and h > 20 and 1.5 < (w/h) < 8:
                if area > best_area:
                    best_area = area
                    best_button = (x, y, w, h)

        if best_button:
            x, y, w, h = best_button
            center_x = x + w // 2
            center_y = y + h // 2
            log.info(f"Found 'Deal Me In' button at ({center_x}, {center_y}), clicking...")
            self.clicker.click(center_x, center_y)
            time.sleep(0.3)
            return True

        return False

    def move_mouse_away_from_buttons(self):
        """Compatibility method."""
        self._move_away()

    def move_mouse_away_from_buttons_jump(self):
        """Compatibility method."""
        self._move_away()


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("FastClicker Test")
    print("=" * 40)

    clicker = FastClicker()
    print(f"Using Quartz: {clicker.use_quartz}")

    # Test move
    print("Moving to (500, 500)...")
    clicker.move(500, 500)
    time.sleep(0.5)

    # Test click (will click wherever the mouse is)
    print("Clicking at (600, 600)...")
    clicker.click(600, 600)

    print("Done!")
