"""
Claude-controlled table setup automation.
Bypasses the buggy UI and directly configures templates via API.

Usage (from Claude):
    from sys_core.tools.claude_table_setup import ClaudeTableSetup

    setup = ClaudeTableSetup("Official GGSystem 6player")
    setup.auto_setup()  # Full automated setup
    # or step by step:
    setup.take_and_analyze_screenshot()
    setup.find_and_extract_gg_logo()
    setup.upload_template()
    setup.verify_template()
"""

import io
import os
import base64
import logging
from datetime import datetime

import cv2
import numpy as np
import requests
from PIL import Image, ImageGrab

log = logging.getLogger(__name__)


class ClaudeTableSetup:
    """
    Automated table setup tool for Claude to use.
    Directly interfaces with the template API, bypassing the buggy UI.
    """

    def __init__(self, table_name="Official GGSystem 6player"):
        self.table_name = table_name
        self.api_url = "https://dickreuter.com:7778/"
        self.screenshot = None
        self.gg_logo = None
        self.debug_dir = "/tmp/poker_debug"
        os.makedirs(self.debug_dir, exist_ok=True)

    def take_screenshot(self):
        """Take screenshot at the correct resolution using ImageGrab"""
        log.info("Taking screenshot...")
        self.screenshot = ImageGrab.grab()
        log.info(f"Screenshot captured: {self.screenshot.size}")

        # Save for debugging
        path = f"{self.debug_dir}/screenshot_{datetime.now().strftime('%H%M%S')}.png"
        self.screenshot.save(path)
        log.info(f"Screenshot saved to {path}")

        return self.screenshot

    def find_gg_logo_by_color(self, screenshot=None):
        """
        Find GG logo by looking for its distinctive red/orange color.
        The GG logo text is typically red (#FF4444 or similar).
        """
        if screenshot is None:
            screenshot = self.screenshot

        img = np.array(screenshot)
        # Convert RGB to HSV for better color detection
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

        # Red color range (GG logo is red/orange)
        lower_red1 = np.array([0, 100, 100])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([160, 100, 100])
        upper_red2 = np.array([180, 255, 255])

        # Create masks for red color
        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        mask = mask1 + mask2

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter by size - GG logo is typically 30-80 pixels
        candidates = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if 500 < area < 10000 and 0.5 < w/h < 2.0:  # Reasonable logo size
                candidates.append((x, y, w, h, area))

        if candidates:
            # Sort by area and take the best match
            candidates.sort(key=lambda c: c[4], reverse=True)
            x, y, w, h, _ = candidates[0]
            log.info(f"Found potential GG logo at ({x}, {y}) size {w}x{h}")
            return x, y, w, h

        log.warning("Could not find GG logo by color detection")
        return None

    def find_gg_text_area(self, screenshot=None):
        """
        Find the "GG Rush & Cash" header text area.
        Searches for dark header bar with text.
        """
        if screenshot is None:
            screenshot = self.screenshot

        img = np.array(screenshot)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Look for dark regions (header bar is usually dark)
        _, thresh = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)

        # Find horizontal dark bars
        kernel = np.ones((5, 100), np.uint8)
        dilated = cv2.dilate(thresh, kernel, iterations=1)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter for header-like shapes (wide, not too tall)
        candidates = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 200 and 20 < h < 80:  # Header bar dimensions
                candidates.append((x, y, w, h))

        if candidates:
            # Take the topmost candidate
            candidates.sort(key=lambda c: c[1])
            x, y, w, h = candidates[0]
            log.info(f"Found potential header bar at ({x}, {y}) size {w}x{h}")
            return x, y, w, h

        return None

    def extract_region(self, x1, y1, x2, y2, screenshot=None):
        """Extract a region from screenshot"""
        if screenshot is None:
            screenshot = self.screenshot

        region = screenshot.crop((x1, y1, x2, y2))
        log.info(f"Extracted region ({x1}, {y1}) to ({x2}, {y2}): {region.size}")
        return region

    def upload_template_image(self, image, label="topleft_corner"):
        """Upload image directly to API"""
        log.info(f"Uploading {label} to template '{self.table_name}'...")

        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        encoded = base64.b64encode(img_bytes.getvalue()).decode('utf-8')

        try:
            response = requests.post(
                self.api_url + "update_table_image",
                json={
                    'pil_image': encoded,
                    'label': label,
                    'table_name': self.table_name
                },
                timeout=30
            )
            success = response.status_code == 200
            log.info(f"Upload {'SUCCESS' if success else 'FAILED'}: {response.status_code}")
            return success
        except Exception as e:
            log.error(f"Upload failed: {e}")
            return False

    def get_current_template(self, label="topleft_corner"):
        """Download current template from API"""
        try:
            response = requests.post(
                self.api_url + "get_table",
                params={'table_name': self.table_name},
                timeout=30
            )
            data = response.json()
            if label in data:
                img_data = base64.b64decode(data[label])
                return Image.open(io.BytesIO(img_data))
        except Exception as e:
            log.error(f"Failed to get template: {e}")
        return None

    def test_template_match(self):
        """Test if current template can find the table"""
        log.info("Testing template match...")

        # Take fresh screenshot
        screenshot = ImageGrab.grab()
        screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGR2RGB)

        # Get current template
        template_pil = self.get_current_template()
        if template_pil is None:
            log.error("No template found!")
            return False, None, None

        template_cv = cv2.cvtColor(np.array(template_pil), cv2.COLOR_BGR2RGB)

        # Run template matching
        res = cv2.matchTemplate(screenshot_cv, template_cv, cv2.TM_SQDIFF_NORMED)
        min_val, _, min_loc, _ = cv2.minMaxLoc(res)

        # Check threshold
        threshold = 0.01
        success = min_val <= threshold

        log.info(f"Match score: {min_val:.6f} (threshold: {threshold})")
        log.info(f"Match location: {min_loc}")
        log.info(f"Result: {'SUCCESS' if success else 'FAILED'}")

        return success, min_val, min_loc

    def test_with_adaptive_threshold(self):
        """Test template with multiple thresholds"""
        from sys_core.tools.screen_operations import find_template_with_adaptive_threshold

        screenshot = ImageGrab.grab()
        screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGR2RGB)

        template_pil = self.get_current_template()
        if template_pil is None:
            return False, None

        template_cv = cv2.cvtColor(np.array(template_pil), cv2.COLOR_BGR2RGB)

        count, points, bestFit, min_val, used_threshold = find_template_with_adaptive_threshold(
            template_cv, screenshot_cv
        )

        if count == 1:
            log.info(f"SUCCESS: Found table with threshold {used_threshold}")
            return True, used_threshold
        else:
            log.warning(f"FAILED: Best score was {min_val:.6f}")
            return False, None

    def auto_setup(self):
        """
        Fully automated setup process:
        1. Take screenshot
        2. Find GG logo
        3. Extract and upload
        4. Verify
        """
        log.info("=" * 50)
        log.info("Starting automated table setup")
        log.info("=" * 50)

        # Step 1: Take screenshot
        self.take_screenshot()

        # Step 2: Try to find GG logo by color
        result = self.find_gg_logo_by_color()
        if result:
            x, y, w, h = result
            # Add padding around the logo
            padding = 5
            self.gg_logo = self.extract_region(
                max(0, x - padding),
                max(0, y - padding),
                x + w + padding,
                y + h + padding
            )

            # Save for inspection
            self.gg_logo.save(f"{self.debug_dir}/extracted_logo.png")
            log.info(f"Extracted logo saved to {self.debug_dir}/extracted_logo.png")

            # Step 3: Upload
            if self.upload_template_image(self.gg_logo):
                # Step 4: Verify
                success, score, loc = self.test_template_match()
                if success:
                    log.info("=" * 50)
                    log.info("SETUP COMPLETE - Template is working!")
                    log.info("=" * 50)
                    return True
                else:
                    log.warning(f"Template uploaded but match failed (score: {score})")
        else:
            log.warning("Could not auto-detect GG logo")
            log.info("Manual extraction may be needed")

        return False

    def manual_extract_and_upload(self, x1, y1, x2, y2):
        """
        Manually extract a region and upload it as the top-left corner template.
        Use when auto-detection fails.
        """
        if self.screenshot is None:
            self.take_screenshot()

        self.gg_logo = self.extract_region(x1, y1, x2, y2)
        self.gg_logo.save(f"{self.debug_dir}/manual_extract.png")

        if self.upload_template_image(self.gg_logo):
            success, score, loc = self.test_template_match()
            return success, score
        return False, None


def quick_test():
    """Quick test function for Claude to run"""
    setup = ClaudeTableSetup()
    success, score, loc = setup.test_template_match()
    print(f"Template match: {'OK' if success else 'FAILED'} (score: {score})")
    return success


def quick_setup():
    """Quick setup function for Claude to run"""
    setup = ClaudeTableSetup()
    return setup.auto_setup()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    quick_test()
