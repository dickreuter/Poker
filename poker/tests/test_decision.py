from unittest import TestCase
from unittest.mock import MagicMock

import numpy as np
import pytest

from poker.decisionmaker.decisionmaker import Decision
from poker.decisionmaker.decisionmaker import DecisionTypes
from poker.tests import init_table
from poker.tools.strategy_handler import StrategyHandler

# pylint: disable=unused-variable

@pytest.mark.skip
class TestDecision(TestCase):
    def no_test_bluff(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/751235173_PreFlop_0.png')
        strategy = StrategyHandler()
        strategy.read_strategy('Pokemon')
        l = MagicMock()
        table.totalPotValue = 0.5
        table.equity = 0.7
        table.checkButton = True
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "Flop"
        strategy.selected_strategy['FlopBluffMinEquity'] = 0.3
        strategy.selected_strategy['FlopBluff'] = "1"

        d.decision = DecisionTypes.check
        table.playersAhead = 0
        d.bluff(table, strategy, history)
        self.assertEqual(d.decision, DecisionTypes.bet_bluff)

        d.decision = DecisionTypes.check
        table.playersAhead = 1
        d.bluff(table, strategy, history)
        self.assertEqual(d.decision, DecisionTypes.check)

    def no_test_position_adjustment(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/467381034_PreFlop_0.png', strategy='Pokemon4')
        table.gameStage = "PreFlop"
        strategy = StrategyHandler()
        strategy.read_strategy('Nickpick12')
        l = MagicMock()
        table.checkButton = True
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "Flop"
        strategy.selected_strategy['FlopBluffMinEquity'] = 0.3
        strategy.selected_strategy['FlopBluff'] = "1"
        strategy.selected_strategy['pre_flop_equity_reduction_by_position'] = 0.02

        d.__init__(table, history, strategy, l)
        self.assertAlmostEqual(d.preflop_adjustment, 0.1, delta=0.01)

    def no_test_preflop_round2(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/378278828_PreFlop_1.png', round_number=1)
        strategy = StrategyHandler()
        strategy.read_strategy('Pokemon4')
        l = MagicMock()
        table.checkButton = False
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"

        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)
        self.assertEqual(table.first_raiser_utg, 2)
        # self.assertEqual(table.preflop_sheet_name, '42R3')

    def no_test_preflop_round2_2(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/107232845_PreFlop_1.png', round_number=1)
        strategy = StrategyHandler()
        strategy.read_strategy('Pokemon4')
        l = MagicMock()
        table.checkButton = False
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"

        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)
        self.assertEqual(table.first_raiser_utg, 4)
        # self.assertEqual(table.preflop_sheet_name, '22R5')

    def no_test_preflop_round2_3(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/897376414_PreFlop_1.png', round_number=1)
        strategy = StrategyHandler()
        strategy.read_strategy('Pokemon4')
        l = MagicMock()
        table.checkButton = False
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"

        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)
        self.assertEqual(table.first_raiser_utg, 2)
        # self.assertEqual(t.preflop_sheet_name, '12R3')

    def no_test_preflop_call_before_raise(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/1791526_PreFlop_0.png', round_number=0)
        strategy = StrategyHandler()
        strategy.read_strategy('Pokemon4')
        l = MagicMock()
        table.checkButton = False
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"

        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)

        self.assertEqual(table.first_raiser, 2)
        self.assertEqual(table.second_raiser, 4)

        self.assertEqual(table.preflop_sheet_name, '6R5C3')

    def incorrect_second_raiser(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/Q9o-first_raiser.png', strategy='Snowie3')
        l = MagicMock()
        table.checkButton = False
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"

        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)

        self.assertEqual(table.first_raiser_utg, 3)
        self.assertEqual(np.isnan(table.second_raiser_utg), True)

        self.assertEqual(table.preflop_sheet_name, '5R4')

    def incorrect_preflop_table1(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/K9o.png', strategy='Snowie3')
        l = MagicMock()
        table.checkButton = False
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"
        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)

        self.assertEqual(table.first_raiser_utg, 4)
        self.assertEqual(np.isnan(table.second_raiser_utg), True)
        self.assertEqual(table.preflop_sheet_name, '6R5')

    def incorrect_preflop_table2(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/3Ts.png', strategy='Snowie3')
        l = MagicMock()
        table.checkButton = False
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"
        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)

        self.assertEqual(table.preflop_sheet_name, '6R1C2')

    def second_round_with_raiser(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/QQ.png', strategy='Snowie3', round_number=1)
        l = MagicMock()
        table.checkButton = False
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"
        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)

        self.assertEqual(table.preflop_sheet_name, '22R6')

    def first_round_2R1(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/JJ.png', strategy='Snowie3', round_number=0)
        l = MagicMock()
        table.checkButton = False
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"
        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)

        self.assertEqual(table.preflop_sheet_name, '2R1')

    def first_round_4R1(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/AJ.png', strategy='Snowie3', round_number=0)
        l = MagicMock()
        table.checkButton = False
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"
        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)

        self.assertEqual(table.preflop_sheet_name, '4R1')

    def first_round_98h(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/98h.png', strategy='Snowie3', round_number=0)
        table.checkButton = False
        l = MagicMock()
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"
        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)

        self.assertEqual(table.preflop_sheet_name, '4R3')

    def sheet_12R4R6(self):
        table, strategy, _, history, _ = init_table('tests/screenshots/12R4R6.png', round_number=1)
        l = MagicMock()
        table.checkButton = False
        d = Decision(table, history, strategy, l)
        table.isHeadsUp = True
        table.gameStage = "PreFlop"
        d.__init__(table, history, strategy, l)
        d.preflop_table_analyser(table, history, strategy)

        self.assertEqual(table.preflop_sheet_name, '12R4R6')
