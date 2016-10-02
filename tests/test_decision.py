from unittest import TestCase
from . import init_table
from decisionmaker.decisionmaker import Decision
from decisionmaker.decisionmaker import DecisionTypes
from unittest.mock import MagicMock
from mongo_manager import StrategyHandler

class TestDecision(TestCase):
    def test_bluff(self):
        t, p, gui_signals, h,logger = init_table('tests/751235173_PreFlop_0.png')
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
        t, p, gui_signals, h,logger = init_table('tests/467381034_PreFlop_0.png')
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
        self.assertEqual(d.preflop_adjustment, 0.07)
