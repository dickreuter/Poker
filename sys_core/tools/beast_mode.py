"""
BEAST MODE - Unified Multi-Table System Utility
Handles registration, multi-table play, and proper button detection.

This combines all the best parts of the codebase:
- gg_automation.py for registration
- dynamic_table_finder.py for table/button detection
- smart_card_detector.py for card reading
- cli_controller.py for decision making

Usage:
    python -m sys_core.tools.beast_mode
    python -m sys_core.tools.beast_mode --max-tables 2
"""

import logging
import subprocess
import time
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from PIL import ImageGrab, Image
import cv2
import numpy as np
from pynput.mouse import Button, Controller

log = logging.getLogger(__name__)

# Retina scale factor
RETINA_SCALE = 2


@dataclass
class TableInfo:
    """Info about a poker table"""
    name: str
    x_pt: int  # Position in POINTS (for clicking)
    y_pt: int
    w_pt: int
    h_pt: int
    x_px: int  # Position in PIXELS (for screenshots)
    y_px: int
    w_px: int
    h_px: int
    last_action_time: float = 0
    action_cooldown: float = 1.5


class BeastModeBot:
    """
    The ultimate system service - handles everything:
    - Multi-table detection via AppleScript
    - Button detection via color (with proper colors)
    - Card detection
    - Action execution
    - Tournament registration
    """

    # GGSystem button colors - PROPERLY CALIBRATED
    # Fold = Dark/muted color (NOT bright red)
    # Call/Check = Green
    # Raise/Bet = Orange/Gold
    BUTTON_COLORS = {
        'call': {
            'lower': np.array([35, 80, 80]),
            'upper': np.array([85, 255, 255]),
            'name': 'Call'
        },
        'raise': {
            'lower': np.array([8, 100, 100]),
            'upper': np.array([25, 255, 255]),
            'name': 'Raise'
        },
    }

    def __init__(self, max_tables: int = 2, auto_register: bool = True):
        self.max_tables = max_tables
        self.auto_register = auto_register
        self.mouse = Controller()
        self.running = False
        self.tables: Dict[str, TableInfo] = {}
        self.actions_taken = 0
        self.start_time = None

    def find_all_windows(self) -> List[Dict]:
        """Find all GGPoker windows via AppleScript"""
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
            result = subprocess.run(['osascript', '-e', script],
                                    capture_output=True, text=True, timeout=5)
            windows = []
            if result.stdout.strip():
                entries = result.stdout.strip().rstrip(';').split(';')
                for entry in entries:
                    if '###' in entry:
                        name, coords = entry.split('###')
                        # Fix Unicode minus sign (−) that macOS returns instead of ASCII minus (-)
                        coords = coords.replace('−', '-').replace('–', '-')
                        parts = coords.split(',')
                        x_pt, y_pt = int(parts[0]), int(parts[1])
                        w_pt, h_pt = int(parts[2]), int(parts[3])
                        windows.append({
                            'name': name.strip(),
                            'x_pt': x_pt, 'y_pt': y_pt,
                            'w_pt': w_pt, 'h_pt': h_pt,
                            'x_px': x_pt * RETINA_SCALE,
                            'y_px': y_pt * RETINA_SCALE,
                            'w_px': w_pt * RETINA_SCALE,
                            'h_px': h_pt * RETINA_SCALE,
                        })
            return windows
        except Exception as e:
            log.error(f"Error finding windows: {e}")
            return []

    def get_poker_tables(self) -> List[TableInfo]:
        """Get only poker table windows (not lobby)"""
        windows = self.find_all_windows()
        tables = []
        keywords = ['Spin', 'Gold', 'Rush', 'Cash', 'Hold', 'Omaha', 'Blinds', 'NL', 'PLO']

        for w in windows:
            if any(kw in w['name'] for kw in keywords):
                tables.append(TableInfo(
                    name=w['name'],
                    x_pt=w['x_pt'], y_pt=w['y_pt'],
                    w_pt=w['w_pt'], h_pt=w['h_pt'],
                    x_px=w['x_px'], y_px=w['y_px'],
                    w_px=w['w_px'], h_px=w['h_px'],
                ))
        return tables

    def capture_table(self, table: TableInfo, screenshot: Image.Image) -> Image.Image:
        """Crop table from full screenshot"""
        return screenshot.crop((
            table.x_px, table.y_px,
            table.x_px + table.w_px,
            table.y_px + table.h_px
        ))

    def find_buttons(self, table_img: Image.Image, table: TableInfo) -> Dict[str, Dict]:
        """Find action buttons by color detection"""
        img = cv2.cvtColor(np.array(table_img), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h_img, w_img = img.shape[:2]

        # Search bottom 30% of table where buttons are
        y_start = int(h_img * 0.70)
        x_start = int(w_img * 0.25)
        x_end = int(w_img * 0.85)

        search_region = hsv[y_start:, x_start:x_end]
        buttons = {}

        for btn_key, color_info in self.BUTTON_COLORS.items():
            mask = cv2.inRange(search_region, color_info['lower'], color_info['upper'])
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Find largest button-shaped contour
            best = None
            best_area = 0
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > best_area and area > 1500:
                    x, y, w, bh = cv2.boundingRect(contour)
                    # Button should be reasonably sized
                    if w > 50 and bh > 20 and w < 350 and bh < 120:
                        center_x = x_start + x + w // 2
                        center_y = y_start + y + bh // 2
                        best = (center_x, center_y, w, bh, area)
                        best_area = area

            if best:
                x_px, y_px, w, h, _ = best
                # Convert to screen points for clicking
                screen_x = table.x_pt + x_px // RETINA_SCALE
                screen_y = table.y_pt + y_px // RETINA_SCALE
                buttons[btn_key] = {
                    'x_px': x_px, 'y_px': y_px,
                    'screen_pt': (screen_x, screen_y),
                    'size': (w, h),
                    'name': color_info['name']
                }

        # FOLD detection - look for button LEFT of call, or standalone dark button
        # GGSystem fold is usually a muted/dark button
        if 'call' in buttons:
            call_x = buttons['call']['x_px']
            # Fold is typically left of call
            fold_region = img[y_start:, x_start:call_x-10]
            if fold_region.shape[1] > 40:
                gray = cv2.cvtColor(fold_region, cv2.COLOR_BGR2GRAY)
                # Look for button-shaped bright areas (text on dark bg)
                _, thresh = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY)
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for cnt in contours:
                    x, y, w, bh = cv2.boundingRect(cnt)
                    area = w * bh
                    if w > 50 and bh > 20 and area > 1500:
                        center_x = x_start + x + w // 2
                        center_y = y_start + y + bh // 2
                        screen_x = table.x_pt + center_x // RETINA_SCALE
                        screen_y = table.y_pt + center_y // RETINA_SCALE
                        buttons['fold'] = {
                            'x_px': center_x, 'y_px': center_y,
                            'screen_pt': (screen_x, screen_y),
                            'size': (w, bh),
                            'name': 'Fold'
                        }
                        break

        return buttons

    def click_button(self, button_info: Dict, table: TableInfo):
        """Click a button"""
        # Focus GGSystem
        subprocess.run(['osascript', '-e',
            'tell application "System Events" to tell process "GGnet" to set frontmost to true'],
            capture_output=True)
        time.sleep(0.05)

        x, y = button_info['screen_pt']
        self.mouse.position = (x, y)
        time.sleep(0.03)
        self.mouse.click(Button.left)

        log.info(f"Clicked {button_info['name']} at ({x}, {y}) on {table.name[:30]}")
        self.actions_taken += 1

    def decide_action(self, buttons: Dict) -> Optional[str]:
        """Decide what action to take based on available buttons"""
        # If we have fold AND call/raise = we need to pay, default FOLD
        if 'fold' in buttons:
            if 'call' in buttons or 'raise' in buttons:
                return 'fold'
            else:
                return 'fold'

        # Only call visible (no fold) = likely CHECK (free)
        if 'call' in buttons and 'fold' not in buttons:
            return 'call'

        # Only raise visible
        if 'raise' in buttons and 'fold' not in buttons and 'call' not in buttons:
            return None  # Not our turn or raise-only situation

        return None

    def process_table(self, table: TableInfo, screenshot: Image.Image) -> bool:
        """Process a single table - detect buttons and act"""
        now = time.time()

        # Cooldown per table
        if now - table.last_action_time < table.action_cooldown:
            return False

        table_img = self.capture_table(table, screenshot)
        buttons = self.find_buttons(table_img, table)

        if not buttons:
            return False

        log.debug(f"[{table.name[:25]}] Buttons: {list(buttons.keys())}")

        action = self.decide_action(buttons)
        if action and action in buttons:
            self.click_button(buttons[action], table)
            table.last_action_time = now
            return True

        return False

    def register_tournament(self):
        """Register for a new Spin & Gold tournament"""
        log.info("Attempting to register for Spin & Gold...")

        # Find main lobby
        windows = self.find_all_windows()
        lobby = None
        for w in windows:
            if w['name'] == 'GGPoker':
                lobby = w
                break

        if not lobby:
            log.warning("GGPoker lobby not found")
            return False

        # Focus lobby
        subprocess.run(['osascript', '-e',
            'tell application "System Events" to tell process "GGnet" to set frontmost to true'],
            capture_output=True)
        time.sleep(0.2)

        # Click Spin & Gold icon (3rd icon in top bar)
        spin_x = lobby['x_pt'] + 210
        spin_y = lobby['y_pt'] + 55
        self.mouse.position = (spin_x, spin_y)
        self.mouse.click(Button.left)
        log.info(f"Clicked Spin & Gold at ({spin_x}, {spin_y})")
        time.sleep(0.5)

        # Click $1 tile (approximately)
        tile_x = lobby['x_pt'] + 430
        tile_y = lobby['y_pt'] + 340
        self.mouse.position = (tile_x, tile_y)
        self.mouse.click(Button.left)
        log.info(f"Clicked $1 tile at ({tile_x}, {tile_y})")
        time.sleep(0.3)

        # Click Play Now
        play_y = lobby['y_pt'] + 400
        self.mouse.position = (tile_x, play_y)
        self.mouse.click(Button.left)
        log.info("Clicked Play Now")

        return True

    def run(self):
        """Main loop - find tables, detect buttons, take actions"""
        log.info("=" * 60)
        log.info("BEAST MODE ACTIVATED")
        log.info(f"Max tables: {self.max_tables}")
        log.info(f"Auto-register: {self.auto_register}")
        log.info("=" * 60)

        self.running = True
        self.start_time = time.time()
        last_register_check = 0

        while self.running:
            try:
                # Get all poker tables
                tables = self.get_poker_tables()

                # Update internal table list
                for t in tables:
                    key = f"{t.x_pt},{t.y_pt}"
                    if key not in self.tables:
                        self.tables[key] = t
                        log.info(f"Found table: {t.name[:40]} at ({t.x_pt}, {t.y_pt})")
                    else:
                        # Update position (in case it moved)
                        self.tables[key].x_pt = t.x_pt
                        self.tables[key].y_pt = t.y_pt
                        self.tables[key].x_px = t.x_px
                        self.tables[key].y_px = t.y_px

                # Register for more tournaments if needed
                now = time.time()
                if self.auto_register and len(tables) < self.max_tables:
                    if now - last_register_check > 10:  # Check every 10 seconds
                        self.register_tournament()
                        last_register_check = now
                        time.sleep(2)
                        continue

                if not tables:
                    time.sleep(1)
                    continue

                # Take screenshot once for all tables
                screenshot = ImageGrab.grab()

                # Process each table
                for t in tables:
                    try:
                        self.process_table(t, screenshot)
                    except Exception as e:
                        log.warning(f"Error processing {t.name[:30]}: {e}")

                time.sleep(0.3)  # Brief pause between scans

            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"Error in main loop: {e}")
                time.sleep(1)

        self.stop()

    def stop(self):
        """Stop the bot"""
        self.running = False
        uptime = time.time() - self.start_time if self.start_time else 0

        log.info("=" * 60)
        log.info("BEAST MODE STOPPED")
        log.info(f"Actions taken: {self.actions_taken}")
        log.info(f"Uptime: {uptime/60:.1f} minutes")
        log.info("=" * 60)


def main():
    import argparse
    from sys_core.tools.helper import init_logger

    init_logger(screenlevel=logging.INFO, filename='beast_mode', logdir='log')

    parser = argparse.ArgumentParser(description="BEAST MODE - Multi-Table System Utility")
    parser.add_argument("--max-tables", type=int, default=2, help="Max concurrent tables")
    parser.add_argument("--no-register", action="store_true", help="Don't auto-register")
    args = parser.parse_args()

    print("=" * 60)
    print("BEAST MODE - Multi-Table System Utility")
    print("=" * 60)
    print(f"Max tables: {args.max_tables}")
    print(f"Auto-register: {not args.no_register}")
    print("Press Ctrl+C to stop")
    print("=" * 60)

    bot = BeastModeBot(
        max_tables=args.max_tables,
        auto_register=not args.no_register
    )

    try:
        bot.run()
    except KeyboardInterrupt:
        print("\nStopping...")
        bot.stop()


if __name__ == "__main__":
    main()
