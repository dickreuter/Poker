# coding: utf-8
__author__ = 'Nicolas Dickreuter'
'''
Runs a Montecarlo simulation to calculate the probability of winning with a certain pokerhand and a given amount of players
This version is based purely on Numpy and is still work in progress
'''

import time
import numpy as np

strided = np.lib.stride_tricks.as_strided


class Evaluation(object):
    def __init__(self):
        self.highcard_multiplier = 1
        self.pair_multiplier = 1000000
        self.twopair_multiplier = 10000000
        self.threeofakind_multiplier = 100000000
        self.straight_multiplier = 1000000000
        self.flush_multiplier = 10000000000
        self.fullhouse_multiplier = 100000000000
        self.fourofakind_multiplier = 1000000000000
        self.straighflush_multiplier = 10000000000000

    def run_evaluation(self, card1, card2, tablecards, iterations, player_amount=2):
        self.start = time.time()
        self.distribute_cards(card1, card2, tablecards, iterations)
        self.get_counts()
        self.get_kickers()
        self.get_multiplecards()
        self.get_fullhouse()
        self.get_straight()
        self.get_flush(iterations, player_amount)
        self.get_straighflush()
        self.get_highcard()
        self.calc_score()

        self.print_output()

        print("Time Elapsed: "+str(time.time() - self.start))

    def distribute_cards(self, card1, card2, tablecards, iterations):
        self.iterations = iterations
        deck = np.arange(0, 12 * 4)
        card1_idx = np.argwhere(deck == card1)
        card2_idx = np.argwhere(deck == card2)
        np.delete(deck, card1_idx)
        np.delete(deck, card2_idx)
        mycards = np.array([card1, card2])

        alldecks = np.tile(deck, reps=(iterations, 1))
        # np.random.shuffle(alldecks.T) # independent=True not yet implemented in numpy
        temp_random = np.random.random(alldecks.shape)
        idx = np.argsort(temp_random, axis=-1)
        shuffled = alldecks[np.arange(alldecks.shape[0])[:, None], idx]

        card_amount_at_river = 7

        plr1_crds = mycards
        plr2_crds = shuffled[:, 7:9]
        plr3_crds = shuffled[:, 9:11]
        plr4_crds = shuffled[:, 11:13]

        self.player_amount = 2

        cards_combined1 = np.append(np.tile(plr1_crds, reps=(iterations, 1)), shuffled, axis=1)[:,
                          0:card_amount_at_river]
        cards_combined2 = np.append(plr2_crds, shuffled, axis=1)[:, 0:card_amount_at_river]
        if self.player_amount > 2: cards_combined3 = np.append(plr3_crds, shuffled, axis=1)[:, 0:card_amount_at_river]
        if self.player_amount > 3: cards_combined4 = np.append(plr4_crds, shuffled, axis=1)[:, 0:card_amount_at_river]
        cards_combined = np.stack((cards_combined1, cards_combined2), axis=-1)  # stack over last axis (=axis 3)
        cards = np.ceil(cards_combined / 4)
        suits = cards_combined % 4 * 1
        self.decks = np.stack((cards, suits), axis=2)  # [iterations, 7, card or suits, player_index]
        self.cards = self.decks[:, :, 0, :]  # [iterations, 7, player_index]
        self.suits = self.decks[:, :, 1, :]  # [iterations, 7, player_index]
        self.cards_sorted = np.sort(self.cards, axis=1)[:, ::-1, :]

    def get_counts(self):
        self.counts = (np.arange(12, 0, -1) == self.cards[:, :, :, None]).sum(1)  # occurrences of each cards
        self.highestCard = self.cards_sorted[:, 0, :]  # iterations, cards_sorted, player

    def get_kickers(self):
        cards12to1 = np.arange(12, 0, -1) * -1

        # [iteration, player]
        self.pair1 = np.sort((self.counts == 2) * cards12to1 * -1, axis=2)[:, :, ::-1][:, :, 0]
        self.pair2 = np.sort((self.counts == 2) * cards12to1 * -1, axis=2)[:, :, ::-1][:, :, 1]
        self.pair3 = np.sort((self.counts == 2) * cards12to1 * -1, axis=2)[:, :, ::-1][:, :, 2]

        self.three1 = np.sort((self.counts == 3) * cards12to1 * -1, axis=2)[:, :, ::-1][:, :, 0]
        self.three2 = np.sort((self.counts == 3) * cards12to1 * -1, axis=2)[:, :, ::-1][:, :, 1]

        self.four1 = np.sort((self.counts == 4) * cards12to1 * -1, axis=2)[:, :, ::-1][:, :, 0]

        self.single1 = np.sort((self.counts == 1) * cards12to1 * -1, axis=2)[:, :, ::-1][:, :, 0]
        self.single2 = np.sort((self.counts == 1) * cards12to1 * -1, axis=2)[:, :, ::-1][:, :, 1]
        self.single3 = np.sort((self.counts == 1) * cards12to1 * -1, axis=2)[:, :, ::-1][:, :, 2]
        self.single4 = np.sort((self.counts == 1) * cards12to1 * -1, axis=2)[:, :, ::-1][:, :, 3]
        self.single5 = np.sort((self.counts == 1) * cards12to1 * -1, axis=2)[:, :, ::-1][:, :, 4]

    def get_multiplecards(self):
        self.pair_amount = (self.counts == 2).sum(2)
        self.threeofakind_amount = (self.counts == 3).sum(2)
        self.fourofakind_amount = (self.counts == 4).sum(2)

        self.pair = (self.pair_amount == 1)
        self.twopair = (self.pair_amount >= 2)
        self.singletwopair = (self.pair_amount == 2)
        self.threepair = (self.pair_amount == 3)  # same as twopair but different treatment of kickers
        self.threeofakind = (self.threeofakind_amount == 1)
        self.fourofakind = (self.fourofakind_amount == 1)

    def get_fullhouse(self):
        self.fullhouse = np.logical_or(self.threeofakind_amount == 2,
                                       np.logical_and(self.threeofakind_amount == 1, self.pair_amount >= 1))

        self.fullhouse_kicker1 = np.sort((self.counts == 3) * np.arange(12, 0, -1), axis=2)[:, :, ::-1][:, :, 0]
        highest_pair = np.sort((self.counts == 2) * np.arange(12, 0, -1), axis=2)[:, :, ::-1][:, :, 0]
        second_threeofakind = np.sort((self.counts == 3) * np.arange(12, 0, -1), axis=2)[:, :, ::-1][:, :, 1]

        self.fullhouse_kicker2 = np.amax(np.stack((highest_pair, second_threeofakind), axis=1), axis=1)

        self.fullhouse_score = self.fullhouse * (self.fullhouse_kicker1 * 1000 + self.fullhouse_kicker2)

    def sortddeck(self):
        sortval = self.decks[:, :, 0] * 4 + self.decks[:, :, 1]
        sortval *= -1  # largest first
        sortedIdx = np.argsort(sortval)
        self.decks = self.decks[np.arange(len(self.decks))[:, None], sortedIdx]

        self.cards = self.decks[:, :, 0]
        self.suits = self.decks[:, :, 1]

    def get_straight(self):
        add_low = self.cards_sorted[:, 0, :] - 12
        straight_cards = np.append(self.cards_sorted, add_low[:, None, :], axis=1)

        stri = straight_cards.strides
        shpe = straight_cards.shape

        cards_stacked_straightvariants = strided(straight_cards,
                                                 shape=(4, shpe[0], 5, shpe[2]),
                                                 strides=(stri[1], stri[0], stri[1], stri[2]))

        cards_stacked_straightvariants_highest_card = cards_stacked_straightvariants[..., 0, :]
        straights_variants = np.all(np.diff(cards_stacked_straightvariants, axis=2) == -1, axis=2)
        self.straight = np.any(straights_variants, axis=0)
        self.straights_score = np.sum(cards_stacked_straightvariants_highest_card * straights_variants, axis=0)

    def get_flush(self, iterations, player_amount):
        self.suitCounts = (self.suits[:, :, :, None] == np.arange(1, 5)).sum(1)  # occurrences of each suit
        self.maxsuit = np.argmax(self.suitCounts, axis=2) + 1
        self.flush = self.suitCounts[np.arange(iterations)[:, None], np.arange(player_amount), self.maxsuit - 1] >= 5
        self.flushcards = self.suits == self.maxsuit[:, None]
        self.sorted_flushcards = (np.sort(self.flushcards * self.cards * -1, axis=1) * -1)
        self.sorted_5flushcards = np.delete(self.sorted_flushcards, [5, 6], axis=1)
        multiplier = np.array([16, 8, 4, 2, 1])
        self.flushscore = (self.sorted_5flushcards * multiplier[..., :, None])[:, 0, :]
        return self.flushscore * self.flush

    def get_straighflush(self):
        # first dimension is the suit type, second the montecarlo, third the card, and fourth the player
        cards_stacked_suits = (self.suits == np.arange(4)[:, None, None, None]) * self.cards
        cards_stacked_suits = np.sort(cards_stacked_suits * -1, axis=2) * -1
        add_low = cards_stacked_suits[:, :, 0, :] - 12  # add highest card - 12 for ace low straight
        cards_stacked_suits = np.append(cards_stacked_suits, add_low[:, :, None, :], axis=2)

        stri = cards_stacked_suits.strides
        shpe = cards_stacked_suits.shape

        # new array 1. 4 checks, 4 different suits, shpe[1] runs, 5 cards down, she[3] players
        cards_stacked_suits_straightvariants = strided(cards_stacked_suits,
                                                       shape=(4, 4, shpe[1], 5, shpe[3]),
                                                       strides=(stri[2], stri[0], stri[1], stri[2], stri[3]))

        cards_stacked_suits_straightvariants_highest_card = cards_stacked_suits_straightvariants[..., 0, :]
        highest_straightflush_cards = np.sum(cards_stacked_suits_straightvariants_highest_card, axis=0)

        straight_flushes_by_suit_and_variant = np.all(np.diff(cards_stacked_suits_straightvariants, axis=3) == -1, axis=3)
        straightflush_by_suit = np.any(straight_flushes_by_suit_and_variant, axis=0)
        self.straightflush_score = np.sum(highest_straightflush_cards * straightflush_by_suit, axis=0)
        self.straightflush=np.any(straightflush_by_suit, axis=0)

    def get_highcard(self):
        self.highcard = np.all(np.stack((self.pair_amount == 0, self.threeofakind == False,
                                         self.fourofakind_amount == 0, self.straight == False,
                                         self.flush == False), axis=0), axis=0)

        # highestcard=...

    def calc_score(self):
        cardtype_names = np.array(
            ['highcard', 'pair', 'twopair', 'threeofakind', 'straight', 'flush', 'fullhouse', 'fourofakind',
             'straightflush'])
        cardtype_multiplier = np.array(
            [self.highcard_multiplier, self.pair_multiplier, self.twopair_multiplier, self.threeofakind_multiplier,
             self.straight_multiplier, self.flush_multiplier, self.fullhouse_multiplier, self.fourofakind_multiplier,
             self.straighflush_multiplier])
        detected_types = np.stack((self.highcard, self.pair, self.twopair, self.threeofakind,
                                          self.straight, self.flush, self.fullhouse, self.fourofakind,
                                          self.straightflush), axis=0)
        detected_types = detected_types * 1
        active_multiplier = cardtype_multiplier[:,None,None] * detected_types
        relevant_multiplier = np.argmax(active_multiplier, axis=0)






    def print_output(self):
        print("Decks")
        print(self.decks)
        print("cards")
        print(self.cards)
        print("suits")
        print(self.suits)
        print("counts")
        print(self.counts)
        print("Fullhouse")
        print(self.fullhouse)

        print("straight")
        print(self.straight)
        print("Highest Straight card")
        print("TBD")
        print("suitcounts")
        print(self.suitCounts)
        print("flush")
        print(self.flush)
        print('Flushcards')
        print(self.flushcards)
        print('Sorted Flushcards')
        print(self.sorted_flushcards)
        print('FlushScore')
        print(self.flushscore)
        print("Straight Flush")
        print(self.straightflush)
        print("all handtypes")
        # print(self.all_hand_types)
        # print("best handtype")
        # print(self.best_hand_type)
        # print("total calc_score")
        # print(self.totalscore)

        print()
        print()


E = Evaluation()
E.run_evaluation(card1=22, card2=1, tablecards=[], iterations=3, player_amount=2)
