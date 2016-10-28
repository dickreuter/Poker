import matplotlib
matplotlib.use('Qt5Agg')
import pytesseract
import threading
import datetime
import sys
from PIL import Image
from PyQt5 import QtWidgets,QtGui

from decisionmaker.decisionmaker import *
from tools.mouse_mover import *
from gui.gui_qt_ui import Ui_Pokerbot
from gui.gui_qt_logic import UIActionAndSignals
from tools.mongo_manager import StrategyHandler,UpdateChecker,GameLogger
from table_analysers.table_screen_based import TableScreenBased
from decisionmaker.current_hand_memory import History, CurrentHandPreflopState

version = 1.921


class ThreadManager(threading.Thread):
    def __init__(self, threadID, name, counter, gui_signals):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.counter = counter
        self.gui_signals = gui_signals
        self.logger = debug_logger().start_logger('main')
        self.game_logger = GameLogger()

    def update_most_gui_items(self, p, t, d, h, gui_signals):
        gui_signals.signal_decision.emit(str(d.decision + " " + d.preflop_sheet_name))
        gui_signals.signal_status.emit(d.decision)

        gui_signals.signal_lcd_number_update.emit('equity', np.round(t.equity * 100, 2))
        gui_signals.signal_lcd_number_update.emit('required_minbet', t.currentBetValue)
        gui_signals.signal_lcd_number_update.emit('required_mincall', t.minCall)
        # gui_signals.signal_lcd_number_update.emit('potsize', t.totalPotValue)
        gui_signals.signal_lcd_number_update.emit('gamenumber',
                                                  int(self.game_logger.get_game_count(p.current_strategy)))
        gui_signals.signal_lcd_number_update.emit('assumed_players', int(t.assumedPlayers))
        gui_signals.signal_lcd_number_update.emit('calllimit', d.finalCallLimit)
        gui_signals.signal_lcd_number_update.emit('betlimit', d.finalBetLimit)
        # gui_signals.signa.l_lcd_number_update.emit('zero_ev', round(d.maxCallEV, 2))

        gui_signals.signal_pie_chart_update.emit(t.winnerCardTypeList)
        gui_signals.signal_curve_chart_update1.emit(h.histEquity, h.histMinCall, h.histMinBet, t.equity,
                                                    t.minCall, t.minBet,
                                                    'bo',
                                                    'ro')

        gui_signals.signal_curve_chart_update2.emit(t.power1, t.power2, t.minEquityCall, t.minEquityBet,
                                                    t.smallBlind, t.bigBlind,
                                                    t.maxValue,
                                                    t.maxEquityCall, t.max_X, t.maxEquityBet)

    def run(self):
        h = History()
        preflop_url = u.get_preflop_sheet_url()
        h.preflop_sheet = pd.read_excel(preflop_url, sheetname=None)

        self.game_logger.clean_database()

        p = StrategyHandler()
        p.read_strategy()

        preflop_state=CurrentHandPreflopState()

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

                ready = t.take_screenshot(True, p) and \
                        t.get_top_left_corner(p) and \
                        t.check_for_captcha(mouse) and \
                        t.get_lost_everything(h, t, p) and \
                        t.check_for_imback(mouse) and \
                        t.get_my_funds(h, p) and \
                        t.get_my_cards(h) and \
                        t.get_new_hand(mouse, h, p) and \
                        t.get_table_cards(h) and \
                        t.upload_collusion_wrapper(p, h) and \
                        t.get_dealer_position() and \
                        t.get_snowie_advice(p, h) and \
                        t.check_fast_fold(h, p) and \
                        t.check_for_button() and \
                        t.get_round_number(h) and \
                        t.init_get_other_players_info() and \
                        t.get_other_player_names(p) and \
                        t.get_other_player_funds(p) and \
                        t.get_other_player_pots() and \
                        t.get_total_pot_value(h) and \
                        t.check_for_checkbutton() and \
                        t.get_other_player_status(p, h) and \
                        t.check_for_call() and \
                        t.check_for_betbutton() and \
                        t.check_for_allincall() and \
                        t.get_current_call_value(p) and \
                        t.get_current_bet_value(p)

            if not self.gui_signals.pause_thread:
                config = ConfigObj("config.ini")
                run_montecarlo_wrapper(p, self.gui_signals, config, ui, t, self.game_logger, preflop_state, h)
                d = Decision(t, h, p, self.logger, self.game_logger)
                d.make_decision(t, h, p, self.logger, self.game_logger)
                if self.gui_signals.exit_thread: sys.exit()

                self.update_most_gui_items(p, t, d, h, self.gui_signals)

                self.logger.info(
                    "Equity: " + str(t.equity * 100) + "% -> " + str(int(t.assumedPlayers)) + " (" + str(
                        int(t.other_active_players)) + "-" + str(int(t.playersAhead)) + "+1) Plr")
                self.logger.info("Final Call Limit: " + str(d.finalCallLimit) + " --> " + str(t.minCall))
                self.logger.info("Final Bet Limit: " + str(d.finalBetLimit) + " --> " + str(t.currentBetValue))
                self.logger.info(
                    "Pot size: " + str((t.totalPotValue)) + " -> Zero EV Call: " + str(round(d.maxCallEV, 2)))
                self.logger.info("+++++++++++++++++++++++ Decision: " + str(d.decision) + "+++++++++++++++++++++++")

                mouse = MouseMoverTableBased(p.selected_strategy['pokerSite'],
                                             p.selected_strategy['BetPlusInc'], t.currentBluff)
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

                # t_log_db = threading.Thread(name='t_log_db', target=self.game_loggerwrite_log_file,args=[p, h, t, d])
                # t_log_db.daemon = True
                # t_log_db.start()
                self.game_logger.write_log_file(p, h, t, d)

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
                h.last_round_bluff = False if t.currentBluff == 0 else True
                if t.gameStage=='PreFlop':
                    preflop_state.update_values(t,d.decision,h)
                self.logger.info("=========== round end ===========")

# ==== MAIN PROGRAM =====
if __name__ == '__main__':
    print(
        "This is a testversion and error messages will appear here. The user interface has opened in a separate window.")
    # Back up the reference to the exceptionhook
    sys._excepthook = sys.excepthook
    u = UpdateChecker()
    u.check_update(version)


    def my_exception_hook(exctype, value, traceback):
        # Print the error and traceback
        print(exctype, value, traceback)
        logger.error(str(exctype))
        logger.error(str(value))
        logger.error(str(traceback))
        # Call the normal Exception hook after
        sys._excepthook(exctype, value, traceback)
        sys.exit(1)


    # Set the exception hook to our wrapping function
    sys.excepthook = my_exception_hook

    # check for tesseract
    try:
        pytesseract.image_to_string(Image.open('pics/PP/3h.png'))
    except Exception as e:
        print(e)
        print(
            "Tesseract not installed. Please install it into the same folder as the pokerbot or alternatively set the path variable.")
        # subprocess.call(["start", 'tesseract-installer/tesseract-ocr-setup-3.05.00dev.exe'], shell=True)
        sys.exit()

    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()

    ui = Ui_Pokerbot()
    ui.setupUi(MainWindow)
    MainWindow.setWindowIcon(QtGui.QIcon('icon.ico'))

    gui_signals = UIActionAndSignals(ui)

    t1 = ThreadManager(1, "Thread-1", 1, gui_signals)
    t1.start()

    MainWindow.show()
    try:
        sys.exit(app.exec_())
    except:
        print("Preparing to exit...")
        gui_signals.exit_thread = True
