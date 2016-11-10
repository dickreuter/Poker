from unittest import TestCase
import numpy as np
from . import init_table
from decisionmaker.outs_calculator import Outs_Calculator

class TestPocketPairToSet(TestCase):
    def test_game_number(self):
        oc = Outs_Calculator()
        my_cards = ['KH', 'KC']
        cards_on_table = ['QD', '4H', '9S']
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 0)


    def test_full_house(self):
        oc = Outs_Calculator()
        my_cards = ['6S', '6D']
        cards_on_table = ['JS', 'JH', 'JD']
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 0)

