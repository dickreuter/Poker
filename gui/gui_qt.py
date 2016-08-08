import matplotlib
matplotlib.use('Qt4Agg')
#matplotlib.rcParams['backend.qt4'] = 'PySide'
from matplotlib.backends.backend_qt4agg import (
    FigureCanvasQTAgg as FigureCanvas)
from matplotlib.figure import Figure
from PyQt4 import QtGui
import random

from weakref import proxy
from gui.gui_qt_ui import Ui_MainWindow


class Plotter1(FigureCanvas):
    def __init__(self, parent):
        self.parent = proxy(parent)
        self.fig = Figure()
        super(Plotter1,self).__init__(self.fig)
        self.drawfigure()
        self.parent.vLayout.insertWidget(1, self)

    def drawfigure(self):
        data = [random.random() for i in range(10)]
        self.axes = self.fig.add_subplot(111) # create an axis
        self.axes.hold(False) # discards the old graph
        self.axes.plot(data, '*-') # plot data
        self.draw()

class Plotter2(FigureCanvas):
    def __init__(self, parent):
        self.parent = proxy(parent)
        self.fig = Figure()
        super(Plotter2,self).__init__(self.fig)
        self.drawfigure()
        self.parent.vLayout2.insertWidget(1, self)

    def drawfigure(self):
        data = [random.random() for i in range(10)]
        self.axes = self.fig.add_subplot(111) # create an axis
        self.axes.hold(False) # discards the old graph
        self.axes.plot(data, '*-') # plot data
        self.draw()

if __name__ == "__main__":
    import sys
    app = QtGui.QApplication(sys.argv)
    Form = QtGui.QWidget()
    ui = Ui_MainWindow()
    ui.setupUi(Form)

    # plotter logic and binding needs to be added here
    plotter1 = Plotter1(ui)
    ui.pushButton.clicked.connect(plotter1.drawfigure)

    plotter2 = Plotter2(ui)


    Form.show()
    sys.exit(app.exec_())