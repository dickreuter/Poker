"""
GGSystem Automation System

Provides automated control for:
- Window management (position, resize, identify)
- Lobby navigation
- Tournament registration
- Table management
- Multi-table positioning
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple, Dict
from PIL import ImageGrab, Image
import cv2
import numpy as np

log = logging.getLogger(__name__)


class WindowType(Enum):
    MAIN_LOBBY = "main_lobby"
    CASHIER = "cashier"
    RUSH_CASH_TABLE = "rush_cash_table"
    CASH_TABLE = "cash_table"
    TOURNAMENT_TABLE = "tournament_table"
    TOURNAMENT_LOBBY = "tournament_lobby"
    SNG_LOBBY = "sng_lobby"
    CHAT = "chat"
    UNKNOWN = "unknown"


@dataclass
class GGWindow:
    """Represents a GGSystem window"""
    name: str
    x: int
    y: int
    width: int
    height: int
    window_type: WindowType = WindowType.UNKNOWN
    is_active: bool = False

    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def bounds(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


class FastClicker:
    """Fast native clicking using Quartz"""

    def __init__(self):
        try:
            import Quartz
            self.quartz = Quartz
            self.enabled = True
            log.debug("FastClicker initialized with Quartz")
        except ImportError:
            self.enabled = False
            log.warning("Quartz not available, using AppleScript clicks")

    def click(self, x: int, y: int):
        """Click at screen coordinates"""
        if self.enabled:
            # Quartz uses half-resolution for Retina
            scale = 2.0  # Retina scale
            point_x = x / scale
            point_y = y / scale

            # Create mouse events
            down = self.quartz.CGEventCreateMouseEvent(
                None, self.quartz.kCGEventLeftMouseDown,
                (point_x, point_y), self.quartz.kCGMouseButtonLeft
            )
            up = self.quartz.CGEventCreateMouseEvent(
                None, self.quartz.kCGEventLeftMouseUp,
                (point_x, point_y), self.quartz.kCGMouseButtonLeft
            )

            self.quartz.CGEventPost(self.quartz.kCGHIDEventTap, down)
            time.sleep(0.05)
            self.quartz.CGEventPost(self.quartz.kCGHIDEventTap, up)

            log.debug(f"Clicked at ({x}, {y}) -> point ({point_x}, {point_y})")
        else:
            # Fallback to AppleScript
            script = f'''
            tell application "System Events"
                click at {{{x}, {y}}}
            end tell
            '''
            subprocess.run(['osascript', '-e', script], capture_output=True)


class GGSystemAutomation:
    """
    Main automation controller for GGSystem

    Usage:
        auto = GGSystemAutomation()
        auto.scan_windows()

        # Navigate to Rush & Cash
        auto.open_rush_cash()

        # Register for a tournament
        auto.register_tournament("$5 Bounty")

        # Position all tables
        auto.arrange_tables(layout='2x2')
    """

    def __init__(self):
        self.windows: List[GGWindow] = []
        self.clicker = FastClicker()
        self.screen_size: Tuple[int, int] = (3420, 2224)  # Retina

    def scan_windows(self) -> List[GGWindow]:
        """Scan all GGPoker windows and classify them"""
        script = '''
        tell application "System Events"
            set windowList to {}
            try
                tell process "GGnet"
                    repeat with win in windows
                        set winPos to position of win
                        set winSize to size of win
                        set winName to name of win
                        set end of windowList to winName & "|||" & (item 1 of winPos as string) & "|||" & (item 2 of winPos as string) & "|||" & (item 1 of winSize as string) & "|||" & (item 2 of winSize as string)
                    end repeat
                end tell
            end try
            return windowList
        end tell
        '''
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)

        self.windows = []
        screenshot = ImageGrab.grab()
        self.screen_size = screenshot.size

        if result.stdout.strip():
            for item in result.stdout.strip().split(', '):
                try:
                    # Fix Unicode minus sign (−) that macOS returns instead of ASCII minus (-)
                    item = item.replace('−', '-').replace('–', '-')
                    parts = item.split('|||')
                    if len(parts) >= 5:
                        win = GGWindow(
                            name=parts[0],
                            x=int(parts[1]),
                            y=int(parts[2]),
                            width=int(parts[3]),
                            height=int(parts[4])
                        )
                        win.window_type = self._classify_window(win, screenshot)
                        self.windows.append(win)
                except Exception as e:
                    log.debug(f"Error parsing window: {e}")

        log.info(f"Found {len(self.windows)} GGPoker windows")
        return self.windows

    def _classify_window(self, window: GGWindow, screenshot: Image.Image) -> WindowType:
        """Classify window type based on name and content"""
        name = window.name.lower()

        # Check by name patterns
        if 'cashier' in name:
            return WindowType.CASHIER
        if 'rush' in name and 'cash' in name:
            return WindowType.RUSH_CASH_TABLE
        if any(x in name for x in ['tournament', 'mtt', 'bounty', 'mystery']):
            return WindowType.TOURNAMENT_TABLE
        if 'sng' in name or 'sit' in name:
            return WindowType.SNG_LOBBY
        if 'ggpoker' == name:
            return WindowType.MAIN_LOBBY
        if any(x in name for x in ['hold', 'nlh', 'plo', 'omaha']):
            return WindowType.CASH_TABLE

        # Analyze content if name isn't conclusive
        try:
            region = screenshot.crop(window.bounds())
            region_cv = cv2.cvtColor(np.array(region), cv2.COLOR_BGR2RGB)
            hsv = cv2.cvtColor(region_cv, cv2.COLOR_RGB2HSV)

            # Check for green felt
            lower_green = np.array([35, 40, 40])
            upper_green = np.array([85, 255, 255])
            mask = cv2.inRange(hsv, lower_green, upper_green)
            green_ratio = np.sum(mask > 0) / mask.size

            if green_ratio > 0.15:
                return WindowType.UNKNOWN  # It's a table, but type unknown
        except:
            pass

        return WindowType.UNKNOWN

    def get_main_lobby(self) -> Optional[GGWindow]:
        """Get the main GGPoker lobby window"""
        for win in self.windows:
            if win.window_type == WindowType.MAIN_LOBBY:
                return win
        return None

    def get_tables(self) -> List[GGWindow]:
        """Get all active poker tables"""
        table_types = [
            WindowType.RUSH_CASH_TABLE,
            WindowType.CASH_TABLE,
            WindowType.TOURNAMENT_TABLE
        ]
        return [w for w in self.windows if w.window_type in table_types]

    def move_window(self, window: GGWindow, x: int, y: int,
                    width: int = None, height: int = None) -> bool:
        """Move and optionally resize a window"""
        size_cmd = ""
        if width and height:
            size_cmd = f"set size of win to {{{width}, {height}}}"

        script = f'''
        tell application "System Events"
            tell process "GGnet"
                repeat with win in windows
                    if name of win is "{window.name}" then
                        set position of win to {{{x}, {y}}}
                        {size_cmd}
                        return "success"
                    end if
                end repeat
            end tell
        end tell
        return "not found"
        '''
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        success = 'success' in result.stdout

        if success:
            window.x = x
            window.y = y
            if width:
                window.width = width
            if height:
                window.height = height

        return success

    def focus_window(self, window: GGWindow) -> bool:
        """Bring window to front"""
        script = f'''
        tell application "System Events"
            tell process "GGnet"
                repeat with win in windows
                    if name of win is "{window.name}" then
                        set frontmost to true
                        perform action "AXRaise" of win
                        return "success"
                    end if
                end repeat
            end tell
        end tell
        return "not found"
        '''
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        return 'success' in result.stdout

    def click_in_window(self, window: GGWindow, rel_x: int, rel_y: int):
        """Click at position relative to window"""
        abs_x = window.x + rel_x
        abs_y = window.y + rel_y
        self.clicker.click(abs_x, abs_y)

    def arrange_tables(self, layout: str = '2x2'):
        """Arrange tables in a grid layout

        Layouts:
        - '2x2': 4 tables in 2x2 grid
        - '3x2': 6 tables in 3x2 grid
        - '4x2': 8 tables in 4x2 grid
        - 'cascade': Overlapping cascade
        - 'stack': All in same position (for table switching)
        """
        self.scan_windows()
        tables = self.get_tables()

        if not tables:
            log.warning("No tables to arrange")
            return

        screen_w, screen_h = self.screen_size

        # Define layouts
        layouts = {
            '2x2': {
                'cols': 2, 'rows': 2,
                'width': screen_w // 2, 'height': screen_h // 2
            },
            '3x2': {
                'cols': 3, 'rows': 2,
                'width': screen_w // 3, 'height': screen_h // 2
            },
            '4x2': {
                'cols': 4, 'rows': 2,
                'width': screen_w // 4, 'height': screen_h // 2
            },
        }

        if layout in layouts:
            cfg = layouts[layout]
            for i, table in enumerate(tables):
                col = i % cfg['cols']
                row = i // cfg['cols']
                if row >= cfg['rows']:
                    break

                x = col * cfg['width']
                y = row * cfg['height']

                log.info(f"Moving {table.name} to ({x}, {y})")
                self.move_window(table, x, y, cfg['width'], cfg['height'])

        elif layout == 'cascade':
            for i, table in enumerate(tables):
                x = 50 + i * 50
                y = 50 + i * 50
                self.move_window(table, x, y)

        elif layout == 'stack':
            for table in tables:
                self.move_window(table, 0, 0, screen_w, screen_h)

    # ========== LOBBY NAVIGATION ==========

    def open_rush_cash(self, stakes: str = None):
        """Navigate to Rush & Cash in the lobby

        Args:
            stakes: Optional stakes like "$0.01/$0.02" or "NL2"
        """
        lobby = self.get_main_lobby()
        if not lobby:
            log.error("Main lobby not found")
            return False

        self.focus_window(lobby)
        time.sleep(0.3)

        # Click on Rush & Cash tab (usually in left sidebar)
        # These positions are approximate - may need calibration
        rush_cash_tab_y = 200  # Relative Y position of Rush & Cash in sidebar
        self.click_in_window(lobby, 100, rush_cash_tab_y)

        log.info("Clicked Rush & Cash tab")
        return True

    def open_tournaments(self):
        """Navigate to Tournaments lobby"""
        lobby = self.get_main_lobby()
        if not lobby:
            log.error("Main lobby not found")
            return False

        self.focus_window(lobby)
        time.sleep(0.3)

        # Click on Tournaments tab
        tournaments_tab_y = 300
        self.click_in_window(lobby, 100, tournaments_tab_y)

        log.info("Clicked Tournaments tab")
        return True

    def register_tournament(self, tournament_name: str):
        """Register for a tournament by name

        This is a placeholder - actual implementation needs:
        1. Navigate to tournaments
        2. Search/find the tournament
        3. Click Register
        4. Confirm registration
        """
        log.info(f"Tournament registration for '{tournament_name}' - NOT IMPLEMENTED")
        # TODO: Implement OCR-based tournament finder
        # TODO: Click register button
        # TODO: Handle confirmation dialogs
        return False

    def open_spin_gold(self):
        """Navigate to Spin & Gold section in lobby"""
        lobby = self.get_main_lobby()
        if not lobby:
            log.error("Main lobby not found")
            return False

        self.focus_window(lobby)
        time.sleep(0.2)

        # Spin & Gold icon is in the TOP ICON ROW
        # Order: Home | All-In or Fold | SPIN & GOLD | Mystery Battle | Rush Cash...
        # SPIN & GOLD is the 3RD icon, around x=200-220
        spin_gold_tab_x = 210  # SPIN & GOLD icon (3rd from left)
        spin_gold_tab_y = 55   # Icon row center

        self.clicker.click(lobby.x * 2 + spin_gold_tab_x, lobby.y * 2 + spin_gold_tab_y)
        log.info("Clicked Spin & Gold icon in top bar")
        time.sleep(0.5)
        return True

    def register_spin_gold_1_dollar(self):
        """Register for $1 Spin & Gold tournament"""
        lobby = self.get_main_lobby()
        if not lobby:
            return False

        self.focus_window(lobby)
        time.sleep(0.2)

        # $1 Spin & Gold tile is in the game grid
        # Based on full screen: $1 tile is 3rd in top row
        # Grid starts around x=350, y=280 from lobby top-left
        # Each tile is ~120px wide
        # $1 tile center: x=430, y=340 (relative to lobby)
        dollar_1_tile_x = 430
        dollar_1_tile_y = 340

        # Click on $1 tile
        self.clicker.click(lobby.x * 2 + dollar_1_tile_x, lobby.y * 2 + dollar_1_tile_y)
        log.info("Clicked $1 Spin & Gold tile")
        time.sleep(0.5)

        # Click "Play Now" button on the tile (slightly lower)
        play_now_y = 400
        self.clicker.click(lobby.x * 2 + dollar_1_tile_x, lobby.y * 2 + play_now_y)
        log.info("Clicked Play Now for $1 Spin & Gold")
        time.sleep(0.5)

        return True

    def wait_for_table_window(self, timeout=30):
        """Wait for a new table window to appear"""
        start = time.time()
        initial_count = len(self.get_tables())

        while time.time() - start < timeout:
            self.scan_windows()
            current_count = len(self.get_tables())
            if current_count > initial_count:
                log.info(f"New table detected! ({current_count} tables)")
                return True
            time.sleep(0.5)

        log.warning(f"Timeout waiting for table ({timeout}s)")
        return False


class TableLayoutPresets:
    """Predefined table layout configurations"""

    @staticmethod
    def get_positions(layout: str, screen_size: Tuple[int, int],
                      num_tables: int) -> List[Tuple[int, int, int, int]]:
        """Get (x, y, width, height) for each table position

        Returns list of tuples for up to num_tables positions
        """
        w, h = screen_size

        presets = {
            # 4 tables - 2x2 grid
            '2x2': [
                (0, 0, w//2, h//2),
                (w//2, 0, w//2, h//2),
                (0, h//2, w//2, h//2),
                (w//2, h//2, w//2, h//2),
            ],
            # 6 tables - 3x2 grid
            '3x2': [
                (0, 0, w//3, h//2),
                (w//3, 0, w//3, h//2),
                (2*w//3, 0, w//3, h//2),
                (0, h//2, w//3, h//2),
                (w//3, h//2, w//3, h//2),
                (2*w//3, h//2, w//3, h//2),
            ],
            # 9 tables - 3x3 grid
            '3x3': [
                (0, 0, w//3, h//3),
                (w//3, 0, w//3, h//3),
                (2*w//3, 0, w//3, h//3),
                (0, h//3, w//3, h//3),
                (w//3, h//3, w//3, h//3),
                (2*w//3, h//3, w//3, h//3),
                (0, 2*h//3, w//3, h//3),
                (w//3, 2*h//3, w//3, h//3),
                (2*w//3, 2*h//3, w//3, h//3),
            ],
            # 2 tables - side by side
            'side_by_side': [
                (0, 0, w//2, h),
                (w//2, 0, w//2, h),
            ],
            # 2 tables - top/bottom
            'top_bottom': [
                (0, 0, w, h//2),
                (0, h//2, w, h//2),
            ],
        }

        if layout in presets:
            return presets[layout][:num_tables]

        # Default: cascade
        return [(i*60, i*40, w-200, h-200) for i in range(num_tables)]


# CLI interface
if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO)

    auto = GGSystemAutomation()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == 'scan':
            windows = auto.scan_windows()
            for w in windows:
                print(f"{w.window_type.value}: {w.name} at ({w.x}, {w.y}) {w.width}x{w.height}")

        elif cmd == 'arrange':
            layout = sys.argv[2] if len(sys.argv) > 2 else '2x2'
            auto.arrange_tables(layout)

        elif cmd == 'rush':
            auto.open_rush_cash()

        elif cmd == 'tournaments':
            auto.open_tournaments()

        else:
            print("Commands: scan, arrange [layout], rush, tournaments")
    else:
        # Default: scan and print
        windows = auto.scan_windows()
        print(f"\nFound {len(windows)} windows:")
        for w in windows:
            print(f"  {w.window_type.value}: {w.name}")
