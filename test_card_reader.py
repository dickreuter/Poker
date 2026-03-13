#!/usr/bin/env python3
"""Quick test for the dynamic card reader.

Usage:
    # Test with a screenshot file:
    python test_card_reader.py /path/to/screenshot.png

    # Test with a live GGSystem window capture:
    python test_card_reader.py --live

    # Save debug images:
    python test_card_reader.py --live --debug
"""

import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(message)s')

from PIL import Image
from sys_core.ocr.card_reader import read_player_cards


def capture_ggpoker_table():
    """Capture a live GGPoker table window."""
    import subprocess
    from PIL import ImageGrab

    # Find GGPoker windows
    script = '''
    tell application "System Events"
        tell process "GGnet"
            set wins to {}
            repeat with w in windows
                set winName to name of w as text
                if winName contains "Rush" or winName contains "Spin" or winName contains "Gold" or winName contains "Blinds" or winName contains "NL" then
                    set winPos to position of w
                    set winSize to size of w
                    set end of wins to {winName, item 1 of winPos, item 2 of winPos, item 1 of winSize, item 2 of winSize}
                end if
            end repeat
            return wins
        end tell
    end tell
    '''

    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"AppleScript error: {result.stderr}")
        return None, None

    output = result.stdout.strip()
    if not output:
        print("No GGPoker table windows found")
        return None, None

    # Parse first window
    parts = output.replace('\u2212', '-').replace('\u2013', '-').split(', ')
    if len(parts) < 5:
        print(f"Unexpected AppleScript output: {output}")
        return None, None

    name = parts[0]
    x, y, w, h = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])

    print(f"Window: {name}")
    print(f"  Position: ({x}, {y}) points, Size: {w}x{h} points")
    print(f"  Pixel size: {w*2}x{h*2} (Retina 2x)")

    # Capture full screen
    screenshot = ImageGrab.grab()

    # Crop to table (points -> pixels for Retina)
    px, py = x * 2, y * 2
    pw, ph = w * 2, h * 2
    table_img = screenshot.crop((px, py, px + pw, py + ph))

    return table_img, f"{w*2}x{h*2}"


def test_with_file(path, debug=False):
    """Test card reader with a screenshot file."""
    img = Image.open(path)
    print(f"\nFile: {path}")
    print(f"  Size: {img.width}x{img.height}")

    debug_dir = '/tmp/card_debug' if debug else None
    cards = read_player_cards(img, debug_dir=debug_dir)

    if cards:
        print(f"  Cards detected: {cards}")
    else:
        print(f"  No cards detected (cards may be face-down)")

    if debug_dir:
        print(f"  Debug images saved to: {debug_dir}/")

    return cards


def test_live(debug=False):
    """Test card reader with live GGSystem window capture."""
    table_img, size = capture_ggpoker_table()
    if table_img is None:
        return []

    # Save capture for reference
    table_img.save('/tmp/card_debug/live_capture.png')
    print(f"\n  Saved capture: /tmp/card_debug/live_capture.png")

    debug_dir = '/tmp/card_debug' if debug else None
    cards = read_player_cards(table_img, debug_dir=debug_dir)

    if cards:
        print(f"  Cards detected: {cards}")
    else:
        print(f"  No cards detected (cards may be face-down)")

    if debug_dir:
        print(f"  Debug images saved to: {debug_dir}/")

    return cards


if __name__ == '__main__':
    import os
    os.makedirs('/tmp/card_debug', exist_ok=True)

    debug = '--debug' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]

    if '--live' in sys.argv:
        test_live(debug=True)
    elif args:
        for path in args:
            test_with_file(path, debug=debug)
    else:
        print(__doc__)
