
import time
import numpy as np

strided = np.lib.stride_tricks.as_strided


class Evaluation(object):
    def __init__(self):
        self.highcard_multiplier = 1
        self.pair_multiplier = 10**2
        self.twopair_multiplier = 10**4
        self.threeofakind_multiplier = 10**6
        self.straight_multiplier = 10**8
        self.flush_multiplier = 10**10
        self.fullhouse_multiplier = 10**12
        self.fourofakind_multiplier = 10**14
        self.straighflush_multiplier = 10**18

    def card_to_num(self,card):
        suits_with_remainders = np.array([1,2,3])
        cardNum = card[0]
        cardSuit = card[1]
        if np.any(cardSuit == suits_with_remainders):
            return(cardNum - 1) * 4 + cardSuit
        else:
            return cardNum*4

        #examples:  [2,1] = 5 [2,2] = 6 [2,3] = 7 [2,0] = 8 [3,1] = 9 etc...

    def set_args(self,card1, card2, tablecards,iterations,player_amount):
        self.card1 = self.card_to_num(card1)
        self.card2 = self.card_to_num(card2)
        tableCardList = []
        for i in range(0,len(tablecards)):
            tableCard = self.card_to_num(tablecards[i])
            tableCardList.append(tableCard)
        self.tableCards = np.array(tableCardList)
        self.iterations = iterations
        self.player_amount = player_amount

    def run_evaluation(self, card1, card2, tablecards, iterations, player_amount):
        self.start = time.time()
        self.set_args(card1, card2, tablecards, iterations, player_amount)
        self.distribute_cards()
        self.get_counts()
        self.get_kickers()
        self.get_multiplecards()
        self.get_straightflush()
        self.get_four_of_a_kind()
        self.get_fullhouse()
        self.get_flush(iterations, player_amount)
        self.get_straight()
        self.get_three_of_a_kind()
        self.get_two_pair_score()
        self.get_pair_score()
        self.get_highcard()

        wins = self.calc_score()

        print("Time Elapsed: "+str(time.time() - self.start))

        return wins

    def distribute_cards(self):
        deck = np.arange(5,57) #52 cards starting at 5 so that later code will make arrays starting at 2
        mycards = np.array([self.card1, self.card2])
        mask = np.isin(deck,mycards,invert =True)
        deck= deck[mask] #deletes my cards out of deck
        mask = np.isin(deck, self.tableCards,invert = True)
        deck = deck[mask] #deletes set tableCards out of deck
        mycards = np.array([self.card1, self.card2])
        mycards = np.append(mycards, self.tableCards) # [My first card, My second card, TableCards]

        #shuffles the deck
        alldecks = np.tile(deck, reps=(self.iterations, 1)) # creates copies of decks  = number of games
        temp_random = np.random.random(alldecks.shape) # create random number arrays that are the size of "alldecks"
        idx = np.argsort(temp_random, axis=-1) #creates ranking of random numbers Highest to Lowest
        shuffled = alldecks[np.arange(alldecks.shape[0])[:, None], idx] #organizes deck according to random ranking

        cards_at_end_of_game = 7 # each player will have 7 cards in their array
        shuffled_cards_to_append = cards_at_end_of_game - len(self.tableCards) # 7 total cards minus ones set to be on the table

        #makes opponent's cards for all games lookup table - later to be turned into numpy array
        cards_player = {}
        for i in range(0, self.player_amount-1):
            startingOppsCard= shuffled_cards_to_append + (i*2)
            endingOppsCard = startingOppsCard+2
            cards_player[i] = shuffled[:,startingOppsCard:endingOppsCard] #first bit of random cards are set aside for random draws
            np.delete(shuffled,shuffled[:,startingOppsCard:endingOppsCard])
            if len(self.tableCards) != 0:
                cards_player[i] = np.insert(cards_player[i] , 2 , self.tableCards[:,None],axis = 1) # puts set tablecards into players 7 cards

        cards_combined_mine = np.append(np.tile(mycards, reps=(self.iterations, 1)), shuffled, axis=1)[:,
                              0:cards_at_end_of_game] #repeats my cards iterations of time to match opponents random iteration arrays
        cards_combined_array = [cards_combined_mine] # create cards list that starts with my cards

        #append players 7 cards to yours
        for i in range(0, self.player_amount-1):
            cards_combined_array.append(np.append(cards_player[i], shuffled, axis=1)[:, 0:cards_at_end_of_game])

        cards_combined = np.stack(cards_combined_array, axis=-1)  # stack over last axis (=axis 3)
        cards = np.ceil(cards_combined / 4)
        suits = cards_combined % 4 * 1
        self.decks = np.stack((cards, suits), axis=2)  # [iterations, 7, card or suits, player_index]
        self.cards = self.decks[:, :, 0, :]  # [iterations, 7, player_index]
        self.suits = self.decks[:, :, 1, :]  # [iterations, 7, player_index]
        self.cards_sorted = np.sort(self.cards, axis=1)[:, ::-1, :]

        # print('cards_combined \n {}'.format(cards_combined))
        # print("All Decks \n {}".format(alldecks))
        # print("Players Cards \n {}".format(cards_player))
        # print("Cards Combined {}".format(cards_combined))
        # print("self.decks {}".format(self.decks))
        # print("self.cards \n {}".format(self.cards))
        # print("self.suits \n {}".format(self.suits))
        # print("self.cards_sorted \ n {}".format(self.cards_sorted))


    def get_counts(self):
        #Counts = [iteration,player,card]
        self.counts = (np.arange(13, 0, -1) == self.cards[:, :, :, None]).sum(1)  # occurrences of each cards
        self.highestCard = self.cards_sorted[:, 0, :]  # iterations, cards_sorted, player

        # print('Counts {}'.format(self.counts))


    def get_kickers(self):
        self.cards13to1 = np.arange(13, 0, -1) * -1 # A = 13 2 = 1

        # [iteration, player]
        # get bool of where counts ==2, multiply by value, sort, invert, get highest pair, second highest, third highest
        self.pair1 = np.sort((self.counts == 2) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, 0]
        self.pair2 = np.sort((self.counts == 2) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, 1]
        self.pair3 = np.sort((self.counts == 2) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, 2]


        self.three1 = np.sort((self.counts == 3) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, 0]
        self.three2 = np.sort((self.counts == 3) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, 1]

        self.four1 = np.sort((self.counts == 4) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, 0]

        self.single1 = np.sort((self.counts == 1) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, 0]
        self.single2 = np.sort((self.counts == 1) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, 1]
        self.single3 = np.sort((self.counts == 1) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, 2]
        self.single4 = np.sort((self.counts == 1) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, 3]
        self.single5 = np.sort((self.counts == 1) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, 4]
        self.single = np.sort((self.counts == 1) * self.cards13to1 * -1, axis=2)[:, :, ::-1][:, :, :]

        # print('self.pair1 \n {}'.format(self.pair1))
        # print('self.pair2 \n {}'.format(self.pair2))
        # print('self.pair3 \n {}'.format(self.pair3))
        #
        # print('self.three1 \n {}'.format(self.three1))
        # print('self.three2 \n {}'.format(self.three2))
        #
        # print('self.four1 \n {}'.format(self.four1))
        #
        # print('self.single 1 \n {}'.format(self.single1))
        # print('self.single 2 \n {}'.format(self.single2))
        # print('self.single 3 \n {}'.format(self.single3))
        # print('self.single 4 \n {}'.format(self.single4))


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

        # print('pair amount \n {}'.format(self.pair_amount))
        # print('three of a kind amount \n {}'.format(self.threeofakind_amount))
        # print('four of a kind amount \n {}'.format(self.fourofakind_amount))
        #
        # print('pair \n {}'.format(self.pair))
        # print('two pair \n {}'.format(self.twopair))
        # print('single two pair \n {}'.format(self.singletwopair))
        # print('threepair \n {}'.format(self.threepair))
        # print('three of a kind \n {}'.format(self.threeofakind_amount))
        # print('four of a kind \n {}'.format(self.fourofakind))



    def get_straightflush(self):
        # first dimension is the suit type, second the montecarlo, third the card, and fourth the player
        cards_stacked_suits = (self.suits == np.arange(4)[:, None, None, None]) * 1 * self.cards
        cards_stacked_suits = np.sort(cards_stacked_suits * -1, axis=2) * -1
        add_low = cards_stacked_suits[:, :, 0, :] - 13  # add highest card - 12 for ace low straight
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

        # print('straight flush \n {}'.format(self.straightflush))
        # print('straight flush score \n {}'.format(self.straightflush_score))

    def get_four_of_a_kind(self):
        four_of_a_kind_multi = 100
        kicker_multi = 1
        self.fourofakindScore = self.four1* four_of_a_kind_multi + self.single1*kicker_multi
        self.fourofakindScore = self.fourofakindScore/four_of_a_kind_multi

        # print('four of a kind score \n {}'.format(self.fourofakindScore))
        # print('four of a kind \n {}'.format(self.fourofakind))

    def get_fullhouse(self):
        fullHouseMulti = 100
        self.fullhouse = np.logical_or(self.threeofakind_amount == 2,
                                       np.logical_and(self.threeofakind_amount == 1, self.pair_amount >= 1))

        self.fullhouse_kicker1 = np.sort((self.counts == 3) * np.arange(13, 0, -1), axis=2)[:, :, ::-1][:, :, 0]

        highest_pair = np.sort((self.counts == 2) * np.arange(13, 0, -1), axis=2)[:, :, ::-1][:, :, 0]

        second_threeofakind = np.sort((self.counts == 3) * np.arange(13, 0, -1), axis=2)[:, :, ::-1][:, :, 1]

        self.fullhouse_kicker2 = np.amax(np.stack((highest_pair, second_threeofakind), axis=1), axis=1)

        self.fullhouseScore = self.fullhouse * (self.fullhouse_kicker1 * fullHouseMulti + self.fullhouse_kicker2)
        self.fullhouseScore = self.fullhouseScore/ fullHouseMulti

        # print('full house score \n {}'.format(self.fullhouseScore))
        # print("Full House {}".format(self.fullhouse))
        # print("Full House Kicker {}".format(self.fullhouse_kicker1))

    def get_flush(self, iterations, player_amount):
        self.suitCounts = (self.suits[:, :, :, None] == np.arange(0, 4)).sum(1)  # occurrences of each suit
        self.maxsuit = np.argmax(self.suitCounts, axis=2)
        self.flush = self.suitCounts[np.arange(iterations)[:, None], np.arange(player_amount), self.maxsuit] >= 5
        self.flushcards = self.suits == self.maxsuit[:, None]
        self.sorted_flushcards = (np.sort(self.flushcards * self.cards * -1, axis=1) * -1)
        self.sorted_5flushcards = np.delete(self.sorted_flushcards, [5, 6], axis=1)
        multiplier = np.array([10**8, 10**6, 10**4, 10**2, 1])
        self.flushScore = (self.sorted_5flushcards * multiplier[..., :, None]).sum(1)
        self.flushScore = self.flushScore/np.sum(multiplier[:])

        # print('get_flush \n {}'.format(self.flushScore))

    def get_straight(self):
        add_low = self.cards_sorted[:, 0, :] - 13
        straight_cards = np.append(self.cards_sorted, add_low[:, None, :], axis=1)

        stri = straight_cards.strides
        shpe = straight_cards.shape

        cards_stacked_straightvariants = strided(straight_cards,
                                                 shape=(4, shpe[0], 5, shpe[2]),
                                                 strides=(stri[1], stri[0], stri[1], stri[2]))

        cards_stacked_straightvariants_highest_card = cards_stacked_straightvariants[..., 0, :]
        straights_variants = np.all(np.diff(cards_stacked_straightvariants, axis=2) == -1, axis=2)
        self.straight = np.any(straights_variants, axis=0)
        self.straightScore = np.sum(cards_stacked_straightvariants_highest_card * straights_variants, axis=0)

        # print('straight \n {}'.format(self.straight))
        # print('Straight Score \n {}'.format(self.straightScore))

    def get_three_of_a_kind(self):
        threepairscore_mult = 10
        kickerMulti = 1
        self.threeScore = (self.three1*threepairscore_mult) + (self.single1 + self.single2)*kickerMulti
        self.threeScore = self.threeScore/threepairscore_mult

        # print('Three of a kind Score {}'.format(self.threeScore))

    def get_two_pair_score(self):
        firstTwoPairScoreMulti = 1000
        secondTwoPairScoreMulti = 10
        kickerMulti = 1
        self.twoPairScore = (self.pair1 * firstTwoPairScoreMulti) + (self.pair2 * secondTwoPairScoreMulti) + (self.single1*kickerMulti)
        self.twoPairScore = self.twoPairScore/firstTwoPairScoreMulti

        # print('Two pair score \n {}'.format(self.twoPairScore))

    def get_pair_score(self):
        PairScoreMulti = 100
        kickerMulti = 1
        self.pairScore = (self.pair1 * PairScoreMulti) + (self.single1 + self.single2 + self.single3)*kickerMulti
        self.pairScore = self.pairScore/PairScoreMulti

        # print('Pair Score \n  {}'.format(self.pairScore))

    def get_highcard(self):
        HighCard1Val = 10**8
        HighCard2Val = 10**6
        HighCard3Val = 10**4
        HighCard4Val = 10**2
        HighCard5Val = 1
        HighCardVals = np.array([HighCard1Val, HighCard2Val, HighCard3Val, HighCard4Val, HighCard5Val])

        self.highcard = np.all(np.stack((self.pair_amount == 0, self.threeofakind == False,
                                         self.fourofakind_amount == 0, self.straight == False,
                                         self.flush == False), axis=0), axis=0)

        cards13to1 = np.arange(13, 0, -1) * -1
        HighCards = np.sort((self.counts == 1) * cards13to1 * -1, axis=2)[:, :, ::-1][:, :, :5]
        highCardsVal = HighCards*HighCardVals
        highCardsVal = highCardsVal.sum(2)
        self.highCardsVal = highCardsVal/np.sum(HighCardVals)

        # print('highCards Val \n {}'.format(self.highCardsVal))

    def calc_score(self):
        cardtype_names = np.array(
            ['highcard', 'pair', 'twopair', 'threeofakind', 'straight', 'flush', 'fullhouse', 'fourofakind',
             'straightflush'])
        self.cardtype_multiplier = np.array(
            [self.highcard_multiplier, self.pair_multiplier, self.twopair_multiplier, self.threeofakind_multiplier,
             self.straight_multiplier, self.flush_multiplier, self.fullhouse_multiplier, self.fourofakind_multiplier,
             self.straighflush_multiplier])
        self.detected_types = np.stack((self.highcard, self.pair, self.twopair, self.threeofakind,
                                        self.straight, self.flush, self.fullhouse, self.fourofakind,
                                        self.straightflush), axis=0)
        self.hand_vals = np.stack((self.highCardsVal, self.pairScore, self.twoPairScore, self.threeScore,self.straightScore,
                                   self.flushScore,self.fullhouseScore,self.fourofakindScore,self.straightflush_score),axis = 0)

        detected_types = self.detected_types * 1
        self.active_multiplier = self.cardtype_multiplier[:,None,None] * detected_types * self.hand_vals
        self.ordered_multiplier = np.sort(self.active_multiplier,axis = 0)[::-1,:,:]
        highestVals = np.argmax(self.ordered_multiplier[0,:,:], axis=1)
        Winners = (self.ordered_multiplier[0, ::] == np.amax(self.ordered_multiplier[0, :, :], axis=1)[:, None])
        MyWinnerMask = np.zeros(self.player_amount, dtype=int)
        MyWinnerMask[0] = 1
        MyWinnArray = (Winners == MyWinnerMask).all(1)
        MyWins = np.sum(MyWinnArray,axis = 0)



        # print('cardtype_multiplier \n {}'.format(self.cardtype_multiplier))
        # print('detected_types \n {}'.format(detected_types))
        # print('hand_vals \n {}'.format(self.hand_vals))
        # print('active_multiplier \n {}'.format(self.active_multiplier))
        # print('ordered_multiplier \n {}'.format(self.ordered_multiplier))
        # print('highest vals \n {}'.format(highestVals))
        # print('My Wins \n {}'.format(MyWins))

        return MyWins / self.iterations




E = Evaluation()
winPercent = E.run_evaluation(card1=[2,0], card2=[2,1], tablecards=[[5,3],[3,2]], iterations=10000, player_amount=3)

print(winPercent)