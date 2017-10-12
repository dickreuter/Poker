from montecarlo_python import MonteCarlo
import json
import time
from collections import OrderedDict
from operator import itemgetter


if __name__ == '__main__':
    Simulation = MonteCarlo()

    equity_dict={}


    hands='23456789TJQKA'
    suits=['D','H']
    for suit1 in suits:
        for i in range(len(hands)):
            h1=hands[i]
            for j in range(i,len(hands)):
                h2=hands[j]
                card1=h1+suit1
                card2=h2+suits[0]
                cardlist=[card1,card2]
                my_cards=[(cardlist)]

                if not (suit1==suits[0] and card1==card2):
                    cards_on_table = []
                    players = 2
                    start_time = time.time()+2
                    Simulation.run_montecarlo(my_cards, cards_on_table, players, 1, maxRuns=15000, timeout=start_time, ui=None, ghost_cards='', opponent_range=1)
                    print("--- %s seconds ---" % (time.time() - start_time))
                    equity = Simulation.equity  # considering draws as wins

                    suited_str='S' if suit1==suits[0] else 'O'
                    if my_cards[0][0][0]==my_cards[0][1][0]: suited_str=''
                    print (my_cards[0][0][0]+my_cards[0][1][0]+suited_str+": "+str(equity))
                    equity_dict[my_cards[0][0][0]+my_cards[0][1][0]+suited_str]=equity

    equity_dict=OrderedDict(sorted(equity_dict.items(), key=itemgetter(1)))
    with open('preflop_equity.json', 'w') as fp:
        json.dump(equity_dict, fp)

