"""
Constants and configuration for the poker bot.
"""

import subprocess
import logging

log = logging.getLogger(__name__)

# Default crop dimensions (pixels on Retina display)
# These are used when we can't detect actual window size
# For standard 800x600 POINTS table = 1600x1200 PIXELS on Retina
CROP_WIDTH = 1600
CROP_HEIGHT = 1200

# Minimum table size (GGPoker requires at least 560x415)
MIN_TABLE_WIDTH = 560
MIN_TABLE_HEIGHT = 415

# Maximum table size (reasonable upper bound)
MAX_TABLE_WIDTH = 2400
MAX_TABLE_HEIGHT = 1600

# Retina display scaling factor (macOS)
RETINA_SCALE = 2


def get_ggpoker_window_sizes():
    """
    Get actual GGPoker window sizes using AppleScript.

    Returns:
        List of (name, x, y, width, height) tuples for each window
    """
    try:
        script = '''
        tell application "System Events"
            if exists process "GGnet" then
                tell process "GGnet"
                    set windowInfo to {}
                    repeat with w in windows
                        set winName to name of w as text
                        set winPos to position of w
                        set winSize to size of w
                        set end of windowInfo to winName & "###" & (item 1 of winPos as text) & "," & (item 2 of winPos as text) & "," & (item 1 of winSize as text) & "," & (item 2 of winSize as text)
                    end repeat
                    return windowInfo as text
                end tell
            end if
        end tell
        '''
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0 or not result.stdout.strip():
            return []

        windows = []
        for line in result.stdout.strip().split(', '):
            if '###' in line:
                name, coords = line.split('###')
                # Fix Unicode minus sign (−) that macOS returns instead of ASCII minus (-)
                coords = coords.replace('−', '-').replace('–', '-')
                parts = coords.split(',')
                if len(parts) == 4:
                    x, y, w, h = map(int, parts)
                    windows.append((name.strip(), x, y, w, h))
                    log.debug(f"Found GGPoker window: {name} at ({x},{y}) size {w}x{h}")

        return windows

    except Exception as e:
        log.debug(f"Could not get GGPoker windows: {e}")
        return []


def get_dynamic_crop_size(window_size=None):
    """
    Get appropriate crop dimensions based on actual window size.

    Args:
        window_size: Optional (width, height) tuple. If not provided,
                    will try to detect from GGPoker windows.

    Returns:
        (width, height) tuple in pixels
    """
    if window_size:
        w, h = window_size
        # Convert from points to pixels for Retina
        return (w * RETINA_SCALE, h * RETINA_SCALE)

    # Try to get from GGPoker
    windows = get_ggpoker_window_sizes()
    if windows:
        # Use the first/largest window as reference
        _, _, _, w, h = windows[0]
        # Convert from points to pixels
        return (w * RETINA_SCALE, h * RETINA_SCALE)

    # Fall back to defaults
    return (CROP_WIDTH, CROP_HEIGHT)


def validate_crop_dimensions(width, height):
    """
    Validate that crop dimensions are reasonable.

    Args:
        width: Width in pixels
        height: Height in pixels

    Returns:
        (width, height) tuple, clamped to valid range
    """
    # Clamp to valid range
    width = max(MIN_TABLE_WIDTH * RETINA_SCALE, min(width, MAX_TABLE_WIDTH))
    height = max(MIN_TABLE_HEIGHT * RETINA_SCALE, min(height, MAX_TABLE_HEIGHT))

    return (int(width), int(height))
