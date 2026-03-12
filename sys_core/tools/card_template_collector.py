"""
Card Template Collector - Captures card images from gameplay to update templates.

Run this while playing and it will:
1. Watch for visible cards
2. Extract and identify them
3. Save to database when all 52 are collected
"""

import os
import io
import time
import base64
import logging
from datetime import datetime
from PIL import Image, ImageGrab
import cv2
import numpy as np
import requests

log = logging.getLogger(__name__)

# All 52 cards
RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
SUITS = ['s', 'h', 'd', 'c']  # spades, hearts, diamonds, clubs
ALL_CARDS = [r.lower() + s for r in RANKS for s in SUITS]


class CardTemplateCollector:
    """Collects card templates from live gameplay."""

    def __init__(self, table_name="Official GGSystem 6player"):
        self.table_name = table_name
        self.collected = {}  # card_key -> PIL Image
        self.save_dir = "/tmp/poker_cards"
        os.makedirs(self.save_dir, exist_ok=True)

        # Card positions (relative to table top-left corner at 14, 850)
        self.tlc = (14, 850)
        # Updated card positions from our analysis
        self.left_card_pos = (800, 955, 835, 1005)   # x1, y1, x2, y2
        self.right_card_pos = (885, 955, 920, 1005)

    def take_screenshot(self):
        """Take screenshot and crop to table area."""
        screenshot = ImageGrab.grab()
        return screenshot

    def extract_card_image(self, screenshot, position):
        """Extract card rank/suit area from screenshot."""
        x1, y1, x2, y2 = position
        # Position is relative to cropped table, add tlc offset
        card = screenshot.crop((self.tlc[0] + x1 - 750, self.tlc[1] + y1 - 880,
                                self.tlc[0] + x2 - 750, self.tlc[1] + y2 - 880))
        return card

    def identify_card_by_color(self, card_img):
        """Identify suit by color (red=hearts/diamonds, black=spades/clubs)."""
        img = np.array(card_img)

        # Check for red pixels (hearts/diamonds)
        red_mask = (img[:,:,0] > 150) & (img[:,:,1] < 100) & (img[:,:,2] < 100)
        red_pixels = np.sum(red_mask)

        # If significant red, it's hearts or diamonds
        is_red = red_pixels > 50

        return 'red' if is_red else 'black'

    def get_card_from_region(self, screenshot, region_coords):
        """Extract a card image from specific coordinates."""
        x1, y1, x2, y2 = region_coords
        return screenshot.crop((x1, y1, x2, y2))

    def capture_current_cards(self):
        """Capture cards currently visible on screen."""
        screenshot = self.take_screenshot()

        # Extract left and right card positions
        left_card = screenshot.crop(self.left_card_pos)
        right_card = screenshot.crop(self.right_card_pos)

        return left_card, right_card

    def save_card(self, card_key, card_img):
        """Save a captured card."""
        if card_key not in ALL_CARDS:
            log.warning(f"Invalid card key: {card_key}")
            return False

        self.collected[card_key] = card_img
        path = f"{self.save_dir}/{card_key}.png"
        card_img.save(path)
        log.info(f"Saved {card_key} to {path}")
        return True

    def upload_card(self, card_key, card_img):
        """Upload a single card template to the API."""
        img_bytes = io.BytesIO()
        card_img.save(img_bytes, format='PNG')
        encoded = base64.b64encode(img_bytes.getvalue()).decode('utf-8')

        try:
            response = requests.post(
                "https://dickreuter.com:7778/update_table_image",
                json={
                    'pil_image': encoded,
                    'label': card_key,
                    'table_name': self.table_name
                },
                timeout=30
            )
            success = response.status_code == 200
            if success:
                log.info(f"Uploaded {card_key}")
            else:
                log.error(f"Failed to upload {card_key}: {response.status_code}")
            return success
        except Exception as e:
            log.error(f"Upload error for {card_key}: {e}")
            return False

    def upload_all_collected(self):
        """Upload all collected cards to API."""
        success_count = 0
        for card_key, card_img in self.collected.items():
            if self.upload_card(card_key, card_img):
                success_count += 1
        log.info(f"Uploaded {success_count}/{len(self.collected)} cards")
        return success_count

    def get_status(self):
        """Get collection status."""
        collected = set(self.collected.keys())
        missing = set(ALL_CARDS) - collected
        return {
            'collected': len(collected),
            'total': 52,
            'missing': sorted(missing),
            'collected_cards': sorted(collected)
        }

    def load_existing(self):
        """Load any previously saved cards."""
        for card_key in ALL_CARDS:
            path = f"{self.save_dir}/{card_key}.png"
            if os.path.exists(path):
                self.collected[card_key] = Image.open(path)
        log.info(f"Loaded {len(self.collected)} existing cards")


def manual_capture(card_key):
    """Manually capture a specific card that's currently visible."""
    collector = CardTemplateCollector()

    screenshot = ImageGrab.grab()

    # Show where to look
    print(f"Looking for {card_key} at positions:")
    print(f"  Left card: {collector.left_card_pos}")
    print(f"  Right card: {collector.right_card_pos}")

    # Extract both positions
    left = screenshot.crop(collector.left_card_pos)
    right = screenshot.crop(collector.right_card_pos)

    left.save(f"/tmp/poker_cards/capture_left.png")
    right.save(f"/tmp/poker_cards/capture_right.png")

    print(f"\nSaved captures to /tmp/poker_cards/")
    print(f"Check which one is {card_key} and run:")
    print(f"  save_card('{card_key}', 'left')  # or 'right'")


def save_card_from_capture(card_key, position='left'):
    """Save a captured card after manual verification."""
    collector = CardTemplateCollector()

    if position == 'left':
        img = Image.open("/tmp/poker_cards/capture_left.png")
    else:
        img = Image.open("/tmp/poker_cards/capture_right.png")

    collector.save_card(card_key, img)
    collector.upload_card(card_key, img)
    print(f"Saved and uploaded {card_key}")


def auto_collect_loop(duration_seconds=300):
    """
    Run automatic card collection for specified duration.
    Takes screenshots and prompts for card identification.
    """
    collector = CardTemplateCollector()
    collector.load_existing()

    print(f"Starting card collection for {duration_seconds}s")
    print(f"Already have: {len(collector.collected)}/52 cards")
    print("=" * 50)

    start = time.time()
    last_capture = 0

    while time.time() - start < duration_seconds:
        # Capture every 2 seconds
        if time.time() - last_capture > 2:
            screenshot = ImageGrab.grab()

            # Extract cards
            left = screenshot.crop(collector.left_card_pos)
            right = screenshot.crop(collector.right_card_pos)

            # Save for review
            timestamp = datetime.now().strftime("%H%M%S")
            left.save(f"{collector.save_dir}/auto_left_{timestamp}.png")
            right.save(f"{collector.save_dir}/auto_right_{timestamp}.png")

            last_capture = time.time()

            status = collector.get_status()
            print(f"\r[{int(time.time()-start)}s] Collected: {status['collected']}/52", end="")

        time.sleep(0.5)

    print(f"\n\nCollection complete!")
    print(f"Cards saved to {collector.save_dir}")
    return collector.get_status()


if __name__ == "__main__":
    # Quick test
    collector = CardTemplateCollector()
    collector.load_existing()
    print(collector.get_status())
