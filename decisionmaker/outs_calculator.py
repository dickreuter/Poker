import numpy as np
import itertools as iter


class Outs_Calculator(object):
    def __init__(self):
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

    def create_card_deck(self, hand):
        values = "23456789TJQKA"
        suites = "CDHS"
        Deck = []
        [Deck.append(x + y) for x in values for y in suites]
        # remove drawn cards
        Deck = [elem for elem in Deck if elem not in hand]
        return Deck

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

        hand = pocket + board

        pocket_score, pocket_cards, pocket_result = oc.calc_score(pocket)
        board_score, board_cards, board_result = oc.calc_score(board)
        hand_score, hand_cards, hand_result = oc.calc_score(hand)

        '''print("----------pocket-------")
        print(pocket_score)
        print(pocket_cards)
        print(pocket_result)
        print("----------board-------")
        print(board_score)
        print(board_cards)
        print(board_result)
        print("----------hand-------")
        print(hand_score)
        print(hand_cards)
        print(hand_result)'''

        print("---------CALCULATING OUTS--------")

        oc.calculate_outs(pocket_score, pocket_cards, pocket_result, board_score, board_cards, board_result, hand_score,
                          hand_cards, hand_result, hand)

    def calculate_outs(self, pocket_score, pocket_cards, pocket_result, board_score, board_cards, board_result,
                       hand_score,
                       hand_cards, hand_result, hand):
        outs = 0
        deck = self.create_card_deck(hand)

        # Use functions to calculate outs

        self.get_pocket_pair_to_set(board_result, pocket_result)
        self.get_one_overcard(pocket_cards, board_cards, pocket_result, board_result)
        self.get_gut_shot_straight_draw(hand, deck)
        self.get_two_pair_to_fh(hand_result, board_result)
        self.get_one_pair_to_two_pair_or_set(pocket_result, board_result, hand_result)
        self.get_no_pair_to_pair(pocket_result, board_result, hand_result)
        self.get_two_overcards_to_over_pair(pocket_cards, pocket_result, board_cards, board_result, hand_result)
        self.get_set_to_fh_or_4_kind(pocket_result, hand_result, board_result)
        self.get_open_straight_draw(hand, deck)
        self.get_flush_draw(hand)
        self.get_gut_shot_two_overcards_draw(hand, board_cards, pocket_cards, deck)
        self.get_straight_flush_draw(hand, deck)

        return outs

    # Pocket Pair to Set
    def get_pocket_pair_to_set(self, board_result, pocket_result):
        # TODO:if paired card rank is lower then minimum board card rank then outs = outs / 2
        if pocket_result == 'Pair' and board_result != 'Pair':
            self.pocket_pair_to_set = True
            outs = 2
        else:
            self.pocket_pair_to_set = False
            outs = 0
        print("get_pocket_pair_to_set   OUT AMOUNT ------------  " + str(outs))
        return outs

    # One Overcard
    def get_one_overcard(self, pocket_cards, board_cards, pocket_result, board_result):

        if pocket_result == 'HighCard' and board_result == 'HighCard':
            # check overcard
            for i in range(0, len(pocket_cards)):
                for j in range(0, len(board_cards)):
                    if pocket_cards[i] <= board_cards[j]:
                        self.one_overcard = False
                        outs = 0
                    else:
                        self.one_overcard = True
                        outs = 3
                        break;
        else:
            outs = 0
        print("get_one_overcard   OUT AMOUNT ------------  " + str(outs))
        return outs

    # Inside Straight
    def get_gut_shot_straight_draw(self, hand, deck):
        straight_outs = 0
        for ghost_card in deck:

            tupleList = list(iter.combinations(hand, 4))
            handList = [[]] * len(tupleList)

            for i in range(0, len(tupleList)):
                handList[i] = list(tupleList[i])
                handList[i].append(ghost_card)

            straightDraw, straight_outs = self.check_straight(handList, ghost_card, straight_outs)

        if straight_outs == 4:
            outs = 4
            self.gut_shot_straight = True
        else:
            self.gut_shot_straight = False
            outs = 0
        print("get_gut_shot_straight_draw   OUT AMOUNT ------------  " + str(outs))
        return outs

    # Two Pair to Full House
    def get_two_pair_to_fh(self, hand_result, board_result):
        # TODO ask if board can also have one pair
        if hand_result == 'TwoPair' and board_result == 'HighCard':
            self.two_pair_to_fh = True
            outs = 4
        else:
            self.two_pair_to_fh = False
            outs = 0
        print("get_two_pair_to_fh   OUT AMOUNT ------------  " + str(outs))
        return outs

    # One Pair to Two Pair or Set
    def get_one_pair_to_two_pair_or_set(self, pocket_result, board_result, hand_result):
        if pocket_result == 'HighCard' and hand_result == 'Pair' and board_result == 'HighCard':
            outs = 5
            self.one_pair_to_two_pair_or_set = True
        else:
            outs = 0
            self.one_pair_to_two_pair_or_set = False
        print("get_one_pair_to_two_pair_or_set   OUT AMOUNT ------------  " + str(outs))
        return outs

    # No pair to one pair
    def get_no_pair_to_pair(self, pocket_result, board_result, hand_result):
        if pocket_result == 'HighCard' and hand_result == 'HighCard' and board_result == 'HighCard':
            outs = 6
            self.no_pair_to_pair = True
        else:
            outs = 0
            self.no_pair_to_pair = False
        print("get_no_pair_to_pair   OUT AMOUNT ------------  " + str(outs))
        return outs

    # Two Overcards to Over Pair
    def get_two_overcards_to_over_pair(self, pocket_cards, pocket_result, board_cards, board_result, hand_result):
        outs = 0
        if pocket_result == 'HighCard' and hand_result == 'HighCard' and board_result == 'HighCard':
            # checkovercard
            for i in range(0, len(pocket_cards)):
                for j in range(0, len(board_cards)):
                    if pocket_cards[i] <= board_cards[j]:
                        self.two_overcards_to_over_pair = False
                        outs = 0
                        break;
                    else:
                        self.two_overcards_to_over_pair = True
                        outs = 6
        print("get_two_overcards_to_over_pair   OUT AMOUNT ------------  " + str(outs))
        return outs

    # Set to Full House or Four of a Kind
    def get_set_to_fh_or_4_kind(self, pocket_result, hand_result, board_result):
        if pocket_result == 'Pair' and hand_result == 'ThreeOfAKind' and board_result == 'HighCard':
            outs = 7
            self.set_to_fh_or_4_kind = True
        else:
            outs = 0
            self.set_to_fh_or_4_kind = False
        print("get_set_to_fh_or_4_kind   OUT AMOUNT ------------  " + str(outs))
        return outs

    # Open Straight
    def get_open_straight_draw(self, hand, deck):
        straight_outs = 0
        for ghost_card in deck:

            tupleList = list(iter.combinations(hand, 4))
            handList = [[]] * len(tupleList)

            for i in range(0, len(tupleList)):
                handList[i] = list(tupleList[i])
                handList[i].append(ghost_card)

            straightDraw, straight_outs = self.check_straight(handList, ghost_card, straight_outs)

        if straight_outs == 8:
            self.open_straight = True
            outs = 8
        else:
            outs = 0
            self.open_straight = False

        print("get_open_straight_draw OUTS ----- " + str(outs))
        return outs

    # Flush Draw
    def get_flush_draw(self, hand):

        original_suits = 'CDHS'

        # check flush draw
        suits = [s for _, s in hand]
        for flushSuit in original_suits:  # get the suit of the flush
            suits.count(flushSuit)
            if suits.count(flushSuit) == 4:
                outs = 9
                self.flush_draw = True
            else:
                outs = 0
                self.flush_draw = False
        print("get_flush_draw   OUT AMOUNT ------------  " + str(outs))
        return outs

    # Inside Straight and Two Overcards
    def get_gut_shot_two_overcards_draw(self, hand, board_cards, pocket_cards, deck):

        # check overcard
        for i in range(0, len(pocket_cards)):
            for j in range(0, len(board_cards)):
                if pocket_cards[i] <= board_cards[j]:
                    two_overcards = False
                    break;
                else:
                    two_overcards = True

        if two_overcards:
            outs2 = self.get_gut_shot_straight_draw(hand, deck)
            if outs2 == 4:
                self.gut_shot_two_overcards = True
                outs = 10
            else:
                self.gut_shot_two_overcards = False
                outs = 0
        else:
            self.gut_shot_two_overcards = False
            outs = 0

        print("get_gut_shot_two_overcards_draw OUTS ----- " + str(outs))
        return outs

    # Inside Straight and Flush // Open Straight and Flush
    def get_straight_flush_draw(self, hand, deck):

        original_suits = 'CDHS'
        outs = 0
        straight_outs = 0

        # Open/Gut Shot Straight and Flush Draw
        # check flush draw
        suits = [s for _, s in hand]
        for flush_suit in original_suits:  # get the suit of the flush
            suits.count(flush_suit)
            if suits.count(flush_suit) == 4:
                flush_draw = True
                break;
            else:
                flush_draw = False
        # check straight draw
        for ghost_card in deck:

            tupleList = list(iter.combinations(hand, 4))
            handList = [[]] * len(tupleList)

            for i in range(0, len(tupleList)):
                handList[i] = list(tupleList[i])
                handList[i].append(ghost_card)

            straight_draw, straight_outs = self.check_straight(handList, ghost_card, straight_outs)

        if straight_outs == 8 or straight_outs == 4:
            straight_draw = True

        if flush_draw and straight_draw:

            if straight_outs == 4:
                outs = 12
                print("gut_shot_and_flush   OUT AMOUNT ------------  " + str(outs))
                self.gut_shot_and_flush = True
                self.open_straight_and_flush = False
            elif straight_outs == 8:
                outs = 15
                print("open_straight_and_flush   OUT AMOUNT ------------  " + str(outs))
                self.open_straight_and_flush = True
                self.gut_shot_and_flush = False
            else:
                print("ERROR CHECK STRAIGHT_FLUSH_DRAW FUNCTION")
                outs = 0
        else:
            print("FLUSH AND STRAIGHT NOT FOUND")
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
                    handy = hand
        return straight, straight_outs


if __name__ == '__main__':
    oc = Outs_Calculator()
    my_cards = ['2H', '2C']
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
