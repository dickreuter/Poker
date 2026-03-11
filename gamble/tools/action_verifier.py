"""
Action Verifier - Verify That Poker Bot Actions Succeeded

After clicking a button (Fold, Call, Bet), this module verifies
that the action actually took effect by checking for UI changes.

This prevents silent failures where the bot thinks it acted but
the click didn't register.

Verification methods:
1. Button disappearance - Fold/Call/Check buttons should vanish
2. UI state change - New hand dealt, pot changes, etc.
3. Retry on failure - If verification fails, retry the action

Usage:
    from gamble.tools.action_verifier import ActionVerifier

    verifier = ActionVerifier()

    # Before action
    before = ImageGrab.grab()

    # Execute action
    mouse.mouse_action("Fold", tlc)

    # Verify
    time.sleep(0.5)
    after = ImageGrab.grab()

    if verifier.verify_action("Fold", before, after, table_region):
        print("Action succeeded!")
    else:
        print("Action may have failed - retry needed")
"""

import logging
import time
from typing import Dict, Optional, Tuple, List

import cv2
import numpy as np
from PIL import Image, ImageGrab

from gamble.tools.button_detector import ButtonDetector
from gamble.tools import constants as const

log = logging.getLogger(__name__)


class ActionVerifier:
    """
    Verify that poker bot actions succeeded.

    Uses visual comparison to detect UI changes after an action.
    """

    def __init__(self):
        self.button_detector = ButtonDetector()
        self.last_verification = None

    def verify_action(self, action: str, before_screenshot: Image.Image,
                     after_screenshot: Image.Image,
                     table_region: Tuple[int, int, int, int]) -> bool:
        """
        Verify that an action had the expected effect.

        Args:
            action: The action that was taken ('Fold', 'Call', etc.)
            before_screenshot: Screenshot before action
            after_screenshot: Screenshot after action
            table_region: (x, y, width, height) of the table

        Returns:
            True if action appears to have succeeded
        """
        action_lower = action.lower().replace(' ', '_')

        # Get buttons before and after
        buttons_before = self.button_detector.find_all_buttons(before_screenshot, table_region)
        buttons_after = self.button_detector.find_all_buttons(after_screenshot, table_region)

        # Count visible buttons
        before_count = sum(1 for b in buttons_before.values() if b is not None)
        after_count = sum(1 for b in buttons_after.values() if b is not None)

        result = False

        if action in ['Fold', 'Call', 'Call2', 'Check']:
            # These actions should make buttons disappear
            if after_count < before_count:
                log.debug(f"Verification: Buttons reduced {before_count} -> {after_count}")
                result = True
            elif after_count == 0:
                log.debug("Verification: No buttons visible (expected for fold/call/check)")
                result = True
            else:
                # Check if the specific button we clicked is gone
                button_type = 'fold' if action == 'Fold' else 'call'
                if buttons_before.get(button_type) and not buttons_after.get(button_type):
                    log.debug(f"Verification: {button_type} button disappeared")
                    result = True

        elif action in ['Bet', 'BetPlus', 'Bet Bluff', 'Bet half pot', 'Bet pot', 'Bet max']:
            # Bet actions - UI might show confirmation or change
            # Check if something changed in the button area
            if after_count != before_count or self._significant_change(before_screenshot, after_screenshot, table_region):
                log.debug("Verification: UI changed after bet action")
                result = True

        else:
            # Unknown action - assume success if any change detected
            if self._significant_change(before_screenshot, after_screenshot, table_region):
                result = True

        self.last_verification = {
            'action': action,
            'success': result,
            'buttons_before': before_count,
            'buttons_after': after_count,
            'timestamp': time.time()
        }

        if result:
            log.info(f"Action '{action}' verified successfully")
        else:
            log.warning(f"Action '{action}' verification FAILED (buttons: {before_count} -> {after_count})")

        return result

    def _significant_change(self, before: Image.Image, after: Image.Image,
                           table_region: Tuple[int, int, int, int],
                           threshold: float = 0.05) -> bool:
        """
        Check if there was a significant visual change in the table area.

        Args:
            before: Screenshot before action
            after: Screenshot after action
            table_region: Table bounding box
            threshold: Minimum change ratio to be significant

        Returns:
            True if significant change detected
        """
        x, y, w, h = table_region

        # Crop to button area (bottom 35%)
        button_y = int(h * 0.65)
        try:
            before_crop = before.crop((x, y + button_y, x + w, y + h))
            after_crop = after.crop((x, y + button_y, x + w, y + h))
        except Exception:
            return False

        # Convert to numpy
        before_np = np.array(before_crop)
        after_np = np.array(after_crop)

        if before_np.shape != after_np.shape:
            return True  # Size change = definitely changed

        # Calculate difference
        diff = cv2.absdiff(before_np, after_np)
        diff_gray = cv2.cvtColor(diff, cv2.COLOR_RGB2GRAY)

        # Count changed pixels
        changed_pixels = np.sum(diff_gray > 30)  # Threshold for "changed"
        total_pixels = diff_gray.size

        change_ratio = changed_pixels / total_pixels

        log.debug(f"Visual change ratio: {change_ratio:.4f} (threshold: {threshold})")

        return change_ratio > threshold

    def wait_for_change(self, table_region: Tuple[int, int, int, int],
                       timeout: float = 3.0, check_interval: float = 0.2) -> bool:
        """
        Wait for a visual change in the table area.

        Useful for waiting until an action takes effect.

        Args:
            table_region: Table bounding box
            timeout: Maximum time to wait (seconds)
            check_interval: Time between checks (seconds)

        Returns:
            True if change detected within timeout
        """
        start_time = time.time()
        initial_screenshot = ImageGrab.grab()

        while time.time() - start_time < timeout:
            time.sleep(check_interval)
            current_screenshot = ImageGrab.grab()

            if self._significant_change(initial_screenshot, current_screenshot, table_region, threshold=0.03):
                log.debug(f"Change detected after {time.time() - start_time:.2f}s")
                return True

        log.warning(f"No change detected within {timeout}s")
        return False


class ActionRetrier:
    """
    Retry failed actions with exponential backoff.
    """

    def __init__(self, max_retries: int = 3, initial_delay: float = 0.5):
        """
        Initialize the retrier.

        Args:
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay between retries (seconds)
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.verifier = ActionVerifier()

    def execute_with_retry(self, action: str, execute_func, table_region: Tuple[int, int, int, int]) -> bool:
        """
        Execute an action with automatic retry on failure.

        Args:
            action: Action name ('Fold', 'Call', etc.)
            execute_func: Function that executes the action (no args)
            table_region: Table bounding box for verification

        Returns:
            True if action eventually succeeded
        """
        delay = self.initial_delay

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                log.info(f"Retry attempt {attempt} for {action}")

            # Capture before state
            before = ImageGrab.grab()

            # Execute action
            execute_func()

            # Wait for UI to update
            time.sleep(0.5)

            # Capture after state
            after = ImageGrab.grab()

            # Verify
            if self.verifier.verify_action(action, before, after, table_region):
                if attempt > 0:
                    log.info(f"Action '{action}' succeeded on retry {attempt}")
                return True

            # Failed - wait before retry
            if attempt < self.max_retries:
                log.warning(f"Action '{action}' failed, retrying in {delay:.1f}s")
                time.sleep(delay)
                delay *= 2  # Exponential backoff

        log.error(f"Action '{action}' failed after {self.max_retries} retries")
        return False


class TableChangeDetector:
    """
    Detect when a new hand is dealt or game state changes.
    """

    def __init__(self):
        self.last_cards_hash = None
        self.last_pot_value = None

    def detect_new_hand(self, current_cards: List[str], current_pot: float) -> bool:
        """
        Detect if a new hand has been dealt.

        Args:
            current_cards: Current hole cards
            current_pot: Current pot value

        Returns:
            True if this appears to be a new hand
        """
        cards_hash = hash(tuple(sorted(current_cards))) if current_cards else 0
        is_new = False

        # New hand if cards changed
        if self.last_cards_hash is not None and cards_hash != self.last_cards_hash:
            is_new = True

        # New hand if pot reset to small value
        if self.last_pot_value is not None and current_pot < self.last_pot_value * 0.3:
            is_new = True

        self.last_cards_hash = cards_hash
        self.last_pot_value = current_pot

        if is_new:
            log.debug("New hand detected")

        return is_new


if __name__ == "__main__":
    # Test verification
    from gamble.tools import constants as const

    print("Action Verifier Test")
    print("=" * 40)

    # Take initial screenshot
    print("Taking initial screenshot...")
    screenshot1 = ImageGrab.grab()

    # Assume table at default position
    table_region = (14, 850, const.CROP_WIDTH, const.CROP_HEIGHT)

    verifier = ActionVerifier()

    print("Detecting initial buttons...")
    buttons = verifier.button_detector.find_all_buttons(screenshot1, table_region)
    for btn, pos in buttons.items():
        print(f"  {btn}: {'FOUND' if pos else 'not found'}")

    print("\nWaiting 3 seconds for any change...")
    changed = verifier.wait_for_change(table_region, timeout=3.0)
    print(f"Change detected: {changed}")

    print("\nTaking second screenshot...")
    screenshot2 = ImageGrab.grab()

    print("Checking for significant change...")
    sig_change = verifier._significant_change(screenshot1, screenshot2, table_region)
    print(f"Significant change: {sig_change}")

    print("\nDone!")
