"""
Keyboard controller for poker bot actions using hotkeys.
GGPoker hotkeys: F=Fold, C=Call, B=Bet/Raise
"""
import logging
import subprocess
import time
import random
from pynput.keyboard import Controller, Key

log = logging.getLogger(__name__)


def activate_ggpoker():
    """Bring GGPoker window to front on macOS"""
    try:
        # Use AppleScript to activate GGPoker (process name is "GGnet")
        script = '''
        tell application "System Events"
            try
                set frontmost of (first process whose name is "GGnet") to true
            on error
                set frontmost of (first process whose name contains "GG") to true
            end try
        end tell
        '''
        result = subprocess.run(['osascript', '-e', script], capture_output=True, timeout=2)
        time.sleep(0.15)  # Brief pause for window to activate
        log.debug("Activated GGPoker window")
        return True
    except Exception as e:
        log.warning(f"Could not activate GGPoker window: {e}")
        return False

# GGPoker hotkeys
HOTKEYS = {
    'Fold': 'f',
    'Call': 'c',
    'Call2': 'c',
    'Check': 'c',  # Check is same as Call in GGPoker
    'Bet': 'b',
    'Bet Bluff': 'b',
    'Bet half pot': 'b',
    'Bet pot': 'b',
    'Bet max': 'b',
    'BetPlus': 'b',
}


class KeyboardController:
    """Send keyboard hotkeys for poker actions."""

    def __init__(self):
        self.keyboard = Controller()

    def press_key(self, key: str):
        """Press and release a single key via AppleScript to GGPoker."""
        try:
            # Send keystroke directly to GGPoker via AppleScript
            script = f'''
            tell application "System Events"
                tell process "GGnet"
                    set frontmost to true
                    delay 0.1
                    keystroke "{key}"
                end tell
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script],
                                   capture_output=True, timeout=3)
            if result.returncode != 0:
                log.warning(f"AppleScript error: {result.stderr.decode()}")
            else:
                log.info(f"Sent keystroke '{key}' to GGPoker via AppleScript")
        except Exception as e:
            log.error(f"Failed to send key: {e}")

        time.sleep(random.uniform(0.1, 0.3))

    def execute_action(self, decision: str):
        """Execute a poker action using keyboard hotkey."""
        # Normalize decision name
        if decision == 'Check Deception':
            decision = 'Check'
        if decision == 'Call Deception':
            decision = 'Call'

        hotkey = HOTKEYS.get(decision)

        if hotkey:
            log.info(f"Keyboard action: {decision} -> pressing '{hotkey}'")
            self.press_key(hotkey)
            return True
        else:
            log.warning(f"No hotkey mapping for action: {decision}")
            return False


class KeyboardControllerTableBased(KeyboardController):
    """Keyboard controller that matches MouseMoverTableBased interface."""

    def __init__(self, table_dict):
        super().__init__()
        self.table_dict = table_dict

    def mouse_action(self, decision, topleftcorner, options=None):
        """
        Execute action using keyboard instead of mouse.
        Matches MouseMoverTableBased.mouse_action() signature.
        """
        log.debug(f"Keyboard action requested: {decision}")

        # Handle special cases that need multiple keys
        if decision == "BetPlus" and options:
            # For bet increases, we might need to press + multiple times
            # But for now, just press bet
            increases = int(options.get('increases_num', 0))
            log.debug(f"BetPlus with {increases} increases - using 'b' key")

        # Handle actions that aren't clickable (like Imback)
        if decision in ("Imback", "resume_hand"):
            log.warning(f"Action '{decision}' requires mouse - no hotkey available")
            return False

        return self.execute_action(decision)

    def move_mouse_away_from_buttons(self):
        """No-op for keyboard mode - nothing to move."""
        pass

    def move_mouse_away_from_buttons_jump(self):
        """No-op for keyboard mode - nothing to move."""
        pass
