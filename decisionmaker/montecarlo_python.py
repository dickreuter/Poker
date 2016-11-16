__author__ = 'Nicolas Dickreuter'
'''
Runs a Montecarlo simulation to calculate the probability of winning with a certain pokerhand and a given amount of players
'''
import operator
import logging
import time
import winsound
import numpy as np

from collections import Counter
from copy import copy


class MonteCarlo(object):
    def __init__(self):
        self.logger = logging.getLogger('montecarlo')
        self.logger.setLevel(logging.DEBUG)

    def get_two_short_notation(self, input_cards, add_O_to_pairs=False):
        card1 = input_cards[0][0]
        card2 = input_cards[1][0]
        suited_str = 'S' if input_cards[0][1] == input_cards[1][1] else 'O'
        if card1[0] == card2[0]:
            if add_O_to_pairs:
                suited_str = "O"
            else:
                suited_str = ''

        return card1 + card2 + suited_str, card2 + card1 + suited_str

    def get_opponent_allowed_cards_list(self, opponent_ranges):
        self.preflop_equities = {
            "23O": 0.354,
            "24O": 0.36233333333333334,
            "26O": 0.3758666666666667,
            "34O": 0.3792,
            "25O": 0.3804666666666667,
            "27O": 0.3807333333333333,
            "23S": 0.3876,
            "36O": 0.39,
            "35O": 0.3900666666666667,
            "37O": 0.3957333333333333,
            "38O": 0.40013333333333334,
            "24S": 0.4024,
            "27S": 0.405,
            "28O": 0.4060666666666667,
            "25S": 0.4076,
            "26S": 0.41046666666666665,
            "46O": 0.4108,
            "47O": 0.41713333333333336,
            "34S": 0.4176666666666667,
            "45O": 0.4179333333333333,
            "29O": 0.4215333333333333,
            "48O": 0.4234,
            "37S": 0.424,
            "35S": 0.4246,
            "36S": 0.4268,
            "39O": 0.42733333333333334,
            "56O": 0.428,
            "28S": 0.42873333333333336,
            "57O": 0.4331333333333333,
            "49O": 0.43473333333333336,
            "38S": 0.4358,
            "2TO": 0.4362666666666667,
            "58O": 0.4378666666666667,
            "45S": 0.4434666666666667,
            "46S": 0.4444,
            "47S": 0.4448666666666667,
            "67O": 0.4461333333333333,
            "3TO": 0.4532,
            "48S": 0.4534,
            "56S": 0.4538,
            "29S": 0.45466666666666666,
            "39S": 0.45686666666666664,
            "68O": 0.4570666666666667,
            "59O": 0.45866666666666667,
            "57S": 0.4640666666666667,
            "4TO": 0.46526666666666666,
            "49S": 0.46546666666666664,
            "2JO": 0.466,
            "69O": 0.4666,
            "5TO": 0.4672,
            "2TS": 0.46786666666666665,
            "78O": 0.4722,
            "58S": 0.4756,
            "6TO": 0.4768,
            "3TS": 0.47733333333333333,
            "79O": 0.4788,
            "67S": 0.4808,
            "3JO": 0.4808,
            "59S": 0.48133333333333334,
            "68S": 0.48346666666666666,
            "4JO": 0.48633333333333334,
            "2QO": 0.4928666666666667,
            "2JS": 0.49406666666666665,
            "69S": 0.49546666666666667,
            "3QO": 0.4965333333333333,
            "4TS": 0.49706666666666666,
            "6JO": 0.4971333333333333,
            "5JO": 0.49793333333333334,
            "5TS": 0.5010666666666667,
            "7TO": 0.5022,
            "89O": 0.5038,
            "6TS": 0.5054,
            "78S": 0.5059333333333333,
            "3JS": 0.5124,
            "8TO": 0.5130666666666667,
            "7JO": 0.5150666666666667,
            "4JS": 0.5166,
            "79S": 0.5176666666666667,
            "7TS": 0.5187333333333334,
            "2QS": 0.5188666666666667,
            "22": 0.5194666666666666,
            "4QO": 0.5205333333333333,
            "6JS": 0.5217333333333334,
            "5QO": 0.5253333333333333,
            "5JS": 0.5254,
            "2KO": 0.5275333333333333,
            "3KO": 0.5282666666666667,
            "89S": 0.5294,
            "8JO": 0.5295333333333333,
            "9TO": 0.5298,
            "6QO": 0.5319333333333334,
            "4QS": 0.5332666666666667,
            "3QS": 0.5352,
            "7QO": 0.5357333333333333,
            "7JS": 0.5391333333333334,
            "4KO": 0.5392,
            "8TS": 0.5393333333333333,
            "5KO": 0.5412666666666667,
            "9JO": 0.5472666666666667,
            "5QS": 0.5484666666666667,
            "2KS": 0.5512666666666667,
            "33": 0.5556,
            "9TS": 0.5558666666666666,
            "8QO": 0.557,
            "6QS": 0.5571333333333334,
            "8JS": 0.5590666666666667,
            "7QS": 0.5597333333333333,
            "6KO": 0.5597333333333333,
            "4KS": 0.5641333333333334,
            "9QO": 0.5652666666666667,
            "3KS": 0.5654666666666667,
            "2AO": 0.5668,
            "8KO": 0.5674,
            "TJO": 0.5682666666666667,
            "7KO": 0.5684,
            "3AO": 0.5736666666666667,
            "8QS": 0.5752,
            "5KS": 0.5762666666666667,
            "9JS": 0.5798666666666666,
            "44": 0.5818666666666666,
            "6KS": 0.5852,
            "TQO": 0.5856666666666667,
            "2AS": 0.5878666666666666,
            "9QS": 0.5883333333333334,
            "7KS": 0.5898666666666667,
            "9KO": 0.5908,
            "JQO": 0.5912,
            "4AO": 0.5918666666666667,
            "6AO": 0.5934666666666667,
            "5AO": 0.5938,
            "TJS": 0.5943333333333334,
            "8KS": 0.5964666666666667,
            "7AO": 0.6003333333333334,
            "3AS": 0.6010666666666666,
            "TQS": 0.6062,
            "TKO": 0.6062666666666666,
            "4AS": 0.6072,
            "9AO": 0.6084,
            "JQS": 0.6100666666666666,
            "JKO": 0.6107333333333334,
            "9KS": 0.6149333333333333,
            "8AO": 0.6162666666666666,
            "55": 0.6185333333333334,
            "6AS": 0.6204666666666667,
            "QKO": 0.6242666666666666,
            "5AS": 0.6255333333333334,
            "7AS": 0.6282666666666666,
            "8AS": 0.6311333333333333,
            "TKS": 0.6348666666666667,
            "TAO": 0.6371333333333333,
            "66": 0.6403333333333333,
            "QKS": 0.6410666666666667,
            "9AS": 0.6426,
            "JKS": 0.6436,
            "JAO": 0.6460666666666667,
            "TAS": 0.6498,
            "QAO": 0.6514,
            "77": 0.6592,
            "KAO": 0.6592,
            "JAS": 0.6612666666666667,
            "QAS": 0.6670666666666667,
            "KAS": 0.6816666666666666,
            "88": 0.6978,
            "99": 0.7197333333333333,
            "TT": 0.7524666666666666,
            "JJ": 0.7754,
            "QQ": 0.8024,
            "KK": 0.8305333333333333,
            "AA": 0.8527333333333333
        }
        peflop_equity_list = sorted(self.preflop_equities.items(), key=operator.itemgetter(1))

        counts = len(peflop_equity_list)
        take_top = int(counts * opponent_ranges)
        allowed = set(list(peflop_equity_list)[-take_top:])
        allowed_cards = [i[0] for i in allowed]
        # logger.debug("Allowed range: "+str(allowed_cards))
        return set(allowed_cards)

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
            kicker = max(card_ranks[2], card_ranks[3])  # avoid for example 11,8,6,7
            card_ranks = (card_ranks[0], card_ranks[1], kicker)
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

    def distribute_cards_to_players(self, deck, player_amount, player_card_list, known_table_cards,
                                    opponent_allowed_cards, passes):

        # rmove table cards from deck
        CardsOnTable = []
        for known_table_card in known_table_cards:
            CardsOnTable.append(deck.pop(deck.index(known_table_card)))  # remove cards that are on the table from the deck

        all_players = []
        knownPlayers = 0  # for potential collusion if more than one bot is running on the same table

        for player_cards in player_card_list:
            known_player = []

            if type(player_cards) == set:
                while True:
                    passes += 1
                    random_card1 = np.random.randint(0, len(deck))
                    random_card2 = np.random.randint(0, len(deck) - 1)
                    if not random_card1 == random_card2:
                        crd1, crd2 = self.get_two_short_notation([deck[random_card1], deck[random_card2]],
                                                                 add_O_to_pairs=False)
                        if crd1 in player_cards or crd2 in player_cards:
                            break
                player_cards = []
                player_cards.append(deck[random_card1])
                player_cards.append(deck[random_card2])

            known_player.append(player_cards[0])
            known_player.append(player_cards[1])
            all_players.append(known_player)

            try:
                deck.pop(deck.index(player_cards[0]))
            except:
                pass
            try:
                deck.pop(deck.index(player_cards[1]))
            except:
                pass

            knownPlayers += 1  # my own cards are known

        for _ in range(player_amount - knownPlayers):
            random_player = []
            while True:
                passes += 1
                random_card1 = np.random.randint(0, len(deck))
                random_card2 = np.random.randint(0, len(deck) - 1)

                if not random_card1 == random_card2:
                    crd1, crd2 = self.get_two_short_notation([deck[random_card1], deck[random_card2]],
                                                             add_O_to_pairs=False)
                    if crd1 in opponent_allowed_cards or crd2 in opponent_allowed_cards:
                        break

            random_player.append(deck.pop(random_card1))
            random_player.append(deck.pop(random_card2))

            all_players.append(random_player)

        return all_players, deck, passes

    def distribute_cards_to_table(self, Deck, table_card_list):
        remaningRandoms = 5 - len(table_card_list)
        for n in range(0, remaningRandoms):
            table_card_list.append(Deck.pop(np.random.random_integers(0, len(Deck) - 1)))
        return table_card_list

    def run_montecarlo(self, logger, original_player_card_list, original_table_card_list, player_amount, ui, maxRuns,
                       timeout, ghost_cards, opponent_range=1):

        if type(opponent_range) == float or type(opponent_range) == int:
            opponent_allowed_cards = self.get_opponent_allowed_cards_list(opponent_range)
            self.logger.info('Preflop reverse tables for ranges for opponent: NO')
        elif type(opponent_range == set):
            logger.info('Preflop reverse tables for ranges for opponent: YES')
            opponent_allowed_cards = opponent_range

        winnerCardTypeList = []
        wins = 0
        runs = 0
        passes = 0
        OriginalDeck = self.create_card_deck()
        if ghost_cards != '':
            OriginalDeck.pop(OriginalDeck.index(ghost_cards[0]))
            OriginalDeck.pop(OriginalDeck.index(ghost_cards[1]))

        for m in range(maxRuns):
            runs += 1
            Deck = copy(OriginalDeck)
            PlayerCardList = copy(original_player_card_list)
            TableCardsList = copy(original_table_card_list)
            Players, Deck, passes = self.distribute_cards_to_players(Deck, player_amount, PlayerCardList,
                                                                     TableCardsList,
                                                                     opponent_allowed_cards, passes)
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

            if passes > 999 and time.time() > timeout:
                self.logger.warning("Cutting short montecarlo due to timeout")
                self.logger.warning("Passes: " + str(passes))
                self.logger.warning("Runs: " + str(runs))
                break

                # if passes >= maxruns: break

        self.equity = wins / runs
        self.winnerCardTypeList = Counter(winnerCardTypeList)
        for key, value in self.winnerCardTypeList.items():
            self.winnerCardTypeList[key] = value / runs

        self.winTypesDict = self.winnerCardTypeList.items()
        self.runs = runs
        self.passes = passes

        return self.equity, self.winTypesDict


def run_montecarlo_wrapper(p, ui_action_and_signals, config, ui, t, L, preflop_state, h):
    # Prepare for montecarlo simulation to evaluate equity (probability of winning with given cards)
    m = MonteCarlo()

    logger = logging.getLogger('montecarlo')
    logger.setLevel(logging.DEBUG)

    if t.gameStage == "PreFlop":
        t.assumedPlayers = 2
        opponent_range = 1

    elif t.gameStage == "Flop":

        if t.isHeadsUp:
            for i in range(5):
                if t.other_players[i]['status'] == 1:
                    break
            n = t.other_players[i]['utg_position']
            logger.info("Opponent utg position: " + str(n))
            opponent_range = float(p.selected_strategy['range_utg' + str(n)])
        else:
            opponent_range = float(p.selected_strategy['range_multiple_players'])

        t.assumedPlayers = t.other_active_players - int(round(t.playersAhead * (1 - opponent_range))) + 1

    else:

        if t.isHeadsUp:
            for i in range(5):
                if t.other_players[i]['status'] == 1:
                    break
            n = t.other_players[i]['utg_position']
            logger.info("Opponent utg position: " + str(n))
            opponent_range = float(p.selected_strategy['range_utg' + str(n)])
        else:
            opponent_range = float(p.selected_strategy['range_multiple_players'])

        t.assumedPlayers = t.other_active_players + 1

    t.assumedPlayers = min(max(t.assumedPlayers, 2), 4)

    t.PlayerCardList = []
    t.PlayerCardList.append(t.mycards)
    t.PlayerCardList_and_others = copy(t.PlayerCardList)

    ghost_cards = ''
    m.collusion_cards = ''

    if p.selected_strategy['collusion'] == 1:
        collusion_cards, collusion_player_dropped_out = L.get_collusion_cards(h.game_number_on_screen, t.gameStage)

        if collusion_cards != '':
            m.collusion_cards = collusion_cards
            winsound.Beep(1000, 100)
            if not collusion_player_dropped_out:
                t.PlayerCardList_and_others.append(collusion_cards)
                logger.info("Collusion found, player still in game. " + str(collusion_cards))
            elif collusion_player_dropped_out:
                logger.info("COllusion found, but player dropped out." + str(collusion_cards))
                ghost_cards = collusion_cards
        else:
            logger.debug("No collusion found")

    else:
        m.collusion_cards = ''

    if t.gameStage == "PreFlop":
        maxRuns = 1000
    else:
        maxRuns = 7500

    if t.gameStage != 'PreFlop':
        try:
            for abs_pos in range(5):
                if t.other_players[abs_pos]['status'] == 1:
                    sheet_name = preflop_state.get_reverse_sheetname(abs_pos, t, h)
                    ranges = preflop_state.get_rangecards_from_sheetname(abs_pos, sheet_name, t, h, p)
                    # logger.debug("Ranges from reverse table: "+str(ranges))

                    # the last player's range will be relevant
                    if t.isHeadsUp == True:
                        opponent_range = ranges

        except Exception as e:
            logger.error("Opponent reverse table failed: " + str(e))

    ui_action_and_signals.signal_status.emit("Running range Monte Carlo: " + str(maxRuns))
    logger.debug("Running Monte Carlo")
    t.montecarlo_timeout = float(config['montecarlo_timeout'])
    timeout = t.mt_tm + t.montecarlo_timeout
    logger.debug("Used opponent range for montecarlo: " + str(opponent_range))
    logger.debug("maxRuns: " + str(maxRuns))
    logger.debug("Player amount: " + str(t.assumedPlayers))

    # calculate range equity
    if t.gameStage != 'PreFlop' and p.selected_strategy['use_relative_equity']:
        if p.selected_strategy['preflop_override'] and preflop_state.preflop_bot_ranges!= None:
            t.player_card_range_list_and_others = t.PlayerCardList_and_others[:]
            t.player_card_range_list_and_others[0] = preflop_state.preflop_bot_ranges

            t.range_equity, _ = m.run_montecarlo(logger, t.player_card_range_list_and_others, t.cardsOnTable,
                                              int(t.assumedPlayers), ui,
                                              maxRuns=maxRuns,
                                              ghost_cards=ghost_cards, timeout=timeout, opponent_range=opponent_range)
            t.range_equity = np.round(t.range_equity, 2)
            logger.debug("Range montecarlo completed successfully with runs: " + str(m.runs))
            logger.debug("Range equity (range for bot): " + str(t.range_equity))

    if preflop_state.preflop_bot_ranges == None and p.selected_strategy['preflop_override'] and t.gameStage != 'PreFlop':
        logger.error("No preflop range for bot, assuming 50% relative equity")
        t.range_equity=.5

    ui_action_and_signals.signal_progressbar_increase.emit(10)
    ui_action_and_signals.signal_status.emit("Running card Monte Carlo: " + str(maxRuns))

    # run montecarlo for absolute equity
    t.abs_equity, _ = m.run_montecarlo(logger, t.PlayerCardList_and_others, t.cardsOnTable, int(t.assumedPlayers), ui, maxRuns=maxRuns,
                     ghost_cards=ghost_cards, timeout=timeout, opponent_range=opponent_range)
    ui_action_and_signals.signal_status.emit("Monte Carlo completed successfully")
    logger.debug("Cards Monte Carlo completed successfully with runs: " + str(m.runs))
    logger.info("Absolute equity (no ranges for bot) " + str(np.round(t.abs_equity,2)))

    if t.gameStage == "PreFlop":
        crd1, crd2 = m.get_two_short_notation(t.mycards)
        if crd1 in m.preflop_equities:
            m.equity = m.preflop_equities[crd1]
        elif crd2 in m.preflop_equities:
            m.equity = m.preflop_equities[crd2]
        elif crd1 + 'O' in m.preflop_equities:
            m.equity = m.preflop_equities[crd1 + 'O']
        else:
            logger.warning("Preflop equity not found in lookup table: " + str(crd1))
        t.abs_equity=m.equity

    t.abs_equity = np.round(t.abs_equity, 2)
    t.winnerCardTypeList = m.winnerCardTypeList

    ui_action_and_signals.signal_progressbar_increase.emit(15)
    m.opponent_range = opponent_range

    if t.gameStage != 'PreFlop' and p.selected_strategy['use_relative_equity']:
        t.relative_equity = np.round(t.abs_equity / t.range_equity / 2, 2)
        logger.info("Relative equity (equity/range equity/2): " + str(t.relative_equity))
    else:
        t.range_equity = ''
        t.relative_equity = ''
    return m


if __name__ == '__main__':
    Simulation = MonteCarlo()
    logger = logging.getLogger('Montecarlo main')
    logger.setLevel(logging.DEBUG)
    # my_cards = [['2D', 'AD']]
    # cards_on_table = ['3S', 'AH', '8D']
    my_cards = [['KS', 'KC']]
    my_cards = [{'AKO', 'AA'}]
    cards_on_table = ['3D', '9H', 'AS', '7S', 'QH']
    players = 3
    secs = 5
    maxruns = 10000
    start_time = time.time()
    timeout = start_time + secs
    ghost_cards = ''
    Simulation.run_montecarlo(logging, my_cards, cards_on_table, player_amount=players, ui=None, maxRuns=maxruns,
                              ghost_cards=ghost_cards, timeout=timeout, opponent_range=0.25)
    print("--- %s seconds ---" % (time.time() - start_time))
    print("Runs: " + str(Simulation.runs))
    print("Passes: " + str(Simulation.passes))
    equity = Simulation.equity  # considering draws as wins
    print("Equity: " + str(equity))
