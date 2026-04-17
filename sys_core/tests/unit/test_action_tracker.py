"""ActionTracker scenarios that mirror real preflop / postflop sequences."""
import pytest

from sys_core.ocr.action_tracker import ActionTracker, position_label_unique


def test_position_label_unique_6max():
    """Standard 6-max layout: BTN=dealer, then SB/BB/UTG/MP/CO clockwise."""
    # dealer at seat 0
    labels = [position_label_unique(s, 0, 6) for s in range(6)]
    assert labels == ['BTN', 'SB', 'BB', 'UTG', 'MP', 'CO']


def test_position_label_unique_9max_distinct():
    """All 9 seats must have distinct labels — UTG+1, LJ, HJ etc."""
    labels = [position_label_unique(s, 0, 9) for s in range(9)]
    assert labels == ['BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'LJ', 'HJ', 'CO']
    assert len(set(labels)) == 9, "9-max labels must be unique"


def test_position_label_unique_heads_up():
    labels = [position_label_unique(s, 0, 2) for s in range(2)]
    assert labels == ['SB', 'BB']


def test_position_label_unique_unknown_dealer():
    assert position_label_unique(3, -1, 6) == 's3'


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


def test_prime_blinds_excludes_blind_postings_from_actions():
    """SB/BB mandatory posts should NOT appear as bet/raise events."""
    t = ActionTracker(hero_seat=0)
    t.prime_blinds(sb_seat=5, sb_amount=0.5, bb_seat=3, bb_amount=1.0)
    # First frame contains the blinds + one open-raise. Blinds should be
    # baseline; only the raise becomes an event.
    t.update(
        [(0.5, 5), (1.0, 3), (3.0, 2)],  # SB post, BB post, UTG raise to 3
        {0, 1, 2, 3, 4, 5}, 'preflop',
        seat_positions={0: 'BB', 1: 'SB', 2: 'UTG', 3: 'BB', 4: 'CO', 5: 'SB'},
    )
    actions = [(e.seat, e.action, e.amount) for e in t.actions]
    assert actions == [(2, 'raise', 3.0)], (
        f"Expected only the UTG raise; got {actions}"
    )


def test_prime_blinds_then_limp_classified_as_call_not_bet():
    """A player matching exactly the BB amount preflop is a limp = call."""
    t = ActionTracker(hero_seat=0)
    t.prime_blinds(sb_seat=5, sb_amount=0.5, bb_seat=3, bb_amount=1.0)
    t.update(
        [(0.5, 5), (1.0, 3), (1.0, 2)],  # UTG limps for 1 BB
        {0, 1, 2, 3, 4, 5}, 'preflop',
    )
    actions = [(e.seat, e.action, e.amount) for e in t.actions]
    assert actions == [(2, 'call', 1.0)], (
        f"Expected UTG limp = call, got {actions}"
    )


def test_position_labels_in_summary():
    """Events should carry position names when seat_positions provided."""
    t = ActionTracker(hero_seat=0)
    # 6-max layout: hero=BB at seat 0, dealer at seat 5, so:
    #   seat 0 = BB, seat 5 = BTN, seat 4 = CO, seat 3 = MP, seat 2 = UTG, seat 1 = SB
    positions = {0: 'BB', 1: 'SB', 2: 'UTG', 3: 'MP', 4: 'CO', 5: 'BTN'}
    t.update([(3.0, 2)], {0, 1, 2, 3, 4, 5}, 'preflop', seat_positions=positions)
    t.update([(3.0, 2), (9.0, 4)], {0, 1, 2, 3, 4, 5}, 'preflop', seat_positions=positions)
    summary = t.summary()
    assert 'UTG-bet3' in summary, f"expected UTG label: {summary}"
    assert 'CO-raise9' in summary, f"expected CO label: {summary}"
    assert 's2' not in summary and 's4' not in summary, f"raw seat labels leaked: {summary}"
