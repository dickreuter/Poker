from unittest import TestCase
from unittest.mock import MagicMock

import pytest

from poker.decisionmaker.current_hand_memory import CurrentHandPreflopState
from poker.decisionmaker.decisionmaker import Decision
from poker.tests import init_table
from poker.tools.strategy_handler import StrategyHandler


def reverse_init(t, h, p):
    lst = MagicMock()
    t.totalPotValue = 0.5
    t.equity = 0.5
    t.checkButton = False
    d = Decision(t, h, p, lst)
    t.isHeadsUp = True
    t.gameStage = "PreFlop"
    d.__init__(t, h, p, lst)
    d.preflop_table_analyser(t, h, p)
    return d

@pytest.mark.skip()
class TestReverseTables(TestCase):
    def no_test_preflop_state1(self):
        strategy = 'snowie1'

        # preflop
        t, p, _, h, _ = init_table('tests/screenshots/76s.png', strategy=strategy)
        p = StrategyHandler()
        p.read_strategy(strategy)
        lst = MagicMock()
        t.totalPotValue = 0.5
        t.equity = 0.5
        t.checkButton = False
        d = Decision(t, h, p, lst)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"
        d.__init__(t, h, p, lst)
        d.preflop_table_analyser(t, h, p)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Call'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        self.assertEqual(t.preflop_sheet_name, '6R4')

        # flop
        t, p, _, h, _ = init_table('tests/screenshots/76ss.png', strategy=strategy)
        sheet_name = ''
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)

        self.assertEqual('4', sheet_name)

    def no_test_preflop_state2(self):
        strategy = 'snowie1'

        # preflop
        t, p, _, h, _ = init_table('tests/screenshots/458770525_PreFlop_0.png', strategy=strategy)
        reverse_init(t, h, p)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Call'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # flop
        t, p, _, h, _ = init_table('tests/screenshots/458770525_Flop_0.png', strategy=strategy)
        sheet_name = ''
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)

        self.assertEqual('3', sheet_name)

    # todo: check if this is really a fail
    # def test_preflop_fullhouse_river_round2(self):
    #     strategy = 'pp_nickpick_supersonic2'
    #
    #     # preflop
    #     t, p, _, h, _ = init_table('tests/screenshots/1791526_PreFlop_0.png', strategy=strategy)
    #     d = reverse_init(t, h, p, _)
    #     preflop_state = CurrentHandPreflopState()
    #     bot_preflop_decision = 'Call'
    #     preflop_state.update_values(t, bot_preflop_decision, h, d)
    #
    #     # river round 2
    #     t, p, _, h, _ = init_table('tests/screenshots/1791526_River_1.png', strategy=strategy)
    #     for abs_pos in range(5):
    #         if t.other_players[abs_pos]['status'] == 1:
    #             sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
    #
    #     self.assertEqual('32C5', sheet_name)

    def no_test_reversetable_88(self):
        strategy = 'Snowie3'
        # preflop
        t, p, _, h, _ = init_table('tests/screenshots/88.png', strategy=strategy)
        reverse_init(t, h, p)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # river round 2
        t, p, _, h, _ = init_table('tests/screenshots/88F.png', strategy=strategy)
        sheet_name = ''
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)

        self.assertEqual('6R1', sheet_name)

    def no_test_reversetable_76(self):
        strategy = 'Snowie3'
        # preflop
        t, p, _, h, _ = init_table('tests/screenshots/76ss.png', strategy=strategy)
        d = reverse_init(t, h, p)
        d.preflop_table_analyser(t, h, p)

        self.assertEqual('6R4', t.preflop_sheet_name)

        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Call'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # river round 2
        t, p, _, h, _ = init_table('tests/screenshots/76s.png', strategy=strategy)
        sheet_name = ''
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)

        self.assertEqual('4', sheet_name)

    def no_test_ranges(self):
        # preflop
        t, p, _, h, _ = init_table('tests/screenshots/709250829_PreFlop_0.png')
        d = reverse_init(t, h, p)
        d.preflop_table_analyser(t, h, p)

        self.assertEqual('3R1', t.preflop_sheet_name)

        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Call'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # river round 2
        t, p, _, h, _ = init_table('tests/screenshots/709250829_Flop_0.png')
        sheet_name = ''
        ranges = ''
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                ranges = preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)

        self.assertEqual('1', sheet_name)
        self.assertEqual(38, len(ranges))

    def no_test_ranges_2nd_round(self):
        # preflop
        t, p, _, h, _ = init_table('tests/screenshots/709250829_PreFlop_0.png')
        reverse_init(t, h, p)

        self.assertEqual('3R1', t.preflop_sheet_name)

        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # flop after 2nd round preflop
        t, p, _, h, _ = init_table('tests/screenshots/709250829_Flop_0.png')
        sheet_name = ''
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)

        self.assertEqual('12R3', sheet_name)
        # self.assertEqual(38, len(ranges))

    def no_test_ranges_2nd_call(self):
        # preflop
        t, p, _, h, _ = init_table('tests/screenshots/AJ2.png')

        reverse_init(t, h, p)

        self.assertEqual('6R3', t.preflop_sheet_name)

        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # flop after 2nd round preflop
        t, p, _, h, _ = init_table('tests/screenshots/AJs.png')
        sheet_name = ''
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)

        self.assertEqual('32R6', sheet_name)
        self.assertEqual("Call", preflop_state.range_column_name)

    def no_test_ranges_call_column(self):
        # preflop
        t, p, _, h, _ = init_table('tests/screenshots/KQ2.png')
        reverse_init(t, h, p)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)
        t, p, _, h, _ = init_table('tests/screenshots/KQ.png')
        sheet_name = ''
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)

        self.assertEqual('42R5', sheet_name)
        self.assertEqual("Call", preflop_state.range_column_name)

    def no_test_incorrect_second_round(self):
        # preflop
        t, p, _, h, _ = init_table('tests/screenshots/3R12.png')
        reverse_init(t, h, p)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)
        t, p, _, h, _ = init_table('tests/screenshots/3R1.png')
        reverse_sheet_names = []
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)
                reverse_sheet_names.append(sheet_name)

        self.assertEqual('3R1', reverse_sheet_names[0])
        self.assertEqual('6R1', reverse_sheet_names[1])
        self.assertEqual("Call", preflop_state.range_column_name)
