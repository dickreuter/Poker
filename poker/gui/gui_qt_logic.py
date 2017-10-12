import matplotlib
from PyQt5.QtCore import *

matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas)
from matplotlib.figure import Figure
from weakref import proxy
from poker.gui.gui_qt_ui_genetic_algorithm import *
from poker.gui.gui_qt_ui_strategy_manager import *
from poker.gui.GUI_QT_ui_analyser import *
from poker.gui.setup import *
from poker.gui.help import *
from poker.tools.vbox_manager import VirtualBoxController
from PyQt5.QtWidgets import QMessageBox
from poker.tools.mongo_manager import GameLogger,StrategyHandler
import webbrowser
from poker.decisionmaker.genetic_algorithm import *
from poker.decisionmaker.curvefitting import *
import os
import logging
from configobj import ConfigObj


class PandasModel(QtCore.QAbstractTableModel):
    """
    Class to populate a table_analysers view with a pandas dataframe
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

    signal_bar_chart_update = QtCore.pyqtSignal(object, str)
    signal_funds_chart_update = QtCore.pyqtSignal(object)
    signal_pie_chart_update = QtCore.pyqtSignal(dict)
    signal_curve_chart_update1 = QtCore.pyqtSignal(float, float, float, float, float, float, str, str)
    signal_curve_chart_update2 = QtCore.pyqtSignal(float, float, float, float, float, float, float, float, float, float, float)
    signal_lcd_number_update = QtCore.pyqtSignal(str, float)
    signal_label_number_update = QtCore.pyqtSignal(str, str)
    signal_update_selected_strategy = QtCore.pyqtSignal(str)

    signal_update_strategy_sliders = QtCore.pyqtSignal(str)
    signal_open_setup = QtCore.pyqtSignal(object, object)

    def __init__(self, ui_main_window):
        self.logger = logging.getLogger('gui')

        l = GameLogger()
        l.clean_database()

        self.p = StrategyHandler()
        self.p.read_strategy()
        p = self.p

        self.pause_thread = True
        self.exit_thread = False

        QObject.__init__(self)
        self.strategy_items_with_multipliers = {
            "always_call_low_stack_multiplier": 1,
            "out_multiplier": 1,
            "FlopBluffMaxEquity": 100,
            "TurnBluffMaxEquity": 100,
            "RiverBluffMaxEquity": 100,
            "max_abs_fundchange": 100,
            "RiverCheckDeceptionMinEquity": 100,
            "TurnCheckDeceptionMinEquity": 100,
            "pre_flop_equity_reduction_by_position": 100,
            "pre_flop_equity_increase_if_bet": 100,
            "pre_flop_equity_increase_if_call": 100,
            "minimum_bet_size": 1,
            "range_multiple_players": 100,
            "range_utg0": 100,
            "range_utg1": 100,
            "range_utg2": 100,
            "range_utg3": 100,
            "range_utg4": 100,
            "range_utg5": 100,
            "PreFlopCallPower": 1,
            "secondRiverBetPotMinEquity": 100,
            "FlopBetPower": 1,
            "betPotRiverEquityMaxBBM": 1,
            "TurnMinBetEquity": 100,
            "PreFlopBetPower": 1,
            "potAdjustmentPreFlop": 1,
            "RiverCallPower": 1,
            "minBullyEquity": 100,
            "PreFlopMinBetEquity": 100,
            "PreFlopMinCallEquity": 100,
            "BetPlusInc": 1,
            "FlopMinCallEquity": 100,
            "secondRoundAdjustmentPreFlop": 100,
            "FlopBluffMinEquity": 100,
            "TurnBluffMinEquity": 100,
            "FlopCallPower": 1,
            "TurnCallPower": 1,
            "RiverMinCallEquity": 100,
            "CoveredPlayersCallLikelihoodFlop": 100,
            "TurnMinCallEquity": 100,
            "secondRoundAdjustment": 100,
            "maxPotAdjustmentPreFlop": 100,
            "bullyDivider": 1,
            "maxBullyEquity": 100,
            "alwaysCallEquity": 100,
            "PreFlopMaxBetEquity": 100,
            "RiverBetPower": 1,
            "minimumLossForIteration": -1,
            "initialFunds": 100,
            "initialFunds2": 100,
            "potAdjustment": 1,
            "FlopCheckDeceptionMinEquity": 100,
            "bigBlind": 100,
            "secondRoundAdjustmentPowerIncrease": 1,
            "considerLastGames": 1,
            "betPotRiverEquity": 100,
            "RiverBluffMinEquity": 100,
            "smallBlind": 100,
            "TurnBetPower": 1,
            "FlopMinBetEquity": 100,
            "strategyIterationGames": 1,
            "RiverMinBetEquity": 100,
            "maxPotAdjustment": 100
        }
        self.pokersite_types = ['PP', 'PS2', 'SN', 'PP_old']

        self.ui = ui_main_window
        self.progressbar_value = 0

        # Main Window matplotlip widgets
        self.gui_funds = FundsPlotter(ui_main_window, p)
        self.gui_bar = BarPlotter(ui_main_window, p)
        self.gui_curve = CurvePlot(ui_main_window, p)
        self.gui_pie = PiePlotter(ui_main_window, winnerCardTypeList={'Highcard': 22})

        # main window status update signal connections
        self.signal_progressbar_increase.connect(self.increase_progressbar)
        self.signal_progressbar_reset.connect(self.reset_progressbar)
        self.signal_status.connect(self.update_mainwindow_status)
        self.signal_decision.connect(self.update_mainwindow_decision)

        self.signal_lcd_number_update.connect(self.update_lcd_number)
        self.signal_label_number_update.connect(self.update_label_number)

        self.signal_bar_chart_update.connect(lambda: self.gui_bar.drawfigure(l, p.current_strategy))

        self.signal_funds_chart_update.connect(lambda: self.gui_funds.drawfigure(l))
        self.signal_curve_chart_update1.connect(self.gui_curve.update_plots)
        self.signal_curve_chart_update2.connect(self.gui_curve.update_lines)
        self.signal_pie_chart_update.connect(self.gui_pie.drawfigure)
        self.signal_open_setup.connect(lambda: self.open_setup(p, l))

        ui_main_window.button_genetic_algorithm.clicked.connect(lambda: self.open_genetic_algorithm(p, l))
        ui_main_window.button_log_analyser.clicked.connect(lambda: self.open_strategy_analyser(p, l))
        ui_main_window.button_strategy_editor.clicked.connect(lambda: self.open_strategy_editor())
        ui_main_window.button_pause.clicked.connect(lambda: self.pause(ui_main_window, p))
        ui_main_window.button_resume.clicked.connect(lambda: self.resume(ui_main_window, p))

        ui_main_window.pushButton_setup.clicked.connect(lambda: self.open_setup(p, l))
        ui_main_window.pushButton_help.clicked.connect(lambda: self.open_help(p, l))

        self.signal_update_strategy_sliders.connect(lambda: self.update_strategy_editor_sliders(p.current_strategy))

        playable_list = p.get_playable_strategy_list()
        ui_main_window.comboBox_current_strategy.addItems(playable_list)
        ui_main_window.comboBox_current_strategy.currentIndexChanged[str].connect(
            lambda: self.signal_update_selected_strategy(l, p))
        config = ConfigObj("config.ini")
        initial_selection = config['last_strategy']
        for i in [i for i, x in enumerate(playable_list) if x == initial_selection]:
            idx = i
        ui_main_window.comboBox_current_strategy.setCurrentIndex(idx)

    def signal_update_selected_strategy(self, l, p):
        newly_selected_strategy = self.ui.comboBox_current_strategy.currentText()
        config = ConfigObj("config.ini")
        config['last_strategy'] = newly_selected_strategy
        config.write()
        p.read_strategy()
        self.logger.info("Active strategy changed to: " + p.current_strategy)

    def pause(self, ui, p):
        ui.button_resume.setEnabled(True)
        ui.button_pause.setEnabled(False)
        self.pause_thread = True

    def resume(self, ui, p):
        ui.button_resume.setEnabled(False)
        ui.button_pause.setEnabled(True)
        self.pause_thread = False

    def increase_progressbar(self, value):
        self.progressbar_value += value
        if self.progressbar_value > 100: self.progressbar_value = 100
        self.ui.progress_bar.setValue(self.progressbar_value)

    def reset_progressbar(self):
        self.progressbar_value = 0
        self.ui.progress_bar.setValue(0)

    def update_mainwindow_status(self, text):
        self.ui.status.setText(text)

    def update_mainwindow_decision(self, text):
        self.ui.last_decision.setText(text)

    def update_lcd_number(self, item, value):
        func = getattr(self.ui, item)
        func.display(value)

    def update_label_number(self, item, value):
        func = getattr(self.ui, item)
        func.setText(str(value))

    def open_strategy_analyser(self, p, l):
        self.signal_progressbar_reset.emit()
        self.stragegy_analyser_form = QtWidgets.QWidget()
        self.ui_analyser = Ui_Form()
        self.ui_analyser.setupUi(self.stragegy_analyser_form)
        self.stragegy_analyser_form.show()

        self.gui_fundschange = FundsChangePlot(self.ui_analyser)
        self.gui_fundschange.drawfigure()

        self.ui_analyser.combobox_actiontype.addItems(
            ['Fold', 'Check', 'Call', 'Bet', 'BetPlus', 'Bet half pot', 'Bet pot', 'Bet Bluff'])
        self.ui_analyser.combobox_gamestage.addItems(['PreFlop', 'Flop', 'Turn', 'River'])
        self.ui_analyser.combobox_strategy.addItems(l.get_played_strategy_list())

        index = self.ui_analyser.combobox_strategy.findText(p.current_strategy, QtCore.Qt.MatchFixedString)
        if index >= 0:
            self.ui_analyser.combobox_strategy.setCurrentIndex(index)

        self.gui_histogram = HistogramEquityWinLoss(self.ui_analyser)
        self.gui_scatterplot = ScatterPlot(self.ui_analyser)

        self.ui_analyser.combobox_gamestage.currentIndexChanged[str].connect(
            lambda: self.strategy_analyser_update_plots(l, p))
        self.ui_analyser.combobox_actiontype.currentIndexChanged[str].connect(
            lambda: self.strategy_analyser_update_plots(l, p))
        self.ui_analyser.combobox_strategy.currentIndexChanged[str].connect(lambda: self.update_strategy_analyser(l, p))

        self.gui_bar2 = BarPlotter2(self.ui_analyser, l)
        self.gui_bar2.drawfigure(l, self.ui_analyser.combobox_strategy.currentText())
        self.update_strategy_analyser(l, p)

    def open_strategy_editor(self):
        self.p_edited = StrategyHandler()
        self.p_edited.read_strategy()
        self.signal_progressbar_reset.emit()
        self.stragegy_editor_form = QtWidgets.QWidget()
        self.ui_editor = Ui_editor_form()
        self.ui_editor.setupUi(self.stragegy_editor_form)
        self.stragegy_editor_form.show()

        self.curveplot_preflop = CurvePlot(self.ui_editor, self.p_edited, layout='verticalLayout_preflop')
        self.curveplot_flop = CurvePlot(self.ui_editor, self.p_edited, layout='verticalLayout_flop')
        self.curveplot_turn = CurvePlot(self.ui_editor, self.p_edited, layout='verticalLayout_turn')
        self.curveplot_river = CurvePlot(self.ui_editor, self.p_edited, layout='verticalLayout_river')

        self.ui_editor.pushButton_update1.clicked.connect(
            lambda: self.update_strategy_editor_graphs(self.p_edited.current_strategy))
        self.ui_editor.pushButton_update2.clicked.connect(
            lambda: self.update_strategy_editor_graphs(self.p_edited.current_strategy))
        self.ui_editor.pushButton_update3.clicked.connect(
            lambda: self.update_strategy_editor_graphs(self.p_edited.current_strategy))
        self.ui_editor.pushButton_update4.clicked.connect(
            lambda: self.update_strategy_editor_graphs(self.p_edited.current_strategy))

        self.ui_editor.pokerSite.addItems(self.pokersite_types)

        self.signal_update_strategy_sliders.emit(self.p_edited.current_strategy)
        self.ui_editor.Strategy.currentIndexChanged.connect(
            lambda: self.update_strategy_editor_sliders(self.ui_editor.Strategy.currentText()))
        self.ui_editor.pushButton_save_new_strategy.clicked.connect(
            lambda: self.save_strategy(self.ui_editor.lineEdit_new_name.text(), False))
        self.ui_editor.pushButton_save_current_strategy.clicked.connect(
            lambda: self.save_strategy(self.ui_editor.Strategy.currentText(), True))

        self.playable_list = self.p_edited.get_playable_strategy_list()
        self.ui_editor.Strategy.addItems(self.playable_list)
        config = ConfigObj("config.ini")
        initial_selection = config['last_strategy']
        for i in [i for i, x in enumerate(self.playable_list) if x == initial_selection]:
            idx = i
        self.ui_editor.Strategy.setCurrentIndex(idx)

    def open_genetic_algorithm(self, p, l):
        self.ui.button_genetic_algorithm.setEnabled(False)
        g = GeneticAlgorithm(False, l)
        r = g.get_results()

        self.genetic_algorithm_dialog = QtWidgets.QDialog()
        self.genetic_algorithm_form = Ui_Dialog()
        self.genetic_algorithm_form.setupUi(self.genetic_algorithm_dialog)
        self.genetic_algorithm_dialog.show()

        self.genetic_algorithm_form.textBrowser.setText(str(r))
        self.genetic_algorithm_dialog.show()

        self.genetic_algorithm_form.buttonBox.accepted.connect(lambda: GeneticAlgorithm(True, self.logger, l))

    def open_help(self, p, l):
        url = "https://github.com/dickreuter/Poker/wiki/Frequently-asked-questions"
        webbrowser.open(url,new=2)
        # self.help_form = QtWidgets.QWidget()
        # self.ui_help = Ui_help_form()
        # self.ui_help.setupUi(self.help_form)
        # self.help_form.show()

    def open_setup(self, p, l):
        self.setup_form = QtWidgets.QWidget()
        self.ui_setup = Ui_setup_form()
        self.ui_setup.setupUi(self.setup_form)
        self.setup_form.show()

        self.ui_setup.pushButton_save.clicked.connect(lambda: self.save_setup())
        vm_list = ['Direct mouse control']
        try:
            vm = VirtualBoxController()
            vm_list += vm.get_vbox_list()
        except:
            pass  # no virtual machine

        self.ui_setup.comboBox_vm.addItems(vm_list)
        timeouts = ['8','9','10', '11','12']
        self.ui_setup.comboBox_2.addItems(timeouts)

        config = ConfigObj("config.ini")
        try:
            mouse_control = config['control']
        except:
            mouse_control = 'Direct mouse control'
        for i in [i for i, x in enumerate(vm_list) if x == mouse_control]:
            idx = i
            self.ui_setup.comboBox_vm.setCurrentIndex(idx)

        try:
            timeout = config['montecarlo_timeout']
        except:
            timeout = 10
        for i in [i for i, x in enumerate(timeouts) if x == timeout]:
            idx = i
            self.ui_setup.comboBox_2.setCurrentIndex(idx)

    def save_setup(self):
        config = ConfigObj("config.ini")
        config['control'] = self.ui_setup.comboBox_vm.currentText()
        config['montecarlo_timeout'] = self.ui_setup.comboBox_2.currentText()
        config.write()
        self.setup_form.close()

    def update_strategy_analyser(self, l, p):
        number_of_games = int(l.get_game_count(self.ui_analyser.combobox_strategy.currentText()))
        total_return = l.get_strategy_return(self.ui_analyser.combobox_strategy.currentText(), 999999)

        winnings_per_bb_100 = total_return / p.selected_strategy['bigBlind'] / number_of_games * 100

        self.ui_analyser.lcdNumber_2.display(number_of_games)
        self.ui_analyser.lcdNumber.display(winnings_per_bb_100)
        self.gui_bar2.drawfigure(l, self.ui_analyser.combobox_strategy.currentText())
        self.gui_fundschange.drawfigure()
        self.strategy_analyser_update_plots(l, p)
        self.strategy_analyser_update_table(l)

    def strategy_analyser_update_plots(self, l, p):
        p_name = str(self.ui_analyser.combobox_strategy.currentText())
        game_stage = str(self.ui_analyser.combobox_gamestage.currentText())
        decision = str(self.ui_analyser.combobox_actiontype.currentText())

        self.gui_histogram.drawfigure(p_name, game_stage, decision, l)

        if p_name == '.*':
            p.read_strategy()
        else:
            p.read_strategy(p_name)

        call_or_bet = 'Bet' if decision[0] == 'B' else 'Call'

        max_value = float(p.selected_strategy['initialFunds'])
        min_equity = float(p.selected_strategy[game_stage + 'Min' + call_or_bet + 'Equity'])
        max_equity = float(
            p.selected_strategy['PreFlopMaxBetEquity']) if game_stage == 'PreFlop' and call_or_bet == 'Bet' else 1
        power = float(p.selected_strategy[game_stage + call_or_bet + 'Power'])
        max_X = .86 if game_stage == "Preflop" else 1

        self.gui_scatterplot.drawfigure(p_name, game_stage, decision, l,
                                        float(p.selected_strategy['smallBlind']),
                                        float(p.selected_strategy['bigBlind']),
                                        max_value,
                                        min_equity,
                                        max_X,
                                        max_equity,
                                        power)

    def strategy_analyser_update_table(self, l):
        p_name = str(self.ui_analyser.combobox_strategy.currentText())
        df = l.get_worst_games(p_name)
        model = PandasModel(df)
        self.ui_analyser.tableView.setModel(model)

    def update_strategy_editor_sliders(self, strategy_name):
        self.p.read_strategy(strategy_name)
        for key, value in self.strategy_items_with_multipliers.items():
            func = getattr(self.ui_editor, key)
            func.setValue(100)
            v = float(self.p.selected_strategy[key]) * value
            func.setValue(v)
            # print (key)

        self.ui_editor.pushButton_save_current_strategy.setEnabled(False)
        try:
            if self.p.selected_strategy['computername'] == os.environ['COMPUTERNAME'] or \
                            os.environ['COMPUTERNAME'] == 'NICOLAS-ASUS' or os.environ['COMPUTERNAME'] == 'Home-PC-ND':
                self.ui_editor.pushButton_save_current_strategy.setEnabled(True)
        except Exception as e:
            pass

        selection = self.p.selected_strategy['pokerSite']
        for i in [i for i, x in enumerate(self.pokersite_types) if x == selection]:
            idx = i
        self.ui_editor.pokerSite.setCurrentIndex(idx)

        self.ui_editor.use_relative_equity.setChecked(self.p.selected_strategy['use_relative_equity'])
        self.ui_editor.use_pot_multiples.setChecked(self.p.selected_strategy['use_pot_multiples'])
        self.ui_editor.opponent_raised_without_initiative_flop.setChecked(self.p.selected_strategy['opponent_raised_without_initiative_flop'])
        self.ui_editor.opponent_raised_without_initiative_turn.setChecked(self.p.selected_strategy['opponent_raised_without_initiative_turn'])
        self.ui_editor.opponent_raised_without_initiative_river.setChecked(self.p.selected_strategy['opponent_raised_without_initiative_river'])
        self.ui_editor.differentiate_reverse_sheet.setChecked(self.p.selected_strategy['differentiate_reverse_sheet'])
        self.ui_editor.preflop_override.setChecked(self.p.selected_strategy['preflop_override'])
        self.ui_editor.gather_player_names.setChecked(self.p.selected_strategy['gather_player_names'])

        self.ui_editor.collusion.setChecked(self.p.selected_strategy['collusion'])
        self.ui_editor.flop_betting_condidion_1.setChecked(self.p.selected_strategy['flop_betting_condidion_1'])
        self.ui_editor.turn_betting_condidion_1.setChecked(self.p.selected_strategy['turn_betting_condidion_1'])
        self.ui_editor.river_betting_condidion_1.setChecked(self.p.selected_strategy['river_betting_condidion_1'])
        self.ui_editor.flop_bluffing_condidion_1.setChecked(self.p.selected_strategy['flop_bluffing_condidion_1'])
        self.ui_editor.turn_bluffing_condidion_1.setChecked(self.p.selected_strategy['turn_bluffing_condidion_1'])
        self.ui_editor.turn_bluffing_condidion_2.setChecked(self.p.selected_strategy['turn_bluffing_condidion_2'])
        self.ui_editor.river_bluffing_condidion_1.setChecked(self.p.selected_strategy['river_bluffing_condidion_1'])
        self.ui_editor.river_bluffing_condidion_2.setChecked(self.p.selected_strategy['river_bluffing_condidion_2'])

        self.update_strategy_editor_graphs(strategy_name)

    def update_strategy_editor_graphs(self, strategy_name):
        strategy_dict = self.update_dictionary(strategy_name)

        try:
            self.curveplot_preflop.update_lines(float(strategy_dict['PreFlopCallPower']),
                                                float(strategy_dict['PreFlopBetPower']),
                                                float(strategy_dict['PreFlopMinCallEquity']),
                                                float(strategy_dict['PreFlopMinBetEquity']),
                                                float(strategy_dict['smallBlind']),
                                                float(strategy_dict['bigBlind']),
                                                float(strategy_dict['initialFunds']),
                                                float(strategy_dict['initialFunds2']),
                                                1,
                                                0.85,
                                                float(strategy_dict['PreFlopMaxBetEquity']))

            self.curveplot_flop.update_lines(float(strategy_dict['FlopCallPower']),
                                             float(strategy_dict['FlopBetPower']),
                                             float(strategy_dict['FlopMinCallEquity']),
                                             float(strategy_dict['FlopMinBetEquity']),
                                             float(strategy_dict['smallBlind']),
                                             float(strategy_dict['bigBlind']),
                                             float(strategy_dict['initialFunds']),
                                             float(strategy_dict['initialFunds2']),
                                             1,
                                             1,
                                             1)

            self.curveplot_turn.update_lines(float(strategy_dict['TurnCallPower']),
                                             float(strategy_dict['TurnBetPower']),
                                             float(strategy_dict['TurnMinCallEquity']),
                                             float(strategy_dict['TurnMinBetEquity']),
                                             float(strategy_dict['smallBlind']),
                                             float(strategy_dict['bigBlind']),
                                             float(strategy_dict['initialFunds']),
                                             float(strategy_dict['initialFunds2']),
                                             1,
                                             1,
                                             1)

            self.curveplot_river.update_lines(float(strategy_dict['RiverCallPower']),
                                              float(strategy_dict['RiverBetPower']),
                                              float(strategy_dict['RiverMinCallEquity']),
                                              float(strategy_dict['RiverMinBetEquity']),
                                              float(strategy_dict['smallBlind']),
                                              float(strategy_dict['bigBlind']),
                                              float(strategy_dict['initialFunds']),
                                              float(strategy_dict['initialFunds2']),
                                              1,
                                              1,
                                              1)
        except:
            print("retry")

    def update_dictionary(self, name):
        self.strategy_dict = self.p_edited.selected_strategy
        for key, value in self.strategy_items_with_multipliers.items():
            func = getattr(self.ui_editor, key)
            self.strategy_dict[key] = func.value() / value
        self.strategy_dict['Strategy'] = name
        self.strategy_dict['pokerSite'] = self.ui_editor.pokerSite.currentText()
        self.strategy_dict['computername'] = os.environ['COMPUTERNAME']

        self.strategy_dict['use_relative_equity'] = int(self.ui_editor.use_relative_equity.isChecked())
        self.strategy_dict['use_pot_multiples'] = int(self.ui_editor.use_pot_multiples.isChecked())

        self.strategy_dict['opponent_raised_without_initiative_flop'] = int(self.ui_editor.opponent_raised_without_initiative_flop.isChecked())
        self.strategy_dict['opponent_raised_without_initiative_turn'] = int(self.ui_editor.opponent_raised_without_initiative_turn.isChecked())
        self.strategy_dict['opponent_raised_without_initiative_river'] = int(self.ui_editor.opponent_raised_without_initiative_river.isChecked())


        self.strategy_dict['differentiate_reverse_sheet'] = int(self.ui_editor.differentiate_reverse_sheet.isChecked())
        self.strategy_dict['preflop_override'] = int(self.ui_editor.preflop_override.isChecked())
        self.strategy_dict['gather_player_names'] = int(self.ui_editor.gather_player_names.isChecked())

        self.strategy_dict['collusion'] = int(self.ui_editor.collusion.isChecked())

        self.strategy_dict['flop_betting_condidion_1'] = int(self.ui_editor.flop_betting_condidion_1.isChecked())
        self.strategy_dict['turn_betting_condidion_1'] = int(self.ui_editor.turn_betting_condidion_1.isChecked())
        self.strategy_dict['river_betting_condidion_1'] = int(self.ui_editor.river_betting_condidion_1.isChecked())
        self.strategy_dict['flop_bluffing_condidion_1'] = int(self.ui_editor.flop_bluffing_condidion_1.isChecked())
        self.strategy_dict['turn_bluffing_condidion_1'] = int(self.ui_editor.turn_bluffing_condidion_1.isChecked())
        self.strategy_dict['turn_bluffing_condidion_2'] = int(self.ui_editor.turn_bluffing_condidion_2.isChecked())
        self.strategy_dict['river_bluffing_condidion_1'] = int(self.ui_editor.river_bluffing_condidion_1.isChecked())
        self.strategy_dict['river_bluffing_condidion_2'] = int(self.ui_editor.river_bluffing_condidion_2.isChecked())

        return self.strategy_dict

    def save_strategy(self, name, update):
        if (name != "" and name not in self.playable_list) or update:
            strategy_dict = self.update_dictionary(name)
            if update:
                self.p_edited.update_strategy(strategy_dict)
            else:
                self.p_edited.save_strategy(strategy_dict)
                self.ui_editor.Strategy.insertItem(0, name)
                idx = len(self.p_edited.get_playable_strategy_list())
                self.ui_editor.Strategy.setCurrentIndex(0)
                self.ui.comboBox_current_strategy.insertItem(0, name)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Saved")
            msg.setWindowTitle("Strategy editor")
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec()
            self.logger.info("Strategy saved successfully")

        else:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("There has been a problem and the strategy is not saved. Check if the name is already taken.")
            msg.setWindowTitle("Strategy editor")
            msg.setStandardButtons(QMessageBox.Ok)
            retval = msg.exec()
            self.logger.warning("Strategy not saved")


class FundsPlotter(FigureCanvas):
    def __init__(self, ui, p):
        self.p = p
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        super(FundsPlotter, self).__init__(self.fig)
        # self.drawfigure()
        self.ui.vLayout.insertWidget(1, self)

    def drawfigure(self, L):
        Strategy = str(self.p.current_strategy)
        data = L.get_fundschange_chart(Strategy)
        data = np.cumsum(data)
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.clear() # discards the old graph
        self.axes.set_title('My Funds')
        self.axes.set_xlabel('Time')
        self.axes.set_ylabel('$')
        self.axes.plot(data, '-')  # plot data
        self.draw()


class BarPlotter(FigureCanvas):
    def __init__(self, ui, p):
        self.p = p
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        super(BarPlotter, self).__init__(self.fig)
        # self.drawfigure()
        self.ui.vLayout2.insertWidget(1, self)

    def drawfigure(self, l, strategy):
        self.axes = self.fig.add_subplot(111)  # create an axis


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
                         ('Bluff/Decept.', 'BetPot', 'BetHfPot', 'Bet/Bet+', 'Call', 'Check', 'Fold'),
                         labelspacing=0.03,
                         prop={'size': 12})
        maxh = float(self.p.selected_strategy['bigBlind']) * 20
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
    def __init__(self, ui_analyser, l):
        self.ui_analyser = proxy(ui_analyser)
        self.fig = Figure(dpi=70)
        super(BarPlotter2, self).__init__(self.fig)
        self.drawfigure(l, self.ui_analyser.combobox_strategy.currentText())
        self.ui_analyser.vLayout_bar.insertWidget(1, self)

    def drawfigure(self, l, strategy):
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis

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
        maxh = 0.02
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

        # self.axes.set_ylim((0, maxh))

        self.draw()


class HistogramEquityWinLoss(FigureCanvas):
    def __init__(self, ui):
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
        super(HistogramEquityWinLoss, self).__init__(self.fig)
        # self.drawfigure(template,game_stage,decision)
        self.ui.horizontalLayout_3.insertWidget(1, self)

    def drawfigure(self, p_name, game_stage, decision, l):
        data = l.get_histrogram_data('Template', p_name, game_stage, decision)
        wins = data[0]
        losses = data[1]
        bins = np.linspace(0, 1, 50)

        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis

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
        # self.drawfigure(winnerCardTypeList)
        self.ui.vLayout4.insertWidget(1, self)

    def drawfigure(self, winnerCardTypeList):
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.clear()
        self.axes.pie([float(v) for v in winnerCardTypeList.values()],
                      labels=[k for k in winnerCardTypeList.keys()], autopct=None)
        self.axes.set_title('Winning probabilities')
        self.draw()


class CurvePlot(FigureCanvas):
    def __init__(self, ui, p, layout='vLayout3'):
        self.p=p
        self.ui = proxy(ui)
        self.fig = Figure(dpi=50)
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

    def update_lines(self, power1, power2, minEquityCall, minEquityBet, smallBlind, bigBlind, maxValue, maxvalue_bet, maxEquityCall,
                     max_X,
                     maxEquityBet):
        x2 = np.linspace(0, 1, 100)

        minimum_curve_value = 0 if self.p.selected_strategy['use_pot_multiples'] else smallBlind
        minimum_curve_value2 = 0 if self.p.selected_strategy['use_pot_multiples'] else bigBlind
        d1 = Curvefitting(x2, minimum_curve_value, minimum_curve_value2 * 2, maxValue, minEquityCall, maxEquityCall, max_X, power1)
        d2 = Curvefitting(x2, minimum_curve_value, minimum_curve_value2, maxvalue_bet, minEquityBet, maxEquityBet, max_X, power2)
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


class FundsChangePlot(FigureCanvas):
    def __init__(self, ui_analyser):
        self.ui_analyser = proxy(ui_analyser)
        self.fig = Figure(dpi=50)
        super(FundsChangePlot, self).__init__(self.fig)
        self.drawfigure()
        self.ui_analyser.vLayout_fundschange.insertWidget(1, self)

    def drawfigure(self):
        LogFilename = 'log'
        L = GameLogger(LogFilename)
        p_name = str(self.ui_analyser.combobox_strategy.currentText())
        data = L.get_fundschange_chart(p_name)
        self.fig.clf()
        self.axes = self.fig.add_subplot(111)  # create an axis
        self.axes.clear()   # discards the old graph
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
            self.axes.set_ylim(0, max(wins['minCall'].tolist() + losses['minCall'].tolist()) * 1.1)
        except:
            self.axes.set_ylim(0, 1)
        self.axes.set_xlim(0, 1)

        # self.axes.set_xlim(.5, .8)
        # self.axes.set_ylim(0, .2)

        area = np.pi * (50 * wins['FinalFundsChange'])  # 0 to 15 point radiuses
        green_dots = self.axes.scatter(x=wins['equity'].tolist(), y=wins['minCall'], s=area, c='green', alpha=0.5)

        area = np.pi * (50 * abs(losses['FinalFundsChange']))
        red_dots = self.axes.scatter(x=losses['equity'].tolist(), y=losses['minCall'], s=area, c='red', alpha=0.5)

        self.axes.legend((green_dots, red_dots),
                         ('Wins', 'Losses'), loc=2)

        x2 = np.linspace(0, 1, 100)
        d2 = Curvefitting(x2, 0, 0, maxValue, minEquityBet, maxEquityBet, max_X, power)
        self.line3, = self.axes.plot(np.arange(0, 1, 0.01), d2.y[-100:],
                                     'r-')  # Returns a tuple of line objects, thus the comma

        self.axes.grid()
        self.draw()


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    editor_form = QtWidgets.QWidget()
    ui = Ui_editor_form()
    ui.setupUi(editor_form)
    editor_form.show()
    sys.exit(app.exec_())
