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

        self.assertEqual(t.other_players[0]['utg_position'], 1)
        self.assertEqual(t.other_players[1]['utg_position'], 2)
        self.assertEqual(t.other_players[2]['utg_position'], 3)
        self.assertEqual(t.other_players[3]['utg_position'], 4)
        self.assertEqual(t.other_players[4]['utg_position'], 5)

    def test_other_players2(self):
        t, p, gui_signals, h, logger=init_table('tests/751235173_PreFlop_0.png')

        self.assertEqual(t.position_utg_plus, 5)
        self.assertEqual(t.dealer_position, 4)
        self.assertEqual(t.first_raiser, 3)
        self.assertEqual(np.isnan(t.first_caller), True)

        self.assertEqual(t.other_players[0]['utg_position'], 0)
        self.assertEqual(t.other_players[1]['utg_position'], 1)
        self.assertEqual(t.other_players[2]['utg_position'], 2)
        self.assertEqual(t.other_players[3]['utg_position'], 3)
        self.assertEqual(t.other_players[4]['utg_position'], 4)


    def test_other_players3(self):
        t, p, gui_signals, h, logger=init_table('tests/691119677_PreFlop_0.png')

        self.assertEqual(t.position_utg_plus, 2)
        self.assertEqual(t.dealer_position, 1)
        self.assertEqual(t.first_raiser_utg, 0)
        self.assertEqual(t.first_caller_utg, 1)
        self.assertEqual(t.playersBehind, 2)
        self.assertEqual(t.playersAhead, 3)

        self.assertEqual(t.other_players[0]['utg_position'], 3)
        self.assertEqual(t.other_players[1]['utg_position'], 4)
        self.assertEqual(t.other_players[2]['utg_position'], 5)
        self.assertEqual(t.other_players[3]['utg_position'], 0)
        self.assertEqual(t.other_players[4]['utg_position'], 1)


    def test_other_players4(self):
        t, p, gui_signals, h, logger=init_table('tests/467381034_PreFlop_0.png')

        self.assertEqual(t.position_utg_plus, 2)
        self.assertEqual(t.dealer_position, 1)
        self.assertEqual(t.first_raiser_utg, 1)
        self.assertEqual(np.isnan(t.first_caller_utg), True)
        self.assertEqual(t.playersBehind, 1)
        self.assertEqual(t.playersAhead, 3)
        self.assertEqual(t.other_players[0]['pot'], '')
        self.assertEqual(t.other_players[1]['pot'], 0.02)
        self.assertEqual(t.other_players[2]['pot'], 0.04)
        self.assertEqual(t.other_players[3]['pot'], '')
        self.assertEqual(t.other_players[4]['pot'], 0.12)

    def test_other_players5(self):
        t, p, gui_signals, h, logger = init_table('tests/496504338_PreFlop_0.png')
        self.assertEqual(t.other_players[0]['pot'], 0.04)
        self.assertEqual(t.other_players[1]['pot'], 0.08)
        self.assertEqual(t.other_players[2]['pot'], '')
        self.assertEqual(t.other_players[3]['pot'], '')
        self.assertEqual(t.other_players[4]['pot'], '')

    def test_other_players6(self):
        t, p, gui_signals, h, logger = init_table('tests/499121363_PreFlop_4.png')
        self.assertEqual(t.other_players[0]['pot'], '')
        self.assertEqual(t.other_players[1]['pot'], '')
        self.assertEqual(t.other_players[2]['pot'], 0.28)
        self.assertEqual(t.other_players[3]['pot'], 0.02)
        self.assertEqual(t.other_players[4]['pot'], 0.04)

    def test_flop(self):
        t, p, gui_signals, h, logger=init_table('tests/307380116_Flop_0.png')
        self.assertEqual(t.playersBehind, 1)
        self.assertEqual(t.playersAhead, 0)

        t, p, gui_signals, h, logger = init_table('tests/712154510_Flop_0.png')
        self.assertEqual(t.playersBehind, 0)
        self.assertEqual(t.playersAhead, 1)
        self.assertEqual(t.isHeadsUp,True)

    def test_preflop_recognition(self):
        t, p, gui_signals, h, logger = init_table('tests/308189727_PreFlop_0.png')
        self.assertEqual(t.other_players[0]['pot'], 0.02)
        self.assertEqual(t.other_players[1]['pot'], 0.04)
        self.assertEqual(t.other_players[2]['pot'], 0.12)
        self.assertEqual(t.other_players[3]['pot'], '')
        self.assertEqual(t.other_players[4]['pot'], '')

    def test_second_round_table(self):
        t, p, gui_signals, h, logger = init_table('tests/107232845_PreFlop_1.png',round_number=1)
        self.assertEqual(t.position_utg_plus, 1)
        self.assertEqual(t.dealer_position, 2)
        self.assertEqual(t.first_raiser, 2)
        self.assertEqual(np.isnan(t.second_raiser), True)
        self.assertEqual(np.isnan(t.first_caller), True)
        self.assertEqual(t.bot_pot, 0.09)

    def test_second_round_table2(self):
        t, p, gui_signals, h, logger = init_table('tests/378278828_PreFlop_1.png',round_number=1)
        self.assertEqual(t.position_utg_plus, 3)
        self.assertEqual(t.dealer_position, 0)
        self.assertEqual(t.first_raiser, 4)
        self.assertEqual(np.isnan(t.second_raiser), True)
        self.assertEqual(np.isnan(t.first_caller), True)
        self.assertEqual(t.bot_pot, 0.22)


    def test_call_raise(self):
        t, p, gui_signals, h, logger = init_table('tests/43457283_PreFlop_0.png')
        self.assertEqual(t.other_players[0]['pot'], '')
        self.assertEqual(t.other_players[1]['pot'], 0.04)
        self.assertEqual(t.other_players[2]['pot'], 0.16)
        self.assertEqual(t.other_players[3]['pot'], '')
        self.assertEqual(t.other_players[4]['pot'], 0.02)


    def test_call_raise_2(self):
        t, p, gui_signals, h, logger = init_table('tests/897376414_PreFlop_1.png')
        self.assertEqual(t.other_players[0]['pot'], '')
        self.assertEqual(t.other_players[1]['pot'], 0.3)
        self.assertEqual(t.other_players[2]['pot'], '')
        self.assertEqual(t.other_players[3]['pot'], 0.02)
        self.assertEqual(t.other_players[4]['pot'], 0.04)