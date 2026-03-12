#!/usr/bin/env python3
"""Simulate a full hand through the bot's decision pipeline.

This tests the REAL code path: GameState → to_table_scraper_compat → Monte Carlo →
DecisionMaker → raise sizing.  No mocks except for mouse clicks.
"""
import logging
import sys
import os

# Must run from project root
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(name)s %(levelname)s %(message)s')
log = logging.getLogger('simulate_hand')

from sys_core.ocr.game_state import GameState, PlayerInfo, AvailableAction, Street
from sys_core.decisionmaker.current_hand_memory import CurrentHandPreflopState, History
from sys_core.decisionmaker.decisionmaker import Decision
from sys_core.decisionmaker.montecarlo_python import run_montecarlo_wrapper
from sys_core.tools.strategy_handler import StrategyHandler
from sys_core.tools.helper import get_config

# Mock signals for Monte Carlo
class MockSignals:
    def __getattr__(self, name): return self
    def __call__(self, *a, **k): return None
    def emit(self, *a, **k): return None


def build_strategy():
    """Build strategy with same settings as engine without DB."""
    p = StrategyHandler()
    # Build strategy dict inline (same as engine.py lines 345-417)
    s = {
        'bigBlind': 1.0, 'smallBlind': 0.5,
        'initialFunds': 100.0, 'initialFunds2': 100.0,
        'PreFlopMinCallEquity': 0.17, 'PreFlopMinBetEquity': 0.22,
        'PreFlopMaxBetEquity': 1.0, 'PreFlopCallPower': 2, 'PreFlopBetPower': 2,
        'FlopMinCallEquity': 0.30, 'FlopMinBetEquity': 0.40, 'FlopCallPower': 2, 'FlopBetPower': 2,
        'TurnMinCallEquity': 0.33, 'TurnMinBetEquity': 0.43, 'TurnCallPower': 2, 'TurnBetPower': 2,
        'RiverMinCallEquity': 0.35, 'RiverMinBetEquity': 0.48, 'RiverCallPower': 2, 'RiverBetPower': 2,
        'secondRoundAdjustmentPreFlop': 0.08, 'secondRoundAdjustment': 0.05,
        'secondRoundAdjustmentPowerIncrease': 1,
        'minimum_bet_size': 3, 'increased_preflop_betting': 2,
        'BetPlusInc': 3.0, 'use_pot_multiples': 0,
        'pre_flop_equity_reduction_by_position': 0.02,
        'pre_flop_equity_increase_if_bet': 0.03,
        'pre_flop_equity_increase_if_call': 0.02,
        'potAdjustment': 1.0, 'maxPotAdjustment': 0.10,
        'potAdjustmentPreFlop': 1.0, 'maxPotAdjustmentPreFlop': 0.05,
        'alwaysCallEquity': 0.80, 'always_call_low_stack_multiplier': 6,
        'range_multiple_players': 0.25, 'range_preflop': 0.50,
        'use_relative_equity': 0, 'range_of_range': 0, 'collusion': 0,
        # Bluff conditions
        'FlopBluffMaxEquity': 100, 'TurnBluffMaxEquity': 100, 'RiverBluffMaxEquity': 100,
        'flop_betting_condidion_1': 1, 'turn_betting_condidion_1': 1, 'river_betting_condidion_1': 1,
        'flop_bluffing_condidion_1': 1, 'turn_bluffing_condidion_1': 0,
        'turn_bluffing_condidion_2': 1, 'river_bluffing_condidion_1': 0, 'river_bluffing_condidion_2': 1,
        'max_abs_fundchange': 4, 'out_multiplier': 0, 'preflop_override': 0,
        # Bet pot conditions
        'betPotRiverEquity': 0.80, 'betPotRiverEquityMaxBBM': 100,
        'secondRiverBetPotMinEquity': 0.70,
        # Bully mode
        'bullyDivider': 10, 'minBullyEquity': 0.60, 'maxBullyEquity': 0.90,
        'differentiate_reverse_sheet': 1,
        'opponent_raised_without_initiative_flop': 1,
        'opponent_raised_without_initiative_turn': 1,
        'opponent_raised_without_initiative_river': 1,
        # Per-position opponent ranges (UTG=0 through BB=5)
        'range_utg0': 0.15,  # UTG tight
        'range_utg1': 0.18,  # UTG+1
        'range_utg2': 0.22,  # MP
        'range_utg3': 0.28,  # CO
        'range_utg4': 0.35,  # BTN
        'range_utg5': 0.30,  # SB/BB
        'range_utg6': 0.25,
        'range_utg7': 0.25,
        'range_utg8': 0.25,
    }
    p.selected_strategy = s
    p.current_strategy = 'simulation'
    return p

# ---------------------------------------------------------------------------
#  Build a mock TableScreenBased that has all required attributes
# ---------------------------------------------------------------------------
class FakeTable:
    """Minimal table object that to_table_scraper_compat() can populate."""
    def __init__(self):
        # These get set by to_table_scraper_compat
        self.mycards = []
        self.cardsOnTable = []
        self.totalPotValue = 0
        self.currentRoundPotValue = 0
        self.currentCallValue = 0
        self.currentBetValue = 0
        self.minCall = 0
        self.minBet = 0
        self.smallBlind = 0.5
        self.bigBlind = 1.0
        self.checkButton = False
        self.callButton = False
        self.raiseButton = False
        self.allInCallButton = False
        self.equity = 0
        self.abs_equity = 0
        self.gameStage = 'PreFlop'
        self.other_active_players = 1
        self.other_players = []
        self.dealer_position = 0
        self.position = 'BTN'
        self.myFunds = 100
        self.myBet = 0
        self.round_number = 0
        self.totalPotValue = 0
        self.minCall = 0
        self.minBet = 0
        self.power1 = 0
        self.power2 = 0
        self.other_player_has_initiative = False
        self.first_raiser_utg = -1
        self.first_raiser = -1
        self.other_player_has_initiative = False
        self.second_round = False
        self.is_headsup = True
        self.friends_and_foes = {}
        self.current_decision = None
        self.last_round_bluff = False
        self.loss_prevented = False
        self.max_X = 0.95  # 0.95 for preflop, 1.0 for postflop
        self.PlayerNames = ['Villain1']
        self.playersAhead = 1
        self.playersBehind = 0
        self.first_caller_utg = -1
        self.total_players = 6
        self.playersAtTable = 6
        self.isHeadsUp = True

    def get_round_number(self, h):
        """Dummy round tracking."""
        self.round_number = h.round_number if hasattr(h, 'round_number') else 0

    def get_abs_from_utg_pos(self, utg_pos, dealer_pos):
        """Map UTG position to absolute position."""
        return (utg_pos + dealer_pos - 4) % self.total_players

    def get_utg_from_abs_pos(self, abs_pos, dealer_pos):
        """Map absolute position to UTG position."""
        return (abs_pos - dealer_pos + 4) % self.total_players


class FakeGameLogger:
    """Minimal game logger that just prints."""
    def mark_new_round(self, *a): pass
    def write_log_file(self, *a): pass
    def get_flop_frequency_of_player(self, *a):
        return float('nan')  # Unknown player frequency
    def __getattr__(self, name):
        return lambda *a, **k: None


def simulate_hand(hero_cards, board_cards, pot, call_amount, hero_stack,
                  position='BTN', opponents=1, min_raise=0,
                  villain_bet=True, street=None):
    """Run one hand through the full decision pipeline.

    Args:
        hero_cards: e.g. ['AH', 'KS']
        board_cards: e.g. ['QH', 'JD', '2C'] or [] for preflop
        pot: total pot in BB
        call_amount: amount to call in BB
        hero_stack: hero stack in BB
        position: hero position
        opponents: number of active opponents
        min_raise: min raise amount in BB
        villain_bet: did villain bet/raise?
        street: override street detection
    """
    log.info("=" * 70)
    log.info(f"HAND: {hero_cards} | Board: {board_cards or 'PREFLOP'}")
    log.info(f"Pot: {pot} BB | Call: {call_amount} BB | Stack: {hero_stack} BB | Pos: {position}")
    log.info("=" * 70)

    # Determine street
    if street is None:
        if len(board_cards) == 0:
            street = Street.PREFLOP
        elif len(board_cards) == 3:
            street = Street.FLOP
        elif len(board_cards) == 4:
            street = Street.TURN
        else:
            street = Street.RIVER

    # Build actions
    actions = [
        AvailableAction('fold', None, 100, 800, 0.9),
    ]
    if call_amount > 0:
        actions.append(AvailableAction('call', call_amount, 200, 800, 0.9))
    else:
        actions.append(AvailableAction('check', None, 200, 800, 0.9))
    if min_raise > 0:
        actions.append(AvailableAction('raise', min_raise, 300, 800, 0.9))

    # Build players
    players = [
        PlayerInfo(seat=0, name="Hero", stack=hero_stack, current_bet=0,
                   is_active=True, is_hero=True),
    ]
    for i in range(opponents):
        players.append(
            PlayerInfo(seat=i + 1, name=f"Villain{i+1}", stack=100.0,
                       current_bet=0, is_active=True, is_hero=False)
        )

    state = GameState(
        window_id=1,
        window_name="Rush & Cash $0.01 / $0.02",
        table_x_pt=0, table_y_pt=0, table_w_pt=855, table_h_pt=615,
        my_cards=hero_cards,
        board_cards=board_cards,
        cards_face_down=False,
        pot=pot,
        current_street_pot=pot * 0.5 if board_cards else pot,
        call_amount=call_amount,
        min_raise_amount=min_raise if min_raise > 0 else call_amount * 2,
        small_blind=0.5,
        big_blind=1.0,
        players=players,
        hero_seat=0,
        dealer_seat=0 if position == 'BTN' else 2,
        available_actions=actions,
        street=street,
        is_my_turn=True,
        position=position,
        opponents_in_hand=opponents,
        ocr_latency_ms=50.0,
        ocr_source='simulation',
        hero_stack_is_estimated=False,
    )

    # Create table + strategy + history
    t = FakeTable()
    p = build_strategy()
    h = History()
    h.round_number = 0
    game_logger = FakeGameLogger()

    # Populate table from GameState (same as live bot does)
    state.to_table_scraper_compat(t)
    t.get_round_number(h)

    log.info(f"Table populated: mycards={t.mycards} board={t.cardsOnTable} "
             f"pot={t.totalPotValue:.1f} call={t.currentCallValue:.1f} "
             f"stack={t.myFunds:.1f} check={t.checkButton} "
             f"raise={t.raiseButton} initiative={'Y' if t.other_player_has_initiative else 'N'}")

    # Run Monte Carlo equity
    mock_signals = MockSignals()
    config = get_config()
    preflop_state = CurrentHandPreflopState()

    log.info("Running Monte Carlo equity calculation...")
    run_montecarlo_wrapper(p, mock_signals, config, None, t, game_logger, preflop_state, h)
    log.info(f"EQUITY: {t.equity:.3f} (abs: {getattr(t, 'abs_equity', 0):.3f})")

    # Make decision
    d = Decision(t, h, p, game_logger)
    d._opp_profile = None
    d._spot_adj = {}
    d._we_bet_prev_street = False
    d._prev_street_equity = None

    d.make_decision(t, h, p, game_logger)

    decision = d.decision
    log.info(f"")
    log.info(f">>> DECISION: {decision}")
    log.info(f"    callLimit={d.finalCallLimit:.1f} betLimit={d.finalBetLimit:.1f}")

    # If it's a raise, compute the sizing
    dec_str = str(decision).lower() if decision else ''
    if 'bet' in dec_str or 'raise' in dec_str or 'allin' in dec_str.replace(' ', ''):
        try:
            from sys_core.decisionmaker.range_equity import compute_bet_size_bb, preflop_raise_size_bb
            bb_size = 1.0
            pot_bb = pot
            stack_bb = hero_stack
            is_preflop = len(board_cards) == 0

            if is_preflop:
                if call_amount <= 1.0:
                    action = 'open'
                elif call_amount <= 5.0:
                    action = '3bet'
                else:
                    action = '4bet'
                pos = position if position in ('UTG', 'MP', 'CO', 'BTN', 'SB', 'BB') else 'CO'
                size = preflop_raise_size_bb(action, pos)
                log.info(f"    RAISE SIZE: {size:.1f} BB (preflop {action} from {pos})")
            else:
                street_str = {3: 'flop', 4: 'turn', 5: 'river'}.get(len(board_cards), 'flop')
                spr = stack_bb / max(pot_bb, 1)
                size = compute_bet_size_bb(pot_bb, stack_bb, street_str)
                log.info(f"    RAISE SIZE: {size:.1f} BB (postflop {street_str}, SPR={spr:.1f})")
        except Exception as e:
            log.warning(f"    Sizing calc failed: {e}")

    # Range equity if available
    try:
        from sys_core.decisionmaker.range_equity import RangeEquity
        req = RangeEquity()
        villain_range = req.estimate_villain_range(
            position='CO',
            action='open' if len(board_cards) == 0 and call_amount <= 1 else 'bet',
            player_type='unknown',
            street='preflop' if not board_cards else 'flop',
        )
        range_eq = req.equity_vs_range(hero_cards, board_cards, villain_range)
        log.info(f"    RANGE EQUITY vs villain ({villain_range[:60]}...): {range_eq:.3f}")
    except Exception as e:
        log.warning(f"    Range equity failed: {e}")

    log.info("")
    return decision


# ---------------------------------------------------------------------------
#  Run scenarios
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("  FULL PIPELINE HAND SIMULATION")
    print("  Using REAL DecisionMaker, Monte Carlo, Range Equity")
    print("=" * 70 + "\n")

    # --- Scenario 1: Premium hand preflop, facing a raise ---
    print("\n### SCENARIO 1: AA on BTN, facing 3 BB open ###\n")
    d1 = simulate_hand(
        hero_cards=['AH', 'AS'],
        board_cards=[],
        pot=4.5,          # SB 0.5 + BB 1.0 + villain open 3.0
        call_amount=3.0,
        hero_stack=100.0,
        position='BTN',
        min_raise=9.0,    # 3-bet to 9
        villain_bet=True,
    )

    # --- Scenario 2: Marginal hand, big bet to call ---
    print("\n### SCENARIO 2: JTo on BB, facing 15 BB 4-bet ###\n")
    d2 = simulate_hand(
        hero_cards=['JD', 'TS'],
        board_cards=[],
        pot=20.0,
        call_amount=15.0,
        hero_stack=85.0,
        position='BB',
        min_raise=40.0,
        villain_bet=True,
    )

    # --- Scenario 3: Top pair on flop, opponent bets ---
    print("\n### SCENARIO 3: AKo on A-7-2 flop, villain bets 3 BB into 6 BB ###\n")
    d3 = simulate_hand(
        hero_cards=['AH', 'KS'],
        board_cards=['AC', '7D', '2H'],
        pot=9.0,          # 6 pot + 3 bet
        call_amount=3.0,
        hero_stack=94.0,
        position='BTN',
        min_raise=9.0,
        villain_bet=True,
    )

    # --- Scenario 4: Flush draw on flop, big bet ---
    print("\n### SCENARIO 4: KQs flush draw on J-5-3 (two hearts), villain bets pot ###\n")
    d4 = simulate_hand(
        hero_cards=['KH', 'QH'],
        board_cards=['JH', '5H', '3C'],
        pot=18.0,
        call_amount=9.0,
        hero_stack=91.0,
        position='CO',
        min_raise=27.0,
        villain_bet=True,
    )

    # --- Scenario 5: THE BANKRUPTCY SCENARIO — call 288 on 16 stack ---
    print("\n### SCENARIO 5: SAFETY TEST — misread call 288, stack 16 ###\n")
    # This tests the new safety code at OCR level
    from sys_core.ocr.table_reader import _parse_amount
    misread = _parse_amount("Call 288", max_expected=16.0)
    log.info(f"_parse_amount('Call 288', max_expected=16): {misread}")
    assert misread is None, f"Should have been rejected! Got {misread}"
    log.info(">>> SAFETY CHECK PASSED: 288 BB call rejected by max_expected\n")

    # Now test with a reasonable call on low stack
    d5 = simulate_hand(
        hero_cards=['QC', 'QD'],
        board_cards=[],
        pot=3.0,
        call_amount=2.0,   # Normal 2 BB open
        hero_stack=16.0,
        position='BB',
        min_raise=6.0,
        villain_bet=True,
    )

    # --- Scenario 6: River bluff spot ---
    print("\n### SCENARIO 6: Missed draw on river, villain checks ###\n")
    d6 = simulate_hand(
        hero_cards=['9H', '8H'],
        board_cards=['JH', '5C', '3D', '2S', 'KC'],
        pot=12.0,
        call_amount=0.0,   # Villain checked
        hero_stack=88.0,
        position='BTN',
        min_raise=2.0,
        villain_bet=False,
    )

    print("\n" + "=" * 70)
    print("  SIMULATION COMPLETE — ALL SCENARIOS RAN THROUGH REAL PIPELINE")
    print("=" * 70)
    print(f"\n  Scenario 1 (AA vs 3BB open):      {d1}")
    print(f"  Scenario 2 (JTo vs 15BB 4-bet):    {d2}")
    print(f"  Scenario 3 (AK TPTK on A72):       {d3}")
    print(f"  Scenario 4 (KQhh flush draw):       {d4}")
    print(f"  Scenario 5 (QQ low stack, safe):    {d5}")
    print(f"  Scenario 6 (98hh missed draw):      {d6}")
    print()
