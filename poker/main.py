#!/usr/bin/env python

import matplotlib
import pandas as pd
import time
import numpy as np

matplotlib.use('Qt5Agg')
import os
# os.environ['KERAS_BACKEND']='theano'
import logging.handlers
import pytesseract
import threading
import datetime
import sys

# if main.py is called manually, set poker folder as root package
sys.path.insert(0, os.path.abspath('..'))
from PIL import Image
from PyQt5 import QtWidgets, QtGui
from configobj import ConfigObj
from poker.gui.gui_qt_ui import Ui_Pokerbot
from poker.gui.gui_qt_logic import UIActionAndSignals
from poker.tools.mongo_manager import StrategyHandler, UpdateChecker, GameLogger
from poker.table_analysers.table_screen_based import TableScreenBased
from poker.decisionmaker.current_hand_memory import History, CurrentHandPreflopState
from poker.decisionmaker.montecarlo_python import run_montecarlo_wrapper
from poker.decisionmaker.decisionmaker import Decision
from poker.tools.mouse_mover import MouseMoverTableBased


version = 3.05




class ThreadManager(threading.Thread):
    def __init__(self, threadID, name, counter, gui_signals):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.counter = counter
        self.gui_signals = gui_signals
        self.logger = logging.getLogger('main')
        self.logger.setLevel(logging.DEBUG)

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
            sheet_name=preflop_state.preflop_sheet_name

        gui_signals.signal_label_number_update.emit('equity', str(np.round(t.abs_equity * 100, 2)) + "%")
        gui_signals.signal_label_number_update.emit('required_minbet', str(np.round(t.minBet,2)))
        gui_signals.signal_label_number_update.emit('required_mincall', str(np.round(t.minCall,2)))
        # gui_signals.signal_lcd_number_update.emit('potsize', t.totalPotValue)
        gui_signals.signal_label_number_update.emit('gamenumber',
                                                    str(int(self.game_logger.get_game_count(p.current_strategy))))
        gui_signals.signal_label_number_update.emit('assumed_players', str(int(t.assumedPlayers)))
        gui_signals.signal_label_number_update.emit('calllimit', str(np.round(d.finalCallLimit,2)))
        gui_signals.signal_label_number_update.emit('betlimit', str(np.round(d.finalBetLimit,2)))
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
        gui_signals.signal_label_number_update.emit('round_pot', str(np.round(t.round_pot_value,2)))
        gui_signals.signal_label_number_update.emit('pot_multiple', str(np.round(d.pot_multiple,2)))

        if t.gameStage != 'PreFlop' and p.selected_strategy['use_relative_equity']:
            gui_signals.signal_label_number_update.emit('relative_equity', str(np.round(t.relative_equity,2) * 100) + "%")
            gui_signals.signal_label_number_update.emit('range_equity', str(np.round(t.range_equity,2) * 100) + "%")
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
                                                    t.maxValue_call,t.maxValue_bet,
                                                    t.maxEquityCall, t.max_X, t.maxEquityBet)

    def run(self):
        h = History()
        preflop_url, preflop_url_backup = u.get_preflop_sheet_url()
        try:
            h.preflop_sheet = pd.read_excel(preflop_url, sheet_name=None)
        except:
            h.preflop_sheet = pd.read_excel(preflop_url_backup, sheet_name=None)

        self.game_logger.clean_database()

        p = StrategyHandler()
        p.read_strategy()

        preflop_state = CurrentHandPreflopState()

        while True:
            if self.gui_signals.pause_thread:
                while self.gui_signals.pause_thread == True:
                    time.sleep(1)
                    if self.gui_signals.exit_thread == True: sys.exit()

            ready = False
            while (not ready):
                p.read_strategy()
                t = TableScreenBased(p, gui_signals, self.game_logger, version)
                mouse = MouseMoverTableBased(p.selected_strategy['pokerSite'])
                mouse.move_mouse_away_from_buttons_jump

                ready = t.take_screenshot(True, p) and \
                        t.get_top_left_corner(p) and \
                        t.check_for_captcha(mouse) and \
                        t.get_lost_everything(h, t, p, gui_signals) and \
                        t.check_for_imback(mouse) and \
                        t.get_my_cards(h) and \
                        t.get_new_hand(mouse, h, p) and \
                        t.get_table_cards(h) and \
                        t.upload_collusion_wrapper(p, h) and \
                        t.get_dealer_position() and \
                        t.get_snowie_advice(p, h) and \
                        t.check_fast_fold(h, p, mouse) and \
                        t.check_for_button() and \
                        t.get_round_number(h) and \
                        t.init_get_other_players_info() and \
                        t.get_other_player_names(p) and \
                        t.get_other_player_funds(p) and \
                        t.get_other_player_pots() and \
                        t.get_total_pot_value(h) and \
                        t.get_round_pot_value(h) and \
                        t.check_for_checkbutton() and \
                        t.get_other_player_status(p, h) and \
                        t.check_for_call() and \
                        t.check_for_betbutton() and \
                        t.check_for_allincall() and \
                        t.get_current_call_value(p) and \
                        t.get_current_bet_value(p)

            if not self.gui_signals.pause_thread:
                config = ConfigObj("config.ini")
                m = run_montecarlo_wrapper(p, self.gui_signals, config, ui, t, self.game_logger, preflop_state, h)
                d = Decision(t, h, p, self.game_logger)
                d.make_decision(t, h, p, self.logger, self.game_logger)
                if self.gui_signals.exit_thread: sys.exit()

                self.update_most_gui_items(preflop_state, p, m, t, d, h, self.gui_signals)

                self.logger.info(
                    "Equity: " + str(t.equity * 100) + "% -> " + str(int(t.assumedPlayers)) + " (" + str(
                        int(t.other_active_players)) + "-" + str(int(t.playersAhead)) + "+1) Plr")
                self.logger.info("Final Call Limit: " + str(d.finalCallLimit) + " --> " + str(t.minCall))
                self.logger.info("Final Bet Limit: " + str(d.finalBetLimit) + " --> " + str(t.minBet))
                self.logger.info(
                    "Pot size: " + str((t.totalPotValue)) + " -> Zero EV Call: " + str(round(d.maxCallEV, 2)))
                self.logger.info("+++++++++++++++++++++++ Decision: " + str(d.decision) + "+++++++++++++++++++++++")

                mouse_target = d.decision
                if mouse_target == 'Call' and t.allInCallButton:
                    mouse_target = 'Call2'
                mouse.mouse_action(mouse_target, t.tlc)

                t.time_action_completed = datetime.datetime.utcnow()

                filename = str(h.GameID) + "_" + str(t.gameStage) + "_" + str(h.round_number) + ".png"
                self.logger.debug("Saving screenshot: " + filename)
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
                h.previous_round_pot_value=t.round_pot_value
                h.last_round_bluff = False if t.currentBluff == 0 else True
                if t.gameStage == 'PreFlop':
                    preflop_state.update_values(t, d.decision, h, d)
                self.logger.info("=========== round end ===========")


# ==== MAIN PROGRAM =====

def run_poker():
    fh = logging.handlers.RotatingFileHandler('log/pokerprogram.log', maxBytes=1000000, backupCount=10)
    fh.setLevel(logging.DEBUG)
    fh2 = logging.handlers.RotatingFileHandler('log/pokerprogram_info_only.log', maxBytes=1000000, backupCount=5)
    fh2.setLevel(logging.INFO)
    er = logging.handlers.RotatingFileHandler('log/errors.log', maxBytes=2000000, backupCount=2)
    er.setLevel(logging.WARNING)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARNING)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    fh2.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    er.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    ch.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))

    root = logging.getLogger()
    root.addHandler(fh)
    root.addHandler(fh2)
    root.addHandler(ch)
    root.addHandler(er)

    print(
        "This is a testversion and error messages will appear here. The user interface has opened in a separate window.")
    # Back up the reference to the exceptionhook
    sys._excepthook = sys.excepthook
    global u
    u = UpdateChecker()
    u.check_update(version)


    def exception_hook(exctype, value, traceback):
        # Print the error and traceback
        logger = logging.getLogger('main')
        logger.setLevel(logging.DEBUG)
        print(exctype, value, traceback)
        logger.error(str(exctype))
        logger.error(str(value))
        logger.error(str(traceback))
        # Call the normal Exception hook after
        sys.__excepthook__(exctype, value, traceback)
        sys.exit(1)


    # Set the exception hook to our wrapping function
    sys.__excepthook__ = exception_hook

    # check for tesseract
    try:
        pytesseract.image_to_string(Image.open('pics/PP/call.png'))
    except Exception as e:
        print(e)
        print(
            "Tesseract not installed. Please install it into the same folder as the pokerbot or alternatively set the path variable.")
        # subprocess.call(["start", 'tesseract-installer/tesseract-ocr-setup-3.05.00dev.exe'], shell=True)
        sys.exit()

    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()

    global ui
    ui= Ui_Pokerbot()
    ui.setupUi(MainWindow)
    MainWindow.setWindowIcon(QtGui.QIcon('icon.ico'))

    global gui_signals
    gui_signals = UIActionAndSignals(ui)

    t1 = ThreadManager(1, "Thread-1", 1, gui_signals)
    t1.start()

    MainWindow.show()
    try:
        sys.exit(app.exec_())
    except:
        print("Preparing to exit...")
        gui_signals.exit_thread = True


    pass

if __name__ == '__main__':
    run_poker()