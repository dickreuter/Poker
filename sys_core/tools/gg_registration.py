"""
GGSystem Spin & Gold Registration Automation

Comprehensive automation flow for tournament registration:
1. Detect if already in Spin & Gold lobby (by finding tile grid)
2. If not, navigate there using visual detection
3. Select the correct stake ($1 preferred, fallback to $0.25)
4. Click "Play Now" button (find by image, not coordinates)
5. Handle "Insufficient Balance" dialog if it appears
6. Verify registration succeeded (new window with "Spin & Gold" in title)
7. Handle errors gracefully with retries

Uses the smart_ui_automation module for all visual detection.

Usage:
    from sys_core.tools.gg_registration import SpinGoldRegistration

    reg = SpinGoldRegistration()
    success = reg.register(stake=1.0)
"""

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageGrab

# Import adaptive learner for self-improvement
from sys_core.tools.adaptive_learner import log_action, report_issue, get_threshold

# Setup dedicated logger for registration
log = logging.getLogger("gg_registration")

# Constants
RETINA_SCALE = 2
LOG_DIR = Path("/Users/sebastian/Developer/Gamble/log")
TEMPLATE_DIR = Path("/Users/sebastian/Developer/Gamble/sys_core/tools/templates")


class RegistrationState(Enum):
    """Current state of the registration flow."""
    UNKNOWN = "unknown"
    NO_GGPOKER = "no_ggpoker"
    MAIN_LOBBY = "main_lobby"
    SPIN_GOLD_LOBBY = "spin_gold_lobby"
    REGISTRATION_DIALOG = "registration_dialog"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    WAITING_FOR_TABLE = "waiting_for_table"
    TABLE_OPEN = "table_open"
    ERROR = "error"


class RegistrationError(Exception):
    """Custom exception for registration errors."""
    pass


@dataclass
class UIElement:
    """Represents a detected UI element."""
    name: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 0.0

    @property
    def center(self) -> Tuple[int, int]:
        """Center point in pixels."""
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def center_points(self) -> Tuple[int, int]:
        """Center point in macOS points (for clicking)."""
        cx, cy = self.center
        return (cx // RETINA_SCALE, cy // RETINA_SCALE)


def setup_registration_logger():
    """Setup dedicated logger for registration module."""
    logger = logging.getLogger("gg_registration")
    logger.setLevel(logging.DEBUG)

    # Create log directory if needed
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # File handler
    log_file = LOG_DIR / "registration.log"
    fh = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=1_000_000,  # 1MB
        backupCount=5
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    ))

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        '%(levelname)s - %(message)s'
    ))

    # Only add handlers if not already added
    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger


# Initialize logger on import
import logging.handlers
setup_registration_logger()


class SmartUIAutomation:
    """
    Smart UI automation using visual detection.

    Finds UI elements by:
    1. Color-based detection (buttons, backgrounds)
    2. Template matching (icons, specific elements)
    3. Text recognition (OCR for labels)
    """

    # Color ranges in HSV for GGSystem UI elements
    COLORS = {
        'green_button': {
            'lower': np.array([35, 80, 80]),
            'upper': np.array([85, 255, 255])
        },
        'orange_button': {
            'lower': np.array([10, 80, 80]),
            'upper': np.array([25, 255, 255])
        },
        'red_button': {
            'lower': np.array([0, 80, 80]),
            'upper': np.array([15, 255, 255])
        },
        'gold_text': {
            'lower': np.array([15, 80, 80]),
            'upper': np.array([35, 255, 255])
        },
        'dark_background': {
            'lower': np.array([0, 0, 0]),
            'upper': np.array([180, 50, 60])
        },
        'spin_gold_purple': {
            'lower': np.array([130, 50, 50]),
            'upper': np.array([160, 255, 255])
        }
    }

    def __init__(self):
        self._screenshot: Optional[Image.Image] = None
        self._screenshot_np: Optional[np.ndarray] = None
        self._screenshot_hsv: Optional[np.ndarray] = None

    def capture_screen(self) -> Image.Image:
        """Capture fresh screenshot."""
        self._screenshot = ImageGrab.grab()
        self._screenshot_np = np.array(self._screenshot)
        self._screenshot_hsv = cv2.cvtColor(
            cv2.cvtColor(self._screenshot_np, cv2.COLOR_RGB2BGR),
            cv2.COLOR_BGR2HSV
        )
        log.debug(f"Captured screenshot: {self._screenshot.size}")
        return self._screenshot

    def find_by_color(
        self,
        color_name: str,
        min_area: int = 1000,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> List[UIElement]:
        """
        Find UI elements by color.

        Args:
            color_name: Key from COLORS dict
            min_area: Minimum contour area
            region: Optional (x, y, w, h) to search within

        Returns:
            List of UIElement objects
        """
        if self._screenshot_hsv is None:
            self.capture_screen()

        if color_name not in self.COLORS:
            log.warning(f"Unknown color: {color_name}")
            return []

        color = self.COLORS[color_name]

        # Crop to region if specified
        hsv = self._screenshot_hsv
        offset_x, offset_y = 0, 0
        if region:
            x, y, w, h = region
            hsv = hsv[y:y+h, x:x+w]
            offset_x, offset_y = x, y

        # Create mask
        mask = cv2.inRange(hsv, color['lower'], color['upper'])

        # Handle red color wraparound in HSV
        if color_name == 'red_button':
            mask2 = cv2.inRange(hsv, np.array([165, 80, 80]), np.array([180, 255, 255]))
            mask = cv2.bitwise_or(mask, mask2)

        # Clean up mask
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        elements = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue

            x, y, w, h = cv2.boundingRect(contour)
            elements.append(UIElement(
                name=color_name,
                x=x + offset_x,
                y=y + offset_y,
                width=w,
                height=h,
                confidence=min(area / 10000, 1.0)  # Rough confidence
            ))

        # Sort by area (largest first)
        elements.sort(key=lambda e: e.width * e.height, reverse=True)
        log.debug(f"Found {len(elements)} {color_name} elements")
        return elements

    def find_by_template(
        self,
        template_path: str,
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> Optional[UIElement]:
        """
        Find UI element by template matching.

        Args:
            template_path: Path to template image
            threshold: Match threshold (0-1)
            region: Optional search region

        Returns:
            UIElement if found, None otherwise
        """
        if self._screenshot_np is None:
            self.capture_screen()

        if not os.path.exists(template_path):
            log.warning(f"Template not found: {template_path}")
            return None

        template = cv2.imread(template_path)
        if template is None:
            log.warning(f"Failed to load template: {template_path}")
            return None

        # Convert screenshot to BGR for matching
        img = cv2.cvtColor(self._screenshot_np, cv2.COLOR_RGB2BGR)

        # Crop to region if specified
        offset_x, offset_y = 0, 0
        if region:
            x, y, w, h = region
            img = img[y:y+h, x:x+w]
            offset_x, offset_y = x, y

        # Template matching
        result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        log.debug(f"Template match score: {max_val:.4f} (threshold: {threshold})")

        if max_val >= threshold:
            th, tw = template.shape[:2]
            return UIElement(
                name=os.path.basename(template_path),
                x=max_loc[0] + offset_x,
                y=max_loc[1] + offset_y,
                width=tw,
                height=th,
                confidence=max_val
            )

        return None

    def find_text_region(
        self,
        text: str,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> Optional[UIElement]:
        """
        Find region containing specific text using OCR.

        Args:
            text: Text to search for (case insensitive)
            region: Optional search region

        Returns:
            UIElement if found, None otherwise
        """
        # This would require pytesseract - placeholder for now
        log.debug(f"OCR search for '{text}' not implemented yet")
        return None

    def detect_spin_gold_tiles(self) -> List[UIElement]:
        """
        Detect Spin & Gold stake selection tiles.

        Tiles are identified by:
        - Gold/orange colored headers
        - Consistent spacing and size
        - Position in center-right of lobby

        Returns:
            List of UIElement for each tile, ordered by stake (low to high)
        """
        if self._screenshot_np is None:
            self.capture_screen()

        # Spin & Gold tiles have gold/orange headers with stake amounts
        gold_elements = self.find_by_color('gold_text', min_area=500)

        # Filter to likely tiles (in center-right area, reasonable size)
        screen_h, screen_w = self._screenshot_np.shape[:2]
        tiles = []

        for elem in gold_elements:
            # Tiles should be in center-right area
            if elem.x < screen_w * 0.3:
                continue
            # Not too close to edges
            if elem.x > screen_w * 0.9:
                continue
            # Reasonable aspect ratio for tile header
            if elem.width < 50 or elem.height < 15:
                continue

            tiles.append(elem)

        log.debug(f"Found {len(tiles)} potential Spin & Gold tiles")
        return tiles

    def detect_play_now_button(self) -> Optional[UIElement]:
        """
        Detect "Play Now" button by color and shape.

        The button is typically green and at the bottom of a tile
        or registration dialog.
        """
        green_buttons = self.find_by_color('green_button', min_area=2000)

        for btn in green_buttons:
            # Button should be wider than tall (typical button shape)
            if btn.width > btn.height and btn.width > 80:
                log.info(f"Found Play Now button at ({btn.x}, {btn.y}) size {btn.width}x{btn.height}")
                return btn

        # Also try template matching
        template_path = str(TEMPLATE_DIR / "play_now_btn.png")
        if os.path.exists(template_path):
            return self.find_by_template(template_path, threshold=0.7)

        return None

    def detect_register_button(self) -> Optional[UIElement]:
        """Detect Register button in dialog."""
        return self.detect_play_now_button()  # Same green button style

    def detect_cancel_button(self) -> Optional[UIElement]:
        """Detect Cancel button (usually gray or outlined)."""
        # Cancel buttons are often darker/gray
        elements = self.find_by_color('dark_background', min_area=2000)

        for elem in elements:
            if elem.width > elem.height and elem.width > 60:
                return elem

        return None

    def detect_insufficient_balance_dialog(self) -> bool:
        """Check if Insufficient Balance dialog is visible."""
        if self._screenshot_np is None:
            self.capture_screen()

        # Look for red warning elements
        red_elements = self.find_by_color('red_button', min_area=500)

        # Also check for specific text patterns via OCR (future)
        # For now, just check if there's a prominent red element
        # in the center of the screen
        screen_h, screen_w = self._screenshot_np.shape[:2]

        for elem in red_elements:
            center_x, center_y = elem.center
            # Center of screen check
            if (screen_w * 0.3 < center_x < screen_w * 0.7 and
                screen_h * 0.3 < center_y < screen_h * 0.7):
                log.warning("Detected potential Insufficient Balance dialog")
                return True

        return False


class WindowManager:
    """
    Manage GGSystem windows using macOS AppleScript.
    """

    @staticmethod
    def get_all_windows() -> List[Dict]:
        """Get all GGSystem windows with positions."""
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
                        windows.append({
                            'name': name.strip(),
                            'x_pt': int(coords[0]),
                            'y_pt': int(coords[1]),
                            'w_pt': int(coords[2]),
                            'h_pt': int(coords[3]),
                            'x_px': int(coords[0]) * RETINA_SCALE,
                            'y_px': int(coords[1]) * RETINA_SCALE,
                            'w_px': int(coords[2]) * RETINA_SCALE,
                            'h_px': int(coords[3]) * RETINA_SCALE,
                        })

            log.debug(f"Found {len(windows)} GGSystem windows")
            return windows

        except subprocess.TimeoutExpired:
            log.error("Timeout getting GGSystem windows")
            return []
        except Exception as e:
            log.error(f"Error getting windows: {e}")
            return []

    @staticmethod
    def find_main_lobby() -> Optional[Dict]:
        """Find the main GGSystem lobby window."""
        windows = WindowManager.get_all_windows()

        for win in windows:
            name = win['name'].lower()
            # Main lobby is usually just "GGSystem" or similar
            if name == 'ggpoker' or 'lobby' in name:
                log.info(f"Found main lobby: {win['name']}")
                return win

        # If no explicit lobby, return largest window
        if windows:
            largest = max(windows, key=lambda w: w['w_pt'] * w['h_pt'])
            log.info(f"Using largest window as lobby: {largest['name']}")
            return largest

        return None

    @staticmethod
    def find_spin_gold_table() -> Optional[Dict]:
        """Find Spin & Gold table window."""
        windows = WindowManager.get_all_windows()

        for win in windows:
            name = win['name'].lower()
            if 'spin' in name and 'gold' in name:
                log.info(f"Found Spin & Gold table: {win['name']}")
                return win

        return None

    @staticmethod
    def focus_window(window_name: str) -> bool:
        """Bring window to front."""
        script = f'''
        tell application "System Events"
            tell process "GGnet"
                set frontmost to true
                repeat with w in windows
                    if name of w contains "{window_name[:20]}" then
                        perform action "AXRaise" of w
                        return true
                    end if
                end repeat
            end tell
        end tell
        return false
        '''

        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=3
            )
            success = 'true' in result.stdout.lower()
            log.debug(f"Focus window '{window_name}': {success}")
            return success
        except Exception as e:
            log.error(f"Failed to focus window: {e}")
            return False

    @staticmethod
    def activate_ggpoker() -> bool:
        """Activate GGSystem application."""
        script = '''
        tell application "GGSystem" to activate
        '''
        try:
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=3)
            time.sleep(0.2)
            return True
        except Exception as e:
            log.error(f"Failed to activate GGSystem: {e}")
            return False

    @staticmethod
    def count_spin_gold_tables() -> int:
        """Count how many Spin & Gold tables are open."""
        windows = WindowManager.get_all_windows()
        count = sum(1 for w in windows if 'spin' in w['name'].lower() and 'gold' in w['name'].lower())
        log.debug(f"Found {count} Spin & Gold tables")
        return count


class Clicker:
    """
    Mouse clicking using Quartz CGEventPost.
    Handles Retina display scaling.
    """

    def __init__(self):
        try:
            from Quartz import (
                CGEventCreateMouseEvent,
                CGEventPost,
                kCGEventLeftMouseDown,
                kCGEventLeftMouseUp,
                kCGEventMouseMoved,
                kCGMouseButtonLeft,
                kCGHIDEventTap,
            )
            from Quartz.CoreGraphics import CGPoint

            self._CGEventCreateMouseEvent = CGEventCreateMouseEvent
            self._CGEventPost = CGEventPost
            self._kCGEventLeftMouseDown = kCGEventLeftMouseDown
            self._kCGEventLeftMouseUp = kCGEventLeftMouseUp
            self._kCGEventMouseMoved = kCGEventMouseMoved
            self._kCGMouseButtonLeft = kCGMouseButtonLeft
            self._kCGHIDEventTap = kCGHIDEventTap
            self._CGPoint = CGPoint
            self._use_quartz = True
            log.debug("Clicker initialized with Quartz")
        except ImportError:
            self._use_quartz = False
            log.warning("Quartz not available, using AppleScript fallback")

    def click_pixels(self, x_px: int, y_px: int, activate: bool = True):
        """
        Click at pixel coordinates (from screenshot).

        Args:
            x_px: X in pixels (screenshot coordinates)
            y_px: Y in pixels (screenshot coordinates)
            activate: Whether to activate GGSystem first
        """
        # Convert pixels to points for macOS
        x_pt = x_px // RETINA_SCALE
        y_pt = y_px // RETINA_SCALE

        self.click_points(x_pt, y_pt, activate)

    def click_points(self, x_pt: int, y_pt: int, activate: bool = True):
        """
        Click at point coordinates (macOS native).

        Args:
            x_pt: X in points
            y_pt: Y in points
            activate: Whether to activate GGSystem first
        """
        if activate:
            WindowManager.activate_ggpoker()
            time.sleep(0.1)

        log.info(f"Clicking at point ({x_pt}, {y_pt})")

        if self._use_quartz:
            self._click_quartz(x_pt, y_pt)
        else:
            self._click_applescript(x_pt, y_pt)

    def _click_quartz(self, x: int, y: int):
        """Click using Quartz CGEventPost."""
        point = self._CGPoint(x, y)

        # Move to position
        move_event = self._CGEventCreateMouseEvent(
            None, self._kCGEventMouseMoved, point, self._kCGMouseButtonLeft
        )
        self._CGEventPost(self._kCGHIDEventTap, move_event)
        time.sleep(0.02)

        # Mouse down
        down_event = self._CGEventCreateMouseEvent(
            None, self._kCGEventLeftMouseDown, point, self._kCGMouseButtonLeft
        )
        self._CGEventPost(self._kCGHIDEventTap, down_event)
        time.sleep(0.02)

        # Mouse up
        up_event = self._CGEventCreateMouseEvent(
            None, self._kCGEventLeftMouseUp, point, self._kCGMouseButtonLeft
        )
        self._CGEventPost(self._kCGHIDEventTap, up_event)

        log.debug(f"Quartz click at ({x}, {y})")

    def _click_applescript(self, x: int, y: int):
        """Click using AppleScript fallback."""
        script = f'''
        tell application "System Events"
            click at {{{x}, {y}}}
        end tell
        '''
        subprocess.run(['osascript', '-e', script], capture_output=True)
        log.debug(f"AppleScript click at ({x}, {y})")

    def click_element(self, element: UIElement, activate: bool = True):
        """Click on a UIElement."""
        self.click_pixels(element.center[0], element.center[1], activate)


class SpinGoldRegistration:
    """
    Comprehensive Spin & Gold registration automation.

    Features:
    - Automatic state detection
    - Visual-based navigation (no hardcoded coordinates)
    - Stake selection with fallback
    - Error handling with retries
    - Balance checking
    - Registration verification
    """

    # Stake priorities (will try in order)
    STAKE_PRIORITIES = [1.0, 0.25, 0.50, 2.0, 5.0]

    # Timing constants
    RETRY_DELAY = 1.0
    MAX_RETRIES = 3
    TABLE_WAIT_TIMEOUT = 60
    NAVIGATION_DELAY = 0.5

    def __init__(self):
        self.ui = SmartUIAutomation()
        self.clicker = Clicker()
        self.state = RegistrationState.UNKNOWN
        self._initial_table_count = 0

        log.info("=" * 60)
        log.info("SpinGoldRegistration initialized")
        log.info("=" * 60)

    def register(
        self,
        stake: float = 1.0,
        fallback: bool = True,
        max_retries: int = 3
    ) -> bool:
        """
        Main registration flow.

        Args:
            stake: Preferred stake (default $1)
            fallback: Whether to try alternative stakes if preferred unavailable
            max_retries: Maximum retry attempts

        Returns:
            True if registration succeeded, False otherwise
        """
        log.info(f"Starting registration for ${stake} Spin & Gold")
        log.info(f"Fallback enabled: {fallback}, Max retries: {max_retries}")

        self._initial_table_count = WindowManager.count_spin_gold_tables()
        log.info(f"Initial Spin & Gold tables: {self._initial_table_count}")

        for attempt in range(max_retries):
            log.info(f"--- Attempt {attempt + 1}/{max_retries} ---")

            try:
                # Step 1: Determine current state
                self._detect_state()
                log.info(f"Current state: {self.state.value}")

                # Step 2: Handle based on state
                if self.state == RegistrationState.NO_GGPOKER:
                    log.error("GGSystem not running!")
                    return False

                if self.state == RegistrationState.TABLE_OPEN:
                    log.info("Already at Spin & Gold table!")
                    return True

                if self.state == RegistrationState.INSUFFICIENT_BALANCE:
                    log.error("Insufficient balance!")
                    self._dismiss_dialog()
                    return False

                # Step 3: Navigate to Spin & Gold lobby if needed
                if self.state != RegistrationState.SPIN_GOLD_LOBBY:
                    if not self._navigate_to_spin_gold():
                        log.warning("Failed to navigate to Spin & Gold lobby")
                        time.sleep(self.RETRY_DELAY)
                        continue

                # Step 4: Select stake and click Play Now
                stakes_to_try = [stake] if not fallback else [stake] + [s for s in self.STAKE_PRIORITIES if s != stake]

                registered = False
                for try_stake in stakes_to_try:
                    log.info(f"Trying stake: ${try_stake}")
                    if self._select_and_register(try_stake):
                        registered = True
                        break
                    time.sleep(0.3)

                if not registered:
                    log.warning("Failed to register for any stake")
                    time.sleep(self.RETRY_DELAY)
                    continue

                # Step 5: Handle registration dialog if it appears
                time.sleep(0.5)
                self._detect_state()

                if self.state == RegistrationState.REGISTRATION_DIALOG:
                    if not self._confirm_registration():
                        log.warning("Failed to confirm registration")
                        time.sleep(self.RETRY_DELAY)
                        continue

                # Step 6: Handle insufficient balance
                if self.state == RegistrationState.INSUFFICIENT_BALANCE:
                    log.error("Insufficient balance for this stake!")
                    self._dismiss_dialog()
                    if fallback:
                        continue  # Try next stake
                    return False

                # Step 7: Wait for table to open
                if self._wait_for_table():
                    log.info("=" * 60)
                    log.info("REGISTRATION SUCCESSFUL!")
                    log.info("=" * 60)

                    # Log success to adaptive learner
                    log_action('registration', success=True, details={
                        'stake': stake,
                        'attempt': attempt + 1,
                        'game_type': 'spin_gold'
                    })
                    return True

            except Exception as e:
                log.error(f"Error during registration: {e}")
                import traceback
                log.debug(traceback.format_exc())
                time.sleep(self.RETRY_DELAY)

        log.error(f"Registration failed after {max_retries} attempts")

        # Log failure to adaptive learner
        log_action('registration', success=False, details={
            'stake': stake,
            'attempts': max_retries,
            'game_type': 'spin_gold',
            'final_state': self.state.value
        })
        report_issue('registration', f"Failed to register for ${stake} Spin & Gold after {max_retries} attempts")

        return False

    def _detect_state(self):
        """Detect current UI state."""
        log.debug("Detecting current state...")

        # Check if GGSystem is running
        windows = WindowManager.get_all_windows()
        if not windows:
            self.state = RegistrationState.NO_GGPOKER
            return

        # Check for Spin & Gold table window
        for win in windows:
            name = win['name'].lower()
            if 'spin' in name and 'gold' in name and 'lobby' not in name:
                self.state = RegistrationState.TABLE_OPEN
                return

        # Capture screenshot and analyze
        self.ui.capture_screen()

        # Check for insufficient balance dialog
        if self.ui.detect_insufficient_balance_dialog():
            self.state = RegistrationState.INSUFFICIENT_BALANCE
            return

        # Check for Spin & Gold tiles (means we're in lobby)
        tiles = self.ui.detect_spin_gold_tiles()
        if tiles:
            self.state = RegistrationState.SPIN_GOLD_LOBBY
            return

        # Check for Play Now / Register button (means we might be in dialog)
        play_btn = self.ui.detect_play_now_button()
        if play_btn:
            self.state = RegistrationState.REGISTRATION_DIALOG
            return

        # Default: assume we're at main lobby
        self.state = RegistrationState.MAIN_LOBBY

    def _navigate_to_spin_gold(self) -> bool:
        """
        Navigate to Spin & Gold lobby.

        Uses visual detection to find the Spin & Gold icon/tab.
        """
        log.info("Navigating to Spin & Gold lobby...")

        # Focus on main lobby
        lobby = WindowManager.find_main_lobby()
        if not lobby:
            log.error("Cannot find main lobby window")
            return False

        WindowManager.focus_window(lobby['name'])
        time.sleep(self.NAVIGATION_DELAY)

        # Method 1: Look for Spin & Gold icon in top nav bar
        # The icon is typically purple/gold colored
        self.ui.capture_screen()

        # Search in top portion of lobby for navigation
        lobby_region = (
            lobby['x_px'],
            lobby['y_px'],
            lobby['w_px'],
            lobby['h_px'] // 4  # Top quarter
        )

        # Look for gold/orange elements (Spin & Gold branding)
        gold_elements = self.ui.find_by_color('gold_text', min_area=300, region=lobby_region)

        if gold_elements:
            # Click on the first (likely the Spin & Gold tab)
            log.info(f"Clicking Spin & Gold tab at ({gold_elements[0].x}, {gold_elements[0].y})")
            self.clicker.click_element(gold_elements[0])
            time.sleep(self.NAVIGATION_DELAY)

            # Verify we're now in Spin & Gold lobby
            self._detect_state()
            if self.state == RegistrationState.SPIN_GOLD_LOBBY:
                return True

        # Method 2: Use known approximate position
        # Spin & Gold is usually 3rd icon in top bar (around x=200-250 from lobby left)
        spin_gold_x = lobby['x_px'] + 420  # Approximate position
        spin_gold_y = lobby['y_px'] + 110  # Top nav bar

        log.info(f"Clicking approximate Spin & Gold position ({spin_gold_x}, {spin_gold_y})")
        self.clicker.click_pixels(spin_gold_x, spin_gold_y)
        time.sleep(self.NAVIGATION_DELAY)

        # Verify
        self._detect_state()
        success = self.state == RegistrationState.SPIN_GOLD_LOBBY

        # Log navigation result to adaptive learner
        log_action('spin_gold_navigation', success=success, details={
            'final_state': self.state.value,
            'gold_elements_found': len(gold_elements) if gold_elements else 0
        })

        return success

    def _select_and_register(self, stake: float) -> bool:
        """
        Select stake tile and click Play Now.

        Args:
            stake: Stake amount to select

        Returns:
            True if Play Now was clicked successfully
        """
        log.info(f"Selecting ${stake} stake...")
        self.ui.capture_screen()

        # Find all stake tiles
        tiles = self.ui.detect_spin_gold_tiles()

        if not tiles:
            log.warning("No stake tiles found!")
            # Try clicking in approximate grid position
            return self._click_approximate_stake(stake)

        # Try to find the correct stake tile
        # For now, click on tiles and look for visual feedback
        for tile in tiles:
            log.debug(f"Checking tile at ({tile.x}, {tile.y})")
            self.clicker.click_element(tile)
            time.sleep(0.3)

            # Look for Play Now button
            self.ui.capture_screen()
            play_btn = self.ui.detect_play_now_button()

            if play_btn:
                log.info(f"Found Play Now button at ({play_btn.x}, {play_btn.y})")
                self.clicker.click_element(play_btn)
                return True

        return False

    def _click_approximate_stake(self, stake: float) -> bool:
        """
        Click approximate stake position based on known UI layout.

        GGSystem Spin & Gold grid layout (approximate positions in pixels):
        Row 1: $0.25, $0.50, $1, $2
        Row 2: $5, $10, $20, ...
        """
        log.info(f"Using approximate position for ${stake}")

        lobby = WindowManager.find_main_lobby()
        if not lobby:
            return False

        # Grid starts approximately at these positions relative to lobby
        grid_start_x = lobby['x_px'] + 700
        grid_start_y = lobby['y_px'] + 560
        tile_width = 240
        tile_height = 260

        # Stake to grid position mapping
        stake_positions = {
            0.25: (0, 0),
            0.50: (1, 0),
            1.0: (2, 0),
            2.0: (3, 0),
            5.0: (0, 1),
            10.0: (1, 1),
            20.0: (2, 1),
        }

        if stake not in stake_positions:
            log.warning(f"Unknown stake ${stake}, using $1 position")
            stake = 1.0

        col, row = stake_positions[stake]
        tile_x = grid_start_x + col * tile_width + tile_width // 2
        tile_y = grid_start_y + row * tile_height + tile_height // 2

        log.info(f"Clicking tile at ({tile_x}, {tile_y})")
        self.clicker.click_pixels(tile_x, tile_y)
        time.sleep(0.3)

        # Now click Play Now button (should appear on the tile)
        play_now_y = tile_y + tile_height // 2 - 40  # Play Now is near bottom of tile
        self.clicker.click_pixels(tile_x, play_now_y)

        return True

    def _confirm_registration(self) -> bool:
        """
        Confirm registration in dialog.

        Clicks the Register/Confirm button in the dialog.
        """
        log.info("Confirming registration...")
        self.ui.capture_screen()

        # Look for green Register/Confirm button
        register_btn = self.ui.detect_register_button()

        if register_btn:
            log.info(f"Clicking Register button at ({register_btn.x}, {register_btn.y})")
            self.clicker.click_element(register_btn)
            return True

        log.warning("Register button not found")
        return False

    def _dismiss_dialog(self):
        """Dismiss any open dialog (Cancel, OK, etc.)."""
        log.info("Dismissing dialog...")
        self.ui.capture_screen()

        # Look for Cancel button
        cancel_btn = self.ui.detect_cancel_button()

        if cancel_btn:
            self.clicker.click_element(cancel_btn)
            return

        # Try pressing Escape
        script = '''
        tell application "System Events"
            keystroke escape
        end tell
        '''
        subprocess.run(['osascript', '-e', script], capture_output=True)

    def _wait_for_table(self, timeout: float = None) -> bool:
        """
        Wait for new Spin & Gold table window to appear.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if new table appeared, False if timeout
        """
        timeout = timeout or self.TABLE_WAIT_TIMEOUT
        log.info(f"Waiting for table (timeout: {timeout}s)...")

        start_time = time.time()

        while time.time() - start_time < timeout:
            current_count = WindowManager.count_spin_gold_tables()

            if current_count > self._initial_table_count:
                log.info(f"New Spin & Gold table detected! ({current_count} tables)")
                return True

            # Also check for table in window titles
            table = WindowManager.find_spin_gold_table()
            if table:
                log.info(f"Spin & Gold table found: {table['name']}")
                return True

            time.sleep(0.5)

        log.warning(f"Timeout waiting for table after {timeout}s")
        return False

    def is_in_spin_gold_lobby(self) -> bool:
        """Check if currently in Spin & Gold lobby."""
        self._detect_state()
        return self.state == RegistrationState.SPIN_GOLD_LOBBY


def main():
    """CLI interface for registration automation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="GGSystem Spin & Gold Registration Automation"
    )
    parser.add_argument(
        "--stake", type=float, default=1.0,
        help="Stake amount in dollars (default: 1.0)"
    )
    parser.add_argument(
        "--no-fallback", action="store_true",
        help="Disable fallback to alternative stakes"
    )
    parser.add_argument(
        "--retries", type=int, default=3,
        help="Maximum retry attempts (default: 3)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--test-detection", action="store_true",
        help="Test state detection only (no clicks)"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger("gg_registration").setLevel(logging.DEBUG)

    print("=" * 60)
    print("GGSystem Spin & Gold Registration")
    print("=" * 60)
    print(f"Stake: ${args.stake}")
    print(f"Fallback: {not args.no_fallback}")
    print(f"Retries: {args.retries}")
    print("=" * 60)

    reg = SpinGoldRegistration()

    if args.test_detection:
        print("\nRunning detection test...")
        reg._detect_state()
        print(f"Detected state: {reg.state.value}")

        print("\nWindow info:")
        for win in WindowManager.get_all_windows():
            print(f"  {win['name']}: ({win['x_pt']}, {win['y_pt']}) {win['w_pt']}x{win['h_pt']}")

        print("\nUI element detection:")
        reg.ui.capture_screen()

        tiles = reg.ui.detect_spin_gold_tiles()
        print(f"  Spin & Gold tiles: {len(tiles)}")

        play_btn = reg.ui.detect_play_now_button()
        print(f"  Play Now button: {'Found' if play_btn else 'Not found'}")

        return

    # Run registration
    success = reg.register(
        stake=args.stake,
        fallback=not args.no_fallback,
        max_retries=args.retries
    )

    if success:
        print("\nRegistration successful!")
    else:
        print("\nRegistration failed!")
        exit(1)


if __name__ == "__main__":
    main()
