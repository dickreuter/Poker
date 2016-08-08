__author__ = 'Nicolas Dickreuter'
'''
Runs a Montecarlo simulation to calculate the probability of winning with a certain pokerhand and a given amount of players
'''
import time
import numpy as np
from collections import Counter
from copy import copy


class MonteCarlo(object):
    def eval_best_hand(self, hands):  # evaluate which hand is best
        scores = [(i, self.calc_score(hand)) for i, hand in enumerate(hands)]
        winner = sorted(scores, key=lambda x: x[1], reverse=True)[0][0]
        return hands[winner], scores[winner][1][-1]

    def calc_score(self, hand):  # assign a calc_score to the hand so it can be compared with other hands
        card_ranks_original = '23456789TJQKA'
        original_suits = 'CDHS'
        rcounts = {card_ranks_original.find(r): ''.join(hand).count(r) for r, _ in hand}.items()
        score, card_ranks = zip(*sorted((cnt, rank) for rank, cnt in rcounts)[::-1])

        potential_threeofakind = score[0] == 3
        potential_twopair = score == (2, 2, 1, 1, 1)
        potential_pair = score == (2, 1, 1, 1, 1, 1)

        if score[0:2] == (3, 2) or score[0:2] == (3, 3):  # fullhouse (three of a kind and pair, or two three of a kind)
            card_ranks = (card_ranks[0], card_ranks[1])
            score = (3, 2)
        elif score[0:4] == (2, 2, 2, 1):  # special case: convert three pair to two pair
            score = (2, 2, 1)  # as three pair are not worth more than two pair
            sortedCrdRanks = sorted(card_ranks, reverse=True)  # avoid for example 11,8,6,7
            card_ranks = (sortedCrdRanks[0], sortedCrdRanks[1], sortedCrdRanks[2], sortedCrdRanks[3])
        elif score[0] == 4:  # four of a kind
            score = (4,)
            sortedCrdRanks = sorted(card_ranks, reverse=True)  # avoid for example 11,8,9
            card_ranks = (sortedCrdRanks[0], sortedCrdRanks[1])
        elif len(score) >= 5:  # high card, flush, straight and straight flush
            # straight
            if 12 in card_ranks:  # adjust if 5 high straight
                card_ranks += (-1,)
            sortedCrdRanks = sorted(card_ranks, reverse=True)  # sort again as if pairs the first rank matches the pair
            for i in range(len(sortedCrdRanks) - 4):
                straight = sortedCrdRanks[i] - sortedCrdRanks[i + 4] == 4
                if straight:
                    card_ranks = (
                        sortedCrdRanks[i], sortedCrdRanks[i + 1], sortedCrdRanks[i + 2], sortedCrdRanks[i + 3],
                        sortedCrdRanks[i + 4])
                    break

            # flush
            suits = [s for _, s in hand]
            flush = max(suits.count(s) for s in suits) >= 5
            if flush:
                for flushSuit in original_suits:  # get the suit of the flush
                    if suits.count(flushSuit) >= 5:
                        break

                flushHand = [k for k in hand if flushSuit in k]
                rcountsFlush = {card_ranks_original.find(r): ''.join(flushHand).count(r) for r, _ in flushHand}.items()
                score, card_ranks = zip(*sorted((cnt, rank) for rank, cnt in rcountsFlush)[::-1])
                card_ranks = tuple(
                    sorted(card_ranks, reverse=True))  # ignore original sorting where pairs had influence

                # check for straight in flush
                if 12 in card_ranks and not -1 in card_ranks:  # adjust if 5 high straight
                    card_ranks += (-1,)
                for i in range(len(card_ranks) - 4):
                    straight = card_ranks[i] - card_ranks[i + 4] == 4
                    if straight:
                        break

            # no pair, straight, flush, or straight flush
            score = ([(1,), (3, 1, 2)], [(3, 1, 3), (5,)])[flush][straight]

        if score == (1,) and potential_threeofakind:
            score = (3, 1)
        elif score == (1,) and potential_twopair:
            score = (2, 2, 1)
        elif score == (1,) and potential_pair:
            score = (2, 1, 1)

        if score[0] == 5:
            hand_type = "StraightFlush"
            # crdRanks=crdRanks[:5] # five card rule makes no difference {:5] would be incorrect
        elif score[0] == 4:
            hand_type = "FoufOfAKind"
            # crdRanks=crdRanks[:2] # already implemented above
        elif score[0:2] == (3, 2):
            hand_type = "FullHouse"
            # crdRanks=crdRanks[:2] # already implmeneted above
        elif score[0:3] == (3, 1, 3):
            hand_type = "Flush"
            card_ranks = card_ranks[:5]
        elif score[0:3] == (3, 1, 2):
            hand_type = "Straight"
            card_ranks = card_ranks[:5]
        elif score[0:2] == (3, 1):
            hand_type = "ThreeOfAKind"
            card_ranks = card_ranks[:3]
        elif score[0:2] == (2, 2):
            hand_type = "TwoPair"
            card_ranks = card_ranks[:3]
        elif score[0] == 2:
            hand_type = "Pair"
            card_ranks = card_ranks[:4]
        elif score[0] == 1:
            hand_type = "HighCard"
            card_ranks = card_ranks[:5]
        else:
            raise Exception('Card Type error!')

        return score, card_ranks, hand_type

    def create_card_deck(self):
        values = "23456789TJQKA"
        suites = "CDHS"
        Deck = []
        [Deck.append(x + y) for x in values for y in suites]
        return Deck

    def distribute_cards_to_players(self, deck, player_amount, player_card_list, table_card_list):
        Players = []
        CardsOnTable = []
        knownPlayers = 0  # for potential collusion if more than one bot is running on the same table

        for player_cards in player_card_list:
            first_player = []
            first_player.append(deck.pop(deck.index(player_cards[0])))
            first_player.append(deck.pop(deck.index(player_cards[1])))
            Players.append(first_player)

            knownPlayers += 1  # my own cards are known

        for c in table_card_list:
            CardsOnTable.append(deck.pop(deck.index(c)))  # remove cards that are on the table from the deck

        for n in range(0, player_amount - knownPlayers):
            plr = []
            plr.append(deck.pop(np.random.random_integers(0, len(deck) - 1)))
            plr.append(deck.pop(np.random.random_integers(0, len(deck) - 1)))
            Players.append(plr)

        return Players, deck

    def distribute_cards_to_table(self, Deck, table_card_list):
        remaningRandoms = 5 - len(table_card_list)
        for n in range(0, remaningRandoms):
            table_card_list.append(Deck.pop(np.random.random_integers(0, len(Deck) - 1)))

        return table_card_list

    def run_montecarlo(self, original_player_card_list, original_table_card_list, player_amount, gui, maxRuns=6000,
                       maxSecs=5):
        winnerCardTypeList = []
        wins = 0
        runs = 0
        timeout_start = time.time()
        OriginalDeck = self.create_card_deck()
        for m in range(maxRuns):
            runs += 1

            Deck = copy(OriginalDeck)
            PlayerCardList = original_player_card_list[:]
            TableCardsList = original_table_card_list[:]
            Players, Deck = self.distribute_cards_to_players(Deck, player_amount, PlayerCardList, TableCardsList)
            Deck5Cards = self.distribute_cards_to_table(Deck, TableCardsList)
            PlayerFinalCardsWithTableCards = []
            for o in range(0, player_amount):
                PlayerFinalCardsWithTableCards.append(Players[o] + Deck5Cards)

            bestHand, winnerCardType = self.eval_best_hand(PlayerFinalCardsWithTableCards)
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
    my_cards = [['8H', 'TH']]
    cards_on_table = []
    players = 4
    start_time = time.time()
    Simulation.run_montecarlo(my_cards, cards_on_table, players, 1, maxRuns=15000, maxSecs=5)
    print("--- %s seconds ---" % (time.time() - start_time))
    equity = Simulation.equity  # considering draws as wins
    print("Equity: " + str(equity))
