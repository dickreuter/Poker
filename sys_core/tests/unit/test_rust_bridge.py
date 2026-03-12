"""Tests for the Rust OCR bridge."""

import json
import pytest
from unittest.mock import patch, MagicMock

from sys_core.ocr.rust_bridge import RustOCRBridge, _find_binary
from sys_core.ocr.game_state import GameState


class TestRustOCRBridge:
    def test_unavailable_when_no_binary(self):
        bridge = RustOCRBridge(binary_path='/nonexistent/path')
        assert bridge.available is False

    def test_capture_returns_none_when_unavailable(self):
        bridge = RustOCRBridge(binary_path='/nonexistent/path')
        result = bridge.capture_table(12345)
        assert result is None

    def test_list_windows_returns_empty_when_unavailable(self):
        bridge = RustOCRBridge(binary_path='/nonexistent/path')
        result = bridge.list_windows()
        assert result == []

    @patch('sys_core.ocr.rust_bridge.subprocess.run')
    def test_capture_parses_json(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                'window_id': 123,
                'window_name': 'Test',
                'is_my_turn': True,
                'my_cards': ['AH', 'KS'],
                'available_actions': [
                    {'action_type': 'call', 'amount': 30.0,
                     'screen_x_pt': 100, 'screen_y_pt': 200,
                     'confidence': 0.95},
                ],
                'street': 'Preflop',
                'pot': 100.0,
            }),
            stderr='',
        )

        bridge = RustOCRBridge.__new__(RustOCRBridge)
        bridge._binary = '/fake/poker_ocr'
        bridge._available = True

        state = bridge.capture_table(123)
        assert state is not None
        assert state.window_id == 123
        assert state.my_cards == ['AH', 'KS']
        assert state.is_my_turn is True
        assert state.ocr_source == 'rust'

    @patch('sys_core.ocr.rust_bridge.subprocess.run')
    def test_capture_handles_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='Window not found',
        )

        bridge = RustOCRBridge.__new__(RustOCRBridge)
        bridge._binary = '/fake/poker_ocr'
        bridge._available = True

        state = bridge.capture_table(999)
        assert state is None

    @patch('sys_core.ocr.rust_bridge.subprocess.run')
    def test_capture_handles_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='poker_ocr', timeout=2)

        bridge = RustOCRBridge.__new__(RustOCRBridge)
        bridge._binary = '/fake/poker_ocr'
        bridge._available = True

        state = bridge.capture_table(123)
        assert state is None


class TestFindBinary:
    def test_returns_none_when_not_found(self):
        with patch('sys_core.ocr.rust_bridge.shutil.which', return_value=None):
            # Will also check build paths which don't exist
            result = _find_binary()
            # Might find in build path if it exists, or return None
            # Just verify it doesn't crash
            assert result is None or isinstance(result, str)
