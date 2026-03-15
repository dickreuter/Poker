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
from sys_core.decisionmaker.base import DecisionBase
from sys_core.tools.helper import GameStages, DecisionTypes
from sys_core.decisionmaker.montecarlo_python import MonteCarlo, run_montecarlo_wrapper
from sys_core.decisionmaker.range_equity import (
    compute_bet_size_bb, geometric_bet_fraction,
    preflop_raise_size_bb, lookup_preflop_equity,
    blocker_adjustment, compute_range_fold_equity,
    compute_villain_bet_frequency, compute_check_ev_game_tree,
)
from .outs_calculator import Outs_Calculator

log = logging.getLogger(__name__)

# ─── Premium hands: tiered for safety checks and GTO fallbacks ────────────────
# TIER1: NEVER fold preflop under any circumstances (safety override).
PREMIUM_HANDS_TIER1 = {'AA', 'KK', 'QQ', 'JJ', 'AKS', 'AKO'}
# TIER2: Don't fold to a single raise, but can fold under extreme ICM pressure
# (e.g., 4-bet all-in on tournament bubble).
PREMIUM_HANDS_TIER2 = {'TT', '99', 'AQS', 'AQO', 'AJS', 'KQS'}
# Combined: used where both tiers apply (cash games, standard open ranges).
PREMIUM_HANDS = PREMIUM_HANDS_TIER1 | PREMIUM_HANDS_TIER2

# --- Load strategy adjustments from feedback loop ---
_strategy_adj = None

def _get_adj():
    """Lazy-load strategy adjustments (cached)."""
    global _strategy_adj
    if _strategy_adj is None:
        try:
            from sys_core.tools.strategy_adjuster import load_adjustments
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

# 4-bet ranges (facing a 3-bet)
GTO_4BET = {
    'value': {'AA', 'KK', 'QQ', 'AKS'},          # Always 4-bet
    'mixed_value': {'JJ'},                          # 4-bet ~60% (rest call)
    'bluff': {'A5S'},                               # 4-bet ~70% (rest fold)
    'call_4bet': {'JJ', 'TT', 'AKO', 'AQS'},      # Call the 3-bet (too strong to fold)
}

# Facing a 4-bet (what to do with our 3-bet range)
FACING_4BET = {
    'shove': {'AA', 'KK'},                          # 5-bet shove
    'call': {'QQ', 'JJ', 'AKS', 'AKO'},            # Call the 4-bet
    # Everything else folds (all bluff 3-bets: A5s, A4s, 76s, etc.)
}

# C-bet strategy by board category (for preflop raiser, heads-up, IP)
CBET_BOARD_STRATEGY = {
    'paired_high': {    # AA5, KK3, AK8 paired
        'cbet_freq': 0.90, 'cbet_size': 0.30,
    },
    'dry_high': {       # A72r, K83r, AJ2r
        'cbet_freq': 0.75, 'cbet_size': 0.33,
    },
    'two_tone_high': {  # As8h3h, Kd7s4s
        'cbet_freq': 0.65, 'cbet_size': 0.40,
    },
    'paired_low': {     # K88, A55, Q77
        'cbet_freq': 0.60, 'cbet_size': 0.55,
    },
    'dry_low': {        # 862r, 743r, 952r
        'cbet_freq': 0.50, 'cbet_size': 0.55,
    },
    'two_tone_connected': {  # JsTh8c, Qh9s8h
        'cbet_freq': 0.45, 'cbet_size': 0.55,
    },
    'wet': {            # JT9ss, QJ8hh
        'cbet_freq': 0.35, 'cbet_size': 0.66,
    },
    'monotone': {       # Jh8h3h, Ks9s4s
        'cbet_freq': 0.27, 'cbet_size': 0.33,
    },
}

# Multiway pot adjustments (keyed by number of active players)
MULTIWAY_ADJUSTMENTS = {
    'cbet_freq_multiplier': {
        2: 1.0,     # Heads-up: normal
        3: 0.55,    # 3-way: cut c-bet freq nearly in half
        4: 0.35,    # 4-way: very selective
        5: 0.20,    # 5-way: only bet the nuts
    },
    'equity_bonus_required': {
        2: 0.0,     # Heads-up: no extra equity needed
        3: 0.10,    # 3-way: +10% equity to bet
        4: 0.15,    # 4-way: +15%
        5: 0.20,    # 5-way: +20%
    },
}


def _normalize_hand(crd1: str, crd2: str) -> str:
    """Normalize hand like 'AKS'/'AKO'/'AA' from two card short notations.

    Input: two strings from MonteCarlo.get_two_short_notation(), e.g. 'AKS', 'KAS'
    Returns the canonical form (higher card first).
    """
    if not crd1 or not crd2 or len(crd1) < 2 or len(crd2) < 2:
        log.warning(f"_normalize_hand: invalid cards crd1={crd1!r} crd2={crd2!r}")
        return ''
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
    if not hand:
        log.warning(f"Hand normalization failed for {crd1!r}/{crd2!r}, defaulting to fold")
        return 'fold'
    pos = position.upper() if position else 'UNKNOWN'

    log.info(f"GTO ANALYSIS: hand={hand} pos={pos} raiser={has_raiser} "
             f"call={call_amount:.1f} stack={hero_stack:.1f} rpos={raiser_position}")

    # ─── PREMIUM SHIELD ──────────────────────────────────────────────────────
    # Guaranteed never to fold these hands preflop to a single raise.
    # If not in a 3-bet range, always call.
    is_premium = hand in PREMIUM_HANDS

    # BB with check option (unraised pot / limped pot)
    if has_check and pos == 'BB':
        bb_raise_range = GTO_OPEN.get('BTN', set())
        if hand in bb_raise_range:
            log.debug("BB unraised: raising wide for isolation")
            return 'raise'
        return 'check'

    # Facing a raise
    if has_raiser and call_amount > 0:
        # ─── 4-BET / FACING 3-BET LOGIC ────────────────────────────────────
        # Detect facing a 3-bet: call_amount > 5BB typically means 3-bet
        # (standard open is 2.5BB, 3-bet is ~7-10BB)
        call_to_stack = call_amount / max(hero_stack, 1.0)
        is_facing_3bet = call_amount > 5.0

        if is_facing_3bet:
            # Facing a 3-bet: use 4-bet ranges
            if hand in GTO_4BET['value']:
                log.info(f"GTO 4-BET VALUE: {hand} (always 4-bet)")
                return 'raise'
            if hand in GTO_4BET.get('mixed_value', set()):
                if random.random() < 0.60:
                    log.info(f"GTO 4-BET MIXED: {hand} (60% 4-bet)")
                    return 'raise'
                else:
                    log.info(f"GTO 4-BET MIXED: {hand} (40% flat)")
                    return 'call'
            if hand in GTO_4BET.get('bluff', set()):
                if random.random() < 0.70:
                    log.info(f"GTO 4-BET BLUFF: {hand} (70% 4-bet)")
                    return 'raise'
                else:
                    return 'fold'
            if hand in GTO_4BET.get('call_4bet', set()):
                log.info(f"GTO CALL 3-BET: {hand}")
                return 'call'
            # Everything else folds to 3-bet
            if hand in PREMIUM_HANDS_TIER1:
                log.info(f"PREMIUM SHIELD vs 3-bet: calling with {hand}")
                return 'call'
            log.info(f"FOLD vs 3-BET: {hand} not in 4-bet/call range")
            return 'fold'

        # ─── FACING 4-BET LOGIC ────────────────────────────────────────────
        # Detect facing a 4-bet: call_amount > 15BB
        is_facing_4bet = call_amount > 15.0
        if is_facing_4bet:
            if hand in FACING_4BET['shove']:
                log.info(f"5-BET SHOVE: {hand}")
                return 'raise'
            if hand in FACING_4BET['call']:
                log.info(f"CALL 4-BET: {hand}")
                return 'call'
            if hand in PREMIUM_HANDS_TIER1:
                log.info(f"PREMIUM SHIELD vs 4-bet: calling with {hand}")
                return 'call'
            log.info(f"FOLD vs 4-BET: {hand}")
            return 'fold'

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
                
                # Determine which premium set to use: in tournaments under
                # high pressure, only TIER1 is exempt from tightening.
                _is_tourney_bb = False  # Standalone function, no table context
                _premium_gate = PREMIUM_HANDS_TIER1 if _is_tourney_bb else PREMIUM_HANDS

                if call_to_stack > 0.45 and hand not in GTO_3BET.get('vs_BTN', set()):
                    log.debug(f"BB Defense: folding {hand} vs massive {call_to_stack:.0%} stack raise")
                    return 'fold'

                # Tiered defense vs smaller raises
                if call_to_stack > 0.15: # Large raise (>4x in Spin, >15x in Cash)
                    # Tighten to only top 50% of defend range + premiums
                    if random.random() < 0.50 and hand not in _premium_gate:
                        log.debug(f"BB Defense: tightening vs large raise ({call_to_stack:.2f})")
                        return 'fold'
                elif call_to_stack > 0.10: # Medium raise (3x-4x in Spin)
                    # Tighten ~30%
                    if random.random() < 0.30 and hand not in _premium_gate:
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
        
        # GGSystem/Rush BB display mode: all values are already in BB units.
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
                from sys_core.decisionmaker.range_equity import get_range_equity
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

                # Use context-aware range when hand context available
                _hand_ctx = getattr(self, '_hand_context', None)
                _n_opp = getattr(t, 'other_active_players', 1)
                _bet_pct = (t.minCall / max(t.totalPotValue, 0.01)
                            if hasattr(t, 'minCall') and t.totalPotValue > 0 else 0.0)

                if _hand_ctx is not None and street != 'preflop':
                    v_range = re.estimate_villain_range_with_context(
                        hand_context=_hand_ctx,
                        street=street,
                        current_action=v_action,
                        bet_size_pct=_bet_pct,
                        player_type=ptype,
                        num_opponents=_n_opp,
                    )
                else:
                    v_range = re.estimate_villain_range(
                        position=v_position,
                        action=v_action,
                        player_type=ptype,
                        street=street,
                        bet_size_pct=_bet_pct,
                    )

                board = getattr(t, 'cardsOnTable', []) or []

                # Use pre-computed table for preflop (instant), live calc for postflop
                range_eq = None
                if t.gameStage == 'PreFlop':
                    from sys_core.decisionmaker.range_equity import lookup_preflop_equity
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

        # --- Hand context: full action history for context-aware ranges ---
        self._hand_context = None  # Set by runner: HandContext from engine.py

        # --- Bayesian range tracking (beyond-GTO exploitative engine) ---
        if not hasattr(self, '_bayesian_villain_range'):
            self._bayesian_villain_range = None
        self._bayesian_analysis = None
        self._bayesian_exploit = None
        self._bayesian_predictions = None

        # --- Bet/call limits ---
        # Postflop: the EV engine (compute_ev_decision) sets these dynamically.
        # Preflop: preflop_table_analyser sets finalBetLimit for raise sizing.
        # finalCallLimit is only used as an always-call override (set in make_decision).
        self.finalCallLimit = 0
        self.finalBetLimit = 0
        self.optimal_bet_bb = 0
        self.push_fold_shove = False

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

            # SAFETY: equity floors prevent misread cards from causing raises.
            # When FACING a raise (call_amount > 0), use much tighter floors because
            # the raiser has a strong range (top 12-25%) and our equity vs random
            # over-estimates our actual equity vs that range.
            # PREMIUM EXEMPTION: Never fold premium hands due to safety floors.
            hand_norm = _normalize_hand(crd1, crd2)
            is_premium_hand = hand_norm in PREMIUM_HANDS
            _facing_raise = has_raiser and float(call_amt) > 0

            if self.decision in (DecisionTypes.bet3, DecisionTypes.bet4):
                # 3-betting/raising requires higher equity when facing action
                if _facing_raise:
                    _raise_floor = 0.40  # Need 40%+ equity to 3-bet vs a raiser
                else:
                    _raise_floor = 0.22  # Opening: 22% is fine (wide range)
                if t.equity < _raise_floor and not is_premium_hand:
                    log.info(f'Preflop raise overridden to FOLD: equity {t.equity:.3f} '
                             f'< {_raise_floor} (facing_raise={_facing_raise})')
                    self.decision = DecisionTypes.fold
            elif self.decision == DecisionTypes.call:
                _ca = float(call_amt) if call_amt else 0
                pot = max(getattr(t, 'totalPotValue', 0) or 0, 1.5)
                if _ca > 0:
                    pot_odds = _ca / (pot + _ca)
                    # When facing a raise, need 35%+ equity to call (raiser has
                    # narrow range, our vs-random equity overstates real equity)
                    if _facing_raise:
                        _call_floor = 0.35  # Tighter floor vs raiser's range
                    else:
                        _call_floor = 0.28  # Limped pot / unraised
                    if t.equity < _call_floor and not is_premium_hand:
                        log.info(f'Preflop call overridden to FOLD: equity {t.equity:.3f} '
                                 f'< {_call_floor} (facing_raise={_facing_raise}, '
                                 f'pot_odds={pot_odds:.3f})')
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
            hand_norm = _normalize_hand(crd1, crd2)
            is_premium_hand = hand_norm in PREMIUM_HANDS

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

        # --- MISREAD SAFETY NET ---
        # If we're about to fold preflop but equity is suspiciously high (>0.55),
        # the hand is likely misread (e.g. JJ read as 3J). A genuine trash hand
        # like 3J offsuit gets ~0.38 equity, but JJ gets ~0.77. If equity says
        # the hand is strong, override fold → call to avoid folding hidden premiums.
        if self.decision == DecisionTypes.fold and t.gameStage == 'PreFlop':
            if hasattr(t, 'equity') and t.equity > 0.55:
                log.warning(f"MISREAD SAFETY NET: Folding preflop but equity={t.equity:.3f} > 0.55 "
                            f"— hand {crd1}/{crd2} is likely misread (possible hidden pair). "
                            f"Overriding FOLD → CALL")
                self.decision = DecisionTypes.call

            t.currentBluff = 0

    # ══════════════════════════════════════════════════════════════════════
    # EV-BASED DECISION ENGINE (March 2026)
    #
    # Replaces threshold cascades with direct EV comparison:
    #   EV(fold) = 0
    #   EV(call) = equity * (pot + call) - (1 - equity) * call
    #   EV(raise) = fold_equity * pot + (1-FE) * [eq_called * new_pot - raise]
    #
    # Picks the action with the highest EV.
    # ══════════════════════════════════════════════════════════════════════

    def compute_ev_decision(self, t, h, p):
        """Compute EV for fold/call/raise and return the best action.

        Returns:
            dict with keys:
                'action': DecisionTypes enum value
                'ev_fold': float (always 0)
                'ev_call': float
                'ev_raise': float or None
                'equity': float (equity used)
                'villain_range': str
                'fold_equity': float
                'spr': float
                'reasoning': str
            Returns None if EV computation is not possible (missing data).
        """
        import math as _math

        # ── Gather game state ──────────────────────────────────────────────
        pot = max(getattr(t, 'totalPotValue', 0) or 0, 0.01)
        call_amount = max(getattr(t, 'minCall', 0) or 0, 0)
        my_stack = max(getattr(t, 'myFunds', 0) or 0, 0)
        bb = t.bigBlind if t.bigBlind > 0 else 1.0
        equity = t.equity if hasattr(t, 'equity') else 0.5
        board = getattr(t, 'cardsOnTable', []) or []
        mycards = getattr(t, 'mycards', None)

        if not mycards or len(mycards) != 2:
            return None

        street_map = {'PreFlop': 'preflop', 'Flop': 'flop', 'Turn': 'turn', 'River': 'river'}
        street = street_map.get(t.gameStage, 'flop')

        spr = self.spr
        hero_pos = getattr(t, '_gto_position', 'CO')

        # ── CFR SOLVER: short stacks + postflop ──────────────────────────
        # Route to the unified solver for short stacks (push/fold Nash)
        # and postflop decisions (CFR with mixed strategies).
        # Falls through to the old EV system for deep preflop and as fallback.
        eff_bb = my_stack / bb if bb > 0 else 100
        try:
            from sys_core.decisionmaker.solver import get_solver
            _solver = get_solver()

            # Determine game type
            _game_type = 'cash'
            game_type_attr = getattr(t, 'game_type', '')
            _table_name = getattr(t, 'tableName', '') or ''
            if ('spin' in str(game_type_attr).lower()
                    or 'spin' in _table_name.lower()):
                _game_type = 'spin'
            elif 'tournament' in str(game_type_attr).lower():
                _game_type = 'tournament'

            # ICM payouts (if available)
            _payouts = getattr(t, '_icm_payouts', None)
            _all_stacks = getattr(t, '_all_stacks', None)

            # Hand context for IP detection
            hand_ctx = getattr(self, '_hand_context', None)
            _hero_ip = hand_ctx.hero_is_ip if hand_ctx else (hero_pos in ('BTN', 'CO'))

            # Use solver for preflop decisions:
            # - Spin & Go: ALL preflop (stacks are always short/medium)
            # - Cash/tournament: ≤20BB (push/fold territory)
            _use_solver_preflop = (
                (eff_bb <= 20) or
                (_game_type == 'spin') or
                (_game_type == 'tournament' and eff_bb <= 30) or
                (call_amount > 0 and call_amount >= my_stack * 0.3)  # Facing big bet/shove
            )
            if _use_solver_preflop and street == 'preflop':
                sr = _solver.decide(
                    hero_cards=mycards, board=board, pot=pot, stack=my_stack,
                    call_amount=call_amount, bb=bb, position=hero_pos,
                    hero_is_ip=_hero_ip, game_type=_game_type,
                    payouts=_payouts, all_stacks=_all_stacks,
                )
                if sr.solver_layer > 0:
                    # Map solver action to DecisionTypes
                    _action_map = {
                        'allin': DecisionTypes.bet4,
                        'raise': DecisionTypes.bet3,
                        'call': DecisionTypes.call,
                        'check': DecisionTypes.check,
                        'fold': DecisionTypes.fold,
                    }
                    best_action = _action_map.get(sr.action, DecisionTypes.fold)
                    if t.checkButton and best_action == DecisionTypes.fold:
                        best_action = DecisionTypes.check

                    log.info(f"SOLVER L{sr.solver_layer}: {sr.action} "
                             f"freq={sr.frequency:.0%} ({sr.solve_time_ms:.0f}ms) "
                             f"| {sr.reasoning}")

                    self._ev_decision_action = best_action
                    result = {
                        'action': best_action,
                        'ev_fold': 0.0, 'ev_call': 0.0, 'ev_raise': 0.0,
                        'equity': equity, 'villain_range': '',
                        'fold_equity': 0.0, 'spr': spr,
                        'reasoning': f'SOLVER L{sr.solver_layer}: {sr.reasoning}',
                        'solver_result': sr,
                    }
                    self._last_ev_result = result
                    return result

        except Exception as e:
            log.debug(f"Solver routing failed, falling through to EV system: {e}")

        # ── Estimate villain range ─────────────────────────────────────────
        opp = self._get_opp()
        ptype = opp.get('type', 'unknown') if opp else 'unknown'
        n_opponents = getattr(t, 'other_active_players', 1)

        # Determine villain action context
        if t.allInCallButton:
            v_action = 'all_in'
        elif call_amount > 0 and not t.checkButton:
            v_action = 'bet'
        elif street == 'preflop' and not _math.isnan(getattr(t, 'first_raiser_utg', float('nan'))):
            v_action = 'open'
        else:
            v_action = 'check'

        # Villain position estimate
        _utg_to_pos = {0: 'UTG', 1: 'MP', 2: 'CO', 3: 'BTN', 4: 'SB', 5: 'BB'}
        _raiser_utg = getattr(t, 'first_raiser_utg', float('nan'))
        if not _math.isnan(_raiser_utg):
            v_position = _utg_to_pos.get(int(_raiser_utg), 'CO')
        elif hero_pos in ('BB', 'SB'):
            v_position = 'BTN'
        else:
            v_position = 'CO'

        # Bet size as fraction of pot (for range narrowing)
        bet_size_pct = call_amount / pot if pot > 0 else 0.0

        # Use context-aware range estimation when hand context is available
        hand_ctx = getattr(self, '_hand_context', None)

        try:
            from sys_core.decisionmaker.range_equity import get_range_equity
            re = get_range_equity()

            if hand_ctx is not None and street != 'preflop':
                # Context-aware: uses full action history across streets
                v_range = re.estimate_villain_range_with_context(
                    hand_context=hand_ctx,
                    street=street,
                    current_action=v_action,
                    bet_size_pct=bet_size_pct,
                    player_type=ptype,
                    num_opponents=n_opponents,
                )
                log.info(f"EV RANGE (context-aware): street={street} "
                         f"pattern='{hand_ctx.villain_pattern}' "
                         f"aggro={hand_ctx.streets_of_aggression} "
                         f"cbet={hand_ctx.is_cbet_spot} "
                         f"multiway={hand_ctx.is_multiway}")
            else:
                # Fallback: single-action estimation
                # Pass raiser_position so calling ranges are position-aware
                _raiser_pos = ''
                if v_action == 'call' and hand_ctx and hand_ctx.hero_was_raiser:
                    _raiser_pos = hero_pos
                elif v_action != 'call' and hand_ctx:
                    _raiser_pos = hand_ctx.preflop_raiser_position or ''
                v_range = re.estimate_villain_range(
                    position=v_position, action=v_action,
                    player_type=ptype, street=street,
                    bet_size_pct=bet_size_pct,
                    raiser_position=_raiser_pos,
                )
        except Exception as e:
            log.debug(f"EV engine: range estimation failed: {e}")
            v_range = '22+, A2s+, K9s+, QTs+'

        # ── Compute equity vs villain range ────────────────────────────────
        # Use board-aware filtering for postflop (more accurate vs betting range)
        try:
            from sys_core.decisionmaker.range_equity import get_range_equity
            re = get_range_equity()
            if street != 'preflop' and len(board) >= 3:
                eq_val, eq_info = re.equity_vs_board_aware_range(
                    mycards, board, v_range,
                    street=street, action=v_action, player_type=ptype,
                )
                log.debug(f"EV EQUITY (board-aware): {eq_val:.1%} — {eq_info}")
            else:
                eq_val = re.equity_vs_range(mycards, board, v_range, iterations=10000)
                log.debug(f"EV EQUITY (range): {eq_val:.1%}")
            equity = eq_val
        except Exception as e:
            log.debug(f"EV engine: equity calc failed, using existing: {e}")
            # Fall back to whatever equity was already computed

        # ── EV(fold) ──────────────────────────────────────────────────────
        ev_fold = 0.0

        # ── EV(call) ──────────────────────────────────────────────────────
        if call_amount > 0:
            ev_call = equity * (pot + call_amount) - (1.0 - equity) * call_amount
        elif t.checkButton:
            # Free check: EV = equity * pot (we see more cards for free)
            ev_call = equity * pot
        else:
            ev_call = equity * pot

        # ── Implied odds adjustment for draws ─────────────────────────────
        # On flop/turn with draws, we can win more money on future streets
        implied_bonus = 0.0
        if street in ('flop', 'turn') and self.outs >= 4:
            # Estimate future winnings: deeper stacks = more implied odds
            remaining_stack = max(my_stack - call_amount, 0)
            # With 8+ outs (flush/OESD), expect to win ~1.5-2x call on future streets
            # With 4-7 outs (gutshot), expect ~0.5-1x call
            if self.outs >= 8:
                implied_mult = min(2.0, remaining_stack / max(call_amount, 1))
                implied_bonus = (self.outs / 46.0) * call_amount * min(implied_mult, 2.0)
            else:
                implied_mult = min(1.0, remaining_stack / max(call_amount, 1))
                implied_bonus = (self.outs / 46.0) * call_amount * min(implied_mult, 1.0)
            ev_call += implied_bonus
            log.debug(f"EV IMPLIED: +{implied_bonus:.2f} ({self.outs} outs)")

        # ── Fold equity estimation ────────────────────────────────────────
        # Primary: range-based fold equity (eval7 — computes from villain range × board)
        # Only when hero is the aggressor (betting into a check), NOT when raising
        # into villain's bet (villain already showed strength by betting).
        # Fallback: heuristic-based
        fold_equity = None
        _hero_is_aggressor = t.checkButton or (call_amount == 0)
        if (street != 'preflop' and len(board) >= 3 and mycards
                and len(mycards) == 2 and _hero_is_aggressor):
            try:
                _bet_frac_for_fe = 0.67  # Default bet size for fold equity calc
                fe_result = compute_range_fold_equity(
                    mycards, board, v_range, bet_fraction=_bet_frac_for_fe,
                )
                if fe_result and 'fold_equity' in fe_result:
                    fold_equity = fe_result['fold_equity']
                    log.info(f"EV FOLD_EQ (range-based): {fold_equity:.0%} "
                             f"({fe_result.get('folding_combos', 0)}/{fe_result.get('total_combos', 0)} combos fold)")
            except Exception as e:
                log.debug(f"Range fold equity failed, using heuristic: {e}")

        if fold_equity is None:
            fold_equity = self._estimate_fold_equity(t, h)

        # Refine with opponent cbet/fold-to-cbet stats if available
        if opp:
            ftcb = opp.get('fold_to_cbet', None)
            if ftcb is not None and opp.get('fold_to_cbet_n', 0) >= 5:
                # Blend tracked fold rate with estimated fold equity
                fold_equity = 0.5 * fold_equity + 0.5 * ftcb
                log.debug(f"EV FOLD_EQ refined: ftcb={ftcb:.0%} → blended={fold_equity:.0%}")

        # ── Blocker-based fold equity adjustment ─────────────────────────
        # Quantify how hero's cards affect fold equity (blocks nut flush, etc.)
        if street != 'preflop' and len(board) >= 3:
            try:
                fe_bonus, eq_bonus = blocker_adjustment(mycards, board, v_range)
                if abs(fe_bonus) > 0.01:
                    fold_equity = max(0.05, min(0.85, fold_equity + fe_bonus))
                    log.debug(f"EV BLOCKER: fold_eq {fe_bonus:+.2f} → {fold_equity:.0%}")
                if abs(eq_bonus) > 0.01:
                    equity = max(0.0, min(1.0, equity + eq_bonus))
                    log.debug(f"EV BLOCKER: equity {eq_bonus:+.2f} → {equity:.1%}")
            except Exception as e:
                log.debug(f"Blocker adjustment failed: {e}")

        # ── Multiway fold equity correction ──────────────────────────────
        # With N opponents, ALL must fold. FE_total = FE_per_player^N.
        n_opponents = max(n_opponents, 1)
        if n_opponents >= 2:
            fold_equity_hu = fold_equity  # Per-player FE
            fold_equity = fold_equity_hu ** n_opponents
            log.debug(f"EV FOLD_EQ multiway: {fold_equity_hu:.0%}^{n_opponents} = {fold_equity:.0%}")

        # ── Bluff eligibility gate ───────────────────────────────────────
        # Only blocks PURE bluffs (no equity, no draws). Semi-bluffs with
        # draws pass through — they have genuine equity and should bet.
        _can_bluff = True
        if street != 'preflop' and equity < 0.12 and self.outs < 4:
            # Pure bluff territory: <12% equity AND no draws
            is_cbet = (getattr(self, '_hand_context', None) is not None
                       and getattr(self._hand_context, 'hero_was_raiser', False)
                       and street == 'flop')
            # River with 0% equity: only bluff if FE covers the bet
            if street == 'river' and equity < 0.05:
                if fold_equity < 0.35:
                    _can_bluff = False
                    log.debug(f"BLUFF GATE: river eq={equity:.0%} FE={fold_equity:.0%} → no bluff")
            # Multiway pure bluff: almost never profitable
            elif n_opponents >= 2 and not is_cbet:
                _can_bluff = False
                log.debug(f"BLUFF GATE: multiway pure bluff eq={equity:.0%} outs={self.outs} → no bluff")

        # ── EV(raise) ─────────────────────────────────────────────────────
        # Determine raise size
        ev_raise = None
        raise_amount = 0.0
        bet_frac = 0.0
        can_raise = hasattr(t, 'raiseButton') and t.raiseButton or t.checkButton

        # Block pure bluffs with trash — if bluff gate says no AND no draws, disable raise.
        # Semi-bluffs with draws (outs >= 4) always allowed to bet.
        has_draw_for_gate = hasattr(self, 'outs') and self.outs >= 4
        if not _can_bluff and equity < 0.12 and not has_draw_for_gate:
            can_raise = False
            log.debug(f"BLUFF BLOCKED: eq={equity:.0%} outs={getattr(self,'outs',0)}, skipping raise")

        if can_raise:
            # Calculate optimal raise size
            streets_map = {'flop': 3, 'turn': 2, 'river': 1, 'preflop': 0}
            streets_left = streets_map.get(street, 1)

            if streets_left > 0:
                geo = geometric_bet_fraction(pot / bb, my_stack / bb, streets_left)
            else:
                geo = 0.66

            # Board wetness affects sizing
            wetness = self._board_wetness(board)
            if street == 'flop':
                if wetness < 0.3:
                    bet_frac = 0.33
                elif wetness > 0.7:
                    bet_frac = 0.75
                else:
                    bet_frac = 0.50
            elif street == 'turn':
                bet_frac = min(geo, 0.80)
            else:
                bet_frac = 0.75  # River: polarized

            # SPR-based commitment: low SPR = shove
            if spr < 1.5:
                bet_frac = 1.0  # Shove
            elif spr < 3.0:
                bet_frac = max(bet_frac, geo)

            raise_amount = bet_frac * pot
            raise_amount = min(raise_amount, my_stack)  # Can't bet more than stack

            if raise_amount > 0:
                # Equity when called: opponent folds weak hands, calling range
                # is stronger. But strong hands retain most equity vs callers.
                #
                # Scale discount by hand strength: strong hands barely lose
                # equity when called (trips vs pair = still 90%+), while
                # marginal hands lose a lot (A-high vs Kx = drops from 50% to 30%).
                if bet_frac <= 0.40:
                    base_discount = 0.80
                elif bet_frac <= 0.70:
                    base_discount = 0.72
                else:
                    base_discount = 0.62

                # Strong hands: lighter discount (we're happy to get called)
                # Draws: NO discount (equity comes from outs, not current strength)
                # Weak hands: heavier discount (callers crush us)
                has_draw = hasattr(self, 'outs') and self.outs >= 4
                if equity >= 0.70:
                    call_discount = max(base_discount, 0.88)  # Trips/overpairs retain equity
                elif equity >= 0.50:
                    call_discount = max(base_discount, 0.78)  # Strong top pair
                elif has_draw:
                    call_discount = max(base_discount, 0.90)  # Draws keep equity (outs don't change when called)
                else:
                    call_discount = base_discount  # Marginal hands

                # Adjust for opponent type
                if ptype == 'nit':
                    call_discount *= 0.85
                elif ptype in ('fish_passive', 'fish_aggro', 'maniac'):
                    call_discount = min(call_discount * 1.10, 0.95)

                eq_when_called = equity * call_discount

                # Total pot if called: pot + our raise + villain's call
                # Villain calls our raise_amount (they match our bet)
                if call_amount > 0:
                    # We're raising over their bet: total new pot = pot + raise + (raise - call_already_in)
                    # Simplified: pot already includes their bet, we add raise_amount
                    total_if_called = pot + raise_amount + raise_amount
                else:
                    # We're betting into them: they call our bet
                    total_if_called = pot + raise_amount + raise_amount

                # EV(raise) = FE * pot + (1-FE) * [eq_called * total_pot_called - raise_amount]
                ev_raise = (fold_equity * pot
                            + (1.0 - fold_equity) * (eq_when_called * total_if_called - raise_amount))

                log.debug(f"EV RAISE: FE={fold_equity:.0%} eq_called={eq_when_called:.0%} "
                          f"raise={raise_amount:.1f} total_if_called={total_if_called:.1f} → EV={ev_raise:.2f}")

        # ── SPR commitment override ───────────────────────────────────────
        # SPR < 3: with any decent equity, we're mathematically committed.
        # Don't fold when pot-committed regardless of EV calculation.
        spr_committed = False
        if spr < 3.0 and equity >= 0.30:
            spr_committed = True
        elif spr < 1.5 and equity >= 0.20:
            spr_committed = True

        # ── ICM adjustment for EV engine ────────────────────────────────
        # In tournaments, the value of chips is non-linear. Losing chips
        # hurts more than winning chips helps. Apply a "risk premium" that
        # penalizes EV(call) and EV(raise) proportionally to ICM pressure.
        icm_ev_adj = 0.0
        ev_icm_pressure = getattr(t, '_icm_pressure', 0.0) or 0.0
        if ev_icm_pressure > 0 and call_amount > 0:
            # Risk premium: penalize putting chips at risk
            # Higher ICM = bigger penalty for calling/raising
            icm_ev_adj = ev_icm_pressure * call_amount * 0.3
            ev_call -= icm_ev_adj
            if ev_raise is not None:
                ev_raise -= icm_ev_adj * 1.2  # Raising is even riskier
            log.debug(f"EV ICM ADJ: pressure={ev_icm_pressure:.2f} "
                      f"penalty={icm_ev_adj:.2f} on call/raise")

        # ── Pick best action ──────────────────────────────────────────────
        reasoning_parts = []
        reasoning_parts.append(f"eq={equity:.1%} pot={pot:.1f} call={call_amount:.1f} "
                               f"spr={spr:.1f} FE={fold_equity:.0%}")
        reasoning_parts.append(f"EV: fold=0, call={ev_call:.2f}")
        if ev_raise is not None:
            reasoning_parts.append(f"raise={ev_raise:.2f}")
        if icm_ev_adj > 0:
            reasoning_parts.append(f"ICM_adj=-{icm_ev_adj:.2f}")

        # Determine which action has highest EV
        best_ev = ev_fold
        best_action = DecisionTypes.fold

        if ev_call > best_ev:
            best_ev = ev_call
            best_action = DecisionTypes.call

        if ev_raise is not None and ev_raise > best_ev:
            best_ev = ev_raise
            # Map to bet sizing
            if raise_amount >= my_stack * 0.85:
                best_action = DecisionTypes.bet4  # All-in / pot
            elif bet_frac >= 0.60:
                best_action = DecisionTypes.bet3  # Half pot+
            elif bet_frac >= 0.30:
                best_action = DecisionTypes.bet2  # Small-medium
            else:
                best_action = DecisionTypes.bet1  # Min bet

        # SPR commitment: override fold with call if committed
        if best_action == DecisionTypes.fold and spr_committed:
            best_action = DecisionTypes.call
            best_ev = ev_call
            reasoning_parts.append(f"SPR_COMMIT: spr={spr:.1f} eq={equity:.1%}")

        # Check button: convert fold/call to check
        if t.checkButton:
            if best_action == DecisionTypes.fold:
                best_action = DecisionTypes.check
            elif best_action == DecisionTypes.call and call_amount <= 0:
                best_action = DecisionTypes.check

        reasoning = ' | '.join(reasoning_parts)

        result = {
            'action': best_action,
            'ev_fold': ev_fold,
            'ev_call': ev_call,
            'ev_raise': ev_raise,
            'equity': equity,
            'villain_range': v_range[:60],
            'fold_equity': fold_equity,
            'spr': spr,
            'raise_amount': raise_amount if ev_raise is not None else 0,
            'bet_fraction': bet_frac if ev_raise is not None else 0,
            'implied_bonus': implied_bonus,
            'reasoning': reasoning,
        }

        log.info(f"EV DECISION: {best_action.name} (EV={best_ev:+.2f}) — {reasoning}")

        # ── Multi-street planning (flop and turn only) ───────────────────
        # After computing single-street EV, run multi-street simulation.
        # If it disagrees with single-street, trust the multi-street planner.
        multi_street_info = None
        try:
            if street == 'flop' and can_raise and len(board) == 3:
                ms = self._plan_multi_street(
                    t, mycards, board, v_range, pot, my_stack, call_amount,
                    fold_equity=fold_equity, equity=equity, ptype=ptype,
                )
                if ms is not None:
                    multi_street_info = ms
                    result['multi_street'] = ms
                    ms_best = ms['best_action']

                    # If multi-street disagrees with single-street on bet vs check
                    if ms_best in ('bet', 'raise') and best_action in (
                            DecisionTypes.fold, DecisionTypes.check, DecisionTypes.call):
                        if ms['total_ev_bet'] > ms['total_ev_check'] + 0.5:
                            # Multi-street says bet is significantly better
                            if raise_amount > 0:
                                if raise_amount >= my_stack * 0.85:
                                    best_action = DecisionTypes.bet4
                                elif bet_frac >= 0.60:
                                    best_action = DecisionTypes.bet3
                                elif bet_frac >= 0.30:
                                    best_action = DecisionTypes.bet2
                                else:
                                    best_action = DecisionTypes.bet1
                                result['action'] = best_action
                                log.info(f"MULTI-STREET OVERRIDE: {ms_best} "
                                         f"(bet_ev={ms['total_ev_bet']:+.2f} > "
                                         f"check_ev={ms['total_ev_check']:+.2f})")

                    elif ms_best in ('check', 'fold') and best_action in (
                            DecisionTypes.bet1, DecisionTypes.bet2,
                            DecisionTypes.bet3, DecisionTypes.bet4):
                        if ms['total_ev_check'] > ms['total_ev_bet'] + 0.5:
                            best_action = DecisionTypes.check if t.checkButton else DecisionTypes.call
                            result['action'] = best_action
                            log.info(f"MULTI-STREET OVERRIDE: {ms_best} "
                                     f"(check_ev={ms['total_ev_check']:+.2f} > "
                                     f"bet_ev={ms['total_ev_bet']:+.2f})")

            elif street == 'turn' and can_raise and len(board) == 4:
                ms = self._plan_multi_street(
                    t, mycards, board, v_range, pot, my_stack, call_amount,
                    fold_equity=fold_equity, equity=equity, ptype=ptype,
                )
                if ms is not None:
                    multi_street_info = ms
                    result['multi_street'] = ms
                    ms_best = ms['best_action']

                    if ms_best in ('bet', 'raise') and best_action in (
                            DecisionTypes.fold, DecisionTypes.check, DecisionTypes.call):
                        if ms['total_ev_bet'] > ms['total_ev_check'] + 0.3:
                            if raise_amount > 0:
                                if raise_amount >= my_stack * 0.85:
                                    best_action = DecisionTypes.bet4
                                elif bet_frac >= 0.60:
                                    best_action = DecisionTypes.bet3
                                elif bet_frac >= 0.30:
                                    best_action = DecisionTypes.bet2
                                else:
                                    best_action = DecisionTypes.bet1
                                result['action'] = best_action
                                log.info(f"MULTI-STREET OVERRIDE (turn): {ms_best} "
                                         f"(bet_ev={ms['total_ev_bet']:+.2f})")

                    elif ms_best in ('check', 'fold') and best_action in (
                            DecisionTypes.bet1, DecisionTypes.bet2,
                            DecisionTypes.bet3, DecisionTypes.bet4):
                        if ms['total_ev_check'] > ms['total_ev_bet'] + 0.3:
                            best_action = DecisionTypes.check if t.checkButton else DecisionTypes.call
                            result['action'] = best_action
                            log.info(f"MULTI-STREET OVERRIDE (turn): {ms_best} "
                                     f"(check_ev={ms['total_ev_check']:+.2f})")

        except Exception as e:
            log.debug(f"Multi-street planning failed: {e}")

        if multi_street_info:
            log.info(f"MULTI-STREET PLAN: {multi_street_info['simulations']} runouts "
                     f"in {multi_street_info['time_ms']:.0f}ms | "
                     f"bet_ev={multi_street_info['total_ev_bet']:+.2f} "
                     f"check_ev={multi_street_info['total_ev_check']:+.2f} | "
                     f"improves {multi_street_info['improvement_rate']:.0%} of turns | "
                     f"plan={multi_street_info['best_action']}")

        # Store for EV gate — prevents legacy betting from overriding
        self._ev_decision_action = best_action

        # Store result on self so engine.py can access multi_street info
        self._last_ev_result = result

        return result

    # ══════════════════════════════════════════════════════════════════════
    # MULTI-STREET PLANNING ENGINE
    #
    # Simulates future runouts using eval7 to compute total expected value
    # across all remaining streets, replacing single-street EV evaluation
    # with full hand planning.
    # ══════════════════════════════════════════════════════════════════════

    def _plan_multi_street(self, t, hero_cards, board, villain_range_str,
                           pot, stack, call_amount,
                           fold_equity=0.30, equity=0.50, ptype='unknown'):
        """Monte Carlo simulation over future streets.

        Samples random turn+river runouts, computes equity at each decision
        point using eval7, and returns the action plan with highest total
        expected value across all remaining streets.

        Args:
            t: Table state object
            hero_cards: ['AH', 'KS']
            board: ['QH', 'JD', '2C'] (3 or 4 cards)
            villain_range_str: eval7 range string
            pot: current pot
            stack: hero's stack
            call_amount: amount to call
            fold_equity: estimated fold equity for betting
            equity: current street equity
            ptype: opponent type string

        Returns:
            dict with planning results, or None if planning not possible.
        """
        import time as _time

        try:
            import eval7
        except ImportError:
            return None

        t_start = _time.monotonic()

        from sys_core.decisionmaker.range_equity import _convert_card, get_range_equity

        hero_e7 = [_convert_card(c) for c in hero_cards if c]
        hero_e7 = [c for c in hero_e7 if c is not None]
        board_e7 = [_convert_card(c) for c in board if c]
        board_e7 = [c for c in board_e7 if c is not None]

        if len(hero_e7) != 2 or len(board_e7) < 3:
            return None

        # River (5 cards) or preflop (0 cards): no future streets to simulate
        if len(board_e7) >= 5:
            return None

        try:
            villain_hr = eval7.HandRange(villain_range_str)
            if len(villain_hr) == 0:
                return None
        except Exception:
            return None

        # Build deck minus known cards
        all_cards = eval7.Deck().cards
        dead = set(str(c) for c in hero_e7 + board_e7)
        remaining = [c for c in all_cards if str(c) not in dead]

        if len(remaining) < 2:
            return None

        is_flop = len(board_e7) == 3
        is_turn = len(board_e7) == 4
        n_sims = 150 if is_flop else 100  # Fewer sims on turn (only 1 street)

        bb = t.bigBlind if t.bigBlind > 0 else 1.0

        # Multiway fold equity correction — critical for accurate planning
        n_opp = max(getattr(t, 'other_active_players', 1) or 1, 1)
        if n_opp >= 2:
            fold_equity = fold_equity ** n_opp

        # Bet sizing for simulation
        bet_frac = 0.55  # Default bet ~55% pot
        wetness = self._board_wetness(board)
        if wetness < 0.3:
            bet_frac = 0.33
        elif wetness > 0.7:
            bet_frac = 0.75

        # Range narrowing: use eval7 fold equity to get calling range
        fe_for_sim = compute_range_fold_equity(hero_cards, board, villain_range_str, bet_frac)
        if fe_for_sim:
            sim_fold_eq = fe_for_sim['fold_equity']
            sim_eq_called = fe_for_sim['equity_when_called']
        else:
            sim_fold_eq = fold_equity
            sim_eq_called = equity * 0.65

        re = get_range_equity()
        call_range_str = re.estimate_villain_range(
            position='CO', action='call',
            player_type=ptype, street='flop' if is_flop else 'turn',
            bet_size_pct=bet_frac,
        )
        try:
            call_range_hr = eval7.HandRange(call_range_str)
        except Exception:
            call_range_hr = villain_hr

        # Pre-compute villain betting behavior on this board (once, not per runout)
        hand_ctx = getattr(self, '_hand_context', None)
        hero_ip = hand_ctx.hero_is_ip if hand_ctx else False
        is_villain_pfr = (hand_ctx.preflop_raiser_position != ''
                          if hand_ctx and hasattr(hand_ctx, 'preflop_raiser_position')
                          else True)

        vbf = compute_villain_bet_frequency(
            board, villain_range_str, hero_cards, wetness, is_villain_pfr
        )
        villain_bet_freq = vbf['bet_freq']
        villain_bet_range = vbf.get('bet_range_str', villain_range_str)
        villain_check_range = vbf.get('check_range_str', villain_range_str)

        # Pre-compute check EV for current board (game tree, replaces flat bonuses)
        check_ev_result = compute_check_ev_game_tree(
            hero_e7, board_e7,
            villain_bet_range, villain_check_range,
            villain_bet_freq, pot, hero_ip,
        )

        # ── Monte Carlo simulation ───────────────────────────────────────
        ev_bet_total = 0.0
        ev_check_total = 0.0
        improvement_count = 0
        n_valid = 0
        current_eq = equity

        random.shuffle(remaining)

        for sim_i in range(n_sims):
            try:
                # Sample future cards
                if is_flop:
                    # Need turn + river
                    if len(remaining) < 2:
                        break
                    idx1 = sim_i % len(remaining)
                    idx2 = (sim_i * 7 + 13) % len(remaining)
                    if idx2 == idx1:
                        idx2 = (idx1 + 1) % len(remaining)
                    turn_card = remaining[idx1]
                    river_card = remaining[idx2]
                    future_board_turn = board_e7 + [turn_card]
                    future_board_river = board_e7 + [turn_card, river_card]
                else:
                    # Turn: only need river
                    idx1 = sim_i % len(remaining)
                    river_card = remaining[idx1]
                    future_board_river = board_e7 + [river_card]
                    future_board_turn = board_e7  # Already on turn

                # ── Compute equity at each future street ────────────────

                if is_flop:
                    # Equity on turn (after dealing turn card)
                    try:
                        turn_eq = float(eval7.py_hand_vs_range_monte_carlo(
                            hero_e7, villain_hr, future_board_turn, 3000))
                    except Exception:
                        turn_eq = equity

                    # Equity on river (exact)
                    try:
                        river_eq = float(eval7.py_hand_vs_range_exact(
                            hero_e7, villain_hr, future_board_river))
                    except Exception:
                        river_eq = turn_eq

                    # Track improvement
                    if turn_eq > current_eq + 0.05:
                        improvement_count += 1

                else:
                    # On turn: just compute river equity
                    turn_eq = equity
                    try:
                        river_eq = float(eval7.py_hand_vs_range_exact(
                            hero_e7, villain_hr, future_board_river))
                    except Exception:
                        river_eq = equity

                    if river_eq > current_eq + 0.05:
                        improvement_count += 1

                # ── Plan A: BET now ────────────────────────────────────
                # Villain folds with fold_equity, or calls with tighter range
                bet_size = bet_frac * pot
                bet_size = min(bet_size, stack)

                # If villain folds
                ev_bet_fold = fold_equity * pot

                # If villain calls: pot grows, we continue
                new_pot_after_call = pot + bet_size * 2
                remaining_stack = stack - bet_size

                if is_flop:
                    # Turn decision: barrel or check based on turn equity
                    # We barrel good turns (equity improved), check bad turns
                    if turn_eq >= 0.45:
                        # Barrel turn
                        turn_bet = bet_frac * new_pot_after_call
                        turn_bet = min(turn_bet, remaining_stack)
                        turn_fe = fold_equity * 0.85  # Less fold equity on later streets

                        # Villain folds turn
                        ev_turn_fold = turn_fe * new_pot_after_call

                        # Villain calls turn: river showdown
                        river_pot = new_pot_after_call + turn_bet * 2
                        ev_turn_call = (1.0 - turn_fe) * (river_eq * river_pot - turn_bet)

                        ev_when_called_flop = ev_turn_fold + ev_turn_call
                    else:
                        # Check turn, go to showdown (or fold to bet)
                        # Simplified: check through, river showdown
                        ev_when_called_flop = river_eq * new_pot_after_call - 0
                else:
                    # On turn: villain calls, river showdown
                    ev_when_called_flop = river_eq * new_pot_after_call - 0

                ev_bet_this = ev_bet_fold + (1.0 - fold_equity) * (
                    ev_when_called_flop - bet_size)

                # ── Plan B: CHECK now (game tree EV) ──────────────────
                if is_flop:
                    if turn_eq >= 0.50:
                        # Good turn: bet turn after checking flop
                        turn_bet_check = bet_frac * pot
                        turn_bet_check = min(turn_bet_check, stack)
                        turn_fe_check = fold_equity * 0.90
                        ev_turn_action = turn_fe_check * pot + (1.0 - turn_fe_check) * (
                            river_eq * (pot + turn_bet_check * 2) - turn_bet_check)
                        # Weight by villain's response to our flop check
                        ev_check_this = (villain_bet_freq * check_ev_result['ev_vs_bet'] +
                                         (1.0 - villain_bet_freq) * ev_turn_action)
                    else:
                        ev_check_this = check_ev_result['ev']
                else:
                    ev_check_this = check_ev_result['ev']
                # No flat IP/OOP bonuses — difference is captured in game tree

                ev_bet_total += ev_bet_this
                ev_check_total += ev_check_this
                n_valid += 1

            except Exception:
                continue

        elapsed_ms = (_time.monotonic() - t_start) * 1000

        if n_valid < 20:
            return None

        avg_ev_bet = ev_bet_total / n_valid
        avg_ev_check = ev_check_total / n_valid
        improvement_rate = improvement_count / n_valid

        # Normalize to BB
        avg_ev_bet_bb = avg_ev_bet / bb
        avg_ev_check_bb = avg_ev_check / bb

        if avg_ev_bet_bb > avg_ev_check_bb:
            best = 'bet'
        else:
            best = 'check'

        # Build reasoning
        if is_flop:
            n_improve = improvement_count
            n_total_cards = len(remaining)
            reasoning = (f"{'Flush draw' if self.outs >= 8 else 'Draw' if self.outs >= 4 else 'Hand'} "
                         f"has {'+'  if avg_ev_bet_bb > 0 else ''}EV bet line "
                         f"despite {equity:.0%} current equity. "
                         f"{n_improve}/{n_valid} turns improve equity >50%. "
                         f"Plan: {'BET flop -> BARREL good turns' if best == 'bet' else 'CHECK flop -> free card'}")
        else:
            reasoning = (f"River simulation: bet_ev={avg_ev_bet_bb:+.1f} BB, "
                         f"check_ev={avg_ev_check_bb:+.1f} BB across {n_valid} runouts.")

        return {
            'best_action': best,
            'total_ev_bet': avg_ev_bet_bb,
            'total_ev_check': avg_ev_check_bb,
            'improvement_rate': improvement_rate,
            'reasoning': reasoning,
            'simulations': n_valid,
            'time_ms': elapsed_ms,
        }

    def _get_opp(self):
        """Get opponent profile dict (safe accessor)."""
        opp = getattr(self, '_opp_profile', None)
        if opp and opp.get('hands', 0) >= 10:
            return opp
        return None

    def _get_icm_pressure(self, t):
        """Calculate ICM pressure for tournament decisions.

        Returns a positive equity offset (need MORE equity to call/commit).
        0.0 for cash games, 0.02-0.15 for tournaments.

        Uses real tournament data from OCR when available:
        - t._icm_pressure: pre-computed from rank/total/paid (0.0-1.0 scale)
        - t._game_type: 'cash', 'spin', 'tournament'
        Falls back to stack-commitment heuristic when OCR data is unavailable.
        """
        # --- Use real OCR tournament data if available ---
        game_type = getattr(t, '_game_type', None)
        ocr_icm = getattr(t, '_icm_pressure', None)

        # Cash games: no ICM
        if game_type == 'cash':
            return 0.0

        # Spin & Gold: winner-take-all, minimal ICM
        if game_type == 'spin':
            hero_stack = max(getattr(t, 'myFunds', 100), 1.0)
            call_amount = max(getattr(t, 'currentCallValue', 0) or 0, 0)
            commitment = call_amount / hero_stack if hero_stack > 0 else 0
            if commitment > 0.50:
                return 0.03  # Tiny pressure even in WTA
            return 0.0

        # Check if this is a tournament by name (fallback)
        if game_type is None or game_type == 'unknown':
            table_name = getattr(t, '_table_name', '') or ''
            if not table_name:
                table_name = getattr(t, '_window_name', '') or ''
            is_tournament = any(kw in table_name.lower() for kw in (
                'spin', 'gold', 'tournament', 'sng', 'mtt', 'buy-in',
                'daily', 'weekly', 'bounty', 'ggmasters'))
            if not is_tournament:
                return 0.0
            # Unknown game type but looks like tournament: use old heuristic
            ocr_icm = None

        # --- Common values ---
        hero_stack = max(getattr(t, 'myFunds', 100), 1.0)
        call_amount = max(getattr(t, 'currentCallValue', 0) or 0, 0)
        commitment = call_amount / hero_stack if hero_stack > 0 else 0

        # --- Real ICM pressure from tournament rank OCR ---
        if ocr_icm is not None and ocr_icm > 0:
            # Scale 0.0-1.0 ICM to equity offset (max 0.12)
            base_pressure = ocr_icm * 0.12

            # Commitment amplifies ICM pressure
            if commitment > 0.50:
                commit_mult = 1.5
            elif commitment > 0.30:
                commit_mult = 1.2
            elif commitment > 0.10:
                commit_mult = 1.0
            else:
                commit_mult = 0.7

            pressure = base_pressure * commit_mult

            # Stack-size adjustment
            if hero_stack > 40:
                pressure *= 0.6   # Big stack can afford to gamble
            elif hero_stack < 8:
                pressure *= 0.4   # Short stack must push, reduce ICM

            rank = getattr(t, '_tournament_rank', None)
            total = getattr(t, '_tournament_total', None)
            paid = getattr(t, '_tournament_players_paid', None)
            if rank:
                log.debug(f"ICM (real data): rank={rank}/{total} paid={paid} "
                          f"icm={ocr_icm:.2f} -> pressure={pressure:.3f}")

            return min(pressure, 0.15)

        # --- Fallback: stack-commitment heuristic (no OCR data) ---
        pressure = 0.02

        if commitment > 0.50:
            pressure = 0.08
        elif commitment > 0.30:
            pressure = 0.05
        elif commitment > 0.15:
            pressure = 0.03

        if hero_stack > 40:
            pressure *= 0.5
        elif hero_stack < 10:
            pressure *= 0.3

        return pressure

    def calling(self, t, p, h):
        """Postflop calling decisions via EV engine. Preflop handled by GTO ranges."""

        # Honour alwaysCallEquity / low-stack overrides set in make_decision()
        if self.finalCallLimit > 0 and t.minCall <= self.finalCallLimit:
            self.decision = DecisionTypes.call
            log.info(f"Always-call override active (call {t.minCall} <= limit {self.finalCallLimit:.1f})")
            return

        # Free check — nothing to decide
        if t.minCall <= 0:
            self.decision = DecisionTypes.call
            return

        # ── EV-BASED CALLING (postflop) ───────────────────────────────────
        # Use the unified EV engine for ALL postflop call/fold decisions.
        # Preflop is excluded: GTO ranges + Nash push/fold handle that.
        if t.gameStage != GameStages.PreFlop.value:
            try:
                ev_result = self.compute_ev_decision(t, h, p)
                if ev_result is not None:
                    action = ev_result['action']

                    # PREMIUM SAFETY: never fold monsters postflop
                    hand_info = self._classify_hand(t)
                    if (action == DecisionTypes.fold
                            and hand_info
                            and hand_info['strength'] in ('monster', 'very_strong')):
                        action = DecisionTypes.call
                        log.info(f"EV PREMIUM OVERRIDE: {hand_info['name']} -> call "
                                 f"(was fold, EV={ev_result['ev_call']:+.2f})")

                    # All-in guard: if facing all-in with low equity, respect the fold
                    if t.allInCallButton and action != DecisionTypes.fold:
                        pot = max(t.totalPotValue, 0.01)
                        call = max(t.minCall, 0)
                        pot_odds = call / (pot + call) if (pot + call) > 0 else 0
                        if ev_result['equity'] < max(0.18, pot_odds):
                            action = DecisionTypes.fold
                            log.info(f"EV ALL-IN GUARD: eq={ev_result['equity']:.1%} "
                                     f"< threshold={max(0.18, pot_odds):.1%} -> fold")

                    self.decision = action
                    self.decision_ev = max(ev_result['ev_fold'],
                                           ev_result['ev_call'],
                                           ev_result['ev_raise'] or float('-inf'))
                    log.info(f"EV CALLING: {action.name} -- {ev_result['reasoning']}")
                    return
            except Exception as e:
                log.warning(f"EV engine failed in calling(), using pot-odds fallback: {e}")

        # ── FALLBACK: simple pot-odds (preflop or if EV engine fails) ─────
        pot = max(t.totalPotValue, 0.01)
        call = max(t.minCall, 0)
        pot_odds = call / (pot + call) if (pot + call) > 0 else 0

        if t.equity >= pot_odds:
            self.decision = DecisionTypes.call
            log.info(f"POT ODDS CALL: eq={t.equity:.3f} >= pot_odds={pot_odds:.3f}")
        else:
            self.decision = DecisionTypes.fold
            log.info(f"POT ODDS FOLD: eq={t.equity:.3f} < pot_odds={pot_odds:.3f}")

        # All-in guard
        if t.allInCallButton:
            all_in_threshold = max(0.18, pot_odds)
            if t.equity < all_in_threshold:
                self.decision = DecisionTypes.fold
                log.info(f"ALL-IN GUARD: equity {t.equity:.3f} < threshold {all_in_threshold:.3f}")

    def betting(self, t, p, h):
        """Betting decisions: preflop uses strategy config, postflop uses EV engine."""

        # ── PREFLOP BETTING ──────────────────────────────────────────────
        if t.gameStage == GameStages.PreFlop.value:
            if self.finalBetLimit > float(t.minBet):
                log.info("Preflop Bet1 condition met")
                self.decision = DecisionTypes.bet1
            if (self.finalBetLimit >= float(t.totalPotValue) / 2) \
                    and (p.selected_strategy['increased_preflop_betting'] == 2):
                log.info("Preflop Bet3 condition met")
                self.decision = DecisionTypes.bet3
            return

        # ── POSTFLOP BETTING (EV engine is sole decision maker) ──────────
        # Skip if calling() already set a raise via EV engine
        if self.decision in (DecisionTypes.bet1, DecisionTypes.bet2,
                             DecisionTypes.bet3, DecisionTypes.bet4):
            log.debug(f"EV BETTING: calling() already set {self.decision.name}, skipping")
            return

        try:
            ev_result = self.compute_ev_decision(t, h, p)
            if ev_result is not None:
                action = ev_result['action']

                # If EV says bet/raise, use the EV sizing
                if action in (DecisionTypes.bet1, DecisionTypes.bet2,
                              DecisionTypes.bet3, DecisionTypes.bet4):
                    self.optimal_bet_bb = ev_result.get('raise_amount', 0) / max(t.bigBlind, 0.01)
                    self.finalBetLimit = ev_result.get('raise_amount', 0)

                    # PREMIUM SAFETY: at least half pot with monsters
                    hand_info_ev = self._classify_hand(t)
                    if (hand_info_ev and hand_info_ev['strength'] in ('monster', 'very_strong')
                            and action in (DecisionTypes.bet1, DecisionTypes.bet2)):
                        action = DecisionTypes.bet3
                        log.info(f"EV MONSTER SIZING UP: {hand_info_ev['name']} -> bet3")

                    self.decision = action
                    self.push_fold_shove = (action == DecisionTypes.bet4
                                            and ev_result.get('raise_amount', 0) >= getattr(t, 'myFunds', 0) * 0.85)
                    log.info(f"EV BETTING: {action.name} (raise={ev_result.get('raise_amount', 0):.1f}) "
                             f"-- {ev_result['reasoning']}")
                    return

                # EV says check/call/fold: don't bet
                log.debug(f"EV BETTING: no profitable bet (EV_raise={ev_result.get('ev_raise', 'N/A')}), "
                          f"keeping {self.decision.name}")
                return

        except Exception as e:
            log.warning(f"EV engine failed in betting(), checking back: {e}")
            # Fallback: check if possible, otherwise keep current decision

    def bluff(self, t, p, h):
        """Bluffing is handled by the EV engine via fold equity in compute_ev_decision().
        This method is kept as a no-op for compatibility."""
        t.currentBluff = 0

    def check_deception(self, t, p, h):
        """Check deception is handled by the EV engine (check vs bet EV comparison).
        Kept as no-op for compatibility."""
        self.UseFlopCheckDeception = False
        self.UseTurnCheckDeception = False
        self.UseRiverCheckDeception = False

    def _board_wetness(self, board_cards):
        """0.0=bone dry, 1.0=extremely wet. Uses flop cards only.

        Enhanced algorithm:
        - Flush draws: 2 suited = +0.15, monotone = +0.40
        - Straight draws: connected cards within 4 ranks = +0.15 each pair
        - Paired board = -0.15 (drier)
        - High card boards (A/K-high) are slightly drier for raiser
        """
        if not board_cards or len(board_cards) < 3:
            return 0.5
        rank_map = {r: i for i, r in enumerate('23456789TJQKA')}
        ranks, suits = [], []
        for card in board_cards[:3]:
            if card and len(card) >= 2:
                r = card[0].upper()
                if r == '1' and len(card) >= 3:
                    r = 'T'
                    suits.append(card[2].upper())
                else:
                    suits.append(card[-1].upper())
                ranks.append(rank_map.get(r, 0))
        if len(ranks) < 3:
            return 0.5

        wetness = 0.0
        from collections import Counter

        # --- Flush potential ---
        suit_counts = Counter(suits)
        top_suit_count = suit_counts.most_common(1)[0][1]
        if top_suit_count >= 3:
            wetness += 0.40  # Monotone (flush already possible)
        elif top_suit_count == 2:
            wetness += 0.15  # Two-tone (flush draw possible)

        # --- Straight potential ---
        sorted_ranks = sorted(set(ranks))
        # Count cards within 5-card windows
        max_in_window = 0
        for base in range(max(0, min(sorted_ranks) - 4), max(sorted_ranks) + 1):
            count = sum(1 for r in sorted_ranks if base <= r < base + 5)
            max_in_window = max(max_in_window, count)

        if max_in_window >= 3:
            wetness += 0.25  # 3 cards within 5 = many straight draws
        elif max_in_window == 2:
            gaps = [sorted_ranks[j+1] - sorted_ranks[j] for j in range(len(sorted_ranks)-1)]
            if min(gaps) <= 2:
                wetness += 0.15  # Some connectivity
            else:
                wetness += 0.05  # Minimal connectivity

        # --- Card height ---
        avg_rank = sum(ranks) / len(ranks)
        if avg_rank >= 10:
            wetness += 0.10  # Broadway-heavy (T+ average)
        elif avg_rank >= 7:
            wetness += 0.05  # Medium cards

        # --- Pairing ---
        if len(set(ranks)) < len(ranks):
            wetness -= 0.15  # Paired board = drier

        return max(0.0, min(1.0, wetness))

    def _classify_board(self, board_cards):
        """Classify flop board into a category for c-bet strategy lookup.

        Returns one of the CBET_BOARD_STRATEGY keys:
        'paired_high', 'paired_low', 'dry_high', 'dry_low',
        'two_tone_high', 'two_tone_connected', 'wet', 'monotone'
        """
        if not board_cards or len(board_cards) < 3:
            return 'dry_high'  # Default

        rank_map = {r: i for i, r in enumerate('23456789TJQKA')}
        ranks, suits = [], []
        for card in board_cards[:3]:
            if card and len(card) >= 2:
                r = card[0].upper()
                if r == '1' and len(card) >= 3:
                    r = 'T'
                    suits.append(card[2].upper())
                else:
                    suits.append(card[-1].upper())
                ranks.append(rank_map.get(r, 0))
        if len(ranks) < 3:
            return 'dry_high'

        from collections import Counter
        suit_counts = Counter(suits)
        top_suit_count = suit_counts.most_common(1)[0][1]
        is_paired = len(set(ranks)) < len(ranks)
        is_monotone = top_suit_count >= 3
        is_two_tone = top_suit_count == 2

        sorted_ranks = sorted(ranks)
        gaps = [sorted_ranks[j+1] - sorted_ranks[j] for j in range(len(sorted_ranks)-1)]
        is_connected = all(g <= 2 for g in gaps) and max(sorted_ranks) - min(sorted_ranks) <= 4
        is_very_connected = all(g == 1 for g in gaps)  # e.g. JT9, QJT
        has_high = max(ranks) >= 11  # Q, K, or A high

        # Classify
        if is_monotone:
            return 'monotone'
        if is_paired:
            return 'paired_high' if has_high else 'paired_low'
        if is_very_connected and is_two_tone:
            return 'wet'  # e.g. JT9 two-tone = very wet
        if is_connected and is_two_tone:
            return 'two_tone_connected'
        if is_very_connected:
            return 'wet'  # e.g. QJT rainbow but very connected = still wet
        if is_two_tone:
            return 'two_tone_high' if has_high else 'two_tone_connected'
        if is_connected:
            return 'two_tone_connected' if has_high else 'dry_low'
        # Rainbow, disconnected
        return 'dry_high' if has_high else 'dry_low'

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

        # --- C-BET SPOT: Hero was preflop raiser betting flop → HIGH fold equity ---
        # Being the preflop raiser means we have range advantage on most boards.
        # Opponents expect us to c-bet and fold their weak hands.
        # GTO c-bet fold equity is 40-55% on dry boards, 30-40% on wet boards.
        ctx = getattr(self, '_hand_context', None)
        if ctx and ctx.hero_was_raiser and t.gameStage == GameStages.Flop.value:
            fold_eq += 0.15  # Big boost: c-bet credibility
            if ctx.is_cbet_spot:
                fold_eq += 0.05  # Extra: first bet on flop as raiser
            log.debug(f"C-BET BOOST: hero was raiser, fold_eq +15-20%")

        # --- Opponent bet into us (raising into aggression) → MUCH less fold equity ---
        # When villain bets, they've shown strength. Raising has lower fold equity
        # than betting into a check. Larger bets = stronger range = less fold equity.
        if t.other_player_has_initiative and not t.checkButton:
            fold_eq -= 0.12  # Major penalty: raising into a bettor
            # Extra penalty for large bets (pot-size or bigger = very strong)
            if hasattr(t, 'minCall') and hasattr(t, 'totalPotValue'):
                bet_to_pot = t.minCall / max(t.totalPotValue - t.minCall, 1.0)
                if bet_to_pot >= 0.75:  # 3/4 pot or bigger
                    fold_eq -= 0.08  # Very strong bet → even less fold equity
                elif bet_to_pot >= 0.50:
                    fold_eq -= 0.04  # Half-pot bet → moderate penalty

        # --- Opponent showed weakness (checked to us) ---
        if t.checkButton:
            fold_eq += 0.06

        # --- Position: NO hardcoded bonuses ---
        # Position now flows through the villain's RANGE width (via
        # CALL_RANGES_BY_POSITION in range_equity.py).  A villain who called
        # from BB vs SB has a ~50% range → more combos miss the board → higher
        # fold equity.  This is computed dynamically by compute_range_fold_equity()
        # which is called first in compute_ev_decision(); this heuristic is only
        # the fallback path.

        # --- Multiway: MUCH harder to bluff multiple players ---
        # With N opponents, ALL must fold. FE_total = FE_per_player^N.
        # With 2 opponents and FE=35% each: 0.35^2 = 12%.
        n_opp = max(getattr(t, 'other_active_players', 1) or 1, 1)
        if n_opp >= 2:
            # Apply geometric multiway discount
            fold_eq = fold_eq ** n_opp

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
                from sys_core.decisionmaker.range_equity import compute_range_fold_equity
                v_range = getattr(self, '_villain_range_str', None)
                if not v_range:
                    # Estimate villain range from context
                    opp = self._get_opp()
                    ptype = (opp.get('type', 'unknown')
                             if opp and opp.get('hands', 0) >= 10 else 'unknown')
                    street = t.gameStage.lower() if t.gameStage != 'PreFlop' else 'preflop'
                    v_action = 'bet' if not t.checkButton else 'check'
                    from sys_core.decisionmaker.range_equity import get_range_equity
                    re = get_range_equity()
                    _hand_ctx = getattr(self, '_hand_context', None)
                    _n_opp = getattr(t, 'other_active_players', 1)
                    if _hand_ctx is not None and street != 'preflop':
                        v_range = re.estimate_villain_range_with_context(
                            hand_context=_hand_ctx,
                            street=street,
                            current_action=v_action,
                            bet_size_pct=bet_size_fraction,
                            player_type=ptype,
                            num_opponents=_n_opp,
                        )
                    else:
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

        Uses HandContext when available for much more accurate estimation.
        """
        strength = 0.5  # Default: unknown
        hand_ctx = getattr(self, '_hand_context', None)

        # --- HandContext-based estimation (preferred) ---
        if hand_ctx is not None:
            # Preflop raiser position
            pf_pos = hand_ctx.preflop_raiser_position
            if pf_pos in ('UTG',):
                strength += 0.18
            elif pf_pos in ('MP',):
                strength += 0.12
            elif pf_pos in ('CO',):
                strength += 0.07
            elif pf_pos in ('BTN',):
                strength += 0.02
            # SB/BB open or no raiser = wide

            # 3-bet or 4-bet preflop
            pf_v_actions = hand_ctx.villain_actions.get('preflop', [])
            if '3bet' in pf_v_actions or '4bet' in pf_v_actions:
                strength += 0.18

            # Multi-street aggression pattern
            pattern = hand_ctx.villain_pattern
            if pattern == 'bet-bet-bet':
                # Triple barrel = very strong or bluff (polarized)
                strength += 0.20
            elif pattern == 'bet-bet':
                # Double barrel = committed/strong
                strength += 0.12
            elif pattern in ('check-bet',):
                # Delayed aggression = trapping or turned hand
                strength += 0.08
            elif pattern == 'bet-check':
                # Gave up = weaker (if they bet river after, it's thin value/bluff)
                strength -= 0.05
            elif pattern.startswith('raise') or 'raise' in pattern:
                # Raised at any point postflop = very strong
                strength += 0.15

            # C-bet spot is slightly weaker than raw betting (wider range c-bets)
            if hand_ctx.is_cbet_spot and hand_ctx.streets_of_aggression == 1:
                strength -= 0.05

            # Donk bet = often weak/medium (fish) or strong (regs)
            if hand_ctx.is_donk_bet:
                strength -= 0.03  # Slightly weaker on average

            # Multiway aggression = much stronger
            if hand_ctx.is_multiway and hand_ctx.streets_of_aggression >= 1:
                strength += 0.10

            # Number of streets of aggression
            strength += hand_ctx.streets_of_aggression * 0.03

        else:
            # --- Fallback: legacy single-snapshot estimation ---
            # Preflop raiser position narrows range
            if not np.isnan(getattr(t, 'first_raiser_utg', np.nan)):
                raiser_utg = t.first_raiser_utg
                if raiser_utg <= 1:    # UTG/UTG+1
                    strength += 0.15
                elif raiser_utg <= 2:  # MP
                    strength += 0.10
                elif raiser_utg <= 3:  # CO
                    strength += 0.05

            # 3-bettor = very strong range
            if not np.isnan(getattr(t, 'second_raiser_utg', np.nan)):
                strength += 0.15

            # Postflop actions indicate strength
            if t.gameStage != GameStages.PreFlop.value:
                if t.other_player_has_initiative:
                    strength += 0.10
                if not t.checkButton and t.minCall > 0:
                    call_to_pot = t.minCall / max(t.totalPotValue, 0.01)
                    if call_to_pot > 0.5:
                        strength += 0.10
                    if call_to_pot > 1.0:
                        strength += 0.10
                if t.gameStage == GameStages.Turn.value and t.other_player_has_initiative:
                    strength += 0.05
                elif t.gameStage == GameStages.River.value and t.other_player_has_initiative:
                    strength += 0.10

        # --- Board texture modifies range strength (always applies) ---
        if t.cardsOnTable and len(t.cardsOnTable) >= 3:
            wetness = self._board_wetness(t.cardsOnTable)
            strength -= wetness * 0.08  # Wet boards = more draws in range

        # --- Current bet sizing adjustment ---
        if t.gameStage != GameStages.PreFlop.value:
            if not t.checkButton and t.minCall > 0:
                call_to_pot = t.minCall / max(t.totalPotValue, 0.01)
                if call_to_pot > 0.5:
                    strength += 0.05  # Big bet
                if call_to_pot > 1.0:
                    strength += 0.05  # Overbet

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
        """River value betting is handled by the EV engine. Kept as no-op."""
        pass
    def facing_raise(self, t, p, h):
        """Facing a raise is handled by the EV engine in calling(). Kept as no-op."""
        pass

    def check_raise(self, t, p, h):
        """Check-raise decisions are handled by the EV engine. Kept as no-op."""
        pass

    def call_deception(self, t, p, h):
        pass

    def bully(self, t, p, h):
        """Bully logic is subsumed by the EV engine. Kept as no-op."""
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
        hand_ctx = getattr(self, '_hand_context', None)
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

            # --- Context-aware narrowing using HandContext ---
            if hand_ctx is not None:
                v_pattern = hand_ctx.villain_pattern

                if v_pattern == 'bet-bet-bet':
                    # Triple barrel = very polarized (nuts or bluff)
                    likely = ['monster', 'bluff']
                    bluff_prob = 0.25  # Balanced villains bluff ~25% on river
                    narrowness = 0.90
                    estimated_opp_eq = 0.70
                elif v_pattern == 'bet-bet':
                    # Double barrel = strong or committed draw
                    likely = ['overpair', 'top_pair', 'two_pair', 'strong_draw']
                    bluff_prob = 0.20
                    narrowness = 0.75
                    estimated_opp_eq = 0.62
                elif v_pattern == 'check-bet':
                    # Delayed aggression = trapping or turned hand
                    likely = ['strong_made_hand', 'slow_play', 'turned_pair']
                    bluff_prob = 0.15
                    narrowness = 0.65
                    estimated_opp_eq = 0.60
                elif v_pattern == 'bet-check':
                    # Gave up after flop bet = medium/weak
                    likely = ['weak_pair', 'missed_draw', 'give_up']
                    bluff_prob = 0.10  # Not really bluffing anymore
                    narrowness = 0.40
                    estimated_opp_eq = 0.40
                elif 'raise' in v_pattern:
                    # Any raise = very strong or big draw
                    likely = ['set', 'two_pair', 'strong_draw', 'bluff_raise']
                    bluff_prob = 0.20
                    narrowness = 0.85
                    estimated_opp_eq = 0.72

                # Multiway pots reduce bluff probability significantly
                if hand_ctx.is_multiway:
                    bluff_prob *= 0.50  # Half as likely to bluff in multiway
                    narrowness = min(narrowness + 0.10, 1.0)

                # C-bet spot is wider range (many villains c-bet 60-80%)
                if hand_ctx.is_cbet_spot and hand_ctx.streets_of_aggression <= 1:
                    bluff_prob = max(bluff_prob, 0.35)
                    narrowness = max(narrowness - 0.10, 0.3)

            else:
                # Legacy: multi-street aggression from single snapshot
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
                from sys_core.decisionmaker.range_equity import (
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

        # ══════════════════════════════════════════════════════════════════
        # DESPERATE SHOVE: ≤2BB shove ANY hand — runs before everything
        # ══════════════════════════════════════════════════════════════════
        if (t.gameStage == GameStages.PreFlop.value
                and hasattr(self, 'hero_stack_bb') and self.hero_stack_bb <= 2):
            log.info(f"DESPERATE SHOVE: {self.hero_stack_bb:.1f}BB — auto all-in with any hand")
            self.decision = DecisionTypes.bet4
            self.push_fold_shove = True
            self.admin(t, p, h)
            self.decision = self.decision.value
            self._analyze_blockers(t)
            self._compute_decision_ev(t, p, h)
            return

        # ══════════════════════════════════════════════════════════════════
        # SOLVER FIRST: For Spin & Go and short stacks, the solver MUST
        # run BEFORE any legacy logic (stack commit, narrow range, etc.)
        # to prevent legacy code from overriding solver decisions.
        # ══════════════════════════════════════════════════════════════════
        _table_name_early = getattr(t, '_table_name', '')
        _is_spin_early = ('spin' in _table_name_early.lower() or 'gold' in _table_name_early.lower())
        _solver_threshold_early = 25 if _is_spin_early else 15

        if (t.gameStage == GameStages.PreFlop.value
                and t.mycards and len(t.mycards) == 2
                and hasattr(self, 'hero_stack_bb') and self.hero_stack_bb <= _solver_threshold_early):
            try:
                from sys_core.decisionmaker.solver import get_solver
                _solver = get_solver()
                _bb = t.bigBlind if t.bigBlind > 0 else 1.0
                _hero_pos = getattr(t, '_gto_position', 'CO')
                _hand_ctx = getattr(self, '_hand_context', None)
                _hero_ip = _hand_ctx.hero_is_ip if _hand_ctx else (_hero_pos in ('BTN', 'CO'))

                sr = _solver.decide(
                    hero_cards=t.mycards, board=[], pot=max(t.totalPotValue or 0, 1.5),
                    stack=t.myFunds, call_amount=float(t.minCall or 0),
                    bb=_bb, position=_hero_pos, hero_is_ip=_hero_ip,
                    game_type='spin' if _is_spin_early else 'cash',
                )
                if sr.solver_layer > 0:
                    _action_map_solver = {
                        'allin': DecisionTypes.bet4,
                        'raise': DecisionTypes.bet3,
                        'call': DecisionTypes.call,
                        'check': DecisionTypes.check,
                        'fold': DecisionTypes.fold,
                    }
                    self.decision = _action_map_solver.get(sr.action, DecisionTypes.fold)
                    if sr.action == 'allin':
                        self.push_fold_shove = True
                    # Convert fold→check when free
                    if self.decision == DecisionTypes.fold and t.checkButton:
                        self.decision = DecisionTypes.check
                    log.info(f"SOLVER L{sr.solver_layer}: {sr.action} "
                             f"freq={sr.frequency:.0%} ({sr.solve_time_ms:.0f}ms) "
                             f"| {sr.reasoning}")
                    self.admin(t, p, h)
                    self.decision = self.decision.value
                    self._analyze_blockers(t)
                    self._compute_decision_ev(t, p, h)
                    return
            except Exception as e:
                log.debug(f"Early solver failed: {e}")

        # ── Legacy logic below (only reached if solver didn't handle it) ──

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

        # (Solver already ran at top of make_decision — this is legacy fallback only)
        # Legacy Nash push/fold fallback (if solver unavailable)
        if t.gameStage == GameStages.PreFlop.value and self.hero_stack_bb <= 15:
            _push_fold_done = False
            try:
                from sys_core.decisionmaker.range_equity import (
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
                # EV SANITY CHECK: If Nash says fold but calling is cheap and +EV, call.
                # Nash push/fold is "shove or fold" but sometimes a cheap call exists.
                # QJo in BB with 0.5BB to call into 1.5BB pot = obviously profitable call.
                if self.decision == DecisionTypes.fold and t.minCall > 0:
                    call_amt = float(t.minCall)
                    pot_total = float(t.totalPotValue) + call_amt
                    pot_odds = call_amt / pot_total if pot_total > 0 else 1.0
                    abs_eq = float(getattr(t, 'equity', 0) or 0)
                    if abs_eq > pot_odds and call_amt <= self.hero_stack_bb * 0.15:
                        # Cheap call that's +EV — override fold
                        ev_call = abs_eq * pot_total - (1.0 - abs_eq) * call_amt
                        log.info(f"EV OVERRIDE NASH FOLD: call={call_amt:.1f}BB into "
                                 f"pot={pot_total:.1f}BB, eq={abs_eq:.0%} > pot_odds={pot_odds:.0%}, "
                                 f"EV(call)={ev_call:+.2f}BB → CALL instead of fold")
                        self.decision = DecisionTypes.call
                        _push_fold_done = True

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

            # EV engine handles all postflop decisions via calling() and betting()
            self.calling(t, p, h)
            self.betting(t, p, h)

        self.admin(t, p, h)
        t.currentBluff = 0  # Bluff tracking (EV engine handles bluffs internally)

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
            from sys_core.core.constants import get_dir
            history_file = os.path.join(get_dir('learning'), 'hand_history.jsonl')
            opp = self._get_opp()
            hand_data = {
                'timestamp': datetime.datetime.utcnow().isoformat(),
                'street': t.gameStage,
                'cards': t.mycards,
                'board': t.cardsOnTable,
                'equity': round(float(t.equity), 3),
                'range_equity': round(float(getattr(t, 'range_equity', t.equity)), 3),
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
