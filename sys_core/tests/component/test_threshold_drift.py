"""
Tests that learned thresholds stay within sane bounds.

These catch the self-healing system drifting thresholds to nonsense values.
"""

import json
import pytest
from pathlib import Path

THRESHOLDS_PATH = Path(__file__).parent.parent.parent.parent / 'data' / 'learning' / 'thresholds.json'

# Sane bounds for each threshold
BOUNDS = {
    'white_pixel_min': (80, 230),
    'card_area_min': (500, 10000),
    'button_area_min': (200, 10000),
    'match_score_max': (0.1, 0.6),
    'action_cooldown': (0.5, 5.0),
    'click_verify_delay': (0.1, 3.0),
    'table_width_min': (200, 800),
    'button_region_y_start': (0.3, 0.8),
}


def load_thresholds():
    if THRESHOLDS_PATH.exists():
        with open(THRESHOLDS_PATH) as f:
            return json.load(f)
    return {}


class TestThresholdDrift:
    @pytest.fixture
    def thresholds(self):
        return load_thresholds()

    def test_all_thresholds_in_bounds(self, thresholds):
        for name, (lower, upper) in BOUNDS.items():
            if name in thresholds:
                val = thresholds[name]
                assert lower <= val <= upper, (
                    f"Threshold '{name}' = {val} is outside sane range [{lower}, {upper}]. "
                    f"Self-healing may have drifted it. Reset to a sensible default."
                )

    def test_hsv_ranges_are_valid(self, thresholds):
        """Each HSV lower must be <= upper component-wise."""
        hsv_pairs = [
            ('hsv_green_lower', 'hsv_green_upper'),
            ('hsv_orange_lower', 'hsv_orange_upper'),
            ('hsv_gray_lower', 'hsv_gray_upper'),
        ]
        for lower_key, upper_key in hsv_pairs:
            lower = thresholds.get(lower_key, [0, 0, 0])
            upper = thresholds.get(upper_key, [180, 255, 255])
            for i, (l, u) in enumerate(zip(lower, upper)):
                assert l <= u, (
                    f"{lower_key}[{i}]={l} > {upper_key}[{i}]={u}. "
                    f"HSV lower must be <= upper."
                )
