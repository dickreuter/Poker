"""
UI Navigator - Full UI Navigation with OCR for GGSystem

This module handles all UI navigation tasks:
1. Finding and clicking the lobby
2. Navigating to game types (Spin & Gold, Rush & Cash, etc.)
3. Registering for new tables
4. Handling popups, errors, and confirmations
5. Visual verification of UI state

Uses OCR and visual detection instead of hardcoded coordinates.

Usage:
    from sys_core.tools.ui_navigator import UINavigator

    nav = UINavigator()
    nav.navigate_to_spin_gold()
    nav.register_new_table()

Author: Claude (2026-01-04)
"""

import logging
import subprocess
import time
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

import cv2
import numpy as np
from PIL import Image, ImageGrab
from pynput.mouse import Button as MouseButton, Controller as MouseController

# Import adaptive learner for self-improving thresholds
try:
    from sys_core.tools.adaptive_learner import AdaptiveLearner
    ADAPTIVE_AVAILABLE = True
except ImportError:
    ADAPTIVE_AVAILABLE = False

log = logging.getLogger(__name__)

RETINA_SCALE = 2


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class UIElement:
    """Represents a detected UI element."""
    element_type: str  # 'button', 'text', 'tile', 'popup'
    text: str
    x_px: int  # Position in screen pixels
    y_px: int
    width: int
    height: int
    confidence: float

    @property
    def center_pt(self) -> Tuple[int, int]:
        """Get center point for clicking."""
        return (
            (self.x_px + self.width // 2) // RETINA_SCALE,
            (self.y_px + self.height // 2) // RETINA_SCALE
        )


@dataclass
class LobbyWindow:
    """Represents the GGPoker lobby window."""
    name: str
    x_pt: int
    y_pt: int
    w_pt: int
    h_pt: int

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


# =============================================================================
# OCR ENGINE
# =============================================================================

class OCREngine:
    """OCR engine for reading text from screenshots."""

    def __init__(self):
        self._tesseract_available = self._check_tesseract()

    def _check_tesseract(self) -> bool:
        """Check if Tesseract OCR is available."""
        try:
            result = subprocess.run(
                ['tesseract', '--version'],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def read_text(self, image: Image.Image, config: str = '') -> str:
        """
        Read text from an image using Tesseract.

        Args:
            image: PIL Image to read from
            config: Tesseract configuration string

        Returns:
            Extracted text or empty string
        """
        if not self._tesseract_available:
            return self._fallback_read(image)

        try:
            import pytesseract
            text = pytesseract.image_to_string(image, config=config)
            return text.strip()
        except Exception as e:
            log.debug(f"Tesseract error: {e}")
            return self._fallback_read(image)

    def read_text_with_boxes(self, image: Image.Image) -> List[Dict]:
        """
        Read text with bounding boxes.

        Returns:
            List of dicts with 'text', 'x', 'y', 'w', 'h', 'conf'
        """
        if not self._tesseract_available:
            return []

        try:
            import pytesseract

            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

            results = []
            for i, text in enumerate(data['text']):
                if text.strip() and data['conf'][i] > 30:
                    results.append({
                        'text': text.strip(),
                        'x': data['left'][i],
                        'y': data['top'][i],
                        'w': data['width'][i],
                        'h': data['height'][i],
                        'conf': data['conf'][i]
                    })

            return results

        except Exception as e:
            log.debug(f"Tesseract box detection error: {e}")
            return []

    def _fallback_read(self, image: Image.Image) -> str:
        """Fallback text detection using OpenCV."""
        # This is a simple fallback - won't give actual text
        # but can detect text regions
        return ""

    def find_text_region(self, image: Image.Image, target_text: str) -> Optional[Tuple[int, int, int, int]]:
        """
        Find region containing specific text.

        Args:
            image: Image to search
            target_text: Text to find (case-insensitive partial match)

        Returns:
            (x, y, w, h) of region or None
        """
        boxes = self.read_text_with_boxes(image)

        target_lower = target_text.lower()

        for box in boxes:
            if target_lower in box['text'].lower():
                return (box['x'], box['y'], box['w'], box['h'])

        # Try combining adjacent boxes for multi-word matches
        for i, box1 in enumerate(boxes):
            for box2 in boxes[i+1:]:
                combined = f"{box1['text']} {box2['text']}".lower()
                if target_lower in combined:
                    x = min(box1['x'], box2['x'])
                    y = min(box1['y'], box2['y'])
                    w = max(box1['x'] + box1['w'], box2['x'] + box2['w']) - x
                    h = max(box1['y'] + box1['h'], box2['y'] + box2['h']) - y
                    return (x, y, w, h)

        return None


# =============================================================================
# VISUAL MATCHER
# =============================================================================

class VisualMatcher:
    """Visual pattern matching for UI elements."""

    # Known UI element colors
    COLORS = {
        'green_button': {
            'lower': np.array([35, 80, 80]),
            'upper': np.array([85, 255, 255])
        },
        'orange_button': {
            'lower': np.array([8, 100, 100]),
            'upper': np.array([28, 255, 255])
        },
        'gold_tile': {
            'lower': np.array([15, 100, 100]),
            'upper': np.array([35, 255, 255])
        },
        'red_close': {
            'lower': np.array([0, 150, 150]),
            'upper': np.array([10, 255, 255])
        }
    }

    def find_colored_buttons(self, image: Image.Image, color_type: str) -> List[Tuple[int, int, int, int]]:
        """
        Find buttons by color.

        Args:
            image: Image to search
            color_type: One of 'green_button', 'orange_button', etc.

        Returns:
            List of (x, y, w, h) bounding boxes
        """
        if color_type not in self.COLORS:
            return []

        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        color_info = self.COLORS[color_type]
        mask = cv2.inRange(hsv, color_info['lower'], color_info['upper'])

        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        buttons = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 1000:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            aspect = w / h if h > 0 else 0

            # Buttons are typically wider than tall
            if aspect > 1.0 and w > 50:
                buttons.append((x, y, w, h))

        return buttons

    def find_tile_by_color(self, image: Image.Image, dominant_hue_range: Tuple[int, int]) -> Optional[Tuple[int, int, int, int]]:
        """
        Find a game tile by its dominant color.

        Args:
            image: Image to search
            dominant_hue_range: (min_hue, max_hue) in HSV

        Returns:
            (x, y, w, h) or None
        """
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        lower = np.array([dominant_hue_range[0], 50, 50])
        upper = np.array([dominant_hue_range[1], 255, 255])
        mask = cv2.inRange(hsv, lower, upper)

        kernel = np.ones((10, 10), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Find largest region
        if contours:
            largest = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            if area > 5000:  # Minimum size for a tile
                return cv2.boundingRect(largest)

        return None


# =============================================================================
# UI NAVIGATOR
# =============================================================================

class UINavigator:
    """Main UI navigation controller with click verification and adaptive learning."""

    def __init__(self):
        self.mouse = MouseController()
        self.ocr = OCREngine()
        self.visual = VisualMatcher()
        self.lobby: Optional[LobbyWindow] = None

        # Initialize adaptive learner for self-improving behavior
        if ADAPTIVE_AVAILABLE:
            self.learner = AdaptiveLearner()
            log.info("UINavigator: Adaptive learner enabled")
        else:
            self.learner = None
            log.debug("UINavigator: Adaptive learner not available")

    def _find_lobby_window(self) -> Optional[LobbyWindow]:
        """Find the GGPoker lobby window."""
        script = '''
        tell application "System Events"
            if not (exists process "GGnet") then return ""
            tell process "GGnet"
                repeat with w in windows
                    set winName to name of w as text
                    if winName contains "GGPoker" or winName contains "Lobby" then
                        set winPos to position of w
                        set winSize to size of w
                        return winName & "###" & (item 1 of winPos) & "," & (item 2 of winPos) & "," & (item 1 of winSize) & "," & (item 2 of winSize)
                    end if
                end repeat
            end tell
        end tell
        return ""
        '''

        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=5
            )

            output = result.stdout.strip()
            if output and '###' in output:
                name, coords = output.split('###')
                coords = coords.replace('−', '-').replace('–', '-')
                parts = coords.split(',')

                self.lobby = LobbyWindow(
                    name=name.strip(),
                    x_pt=int(parts[0]),
                    y_pt=int(parts[1]),
                    w_pt=int(parts[2]),
                    h_pt=int(parts[3])
                )
                log.info(f"Found lobby: {self.lobby.name} at ({self.lobby.x_pt}, {self.lobby.y_pt})")
                return self.lobby

        except Exception as e:
            log.error(f"Error finding lobby: {e}")

        return None

    def _focus_ggpoker(self):
        """Bring GGSystem to front."""
        script = 'tell application "System Events" to tell process "GGnet" to set frontmost to true'
        try:
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=2)
        except:
            pass

    def _click_at(self, x_pt: int, y_pt: int, verify_delay: float = 0.3,
                   verify: bool = True, action_name: str = "click"):
        """
        Click at screen point coordinates with verification.

        Args:
            x_pt, y_pt: Screen point coordinates
            verify_delay: Time to wait before verification
            verify: If True, take before/after screenshots to verify change
            action_name: Name of action for logging
        """
        # Take BEFORE screenshot if verifying
        before_screenshot = None
        if verify:
            before_screenshot = ImageGrab.grab()

        self._focus_ggpoker()
        time.sleep(0.05)

        self.mouse.position = (x_pt, y_pt)
        time.sleep(0.03)
        self.mouse.click(MouseButton.left)

        log.debug(f"Clicked {action_name} at ({x_pt}, {y_pt})")
        time.sleep(verify_delay)

        # Verify click worked by comparing screenshots
        if verify and before_screenshot:
            after_screenshot = ImageGrab.grab()
            verified = self._verify_click(before_screenshot, after_screenshot, x_pt, y_pt)

            # Log to adaptive learner
            if ADAPTIVE_AVAILABLE and hasattr(self, 'learner'):
                self.learner.log_action(f'ui_click_{action_name}',
                                       success=verified,
                                       details={'x': x_pt, 'y': y_pt})

            if not verified:
                log.warning(f"Click verification FAILED for {action_name} at ({x_pt}, {y_pt})")
            else:
                log.info(f"Click verified: {action_name}")

            return verified
        return True

    def _verify_click(self, before: Image.Image, after: Image.Image,
                     click_x: int, click_y: int) -> bool:
        """
        Verify a click caused a UI change.

        Compares before/after screenshots around the click area.
        Returns True if significant change detected.
        """
        # Convert to arrays
        before_arr = np.array(before)
        after_arr = np.array(after)

        # Define region around click (in pixels, account for retina)
        region_size = 200  # pixels
        px_x = click_x * RETINA_SCALE
        px_y = click_y * RETINA_SCALE

        x1 = max(0, px_x - region_size)
        y1 = max(0, px_y - region_size)
        x2 = min(before_arr.shape[1], px_x + region_size)
        y2 = min(before_arr.shape[0], px_y + region_size)

        # Extract regions
        before_region = before_arr[y1:y2, x1:x2]
        after_region = after_arr[y1:y2, x1:x2]

        # Calculate difference
        diff = cv2.absdiff(before_region, after_region)
        diff_gray = cv2.cvtColor(diff, cv2.COLOR_RGB2GRAY)
        changed_pixels = np.sum(diff_gray > 30)  # Pixels that changed significantly
        total_pixels = diff_gray.size

        change_ratio = changed_pixels / total_pixels if total_pixels > 0 else 0

        log.debug(f"Click verification: {change_ratio*100:.1f}% pixels changed")

        # Consider verified if >5% of region changed
        return change_ratio > 0.05

    def _capture_lobby(self) -> Optional[Image.Image]:
        """Capture the lobby window."""
        if not self.lobby:
            if not self._find_lobby_window():
                return None

        screenshot = ImageGrab.grab()
        return screenshot.crop((
            self.lobby.x_px,
            self.lobby.y_px,
            self.lobby.x_px + self.lobby.w_px,
            self.lobby.y_px + self.lobby.h_px
        ))

    def find_and_click_text(self, target_text: str, timeout: float = 10,
                            verify: bool = True, retry_on_fail: bool = True) -> bool:
        """
        Find text on screen using OCR and click it with verification.

        Works with ANY size buttons - uses OCR to find text wherever it appears.

        Args:
            target_text: Text to find and click (e.g., "Play Now", "Fold", "Call")
            timeout: Maximum time to search
            verify: If True, verify the click caused a UI change
            retry_on_fail: If True, retry click if verification fails

        Returns:
            True if found, clicked, and verified
        """
        start = time.time()
        attempts = 0
        max_attempts = 3 if retry_on_fail else 1

        while time.time() - start < timeout and attempts < max_attempts:
            # Search full screen if no lobby, otherwise search lobby
            if self.lobby:
                search_img = self._capture_lobby()
                offset_x_pt = self.lobby.x_pt
                offset_y_pt = self.lobby.y_pt
            else:
                search_img = ImageGrab.grab()
                offset_x_pt = 0
                offset_y_pt = 0

            if search_img is None:
                time.sleep(0.5)
                continue

            region = self.ocr.find_text_region(search_img, target_text)
            if region:
                x, y, w, h = region
                # Convert to screen coordinates (NO size filtering - any size works)
                click_x = offset_x_pt + (x + w // 2) // RETINA_SCALE
                click_y = offset_y_pt + (y + h // 2) // RETINA_SCALE

                # Click with verification
                verified = self._click_at(click_x, click_y, verify=verify,
                                         action_name=f"text_{target_text}")

                if verified or not verify:
                    log.info(f"Successfully clicked '{target_text}' at ({click_x}, {click_y})")
                    return True
                else:
                    attempts += 1
                    log.warning(f"Click on '{target_text}' not verified, attempt {attempts}/{max_attempts}")
                    time.sleep(0.3)
                    continue

            time.sleep(0.5)

        log.warning(f"Could not find or click text: {target_text}")
        return False

    def find_and_click_button(self, color_type: str, position_hint: str = None,
                               verify: bool = True, retry_on_fail: bool = True) -> bool:
        """
        Find a colored button and click it with verification.

        Works with ANY size buttons - no minimum/maximum size constraints.

        Args:
            color_type: 'green_button', 'orange_button', etc.
            position_hint: 'top', 'bottom', 'center' to filter by position
            verify: If True, verify the click caused a UI change
            retry_on_fail: If True, retry click if verification fails

        Returns:
            True if found, clicked, and verified
        """
        attempts = 0
        max_attempts = 3 if retry_on_fail else 1

        while attempts < max_attempts:
            lobby_img = self._capture_lobby()
            if lobby_img is None:
                return False

            buttons = self.visual.find_colored_buttons(lobby_img, color_type)

            if not buttons:
                log.debug(f"No {color_type} buttons found")
                return False

            # Filter by position hint (uses relative positions - works any size)
            if position_hint and buttons:
                img_h = lobby_img.height
                if position_hint == 'top':
                    buttons = [b for b in buttons if b[1] < img_h * 0.3]
                elif position_hint == 'bottom':
                    buttons = [b for b in buttons if b[1] > img_h * 0.7]
                elif position_hint == 'center':
                    buttons = [b for b in buttons if img_h * 0.3 <= b[1] <= img_h * 0.7]

            if not buttons:
                return False

            # Click the largest button (works for any size)
            button = max(buttons, key=lambda b: b[2] * b[3])
            x, y, w, h = button

            click_x = self.lobby.x_pt + (x + w // 2) // RETINA_SCALE
            click_y = self.lobby.y_pt + (y + h // 2) // RETINA_SCALE

            # Click with verification
            verified = self._click_at(click_x, click_y, verify=verify,
                                     action_name=f"button_{color_type}")

            if verified or not verify:
                log.info(f"Successfully clicked {color_type} at ({click_x}, {click_y})")
                return True
            else:
                attempts += 1
                log.warning(f"Click on {color_type} not verified, attempt {attempts}/{max_attempts}")
                time.sleep(0.3)
                continue

        return False

    def navigate_to_spin_gold(self) -> bool:
        """
        Navigate to Spin & Gold game selection.

        Returns:
            True if successfully navigated
        """
        log.info("Navigating to Spin & Gold...")

        # First, find and click the Spin & Gold tile
        # The tile typically has golden/orange coloring
        lobby_img = self._capture_lobby()
        if lobby_img is None:
            return False

        # Try finding by text first
        if self.find_and_click_text("Spin & Gold"):
            time.sleep(1)
            return True

        if self.find_and_click_text("Spin"):
            time.sleep(1)
            return True

        # Try finding by color (gold tiles)
        tile = self.visual.find_tile_by_color(lobby_img, (15, 35))  # Gold hue range
        if tile:
            x, y, w, h = tile
            click_x = self.lobby.x_pt + (x + w // 2) // RETINA_SCALE
            click_y = self.lobby.y_pt + (y + h // 2) // RETINA_SCALE
            self._click_at(click_x, click_y)
            log.info("Clicked Spin & Gold tile by color")
            time.sleep(1)
            return True

        log.warning("Could not find Spin & Gold")
        return False

    def register_new_table(self, stake_level: str = None) -> bool:
        """
        Register for a new Spin & Gold table.

        Args:
            stake_level: Optional stake level like "$1", "$5", etc.

        Returns:
            True if registration started
        """
        log.info("Registering for new table...")

        # If stake level specified, try to find and click it
        if stake_level:
            if self.find_and_click_text(stake_level):
                time.sleep(0.5)

        # Look for "Play Now" or "Register" button
        if self.find_and_click_text("Play Now"):
            log.info("Clicked 'Play Now'")
            time.sleep(0.5)
            return True

        if self.find_and_click_text("Register"):
            log.info("Clicked 'Register'")
            time.sleep(0.5)
            return True

        # Try finding green button (Play Now is usually green)
        if self.find_and_click_button('green_button', 'bottom'):
            log.info("Clicked green button (likely Play Now)")
            return True

        log.warning("Could not find registration button")
        return False

    def close_popup(self) -> bool:
        """
        Close any popup/dialog that might be open.

        Returns:
            True if popup was closed
        """
        lobby_img = self._capture_lobby()
        if lobby_img is None:
            return False

        # Look for X button or close button
        # X buttons are often in top-right with specific appearance

        # Try finding "OK", "Close", "Cancel" text
        for text in ['OK', 'Close', 'Cancel', 'Got it', 'X']:
            if self.find_and_click_text(text):
                log.info(f"Closed popup by clicking '{text}'")
                return True

        # Try finding red close button
        if self.find_and_click_button('red_close', 'top'):
            log.info("Closed popup via red X button")
            return True

        return False

    def wait_for_table(self, timeout: float = 30) -> bool:
        """
        Wait for a new table to open.

        Args:
            timeout: Maximum time to wait

        Returns:
            True if new table appeared
        """
        log.info(f"Waiting up to {timeout}s for new table...")

        start = time.time()
        initial_windows = self._count_poker_tables()

        while time.time() - start < timeout:
            current_windows = self._count_poker_tables()
            if current_windows > initial_windows:
                log.info(f"New table appeared! ({initial_windows} -> {current_windows})")
                return True
            time.sleep(1)

        log.warning("Timeout waiting for new table")
        return False

    def _count_poker_tables(self) -> int:
        """Count current poker table windows."""
        script = '''
        tell application "System Events"
            if not (exists process "GGnet") then return "0"
            tell process "GGnet"
                set count_ to 0
                repeat with w in windows
                    set winName to name of w as text
                    if winName contains "Spin" or winName contains "Gold" or winName contains "Rush" or winName contains "Cash" or winName contains "Hold" or winName contains "NL" then
                        set count_ to count_ + 1
                    end if
                end repeat
                return count_ as text
            end tell
        end tell
        '''

        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=5
            )
            return int(result.stdout.strip())
        except:
            return 0

    def ensure_tables_open(self, target_count: int = 1, max_attempts: int = 3) -> int:
        """
        Ensure at least target_count tables are open.

        Args:
            target_count: Desired number of tables
            max_attempts: Maximum registration attempts

        Returns:
            Number of tables currently open
        """
        current = self._count_poker_tables()
        log.info(f"Currently {current} tables open, target is {target_count}")

        attempts = 0
        while current < target_count and attempts < max_attempts:
            attempts += 1

            # Navigate to Spin & Gold
            if not self.navigate_to_spin_gold():
                time.sleep(1)
                continue

            # Register
            if not self.register_new_table():
                time.sleep(1)
                continue

            # Wait for table
            if self.wait_for_table(timeout=15):
                current = self._count_poker_tables()
                log.info(f"Now have {current} tables")
            else:
                # Maybe there was a popup
                self.close_popup()

        return current

    def full_startup_sequence(self, target_tables: int = 1) -> bool:
        """
        Full startup: find lobby, navigate, and register for tables.

        Args:
            target_tables: Number of tables to register for

        Returns:
            True if at least one table is running
        """
        log.info(f"Starting full sequence for {target_tables} tables...")

        # Find lobby
        if not self._find_lobby_window():
            log.error("GGPoker lobby not found!")
            return False

        # Ensure GGSystem is focused
        self._focus_ggpoker()
        time.sleep(0.5)

        # Open tables
        final_count = self.ensure_tables_open(target_tables)

        success = final_count > 0
        if success:
            log.info(f"Startup complete with {final_count} tables")
        else:
            log.error("Failed to open any tables")

        return success


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Test UI navigator."""
    import argparse

    parser = argparse.ArgumentParser(description="UI Navigator Test")
    parser.add_argument("--action", choices=["test", "spin", "register", "startup"],
                       default="test", help="Action to perform")
    parser.add_argument("--tables", type=int, default=1, help="Target table count")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    nav = UINavigator()

    if args.action == "test":
        print("Finding lobby...")
        lobby = nav._find_lobby_window()
        if lobby:
            print(f"Found: {lobby.name} at ({lobby.x_pt}, {lobby.y_pt})")
            print(f"Tables open: {nav._count_poker_tables()}")
        else:
            print("Lobby not found")

    elif args.action == "spin":
        if nav.navigate_to_spin_gold():
            print("Successfully navigated to Spin & Gold")
        else:
            print("Failed to navigate")

    elif args.action == "register":
        if nav.register_new_table():
            print("Registration started")
            if nav.wait_for_table():
                print("New table opened!")
        else:
            print("Failed to register")

    elif args.action == "startup":
        if nav.full_startup_sequence(args.tables):
            print(f"Startup complete with {nav._count_poker_tables()} tables")
        else:
            print("Startup failed")


if __name__ == "__main__":
    main()
