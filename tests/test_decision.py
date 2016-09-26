from unittest import TestCase
from . import init_table
from decisionmaker.decisionmaker3 import Decision
from decisionmaker.decisionmaker3 import DecisionTypes
from unittest.mock import MagicMock

class TestDecision(TestCase):
    def test_bluff(self):
        t, p, gui_signals, h,logger = init_table('tests/751235173_PreFlop_0.png')
        l = MagicMock()
        t.totalPotValue=0.5
        t.equity=0.5
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
