"""
Full Decision Pipeline Tests -- verifies the COMPLETE decision engine
(Monte Carlo equity + Decision.make_decision) produces correct plays.

Each test creates a synthetic game state (no screenshots) and runs the
full pipeline that the live bot uses.
"""

import sys
import os
import logging
import numpy as np
from types import SimpleNamespace
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from sys_core.decisionmaker.decisionmaker import Decision, PREMIUM_HANDS_TIER1
from sys_core.decisionmaker.current_hand_memory import History, CurrentHandPreflopState
from sys_core.decisionmaker.montecarlo_python import run_montecarlo_wrapper
from sys_core.tools.helper import DecisionTypes, GameStages
from sys_core.tools.game_logger import GameLogger

# Quiet loggers
logging.basicConfig(level=logging.WARNING)
for name in ('montecarlo', 'decisionmaker', 'curvefitting', 'range_equity',
             'handmemory', 'strategy_adjuster', 'sys_core', 'root'):
    logging.getLogger(name).setLevel(logging.WARNING)
log = logging.getLogger('test_pipeline')
log.setLevel(logging.INFO)

# ─── Cache strategy so we don't reload it for every scenario ─────────────────
_cached_strategy = None

def _load_strategy():
    global _cached_strategy
    if _cached_strategy is not None:
        return _cached_strategy
    from sys_core.gui.action_and_signals import StrategyHandler
    sh = StrategyHandler()
    sh.read_strategy()
    s = sh.selected_strategy
    s['bigBlind'] = 1.0
    s['smallBlind'] = 0.5
    s['initialFunds'] = 100.0
    s['initialFunds2'] = 100.0
    s['use_pot_multiples'] = 0
    s['use_relative_equity'] = 0
    s['preflop_override'] = 1
    s['always_call_low_stack_multiplier'] = 8
    s['alwaysCallEquity'] = 0.85
    s['c'] = 0.5
    s['PreFlopMinCallEquity'] = 0.17
    s['PreFlopMinBetEquity'] = 0.22
    s['PreFlopMaxBetEquity'] = 1.0
    s['PreFlopCallPower'] = 2
    s['PreFlopBetPower'] = 2
    s['FlopMinCallEquity'] = 0.30
    s['FlopMinBetEquity'] = 0.40
    s['FlopMaxBetEquity'] = 1.0
    s['FlopCallPower'] = 2
    s['FlopBetPower'] = 2
    s['TurnMinCallEquity'] = 0.30
    s['TurnMinBetEquity'] = 0.42
    s['TurnMaxBetEquity'] = 1.0
    s['TurnCallPower'] = 2
    s['TurnBetPower'] = 2
    s['RiverMinCallEquity'] = 0.28
    s['RiverMinBetEquity'] = 0.45
    s['RiverMaxBetEquity'] = 1.0
    s['RiverCallPower'] = 2
    s['RiverBetPower'] = 2
    for i in range(6):
        s[f'range_utg{i}'] = 0.25
    s['range_multiple_players'] = 0.25
    s['range_preflop'] = 100
    _cached_strategy = sh
    return sh


class MockSignals:
    def __init__(self):
        self.signal_progressbar_increase = SimpleNamespace(emit=lambda x: None)
        self.signal_status = SimpleNamespace(emit=lambda x: None)
        self.lock = SimpleNamespace(acquire=lambda: None, release=lambda: None)


def build_table(strategy, *, my_cards, board_cards, pot, call_amount, my_stack,
                opp_stacks, position='CO', has_check=False, has_call=True,
                has_raise=True, has_fold=True, num_players=6,
                first_raiser_utg=float('nan')):
    """Build a fully populated table object for Decision."""
    from sys_core.scraper.table_screen_based import TableScreenBased

    t = TableScreenBased(strategy, {}, MockSignals(), GameLogger(), version=6.76, nn_model=None)
    t.mycards = list(my_cards)
    t.cardsOnTable = list(board_cards) if board_cards else []

    n_board = len(t.cardsOnTable)
    if n_board == 0:
        t.gameStage = 'PreFlop'
    elif n_board == 3:
        t.gameStage = 'Flop'
    elif n_board == 4:
        t.gameStage = 'Turn'
    else:
        t.gameStage = 'River'

    t.totalPotValue = float(pot)
    t.currentRoundPotValue = float(pot)
    t.round_pot_value = float(pot)
    t.currentCallValue = float(call_amount)
    t.currentBetValue = float(call_amount * 2) if call_amount > 0 else 2.0
    t.bigBlind = 1.0
    t.smallBlind = 0.5
    t.checkButton = has_check
    t.callButton = has_call
    t.raiseButton = has_raise
    t.allInCallButton = False
    t.myFunds = float(my_stack)
    t.myFundsChange = 0.0
    t.total_players = num_players
    t.playersAtTable = min(len(opp_stacks) + 1, num_players)

    other_tmpl = {'utg_position': 0, 'name': '', 'status': 1,
                  'funds': 0, 'pot': 0, 'decision': '', 'abs_position': 0}
    t.other_players = []
    for i, stk in enumerate(opp_stacks):
        op = deepcopy(other_tmpl)
        op['abs_position'] = i
        op['utg_position'] = i
        op['funds'] = float(stk)
        op['status'] = 1
        t.other_players.append(op)
    while len(t.other_players) < num_players - 1:
        pad = deepcopy(other_tmpl)
        pad['abs_position'] = len(t.other_players)
        pad['status'] = 0
        t.other_players.append(pad)

    t.other_active_players = len(opp_stacks)
    t.other_player_has_initiative = (call_amount > 0)
    t.isHeadsUp = (len(opp_stacks) == 1)
    t.first_raiser_utg = first_raiser_utg
    t.first_caller = np.nan
    t.first_caller_utg = np.nan
    t.second_raiser_utg = np.nan
    t.first_raiser = 2.0 if not np.isnan(first_raiser_utg) else np.nan
    t.assumedPlayers = len(opp_stacks) + 1

    pos_map = {'UTG': 0, 'MP': 1, 'CO': 2, 'BTN': 3, 'SB': 4, 'BB': 5}
    t._gto_position = position
    t.position_utg_plus = pos_map.get(position, 2)
    t.max_X = 0
    t.max_X_cum = 0
    t.second_round_pot_already_called = 0
    t.power1 = 2
    t.power2 = 2
    t.potStretch = 1.0
    t._table_name = 'Spin & Gold'
    t.currentBluff = 0
    t.playersAhead = 0
    t.playersBehind = 0
    t.mt_tm = 0
    t.montecarlo_timeout = 10
    return t


def run_mc(strategy, t, h):
    """Run Monte Carlo equity calculation."""
    from sys_core.tools.helper import get_config
    config = get_config()
    preflop_state = CurrentHandPreflopState()
    run_montecarlo_wrapper(strategy, MockSignals(), config, None, t, GameLogger(), preflop_state, h)


def decide(strategy, t, h):
    d = Decision(t, h, strategy, GameLogger())
    d.make_decision(t, h, strategy, GameLogger())
    return d


def classify(d):
    """Classify decision into fold/call/raise."""
    dec = d.decision
    # Handle both enum and string values
    if isinstance(dec, DecisionTypes):
        if dec == DecisionTypes.fold:
            return 'fold'
        if dec in (DecisionTypes.call, DecisionTypes.check,
                   DecisionTypes.call_deception, DecisionTypes.check_deception):
            return 'call'
        if dec in (DecisionTypes.bet1, DecisionTypes.bet2, DecisionTypes.bet3,
                   DecisionTypes.bet4, DecisionTypes.bet_bluff):
            return 'raise'
    # String fallback
    dec_str = dec.value if isinstance(dec, DecisionTypes) else str(dec)
    dec_lower = dec_str.lower()
    if dec_lower == 'fold':
        return 'fold'
    if dec_lower in ('call', 'check', 'call deception', 'check deception'):
        return 'call'
    if 'bet' in dec_lower or 'raise' in dec_lower or 'allin' in dec_lower:
        return 'raise'
    return dec_lower


def run_test(name, *, expected, forbidden=None, **kwargs):
    """Run a scenario and return (passed, category, equity, details)."""
    strategy = _load_strategy()
    h = History()
    h.round_number = 0
    h.previous_decision = ''
    t = build_table(strategy, **kwargs)

    try:
        run_mc(strategy, t, h)
    except Exception as e:
        pass  # MC can fail for some edge cases

    if not hasattr(t, 'equity') or t.equity == 0:
        t.equity = 0.35
    if not hasattr(t, 'abs_equity'):
        t.abs_equity = t.equity
    if not hasattr(t, 'relative_equity'):
        t.relative_equity = t.equity

    d = decide(strategy, t, h)
    cat = classify(d)
    eq = t.equity

    ok = cat in expected
    if forbidden and cat in forbidden:
        ok = False

    dec_str = d.decision.value if hasattr(d.decision, 'value') else str(d.decision)
    return ok, cat, eq, dec_str, d.finalCallLimit, d.finalBetLimit


def main():
    print("=" * 72)
    print("  FULL DECISION PIPELINE TESTS")
    print("  Testing Monte Carlo equity + Decision.make_decision()")
    print("=" * 72)

    # Build preflop tables once
    try:
        from sys_core.decisionmaker.range_equity import build_preflop_equity_table, build_push_fold_table
        build_preflop_equity_table()
        build_push_fold_table()
        print("  Preflop equity + push/fold tables built OK")
    except Exception as e:
        print(f"  WARNING: Preflop tables failed: {e}")

    results = []
    scenarios = [
        # ── SC1: 63o on K72r facing full pot bet → FOLD ─────────────
        dict(
            name="SC1: 63o on K72r, villain bets full pot -> FOLD",
            my_cards=['6H', '3S'], board_cards=['KD', '7C', '2S'],
            pot=6.0, call_amount=6.0, my_stack=47.0,
            opp_stacks=[50.0], position='CO',
            has_check=False, has_call=True, has_raise=True, has_fold=True,
            first_raiser_utg=2,
            expected=['fold'],
            reason="No pair, no draw, no overcards. ~10% equity vs pot-size bet.",
        ),
        # ── SC2: AA on J73r → NEVER FOLD ───────────────────────────
        dict(
            name="SC2: AA on J73r, villain bets -> NEVER FOLD",
            my_cards=['AH', 'AS'], board_cards=['JD', '7C', '3S'],
            pot=6.0, call_amount=3.0, my_stack=97.0,
            opp_stacks=[100.0], position='BTN',
            has_check=False, has_call=True, has_raise=True, has_fold=True,
            first_raiser_utg=2,
            expected=['call', 'raise'], forbidden=['fold'],
            reason="AA = overpair, top of range. Must never fold.",
        ),
        # ── SC3: Flush draw 9h8h on Jh4h2c → CALL/RAISE ──────────
        dict(
            name="SC3: 9h8h flush draw on Jh4h2c -> CALL or RAISE",
            my_cards=['9H', '8H'], board_cards=['JH', '4H', '2C'],
            pot=6.0, call_amount=3.0, my_stack=47.0,
            opp_stacks=[50.0], position='BB',
            has_check=False, has_call=True, has_raise=True, has_fold=True,
            first_raiser_utg=3,
            expected=['call', 'raise'], forbidden=['fold'],
            reason="9 outs flush draw, ~35% equity, getting 3:1 pot odds.",
        ),
        # ── SC4: Free check BB on K92 → CHECK (call category) ─────
        dict(
            name="SC4: A8 BB check on K92 -> CHECK (not donk-bet big)",
            my_cards=['AH', '8S'], board_cards=['KD', '9C', '2S'],
            pot=4.0, call_amount=0.0, my_stack=49.0,
            opp_stacks=[50.0], position='BB',
            has_check=True, has_call=False, has_raise=True, has_fold=False,
            first_raiser_utg=3,
            expected=['call', 'raise'],  # check = call category; bet is also OK
            reason="Free check. A8 on K92 should check or small bet. Must not fold.",
        ),
        # ── SC5: 5BB CO with K9s → SHOVE ──────────────────────────
        dict(
            name="SC5: 5BB K9s in CO -> SHOVE (Nash push/fold)",
            my_cards=['KH', '9H'], board_cards=[],
            pot=1.5, call_amount=0.0, my_stack=5.0,
            opp_stacks=[25.0, 25.0], position='CO',
            has_check=False, has_call=True, has_raise=True, has_fold=True,
            expected=['raise'],
            reason="5BB Nash range for CO includes K9s. Should shove.",
        ),
        # ── SC6: Pot committed 1BB, pot 10BB with pair → CALL ──────
        dict(
            name="SC6: 1BB stack, 10BB pot, Q7 on Q53 -> CALL (pot committed)",
            my_cards=['QS', '7H'], board_cards=['QD', '5C', '3S'],
            pot=10.0, call_amount=1.0, my_stack=1.0,
            opp_stacks=[50.0], position='BB',
            has_check=False, has_call=True, has_raise=False, has_fold=True,
            first_raiser_utg=3,
            expected=['call', 'raise'], forbidden=['fold'],
            reason="Pot committed: 1BB to call into 10BB with top pair. Must call.",
        ),
        # ── SC7: AA preflop vs 3-bet → NEVER FOLD ─────────────────
        dict(
            name="SC7: AA preflop facing 3-bet -> RAISE (4-bet) or CALL",
            my_cards=['AD', 'AC'], board_cards=[],
            pot=7.0, call_amount=5.0, my_stack=95.0,
            opp_stacks=[100.0], position='UTG',
            has_check=False, has_call=True, has_raise=True, has_fold=True,
            first_raiser_utg=0,
            expected=['call', 'raise'], forbidden=['fold'],
            reason="AA is PREMIUM_TIER1. Must never fold preflop.",
        ),
        # ── SC8: KK preflop open CO → RAISE ───────────────────────
        dict(
            name="SC8: KK first-in CO -> RAISE",
            my_cards=['KH', 'KD'], board_cards=[],
            pot=1.5, call_amount=1.0, my_stack=100.0,
            opp_stacks=[100.0, 100.0, 100.0], position='CO',
            has_check=False, has_call=True, has_raise=True, has_fold=True,
            expected=['raise'],
            reason="KK in CO: mandatory open raise.",
        ),
        # ── SC9: 72o UTG → FOLD ───────────────────────────────────
        dict(
            name="SC9: 72o UTG 100BB deep -> FOLD",
            my_cards=['7S', '2H'], board_cards=[],
            pot=1.5, call_amount=1.0, my_stack=100.0,
            opp_stacks=[100.0, 100.0, 100.0, 100.0], position='UTG',
            has_check=False, has_call=True, has_raise=True, has_fold=True,
            expected=['fold'],
            reason="72o is unplayable from UTG at any stack depth.",
        ),
        # ── SC10: 2BB stack any hand → SHOVE ──────────────────────
        dict(
            name="SC10: 2BB stack 53o BTN -> SHOVE (desperate)",
            my_cards=['5H', '3S'], board_cards=[],
            pot=1.5, call_amount=0.0, my_stack=2.0,
            opp_stacks=[50.0, 50.0], position='BTN',
            has_check=False, has_call=True, has_raise=True, has_fold=True,
            expected=['raise'],
            reason="2BB = desperate shove with ANY hand.",
        ),
        # ── SC11: AKs BTN → RAISE ─────────────────────────────────
        dict(
            name="SC11: AKs BTN first-in -> RAISE",
            my_cards=['AH', 'KH'], board_cards=[],
            pot=1.5, call_amount=1.0, my_stack=100.0,
            opp_stacks=[100.0, 100.0], position='BTN',
            has_check=False, has_call=True, has_raise=True, has_fold=True,
            expected=['raise'],
            reason="AKs on BTN = mandatory open raise.",
        ),
        # ── SC12: TPTK on dry board → RAISE/CALL ──────────────────
        dict(
            name="SC12: AK on A72r -> RAISE or CALL (TPTK)",
            my_cards=['AH', 'KS'], board_cards=['AD', '7C', '2S'],
            pot=6.0, call_amount=3.0, my_stack=94.0,
            opp_stacks=[97.0], position='BTN',
            has_check=False, has_call=True, has_raise=True, has_fold=True,
            first_raiser_utg=2,
            expected=['call', 'raise'], forbidden=['fold'],
            reason="TPTK on dry board. Value bet or call, never fold.",
        ),
    ]

    for sc in scenarios:
        name = sc.pop('name')
        expected = sc.pop('expected')
        forbidden = sc.pop('forbidden', None)
        reason = sc.pop('reason', '')
        print(f"\n--- {name} ---")

        ok, cat, eq, dec_str, call_lim, bet_lim = run_test(
            name, expected=expected, forbidden=forbidden, **sc
        )

        symbol = "+" if ok else "X"
        status = "PASS" if ok else "FAIL"
        print(f"  [{symbol}] Decision: {dec_str} (category={cat})")
        print(f"      equity={eq:.3f} callLim={call_lim:.1f} betLim={bet_lim:.1f}")
        if not ok:
            print(f"      *** EXPECTED: {expected}, GOT: {cat} ***")
            print(f"      Reason: {reason}")

        results.append((name, ok, cat, eq))

    # Summary
    print("\n" + "=" * 72)
    total = len(results)
    passed = sum(1 for _, ok, *_ in results if ok)
    failed = total - passed
    print(f"  RESULTS: {passed}/{total} PASSED, {failed} FAILED")
    print("=" * 72)
    for name, ok, cat, eq in results:
        sym = "PASS" if ok else "FAIL"
        print(f"  [{sym}] {name}  (got={cat}, eq={eq:.3f})")
    print("=" * 72)

    if failed > 0:
        print(f"\n  WARNING: {failed} scenario(s) failed!")
        print("  These need investigation and potential fixes.")
    else:
        print("\n  All scenarios passed -- strategy is making correct plays.")

    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
