"""Unified poker solver — one system for all game types.

Architecture:
  Layer 1 (≤8BB):  Nash push/fold — pre-computed, instant lookup
  Layer 2 (8-20BB): Short-stack preflop — pre-computed open/3bet/shove
  Layer 3 (>20BB):  Real-time postflop CFR — ~1-5s per decision

ICM overlay adjusts all layers for tournament/Spin & Go equity.
eval7 is the evaluation backbone throughout.
"""
import logging
import random
import time
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

try:
    import eval7
    HAS_EVAL7 = True
except ImportError:
    HAS_EVAL7 = False

from .icm import icm_factor
from .push_fold import (
    get_push_fold_strategy, should_push, should_call_shove,
    precompute_push_fold_tables,
)
from .cfr_engine import CFRSolver
from .game_tree import build_tree, Player, Action, count_terminals
from .hand_buckets import bucket_postflop, hand_to_canonical


class SolverResult:
    """Result from the unified solver."""
    __slots__ = ('action', 'bet_size_frac', 'frequency', 'ev',
                 'strategy', 'reasoning', 'solver_layer', 'solve_time_ms')

    def __init__(self):
        self.action = 'fold'        # 'fold', 'check', 'call', 'raise', 'allin'
        self.bet_size_frac = 0.0    # Bet size as fraction of pot (0.33, 0.67, etc.)
        self.frequency = 1.0        # How often to take this action (for mixing)
        self.ev = 0.0               # Expected value in BB
        self.strategy = {}          # Full strategy: {action: frequency}
        self.reasoning = ''         # Human-readable explanation
        self.solver_layer = 0       # Which layer solved this (1, 2, or 3)
        self.solve_time_ms = 0.0    # Time spent solving


class UnifiedSolver:
    """Single entry point for all poker decisions."""

    def __init__(self):
        self._cfr = CFRSolver()
        self._postflop_cache: Dict[str, Dict] = {}

    def decide(self,
               hero_cards: List[str],
               board: List[str],
               pot: float,
               stack: float,
               call_amount: float,
               bb: float,
               position: str = 'BTN',
               villain_range_str: str = '22+, A2s+, KTo+, QJo',
               hero_range_str: str = None,
               hero_is_ip: bool = True,
               game_type: str = 'cash',
               payouts: List[float] = None,
               all_stacks: List[float] = None,
               ) -> SolverResult:
        """Route to the right solver layer and return a decision.

        Args:
            hero_cards: ['AH', 'KS']
            board: community cards (empty for preflop)
            pot: current pot in chips
            stack: hero's remaining stack
            call_amount: amount to call (0 if not facing bet)
            bb: big blind size
            position: hero's position
            villain_range_str: estimated villain range
            hero_range_str: hero's range in this spot (for balanced play)
            hero_is_ip: True if hero is in position
            game_type: 'cash', 'spin', 'tournament', 'aof'
            payouts: prize structure (None for cash)
            all_stacks: all player stacks (for ICM)

        Returns:
            SolverResult with action, sizing, frequency, and strategy.
        """
        t_start = time.monotonic()
        result = SolverResult()

        if not hero_cards or len(hero_cards) != 2 or bb <= 0:
            result.reasoning = 'Invalid input'
            return result

        eff_stack_bb = stack / bb
        hand_key = hand_to_canonical(hero_cards)

        # Compute ICM factor
        icm = 1.0
        if payouts and all_stacks and game_type != 'cash':
            try:
                hero_idx = 0  # Assume hero is first in stacks list
                icm = icm_factor(hero_idx, all_stacks, payouts, chip_delta=bb)
            except Exception:
                icm = 1.0

        # ── LAYER 1: Push/Fold (≤8BB or All-in-or-Fold) ──────────────
        if eff_stack_bb <= 8 or game_type == 'aof':
            result = self._solve_push_fold(hand_key, eff_stack_bb, position,
                                           call_amount, bb, icm)
            result.solver_layer = 1
            result.solve_time_ms = (time.monotonic() - t_start) * 1000
            return result

        # ── LAYER 2: Preflop (any stack depth) ─────────────────────────
        # Uses push/fold for short stacks, equity-based for deeper stacks.
        # No hardcoded ranges — just eval7 math.
        if not board or len(board) == 0:
            result = self._solve_short_stack_preflop(
                hand_key, hero_cards, eff_stack_bb, position,
                call_amount, bb, villain_range_str, icm
            )
            result.solver_layer = 2
            result.solve_time_ms = (time.monotonic() - t_start) * 1000
            return result

        # ── LAYER 3: Real-Time Postflop CFR ──────────────────────────
        if board and len(board) >= 3:
            result = self._solve_postflop_cfr(
                hero_cards, board, pot, stack, call_amount, bb,
                villain_range_str, hero_range_str, hero_is_ip, icm
            )
            result.solver_layer = 3
            result.solve_time_ms = (time.monotonic() - t_start) * 1000
            return result

        # ── Fallback: preflop >20BB ──────────────────────────────────
        # Use existing range_equity system (not solver, but works)
        result.action = 'check'  # Neutral default — decisionmaker.py handles real decision
        result.reasoning = 'Deep-stack preflop: deferring to existing range_equity system'
        result.solver_layer = 0
        result.solve_time_ms = (time.monotonic() - t_start) * 1000
        return result

    def _solve_push_fold(self, hand_key, stack_bb, position,
                         call_amount, bb, icm) -> SolverResult:
        """Layer 1: Nash push/fold lookup."""
        result = SolverResult()

        is_facing_shove = call_amount > 0 and call_amount >= stack_bb * bb * 0.5

        if is_facing_shove:
            # Facing all-in: call or fold
            do_call, freq = should_call_shove(hand_key, stack_bb, icm)
            if do_call:
                result.action = 'call'
                result.frequency = freq
                result.strategy = {'call': freq, 'fold': 1.0 - freq}
            else:
                result.action = 'fold'
                result.frequency = 1.0 - freq
                result.strategy = {'call': freq, 'fold': 1.0 - freq}
            result.reasoning = f'Nash push/fold: {hand_key} {stack_bb:.0f}BB call={freq:.0%}'
        else:
            # First to act or facing limp: push or fold
            # Any non-BB position is the pusher; BB is the caller
            is_sb = position.upper() not in ('BB',)
            do_push, freq = should_push(hand_key, stack_bb, is_sb, icm)

            if do_push:
                result.action = 'allin'
                result.frequency = freq
                result.strategy = {'allin': freq, 'fold': 1.0 - freq}
            else:
                result.action = 'fold'
                result.frequency = 1.0 - freq
                result.strategy = {'allin': freq, 'fold': 1.0 - freq}
            result.reasoning = f'Nash push/fold: {hand_key} {stack_bb:.0f}BB push={freq:.0%}'

        # Apply mixed strategy
        roll = random.random()
        if result.action == 'allin' and roll > freq:
            result.action = 'fold'
        elif result.action == 'call' and roll > freq:
            result.action = 'fold'
        elif result.action == 'fold' and result.strategy.get('allin', 0) > 0:
            if roll < result.strategy['allin']:
                result.action = 'allin'
        elif result.action == 'fold' and result.strategy.get('call', 0) > 0:
            if roll < result.strategy['call']:
                result.action = 'call'

        return result

    def _solve_short_stack_preflop(self, hand_key, hero_cards, stack_bb,
                                   position, call_amount, bb,
                                   villain_range_str, icm) -> SolverResult:
        """Layer 2: Equity-based preflop decisions for any stack depth.

        No hardcoded ranges. Uses eval7 to compute equity vs villain range,
        then compares to pot odds and position-based thresholds.
        """
        result = SolverResult()

        # Compute equity vs villain range
        eq = 0.5
        if HAS_EVAL7:
            try:
                from sys_core.decisionmaker.range_equity import _convert_card
                c1 = _convert_card(hero_cards[0])
                c2 = _convert_card(hero_cards[1])
                if c1 and c2:
                    vr = eval7.HandRange(villain_range_str)
                    eq = float(eval7.py_hand_vs_range_monte_carlo(
                        [c1, c2], vr, [], 5000))
            except Exception:
                eq = 0.5

        call_bb = call_amount / bb if bb > 0 else call_amount

        if call_amount > 0:
            # ── FACING A RAISE ──────────────────────────────────────────
            pot_bb = max(call_bb + 1.5, 1.5)  # Approximate pot
            pot_odds = call_bb / (pot_bb + call_bb) if (pot_bb + call_bb) > 0 else 0.5
            call_to_stack = call_bb / max(stack_bb, 1)

            # Shove-or-fold: if calling commits >30% of stack
            if call_to_stack > 0.30 and stack_bb <= 20:
                if eq >= 0.40:
                    result.action = 'allin'
                    result.frequency = 1.0
                    result.reasoning = f'Preflop shove: {hand_key} eq={eq:.0%} call/stack={call_to_stack:.0%}'
                elif eq >= pot_odds:
                    result.action = 'call'
                    result.frequency = 1.0
                    result.reasoning = f'Preflop call: {hand_key} eq={eq:.0%} > pot_odds={pot_odds:.0%}'
                else:
                    result.action = 'fold'
                    result.frequency = 1.0
                    result.reasoning = f'Preflop fold: {hand_key} eq={eq:.0%} < pot_odds={pot_odds:.0%}'

            # Normal facing raise: call if equity > pot odds, raise if strong
            else:
                if eq >= 0.55:
                    # Strong hand: 3-bet or raise
                    if stack_bb <= 25:
                        result.action = 'allin'  # Short enough to shove
                    else:
                        result.action = 'raise'
                        result.bet_size_frac = 3.0 * call_bb / max(pot_bb, 1)
                    result.frequency = 1.0
                    result.reasoning = f'Preflop raise: {hand_key} eq={eq:.0%} stack={stack_bb:.0f}BB'
                elif eq >= max(pot_odds, 0.35):
                    # Decent hand: call
                    result.action = 'call'
                    result.frequency = 1.0
                    result.reasoning = f'Preflop call: {hand_key} eq={eq:.0%} > {max(pot_odds, 0.35):.0%}'
                else:
                    result.action = 'fold'
                    result.frequency = 1.0
                    result.reasoning = f'Preflop fold: {hand_key} eq={eq:.0%} stack={stack_bb:.0f}BB'

        else:
            # ── FIRST IN (no raise to face) ─────────────────────────────
            # Open-raise threshold by position (wider in late, tighter early)
            open_thresholds = {
                'BTN': 0.33, 'SB': 0.36, 'CO': 0.37,
                'MP': 0.40, 'UTG': 0.43, 'BB': 0.50,
            }
            threshold = open_thresholds.get(position.upper(), 0.38)

            if stack_bb <= 12:
                # Short stack: shove or fold
                if eq >= threshold:
                    result.action = 'allin'
                    result.frequency = 1.0
                    result.reasoning = f'Open shove: {hand_key} eq={eq:.0%} {stack_bb:.0f}BB {position}'
                else:
                    result.action = 'fold'
                    result.frequency = 1.0
                    result.reasoning = f'Fold: {hand_key} eq={eq:.0%} < {threshold:.0%} {position}'
            else:
                # Deeper: open-raise or fold
                if eq >= threshold:
                    result.action = 'raise'
                    result.bet_size_frac = 2.2  # ~2.2BB open
                    result.frequency = 1.0
                    result.reasoning = f'Open raise: {hand_key} eq={eq:.0%} {stack_bb:.0f}BB {position}'
                else:
                    result.action = 'fold'
                    result.frequency = 1.0
                    result.reasoning = f'Fold: {hand_key} eq={eq:.0%} < {threshold:.0%} {position}'

        return result

    def _solve_postflop_cfr(self, hero_cards, board, pot, stack,
                            call_amount, bb, villain_range_str,
                            hero_range_str, hero_is_ip, icm) -> SolverResult:
        """Layer 3: Real-time postflop CFR solving."""
        result = SolverResult()

        if not HAS_EVAL7:
            result.action = 'check' if call_amount == 0 else 'fold'
            result.reasoning = 'No eval7 for CFR'
            return result

        # Default hero range if not provided
        if not hero_range_str:
            hero_range_str = villain_range_str  # Rough approximation

        spr = stack / pot if pot > 0 else 10.0
        n_buckets = 15 if spr < 5 else 20

        # Choose iterations based on SPR (deeper = more complex = more iters)
        if spr < 3:
            n_iters = 200
        elif spr < 8:
            n_iters = 350
        else:
            n_iters = 500

        # Bucket hands
        try:
            hero_buckets, villain_buckets, equity_matrix = bucket_postflop(
                hero_range_str, villain_range_str, board, n_buckets=n_buckets
            )
        except Exception as e:
            log.warning(f"CFR bucketing failed: {e}")
            result.action = 'check' if call_amount == 0 else 'fold'
            result.reasoning = f'Bucketing failed: {e}'
            return result

        if not hero_buckets or not villain_buckets or not equity_matrix:
            result.action = 'check' if call_amount == 0 else 'fold'
            result.reasoning = 'Empty buckets'
            return result

        # Find hero's bucket
        from sys_core.decisionmaker.range_equity import _convert_card
        hero_e7 = [_convert_card(c) for c in hero_cards]
        hero_e7 = [c for c in hero_e7 if c is not None]
        hero_combo_str = ''.join(str(c) for c in hero_e7)
        hero_bucket = hero_buckets.get(hero_combo_str)

        if hero_bucket is None:
            # Try reversed order
            hero_combo_str_rev = ''.join(str(c) for c in reversed(hero_e7))
            hero_bucket = hero_buckets.get(hero_combo_str_rev)

        if hero_bucket is None and hero_e7 and len(hero_e7) == 2:
            # Find nearest bucket by hand strength on this board
            try:
                board_e7_lookup = [_convert_card(c) for c in board if c]
                board_e7_lookup = [c for c in board_e7_lookup if c]
                hero_val = eval7.evaluate(list(hero_e7) + board_e7_lookup)
                # Find bucket whose representative has closest hand value
                best_dist = float('inf')
                for combo_str, bucket_idx in hero_buckets.items():
                    try:
                        combo_cards = [eval7.Card(combo_str[i:i+2])
                                       for i in range(0, len(combo_str), 2)]
                        dead = set(str(c) for c in board_e7_lookup)
                        if any(str(c) in dead for c in combo_cards):
                            continue
                        val = eval7.evaluate(combo_cards + board_e7_lookup)
                        dist = abs(val - hero_val)
                        if dist < best_dist:
                            best_dist = dist
                            hero_bucket = bucket_idx
                    except Exception:
                        continue
            except Exception:
                pass

        if hero_bucket is None:
            # Last resort: use middle bucket
            if hero_buckets:
                hero_bucket = max(hero_buckets.values()) // 2
            else:
                result.action = 'check' if call_amount == 0 else 'fold'
                result.reasoning = 'Hero hand not in range buckets'
                return result

        n_hero = max(hero_buckets.values()) + 1 if hero_buckets else 1
        n_villain = max(villain_buckets.values()) + 1 if villain_buckets else 1

        # Build game tree
        stacks_tuple = (stack, stack)  # Assume symmetric for simplicity
        tree = build_tree(pot, stacks_tuple, hero_is_ip=hero_is_ip, spr=spr)

        n_terms = count_terminals(tree)
        log.info(f"CFR: {n_terms} terminals, {n_hero}×{n_villain} buckets, "
                 f"{n_iters} iterations, SPR={spr:.1f}")

        # Solve with DCFR
        try:
            self._cfr = CFRSolver()
            avg_strategy = self._cfr.solve(
                tree, n_hero, n_villain, equity_matrix, n_iters
            )
        except Exception as e:
            log.warning(f"CFR solve failed: {e}")
            result.action = 'check' if call_amount == 0 else 'fold'
            result.reasoning = f'CFR failed: {e}'
            return result

        # Look up strategy for hero's bucket at root
        hero_strategy = self._cfr.get_strategy_for_hand(
            avg_strategy, Player.HERO, hero_bucket, ''
        )

        if not hero_strategy:
            # Try all possible histories where hero acts
            for hist in ['x', 'xb', 'xB', 'xA', 'b', 'B', 'A']:
                hero_strategy = self._cfr.get_strategy_for_hand(
                    avg_strategy, Player.HERO, hero_bucket, hist
                )
                if hero_strategy:
                    break

        if not hero_strategy:
            # Search all info sets for this bucket
            for info_set, strat in avg_strategy.items():
                if info_set[0] == Player.HERO and info_set[1] == hero_bucket:
                    hero_strategy = strat
                    break

        if not hero_strategy:
            result.action = 'check' if call_amount == 0 else 'fold'
            result.reasoning = 'No strategy found for hero bucket'
            return result

        result.strategy = hero_strategy

        # ── Equity sanity check ──────────────────────────────────────
        # If hero's actual equity is very low, override aggressive CFR
        # outputs. The CFR may have bucketing errors that map trash to
        # strong buckets. This gate prevents catastrophic bluffs.
        hero_eq_actual = None
        try:
            villain_hr = eval7.HandRange(villain_range_str)
            _board_for_eq = [_convert_card(c) for c in board if c]
            _board_for_eq = [c for c in _board_for_eq if c is not None]
            hero_eq_actual = float(eval7.py_hand_vs_range_monte_carlo(
                hero_e7, villain_hr, _board_for_eq, 2000))
        except Exception:
            pass

        if hero_eq_actual is not None and hero_eq_actual < 0.20:
            # Very weak hand — override CFR output entirely
            if call_amount > 0:
                # Facing a bet with trash — fold unless pot odds are good
                pot_odds = call_amount / (pot + call_amount) if (pot + call_amount) > 0 else 1.0
                if hero_eq_actual < pot_odds:
                    hero_strategy = {Action.FOLD: 1.0}
                    log.info(f"CFR EQUITY GATE: eq={hero_eq_actual:.0%} < pot_odds={pot_odds:.0%} → fold")
                else:
                    hero_strategy = {Action.CALL: 1.0}
                    log.info(f"CFR EQUITY GATE: eq={hero_eq_actual:.0%} >= pot_odds={pot_odds:.0%} → call")
            else:
                # Not facing a bet — check (free)
                hero_strategy = {Action.CHECK: 1.0}
                log.info(f"CFR EQUITY GATE: eq={hero_eq_actual:.0%} < 15% → check")

        result.strategy = hero_strategy

        # Sample action from mixed strategy
        roll = random.random()
        cumulative = 0.0
        chosen_action = None
        for action, freq in sorted(hero_strategy.items(),
                                   key=lambda x: -x[1]):
            cumulative += freq
            if roll <= cumulative:
                chosen_action = action
                break
        if chosen_action is None:
            chosen_action = max(hero_strategy, key=hero_strategy.get)

        # Map solver action to bot action
        result.action, result.bet_size_frac = self._map_action(
            chosen_action, call_amount, pot
        )
        result.frequency = hero_strategy.get(chosen_action, 0.0)
        result.reasoning = (
            f'CFR {n_iters}it: {hand_to_canonical(hero_cards)} bucket={hero_bucket} '
            f'eq={hero_eq_actual:.0%} '
            f'strategy={_fmt_strategy(hero_strategy)}'
        ) if hero_eq_actual is not None else (
            f'CFR {n_iters}it: {hand_to_canonical(hero_cards)} bucket={hero_bucket} '
            f'strategy={_fmt_strategy(hero_strategy)}'
        )

        return result

    def _map_action(self, solver_action, call_amount, pot):
        """Map solver action string to bot action + bet size."""
        if solver_action == Action.FOLD:
            return 'fold', 0.0
        elif solver_action == Action.CHECK:
            return 'check' if call_amount == 0 else 'call', 0.0
        elif solver_action == Action.CALL:
            return 'call', 0.0
        elif solver_action == Action.BET_SMALL:
            return 'raise', 0.33
        elif solver_action == Action.BET_MEDIUM:
            return 'raise', 0.67
        elif solver_action == Action.BET_LARGE:
            return 'raise', 1.25
        elif solver_action == Action.ALLIN:
            return 'allin', 99.0  # Signal for all-in
        return 'check' if call_amount == 0 else 'fold', 0.0


def _fmt_strategy(strategy):
    """Format strategy dict for logging."""
    parts = []
    for action, freq in sorted(strategy.items(), key=lambda x: -x[1]):
        if freq > 0.01:
            parts.append(f'{action}={freq:.0%}')
    return ' '.join(parts)


# ── Singleton ──────────────────────────────────────────────────────────────

_solver_instance = None


def get_solver() -> UnifiedSolver:
    """Get or create the global solver instance."""
    global _solver_instance
    if _solver_instance is None:
        _solver_instance = UnifiedSolver()
    return _solver_instance
