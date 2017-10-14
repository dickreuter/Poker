from unittest import TestCase
import numpy as np
from . import init_table


class TestTableScreenBased(TestCase):
    def test1(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/test1.png')
        t.get_game_number_on_screen(h)
        self.assertEqual(h.game_number_on_screen, "16543145686")
        self.assertEqual(t.mycards, ['QD', 'QS'])
        self.assertEqual(t.checkButton, True)
        self.assertEqual(t.callButton, False)
        self.assertEqual(t.bet_button_found, True)
        self.assertEqual(t.cardsOnTable, ['KH', '3C', 'TS'])

    def test2(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/test2.png')
        t.get_game_number_on_screen(h)
        self.assertEqual(h.game_number_on_screen, "16547195085")
        self.assertEqual(t.mycards, ['3H', 'TS'])
        self.assertEqual(t.checkButton, False)
        self.assertEqual(t.callButton, True)
        self.assertEqual(t.bet_button_found, True)
        self.assertEqual(t.cardsOnTable, [])
        self.assertEqual(t.currentCallValue, 0.05)
        self.assertEqual(t.other_players[0]['pot'], '')
        self.assertEqual(t.other_players[1]['pot'], '')
        self.assertEqual(t.other_players[2]['pot'], 0.10)
        self.assertEqual(t.other_players[3]['pot'], '')
        self.assertEqual(t.other_players[4]['pot'], 0.02)

    def test3(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/test3.png')
        t.get_game_number_on_screen(h)
        self.assertEqual(t.mycards, ['3H', 'TS'])
        self.assertEqual(t.checkButton, True)
        self.assertEqual(t.callButton, False)
        self.assertEqual(t.bet_button_found, True)
        self.assertEqual(t.cardsOnTable, ['5C', 'AS', '5H', 'KH', '9S'])


    def test4(self):
        t, p, gui_signals, h, logger = init_table('tests/screenshots/test4.png')
        t.get_game_number_on_screen(h)
        self.assertEqual(t.mycards, ['JC', '2C'])

        # def test_game_number(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/1773793_PreFlop_0.png')
        #     t.get_game_number_on_screen(h)
        #     self.assertEqual(h.game_number_on_screen,"15,547,039,153")
        #
        # def test_other_players1(self):
        #     t, p, gui_signals, h, logger=init_table('tests/screenshots/1773793_PreFlop_0.png')
        #
        #     self.assertEqual(t.position_utg_plus,0)
        #     self.assertEqual(t.dealer_position, 3)
        #     self.assertEqual(np.isnan(t.first_raiser), True)
        #     self.assertEqual(np.isnan(t.first_caller), True)
        #
        #     self.assertEqual(t.other_players[0]['utg_position'], 1)
        #     self.assertEqual(t.other_players[1]['utg_position'], 2)
        #     self.assertEqual(t.other_players[2]['utg_position'], 3)
        #     self.assertEqual(t.other_players[3]['utg_position'], 4)
        #     self.assertEqual(t.other_players[4]['utg_position'], 5)

        # def test_other_players2(self):
        #     t, p, gui_signals, h, logger=init_table('tests/screenshots/751235173_PreFlop_0.png')
        #
        #     self.assertEqual(t.position_utg_plus, 5)
        #     self.assertEqual(t.dealer_position, 4)
        #     self.assertEqual(t.first_raiser, 3)
        #     self.assertEqual(np.isnan(t.first_caller), True)
        #
        #     self.assertEqual(t.other_players[0]['utg_position'], 0)
        #     self.assertEqual(t.other_players[1]['utg_position'], 1)
        #     self.assertEqual(t.other_players[2]['utg_position'], 2)
        #     self.assertEqual(t.other_players[3]['utg_position'], 3)
        #     self.assertEqual(t.other_players[4]['utg_position'], 4)
        #
        #
        # def test_other_players3(self):
        #     t, p, gui_signals, h, logger=init_table('tests/screenshots/691119677_PreFlop_0.png')
        #
        #     self.assertEqual(t.position_utg_plus, 2)
        #     self.assertEqual(t.dealer_position, 1)
        #     self.assertEqual(t.first_raiser_utg, 0)
        #     self.assertEqual(t.first_caller_utg, 1)
        #     self.assertEqual(t.playersBehind, 2)
        #     self.assertEqual(t.playersAhead, 3)
        #
        #     self.assertEqual(t.other_players[0]['utg_position'], 3)
        #     self.assertEqual(t.other_players[1]['utg_position'], 4)
        #     self.assertEqual(t.other_players[2]['utg_position'], 5)
        #     self.assertEqual(t.other_players[3]['utg_position'], 0)
        #     self.assertEqual(t.other_players[4]['utg_position'], 1)
        #
        #
        # def test_other_players4(self):
        #     t, p, gui_signals, h, logger=init_table('tests/screenshots/467381034_PreFlop_0.png')
        #
        #     self.assertEqual(t.position_utg_plus, 2)
        #     self.assertEqual(t.dealer_position, 1)
        #     self.assertEqual(t.first_raiser_utg, 1)
        #     self.assertEqual(np.isnan(t.first_caller_utg), True)
        #     self.assertEqual(t.playersBehind, 1)
        #     self.assertEqual(t.playersAhead, 3)
        #     self.assertEqual(t.other_players[0]['pot'], '')
        #     self.assertEqual(t.other_players[1]['pot'], 0.02)
        #     self.assertEqual(t.other_players[2]['pot'], 0.04)
        #     self.assertEqual(t.other_players[3]['pot'], '')
        #     self.assertEqual(t.other_players[4]['pot'], 0.12)
        #
        # def test_other_players5(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/496504338_PreFlop_0.png')
        #     self.assertEqual(t.other_players[0]['pot'], 0.04)
        #     self.assertEqual(t.other_players[1]['pot'], 0.08)
        #     self.assertEqual(t.other_players[2]['pot'], '')
        #     self.assertEqual(t.other_players[3]['pot'], '')
        #     self.assertEqual(t.other_players[4]['pot'], '')
        #
        # def test_other_players6(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/499121363_PreFlop_4.png')
        #     self.assertEqual(t.other_players[0]['pot'], '')
        #     self.assertEqual(t.other_players[1]['pot'], '')
        #     self.assertEqual(t.other_players[2]['pot'], 0.28)
        #     self.assertEqual(t.other_players[3]['pot'], 0.02)
        #     self.assertEqual(t.other_players[4]['pot'], 0.04)
        #
        # def test_flop(self):
        #     t, p, gui_signals, h, logger=init_table('tests/screenshots/307380116_Flop_0.png')
        #     self.assertEqual(t.playersBehind, 1)
        #     self.assertEqual(t.playersAhead, 0)
        #
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/712154510_Flop_0.png')
        #     self.assertEqual(t.playersBehind, 0)
        #     self.assertEqual(t.playersAhead, 1)
        #     self.assertEqual(t.isHeadsUp,True)
        #
        # def test_preflop_recognition(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/308189727_PreFlop_0.png')
        #     self.assertEqual(t.other_players[0]['pot'], 0.02)
        #     self.assertEqual(t.other_players[1]['pot'], 0.04)
        #     self.assertEqual(t.other_players[2]['pot'], 0.12)
        #     self.assertEqual(t.other_players[3]['pot'], '')
        #     self.assertEqual(t.other_players[4]['pot'], '')
        #
        # def test_second_round_table(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/107232845_PreFlop_1.png',round_number=1)
        #     self.assertEqual(t.position_utg_plus, 1)
        #     self.assertEqual(t.dealer_position, 2)
        #     self.assertEqual(t.first_raiser, 2)
        #     self.assertEqual(np.isnan(t.second_raiser), True)
        #     self.assertEqual(np.isnan(t.first_caller), True)
        #     self.assertEqual(t.bot_pot, 0.09)
        #
        # def test_second_round_table2(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/378278828_PreFlop_1.png',round_number=1)
        #     self.assertEqual(t.position_utg_plus, 3)
        #     self.assertEqual(t.dealer_position, 0)
        #     self.assertEqual(t.first_raiser, 4)
        #     self.assertEqual(np.isnan(t.second_raiser), True)
        #     self.assertEqual(np.isnan(t.first_caller), True)
        #     self.assertEqual(t.bot_pot, 0.22)
        #
        #
        # def test_call_raise(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/43457283_PreFlop_0.png')
        #     self.assertEqual(t.other_players[0]['pot'], '')
        #     self.assertEqual(t.other_players[1]['pot'], 0.04)
        #     self.assertEqual(t.other_players[2]['pot'], 0.16)
        #     self.assertEqual(t.other_players[3]['pot'], '')
        #     self.assertEqual(t.other_players[4]['pot'], 0.02)
        #
        #
        # def test_call_raise_2(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/897376414_PreFlop_1.png')
        #     self.assertEqual(t.other_players[0]['pot'], '')
        #     self.assertEqual(t.other_players[1]['pot'], 0.3)
        #     self.assertEqual(t.other_players[2]['pot'], '')
        #     self.assertEqual(t.other_players[3]['pot'], 0.02)
        #     self.assertEqual(t.other_players[4]['pot'], 0.04)
        #
        #
        # def test_second_round_snowie_1(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/Q9o.png', round_number=0, strategy='snowie1')
        #     self.assertEqual(t.position_utg_plus, 5)
        #     self.assertEqual(t.dealer_position, 4)
        #     self.assertEqual(np.isnan(t.second_raiser), True)
        #     self.assertEqual(t.first_caller_utg,2)
        #
        # def test_raiser_utg3(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/571351571_PreFlop_0.png', round_number=0)
        #     self.assertEqual(t.position_utg_plus, 5)
        #     self.assertEqual(t.dealer_position, 4)
        #     self.assertEqual(np.isnan(t.second_raiser), True)
        #     self.assertEqual(t.first_raiser_utg, 3)
        #
        # def funds_error1(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/FundsError1.png')
        #     self.assertEqual(t.myFunds, 8.80)
        #
        # def funds_error2(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/FundsError2.png')
        #     self.assertEqual(t.myFunds, 10.80)
        #
        # def sheet_incorrect_fold(self):
        #     t, p, gui_signals, h, logger = init_table('tests/screenshots/49278076_PreFlop_0.png')
        #     self.assertEqual(t.currentCallValue,0.34)
        #     self.assertEqual(t.currentBetValue, 0.60)
        #     self.assertEqual(t.myFunds,4.98)
