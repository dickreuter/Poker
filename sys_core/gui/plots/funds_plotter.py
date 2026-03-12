from weakref import proxy

import numpy as np
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas)
from matplotlib.figure import Figure


class FundsPlotter(FigureCanvas):
    def __init__(self, ui, p):
        self.p = p
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        self.axes = self.fig.add_subplot(111)  # create an axis
        super(FundsPlotter, self).__init__(self.fig)
        # self.drawfigure()
        self.ui.vLayout.insertWidget(1, self)

    def drawfigure(self, L):
        Strategy = str(self.p.current_strategy)
        data = L.get_fundschange_chart(Strategy)
        data = np.cumsum(data)
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.clear()  # discards the old graph
        self.axes.set_title('My Funds')
        self.axes.set_xlabel('Time')
        self.axes.set_ylabel('$')
        self.axes.plot(data, '-')  # plot data
        self.draw()
