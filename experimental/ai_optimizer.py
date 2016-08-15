import numpy as np
import pandas as pd

from decisionmaker.curvefitting import *


class AI_optimizer(object):
    def getReturn(self, mx, df, eq):
        total = df[
            (0 <= df['minCall']) & (df['minBet'] <= mx) & (df['gameStage'] == 'PreFlop') & (df['equity'] == eq) & (
                df['decision'] != 'Fold')][['FinalFundsChange', 'equity', 'minBet']].FinalFundsChange.sum()
        return total

    def func(self, maxAmount, df, eq):
        i = list(enumerate(maxAmount))
        r = []
        for counter in i:
            mx = counter[1]
            total = self.getReturn(mx, df, eq)
            # df.plot(kind='scatter', x='equity', y='minCall')
            r.append(total)
            # print (r)
        return r

    def __init__(self):
        df = pd.read_csv(r'log.csv')
        initialFunds = 2.0

        oPoints = []
        equityList = np.arange(.3, .85, 0.01)
        # equityList=[0.99]
        for equity in equityList:
            n = np.arange(0.0, initialFunds, 0.01)
            r = self.func(n, df, equity)
            optMax = n[r.index(max(r))]
            fundchange = self.getReturn(optMax, df, equity)
            print(equity, optMax, fundchange)
            oPoints.append((equity, optMax))

        # plt.show()

        smallBlind = 0.02
        bigBlind = 0.04
        maxValue = 2

        minEquity = 0.45
        pw = 2
        #
        # minCall=
        # minEquity=
        # d=curveFitting(minCall,smallBlind,bigBlind,maxValue,minEquity,pw)
        # print (d.y)
        #
        #
        #     if y>equity:
        #         l.extend(ffc)


AI = AI_optimizer()
