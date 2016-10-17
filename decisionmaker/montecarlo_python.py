__author__ = 'Nicolas Dickreuter'
'''
Runs a Montecarlo simulation to calculate the probability of winning with a certain pokerhand and a given amount of players
'''
import time
import numpy as np
from collections import Counter
from copy import copy
import operator
import os
import winsound
from numba import jit


class MonteCarlo(object):
    def get_two_short_notation(self, input_cards):
        card1 = input_cards[0][0]
        card2 = input_cards[1][0]
        suited_str = 's' if input_cards[0][1] == input_cards[1][1] else 'o'
        return card1 + card2 + suited_str, card2 + card1 + suited_str

    def get_opponent_allowed_cards_list(self, opponent_call_probability, logger):
        self.preflop_equities = {
            "23o": 0.354,
            "24o": 0.36233333333333334,
            "26o": 0.3758666666666667,
            "34o": 0.3792,
            "25o": 0.3804666666666667,
            "27o": 0.3807333333333333,
            "23s": 0.3876,
            "36o": 0.39,
            "35o": 0.3900666666666667,
            "37o": 0.3957333333333333,
            "38o": 0.40013333333333334,
            "24s": 0.4024,
            "27s": 0.405,
            "28o": 0.4060666666666667,
            "25s": 0.4076,
            "26s": 0.41046666666666665,
            "46o": 0.4108,
            "47o": 0.41713333333333336,
            "34s": 0.4176666666666667,
            "45o": 0.4179333333333333,
            "29o": 0.4215333333333333,
            "48o": 0.4234,
            "37s": 0.424,
            "35s": 0.4246,
            "36s": 0.4268,
            "39o": 0.42733333333333334,
            "56o": 0.428,
            "28s": 0.42873333333333336,
            "57o": 0.4331333333333333,
            "49o": 0.43473333333333336,
            "38s": 0.4358,
            "2To": 0.4362666666666667,
            "58o": 0.4378666666666667,
            "45s": 0.4434666666666667,
            "46s": 0.4444,
            "47s": 0.4448666666666667,
            "67o": 0.4461333333333333,
            "3To": 0.4532,
            "48s": 0.4534,
            "56s": 0.4538,
            "29s": 0.45466666666666666,
            "39s": 0.45686666666666664,
            "68o": 0.4570666666666667,
            "59o": 0.45866666666666667,
            "57s": 0.4640666666666667,
            "4To": 0.46526666666666666,
            "49s": 0.46546666666666664,
            "2Jo": 0.466,
            "69o": 0.4666,
            "5To": 0.4672,
            "2Ts": 0.46786666666666665,
            "78o": 0.4722,
            "58s": 0.4756,
            "6To": 0.4768,
            "3Ts": 0.47733333333333333,
            "79o": 0.4788,
            "67s": 0.4808,
            "3Jo": 0.4808,
            "59s": 0.48133333333333334,
            "68s": 0.48346666666666666,
            "4Jo": 0.48633333333333334,
            "2Qo": 0.4928666666666667,
            "2Js": 0.49406666666666665,
            "69s": 0.49546666666666667,
            "3Qo": 0.4965333333333333,
            "4Ts": 0.49706666666666666,
            "6Jo": 0.4971333333333333,
            "5Jo": 0.49793333333333334,
            "5Ts": 0.5010666666666667,
            "7To": 0.5022,
            "89o": 0.5038,
            "6Ts": 0.5054,
            "78s": 0.5059333333333333,
            "3Js": 0.5124,
            "8To": 0.5130666666666667,
            "7Jo": 0.5150666666666667,
            "4Js": 0.5166,
            "79s": 0.5176666666666667,
            "7Ts": 0.5187333333333334,
            "2Qs": 0.5188666666666667,
            "22o": 0.5194666666666666,
            "4Qo": 0.5205333333333333,
            "6Js": 0.5217333333333334,
            "5Qo": 0.5253333333333333,
            "5Js": 0.5254,
            "2Ko": 0.5275333333333333,
            "3Ko": 0.5282666666666667,
            "89s": 0.5294,
            "8Jo": 0.5295333333333333,
            "9To": 0.5298,
            "6Qo": 0.5319333333333334,
            "4Qs": 0.5332666666666667,
            "3Qs": 0.5352,
            "7Qo": 0.5357333333333333,
            "7Js": 0.5391333333333334,
            "4Ko": 0.5392,
            "8Ts": 0.5393333333333333,
            "5Ko": 0.5412666666666667,
            "9Jo": 0.5472666666666667,
            "5Qs": 0.5484666666666667,
            "2Ks": 0.5512666666666667,
            "33o": 0.5556,
            "9Ts": 0.5558666666666666,
            "8Qo": 0.557,
            "6Qs": 0.5571333333333334,
            "8Js": 0.5590666666666667,
            "7Qs": 0.5597333333333333,
            "6Ko": 0.5597333333333333,
            "4Ks": 0.5641333333333334,
            "9Qo": 0.5652666666666667,
            "3Ks": 0.5654666666666667,
            "2Ao": 0.5668,
            "8Ko": 0.5674,
            "TJo": 0.5682666666666667,
            "7Ko": 0.5684,
            "3Ao": 0.5736666666666667,
            "8Qs": 0.5752,
            "5Ks": 0.5762666666666667,
            "9Js": 0.5798666666666666,
            "44o": 0.5818666666666666,
            "6Ks": 0.5852,
            "TQo": 0.5856666666666667,
            "2As": 0.5878666666666666,
            "9Qs": 0.5883333333333334,
            "7Ks": 0.5898666666666667,
            "9Ko": 0.5908,
            "JQo": 0.5912,
            "4Ao": 0.5918666666666667,
            "6Ao": 0.5934666666666667,
            "5Ao": 0.5938,
            "TJs": 0.5943333333333334,
            "8Ks": 0.5964666666666667,
            "7Ao": 0.6003333333333334,
            "3As": 0.6010666666666666,
            "TQs": 0.6062,
            "TKo": 0.6062666666666666,
            "4As": 0.6072,
            "9Ao": 0.6084,
            "JQs": 0.6100666666666666,
            "JKo": 0.6107333333333334,
            "9Ks": 0.6149333333333333,
            "8Ao": 0.6162666666666666,
            "55o": 0.6185333333333334,
            "6As": 0.6204666666666667,
            "QKo": 0.6242666666666666,
            "5As": 0.6255333333333334,
            "7As": 0.6282666666666666,
            "8As": 0.6311333333333333,
            "TKs": 0.6348666666666667,
            "TAo": 0.6371333333333333,
            "66o": 0.6403333333333333,
            "QKs": 0.6410666666666667,
            "9As": 0.6426,
            "JKs": 0.6436,
            "JAo": 0.6460666666666667,
            "TAs": 0.6498,
            "QAo": 0.6514,
            "77o": 0.6592,
            "KAo": 0.6592,
            "JAs": 0.6612666666666667,
            "QAs": 0.6670666666666667,
            "KAs": 0.6816666666666666,
            "88o": 0.6978,
            "99o": 0.7197333333333333,
            "TTo": 0.7524666666666666,
            "JJo": 0.7754,
            "QQo": 0.8024,
            "KKo": 0.8305333333333333,
            "AAo": 0.8527333333333333
        }
        peflop_equity_list = sorted(self.preflop_equities.items(), key=operator.itemgetter(1))

        counts = len(peflop_equity_list)
        take_top = int(counts * opponent_call_probability)
        allowed = set(list(peflop_equity_list)[-take_top:])
        allowed_cards = [i[0] for i in allowed]
        # logger.debug("Allowed range: "+str(allowed_cards))
        return allowed_cards

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

    def distribute_cards_to_players(self, deck, player_amount, player_card_list, table_card_list,
                                    opponent_allowed_cards):
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

        n = 0
        while True:
            plr = []

            random_card1 = np.random.random_integers(0, len(deck) - 1)
            plr.append(deck.pop(random_card1))
            random_card2 = np.random.random_integers(0, len(deck) - 1)
            plr.append(deck.pop(random_card2))

            # check for ranges
            crd1, crd2 = self.get_two_short_notation(plr)
            if not (crd1 in opponent_allowed_cards or crd2 in opponent_allowed_cards):
                deck.append(plr[0])
                deck.append(plr[1])
            else:
                Players.append(plr)
                n += 1
            if n == player_amount - knownPlayers or knownPlayers >= 2: break

        return Players, deck

    def distribute_cards_to_table(self, Deck, table_card_list):
        remaningRandoms = 5 - len(table_card_list)
        for n in range(0, remaningRandoms):
            table_card_list.append(Deck.pop(np.random.random_integers(0, len(Deck) - 1)))
        return table_card_list

    def run_montecarlo(self, logger, original_player_card_list, original_table_card_list, player_amount, ui, maxRuns,
                       timeout, ghost_cards, opponent_call_probability=1):
        opponent_allowed_cards = self.get_opponent_allowed_cards_list(opponent_call_probability, logger)

        winnerCardTypeList = []
        wins = 0
        runs = 0
        OriginalDeck = self.create_card_deck()
        if ghost_cards != '':
            OriginalDeck.pop(OriginalDeck.index(ghost_cards[0]))
            OriginalDeck.pop(OriginalDeck.index(ghost_cards[1]))

        for m in range(maxRuns):
            runs += 1
            Deck = copy(OriginalDeck)
            PlayerCardList = original_player_card_list[:]
            TableCardsList = original_table_card_list[:]
            Players, Deck = self.distribute_cards_to_players(Deck, player_amount, PlayerCardList, TableCardsList,
                                                             opponent_allowed_cards)
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
                    # if gui.active == True:
                    #     gui.progress["value"] = int(round(m * 100 / maxRuns))
                    #     gui.var2.set("Equity: " + str(self.equity * 100) + "%")
                    #     gui.statusbar.set("Running Monte Carlo: " + str(m) + "/" + str(maxRuns))
                    if m > 999 and time.time() > timeout:
                        break
            except:
                pass

        self.equity = wins / runs
        self.winnerCardTypeList = Counter(winnerCardTypeList)
        for key, value in self.winnerCardTypeList.items():
            self.winnerCardTypeList[key] = value / runs

        self.winTypesDict = self.winnerCardTypeList.items()
        self.runs = runs

        return self.equity, self.winTypesDict


def run_montecarlo_wrapper(logger, p, ui_action_and_signals, config, ui, t, L):
    # Prepare for montecarlo simulation to evaluate equity (probability of winning with given cards)

    if t.gameStage == "PreFlop":
        t.assumedPlayers = 2
        opponent_call_probability = 1

    elif t.gameStage == "Flop":

        if t.isHeadsUp:
            for i in range(5):
                if t.other_players[i]['status'] == 1:
                    break
            n = t.other_players[i]['utg_position']
            logger.info("Opponent utg position: " + str(n))
            opponent_call_probability = float(p.selected_strategy['range_utg' + str(n)])
        else:
            opponent_call_probability = float(p.selected_strategy['range_multiple_players'])

        t.assumedPlayers = t.other_active_players - int(round(t.playersAhead * (1 - opponent_call_probability))) + 1

    else:

        if t.isHeadsUp:
            for i in range(5):
                if t.other_players[i]['status'] == 1:
                    break
            n = t.other_players[i]['utg_position']
            logger.info("Opponent utg position: " + str(n))
            opponent_call_probability = float(p.selected_strategy['range_utg' + str(n)])
        else:
            opponent_call_probability = float(p.selected_strategy['range_multiple_players'])

        t.assumedPlayers = t.other_active_players + 1

    t.assumedPlayers = min(max(t.assumedPlayers, 2), 4)

    t.PlayerCardList = []
    t.PlayerCardList.append(t.mycards)
    t.PlayerCardList_and_others = copy(t.PlayerCardList)

    ghost_cards = ''

    if p.selected_strategy['collusion'] == 1:
        collusion_cards, collusion_player_dropped_out = L.get_collusion_cards(t.game_number_on_screen, t.gameStage)
        if collusion_cards != '':
            winsound.Beep(1000, 100)
            if not collusion_player_dropped_out:
                t.PlayerCardList_and_others.append(collusion_cards)
                print("COLLUSION FOUND")
            elif collusion_player_dropped_out:
                print("COLLUSION FOUND, but player dropped out")
                ghost_cards = collusion_cards
        else:
            print("NO COLLUSION FOUND")

    if t.gameStage == "PreFlop":
        maxRuns = 1000
    else:
        maxRuns = 7500

    ui_action_and_signals.signal_status.emit("Running Monte Carlo: " + str(maxRuns))
    logger.debug("Running Monte Carlo")
    t.montecarlo_timeout = float(config['montecarlo_timeout'])
    timeout = t.mt_tm + t.montecarlo_timeout
    m = MonteCarlo()
    logger.debug("Opponent call range: " + str(opponent_call_probability))
    logger.debug("maxRuns: " + str(maxRuns))
    logger.debug("Player amount: " + str(t.assumedPlayers))
    m.run_montecarlo(logger, t.PlayerCardList_and_others, t.cardsOnTable, int(t.assumedPlayers), ui, maxRuns=maxRuns,
                     ghost_cards=ghost_cards, timeout=timeout, opponent_call_probability=opponent_call_probability)
    ui_action_and_signals.signal_status.emit("Monte Carlo completed successfully")
    logger.debug("Monte Carlo completed successfully with runs: " + str(m.runs))

    if t.gameStage == "PreFlop":
        crd1, crd2 = m.get_two_short_notation(t.mycards)
        if crd1 in m.preflop_equities:
            m.equity = m.preflop_equities[crd1]
        elif crd2 in m.preflop_equities:
            m.equity = m.preflop_equities[crd2]
        elif crd1[0:2] in m.preflop_equities:
            m.equity = m.preflop_equities[crd1[0:2]]
        else:
            logger.warning("Preflop not found in table: " + str(crd1))

    t.equity = np.round(m.equity, 3)
    t.winnerCardTypeList = m.winnerCardTypeList

    ui_action_and_signals.signal_progressbar_increase.emit(30)


if __name__ == '__main__':
    Simulation = MonteCarlo()
    import logging

    logger = logging.getLogger('Montecarlo main')
    my_cards = [['2D', 'AD']]
    cards_on_table = ['3S', 'AH', '8D']
    players = 2
    secs = 3
    start_time = time.time()
    timeout = start_time + secs
    ghost_cards = ''
    Simulation.run_montecarlo(logging, my_cards, cards_on_table, player_amount=players, ui=None, maxRuns=15000,
                              ghost_cards=ghost_cards, timeout=timeout, opponent_call_probability=0.3)
    print("--- %s seconds ---" % (time.time() - start_time))
    print("Runs: " + str(Simulation.runs))
    equity = Simulation.equity  # considering draws as wins
    print("Equity: " + str(equity))
