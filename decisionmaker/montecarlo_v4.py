# coding: utf-8
__author__ = 'Nicolas Dickreuter'
'''
Runs a Montecarlo simulation to calculate the probability of winning with a certain pokerhand and a given amount of players
This version is based purely on Numpy and is still work in progress
'''

import time
import numpy as np


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

    def distribute_cards(self, card1, card2, iterations):
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
        player_id = 2
        cards_combined = np.append(np.tile(mycards, reps=(iterations, 1)), shuffled, axis=1)[:,
                         player_id * card_amount_at_river - card_amount_at_river:card_amount_at_river * player_id]
        cards = np.ceil(cards_combined / 4)
        suits = cards_combined % 4 + 1
        self.decks = np.dstack((cards, suits))

        self.cards = self.decks[:, :, 0]
        self.suits = self.decks[:, :, 1]

    def run_evaluation(self, card1, card2, iterations):
        self.start = time.time()
        self.distribute_cards(card1, card2, iterations)
        self.get_counts()
        self.get_kickers()
        self.get_multiplecards()
        self.get_fullhouse()
        self.get_straight()
        self.get_flush()
        self.get_straighflush()
        self.get_highcard()
        self.calc_score()

        self.print_output()
        print(time.time() - self.start)

    def sortddeck(self):
        sortval = self.decks[:, :, 0] * 4 + self.decks[:, :, 1]
        sortval *= -1  # largest first
        sortedIdx = np.argsort(sortval)
        self.decks = self.decks[np.arange(len(self.decks))[:, None], sortedIdx]

        self.cards = self.decks[:, :, 0]
        self.suits = self.decks[:, :, 1]

    def get_counts(self):
        self.counts = (self.cards[:, :, None] == np.arange(12, 0, -1)).sum(1)  # occurrences of each cards
        self.highestCard = self.cards[:, 0]

    def get_highcard(self):
        self.highcard = np.all(np.column_stack((self.pair_amount == 0, self.threeofakind.T == False,
                                                self.fourofakind_amount == False, self.straight.T == False,
                                                self.flush.T == False)), axis=1)
        np.column_stack((self.pair_amount == 0, self.threeofakind.T == False))

    def get_kickers(self):
        cards12to1 = np.arange(12, 0, -1) * -1

        self.pair1 = (np.sort((self.counts == 2) * cards12to1, axis=1) * -1)[:, 0]
        self.pair2 = (np.sort((self.counts == 2) * cards12to1, axis=1) * -1)[:, 1]
        self.pair3 = (np.sort((self.counts == 2) * cards12to1, axis=1) * -1)[:, 2]

        self.three1 = (np.sort((self.counts == 3) * cards12to1, axis=1) * -1)[:, 0]
        self.three2 = (np.sort((self.counts == 3) * cards12to1, axis=1) * -1)[:, 1]

        self.four1 = (np.sort((self.counts == 4) * cards12to1, axis=1) * -1)[:, 0]

        self.single1 = (np.sort((self.counts == 1) * cards12to1, axis=1) * -1)[:, 0]
        self.single2 = (np.sort((self.counts == 1) * cards12to1, axis=1) * -1)[:, 1]
        self.single3 = (np.sort((self.counts == 1) * cards12to1, axis=1) * -1)[:, 2]
        self.single4 = (np.sort((self.counts == 1) * cards12to1, axis=1) * -1)[:, 3]
        self.single5 = (np.sort((self.counts == 1) * cards12to1, axis=1) * -1)[:, 4]

    def get_multiplecards(self):
        self.pair_amount = (self.counts[:, :, None] == 2).sum(1)
        self.twopair_amount = (self.counts[:, :, None] == 2).sum(1)
        self.threeofakind_amount = (self.counts[:, :, None] == 3).sum(1)
        self.fourofakind_amount = (self.counts[:, :, None] == 4).sum(1)

        self.pair = (self.pair_amount == 1).T
        self.twopair = (self.pair_amount >= 2).T
        self.singletwopair = (self.pair_amount == 2).T
        self.threepair = (self.pair_amount == 3).T  # same as twopair but different treatment of kickers
        self.threeofakind = (self.threeofakind_amount == 1).T
        self.fourofakind = (self.fourofakind_amount == 1).T

    def get_fullhouse(self):
        self.fullhouse = np.logical_or(self.threeofakind_amount == 2,
                                       np.logical_and(self.threeofakind_amount == 1, self.pair_amount >= 1)).T

        self.fullhouse_kicker1 = (np.sort((self.counts == 3) * np.arange(12, 0, -1) * -1, axis=1) * -1)[:, 0]

        highest_pair = (np.sort((self.counts == 2) * np.arange(12, 0, -1) * -1, axis=1) * -1)[:, 0]
        second_threeofakind = (np.sort((self.counts == 3) * np.arange(12, 0, -1) * -1, axis=1) * -1)[:, 1]
        self.fullhouse_kicker2 = np.amax(np.column_stack((highest_pair, second_threeofakind)), axis=1)

        self.fullhouse_score = self.fullhouse * (self.fullhouse_kicker1 * 1000 + self.fullhouse_kicker2)

    def get_straight(self):  # status: ok
        self.card_is_present = np.copy(self.counts)
        self.card_is_present[self.card_is_present > 1] = 1
        add_at_end = (self.highestCard == 12).astype(int)  # add ace to bottom for 5 high straight
        self.card_is_present = np.append(self.card_is_present, add_at_end[..., None], axis=1)
        s1 = np.sum(self.card_is_present[:, 0:5], axis=1)  # check for variations of 5 consecutive cards
        s2 = np.sum(self.card_is_present[:, 1:6], axis=1)
        s3 = np.sum(self.card_is_present[:, 2:7], axis=1)
        s4 = np.sum(self.card_is_present[:, 3:8], axis=1)
        self.s = np.column_stack((s1, s2, s3, s4))
        self.s_index = np.argmax(self.s, axis=1)
        self.straight = self.s[np.arange(self.iterations), self.s_index] == 5
        self.highestStraightcard = self.cards[np.arange(self.iterations), self.s_index]

    def get_flush(self):  # status: ok
        self.suitCounts = (self.suits[:, :, None] == np.arange(1, 5)).sum(1)  # occurrences of each suit
        self.maxsuit = np.argmax(self.suitCounts, axis=1) + 1
        self.flush = np.choose(self.maxsuit - 1, self.suitCounts.T) >= 5
        self.flushcards = self.suits == self.maxsuit[:, None]
        self.sorted_flushcards = (np.sort(self.flushcards * self.cards * -1, axis=1) * -1)
        self.sorted_5flushcards = np.delete(self.sorted_flushcards, [5, 6], axis=1)
        multiplier = np.array([16, 8, 4, 2, 1])
        self.flushscore = np.sum(self.sorted_5flushcards * multiplier, axis=1)

    def get_straighflush(self):
        def check_substraight(start, suit):
            diffs = np.diff(suit[:, start:start + 5], axis=1)
            substraight = np.all(diffs == -1, axis=1)
            return substraight

        club_cards = np.sort((self.suits == 1) * self.cards * -1) * -1
        diamond_cards = np.sort((self.suits == 2) * self.cards * -1) * -1
        heart_cards = np.sort((self.suits == 3) * self.cards * -1) * -1
        spade_cards = np.sort((self.suits == 4) * self.cards * -1) * -1

        # add highestcard-12 at end (0 if ace is present for 5 high straight)
        highest_club = club_cards[:, 0]
        highest_diamond = diamond_cards[:, 0]
        highest_heart = heart_cards[:, 0]
        highest_spade = spade_cards[:, 0]

        # add highest card-12 at the end
        club_cards = np.append(club_cards, highest_club[..., None] - 12, axis=1)
        diamond_cards = np.append(diamond_cards, highest_diamond[..., None] - 12, axis=1)
        heart_cards = np.append(heart_cards, highest_heart[..., None] - 12, axis=1)
        spade_cards = np.append(spade_cards, highest_spade[..., None] - 12, axis=1)

        # check for straight
        c1 = check_substraight(0, club_cards)
        c2 = check_substraight(1, club_cards)
        c3 = check_substraight(2, club_cards)
        c4 = check_substraight(3, club_cards)
        d1 = check_substraight(0, diamond_cards)
        d2 = check_substraight(1, diamond_cards)
        d3 = check_substraight(2, diamond_cards)
        d4 = check_substraight(3, diamond_cards)
        h1 = check_substraight(0, heart_cards)
        h2 = check_substraight(1, heart_cards)
        h3 = check_substraight(2, heart_cards)
        h4 = check_substraight(3, heart_cards)
        s1 = check_substraight(0, spade_cards)
        s2 = check_substraight(1, spade_cards)
        s3 = check_substraight(2, spade_cards)
        s4 = check_substraight(3, spade_cards)

        filler = y = np.zeros((self.iterations, 4), dtype=bool)

        straightflush_club = np.append(np.column_stack((c1, c2, c3, c4)), filler, axis=1)
        straightflush_diamond = np.append(np.column_stack((d1, d2, d3, d4)), filler, axis=1)
        straightflush_heart = np.append(np.column_stack((h1, h2, h3, h4)), filler, axis=1)
        straightflush_spade = np.append(np.column_stack((s1, s2, s3, s4)), filler, axis=1)

        # only one suit can be straight flush
        club_highest_straightflush = np.amax(straightflush_club * club_cards, axis=1)
        diamond_highest_straightflush = np.amax(straightflush_diamond * diamond_cards, axis=1)
        heart_highest_straightflush = np.amax(straightflush_heart * heart_cards, axis=1)
        spade_highest_straightflush = np.amax(straightflush_spade * spade_cards, axis=1)

        highest_straighflush = np.amax(np.column_stack((club_highest_straightflush, diamond_highest_straightflush,
                                                        heart_highest_straightflush, spade_highest_straightflush)),
                                       axis=1)

        self.straightflush_score = highest_straighflush
        self.straightflush = highest_straighflush > 0

    def calc_score(self):
        cardtype_names = np.array(
            ['highcard', 'pair', 'twopair', 'threeofakind', 'straight', 'flush', 'fullhouse', 'fourofakind',
             'straightflush'])
        cardtype_multiplier = np.array(
            [self.highcard_multiplier, self.pair_multiplier, self.twopair_multiplier, self.threeofakind_multiplier,
             self.straight_multiplier, self.flush_multiplier, self.fullhouse_multiplier, self.fourofakind_multiplier,
             self.straighflush_multiplier])
        detected_types = np.column_stack((self.highcard.T, self.pair.T, self.twopair.T, self.threeofakind.T,
                                          self.straight.T, self.flush.T, self.fullhouse.T, self.fourofakind.T,
                                          self.straightflush.T))
        detected_types = detected_types * 1
        active_multiplier = cardtype_multiplier * detected_types
        self.all_hand_types = np.core.defchararray.multiply(cardtype_names, detected_types)
        relevant_multiplier = np.argmax(active_multiplier, axis=1)
        self.best_hand_type = np.choose(relevant_multiplier, cardtype_names.T)

        self.totalscore = self.highcard_multiplier * (relevant_multiplier == 0).T * (
            self.single1 * 12 ** 5 + self.single2 * 12 ** 4 + self.single3 * 12 ** 3 + self.single4 * 12 ** 4 + self.single5 * 12 ** 5) + \
                          self.pair_multiplier * (relevant_multiplier == 1).T * (self.pair1 * 12 ** 2 + self.single1) + \
                          self.twopair_multiplier * self.singletwopair * (relevant_multiplier == 2).T * (
                              self.pair1 * 12 ** 3 + self.pair2 * 12 ** 2 + self.single1 * 12 ** 1) + \
                          self.twopair_multiplier * self.threepair * (relevant_multiplier == 2).T * (
                              self.pair1 * 12 ** 3 + self.pair2 * 12 ** 2 + self.pair3 * 12 ** 1) + \
                          self.threeofakind_multiplier * (relevant_multiplier == 3).T * (
                              self.three1 * 12 ** 3 + self.single1 * 12 ** 2 + self.single2 * 12 ** 1) + \
                          self.straight_multiplier * (relevant_multiplier == 4).T * self.highestStraightcard + \
                          self.flush_multiplier * (relevant_multiplier == 5).T * self.flushscore + \
                          self.fullhouse_multiplier * self.fullhouse_score * (
                              self.fullhouse_kicker1 * 12 ** 2 + self.fullhouse_kicker2) + \
                          self.fourofakind_multiplier * self.fourofakind * self.four1 * 12 + self.single1 + \
                          self.straighflush_multiplier * self.straightflush_score

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

        print("straights")
        print(self.s)
        print("straight_index")
        print(self.s_index)
        print("straight")
        print(self.straight)
        print("Highest Straight card")
        print(self.highestStraightcard)
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
        print(self.all_hand_types)
        print("best handtype")
        print(self.best_hand_type)
        print("total calc_score")
        print(self.totalscore)

        print()
        print()


E = Evaluation()
E.run_evaluation(card1=22, card2=1, iterations=100000, )
