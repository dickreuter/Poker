from unittest import TestCase

import pytest

from poker.tests import init_table


@pytest.mark.skip
class TestTableScreenBased(TestCase):
    def no_test1(self):
        t, _, _, h, _ = init_table('tests/screenshots/test1.png')
        t.get_game_number_on_screen(h)
        # self.assertEqual(h.game_number_on_screen, "16543145686")
        self.assertEqual(t.mycards, ['QD', 'QS'])
        self.assertEqual(t.checkButton, True)
        self.assertEqual(t.callButton, False)
        self.assertEqual(t.bet_button_found, True)
        self.assertEqual(t.cardsOnTable, ['KH', '3C', 'TS'])

    def no_test2(self):
        t, _, _, h, _ = init_table('tests/screenshots/test2.png')
        t.get_game_number_on_screen(h)
        # self.assertEqual(h.game_number_on_screen, "16547195085")
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

    def no_test3(self):
        t, _, _, h, _ = init_table('tests/screenshots/test3.png')
        t.get_game_number_on_screen(h)
        self.assertEqual(t.mycards, ['3H', 'TS'])
        self.assertEqual(t.checkButton, True)
        self.assertEqual(t.callButton, False)
        self.assertEqual(t.bet_button_found, True)
        self.assertEqual(t.cardsOnTable, ['5C', 'AS', '5H', 'KH', '9S'])

    def no_test4(self):
        t, _, _, h, _ = init_table('tests/screenshots/test4.png')
        t.get_game_number_on_screen(h)
        self.assertEqual(t.mycards, ['JC', '2C'])
