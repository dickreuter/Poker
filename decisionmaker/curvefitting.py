import numpy as np
from lmfit import minimize, Parameters, Parameter, report_fit

'''
Helps to fit curves when two points and a curvature are given.
'''


class Curvefitting(object):
    def __init__(self, x, smallBlind, bigBlind, maxValue, minEquity, maxEquity, pw, pl=False):
        def fcn2min(params, x, data):
            pw = params['pw'].value
            adj1 = params['adj1'].value
            adj2 = params['adj2'].value
            model = adj1 * np.power(x + adj2, pw)
            return model - data

        def finalFunction(x, adj1, adj2, pw, start, end, smallBlind):
            y = adj1 * np.power(x + adj2, pw)
            y[x < start] = smallBlind
            y[x > maxEquity] = 0
            return y

        def plot():
            import pylab
            pylab.plot(xf, yf, 'ko')
            pylab.plot(x, y, 'r')
            pylab.show()

        xf = [minEquity, 1]
        yf = [bigBlind, maxValue]

        # create a set of Parameters
        params = Parameters()
        params.add('pw', value=pw, vary=False)
        params.add('adj1', value=1)
        params.add('adj2', value=1)

        # do fit, here with leastsq model
        result = minimize(fcn2min, params, args=(xf, yf))

        adj1 = result.params['adj1']
        adj2 = result.params['adj2']

        # plot results
        y = finalFunction(x, adj1, adj2, pw, xf[0], maxEquity, smallBlind)
        if pl == True:
            plot()
        self.y = y


if __name__ == '__main__':
    smallBlind = 0.02
    bigBlind = 0.04
    maxValue = 2
    minEquity = 0.75
    maxEquity = 0.9
    pw = 16
    x = np.linspace(0, 1, 100)
    x - np.array([0.3])
    # x=[0.2,0.5,0.8]
    d = Curvefitting(x, smallBlind, bigBlind, maxValue, minEquity, maxEquity, pw, pl=True)
    print(d.y)
