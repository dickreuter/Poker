from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas)
from matplotlib.figure import Figure
from poker.decisionmaker.curvefitting import *
from weakref import proxy
import numpy as np


class ScatterPlot(FigureCanvas):
    def __init__(self, ui):
        self.ui = proxy(ui)
        self.fig = Figure()
        self.axes = self.fig.add_subplot(111)  # create an axis
        super(ScatterPlot, self).__init__(self.fig)
        self.ui.horizontalLayout_4.insertWidget(1, self)

    # pylint: disable=too-many-arguments
    def drawfigure(self, p_name, game_stage, decision, l, smallBlind, bigBlind, maxValue, minEquityBet, max_X,
                   maxEquityBet,
                   power):
        wins, losses = l.get_scatterplot_data('Template', p_name, game_stage, decision)
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.set_title('Wins and Losses')
        self.axes.set_xlabel('Equity')
        self.axes.set_ylabel('Minimum required call')

        try:
            self.axes.set_ylim(0, max(np.concatenate([losses['minCall'].astype(float).values,
                                                      wins['minCall'].astype(float).values])))
        except:
            self.axes.set_ylim(0, 1)
        self.axes.set_xlim(0, 1)

        # self.axes.set_xlim(.5, .8)
        # self.axes.set_ylim(0, .2)

        area = np.pi * (50 * wins['FinalFundsChange'])  # 0 to 15 point radiuses
        green_dots = self.axes.scatter(x=wins['equity'].astype(float).tolist(),
                                       y=wins['minCall'].astype(float), s=area, c='green', alpha=0.2)

        area = np.pi * (50 * abs(losses['FinalFundsChange']))
        red_dots = self.axes.scatter(x=losses['equity'].astype(float).tolist(),
                                     y=losses['minCall'].astype(float), s=area, c='red', alpha=0.2)

        self.axes.legend((green_dots, red_dots),
                         ('Wins', 'Losses'), loc=2)

        x2 = np.linspace(0, 1, 100)
        d2 = Curvefitting(x2, 0, 0, maxValue, minEquityBet, maxEquityBet, max_X, power)
        self.line3, = self.axes.plot(np.arange(0, 1, 0.01), d2.y[-100:],
                                     'r-')  # Returns a tuple of line objects, thus the comma

        self.axes.grid()
        self.draw()
