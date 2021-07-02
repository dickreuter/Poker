from weakref import proxy

from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas)
from matplotlib.figure import Figure

from poker.tools.game_logger import GameLogger


class FundsChangePlot(FigureCanvas):
    def __init__(self, ui_analyser):
        self.ui_analyser = proxy(ui_analyser)
        self.fig = Figure(dpi=50)
        self.axes = self.fig.add_subplot(111)  # create an axis
        super(FundsChangePlot, self).__init__(self.fig)
        self.ui_analyser.vLayout_fundschange.insertWidget(1, self)

    def drawfigure(self, my_computer_only):
        LogFilename = 'log'
        L = GameLogger(LogFilename)
        p_name = str(self.ui_analyser.combobox_strategy.currentText())
        data = L.get_fundschange_chart(p_name, my_computer_only)
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.clear()  # discards the old graph
        self.axes.set_title('My Funds')
        self.axes.set_xlabel('Time')
        self.axes.set_ylabel('$')
        self.axes.plot(data, '-')  # plot data
        self.draw()
