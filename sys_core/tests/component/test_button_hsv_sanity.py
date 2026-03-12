"""
Sanity tests for button HSV thresholds.

Ensures learned thresholds haven't drifted to values that detect wrong colors.
"""

import json
import pytest
from pathlib import Path


THRESHOLDS_PATH = Path(__file__).parent.parent.parent.parent / 'data' / 'learning' / 'thresholds.json'


def load_thresholds():
    if THRESHOLDS_PATH.exists():
        with open(THRESHOLDS_PATH) as f:
            return json.load(f)
    return {}


class TestHSVSanity:
    """Verify HSV ranges detect actual button colors, not noise."""

    def test_green_lower_hue_in_green_range(self):
        t = load_thresholds()
        lower = t.get('hsv_green_lower', [35, 50, 50])
        # Green hue should be between 25-60 (not 0 which is red)
        assert lower[0] >= 20, f"Green H lower={lower[0]} too low (detecting red/white)"

    def test_green_lower_saturation_not_zero(self):
        t = load_thresholds()
        lower = t.get('hsv_green_lower', [35, 50, 50])
        # Saturation must be >20 to exclude grays/whites
        assert lower[1] >= 20, f"Green S lower={lower[1]} too low (detecting gray/white)"

    def test_green_lower_value_not_too_high(self):
        t = load_thresholds()
        lower = t.get('hsv_green_lower', [35, 50, 50])
        # Value threshold >200 means only very bright pixels = too restrictive
        assert lower[2] <= 200, f"Green V lower={lower[2]} too high (missing dark buttons)"

    def test_orange_hue_in_orange_range(self):
        t = load_thresholds()
        lower = t.get('hsv_orange_lower', [8, 80, 80])
        upper = t.get('hsv_orange_upper', [25, 255, 255])
        # Orange hue: 5-30
        assert lower[0] >= 3, f"Orange H lower={lower[0]} too low"
        assert upper[0] <= 40, f"Orange H upper={upper[0]} too high"

    def test_gray_range_excludes_bright_colors(self):
        t = load_thresholds()
        upper = t.get('hsv_gray_upper', [180, 60, 120])
        # Gray should have low saturation
        assert upper[1] <= 100, f"Gray S upper={upper[1]} too high (matching colored areas)"

    def test_button_area_min_reasonable(self):
        t = load_thresholds()
        area = t.get('button_area_min', 1500)
        # Too small = noise, too large = missing buttons
        assert 200 <= area <= 10000, f"button_area_min={area} out of range"

    def test_button_region_y_start_reasonable(self):
        t = load_thresholds()
        y_start = t.get('button_region_y_start', 0.6)
        # Buttons are in bottom portion of screen
        assert 0.4 <= y_start <= 0.8, f"button_region_y_start={y_start} out of range"

    def test_no_drifted_green_detects_white(self):
        """The specific bug: hsv_green_lower=[0,0,163] detects white as green."""
        t = load_thresholds()
        lower = t.get('hsv_green_lower', [35, 50, 50])
        # This exact combination was the bug
        is_broken = lower[0] == 0 and lower[1] == 0 and lower[2] > 100
        assert not is_broken, (
            f"CRITICAL: Green threshold {lower} detects white/gray as green! "
            "Reset to [35, 50, 50]."
        )
