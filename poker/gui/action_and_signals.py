# pylint: disable=ungrouped-imports

from sys import platform

import numexpr  # required for pyinstaller
from PyQt6 import QtCore

_ = numexpr
import matplotlib
from matplotlib import pyplot as plt
import seaborn as sns
import numpy as np

from poker.gui.pandas_model import PandasModel
from poker.gui.plots.bar_plotter_2 import BarPlotter2
from poker.gui.plots.curve_plot import CurvePlot
from poker.gui.plots.funds_change_plot import FundsChangePlot
from poker.gui.plots.funds_plotter import FundsPlotter
from poker.gui.plots.histogram_equity import HistogramEquityWinLoss
from poker.gui.plots.pie_plotter import PiePlotter
from poker.gui.plots.scatter_plot import ScatterPlot
from poker.tools.helper import COMPUTER_NAME, open_payment_link

if not (platform == "linux" or platform == "linux2"):  # pylint: disable=consider-using-in
    matplotlib.use('Qt5Agg')
from PyQt6.QtCore import *
from poker.scraper.table_setup_actions_and_signals import TableSetupActionAndSignals
from poker.gui.gui_launcher import TableSetupForm, GeneticAlgo, SetupForm, StrategyEditorForm, AnalyserForm
from poker.tools.mongo_manager import MongoManager

from poker.tools.vbox_manager import VirtualBoxController
from PyQt6.QtWidgets import QMessageBox
import webbrowser
from poker.decisionmaker.genetic_algorithm import *  # pylint: disable=wildcard-import
import os
import logging



# pylint: disable=unnecessary-lambda

class UIActionAndSignals(QObject):  # pylint: disable=undefined-variable
    signal_progressbar_increase = QtCore.pyqtSignal(int)
    signal_progressbar_reset = QtCore.pyqtSignal()

    signal_status = QtCore.pyqtSignal(str)
    signal_decision = QtCore.pyqtSignal(str)

    signal_bar_chart_update = QtCore.pyqtSignal(object, str)
    signal_funds_chart_update = QtCore.pyqtSignal(object)
    signal_pie_chart_update = QtCore.pyqtSignal(dict)
    signal_curve_chart_update1 = QtCore.pyqtSignal(float, float, float, float, float, float, str, str)
    signal_curve_chart_update2 = QtCore.pyqtSignal(float, float, float, float, float, float, float, float, float, float,
                                                   float)
    signal_lcd_number_update = QtCore.pyqtSignal(str, float)
    signal_label_number_update = QtCore.pyqtSignal(str, str)
    # signal_update_selected_strategy = QtCore.pyqtSignal(str)

    signal_update_strategy_sliders = QtCore.pyqtSignal(str)
    signal_open_setup = QtCore.pyqtSignal(object, object)

    def __init__(self, ui_main_window):
        self.logger = logging.getLogger('gui')

        self.ui_analyser = None

        gl = GameLogger()

        self.strategy_handler = StrategyHandler()
        self.strategy_handler.read_strategy()
        p = self.strategy_handler

        self.pause_thread = True
        self.exit_thread = False

        QObject.__init__(self)  # pylint: disable=undefined-variable
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
            "range_utg6": 100,
            "range_utg7": 100,
            "range_utg8": 100,
            "range_preflop": 100,
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
            "maxPotAdjustment": 100,
            "increased_preflop_betting": 1

        }

        self.ui = ui_main_window
        self.progressbar_value = 0

        # Main Window matplotlip widgets
        self.gui_funds = FundsPlotter(ui_main_window, p)
        self.gui_bar = BarPlotter2(ui_main_window, initialize=True)
        self.gui_curve = CurvePlot(ui_main_window, p)
        self.gui_pie = PiePlotter(ui_main_window, winnerCardTypeList={'Highcard': 22})

        # main window status update signal connections
        self.signal_progressbar_increase.connect(self.increase_progressbar)
        self.signal_progressbar_reset.connect(self.reset_progressbar)
        self.signal_status.connect(self.update_mainwindow_status)
        self.signal_decision.connect(self.update_mainwindow_decision)

        self.signal_lcd_number_update.connect(self.update_lcd_number)
        self.signal_label_number_update.connect(self.update_label_number)

        self.signal_bar_chart_update.connect(lambda: self.gui_bar.drawfigure(gl, p.current_strategy))

        self.signal_funds_chart_update.connect(lambda: self.gui_funds.drawfigure(gl))
        self.signal_curve_chart_update1.connect(self.gui_curve.update_plots)
        self.signal_curve_chart_update2.connect(self.gui_curve.update_lines)
        self.signal_pie_chart_update.connect(self.gui_pie.drawfigure)
        self.signal_open_setup.connect(lambda: self.open_setup())

        ui_main_window.button_genetic_algorithm.clicked.connect(lambda: self.open_genetic_algorithm(p, gl))
        ui_main_window.button_log_analyser.clicked.connect(lambda: self.open_strategy_analyser(p, gl))
        ui_main_window.button_strategy_editor.clicked.connect(lambda: self.open_strategy_editor())
        ui_main_window.button_pause.clicked.connect(lambda: self.pause(ui_main_window, p))
        ui_main_window.button_resume.clicked.connect(lambda: self.resume(ui_main_window, p))

        ui_main_window.pushButton_setup.clicked.connect(lambda: self.open_setup())
        ui_main_window.pushButton_help.clicked.connect(lambda: self.open_help())
        ui_main_window.open_chat.clicked.connect(lambda: self.open_chat())
        ui_main_window.button_table_setup.clicked.connect(lambda: self.open_table_setup())

        self.signal_update_strategy_sliders.connect(lambda: self.update_strategy_editor_sliders(p.current_strategy))

        mongo = MongoManager()
        available_tables = mongo.get_available_tables(COMPUTER_NAME)
        ui_main_window.table_selection.addItems(available_tables)
        playable_list = p.get_playable_strategy_list()
        ui_main_window.comboBox_current_strategy.addItems(playable_list)
        ui_main_window.comboBox_current_strategy.currentIndexChanged[int].connect(
            lambda: self.signal_update_selected_strategy(p))
        ui_main_window.table_selection.currentIndexChanged[int].connect(
            lambda: self.signal_update_selected_strategy(p))
        config = get_config()
        initial_selection = config.config.get('main', 'last_strategy')
        idx = 0
        for i in [i for i, x in enumerate(playable_list) if x == initial_selection]:
            idx = i
        ui_main_window.comboBox_current_strategy.setCurrentIndex(idx)

        table_scraper_name = config.config.get('main', 'table_scraper_name')
        try:
            idx = available_tables.index(table_scraper_name)
        except ValueError:
            idx = 0
        ui_main_window.table_selection.setCurrentIndex(idx)

    def signal_update_selected_strategy(self, p):
        config = get_config()

        newly_selected_strategy = self.ui.comboBox_current_strategy.currentText()
        config.config.set('main', 'last_strategy', newly_selected_strategy)

        table_selection = self.ui.table_selection.currentText()
        config.config.set('main', 'table_scraper_name', table_selection)

        config.update_file()
        p.read_strategy()
        self.logger.info("Active strategy changed to: " + p.current_strategy)
        self.logger.info("Active table changed to: " + table_selection)

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
        self.progressbar_value = min(self.progressbar_value, 100)
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
        self.ui_analyser = AnalyserForm()

        self.gui_fundschange = FundsChangePlot(self.ui_analyser)
        self.gui_fundschange.drawfigure(self.ui_analyser.my_computer_only.isChecked())

        self.ui_analyser.combobox_actiontype.addItems(
            ['All', 'Fold', 'Check', 'Call', 'Bet', 'BetPlus', 'Bet half pot', 'Bet pot', 'Bet Bluff'])
        self.ui_analyser.combobox_gamestage.addItems(['All', 'PreFlop', 'Flop', 'Turn', 'River'])
        self.ui_analyser.combobox_strategy.addItems(l.get_played_strategy_list())

        index = self.ui_analyser.combobox_strategy.findText(p.current_strategy, QtCore.Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            self.ui_analyser.combobox_strategy.setCurrentIndex(index)

        self.gui_histogram = HistogramEquityWinLoss(self.ui_analyser)
        self.gui_scatterplot = ScatterPlot(self.ui_analyser)

        self.ui_analyser.combobox_gamestage.currentIndexChanged[int].connect(
            lambda: self.strategy_analyser_update_plots(l, p))
        self.ui_analyser.combobox_actiontype.currentIndexChanged[int].connect(
            lambda: self.strategy_analyser_update_plots(l, p))
        self.ui_analyser.combobox_strategy.currentIndexChanged[int].connect(lambda: self.update_strategy_analyser(l, p))
        self.ui_analyser.show_rounds.stateChanged[int].connect(lambda: self.update_strategy_analyser(l, p))
        self.ui_analyser.my_computer_only.stateChanged[int].connect(lambda: self.update_strategy_analyser(l, p))
        self.ui_analyser.show_league_table.clicked.connect(lambda: self.show_league_table())

        self.gui_bar2 = BarPlotter2(self.ui_analyser)
        self.gui_bar2.drawfigure(l,
                                 self.ui_analyser.combobox_strategy.currentText(),
                                 self.ui_analyser.combobox_gamestage.currentText(),
                                 self.ui_analyser.combobox_actiontype.currentText(),
                                 self.ui_analyser.show_rounds.isChecked(),
                                 self.ui_analyser.my_computer_only.isChecked())
        self.update_strategy_analyser(l, p)

    @staticmethod
    def show_league_table():
        mongo = MongoManager()
        top_df = mongo.get_top_strategies().sort_values('Return per bb in 100 Hands', ascending=False)

        def colors_from_values(values, palette_name):
            # normalize the values to range [0, 1]
            normalized = (values - min(values)) / (max(values) - min(values))
            # convert to indices
            indices = np.round(normalized * (len(values) - 1)).astype(np.int32)
            # use the indices to get the colors
            palette = sns.color_palette(palette_name, len(values))
            return np.array(palette).take(indices, axis=0)

        ax, fig = plt.subplots(figsize=(25, 20))
        sns.barplot(data=top_df, x='Return per bb in 100 Hands', y='_id', ci=None,
                    palette=colors_from_values(top_df['count'], "YlOrRd")).set(
            title='Top Strategies by individual player')
        plt.show()

    def open_strategy_editor(self):
        self.p_edited = StrategyHandler()
        self.p_edited.read_strategy()
        self.signal_progressbar_reset.emit()
        self.ui_editor = StrategyEditorForm()

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

        self.signal_update_strategy_sliders.emit(self.p_edited.current_strategy)
        self.ui_editor.Strategy.currentIndexChanged.connect(
            lambda: self.update_strategy_editor_sliders(self.ui_editor.Strategy.currentText()))
        self.ui_editor.pushButton_save_new_strategy.clicked.connect(
            lambda: self.save_strategy(self.ui_editor.lineEdit_new_name.text(), False))
        self.ui_editor.pushButton_save_current_strategy.clicked.connect(
            lambda: self.save_strategy(self.ui_editor.Strategy.currentText(), True))

        self.playable_list = self.p_edited.get_playable_strategy_list()
        self.ui_editor.Strategy.addItems(self.playable_list)
        config = get_config()
        initial_selection = config.config.get('main', 'last_strategy')
        idx = 0
        for i in [i for i, x in enumerate(self.playable_list) if x == initial_selection]:
            idx = i
        self.ui_editor.Strategy.setCurrentIndex(idx)

    def open_genetic_algorithm(self, p, l):
        self.ui.button_genetic_algorithm.setEnabled(False)
        g = GeneticAlgorithm(False, l)
        r = g.get_results()
        self.genetic_algorithm_form = GeneticAlgo()
        self.genetic_algorithm_form.textBrowser.setText(str(r))

        self.genetic_algorithm_form.buttonBox.accepted.connect(lambda: GeneticAlgorithm(True, l))

    def open_help(self):
        url = "https://github.com/dickreuter/Poker"
        webbrowser.open(url, new=2)
        # self.help_form = QtWidgets.QWidget()
        # self.ui_help = Ui_help_form()
        # self.ui_help.setupUi(self.help_form)
        # self.help_form.show()

    def open_chat(self):
        url = "https://discord.gg/xB9sR3Q7r3"
        webbrowser.open(url, new=2)

    def open_table_setup(self):
        self.ui_setup_table = TableSetupForm()
        gui_signals = TableSetupActionAndSignals(self.ui_setup_table)

    def open_setup(self):
        self.ui_setup = SetupForm()
        self.ui_setup.pushButton_save.clicked.connect(lambda: self.save_setup())
        vm_list = ['Direct mouse control']
        try:
            vm = VirtualBoxController()
            vm_list += vm.get_vbox_list()
        except:
            pass  # no virtual machine

        self.ui_setup.comboBox_vm.addItems(vm_list)
        timeouts = ['8', '9', '10', '11', '12']
        self.ui_setup.comboBox_2.addItems(timeouts)

        config = get_config()
        try:
            mouse_control = config.config.get('main', 'control')
        except:
            mouse_control = 'Direct mouse control'
        for i in [i for i, x in enumerate(vm_list) if x == mouse_control]:
            idx = i
            self.ui_setup.comboBox_vm.setCurrentIndex(idx)

        try:
            timeout = config.config.get('main', 'montecarlo_timeout')
        except:
            timeout = 10
        for i in [i for i, x in enumerate(timeouts) if x == timeout]:
            idx = i
            self.ui_setup.comboBox_2.setCurrentIndex(idx)

        login = config.config.get('main', 'login')
        password = config.config.get('main', 'password')
        db = config.config.get('main', 'db')

        self.ui_setup.login.setText(login)
        self.ui_setup.password.setText(password)

    def save_setup(self):
        config = get_config()
        config.config.set('main', 'control', self.ui_setup.comboBox_vm.currentText())
        config.config.set('main', 'montecarlo_timeout', self.ui_setup.comboBox_2.currentText())
        config.config.set('main', 'login', self.ui_setup.login.text())
        config.config.set('main', 'password', self.ui_setup.password.text())
        config.update_file()
        self.ui_setup.close()

    def update_strategy_analyser(self, l, p):
        number_of_games = int(l.get_game_count(self.ui_analyser.combobox_strategy.currentText(),
                                               self.ui_analyser.my_computer_only.isChecked()))
        total_return = l.get_strategy_return(self.ui_analyser.combobox_strategy.currentText(), 999999,
                                             self.ui_analyser.my_computer_only.isChecked())

        try:
            winnings_per_bb_100 = total_return / p.selected_strategy['bigBlind'] / number_of_games * 100
        except ZeroDivisionError:
            winnings_per_bb_100 = 0

        self.ui_analyser.lcdNumber_2.display(number_of_games)
        self.ui_analyser.lcdNumber.display(winnings_per_bb_100)
        self.gui_fundschange.drawfigure(self.ui_analyser.my_computer_only.isChecked())
        self.strategy_analyser_update_plots(l, p)
        self.strategy_analyser_update_table(l)

    def strategy_analyser_update_plots(self, l, p):
        p_name = str(self.ui_analyser.combobox_strategy.currentText())
        game_stage = str(self.ui_analyser.combobox_gamestage.currentText())
        decision = str(self.ui_analyser.combobox_actiontype.currentText())

        self.gui_histogram.drawfigure(p_name, game_stage, decision, l)
        self.gui_bar2.drawfigure(l,
                                 self.ui_analyser.combobox_strategy.currentText(),
                                 self.ui_analyser.combobox_gamestage.currentText(),
                                 self.ui_analyser.combobox_actiontype.currentText(),
                                 self.ui_analyser.show_rounds.isChecked(),
                                 self.ui_analyser.my_computer_only.isChecked())

        p.read_strategy(p_name)

        call_or_bet = 'Bet' if decision[0] == 'B' else 'Call'

        max_value = float(p.selected_strategy['initialFunds'])
        if game_stage == 'All':
            game_stage = 'PreFlop'
        min_equity = float(p.selected_strategy[game_stage + 'Min' + call_or_bet + 'Equity'])
        max_equity = float(
            p.selected_strategy['PreFlopMaxBetEquity']) if game_stage == 'PreFlop' and call_or_bet == 'Bet' else 1
        power = float(p.selected_strategy[game_stage + call_or_bet + 'Power'])
        max_X = .95 if game_stage == "Preflop" else 1

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
        if not df.empty:
            model = PandasModel(df)
            self.ui_analyser.tableView.setModel(model)

    def update_strategy_editor_sliders(self, strategy_name):
        self.strategy_handler.read_strategy(strategy_name)
        for key, value in self.strategy_items_with_multipliers.items():
            func = getattr(self.ui_editor, key)
            func.setValue(100)
            v = int(self.strategy_handler.selected_strategy[key] * value)
            func.setValue(v)
            # print (key)

        self.ui_editor.pushButton_save_current_strategy.setEnabled(False)
        try:
            if self.strategy_handler.selected_strategy['computername'] == COMPUTER_NAME or \
                    COMPUTER_NAME == 'NICOLAS-ASUS' or COMPUTER_NAME == 'Home-PC-ND':
                self.ui_editor.pushButton_save_current_strategy.setEnabled(True)
        except Exception as e:
            pass

        self.ui_editor.use_relative_equity.setChecked(self.strategy_handler.selected_strategy['use_relative_equity'])
        self.ui_editor.use_pot_multiples.setChecked(self.strategy_handler.selected_strategy['use_pot_multiples'])
        self.ui_editor.opponent_raised_without_initiative_flop.setChecked(
            self.strategy_handler.selected_strategy['opponent_raised_without_initiative_flop'])
        self.ui_editor.opponent_raised_without_initiative_turn.setChecked(
            self.strategy_handler.selected_strategy['opponent_raised_without_initiative_turn'])
        self.ui_editor.opponent_raised_without_initiative_river.setChecked(
            self.strategy_handler.selected_strategy['opponent_raised_without_initiative_river'])
        self.ui_editor.differentiate_reverse_sheet.setChecked(
            self.strategy_handler.selected_strategy['differentiate_reverse_sheet'])
        self.ui_editor.range_of_range.setChecked(
            self.strategy_handler.selected_strategy['range_of_range'])
        self.ui_editor.preflop_override.setChecked(self.strategy_handler.selected_strategy['preflop_override'])
        self.ui_editor.gather_player_names.setChecked(self.strategy_handler.selected_strategy['gather_player_names'])

        self.ui_editor.collusion.setChecked(self.strategy_handler.selected_strategy['collusion'])
        self.ui_editor.flop_betting_condidion_1.setChecked(
            self.strategy_handler.selected_strategy['flop_betting_condidion_1'])
        self.ui_editor.turn_betting_condidion_1.setChecked(
            self.strategy_handler.selected_strategy['turn_betting_condidion_1'])
        self.ui_editor.river_betting_condidion_1.setChecked(
            self.strategy_handler.selected_strategy['river_betting_condidion_1'])
        self.ui_editor.flop_bluffing_condidion_1.setChecked(
            self.strategy_handler.selected_strategy['flop_bluffing_condidion_1'])
        self.ui_editor.turn_bluffing_condidion_1.setChecked(
            self.strategy_handler.selected_strategy['turn_bluffing_condidion_1'])
        self.ui_editor.turn_bluffing_condidion_2.setChecked(
            self.strategy_handler.selected_strategy['turn_bluffing_condidion_2'])
        self.ui_editor.river_bluffing_condidion_1.setChecked(
            self.strategy_handler.selected_strategy['river_bluffing_condidion_1'])
        self.ui_editor.river_bluffing_condidion_2.setChecked(
            self.strategy_handler.selected_strategy['river_bluffing_condidion_2'])

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
        self.strategy_dict['computername'] = COMPUTER_NAME

        self.strategy_dict['use_relative_equity'] = int(self.ui_editor.use_relative_equity.isChecked())
        self.strategy_dict['use_pot_multiples'] = int(self.ui_editor.use_pot_multiples.isChecked())

        self.strategy_dict['opponent_raised_without_initiative_flop'] = int(
            self.ui_editor.opponent_raised_without_initiative_flop.isChecked())
        self.strategy_dict['opponent_raised_without_initiative_turn'] = int(
            self.ui_editor.opponent_raised_without_initiative_turn.isChecked())
        self.strategy_dict['opponent_raised_without_initiative_river'] = int(
            self.ui_editor.opponent_raised_without_initiative_river.isChecked())

        self.strategy_dict['differentiate_reverse_sheet'] = int(self.ui_editor.differentiate_reverse_sheet.isChecked())
        self.strategy_dict['preflop_override'] = int(self.ui_editor.preflop_override.isChecked())
        self.strategy_dict['range_of_range'] = int(self.ui_editor.range_of_range.isChecked())
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
                success = self.p_edited.update_strategy(strategy_dict)
            else:
                success = self.p_edited.save_strategy(strategy_dict)
                self.ui_editor.Strategy.insertItem(0, name)
                idx = len(self.p_edited.get_playable_strategy_list())
                self.ui_editor.Strategy.setCurrentIndex(0)
                self.ui.comboBox_current_strategy.insertItem(0, name)
            msg = QMessageBox()
            # msg.setIcon(QMessageBox.information())
            if success:
                msg.setText("Saved")
            else:
                msg.setText("To save strategies you need to purchase a subscription")
                open_payment_link()
            msg.setWindowTitle("Strategy editor")
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            retval = msg.exec()
            self.logger.info("Strategy saved successfully")

        else:
            msg = QMessageBox()
            msg.setText("There has been a problem and the strategy is not saved. Check if the name is already taken.")
            msg.setWindowTitle("Strategy editor")
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            retval = msg.exec()
            self.logger.warning("Strategy not saved")

    def recommendation_pop_up(self, mouse_target):
            msg = QMessageBox()
            msg.setText(f"Execute the {mouse_target} and then press OK to continue")
            msg.setWindowTitle(f"Recommendation: {mouse_target}")
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            retval = msg.exec()