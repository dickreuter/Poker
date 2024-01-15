import datetime
import logging.handlers
import sys
import threading
import time
import warnings
from sys import platform

import matplotlib
import numpy as np
import pandas as pd
from PyQt6 import QtGui, QtWidgets

from poker.restapi_local import local_restapi
from poker.tools import constants as const

if platform not in ["linux", "linux2"]:
    matplotlib.use('Qt5Agg')

from poker.decisionmaker.current_hand_memory import (CurrentHandPreflopState,
                                                     History)
from poker.decisionmaker.decisionmaker import Decision
from poker.decisionmaker.montecarlo_python import run_montecarlo_wrapper
from poker.gui.action_and_signals import StrategyHandler, UIActionAndSignals
from poker.gui.gui_launcher import UiPokerbot
from poker.scraper.table_screen_based import TableScreenBased
from poker.tools.game_logger import GameLogger
from poker.tools.helper import init_logger, get_config, get_dir
from poker.tools.mongo_manager import MongoManager
from poker.tools.mouse_mover import MouseMoverTableBased
from poker.tools.update_checker import UpdateChecker

# pylint: disable=no-member,simplifiable-if-expression,protected-access,line-too-long,use-fstring-for-concatenation,refactoring:missing-module-dosctring,

warnings.filterwarnings("ignore", category=matplotlib.MatplotlibDeprecationWarning)
warnings.filterwarnings("ignore", message="ignoring `maxfev` argument to `Minimizer()`. Use `max_nfev` instead.")
warnings.filterwarnings("ignore", message="DataFrame columns are not unique, some columns will be omitted.")
warnings.filterwarnings("ignore", message="All-NaN axis encountered")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

version = 6.76
ui = None


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
            _range = t.reverse_sheet_name
            if hasattr(preflop_state, 'range_column_name'):
                range2 = " " + preflop_state.range_column_name + ""

        else:
            _range = str(m.opponent_range)
        if _range == '1':
            _range = 'All cards'

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
        gui_signals.signal_label_number_update.emit('opponent_range', str(_range) + str(range2))
        gui_signals.signal_label_number_update.emit('mincallequity', str(np.round(t.minEquityCall*100, 2)) + "%")
        gui_signals.signal_label_number_update.emit('minbetequity', str(np.round(t.minEquityBet*100, 2)) + "%")
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
        history = History()
        preflop_url, preflop_url_backup = self.updater.get_preflop_sheet_url()
        try:
            history.preflop_sheet = pd.read_excel(preflop_url, sheet_name=None, engine='openpyxl')
        except:
            history.preflop_sheet = pd.read_excel(preflop_url_backup, sheet_name=None, engine='openpyxl')


        strategy = StrategyHandler()
        strategy.read_strategy()

        preflop_state = CurrentHandPreflopState()
        mongo = MongoManager()
        table_scraper_name = None

        while True:
            # reload table if changed

            if self.gui_signals.pause_thread:
                while self.gui_signals.pause_thread:
                    time.sleep(0.5)
                    if self.gui_signals.exit_thread:
                        sys.exit()

            ready = False
            while not ready:
                config = get_config()
                if table_scraper_name != config.config.get('main','table_scraper_name'):
                    table_scraper_name = config.config.get('main','table_scraper_name')
                    log.info(f"Loading table scraper info for {table_scraper_name}")
                    table_dict = mongo.get_table(table_scraper_name)
                    nn_model = None
                    slow_table = False
                    if 'use_neural_network' in table_dict and (table_dict['use_neural_network'] == '2' or table_dict['use_neural_network'] == 'CheckState.Checked'):
                        from tensorflow.keras.models import model_from_json
                        try:
                            nn_model = model_from_json(table_dict['_model'])
                        except KeyError:
                            raise Exception("This table does not have a neural network model. Please train one first or untick neural network for this table.")
                            
                        mongo.load_table_nn_weights(table_scraper_name)
                        nn_model.load_weights(get_dir('codebase') + '/loaded_model.h5')
                        slow_table = True

                table = TableScreenBased(strategy, table_dict, self.gui_signals, self.game_logger, version, nn_model)
                mouse = MouseMoverTableBased(table_dict)
                mouse.move_mouse_away_from_buttons_jump()

                ready = table.take_screenshot(True, strategy) and \
                        table.get_top_left_corner(strategy) and \
                        table.check_for_captcha(mouse) and \
                        table.get_lost_everything(history, table, strategy, self.gui_signals) and \
                        table.check_for_imback(mouse) and \
                        table.check_for_resume_hand(mouse) and \
                        table.check_for_button_if_slow_table(slow_table) and \
                        table.get_my_cards() and \
                        table.get_new_hand(mouse, history, strategy) and \
                        table.get_table_cards(history) and \
                        table.upload_collusion_wrapper(strategy, history) and \
                        table.get_dealer_position() and \
                        table.check_fast_fold(history, strategy, mouse) and \
                        table.check_for_button() and \
                        strategy.read_strategy() and \
                        table.get_round_number(history) and \
                        table.check_for_checkbutton() and \
                        table.init_get_other_players_info() and \
                        table.get_other_player_status(strategy, history) and \
                        table.get_other_player_names(strategy) and \
                        table.get_other_player_funds(strategy) and \
                        table.get_total_pot_value(history) and \
                        table.get_round_pot_value(history) and \
                        table.check_for_call() and \
                        table.check_for_betbutton() and \
                        table.check_for_allincall() and \
                        table.get_current_call_value(strategy) and \
                        table.get_current_bet_value(strategy)

            if not self.gui_signals.pause_thread:
                config = get_config()
                m = run_montecarlo_wrapper(strategy, self.gui_signals, config, ui, table, self.game_logger,
                                           preflop_state, history)
                self.gui_signals.signal_progressbar_increase.emit(20)
                d = Decision(table, history, strategy, self.game_logger)
                d.make_decision(table, history, strategy, self.game_logger)
                self.gui_signals.signal_progressbar_increase.emit(10)
                if self.gui_signals.exit_thread: sys.exit()

                self.update_most_gui_items(preflop_state, strategy, m, table, d, history, self.gui_signals)

                log.info(
                    "Equity: " + str(table.equity * 100) + "% -> " + str(int(table.assumedPlayers)) + " (" + str(
                        int(table.other_active_players)) + "-" + str(int(table.playersAhead)) + "+1) Plr")
                log.info("Final Call Limit: " + str(d.finalCallLimit) + " --> " + str(table.minCall))
                log.info("Final Bet Limit: " + str(d.finalBetLimit) + " --> " + str(table.minBet))
                log.info(
                    "Pot size: " + str(table.totalPotValue) + " -> Zero EV Call: " + str(round(d.maxCallEV, 2)))
                log.info("+++++++++++++++++++++++ Decision: " + str(d.decision) + "+++++++++++++++++++++++")

                mouse_target = d.decision
                action_options = {}

                if mouse_target == 'Call' and table.allInCallButton:
                    mouse_target = 'Call2'
                elif mouse_target == 'BetPlus':
                    action_options['increases_num'] = strategy.selected_strategy['BetPlusInc']

                if self.gui_signals.ui.auto_act.isChecked():
                    mouse.mouse_action(mouse_target, table.tlc, action_options)
                else:
                    input("=== Press Enter to continue ===")
                    

                # for pokerstars, high fold straight after all in call (fold button matches the stay in game)
                # if mouse_target == 'Call2' and table.allInCallButton:
                #     mouse_target = 'Fold'
                #     mouse.mouse_action(mouse_target, table.tlc, action_options)

                table.time_action_completed = datetime.datetime.utcnow()

                filename = str(history.GameID) + "_" + str(table.gameStage) + "_" + str(history.round_number) + ".png"
                log.debug("Saving screenshot: " + filename)
                pil_image = table.crop_image(table.entireScreenPIL, table.tlc[0], table.tlc[1], table.tlc[0] + const.CROP_WIDTH,
                                             table.tlc[1] + const.CROP_HEIGHT)
                pil_image.save("log/screenshots/" + filename)

                self.gui_signals.signal_status.emit("Logging data")

                t_log_db = threading.Thread(name='t_log_db', target=self.game_logger.write_log_file,
                                            args=[strategy, history, table, d])
                t_log_db.daemon = True
                t_log_db.start()
                # self.game_logger.write_log_file(strategy, history, table, d)

                history.previousPot = table.totalPotValue
                history.histGameStage = table.gameStage
                history.histDecision = d.decision
                history.histEquity = table.equity
                history.histMinCall = table.minCall
                history.histMinBet = table.minBet
                history.hist_other_players = table.other_players
                history.first_raiser = table.first_raiser
                history.first_caller = table.first_caller
                history.previous_decision = d.decision
                history.lastRoundGameID = history.GameID
                history.previous_round_pot_value = table.round_pot_value
                history.last_round_bluff = False if table.currentBluff == 0 else True
                if table.gameStage == 'PreFlop':
                    preflop_state.update_values(table, d.decision, history, d)
                mongo.increment_plays(table_scraper_name)
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
    global ui  # pylint: disable=global-statement
    ui = UiPokerbot()
    ui.setWindowIcon(QtGui.QIcon('gui/ui/icon.ico'))

    gui_signals = UIActionAndSignals(ui)

    t1 = ThreadManager(1, "Thread-1", 1, gui_signals, updater)
    t1.start()
    
    t2 = threading.Thread(target=local_restapi)
    t2.daemon = True
    t2.start()

    try:
        sys.exit(app.exec())
    except:
        print("Preparing to exit...")
        gui_signals.exit_thread = True


if __name__ == '__main__':
    run_poker()
