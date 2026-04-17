"""ActionTracker scenarios that mirror real preflop / postflop sequences."""
import pytest

from sys_core.ocr.action_tracker import ActionTracker


def _run(frames):
    """Feed a list of (postings, active_seats, street) frames; return events tuple."""
    t = ActionTracker(hero_seat=0)
    for postings, active, street in frames:
        t.update(postings, set(active), street)
    return [(e.street, e.seat, e.action, e.amount) for e in t.actions]


def test_open_raise_then_call():
    events = _run([
        ([(3.0, 2)], {0, 1, 2, 3, 4, 5}, 'preflop'),
        ([(3.0, 2), (3.0, 5)], {0, 1, 2, 3, 4, 5}, 'preflop'),
    ])
    assert events == [
        ('preflop', 2, 'bet', 3.0),
        ('preflop', 5, 'call', 3.0),
    ]


def test_3bet_sequence():
    events = _run([
        ([(3.0, 2)], {0, 1, 2, 3, 4, 5}, 'preflop'),
        ([(3.0, 2), (9.0, 4)], {0, 1, 2, 3, 4, 5}, 'preflop'),
        ([(9.0, 2), (9.0, 4)], {0, 1, 2, 3, 4, 5}, 'preflop'),
    ])
    assert events == [
        ('preflop', 2, 'bet', 3.0),
        ('preflop', 4, 'raise', 9.0),
        ('preflop', 2, 'call', 9.0),
    ]


def test_folds_from_card_back_disappearance():
    events = _run([
        ([(3.0, 2)], {0, 1, 2, 3, 4, 5}, 'preflop'),
        ([(3.0, 2)], {0, 1, 2, 4, 5}, 'preflop'),       # MP folded
        ([(3.0, 2)], {0, 1, 2, 5}, 'preflop'),          # CO folded
        ([(3.0, 2), (3.0, 5)], {0, 1, 2, 5}, 'preflop'),
    ])
    assert events == [
        ('preflop', 2, 'bet', 3.0),
        ('preflop', 3, 'fold', 0),
        ('preflop', 4, 'fold', 0),
        ('preflop', 5, 'call', 3.0),
    ]


def test_simultaneous_bet_and_call_in_same_frame():
    """Two actions can happen between polls — must classify in posting-amount order."""
    events = _run([
        ([(2.0, 4), (2.0, 0)], {0, 4}, 'preflop'),
        ([], {0, 4}, 'flop'),
        ([(3.0, 4)], {0, 4}, 'flop'),
    ])
    assert events == [
        ('preflop', 4, 'bet', 2.0),
        ('preflop', 0, 'call', 2.0),
        ('flop', 4, 'bet', 3.0),
    ]


def test_4bet_shove():
    events = _run([
        ([(3.0, 2)], {0, 1, 2, 3, 4, 5}, 'preflop'),
        ([(3.0, 2), (100.0, 5)], {0, 1, 2, 3, 4, 5}, 'preflop'),
        ([(3.0, 2), (100.0, 5)], {0, 1, 3, 4, 5}, 'preflop'),  # UTG fold
    ])
    assert events == [
        ('preflop', 2, 'bet', 3.0),
        ('preflop', 5, 'raise', 100.0),
        ('preflop', 2, 'fold', 0),
    ]


def test_reset_for_new_hand_clears_state():
    t = ActionTracker(hero_seat=0)
    t.update([(3.0, 2)], {0, 1, 2}, 'preflop')
    assert len(t.actions) == 1
    t.reset_for_new_hand()
    assert t.actions == []
    assert t._last_postings == {}
    assert t._street_max == 0.0


def test_hero_action_tagged():
    t = ActionTracker(hero_seat=0)
    t.update([(3.0, 0)], {0, 1, 2}, 'preflop')
    assert t.actions[0].is_hero is True
    t.update([(3.0, 0), (9.0, 2)], {0, 1, 2}, 'preflop')
    assert t.actions[1].is_hero is False
