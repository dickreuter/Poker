import numpy as np
import itertools as iter


class Outs_Calculator(object):
    def __init__(self):
        pass

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

        pocketScore, pocketCards, pocketResult = oc.calc_score(pocket)
        boardScore, boardCards, boardResult = oc.calc_score(board)
        handScore, handCards, handResult = oc.calc_score(hand)

        print("----------pocket-------")
        print(pocketScore)
        print(pocketCards)
        print(pocketResult)
        print("----------board-------")
        print(boardScore)
        print(boardCards)
        print(boardResult)
        print("----------hand-------")
        print(handScore)
        print(handCards)
        print(handResult)

        print("---------CALCULATING OUTS--------")

        oc.calculate_outs(pocketScore, pocketCards, pocketResult, boardScore, boardCards, boardResult, handScore,
                          handCards, handResult, hand)

    def create_card_deck(self, hand):
        values = "23456789TJQKA"
        suites = "CDHS"
        Deck = []
        [Deck.append(x + y) for x in values for y in suites]
        # remove drawn cards
        Deck = [elem for elem in Deck if elem not in hand]
        return Deck

    def calculate_outs(self, pocketScore, pocketCards, pocketResult, boardScore, boardCards, boardResult, handScore,
                       handCards, handResult, hand):
        deck = self.create_card_deck(hand)
        straightDraw = False
        gutShot = False
        outs = 0
        handy = []
        original_suits = 'CDHS'

        # Open Straight and Flush Draw
        # check flush draw
        suits = [s for _, s in hand]
        for flushSuit in original_suits:  # get the suit of the flush
            suits.count(flushSuit)

            if suits.count(flushSuit) == 4:
                flushDraw = True
            else:
                flushDraw = False

        # check straight draw
        straight_outs = 0
        a = 0

        for ghost_card in deck:

            tulpeList = list(iter.combinations(hand, 4))
            handList = [[]] * len(tulpeList)

            for i in range(0,len(tulpeList)):
                handList[i] = list(tulpeList[i])
                handList[i].append(ghost_card)

            straightDraw, handy, gutShot, straight_outs = self.check_straight(handList, ghost_card, straight_outs)
        print("OUT AMOUNT ------------  " + str(straight_outs))

        if (straight_outs == 8 or straight_outs == 4):
            straightDraw = True

        if (flushDraw == True and straightDraw == True):
            if (straight_outs == 4):
                print("GUT SHOT -- OUTS:  " + str(straight_outs))
            else:
                print("OPEN STRAIGHT -- OUTS:  " + str(straight_outs))
            print("Straight and Flush Draw")

        elif (flushDraw == True and straightDraw == False):
            print("Flush Draw")

        elif (flushDraw == False and straightDraw):
            if (straight_outs == 4):
                print("GUT SHOT -- OUTS:  " + str(straight_outs))
            else:
                print("OPEN STRAIGHT -- OUTS:  " + str(straight_outs))
            print("Straight Draw")

        return outs

    def check_straight(self, handList, ghost_card, straight_outs):
        card_ranks_original = '23456789TJQKA'
        original_suits = 'CDHS'
        straight = False
        gutShot = False
        handy = []
        tempHand = [[]] * 5
        for hand in handList:
            rcounts = {card_ranks_original.find(r): ''.join(hand).count(r) for r, _ in hand}.items()
            score, card_ranks = zip(*sorted((cnt, rank) for rank, cnt in rcounts)[::-1])

            # get rank of ghost card to check if it is gut shot
            rcountsGhost = {card_ranks_original.find(r): ''.join(ghost_card).count(r) for r in ghost_card}.items()
            scoreGhost, ghost_card_rank = zip(*sorted((cnt, rank) for rank, cnt in rcountsGhost)[::-1])
            ghost_card_rank = sorted(ghost_card_rank, reverse=True)

            if 12 in card_ranks:  # adjust if 5 high straight
                card_ranks += (-1,)
            sortedCrdRanks = sorted(card_ranks, reverse=True)  # sort again as if pairs the first rank matches the pair
            for i in range(len(sortedCrdRanks) - 4):
                straight = sortedCrdRanks[i] - sortedCrdRanks[i + 4] == 4
                if (straight == True):
                    #check duplicate straight hands
                    if( tempHand[4] != hand[4]):
                        straight_outs = straight_outs + 1
                    tempHand = hand
                    handy = hand
        return straight, handy, gutShot, straight_outs


if __name__ == '__main__':
    oc = Outs_Calculator()
    my_cards = ['AS', '2S']
    cards_on_table = ['3S', '4S', '8C','JH', 'QH']
    oc.evaluate_hands(my_cards, cards_on_table, oc)
