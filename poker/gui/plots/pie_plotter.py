from weakref import proxy

from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas)
from matplotlib.figure import Figure


class PiePlotter(FigureCanvas):
    def __init__(self, ui, winnerCardTypeList):
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        self.axes = self.fig.add_subplot(111)  # create an axis
        super(PiePlotter, self).__init__(self.fig)
        # self.drawfigure(winnerCardTypeList)
        self.ui.vLayout4.insertWidget(1, self)

    def drawfigure(self, winnerCardTypeList):
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.clear()
        self.axes.pie([float(v) for v in winnerCardTypeList.values()],
                      labels=[k for k in winnerCardTypeList.keys()], autopct=None)
        self.axes.set_title('Winning+draw probabilities')
        self.draw()
