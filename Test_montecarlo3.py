'''
Unittest for Montecarlosimulation. Checks if the differnt type of hands and their corresponding probability to win (equity)
is calculated correctly and within a given amount of time without a timeout
'''

import unittest
import Montecarlo_v3 as mc
import time
import numpy as np


class TestMonteCarlo(unittest.TestCase):
    def test_evaluator(
            self):  # unittest to make sure the evaluator returns the corret winner hand 1 or 2 (returned as index of 0 or 1)
        Simulation = mc.MonteCarlo()

        Simulation.PlayerFinalCards = [['8H', '8D', 'QH', '7H', '9H', 'JH', 'TH'],
                                       ['KH', '6C', 'QH', '7H', '9H', 'JH', 'TH']]  # two straight flush
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 1)

        Simulation.PlayerFinalCards = [['AS', 'KS', 'TS', '9S', '7S', '2H', '2H'],
                                       ['AS', 'KS', 'TS', '9S', '8S', '2H', '2H']]  # two flush
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 1)

        Simulation.PlayerFinalCards = [['8S', 'TS', '8H', 'KS', '9S', 'TH', 'KH'],
                                       ['TD', '7S', '8H', 'KS', '9S', 'TH', 'KH']]  # two pairs
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 0)

        Simulation.PlayerFinalCards = [['2D', '2H', 'AS', 'AD', 'AH', '8S', '7H'],
                                       ['7C', '7S', '7H', 'AD', 'AS', '8S', '8H']]  # FULLHOUSES
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 0)

        Simulation.PlayerFinalCards = [['7C', '7S', '7H', 'AD', 'KS', '5S', '8H'],
                                       ['2D', '3H', 'AS', '4D', '5H', '8S', '7H']]  # THREE OF A KIND AND STRAIGHT
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 1)

        Simulation.PlayerFinalCards = [['7C', '7C', 'AC', 'AC', '8C', '8S', '7H'],
                                       ['2C', '3C', '4C', '5C', '6C', '8S', 'KH']]  # FULL OF ACE AND STRAIGHT FLUSH
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 1)

        Simulation.PlayerFinalCards = [['AC', 'JS', 'AS', '2D', '5H', '3S', '3H'],
                                       ['QD', 'JD', 'TS', '9D', '6H', '8S', 'KH'],
                                       ['2D', '3D', '4S', '5D', '6H', '8S', 'KH']]  # STRAIGHTS and twoPair
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 1)

        Simulation.PlayerFinalCards = [['7C', '5S', '3S', 'JD', '8H', '2S', 'KH'],
                                       ['AD', '3D', '4S', '5D', '9H', '8S', 'KH']]  # Highcardds
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 1)

        Simulation.PlayerFinalCards = [['2C', '2D', '4S', '4D', '4H', '8S', 'KH'],
                                       ['7C', '7S', '7D', '7H', '8H', '8S', 'JH']]  # Fullhouse and four of a kind
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 1)

        Simulation.PlayerFinalCards = [['7C', '5S', '3S', 'JD', '8H', '2S', 'KH'],
                                       ['AD', '3D', '3S', '5D', '9H', '8S', 'KH']]  # Highcard and Pair
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 1)

        Simulation.PlayerFinalCards = [['7H', '7S', '3S', 'JD', '8H', '2S', 'KH'],
                                       ['7D', '3D', '3S', '7C', '9H', '8S', 'KH']]  # Two pairs over one pair
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 1)

        Simulation.PlayerFinalCards = [['AS', '8H', 'TS', 'JH', '3H', '2H', 'AH'],
                                       ['QD', 'QH', 'TS', 'JH', '3H', '2H', 'AH']]  # Two flushes
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 1)

        Simulation.PlayerFinalCards = [['9S', '7H', 'KS', 'KH', 'AH', 'AS', 'AC'],
                                       ['8D', '2H', 'KS', 'KH', 'AH', 'AS', 'AC']]  # Full house on table that is draw
        print(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[1])
        print("\r")
        self.assertEqual(Simulation.PlayerFinalCards.index(Simulation.EvalBestHand(Simulation.PlayerFinalCards)[0]), 0)

    def test_monteCarlo(self):  # Unittest to ensure correct winning probabilities are returned
        def testRun(Simulation, mycards, cardsOnTable, players, expectedResult):
            maxRuns = 15000  # maximum number of montecarlo runs
            testRuns = 5  # make several testruns to get standard deviation of winning probability
            secs = 5  # cut simulation short if amount of seconds are exceeded

            totalResult = []
            for n in range(testRuns):
                start_time = time.time()
                Simulation.RunMonteCarlo(mycards, cardsOnTable, players, 1, maxRuns=maxRuns, maxSecs=secs)
                equity = Simulation.equity
                totalResult.append(equity * 100)
                print("--- %s seconds ---" % (time.time() - start_time))

                for keys, values in Simulation.winTypesDict:
                    print(keys + ": " + (str(np.round(values * 100, 2))))
                print("Equity: " + str(np.round(equity * 100, 2)))
                self.assertAlmostEqual(sum(Simulation.winnerCardTypeList.values()) - equity, 0, delta=0.0001)

            stdev = np.std(totalResult)
            avg = np.mean(totalResult)

            print("Mean: " + str(avg))
            print("Stdev: " + str(stdev))

            self.assertAlmostEqual(avg, expectedResult, delta=1)
            self.assertAlmostEqual(stdev, 0, delta=1)

        Simulation = mc.MonteCarlo()

        mycards = [['8H', '8D']]
        cardsOnTable = ['QH', '7H', '9H', 'JH', 'TH']
        expectedResult = 95.6
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['AS', 'KS']]
        cardsOnTable = []
        expectedResult = 49.9 + 1.9
        players = 3
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['AS', 'KS']]
        cardsOnTable = []
        expectedResult = 66.1 + 1.6
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['8S', 'TS']]
        cardsOnTable = ['8H', 'KS', '9S', 'TH', 'KH']
        expectedResult = 71.5 + 5.9
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['8S', 'TS']]
        cardsOnTable = ['2S', '3S', '4S', 'KS', 'AS']
        expectedResult = 87
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['8S', '2S']]
        cardsOnTable = ['5S', '3S', '4S', 'KS', 'AS']
        expectedResult = 100
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['8S', 'TS']]
        cardsOnTable = []
        expectedResult = 22.6 + 2.9
        players = 5
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['2C', 'QS']]
        cardsOnTable = []
        expectedResult = 49.6  # 45 win and 4 tie
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['7H', '7S']]
        cardsOnTable = ['7C', '8C', '8S', 'AC', 'AH']
        expectedResult = 83
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['3S', 'QH']]
        cardsOnTable = ['2C', '5H', '7C']
        expectedResult = 30.9 + 2.2
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['5C', 'JS']]
        cardsOnTable = []
        expectedResult = 23
        players = 4
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['TC', 'TH']]
        cardsOnTable = ['4D', 'QD', 'KC']
        expectedResult = 66.7 + 0.38
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['JH', 'QS']]
        cardsOnTable = ['5C', 'JD', 'AS', 'KS', 'QD']
        expectedResult = 77
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['2H', '8S']]
        cardsOnTable = ['AC', 'AD', 'AS', 'KS', 'KD']
        expectedResult = 95
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['KD', 'KS']]
        cardsOnTable = ['4D', '6S', '9C', '9S', 'TC']
        expectedResult = 88
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['5H', 'KD']]
        cardsOnTable = ['KH', 'JS', '2C', 'QS']
        expectedResult = 75.6 + 3.6
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['JD', 'JS']]
        cardsOnTable = ['8C', 'TC', 'JC', '5H', 'QC']
        expectedResult = 26
        players = 3
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)

        mycards = [['TD', '7D']]
        cardsOnTable = ['8D', 'QD', '7C', '5D', '6D']
        expectedResult = 87
        players = 2
        testRun(Simulation, mycards, cardsOnTable, players, expectedResult)
