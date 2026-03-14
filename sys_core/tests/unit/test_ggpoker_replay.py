"""Replay integration tests for GGPoker screenshots.

Loads real GGPoker screenshots, runs them through the OCR pipeline,
and asserts detection matches ground truth.

To add test data:
1. During a live session, save screenshots to sys_core/tests/screenshots/ggpoker/
2. Update ground_truth.json with expected values
3. Re-run this test
"""

import json
import os
import time

import pytest
from PIL import Image

SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'screenshots', 'ggpoker')
GROUND_TRUTH_FILE = os.path.join(SCREENSHOTS_DIR, 'ground_truth.json')


def _load_ground_truth():
    """Load ground truth, excluding the examples template."""
    if not os.path.exists(GROUND_TRUTH_FILE):
        return {}
    with open(GROUND_TRUTH_FILE) as f:
        data = json.load(f)
    # Remove metadata keys
    return {k: v for k, v in data.items()
            if not k.startswith('_') and k != 'examples'}


def _get_test_cases():
    """Return list of (filename, expected) for parametrize."""
    gt = _load_ground_truth()
    cases = []
    for filename, expected in gt.items():
        img_path = os.path.join(SCREENSHOTS_DIR, filename)
        if os.path.exists(img_path):
            cases.append((filename, expected))
    return cases


def _has_screenshots():
    """Check if any real GGPoker screenshots exist."""
    return bool(_get_test_cases())


@pytest.mark.skipif(
    not _has_screenshots(),
    reason="No GGPoker screenshots with ground truth found. "
           "Capture screenshots during a live session and add to ground_truth.json."
)
class TestGGPokerReplay:
    """Replay tests using real GGPoker screenshots."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from sys_core.ocr.table_reader import read_table
        self.read_table = read_table

    @pytest.mark.parametrize("filename,expected", _get_test_cases(),
                             ids=[c[0] for c in _get_test_cases()] if _get_test_cases() else [])
    def test_detection_matches_ground_truth(self, filename, expected):
        img_path = os.path.join(SCREENSHOTS_DIR, filename)
        img = Image.open(img_path)

        state = self.read_table(img)

        # Check is_my_turn
        if 'is_my_turn' in expected:
            assert state.is_my_turn == expected['is_my_turn'], \
                f"is_my_turn: got {state.is_my_turn}, expected {expected['is_my_turn']}"

        # Check cards (only when expected to be detected)
        if expected.get('my_cards'):
            assert sorted(state.my_cards) == sorted(expected['my_cards']), \
                f"my_cards: got {state.my_cards}, expected {expected['my_cards']}"

        # Check board cards
        if expected.get('board_cards'):
            assert sorted(state.board_cards) == sorted(expected['board_cards']), \
                f"board_cards: got {state.board_cards}, expected {expected['board_cards']}"

        # Check available actions
        if expected.get('available_actions'):
            detected_types = sorted(a.action_type for a in state.available_actions)
            expected_types = sorted(expected['available_actions'])
            assert detected_types == expected_types, \
                f"actions: got {detected_types}, expected {expected_types}"

        # Check pot range (if specified)
        if 'pot_min' in expected and state.pot > 0:
            assert state.pot >= expected['pot_min'], \
                f"pot {state.pot} < min {expected['pot_min']}"
        if 'pot_max' in expected and state.pot > 0:
            assert state.pot <= expected['pot_max'], \
                f"pot {state.pot} > max {expected['pot_max']}"

    @pytest.mark.parametrize("filename,expected", _get_test_cases(),
                             ids=[c[0] for c in _get_test_cases()] if _get_test_cases() else [])
    def test_latency_under_500ms(self, filename, expected):
        """OCR pipeline must complete in under 500ms per screenshot."""
        img_path = os.path.join(SCREENSHOTS_DIR, filename)
        img = Image.open(img_path)

        # Warm up cache
        self.read_table(img)

        # Measure
        start = time.time()
        self.read_table(img)
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 500, \
            f"read_table took {elapsed_ms:.0f}ms (limit: 500ms)"


class TestGGPokerReplayScaffolding:
    """Tests that verify the replay infrastructure is properly set up."""

    def test_ground_truth_file_exists(self):
        assert os.path.exists(GROUND_TRUTH_FILE), \
            f"Ground truth file missing: {GROUND_TRUTH_FILE}"

    def test_ground_truth_valid_json(self):
        with open(GROUND_TRUTH_FILE) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_screenshots_directory_exists(self):
        assert os.path.isdir(SCREENSHOTS_DIR), \
            f"Screenshots directory missing: {SCREENSHOTS_DIR}"

    def test_ground_truth_entries_have_required_fields(self):
        gt = _load_ground_truth()
        required_fields = {'is_my_turn'}
        for filename, expected in gt.items():
            for field in required_fields:
                assert field in expected, \
                    f"{filename} missing required field: {field}"
