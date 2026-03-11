"""
CLI Controller for Poker Bot - Headless Operation

This module allows Claude (or any script) to control the poker bot
without needing the GUI. It provides:
- start() - Start the bot
- stop() - Stop the bot
- status() - Get current bot status
- run_single_hand() - Process one hand and stop

Usage:
    from gamble.tools.cli_controller import BotController

    bot = BotController()
    bot.start()  # Start bot in background
    bot.status()  # Check what's happening
    bot.stop()  # Stop the bot
"""

import datetime
import logging
import logging.handlers
import sys
import threading
import time
import warnings
from sys import platform

import numpy as np
import pandas as pd

# Set up matplotlib backend before importing
import matplotlib
if platform not in ["linux", "linux2"]:
    matplotlib.use('Agg')  # Use non-GUI backend for headless operation

from gamble.decisionmaker.current_hand_memory import CurrentHandPreflopState, History
from gamble.decisionmaker.decisionmaker import Decision
from gamble.decisionmaker.montecarlo_python import run_montecarlo_wrapper
from gamble.gui.action_and_signals import StrategyHandler
from gamble.scraper.table_screen_based import TableScreenBased
from gamble.tools.game_logger import GameLogger
from gamble.tools.helper import init_logger, get_config, get_dir
from gamble.tools.mongo_manager import MongoManager
from gamble.tools.mouse_mover import MouseMoverTableBased
from gamble.tools.keyboard_controller import KeyboardControllerTableBased
from gamble.tools.fast_clicker import FastMouseMover
from gamble.tools.dynamic_mouse_mover import DynamicMouseMover
from gamble.tools.update_checker import UpdateChecker
from gamble.tools import constants as const
from gamble.tools.adaptive_learner import get_learner, log_action, report_issue
from gamble.tools.self_healer import get_healer, heal_buttons, heal_cards, auto_heal, analyze_and_act

# Vision analyzer for REAL self-learning
try:
    from gamble.tools.vision_analyzer import auto_fix_detection, auto_fix_buttons, auto_fix_cards
    VISION_ANALYZER_AVAILABLE = True
except ImportError:
    VISION_ANALYZER_AVAILABLE = False
    log.warning("Vision analyzer not available")

# Input method constants
# Lobby navigation imports
try:
    from gamble.tools.ui_navigator import UINavigator
    UI_NAVIGATOR_AVAILABLE = True
except ImportError:
    UI_NAVIGATOR_AVAILABLE = False

try:
    from gamble.tools.dynamic_lobby_navigator import DynamicLobbyNavigator
    LOBBY_NAV_AVAILABLE = True
except ImportError:
    LOBBY_NAV_AVAILABLE = False
INPUT_MOUSE = 'mouse'
INPUT_KEYBOARD = 'keyboard'
INPUT_FAST = 'fast'  # CGEventPost-based fast clicking
INPUT_DYNAMIC = 'dynamic'  # Color-based button detection (most reliable)

warnings.filterwarnings("ignore")

log = logging.getLogger(__name__)

VERSION = 6.76


class MockAutoAct:
    """Mock checkbox that always returns True for auto-act in CLI mode"""
    def __init__(self, enabled=True):
        self._enabled = enabled

    def isChecked(self):
        return self._enabled

    def setChecked(self, value):
        self._enabled = value


class MockUI:
    """Mock UI object for headless operation"""
    def __init__(self):
        self.auto_act = MockAutoAct(enabled=True)

    def __getattr__(self, name):
        """Return a no-op for any attribute access"""
        return lambda *args, **kwargs: None


class CLISignals:
    """
    Replacement for UIActionAndSignals that works without a GUI.
    Logs events instead of updating GUI widgets.
    """

    def __init__(self, auto_act=True, verbose=True):
        self.pause_thread = True  # Start paused
        self.exit_thread = False
        self.ui = MockUI()
        self.ui.auto_act.setChecked(auto_act)
        self.verbose = verbose
        self.last_decision = None
        self.last_equity = None
        self.last_status = None
        self.hand_count = 0

        # Create mock signals that just log
        self._setup_mock_signals()

    def _setup_mock_signals(self):
        """Create mock signal objects for all signals used by the bot"""
        # Create mock signal emitters for ALL signals from GUI
        self.signal_funds_chart_update = MockSignalEmitter(lambda *args: None)
        self.signal_curve_chart_update1 = MockSignalEmitter(lambda *args: None)
        self.signal_curve_chart_update2 = MockSignalEmitter(lambda *args: None)
        self.signal_pie_chart_update = MockSignalEmitter(lambda *args: None)
        self.signal_bar_chart_update = MockSignalEmitter(lambda *args: None)
        self.signal_update_selected_strategy = MockSignalEmitter(lambda *args: None)
        self.signal_update_strategy_sliders = MockSignalEmitter(lambda *args: None)
        self.signal_progressbar_increase = MockSignalEmitter(lambda *args: None)
        self.signal_progressbar_reset = MockSignalEmitter(lambda *args: None)
        self.signal_status = MockSignalEmitter(lambda *args: None)
        self.signal_decision = MockSignalEmitter(lambda *args: None)
        self.signal_lcd_number_update = MockSignalEmitter(lambda *args: None)
        self.signal_label_number_update = MockSignalEmitter(lambda *args: None)
        self.signal_open_setup = MockSignalEmitter(lambda *args: None)

    def _log(self, msg):
        if self.verbose:
            log.info(f"[CLI] {msg}")

    # Mock signal emit methods - just log the data
    def signal_decision_emit(self, text):
        self.last_decision = text
        self._log(f"Decision: {text}")

    def signal_status_emit(self, text):
        self.last_status = text
        self._log(f"Status: {text}")

    def signal_progressbar_increase_emit(self, value):
        pass  # No progressbar in CLI

    def signal_progressbar_reset_emit(self):
        pass

    def signal_label_number_update_emit(self, label, value):
        if label == 'equity':
            self.last_equity = value
        if self.verbose and label in ['equity', 'mycards', 'tablecards', 'decision']:
            self._log(f"{label}: {value}")

    def signal_lcd_number_update_emit(self, label, value):
        pass

    def signal_pie_chart_update_emit(self, data):
        pass

    def signal_curve_chart_update1_emit(self, *args):
        pass

    def signal_curve_chart_update2_emit(self, *args):
        pass

    def signal_funds_chart_update_emit(self, *args):
        pass


class MockSignalEmitter:
    """Wrapper that makes signal.emit() calls work"""
    def __init__(self, callback):
        self.callback = callback

    def emit(self, *args):
        self.callback(*args)

    def connect(self, *args):
        pass  # No-op for connect


class BotController:
    """
    Main controller for running the poker bot headlessly.

    Usage:
        bot = BotController()
        bot.start()  # Non-blocking, runs in background
        bot.status()
        bot.stop()

    Or for single hand:
        bot.run_single_hand()  # Blocks until hand complete
    """

    def __init__(self, table_name=None, strategy_name=None, auto_act=True, verbose=True, input_method=INPUT_MOUSE):
        """
        Initialize the bot controller.

        Args:
            table_name: Template name (default: from config)
            strategy_name: Strategy name (default: from config)
            auto_act: Whether to automatically click buttons (default: True)
            verbose: Print detailed logs (default: True)
            input_method: 'mouse' for mouse clicks, 'keyboard' for hotkeys (default: mouse)
        """
        self.table_name = table_name
        self.strategy_name = strategy_name
        self.auto_act = auto_act
        self.verbose = verbose
        self.input_method = input_method

        self.signals = None
        self.thread = None
        self.running = False
        self.game_logger = GameLogger()

        # Initialize logging
        init_logger(screenlevel=logging.INFO if verbose else logging.WARNING,
                   filename='dm_assistant', logdir='log')

    def _create_signals(self):
        """Create CLI signals with mock emit methods"""
        self.signals = CLISignals(auto_act=self.auto_act, verbose=self.verbose)

        # Wire up the emit methods so they work like real signals
        class SignalProxy:
            def __init__(self, emit_func):
                self.emit = emit_func
            def connect(self, *args):
                pass

        self.signals.signal_decision = SignalProxy(self.signals.signal_decision_emit)
        self.signals.signal_status = SignalProxy(self.signals.signal_status_emit)
        self.signals.signal_progressbar_increase = SignalProxy(self.signals.signal_progressbar_increase_emit)
        self.signals.signal_progressbar_reset = SignalProxy(self.signals.signal_progressbar_reset_emit)
        self.signals.signal_label_number_update = SignalProxy(self.signals.signal_label_number_update_emit)
        self.signals.signal_lcd_number_update = SignalProxy(self.signals.signal_lcd_number_update_emit)
        self.signals.signal_pie_chart_update = SignalProxy(self.signals.signal_pie_chart_update_emit)
        self.signals.signal_curve_chart_update1 = SignalProxy(self.signals.signal_curve_chart_update1_emit)
        self.signals.signal_curve_chart_update2 = SignalProxy(self.signals.signal_curve_chart_update2_emit)

        return self.signals

    def _bot_loop(self, single_hand=False):
        """Main bot loop - runs in background thread"""
        log.info("=" * 50)
        log.info("Bot starting in CLI/headless mode")
        log.info("=" * 50)

        # Load preflop sheet
        updater = UpdateChecker()
        history = History()
        preflop_url, preflop_url_backup = updater.get_preflop_sheet_url()
        try:
            history.preflop_sheet = pd.read_excel(preflop_url, sheet_name=None, engine='openpyxl')
        except:
            history.preflop_sheet = pd.read_excel(preflop_url_backup, sheet_name=None, engine='openpyxl')

        # Load strategy
        strategy = StrategyHandler()
        if self.strategy_name:
            strategy.read_strategy(self.strategy_name)
        else:
            strategy.read_strategy()

        preflop_state = CurrentHandPreflopState()
        mongo = MongoManager()

        # Override table name if specified
        if self.table_name:
            config = get_config()
            config.config.set('main', 'table_scraper_name', self.table_name)
            config.update_file()

        table_scraper_name = None
        hands_played = 0
        consecutive_table_failures = 0
        max_failures_before_lobby_nav = 5  # After 5 failures, try lobby navigation

        while not self.signals.exit_thread:
            # Check for pause
            if self.signals.pause_thread:
                while self.signals.pause_thread and not self.signals.exit_thread:
                    time.sleep(0.5)
                if self.signals.exit_thread:
                    break

            ready = False
            while not ready and not self.signals.exit_thread:
                config = get_config()

                # Reload table if changed
                current_table = config.config.get('main', 'table_scraper_name')
                if table_scraper_name != current_table:
                    table_scraper_name = current_table
                    log.info(f"Loading table: {table_scraper_name}")
                    table_dict = mongo.get_table(table_scraper_name)
                    nn_model = None
                    slow_table = False

                    if 'use_neural_network' in table_dict and table_dict['use_neural_network'] in ['2', 'CheckState.Checked']:
                        from tensorflow.keras.models import model_from_json
                        try:
                            nn_model = model_from_json(table_dict['_model'])
                            mongo.load_table_nn_weights(table_scraper_name)
                            nn_model.load_weights(get_dir('codebase') + '/loaded_model.h5')
                            slow_table = True
                        except KeyError:
                            log.warning("Neural network model not found in table")

                table = TableScreenBased(strategy, table_dict, self.signals, self.game_logger, VERSION, nn_model)

                # Initialize adaptive learner for this session
                learner = get_learner()

                # Create input controller based on method
                if self.input_method == INPUT_KEYBOARD:
                    mouse = KeyboardControllerTableBased(table_dict)
                    log.info("Using KEYBOARD hotkeys for actions (F=Fold, C=Call, B=Bet)")
                elif self.input_method == INPUT_FAST:
                    mouse = FastMouseMover(table_dict)
                    log.info("Using FAST CGEventPost clicks for actions (instant, reliable)")
                elif self.input_method == INPUT_DYNAMIC:
                    mouse = DynamicMouseMover()
                    log.info("Using DYNAMIC color-based button detection (most reliable)")
                else:
                    mouse = MouseMoverTableBased(table_dict)
                    mouse.move_mouse_away_from_buttons_jump()
                    log.info("Using MOUSE clicks for actions")

                # Run all the checks
                ready = (
                    table.take_screenshot(True, strategy) and
                    table.get_top_left_corner(strategy) and
                    table.check_for_captcha(mouse) and
                    table.get_lost_everything(history, table, strategy, self.signals) and
                    table.check_for_imback(mouse) and
                    table.check_for_resume_hand(mouse) and
                    table.check_for_button_if_slow_table(slow_table) and
                    table.get_my_cards() and
                    table.get_new_hand(mouse, history, strategy) and
                    table.get_table_cards(history) and
                    table.upload_collusion_wrapper(strategy, history) and
                    table.get_dealer_position() and
                    table.check_fast_fold(history, strategy, mouse) and
                    table.check_for_button() and
                    strategy.read_strategy() and
                    table.get_round_number(history) and
                    table.check_for_checkbutton() and
                    table.init_get_other_players_info() and
                    table.get_other_player_status(strategy, history) and
                    table.get_other_player_names(strategy) and
                    table.get_other_player_funds(strategy) and
                    table.get_total_pot_value(history) and
                    table.get_round_pot_value(history) and
                    table.check_for_call() and
                    table.check_for_betbutton() and
                    table.check_for_allincall() and
                    table.get_current_call_value(strategy) and
                    table.get_current_bet_value(strategy)
                )

                if not ready:
                    # Log detection failure with screenshot for adaptive learning
                    if hasattr(table, 'entireScreenPIL') and table.entireScreenPIL:
                        from gamble.tools.adaptive_learner import save_debug_screenshot
                        try:
                            save_debug_screenshot('table_detection', table.entireScreenPIL, 'not_ready')
                        except Exception:
                            pass
                    log_action('table_detection', success=False, details={
                        'stage': 'checks_failed',
                        'cards_found': hasattr(table, 'mycards') and table.mycards
                    })

                    # Check if we need to click "Deal Me In" (Rush & Cash)
                    if hasattr(mouse, 'click_deal_me_in'):
                        if mouse.click_deal_me_in():
                            log.info("Clicked 'Deal Me In' button")
                            time.sleep(1)  # Wait for new hand to be dealt
                            continue

                    # FALLBACK: If full analysis failed but buttons ARE visible, take action anyway
                    # This handles Spin & Gold and other tables where card detection fails
                    try:
                        from gamble.tools.dynamic_table_finder import DynamicTableFinder, click_button
                        from gamble.tools.smart_card_detector import SmartCardDetector

                        fallback_finder = DynamicTableFinder()
                        poker_tables = fallback_finder.find_poker_tables()

                        # AUTONOMOUS ACTION: First, try to understand and act on what's on screen
                        # This handles dialogs, popups, and any screen state automatically
                        try:
                            from PIL import ImageGrab
                            full_screenshot = ImageGrab.grab()
                            if analyze_and_act(full_screenshot):
                                log.info("AUTONOMOUS: Action taken based on screen analysis")
                                time.sleep(1)  # Wait for UI to update
                                continue  # Retry detection
                        except Exception as auto_err:
                            log.debug(f"Autonomous action failed: {auto_err}")

                        # AUTO-REGISTRATION: If no poker tables open, register for one
                        if not poker_tables:
                            all_windows = fallback_finder.find_all_tables()
                            if all_windows:  # GGPoker is open but no tables
                                log.info("AUTO-REGISTER: No poker tables open, attempting to register...")
                                try:
                                    from gamble.tools.dynamic_lobby_navigator import DynamicLobbyNavigator
                                    navigator = DynamicLobbyNavigator()
                                    if navigator.find_lobby_window():
                                        success = navigator.register_for_spin_gold(stake_index=0)
                                        if success:
                                            log.info("AUTO-REGISTER: Successfully registered for Spin & Gold!")
                                            log_action('auto_registration', success=True, details={
                                                'game_type': 'spin_gold'
                                            })
                                            time.sleep(5)  # Wait for table to open
                                        else:
                                            log.warning("AUTO-REGISTER: Failed to register")
                                            log_action('auto_registration', success=False, details={
                                                'reason': 'registration_failed'
                                            })
                                except Exception as e:
                                    log.warning(f"AUTO-REGISTER: Error during registration: {e}")
                                continue  # Retry after registration attempt

                        if poker_tables:
                            log.info(f"FALLBACK: Checking {len(poker_tables)} poker table(s)")
                            screenshot = fallback_finder.capture_screenshot()
                            card_detector = SmartCardDetector(table_dict)
                            healer = get_healer()  # Get self-healer for autonomous fixes

                            for ptable in poker_tables:
                                # Use hybrid OCR+color detection for reliable button finding
                                if hasattr(fallback_finder, 'find_buttons_hybrid'):
                                    buttons = fallback_finder.find_buttons_hybrid(ptable, screenshot)
                                else:
                                    buttons = fallback_finder.find_buttons(ptable, screenshot)

                                # SELF-HEALING: If no buttons found, try auto-healing
                                if not buttons:
                                    log.info(f"SELF-HEALING: Button detection failed, attempting auto-heal...")
                                    table_img = ptable.capture(screenshot)
                                    buttons = healer.heal_button_detection(table_img)
                                    if buttons:
                                        log.info(f"SELF-HEALING: Successfully found {list(buttons.keys())}")
                                        # Convert healed button coords to screen coords
                                        for btn_key in buttons:
                                            btn = buttons[btn_key]
                                            btn['screen_pt'] = ptable.table_px_to_screen_pt(
                                                btn['x_px'], btn['y_px']
                                            )

                                if not buttons:
                                    continue

                                log.info(f"FALLBACK [{ptable.name[:25]}]: buttons {list(buttons.keys())}")

                                # Try to detect cards for smarter decision
                                table_region = (ptable.x_px, ptable.y_px, ptable.w_px, ptable.h_px)
                                cards = card_detector.detect_cards(screenshot, table_region)

                                # SELF-HEALING: If no cards found, try auto-healing
                                if not cards or len(cards) < 2:
                                    log.info(f"SELF-HEALING: Card detection failed, attempting auto-heal...")
                                    table_img = ptable.capture(screenshot)
                                    healed_cards = healer.heal_card_detection(table_img)
                                    if healed_cards and healed_cards.get('cards'):
                                        log.info(f"SELF-HEALING: Found card regions via auto-heal")
                                        # For now, we found cards but don't have ranks yet
                                        # This at least confirms cards are present

                                action = None
                                if cards and len(cards) == 2:
                                    log.info(f"FALLBACK [{ptable.name[:25]}]: Cards detected: {cards}")
                                    # TODO: Use equity calculation for real decision
                                    ranks = [c[0] for c in cards]
                                    # Only trust detection if we got actual ranks (not '?')
                                    if '?' not in ranks:
                                        if ranks[0] == ranks[1]:  # Pair
                                            action = 'call' if 'call' in buttons else 'raise'
                                            log.info(f"FALLBACK: PAIR {ranks[0]} detected - {action.upper()}")
                                        elif any(r in 'AKQJ' for r in ranks):  # High card
                                            action = 'call' if 'call' in buttons else None
                                            log.info(f"FALLBACK: HIGH CARD {ranks} - CALL")
                                        else:
                                            action = 'fold' if 'fold' in buttons else None
                                            log.info(f"FALLBACK: LOW CARDS {ranks} - FOLD")
                                    else:
                                        # Unknown ranks - be conservative, fold
                                        action = 'fold' if 'fold' in buttons else None
                                        log.info(f"FALLBACK [{ptable.name[:25]}]: Ranks unknown, FOLD")
                                else:
                                    # No cards detected - use safe defaults
                                    if 'fold' in buttons and 'call' in buttons:
                                        action = 'fold'
                                        log.info(f"FALLBACK [{ptable.name[:25]}]: No cards, FOLD (safe)")
                                    elif 'call' in buttons and 'fold' not in buttons:
                                        action = 'call'
                                        log.info(f"FALLBACK [{ptable.name[:25]}]: CHECK (free)")
                                    elif 'fold' in buttons:
                                        action = 'fold'

                                if action and action in buttons:
                                    click_button(buttons[action], ptable)
                                    log.info(f"FALLBACK [{ptable.name[:25]}]: Clicked {action.upper()}")

                                    # Log fallback action to adaptive learner
                                    log_action('fallback_action', success=True, details={
                                        'action': action,
                                        'table': ptable.name[:25],
                                        'cards_detected': cards and len(cards) == 2,
                                        'buttons_found': list(buttons.keys())
                                    })

                                    time.sleep(0.8)  # Brief wait, then check next table

                    except Exception as e:
                        log.warning(f"Fallback button check failed: {e}")

                    time.sleep(0.5)  # Faster retry for responsive play

            if self.signals.exit_thread:
                break

            # Process the hand
            if not self.signals.pause_thread:
                config = get_config()
                m = run_montecarlo_wrapper(strategy, self.signals, config, None, table,
                                          self.game_logger, preflop_state, history)

                d = Decision(table, history, strategy, self.game_logger)
                d.make_decision(table, history, strategy, self.game_logger)

                # Log decision info
                log.info(f"Cards: {table.mycards} | Table: {table.cardsOnTable}")
                log.info(f"Equity: {table.equity * 100:.1f}% | Players: {int(table.assumedPlayers)}")
                log.info(f"Call Limit: {d.finalCallLimit:.2f} | Min Call: {table.minCall}")
                log.info(f"Bet Limit: {d.finalBetLimit:.2f} | Min Bet: {table.minBet}")
                log.info(f">>> DECISION: {d.decision} <<<")

                # Log card detection to adaptive learner
                cards_detected = table.mycards is not None and len(table.mycards) > 0
                log_action('card_detection', success=cards_detected, details={
                    'cards': table.mycards if cards_detected else None,
                    'table_cards': table.cardsOnTable,
                    'game_stage': table.gameStage
                })

                # Execute action
                mouse_target = d.decision
                action_options = {}

                if mouse_target == 'Call' and table.allInCallButton:
                    mouse_target = 'Call2'
                elif mouse_target == 'BetPlus':
                    action_options['increases_num'] = strategy.selected_strategy['BetPlusInc']

                if self.signals.ui.auto_act.isChecked():
                    mouse.mouse_action(mouse_target, table.tlc, action_options)
                    log.info(f"Executed: {mouse_target}")

                    # Log action execution to adaptive learner
                    log_action('action_execution', success=True, details={
                        'action': mouse_target,
                        'decision': d.decision,
                        'equity': table.equity,
                        'pot': table.totalPotValue,
                        'call_amount': table.minCall,
                        'game_stage': table.gameStage
                    })
                else:
                    log.info(f"Auto-act disabled. Manual action needed: {mouse_target}")

                table.time_action_completed = datetime.datetime.utcnow()

                # Save screenshot
                filename = f"{history.GameID}_{table.gameStage}_{history.round_number}.png"
                pil_image = table.crop_image(table.entireScreenPIL, table.tlc[0], table.tlc[1],
                                            table.tlc[0] + const.CROP_WIDTH, table.tlc[1] + const.CROP_HEIGHT)
                pil_image.save(f"log/screenshots/{filename}")

                # Log to database
                t_log = threading.Thread(target=self.game_logger.write_log_file,
                                        args=[strategy, history, table, d])
                t_log.daemon = True
                t_log.start()

                # Update history
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
                hands_played += 1
                self.signals.hand_count = hands_played

                # Log hand completion to adaptive learner
                log_action('hand_complete', success=True, details={
                    'hand_number': hands_played,
                    'decision': d.decision,
                    'game_stage': table.gameStage,
                    'equity': table.equity,
                    'pot': table.totalPotValue
                })

                log.info(f"=========== Hand #{hands_played} complete ===========")

                # If single hand mode, stop after one hand
                if single_hand:
                    self.signals.exit_thread = True

        # End adaptive learning session and save stats
        try:
            learner = get_learner()
            summary = learner.end_session()
            log.info(f"Learning session ended: {summary['total_actions']} actions, "
                     f"{summary['actions_per_minute']:.1f}/min")
            recommendations = learner.get_recommendations()
            for rec in recommendations:
                log.info(f"Recommendation: {rec}")
        except Exception as e:
            log.warning(f"Failed to end learning session: {e}")

        log.info("Bot stopped")
        self.running = False

    def start(self):
        """Start the bot in background thread (non-blocking)"""
        if self.running:
            log.warning("Bot is already running")
            return False

        self._create_signals()
        self.signals.pause_thread = False
        self.signals.exit_thread = False
        self.running = True

        self.thread = threading.Thread(target=self._bot_loop, args=(False,))
        self.thread.daemon = True
        self.thread.start()

        log.info("Bot started in background")
        return True

    def stop(self):
        """Stop the bot"""
        if not self.running:
            log.warning("Bot is not running")
            return False

        self.signals.exit_thread = True
        self.signals.pause_thread = False  # Unpause so it can exit

        if self.thread:
            self.thread.join(timeout=5)

        self.running = False
        log.info("Bot stopped")
        return True

    def pause(self):
        """Pause the bot"""
        if self.signals:
            self.signals.pause_thread = True
            log.info("Bot paused")

    def resume(self):
        """Resume the bot"""
        if self.signals:
            self.signals.pause_thread = False
            log.info("Bot resumed")

    def status(self):
        """Get current bot status"""
        if not self.signals:
            return {"running": False, "status": "Not initialized"}

        return {
            "running": self.running,
            "paused": self.signals.pause_thread,
            "hands_played": self.signals.hand_count,
            "last_decision": self.signals.last_decision,
            "last_equity": self.signals.last_equity,
            "last_status": self.signals.last_status,
            "auto_act": self.signals.ui.auto_act.isChecked()
        }

    def set_auto_act(self, enabled):
        """Enable/disable automatic clicking"""
        if self.signals:
            self.signals.ui.auto_act.setChecked(enabled)
            log.info(f"Auto-act {'enabled' if enabled else 'disabled'}")

    def run_single_hand(self):
        """Run bot for exactly one hand (blocking)"""
        self._create_signals()
        self.signals.pause_thread = False
        self.signals.exit_thread = False
        self.running = True

        # Run in current thread (blocking)
        self._bot_loop(single_hand=True)

        return self.status()


# Convenience functions for quick CLI use
def start_bot(table_name=None, strategy_name=None, auto_act=True, input_method=INPUT_MOUSE):
    """Quick start function"""
    bot = BotController(table_name=table_name, strategy_name=strategy_name,
                       auto_act=auto_act, input_method=input_method)
    bot.start()
    return bot


def test_table_detection(table_name="Official GGPoker 6player"):
    """Test if the bot can find the poker table"""
    from gamble.tools.claude_table_setup import ClaudeTableSetup

    setup = ClaudeTableSetup(table_name)
    success, score, loc = setup.test_template_match()

    print(f"Table: {table_name}")
    print(f"Match: {'SUCCESS' if success else 'FAILED'}")
    print(f"Score: {score:.6f}" if score else "Score: N/A")
    print(f"Location: {loc}" if loc else "Location: Not found")

    return success


def ask_input_method():
    """Returns dynamic by default - color-based detection is most reliable"""
    print("Using DYNAMIC color-based button detection (most reliable)")
    return INPUT_DYNAMIC


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Poker Bot CLI Controller")
    parser.add_argument("command", choices=["start", "test", "single", "multi"],
                       help="Command to run (multi = multi-table mode)")
    parser.add_argument("--table", default=None, help="Table template name")
    parser.add_argument("--strategy", default=None, help="Strategy name")
    parser.add_argument("--no-auto", action="store_true", help="Disable auto-clicking")
    parser.add_argument("--input", choices=["mouse", "keyboard", "fast", "dynamic"], default=None,
                       help="Input method: mouse, keyboard, fast (CGEventPost), or dynamic (color detection). Defaults to dynamic.")
    parser.add_argument("--max-tables", type=int, default=4,
                       help="Maximum number of tables for multi-table mode")

    args = parser.parse_args()

    if args.command == "test":
        test_table_detection(args.table or "Official GGPoker 6player")

    elif args.command == "multi":
        # Multi-table mode
        from gamble.tools.multi_table_controller import MultiTableController

        print("=" * 60)
        print("MULTI-TABLE MODE")
        print("=" * 60)

        if args.input:
            input_method = args.input
        else:
            input_method = ask_input_method()

        controller = MultiTableController(
            table_name=args.table,
            strategy_name=args.strategy,
            input_method=input_method,
            max_tables=args.max_tables,
            auto_act=not args.no_auto
        )
        controller.start()

        print("Multi-table bot running. Press Ctrl+C to stop.")
        print("=" * 60)

        try:
            while controller.running:
                time.sleep(5)
                status = controller.get_status()
                tables = status.get('tables', {})
                print(f"[Status] Tables: {tables.get('visible_sessions', 0)} visible | "
                      f"Action needed: {tables.get('needs_action', 0)} | "
                      f"Hands: {status['total_hands']} | "
                      f"Uptime: {status['uptime']:.0f}s")
        except KeyboardInterrupt:
            print("\nStopping...")
        controller.stop()
        print("Done.")

    elif args.command == "start":
        # Single table mode (legacy)
        if args.input:
            input_method = args.input
        else:
            input_method = ask_input_method()

        bot = BotController(table_name=args.table, strategy_name=args.strategy,
                           auto_act=not args.no_auto, input_method=input_method)
        bot.start()
        print("Bot running. Press Ctrl+C to stop.")
        try:
            while bot.running:
                time.sleep(1)
        except KeyboardInterrupt:
            bot.stop()

    elif args.command == "single":
        # Single hand mode
        if args.input:
            input_method = args.input
        else:
            input_method = ask_input_method()

        bot = BotController(table_name=args.table, strategy_name=args.strategy,
                           auto_act=not args.no_auto, input_method=input_method)
        result = bot.run_single_hand()
        print(f"Result: {result}")
