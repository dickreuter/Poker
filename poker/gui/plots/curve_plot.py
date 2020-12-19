from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas)
from matplotlib.figure import Figure
from poker.decisionmaker.curvefitting import *
from weakref import proxy
import numpy as np

# pylint: disable=access-member-before-definition
class CurvePlot(FigureCanvas):
    def __init__(self, ui, p, layout='vLayout3'):
        self.p = p
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        self.axes = self.fig.add_subplot(111)  # create an axis
        super(CurvePlot, self).__init__(self.fig)
        self.drawfigure()
        layout = getattr(self.ui, layout)
        func = getattr(layout, 'insertWidget')
        func(1, self)

    def drawfigure(self):
        self.axes = self.fig.add_subplot(111)  # create an axis

        self.axes.axis((0, 1, 0, 1))
        self.axes.set_title('Maximum bet')
        self.axes.set_xlabel('Equity')
        self.axes.set_ylabel('Max $ or pot multiple')
        self.draw()

    def update_plots(self, histEquity, histMinCall, histMinBet, equity, minCall, minBet, color1, color2):
        try:
            self.dots1.remove()
            self.dots2.remove()
            self.dots1h.remove()
            self.dots2h.remove()
        except:
            pass

        self.dots1h, = self.axes.plot(histEquity, histMinCall, 'wo')
        self.dots2h, = self.axes.plot(histEquity, histMinBet, 'wo')
        self.dots1, = self.axes.plot(equity, minCall, color1)
        self.dots2, = self.axes.plot(equity, minBet, color2)

        self.draw()

    # pylint: disable=too-many-arguments
    def update_lines(self, power1, power2, minEquityCall, minEquityBet, smallBlind, bigBlind, maxValue, maxvalue_bet,
                     maxEquityCall,
                     max_X,
                     maxEquityBet):
        x2 = np.linspace(0, 1, 100)

        minimum_curve_value = 0 if self.p.selected_strategy['use_pot_multiples'] else smallBlind
        minimum_curve_value2 = 0 if self.p.selected_strategy['use_pot_multiples'] else bigBlind
        d1 = Curvefitting(x2, minimum_curve_value, minimum_curve_value2 * 2, maxValue, minEquityCall, maxEquityCall,
                          max_X, power1)
        d2 = Curvefitting(x2, minimum_curve_value, minimum_curve_value2, maxvalue_bet, minEquityBet, maxEquityBet,
                          max_X, power2)
        x = np.arange(0, 1, 0.01)
        try:
            self.line1.remove()
            self.line2.remove()
        except:
            pass

        self.line1, = self.axes.plot(x, d1.y, 'b-')  # Returns a tuple of line objects, thus the comma
        self.line2, = self.axes.plot(x, d2.y, 'r-')  # Returns a tuple of line objects, thus the comma
        self.axes.legend((self.line1, self.line2), ('Maximum call limit', 'Maximum bet limit'), loc=2)

        self.axes.set_ylim(0, max(1, maxValue, maxvalue_bet))

        stage = 'Flop'
        xmin = 0.2  # float(self.p.selected_strategy[stage+'BluffMinEquity'])
        xmax = 0.3  # float(self.p.selected_strategy[stage+'BluffMaxEquity'])
        # self.axes.axvline(x=xmin, ymin=0, ymax=1, linewidth=1, color='g')
        # self.axes.axvline(x=xmax, ymin=0, ymax=1, linewidth=1, color='g')

        self.draw()
