import numpy as np
import matplotlib.pyplot as plt


class ExpectedValue(object):
    def CalculateEVCall(self, E, P, S):
        EV = (E * (P - S + S)) - ((1 - E) * S)
        return EV

    def calcEVCallLimit(self, E, P):
        MaxCall = 100
        CallValues = np.arange(0.01, MaxCall, 0.01)
        EV = [self.CalculateEVCall(E, P, S) for S in CallValues]
        # plt.plot(CallValues,EV)
        # plt.show()
        BestEquity = min(EV, key=lambda x: abs(x - 0.1))
        ind = EV.index(BestEquity)
        self.zeroEvCallSize = np.round(EV.index(BestEquity), 2)
        return CallValues[self.zeroEvCallSize]


E = .53
P = 2
EV = ExpectedValue()
ev = EV.calcEVCallLimit(E, P)
print(ev)
