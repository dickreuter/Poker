from PyQt5.QtCore import *
import matplotlib
from .GUI_QT_ui_analyser import *
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas)
from matplotlib.figure import Figure
from weakref import proxy
from gui.gui_qt_ui import Ui_Pokerbot
from gui.gui_qt_ui_genetic_algorithm import *
from decisionmaker.genetic_algorithm1 import *
from decisionmaker.curvefitting import *

class PandasModel(QtCore.QAbstractTableModel):
    """
    Class to populate a table view with a pandas dataframe
    """
    def __init__(self, data, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self._data = data

    def rowCount(self, parent=None):
        return len(self._data.values)

    def columnCount(self, parent=None):
        return self._data.columns.size

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if index.isValid():
            if role == QtCore.Qt.DisplayRole:
                return str(self._data.values[index.row()][index.column()])
        return None

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._data.columns[col]
        return None

class UIActionAndSignals(QObject):
    signal_progressbar_increase = QtCore.pyqtSignal(int)
    signal_progressbar_reset = QtCore.pyqtSignal()

    signal_status = QtCore.pyqtSignal(str)
    signal_decision = QtCore.pyqtSignal(str)

    signal_bar_chart_update=QtCore.pyqtSignal(object)
    signal_funds_chart_update=QtCore.pyqtSignal(object)
    signal_pie_chart_update=QtCore.pyqtSignal(dict)
    signal_curve_chart_update1=QtCore.pyqtSignal(float,float,float,float,float,float,str,str)
    signal_curve_chart_update2 = QtCore.pyqtSignal(float, float, float, float, float, float, float, float,float)
    signal_lcd_number_update = QtCore.pyqtSignal(str,float)

    def __init__(self,ui,p,l,logger):
        QObject.__init__(self)
        self.ui=ui
        self.progressbar_value=0
        self.logger=logger

        # Main Window matplotlip widgets
        self.gui_funds = FundsPlotter(ui, p)
        self.gui_bar = BarPlotter(ui, p)
        self.gui_curve = CurvePlot(ui, p)
        self.gui_pie = PiePlotter(ui, winnerCardTypeList={'Highcard':22})

        # main window status update signal connections
        self.signal_progressbar_increase.connect(self.increase_progressbar)
        self.signal_progressbar_reset.connect(self.reset_progressbar)
        self.signal_status.connect(self.update_mainwindow_status)
        self.signal_decision.connect(self.update_mainwindow_decision)

        self.signal_lcd_number_update.connect(self.update_lcd_number)

        strategy=p.current_strategy
        self.signal_bar_chart_update.connect(lambda: self.gui_bar.drawfigure(l,strategy))

        self.signal_funds_chart_update.connect(lambda: self.gui_funds.drawfigure(l))
        self.signal_curve_chart_update1.connect(self.gui_curve.update_plots)
        self.signal_curve_chart_update2.connect(self.gui_curve.update_lines)
        self.signal_pie_chart_update.connect(self.gui_pie.drawfigure)

        # ui.button_options.clicked.connect()
        # ui.button_strategy_editor.clicked.connect()
        # ui.button_options.clicked.connect()
        ui.button_genetic_algorithm.clicked.connect(lambda: self.open_genetic_algorithm(p,l))

        ui.button_log_analyser.clicked.connect(lambda: self.open_strategy_analyser(p,l))

        ui.button_pause.clicked.connect(lambda: self.pause(ui,p))
        ui.button_resume.clicked.connect(lambda: self.resume(ui,p))

    def pause(self,ui,p):
        print ("Game paused")
        ui.button_resume.setEnabled(True)
        ui.button_pause.setEnabled(False)
        ui.button_genetic_algorithm.setEnabled(True)
        ui.button_log_analyser.setEnabled(True)
        p.pause=True

    def resume(self, ui,p):
        print("Game resumed")
        ui.button_resume.setEnabled(False)
        ui.button_pause.setEnabled(True)
        ui.button_genetic_algorithm.setEnabled(False)
        ui.button_log_analyser.setEnabled(False)
        p.pause=False

    def increase_progressbar(self, value):
        self.progressbar_value+=value
        if self.progressbar_value>100: self.progressbar_value=100
        self.ui.progress_bar.setValue(self.progressbar_value)

    def reset_progressbar(self):
        self.progressbar_value=0
        self.ui.progress_bar.setValue(0)

    def update_mainwindow_status(self, text):
        self.ui.status.setText(text)

    def update_mainwindow_decision(self, text):
        self.ui.last_decision.setText(text)

    def update_lcd_number(self,item,value):
        func=getattr(self.ui, item)
        func.display(value)

    def open_strategy_analyser(self,p,l):
        self.signal_progressbar_reset.emit()
        self.stragegy_analyser_form = QtWidgets.QWidget()
        self.ui_analyser = Ui_Form()
        self.ui_analyser.setupUi(self.stragegy_analyser_form)
        self.stragegy_analyser_form.show()

        self.gui_fundschange = FundsChangePlot(self.ui_analyser)
        self.gui_fundschange.drawfigure()

        self.ui_analyser.combobox_actiontype.addItems(['Fold','Check','Call','Bet','BetPlus','Bet half pot','Bet pot','Bet Bluff'])
        self.ui_analyser.combobox_gamestage.addItems(['PreFlop','Flop','Turn','River'])
        self.ui_analyser.combobox_strategy.addItems(l.get_played_strategy_list())

        self.gui_histogram = HistogramEquityWinLoss(self.ui_analyser)
        self.gui_scatterplot = ScatterPlot(self.ui_analyser)

        self.ui_analyser.combobox_gamestage.currentIndexChanged[str].connect(lambda: self.strategy_analyser_update_plots(l,p))
        self.ui_analyser.combobox_actiontype.currentIndexChanged[str].connect(lambda: self.strategy_analyser_update_plots(l,p))
        self.ui_analyser.combobox_strategy.currentIndexChanged[str].connect(lambda: self.update_strategy_analyser(l,p))

        self.gui_bar2 = BarPlotter2(self.ui_analyser,l)
        self.gui_bar2.drawfigure(l, self.ui_analyser.combobox_strategy.currentText())
        self.update_strategy_analyser(l,p)

    def open_genetic_algorithm(self, p, l):
        self.ui.button_genetic_algorithm.setEnabled(False)
        g=GeneticAlgorithm(False, self.logger, l)
        r=g.get_results()


        self.genetic_algorithm_dialog = QtWidgets.QDialog()
        self.genetic_algorithm_form = Ui_Dialog()
        self.genetic_algorithm_form.setupUi(self.genetic_algorithm_dialog)
        self.genetic_algorithm_dialog.show()

        self.genetic_algorithm_form.textBrowser.setText(str(r))
        self.genetic_algorithm_dialog.show()

        self.genetic_algorithm_form.buttonBox.accepted.connect(lambda: GeneticAlgorithm(True, self.logger, l))

    def update_strategy_analyser(self,l,p):
        number_of_games=int(l.get_game_count(self.ui_analyser.combobox_strategy.currentText()))
        total_return=l.get_strategy_return(self.ui_analyser.combobox_strategy.currentText(), 999999)
        small_blind=0.02

        self.ui_analyser.lcdNumber_2.display(number_of_games)
        self.ui_analyser.lcdNumber.display(total_return/number_of_games/small_blind*100)
        self.gui_bar2.drawfigure(l,self.ui_analyser.combobox_strategy.currentText())
        self.gui_fundschange.drawfigure()
        self.strategy_analyser_update_plots(l,p)
        self.strategy_analyser_update_table(l)

    def strategy_analyser_update_plots(self,l,p):
        p_name = str(self.ui_analyser.combobox_strategy.currentText())
        game_stage = str(self.ui_analyser.combobox_gamestage.currentText())
        decision = str(self.ui_analyser.combobox_actiontype.currentText())

        self.gui_histogram.drawfigure(p_name, game_stage, decision,l)

        if p_name=='.*': p.read_XML()
        else: p.read_strategy(p_name)

        call_or_bet='Bet' if decision[0]=='B' else 'Call'

        max_value=1
        min_equity=float(p.selected_strategy[game_stage+'Min'+call_or_bet+'Equity'])
        max_equity=float(p.selected_strategy['PreFlopMaxBetEquity']) if game_stage=='PreFlop' and call_or_bet=='Bet' else 1
        power=float(p.selected_strategy[game_stage+call_or_bet+'Power'])

        self.gui_scatterplot.drawfigure(p_name, game_stage, decision,l,
                                        float(p.selected_strategy['smallBlind']),
                                        float(p.selected_strategy['bigBlind']),
                                        max_value,
                                        min_equity,
                                        max_equity,
                                        power)

    def strategy_analyser_update_table(self, l):
        p_name = str(self.ui_analyser.combobox_strategy.currentText())
        df=l.get_worst_games(p_name)
        model = PandasModel(df)
        self.ui_analyser.tableView.setModel(model)

class FundsPlotter(FigureCanvas):
    def __init__(self, ui, p):
        self.p = p
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        super(FundsPlotter, self).__init__(self.fig)
        #self.drawfigure()
        self.ui.vLayout.insertWidget(1, self)

    def drawfigure(self,L):
        Strategy = str(self.p.current_strategy)
        data=L.get_fundschange_chart(Strategy)
        data=np.cumsum(data)
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.hold(False)  # discards the old graph
        self.axes.set_title('My Funds')
        self.axes.set_xlabel('Time')
        self.axes.set_ylabel('$')
        self.axes.plot(data, '-')  # plot data
        self.draw()

class BarPlotter(FigureCanvas):
    def __init__(self, ui, p):
        self.p=p
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        super(BarPlotter, self).__init__(self.fig)
        #self.drawfigure()
        self.ui.vLayout2.insertWidget(1, self)

    def drawfigure(self,l,strategy):
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.hold(True)  # discards the old graph

        data = l.get_stacked_bar_data('Template', strategy, 'stackedBar')

        N = 11
        Bluff = data[0]
        BP = data[1]
        BHP = data[2]
        Bet = data[3]
        Call = data[4]
        Check = data[5]
        Fold = data[6]
        ind = np.arange(N)  # the x locations for the groups
        width = 1  # the width of the bars: can also be len(x) sequence

        self.p0 = self.axes.bar(ind, Bluff, width, color='y')
        self.p1 = self.axes.bar(ind, BP, width, color='k', bottom=Bluff)
        self.p2 = self.axes.bar(ind, BHP, width, color='b', bottom=[sum(x) for x in zip(Bluff, BP)])
        self.p3 = self.axes.bar(ind, Bet, width, color='c', bottom=[sum(x) for x in zip(Bluff, BP, BHP)])
        self.p4 = self.axes.bar(ind, Call, width, color='g', bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet)])
        self.p5 = self.axes.bar(ind, Check, width, color='w', bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet, Call)])
        self.p6 = self.axes.bar(ind, Fold, width, color='r',
                                bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet, Call, Check)])

        self.axes.set_ylabel('Profitability')
        self.axes.set_title('FinalFundsChange ABS')
        self.axes.set_xlabel(['PF Win', 'Loss', '', 'F Win', 'Loss', '', 'T Win', 'Loss', '', 'R Win', 'Loss'])
        self.axes.legend((self.p0[0], self.p1[0], self.p2[0], self.p3[0], self.p4[0], self.p5[0], self.p6[0]),
                         ('Bluff', 'BetPot', 'BetHfPot', 'Bet/Bet+', 'Call', 'Check', 'Fold'), labelspacing=0.03,
                         prop={'size': 12})
        maxh = float(self.p.selected_strategy['bigBlind']) * 10
        i = 0
        for rect0, rect1, rect2, rect3, rect4, rect5, rect6 in zip(self.p0.patches, self.p1.patches,
                                                                   self.p2.patches,
                                                                   self.p3.patches, self.p4.patches,
                                                                   self.p5.patches, self.p6.patches):
            g = list(zip(data[0], data[1], data[2], data[3], data[4], data[5], data[6]))
            height = g[i]
            i += 1
            rect0.set_height(height[0])
            rect1.set_y(height[0])
            rect1.set_height(height[1])
            rect2.set_y(height[0] + height[1])
            rect2.set_height(height[2])
            rect3.set_y(height[0] + height[1] + height[2])
            rect3.set_height(height[3])
            rect4.set_y(height[0] + height[1] + height[2] + height[3])
            rect4.set_height(height[4])
            rect5.set_y(height[0] + height[1] + height[2] + height[3] + height[4])
            rect5.set_height(height[5])
            rect6.set_y(height[0] + height[1] + height[2] + height[3] + height[4] + height[5])
            rect6.set_height(height[6])
            maxh = max(height[0] + height[1] + height[2] + height[3] + height[4] + height[5] + height[6], maxh)

        self.axes.set_ylim((0, maxh))

        self.draw()

class BarPlotter2(FigureCanvas):
    def __init__(self, ui_analyser,l):
        self.ui_analyser = proxy(ui_analyser)
        self.fig = Figure(dpi=70)
        super(BarPlotter2, self).__init__(self.fig)
        self.drawfigure(l,self.ui_analyser.combobox_strategy.currentText())
        self.ui_analyser.vLayout_bar.insertWidget(1, self)

    def drawfigure(self,l,strategy):
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.hold(True)  # discards the old graph

        p_name = str(strategy)
        data = l.get_stacked_bar_data('Template', p_name, 'stackedBar')

        N = 11
        Bluff = data[0]
        BP = data[1]
        BHP = data[2]
        Bet = data[3]
        Call = data[4]
        Check = data[5]
        Fold = data[6]
        ind = np.arange(N)  # the x locations for the groups
        width = 1  # the width of the bars: can also be len(x) sequence

        self.p0 = self.axes.bar(ind, Bluff, width, color='y')
        self.p1 = self.axes.bar(ind, BP, width, color='k', bottom=Bluff)
        self.p2 = self.axes.bar(ind, BHP, width, color='b', bottom=[sum(x) for x in zip(Bluff, BP)])
        self.p3 = self.axes.bar(ind, Bet, width, color='c', bottom=[sum(x) for x in zip(Bluff, BP, BHP)])
        self.p4 = self.axes.bar(ind, Call, width, color='g', bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet)])
        self.p5 = self.axes.bar(ind, Check, width, color='w', bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet, Call)])
        self.p6 = self.axes.bar(ind, Fold, width, color='r',
                                bottom=[sum(x) for x in zip(Bluff, BP, BHP, Bet, Call, Check)])

        self.axes.set_ylabel('Profitability')
        self.axes.set_title('FinalFundsChange ABS')
        self.axes.set_xlabel(['PF Win', 'Loss', '', 'F Win', 'Loss', '', 'T Win', 'Loss', '', 'R Win', 'Loss'])
        # plt.yticks(np.arange(0,10,0.5))
        # self.c.tight_layout()
        self.axes.legend((self.p0[0], self.p1[0], self.p2[0], self.p3[0], self.p4[0], self.p5[0], self.p6[0]),
                         ('Bluff', 'BetPot', 'BetHfPot', 'Bet/Bet+', 'Call', 'Check', 'Fold'), labelspacing=0.03,
                         prop={'size': 12})
        i = 0
        maxh=0.02
        for rect0, rect1, rect2, rect3, rect4, rect5, rect6 in zip(self.p0.patches, self.p1.patches,
                                                                   self.p2.patches,
                                                                   self.p3.patches, self.p4.patches,
                                                                   self.p5.patches, self.p6.patches):
            g = list(zip(data[0], data[1], data[2], data[3], data[4], data[5], data[6]))
            height = g[i]
            i += 1
            rect0.set_height(height[0])
            rect1.set_y(height[0])
            rect1.set_height(height[1])
            rect2.set_y(height[0] + height[1])
            rect2.set_height(height[2])
            rect3.set_y(height[0] + height[1] + height[2])
            rect3.set_height(height[3])
            rect4.set_y(height[0] + height[1] + height[2] + height[3])
            rect4.set_height(height[4])
            rect5.set_y(height[0] + height[1] + height[2] + height[3] + height[4])
            rect5.set_height(height[5])
            rect6.set_y(height[0] + height[1] + height[2] + height[3] + height[4] + height[5])
            rect6.set_height(height[6])
            maxh = max(height[0] + height[1] + height[2] + height[3] + height[4] + height[5] + height[6], maxh)


        #self.axes.set_ylim((0, maxh))

        self.draw()

class HistogramEquityWinLoss(FigureCanvas):
    def __init__(self, ui):
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        super(HistogramEquityWinLoss, self).__init__(self.fig)
        #self.drawfigure(template,game_stage,decision)
        self.ui.horizontalLayout_3.insertWidget(1, self)

    def drawfigure(self,p_name, game_stage, decision,l):
        data = l.get_histrogram_data('Template', p_name, game_stage, decision)
        wins = data[0]
        losses = data[1]
        bins = np.linspace(0, 1, 50)

        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.hold(True)  # discards the old graph
        self.axes.set_title('Histogram')
        self.axes.set_xlabel('Equity')
        self.axes.set_ylabel('Number of hands')

        self.axes.hist(wins, bins, alpha=0.5, label='wins', color='g')
        self.axes.hist(losses, bins, alpha=0.5, label='losses', color='r')
        self.axes.legend(loc='upper right')
        self.draw()

class PiePlotter(FigureCanvas):
    def __init__(self, ui, winnerCardTypeList):
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        super(PiePlotter, self).__init__(self.fig)
        #self.drawfigure(winnerCardTypeList)
        self.ui.vLayout4.insertWidget(1, self)

    def drawfigure(self, winnerCardTypeList):
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.hold(False)
        self.axes.pie([float(v) for v in winnerCardTypeList.values()],
                        labels=[k for k in winnerCardTypeList.keys()], autopct=None)
        self.axes.set_title('Winning probabilities')
        self.draw()

class CurvePlot(FigureCanvas):
    def __init__(self, ui, p):
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        super(CurvePlot, self).__init__(self.fig)
        self.drawfigure()
        self.ui.vLayout3.insertWidget(1, self)

    def drawfigure(self):
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.hold(True)  # discards the old graph

        self.x2 = []
        self.y2 = []
        self.y3 = []
        self.x2 = np.arange(0, 1, 0.01)
        for each in self.x2:
            self.y2.append(0.5)
            self.y3.append(0.7)

        self.line2, = self.axes.plot(self.x2, self.y2, 'b-')  # Returns a tuple of line objects, thus the comma
        self.line3, = self.axes.plot(self.x2, self.y3, 'r-')  # Returns a tuple of line objects, thus the comma
        self.axes.axis((0, 1, 0, 1))
        self.axes.set_title('Maximum bet')
        self.axes.set_xlabel('Equity')
        self.axes.set_ylabel('Max $')
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

    def update_lines(self, power1, power2, minEquityCall, minEquityBet, smallBlind, bigBlind, maxValue, maxEquityCall,
                     maxEquityBet):
        x2 = np.linspace(0, 1, 100)

        d1 = Curvefitting(x2, smallBlind, bigBlind * 2, maxValue, minEquityCall, maxEquityCall, power1)
        d2 = Curvefitting(x2, smallBlind, bigBlind, maxValue, minEquityBet, maxEquityBet, power2)

        self.y2.extend(d1.y)
        self.y3.extend(d2.y)
        self.line2.set_ydata(self.y2[-100:])
        self.line3.set_ydata(self.y3[-100:])
        self.axes.set_ylim(0, max(1, maxValue))
        self.draw()

class FundsChangePlot(FigureCanvas):
    def __init__(self, ui_analyser):
        self.ui_analyser = proxy(ui_analyser)
        self.fig = Figure(dpi=50)
        super(FundsChangePlot, self).__init__(self.fig)
        self.drawfigure()
        self.ui_analyser.vLayout_fundschange.insertWidget(1, self)

    def drawfigure(self):
        LogFilename = 'log'
        L = Logging(LogFilename)
        p_name = str(self.ui_analyser.combobox_strategy.currentText())
        data=L.get_fundschange_chart(p_name)
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.hold(False)  # discards the old graph
        self.axes.set_title('My Funds')
        self.axes.set_xlabel('Time')
        self.axes.set_ylabel('$')
        self.axes.plot(data, '-')  # plot data
        self.draw()

class ScatterPlot(FigureCanvas):
    def __init__(self, ui):
        self.ui = proxy(ui)
        self.fig = Figure()
        super(ScatterPlot, self).__init__(self.fig)
        self.ui.horizontalLayout_4.insertWidget(1, self)

    def drawfigure(self,p_name, game_stage, decision,l,smallBlind, bigBlind, maxValue, minEquityBet, maxEquityBet, power):
        wins,losses=l.get_scatterplot_data('Template', p_name, game_stage, decision)
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.hold(True)
        self.axes.set_title('Wins and Losses')
        self.axes.set_xlabel('Equity')
        self.axes.set_ylabel('Minimum required call')

        try: self.axes.set_ylim(0, max(wins['minCall'].tolist()+losses['minCall'].tolist())*1.1)
        except: self.axes.set_ylim(0,1)
        self.axes.set_xlim(0, 1)

        # self.axes.set_xlim(.5, .8)
        # self.axes.set_ylim(0, .2)

        area = np.pi * (50 * wins['FinalFundsChange'])  # 0 to 15 point radiuses
        green_dots=self.axes.scatter(x=wins['equity'].tolist(), y=wins['minCall'], s=area, c='green', alpha=0.5)

        area = np.pi * (50 * abs(losses['FinalFundsChange']))
        red_dots=self.axes.scatter(x=losses['equity'].tolist(), y=losses['minCall'], s=area, c='red', alpha=0.5)

        self.axes.legend((green_dots,red_dots),
                         ('Wins', 'Losses'), loc=2)

        x2 = np.linspace(0, 1, 100)
        d2 = Curvefitting(x2, smallBlind, bigBlind, maxValue, minEquityBet, maxEquityBet, power)
        self.line3, = self.axes.plot(np.arange(0, 1, 0.01), d2.y[-100:], 'r-')  # Returns a tuple of line objects, thus the comma

        self.axes.grid()
        self.draw()

if __name__ == "__main__":
    import sys
    app = QtGui.QApplication(sys.argv)
    MainWindow = QtGui.QMainWindow()
    ui = Ui_Pokerbot()
    ui.setupUi(MainWindow)

    p = StrategyHandler()
    p.read_strategy()

    # plotter logic and binding needs to be added here
    gui_funds = FundsPlotter(ui, p)
    #ui.button_config.clicked.connect(plotter1.drawfigure)
    gui_bar = BarPlotter(ui, p)
    gui_curve = CurvePlot(ui, p)
    gui_pie = PiePlotter(ui, p)





    MainWindow.show()
    sys.exit(app.exec_())
