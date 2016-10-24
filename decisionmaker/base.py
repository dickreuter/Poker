import numpy as np


class DecisionBase(object):
    # Contains routines that make the actual decisions to play: the main function is make_decision
    def calc_bet_EV(self, E, P, S, c, t):
        n = 1 if t.isHeadsUp == True else 2
        f = max(0, 1 - min(S / P, 1)) * c * n
        EV = E * (P + f) - (1 - E) * S
        return EV

    def calc_call_EV(self, E, P, S):
        EV = (E * (P - S + S)) - ((1 - E) * S)
        return EV

    def calc_EV_call_limit(self, E, P):
        MaxCall = 10
        CallValues = np.arange(0.01, MaxCall, 0.01)
        EV = [self.calc_call_EV(E, P, S) for S in CallValues]
        BestEquity = min(EV, key=lambda x: abs(x - 0))
        ind = EV.index(BestEquity)
        self.zeroEvCallSize = np.round(EV.index(BestEquity), 2)
        return CallValues[self.zeroEvCallSize]

    def calc_bet_limit(self, E, P, c, t, logger):
        Step = 0.01
        MaxCall = 1000
        rng = int(np.round((1 * Step + MaxCall) / Step))
        EV =[self.calc_bet_EV(E, P, S * Step, c, t) for S in range(rng)]
        X = range(rng)

        # plt.plot(X[1:200],EV[1:200])
        # plt.show()

        BestEquity = max(EV)
        logger.debug("Experimental maximum EV for betting: " + str(BestEquity))
        ind = EV.index(BestEquity)
        self.maxEvBetSize = np.round(EV.index(BestEquity) * Step, 2)
        return self.maxEvBetSize

    def calc_max_invest(self, equity, pw, bigBlindMultiplier):
        return np.round((equity ** pw) * bigBlindMultiplier, 2)


class Collusion(object):
    # If more than one pokerbot plays on the same table_analysers, the players can collude. This is not yet fully implemented
    # The gained advantage is expected to be limited unless a corresponding strategy is trained independently
    def __init__(self):
        pass
        # connect to server to download other player cards
        # add cards
        # for cardLIst in ColludingPlayers
        # t.PlayerCardList.append(cardList)
