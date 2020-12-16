import time
import warnings
from sys import platform

import matplotlib
import numpy as np
import pandas as pd

from poker.tools.game_logger import GameLogger
from poker.tools.helper import init_logger, CONFIG_FILENAME
from poker.tools.update_checker import UpdateChecker

if not (platform == "linux" or platform == "linux2"):
    matplotlib.use('Qt5Agg')

import logging.handlers
import threading
import datetime
import sys
from PyQt5 import QtWidgets, QtGui
from configobj import ConfigObj
from poker.gui.gui_qt_ui import Ui_Pokerbot
from poker.gui.gui_qt_logic import UIActionAndSignals, StrategyHandler
from poker.tools.mongo_manager import MongoManager
from poker.table_analysers.table_screen_based import TableScreenBased
from poker.decisionmaker.current_hand_memory import History, CurrentHandPreflopState
from poker.decisionmaker.montecarlo_python import run_montecarlo_wrapper
from poker.decisionmaker.decisionmaker import Decision
from poker.tools.mouse_mover import MouseMoverTableBased

warnings.filterwarnings("ignore", category=matplotlib.cbook.mplDeprecation)
warnings.filterwarnings("ignore", message="ignoring `maxfev` argument to `Minimizer()`. Use `max_nfev` instead.")
warnings.filterwarnings("ignore", message="DataFrame columns are not unique, some columns will be omitted.")
warnings.filterwarnings("ignore", message="All-NaN axis encountered")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

version = 4.21


class ThreadManager(threading.Thread):
    def __init__(self, threadID, name, counter, gui_signals, updater):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.gui_signals = gui_signals
        self.updater = updater
        self.name = name
        self.counter = counter
        self.loger = logging.getLogger('main')

        self.game_logger = GameLogger()

    def update_most_gui_items(self, preflop_state, p, m, t, d, h, gui_signals):
        try:
            sheet_name = t.preflop_sheet_name
        except:
            sheet_name = ''
        gui_signals.signal_decision.emit(str(d.decision + " " + sheet_name))
        gui_signals.signal_status.emit(d.decision)
        range2 = ''
        if hasattr(t, 'reverse_sheet_name'):
            range = t.reverse_sheet_name
            if hasattr(preflop_state, 'range_column_name'):
                range2 = " " + preflop_state.range_column_name + ""

        else:
            range = str(m.opponent_range)
        if range == '1': range = 'All cards'

        if t.gameStage != 'PreFlop' and p.selected_strategy['preflop_override']:
            sheet_name = preflop_state.preflop_sheet_name

        gui_signals.signal_label_number_update.emit('equity', str(np.round(t.abs_equity * 100, 2)) + "%")
        gui_signals.signal_label_number_update.emit('required_minbet', str(np.round(t.minBet, 2)))
        gui_signals.signal_label_number_update.emit('required_mincall', str(np.round(t.minCall, 2)))
        # gui_signals.signal_lcd_number_update.emit('potsize', t.totalPotValue)
        gui_signals.signal_label_number_update.emit('gamenumber',
                                                    str(int(self.game_logger.get_game_count(p.current_strategy))))
        gui_signals.signal_label_number_update.emit('assumed_players', str(int(t.assumedPlayers)))
        gui_signals.signal_label_number_update.emit('calllimit', str(np.round(d.finalCallLimit, 2)))
        gui_signals.signal_label_number_update.emit('betlimit', str(np.round(d.finalBetLimit, 2)))
        gui_signals.signal_label_number_update.emit('runs', str(int(m.runs)))
        gui_signals.signal_label_number_update.emit('sheetname', sheet_name)
        gui_signals.signal_label_number_update.emit('collusion_cards', str(m.collusion_cards))
        gui_signals.signal_label_number_update.emit('mycards', str(t.mycards))
        gui_signals.signal_label_number_update.emit('tablecards', str(t.cardsOnTable))
        gui_signals.signal_label_number_update.emit('opponent_range', str(range) + str(range2))
        gui_signals.signal_label_number_update.emit('mincallequity', str(np.round(t.minEquityCall, 2) * 100) + "%")
        gui_signals.signal_label_number_update.emit('minbetequity', str(np.round(t.minEquityBet, 2) * 100) + "%")
        gui_signals.signal_label_number_update.emit('outs', str(d.outs))
        gui_signals.signal_label_number_update.emit('initiative', str(t.other_player_has_initiative))
        gui_signals.signal_label_number_update.emit('round_pot', str(np.round(t.round_pot_value, 2)))
        gui_signals.signal_label_number_update.emit('pot_multiple', str(np.round(d.pot_multiple, 2)))

        if t.gameStage != 'PreFlop' and p.selected_strategy['use_relative_equity']:
            gui_signals.signal_label_number_update.emit('relative_equity',
                                                        str(np.round(t.relative_equity, 2) * 100) + "%")
            gui_signals.signal_label_number_update.emit('range_equity', str(np.round(t.range_equity, 2) * 100) + "%")
        else:
            gui_signals.signal_label_number_update.emit('relative_equity', "")
            gui_signals.signal_label_number_update.emit('range_equity', "")

        # gui_signals.signal_lcd_number_update.emit('zero_ev', round(d.maxCallEV, 2))

        gui_signals.signal_pie_chart_update.emit(t.winnerCardTypeList)
        gui_signals.signal_curve_chart_update1.emit(h.histEquity, h.histMinCall, h.histMinBet, t.equity,
                                                    t.minCall, t.minBet,
                                                    'bo',
                                                    'ro')

        gui_signals.signal_curve_chart_update2.emit(t.power1, t.power2, t.minEquityCall, t.minEquityBet,
                                                    t.smallBlind, t.bigBlind,
                                                    t.maxValue_call, t.maxValue_bet,
                                                    t.maxEquityCall, t.max_X, t.maxEquityBet)

    def run(self):
        log = logging.getLogger(__name__)
        h = History()
        preflop_url, preflop_url_backup = self.updater.get_preflop_sheet_url()
        try:
            h.preflop_sheet = pd.read_excel(preflop_url, sheet_name=None, engine='openpyxl')
        except:
            h.preflop_sheet = pd.read_excel(preflop_url_backup, sheet_name=None, engine='openpyxl')

        self.game_logger.clean_database()

        p = StrategyHandler()
        p.read_strategy()

        preflop_state = CurrentHandPreflopState()
        mongo = MongoManager()
        table_scraper_name = None

        while True:
            # reload table if changed
            config = ConfigObj(CONFIG_FILENAME)
            if table_scraper_name != config['table_scraper_name']:
                table_scraper_name = config['table_scraper_name']
                log.info(f"Loading table scraper info for {table_scraper_name}")
                table_dict = mongo.get_table(table_scraper_name)

            if self.gui_signals.pause_thread:
                while self.gui_signals.pause_thread:
                    time.sleep(0.5)
                    if self.gui_signals.exit_thread:
                        sys.exit()

            ready = False
            while not ready:
                p.read_strategy()
                t = TableScreenBased(p, table_dict, self.gui_signals, self.game_logger, version)
                mouse = MouseMoverTableBased(table_dict)
                mouse.move_mouse_away_from_buttons_jump()

                ready = t.take_screenshot(True, p) and \
                        t.get_top_left_corner(p) and \
                        t.check_for_captcha(mouse) and \
                        t.get_lost_everything(h, t, p, self.gui_signals) and \
                        t.check_for_imback(mouse) and \
                        t.get_my_cards(h) and \
                        t.get_new_hand(mouse, h, p) and \
                        t.get_table_cards(h) and \
                        t.upload_collusion_wrapper(p, h) and \
                        t.get_dealer_position() and \
                        t.check_fast_fold(h, p, mouse) and \
                        t.check_for_button() and \
                        t.get_round_number(h) and \
                        t.check_for_checkbutton() and \
                        t.init_get_other_players_info() and \
                        t.get_other_player_status(p, h) and \
                        t.get_other_player_names(p) and \
                        t.get_other_player_funds(p) and \
                        t.get_other_player_pots() and \
                        t.get_total_pot_value(h) and \
                        t.get_round_pot_value(h) and \
                        t.check_for_call() and \
                        t.check_for_betbutton() and \
                        t.check_for_allincall() and \
                        t.get_current_call_value(p) and \
                        t.get_current_bet_value(p)

            if not self.gui_signals.pause_thread:
                config = ConfigObj(CONFIG_FILENAME)
                m = run_montecarlo_wrapper(p, self.gui_signals, config, ui, t, self.game_logger, preflop_state, h)
                self.gui_signals.signal_progressbar_increase.emit(20)
                d = Decision(t, h, p, self.game_logger)
                d.make_decision(t, h, p, self.game_logger)
                self.gui_signals.signal_progressbar_increase.emit(10)
                if self.gui_signals.exit_thread: sys.exit()

                self.update_most_gui_items(preflop_state, p, m, t, d, h, self.gui_signals)

                log.info(
                    "Equity: " + str(t.equity * 100) + "% -> " + str(int(t.assumedPlayers)) + " (" + str(
                        int(t.other_active_players)) + "-" + str(int(t.playersAhead)) + "+1) Plr")
                log.info("Final Call Limit: " + str(d.finalCallLimit) + " --> " + str(t.minCall))
                log.info("Final Bet Limit: " + str(d.finalBetLimit) + " --> " + str(t.minBet))
                log.info(
                    "Pot size: " + str((t.totalPotValue)) + " -> Zero EV Call: " + str(round(d.maxCallEV, 2)))
                log.info("+++++++++++++++++++++++ Decision: " + str(d.decision) + "+++++++++++++++++++++++")

                mouse_target = d.decision
                if mouse_target == 'Call' and t.allInCallButton:
                    mouse_target = 'Call2'
                mouse.mouse_action(mouse_target, t.tlc)

                t.time_action_completed = datetime.datetime.utcnow()

                filename = str(h.GameID) + "_" + str(t.gameStage) + "_" + str(h.round_number) + ".png"
                log.debug("Saving screenshot: " + filename)
                pil_image = t.crop_image(t.entireScreenPIL, t.tlc[0], t.tlc[1], t.tlc[0] + 950, t.tlc[1] + 650)
                pil_image.save("log/screenshots/" + filename)

                self.gui_signals.signal_status.emit("Logging data")

                t_log_db = threading.Thread(name='t_log_db', target=self.game_logger.write_log_file, args=[p, h, t, d])
                t_log_db.daemon = True
                t_log_db.start()
                # self.game_logger.write_log_file(p, h, t, d)

                h.previousPot = t.totalPotValue
                h.histGameStage = t.gameStage
                h.histDecision = d.decision
                h.histEquity = t.equity
                h.histMinCall = t.minCall
                h.histMinBet = t.minBet
                h.hist_other_players = t.other_players
                h.first_raiser = t.first_raiser
                h.first_caller = t.first_caller
                h.previous_decision = d.decision
                h.lastRoundGameID = h.GameID
                h.previous_round_pot_value = t.round_pot_value
                h.last_round_bluff = False if t.currentBluff == 0 else True
                if t.gameStage == 'PreFlop':
                    preflop_state.update_values(t, d.decision, h, d)
                log.info("=========== round end ===========")


# ==== MAIN PROGRAM =====

def run_poker():
    init_logger(screenlevel=logging.INFO, filename='deepmind_pokerbot', logdir='log')
    # print(f"Screenloglevel: {screenloglevel}")
    log = logging.getLogger("")
    log.info("Initializing program")

    # Back up the reference to the exceptionhook
    sys._excepthook = sys.excepthook
    log.info("Check for auto-update")
    updater = UpdateChecker()
    updater.check_update(version)
    log.info(f"Lastest version already installed: {version}")

    def exception_hook(exctype, value, traceback):
        # Print the error and traceback
        logger = logging.getLogger('main')
        print(exctype, value, traceback)
        logger.error(str(exctype))
        logger.error(str(value))
        logger.error(str(traceback))
        # Call the normal Exception hook after
        sys.__excepthook__(exctype, value, traceback)
        sys.exit(1)

    # Set the exception hook to our wrapping function
    sys.__excepthook__ = exception_hook

    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    global ui
    ui = Ui_Pokerbot()
    ui.setupUi(MainWindow)
    MainWindow.setWindowIcon(QtGui.QIcon('icon.ico'))

    gui_signals = UIActionAndSignals(ui)

    t1 = ThreadManager(1, "Thread-1", 1, gui_signals, updater)
    t1.start()

    MainWindow.show()
    try:
        sys.exit(app.exec_())
    except:
        print("Preparing to exit...")
        gui_signals.exit_thread = True


if __name__ == '__main__':
    run_poker()
