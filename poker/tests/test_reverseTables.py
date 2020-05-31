from unittest import TestCase
from unittest.mock import MagicMock

from decisionmaker.decisionmaker import Decision

from poker.decisionmaker.current_hand_memory import CurrentHandPreflopState
from poker.tools.mongo_manager import StrategyHandler
from . import init_table


def reverse_init(t,h,p,logger):
    l = MagicMock()
    t.totalPotValue = 0.5
    t.equity = 0.5
    t.checkButton = False
    d = Decision(t, h, p, l)
    t.isHeadsUp = True
    t.gameStage = "PreFlop"
    d.__init__(t, h, p, l)
    d.preflop_table_analyser(t, logger, h, p)
    return d

class TestReverseTables(TestCase):
    def test_preflop_state1(self):
        strategy = 'snowie1'

        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/76s.png', strategy=strategy)
        p = StrategyHandler()
        p.read_strategy(strategy)
        l = MagicMock()
        t.totalPotValue = 0.5
        t.equity = 0.5
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"
        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Call'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        self.assertEqual(t.preflop_sheet_name, '6R4')

        # flop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/76ss.png', strategy=strategy)
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)

        self.assertEqual('4', sheet_name)

    def test_preflop_state2(self):
        strategy = 'snowie1'

        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/458770525_PreFlop_0.png', strategy=strategy)
        d = reverse_init(t, h, p, logger)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Call'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # flop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/458770525_Flop_0.png', strategy=strategy)
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)

        self.assertEqual('3', sheet_name)

    # todo: check if this is really a fail
    # def test_preflop_fullhouse_river_round2(self):
    #     strategy = 'pp_nickpick_supersonic2'
    #
    #     # preflop
    #     t, p, gui_signals, h, logger = init_table('tests/screenshots/1791526_PreFlop_0.png', strategy=strategy)
    #     d = reverse_init(t, h, p, logger)
    #     preflop_state = CurrentHandPreflopState()
    #     bot_preflop_decision = 'Call'
    #     preflop_state.update_values(t, bot_preflop_decision, h, d)
    #
    #     # river round 2
    #     t, p, gui_signals, h, logger = init_table('tests/screenshots/1791526_River_1.png', strategy=strategy)
    #     for abs_pos in range(5):
    #         if t.other_players[abs_pos]['status'] == 1:
    #             sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
    #
    #     self.assertEqual('32C5', sheet_name)

    def test_reversetable_88(self):
        strategy = 'Snowie3'
        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/88.png', strategy=strategy)
        d = reverse_init(t, h, p, logger)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # river round 2
        t, p, gui_signals, h, logger = init_table('tests/screenshots/88F.png', strategy=strategy)
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)

        self.assertEqual('6R1', sheet_name)

    def test_reversetable_76(self):
        strategy = 'Snowie3'
        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/76ss.png', strategy=strategy)
        d = reverse_init(t, h, p, logger)
        d.preflop_table_analyser(t, logger, h, p)

        self.assertEqual('6R4', t.preflop_sheet_name)

        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Call'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # river round 2
        t, p, gui_signals, h, logger = init_table('tests/screenshots/76s.png', strategy=strategy)
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)

        self.assertEqual('4', sheet_name)

    def test_ranges(self):
        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/709250829_PreFlop_0.png')
        d = reverse_init(t, h, p, logger)
        d.preflop_table_analyser(t, logger, h, p)

        self.assertEqual('3R1', t.preflop_sheet_name)

        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Call'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # river round 2
        t, p, gui_signals, h, logger = init_table('tests/screenshots/709250829_Flop_0.png')
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                ranges = preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)

        self.assertEqual('1', sheet_name)
        self.assertEqual(38, len(ranges))


    def test_ranges_2nd_round(self):
        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/709250829_PreFlop_0.png')
        d = reverse_init(t, h, p, logger)

        self.assertEqual('3R1', t.preflop_sheet_name)

        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # flop after 2nd round preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/709250829_Flop_0.png')
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                ranges = preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)

        self.assertEqual('12R3', sheet_name)
        #self.assertEqual(38, len(ranges))

    def test_ranges_2nd_call(self):
        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/AJ2.png')

        d=reverse_init(t,h,p,logger)

        self.assertEqual('6R3', t.preflop_sheet_name)

        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)

        # flop after 2nd round preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/AJs.png')
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                ranges = preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)

        self.assertEqual('32R6', sheet_name)
        self.assertEqual("Call", preflop_state.range_column_name)

    def test_ranges_call_column(self):
        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/KQ2.png')
        reverse_init(t,h,p,logger)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)
        t, p, gui_signals, h, logger = init_table('tests/screenshots/KQ.png')
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                ranges = preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)

        self.assertEqual('42R5', sheet_name)
        self.assertEqual("Call", preflop_state.range_column_name)

    def test_incorrect_second_round(self):
        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/3R12.png')
        reverse_init(t,h,p,logger)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        d = MagicMock()
        d = MagicMock()
        preflop_state.update_values(t, bot_preflop_decision, h, d)
        t, p, gui_signals, h, logger = init_table('tests/screenshots/3R1.png')
        reverse_sheet_names=[]
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                ranges = preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)
                reverse_sheet_names.append(sheet_name)

        self.assertEqual('3R1', reverse_sheet_names[0])
        self.assertEqual('6R1', reverse_sheet_names[1])
        self.assertEqual("Call", preflop_state.range_column_name)

