import matplotlib
matplotlib.use('Qt4Agg')
#matplotlib.rcParams['backend.qt4'] = 'PySide'
from matplotlib.backends.backend_qt4agg import (
    FigureCanvasQTAgg as FigureCanvas)
from matplotlib.figure import Figure
from PyQt4 import QtGui
import random

from weakref import proxy
from gui.gui_qt_ui import Ui_Pokerbot
import threading

import math
from decisionmaker.genetic_algorithm1 import *
from decisionmaker.curvefitting import *


class Plotter1(FigureCanvas):
    def __init__(self, ui):
        self.ui = proxy(ui)
        self.fig = Figure()
        super(Plotter1,self).__init__(self.fig)
        self.drawfigure()
        self.ui.vLayout.insertWidget(1, self)

    def drawfigure(self):
        data = [random.random() for i in range(10)]
        self.axes = self.fig.add_subplot(111) # create an axis
        self.axes.hold(False) # discards the old graph
        self.axes.plot(data, '*-') # plot data
        self.draw()

class Plotter2(FigureCanvas):
    def __init__(self, ui):
        self.ui = proxy(ui)
        self.fig = Figure()
        super(Plotter2,self).__init__(self.fig)
        self.drawfigure()
        self.ui.vLayout2.insertWidget(1, self)

    def drawfigure(self):
        data = [random.random() for i in range(10)]
        self.axes = self.fig.add_subplot(111) # create an axis
        self.axes.hold(False) # discards the old graph
        self.axes.plot(data, '*-') # plot data
        self.draw()

class Pieplot(FigureCanvas):
    def __init__(self, ui):
        self.ui = proxy(ui)
        self.fig = Figure()
        super(Pieplot,self).__init__(self.fig)
        self.drawfigure()
        self.ui.vLayout4.insertWidget(1, self)


    def drawfigure(self):
        self.axes = self.fig.add_subplot(111) # create an axis
        self.axes.hold(False) # discards the old graph
        self.axes.pie([22, 100 - 22], autopct='%1.1f%%')
        D = {u'HighCard': 0}
        self.pieChartCircles = self.axes.pie([float(v) for v in D.values()], labels=[k for k in D.keys()],
                                              autopct=None)

        self.axes.set_title('Winning probabilities')
        self.draw()

class CurvePlot(FigureCanvas):
    def __init__(self, ui):
        self.ui = proxy(ui)
        self.fig = Figure()
        super(CurvePlot, self).__init__(self.fig)
        self.drawfigure()
        self.ui.vLayout3.insertWidget(1, self)

    def drawfigure(self):
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.hold(False)  # discards the old graph

        self.x2 = []
        self.y2 = []
        self.y3 = []
        self.x2 = np.arange(0, 1, 0.01)
        for each in self.x2:
            self.y2.append(0.5)
            self.y3.append(0.7)

        self.axes.plot(self.x2, self.y2, 'b-')  # Returns a tuple of line objects, thus the comma
        self.axes.plot(self.x2, self.y3, 'r-')  # Returns a tuple of line objects, thus the comma
        self.axes.axis((0, 1, 0, 1))
        self.axes.set_title('Maximum bet')
        self.axes.set_xlabel('Equity')
        self.axes.set_ylabel('Max $')
        self.draw()


class Updater(FigureCanvas):
    def __init__(self, ui):
        ui.equity.display("0.03")
        ui.progress_bar.setValue(0)
        ui.status.setText("None")
        ui.last_decision.setText("None")





# class GUI():
#     def __init__(self, p, ui):
    #     self.a = self.f.add_subplot(111)
    #
    #     self.line1, = self.a.plot(self.x, self.y, 'r-')  # Returns a tuple of line objects, thus the comma
    #     self.a.axis((0, 100, 0, 8))
    #     self.a.set_title('My Funds')
    #     self.a.set_xlabel('Time')
    #     self.a.set_ylabel('$')
    #     canvas = FigureCanvasTkAgg(self.f, master=self.root)
    #     canvas.show()
    #     canvas.get_tk_widget().grid(row=7, column=1)
    #     canvas._tkcanvas.grid(row=7, column=1, ipadx=5, ipady=5)
    #
    #     self.x2 = [];
    #     self.y2 = [];
    #     self.y3 = [];
    #     self.x2 = np.arange(0, 1, 0.01)
    #     for each in self.x2:
    #         self.y2.append(0.5)
    #         self.y3.append(0.7)
    #     self.g = Figure(figsize=(5, 4), dpi=60);
    #     self.g.clf()
    #     self.b = self.g.add_subplot(111)
    #
    #     self.line2, = self.b.plot(self.x2, self.y2, 'b-')  # Returns a tuple of line objects, thus the comma
    #     self.line3, = self.b.plot(self.x2, self.y3, 'r-')  # Returns a tuple of line objects, thus the comma
    #     self.b.axis((0, 1, 0, 1))
    #     self.b.set_title('Maximum bet')
    #     self.b.set_xlabel('Equity')
    #     self.b.set_ylabel('Max $')
    #     canvas = FigureCanvasTkAgg(self.g, master=self.root)
    #     canvas.show()
    #     # canvas.get_tk_widget().grid(row=6, column=1)
    #     canvas._tkcanvas.grid(row=8, column=1, padx=5, pady=5, columnspan=1)
    #
    #     self.pie = Figure(figsize=(5, 4), dpi=60);
    #     self.pie.clf()
    #     self.piePlot = self.pie.add_subplot(111)
    #     D = {u'': 50}
    #     # self.piePlotting= self.piePlot.pie([float(v) for v in Simulation.winnerCardTypeList.values()], labels=[k for k in Simulation.winnerCardTypeList.keys()],autopct=None)
    #     self.pieChartCircles = self.piePlot.pie([float(v) for v in D.values()], labels=[k for k in D.keys()],
    #                                             autopct=None)
    #     self.piePlot.set_title('Chance of winning')
    #     canvas = FigureCanvasTkAgg(self.pie, master=self.root)
    #     canvas.show()
    #     # canvas.get_tk_widget().grid(row=6, column=1)
    #     canvas._tkcanvas.grid(row=8, column=2, padx=5, pady=5, columnspan=1)
    #
    #     self.h = Figure(figsize=(5, 4), dpi=60);
    #     self.c = self.h.add_subplot(111)
    #     L = Logging('log')
    #     data = L.get_stacked_bar_data('Template', p.current_strategy.text, 'stackedBar')
    #     N = 11
    #     Bluff = data[0]
    #     BP = data[1]
    #     BHP = data[2]
    #     Bet = data[3]
    #     Call = data[4]
    #     Check = data[5]
    #     Fold = data[6]
    #     ind = np.arange(N)  # the x locations for the groups
    #     width = 1  # the width of the bars: can also be len(x) sequence
    #
    #     self.p0 = self.c.bar(ind, Bluff, width, color='y')
    #     self.p1 = self.c.bar(ind, BP, width, color='k', bottom=Bluff)
    #     self.p2 = self.c.bar(ind, BHP, width, color='b', bottom=[sum(x) for x in zip(Bluff, BP)])
    #     self.p3 = self.c.bar(ind, Bet, width, color='c', bottom=[sum(x) for x in zip(Bluff, BP, BHP)])
    #     self.p4 = self.c.bar(ind, Call, width, color='g', bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet)])
    #     self.p5 = self.c.bar(ind, Check, width, color='w', bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet, Call)])
    #     self.p6 = self.c.bar(ind, Fold, width, color='r',
    #                          bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet, Call, Check)])
    #
    #     self.c.set_ylabel('Profitability')
    #     self.c.set_title('FinalFundsChange ABS')
    #     self.c.set_xlabel(['PF Win', 'Loss', '', 'F Win', 'Loss', '', 'T Win', 'Loss', '', 'R Win', 'Loss'])
    #     # plt.yticks(np.arange(0,10,0.5))
    #     # self.c.tight_layout()
    #     self.c.legend((self.p0[0], self.p1[0], self.p2[0], self.p3[0], self.p4[0], self.p5[0], self.p6[0]),
    #                   ('Bluff', 'BetPot', 'BetHfPot', 'Bet/Bet+', 'Call', 'Check', 'Fold'), labelspacing=0.03,
    #                   prop={'size': 12})
    #
    #     i = 0
    #     maxh = 0
    #     for rect0, rect1, rect2, rect3, rect4, rect5, rect6 in zip(self.p0.patches, self.p1.patches, self.p2.patches,
    #                                                                self.p3.patches, self.p4.patches, self.p5.patches,
    #                                                                self.p6.patches):
    #         g = list(zip(data[0], data[1], data[2], data[3], data[4], data[5], data[6]))
    #         h = g[i]
    #         i += 1
    #         rect0.set_height(h[0])
    #         rect1.set_y(h[0])
    #         rect1.set_height(h[1])
    #         rect2.set_y(h[0] + h[1])
    #         rect2.set_height(h[2])
    #         rect3.set_y(h[0] + h[1] + h[2])
    #         rect3.set_height(h[3])
    #         rect4.set_y(h[0] + h[1] + h[2] + h[3])
    #         rect4.set_height(h[4])
    #         rect5.set_y(h[0] + h[1] + h[2] + h[3] + h[4])
    #         rect5.set_height(h[5])
    #         rect6.set_y(h[0] + h[1] + h[2] + h[3] + h[4] + h[5])
    #         rect6.set_height(h[6])
    #         maxh = max(h[0] + h[1] + h[2] + h[3] + h[4] + h[5] + h[6], maxh)
    #
    #     self.c.set_ylim((0, maxh))
    #     canvas = FigureCanvasTkAgg(self.h, master=self.root)
    #     canvas.show()
    #     # canvas.get_tk_widget().grid(row=6, column=1)
    #     canvas._tkcanvas.grid(row=7, column=2, padx=5, pady=5, columnspan=1)
    #
    #     self.progress = ttk.Progressbar(self.root, orient="horizontal", length=300, mode="determinate")
    #     self.progress.grid(row=10, column=1, columnspan=2)
    #
    # def on_closing(self):
    #     # if tk.messagebox.askokcancel("Quit", "Do you want to quit?"):
    #     self.active = False
    #     self.root.destroy()
    #
    # def updatePlots(self, histEquity, histMinCall, histMinBet, equity, minCall, minBet, color1, color2):
    #     try:
    #         self.dots1.remove()
    #         self.dots2.remove()
    #         self.dots1h.remove()
    #         self.dots2h.remove()
    #     except:
    #         pass
    #
    #     self.dots1h, = self.b.plot(histEquity, histMinCall, 'wo')
    #     self.dots2h, = self.b.plot(histEquity, histMinBet, 'wo')
    #     self.dots1, = self.b.plot(equity, minCall, color1)
    #     self.dots2, = self.b.plot(equity, minBet, color2)
    #
    #     self.g.canvas.draw()
    #
    # def updateLines(self, power1, power2, minEquityCall, minEquityBet, smallBlind, bigBlind, maxValue, maxEquityCall,
    #                 maxEquityBet):
    #     x2 = np.linspace(0, 1, 100)
    #     self.statusbar.set("Updating GUI")
    #
    #     d1 = Curvefitting(x2, smallBlind, bigBlind * 2, maxValue, minEquityCall, maxEquityCall, power1)
    #     d2 = Curvefitting(x2, smallBlind, bigBlind, maxValue, minEquityBet, maxEquityBet, power2)
    #
    #     self.y2.extend(d1.y)
    #     self.y3.extend(d2.y)
    #     self.line2.set_ydata(self.y2[-100:])
    #     self.line3.set_ydata(self.y3[-100:])
    #     self.b.set_ylim(0, max(1, maxValue))
    #     self.g.canvas.draw()

#
# class Calcuiation(object):
#     def __init__(self):
#         self.i = 0
#
#     def calculation(self):
#         while True:
#             # complex calculations that last 30 minutes in total
#             try:
#                 self.i += gui.s1.get()
#             except:
#                 self.i += 1
#             time.sleep(.1)
#             gui.l.append(self.i)
#             # print gui.l
#
#             if gui.active == True:
#                 max = 1000
#                 gui.var1.set("Value1: " + str(self.i))
#                 gui.var2.set("Value2: " + str(self.i + 100))
#                 gui.var3.set("Value3: " + str(self.i + 100))
#                 gui.var4.set("Value4: " + str(self.i + 100))
#                 gui.var5.set("Value5: " + str(self.i + 100))
#                 gui.var6.set("Value6: " + str(self.i + 100))
#                 gui.statusbar.set("This is the statusbar:")
#                 gui.progress["value"] = int(round(self.i * 100 / max))
#                 # self.update()  # no need, will be automatic as mainloop() runs
#                 # self.after(1, self.calculation) not necessary anymore as everything is in a main loop#
#
#
#                 gui.y.append(self.i * 10)
#                 gui.line1.set_ydata(gui.y[-100:])
#
#                 gui.f.canvas.draw()
#
#                 x2 = np.arange(0, 1, 0.01)
#                 for item in x2:
#                     gui.y2.append(item ** 2)
#                     gui.y3.append(item ** 3)
#                 gui.line2.set_ydata(gui.y2[-100:])
#                 gui.line3.set_ydata(gui.y3[-100:])
#                 gui.g.canvas.draw()
#
#
#                 gui.pie.clf()
#                 gui.piePlot = gui.pie.add_subplot(111)
#                 gui.piePlot.pie([22, 100 - 22], autopct='%1.1f%%')
#                 D = {u'HighCard': 0}
#                 gui.pieChartCircles = gui.piePlot.pie([float(v) for v in D.values()], labels=[k for k in D.keys()],
#                                                       autopct=None)
#                 gui.piePlot.set_title('Winning probabilities')
#                 # gui.piePlot.suptitle(subtitle_string, y=1.05, fontsize=10)
#                 gui.pie.canvas.draw_idle()
#                 # gui.pie.canvas.draw()
#
#                 gui.a.set_ylim(0, 7)
#                 gui.f.canvas.draw()


if __name__ == "__main__":
    import sys
    app = QtGui.QApplication(sys.argv)
    MainWindow = QtGui.QWidget()
    ui = Ui_Pokerbot()
    ui.setupUi(MainWindow)

    # plotter logic and binding needs to be added here
    plotter1 = Plotter1(ui)
    ui.button_config.clicked.connect(plotter1.drawfigure)
    plotter2 = Plotter2(ui)
    plotter3 = CurvePlot(ui)
    plotter4 = Pieplot(ui)

    p = XMLHandler('../strategies.xml')
    p.read_XML()
    #gui = GUI(p,ui)
    # calc = Calcuiation()
    # t1 = threading.Thread(target=calc.calculation, args=[])
    # t1.start()
    Updater(ui)

    MainWindow.show()
    sys.exit(app.exec_())