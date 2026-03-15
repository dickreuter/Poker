"""Hand bucketing for CFR solving.

Groups hands into strategically similar clusters using eval7.
Preflop: by equity vs villain range.
Postflop: by hand strength on board + draw potential.
"""
import logging
from typing import List, Tuple, Dict, Optional

log = logging.getLogger(__name__)

try:
    import eval7
    HAS_EVAL7 = True
except ImportError:
    HAS_EVAL7 = False


def bucket_preflop(villain_range_str: str, n_buckets: int = 20,
                   iterations: int = 3000) -> Dict[str, int]:
    """Bucket all 169 canonical hands by equity vs villain range.

    Returns:
        Dict mapping hand_key (e.g. 'AKs', 'TT') to bucket index 0..n_buckets-1.
        Bucket 0 = weakest, bucket n_buckets-1 = strongest.
    """
    if not HAS_EVAL7:
        return {}

    from sys_core.decisionmaker.range_equity import (
        _ALL_HANDS_169, _hand_to_eval7_cards
    )

    try:
        villain_hr = eval7.HandRange(villain_range_str)
    except Exception:
        return {}

    # Compute equity for each hand
    hand_equities = []
    for hand_key in _ALL_HANDS_169:
        c1, c2 = _hand_to_eval7_cards(hand_key)
        if c1 is None:
            continue
        try:
            eq = float(eval7.py_hand_vs_range_monte_carlo(
                [c1, c2], villain_hr, [], iterations))
            hand_equities.append((hand_key, eq))
        except Exception:
            hand_equities.append((hand_key, 0.5))

    # Sort by equity and assign to buckets
    hand_equities.sort(key=lambda x: x[1])
    bucket_size = max(1, len(hand_equities) // n_buckets)

    buckets = {}
    for i, (hand_key, eq) in enumerate(hand_equities):
        bucket_idx = min(i // bucket_size, n_buckets - 1)
        buckets[hand_key] = bucket_idx

    return buckets


def bucket_postflop(hero_range_str: str, villain_range_str: str,
                    board_cards: List[str], n_buckets: int = 20,
                    iterations: int = 2000) -> Tuple[Dict, Dict, Dict]:
    """Bucket hands for postflop CFR.

    Uses hand strength on the board + draw detection for clustering.

    Returns:
        (hero_buckets, villain_buckets, equity_matrix)
        hero_buckets: {combo_str: bucket_idx}
        villain_buckets: {combo_str: bucket_idx}
        equity_matrix: {(hero_bucket, villain_bucket): hero_equity}
    """
    if not HAS_EVAL7:
        return {}, {}, {}

    from sys_core.decisionmaker.range_equity import _convert_card

    board_e7 = [_convert_card(c) for c in board_cards if c]
    board_e7 = [c for c in board_e7 if c is not None]
    if len(board_e7) < 3:
        return {}, {}, {}

    dead = set(str(c) for c in board_e7)

    # Parse ranges
    try:
        hero_hr = eval7.HandRange(hero_range_str)
        villain_hr = eval7.HandRange(villain_range_str)
    except Exception:
        return {}, {}, {}

    # Evaluate and bucket each range
    hero_buckets = _evaluate_and_bucket(hero_hr, board_e7, dead, n_buckets)
    villain_buckets = _evaluate_and_bucket(villain_hr, board_e7, dead, n_buckets)

    if not hero_buckets or not villain_buckets:
        return {}, {}, {}

    # Pre-compute equity matrix between bucket representatives
    equity_matrix = _compute_equity_matrix(
        hero_buckets, villain_buckets, board_e7, iterations
    )

    return hero_buckets['assignments'], villain_buckets['assignments'], equity_matrix


def _evaluate_and_bucket(hand_range, board_e7, dead, n_buckets):
    """Evaluate each combo in a range on the board and assign to buckets."""
    combo_strengths = []

    for combo in hand_range:
        cards = combo[0]
        if any(str(c) in dead for c in cards):
            continue
        combo_str = ''.join(str(c) for c in cards)

        try:
            # Hand strength (absolute, for bucketing)
            hand_val = eval7.evaluate(list(cards) + board_e7)

            # Draw detection: check if hand has flush/straight potential
            draw_bonus = _detect_draws(cards, board_e7)

            combo_strengths.append((combo_str, hand_val, draw_bonus, cards))
        except Exception:
            continue

    if not combo_strengths:
        return None

    # Sort by hand_value + draw_bonus (draws get slight bump)
    combo_strengths.sort(key=lambda x: x[1] + x[2] * 1000, reverse=True)

    bucket_size = max(1, len(combo_strengths) // n_buckets)
    assignments = {}
    representatives = {}  # {bucket_idx: representative eval7 cards}

    for i, (combo_str, val, draw, cards) in enumerate(combo_strengths):
        bucket_idx = min(i // bucket_size, n_buckets - 1)
        assignments[combo_str] = bucket_idx
        # Use middle combo as representative
        if i % bucket_size == bucket_size // 2:
            representatives[bucket_idx] = list(cards)

    # Fill any missing representatives
    for b in range(n_buckets):
        if b not in representatives:
            # Use nearest available
            for i, (combo_str, val, draw, cards) in enumerate(combo_strengths):
                if assignments[combo_str] == b:
                    representatives[b] = list(cards)
                    break

    return {
        'assignments': assignments,
        'representatives': representatives,
        'n_combos': len(combo_strengths),
    }


def _detect_draws(cards, board_e7):
    """Detect flush/straight draws. Returns a bonus value 0-2."""
    all_cards = list(cards) + board_e7
    suits = {}
    ranks = set()

    for c in all_cards:
        s = str(c)[1]
        r = '23456789TJQKA'.index(str(c)[0])
        suits[s] = suits.get(s, 0) + 1
        ranks.add(r)

    bonus = 0.0

    # Flush draw: 4 of same suit
    if max(suits.values()) >= 4:
        bonus += 1.0

    # Straight draw: 4 cards within 5 ranks
    sorted_ranks = sorted(ranks)
    for base in range(max(0, min(sorted_ranks) - 4), 14):
        count = sum(1 for r in sorted_ranks if base <= r < base + 5)
        if count >= 4:
            bonus += 0.8
            break

    return bonus


def _compute_equity_matrix(hero_data, villain_data, board_e7, iterations):
    """Pre-compute equity for each (hero_bucket, villain_bucket) pair.

    This is called ONCE before CFR iterations. CFR then uses cached values.
    """
    hero_reps = hero_data['representatives']
    villain_reps = villain_data['representatives']

    matrix = {}
    for hb, h_cards in hero_reps.items():
        for vb, v_cards in villain_reps.items():
            # Check for card conflicts
            h_set = set(str(c) for c in h_cards)
            v_set = set(str(c) for c in v_cards)
            if h_set & v_set:
                matrix[(hb, vb)] = 0.5
                continue

            try:
                # Exact evaluation if board is complete (river)
                if len(board_e7) >= 5:
                    h_val = eval7.evaluate(h_cards + board_e7)
                    v_val = eval7.evaluate(v_cards + board_e7)
                    if h_val > v_val:
                        matrix[(hb, vb)] = 1.0
                    elif h_val < v_val:
                        matrix[(hb, vb)] = 0.0
                    else:
                        matrix[(hb, vb)] = 0.5
                else:
                    # Monte Carlo for flop/turn
                    villain_single = eval7.HandRange(
                        ''.join(str(c) for c in v_cards))
                    eq = float(eval7.py_hand_vs_range_monte_carlo(
                        h_cards, villain_single, board_e7, iterations))
                    matrix[(hb, vb)] = eq
            except Exception:
                matrix[(hb, vb)] = 0.5

    return matrix


def hand_to_canonical(cards: List[str]) -> str:
    """Convert ['AH', 'KS'] to canonical 'AKo' format."""
    if not cards or len(cards) != 2:
        return ''
    rank_order = '23456789TJQKA'
    c1, c2 = cards[0].upper(), cards[1].upper()
    r1 = c1[0] if c1[0] != '1' else 'T'
    r2 = c2[0] if c2[0] != '1' else 'T'
    s1, s2 = c1[-1], c2[-1]

    ri1 = rank_order.index(r1) if r1 in rank_order else 0
    ri2 = rank_order.index(r2) if r2 in rank_order else 0

    if ri1 < ri2:
        r1, r2 = r2, r1
        s1, s2 = s2, s1

    if r1 == r2:
        return f'{r1}{r2}'
    elif s1 == s2:
        return f'{r1}{r2}s'
    else:
        return f'{r1}{r2}o'
