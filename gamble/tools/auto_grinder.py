#!/usr/bin/env python3
"""
AUTO GRINDER - Fully automated Spin & Gold poker bot
Monitors tables, makes decisions, handles registration automatically
"""
import time
import subprocess
from PIL import ImageGrab
import numpy as np
import cv2
from pynput.mouse import Button, Controller

mouse = Controller()

# LEARNED COORDINATES (Retina 2x)
COORDS = {
    'global_sitout_checkbox': (135, 694),  # Bottom left of table window
    'fold_btn': (557, 360),
    'call_btn': (650, 360),
    'raise_btn': (743, 360),
}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def focus_gg():
    subprocess.run(['osascript', '-e', 'tell application "System Events" to tell process "GGnet" to set frontmost to true'], capture_output=True)
    time.sleep(0.1)

def click(x, y):
    mouse.position = (x, y)
    time.sleep(0.03)
    mouse.click(Button.left)

def get_windows():
    result = subprocess.run(['osascript', '-e', '''
    tell application "System Events"
        tell process "GGnet"
            return name of every window
        end tell
    end tell
    '''], capture_output=True, text=True)
    return [w.strip() for w in result.stdout.strip().split(',')]

def find_button_by_color(img, color='green'):
    """Find button by HSV color"""
    hsv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2HSV)

    if color == 'green':
        lower, upper = np.array([35, 80, 80]), np.array([85, 255, 255])
    elif color == 'red':
        lower, upper = np.array([0, 80, 80]), np.array([15, 255, 255])
    elif color == 'blue':
        lower, upper = np.array([100, 80, 80]), np.array([130, 255, 255])
    else:
        return None

    mask = cv2.inRange(hsv, lower, upper)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(c) > 1500:
            x, y, w, h = cv2.boundingRect(c)
            return (x + w//2) // 2, (y + h//2) // 2  # Points
    return None

def detect_state(img):
    """Detect current game state from screenshot"""
    # Check for "WINNER" text (yellow/gold area in center)
    center = img.crop((img.width//3, img.height//4, 2*img.width//3, img.height//2))
    hsv = cv2.cvtColor(np.array(center), cv2.COLOR_RGB2HSV)
    gold_mask = cv2.inRange(hsv, np.array([15, 100, 100]), np.array([35, 255, 255]))
    if np.sum(gold_mask > 0) > 5000:
        return 'WINNER_DIALOG'

    # Check for action buttons (fold/call visible)
    bottom = img.crop((0, 2*img.height//3, img.width, img.height))
    if find_button_by_color(bottom, 'red'):  # Fold button
        return 'MY_TURN'

    # Check for registration dialog (Register button visible)
    if find_button_by_color(img, 'green'):
        return 'REGISTER_DIALOG'

    return 'WAITING'

def handle_winner():
    """Handle winner dialog - click Play Again"""
    log("Winner dialog - clicking Play Again")
    focus_gg()
    img = ImageGrab.grab()
    btn = find_button_by_color(img, 'green')
    if btn:
        click(btn[0], btn[1])
        return True
    return False

def handle_register():
    """Handle registration dialog"""
    log("Registration dialog - clicking Register")
    focus_gg()
    img = ImageGrab.grab()
    btn = find_button_by_color(img, 'green')
    if btn:
        click(btn[0], btn[1])
        time.sleep(1)
        # Uncheck global sitout
        click(COORDS['global_sitout_checkbox'][0], COORDS['global_sitout_checkbox'][1])
        return True
    return False

def handle_my_turn():
    """Handle when it's our turn to act"""
    log("My turn - analyzing...")
    focus_gg()
    # For now: simple strategy - call/check
    img = ImageGrab.grab()

    # Find call button (green)
    call_btn = find_button_by_color(img, 'green')
    if call_btn:
        log(f"Clicking Call at {call_btn}")
        click(call_btn[0], call_btn[1])
        return 'CALL'

    # Fallback: fold
    fold_btn = find_button_by_color(img, 'red')
    if fold_btn:
        log(f"Clicking Fold at {fold_btn}")
        click(fold_btn[0], fold_btn[1])
        return 'FOLD'

    return None

def main_loop():
    """Main automation loop"""
    log("=== AUTO GRINDER STARTED ===")
    hands_played = 0

    while True:
        try:
            img = ImageGrab.grab()
            state = detect_state(img)

            if state == 'WINNER_DIALOG':
                handle_winner()
                time.sleep(1)
            elif state == 'REGISTER_DIALOG':
                handle_register()
                time.sleep(2)
            elif state == 'MY_TURN':
                action = handle_my_turn()
                if action:
                    hands_played += 1
                    log(f"Hands: {hands_played}")
                time.sleep(0.5)
            else:
                time.sleep(0.3)

        except KeyboardInterrupt:
            log("Stopped by user")
            break
        except Exception as e:
            log(f"Error: {e}")
            time.sleep(1)

if __name__ == '__main__':
    main_loop()
