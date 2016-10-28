from unittest import TestCase
import numpy as np
from . import init_table
from decisionmaker.current_hand_memory import CurrentHandPreflopState

class TestReverseTables(TestCase):

    def test_preflop_state1(self):
        t, p, gui_signals, h, logger=init_table('tests/screenshots/307380116_Flop_0.png')

        preflop_state = CurrentHandPreflopState()
        bot_preflop_decision='Call'
        t.bot_pot=0.04
        t.first_raiser=1
        t.second_raiser=2
        t.first_caller=3
        t.bigBlind=0.04
        preflop_state.update_values(t, bot_preflop_decision, h)

        abs_pos=2
        sheet_name=preflop_state.get_reverse_sheetname(abs_pos, t)

        self.assertEqual(t.other_players[2]['utg_position']+1, 5)
        self.assertEqual('5R1R2C2C3', sheet_name)

