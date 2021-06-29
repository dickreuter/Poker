from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas)
from matplotlib.figure import Figure
from poker.decisionmaker.curvefitting import *
from weakref import proxy
import numpy as np


class HistogramEquityWinLoss(FigureCanvas):
    def __init__(self, ui):
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        self.axes = self.fig.add_subplot(111)  # create an axis
        super(HistogramEquityWinLoss, self).__init__(self.fig)
        # self.drawfigure(template,game_stage,decision)
        self.ui.horizontalLayout_3.insertWidget(1, self)

    def drawfigure(self, p_name, game_stage, decision, l):
        data = l.get_histrogram_data('Template', p_name, game_stage, decision)
        wins = data[0]
        losses = data[1]
        bins = np.linspace(0, 1, 20)

        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis

        self.axes.set_title('Histogram')
        self.axes.set_xlabel('Equity')
        self.axes.set_ylabel('Number of hands')

        self.axes.hist(wins, bins, alpha=0.5, label='wins', color='g')
        self.axes.hist(losses, bins, alpha=0.5, label='losses', color='r')
        self.axes.legend(loc='upper right')
        self.draw()
