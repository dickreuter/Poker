"""Nash push/fold solver using MCCFR.

Pre-computes mathematically optimal push/fold/call strategies for short stacks.
Covers All-in-or-Fold, short-stack Spin & Go, and tournament endgames.

Uses eval7 for equity calculation at showdown terminals.
"""
import logging
import os
import pickle
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

try:
    import eval7
    HAS_EVAL7 = True
except ImportError:
    HAS_EVAL7 = False

# All 169 canonical hands
_RANKS = '23456789TJQKA'
_ALL_169 = []
for i in range(13):
    for j in range(i, 13):
        if i == j:
            _ALL_169.append(f'{_RANKS[j]}{_RANKS[i]}')
        else:
            _ALL_169.append(f'{_RANKS[j]}{_RANKS[i]}s')
            _ALL_169.append(f'{_RANKS[j]}{_RANKS[i]}o')


def _hand_to_cards(hand_key: str):
    """Convert 'AKs' to eval7 Card pair."""
    if not HAS_EVAL7:
        return None, None
    r1, r2 = hand_key[0], hand_key[1]
    is_suited = hand_key.endswith('s')
    is_pair = (r1 == r2)
    if is_pair:
        return eval7.Card(f'{r1}h'), eval7.Card(f'{r2}s')
    elif is_suited:
        return eval7.Card(f'{r1}h'), eval7.Card(f'{r2}h')
    else:
        return eval7.Card(f'{r1}h'), eval7.Card(f'{r2}s')


# Pre-compute equity cache for all hand matchups
_equity_cache: Dict[Tuple[str, str], float] = {}


def _get_matchup_equity(hand1: str, hand2: str) -> float:
    """Get equity of hand1 vs hand2 preflop. Cached."""
    key = (hand1, hand2)
    if key in _equity_cache:
        return _equity_cache[key]

    c1a, c1b = _hand_to_cards(hand1)
    c2a, c2b = _hand_to_cards(hand2)
    if c1a is None or c2a is None:
        return 0.5

    # Check for card conflicts
    h1 = {str(c1a), str(c1b)}
    h2 = {str(c2a), str(c2b)}
    if h1 & h2:
        # Card conflict — use alternate suits
        if hand2.endswith('s'):
            c2a = eval7.Card(f'{hand2[0]}d')
            c2b = eval7.Card(f'{hand2[1]}d')
        else:
            c2a = eval7.Card(f'{hand2[0]}d')
            c2b = eval7.Card(f'{hand2[1]}c')
        h2 = {str(c2a), str(c2b)}
        if h1 & h2:
            _equity_cache[key] = 0.5
            return 0.5

    try:
        villain_range = eval7.HandRange(''.join(str(c) for c in [c2a, c2b]))
        eq = float(eval7.py_hand_vs_range_monte_carlo(
            [c1a, c1b], villain_range, [], 5000))
    except Exception:
        eq = 0.5

    _equity_cache[key] = eq
    _equity_cache[(hand2, hand1)] = 1.0 - eq
    return eq


def solve_push_fold(stack_bb: float, is_sb: bool = True,
                    n_iterations: int = 100,
                    icm_factor: float = 1.0) -> Dict[str, Dict[str, float]]:
    """Solve heads-up push/fold Nash equilibrium.

    Uses iterative best response with eval7 range equity for speed.
    Each iteration: build opponent's range string from their frequencies,
    then compute equity vs that range in one eval7 call per hand.

    Args:
        stack_bb: effective stack in big blinds
        is_sb: True if solving for SB/BTN (pusher), False for BB (caller)
        n_iterations: optimization iterations
        icm_factor: ICM multiplier (1.0 = cash, <1.0 = tournament pressure)

    Returns:
        {hand_key: {'push': freq, 'fold': freq}} for SB
        {hand_key: {'call': freq, 'fold': freq}} for BB
    """
    if not HAS_EVAL7:
        return {}

    # Initialize with equity-based heuristic
    push_freq = {h: 0.0 for h in _ALL_169}
    call_freq = {h: 0.0 for h in _ALL_169}

    # Warm start: push top ~40% of hands, call top ~25%
    equities = []
    any_range = eval7.HandRange('22+, A2s+, A2o+, K2s+, K5o+, Q5s+, Q8o+, J7s+, T7s+')
    for hand in _ALL_169:
        c1, c2 = _hand_to_cards(hand)
        if c1 is None:
            equities.append((hand, 0.5))
            continue
        try:
            eq = float(eval7.py_hand_vs_range_monte_carlo([c1, c2], any_range, [], 3000))
            equities.append((hand, eq))
        except Exception:
            equities.append((hand, 0.5))

    equities.sort(key=lambda x: -x[1])
    for i, (h, eq) in enumerate(equities):
        if i < len(equities) * 0.40:
            push_freq[h] = 1.0
        if i < len(equities) * 0.25:
            call_freq[h] = 1.0

    for iteration in range(n_iterations):
        lr = 2.0 / (iteration + 3)

        # Build call range string from current frequencies
        call_hands = [h for h in _ALL_169 if call_freq[h] > 0.5]
        if not call_hands:
            call_hands = ['AA', 'KK', 'QQ', 'AKs']
        call_range_str = ', '.join(call_hands)

        # Fraction of hands that call
        call_combos = sum(_hand_combos(h) for h in call_hands)
        total_combos = sum(_hand_combos(h) for h in _ALL_169)
        call_pct = call_combos / total_combos if total_combos > 0 else 0.2

        try:
            call_hr = eval7.HandRange(call_range_str)
        except Exception:
            call_hr = eval7.HandRange('QQ+, AKs')
            call_pct = 0.03

        # Step 1: Compute push EV for each hand
        for hand in _ALL_169:
            c1, c2 = _hand_to_cards(hand)
            if c1 is None:
                continue

            ev_fold = -0.5  # Lose SB

            # P(fold) × win_blinds + P(call) × (eq × 2*stack - stack)
            try:
                eq_vs_callers = float(eval7.py_hand_vs_range_monte_carlo(
                    [c1, c2], call_hr, [], 1000))
            except Exception:
                eq_vs_callers = 0.5

            ev_when_called = (eq_vs_callers * 2.0 * stack_bb - stack_bb) * icm_factor
            ev_push = (1.0 - call_pct) * 1.5 + call_pct * ev_when_called

            if ev_push > ev_fold:
                push_freq[hand] = push_freq[hand] * (1 - lr) + 1.0 * lr
            else:
                push_freq[hand] = push_freq[hand] * (1 - lr) + 0.0 * lr

        # Build push range string from current frequencies
        push_hands = [h for h in _ALL_169 if push_freq[h] > 0.5]
        if not push_hands:
            push_hands = ['AA', 'KK', 'QQ', 'JJ', 'AKs', 'AKo']
        push_range_str = ', '.join(push_hands)

        try:
            push_hr = eval7.HandRange(push_range_str)
        except Exception:
            push_hr = eval7.HandRange('JJ+, AKs, AKo')

        # Step 2: Compute call EV for each hand
        for hand in _ALL_169:
            c1, c2 = _hand_to_cards(hand)
            if c1 is None:
                continue

            ev_fold_bb = 0.0  # Already posted BB, folding costs nothing more

            try:
                eq_vs_pushers = float(eval7.py_hand_vs_range_monte_carlo(
                    [c1, c2], push_hr, [], 1000))
            except Exception:
                eq_vs_pushers = 0.5

            # Call: risk (stack_bb - 1) more chips. Win 2*stack_bb total pot.
            ev_call = (eq_vs_pushers * 2.0 * stack_bb - stack_bb) * icm_factor

            if ev_call > ev_fold_bb:
                call_freq[hand] = call_freq[hand] * (1 - lr) + 1.0 * lr
            else:
                call_freq[hand] = call_freq[hand] * (1 - lr) + 0.0 * lr

    if is_sb:
        return {h: {'push': push_freq[h], 'fold': 1.0 - push_freq[h]}
                for h in _ALL_169}
    else:
        return {h: {'call': call_freq[h], 'fold': 1.0 - call_freq[h]}
                for h in _ALL_169}


def _hand_combos(hand_key: str) -> int:
    """Number of combos for a canonical hand."""
    if len(hand_key) == 2:  # Pair
        return 6
    elif hand_key.endswith('s'):
        return 4
    else:
        return 12


def _card_removal_factor(hand1: str, hand2: str) -> float:
    """Approximate card removal (0-1 multiplier on combos)."""
    r1a, r1b = hand1[0], hand1[1]
    r2a, r2b = hand2[0], hand2[1]

    shared_ranks = 0
    if r1a == r2a or r1a == r2b:
        shared_ranks += 1
    if r1b == r2a or r1b == r2b:
        shared_ranks += 1

    if shared_ranks == 0:
        return 1.0
    elif shared_ranks == 1:
        return 0.7  # ~30% combos blocked
    else:
        return 0.3  # Most combos blocked


# ── Pre-computation and caching ─────────────────────────────────────────

_CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'solver')
_push_fold_cache: Dict[Tuple, Dict] = {}


def get_push_fold_strategy(stack_bb: float, is_sb: bool = True,
                           icm_factor: float = 1.0) -> Dict[str, Dict[str, float]]:
    """Get push/fold strategy, using cache if available.

    Rounds stack to nearest 0.5BB for caching.
    """
    # Round stack
    rounded = round(stack_bb * 2) / 2.0
    rounded = max(1.0, min(20.0, rounded))
    cache_key = (rounded, is_sb, round(icm_factor, 2))

    if cache_key in _push_fold_cache:
        return _push_fold_cache[cache_key]

    # Try loading from disk
    cache_path = os.path.join(_CACHE_DIR, 'push_fold.pkl')
    if os.path.exists(cache_path) and not _push_fold_cache:
        try:
            with open(cache_path, 'rb') as f:
                _push_fold_cache.update(pickle.load(f))
            if cache_key in _push_fold_cache:
                return _push_fold_cache[cache_key]
        except Exception:
            pass

    # Compute fresh (use fewer iterations for real-time, more for pre-compute)
    log.info(f"PUSH/FOLD: solving stack={rounded}BB is_sb={is_sb} icm={icm_factor:.2f}")
    strategy = solve_push_fold(rounded, is_sb, n_iterations=30,
                               icm_factor=icm_factor)
    _push_fold_cache[cache_key] = strategy
    return strategy


def precompute_push_fold_tables(stacks=None, icm_factors=None):
    """Pre-compute and save push/fold tables for common configurations."""
    if stacks is None:
        stacks = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15]
    if icm_factors is None:
        icm_factors = [1.0, 0.85, 0.70]  # Cash, mild ICM, strong ICM

    total = len(stacks) * 2 * len(icm_factors)
    count = 0

    for stack in stacks:
        for is_sb in [True, False]:
            for icm in icm_factors:
                cache_key = (float(stack), is_sb, round(icm, 2))
                if cache_key not in _push_fold_cache:
                    strategy = solve_push_fold(stack, is_sb, n_iterations=20000,
                                               icm_factor=icm)
                    _push_fold_cache[cache_key] = strategy
                count += 1
                if count % 10 == 0:
                    log.info(f"PUSH/FOLD: computed {count}/{total} tables")

    # Save to disk
    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(_CACHE_DIR, 'push_fold.pkl')
    with open(cache_path, 'wb') as f:
        pickle.dump(dict(_push_fold_cache), f)
    log.info(f"PUSH/FOLD: saved {len(_push_fold_cache)} tables to {cache_path}")


def should_push(hand_key: str, stack_bb: float, is_sb: bool = True,
                icm_factor: float = 1.0) -> Tuple[bool, float]:
    """Quick check: should this hand push?

    Returns:
        (should_push, push_frequency)
    """
    strategy = get_push_fold_strategy(stack_bb, is_sb, icm_factor)
    if not strategy or hand_key not in strategy:
        return False, 0.0

    freq = strategy[hand_key].get('push', 0.0)
    return freq > 0.5, freq


def should_call_shove(hand_key: str, stack_bb: float,
                      icm_factor: float = 1.0) -> Tuple[bool, float]:
    """Quick check: should BB call an all-in?

    Returns:
        (should_call, call_frequency)
    """
    strategy = get_push_fold_strategy(stack_bb, is_sb=False,
                                      icm_factor=icm_factor)
    if not strategy or hand_key not in strategy:
        return False, 0.0

    freq = strategy[hand_key].get('call', 0.0)
    return freq > 0.5, freq
