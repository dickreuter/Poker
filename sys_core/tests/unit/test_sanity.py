"""Sanity-check tests using bug examples observed in real session logs."""
import pytest

from sys_core.ocr.sanity import check_state, is_safe_to_act, summary_line
from sys_core.ocr.game_state import (
    GameState, PlayerInfo, Street, AvailableAction
)


def _action(t='check', amt=0):
    return AvailableAction(action_type=t, amount=amt,
                           screen_x_pt=0, screen_y_pt=0, confidence=0.9)


def _state(**overrides):
    s = GameState()
    s.is_my_turn = overrides.get('is_my_turn', True)
    s.players = overrides.get('players', [
        PlayerInfo(seat=0, name='hero', stack=100, current_bet=0,
                   is_active=True, is_hero=True),
    ])
    s.street = overrides.get('street', Street.PREFLOP)
    s.position = overrides.get('position', 'BTN')
    s.pot = overrides.get('pot', 1.5)
    s.call_amount = overrides.get('call_amount', 1.0)
    s.my_cards = overrides.get('my_cards', ['AS', 'KH'])
    s.board_cards = overrides.get('board_cards', [])
    s.available_actions = overrides.get('available_actions', [_action('call', 1)])
    return s


def test_clean_state_has_no_warnings():
    assert check_state(_state()) == []
    assert is_safe_to_act(_state())
    assert summary_line(_state()) == ''


def test_hero_stack_8959_bug():
    """Real bug: hero stack OCR'd as 8959 BB on a $0.01/$0.02 table."""
    s = _state(players=[
        PlayerInfo(seat=0, name='hero', stack=8959, current_bet=0,
                   is_active=True, is_hero=True),
    ])
    warns = check_state(s)
    assert any(w[0] == 'high' and w[1] == 'hero_stack' for w in warns), \
        f"missed catastrophic stack misread: {warns}"
    assert not is_safe_to_act(s)


def test_villain_bet_255_on_100bb_stack_bug():
    """Real bug: 2.55 BB bet OCR'd as 255 BB."""
    s = _state(players=[
        PlayerInfo(seat=0, name='hero', stack=113, current_bet=0,
                   is_active=True, is_hero=True),
        PlayerInfo(seat=1, name='villain', stack=235, current_bet=255,
                   is_active=True, is_hero=False),
    ], call_amount=255, pot=4, street=Street.FLOP, board_cards=['JS', '4D', '2H'])
    warns = check_state(s)
    assert any(w[0] == 'high' and 'seat_1_bet' in w[1] for w in warns)
    assert not is_safe_to_act(s)


def test_position_unknown_with_action_flagged():
    s = _state(position='UNKNOWN', street=Street.FLOP,
               board_cards=['AS', 'KD', '7C'])
    warns = check_state(s)
    assert any(w[0] == 'high' and w[1] == 'position' for w in warns)


def test_bet_exceeds_stack_flagged():
    """Player bets more than their stack — physically impossible."""
    s = _state(players=[
        PlayerInfo(seat=0, name='hero', stack=100, current_bet=0,
                   is_active=True, is_hero=True),
        PlayerInfo(seat=1, name='villain', stack=20, current_bet=200,
                   is_active=True, is_hero=False),
    ])
    warns = check_state(s)
    assert any(w[0] == 'high' and 'bet' in w[1] for w in warns)


def test_summary_line_shows_high_count():
    s = _state(players=[
        PlayerInfo(seat=0, name='hero', stack=8959, current_bet=0,
                   is_active=True, is_hero=True),
    ])
    line = summary_line(s)
    assert 'HIGH' in line and '⚠' in line


def test_malformed_card_flagged():
    s = _state(my_cards=['AS', 'XX'])
    warns = check_state(s)
    assert any(w[0] == 'high' and w[1] == 'hero_cards' for w in warns)
