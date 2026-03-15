"""ICM (Independent Chip Model) calculator.

Converts chip stacks to tournament prize equity using Malmuth-Harville.
Cash games: factor = 1.0 (linear). Tournaments: non-linear (concave).
"""
import logging
from typing import List, Optional

log = logging.getLogger(__name__)


def icm_equity(stacks: List[float], payouts: List[float]) -> List[float]:
    """Compute each player's $-equity given chip stacks and prize payouts.

    Uses Malmuth-Harville model: probability of finishing in position k
    is proportional to chip stack, then recursively for remaining positions.

    Args:
        stacks: chip stacks for each player (e.g. [1500, 1000, 500])
        payouts: prizes per position (e.g. [50, 30, 20] for 1st/2nd/3rd)

    Returns:
        List of $-equities, one per player. Sums to sum(payouts).
    """
    n = len(stacks)
    total = sum(stacks)
    if total <= 0 or not payouts:
        return [0.0] * n

    pays = list(payouts) + [0.0] * max(0, n - len(payouts))
    equities = [0.0] * n

    # For each player, compute P(finish in place k) for each place k
    _icm_recursive(stacks, pays, equities, list(range(n)), 0, 1.0)
    return equities


def _icm_recursive(stacks, payouts, equities, remaining, place, prob):
    """Recursive Malmuth-Harville.

    prob = probability of reaching this branch (product of all prior place assignments).
    """
    if place >= len(payouts) or not remaining or prob < 1e-12:
        return

    total = sum(stacks[i] for i in remaining)
    if total <= 0:
        return

    for i in remaining:
        if stacks[i] <= 0:
            continue
        # P(player i finishes in this place | reached this branch)
        p_i = stacks[i] / total
        # Accumulate equity for player i
        equities[i] += prob * p_i * payouts[place]

        # Recurse: remove player i, assign next place
        new_remaining = [j for j in remaining if j != i]
        if new_remaining and place + 1 < len(payouts):
            _icm_recursive(stacks, payouts, equities, new_remaining,
                           place + 1, prob * p_i)


def icm_factor(hero_idx: int, stacks: List[float],
               payouts: List[float], chip_delta: float = 1.0) -> float:
    """Compute ICM pressure factor for range adjustment.

    Returns a multiplier 0.5-1.5 that represents how much ICM
    should tighten (< 1.0) or loosen (> 1.0) hero's ranges.

    The factor compares the risk/reward asymmetry:
    - risk = ICM$ lost if hero loses a pot of size delta
    - reward = ICM$ gained if hero wins a pot of size delta
    - factor = reward / risk

    For cash: always 1.0 (symmetric).
    For tournaments: < 1.0 when losing hurts more than winning helps.
    """
    if not payouts:
        return 1.0

    total_chips = sum(stacks)
    if total_chips <= 0 or stacks[hero_idx] <= 0:
        return 1.0

    # Use a meaningful pot-sized delta
    avg_stack = total_chips / len(stacks)
    delta = max(chip_delta, avg_stack * 0.10)
    delta = min(delta, stacks[hero_idx] * 0.40)

    base_eq = icm_equity(stacks, payouts)[hero_idx]

    # What hero gains if they win delta chips
    stacks_win = list(stacks)
    stacks_win[hero_idx] += delta
    # Chips come from opponents (distribute loss evenly)
    loss_per_opp = delta / max(1, len(stacks) - 1)
    for i in range(len(stacks_win)):
        if i != hero_idx:
            stacks_win[i] = max(0.01, stacks_win[i] - loss_per_opp)
    reward = icm_equity(stacks_win, payouts)[hero_idx] - base_eq

    # What hero loses if they lose delta chips
    stacks_lose = list(stacks)
    stacks_lose[hero_idx] = max(0.01, stacks_lose[hero_idx] - delta)
    for i in range(len(stacks_lose)):
        if i != hero_idx:
            stacks_lose[i] += loss_per_opp
    risk = base_eq - icm_equity(stacks_lose, payouts)[hero_idx]

    if risk <= 0:
        return 1.0

    factor = reward / risk
    return max(0.5, min(1.5, factor))  # Clamp to reasonable range
