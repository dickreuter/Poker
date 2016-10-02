from lmfit import minimize, Parameters, Parameter, report_fit
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from copy import copy
'''
Helps to fit curves when two points and a curvature are given.
'''

class Curvefitting_scipy():
    def __init__(self, xf, smallBlind, bigBlind, maxValue, minEquity, maxEquity, pw, pl=False):
        x = [minEquity, 1]
        y = [bigBlind, maxValue]
        self.pw=pw
        popt, pcov = curve_fit(self.func, x, y,maxfev=10000)

        yf=self.func(xf, *popt)
        yf2=copy(yf)
        yf2=[x + smallBlind for x in yf2]
        yf2=np.array(yf)
        #print (yf)
        yf2[yf2 > maxEquity] = 0
        yf2[yf2 < minEquity] = smallBlind
        self.x=xf
        self.y=yf2
        if pl:
            plt.figure()
            plt.plot(xf, yf, 'r-', label="Fitted Curve")
            plt.show()

    def func(self,x, adj1, adj2):
        return ((x + adj1) ** self.pw) * adj2

class Curvefitting(object):
    def __init__(self, x, smallBlind, bigBlind, maxValue, minEquity, maxEquity, max_X, pw, pl=False):
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

        xf = [minEquity, max_X]
        yf = [bigBlind, maxValue]
        self.x = x

        # create a set of Parameters
        params = Parameters()
        params.add('pw', value=pw, vary=False)
        params.add('adj1', value=1)
        params.add('adj2', value=1)

        # do fit, here with leastsq model
        result = minimize(fcn2min, params, args=(xf, yf), maxfev=3000)

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
    max_X=1

    xf = np.linspace(0, 1, 50)
    d=Curvefitting(xf, smallBlind, bigBlind, maxValue, minEquity, maxEquity, max_X, pw, pl=False)



