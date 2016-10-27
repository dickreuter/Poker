from unittest import TestCase
import numpy as np
from . import init_table
from decisionmaker.current_hand_memory import CurrentHandPreflopState

class TestReverseTables(TestCase):

    def test_other_players(self):
        t, p, gui_signals, h, logger=init_table('tests/screenshots/1773793_PreFlop_0.png')

        self.assertEqual(t.position_utg_plus,0)
        self.assertEqual(t.dealer_position, 3)
        self.assertEqual(np.isnan(t.first_raiser), True)
        self.assertEqual(np.isnan(t.first_caller), True)

        self.assertEqual(t.other_players[0]['utg_position'], 1)
        self.assertEqual(t.other_players[1]['utg_position'], 2)
        self.assertEqual(t.other_players[2]['utg_position'], 3)
        self.assertEqual(t.other_players[3]['utg_position'], 4)
        self.assertEqual(t.other_players[4]['utg_position'], 5)

        if t.gameStage == 'PreFlop':
            preflop_state = CurrentHandPreflopState()
            preflop_state.update_values(t, d.decision, h)


        for abs_pos in range(6):
            sheet_name=preflop_state.calculate_reverse_table(abs_pos, t.dealer_position, t, p, h)



