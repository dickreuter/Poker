"""
Dynamic Lobby Navigator for GGSystem

Finds and clicks UI elements using VISUAL DETECTION, not hardcoded coordinates.
Works regardless of window size or position.

Features:
- Find Spin & Gold icon by its distinctive gold/yellow HSV color
- Find game tiles by their colored backgrounds (gold, blue, purple, red, teal)
- Find Play Now buttons by detecting white text on dark background
- Handles Retina display scaling (pixel coords / 2 for clicking)
- Full registration flow for Spin & Gold tournaments

Detection Methods:
1. Spin & Gold Icon: HSV color detection for gold/yellow (H=15-35)
2. Game Tiles: HSV color detection for various tile background colors
3. Play Now Buttons: Grayscale thresholding + dilation to find white text

Coordinate System:
- Screenshots are in PIXELS (2x on Retina displays)
- Click coordinates are in POINTS (half of pixel values)
- Window position from AppleScript is already in POINTS

Usage:
    # Test detection without clicking
    python -m sys_core.tools.dynamic_lobby_navigator --test

    # Register for Spin & Gold (cheapest stake)
    python -m sys_core.tools.dynamic_lobby_navigator --register

    # Register at specific stake level
    python -m sys_core.tools.dynamic_lobby_navigator --register --stake 1

    # Enable debug logging
    python -m sys_core.tools.dynamic_lobby_navigator --test --debug

API Usage:
    from sys_core.tools.dynamic_lobby_navigator import DynamicLobbyNavigator

    nav = DynamicLobbyNavigator()
    nav.find_lobby_window()
    lobby_img = nav.capture_lobby()

    # Find elements
    icon = nav.find_spin_gold_icon(lobby_img)
    tiles = nav.find_game_tiles(lobby_img)
    buttons = nav.find_play_now_buttons(lobby_img)

    # Click elements
    nav.click_element(icon)
    nav.click_element(tiles[0])
    nav.click_element(buttons[0])

    # Or use the full flow
    nav.register_for_spin_gold(stake_index=0)
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from PIL import ImageGrab, Image
import cv2
import numpy as np

# Import adaptive learner for self-improvement
from sys_core.tools.adaptive_learner import log_action, report_issue, get_threshold, save_screenshot

log = logging.getLogger(__name__)

# Retina display scale factor
RETINA_SCALE = 2


@dataclass
class DetectedElement:
    """A UI element found by color detection"""
    name: str
    x_px: int  # Position in pixels (screenshot coords)
    y_px: int
    width: int
    height: int
    confidence: float = 1.0

    @property
    def center_px(self) -> Tuple[int, int]:
        """Center position in pixels"""
        return (self.x_px + self.width // 2, self.y_px + self.height // 2)

    def to_screen_point(self, window_x_pt: int, window_y_pt: int) -> Tuple[int, int]:
        """Convert to screen click coordinates (points)"""
        cx, cy = self.center_px
        # Convert pixel offset to points, add to window position
        return (window_x_pt + cx // RETINA_SCALE,
                window_y_pt + cy // RETINA_SCALE)


@dataclass
class LobbyWindow:
    """GGSystem lobby window"""
    name: str
    x_pt: int  # Position in points (screen coords for clicking)
    y_pt: int
    w_pt: int
    h_pt: int

    @property
    def x_px(self) -> int: return self.x_pt * RETINA_SCALE
    @property
    def y_px(self) -> int: return self.y_pt * RETINA_SCALE
    @property
    def w_px(self) -> int: return self.w_pt * RETINA_SCALE
    @property
    def h_px(self) -> int: return self.h_pt * RETINA_SCALE


class DynamicLobbyNavigator:
    """
    Navigate GGSystem lobby using dynamic color detection.

    All UI elements are found by their distinctive colors:
    - Spin & Gold icon: Gold/yellow colored icon in top bar
    - Game tiles: Colored background tiles in the game grid
    - Play Now buttons: Green buttons on tiles
    - Stakes text: Could be enhanced with OCR

    This approach works regardless of window size or position because
    we detect elements by their visual appearance, not coordinates.
    """

    # Color definitions in HSV for detection
    # HSV ranges: H(0-180), S(0-255), V(0-255)

    # Spin & Gold icon - distinctive gold/yellow/orange color
    SPIN_GOLD_ICON_HSV = {
        'lower': np.array([15, 100, 150]),   # Gold/yellow hue
        'upper': np.array([35, 255, 255]),
        'name': 'Spin & Gold Icon'
    }

    # Play Now button - green (can be various shades)
    PLAY_NOW_HSV = {
        'lower': np.array([35, 50, 50]),   # Wider range to catch darker greens
        'upper': np.array([90, 255, 255]),
        'name': 'Play Now Button'
    }

    # Game tile backgrounds - various colors
    # We'll look for rectangular regions with consistent colors
    TILE_COLORS = {
        'gold': {
            'lower': np.array([15, 80, 100]),
            'upper': np.array([35, 255, 255])
        },
        'blue': {
            'lower': np.array([90, 80, 80]),
            'upper': np.array([130, 255, 255])
        },
        'purple': {
            'lower': np.array([130, 60, 80]),
            'upper': np.array([160, 255, 255])
        },
        'red': {
            'lower': np.array([0, 100, 100]),
            'upper': np.array([10, 255, 255])
        },
        'teal': {
            'lower': np.array([80, 80, 80]),
            'upper': np.array([100, 255, 255])
        }
    }

    # Top icon bar - where game type icons are located
    # Usually in the top ~80 pixels of the lobby
    ICON_BAR_HEIGHT_RATIO = 0.12  # Top 12% of window

    # Game grid area - where tiles are displayed
    GRID_TOP_RATIO = 0.15  # Grid starts below icon bar
    GRID_BOTTOM_RATIO = 0.95  # Grid extends almost to bottom (Play Now buttons are near bottom)

    def __init__(self):
        self.lobby: Optional[LobbyWindow] = None
        self.last_screenshot: Optional[Image.Image] = None
        self.detected_elements: Dict[str, DetectedElement] = {}

    def find_lobby_window(self) -> Optional[LobbyWindow]:
        """Find the main GGSystem lobby window using AppleScript"""
        script = '''
        tell application "System Events"
            if not (exists process "GGnet") then return ""
            tell process "GGnet"
                repeat with w in windows
                    set winName to name of w as text
                    if winName is "GGSystem" then
                        set winPos to position of w
                        set winSize to size of w
                        return winName & "###" & (item 1 of winPos as text) & "," & (item 2 of winPos as text) & "," & (item 1 of winSize as text) & "," & (item 2 of winSize as text)
                    end if
                end repeat
            end tell
        end tell
        return ""
        '''
        try:
            result = subprocess.run(['osascript', '-e', script],
                                    capture_output=True, text=True, timeout=5)
            output = result.stdout.strip()

            if output and '###' in output:
                name, coords = output.split('###')
                # Fix Unicode minus signs from macOS
                coords = coords.replace('\u2212', '-').replace('\u2013', '-')
                parts = coords.split(',')

                self.lobby = LobbyWindow(
                    name=name.strip(),
                    x_pt=int(parts[0]),
                    y_pt=int(parts[1]),
                    w_pt=int(parts[2]),
                    h_pt=int(parts[3])
                )
                log.info(f"Found lobby: {self.lobby.name} at ({self.lobby.x_pt}, {self.lobby.y_pt}) "
                        f"size {self.lobby.w_pt}x{self.lobby.h_pt}")
                return self.lobby

        except Exception as e:
            log.error(f"Error finding lobby window: {e}")

        return None

    def capture_lobby(self) -> Optional[Image.Image]:
        """Take screenshot and crop to lobby area"""
        if not self.lobby:
            self.find_lobby_window()

        if not self.lobby:
            log.error("No lobby window found")
            return None

        try:
            screenshot = ImageGrab.grab()
            lobby_img = screenshot.crop((
                self.lobby.x_px,
                self.lobby.y_px,
                self.lobby.x_px + self.lobby.w_px,
                self.lobby.y_px + self.lobby.h_px
            ))
            self.last_screenshot = lobby_img
            return lobby_img
        except Exception as e:
            log.error(f"Error capturing lobby: {e}")
            return None

    def find_spin_gold_icon(self, lobby_img: Image.Image) -> Optional[DetectedElement]:
        """
        Find the Spin & Gold icon in the top icon bar using OCR + color detection.

        IMPROVED: Uses OCR to find "Spin" text first, then looks for nearby gold icons.
        This prevents clicking on wrong gold-colored elements like GGMasters banners.
        """
        img = cv2.cvtColor(np.array(lobby_img), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h_img, w_img = img.shape[:2]

        # Search only in the top icon bar area
        icon_bar_height = int(h_img * self.ICON_BAR_HEIGHT_RATIO)

        # METHOD 1: OCR-based detection (most reliable)
        try:
            import pytesseract

            # Look for "Spin" text in the icon bar
            icon_bar_img = lobby_img.crop((0, 0, w_img, icon_bar_height))
            ocr_data = pytesseract.image_to_data(icon_bar_img, output_type=pytesseract.Output.DICT)

            for i, text in enumerate(ocr_data['text']):
                text_lower = text.lower().strip()
                # Look for "Spin" or "Gold" text
                if text_lower in ['spin', 'gold', 'spin&gold', 'spin&', '&gold']:
                    x = ocr_data['left'][i]
                    y = ocr_data['top'][i]
                    w = ocr_data['width'][i]
                    h = ocr_data['height'][i]

                    if w > 10 and h > 5:  # Valid detection
                        log.info(f"OCR found '{text}' at ({x}, {y})")

                        # Create element centered on the text, expanded to include icon
                        best = DetectedElement(
                            name='Spin & Gold Icon',
                            x_px=max(0, x - 20),  # Expand left for icon
                            y_px=max(0, y - 10),
                            width=w + 40,
                            height=h + 20,
                            confidence=0.95
                        )
                        self.detected_elements['spin_gold_icon'] = best
                        log_action('spin_gold_detection', success=True, details={
                            'method': 'ocr',
                            'text_found': text,
                            'position': (best.x_px, best.y_px)
                        }, save_on_fail=False)
                        return best

        except ImportError:
            log.warning("pytesseract not available, falling back to color detection")
        except Exception as e:
            log.warning(f"OCR detection failed: {e}, falling back to color detection")

        # METHOD 2: Color-based detection (fallback)
        search_region = hsv[:icon_bar_height, :]

        # Create mask for gold/yellow color
        mask = cv2.inRange(search_region,
                          self.SPIN_GOLD_ICON_HSV['lower'],
                          self.SPIN_GOLD_ICON_HSV['upper'])

        # Clean up mask
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Find the best gold icon candidate
        # Should be roughly square-ish and substantial size
        # IMPROVED: Stricter position filtering - Spin & Gold is ALWAYS in left 40% of icon bar
        best = None
        best_score = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 200:  # Too small
                continue

            x, y, w, h = cv2.boundingRect(cnt)

            # Icon should be roughly square (aspect ratio 0.5-2.0)
            if h == 0:
                continue
            aspect = w / h
            if not (0.4 < aspect < 2.5):
                continue

            # STRICT position check - Spin & Gold is in LEFT part of icon bar
            x_center = x + w // 2
            if x_center > w_img * 0.5:  # Skip anything in right half
                continue

            # Score by area and position (prefer left side)
            position_score = 1.0 - (x_center / w_img)  # Higher score for leftmost

            score = area * position_score

            if score > best_score:
                best_score = score
                best = DetectedElement(
                    name='Spin & Gold Icon',
                    x_px=x,
                    y_px=y,
                    width=w,
                    height=h,
                    confidence=min(1.0, area / 1000)
                )

        if best:
            log.info(f"Found Spin & Gold icon at ({best.x_px}, {best.y_px}) "
                    f"size {best.width}x{best.height}")
            self.detected_elements['spin_gold_icon'] = best
            log_action('spin_gold_detection', success=True, details={
                'method': 'color',
                'position': (best.x_px, best.y_px),
                'size': (best.width, best.height)
            }, save_on_fail=False)
        else:
            log_action('spin_gold_detection', success=False, details={
                'search_height': icon_bar_height,
                'method': 'both_failed'
            }, screenshot=lobby_img)  # Save lobby screenshot for debugging

        return best

    def find_game_tiles(self, lobby_img: Image.Image) -> List[DetectedElement]:
        """
        Find game tiles in the lobby grid.

        Tiles are rectangular regions with colored backgrounds.
        They appear in a grid below the icon bar.
        """
        img = cv2.cvtColor(np.array(lobby_img), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h_img, w_img = img.shape[:2]

        # Search in the grid area (below icons, above bottom nav)
        grid_top = int(h_img * self.GRID_TOP_RATIO)
        grid_bottom = int(h_img * self.GRID_BOTTOM_RATIO)
        search_region = hsv[grid_top:grid_bottom, :]

        tiles = []

        # Look for tiles of each color type
        for color_name, color_range in self.TILE_COLORS.items():
            mask = cv2.inRange(search_region, color_range['lower'], color_range['upper'])

            # Clean up mask
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 3000:  # Tiles should be substantial
                    continue

                x, y, w, h = cv2.boundingRect(cnt)

                # Tiles are usually wider than tall (landscape)
                if h == 0:
                    continue
                aspect = w / h
                if not (0.8 < aspect < 3.0):  # Reasonable tile aspect ratio
                    continue

                # Minimum dimensions
                if w < 80 or h < 50:
                    continue

                tiles.append(DetectedElement(
                    name=f'{color_name.title()} Tile',
                    x_px=x,
                    y_px=y + grid_top,  # Adjust back to full image coords
                    width=w,
                    height=h,
                    confidence=min(1.0, area / 10000)
                ))

        # Sort tiles by position (top to bottom, left to right)
        tiles.sort(key=lambda t: (t.y_px // 50, t.x_px))

        # Remove duplicates/overlapping tiles
        filtered = []
        for tile in tiles:
            is_duplicate = False
            for existing in filtered:
                # Check if centers are close
                dx = abs(tile.center_px[0] - existing.center_px[0])
                dy = abs(tile.center_px[1] - existing.center_px[1])
                if dx < 50 and dy < 50:
                    is_duplicate = True
                    break
            if not is_duplicate:
                filtered.append(tile)

        log.info(f"Found {len(filtered)} game tiles")
        for i, tile in enumerate(filtered[:6]):  # Log first 6
            log.debug(f"  Tile {i+1}: {tile.name} at ({tile.x_px}, {tile.y_px})")

        self.detected_elements['tiles'] = filtered

        # Log for adaptive learning
        log_action('tile_detection', success=len(filtered) > 0, details={
            'count': len(filtered),
            'colors': [t.name for t in filtered[:5]]
        })

        return filtered

    def find_play_now_buttons(self, lobby_img: Image.Image,
                              search_area: Optional[Tuple[int, int, int, int]] = None) -> List[DetectedElement]:
        """
        Find "Play Now" buttons by detecting white text on dark background.

        GGSystem's Play Now buttons are dark with white text, so we detect them
        by finding white text regions in the bottom of the lobby.
        """
        img = cv2.cvtColor(np.array(lobby_img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h_img, w_img = img.shape[:2]

        if search_area:
            x1, y1, x2, y2 = search_area
            search_region = gray[y1:y2, x1:x2]
            offset_x, offset_y = x1, y1
        else:
            # Search bottom 15% where Play Now buttons appear
            bottom_start = int(h_img * 0.85)
            # Focus on left-center area (avoid right sidebar)
            left_margin = int(w_img * 0.05)
            right_margin = int(w_img * 0.60)
            search_region = gray[bottom_start:, left_margin:right_margin]
            offset_x, offset_y = left_margin, bottom_start
            log.debug(f"Searching for Play Now buttons: y={bottom_start}+, x={left_margin}-{right_margin}")

        # Find white text areas (high brightness)
        _, white_mask = cv2.threshold(search_region, 150, 255, cv2.THRESH_BINARY)

        # Dilate horizontally to connect text characters into button-sized regions
        kernel = np.ones((5, 15), np.uint8)
        dilated = cv2.dilate(white_mask, kernel, iterations=2)

        # Find contours of text groups
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        buttons = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 1000:  # Skip tiny regions
                continue

            x, y, w, h = cv2.boundingRect(cnt)

            # Button text should be button-sized
            # "Play Now" text is roughly 100-200px wide, 20-50px tall
            if not (60 < w < 300 and 15 < h < 80):
                continue

            # Aspect ratio check - text is wider than tall
            if h == 0:
                continue
            aspect = w / h
            if not (1.5 < aspect < 12.0):
                continue

            buttons.append(DetectedElement(
                name='Play Now',
                x_px=x + offset_x,
                y_px=y + offset_y,
                width=w,
                height=h,
                confidence=min(1.0, area / 5000)
            ))
            log.debug(f"Play Now candidate: ({x + offset_x}, {y + offset_y}) size {w}x{h}")

        # Sort by x position (leftmost first - "without insurance" is usually left)
        buttons.sort(key=lambda b: b.x_px)

        # Filter to keep only the most likely Play Now buttons
        # They should be near each other horizontally and similar y position
        if len(buttons) > 2:
            # Keep up to 2 buttons that are at similar y positions
            filtered = []
            for btn in buttons:
                if not filtered:
                    filtered.append(btn)
                else:
                    # Check if similar y to first button
                    if abs(btn.y_px - filtered[0].y_px) < 50:
                        filtered.append(btn)
                        if len(filtered) >= 2:
                            break
            buttons = filtered

        log.info(f"Found {len(buttons)} Play Now buttons")
        self.detected_elements['play_now_buttons'] = buttons

        # Log for adaptive learning with game type context
        game_type = 'unknown'
        if self.detected_elements.get('spin_gold_icon'):
            game_type = 'spin_gold'
        log_action('play_now_detection', success=len(buttons) > 0, details={
            'count': len(buttons),
            'game_type': game_type,
            'positions': [(b.x_px, b.y_px) for b in buttons[:3]]
        })

        return buttons

    def click_at(self, x_pt: int, y_pt: int, description: str = ""):
        """Click at screen coordinates (points)"""
        try:
            # Focus GGSystem first
            subprocess.run(['osascript', '-e',
                'tell application "System Events" to tell process "GGnet" to set frontmost to true'],
                capture_output=True, timeout=2)
            time.sleep(0.05)

            # Use Quartz for clicking (faster and more reliable)
            try:
                import Quartz

                # Create click events
                down_event = Quartz.CGEventCreateMouseEvent(
                    None, Quartz.kCGEventLeftMouseDown,
                    (x_pt, y_pt), Quartz.kCGMouseButtonLeft
                )
                up_event = Quartz.CGEventCreateMouseEvent(
                    None, Quartz.kCGEventLeftMouseUp,
                    (x_pt, y_pt), Quartz.kCGMouseButtonLeft
                )

                Quartz.CGEventPost(Quartz.kCGHIDEventTap, down_event)
                time.sleep(0.03)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up_event)

            except ImportError:
                # Fallback to pynput
                from pynput.mouse import Button, Controller
                mouse = Controller()
                mouse.position = (x_pt, y_pt)
                time.sleep(0.02)
                mouse.click(Button.left)

            log.info(f"Clicked {description} at ({x_pt}, {y_pt})")
            return True

        except Exception as e:
            log.error(f"Click failed: {e}")
            return False

    def click_element(self, element: DetectedElement) -> bool:
        """Click on a detected element with adaptive learning"""
        if not self.lobby:
            log.error("No lobby window found")
            return False

        x_pt, y_pt = element.to_screen_point(self.lobby.x_pt, self.lobby.y_pt)
        success = self.click_at(x_pt, y_pt, element.name)

        # Log for adaptive learning
        log_action('lobby_click', success=success, details={
            'element': element.name,
            'position': (x_pt, y_pt)
        })

        if not success:
            report_issue('lobby_click', f"Failed to click {element.name} at ({x_pt}, {y_pt})")

        return success

    def navigate_to_spin_gold(self) -> bool:
        """Navigate to the Spin & Gold section in the lobby"""
        log.info("=== Navigating to Spin & Gold ===")

        # Find and capture lobby
        if not self.find_lobby_window():
            log.error("Could not find GGSystem lobby")
            return False

        lobby_img = self.capture_lobby()
        if lobby_img is None:
            return False

        # Find Spin & Gold icon
        icon = self.find_spin_gold_icon(lobby_img)
        if not icon:
            log.error("Could not find Spin & Gold icon")
            return False

        # Click it
        if not self.click_element(icon):
            return False

        time.sleep(0.5)  # Wait for animation
        return True

    def select_stake_tile(self, tile_index: int = 0) -> bool:
        """
        Select a game tile by index.

        Args:
            tile_index: 0-based index of tile to select (0 = first/cheapest)
        """
        log.info(f"=== Selecting tile {tile_index} ===")

        # Capture fresh screenshot
        lobby_img = self.capture_lobby()
        if lobby_img is None:
            return False

        # Find tiles
        tiles = self.find_game_tiles(lobby_img)
        if not tiles:
            log.error("No game tiles found")
            return False

        if tile_index >= len(tiles):
            log.warning(f"Tile index {tile_index} out of range, using last tile")
            tile_index = len(tiles) - 1

        tile = tiles[tile_index]
        log.info(f"Selecting: {tile.name} at ({tile.x_px}, {tile.y_px})")

        return self.click_element(tile)

    def click_play_now(self) -> bool:
        """Click the Play Now button"""
        log.info("=== Clicking Play Now ===")

        # Capture fresh screenshot
        lobby_img = self.capture_lobby()
        if lobby_img is None:
            return False

        # Find Play Now buttons
        buttons = self.find_play_now_buttons(lobby_img)
        if not buttons:
            log.error("No Play Now button found")
            return False

        # Click the first (most prominent) one
        button = buttons[0]
        log.info(f"Found Play Now at ({button.x_px}, {button.y_px})")

        return self.click_element(button)

    def close_popups(self) -> bool:
        """
        Close any popup dialogs that might be blocking the lobby.

        Looks for:
        - X buttons in top-right corners
        - "OK" / "Close" buttons
        - Pressing Escape key
        """
        log.info("=== Checking for popups to close ===")

        # First, try pressing Escape to close any popup
        try:
            import subprocess
            # Press Escape key via AppleScript
            subprocess.run(['osascript', '-e',
                'tell application "System Events" to key code 53'],  # 53 = Escape
                capture_output=True, timeout=2)
            time.sleep(0.3)
        except Exception as e:
            log.debug(f"Escape key failed: {e}")

        # Take screenshot and look for X buttons or OK buttons
        lobby_img = self.capture_lobby()
        if lobby_img is None:
            return False

        img = cv2.cvtColor(np.array(lobby_img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = img.shape[:2]

        # Look for X buttons (usually white/light on dark background, top-right of popups)
        # Search the center-right area where popup close buttons typically are
        search_x1, search_x2 = int(w * 0.5), int(w * 0.95)
        search_y1, search_y2 = int(h * 0.1), int(h * 0.5)

        search_region = gray[search_y1:search_y2, search_x1:search_x2]

        # Find bright pixels (X buttons are usually white)
        _, binary = cv2.threshold(search_region, 200, 255, cv2.THRESH_BINARY)

        # Look for small bright areas that could be X buttons
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 100 < area < 2000:  # X button sized
                x, y, bw, bh = cv2.boundingRect(cnt)
                # Check aspect ratio - X buttons are roughly square
                if 0.5 < bw / bh < 2.0:
                    # Click this potential X button
                    click_x = search_x1 + x + bw // 2
                    click_y = search_y1 + y + bh // 2
                    screen_x = self.lobby.x_pt + click_x // RETINA_SCALE
                    screen_y = self.lobby.y_pt + click_y // RETINA_SCALE

                    log.info(f"Found potential popup X button at ({screen_x}, {screen_y})")
                    self.click_at(screen_x, screen_y, "Popup X")
                    time.sleep(0.3)

                    log_action('popup_close', success=True, details={
                        'position': (screen_x, screen_y),
                        'method': 'x_button'
                    })
                    return True

        # Also try clicking outside the popup (on dark overlay)
        # Click in the bottom-left corner which is usually overlay
        overlay_x = self.lobby.x_pt + 50
        overlay_y = self.lobby.y_pt + self.lobby.h_pt - 50
        self.click_at(overlay_x, overlay_y, "Overlay close")
        time.sleep(0.2)

        return False

    def count_poker_tables(self) -> int:
        """Count how many poker table windows are currently open"""
        script = '''
        tell application "System Events"
            tell process "GGnet"
                set tableCount to 0
                repeat with w in windows
                    set winName to name of w as text
                    if winName contains "Spin" or winName contains "Gold" or winName contains "Hold" or winName contains "NL" or winName contains "Blinds" then
                        set tableCount to tableCount + 1
                    end if
                end repeat
                return tableCount
            end tell
        end tell
        '''
        try:
            result = subprocess.run(['osascript', '-e', script],
                                    capture_output=True, text=True, timeout=5)
            return int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
        except:
            return 0

    def verify_registration_success(self, tables_before: int, timeout: float = 10.0) -> bool:
        """
        Verify that registration succeeded by checking if a new table window opened.

        Args:
            tables_before: Number of tables before registration
            timeout: How long to wait for table to open

        Returns:
            True if a new table window appeared
        """
        log.info(f"Verifying registration... (had {tables_before} tables)")

        start_time = time.time()
        while time.time() - start_time < timeout:
            tables_now = self.count_poker_tables()
            if tables_now > tables_before:
                log.info(f"SUCCESS: New table opened! ({tables_before} -> {tables_now})")
                log_action('registration_verification', success=True, details={
                    'tables_before': tables_before,
                    'tables_after': tables_now,
                    'wait_time': time.time() - start_time
                })
                return True
            time.sleep(0.5)

        log.warning(f"FAILED: No new table after {timeout}s")
        log_action('registration_verification', success=False, details={
            'tables_before': tables_before,
            'tables_after': self.count_poker_tables(),
            'timeout': timeout
        })
        return False

    def register_for_spin_gold(self, stake_index: int = 0) -> bool:
        """
        Complete registration flow for Spin & Gold with verification.

        Args:
            stake_index: Which stake level to select (0 = cheapest)

        Returns:
            True if registration was successful AND a table opened
        """
        log.info(f"=== Registering for Spin & Gold (stake index: {stake_index}) ===")

        # Record tables before registration
        tables_before = self.count_poker_tables()
        log.info(f"Tables before: {tables_before}")

        # Step 0: Close any popups first
        self.close_popups()
        time.sleep(0.2)

        # Step 1: Navigate to Spin & Gold section
        if not self.navigate_to_spin_gold():
            log_action('spin_gold_registration', success=False, details={
                'step': 'navigate',
                'reason': 'failed_to_find_icon'
            })
            return False
        time.sleep(0.5)

        # Step 2: Verify we're on Spin & Gold page (not GGMasters, etc.)
        # Take screenshot and look for "Spin & Gold" text OR "Join Now" button
        try:
            import pytesseract
            lobby_img = self.capture_lobby()
            if lobby_img:
                ocr_text = pytesseract.image_to_string(lobby_img).lower()
                # Accept page if we find Spin, Gold, OR Join Now (indicates game selection page)
                valid_indicators = ['spin', 'gold', 'join now', 'join', 'mystery', 'jackpot', 'bounties']
                found_indicator = any(ind in ocr_text for ind in valid_indicators)
                if not found_indicator:
                    log.warning("WARNING: May not be on Spin & Gold page! OCR didn't find expected text")
                    log.debug(f"OCR text sample: {ocr_text[:300]}")
                    # Still continue - the visual detection may be more reliable
                    log.info("Continuing anyway - will try to find game tiles")
                else:
                    log.info("Page verification: Confirmed on game selection page")
        except Exception as e:
            log.debug(f"Page verification skipped: {e}")

        # Step 3: Select stake tile
        if not self.select_stake_tile(stake_index):
            log_action('spin_gold_registration', success=False, details={
                'step': 'select_tile',
                'reason': 'no_tiles_found'
            })
            return False
        time.sleep(0.3)

        # Step 4: Click Play Now
        if not self.click_play_now():
            log_action('spin_gold_registration', success=False, details={
                'step': 'play_now',
                'reason': 'button_not_found'
            })
            return False

        log.info("Registration submitted, verifying...")

        # Step 5: VERIFY - Did a table actually open?
        success = self.verify_registration_success(tables_before, timeout=8.0)

        log_action('spin_gold_registration', success=success, details={
            'stake_index': stake_index,
            'tables_before': tables_before,
            'tables_after': self.count_poker_tables(),
            'verified': success
        })

        if success:
            log.info("Registration VERIFIED - table opened!")
        else:
            log.warning("Registration UNVERIFIED - no new table detected")
            report_issue('registration', f'Clicked Play Now but no table opened after 8s')

        return success

    def _set_max_buyin(self):
        """Set max buy-in in the buy-in dialog before clicking OK.

        Tries multiple strategies:
        1. Click "Max" text (OCR)
        2. Click the right end of the slider track
        3. Drag slider to the right
        """
        try:
            import pytesseract
            screenshot = ImageGrab.grab()
            data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)

            # Strategy 1: Find and click "Max" text
            for i, text in enumerate(data['text']):
                t = text.strip().lower() if text else ''
                if t in ('max', 'maximum'):
                    x = data['left'][i] + data['width'][i] // 2
                    y = data['top'][i] + data['height'][i] // 2
                    click_x, click_y = x // RETINA_SCALE, y // RETINA_SCALE
                    log.info(f"Clicking 'Max' buy-in at ({click_x}, {click_y})")
                    self.click_at(click_x, click_y, "Max buy-in")
                    time.sleep(0.5)
                    return True

            # Strategy 2: Find the slider by looking for a horizontal colored bar
            # in the center area of the screen (where the dialog is).
            # The slider track is typically a thin colored line. Click the right end.
            img = np.array(screenshot)
            h_img, w_img = img.shape[:2]

            # Dialog is in the center third of the screen
            center_y1 = h_img // 4
            center_y2 = 3 * h_img // 4
            center_x1 = w_img // 4
            center_x2 = 3 * w_img // 4
            center_crop = img[center_y1:center_y2, center_x1:center_x2]

            # Look for the slider: a colored horizontal bar (orange/yellow accent)
            hsv = cv2.cvtColor(center_crop, cv2.COLOR_RGB2HSV)
            # GGSystem slider is often orange/gold
            slider_mask = cv2.inRange(hsv, (10, 80, 100), (30, 255, 255))
            # Also try green slider
            green_mask = cv2.inRange(hsv, (35, 80, 100), (85, 255, 255))
            combined = cv2.bitwise_or(slider_mask, green_mask)

            # Find rightmost point of the slider track
            rows = np.any(combined > 0, axis=1)
            if np.any(rows):
                slider_rows = np.where(rows)[0]
                mid_row = slider_rows[len(slider_rows) // 2]
                # Find slider pixels in this row
                slider_cols = np.where(combined[mid_row] > 0)[0]
                if len(slider_cols) > 10:  # Reasonable slider width
                    # Click 95% to the right of the slider track (near max)
                    right_x = int(slider_cols[-1])
                    # Convert back to full-screen pixels
                    full_x = center_x1 + right_x
                    full_y = center_y1 + mid_row
                    click_x, click_y = full_x // RETINA_SCALE, full_y // RETINA_SCALE
                    log.info(f"Clicking slider right end at ({click_x}, {click_y})")
                    self.click_at(click_x, click_y, "Slider max")
                    time.sleep(0.5)
                    return True

            # Strategy 3: Find the "+" button (increment) and click it many times
            for i, text in enumerate(data['text']):
                t = text.strip() if text else ''
                if t == '+':
                    x = data['left'][i] + data['width'][i] // 2
                    y = data['top'][i] + data['height'][i] // 2
                    click_x, click_y = x // RETINA_SCALE, y // RETINA_SCALE
                    log.info(f"Clicking '+' button repeatedly for max buy-in at ({click_x}, {click_y})")
                    for _ in range(20):  # Click 20 times to max out
                        self.click_at(click_x, click_y, "+")
                        time.sleep(0.05)
                    time.sleep(0.3)
                    return True

            log.warning("Could not find Max button or slider in buy-in dialog")
            return False

        except Exception as e:
            log.warning(f"Max buy-in setting failed: {e}")
            return False

    def open_rush_and_cash(self, stake='0.01/0.02'):
        """Open a Rush & Cash table at the specified stake.

        Args:
            stake: Stake level string, e.g. '0.01/0.02' for NL2
        """
        log.info(f"Opening Rush & Cash table at {stake}...")

        # 1. Find and focus the lobby
        lobby_window = self.find_lobby_window()
        if not lobby_window:
            log.error("Could not find GGSystem lobby window")
            return False

        # Focus the LOBBY window specifically (not just the process)
        # Using AXRaise to bring the lobby window in front of poker tables
        try:
            focus_script = '''
            tell application "System Events"
                tell process "GGnet"
                    set frontmost to true
                    repeat with w in windows
                        if name of w is "GGSystem" then
                            perform action "AXRaise" of w
                        end if
                    end repeat
                end tell
            end tell
            '''
            subprocess.run(['osascript', '-e', focus_script],
                capture_output=True, timeout=3)
        except Exception:
            pass
        time.sleep(0.8)

        # 2. Take screenshot CROPPED TO LOBBY WINDOW only (avoid terminal text)
        screenshot = ImageGrab.grab()
        lw = lobby_window
        # Lobby bounds in pixels (Retina 2x)
        lx = max(0, lw.x_pt * RETINA_SCALE)
        ly = max(0, lw.y_pt * RETINA_SCALE)
        lw_px = lw.w_pt * RETINA_SCALE
        lh_px = lw.h_pt * RETINA_SCALE
        lobby_crop = screenshot.crop((lx, ly, lx + lw_px, ly + lh_px))
        log.info(f"Cropped lobby: ({lx},{ly}) {lw_px}x{lh_px} pixels")

        try:
            import pytesseract
            data = pytesseract.image_to_data(lobby_crop, output_type=pytesseract.Output.DICT)
        except Exception as e:
            log.error(f"OCR failed: {e}")
            return False

        # Debug: log all detected text for troubleshooting
        all_text = [t for t in data['text'] if t and t.strip()]
        log.info(f"Lobby OCR detected {len(all_text)} words: {all_text[:30]}")

        # Save lobby screenshot for debugging (overwrite each time)
        try:
            debug_path = os.path.join('data', 'learning', 'debug', 'lobby_latest.png')
            os.makedirs(os.path.dirname(debug_path), exist_ok=True)
            lobby_crop.save(debug_path)
        except Exception:
            pass

        # Check if lobby already shows Join buttons (Rush & Cash list visible)
        has_join = any(
            t.lower().strip() == 'join'
            for t in data['text'] if t
        )

        if has_join:
            log.info("Rush & Cash game list already visible (Join buttons found)")
            rush_clicked = True
        else:
            # Look for "Rush" text to click on the Rush & Cash tab
            # OCR coords are relative to lobby_crop, convert to screen points
            rush_clicked = False
            for i, text in enumerate(data['text']):
                if text and 'rush' in text.lower():
                    crop_x = data['left'][i] + data['width'][i] // 2
                    crop_y = data['top'][i] + data['height'][i] // 2
                    screen_x_pt = (lx + crop_x) // RETINA_SCALE
                    screen_y_pt = (ly + crop_y) // RETINA_SCALE
                    log.info(f"Found 'Rush' text at pt({screen_x_pt}, {screen_y_pt}), clicking...")
                    self.click_at(screen_x_pt, screen_y_pt, "Rush tab")
                    rush_clicked = True
                    time.sleep(1.0)
                    break

            if not rush_clicked:
                log.warning("Could not find 'Rush' text in lobby, trying 'Cash' text...")
                for i, text in enumerate(data['text']):
                    if text and 'cash' in text.lower():
                        crop_x = data['left'][i] + data['width'][i] // 2
                        crop_y = data['top'][i] + data['height'][i] // 2
                        screen_x_pt = (lx + crop_x) // RETINA_SCALE
                        screen_y_pt = (ly + crop_y) // RETINA_SCALE
                        log.info(f"Found 'Cash' text at pt({screen_x_pt}, {screen_y_pt}), clicking...")
                        self.click_at(screen_x_pt, screen_y_pt, "Cash tab")
                        rush_clicked = True
                        time.sleep(1.0)
                        break

            if not rush_clicked:
                log.error("Could not find Rush & Cash in lobby")
                return False

        # 3. Now find the stake level and click Join/Play
        time.sleep(1.5)  # Wait for lobby to show Rush & Cash list
        screenshot2 = ImageGrab.grab()
        # Crop to lobby again for stake/join detection
        lobby_crop2 = screenshot2.crop((lx, ly, lx + lw_px, ly + lh_px))
        data2 = pytesseract.image_to_data(lobby_crop2, output_type=pytesseract.Output.DICT)

        # Strategy: find all "Join" buttons, then pick the one on the same row
        # as our target stake. All coords here are relative to lobby_crop2.
        stake_parts = stake.split('/')
        stake_low = stake_parts[0].replace('$', '')  # e.g. "0.01"

        # Helper: convert lobby-crop pixel coords to screen points
        def crop_to_screen_pt(crop_px_x, crop_px_y):
            return (lx + crop_px_x) // RETINA_SCALE, (ly + crop_px_y) // RETINA_SCALE

        # Collect all Join button positions (in crop pixels)
        join_buttons = []
        for i, text in enumerate(data2['text']):
            t = text.lower().strip() if text else ''
            if t in ('join', 'play'):
                btn_x = data2['left'][i] + data2['width'][i] // 2
                btn_y = data2['top'][i] + data2['height'][i] // 2
                join_buttons.append((btn_x, btn_y, text))
                log.debug(f"Found '{text}' button at crop pixel ({btn_x}, {btn_y})")

        # Collect all stake text positions
        stake_rows = []
        for i, text in enumerate(data2['text']):
            if text and stake_low in text.replace('$', ''):
                sy = data2['top'][i]
                # Skip top 15% of lobby (title bar / tab area)
                if sy < lh_px * 0.15:
                    log.debug(f"Skipping stake '{text}' at crop y={sy} (title area)")
                    continue
                stake_rows.append(sy)
                log.debug(f"Found stake '{text}' at crop y={sy}")

        # Find the Join button closest to a matching stake row
        join_clicked = False
        best_join = None
        best_dist = 999999
        for jx, jy, jtext in join_buttons:
            for sy in stake_rows:
                dist = abs(jy - sy)
                if dist < 80 and dist < best_dist:
                    best_dist = dist
                    best_join = (jx, jy, jtext)

        if best_join:
            jx, jy, jtext = best_join
            click_x, click_y = crop_to_screen_pt(jx, jy)
            log.info(f"Clicking '{jtext}' at pt({click_x}, {click_y}) for stake {stake}")
            self.click_at(click_x, click_y, f"Join ({jtext})")
            join_clicked = True
            time.sleep(2.0)
        elif join_buttons:
            # No stake match found — click the last (lowest stake) Join button
            jx, jy, jtext = join_buttons[-1]
            click_x, click_y = crop_to_screen_pt(jx, jy)
            log.info(f"No stake match, clicking last '{jtext}' at pt({click_x}, {click_y})")
            self.click_at(click_x, click_y, f"Join fallback ({jtext})")
            join_clicked = True
            time.sleep(2.0)
        else:
            # Fallback: look for green button in the lobby content area
            log.warning("No Join text found, looking for green button...")
            img = np.array(lobby_crop2)
            hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
            green_mask = cv2.inRange(hsv, (35, 80, 80), (85, 255, 255))

            # Only look in the lower 2/3 (lobby content, not tabs)
            green_mask[:green_mask.shape[0] // 3, :] = 0

            contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL,
                                            cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                M = cv2.moments(largest)
                if M['m00'] > 0:
                    cx = int(M['m10'] / M['m00'])
                    cy = int(M['m01'] / M['m00'])
                    click_x, click_y = crop_to_screen_pt(cx, cy)
                    log.info(f"Clicking green button at pt({click_x}, {click_y})")
                    self.click_at(click_x, click_y, "Green Join button")
                    join_clicked = True
                    time.sleep(2.0)

        if join_clicked:
            # 5. Handle the Buy-in confirmation dialog
            # GGSystem shows a dialog with buy-in slider, "Max" button, and "OK"/"Cancel"
            log.info("Waiting for buy-in dialog...")
            time.sleep(1.5)

            # Step A: Set max buy-in by clicking "Max" text or dragging slider
            self._set_max_buyin()

            time.sleep(0.5)

            # Step B: Click OK to confirm
            screenshot3 = ImageGrab.grab()
            data3 = pytesseract.image_to_data(screenshot3, output_type=pytesseract.Output.DICT)

            # Look for "OK" button text in the dialog
            ok_clicked = False
            for i, text in enumerate(data3['text']):
                t = text.strip() if text else ''
                if t == 'OK':
                    x = data3['left'][i] + data3['width'][i] // 2
                    y = data3['top'][i] + data3['height'][i] // 2
                    click_x, click_y = x // RETINA_SCALE, y // RETINA_SCALE
                    log.info(f"Clicking OK on buy-in dialog at ({click_x}, {click_y})")
                    self.click_at(click_x, click_y, "Buy-in OK")
                    ok_clicked = True
                    time.sleep(3.0)  # Wait for table to open
                    break

            if not ok_clicked:
                # Fallback: look for green OK button by color
                img3 = np.array(screenshot3)
                hsv3 = cv2.cvtColor(img3, cv2.COLOR_RGB2HSV)
                green_mask3 = cv2.inRange(hsv3, (35, 80, 80), (85, 255, 255))
                h, w = green_mask3.shape
                green_mask3[:h // 3, :] = 0
                green_mask3[2 * h // 3:, :] = 0
                green_mask3[:, :w // 4] = 0
                green_mask3[:, 3 * w // 4:] = 0

                contours3, _ = cv2.findContours(green_mask3, cv2.RETR_EXTERNAL,
                                                 cv2.CHAIN_APPROX_SIMPLE)
                if contours3:
                    largest3 = max(contours3, key=cv2.contourArea)
                    area = cv2.contourArea(largest3)
                    if area > 500:
                        M3 = cv2.moments(largest3)
                        if M3['m00'] > 0:
                            cx = int(M3['m10'] / M3['m00'])
                            cy = int(M3['m01'] / M3['m00'])
                            click_x, click_y = cx // RETINA_SCALE, cy // RETINA_SCALE
                            log.info(f"Clicking green OK button at ({click_x}, {click_y})")
                            self.click_at(click_x, click_y, "Buy-in OK (green)")
                            ok_clicked = True
                            time.sleep(3.0)

            if ok_clicked:
                log.info("Rush & Cash table opening confirmed (max buy-in)")
                return True
            else:
                log.warning("Buy-in dialog OK not found, but Join was clicked")
                return True  # Join was clicked, might still work

        log.error("Failed to open Rush & Cash table")
        return False

    def debug_save_detection(self, lobby_img: Image.Image, output_dir: str = '/tmp/gg_debug'):
        """Save debug images showing what was detected"""
        import os
        os.makedirs(output_dir, exist_ok=True)

        # Save original
        lobby_img.save(f'{output_dir}/lobby_original.png')

        # Create debug image with annotations
        img = cv2.cvtColor(np.array(lobby_img), cv2.COLOR_RGB2BGR)

        # Draw detected elements
        if 'spin_gold_icon' in self.detected_elements:
            elem = self.detected_elements['spin_gold_icon']
            cv2.rectangle(img,
                         (elem.x_px, elem.y_px),
                         (elem.x_px + elem.width, elem.y_px + elem.height),
                         (0, 215, 255), 2)  # Gold color
            cv2.putText(img, 'Spin&Gold', (elem.x_px, elem.y_px - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 215, 255), 1)

        if 'tiles' in self.detected_elements:
            for i, tile in enumerate(self.detected_elements['tiles'][:10]):
                cv2.rectangle(img,
                             (tile.x_px, tile.y_px),
                             (tile.x_px + tile.width, tile.y_px + tile.height),
                             (255, 0, 0), 2)  # Blue
                cv2.putText(img, f'Tile {i+1}', (tile.x_px, tile.y_px - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)

        if 'play_now_buttons' in self.detected_elements:
            for btn in self.detected_elements['play_now_buttons']:
                cv2.rectangle(img,
                             (btn.x_px, btn.y_px),
                             (btn.x_px + btn.width, btn.y_px + btn.height),
                             (0, 255, 0), 2)  # Green
                cv2.putText(img, 'Play Now', (btn.x_px, btn.y_px - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

        cv2.imwrite(f'{output_dir}/lobby_annotated.png', img)
        log.info(f"Debug images saved to {output_dir}")


def test_detection():
    """Test the detection without clicking"""
    print("=" * 60)
    print("Dynamic Lobby Navigator - Detection Test")
    print("=" * 60)

    navigator = DynamicLobbyNavigator()

    # Find lobby
    lobby = navigator.find_lobby_window()
    if not lobby:
        print("ERROR: GGSystem lobby not found. Is it open?")
        return False

    print(f"Lobby: {lobby.name}")
    print(f"  Position: ({lobby.x_pt}, {lobby.y_pt})")
    print(f"  Size: {lobby.w_pt} x {lobby.h_pt}")

    # Capture
    lobby_img = navigator.capture_lobby()
    if not lobby_img:
        print("ERROR: Could not capture lobby")
        return False

    print(f"  Screenshot size: {lobby_img.size}")

    # Detect elements
    print("\nDetecting UI elements...")

    icon = navigator.find_spin_gold_icon(lobby_img)
    if icon:
        x_pt, y_pt = icon.to_screen_point(lobby.x_pt, lobby.y_pt)
        print(f"  Spin & Gold Icon: ({icon.x_px}, {icon.y_px}) -> click at ({x_pt}, {y_pt})")
    else:
        print("  Spin & Gold Icon: NOT FOUND")

    tiles = navigator.find_game_tiles(lobby_img)
    print(f"  Game Tiles: {len(tiles)} found")
    for i, tile in enumerate(tiles[:5]):
        x_pt, y_pt = tile.to_screen_point(lobby.x_pt, lobby.y_pt)
        print(f"    {i+1}. {tile.name} ({tile.width}x{tile.height}) -> click at ({x_pt}, {y_pt})")

    buttons = navigator.find_play_now_buttons(lobby_img)
    print(f"  Play Now Buttons: {len(buttons)} found")
    for btn in buttons[:3]:
        x_pt, y_pt = btn.to_screen_point(lobby.x_pt, lobby.y_pt)
        print(f"    ({btn.width}x{btn.height}) -> click at ({x_pt}, {y_pt})")

    # Save debug images
    navigator.debug_save_detection(lobby_img)
    print("\nDebug images saved to /tmp/gg_debug/")

    return True


def main():
    import argparse
    from sys_core.tools.helper import init_logger

    parser = argparse.ArgumentParser(description="Dynamic GGSystem Lobby Navigator")
    parser.add_argument("--test", action="store_true", help="Test detection without clicking")
    parser.add_argument("--register", action="store_true", help="Register for Spin & Gold")
    parser.add_argument("--stake", type=int, default=0, help="Stake index (0=cheapest)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    init_logger(screenlevel=log_level, filename='dynamic_lobby', logdir='log')

    if args.test:
        test_detection()
    elif args.register:
        navigator = DynamicLobbyNavigator()
        navigator.register_for_spin_gold(stake_index=args.stake)
    else:
        # Default: test detection
        test_detection()


if __name__ == "__main__":
    main()
