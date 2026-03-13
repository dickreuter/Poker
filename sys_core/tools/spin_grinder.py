"""
SPIN & GOLD GRINDER - Automated multi-table poker grinding
Uses visual detection (NO hardcoded coordinates)
"""
import logging
import subprocess
import time
import cv2
import numpy as np
from PIL import ImageGrab
from pynput.mouse import Button, Controller

log = logging.getLogger(__name__)
mouse = Controller()

class SpinGrinder:
    """Automated Spin & Gold grinder with visual detection"""

    def __init__(self, max_tables=2, stake=1.0):
        self.max_tables = max_tables
        self.stake = stake
        self.games_played = 0
        self.running = False

    def focus_ggpoker(self):
        subprocess.run(['osascript', '-e',
            'tell application "System Events" to tell process "GGnet" to set frontmost to true'],
            capture_output=True)
        time.sleep(0.2)

    def get_windows(self):
        """Get all GGSystem window names"""
        script = '''
        tell application "System Events"
            tell process "GGnet"
                set output to ""
                repeat with w in windows
                    set output to output & name of w & "\\n"
                end repeat
                return output
            end tell
        end tell
        '''
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        return [w.strip() for w in result.stdout.strip().split('\n') if w.strip()]

    def count_active_tables(self):
        """Count Spin & Gold tables currently open"""
        windows = self.get_windows()
        return len([w for w in windows if 'Spin' in w and 'Blinds' in w])

    def find_buttons_by_color(self, screenshot, color='green'):
        """Find buttons by HSV color"""
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        colors = {
            'green': (np.array([35, 80, 80]), np.array([85, 255, 255])),
            'gray': (np.array([0, 0, 40]), np.array([180, 50, 120])),
        }

        lower, upper = colors.get(color, colors['green'])
        mask = cv2.inRange(hsv, lower, upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        buttons = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 2000:
                x, y, w, h = cv2.boundingRect(cnt)
                if 50 < w < 400 and 20 < h < 100:
                    # Calculate center in PIXELS first, then convert to POINTS
                    center_x_px = x + w // 2
                    center_y_px = y + h // 2
                    buttons.append({
                        'screen_pt': (center_x_px // 2, center_y_px // 2),
                        'area': area,
                        'y': y,
                        'x': x
                    })
        return buttons

    def click(self, pos, label=""):
        """Click at screen position (in POINTS)"""
        self.focus_ggpoker()
        mouse.position = pos
        time.sleep(0.05)
        mouse.click(Button.left)
        log.info(f"Clicked {label} at {pos}")

    def get_lobby_window_bounds(self):
        """Get the GGSystem main lobby window bounds"""
        script = '''
        tell application "System Events"
            tell process "GGnet"
                repeat with w in windows
                    set winName to name of w as text
                    if winName contains "GGPoker" then
                        set winPos to position of w
                        set winSize to size of w
                        return (item 1 of winPos as text) & "," & (item 2 of winPos as text) & "," & (item 1 of winSize as text) & "," & (item 2 of winSize as text)
                    end if
                end repeat
            end tell
        end tell
        '''
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        if result.stdout.strip():
            # Fix Unicode minus sign (−) that macOS returns instead of ASCII minus (-)
            stdout = result.stdout.strip().replace('−', '-').replace('–', '-')
            parts = stdout.split(',')
            if len(parts) == 4:
                return {
                    'x': int(parts[0]),
                    'y': int(parts[1]),
                    'w': int(parts[2]),
                    'h': int(parts[3])
                }
        return None

    def click_stake_tile(self, stake):
        """Click on the stake tile in the lobby

        The Spin & Gold lobby has small stake filter buttons at the top-left
        of the tile grid area. These show $0.25, $1.00, etc.
        """
        # Stake filter positions (small text buttons at top of tile grid)
        # These are above the actual prize tiles
        stake_positions = {
            0.25: (0.22, 0.22),  # First stake filter "$0.25"
            1.0:  (0.30, 0.22),  # Second stake filter "$1.00"
            5.0:  (0.38, 0.22),  # Third stake filter "$5.00"
            10.0: (0.46, 0.22),  # Fourth stake filter "$10"
        }

        bounds = self.get_lobby_window_bounds()
        if not bounds:
            log.warning("Could not get lobby window bounds")
            return False

        # If exact stake not found, try to click on the closest tile
        if stake not in stake_positions:
            log.warning(f"Stake ${stake} not in known positions")
            # Try clicking on the leftmost low-stake tile
            if stake <= 1.0:
                stake = 1.0 if 1.0 in stake_positions else 0.25
            else:
                stake = 5.0

        pct_x, pct_y = stake_positions.get(stake, (0.30, 0.22))
        click_x = bounds['x'] + int(bounds['w'] * pct_x)
        click_y = bounds['y'] + int(bounds['h'] * pct_y)

        log.info(f"Lobby bounds: {bounds}")
        self.click((click_x, click_y), f"${stake} stake filter")
        return True

    def register_for_game(self):
        """Register for a Spin & Gold game via Game List menu"""
        log.info("Registering for Spin & Gold...")

        self.focus_ggpoker()
        time.sleep(0.3)

        bounds = self.get_lobby_window_bounds()
        if not bounds:
            log.warning("Could not get lobby window bounds")
            return False

        # Navigate to Game List (left menu, ~108px from lobby top)
        game_list_x = bounds['x'] + 55
        game_list_y = bounds['y'] + 108
        self.click((game_list_x, game_list_y), "Game List")
        time.sleep(1)

        # Click on "Recent Game: Spin & Gold $1" in the "For You" section
        # This is at ~95px from left, ~321px from lobby top
        spin_x = bounds['x'] + 95
        spin_y = bounds['y'] + 321
        self.click((spin_x, spin_y), f"Spin & Gold ${self.stake}")

        # Wait for table to open (search + match can take 30-60 seconds)
        log.info("Waiting for table to open (searching for players)...")

        # Check periodically for table
        for i in range(6):
            time.sleep(10)
            if self.count_active_tables() > 0:
                self.games_played += 1
                log.info(f"Game #{self.games_played} started!")
                return True
            log.info(f"Still searching... ({(i+1)*10}s)")

        log.warning("Table didn't open - no players available (try again later)")
        return False

    def handle_game_end(self):
        """Handle end-of-game dialog - click Play Again"""
        log.info("Checking for game end dialog...")

        self.focus_ggpoker()
        screenshot = ImageGrab.grab()
        green_buttons = self.find_buttons_by_color(screenshot, 'green')

        if len(green_buttons) >= 1:
            # Play Again is typically the LEFT-most green button
            green_buttons.sort(key=lambda b: b['x'])
            play_again = green_buttons[0]
            self.click(play_again['screen_pt'], "Play Again")
            log.info("Clicked Play Again")
            return True
        return False

    def run(self):
        """Main grinder loop"""
        log.info("=" * 50)
        log.info("SPIN GRINDER STARTED")
        log.info(f"Max tables: {self.max_tables}")
        log.info(f"Stake: ${self.stake}")
        log.info("=" * 50)

        self.running = True
        last_register_time = 0

        while self.running:
            try:
                active_tables = self.count_active_tables()

                # Register for more games if needed
                if active_tables < self.max_tables:
                    if time.time() - last_register_time > 15:  # Cooldown
                        if self.register_for_game():
                            last_register_time = time.time()
                        time.sleep(2)

                # Check for end-of-game dialogs
                self.handle_game_end()

                time.sleep(1)

            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"Error: {e}")
                time.sleep(2)

        log.info(f"Grinder stopped. Games played: {self.games_played}")


def main():
    from sys_core.tools.helper import init_logger
    init_logger(screenlevel=logging.INFO, filename='spin_grinder', logdir='log')

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-tables', type=int, default=2)
    parser.add_argument('--stake', type=float, default=1.0)
    args = parser.parse_args()

    grinder = SpinGrinder(max_tables=args.max_tables, stake=args.stake)

    print("=" * 50)
    print("SPIN & GOLD GRINDER")
    print(f"Max tables: {args.max_tables}")
    print(f"Stake: ${args.stake}")
    print("Press Ctrl+C to stop")
    print("=" * 50)

    grinder.run()


if __name__ == "__main__":
    main()
