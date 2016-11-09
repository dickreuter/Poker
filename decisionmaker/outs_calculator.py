import numpy as np
import itertools as iter
import time
import logging


class Outs_Calculator(object):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        self.pocket_pair_to_set = False
        self.one_overcard = False
        self.gut_shot_straight = False  # get_gut_shot_straight_draw
        self.two_pair_to_fh = False
        self.one_pair_to_two_pair_or_set = False
        self.no_pair_to_pair = False
        self.two_overcards_to_over_pair = False
        self.set_to_fh_or_4_kind = False
        self.open_straight = False  # get_open_straight_draw
        self.flush_draw = False
        self.gut_shot_two_overcards = False  # get_gut_shot_two_overcards_draw
        self.gut_shot_and_flush = False  # get_straight_flush_draw
        self.open_straight_and_flush = False  # get_straight_flush_draw
        self.two_overcards = False  # boolean for two overcards
        self.straight_flush = False  # boolean for straight or flush is counted

    def create_card_deck(self, oc):
        values = "23456789TJQKA"
        suites = "CDHS"
        oc.deck = []
        [oc.deck.append(x + y) for x in values for y in suites]
        # remove drawn cards
        oc.deck = [elem for elem in oc.deck if elem not in oc.hand]
        return oc.deck

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

    def evaluate_hands(self, pocket, board, oc):
        oc.hand = pocket + board
        oc.board = board
        oc.pocket = pocket

        oc.pocket_score, oc.pocket_cards, oc.pocket_result = oc.calc_score(oc.pocket)
        oc.board_score, oc.board_cards, oc.board_result = oc.calc_score(oc.board)
        oc.hand_score, oc.hand_cards, oc.hand_result = oc.calc_score(oc.hand)

        outs = self.calculate_outs(oc)

        return outs

    def calculate_outs(self, oc):
        outs = 0
        oc.deck = self.create_card_deck(oc)

        # Use functions to calculate outs
        outs_list = [0] * 12
        outs_rank = [
            self.get_straight_flush_draw,
            self.get_gut_shot_two_overcards_draw,
            self.get_flush_draw, self.get_open_straight_draw,
            self.get_gut_shot_straight_draw,
            self.get_set_to_fh_or_4_kind,
            self.get_two_overcards_to_over_pair,
            self.get_one_overcard,
            self.get_no_pair_to_pair,
            self.get_one_pair_to_two_pair_or_set,
            self.get_two_pair_to_fh,
            self.get_pocket_pair_to_set
        ]

        for i in range(0, len(outs_rank)):
            outs = outs_list[i] = outs_rank[i](oc)
            if i == 0 and outs_list[0] != 0:
                outs = outs_list[0] + (outs_rank[6](oc) + outs_rank[7](oc)) / 2
                break
            if i == 1 and outs_list[i] != 0:
                outs = outs_list[1]
                break
            elif i == 2 and outs_list[i] != 0:
                outs = outs_list[2] + (outs_rank[6](oc) + outs_rank[7](oc)) / 2
                break
            elif i == 3 and outs_list[i] != 0:
                outs = outs_list[3] + (outs_rank[6](oc) + outs_rank[7](oc)) / 2
                break
            elif i == 4 and outs_list[i] != 0:
                outs = outs_list[4] + (outs_rank[6](oc) + outs_rank[7](oc)) / 2
                break
            elif i == 5 and outs_list[i] != 0:
                outs = outs_list[5]
                break
            elif i == 6 and outs_list[i] != 0:
                outs = outs_list[6]
                break
            elif i == 7 and outs_list[i] != 0:
                outs = outs_list[7]
                break
            elif i == 8 and outs_list[i] != 0:
                outs = outs_list[8]
                break
            elif i == 9 and outs_list[i] != 0:
                outs = outs_list[9]
                break
            elif i == 10 and outs_list[i] != 0:
                outs = outs_list[10]
                break
            elif i == 11 and outs_list[i] != 0:
                outs = outs_list[11]
                break

        self.logger.info(outs)

        return outs

    # Pocket Pair to Set
    # Revisit this
    def get_pocket_pair_to_set(self, oc):
        # TODO:if paired card rank is lower then minimum board card rank then outs = outs / 2
        if oc.pocket_result == 'Pair' and oc.board_result != 'Pair':
            self.pocket_pair_to_set = True
            outs = 2
            overcard = 0
            # calculate overcards
            for i in range(0, len(oc.pocket_cards)):
                for j in range(0, len(oc.board_cards)):
                    if (oc.pocket_cards[i] > oc.board_cards[j]):
                        overcard += 1
            # if overcard is 3, get highest board card also as outs
            if (overcard == 3):
                outs += 3
            # if overcard is 4, get highest 2 board card also as outs
            if (overcard == 4):
                outs += 6
        else:
            self.pocket_pair_to_set = False
            outs = 0
        return outs

    # One Overcard
    # TODO: REMOVE IF STATEMENT
    def get_one_overcard(self, oc):
        outs = 0
        if oc.pocket_result == 'HighCard' and oc.board_result == 'HighCard' and self.no_pair_to_pair == False:
            # check overcard
            if self.two_overcards == False:
                for i in range(0, len(oc.pocket_cards)):
                    if self.one_overcard == True:
                        break
                    else:
                        for j in range(0, len(oc.board_cards)):
                            if oc.pocket_cards[i] <= oc.board_cards[j]:
                                self.one_overcard = False
                                outs = 0
                                break
                            else:
                                self.one_overcard = True
                                outs = 3

        return outs

    # Inside Straight
    def get_gut_shot_straight_draw(self, oc):
        straight_outs = 0
        boardFlush = self.check_board_flush()
        for ghost_card in oc.deck:

            tupleList = list(iter.combinations(oc.hand, 4))
            handList = [[]] * len(tupleList)

            for i in range(0, len(tupleList)):
                handList[i] = list(tupleList[i])
                handList[i].append(ghost_card)

            straightDraw, straight_outs = self.check_straight(handList, ghost_card, straight_outs)

        if straight_outs == 4:
            outs = 4
            if boardFlush: outs -= 1
            self.gut_shot_straight = True
        else:
            self.gut_shot_straight = False
            outs = 0

        return outs

    # Two Pair to Full House
    def get_two_pair_to_fh(self, oc):
        # TODO ask if board can also have one pair
        if oc.hand_result == 'TwoPair' and oc.board_result == 'HighCard':
            self.two_pair_to_fh = True
            outs = 4
        else:
            self.two_pair_to_fh = False
            outs = 0
        return outs

    # One Pair to Two Pair or Set
    def get_one_pair_to_two_pair_or_set(self, oc):
        if oc.pocket_result == 'HighCard' and oc.hand_result == 'Pair' and oc.board_result == 'HighCard':
            outs = 5
            self.one_pair_to_two_pair_or_set = True
        else:
            outs = 0
            self.one_pair_to_two_pair_or_set = False
        return outs

    # No pair to one pair
    # TODO: REMOVE IF STATEMENT
    def get_no_pair_to_pair(self, oc):
        if oc.pocket_result == 'HighCard' and oc.hand_result == 'HighCard' and oc.board_result == 'HighCard' and self.two_overcards == False:
            outs = 6
            self.no_pair_to_pair = True
        else:
            outs = 0
            self.no_pair_to_pair = False
        return outs

    # Two Overcards to Over Pair
    # TODO: OVERCARD BOOL STATEMNT
    def get_two_overcards_to_over_pair(self, oc):
        outs = 0
        if oc.pocket_result == 'HighCard' and oc.hand_result == 'HighCard' and oc.board_result == 'HighCard':
            # checkovercard
            for i in range(0, len(oc.pocket_cards)):
                for j in range(0, len(oc.board_cards)):
                    if oc.pocket_cards[i] <= oc.board_cards[j]:
                        self.two_overcards_to_over_pair = False
                        outs = 0
                        self.two_overcards = False
                        break
                    else:
                        self.two_overcards_to_over_pair = True
                        self.two_overcards = True
                        outs = 6
        return outs

    # Set to Full House or Four of a Kind
    def get_set_to_fh_or_4_kind(self, oc):
        if oc.pocket_result == 'Pair' and oc.hand_result == 'ThreeOfAKind' and oc.board_result == 'HighCard':
            outs = 7
            self.set_to_fh_or_4_kind = True
        else:
            outs = 0
            self.set_to_fh_or_4_kind = False
        return outs

    # Open Straight
    def get_open_straight_draw(self, oc):
        straight_outs = 0
        boardFlush = self.check_board_flush()
        for ghost_card in oc.deck:

            tupleList = list(iter.combinations(oc.hand, 4))
            handList = [[]] * len(tupleList)

            for i in range(0, len(tupleList)):
                handList[i] = list(tupleList[i])
                handList[i].append(ghost_card)

            straightDraw, straight_outs = self.check_straight(handList, ghost_card, straight_outs)

        if straight_outs == 8:
            self.open_straight = True
            outs = 8
            if boardFlush: outs -= 1
        else:
            outs = 0
            self.open_straight = False

        return outs

    # Flush Draw
    def get_flush_draw(self, oc):
        original_suits = 'CDHS'
        bool_outs = True
        # check flush draw
        boardFlush = self.check_board_flush
        suits = [s for _, s in oc.hand]
        for flushSuit in original_suits:  # get the suit of the flush
            suits.count(flushSuit)
            if suits.count(flushSuit) == 4:
                outs = 9
                if boardFlush: outs -= 1
                self.flush_draw = True
                break
            else:
                outs = 0
                self.flush_draw = False
        return outs

    # Inside Straight and Two Overcards
    def get_gut_shot_two_overcards_draw(self, oc):
        # check overcard
        for i in range(0, len(oc.pocket_cards)):
            for j in range(0, len(oc.board_cards)):
                if oc.pocket_cards[i] <= oc.board_cards[j]:
                    two_overcards = False
                    break
                else:
                    two_overcards = True

        if two_overcards:
            outs2 = self.get_gut_shot_straight_draw(oc)
            if outs2 == 4:
                self.gut_shot_two_overcards = True
                outs = 10
            else:
                self.gut_shot_two_overcards = False
                outs = 0
        else:
            self.gut_shot_two_overcards = False
            outs = 0

        return outs

    # Inside Straight and Flush // Open Straight and Flush
    def get_straight_flush_draw(self, oc):
        original_suits = 'CDHS'
        outs = 0
        straight_outs = 0

        # Open/Gut Shot Straight and Flush Draw
        # check flush draw

        boardFlush = self.check_board_flush()
        suits = [s for _, s in oc.hand]
        for flush_suit in original_suits:  # get the suit of the flush
            suits.count(flush_suit)
            if suits.count(flush_suit) == 4:
                self.flush_draw = True
                break
            else:
                self.flush_draw = False
        # check straight draw
        for ghost_card in oc.deck:

            tupleList = list(iter.combinations(oc.hand, 4))
            hand_list = [[]] * len(tupleList)

            for i in range(0, len(tupleList)):
                hand_list[i] = list(tupleList[i])
                hand_list[i].append(ghost_card)

            straight_draw, straight_outs = self.check_straight(hand_list, ghost_card, straight_outs)

        if straight_outs == 8 or straight_outs == 4:
            straight_draw = True

        if self.flush_draw and straight_draw:
            if straight_outs == 4:
                outs = 12
                if boardFlush: outs -= 1
                self.gut_shot_and_flush = True
                self.open_straight_and_flush = False
            elif straight_outs == 8:
                outs = 15
                if boardFlush: outs -= 1
                self.open_straight_and_flush = True
                self.gut_shot_and_flush = False
            else:
                self.logger.warning("ERROR CHECK STRAIGHT_FLUSH_DRAW FUNCTION")
                outs = 0

        return outs

    # Determine how many straight outs are they
    def check_straight(self, hand_list, ghost_card, straight_outs):
        card_ranks_original = '23456789TJQKA'
        straight = False
        tempHand = [[]] * 5
        for hand in hand_list:
            rcounts = {card_ranks_original.find(r): ''.join(hand).count(r) for r, _ in hand}.items()
            score, card_ranks = zip(*sorted((cnt, rank) for rank, cnt in rcounts)[::-1])

            # get rank of ghost card to check if it is gut shot
            rcounts_ghost = {card_ranks_original.find(r): ''.join(ghost_card).count(r) for r in ghost_card}.items()
            score_ghost, ghost_card_rank = zip(*sorted((cnt, rank) for rank, cnt in rcounts_ghost)[::-1])
            ghost_card_rank = sorted(ghost_card_rank, reverse=True)

            if 12 in card_ranks:  # adjust if 5 high straight
                card_ranks += (-1,)
            sortedCrdRanks = sorted(card_ranks, reverse=True)  # sort again as if pairs the first rank matches the pair
            for i in range(len(sortedCrdRanks) - 4):
                straight = sortedCrdRanks[i] - sortedCrdRanks[i + 4] == 4
                if straight:
                    # check duplicate straight hands
                    if tempHand[4] != hand[4]:
                        straight_outs += 1
                    tempHand = hand
        return straight, straight_outs

    def check_board_flush(self):
        flush_draw = False
        original_suits = 'CDHS'
        suits = [s for _, s in self.board]
        for flush_suit in original_suits:  # get the suit of the flush
            suits.count(flush_suit)
            if suits.count(flush_suit) >= 2:
                flush_draw = True
                break
            else:
                flush_draw = False

        return flush_draw


if __name__ == '__main__':
    start_time = time.clock()
    oc = Outs_Calculator()

    my_cards = ['KH', 'KC']
    cards_on_table = ['QD', '4H', '9S']
    print("POCKET PAIR TO SET")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['AS', '8D']
    cards_on_table = ['JC', '5S', '2D']
    print("ONE OVERCARD")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['JH', '9C']
    cards_on_table = ['QS', '8D', '4C']
    print("INSIDE STRAIGHT DRAW")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['KH', 'QS']
    cards_on_table = ['KC', 'QD', '5S']
    print("TWO PAIR TO FULL HOUSE")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['AC', 'QD']
    cards_on_table = ['AD', 'TC', '3S']
    print("ONE PAIR TO TWO PAIR OF SET")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['9C', '7D']
    cards_on_table = ['2S', '3D', 'JC']
    print("NO PAIR TO PAIR")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['AD', 'JH']
    cards_on_table = ['TC', '8D', '2S']
    print("TWO OVERCARDS TO OVER PAIR")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['6C', '6D']
    cards_on_table = ['6S', '7H', 'JC']
    print("SET TO FULLHOUSE / FOUR OF A KIND")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['9C', '8D']
    cards_on_table = ['7C', 'TH', '3S']
    print("OPEN ENDED STRAIGHT DRAW")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['KS', 'JS']
    cards_on_table = ['AS', '6S', '8D']
    print("FLUSH DRAW")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['AC', 'KD']
    cards_on_table = ['QH', 'TC', '2S']
    print("INSIDE STRAIGHT AND TWO OVERCARDS DRAW")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['AD', 'KD']
    cards_on_table = ['JD', 'QS', '3D']
    print("INSIDE STRAIGHT AND FLUSH DRAW")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    my_cards = ['KH', 'QH']
    cards_on_table = ['TH', 'JS', '4H']
    print("OPEN STRAIGHT AND FLUSH DRAW")
    print(my_cards + cards_on_table)
    print("----------------")
    oc.evaluate_hands(my_cards, cards_on_table, oc)
    print("")
    print("")
    print("")

    print(time.clock() - start_time)
