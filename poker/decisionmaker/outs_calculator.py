import numpy as np
import itertools as iter
import logging


class Outs_Calculator(object):
    def __init__(self):
        self.logger = logging.getLogger('out_calc')
        self.logger.setLevel(logging.DEBUG)


        self.gut_shot_straight = False  # get_gut_shot_straight_draw
        self.open_straight = False  # get_open_straight_draw
        self.flush_draw = False
        self.gut_shot_and_flush = False  # get_straight_flush_draw
        self.open_straight_and_flush = False  # get_straight_flush_draw

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
        elif score[0] == 3:
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
        outs_list = [0] * 4
        outs_rank = [
            self.get_straight_flush_draw,
            self.get_flush_draw, self.get_open_straight_draw,
            self.get_gut_shot_straight_draw
        ]

        #print(len(outs_rank))

        for i in range(0, len(outs_rank)):
            outs = outs_list[i] = outs_rank[i](oc)
            if i == 0 and outs_list[0] != 0:
                outs = outs_list[0]
                break
            if i == 1 and outs_list[i] != 0:
                outs = outs_list[1]
                break
            elif i == 2 and outs_list[i] != 0:
                outs = outs_list[2]
                break
            elif i == 3 and outs_list[i] != 0:
                outs = outs_list[3]
                break

        self.logger.info(outs)
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
            #if boardFlush: outs -= 1
            self.gut_shot_straight = True
        else:
            self.gut_shot_straight = False
            outs = 0

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
            #if boardFlush: outs -= 1
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
                #if boardFlush: outs -= 1
                self.flush_draw = True
                break
            else:
                outs = 0
                self.flush_draw = False
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
                #if boardFlush: outs -= 1
                self.gut_shot_and_flush = True
                self.open_straight_and_flush = False
            elif straight_outs == 8:
                outs = 15
                #if boardFlush: outs -= 1
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