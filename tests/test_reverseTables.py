from unittest import TestCase
from . import init_table
from decisionmaker.current_hand_memory import CurrentHandPreflopState
from tools.mongo_manager import StrategyHandler
from unittest.mock import MagicMock
from decisionmaker.decisionmaker import Decision


class TestReverseTables(TestCase):
    def test_preflop_state1(self):
        strategy='snowie1'

        #preflop
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
        d.preflop_override(t, logger, h, p)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Call'
        preflop_state.update_values(t, bot_preflop_decision, h)

        self.assertEqual(t.preflop_sheet_name, '6R4')

        # flop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/76ss.png', strategy=strategy)
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t)

        self.assertEqual('4', sheet_name)

    def test_preflop_state2(self):
        strategy='snowie1'

        #preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/458770525_PreFlop_0.png', strategy=strategy)
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
        d.preflop_override(t, logger, h, p)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Call'
        preflop_state.update_values(t, bot_preflop_decision, h)

        # flop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/458770525_Flop_0.png', strategy=strategy)
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t)

        self.assertEqual('3', sheet_name)


    def test_preflop_fullhouse_river_round2(self):
        strategy = 'pp_nickpick_supersonic2'

        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/1791526_PreFlop_0.png', strategy=strategy)
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
        d.preflop_override(t, logger, h, p)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Call'
        preflop_state.update_values(t, bot_preflop_decision, h)

        # river round 2
        t, p, gui_signals, h, logger = init_table('tests/screenshots/1791526_River_1.png', strategy=strategy)
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t)

        self.assertEqual('12R4C5', sheet_name)

    def test_reversetable_88(self):
        strategy = 'Snowie3'
        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/88.png', strategy=strategy)
        l = MagicMock()
        t.totalPotValue = 0.5
        t.equity = 0.5
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"
        d.__init__(t, h, p, l)
        d.preflop_override(t, logger, h, p)
        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        preflop_state.update_values(t, bot_preflop_decision, h)

        # river round 2
        t, p, gui_signals, h, logger = init_table('tests/screenshots/88F.png', strategy=strategy)
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t)

        self.assertEqual('6R1', sheet_name)



    def test_reversetable_76(self):
        strategy = 'Snowie3'
        # preflop
        t, p, gui_signals, h, logger = init_table('tests/screenshots/76ss.png', strategy=strategy)
        l = MagicMock()
        t.totalPotValue = 0.5
        t.equity = 0.5
        t.checkButton = False
        d = Decision(t, h, p, l)
        t.isHeadsUp = True
        t.gameStage = "PreFlop"
        d.__init__(t, h, p, l)
        d.preflop_override(t, logger, h, p)

        self.assertEqual('6R4', t.preflop_sheet_name)

        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision = 'Bet'
        preflop_state.update_values(t, bot_preflop_decision, h)

        # river round 2
        t, p, gui_signals, h, logger = init_table('tests/screenshots/76s.png', strategy=strategy)
        for abs_pos in range(5):
            if t.other_players[abs_pos]['status'] == 1:
                sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t)

        self.assertEqual('4', sheet_name)