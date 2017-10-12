from unittest import TestCase
from unittest.mock import MagicMock

import numpy as np

from poker.decisionmaker.decisionmaker import Decision
from poker.decisionmaker.decisionmaker import DecisionTypes
from poker.tools import StrategyHandler
from . import init_table


class TestDecision(TestCase):
    def test_bluff(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/751235173_PreFlop_0.png')
        p = StrategyHandler()
        p.read_strategy('Pokemon')
        l = MagicMock()
        t.totalPotValue = 0.5
        t.equity = 0.7
        t.checkButton = True
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "Flop"
        p.selected_strategy['FlopBluffMinEquity'] = 0.3
        p.selected_strategy['FlopBluff'] = "1"

        d.decision = DecisionTypes.check
        t.playersAhead = 0
        d.bluff(t, p, h)
        self.assertEqual(d.decision, DecisionTypes.bet_bluff)

        d.decision = DecisionTypes.check
        t.playersAhead = 1
        d.bluff(t, p, h)
        self.assertEqual(d.decision, DecisionTypes.check)

    def test_position_adjustment(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/467381034_PreFlop_0.png', strategy='Pokemon4')
        t.gameStage="PreFlop"
        p = StrategyHandler()
        p.read_strategy('Nickpick12')
        l = MagicMock()
        t.checkButton = True
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "Flop"
        p.selected_strategy['FlopBluffMinEquity'] = 0.3
        p.selected_strategy['FlopBluff'] = "1"
        p.selected_strategy['pre_flop_equity_reduction_by_position'] = 0.02

        d.__init__(t, h, p, l)
        self.assertAlmostEqual(d.preflop_adjustment, 0.1, delta=0.01)

    def test_preflop_round2(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/378278828_PreFlop_1.png', round_number=1)
        p = StrategyHandler()
        p.read_strategy('Pokemon4')
        l = MagicMock()
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"

        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)
        self.assertEqual(t.first_raiser_utg, 2)
        # self.assertEqual(t.preflop_sheet_name, '42R3')

    def test_preflop_round2_2(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/107232845_PreFlop_1.png', round_number=1)
        p = StrategyHandler()
        p.read_strategy('Pokemon4')
        l = MagicMock()
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"

        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)
        self.assertEqual(t.first_raiser_utg, 4)
        # self.assertEqual(t.preflop_sheet_name, '22R5')

    def test_preflop_round2_3(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/897376414_PreFlop_1.png', round_number=1)
        p = StrategyHandler()
        p.read_strategy('Pokemon4')
        l = MagicMock()
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"

        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)
        self.assertEqual(t.first_raiser_utg, 2)
        # self.assertEqual(t.preflop_sheet_name, '12R3')

    def test_preflop_call_before_raise(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/1791526_PreFlop_0.png', round_number=0)
        p = StrategyHandler()
        p.read_strategy('Pokemon4')
        l = MagicMock()
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"

        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)

        self.assertEqual(t.first_raiser, 2)
        self.assertEqual(t.second_raiser, 4)

        self.assertEqual(t.preflop_sheet_name, '6R5C3')

    def incorrect_second_raiser(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/Q9o-first_raiser.png', strategy='Snowie3')
        l = MagicMock()
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"

        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)

        self.assertEqual(t.first_raiser_utg, 3)
        self.assertEqual(np.isnan(t.second_raiser_utg), True)

        self.assertEqual(t.preflop_sheet_name, '5R4')

    def incorrect_preflop_table1(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/K9o.png', strategy='Snowie3')
        l = MagicMock()
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"
        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)

        self.assertEqual(t.first_raiser_utg, 4)
        self.assertEqual(np.isnan(t.second_raiser_utg), True)
        self.assertEqual(t.preflop_sheet_name, '6R5')


    def incorrect_preflop_table2(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/3Ts.png', strategy='Snowie3')
        l = MagicMock()
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"
        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)

        self.assertEqual(t.preflop_sheet_name, '6R1C2')

    def second_round_with_raiser(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/QQ.png', strategy='Snowie3', round_number=1)
        l = MagicMock()
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"
        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)

        self.assertEqual(t.preflop_sheet_name, '22R6')

    def first_round_2R1(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/JJ.png', strategy='Snowie3', round_number=0)
        l = MagicMock()
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"
        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)

        self.assertEqual(t.preflop_sheet_name, '2R1')

    def first_round_4R1(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/AJ.png', strategy='Snowie3', round_number=0)
        l = MagicMock()
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"
        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)

        self.assertEqual(t.preflop_sheet_name, '4R1')

    def first_round_98h(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/98h.png', strategy='Snowie3', round_number=0)
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"
        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)

        self.assertEqual(t.preflop_sheet_name, '4R3')

    def sheet_12R4R6(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/12R4R6.png', round_number=1)
        l = MagicMock()
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"
        d.__init__(t, h, p, l)
        d.preflop_table_analyser(t, logger, h, p)

        self.assertEqual(t.preflop_sheet_name, '12R4R6')
