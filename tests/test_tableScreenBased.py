from unittest import TestCase
import numpy as np
from . import init_table

class TestTableScreenBased(TestCase):
    def test_game_number(self):
        t, p, gui_signals, h, logger = init_table('tests/1773793_PreFlop_0.png')
        t.get_game_number_on_screen()
        self.assertEqual(t.game_number_on_screen,"15,547,039,153")

    def test_other_players1(self):
        t, p, gui_signals, h, logger=init_table('tests/1773793_PreFlop_0.png')

        self.assertEqual(t.position_utg_plus,0)
        self.assertEqual(t.dealer_position, 3)
        self.assertEqual(np.isnan(t.first_raiser), True)
        self.assertEqual(np.isnan(t.first_caller), True)

        self.assertEqual(t.other_players['0']['utg_position'], 1)
        self.assertEqual(t.other_players['1']['utg_position'], 2)
        self.assertEqual(t.other_players['2']['utg_position'], 3)
        self.assertEqual(t.other_players['3']['utg_position'], 4)
        self.assertEqual(t.other_players['4']['utg_position'], 5)

    def test_other_players2(self):
        t, p, gui_signals, h, logger=init_table('tests/751235173_PreFlop_0.png')

        self.assertEqual(t.position_utg_plus, 5)
        self.assertEqual(t.dealer_position, 4)
        self.assertEqual(t.first_raiser, 3)
        self.assertEqual(np.isnan(t.first_caller), True)

        self.assertEqual(t.other_players['0']['utg_position'], 0)
        self.assertEqual(t.other_players['1']['utg_position'], 1)
        self.assertEqual(t.other_players['2']['utg_position'], 2)
        self.assertEqual(t.other_players['3']['utg_position'], 3)
        self.assertEqual(t.other_players['4']['utg_position'], 4)


    def test_other_players3(self):
        t, p, gui_signals, h, logger=init_table('tests/691119677_PreFlop_0.png')

        self.assertEqual(t.position_utg_plus, 2)
        self.assertEqual(t.dealer_position, 1)
        self.assertEqual(t.first_raiser_utg, 0)
        self.assertEqual(t.first_caller_utg, 1)
        self.assertEqual(t.playersBehind, 2)
        self.assertEqual(t.playersAhead, 3)

        self.assertEqual(t.other_players['0']['utg_position'], 3)
        self.assertEqual(t.other_players['1']['utg_position'], 4)
        self.assertEqual(t.other_players['2']['utg_position'], 5)
        self.assertEqual(t.other_players['3']['utg_position'], 0)
        self.assertEqual(t.other_players['4']['utg_position'], 1)


    def test_flop(self):
        t, p, gui_signals, h, logger=init_table('tests/307380116_Flop_0.png')
        self.assertEqual(t.playersBehind, 1)
        self.assertEqual(t.playersAhead, 0)

        t, p, gui_signals, h, logger = init_table('tests/712154510_Flop_0.png')
        self.assertEqual(t.playersBehind, 0)
        self.assertEqual(t.playersAhead, 1)
        self.assertEqual(t.isHeadsUp,True)

