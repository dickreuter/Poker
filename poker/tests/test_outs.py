from unittest import TestCase

from poker.decisionmaker.outs_calculator import Outs_Calculator


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

        #DRAW TESTS

    def test_pocket_pair_to_set(self):
        oc = Outs_Calculator()
        my_cards = ['KH', 'KC']
        cards_on_table = ['QD', '4H', '9S']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 0)

    def test_one_overcard(self):
        oc = Outs_Calculator()
        my_cards = ['AS', '8D']
        cards_on_table = ['JC', '5S', '2D']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 0)

    def test_inside_straight_draw(self):
        oc = Outs_Calculator()
        my_cards = ['JH', '9C']
        cards_on_table = ['QS', '8D', '4C']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 4)

    def test_two_pair_to_full_house(self):
        oc = Outs_Calculator()
        my_cards = ['KH', 'QS']
        cards_on_table = ['KC', 'QD', '5S']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 0)

    def test__one_pair_to_two_pair_of_set(self):
        oc = Outs_Calculator()
        my_cards = ['AC', 'QD']
        cards_on_table = ['AD', 'TC', '3S']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 0)

    def test_no_pair_to_pair(self):
        oc = Outs_Calculator()
        my_cards = ['9C', '7D']
        cards_on_table = ['2S', '3D', 'JC']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 0)

    def test_two_overcards_to_over_pair(self):
        oc = Outs_Calculator()
        my_cards = ['AD', 'JH']
        cards_on_table = ['TC', '8D', '2S']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 0)

    def test_full_house_or_4_kind_draw(self):
        oc = Outs_Calculator()
        my_cards = ['6C', '6D']
        cards_on_table = ['6S', '7H', 'JC']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 0)

    def test_open_ended_straight_draw(self):
        oc = Outs_Calculator()
        my_cards = ['9C', '8D']
        cards_on_table = ['7C', 'TH', '3S']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 8)

    def test_flush_draw(self):
        oc = Outs_Calculator()
        my_cards = ['KS', 'JS']
        cards_on_table = ['AS', '6S', '8D']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 9)

    def test_inside_straight_and_two_overcards_draw(self):
        oc = Outs_Calculator()
        my_cards = ['AC', 'KD']
        cards_on_table = ['QH', 'TC', '2S']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 4)

    def test_inside_straight_and_flush_draw(self):
        oc = Outs_Calculator()
        my_cards = ['AD', 'KD']
        cards_on_table = ['JD', 'QS', '3D']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 12)

    def test_open_straight_and_flush_draw(self):
        oc = Outs_Calculator()
        my_cards = ['KH', 'QH']
        cards_on_table = ['TH', 'JS', '4H']
        oc.evaluate_hands(my_cards, cards_on_table, oc)
        self.assertEqual(oc.evaluate_hands(my_cards, cards_on_table, oc), 15)
