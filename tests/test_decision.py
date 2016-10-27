from unittest import TestCase
from unittest.mock import MagicMock

from decisionmaker.decisionmaker import Decision
from decisionmaker.decisionmaker import DecisionTypes
from tools.mongo_manager import StrategyHandler
from . import init_table


class TestDecision(TestCase):
    def test_bluff(self):
        t, p, gui_signals, h,logger = init_table('tests/screenshots/751235173_PreFlop_0.png')
        p = StrategyHandler()
        p.read_strategy('Pokemon')
        l = MagicMock()
        t.totalPotValue=0.5
        t.equity=0.7
        t.checkButton=True
        d=Decision(t, h, p, logger, l)
        t.isHeadsUp=True
        t.gameStage="Flop"
        p.selected_strategy['FlopBluffMinEquity']=0.3
        p.selected_strategy['FlopBluff']="1"

        d.decision=DecisionTypes.check
        t.playersAhead = 0
        d.bluff(t,p,h,logger)
        self.assertEqual(d.decision,DecisionTypes.bet_bluff)

        d.decision=DecisionTypes.check
        t.playersAhead = 1
        d.bluff(t,p,h,logger)
        self.assertEqual(d.decision,DecisionTypes.check)

    def test_position_adjustment(self):
        t, p, gui_signals, h,logger = init_table('tests/screenshots/467381034_PreFlop_0.png')
        p = StrategyHandler()
        p.read_strategy('Nickpick12')
        l = MagicMock()
        t.totalPotValue=0.5
        t.equity=0.5
        t.checkButton=True
        d=Decision(t, h, p, logger, l)
        t.isHeadsUp=True
        t.gameStage="Flop"
        p.selected_strategy['FlopBluffMinEquity']=0.3
        p.selected_strategy['FlopBluff']="1"
        p.selected_strategy['pre_flop_equity_reduction_by_position'] = 0.02

        d.__init__(t, h, p, logger, l)
        self.assertEqual(d.preflop_adjustment, 0.1)


    def test_preflop_round2(self):
        t, p, gui_signals, h,logger = init_table('tests/screenshots/378278828_PreFlop_1.png',round_number=1)
        p = StrategyHandler()
        p.read_strategy('Strategy100')
        l = MagicMock()
        t.totalPotValue=0.5
        t.equity=0.5
        t.checkButton=False
        d=Decision(t, h, p, logger, l)
        t.isHeadsUp=True
        t.gameStage="PreFlop"

        d.__init__(t, h, p, logger, l)
        d.preflop_override(t,logger,h,p)

        self.assertEqual(d.preflop_sheet_name, '42R3')

    def test_preflop_round2_2(self):
        t, p, gui_signals, h,logger = init_table('tests/screenshots/107232845_PreFlop_1.png',round_number=1)
        p = StrategyHandler()
        p.read_strategy('Strategy100')
        l = MagicMock()
        t.totalPotValue=0.5
        t.equity=0.5
        t.checkButton=False
        d=Decision(t, h, p, logger, l)
        t.isHeadsUp=True
        t.gameStage="PreFlop"

        d.__init__(t, h, p, logger, l)
        d.preflop_override(t,logger,h,p)

        self.assertEqual(d.preflop_sheet_name, '22R5')


    def test_preflop_round2_3(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/897376414_PreFlop_1.png', round_number=1)
        p = StrategyHandler()
        p.read_strategy('Strategy100')
        l = MagicMock()
        t.totalPotValue = 0.5
        t.equity = 0.5
        t.checkButton = False
        d = Decision(t, h, p, logger, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"

        d.__init__(t, h, p, logger, l)
        d.preflop_override(t, logger, h, p)

        self.assertEqual(d.preflop_sheet_name, '12R3')


