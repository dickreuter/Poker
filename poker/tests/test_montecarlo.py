'''
Unittest for Montecarlosimulation. Checks if the differnt type of hands and their corresponding probability to win (equity)
is calculated correctly and within a given amount of time without a timeout
'''

import time
import unittest
from unittest.mock import MagicMock

import numpy as np

from poker.decisionmaker import montecarlo_python as mc


class TestMonteCarlo(unittest.TestCase):
    def test_twopairs1(
            self):
        Simulation = mc.MonteCarlo()

        Simulation.player_final_cards = [['3H', '3S', '4H', '4S', '8S', '8C', 'QH'],
                                         ['KH', '6C', '4H', '4S', '8S', '8C', 'QH']]
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

    def test_twopairs2(
            self):
        Simulation = mc.MonteCarlo()

        Simulation.player_final_cards = [['3H', '3S', '4H', '4S', '8S', '8C', 'QH'],
                                         ['KH', '3D', '4H', '4S', '8S', '8C', 'QH']]
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

    def test_evaluator(
            self):  # unittest to make sure the evaluator returns the corret winner hand 1 or 2 (returned as index of 0 or 1)
        Simulation = mc.MonteCarlo()

        Simulation.player_final_cards = [['8H', '8D', 'QH', '7H', '9H', 'JH', 'TH'],
                                         ['KH', '6C', 'QH', '7H', '9H', 'JH', 'TH']]  # two straight flush
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

        Simulation.player_final_cards = [['AS', 'KS', 'TS', '9S', '7S', '2H', '2H'],
                                         ['AS', 'KS', 'TS', '9S', '8S', '2H', '2H']]  # two flush
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

        Simulation.player_final_cards = [['8S', 'TS', '8H', 'KS', '9S', 'TH', 'KH'],
                                         ['TD', '7S', '8H', 'KS', '9S', 'TH', 'KH']]  # two pairs
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            0)

        Simulation.player_final_cards = [['2D', '2H', 'AS', 'AD', 'AH', '8S', '7H'],
                                         ['7C', '7S', '7H', 'AD', 'AS', '8S', '8H']]  # FULLHOUSES
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            0)

        Simulation.player_final_cards = [['7C', '7S', '7H', 'AD', 'KS', '5S', '8H'],
                                         ['2D', '3H', 'AS', '4D', '5H', '8S', '7H']]  # THREE OF A KIND AND STRAIGHT
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

        Simulation.player_final_cards = [['7C', '7C', 'AC', 'AC', '8C', '8S', '7H'],
                                         ['2C', '3C', '4C', '5C', '6C', '8S', 'KH']]  # FULL OF ACE AND STRAIGHT FLUSH
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

        Simulation.player_final_cards = [['AC', 'JS', 'AS', '2D', '5H', '3S', '3H'],
                                         ['QD', 'JD', 'TS', '9D', '6H', '8S', 'KH'],
                                         ['2D', '3D', '4S', '5D', '6H', '8S', 'KH']]  # STRAIGHTS and twoPair
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

        Simulation.player_final_cards = [['7C', '5S', '3S', 'JD', '8H', '2S', 'KH'],
                                         ['AD', '3D', '4S', '5D', '9H', '8S', 'KH']]  # Highcardds
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

        Simulation.player_final_cards = [['2C', '2D', '4S', '4D', '4H', '8S', 'KH'],
                                         ['7C', '7S', '7D', '7H', '8H', '8S', 'JH']]  # Fullhouse and four of a kind
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

        Simulation.player_final_cards = [['7C', '5S', '3S', 'JD', '8H', '2S', 'KH'],
                                         ['AD', '3D', '3S', '5D', '9H', '8S', 'KH']]  # Highcard and Pair
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

        Simulation.player_final_cards = [['7H', '7S', '3S', 'JD', '8H', '2S', 'KH'],
                                         ['7D', '3D', '3S', '7C', '9H', '8S', 'KH']]  # Two pairs over one pair
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

        Simulation.player_final_cards = [['AS', '8H', 'TS', 'JH', '3H', '2H', 'AH'],
                                         ['QD', 'QH', 'TS', 'JH', '3H', '2H', 'AH']]  # Two flushes
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            1)

        Simulation.player_final_cards = [['9S', '7H', 'KS', 'KH', 'AH', 'AS', 'AC'],
                                         ['8D', '2H', 'KS', 'KH', 'AH', 'AS', 'AC']]
        print(Simulation.eval_best_hand(Simulation.player_final_cards)[1])
        print("\r")
        self.assertEqual(
            Simulation.player_final_cards.index(Simulation.eval_best_hand(Simulation.player_final_cards)[0]),
            0)

    def test_monteCarlo(self):  # Unittest to ensure correct winning probabilities are returned
        def testRun(Simulation, my_cards, cards_on_table, players, expected_results, opponent_range=1):
            maxRuns = 15000  # maximum number of montecarlo runs
            testRuns = 5  # make several testruns to get standard deviation of winning probability
            secs = 1  # cut simulation short if amount of seconds are exceeded

            total_result = []
            for _ in range(testRuns):
                start_time = time.time() + secs
                logger = MagicMock()
                Simulation.run_montecarlo(logger, my_cards, cards_on_table, players, 1, maxRuns=maxRuns,
                                          timeout=start_time, ghost_cards='', opponent_range=opponent_range)
                equity = Simulation.equity
                total_result.append(equity * 100)
                print("--- %s seconds ---" % (time.time() - start_time))

                for keys, values in Simulation.winTypesDict:
                    print(keys + ": " + (str(np.round(values * 100, 2))))
                print("Equity: " + str(np.round(equity * 100, 2)))
                self.assertAlmostEqual(sum(Simulation.winnerCardTypeList.values()) - equity, 0, delta=0.0001)

            stdev = np.std(total_result)
            avg = np.mean(total_result)

            print("Mean: " + str(avg))
            print("Stdev: " + str(stdev))

            self.assertAlmostEqual(avg, expected_results, delta=2)
            self.assertAlmostEqual(stdev, 0, delta=2)

        Simulation = mc.MonteCarlo()

        my_cards = [['3H', '3S']]
        cards_on_table = ['8S', '4S', 'QH', '8C', '4H']
        expected_results = 40.2
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['8H', '8D']]
        cards_on_table = ['QH', '7H', '9H', 'JH', 'TH']
        expected_results = 95.6
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['AS', 'KS']]
        cards_on_table = []
        expected_results = 49.9 + 1.9
        players = 3
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['AS', 'KS']]
        cards_on_table = []
        expected_results = 66.1 + 1.6
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['8S', 'TS']]
        cards_on_table = ['8H', 'KS', '9S', 'TH', 'KH']
        expected_results = 71.5 + 5.9
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['8S', 'TS']]
        cards_on_table = ['2S', '3S', '4S', 'KS', 'AS']
        expected_results = 87
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['8S', '2S']]
        cards_on_table = ['5S', '3S', '4S', 'KS', 'AS']
        expected_results = 100
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['8S', 'TS']]
        cards_on_table = []
        expected_results = 22.6 + 2.9
        players = 5
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['2C', 'QS']]
        cards_on_table = []
        expected_results = 49.6  # 45 win and 4 tie
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['7H', '7S']]
        cards_on_table = ['7C', '8C', '8S', 'AC', 'AH']
        expected_results = 83
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['3S', 'QH']]
        cards_on_table = ['2C', '5H', '7C']
        expected_results = 30.9 + 2.2
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['5C', 'JS']]
        cards_on_table = []
        expected_results = 23
        players = 4
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['TC', 'TH']]
        cards_on_table = ['4D', 'QD', 'KC']
        expected_results = 66.7 + 0.38
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['JH', 'QS']]
        cards_on_table = ['5C', 'JD', 'AS', 'KS', 'QD']
        expected_results = 77
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['2H', '8S']]
        cards_on_table = ['AC', 'AD', 'AS', 'KS', 'KD']
        expected_results = 95
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['KD', 'KS']]
        cards_on_table = ['4D', '6S', '9C', '9S', 'TC']
        expected_results = 88
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['5H', 'KD']]
        cards_on_table = ['KH', 'JS', '2C', 'QS']
        expected_results = 75.6 + 3.6
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['JD', 'JS']]
        cards_on_table = ['8C', 'TC', 'JC', '5H', 'QC']
        expected_results = 26.1
        players = 3
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['TD', '7D']]
        cards_on_table = ['8D', 'QD', '7C', '5D', '6D']
        expected_results = 87
        players = 2
        testRun(Simulation, my_cards, cards_on_table, players, expected_results)

        my_cards = [['KS', 'KC']]
        cards_on_table = ['3D', '9H', 'AS', '7S', 'QH']
        opponent_range=0.25
        expected_results = 12.8
        players = 3
        testRun(Simulation, my_cards, cards_on_table, players, expected_results, opponent_range=opponent_range)

        my_cards = [{'AKO','AA'}]
        cards_on_table = ['3D', '9H', 'AS', '7S', 'QH']
        opponent_range=0.25
        expected_results = 77.8
        players = 3
        testRun(Simulation, my_cards, cards_on_table, players, expected_results, opponent_range=opponent_range)
