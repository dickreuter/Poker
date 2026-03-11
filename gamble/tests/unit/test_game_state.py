"""Tests for the GameState data model."""

import json
import pytest

from gamble.ocr.game_state import (
    AvailableAction,
    GameState,
    PlayerInfo,
    Street,
)


class TestPlayerInfo:
    def test_from_json(self):
        data = {
            'seat': 0, 'name': 'Hero', 'stack': 500.0,
            'current_bet': 30.0, 'is_active': True, 'is_hero': True,
        }
        p = PlayerInfo.from_json(data)
        assert p.seat == 0
        assert p.name == 'Hero'
        assert p.stack == 500.0
        assert p.is_hero is True

    def test_from_json_defaults(self):
        p = PlayerInfo.from_json({})
        assert p.seat == 0
        assert p.name == ''
        assert p.stack == 0.0


class TestAvailableAction:
    def test_from_json(self):
        data = {
            'action_type': 'call', 'amount': 30.0,
            'screen_x_pt': 500, 'screen_y_pt': 624,
            'confidence': 0.98,
        }
        a = AvailableAction.from_json(data)
        assert a.action_type == 'call'
        assert a.amount == 30.0
        assert a.screen_x_pt == 500

    def test_from_json_null_amount(self):
        data = {'action_type': 'fold', 'amount': None}
        a = AvailableAction.from_json(data)
        assert a.amount is None


class TestGameState:
    SAMPLE_JSON = {
        'window_id': 12345,
        'window_name': 'Spin & Gold $0.25 - Blinds 15 | 30',
        'table_x_pt': 0, 'table_y_pt': 0,
        'table_w_pt': 800, 'table_h_pt': 600,
        'my_cards': ['AH', 'KS'],
        'board_cards': ['QH', 'JD', '2C'],
        'cards_face_down': False,
        'pot': 150.0,
        'current_street_pot': 50.0,
        'call_amount': 30.0,
        'min_raise_amount': 60.0,
        'small_blind': 15.0,
        'big_blind': 30.0,
        'players': [
            {'seat': 0, 'name': 'Hero', 'stack': 500.0, 'current_bet': 30.0,
             'is_active': True, 'is_hero': True},
            {'seat': 1, 'name': 'Villain', 'stack': 450.0, 'current_bet': 60.0,
             'is_active': True, 'is_hero': False},
        ],
        'hero_seat': 0,
        'dealer_seat': 2,
        'available_actions': [
            {'action_type': 'fold', 'amount': None,
             'screen_x_pt': 322, 'screen_y_pt': 624, 'confidence': 0.95},
            {'action_type': 'call', 'amount': 30.0,
             'screen_x_pt': 500, 'screen_y_pt': 624, 'confidence': 0.98},
            {'action_type': 'raise', 'amount': 60.0,
             'screen_x_pt': 680, 'screen_y_pt': 624, 'confidence': 0.92},
        ],
        'street': 'Flop',
        'is_my_turn': True,
        'ocr_latency_ms': 47.3,
        'ocr_source': 'rust',
    }

    def test_from_json(self):
        state = GameState.from_json(self.SAMPLE_JSON)
        assert state.window_id == 12345
        assert state.my_cards == ['AH', 'KS']
        assert state.board_cards == ['QH', 'JD', '2C']
        assert state.pot == 150.0
        assert state.is_my_turn is True
        assert state.street == Street.FLOP
        assert len(state.players) == 2
        assert len(state.available_actions) == 3

    def test_to_json_roundtrip(self):
        state = GameState.from_json(self.SAMPLE_JSON)
        output = state.to_json()
        state2 = GameState.from_json(output)
        assert state2.window_id == state.window_id
        assert state2.my_cards == state.my_cards
        assert state2.pot == state.pot
        assert state2.is_my_turn == state.is_my_turn

    def test_backward_compat_properties(self):
        state = GameState.from_json(self.SAMPLE_JSON)
        assert state.has_call_button is True
        assert state.has_raise_button is True
        assert state.has_fold_button is True
        assert state.hero_stack == 500.0
        assert state.game_stage == 'Flop'
        assert state.num_board_cards == 3

    def test_get_action_by_type(self):
        state = GameState.from_json(self.SAMPLE_JSON)
        call = state.get_action_by_type('call')
        assert call is not None
        assert call.amount == 30.0

        none = state.get_action_by_type('all_in')
        assert none is None

    def test_face_down_state(self):
        data = {
            'my_cards': [],
            'cards_face_down': True,
            'is_my_turn': False,
            'available_actions': [],
        }
        state = GameState.from_json(data)
        assert state.cards_face_down is True
        assert state.is_my_turn is False
        assert state.has_call_button is False

    def test_street_unknown(self):
        data = {'street': 'InvalidStreet'}
        state = GameState.from_json(data)
        assert state.street == Street.UNKNOWN

    def test_empty_state(self):
        state = GameState()
        assert state.window_id == 0
        assert state.my_cards == []
        assert state.is_my_turn is False
        assert state.hero_stack == 0.0

    def test_json_serializable(self):
        state = GameState.from_json(self.SAMPLE_JSON)
        json_str = json.dumps(state.to_json())
        assert '"window_id": 12345' in json_str


class TestBBPassthrough:
    """Test that OCR values pass through unchanged (BB display always on)."""

    def _make_scraper_stub(self):
        """Minimal object that to_table_scraper_compat can populate."""
        class Stub:
            pass
        s = Stub()
        s.derive_preflop_sheet_name = lambda *a, **k: '1'
        return s

    def test_spin_gold_values_pass_through(self):
        """Spin & Gold with BB display: OCR values are already in BB."""
        state = GameState(
            window_name='Spin & Gold $0.25 - Blinds 15 | 30',
            pot=2.0,           # 2 BB (displayed on table with BB mode)
            call_amount=1.0,   # 1 BB
            small_blind=15.0,
            big_blind=30.0,
            my_cards=['AH', 'KS'],
            board_cards=['QH', 'JD', '2C'],
            players=[
                PlayerInfo(seat=0, name='', stack=50.0, current_bet=0.0,
                           is_active=True, is_hero=True),
                PlayerInfo(seat=1, name='', stack=40.0, current_bet=0.0,
                           is_active=True, is_hero=False),
            ],
            available_actions=[
                AvailableAction(action_type='call', amount=1.0,
                                screen_x_pt=500, screen_y_pt=624, confidence=0.9),
                AvailableAction(action_type='fold', amount=None,
                                screen_x_pt=322, screen_y_pt=624, confidence=0.9),
            ],
        )
        t = self._make_scraper_stub()
        state.to_table_scraper_compat(t)

        assert abs(t.totalPotValue - 2.0) < 0.01, f"Pot {t.totalPotValue} should be 2.0 BB"
        assert abs(t.currentCallValue - 1.0) < 0.01, f"Call {t.currentCallValue} should be 1.0 BB"
        assert abs(t.myFunds - 50.0) < 0.01, f"Stack {t.myFunds} should be 50.0 BB"

    def test_rush_cash_values_pass_through(self):
        """Rush & Cash with BB display: values pass through unchanged."""
        state = GameState(
            window_name='Rush & Cash - $0.01 / $0.02',
            pot=7.0,          # 7 BB
            call_amount=2.5,  # 2.5 BB
            small_blind=0.01,
            big_blind=0.02,
            my_cards=['2H', '6H'],
            board_cards=['8H', '4H', 'JH'],
            players=[
                PlayerInfo(seat=0, name='', stack=123.5, current_bet=0.0,
                           is_active=True, is_hero=True),
                PlayerInfo(seat=1, name='', stack=132.0, current_bet=0.0,
                           is_active=True, is_hero=False),
            ],
            available_actions=[
                AvailableAction(action_type='call', amount=2.5,
                                screen_x_pt=500, screen_y_pt=624, confidence=0.9),
                AvailableAction(action_type='fold', amount=None,
                                screen_x_pt=322, screen_y_pt=624, confidence=0.9),
                AvailableAction(action_type='raise', amount=5.0,
                                screen_x_pt=680, screen_y_pt=624, confidence=0.9),
            ],
        )
        t = self._make_scraper_stub()
        state.to_table_scraper_compat(t)

        assert abs(t.totalPotValue - 7.0) < 0.01, f"Pot {t.totalPotValue} should be 7.0 BB"
        assert abs(t.currentCallValue - 2.5) < 0.01, f"Call {t.currentCallValue} should be 2.5 BB"
        assert abs(t.myFunds - 123.5) < 0.01, f"Stack {t.myFunds} should be 123.5 BB"

    def test_safety_cap_ocr_misread(self):
        """OCR misread call=288 → safety cap catches it regardless of format."""
        state = GameState(
            window_name='Rush & Cash - $0.01 / $0.02',
            pot=3.0,          # 3 BB
            call_amount=288,  # OCR misread (should be ~2-3 BB)
            small_blind=0.01,
            big_blind=0.02,
            my_cards=['Q5', 'H'],
            board_cards=[],
            players=[
                PlayerInfo(seat=0, name='', stack=100.0, current_bet=0.0,
                           is_active=True, is_hero=True),
            ],
            available_actions=[
                AvailableAction(action_type='call', amount=288,
                                screen_x_pt=500, screen_y_pt=624, confidence=0.9),
            ],
        )
        t = self._make_scraper_stub()
        state.to_table_scraper_compat(t)

        # Call 288 > hero stack 100 → capped to 100 (Rule 1)
        # Call 100 > 4x pot 12 → capped to 4x pot = 12.0 (Rule 2)
        assert t.currentCallValue <= 12.0, (
            f"Call {t.currentCallValue} should be capped (288 misread)"
        )

    def test_legitimate_3bet_not_overcapped(self):
        """A normal 11 BB 3-bet into a 4.5 BB pot should NOT be capped."""
        state = GameState(
            window_name='Spin & Gold $0.25 - Blinds 15 | 30',
            pot=4.5,            # 4.5 BB pot (open + 3bet)
            call_amount=11.0,   # 11 BB 3-bet
            small_blind=15.0,
            big_blind=30.0,
            my_cards=['AH', 'KS'],
            board_cards=[],
            players=[
                PlayerInfo(seat=0, name='', stack=50.0, current_bet=0.0,
                           is_active=True, is_hero=True),
            ],
            available_actions=[
                AvailableAction(action_type='call', amount=11.0,
                                screen_x_pt=500, screen_y_pt=624, confidence=0.9),
            ],
        )
        t = self._make_scraper_stub()
        state.to_table_scraper_compat(t)

        # 11 BB < 4x pot (18 BB) → should NOT be capped
        assert abs(t.currentCallValue - 11.0) < 0.01, (
            f"Call {t.currentCallValue} should be 11.0 (legitimate 3-bet)"
        )
