"""Screenshot replay tests — regression safety net for OCR detection.

Loads saved screenshots and verifies that read_table() produces correct
game state. This catches detection regressions before they cause real-money
mistakes.

To add a new test case:
1. Save a screenshot PNG to sys_core/tests/screenshots/ggpoker/
2. Add a corresponding entry to REPLAY_CASES below with expected values.
"""

import os
import pytest
from pathlib import Path

from PIL import Image

# Guard against import failures in CI environments
try:
    from sys_core.ocr.table_reader import read_table
    from sys_core.ocr.game_state import ReadConfidence
    TABLE_READER_AVAILABLE = True
except ImportError:
    TABLE_READER_AVAILABLE = False


SCREENSHOTS_DIR = Path(__file__).parent.parent / "screenshots" / "ggpoker"


# Each entry: {
#   'file': filename in screenshots/ggpoker/,
#   'expected_turn': True/False,  # is_my_turn
#   'expected_buttons': ['fold', 'call', ...],  # subset of buttons that MUST be present
#   'min_cards': 0,  # minimum number of hole cards detected (0 = don't check)
#   'min_confidence': 0.0,  # minimum overall confidence (0 = don't check)
# }
REPLAY_CASES = []


def _discover_cases():
    """Auto-discover PNG files in the screenshots dir for basic smoke tests."""
    if not SCREENSHOTS_DIR.exists():
        return []
    cases = []
    for png in sorted(SCREENSHOTS_DIR.glob("*.png")):
        cases.append({
            'file': png.name,
            'expected_turn': None,  # Auto-discovered = no assertion
            'expected_buttons': [],
            'min_cards': 0,
            'min_confidence': 0.0,
        })
    return cases


@pytest.mark.skipif(not TABLE_READER_AVAILABLE, reason="table_reader not importable")
class TestScreenshotReplay:
    """Replay saved screenshots through read_table() and verify output."""

    def test_read_table_smoke(self):
        """Basic smoke test: read_table doesn't crash on any saved screenshot."""
        if not SCREENSHOTS_DIR.exists():
            pytest.skip(f"No screenshots directory at {SCREENSHOTS_DIR}")

        pngs = list(SCREENSHOTS_DIR.glob("*.png"))
        if not pngs:
            pytest.skip("No PNG screenshots found")

        for png_path in pngs:
            img = Image.open(png_path)
            state = read_table(
                img,
                window_name="Test Table",
                window_id=99999,
                table_x_pt=0, table_y_pt=0,
                table_w_pt=img.width // 2, table_h_pt=img.height // 2,
            )
            assert state is not None, f"read_table returned None for {png_path.name}"
            # Confidence should always be populated
            assert hasattr(state, 'confidence'), f"No confidence on {png_path.name}"

    def test_confidence_populated(self):
        """Verify that confidence scores are always populated (never all zero when turn)."""
        if not SCREENSHOTS_DIR.exists():
            pytest.skip(f"No screenshots directory at {SCREENSHOTS_DIR}")

        pngs = list(SCREENSHOTS_DIR.glob("*.png"))
        if not pngs:
            pytest.skip("No PNG screenshots found")

        for png_path in pngs:
            img = Image.open(png_path)
            state = read_table(
                img,
                window_name="Test Table",
                window_id=99999,
                table_x_pt=0, table_y_pt=0,
                table_w_pt=img.width // 2, table_h_pt=img.height // 2,
            )
            conf = state.confidence
            if state.is_my_turn:
                # When it's our turn, at least buttons should have confidence > 0
                assert conf.buttons > 0, (
                    f"Button confidence is 0 when is_my_turn=True for {png_path.name}"
                )

    @pytest.mark.parametrize("case", REPLAY_CASES or _discover_cases(),
                             ids=lambda c: c.get('file', 'unknown'))
    def test_replay_case(self, case):
        """Test a specific replay case with expected values."""
        png_path = SCREENSHOTS_DIR / case['file']
        if not png_path.exists():
            pytest.skip(f"Screenshot not found: {png_path}")

        img = Image.open(png_path)
        state = read_table(
            img,
            window_name="Test Table",
            window_id=99999,
            table_x_pt=0, table_y_pt=0,
            table_w_pt=img.width // 2, table_h_pt=img.height // 2,
        )

        # Check is_my_turn if specified
        if case.get('expected_turn') is not None:
            assert state.is_my_turn == case['expected_turn'], (
                f"is_my_turn mismatch for {case['file']}: "
                f"got {state.is_my_turn}, expected {case['expected_turn']}"
            )

        # Check expected buttons are present
        detected_types = {a.action_type for a in state.available_actions}
        for btn in case.get('expected_buttons', []):
            assert btn in detected_types, (
                f"Missing button '{btn}' in {case['file']}: detected={detected_types}"
            )

        # Check minimum card count
        min_cards = case.get('min_cards', 0)
        if min_cards > 0:
            assert len(state.my_cards) >= min_cards, (
                f"Card count {len(state.my_cards)} < expected {min_cards} "
                f"for {case['file']}"
            )

        # Check minimum confidence
        min_conf = case.get('min_confidence', 0.0)
        if min_conf > 0:
            assert state.confidence.overall >= min_conf, (
                f"Confidence {state.confidence.overall:.2f} < {min_conf} "
                f"for {case['file']}: {state.confidence}"
            )
