""""
Strategy Definition
t contains variables that have been scraped from the table
h contains values from the historical (last) decision
p contains values from the Strategy as defined in the xml file
"""

# pylint: disable=too-many-boolean-expressions,unused-argument,too-many-branches,chained-comparison,singleton-comparison

import logging
import numpy as np
from enum import Enum
import random
from gamble.decisionmaker.base import DecisionBase
from gamble.tools.helper import GameStages, DecisionTypes
from gamble.decisionmaker.montecarlo_python import MonteCarlo, run_montecarlo_wrapper
from gamble.decisionmaker.range_equity import (
    compute_bet_size_bb, geometric_bet_fraction,
    preflop_raise_size_bb, lookup_preflop_equity
)
from gamble.decisionmaker.curvefitting import Curvefitting
from .outs_calculator import Outs_Calculator

log = logging.getLogger(__name__)

# --- Load strategy adjustments from feedback loop ---
_strategy_adj = None

def _get_adj():
    """Lazy-load strategy adjustments (cached)."""
    global _strategy_adj
    if _strategy_adj is None:
        try:
            from gamble.tools.strategy_adjuster import load_adjustments
            _strategy_adj = load_adjustments()
            if _strategy_adj.get('detected_leaks'):
                log.info(f"Strategy adjustments loaded: {len(_strategy_adj['detected_leaks'])} leaks detected")
        except Exception:
            _strategy_adj = {}
    return _strategy_adj

# ─── GTO 6-max preflop ranges (solver-derived) ───────────────────────────────
# Hand notation: "AKS"=suited, "AKO"=offsuit, "AA"=pair
# These are used when the Excel preflop sheet doesn't cover a hand.

# Open-raise ranges by position (first in)
GTO_OPEN = {
    'UTG': {  # ~15% of hands
        'AA', 'KK', 'QQ', 'JJ', 'TT', '99', '88', '77', '66',
        'AKS', 'AQS', 'AJS', 'ATS', 'A5S', 'A4S', 'A3S', 'A2S',
        'AKO', 'AQO', 'AJO',
        'KQS', 'KJS', 'KTS',
        'QJS', 'QTS',
        'JTS', 'T9S', '98S', '87S', '76S',
    },
    'MP': {  # ~20% of hands
        'AA', 'KK', 'QQ', 'JJ', 'TT', '99', '88', '77', '66', '55',
        'AKS', 'AQS', 'AJS', 'ATS', 'A9S', 'A8S', 'A5S', 'A4S', 'A3S', 'A2S',
        'AKO', 'AQO', 'AJO', 'ATO',
        'KQS', 'KJS', 'KTS', 'K9S',
        'KQO',
        'QJS', 'QTS', 'Q9S',
        'JTS', 'J9S',
        'T9S', 'T8S', '98S', '87S', '76S', '65S',
    },
    'CO': {  # ~28% of hands
        'AA', 'KK', 'QQ', 'JJ', 'TT', '99', '88', '77', '66', '55', '44', '33', '22',
        'AKS', 'AQS', 'AJS', 'ATS', 'A9S', 'A8S', 'A7S', 'A6S', 'A5S', 'A4S', 'A3S', 'A2S',
        'AKO', 'AQO', 'AJO', 'ATO', 'A9O',
        'KQS', 'KJS', 'KTS', 'K9S', 'K8S',
        'KQO', 'KJO',
        'QJS', 'QTS', 'Q9S', 'Q8S',
        'QJO',
        'JTS', 'J9S', 'J8S',
        'JTO',
        'T9S', 'T8S', '98S', '97S', '87S', '86S', '76S', '75S', '65S', '54S',
    },
    'BTN': {  # ~42% of hands
        'AA', 'KK', 'QQ', 'JJ', 'TT', '99', '88', '77', '66', '55', '44', '33', '22',
        'AKS', 'AQS', 'AJS', 'ATS', 'A9S', 'A8S', 'A7S', 'A6S', 'A5S', 'A4S', 'A3S', 'A2S',
        'AKO', 'AQO', 'AJO', 'ATO', 'A9O', 'A8O', 'A7O', 'A6O', 'A5O', 'A4O', 'A3O', 'A2O',
        'KQS', 'KJS', 'KTS', 'K9S', 'K8S', 'K7S', 'K6S', 'K5S', 'K4S',
        'KQO', 'KJO', 'KTO', 'K9O',
        'QJS', 'QTS', 'Q9S', 'Q8S', 'Q7S', 'Q6S',
        'QJO', 'QTO',
        'JTS', 'J9S', 'J8S', 'J7S',
        'JTO', 'J9O',
        'T9S', 'T8S', 'T7S',
        'T9O',
        '98S', '97S', '96S', '87S', '86S', '76S', '75S', '65S', '64S', '54S', '53S', '43S',
    },
    'SB': {  # ~38% of hands (slightly tighter OOP)
        'AA', 'KK', 'QQ', 'JJ', 'TT', '99', '88', '77', '66', '55', '44', '33', '22',
        'AKS', 'AQS', 'AJS', 'ATS', 'A9S', 'A8S', 'A7S', 'A6S', 'A5S', 'A4S', 'A3S', 'A2S',
        'AKO', 'AQO', 'AJO', 'ATO', 'A9O', 'A8O', 'A7O', 'A5O', 'A4O',
        'KQS', 'KJS', 'KTS', 'K9S', 'K8S', 'K7S', 'K6S', 'K5S',
        'KQO', 'KJO', 'KTO',
        'QJS', 'QTS', 'Q9S', 'Q8S', 'Q7S',
        'QJO', 'QTO',
        'JTS', 'J9S', 'J8S',
        'JTO',
        'T9S', 'T8S', 'T7S',
        'T9O',
        '98S', '97S', '87S', '86S', '76S', '75S', '65S', '54S',
    },
}

# 3-bet ranges by position vs open raiser
GTO_3BET = {
    'vs_UTG': {  # Tight linear
        'AA', 'KK', 'QQ', 'JJ', 'AKS', 'AKO', 'AQS',
        'A5S', 'A4S',  # Bluffs
    },
    'vs_MP': {
        'AA', 'KK', 'QQ', 'JJ', 'TT', 'AKS', 'AKO', 'AQS', 'AQO',
        'A5S', 'A4S', 'A3S', 'KQS',  # Bluffs
    },
    'vs_CO': {
        'AA', 'KK', 'QQ', 'JJ', 'TT', '99', 'AKS', 'AKO', 'AQS', 'AQO', 'AJS', 'AJO',
        'KQS', 'A5S', 'A4S', 'A3S', 'A2S', '76S', '65S',  # Bluffs
    },
    'vs_BTN': {
        'AA', 'KK', 'QQ', 'JJ', 'TT', '99', '88',
        'AKS', 'AKO', 'AQS', 'AQO', 'AJS', 'AJO', 'ATS', 'ATO',
        'KQS', 'KJS', 'KQO',
        'A9S', 'A8S', 'A5S', 'A4S', 'A3S', 'A2S',
        'QJS', 'JTS', 'T9S', '98S', '87S', '76S', '65S', '54S',  # Bluffs
    },
}

# BB defend range (call vs open raise)
GTO_BB_DEFEND = {
    'AA', 'KK', 'QQ', 'JJ', 'TT', '99', '88', '77', '66', '55', '44', '33', '22',
    'AKS', 'AQS', 'AJS', 'ATS', 'A9S', 'A8S', 'A7S', 'A6S', 'A5S', 'A4S', 'A3S', 'A2S',
    'AKO', 'AQO', 'AJO', 'ATO', 'A9O', 'A8O', 'A7O', 'A6O', 'A5O', 'A4O', 'A3O',
    'KQS', 'KJS', 'KTS', 'K9S', 'K8S', 'K7S', 'K6S', 'K5S', 'K4S', 'K3S', 'K2S',
    'KQO', 'KJO', 'KTO', 'K9O',
    'QJS', 'QTS', 'Q9S', 'Q8S', 'Q7S', 'Q6S', 'Q5S',
    'QJO', 'QTO', 'Q9O',
    'JTS', 'J9S', 'J8S', 'J7S',
    'JTO', 'J9O',
    'T9S', 'T8S', 'T7S',
    'T9O',
    '98S', '97S', '96S', '87S', '86S', '76S', '75S', '65S', '64S', '54S', '53S', '43S',
}


def _normalize_hand(crd1: str, crd2: str) -> str:
    """Normalize hand like 'AKS'/'AKO'/'AA' from two card short notations.

    Input: two strings from MonteCarlo.get_two_short_notation(), e.g. 'AKS', 'KAS'
    Returns the canonical form (higher card first).
    """
    # Handle pair
    if len(crd1) >= 2 and crd1[0] == crd1[1]:
        return crd1[0:2]
    if len(crd2) >= 2 and crd2[0] == crd2[1]:
        return crd2[0:2]

    # Extract rank + suited/offsuit from crd1 or crd2
    for crd in (crd1, crd2):
        if len(crd) >= 3:
            r1, r2, suit_char = crd[0], crd[1], crd[2]
            # Ensure higher rank first
            rank_order = '23456789TJQKA'
            if rank_order.index(r1) < rank_order.index(r2):
                r1, r2 = r2, r1
            return r1 + r2 + suit_char
        elif len(crd) == 2:
            return crd  # Pair like 'AA'

    return crd1  # Fallback


def gto_preflop_decision(crd1: str, crd2: str, position: str,
                         has_raiser: bool, call_amount: float,
                         has_check: bool, hero_stack: float = 100.0,
                         raiser_position: str = '') -> str:
    """Return GTO preflop decision: 'raise', 'call', 'check', or 'fold'.

    Uses solver-derived ranges instead of raw equity thresholds.
    raiser_position: position of the raiser (UTG/MP/CO/BTN/SB/BB) for 3-bet range lookup.
    """
    hand = _normalize_hand(crd1, crd2)
    pos = position.upper() if position else 'UNKNOWN'
    
    log.info(f"GTO ANALYSIS: hand={hand} pos={pos} raiser={has_raiser} "
             f"call={call_amount:.1f} stack={hero_stack:.1f} rpos={raiser_position}")

    # ─── PREMIUM SHIELD ──────────────────────────────────────────────────────
    # Guaranteed never to fold these hands preflop to a single raise. 
    # If not in a 3-bet range, always call.
    PREMIUMS = {'AA', 'KK', 'QQ', 'JJ', 'TT', '99', 'AKS', 'AKO', 'AQS', 'AJS', 'KQS'}
    is_premium = hand in PREMIUMS

    # BB with check option (unraised pot / limped pot)
    if has_check and pos == 'BB':
        bb_raise_range = GTO_OPEN.get('BTN', set())
        if hand in bb_raise_range:
            log.debug("BB unraised: raising wide for isolation")
            return 'raise'
        return 'check'

    # Facing a raise
    if has_raiser and call_amount > 0:
        # PREMIUM SHIELD (Action-Facing): Never fold these to a single raise.
        if is_premium:
            log.info(f"PREMIUM SHIELD: defending {hand} against raise")
            # Determine if we should 3-bet or just call
            rpos = raiser_position.upper() if raiser_position else ''
            if rpos in ('UTG',): raiser_key = 'vs_UTG'
            elif rpos in ('MP',): raiser_key = 'vs_MP'
            elif rpos in ('CO',): raiser_key = 'vs_CO'
            else: raiser_key = 'vs_BTN'
            
            if hand in GTO_3BET.get(raiser_key, set()):
                return 'raise'
            return 'call'

        rpos = raiser_position.upper() if raiser_position else ''
        if rpos in ('UTG',): raiser_key = 'vs_UTG'
        elif rpos in ('MP',): raiser_key = 'vs_MP'
        elif rpos in ('CO',): raiser_key = 'vs_CO'
        else: raiser_key = 'vs_BTN'

        # Check 3-bet range
        if hand in GTO_3BET.get(raiser_key, set()):
            log.debug(f"Hand in 3-bet range {raiser_key}")
            return 'raise'

        # MIXED STRATEGY (Bluffs)
        if hand in ('A5S', 'A4S', 'A3S', '76S', '65S', '54S'):
            if random.random() < 0.30:
                log.info(f"MIXED BLUFF: randomized 3-bet with {hand}")
                return 'raise'

        # Premium Trapping/Defending (redundant with shield above but kept for flow)
        if is_premium:
            log.info(f"PREMIUM SHIELD: calling with {hand} (not in 3-bet range)")
            return 'call'

        # Stack-relative call gating
        call_to_stack = call_amount / max(hero_stack, 1.0)
        
        # BB Defense (Deep math)
        if pos == 'BB':
            if hand in GTO_BB_DEFEND:
                # Fix 4: Tiered BB defense based on raise size
                # call_to_stack is raise_size / hero_stack
                # Typical raise is 2-2.5BB. If stack is 100BB, call_to_stack is 0.02.
                # If stack is 25BB (Spin), call_to_stack is 0.08.
                
                # Convert call_amount to relative BB size
                raise_size_bb = call_amount / 1.0 # Approximate
                
                if call_to_stack > 0.45 and hand not in GTO_3BET.get('vs_BTN', set()):
                    log.debug(f"BB Defense: folding {hand} vs massive {call_to_stack:.0%} stack raise")
                    return 'fold'
                
                # Tiered defense vs smaller raises
                if call_to_stack > 0.15: # Large raise (>4x in Spin, >15x in Cash)
                    # Tighten to only top 50% of defend range + premiums
                    if random.random() < 0.50 and hand not in PREMIUMS:
                        log.debug(f"BB Defense: tightening vs large raise ({call_to_stack:.2f})")
                        return 'fold'
                elif call_to_stack > 0.10: # Medium raise (3x-4x in Spin)
                    # Tighten ~30%
                    if random.random() < 0.30 and hand not in PREMIUMS:
                        log.debug(f"BB Defense: tightening vs medium raise ({call_to_stack:.2f})")
                        return 'fold'

                log.debug(f"BB Defense: calling with {hand}")
                return 'call'
        
        # Other positions (IP/SB)
        open_range = GTO_OPEN.get(pos, GTO_OPEN.get('CO', set()))
        if hand in open_range:
            # GTO: Call vs raise if in open range and not massive commitment
            if call_to_stack > 0.45:
                log.debug(f"Commitment: folding {hand} vs {call_to_stack:.0%} stack raise")
                return 'fold'
            log.debug(f"Open-range Defense: calling with {hand}")
            return 'call'

        log.debug(f"GTO Default: folding weak hand {hand}")
        return 'fold'

    # First in (no raiser) — open raise
    open_range = GTO_OPEN.get(pos, GTO_OPEN.get('CO', set()))
    if hand in open_range:
        log.debug(f"Open-raising {hand} from {pos}")
        return 'raise'

    # SB complete/check
    if pos == 'SB' and has_check:
        log.debug("SB completing/checking")
        return 'check'

    # BB safety
    if pos == 'BB' and not has_raiser:
        return 'check'

    log.debug("GTO Default: folding")
    return 'fold'


class Decision(DecisionBase):
    """
    Core strategy engine that maps game state and equity to poker actions.

    HYBRID STRATEGY ARCHITECTURE:
    1. GTO Preflop: Uses POSITION-based static ranges for opens, 3-bets, and 4-bets.
    2. Nash Equilibrium: Employs specialized push/fold ranges for short stacks (<=15 BB).
    3. Range-Based Equity (eval7): Computes real-time equity against estimated 
       opponent ranges instead of random hands.
    4. Postflop Sizing: Dynamic bet sizing based on pot odds, SPR, and board wetness.

    SAFETY MECHANICS:
    - Preflop Safety Floors: Overrides actions to 'fold' if equity < 0.22/0.28 to prevent
      acting on card misreads (e.g. 5S+5S read as pocket 5s).
    - PREMIUM EXEMPTION: Explicitly ignores safety floors for hands in 
      {'AA', 'KK', 'QQ', 'JJ', 'AKS', 'AKO', 'AQS'} to ensure strongest hands 
      are never folded due to equity miscalculations.
    """
    def __init__(self, t, h, p, l):
        # Use OCR-detected blinds if available (set by GameState.to_table_scraper_compat),
        # otherwise fall back to strategy config
        if not getattr(t, 'bigBlind', 0) or t.bigBlind <= 0:
            t.bigBlind = float(p.selected_strategy['bigBlind'])
        if not getattr(t, 'smallBlind', 0) or t.smallBlind <= 0:
            t.smallBlind = float(p.selected_strategy['smallBlind'])

        t.bigBlindMultiplier = t.bigBlind / 0.02

        # --- SPR (Stack-to-Pot Ratio) ---
        # Critical for commitment decisions: SPR<3=committed, SPR 3-7=medium, SPR>7=deep
        my_stack = getattr(t, 'myFunds', 0) or 0
        pot = max(getattr(t, 'totalPotValue', 0) or 0, t.bigBlind)
        self.spr = my_stack / pot if pot > 0 else 20.0
        
        # GGPoker/Rush BB display mode: all values are already in BB units.
        # Do NOT divide by t.bigBlind (which is the dollar value, e.g. 0.02).
        self.hero_stack_bb = my_stack
        log.info(f"SPR={self.spr:.1f} stack={my_stack:.1f} pot={pot:.1f} stack_bb={self.hero_stack_bb:.0f}")

        # pylint: disable=unidiomatic-typecheck
        pots = [player['pot']
                for player in t.other_players if type(player['pot']) != str]
        try:
            self.max_player_pot = max(pots)
            log.debug("Highest player pot: %s", self.max_player_pot)
        except:
            self.max_player_pot = 0
        log.debug("Round pot: " + str(t.round_pot_value))
        if t.round_pot_value == 0:
            t.round_pot_value = t.bigBlind * 4
            log.debug("Assuming round pot is 4*bigBlind")
        self.pot_multiple = self.max_player_pot / t.round_pot_value
        if self.pot_multiple == '':
            self.pot_multiple = 0

        if p.selected_strategy['use_pot_multiples']:
            log.info(
                "Using pot multiple: Replacing mincall and minbet: " + str(self.pot_multiple))
            t.minCall = self.pot_multiple
            t.minBet = self.pot_multiple
        else:
            try:
                t.minCall = float(t.currentCallValue)
            except:
                t.minCall = float(0.0)
                if not t.checkButton:
                    log.warning(
                        "Failed to convert current Call value, saving error.png, deriving from bet value, result:")
                    self.DeriveCallButtonFromBetButton = True
                    t.minCall = np.round(
                        float(t.get_current_bet_value(p)) / 2, 2)
                    log.info("mincall: " + str(t.minCall))
                    # adjMinCall=minCall*c1*c2

            try:
                t.minBet = float(t.currentBetValue)
                t.opponentBetIncreases = t.minBet - h.myLastBet
            except:
                log.warning("Betvalue not recognised!")
                t.minBet = float(100.0)
                t.opponentBetIncreases = 0

        if t.gameStage != 'PreFlop' and p.selected_strategy['use_relative_equity']:
            log.info("Replacing equity with relative equity")
            t.equity = t.relative_equity
        else:
            t.equity = t.abs_equity
            log.info("Use absolute equity")

        # --- Range-based equity (eval7) ---
        # Overrides Monte Carlo equity when we can estimate villain's range
        try:
            # OPTIMIZATION: If the unified pipeline already calculated range_equity, use it
            if hasattr(t, 'range_equity') and t.range_equity is not None:
                log.info(f"UNIFIED EQUITY: Using pre-calculated range equity: {t.range_equity:.1%}")
                t.equity = t.range_equity
            elif getattr(t, 'mycards', None) and len(t.mycards) == 2:
                from gamble.decisionmaker.range_equity import get_range_equity
                re = get_range_equity()
                opp_profile = getattr(self, '_opp_profile', None) or {}
                ptype = opp_profile.get('type', 'unknown') if opp_profile.get('hands', 0) >= 10 else 'unknown'

                # Determine villain's action
                if t.allInCallButton:
                    v_action = 'all_in'
                elif t.minCall > 0 and getattr(t, 'first_raiser', False):
                    v_action = '3bet'
                elif not t.checkButton and t.minCall > 0:
                    v_action = 'bet'
                elif t.gameStage == 'PreFlop':
                    v_action = 'open'
                else:
                    v_action = 'check'

                street = t.gameStage.lower() if t.gameStage != 'PreFlop' else 'preflop'

                # Estimate villain position from raiser info + hero position
                _utg_to_pos = {0: 'UTG', 1: 'MP', 2: 'CO', 3: 'BTN', 4: 'SB', 5: 'BB'}
                _hero_pos = getattr(t, '_gto_position', 'UNKNOWN')
                import math as _math
                _raiser_utg = getattr(t, 'first_raiser_utg', float('nan'))
                if not _math.isnan(_raiser_utg):
                    v_position = _utg_to_pos.get(int(_raiser_utg), 'CO')
                elif _hero_pos in ('BB', 'SB'):
                    # We're in the blinds facing action — villain likely late position
                    v_position = 'BTN'
                elif _hero_pos == 'UTG':
                    # We opened, villain 3-bet — likely BTN/CO
                    v_position = 'CO' if v_action == '3bet' else 'MP'
                else:
                    v_position = 'CO'  # Safe default

                v_range = re.estimate_villain_range(
                    position=v_position,
                    action=v_action,
                    player_type=ptype,
                    street=street,
                )

                board = getattr(t, 'cardsOnTable', []) or []

                # Use pre-computed table for preflop (instant), live calc for postflop
                range_eq = None
                if t.gameStage == 'PreFlop':
                    from gamble.decisionmaker.range_equity import lookup_preflop_equity
                    range_eq = lookup_preflop_equity(t.mycards, v_range)
                    if range_eq is not None:
                        log.debug(f"PREFLOP LOOKUP: {range_eq:.1%} (cached)")

                if range_eq is None:
                    if street != 'preflop' and board and len(board) >= 3:
                        # Board-aware filtering: evaluate each combo on the actual
                        # board, remove hands too weak to bet, compute equity vs
                        # the realistic betting range.
                        range_eq, filter_info = re.equity_vs_board_aware_range(
                            t.mycards, board, v_range,
                            street=street, action=v_action,
                            player_type=ptype,
                        )
                        log.info(f"BOARD-AWARE RANGE: {filter_info}")
                    else:
                        range_eq = re.equity_vs_range(t.mycards, board, v_range, iterations=10000)

                log.info(f"RANGE EQUITY: {range_eq:.1%} vs {ptype} {v_position} {v_action} "
                         f"(old Monte Carlo: {t.equity:.1%}, range: {v_range[:60]})")

                # Use range equity (accurate vs estimated villain range)
                t.equity = range_eq
                t.range_equity = range_eq
        except Exception as e:
            log.debug(f"Range equity failed (using Monte Carlo): {e}")

        out_multiplier = p.selected_strategy['out_multiplier']
        oc = Outs_Calculator()
        if 3 <= len(t.cardsOnTable) <= 4:  #
            try:
                outs = oc.evaluate_hands(t.mycards, t.cardsOnTable, oc)
            except:
                outs = 0
                log.critical("Error in outs calculation!")
        else:
            outs = 0
        self.out_adjustment = outs * out_multiplier * .01

        self.outs = outs

        if outs > 0:
            log.info("Minimum equity is reduced because of outs by percent: %s", int(
                self.out_adjustment * 100))

        # Positional Adjustment: only penalize when we don't know who is behind us.
        # If we are in BB, we close the action (penalty = 0).
        pos_penalty_factor = float(p.selected_strategy['pre_flop_equity_reduction_by_position'])
        hero_pos = getattr(t, '_gto_position', 'CO')
        
        if hero_pos == 'BB':
            self.preflop_adjustment = 0.0
        elif hero_pos == 'SB':
            self.preflop_adjustment = -pos_penalty_factor * 0.5 # Half penalty for SB
        else:
            self.preflop_adjustment = -pos_penalty_factor * t.position_utg_plus
            
        log.info(f"Preflop adjustment (Pos={hero_pos}, UTG+{t.position_utg_plus}): {self.preflop_adjustment}")

        # Raiser Adjustment: if someone raised, we need more equity, UNLESS we are in BB
        if not np.isnan(t.first_raiser_utg):
            raiser_penalty = float(p.selected_strategy['pre_flop_equity_increase_if_bet'])
            if hero_pos != 'BB':
                self.preflop_adjustment += raiser_penalty
            else:
                # In BB facing a raise, we only need small adjustment for the raiser's strength
                self.preflop_adjustment += raiser_penalty * 0.3 
                
        log.info(f"Preflop adjustment including raisers: {self.preflop_adjustment:.3f}")

        if not np.isnan(t.first_caller_utg):
            # Limpers/callers add "dead money" -> reduce required equity
            caller_bonus = float(p.selected_strategy['pre_flop_equity_increase_if_call'])
            self.preflop_adjustment += caller_bonus
            
        log.info(f"Preflop final adjustment: {self.preflop_adjustment:.3f}")

        # in case the other players called my bet become less aggressive and make an adjustment for the second round
        if (h.histGameStage == t.gameStage and h.lastRoundGameID == h.GameID) or h.lastSecondRoundAdjustment > 0:
            if t.gameStage == 'PreFlop':
                self.secondRoundAdjustment = float(
                    p.selected_strategy['secondRoundAdjustmentPreFlop'])
            else:
                self.secondRoundAdjustment = float(
                    p.selected_strategy['secondRoundAdjustment'])

            secondRoundAdjustmentPowerIncrease = int(
                p.selected_strategy['secondRoundAdjustmentPowerIncrease'])
        else:
            self.secondRoundAdjustment = 0
            secondRoundAdjustmentPowerIncrease = 0

        P = float(t.totalPotValue)
        self.maxCallEV = self.calc_EV_call_limit(t.equity, P)
        # self.maxBetEV = self.calc_bet_limit(t.equity, P, float(p.selected_strategy['c']), t, logger)
        log.debug("Max call EV: " + str(self.maxCallEV))

        self.DeriveCallButtonFromBetButton = False

        # --- Analysis attributes (computed after decision) ---
        self.decision_ev = 0.0
        self.blockers_info = {}
        self.opponent_range_estimate = {}
        self._opp_profile = None  # Set by runner from OpponentModeler

        # --- Multi-street planning: track previous street actions ---
        self._prev_street_action = None   # Set by runner: 'bet', 'check', 'call', 'fold'
        self._prev_street_equity = None   # Set by runner: equity on previous street
        self._we_bet_prev_street = False  # Set by runner: True if we bet/raised prev street

        # --- Bayesian range tracking (beyond-GTO exploitative engine) ---
        # These persist across streets within the SAME hand
        # _bayesian_villain_range is set by runner or created in _narrow_opponent_range
        # Reset only if this is a new hand (checked by runner)
        if not hasattr(self, '_bayesian_villain_range'):
            self._bayesian_villain_range = None
        self._bayesian_analysis = None
        self._bayesian_exploit = None
        self._bayesian_predictions = None

        self.potAdjustmentPreFlop = t.totalPotValue / t.bigBlind / 250 * float(
            p.selected_strategy['potAdjustmentPreFlop'])
        self.potAdjustmentPreFlop = min(self.potAdjustmentPreFlop,
                                        float(p.selected_strategy['maxPotAdjustmentPreFlop']))

        self.potAdjustment = t.totalPotValue / t.bigBlind / \
                             250 * float(p.selected_strategy['potAdjustment'])
        self.potAdjustment = min(self.potAdjustment, float(
            p.selected_strategy['maxPotAdjustment']))

        if t.gameStage == GameStages.PreFlop.value:
            t.power1 = int(p.selected_strategy['PreFlopCallPower'])
            t.minEquityCall = float(
                p.selected_strategy[
                    'PreFlopMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustmentPreFlop + self.preflop_adjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == GameStages.Flop.value:
            t.power1 = int(
                p.selected_strategy['FlopCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy[
                    'FlopMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustment - self.out_adjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == GameStages.Turn.value:
            t.power1 = int(
                float(p.selected_strategy['TurnCallPower'])) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy[
                    'TurnMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustment - self.out_adjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1
        elif t.gameStage == GameStages.River.value:
            t.power1 = int(
                p.selected_strategy['RiverCallPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityCall = float(
                p.selected_strategy['RiverMinCallEquity']) + self.secondRoundAdjustment - self.potAdjustment
            t.minCallAmountIfAboveLimit = t.bigBlind * 2
            t.potStretch = 1
            t.maxEquityCall = 1

        t.maxValue_call = float(
            p.selected_strategy['initialFunds']) * t.potStretch
        minimum_curve_value = 0
        minimum_curve_value2 = 0 if p.selected_strategy[
            'use_pot_multiples'] else t.minCallAmountIfAboveLimit
        d = Curvefitting(np.array([t.equity]), minimum_curve_value, minimum_curve_value2, t.maxValue_call,
                         t.minEquityCall,
                         t.maxEquityCall, t.max_X, t.power1)
        self.maxCallE = round(d.y[0], 2)

        if not np.isnan(t.first_raiser_utg) and not t.checkButton:
            opponent_raised_without_initiative = 1
            log.info(
                "Other player has no initiative and there is no check button. Activate increased required equity for betting if corresponding tickbox in strategy is checked.")
        else:
            opponent_raised_without_initiative = 0
            log.debug("Increase required equity for betting not acviated")

        opponent_raised_without_initiative_flop = 0.1 * p.selected_strategy[
            'opponent_raised_without_initiative_flop'] * opponent_raised_without_initiative
        opponent_raised_without_initiative_turn = 0.1 * p.selected_strategy[
            'opponent_raised_without_initiative_turn'] * opponent_raised_without_initiative
        opponent_raised_without_initiative_river = 0.1 * p.selected_strategy[
            'opponent_raised_without_initiative_river'] * opponent_raised_without_initiative

        if t.gameStage == GameStages.PreFlop.value:
            t.power2 = int(
                p.selected_strategy['PreFlopBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy[
                    'PreFlopMinBetEquity']) + self.secondRoundAdjustment - self.potAdjustment + self.preflop_adjustment
            t.maxEquityBet = float(p.selected_strategy['PreFlopMaxBetEquity'])
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == GameStages.Flop.value:
            t.power2 = int(
                p.selected_strategy['FlopBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy[
                    'FlopMinBetEquity']) + self.secondRoundAdjustment - self.out_adjustment + opponent_raised_without_initiative_flop
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == GameStages.Turn.value:
            t.power2 = int(
                p.selected_strategy['TurnBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy[
                    'TurnMinBetEquity']) + self.secondRoundAdjustment - self.out_adjustment + opponent_raised_without_initiative_turn
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2
        elif t.gameStage == GameStages.River.value:
            t.power2 = int(
                p.selected_strategy['RiverBetPower']) + secondRoundAdjustmentPowerIncrease
            t.minEquityBet = float(
                p.selected_strategy[
                    'RiverMinBetEquity']) + self.secondRoundAdjustment + opponent_raised_without_initiative_river
            t.maxEquityBet = 1
            t.minBetAmountIfAboveLimit = t.bigBlind * 2

        # adjustment for player profile
        if t.isHeadsUp and t.gameStage != GameStages.PreFlop.value:
            try:
                self.flop_probability_player = l.get_flop_frequency_of_player(
                    t.PlayerNames[0])
                log.info(
                    "Probability profile of : " + t.PlayerNames[0] + ": " + str(self.flop_probability_player))
            except:
                self.flop_probability_player = np.nan

            if self.flop_probability_player < 0.30:
                log.info("Defensive play due to probability profile")
                t.power1 += 2
                t.power2 += 2
                self.player_profile_adjustment = 2
            elif self.flop_probability_player > 0.60:
                log.info("Agressive play due to probability profile")
                t.power1 -= 2
                t.power2 -= 2
                self.player_profile_adjustment = -2
            else:
                self.player_profile_adjustment = 0
        t.maxValue_bet = float(p.selected_strategy['initialFunds2']) * t.potStretch
        d = Curvefitting(np.array([t.equity]), minimum_curve_value, t.minBetAmountIfAboveLimit, t.maxValue_bet,
                         t.minEquityBet, t.maxEquityBet, t.max_X, t.power2)
        self.maxBetE = round(d.y[0], 2)

        # min(self.maxCallE, self.maxCallEV)
        self.finalCallLimit = self.maxCallE
        self.finalBetLimit = self.maxBetE  # min(self.maxBetE, self.maxCallEV)

    def preflop_table_analyser(self, t, h, p):
        if t.gameStage == GameStages.PreFlop.value:
            m = MonteCarlo()
            crd1, crd2 = m.get_two_short_notation(t.mycards)
            crd1 = crd1.upper()
            crd2 = crd2.upper()

            # Always use GTO solver ranges + eval7 equity instead of
            # hardcoded preflop Excel sheet. This gives position-aware
            # open/3bet/defend ranges with range-based equity gating.
            log.info("Using GTO ranges + eval7 (preflop sheet bypassed)")

            # Jump directly to GTO range decision
            position = getattr(t, '_gto_position', 'UNKNOWN')
            has_raiser = getattr(t, 'first_raiser', False)
            call_amt = getattr(t, 'currentCallValue', 0) or 0
            has_check = getattr(t, 'checkButton', False)

            _utg_to_pos_map = {0: 'UTG', 1: 'MP', 2: 'CO', 3: 'BTN', 4: 'SB', 5: 'BB'}
            _raiser_utg = getattr(t, 'first_raiser_utg', float('nan'))
            import math as _m
            _raiser_pos = _utg_to_pos_map.get(int(_raiser_utg), 'BTN') if not _m.isnan(_raiser_utg) else ''
            _hero_stk = max(getattr(t, 'myFunds', 100), 1.0)

            gto_action = gto_preflop_decision(
                crd1, crd2, position, has_raiser, float(call_amt), has_check,
                hero_stack=_hero_stk, raiser_position=_raiser_pos)

            hand_str = _normalize_hand(crd1, crd2)
            log.info(f'GTO PREFLOP: {hand_str} pos={position} → {gto_action} '
                     f'(raiser={_raiser_pos}, call={call_amt}, equity={t.equity:.3f})')

            if gto_action == 'raise':
                # Use superb preflop sizing
                raiser_pos = _utg_to_pos_map.get(int(_raiser_utg), 'BTN') if not _m.isnan(_raiser_utg) else 'NONE'
                pf_action = '3bet' if has_raiser else 'open'
                
                # BB conversion for call_amt
                _bb = t.bigBlind if t.bigBlind > 0 else 1.0
                call_bb = float(call_amt) / _bb
                
                optimal_pf_bb = preflop_raise_size_bb(
                    action=pf_action,
                    position=position,
                    num_limpers=getattr(t, 'num_limpers', 0) if not has_raiser else 0,
                    prev_raise_bb=call_bb,
                    big_blind=t.bigBlind
                )
                
                # Map to decision types and set finalBetLimit (crucial for execution)
                self.optimal_bet_bb = optimal_pf_bb
                self.finalBetLimit = optimal_pf_bb * _bb
                
                if pf_action == '3bet':
                    # For 3-bets, use bet4 (pot/large) if sizing is substantial
                    self.decision = DecisionTypes.bet4 if optimal_pf_bb >= 15 else DecisionTypes.bet3
                else:
                    self.decision = DecisionTypes.bet3  # Standard 2.5-3x open
                
                log.info(f"GTO PREFLOP RAISE: {hand_str} → {self.decision} (sizing={optimal_pf_bb:.1f}BB, val={self.finalBetLimit:.1f})")
            elif gto_action == 'call':
                self.decision = DecisionTypes.call
                # Stack-relative call gating using eval7 equity
                _call_amt_g = float(call_amt) if call_amt else 0
                _call_to_stack_g = _call_amt_g / _hero_stk

                opp = self._get_opp()
                _gate_bonus = 0.0
                if opp:
                    ptype = opp.get('type', 'unknown')
                    if ptype == 'nit':
                        _gate_bonus = 0.05
                    elif ptype in ('maniac', 'fish_aggro'):
                        _gate_bonus = -0.05
                    elif ptype == 'fish_passive':
                        _gate_bonus = 0.03

                if _call_to_stack_g > 0.50 and t.equity < (0.45 + _gate_bonus):
                    log.info(f"GTO GATE: call/stack={_call_to_stack_g:.0%}, eq={t.equity:.3f} < {0.45 + _gate_bonus:.2f} → FOLD")
                    self.decision = DecisionTypes.fold
                elif _call_to_stack_g > 0.25 and t.equity < (0.35 + _gate_bonus):
                    log.info(f"GTO GATE: call/stack={_call_to_stack_g:.0%}, eq={t.equity:.3f} < {0.35 + _gate_bonus:.2f} → FOLD")
                    self.decision = DecisionTypes.fold
                elif _call_to_stack_g > 0.10 and t.equity < (0.25 + _gate_bonus):
                    log.info(f"GTO GATE: call/stack={_call_to_stack_g:.0%}, eq={t.equity:.3f} < {0.25 + _gate_bonus:.2f} → FOLD")
                    self.decision = DecisionTypes.fold
            elif gto_action == 'check':
                self.decision = DecisionTypes.check
            else:
                self.decision = DecisionTypes.fold

            # SAFETY: equity floors prevent misread cards from causing raises
            # PREMIUM EXEMPTION: Never fold premium hands due to safety floors
            PREMIUMS = {'AA', 'KK', 'QQ', 'JJ', 'AKS', 'AKO', 'AQS'}
            hand_norm = _normalize_hand(crd1, crd2)
            is_premium_hand = hand_norm in PREMIUMS

            if self.decision in (DecisionTypes.bet3, DecisionTypes.bet4):
                if t.equity < 0.22 and not is_premium_hand:
                    log.info(f'Preflop raise overridden to FOLD: equity {t.equity:.3f} < 0.22')
                    self.decision = DecisionTypes.fold
            elif self.decision == DecisionTypes.call:
                _ca = float(call_amt) if call_amt else 0
                pot = max(getattr(t, 'totalPotValue', 0) or 0, 1.5)
                if _ca > 0:
                    pot_odds = _ca / (pot + _ca)
                    if t.equity < pot_odds and t.equity < 0.28 and not is_premium_hand:
                        log.info(f'Preflop call overridden to FOLD: equity {t.equity:.3f} '
                                 f'< pot_odds {pot_odds:.3f} and < 0.28')
                        self.decision = DecisionTypes.fold

            t.currentBluff = 0
            return  # Done — skip old preflop sheet code below

            # ---- OLD PREFLOP SHEET CODE (bypassed) ----
            sheet_name = t.derive_preflop_sheet_name(
                t, h, t.first_raiser_utg, t.first_caller_utg, t.second_raiser_utg)

            log.info("Sheet name: " + sheet_name)
            excel_file = h.preflop_sheet
            info_sheet = excel_file['Info']
            sheet_version = info_sheet['Version'].iloc[0]
            log.info("Preflop Excelsheet Version: " + str(sheet_version))
            if sheet_name in excel_file:
                sheet = excel_file[sheet_name]
                log.debug("Sheetname found")
            elif sheet_name[:-2] in excel_file:
                log.warning("Sheetname " + sheet_name +
                            " not found, cutting last element: " + sheet_name[:-2])
                sheet = excel_file[sheet_name[:-2]]
            else:
                if sheet_name == '6':
                    # Sheet "6" (BB unraised) doesn't exist in the Excel.
                    # Skip directly to GTO range below instead of wrong backup.
                    log.info("Sheet 6 (BB unraised) missing, using GTO BB defense")
                    sheet = None
                else:
                    backup_sheet_name = '2R1'
                    sheet = excel_file[backup_sheet_name]
                    log.warning("Sheetname not found: " + sheet_name)
                    log.warning("Backup sheet in use: " + backup_sheet_name)
                    if t.entireScreenPIL is not None:
                        t.entireScreenPIL.save('sheet_not_found.png')
            if sheet is not None:
                sheet['Hand'] = sheet['Hand'].apply(lambda x: str(x).upper())

            handlist = set(sheet['Hand'].tolist()) if sheet is not None else set()
            self.preflop_bot_ranges = handlist

            found_card = ''

            if crd1 in handlist:
                found_card = crd1
            elif crd2 in handlist:
                found_card = crd2

            log.debug("Looking in preflop table for: " +
                      crd1 + ", " + crd2 + ", " + crd1[0:2])
            log.debug("Found in preflop table: " + found_card)

            if found_card != '':
                call_probability = sheet[sheet['Hand'] == found_card]['Call'].iloc[0]
                bet_probability = sheet[sheet['Hand'] == found_card]['Raise'].iloc[0]
                rnd = random.random()
                log.debug(f"Random number: {rnd}")
                log.debug(f"Call probability: {call_probability}")
                log.debug(f"Raise probability: {bet_probability}")

                if rnd < call_probability:
                    self.decision = DecisionTypes.call
                    log.info('Preflop calling activated from preflop table')

                    # Phase 4.1: Stack-relative call gating
                    _call_amt = getattr(t, 'currentCallValue', 0) or 0
                    _hero_stack = max(getattr(t, 'myFunds', 100), 1.0)
                    _call_to_stack = float(_call_amt) / _hero_stack

                    # Opponent-adaptive preflop gating: adjust thresholds
                    # based on who raised (nit raise = very strong, maniac = wide)
                    opp = self._get_opp()
                    _gate_bonus = 0.0
                    if opp:
                        ptype = opp.get('type', 'unknown')
                        if ptype == 'nit':
                            # Nit raised → they have a monster → tighten up
                            _gate_bonus = 0.05
                            log.info(f"OPP_ADAPT: preflop tightening vs NIT raiser")
                        elif ptype in ('maniac', 'fish_aggro'):
                            # Maniac raised → could be anything → loosen up
                            _gate_bonus = -0.05
                            log.info(f"OPP_ADAPT: preflop loosening vs {ptype} raiser")
                        elif ptype == 'fish_passive':
                            # Passive fish raised → they actually have something
                            _gate_bonus = 0.03

                    if _call_to_stack > 0.50 and t.equity < (0.45 + _gate_bonus):
                        log.info(f"PREFLOP GATE: call/stack={_call_to_stack:.0%} > 50%, "
                                 f"equity={t.equity:.3f} < {0.45 + _gate_bonus:.2f} → FOLD")
                        self.decision = DecisionTypes.fold
                    elif _call_to_stack > 0.25 and t.equity < (0.35 + _gate_bonus):
                        log.info(f"PREFLOP GATE: call/stack={_call_to_stack:.0%} > 25%, "
                                 f"equity={t.equity:.3f} < {0.35 + _gate_bonus:.2f} → FOLD")
                        self.decision = DecisionTypes.fold
                    elif _call_to_stack > 0.10 and t.equity < (0.25 + _gate_bonus):
                        log.info(f"PREFLOP GATE: call/stack={_call_to_stack:.0%} > 10%, "
                                 f"equity={t.equity:.3f} < {0.25 + _gate_bonus:.2f} → FOLD")
                        self.decision = DecisionTypes.fold

                elif call_probability <= rnd <= bet_probability + call_probability:
                    if sheet_name in ['1', '2', '3', '4']:
                        self.decision = DecisionTypes.bet3
                        log.info('Preflop betting 3 activated from preflop table')
                    else:
                        self.decision = DecisionTypes.bet4
                        log.info('Preflop betting 4 activated from preflop table')
                        # 1, 2, 3, 4 = half pot
                        # 5 = pot and the
                        # rest POT
                else:
                    self.decision = DecisionTypes.fold
                    log.info('Preflop folding from preflop table')
            else:
                # Hand not in preflop sheet — use GTO solver ranges instead.
                position = getattr(t, '_gto_position', 'UNKNOWN')
                has_raiser = getattr(t, 'first_raiser', False)
                call_amt = getattr(t, 'currentCallValue', 0) or 0
                has_check = getattr(t, 'checkButton', False)

                # Derive raiser position from first_raiser_utg
                _utg_to_pos_map = {0: 'UTG', 1: 'MP', 2: 'CO', 3: 'BTN', 4: 'SB', 5: 'BB'}
                _raiser_utg = getattr(t, 'first_raiser_utg', float('nan'))
                import math as _m
                _raiser_pos = _utg_to_pos_map.get(int(_raiser_utg), 'BTN') if not _m.isnan(_raiser_utg) else ''

                _hero_stk = max(getattr(t, 'myFunds', 100), 1.0)
                gto_action = gto_preflop_decision(
                    crd1, crd2, position, has_raiser, float(call_amt), has_check,
                    hero_stack=_hero_stk, raiser_position=_raiser_pos)

                hand_str = _normalize_hand(crd1, crd2)
                log.info(f'Hand {crd1}/{crd2} ({hand_str}) not in sheet, '
                         f'GTO range says: {gto_action} (pos={position}, '
                         f'raiser={has_raiser}, call={call_amt})')

            # PREMIUM EXEMPTION: Never fold premium hands due to safety floors or stack gates
            PREMIUMS = {'AA', 'KK', 'QQ', 'JJ', 'TT', 'AKS', 'AKO', 'AQS', 'AJS', 'KQS'}
            hand_norm = _normalize_hand(crd1, crd2)
            is_premium_hand = hand_norm in PREMIUMS

            if gto_action == 'raise':
                # Use bet3 for opens/3-bets, bet4 for 4-bets
                if float(call_amt) > 4:
                    self.decision = DecisionTypes.bet4
                else:
                    self.decision = DecisionTypes.bet3
            elif gto_action == 'call':
                self.decision = DecisionTypes.call
                # Phase 4.1/4.3: Stack-relative call gating for GTO fallback
                _call_amt_g = float(call_amt) if call_amt else 0
                _hero_stack_g = max(getattr(t, 'myFunds', 100), 1.0)
                _call_to_stack_g = _call_amt_g / _hero_stack_g
                
                # GTO GATES: Prevent calling off large stack portions with weak equity
                # EXEMPT PREMIUMS: JJ, TT, AK, etc. should always call/raise regardless of gate
                if not is_premium_hand:
                    if _call_to_stack_g > 0.50 and t.equity < 0.45:
                        log.info(f"GTO GATE: call/stack={_call_to_stack_g:.0%}, eq={t.equity:.3f} < 0.45 → FOLD")
                        self.decision = DecisionTypes.fold
                    elif _call_to_stack_g > 0.25 and t.equity < 0.35:
                        log.info(f"GTO GATE: call/stack={_call_to_stack_g:.0%}, eq={t.equity:.3f} < 0.35 → FOLD")
                        self.decision = DecisionTypes.fold
                    elif _call_to_stack_g > 0.10 and t.equity < 0.25:
                        log.info(f"GTO GATE: call/stack={_call_to_stack_g:.0%}, eq={t.equity:.3f} < 0.25 → FOLD")
                        self.decision = DecisionTypes.fold
            elif gto_action == 'check':
                self.decision = DecisionTypes.check
            else:
                self.decision = DecisionTypes.fold

        # --- BULLETPROOF EV SAFETY (eval7-aware) ---
        # Instead of hardcoded floors, calculate if the action is actually profitable.
        if self.decision == DecisionTypes.call:
            call_amt = float(getattr(t, 'currentCallValue', 0) or 0)
            pot = max(float(getattr(t, 'totalPotValue', 0) or 0), 1.5)
            
            if call_amt > 0:
                pot_odds = call_amt / (pot + call_amt)
                # Requirement: Equity must justify the call price
                # We allow 15% 'slack' for implied odds/playability
                min_eq_req = pot_odds * 0.85
                
                # Minimum absolute safety: never call with < 15% equity unless checking
                if t.equity < min_eq_req and t.equity < 0.25 and not is_premium_hand:
                    log.info(f"EV SAFETY: Call {call_amt} into {pot} (odds {pot_odds:.1%}) "
                             f"needs eq > {min_eq_req:.1%}. Hero has {t.equity:.1%}. FOLDING.")
                    self.decision = DecisionTypes.fold
        
        elif self.decision in (DecisionTypes.bet3, DecisionTypes.bet4):
            # For raises, we must have at least 20% absolute equity OR be a premium
            if t.equity < 0.20 and not is_premium_hand:
                log.info(f"EV SAFETY: Raise overridden to FOLD. Equity {t.equity:.1%} is too low for non-premium.")
                self.decision = DecisionTypes.fold

            t.currentBluff = 0

    def _get_opp(self):
        """Get opponent profile dict (safe accessor)."""
        opp = getattr(self, '_opp_profile', None)
        if opp and opp.get('hands', 0) >= 10:
            return opp
        return None

    def _get_icm_pressure(self, t):
        """Calculate ICM pressure for tournament decisions.

        Returns a positive equity offset (need MORE equity to call/commit).
        0.0 for cash games, 0.02-0.10 for tournaments.
        """
        # Only applies to tournaments (detected by table name)
        table_name = getattr(t, '_table_name', '')
        if not table_name:
            return 0.0

        is_tournament = any(kw in table_name for kw in ('Spin', 'Gold', 'Tournament', 'SNG', 'MTT'))
        if not is_tournament:
            return 0.0

        hero_stack = max(getattr(t, 'myFunds', 100), 1.0)
        pot = max(getattr(t, 'totalPotValue', 0), 0.01)
        call_amount = max(getattr(t, 'currentCallValue', 0) or 0, 0)

        # Stack commitment ratio: how much of our stack is at risk
        commitment = call_amount / hero_stack if hero_stack > 0 else 0

        # Base ICM pressure: always need slightly more equity in tournaments
        pressure = 0.02

        # High commitment = tournament life at stake
        if commitment > 0.50:
            # All-in or near all-in: significant ICM penalty
            pressure = 0.08
        elif commitment > 0.30:
            # Large pot: moderate ICM penalty
            pressure = 0.05
        elif commitment > 0.15:
            # Medium pot: small ICM penalty
            pressure = 0.03

        # Big stack advantage: reduce pressure (we can afford to lose)
        # Typical Spin & Gold starts with ~25 BB
        if hero_stack > 40:  # Deep stacked (40+ BB)
            pressure *= 0.5
        elif hero_stack < 10:  # Short stacked (< 10 BB)
            # Short stack: ICM pressure is LOWER because we need to gamble
            # Can't blind out — must take spots
            pressure *= 0.3

        return pressure

    def calling(self, t, p, h):
        # Honour alwaysCallEquity / low-stack overrides set in make_decision()
        if self.finalCallLimit > 0 and t.minCall <= self.finalCallLimit:
            self.decision = DecisionTypes.call
            log.info(f"Always-call override active (call {t.minCall} <= limit {self.finalCallLimit:.1f})")
            return

        pot = max(t.totalPotValue, 0.01)
        call = max(t.minCall, 0)

        if call <= 0:
            self.decision = DecisionTypes.call
            return

        pot_odds = call / (pot + call)

        # Blocker adjustment: holding blockers to opponent's strong range
        # improves our effective equity (they're less likely to have the nuts)
        blocker_adj = 0.0
        if not hasattr(self, 'blockers_info') or not self.blockers_info:
            self._analyze_blockers(t)
        if self.blockers_info.get('blocker_score', 0) > 0:
            blocker_adj = self.blockers_info['blocker_score'] * 0.04  # Up to ~4% equity bonus
            log.debug(f"Blocker adjustment: +{blocker_adj:.3f} (score={self.blockers_info['blocker_score']:.2f})")

        # Implied odds bonus for draws (using self.outs from __init__)
        implied_adj = 0.0
        if self.outs >= 8:      # OESD or flush draw
            implied_adj = 0.08
        elif self.outs >= 4:    # Gutshot
            implied_adj = 0.04

        # --- Opponent-adaptive adjustment ---
        opp = self._get_opp()
        opp_call_adj = 0.0
        if opp:
            ptype = opp.get('type', 'unknown')
            if ptype == 'nit':
                # Nits only bet/raise with strong hands — need MORE equity to call
                opp_call_adj = 0.05
                log.info(f"OPP_ADAPT: vs NIT, +5% required equity")
            elif ptype == 'tag':
                # TAGs are balanced — slight tightening
                opp_call_adj = 0.02
            elif ptype == 'fish_passive':
                # Calling stations bet weak — call DOWN lighter
                opp_call_adj = -0.05
                log.info(f"OPP_ADAPT: vs FISH_PASSIVE, -5% required equity (they bet weak)")
            elif ptype == 'maniac':
                # Maniacs over-bluff — call DOWN much lighter
                opp_call_adj = -0.08
                log.info(f"OPP_ADAPT: vs MANIAC, -8% required equity (they over-bluff)")
            elif ptype == 'lag':
                # LAGs bluff more than average
                opp_call_adj = -0.04
            elif ptype == 'fish_aggro':
                opp_call_adj = -0.03

        # --- Range-based adjustment ---
        range_adj = 0.0
        range_est = getattr(self, 'opponent_range_estimate', {})
        if range_est:
            bluff_prob = range_est.get('bluff_probability', 0.3)
            narrowness = range_est.get('range_narrowness', 0.5)
            # High bluff probability → reduce required equity (call lighter)
            # Low bluff probability → increase required equity (fold more)
            range_adj = (bluff_prob - 0.25) * 0.15  # ±~5% equity swing
            # Very narrow range (they're polarized) → amplify the adjustment
            if narrowness > 0.7:
                range_adj *= 1.3
            log.debug(f"Range adj: bluff={bluff_prob:.2f} narrow={narrowness:.2f} adj={range_adj:+.3f}")

        # --- Live spot-type adjustment ---
        spot_adj = 0.0
        _spot = getattr(self, '_spot_adj', {})
        if _spot:
            spot_adj = _spot.get('call_equity_offset', 0.0)
            if spot_adj != 0.0:
                log.debug(f"Spot adj: call_equity_offset={spot_adj:+.3f}")

        # --- Bet sizing exploitation ---
        # Small bets = weaker range = call lighter; large bets = stronger = need more equity
        sizing_adj = 0.0
        if call > 0 and pot > 0.5:
            bet_to_pot = call / pot
            if bet_to_pot <= 0.33:
                # Small bet: opponent likely has weak/marginal hand or blocking
                sizing_adj = -0.04  # Call 4% lighter
                log.debug(f"Sizing: small bet ({bet_to_pot:.2f}x pot) → call lighter")
            elif bet_to_pot <= 0.55:
                # Standard bet: neutral
                sizing_adj = 0.0
            elif bet_to_pot <= 0.80:
                # Large bet: opponent has strong hand or good semi-bluff
                sizing_adj = 0.02  # Need 2% more equity
                log.debug(f"Sizing: large bet ({bet_to_pot:.2f}x pot) → tighter")
            elif bet_to_pot <= 1.2:
                # Pot-sized: strong or very polarized
                sizing_adj = 0.03
                log.debug(f"Sizing: pot bet ({bet_to_pot:.2f}x pot) → need more equity")
            else:
                # Overbet: very polarized (nuts or bluff)
                # Against an overbet, we should call with medium-strength hands
                # because opponent is polarized — they either crush us or are bluffing
                sizing_adj = -0.02  # Slightly lighter (their bluff frequency is higher)
                log.debug(f"Sizing: overbet ({bet_to_pot:.2f}x pot) → polarized, call slightly lighter")

            # Combine with opponent type: nits don't bluff even with overbets
            opp = self._get_opp()
            if opp:
                ptype = opp.get('type', 'unknown')
                if ptype == 'nit' and bet_to_pot > 0.75:
                    sizing_adj = 0.05  # Nit big bet = always strong
                    log.debug(f"Sizing: nit overbet → they always have it")
                elif ptype in ('maniac', 'fish_aggro') and bet_to_pot > 0.75:
                    sizing_adj = -0.06  # Maniac big bet = often bluff
                    log.debug(f"Sizing: maniac overbet → likely bluff")

        # --- ICM pressure for tournaments ---
        icm_adj = self._get_icm_pressure(t)
        if icm_adj > 0:
            log.info(f"ICM PRESSURE: +{icm_adj:.3f} equity required (tournament)")

        # --- Bayesian exploit adjustment (beyond-GTO) ---
        bayesian_adj = 0.0
        _exploit = getattr(self, '_bayesian_exploit', None)
        _banalysis = getattr(self, '_bayesian_analysis', None)
        if _exploit and _banalysis and _exploit.get('confidence', 0) >= 0.55:
            _exp_action = _exploit.get('action', '')
            _exp_conf = _exploit.get('confidence', 0)
            _is_capped = _banalysis.get('is_capped', False)
            _bp = _banalysis.get('bluff_pct', 0)

            if _exp_action == 'call' and _bp > 0.25:
                # Bayesian says call — villain has too many bluffs
                bayesian_adj = -(_bp - 0.25) * 0.20  # up to -7% equity needed
                bayesian_adj = max(bayesian_adj, -0.08)
                log.info(f"BAYESIAN CALL BOOST: bluffs={_bp:.0%}, adj={bayesian_adj:+.3f} "
                         f"(conf={_exp_conf:.0%})")
            elif _exp_action == 'fold' and _banalysis.get('value_pct', 0) > 0.60:
                # Bayesian says fold — villain range is narrow and strong
                bayesian_adj = 0.06
                log.info(f"BAYESIAN FOLD PRESSURE: value={_banalysis['value_pct']:.0%}, "
                         f"adj=+{bayesian_adj:.3f} (conf={_exp_conf:.0%})")

        # Fix 5: Multiway Pot Tightening (Tighten ~6% per extra opponent)
        multiway_adj = 0.0
        other_players = getattr(t, 'other_active_players', 1)
        if other_players >= 2:
            multiway_adj = (other_players - 1) * 0.06
            log.info(f"MULTIWAY TIGHTENING: +{multiway_adj:.1%} (opponents={other_players})")

        required_equity = max(pot_odds - implied_adj - blocker_adj + opp_call_adj - range_adj + spot_adj + sizing_adj + icm_adj + bayesian_adj + multiway_adj, 0.05)

        # --- Hand strength gate: discount equity when facing bets with weak hands ---
        # Monte Carlo equity is vs RANDOM hands. When opponent bets, their range is
        # much stronger than random. Weak hands overestimate their equity significantly.
        if t.gameStage != 'PreFlop' and call > 0:
            hand_info = self._classify_hand(t)
            if hand_info:
                log.info(f"CALL HAND: {hand_info['name']} ({hand_info['strength']})")

                if hand_info['strength'] == 'weak':
                    # High card, low pair, board pair only — heavily discount
                    # AJ on Q376 = ace high → equity vs random ~35% but vs betting range ~15%
                    range_discount = 0.12
                    if t.allInCallButton:
                        range_discount = 0.18  # All-in = very strong range
                    required_equity += range_discount
                    log.info(f"WEAK HAND DISCOUNT: {hand_info['name']} → +{range_discount:.0%} req equity "
                             f"(new req={required_equity:.3f})")

                elif hand_info['strength'] == 'marginal':
                    # Second pair, top pair weak kicker — moderate discount
                    range_discount = 0.06
                    if t.allInCallButton:
                        range_discount = 0.10
                    required_equity += range_discount
                    log.info(f"MARGINAL HAND DISCOUNT: {hand_info['name']} → +{range_discount:.0%} req equity")

                elif hand_info['strength'] == 'medium':
                    # Top pair good kicker, two pair medium — small discount
                    if t.allInCallButton:
                        required_equity += 0.05
                        log.info(f"MEDIUM HAND ALL-IN CAUTION: {hand_info['name']} → +5% req equity")

        # Board scare is handled by board-aware range filtering in range_equity.py:
        # eval7 evaluates each villain combo on the actual board and removes
        # hands too weak to bet, giving accurate equity without bandaid penalties.

        # SPR commitment: when SPR < 3 and we have decent equity, we're pot-committed
        if self.spr < 3.0 and t.equity >= 0.35:
            self.decision = DecisionTypes.call
            log.info(f"SPR COMMIT CALL: eq={t.equity:.3f} spr={self.spr:.1f} "
                     f"(pot_odds={pot_odds:.3f})")
        elif self.spr < 1.5 and t.equity >= 0.25:
            # Very low SPR — almost always call
            self.decision = DecisionTypes.call
            log.info(f"SPR DEEP COMMIT: eq={t.equity:.3f} spr={self.spr:.1f}")
        elif t.equity >= required_equity:
            self.decision = DecisionTypes.call
            _opp_tag = f", vs {opp['type']}" if opp else ''
            log.info(f"POT ODDS CALL: eq={t.equity:.3f} >= req={required_equity:.3f} "
                     f"(pot_odds={pot_odds:.3f}, outs={self.outs}, sizing={sizing_adj:+.3f}{_opp_tag})")
        else:
            self.decision = DecisionTypes.fold
            _opp_tag = f", vs {opp['type']}" if opp else ''
            log.info(f"POT ODDS FOLD: eq={t.equity:.3f} < req={required_equity:.3f} "
                     f"(pot_odds={pot_odds:.3f}, sizing={sizing_adj:+.3f}{_opp_tag})")

        # All-in guard — fold low-equity all-in situations
        if t.allInCallButton:
            # Pot Odds Guard: equity < call / (pot + call)
            pot_odds_limit = call / (pot + call) if (pot + call) > 0 else 0
            # Minimum floor 0.18 (never call with pure garbage)
            all_in_threshold = max(0.18, pot_odds_limit)
            if t.equity < all_in_threshold:
                self.decision = DecisionTypes.fold
                log.info(f"ALL-IN GUARD: equity {t.equity:.3f} < threshold {all_in_threshold:.3f} "
                         f"(pot_odds={pot_odds_limit:.3f}), folding")

    def betting(self, t, p, h):
        # preflop
        if t.gameStage == GameStages.PreFlop.value:
            if self.finalBetLimit > float(t.minBet):
                log.info("Bet1 condition met")
                self.decision = DecisionTypes.bet1

            if (self.finalBetLimit >= float(t.totalPotValue) / 2) \
                    and (p.selected_strategy['increased_preflop_betting'] == 2):
                log.info("Bet3 condition met")
                self.decision = DecisionTypes.bet3

            # if (self.finalBetLimit > float(t.minBet)) and \
            #         (t.first_raiser_utg >= 0 or t.first_caller_utg >= 0):
            #     log.info("Bet4 condition met")
            #     self.decision = DecisionTypes.bet4

        # flop turn river
        if t.gameStage != GameStages.PreFlop.value:
            stage = t.gameStage.lower()
            wetness = self._board_wetness(t.cardsOnTable)
            pot_bb = float(t.totalPotValue) / t.bigBlind
            stack_bb = self.hero_stack_bb

            # --- Hand strength classification ---
            hand_info = self._classify_hand(t)
            if hand_info:
                log.info(f"HAND: {hand_info['name']} ({hand_info['strength']}) rank={hand_info['rank']}")

            # --- "Superb" Bet Sizing (Geometric/Polarized) ---
            is_ip = not t.other_player_has_initiative # Position proxy
            is_value = hand_info and hand_info['strength'] in ('monster', 'very_strong', 'strong', 'medium')

            # Calculate optimal BB size using the range_equity model
            self.optimal_bet_bb = compute_bet_size_bb(
                pot_bb=pot_bb,
                stack_bb=stack_bb,
                street=stage,
                board_wetness=wetness,
                spr=self.spr,
                is_ip=is_ip,
                hand_strength=hand_info['strength'] if hand_info else 'weak',
                is_value=is_value
            )
            # Update finalBetLimit to reflect this calculation
            self.finalBetLimit = self.optimal_bet_bb * t.bigBlind
            log.info(f"SUPERB SIZING: optimal={self.optimal_bet_bb:.1f} BB (pot={pot_bb:.1f} spr={self.spr:.1f})")

            # --- LOW SPR POSTFLOP SHOVE (pot-committed) ---
            # With SPR < 2, we're pot-committed. Any bet should be a shove.
            # Don't min-bet into a pot that's bigger than our stack.
            if self.spr < 2.0 and self.hero_stack_bb > 0:
                # With any pair, draw, or better → shove
                should_shove = False
                if hand_info and hand_info['strength'] not in ('weak',):
                    should_shove = True
                elif t.equity >= 0.25:
                    should_shove = True

                if should_shove:
                    if t.checkButton:
                        # We can check — shove as a bet
                        self.decision = DecisionTypes.bet4
                        self.push_fold_shove = True
                        log.info(f"LOW SPR SHOVE: spr={self.spr:.1f} stack={self.hero_stack_bb:.1f}BB "
                                 f"hand={hand_info['name'] if hand_info else '?'} eq={t.equity:.3f} → ALL-IN")
                        return
                    else:
                        # Facing a bet — raise all-in
                        self.decision = DecisionTypes.bet4
                        self.push_fold_shove = True
                        log.info(f"LOW SPR SHOVE vs BET: spr={self.spr:.1f} stack={self.hero_stack_bb:.1f}BB "
                                 f"hand={hand_info['name'] if hand_info else '?'} eq={t.equity:.3f} → ALL-IN")
                        return
                else:
                    log.info(f"LOW SPR CHECK/FOLD: spr={self.spr:.1f} "
                             f"hand={hand_info['name'] if hand_info else '?'} eq={t.equity:.3f} — too weak to commit")

            # --- STRONG HAND VALUE BETTING (never check down flushes/sets!) ---
            if hand_info and hand_info['strength'] in ('monster', 'very_strong'):
                if t.checkButton:
                    # Use geometric for monster strength to polarize
                    self.decision = DecisionTypes.bet3 if self.optimal_bet_bb < pot_bb * 0.8 else DecisionTypes.bet4
                    log.info(f"HAND VALUE BET: {hand_info['name']} → {self.decision} (sizing={self.optimal_bet_bb:.1f}BB)")
                    return
                else:
                    # Facing a bet with monster — raise for value
                    if hand_info['rank'] >= 5 or self.spr < 3:  # Flush or better or low SPR
                        self.decision = DecisionTypes.bet4
                        self.push_fold_shove = (self.optimal_bet_bb >= stack_bb * 0.7)
                        log.info(f"HAND VALUE RAISE: {hand_info['name']} → {self.decision} for value")
                        return

            if hand_info and hand_info['strength'] == 'strong':
                if t.checkButton:
                    # Strong hands use the calculated optimal size
                    self.decision = DecisionTypes.bet3 if self.optimal_bet_bb >= pot_bb * 0.6 else DecisionTypes.bet2
                    log.info(f"HAND VALUE BET: {hand_info['name']} → {self.decision} (sizing={self.optimal_bet_bb:.1f}BB)")
                    return

            # --- Medium hand value betting (top pair good kicker, two pair w/ board) ---
            if hand_info and hand_info['strength'] == 'medium':
                if t.checkButton:
                    # Equity floor: don't bet medium hands with very low equity
                    # (e.g. JJ on AQ43A — board paired higher, anyone with Ax has trips)
                    if t.equity < 0.30:
                        log.info(f"MEDIUM CHECK: {hand_info['name']} eq={t.equity:.3f} "
                                 f"(below 30% floor, checking)")
                        return
                    # Deep-stacked pot control: check some medium hands
                    if t.equity < 0.55 and self.spr > 6.0 and random.random() < 0.50:
                        log.info(f"POT CONTROL: {hand_info['name']} eq={t.equity:.3f} "
                                 f"spr={self.spr:.1f} (medium hand, checking)")
                        return
                    else:
                        self.decision = DecisionTypes.bet2
                        log.info(f"MEDIUM VALUE BET: {hand_info['name']} eq={t.equity:.3f} "
                                 f"spr={self.spr:.1f}")
                        return

            # --- Marginal hand thin value vs weak opponents ---
            if hand_info and hand_info['strength'] == 'marginal':
                if t.checkButton and t.equity >= 0.42:
                    opp = self._get_opp()
                    ptype = opp.get('type', 'unknown') if opp else 'unknown'
                    if ptype in ('fish_passive', 'fish_aggro', 'maniac', 'unknown'):
                        self.decision = DecisionTypes.bet2
                        log.info(f"THIN VALUE BET: {hand_info['name']} eq={t.equity:.3f} "
                                 f"vs {ptype}")
                        return

            # --- Bayesian exploit: bet when villain range is capped/weak ---
            _bexploit = getattr(self, '_bayesian_exploit', None)
            if _bexploit and _bexploit.get('confidence', 0) >= 0.55:
                _baction = _bexploit.get('action', '')
                if _baction == 'bet' and t.checkButton:
                    _bsizing = _bexploit.get('sizing_pct', 0.5)
                    if _bsizing >= 0.75:
                        self.decision = DecisionTypes.bet4
                    elif _bsizing >= 0.50:
                        self.decision = DecisionTypes.bet3
                    else:
                        self.decision = DecisionTypes.bet2
                    log.info(f"BAYESIAN BET: {_bexploit['reasoning']} "
                             f"(sizing={_bsizing:.0%}, conf={_bexploit['confidence']:.0%})")
                    return

            # --- Pot control: medium hands check back when deep-stacked ---
            # Equity 40-60% and SPR > 6 = marginal hand, keep pot small
            if t.checkButton and 0.40 <= t.equity < 0.60 and self.spr > 6.0:
                # Check back to control pot (don't build a big pot with marginal hands)
                # Exception: still c-bet sometimes for deception
                # But NOT if Bayesian says villain is capped (already handled above)
                if random.random() > 0.30:  # 70% check back, 30% still bet
                    log.info(f"POT CONTROL CHECK: eq={t.equity:.3f} spr={self.spr:.1f} "
                             f"(marginal hand, deep stacked)")
                    return  # Skip betting logic — keep pot small

            # --- SPR-aware value betting: bet bigger when committed ---
            if t.equity >= 0.70 and self.spr < 3.0:
                # Strong hand + low SPR = go for stacks
                if t.checkButton:
                    self.decision = DecisionTypes.bet4  # Pot-size to get it in
                    log.info(f"SPR VALUE JAM: eq={t.equity:.3f} spr={self.spr:.1f} (going for stacks)")
                    return

            # --- Strong value bet: high equity → always bet big ---
            # Opponent-adaptive: bet thinner for value vs fish who call with worse
            value_threshold = 0.70
            # Fix 5: Multiway Tightening (~5% higher threshold per extra opponent)
            if other_players >= 2:
                value_threshold += (other_players - 1) * 0.05
                log.info(f"MULTIWAY VALUE TIGHTENING: threshold={value_threshold:.2f} (opponents={other_players})")
            opp = self._get_opp()
            if opp:
                ptype = opp.get('type', 'unknown')
                if ptype in ('fish_passive', 'fish_aggro'):
                    value_threshold = 0.58  # Bet thinner vs fish — they call with much worse
                    log.info(f"OPP_ADAPT: value threshold 58% (vs {ptype})")
                elif ptype == 'maniac':
                    value_threshold = 0.55  # Maniacs will call or raise with worse
                    log.info(f"OPP_ADAPT: value threshold 55% (vs maniac)")
                elif ptype == 'nit':
                    value_threshold = 0.80  # Nits only call with good hands — need more equity
                    log.info(f"OPP_ADAPT: value threshold 80% (vs nit)")

            if t.equity >= value_threshold and t.checkButton:
                # --- GEOMETRIC BET SIZING (Optimization) ---
                # Calculate the optimal bet size to get stacks in by the river
                streets_left = 0
                if t.gameStage == GameStages.Flop.value: streets_left = 3
                elif t.gameStage == GameStages.Turn.value: streets_left = 2
                elif t.gameStage == GameStages.River.value: streets_left = 1
                
                geo_size = self._geometric_bet_size(pot_bb, self.hero_stack_bb, streets_left)
                
                # Map geometric size to closest button
                # bet2=min/small, bet3=half, bet4=pot
                half_pot = pot_bb * 0.5
                pot_size = pot_bb * 1.0
                
                if geo_size >= pot_size * 0.85:
                    self.decision = DecisionTypes.bet4  # Pot
                elif geo_size >= half_pot * 0.85:
                    self.decision = DecisionTypes.bet3  # Half/Two-Thirds
                else:
                    self.decision = DecisionTypes.bet2  # Small
                
                log.info(f"GEOMETRIC VALUE: eq={t.equity:.3f} streets={streets_left} "
                         f"geo_size={geo_size:.1f}BB (mapped to {self.decision})")
                return

            # C-bet logic when we can check (first action on street)
            if h.round_number == 0 and t.checkButton:
                cbet_freq = 0.70 - (wetness * 0.40) + _get_adj().get('cbet_freq_offset', 0.0)

                # --- Opponent-adaptive c-bet frequency ---
                opp = self._get_opp()
                if opp:
                    fold_to_cbet = opp.get('fold_to_cbet', 0.45)
                    ptype = opp.get('type', 'unknown')
                    if fold_to_cbet > 0.55:
                        # They fold to c-bets a lot → c-bet MORE (print money)
                        cbet_freq = min(cbet_freq + 0.15, 0.90)
                        log.info(f"OPP_ADAPT: c-bet freq UP (fold_to_cbet={fold_to_cbet:.0%})")
                    elif fold_to_cbet < 0.30:
                        # They rarely fold → only c-bet for value
                        cbet_freq = max(cbet_freq - 0.20, 0.20)
                        log.info(f"OPP_ADAPT: c-bet freq DOWN (fold_to_cbet={fold_to_cbet:.0%})")
                    elif ptype == 'fish_passive':
                        # Calling stations (no fold_to_cbet data yet): c-bet for thin value
                        cbet_freq = min(cbet_freq + 0.10, 0.85)
                        log.info(f"OPP_ADAPT: c-bet freq UP (fish_passive default)")

                # --- Live spot-type c-bet adjustment ---
                _spot = getattr(self, '_spot_adj', {})
                if _spot:
                    cbet_freq += _spot.get('cbet_freq_offset', 0.0)
                    cbet_freq = max(0.15, min(0.90, cbet_freq))

                if t.equity >= 0.55:
                    self.decision = DecisionTypes.bet3
                    log.info(f"C-BET VALUE: eq={t.equity:.3f} wet={wetness:.2f} "
                             f"(strong hand, first action)")
                    return
                elif t.equity >= 0.30 and random.random() < cbet_freq:
                    self.decision = DecisionTypes.bet3
                    log.info(f"C-BET: eq={t.equity:.3f} wet={wetness:.2f} freq={cbet_freq:.2f}")
                    return  # Don't run rest of betting logic

            # --- Turn barrel: continue aggression from flop ---
            if t.gameStage == GameStages.Turn.value and t.checkButton:
                # Fix 6: Turn Probe Bet (when flop was checked around)
                no_initiative = not t.other_player_has_initiative and not getattr(self, '_we_bet_prev_street', False)
                if no_initiative and t.equity >= 0.45:
                    probe_freq = 0.60
                    # Probe more on dry boards, less on wet
                    if wetness > 0.6: probe_freq -= 0.15
                    elif wetness < 0.3: probe_freq += 0.10
                    
                    if random.random() < probe_freq:
                        self.decision = DecisionTypes.bet2
                        log.info(f"PROBE BET: eq={t.equity:.3f} wet={wetness:.2f} freq={probe_freq:.2f}")
                        return

                we_bet_prev = getattr(self, '_we_bet_prev_street', False)
                prev_equity = getattr(self, '_prev_street_equity', None)

                if we_bet_prev and prev_equity is not None:
                    equity_change = t.equity - prev_equity

                    # Equity improved: keep barreling (hit turn card, scare card)
                    if equity_change > 0.05 and t.equity >= 0.45:
                        self.decision = DecisionTypes.bet3
                        log.info(f"TURN BARREL: equity improved {prev_equity:.3f}→{t.equity:.3f} "
                                f"(+{equity_change:.3f}), betting")

                    # Equity stable and strong: value barrel
                    elif t.equity >= 0.60:
                        self.decision = DecisionTypes.bet3
                        log.info(f"TURN VALUE BARREL: equity={t.equity:.3f}, strong hand, betting")

                    # Equity dropped: consider giving up
                    elif equity_change < -0.08 and t.equity < 0.40:
                        log.info(f"TURN GIVE UP: equity dropped {prev_equity:.3f}→{t.equity:.3f} "
                                f"({equity_change:+.3f}), checking")
                        # Don't override — let it check

                    # Medium equity with draws: semi-barrel
                    elif self.outs >= 8 and t.equity >= 0.30:
                        self.decision = DecisionTypes.bet3
                        log.info(f"TURN SEMI-BARREL: {self.outs} outs, equity={t.equity:.3f}")

            # --- River value: bet when we were barreling and still strong ---
            if t.gameStage == GameStages.River.value and t.checkButton:
                we_bet_prev = getattr(self, '_we_bet_prev_street', False)

                if we_bet_prev and t.equity >= 0.65:
                    self.decision = DecisionTypes.bet3
                    log.info(f"RIVER VALUE: was betting, equity={t.equity:.3f}, value betting")
                elif we_bet_prev and t.equity >= 0.45:
                    # Medium hand after barreling: check back for showdown value
                    log.info(f"RIVER SHOWDOWN: was betting, equity={t.equity:.3f}, checking for showdown")

            # multiple decision
            if p.selected_strategy['use_pot_multiples']:
                if self.finalBetLimit > t.minBet and \
                        (not t.checkButton or not t.other_player_has_initiative or
                         p.selected_strategy[stage + '_betting_condidion_1'] == 0):
                    self.decision = DecisionTypes.bet3
                    log.info("Bet3 activated (based on pot multiple decision)")

            # absolute value decision
            else:
                if not (h.round_number > 0 and h.previous_decision == DecisionTypes.check_deception.value):
                    # bet1
                    if self.finalBetLimit >= t.minBet \
                            and (not t.checkButton
                                 or not t.other_player_has_initiative
                                 or p.selected_strategy[stage + '_betting_condidion_1'] == 0):
                        self.decision = DecisionTypes.bet1
                        log.info("Bet1 condition met")
                    # bet2
                    if self.finalBetLimit >= (t.minBet + t.bigBlind * float(p.selected_strategy['BetPlusInc'])) \
                            and ((t.gameStage == GameStages.Turn.value and t.totalPotValue > t.bigBlind * 3)
                                 or t.gameStage == GameStages.River.value) \
                            and (not t.checkButton
                                 or not t.other_player_has_initiative
                                 or p.selected_strategy[stage + '_betting_condidion_1'] == 0):
                        self.decision = DecisionTypes.bet2
                        log.info("Bet2 condition met")
                    # bet3
                    log.debug(
                        f"Checking for betting half pot: {float(t.totalPotValue) / 2} "
                        f"needs be be below or equal {self.finalBetLimit}"
                    )
                    if (self.finalBetLimit >= float(t.totalPotValue) / 2) \
                            and (t.minBet < float(t.totalPotValue) / 2) and \
                            (not t.checkButton or not t.other_player_has_initiative or p.selected_strategy[
                                stage + '_betting_condidion_1'] == 0):
                        log.info("Bet3 condition met")
                        self.decision = DecisionTypes.bet3
                    # bet4
                    if t.allInCallButton == False and t.equity >= float(p.selected_strategy['betPotRiverEquity']) and \
                            t.gameStage == GameStages.River.value and \
                            float(t.totalPotValue) < t.bigBlind * float(
                        p.selected_strategy['betPotRiverEquityMaxBBM']) and \
                            (not t.checkButton or not t.other_player_has_initiative or p.selected_strategy[
                                stage + '_betting_condidion_1'] == 0):
                        log.info("Bet4 condition met")
                        self.decision = DecisionTypes.bet4

    def bluff(self, t, p, h):
        t.currentBluff = 0

        # Compute blockers for bluff decisions
        if not hasattr(self, 'blockers_info') or not self.blockers_info:
            self._analyze_blockers(t)

        # MULTI-STREET BARRELING: continue betting when we bet previous street
        if t.gameStage != GameStages.PreFlop.value and \
                self.decision in (DecisionTypes.check, DecisionTypes.check_deception) and \
                t.checkButton:
            if self._should_barrel(t, h):
                t.currentBluff = 1
                self.decision = DecisionTypes.bet3
                log.info(f"BARREL: eq={t.equity:.3f} stage={t.gameStage} spr={self.spr:.1f} "
                         f"(continuing aggression from previous street)")
                return

        # SEMI-BLUFF: bet/raise draws aggressively (not on river — draws are dead)
        if t.gameStage not in (GameStages.PreFlop.value, GameStages.River.value):
            if self.outs >= 8 and t.equity >= 0.25:
                if self.decision in (DecisionTypes.check, DecisionTypes.check_deception, DecisionTypes.fold,
                                     DecisionTypes.call):
                    if t.checkButton or not t.other_player_has_initiative:
                    # We can check — bet as semi-bluff
                        t.currentBluff = 1
                        # Use superb sizing for semi-bluffs to be balanced with value
                        self.decision = DecisionTypes.bet3 if self.optimal_bet_bb >= t.totalPotValue * 0.6 else DecisionTypes.bet2
                        log.info(f"SEMI-BLUFF BET: outs={self.outs} eq={t.equity:.3f} → {self.decision} (sizing={self.optimal_bet_bb:.1f}BB)")
                        return
                elif t.other_player_has_initiative and self.decision in (
                        DecisionTypes.call, DecisionTypes.fold):
                    # Facing a bet with strong draw — raise as semi-bluff
                    # Only if SPR allows it (don't semi-bluff when pot-committed)
                    if self.spr > 2.0 and self.outs >= 9:
                        t.currentBluff = 1
                        self.decision = DecisionTypes.bet4  # Raise
                        log.info(f"SEMI-BLUFF RAISE: outs={self.outs} eq={t.equity:.3f} "
                                 f"spr={self.spr:.1f} → {self.decision}")
                        return

        # Bayesian bluff opportunity: villain range capped → bluff if EV+
        _bexploit_bluff = getattr(self, '_bayesian_exploit', None)
        _banalysis_bluff = getattr(self, '_bayesian_analysis', None)
        if (_bexploit_bluff and _banalysis_bluff
                and _bexploit_bluff.get('action') == 'bet'
                and _banalysis_bluff.get('is_capped', False)
                and _bexploit_bluff.get('confidence', 0) >= 0.50
                and t.gameStage != GameStages.PreFlop.value
                and self.decision in (DecisionTypes.check, DecisionTypes.check_deception)
                and t.checkButton):
            # Bayesian says villain is capped — stab with any hand
            for exploit_info in _bexploit_bluff.get('exploits', []):
                if exploit_info.get('exploit') in ('position_bluff', 'bluff'):
                    t.currentBluff = 1
                    # Use superb sizing for bayesian bluffs too
                    self.decision = DecisionTypes.bet3 if self.optimal_bet_bb >= t.totalPotValue * 0.6 else DecisionTypes.bet2
                    log.info(f"BAYESIAN BLUFF: villain capped ({_banalysis_bluff.get('num_combos',0)} combos, "
                             f"value={_banalysis_bluff.get('value_pct',0):.0%}), "
                             f"conf={_bexploit_bluff['confidence']:.0%} → {self.decision}")
                    return

        # EV-based bluffing: only bluff when profitable
        if t.gameStage != GameStages.PreFlop.value and \
                self.decision in (DecisionTypes.check, DecisionTypes.check_deception):

            # Determine current bet fraction from geometric engine for accurate EV
            bet_frac = (self.optimal_bet_bb / t.totalPotValue) if t.totalPotValue > 0 else 0.5
            bet_frac = max(0.2, min(1.0, bet_frac)) # Clamp to reasonable sizes
            
            bluff_ev, check_ev, fold_eq = self._bluff_ev(t, h, bet_size_fraction=bet_frac)
            ev_gain = bluff_ev - check_ev

            # Only bluff when EV-positive and we have enough fold equity
            # Base threshold: need ~33% fold equity to break even on pot-sized bluff
            min_fold_eq = 0.33 + _get_adj().get('bluff_min_fold_eq_offset', 0.0)
            if not t.isHeadsUp:
                min_fold_eq = 0.45 + _get_adj().get('bluff_min_fold_eq_offset', 0.0)

            # --- Opponent-adaptive fold equity threshold ---
            opp = self._get_opp()
            if opp:
                ptype = opp.get('type', 'unknown')
                fold_to_cbet = opp.get('fold_to_cbet', 0.45)
                af = opp.get('af', 1.5)
                if ptype == 'nit':
                    min_fold_eq -= 0.08  # Nits fold a lot → bluff more
                    log.info(f"OPP_ADAPT: bluff threshold -8% vs NIT")
                elif ptype in ('fish_passive',):
                    min_fold_eq += 0.08  # Calling stations fold less → fewer bluffs
                    log.info(f"OPP_ADAPT: bluff threshold +8% vs FISH_PASSIVE")
                elif ptype == 'maniac':
                    min_fold_eq += 0.10  # Maniacs don't fold → don't bluff them
                elif ptype == 'tag':
                    min_fold_eq -= 0.05  # TAGs fold correctly → slight bluff increase
                # Fine-tune with actual fold-to-cbet stat
                if fold_to_cbet > 0.60:
                    min_fold_eq -= 0.05
                elif fold_to_cbet < 0.25:
                    min_fold_eq += 0.05

            # --- Live spot-type bluff adjustment ---
            _spot = getattr(self, '_spot_adj', {})
            if _spot:
                min_fold_eq += _spot.get('bluff_fold_eq_offset', 0.0)

            if ev_gain > 0 and fold_eq >= min_fold_eq:
                # Don't bluff with total air (no draws, no equity) on any street
                if t.equity < 0.12 and self.outs <= 1:
                    blocker = self._blocker_bonus(t.mycards, t.cardsOnTable) if t.mycards and t.cardsOnTable else 0
                    if blocker < 0.03:
                        log.info(f"BLUFF SKIP (total air): fold_eq={fold_eq:.3f} "
                                 f"eq={t.equity:.3f} outs={self.outs} ev_gain={ev_gain:.3f}")
                        return

                # Don't bluff with total air on river (need some showdown value or blockers)
                if t.gameStage == GameStages.River.value and t.equity < 0.10:
                    blocker = self._blocker_bonus(t.mycards, t.cardsOnTable) if t.mycards and t.cardsOnTable else 0
                    if blocker < 0.03:
                        log.info(f"BLUFF SKIP (river air, no blockers): fold_eq={fold_eq:.3f} "
                                 f"eq={t.equity:.3f} ev_gain={ev_gain:.3f}")
                    else:
                        t.currentBluff = 1
                        self.decision = DecisionTypes.bet_bluff
                        log.info(f"BLUFF (river blocker): fold_eq={fold_eq:.3f} eq={t.equity:.3f} "
                                 f"ev_gain={ev_gain:.3f} blocker={blocker:.3f}")
                else:
                    t.currentBluff = 1
                    self.decision = DecisionTypes.bet_bluff
                    log.info(f"BLUFF: fold_eq={fold_eq:.3f} eq={t.equity:.3f} "
                             f"ev_gain={ev_gain:.3f} stage={t.gameStage}")
            else:
                log.debug(f"BLUFF REJECTED: fold_eq={fold_eq:.3f} ev_gain={ev_gain:.3f} "
                          f"eq={t.equity:.3f} min_fold={min_fold_eq:.2f}")

    def check_deception(self, t, p, h):
        self.UseFlopCheckDeception = False
        self.UseTurnCheckDeception = False
        self.UseRiverCheckDeception = False

        # GTO check-raise/slow-play: trap with strong hands at low frequency
        # to keep our checking range balanced (otherwise opponents always fold to our bets)
        if t.equity < 0.75:
            return  # Only slow-play with very strong hands

        if t.gameStage == GameStages.River.value:
            return  # Never slow-play river — last chance for value

        # Frequency: trap ~15-25% of the time depending on equity
        # 75-85% equity → 15% trap freq, 85-95% → 20%, 95%+ → 30%
        if t.equity >= 0.95:
            trap_freq = 0.30
        elif t.equity >= 0.85:
            trap_freq = 0.20
        else:
            trap_freq = 0.15

        # Wet boards: trap less (opponent may improve for free)
        if hasattr(self, '_board_wetness') and t.cardsOnTable:
            wetness = self._board_wetness(t.cardsOnTable)
            if wetness > 0.5:
                trap_freq *= 0.5  # Halve trap frequency on wet boards

        if random.random() > trap_freq:
            return

        if self.decision in (DecisionTypes.bet1, DecisionTypes.bet2,
                             DecisionTypes.bet3, DecisionTypes.bet4):
            self.decision = DecisionTypes.check_deception
            if t.gameStage == GameStages.Flop.value:
                self.UseFlopCheckDeception = True
            else:
                self.UseTurnCheckDeception = True
            log.info(f"CHECK TRAP: eq={t.equity:.3f} stage={t.gameStage} freq={trap_freq:.0%}")

    def _board_wetness(self, board_cards):
        """0.0=bone dry, 1.0=extremely wet. Uses flop cards only."""
        if not board_cards or len(board_cards) < 3:
            return 0.5
        rank_map = {r: i for i, r in enumerate('23456789TJQKA')}
        ranks, suits = [], []
        for card in board_cards[:3]:
            if len(card) >= 2:
                ranks.append(rank_map.get(card[0].upper(), 0))
                suits.append(card[1].upper())
        if len(ranks) < 3:
            return 0.5

        wetness = 0.0
        from collections import Counter
        top_suit = Counter(suits).most_common(1)[0][1]
        if top_suit >= 3: wetness += 0.4      # Monotone
        elif top_suit >= 2: wetness += 0.2    # Two-tone

        sr = sorted(ranks)
        gaps = [sr[i+1] - sr[i] for i in range(len(sr)-1)]
        if all(g <= 2 for g in gaps): wetness += 0.2    # Connected
        if all(g == 1 for g in gaps): wetness += 0.1    # Very connected

        if sum(ranks)/len(ranks) >= 10: wetness += 0.1  # Broadway-heavy
        if len(set(ranks)) < len(ranks): wetness -= 0.15 # Paired = drier

        return max(0.0, min(1.0, wetness))

    def _parse_card(self, card_str):
        """Parse card string like 'QD', 'AH', '10S', 'TS' into (rank_num, suit_char)."""
        if not card_str or len(card_str) < 2:
            return (0, '?')
        card = card_str.upper()
        if len(card) == 3 and card[:2] == '10':
            return (10, card[2])
        rank_map = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
                    '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        return (rank_map.get(card[:-1].upper(), 0), card[-1])

    def _classify_hand(self, t):
        """Classify hero's made hand strength on the current board.

        Returns dict with:
            rank: 0-8 (high_card to straight_flush)
            name: descriptive name
            strength: 'weak', 'marginal', 'medium', 'strong', 'very_strong', 'monster'
        Returns None if cards not available.
        """
        if not getattr(t, 'mycards', None) or len(t.mycards) < 2:
            return None
        if not getattr(t, 'cardsOnTable', None) or len(t.cardsOnTable) < 3:
            return None

        hero = [self._parse_card(c) for c in t.mycards]
        board = [self._parse_card(c) for c in t.cardsOnTable]
        all_cards = hero + board

        hero_ranks = [r for r, s in hero]
        hero_suits = [s for r, s in hero]
        board_ranks = [r for r, s in board]
        all_ranks = [r for r, s in all_cards]
        all_suits = [s for r, s in all_cards]

        from collections import Counter
        suit_counts = Counter(all_suits)
        flush_suit = None
        for s, cnt in suit_counts.items():
            if cnt >= 5:
                flush_suit = s
        has_flush = flush_suit is not None
        hero_in_flush = has_flush and any(s == flush_suit for s in hero_suits)

        # --- Straight detection ---
        def check_straight(rank_list):
            unique = sorted(set(rank_list))
            if 14 in unique:
                unique = [1] + unique  # wheel
            best = 0
            for i in range(len(unique) - 4):
                if unique[i + 4] - unique[i] == 4:
                    window = set(range(unique[i], unique[i] + 5))
                    if window.issubset(set(unique)):
                        best = unique[i + 4]
            return best > 0, best

        all_straight, straight_high = check_straight(all_ranks)
        board_straight, _ = check_straight(board_ranks)
        hero_makes_straight = all_straight and not board_straight

        # --- Rank counting ---
        all_rank_counts = Counter(all_ranks)
        quads = [r for r, c in all_rank_counts.items() if c == 4]
        trips = [r for r, c in all_rank_counts.items() if c == 3]
        pairs = [r for r, c in all_rank_counts.items() if c == 2]

        hero_in_quads = any(r in hero_ranks for r in quads)
        hero_in_trips = any(r in hero_ranks for r in trips)
        hero_in_pairs = any(r in hero_ranks for r in pairs)

        # --- Classify highest to lowest ---

        # Straight flush
        if has_flush and all_straight and hero_in_flush:
            flush_ranks = sorted([r for r, s in all_cards if s == flush_suit])
            if 14 in flush_ranks:
                flush_ranks = [1] + flush_ranks
            for i in range(len(flush_ranks) - 4):
                if flush_ranks[i + 4] - flush_ranks[i] == 4:
                    return {'rank': 8, 'name': 'straight_flush', 'strength': 'monster'}

        # Quads
        if quads and hero_in_quads:
            return {'rank': 7, 'name': 'quads', 'strength': 'monster'}

        # Full house
        if len(trips) >= 1 and (len(pairs) >= 1 or len(trips) >= 2):
            if hero_in_trips or hero_in_pairs:
                return {'rank': 6, 'name': 'full_house', 'strength': 'monster'}

        # Flush (hero contributes)
        if has_flush and hero_in_flush:
            hero_flush = sorted([r for r, s in hero if s == flush_suit], reverse=True)
            top = hero_flush[0] if hero_flush else 0
            if top >= 14:
                return {'rank': 5, 'name': 'nut_flush', 'strength': 'monster'}
            elif top >= 12:
                return {'rank': 5, 'name': 'high_flush', 'strength': 'very_strong'}
            else:
                return {'rank': 5, 'name': 'low_flush', 'strength': 'strong'}

        # Board flush (hero doesn't contribute — usually bad)
        if has_flush and not hero_in_flush:
            return {'rank': 0, 'name': 'no_flush_card', 'strength': 'weak'}

        # Straight (hero contributes)
        if hero_makes_straight:
            if straight_high >= 14:
                return {'rank': 4, 'name': 'nut_straight', 'strength': 'very_strong'}
            return {'rank': 4, 'name': 'straight', 'strength': 'strong'}

        # Set (pocket pair hit board)
        if trips and hero_in_trips:
            if hero_ranks[0] == hero_ranks[1] and hero_ranks[0] in trips:
                return {'rank': 3, 'name': 'set', 'strength': 'very_strong'}
            return {'rank': 3, 'name': 'trips', 'strength': 'strong'}

        # Two pair
        hero_pair_ranks = [r for r in pairs if r in hero_ranks]
        if len(hero_pair_ranks) >= 2:
            return {'rank': 2, 'name': 'two_pair', 'strength': 'strong'}
        elif len(hero_pair_ranks) == 1 and len(pairs) >= 2:
            # Hero contributes to one pair, board has another pair
            # If hero's pair is BELOW the board pair, it's weak — everyone
            # shares the top board pair (e.g. JJ on AxxA board = underpair + board pair)
            board_pair_ranks = [r for r in pairs if r not in hero_ranks]
            hero_pr = hero_pair_ranks[0]
            board_pr = max(board_pair_ranks) if board_pair_ranks else 0
            if hero_pr < board_pr:
                return {'rank': 1, 'name': 'underpair_board_pair', 'strength': 'weak'}
            return {'rank': 2, 'name': 'two_pair', 'strength': 'medium'}

        # One pair (hero contributes)
        if hero_in_pairs:
            pair_rank = max(r for r in pairs if r in hero_ranks)
            board_sorted = sorted(board_ranks, reverse=True)

            # Overpair
            if hero_ranks[0] == hero_ranks[1] and pair_rank > board_sorted[0]:
                return {'rank': 1, 'name': 'overpair', 'strength': 'strong'}
            # Top pair
            if pair_rank == board_sorted[0]:
                kicker = max((r for r in hero_ranks if r != pair_rank), default=0)
                if kicker >= 11:  # J+ kicker
                    return {'rank': 1, 'name': 'top_pair_good_kicker', 'strength': 'medium'}
                return {'rank': 1, 'name': 'top_pair_weak_kicker', 'strength': 'marginal'}
            # Second pair
            if len(board_sorted) > 1 and pair_rank >= board_sorted[1]:
                return {'rank': 1, 'name': 'second_pair', 'strength': 'marginal'}
            return {'rank': 1, 'name': 'low_pair', 'strength': 'weak'}

        # Board pair (hero doesn't contribute)
        if pairs:
            return {'rank': 0, 'name': 'board_pair_only', 'strength': 'weak'}

        # High card
        top_hero = max(hero_ranks)
        if top_hero >= 14:
            return {'rank': 0, 'name': 'ace_high', 'strength': 'weak'}
        return {'rank': 0, 'name': 'high_card', 'strength': 'weak'}

    def _estimate_fold_equity(self, t, h):
        """Estimate probability opponent folds to a bet (0.0 - 1.0).

        Uses available signals: board texture, initiative, position,
        opponent behavior, heads-up/multiway, street.
        """
        fold_eq = 0.0

        # --- Base rate by street (micro stakes: opponents call very wide) ---
        street_base = {
            GameStages.Flop.value: 0.30,
            GameStages.Turn.value: 0.25,
            GameStages.River.value: 0.20,
        }
        fold_eq = street_base.get(t.gameStage, 0.28)

        # --- Board texture: scary boards get more folds ---
        wetness = self._board_wetness(t.cardsOnTable)
        # Dry boards: opponents fold more (they missed)
        # Wet boards: opponents fold less (they have draws/pairs)
        fold_eq += (0.5 - wetness) * 0.12  # dry +6%, wet -6%

        # --- Scare cards: high cards on board pressure opponents ---
        if t.cardsOnTable:
            rank_map = {r: i for i, r in enumerate('23456789TJQKA')}
            board_ranks = [rank_map.get(c[0].upper(), 0) for c in t.cardsOnTable if len(c) >= 2]
            high_cards = sum(1 for r in board_ranks if r >= 10)  # J, Q, K, A
            fold_eq += high_cards * 0.03  # each broadway card +3%

        # --- We have initiative (we were betting) → more credible ---
        if not t.other_player_has_initiative:
            fold_eq += 0.08

        # --- Opponent showed weakness (checked to us) ---
        if t.checkButton:
            fold_eq += 0.06

        # --- Position: in-position bluffs are more credible ---
        pos = getattr(t, '_gto_position', getattr(t, 'position_utg_plus', 3))
        if isinstance(pos, str):
            pos_bonus = {'BTN': 0.06, 'CO': 0.04, 'MP': 0.0, 'SB': -0.03, 'BB': -0.02, 'UTG': -0.02}
            fold_eq += pos_bonus.get(pos, 0.0)
        elif isinstance(pos, (int, float)):
            # position_utg_plus: 0=UTG, higher=later position
            fold_eq += min(pos, 4) * 0.015

        # --- Multiway: much harder to bluff multiple players ---
        if not t.isHeadsUp:
            fold_eq -= 0.15

        # --- Continuation: we bet previous street (story is consistent) ---
        if h.round_number == 0 and h.previous_decision in (
            DecisionTypes.bet1.value, DecisionTypes.bet2.value,
            DecisionTypes.bet3.value, DecisionTypes.bet4.value,
            DecisionTypes.bet_bluff.value,
        ):
            fold_eq += 0.05  # continuation = credible

        # --- Blocker analysis: do our hole cards block opponent's strong hands? ---
        if t.mycards and t.cardsOnTable and len(t.cardsOnTable) >= 3:
            fold_eq += self._blocker_bonus(t.mycards, t.cardsOnTable)

        # --- Opponent range strength: strong range = less likely to fold ---
        opp_strength = self._estimate_opponent_range_strength(t, h)
        fold_eq -= (opp_strength - 0.5) * 0.15  # Strong range: -7.5%, weak range: +7.5%

        # --- Our representation: credible line = more folds ---
        our_rep = self._what_we_represent(t, h)
        fold_eq += (our_rep - 0.5) * 0.10  # Strong rep: +5%, weak rep: -5%

        # Blocker bonus: if we block opponent's value hands, they fold more
        if hasattr(self, 'blockers_info') and self.blockers_info:
            fold_eq += self.blockers_info.get('blocker_score', 0) * 0.08

        # --- Opponent profile adjustment ---
        opp_profile = getattr(self, '_opp_profile', None)
        if opp_profile and opp_profile.get('hands', 0) >= 10:
            fold_eq += opp_profile.get('fold_equity_bonus', 0.0)

        # --- Feedback loop adjustment ---
        fold_eq += _get_adj().get('fold_equity_offset', 0.0)

        return max(0.05, min(0.85, fold_eq))

    def _blocker_bonus(self, mycards, board):
        """Bonus fold equity from holding blockers to opponent's strong hands."""
        bonus = 0.0
        if not mycards or len(mycards) < 2:
            return 0.0

        rank_map = {r: i for i, r in enumerate('23456789TJQKA')}
        my_ranks = [rank_map.get(c[0].upper(), 0) for c in mycards if len(c) >= 2]
        my_suits = [c[1].upper() for c in mycards if len(c) >= 2]
        board_suits = [c[1].upper() for c in board if len(c) >= 2]

        # Flush blocker: we hold the ace of a suit with 2+ of that suit on board
        from collections import Counter
        suit_counts = Counter(board_suits)
        for suit, count in suit_counts.items():
            if count >= 2:
                # Check if we hold the A of that suit
                for i, (r, s) in enumerate(zip(my_ranks, my_suits)):
                    if s == suit and r == 12:  # Ace of flush suit
                        bonus += 0.06
                    elif s == suit and r == 11:  # King of flush suit
                        bonus += 0.03

        # Straight blocker: we hold cards that block the nut straight
        # (simplified: holding an A on a broadway-heavy board)
        board_ranks = [rank_map.get(c[0].upper(), 0) for c in board if len(c) >= 2]
        if 12 in my_ranks and any(r >= 9 for r in board_ranks):
            bonus += 0.03  # Holding A on connected high board

        return min(bonus, 0.12)

    def _bluff_ev(self, t, h, bet_size_fraction=0.5):
        """Calculate EV of bluffing vs checking.

        Uses eval7 range-based fold equity when available (postflop with board
        cards and villain range estimate). Falls back to heuristic.

        Returns (bluff_ev, check_ev, fold_equity).
        bet_size_fraction: bet as fraction of pot (0.5 = half pot)
        """
        pot = max(t.totalPotValue, 0.01)
        bet_size = pot * bet_size_fraction
        equity = t.equity
        fold_eq = self._estimate_fold_equity(t, h)  # Heuristic fallback

        # --- eval7 range-based fold equity (postflop only) ---
        board = getattr(t, 'cardsOnTable', None) or []
        cards = getattr(t, 'mycards', None) or []
        if len(board) >= 3 and len(cards) == 2:
            try:
                from gamble.decisionmaker.range_equity import compute_range_fold_equity
                v_range = getattr(self, '_villain_range_str', None)
                if not v_range:
                    # Estimate villain range from context
                    opp = self._get_opp()
                    ptype = (opp.get('type', 'unknown')
                             if opp and opp.get('hands', 0) >= 10 else 'unknown')
                    street = t.gameStage.lower() if t.gameStage != 'PreFlop' else 'preflop'
                    v_action = 'bet' if not t.checkButton else 'check'
                    from gamble.decisionmaker.range_equity import get_range_equity
                    re = get_range_equity()
                    v_range = re.estimate_villain_range(
                        position='CO', action=v_action,
                        player_type=ptype, street=street,
                    )
                if v_range:
                    fe_result = compute_range_fold_equity(
                        cards, board, v_range, bet_size_fraction)
                    if fe_result and fe_result['total_combos'] >= 20:
                        fold_eq = fe_result['fold_equity']
                        equity = fe_result['equity_when_called']
                        log.debug(f"EVAL7 FOLD_EQ: {fold_eq:.0%} "
                                  f"(vs {fe_result['total_combos']} combos, "
                                  f"eq_called={equity:.0%})")
            except Exception as e:
                log.debug(f"eval7 fold equity failed: {e}")

        # EV of checking (passive line)
        check_ev = t.equity * pot  # Use original equity for check EV

        # EV of betting
        ev_when_called = equity * (pot + bet_size) - (1 - equity) * bet_size
        bluff_ev = fold_eq * pot + (1 - fold_eq) * ev_when_called

        return bluff_ev, check_ev, fold_eq

    def _should_barrel(self, t, h):
        """Decide whether to continue betting on turn/river after betting previous street.

        Returns True if we should fire another barrel.
        """
        if t.gameStage == GameStages.PreFlop.value or t.gameStage == GameStages.Flop.value:
            return False  # Only relevant on turn/river

        # Did we bet previous street?
        prev_bet = h.previous_decision in (
            DecisionTypes.bet1.value, DecisionTypes.bet2.value,
            DecisionTypes.bet3.value, DecisionTypes.bet4.value,
            DecisionTypes.bet_bluff.value,
        )
        if not prev_bet:
            return False  # We didn't bet last street, not a barrel

        # Good barrel conditions:
        # 1. Our equity improved or stayed strong
        if t.equity >= 0.55:
            return True  # Value barrel

        # 2. Scare card on turn/river (A, K hit the board)
        if t.cardsOnTable and len(t.cardsOnTable) >= 4:
            rank_map = {r: i for i, r in enumerate('23456789TJQKA')}
            latest_card = t.cardsOnTable[-1]  # Most recent card
            if len(latest_card) >= 2:
                latest_rank = rank_map.get(latest_card[0].upper(), 0)
                if latest_rank >= 11:  # K or A on turn/river
                    return True  # Scare card barrel

                # Flush completing card
                board_suits = [c[1].upper() for c in t.cardsOnTable if len(c) >= 2]
                from collections import Counter
                if Counter(board_suits).most_common(1)[0][1] >= 3:
                    # 3+ of a suit — potential flush completed
                    my_suits = [c[1].upper() for c in t.mycards if len(c) >= 2] if t.mycards else []
                    if any(s == Counter(board_suits).most_common(1)[0][0] for s in my_suits):
                        return True  # We have the flush suit — barrel

        # 3. We have outs (semi-barrel)
        if self.outs >= 8 and t.gameStage == GameStages.Turn.value:
            return True

        return False

    def _estimate_opponent_range_strength(self, t, h):
        """Estimate how strong the opponent's range is based on their actions this hand.

        Returns 0.0 (weak/wide) to 1.0 (very strong/narrow).

        Key insight: each aggressive action narrows opponent's range.
        - Preflop open from EP = strong
        - Preflop call = medium
        - Postflop raise = very strong
        - Check then call = medium/drawing
        - Check then fold = weak (but we don't see this)
        """
        strength = 0.5  # Default: unknown

        # --- Preflop raiser position narrows range ---
        if not np.isnan(getattr(t, 'first_raiser_utg', np.nan)):
            raiser_utg = t.first_raiser_utg
            # Earlier position = tighter range = stronger
            if raiser_utg <= 1:    # UTG/UTG+1
                strength += 0.15
            elif raiser_utg <= 2:  # MP
                strength += 0.10
            elif raiser_utg <= 3:  # CO
                strength += 0.05
            # BTN/SB open = wide range, no bonus

        # --- 3-bettor = very strong range ---
        if not np.isnan(getattr(t, 'second_raiser_utg', np.nan)):
            strength += 0.15  # 3-bet = strong range

        # --- Postflop actions indicate strength ---
        if t.gameStage != GameStages.PreFlop.value:
            # Opponent has initiative = they were betting/raising
            if t.other_player_has_initiative:
                strength += 0.10

            # Opponent raised us (we bet, they raised) = very strong
            if not t.checkButton and t.minCall > 0:
                # We're facing a bet/raise
                call_to_pot = t.minCall / max(t.totalPotValue, 0.01)
                if call_to_pot > 0.5:
                    strength += 0.10  # Big bet/raise = strong
                if call_to_pot > 1.0:
                    strength += 0.10  # Overbet = polarized (very strong or bluff)

            # Later streets with continued aggression = stronger
            if t.gameStage == GameStages.Turn.value and t.other_player_has_initiative:
                strength += 0.05  # Firing second barrel
            elif t.gameStage == GameStages.River.value and t.other_player_has_initiative:
                strength += 0.10  # Triple barrel = very strong or bluff

        # --- Board texture modifies range strength ---
        # On very wet boards, opponent's range includes more draws (weaker)
        if t.cardsOnTable and len(t.cardsOnTable) >= 3:
            wetness = self._board_wetness(t.cardsOnTable)
            strength -= wetness * 0.08  # Wet boards = more draws in range

        return max(0.1, min(0.95, strength))

    def _what_we_represent(self, t, h):
        """Estimate what range WE appear to have based on our line.

        Returns 0.0 (weak) to 1.0 (very strong).
        Used to decide if bluffs are credible.
        """
        rep_strength = 0.3  # Default: unknown/passive

        # Preflop raise = we represent a strong hand
        prev = getattr(h, 'previous_decision', 0)
        bet_decisions = (
            DecisionTypes.bet1.value, DecisionTypes.bet2.value,
            DecisionTypes.bet3.value, DecisionTypes.bet4.value,
            DecisionTypes.bet_bluff.value,
        )

        # Did we raise preflop? (check history)
        if h.histGameStage == GameStages.PreFlop.value and prev in bet_decisions:
            rep_strength += 0.20  # We opened/3-bet

        # Are we betting this street? (current decision)
        if self.decision in (DecisionTypes.bet1, DecisionTypes.bet2,
                             DecisionTypes.bet3, DecisionTypes.bet4,
                             DecisionTypes.bet_bluff):
            rep_strength += 0.15

        # Continuation from previous street
        if h.round_number == 0 and prev in bet_decisions:
            rep_strength += 0.10  # We bet last street too (consistent story)

        # Position: IP bets are more credible
        pos = getattr(t, 'position_utg_plus', 3)
        if isinstance(pos, (int, float)) and pos >= 3:
            rep_strength += 0.05  # Late position = more credible

        return max(0.1, min(0.95, rep_strength))

    def _geometric_bet_size(self, current_pot, effective_stack, streets_remaining):
        """
        Calculate the geometric bet size to get stacks in by the river.

        Formula: B = Pot * (( (S/P + 1)^(1/N) ) - 1) / 2
        Where S=Stack, P=Pot, N=Streets
        """
        if streets_remaining <= 0:
            return effective_stack

        # Prevent division by zero or negative log
        pot = max(current_pot, 0.01)
        stack = max(effective_stack, 0.01)

        # Calculate required growth factor per street
        total_growth = (stack / pot) + 1
        street_growth = total_growth ** (1 / streets_remaining)

        # Convert growth factor to bet size (as fraction of pot)
        # Pot_next = Pot_curr * growth
        # Pot_curr + 2*Bet = Pot_curr * growth
        # 2*Bet = Pot_curr * (growth - 1)
        # Bet = Pot_curr * (growth - 1) / 2
        bet_amount = pot * (street_growth - 1) / 2

        return bet_amount

    def river_value_bet(self, t, p, h):
        """Thin value bet on river: bet when we're likely ahead of opponent's calling range.

        Called from make_decision() on the river when we can check.
        """
        if t.gameStage != GameStages.River.value:
            return
        if not t.checkButton:
            return  # We're facing a bet, not our decision to value bet

        # Already decided to bet? Don't override.
        if self.decision in (DecisionTypes.bet1, DecisionTypes.bet2,
                             DecisionTypes.bet3, DecisionTypes.bet4):
            return

        opp_strength = self._estimate_opponent_range_strength(t, h)

        # Thin value: bet when our equity is good enough relative to opponent's range
        # On river, equity = probability we win at showdown
        # We need to be called by worse hands more than by better hands
        #
        # Key math: if opponent calls with range centered around opp_strength,
        # we want our equity to be significantly above their calling threshold.

        rv_thresh = _get_adj().get('river_value_threshold', 0.60)
        tv_thresh = _get_adj().get('thin_value_threshold', 0.50)

        if t.equity >= rv_thresh:
            # Standard value bet: we're likely ahead
            if opp_strength < 0.65:  # Opponent doesn't seem super strong
                self.decision = DecisionTypes.bet3  # Half pot
                log.info(f"RIVER VALUE BET: eq={t.equity:.3f} opp_range={opp_strength:.2f} "
                         f"spr={self.spr:.1f}")
        elif t.equity >= tv_thresh and opp_strength < 0.50:
            # Very thin value: only when opponent looks weak
            # Smaller sizing to get called by worse
            if self.spr < 5.0:  # Don't thin value bet deep
                self.decision = DecisionTypes.bet1  # Small bet
                log.info(f"RIVER THIN VALUE: eq={t.equity:.3f} opp_range={opp_strength:.2f} "
                         f"spr={self.spr:.1f}")
    def facing_raise(self, t, p, h):
        """Logic for when opponent raises our bet (postflop 3-bet decision).

        Only applies when we bet and opponent raised (no check button, facing larger bet).
        """
        if t.gameStage == GameStages.PreFlop.value:
            return  # Preflop raises handled by preflop logic
        if t.checkButton:
            return  # Not facing a raise

        # Detect if this is a re-raise situation (we bet previously this street)
        is_reraise = (h.round_number > 0 and h.previous_decision in (
            DecisionTypes.bet1.value, DecisionTypes.bet2.value,
            DecisionTypes.bet3.value, DecisionTypes.bet4.value,
            DecisionTypes.bet_bluff.value,
        ))

        if not is_reraise:
            return  # Not a raise over our bet

        opp_strength = self._estimate_opponent_range_strength(t, h)
        log.info(f"FACING RAISE: eq={t.equity:.3f} opp_range={opp_strength:.2f} "
                 f"spr={self.spr:.1f} stage={t.gameStage}")
        # Opponent raised our bet — their range is strong
        # Decision: re-raise (4-bet), call, or fold

        # 1. Very strong hand: re-raise for value
        if t.equity >= 0.80:
            # Use superb sizing for re-raises
            self.decision = DecisionTypes.bet4 if self.optimal_bet_bb >= self.hero_stack_bb * 0.7 else DecisionTypes.bet3
            log.info(f"RE-RAISE VALUE: eq={t.equity:.3f} → {self.decision} (sizing={self.optimal_bet_bb:.1f}BB)")
            return

        # 2. Strong hand but not monster: call (keep them in with bluffs)
        if t.equity >= 0.60:
            self.decision = DecisionTypes.call
            log.info(f"CALL RAISE (strong but not monster): eq={t.equity:.3f}")
            return

        # 3. Draw with good odds: call or re-raise (semi-bluff)
        if self.outs >= 8 and t.gameStage != GameStages.River.value:
            pot_odds = t.minCall / max(t.totalPotValue + t.minCall, 0.01)
            implied_adj = 0.08  # Implied odds for big draw
            if t.equity >= (pot_odds - implied_adj):
                self.decision = DecisionTypes.call
                log.info(f"CALL RAISE (draw): eq={t.equity:.3f} outs={self.outs} "
                         f"pot_odds={pot_odds:.3f}")
                return

        # 4. Medium hand facing raise: fold unless getting great price
        if t.equity >= 0.40 and opp_strength < 0.60:
            # Opponent might be bluffing — call if pot odds justify it
            pot_odds = t.minCall / max(t.totalPotValue + t.minCall, 0.01)
            if t.equity >= pot_odds:
                self.decision = DecisionTypes.call
                log.info(f"CALL RAISE (bluff-catch): eq={t.equity:.3f} opp_range={opp_strength:.2f}")
                return

        # 5. Weak hand facing strong raise: fold
        # (calling() already set fold, just log why)
        log.info(f"FOLD TO RAISE: eq={t.equity:.3f} opp_range={opp_strength:.2f}")

    def check_raise(self, t, p, h):
        """Check-raise for value: when we have a strong hand and opponent has initiative,
        check to let them bet, then raise. Only when facing a bet (no check button)."""
        if t.gameStage == GameStages.PreFlop.value:
            return  # No check-raising preflop (handled by 3-bet logic)

        if t.checkButton:
            return  # Can't check-raise when we have the check button (we go first)

        # We're facing a bet (no check button, opponent bet into us)
        # If we have a very strong hand, raise instead of just calling
        if t.equity >= 0.75 and t.other_player_has_initiative:
            # Check-raise frequency: more on dry boards (less likely to be outdraw)
            wetness = self._board_wetness(t.cardsOnTable)
            cr_freq = 0.45 - (wetness * 0.20)  # 45% dry, 25% wet

            # Higher frequency with low SPR (want to get stacks in)
            if self.spr < 4.0:
                cr_freq += 0.15

            if random.random() < cr_freq:
                # Match superb sizing: if optimal is large, use bet4
                self.decision = DecisionTypes.bet4 if self.optimal_bet_bb >= self.hero_stack_bb * 0.7 or self.optimal_bet_bb >= t.totalPotValue * 0.8 else DecisionTypes.bet3
                log.info(f"CHECK-RAISE VALUE: eq={t.equity:.3f} spr={self.spr:.1f} → {self.decision} (sizing={self.optimal_bet_bb:.1f}BB)")

        # Semi-bluff raise with draws: raise opponent's bet for fold equity + draw equity
        elif self.outs >= 8 and t.equity >= 0.25 and t.other_player_has_initiative:
            if t.gameStage != GameStages.River.value:  # No draws on river
                # Stronger draws raise more often
                cr_freq = 0.30 if self.outs >= 12 else 0.25 if self.outs >= 9 else 0.20
                # Lower SPR = more willing to raise (getting stacks in with draw)
                if self.spr < 4.0:
                    cr_freq += 0.10
                if t.isHeadsUp and random.random() < cr_freq:
                    size = DecisionTypes.bet4 if self.spr < 3.0 else DecisionTypes.bet3
                    self.decision = size
                    log.info(f"SEMI-BLUFF RAISE: outs={self.outs} eq={t.equity:.3f} "
                             f"spr={self.spr:.1f} freq={cr_freq:.0%}")

    def call_deception(self, t, p, h):
        pass

    def bully(self, t, p, h):
        if t.isHeadsUp:
            for i in range(t.total_players-1):
                if t.other_players[i]['status'] == 1:
                    break
            opponentFunds = t.other_players[i]['funds']

            if opponentFunds == '':
                opponentFunds = float(p.selected_strategy['initialFunds'])

            self.bullyMode = opponentFunds > float(
                p.selected_strategy['bullyDivider'])

            if (t.equity >= float(p.selected_strategy['minBullyEquity'])) and (
                    t.equity <= float(p.selected_strategy['maxBullyEquity'])) and self.bullyMode:
                self.decision = DecisionTypes.bet_bluff
                log.info("Bullying activated")
                self.bullyDecision = True
            else:
                self.bullyDecision = False

    def admin(self, t, p, h):
        if t.gameStage != GameStages.PreFlop.value:
            if int(p.selected_strategy['minimum_bet_size']) == 2 and self.decision == DecisionTypes.bet1:
                self.decision = DecisionTypes.bet2
            if int(p.selected_strategy['minimum_bet_size']) == 3 and self.decision == DecisionTypes.bet1:
                self.decision = DecisionTypes.bet3
            if int(p.selected_strategy['minimum_bet_size']) == 3 and self.decision == DecisionTypes.bet2:
                self.decision = DecisionTypes.bet3
            if int(p.selected_strategy['minimum_bet_size']) == 4 and self.decision == DecisionTypes.bet1:
                self.decision = DecisionTypes.bet4
            if int(p.selected_strategy['minimum_bet_size']) == 4 and self.decision == DecisionTypes.bet2:
                self.decision = DecisionTypes.bet4
            if int(p.selected_strategy['minimum_bet_size']) == 4 and self.decision == DecisionTypes.bet3:
                self.decision = DecisionTypes.bet4

        if t.checkButton == False and t.minCall == 0.0 and p.selected_strategy['use_pot_multiples'] == 0:
            self.ErrCallButton = True
            log.error("Call button or pot multiple had no value")
        else:
            self.ErrCallButton = False

        if t.allInCallButton and self.decision != DecisionTypes.fold:
            if self.decision in (DecisionTypes.check, DecisionTypes.check_deception):
                pass  # Check is free, keep it
            else:
                # Pot Odds Guard: equity < call / (pot + call)
                pot = max(t.totalPotValue, 0.01)
                call = max(t.minCall, 0)
                pot_odds_limit = call / (pot + call) if (pot + call) > 0 else 0
                # Minimum floor 0.18 (never call with pure garbage)
                all_in_threshold = max(0.18, pot_odds_limit)
                
                if t.equity >= all_in_threshold:
                    log.info(f"All-in call button: equity {t.equity:.3f} >= threshold {all_in_threshold:.3f}, calling")
                    self.decision = DecisionTypes.call
                else:
                    log.info(f"ALL-IN GUARD (admin): equity {t.equity:.3f} < threshold {all_in_threshold:.3f} "
                             f"(pot_odds={pot_odds_limit:.3f}), folding instead of all-in")
                    self.decision = DecisionTypes.fold

        h.lastSecondRoundAdjustment = self.secondRoundAdjustment

        if self.decision == DecisionTypes.check or self.decision == DecisionTypes.check_deception:
            h.myLastBet = 0
        if self.decision == DecisionTypes.call or self.decision == DecisionTypes.check_deception:
            h.myLastBet = t.minCall

        if self.decision == DecisionTypes.bet1:
            h.myLastBet = t.minBet
        if self.decision == DecisionTypes.bet2:
            h.myLastBet = t.minBet * float(
                p.selected_strategy['BetPlusInc']) + t.minBet
        if self.decision == DecisionTypes.bet_bluff:
            h.myLastBet = t.totalPotValue / 2
        if self.decision == DecisionTypes.bet3:
            h.myLastBet = t.totalPotValue / 2
        if self.decision == DecisionTypes.bet4:
            h.myLastBet = t.totalPotValue

        if t.checkButton:
            if self.decision == DecisionTypes.fold:
                self.decision = DecisionTypes.check
            if self.decision == DecisionTypes.call:
                self.decision = DecisionTypes.check
            if self.decision == DecisionTypes.call_deception:
                self.decision = DecisionTypes.check_deception

    def _compute_decision_ev(self, t, p, h):
        """Compute EV of the decision just made. Stored as self.decision_ev (in BB)."""
        pot = max(getattr(t, 'totalPotValue', 0) or 0, 0.01)
        call = max(getattr(t, 'minCall', 0) or 0, 0)
        equity = t.equity if hasattr(t, 'equity') else 0.5

        if self.decision == DecisionTypes.fold.value:
            self.decision_ev = 0.0  # Folding always has EV=0 (we lose nothing more)
        elif self.decision in (DecisionTypes.call.value, DecisionTypes.check.value):
            if call > 0:
                # EV(call) = equity * (pot + call) - (1 - equity) * call
                self.decision_ev = equity * (pot + call) - (1 - equity) * call
            else:
                # Free check — EV = equity * pot
                self.decision_ev = equity * pot
        else:
            # Betting/raising — use fold equity estimate
            fold_eq = self._estimate_fold_equity(t, h) if hasattr(self, '_estimate_fold_equity') else 0.3
            bet_size = pot * 0.5  # Approximate
            # EV(bet) = fold_eq * pot + (1 - fold_eq) * (equity * (pot + 2*bet_size) - bet_size)
            self.decision_ev = fold_eq * pot + (1 - fold_eq) * (equity * (pot + 2 * bet_size) - bet_size)

    def _analyze_blockers(self, t):
        """Analyze what strong opponent hands our hole cards block."""
        self.blockers_info = {
            'blocks_nut_flush': False,
            'blocks_top_pair': False,
            'blocks_overpair': False,
            'blocks_sets': False,
            'blocker_score': 0.0,  # 0-1, higher = more blockers
        }

        if not hasattr(t, 'mycards') or not t.mycards or len(t.mycards) < 2:
            return

        try:
            my_cards = list(t.mycards)  # e.g. ['AH', 'KS']
        except:
            return

        my_ranks = []
        my_suits = []
        for card in my_cards:
            if len(card) >= 2:
                my_ranks.append(card[0].upper())
                my_suits.append(card[1].upper())

        if len(my_ranks) < 2:
            return

        board_cards = getattr(t, 'cardsOnTable', []) or []
        board_ranks = []
        board_suits = []
        for card in board_cards:
            if card and len(card) >= 2:
                board_ranks.append(card[0].upper())
                board_suits.append(card[1].upper())

        score = 0.0

        # 1. Nut flush blocker: we hold the ace of the most common board suit
        if board_suits:
            from collections import Counter
            suit_counts = Counter(board_suits)
            most_common_suit = suit_counts.most_common(1)[0]
            if most_common_suit[1] >= 2:  # Two-tone or monotone
                flush_suit = most_common_suit[0]
                for i, s in enumerate(my_suits):
                    if s == flush_suit and my_ranks[i] == 'A':
                        self.blockers_info['blocks_nut_flush'] = True
                        score += 0.3
                        break

        # 2. Top pair blocker: we hold the highest board rank
        if board_ranks:
            rank_order = '23456789TJQKA'
            board_rank_values = [rank_order.index(r) for r in board_ranks if r in rank_order]
            if board_rank_values:
                highest_board_rank = rank_order[max(board_rank_values)]
                if highest_board_rank in my_ranks:
                    self.blockers_info['blocks_top_pair'] = True
                    score += 0.2

        # 3. Overpair blocker: we hold A or K (blocks AA, KK)
        if 'A' in my_ranks:
            self.blockers_info['blocks_overpair'] = True
            score += 0.15
        elif 'K' in my_ranks:
            self.blockers_info['blocks_overpair'] = True
            score += 0.10

        # 4. Set blocker: we hold a card that matches a board card (blocks their sets)
        for r in my_ranks:
            if r in board_ranks:
                self.blockers_info['blocks_sets'] = True
                score += 0.15
                break

        self.blockers_info['blocker_score'] = min(1.0, score)

    def _narrow_opponent_range(self, t, h):
        """Estimate opponent hand categories based on their betting line."""
        self.opponent_range_estimate = {
            'likely_hands': [],        # e.g. ['overpair', 'top_pair', 'flush_draw']
            'estimated_equity': 0.5,   # Our estimate of opponent's equity
            'range_narrowness': 0.5,   # 0=wide, 1=very narrow
            'bluff_probability': 0.3,  # Probability they're bluffing
        }

        opp_strength = self._estimate_opponent_range_strength(t, h) if hasattr(self, '_estimate_opponent_range_strength') else 0.5

        likely = []
        estimated_opp_eq = 0.5
        narrowness = 0.3
        bluff_prob = 0.3

        # Preflop raiser from early position -> narrow strong range
        if not np.isnan(getattr(t, 'first_raiser_utg', np.nan)):
            raiser_utg = t.first_raiser_utg
            if raiser_utg <= 1:  # UTG/UTG+1
                likely.extend(['overpair', 'big_ace'])
                estimated_opp_eq = 0.65
                narrowness = 0.7
                bluff_prob = 0.10
            elif raiser_utg <= 3:  # MP/CO
                likely.extend(['overpair', 'top_pair', 'big_ace', 'suited_connectors'])
                estimated_opp_eq = 0.55
                narrowness = 0.5
                bluff_prob = 0.20
            else:  # BTN/SB
                likely.extend(['wide_range', 'any_pair', 'suited_cards'])
                estimated_opp_eq = 0.45
                narrowness = 0.3
                bluff_prob = 0.35

        # 3-bet -> very strong
        if not np.isnan(getattr(t, 'second_raiser_utg', np.nan)):
            likely = ['premium_pair', 'big_ace']  # Narrow to very strong
            estimated_opp_eq = 0.70
            narrowness = 0.8
            bluff_prob = 0.10

        # Postflop actions narrow further
        if t.gameStage != 'PreFlop':
            if not t.checkButton and t.minCall > 0:
                # Opponent bet into us
                call_to_pot = t.minCall / max(getattr(t, 'totalPotValue', 1), 0.01)

                if call_to_pot > 0.75:
                    # Overbet -> polarized (very strong or bluff)
                    likely = ['monster', 'bluff']
                    bluff_prob = 0.35
                    narrowness = 0.9
                elif call_to_pot > 0.5:
                    # Big bet -> strong value or semi-bluff
                    likely = ['overpair', 'top_pair', 'two_pair', 'flush_draw']
                    bluff_prob = 0.20
                    narrowness = 0.7
                else:
                    # Small bet -> wide range, possible probe
                    likely = ['middle_pair', 'draw', 'weak_top_pair', 'bluff']
                    bluff_prob = 0.35
                    narrowness = 0.4

            # Multi-street aggression = stronger
            if getattr(t, 'other_player_has_initiative', False):
                if t.gameStage == 'Turn':
                    bluff_prob *= 0.7  # Fewer bluffs on turn
                    narrowness = min(narrowness + 0.1, 1.0)
                elif t.gameStage == 'River':
                    bluff_prob *= 0.5  # Even fewer on river
                    narrowness = min(narrowness + 0.2, 1.0)

        # Adjust based on opponent profile (if available)
        opp_profile = getattr(self, '_opp_profile', None)
        if opp_profile and opp_profile.get('hands', 0) >= 10:
            ptype = opp_profile.get('type', 'unknown')
            if ptype == 'nit':
                bluff_prob *= 0.5  # Nits rarely bluff
                narrowness = min(narrowness + 0.15, 1.0)
            elif ptype == 'fish_passive':
                bluff_prob *= 0.6  # Passive fish rarely bluff
            elif ptype == 'maniac':
                bluff_prob *= 1.5  # Maniacs bluff a lot
                bluff_prob = min(bluff_prob, 0.60)
            elif ptype == 'lag':
                bluff_prob *= 1.3
                bluff_prob = min(bluff_prob, 0.50)

        self.opponent_range_estimate = {
            'likely_hands': likely,
            'estimated_equity': estimated_opp_eq,
            'range_narrowness': narrowness,
            'bluff_probability': bluff_prob,
        }

        # ── Bayesian range tracking (eval7-based, beyond-GTO) ──
        # Only activates when the spot is worth analyzing:
        # deep stacks, significant pots, multiple actions observed.
        board = getattr(t, 'cardsOnTable', None) or []
        cards = getattr(t, 'mycards', None) or []
        if len(board) >= 3 and len(cards) == 2 and t.gameStage != 'PreFlop':
            try:
                from gamble.decisionmaker.range_equity import (
                    get_bayesian_tracker, log_hand_analysis,
                    should_use_bayesian,
                )

                # Check if this spot is worth Bayesian analysis
                _bb = t.bigBlind if t.bigBlind > 0 else 1.0
                _pot_bb = max(getattr(t, 'totalPotValue', 0) or 0, 0.01) / _bb
                _n_actions = len(getattr(self, '_bayesian_villain_range', {}).get('history', []))
                _opp_hands = 0
                _opp = getattr(self, '_opp_profile', None)
                if _opp:
                    _opp_hands = _opp.get('hands', 0)
                street_map = {'Flop': 'flop', 'Turn': 'turn', 'River': 'river'}
                _street_name = street_map.get(t.gameStage, 'flop')

                activation = should_use_bayesian(
                    hero_stack_bb=self.hero_stack_bb,
                    pot_bb=_pot_bb,
                    street=_street_name,
                    num_villain_actions=_n_actions,
                    has_check_button=bool(t.checkButton),
                    hero_equity=t.equity,
                    opponent_hands_seen=_opp_hands,
                )

                if not activation['use']:
                    log.debug(f"BAYESIAN SKIP: {activation['reason']}")
                    return  # Not worth analyzing this spot

                log.debug(f"BAYESIAN ACTIVE: {activation['reason']}")
                tracker = get_bayesian_tracker()

                # Create or reuse villain range from previous street
                v_range = getattr(self, '_bayesian_villain_range', None)
                if v_range is None:
                    # First postflop street: create from preflop action
                    _raiser_utg = getattr(t, 'first_raiser_utg', float('nan'))
                    ptype = 'unknown'
                    _opp = getattr(self, '_opp_profile', None)
                    if _opp and _opp.get('hands', 0) >= 10:
                        ptype = _opp.get('type', 'unknown')
                    _pos_map = {0: 'UTG', 1: 'MP', 2: 'CO', 3: 'BTN', 4: 'SB', 5: 'BB'}
                    v_pos = _pos_map.get(int(_raiser_utg), 'CO') if not np.isnan(_raiser_utg) else 'CO'
                    pf_action = '3bet' if not np.isnan(getattr(t, 'second_raiser_utg', np.nan)) else 'open'

                    v_range = tracker.create_initial_range(
                        position=v_pos, preflop_action=pf_action,
                        player_type=ptype, hero_cards=cards, board=board,
                    )

                # Determine villain's action on this street
                if not t.checkButton and t.minCall > 0:
                    pot_val = max(getattr(t, 'totalPotValue', 1), 0.01)
                    v_bet_pct = t.minCall / pot_val
                    v_action = 'bet'
                elif getattr(t, 'other_player_has_initiative', False):
                    v_action = 'bet'
                    v_bet_pct = 0.50  # default
                else:
                    v_action = 'check'
                    v_bet_pct = 0.0

                street_map = {'Flop': 'flop', 'Turn': 'turn', 'River': 'river'}
                street = street_map.get(t.gameStage, 'flop')

                # Don't re-narrow if we already did this street
                _last_street = v_range.get('_last_narrowed_street', '')
                if _last_street != street:
                    v_range = tracker.narrow_range(
                        v_range, board, v_action, v_bet_pct, street,
                    )
                    v_range['_last_narrowed_street'] = street
                    self._bayesian_villain_range = v_range

                # Get analysis
                analysis = tracker.get_range_analysis(v_range, board, cards)
                if analysis and analysis.get('num_combos', 0) >= 5:
                    self._bayesian_analysis = analysis

                    # Override heuristic with Bayesian data
                    self.opponent_range_estimate['bluff_probability'] = analysis.get('bluff_pct', bluff_prob)
                    n_range = 1.0 - (analysis.get('num_combos', 100) / 300.0)
                    self.opponent_range_estimate['range_narrowness'] = max(0.0, min(1.0, n_range))
                    self.opponent_range_estimate['bayesian'] = True

                    # Get exploit recommendation
                    _hand_strength = 'medium'
                    if hasattr(self, '_classify_hand'):
                        _h_info = self._classify_hand(t)
                        _hand_strength = _h_info.get('strength', 'medium') if _h_info else 'medium'

                    hero_pos = getattr(t, '_gto_position', 'CO')
                    is_ip = hero_pos in ('BTN', 'CO')
                    _bb = t.bigBlind if t.bigBlind > 0 else 1.0

                    exploit = tracker.get_exploit_recommendation(
                        analysis,
                        hero_equity=t.equity,
                        hero_hand_strength=_hand_strength,
                        pot_bb=max(getattr(t, 'totalPotValue', 0) or 0, 0.01) / _bb,
                        stack_bb=self.hero_stack_bb,
                        street=street,
                        is_ip=is_ip,
                    )
                    self._bayesian_exploit = exploit

                    # Log hand analysis
                    log_hand_analysis(
                        hero_cards=cards, board_cards=board,
                        street=street, decision='pending',
                        equity=t.equity,
                        pot_bb=max(getattr(t, 'totalPotValue', 0) or 0, 0.01) / _bb,
                        call_bb=t.minCall / _bb if _bb > 0 else 0,
                        stack_bb=self.hero_stack_bb,
                        range_analysis=analysis,
                        exploit_rec=exploit,
                    )

                    # Hand prediction (river or when range is narrow)
                    if street == 'river' or analysis.get('num_combos', 999) < 50:
                        predictions = tracker.predict_hand(v_range, board, cards)
                        self._bayesian_predictions = predictions

            except Exception as e:
                log.debug(f"Bayesian range tracking failed: {e}")

    def make_decision(self, t, h, p, l):
        self.preflop_sheet_name = ''
        if t.equity >= float(p.selected_strategy['alwaysCallEquity']):
            log.info("Equity is above the always call threshold")
            self.finalCallLimit = max(t.myFunds, t.totalPotValue)

        # ICM: raise commit thresholds in tournaments
        _table_name = getattr(t, '_table_name', '')
        _is_tourney = any(kw in _table_name for kw in ('Spin', 'Gold', 'Tournament', 'SNG', 'MTT'))
        _commit_50_eq = 0.40 if _is_tourney else 0.35
        _commit_25_eq = 0.50 if _is_tourney else 0.45

        # Low-stack commit: use call-to-stack ratio instead of pot-vs-stack
        _call_to_stack = t.minCall / max(t.myFunds, 1.0)
        if _call_to_stack > 0.5 and t.equity >= _commit_50_eq:
            log.info(f"STACK COMMIT: call/stack={_call_to_stack:.0%}, equity={t.equity:.3f} >= {_commit_50_eq}, committing"
                     f"{' (ICM adjusted)' if _is_tourney else ''}")
            self.finalCallLimit = t.myFunds
        elif _call_to_stack > 0.25 and t.equity >= _commit_25_eq:
            log.info(f"STACK COMMIT: call/stack={_call_to_stack:.0%}, equity={t.equity:.3f} >= {_commit_25_eq}, committing"
                     f"{' (ICM adjusted)' if _is_tourney else ''}")
            self.finalCallLimit = t.myFunds
        elif t.myFunds > 0 and t.myFunds * int(p.selected_strategy['always_call_low_stack_multiplier']) < t.totalPotValue:
            if t.equity >= 0.35:
                log.info(f"Low funds commit: pot={t.totalPotValue} > stack*{p.selected_strategy['always_call_low_stack_multiplier']}, "
                         f"equity={t.equity:.3f} >= 0.35")
                self.finalCallLimit = t.myFunds
            else:
                log.info(f"Low funds but equity too low ({t.equity:.3f} < 0.35) to auto-call")

        # --- Narrow opponent range BEFORE decisions so it informs calling/betting ---
        self._narrow_opponent_range(t, h)

        # ── Push/Fold for short stacks (≤ 15 BB preflop) ────────────────────
        # DESPERATE STACK: under 2BB, shove ANY hand preflop — folding is
        # never correct when blinds will eat you next orbit anyway.
        if t.gameStage == GameStages.PreFlop.value and self.hero_stack_bb <= 2:
            log.info(f"DESPERATE SHOVE: {self.hero_stack_bb:.1f}BB — auto all-in with any hand")
            self.decision = DecisionTypes.bet4
            self.push_fold_shove = True
            return

        # Nash-equilibrium: at short stacks, poker is solved — shove or fold.
        # Covers: open-shove, call-vs-shove, reshove vs opener, shove over
        # limpers, and 4-bet shove (all with eval7 blocker math).
        if t.gameStage == GameStages.PreFlop.value and self.hero_stack_bb <= 15:
            _push_fold_done = False
            try:
                from gamble.decisionmaker.range_equity import (
                    lookup_push_fold, lookup_call_shove,
                    reshove_decision, shove_over_limpers_decision,
                    m_ratio as _m_ratio, wait_for_better_spot,
                )

                hero_pos = getattr(t, '_gto_position', 'CO')

                # Tournament urgency: M-ratio and zone info
                _m_info = _m_ratio(self.hero_stack_bb,
                                   getattr(t, 'playersAtTable', 6) or 6)
                log.info(f"TOURNAMENT: M={_m_info['m']}, zone={_m_info['zone']}, "
                         f"hands_left≈{_m_info['hands_left']:.0f}, "
                         f"urgency={_m_info['urgency']:.0%}")
                _raiser_utg_pf = getattr(t, 'first_raiser_utg', float('nan'))
                _has_raiser = not np.isnan(_raiser_utg_pf)
                _bb = t.bigBlind if t.bigBlind > 0 else 1.0
                _utg_to_pos_pf = {0: 'UTG', 1: 'MP', 2: 'CO', 3: 'BTN', 4: 'SB', 5: 'BB'}

                # Opponent type from profiler (if available)
                _opp_profile = getattr(self, '_opp_profile', None) or {}
                _opp_type = (_opp_profile.get('type', 'unknown')
                             if _opp_profile.get('hands', 0) >= 10 else 'unknown')

                # Pot and call amounts in BB
                pot_bb = max(getattr(t, 'totalPotValue', 0) or 0, 1.5) / _bb
                call_amt = float(getattr(t, 'currentCallValue', 0) or 0)
                call_bb = call_amt / _bb

                # SAFETY: If call > 1.5 BB preflop, someone raised — even if
                # first_raiser_utg wasn't detected (e.g. Battle Royale theme).
                # Without this, the code falls to "limpers" branch which
                # estimates absurd limper counts from inflated pots and shoves
                # trash hands (42o) over "dead money" that's actually a raise.
                if not _has_raiser and call_bb > 1.5:
                    _has_raiser = True
                    # Assume worst case: raise from CO (middle position)
                    _raiser_utg_pf = 2.0
                    log.info(f"RAISER INFERRED from call_bb={call_bb:.1f} "
                             f"(no first_raiser_utg detected)")

                if t.allInCallButton and _has_raiser:
                    # CASE 1: FACING ALL-IN SHOVE → call or fold
                    shover_pos = _utg_to_pos_pf.get(int(_raiser_utg_pf), 'CO')
                    cs = lookup_call_shove(t.mycards, shover_pos, call_bb, pot_bb)
                    if cs:
                        t.equity = cs['equity']
                        if cs['action'] == 'call':
                            self.decision = DecisionTypes.call
                        else:
                            self.decision = DecisionTypes.fold
                        log.info(f"CALL-SHOVE: {cs['action']} vs {shover_pos} shove "
                                 f"(eq={cs['equity']:.1%}, pot_odds={cs['pot_odds']:.1%}, "
                                 f"EV={cs['ev']:+.2f}BB, vs {cs['range_size']} combos)")
                        _push_fold_done = True

                elif _has_raiser and not t.allInCallButton:
                    # CASE 2: FACING A RAISE (not all-in) → reshove or fold
                    # Covers both 3-bet shove (vs opener) and 4-bet shove (vs 3-bettor).
                    opener_pos = _utg_to_pos_pf.get(int(_raiser_utg_pf), 'CO')
                    rs = reshove_decision(
                        hero_cards=t.mycards,
                        hero_stack_bb=self.hero_stack_bb,
                        hero_position=hero_pos,
                        opener_position=opener_pos,
                        raise_size_bb=call_bb,
                        pot_bb=pot_bb,
                        player_type=_opp_type,
                    )
                    if rs:
                        if rs['action'] == 'shove':
                            self.decision = DecisionTypes.bet4
                            self.push_fold_shove = True
                        else:
                            self.decision = DecisionTypes.fold
                        t.equity = rs.get('equity_when_called', t.equity)
                        log.info(f"RESHOVE: {rs['action'].upper()} vs {opener_pos} raise "
                                 f"(FE={rs['fold_equity']:.0%}, eq={rs['equity_when_called']:.0%}, "
                                 f"EV={rs['ev']:+.2f}BB)")
                        _push_fold_done = True

                elif not _has_raiser and not t.allInCallButton:
                    # No raiser detected — either folded to us or limpers ahead
                    # Estimate limpers: normal pot = 1.5 BB, each limper adds ~1 BB
                    # Cap at (players_at_table - 1) to avoid absurd estimates
                    _max_limpers = max((getattr(t, 'playersAtTable', 6) or 6) - 1, 1)
                    _num_limpers = min(max(0, round(pot_bb - 1.5)), _max_limpers)

                    if _num_limpers > 0:
                        # CASE 3: LIMPERS → shove over dead money or check (BB)
                        sol = shove_over_limpers_decision(
                            hero_cards=t.mycards,
                            hero_stack_bb=self.hero_stack_bb,
                            hero_position=hero_pos,
                            num_limpers=_num_limpers,
                            pot_bb=pot_bb,
                            player_type=_opp_type,
                        )
                        if sol and sol['action'] == 'shove':
                            self.decision = DecisionTypes.bet4
                            self.push_fold_shove = True
                            t.equity = sol.get('equity_when_called', t.equity)
                            log.info(f"SHOVE OVER {_num_limpers} LIMPER(S): "
                                     f"(FE={sol['fold_equity']:.0%}, "
                                     f"eq={sol['equity_when_called']:.0%}, "
                                     f"EV={sol['ev']:+.2f}BB)")
                            _push_fold_done = True
                        elif sol and hero_pos != 'BB':
                            # Not BB and shove is -EV → fold
                            self.decision = DecisionTypes.fold
                            log.info(f"FOLD vs {_num_limpers} limper(s) "
                                     f"(shove EV={sol['ev']:+.2f}BB)")
                            _push_fold_done = True
                        # BB with limpers and -EV shove → fall through to check

                    elif hero_pos != 'BB':
                        # CASE 4: FOLDED TO HERO → open-shove or fold
                        pf = lookup_push_fold(t.mycards, hero_pos, self.hero_stack_bb)
                        if pf:
                            if pf['action'] == 'shove':
                                self.decision = DecisionTypes.bet4
                                self.push_fold_shove = True
                            else:
                                self.decision = DecisionTypes.fold
                            log.info(f"PUSH/FOLD: {pf['hand']} {pf['position']} "
                                     f"{pf['stack']}BB → {pf['action'].upper()} "
                                     f"(range: {pf['range_size']}/169)")
                            _push_fold_done = True
            except Exception as e:
                log.debug(f"Push/fold check failed: {e}")

            if _push_fold_done:
                # Log "wait for better spot" analysis for marginal decisions
                try:
                    if self.decision == DecisionTypes.fold and t.mycards:
                        _wait = wait_for_better_spot(
                            t.mycards, self.hero_stack_bb, hero_pos,
                            num_players=getattr(t, 'playersAtTable', 6) or 6,
                            current_shove_ev=0.0)
                        log.info(f"WAIT ANALYSIS: M={_wait['m_ratio']}, "
                                 f"premium_in≈{_wait['expected_hands_to_premium']:.0f}h, "
                                 f"blind_cost={_wait['blind_cost_waiting']:.1f}BB, "
                                 f"hands_to_critical={_wait['hands_to_critical']}")
                except Exception:
                    pass

                self.admin(t, p, h)
                self.decision = self.decision.value
                self._analyze_blockers(t)
                self._compute_decision_ev(t, p, h)
                return

        if p.selected_strategy['preflop_override'] and t.gameStage == GameStages.PreFlop.value:
            self.preflop_table_analyser(t, h, p)
            log.info('Preflop table is used for this decision')
        else:
            if t.gameStage == GameStages.PreFlop.value:
                log.info('Make preflop decision based on equity, not using preflop table')

            self.calling(t, p, h)
            self.betting(t, p, h)
            if t.checkButton:
                self.check_deception(t, p, h)

            # Check-raise: when facing a bet with a strong hand or draw
            self.check_raise(t, p, h)

            # Facing a raise: opponent raised our bet
            self.facing_raise(t, p, h)

            # River thin value: extract value with medium+ hands
            self.river_value_bet(t, p, h)

            if not t.allInCallButton \
                    and t.equity >= float(p.selected_strategy['secondRiverBetPotMinEquity']) \
                    and t.gameStage == GameStages.River.value \
                    and h.histGameStage == GameStages.River.value:
                self.decision = DecisionTypes.bet4
                # self.bully(t,p,h,logger)

        self.admin(t, p, h)
        self.bluff(t, p, h)

        # SAFETY: Cannot check when facing a bet. If decision is check but
        # there's a call amount, the click mapper falls back to 'call' which
        # would call with terrible equity. Override to fold instead.
        call_val = getattr(t, 'minCall', 0) or getattr(t, 'currentCallValue', 0) or 0
        if self.decision == DecisionTypes.check and float(call_val) > 0 and not t.checkButton:
            log.info(f"SAFETY: Check→Fold (can't check when facing call={call_val})")
            self.decision = DecisionTypes.fold

        self.decision = self.decision.value

        # Fix 7: Hand History Writing (Enables Feedback Loop)
        try:
            import datetime
            import json
            from gamble.core.constants import get_dir
            history_file = os.path.join(get_dir('learning'), 'hand_history.jsonl')
            opp = self._get_opp()
            hand_data = {
                'timestamp': datetime.datetime.utcnow().isoformat(),
                'street': t.gameStage,
                'cards': t.mycards,
                'board': t.cardsOnTable,
                'equity': round(float(t.equity), 3),
                'decision': self.decision,
                'pot_bb': round(float(t.totalPotValue) / t.bigBlind, 1) if t.bigBlind > 0 else 0,
                'call_bb': round(float(t.minCall) / t.bigBlind, 1) if t.bigBlind > 0 else 0,
                'spr': round(float(self.spr), 1),
                'opponent_type': opp.get('type', 'unknown') if opp else 'unknown',
                'table': getattr(t, '_table_name', 'unknown')
            }
            with open(history_file, 'a') as f:
                f.write(json.dumps(hand_data) + '\n')
        except Exception as e:
            log.debug(f"Hand history write failed: {e}")

        # --- Analysis (computed after decision for logging) ---
        self._analyze_blockers(t)
        self._compute_decision_ev(t, p, h)
