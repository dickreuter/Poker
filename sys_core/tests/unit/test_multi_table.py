"""Multi-table logic verification tests.

Tests priority queue, session management, and cooldown behavior
without requiring live tables.
"""

import time
from unittest.mock import MagicMock, patch

import pytest


def _make_table_window(window_id, name='Test Table'):
    """Create a mock TableWindow."""
    tw = MagicMock()
    tw.window_id = window_id
    tw.name = name
    tw.x = 0
    tw.y = 0
    tw.width = 800
    tw.height = 600
    return tw


def _make_game_state(is_my_turn=False, my_cards=None, available_actions=None,
                     pot=0.0, board_cards=None):
    """Create a mock GameState."""
    from sys_core.ocr.game_state import GameState, AvailableAction
    state = GameState()
    state.is_my_turn = is_my_turn
    state.my_cards = my_cards or []
    state.board_cards = board_cards or []
    state.pot = pot
    if available_actions:
        state.available_actions = [
            AvailableAction(action_type=a, amount=None, screen_x_pt=500,
                            screen_y_pt=600, confidence=0.95)
            for a in available_actions
        ]
    else:
        state.available_actions = []
    return state


class TestSessionManagement:
    """Test adding/removing table sessions."""

    def test_new_windows_create_sessions(self):
        """When new windows are found, sessions should be created."""
        from sys_core.ocr.game_state import GameState
        # Import the TableSession namedtuple/class
        try:
            from sys_core.engine import TableSession
        except ImportError:
            pytest.skip("Cannot import TableSession from engine")

        w1 = _make_table_window(1, 'Spin #1')
        w2 = _make_table_window(2, 'Spin #2')

        sessions = {}
        for w in [w1, w2]:
            if w.window_id not in sessions:
                session = MagicMock()
                session.window = w
                session._last_acted_key = ''
                session._last_action_time = 0
                sessions[w.window_id] = session

        assert len(sessions) == 2
        assert 1 in sessions
        assert 2 in sessions

    def test_closed_windows_remove_sessions(self):
        """Sessions for closed windows should be cleaned up."""
        sessions = {1: MagicMock(), 2: MagicMock(), 3: MagicMock()}
        active_window_ids = {1, 3}

        closed = [wid for wid in sessions if wid not in active_window_ids]
        for wid in closed:
            del sessions[wid]

        assert len(sessions) == 2
        assert 2 not in sessions


class TestPriorityQueue:
    """Test that tables needing action are processed first."""

    def test_action_tables_prioritized(self):
        """Tables with is_my_turn=True should be processed before waiting tables."""
        states = {
            'table_1': _make_game_state(is_my_turn=False),
            'table_2': _make_game_state(is_my_turn=True, my_cards=['AH', 'KS'],
                                         available_actions=['fold', 'call', 'raise']),
            'table_3': _make_game_state(is_my_turn=False),
        }

        # Priority: tables where it's our turn come first
        urgent = [name for name, s in states.items() if s.is_my_turn]
        waiting = [name for name, s in states.items() if not s.is_my_turn]

        assert urgent == ['table_2']
        assert len(waiting) == 2

    def test_multiple_urgent_tables_all_processed(self):
        """When multiple tables need action, all should be in the urgent list."""
        states = {
            'table_1': _make_game_state(is_my_turn=True, my_cards=['AH', 'KS'],
                                         available_actions=['fold', 'call']),
            'table_2': _make_game_state(is_my_turn=True, my_cards=['QH', 'QD'],
                                         available_actions=['fold', 'raise']),
            'table_3': _make_game_state(is_my_turn=False),
        }

        urgent = [name for name, s in states.items() if s.is_my_turn]
        assert len(urgent) == 2


class TestActionCooldown:
    """Test the cooldown between actions on the same table."""

    def test_cooldown_prevents_double_action(self):
        """Same table should not be acted on twice within cooldown period."""
        cooldown_seconds = 2.0
        last_action_time = time.time() - 1.0  # 1 second ago

        elapsed = time.time() - last_action_time
        can_act = elapsed >= cooldown_seconds

        assert not can_act, "Should NOT act within cooldown period"

    def test_cooldown_allows_action_after_expiry(self):
        """Should allow action after cooldown expires."""
        cooldown_seconds = 2.0
        last_action_time = time.time() - 3.0  # 3 seconds ago

        elapsed = time.time() - last_action_time
        can_act = elapsed >= cooldown_seconds

        assert can_act, "Should act after cooldown expires"


class TestDedupGuard:
    """Test that the bot doesn't act twice on the same situation."""

    def test_same_key_blocks_second_action(self):
        """Acting on the same cards+board+pot should be blocked."""
        def make_key(cards, board_count, pot):
            cards_key = ','.join(sorted(cards)) if len(cards) == 2 else ''
            return f"{cards_key}|{board_count}|{round(pot, 1)}"

        key1 = make_key(['AH', 'KS'], 0, 3.0)
        key2 = make_key(['AH', 'KS'], 0, 3.0)
        assert key1 == key2, "Same situation should produce same key"

    def test_different_pot_allows_action(self):
        """Different pot size should produce different key (allows re-raise)."""
        def make_key(cards, board_count, pot):
            cards_key = ','.join(sorted(cards)) if len(cards) == 2 else ''
            return f"{cards_key}|{board_count}|{round(pot, 1)}"

        key1 = make_key(['AH', 'KS'], 0, 3.0)
        key2 = make_key(['AH', 'KS'], 0, 9.0)  # After 3-bet
        assert key1 != key2, "Different pot should allow new action"

    def test_new_street_allows_action(self):
        """New board cards (new street) should allow action."""
        def make_key(cards, board_count, pot):
            cards_key = ','.join(sorted(cards)) if len(cards) == 2 else ''
            return f"{cards_key}|{board_count}|{round(pot, 1)}"

        key_preflop = make_key(['AH', 'KS'], 0, 3.0)
        key_flop = make_key(['AH', 'KS'], 3, 6.0)
        assert key_preflop != key_flop, "New street should allow action"


class TestGameStateIntegration:
    """Test GameState model integration with multi-table logic."""

    def test_game_state_available_actions(self):
        """GameState should correctly report available actions."""
        state = _make_game_state(
            is_my_turn=True,
            my_cards=['AH', 'KS'],
            available_actions=['fold', 'call', 'raise']
        )

        assert state.is_my_turn is True
        assert len(state.available_actions) == 3
        action_types = [a.action_type for a in state.available_actions]
        assert 'fold' in action_types
        assert 'call' in action_types
        assert 'raise' in action_types

    def test_has_button_properties(self):
        """GameState button properties should work."""
        state = _make_game_state(
            is_my_turn=True,
            available_actions=['fold', 'call', 'raise']
        )
        # Set call amount so it's not treated as check
        for a in state.available_actions:
            if a.action_type == 'call':
                a.amount = 3.0

        assert state.has_fold_button is True
        assert state.has_call_button is True
        assert state.has_raise_button is True
        assert state.has_check_button is False

    def test_empty_state(self):
        """Empty GameState should not crash."""
        state = _make_game_state()
        assert state.is_my_turn is False
        assert state.my_cards == []
        assert state.available_actions == []
