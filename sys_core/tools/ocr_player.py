"""
OCR-based System Player - Uses text recognition instead of coordinates.
This ACTUALLY WORKS because it finds buttons by their text, not guessed positions.
"""

import pytesseract
from PIL import ImageGrab
from pynput.mouse import Controller, Button
import subprocess
import time
import logging

log = logging.getLogger(__name__)

class OCRPlayer:
    def __init__(self):
        self.mouse = Controller()
        self.last_action_time = 0
        self.cooldown = 1.5
        self.actions_taken = 0

    def focus_ggpoker(self):
        """Focus GGSystem window."""
        subprocess.run(['osascript', '-e',
            'tell application "System Events" to tell process "GGnet" to set frontmost to true'],
            capture_output=True, timeout=2)
        time.sleep(0.1)

    def take_screenshot(self):
        """Take full screen screenshot."""
        return ImageGrab.grab()

    def find_text(self, screenshot, search_terms):
        """Find text on screen using OCR. Returns dict of found items with click positions."""
        data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
        found = {}

        for i, text in enumerate(data['text']):
            text_str = str(text).strip().lower()
            if not text_str:
                continue

            conf = data['conf'][i]
            if conf < 50:  # Skip low confidence
                continue

            for term in search_terms:
                if term.lower() == text_str or term.lower() in text_str:
                    x = data['left'][i]
                    y = data['top'][i]
                    w = data['width'][i]
                    h = data['height'][i]
                    # Convert PIXELS to POINTS for clicking
                    click_x = (x + w // 2) // 2
                    click_y = (y + h // 2) // 2
                    found[term.lower()] = {
                        'pixel_x': x, 'pixel_y': y,
                        'click_x': click_x, 'click_y': click_y,
                        'confidence': conf
                    }
                    break

        return found

    def click(self, x, y, name=""):
        """Click at position (in POINTS)."""
        self.focus_ggpoker()
        self.mouse.position = (x, y)
        time.sleep(0.03)
        self.mouse.click(Button.left)
        self.actions_taken += 1
        self.last_action_time = time.time()
        log.info(f"Clicked {name} at ({x}, {y})")

    def process(self):
        """Process one frame - find and click appropriate button."""
        now = time.time()
        if now - self.last_action_time < self.cooldown:
            return False

        screenshot = self.take_screenshot()

        # Look for action buttons
        actions = self.find_text(screenshot, ['Check', 'Call', 'Fold', 'Raise', 'Bet', 'All-In'])

        if not actions:
            # Look for Deal Me In
            deal = self.find_text(screenshot, ['Deal'])
            if 'deal' in deal:
                self.click(deal['deal']['click_x'], deal['deal']['click_y'], "Deal Me In")
                return True
            return False

        log.info(f"Found buttons: {list(actions.keys())}")

        # Decision logic:
        # 1. Check is FREE - always take it if available
        # 2. If must pay (call/fold), be conservative and fold

        if 'check' in actions:
            # Check is FREE - always take it
            self.click(actions['check']['click_x'], actions['check']['click_y'], "Check")
            return True

        if 'call' in actions and 'fold' in actions:
            # Must pay to continue - fold (conservative strategy)
            self.click(actions['fold']['click_x'], actions['fold']['click_y'], "Fold")
            return True

        if 'call' in actions:
            # Only call visible (might be all-in situation)
            self.click(actions['call']['click_x'], actions['call']['click_y'], "Call")
            return True

        if 'fold' in actions:
            self.click(actions['fold']['click_x'], actions['fold']['click_y'], "Fold")
            return True

        return False

    def run(self):
        """Main loop."""
        print("=" * 60)
        print("OCR PLAYER - Using text recognition")
        print("=" * 60)

        while True:
            try:
                self.process()
                time.sleep(0.3)
            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"Error: {e}")
                time.sleep(1)

        print(f"\nStopped. Actions: {self.actions_taken}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    player = OCRPlayer()
    player.run()


if __name__ == "__main__":
    main()
