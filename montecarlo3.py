__author__ = 'Nicolas Dickreuter'
'''
Runs a Montecarlo simulation to calculate the probability of winning with a certain pokerhand and a given amount of players
'''
import time
import numpy as np
from collections import Counter
from copy import copy


class MonteCarlo(object):
    def EvalBestHand(self, hands):  # evaluate which hand is best
        scores = [(i, self.score(hand)) for i, hand in enumerate(hands)]
        winner = sorted(scores, key=lambda x: x[1], reverse=True)[0][0]
        return hands[winner], scores[winner][1][-1]

    def score(self, hand):  # assign a score to the hand so it can be compared with other hands
        crdRanksOriginal = '23456789TJQKA'
        originalSuits = 'CDHS'
        rcounts = {crdRanksOriginal.find(r): ''.join(hand).count(r) for r, _ in hand}.items()
        score, crdRanks = zip(*sorted((cnt, rank) for rank, cnt in rcounts)[::-1])

        potentialThreeOfAKind = score[0] == 3
        potentialTwoPair = score == (2, 2, 1, 1, 1)
        potentialPair = score == (2, 1, 1, 1, 1, 1)

        if score[0:2] == (3, 2) or score[0:2] == (3, 3):  # fullhouse (three of a kind and pair, or two three of a kind)
            crdRanks = (crdRanks[0], crdRanks[1])
            score = (3, 2)
        elif score[0:4] == (2, 2, 2, 1):  # special case: convert three pair to two pair
            score = (2, 2, 1)  # as three pair are not worth more than two pair
            sortedCrdRanks = sorted(crdRanks, reverse=True)  # avoid for example 11,8,6,7
            crdRanks = (sortedCrdRanks[0], sortedCrdRanks[1], sortedCrdRanks[2], sortedCrdRanks[3])
        elif score[0] == 4:  # four of a kind
            score = (4,)
            sortedCrdRanks = sorted(crdRanks, reverse=True)  # avoid for example 11,8,9
            crdRanks = (sortedCrdRanks[0], sortedCrdRanks[1])
        elif len(score) >= 5:  # high card, flush, straight and straight flush
            # straight
            if 12 in crdRanks:  # adjust if 5 high straight
                crdRanks += (-1,)
            sortedCrdRanks = sorted(crdRanks, reverse=True)  # sort again as if pairs the first rank matches the pair
            for i in range(len(sortedCrdRanks) - 4):
                straight = sortedCrdRanks[i] - sortedCrdRanks[i + 4] == 4
                if straight:
                    crdRanks = (sortedCrdRanks[i], sortedCrdRanks[i + 1], sortedCrdRanks[i + 2], sortedCrdRanks[i + 3],
                                sortedCrdRanks[i + 4])
                    break

            # flush
            suits = [s for _, s in hand]
            flush = max(suits.count(s) for s in suits) >= 5
            if flush:
                for flushSuit in originalSuits:  # get the suit of the flush
                    if suits.count(flushSuit) >= 5:
                        break

                flushHand = [k for k in hand if flushSuit in k]
                rcountsFlush = {crdRanksOriginal.find(r): ''.join(flushHand).count(r) for r, _ in flushHand}.items()
                score, crdRanks = zip(*sorted((cnt, rank) for rank, cnt in rcountsFlush)[::-1])
                crdRanks = tuple(sorted(crdRanks, reverse=True))  # ignore original sorting where pairs had influence

                # check for straight in flush
                if 12 in crdRanks and not -1 in crdRanks:  # adjust if 5 high straight
                    crdRanks += (-1,)
                for i in range(len(crdRanks) - 4):
                    straight = crdRanks[i] - crdRanks[i + 4] == 4
                    if straight:
                        break

            # no pair, straight, flush, or straight flush
            score = ([(1,), (3, 1, 2)], [(3, 1, 3), (5,)])[flush][straight]

        if score == (1,) and potentialThreeOfAKind:
            score = (3, 1)
        elif score == (1,) and potentialTwoPair:
            score = (2, 2, 1)
        elif score == (1,) and potentialPair:
            score = (2, 1, 1)

        if score[0] == 5:
            handType = "StraightFlush"
            # crdRanks=crdRanks[:5] # five card rule makes no difference {:5] would be incorrect
        elif score[0] == 4:
            handType = "FoufOfAKind"
            # crdRanks=crdRanks[:2] # already implemented above
        elif score[0:2] == (3, 2):
            handType = "FullHouse"
            # crdRanks=crdRanks[:2] # already implmeneted above
        elif score[0:3] == (3, 1, 3):
            handType = "Flush"
            crdRanks = crdRanks[:5]
        elif score[0:3] == (3, 1, 2):
            handType = "Straight"
            crdRanks = crdRanks[:5]
        elif score[0:2] == (3, 1):
            handType = "ThreeOfAKind"
            crdRanks = crdRanks[:3]
        elif score[0:2] == (2, 2):
            handType = "TwoPair"
            crdRanks = crdRanks[:3]
        elif score[0] == 2:
            handType = "Pair"
            crdRanks = crdRanks[:4]
        elif score[0] == 1:
            handType = "HighCard"
            crdRanks = crdRanks[:5]
        else:
            raise Exception('Card Type error!')

        return score, crdRanks, handType

    def createCardDeck(self):
        values = "23456789TJQKA"
        suites = "CDHS"
        Deck = []
        [Deck.append(x + y) for x in values for y in suites]
        return Deck

    def distributeToPlayers(self, Deck, PlayerAmount, PlayerCardList, TableCardsList):
        Players = []
        CardsOnTable = []
        knownPlayers = 0  # for potential collusion if more than one bot is running on the same table

        for PlayerCards in PlayerCardList:
            FirstPlayer = []
            FirstPlayer.append(Deck.pop(Deck.index(PlayerCards[0])))
            FirstPlayer.append(Deck.pop(Deck.index(PlayerCards[1])))
            Players.append(FirstPlayer)

            knownPlayers += 1  # my own cards are known

        for c in TableCardsList:
            CardsOnTable.append(Deck.pop(Deck.index(c)))  # remove cards that are on the table from the deck

        for n in range(0, PlayerAmount - knownPlayers):
            plr = []
            plr.append(Deck.pop(np.random.random_integers(0, len(Deck) - 1)))
            plr.append(Deck.pop(np.random.random_integers(0, len(Deck) - 1)))
            Players.append(plr)

        return Players, Deck

    def distributeToTable(self, Deck, TableCardsList):
        remaningRandoms = 5 - len(TableCardsList)
        for n in range(0, remaningRandoms):
            TableCardsList.append(Deck.pop(np.random.random_integers(0, len(Deck) - 1)))

        return TableCardsList

    def RunMonteCarlo(self, originalPlayerCardList, originalTableCardsList, PlayerAmount, gui, maxRuns=6000, maxSecs=5):
        winnerlist = []
        EquityList = []
        winnerCardTypeList = []
        wins = 0
        runs = 0
        timeout_start = time.time()
        OriginalDeck = self.createCardDeck()
        for m in range(maxRuns):
            runs += 1

            Deck = copy(OriginalDeck)
            PlayerCardList = originalPlayerCardList[:]
            TableCardsList = originalTableCardsList[:]
            Players, Deck = self.distributeToPlayers(Deck, PlayerAmount, PlayerCardList, TableCardsList)
            Deck5Cards = self.distributeToTable(Deck, TableCardsList)
            PlayerFinalCardsWithTableCards = []
            for o in range(0, PlayerAmount):
                PlayerFinalCardsWithTableCards.append(Players[o] + Deck5Cards)

            bestHand, winnerCardType = self.EvalBestHand(PlayerFinalCardsWithTableCards)
            winner = (PlayerFinalCardsWithTableCards.index(bestHand))

            # print (winnerCardType)

            CollusionPlayers = 0
            if winner < CollusionPlayers + 1:
                wins += 1
                winnerCardTypeList.append(winnerCardType)
                # winnerlist.append(winner)
                # self.equity=wins/m
                # if self.equity>0.99: self.equity=0.99
                # EquityList.append(self.equity)

            self.equity = np.round(wins / runs, 3)

            try:
                if m % 1000 == 0:
                    if gui.active == True:
                        gui.progress["value"] = int(round(m * 100 / maxRuns))
                        gui.var2.set("Equity: " + str(self.equity * 100) + "%")
                        gui.statusbar.set("Running Monte Carlo: " + str(m) + "/" + str(maxRuns))
            except:
                pass

            if time.time() > timeout_start + maxSecs:
                break

        self.equity = wins / runs
        self.winnerCardTypeList = Counter(winnerCardTypeList)
        for key, value in self.winnerCardTypeList.items():
            self.winnerCardTypeList[key] = value / runs

        self.winTypesDict = self.winnerCardTypeList.items()
        self.runs = runs

        try:
            if gui.active == True:
                gui.progress["value"] = int(round(self.runs * 100 / maxRuns))
        except:
            print("Runs: " + str(self.runs))

        return self.equity, self.winTypesDict


if __name__ == '__main__':
    Simulation = MonteCarlo()
    mycards = [['8H', 'TH']]
    cardsOnTable = []
    players = 4
    start_time = time.time()
    Simulation.RunMonteCarlo(mycards, cardsOnTable, players, 1, maxRuns=15000, maxSecs=5)
    print("--- %s seconds ---" % (time.time() - start_time))
    equity = Simulation.equity  # considering draws as wins
    print("Equity: " + str(equity))
