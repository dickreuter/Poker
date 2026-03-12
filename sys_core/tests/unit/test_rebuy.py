"""Tests for the rebuy/Add Chips dialog handling in engine."""

import datetime
import time
from unittest.mock import MagicMock, patch, PropertyMock
import numpy as np
from PIL import Image
import pytest


# Minimal stubs so we can import MultiTableRunner without full dependencies
@pytest.fixture(autouse=True)
def _mock_heavy_imports(monkeypatch):
    """Prevent heavy imports (MongoDB, TensorFlow, etc.) from failing."""
    # We only need the _detect_and_handle_rebuy method, so we'll test it
    # by instantiating a minimal object and calling the method directly.
    pass


def _make_runner_and_session():
    """Create a minimal MultiTableRunner + TableSession for testing."""
    from sys_core.engine import MultiTableRunner, TableSession, TableWindow, TableState

    # Build a TableWindow
    window = TableWindow(
        window_id=1,
        name="Rush & Cash $0.01 / $0.02",
        x=100,   # screen points
        y=200,
        width=800,
        height=600,
    )

    # Build a minimal session
    session = TableSession(window=window, table_dict={})
    session.last_action_time = datetime.datetime.utcnow() - datetime.timedelta(seconds=10)
    session.state = TableState.WAITING
    session.priority = 1
    # Ensure cooldown is expired
    session._last_rebuy_attempt = 0

    # Build runner (skip __init__ — we only need the method)
    runner = object.__new__(MultiTableRunner)
    # Initialize bankroll protection attributes (normally set in __init__)
    runner._session_rebuys = 0
    runner._max_session_rebuys = 5
    runner._buyins_lost = 0
    runner._max_buyins_loss = 3
    runner.running = True

    return runner, session


def _fake_screenshot(w=1600, h=1200):
    """Create a fake table screenshot (PIL Image)."""
    return Image.fromarray(np.zeros((h, w, 3), dtype=np.uint8))


class TestDetectAndHandleRebuy:
    """Test _detect_and_handle_rebuy method."""

    @patch('sys_core.engine.log_action')
    def test_cooldown_prevents_rapid_checks(self, mock_log_action):
        """If we checked less than 5 seconds ago, skip."""
        runner, session = _make_runner_and_session()
        session._last_rebuy_attempt = time.time()  # Just checked

        with patch('pytesseract.image_to_string') as mock_ocr:
            result = runner._detect_and_handle_rebuy(session)
            assert result is False
            mock_ocr.assert_not_called()

    @patch('sys_core.engine.log_action')
    def test_no_rebuy_dialog_returns_false(self, mock_log_action):
        """Normal table (no 'Add Chip' text) returns False."""
        runner, session = _make_runner_and_session()
        runner.get_table_screenshot = MagicMock(return_value=_fake_screenshot())

        with patch('pytesseract.image_to_string', return_value="Blinds 0.01 | 0.02\nTotal Pot : $0.05"):
            result = runner._detect_and_handle_rebuy(session)
            assert result is False

    @patch('sys_core.engine.log_action')
    def test_rebuy_dialog_clicks_max_and_ok_via_ocr(self, mock_log_action):
        """When rebuy dialog detected, clicks Max then OK via OCR text positions."""
        runner, session = _make_runner_and_session()
        runner.get_table_screenshot = MagicMock(return_value=_fake_screenshot())

        # First call: image_to_string detects dialog
        # Subsequent calls: image_to_data returns word positions
        ocr_data_with_max = {
            'text': ['Add', 'Chip', 'with', 'Min', '$1', 'Max', '$2', 'OK', 'Cancel'],
            'left': [50, 100, 150, 50, 90, 200, 240, 120, 200],
            'top':  [30,  30,  30, 200, 200, 200, 200, 300, 300],
            'width': [30, 40, 30, 30, 30, 30, 30, 40, 50],
            'height': [15, 15, 15, 15, 15, 15, 15, 20, 20],
        }

        with patch('pytesseract.image_to_string', return_value="Add Chip with\nAmount to add\nMin $1  Max $2\nOK Cancel"):
            with patch('pytesseract.image_to_data', return_value=ocr_data_with_max):
                with patch('pyautogui.click') as mock_click:
                    result = runner._detect_and_handle_rebuy(session)

                    assert result is True
                    # Should have clicked at least twice (Max + OK)
                    assert mock_click.call_count >= 2

                    # First click should be for "Max"
                    first_click = mock_click.call_args_list[0]
                    # Second click should be for "OK"
                    second_click = mock_click.call_args_list[1]

                    # Verify clicks are at reasonable screen coordinates
                    # (window.x=100, window.y=200, plus offset from dialog region)
                    assert first_click[0][0] > 100   # x > window.x
                    assert first_click[0][1] > 200   # y > window.y
                    assert second_click[0][0] > 100
                    assert second_click[0][1] > 200

                    # Verify success was logged
                    mock_log_action.assert_called_with(
                        'rebuy', success=True,
                        details={'table': session.window.name}
                    )

    @patch('sys_core.engine.log_action')
    def test_rebuy_ok_fallback_to_green_button(self, mock_log_action):
        """If OCR can't find 'OK' text, falls back to green button detection."""
        runner, session = _make_runner_and_session()

        # Create a screenshot with a green rectangle where OK button would be
        img = np.zeros((1200, 1600, 3), dtype=np.uint8)
        # Add a green rectangle (OK button) in the dialog area
        # Dialog region: x=320..1280, y=180..1020
        # Green button at center-bottom of dialog
        img[800:840, 700:800] = [0, 200, 0]  # Green in RGB
        screenshot = Image.fromarray(img)
        runner.get_table_screenshot = MagicMock(return_value=screenshot)

        # OCR finds "Max" but NOT "OK"
        ocr_data_max_only = {
            'text': ['Add', 'Chip', 'Max', '$2', 'Cancel'],
            'left': [50, 100, 200, 240, 200],
            'top':  [30,  30, 200, 200, 300],
            'width': [30, 40, 30, 30, 50],
            'height': [15, 15, 15, 15, 20],
        }

        with patch('pytesseract.image_to_string', return_value="Add Chip with\nMax $2"):
            with patch('pytesseract.image_to_data', return_value=ocr_data_max_only):
                with patch('pyautogui.click') as mock_click:
                    result = runner._detect_and_handle_rebuy(session)

                    # Should still succeed via green button fallback
                    assert result is True
                    # At least 2 clicks (Max + OK green button)
                    assert mock_click.call_count >= 2

    @patch('sys_core.engine.log_action')
    def test_rebuy_max_fallback_to_position(self, mock_log_action):
        """If OCR can't find 'Max' text, falls back to position-based click."""
        runner, session = _make_runner_and_session()

        # Create screenshot with green OK button
        img = np.zeros((1200, 1600, 3), dtype=np.uint8)
        img[800:840, 700:800] = [0, 200, 0]
        screenshot = Image.fromarray(img)
        runner.get_table_screenshot = MagicMock(return_value=screenshot)

        # OCR finds dialog but NOT "Max" — only "OK"
        ocr_data_no_max = {
            'text': ['Add', 'Chip', 'OK'],
            'left': [50, 100, 120],
            'top':  [30,  30, 300],
            'width': [30, 40, 40],
            'height': [15, 15, 20],
        }

        with patch('pytesseract.image_to_string', return_value="Add Chip with\nAmount to add"):
            with patch('pytesseract.image_to_data', return_value=ocr_data_no_max):
                with patch('pyautogui.click') as mock_click:
                    result = runner._detect_and_handle_rebuy(session)

                    assert result is True
                    # First click = Max fallback position, second = OK via OCR
                    assert mock_click.call_count >= 2

    @patch('sys_core.engine.log_action')
    def test_rebuy_sets_cooldown_timestamp(self, mock_log_action):
        """After detecting rebuy, sets cooldown to prevent rapid re-checks."""
        runner, session = _make_runner_and_session()
        runner.get_table_screenshot = MagicMock(return_value=_fake_screenshot())

        ocr_data = {
            'text': ['Max', 'OK'],
            'left': [200, 120],
            'top':  [200, 300],
            'width': [30, 40],
            'height': [15, 20],
        }

        before = time.time()
        with patch('pytesseract.image_to_string', return_value="Add Chip with"):
            with patch('pytesseract.image_to_data', return_value=ocr_data):
                with patch('pyautogui.click'):
                    runner._detect_and_handle_rebuy(session)

        assert session._last_rebuy_attempt >= before


class TestCheckTableStateRebuyIntegration:
    """Test that check_table_state triggers rebuy at the right time."""

    def test_rebuy_triggered_when_deal_me_in_visible(self):
        """Rebuy check fires when deal_me_in is detected (sitting out)."""
        from sys_core.engine import MultiTableRunner, TableSession, TableWindow, TableState
        from sys_core.ocr.game_state import GameState, AvailableAction

        runner, session = _make_runner_and_session()

        # Create a GameState where deal_me_in is visible (sitting out after bust)
        state = MagicMock(spec=GameState)
        state.is_my_turn = False
        state.my_cards = []
        state.board_cards = []
        state.available_actions = [
            AvailableAction(action_type='deal_me_in', amount=None,
                           screen_x_pt=500, screen_y_pt=400, confidence=0.9),
        ]
        state.get_action_by_type = lambda t: next(
            (a for a in state.available_actions if a.action_type == t), None
        )

        runner.capture_game_state = MagicMock(return_value=state)
        runner._detect_and_handle_rebuy = MagicMock(return_value=True)

        result = runner.check_table_state(session)

        # Should have called rebuy detection since we're sitting out
        runner._detect_and_handle_rebuy.assert_called_once_with(session)
        assert result == TableState.WAITING

    def test_rebuy_not_triggered_during_normal_play(self):
        """Rebuy check does NOT fire during normal hand (poker buttons visible)."""
        from sys_core.engine import MultiTableRunner, TableSession, TableWindow, TableState
        from sys_core.ocr.game_state import GameState, AvailableAction

        runner, session = _make_runner_and_session()

        # Normal hand: fold + call visible, it's our turn
        state = MagicMock(spec=GameState)
        state.is_my_turn = True
        state.my_cards = ['AH', 'KS']
        state.board_cards = []
        state.available_actions = [
            AvailableAction(action_type='fold', amount=None,
                           screen_x_pt=300, screen_y_pt=500, confidence=0.9),
            AvailableAction(action_type='call', amount=0.04,
                           screen_x_pt=500, screen_y_pt=500, confidence=0.9),
        ]
        state.get_action_by_type = lambda t: next(
            (a for a in state.available_actions if a.action_type == t), None
        )

        runner.capture_game_state = MagicMock(return_value=state)
        runner._detect_and_handle_rebuy = MagicMock(return_value=False)

        result = runner.check_table_state(session)

        # Should NOT have called rebuy detection
        runner._detect_and_handle_rebuy.assert_not_called()
        assert result == TableState.NEED_ACTION
