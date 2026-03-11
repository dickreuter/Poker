"""
Multi-Table Controller - Orchestrates Multiple Poker Tables

This module provides the main controller for running the poker bot
on multiple tables simultaneously. It uses an event-driven architecture
with priority-based action execution.

Architecture:
    MultiTableController
    ├── TableSessionManager (manages TableSession instances)
    ├── ActionQueue (priority queue for pending actions)
    └── Main Loop:
        1. Capture all table states (parallel via threads)
        2. Identify tables needing action
        3. Prioritize by urgency
        4. Execute actions sequentially
        5. Verify success
        6. Repeat

Usage:
    from gamble.tools.multi_table_controller import MultiTableController

    controller = MultiTableController()
    controller.start()  # Non-blocking, runs in background

    # Check status
    print(controller.get_status())

    # Stop
    controller.stop()
"""

import datetime
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from queue import PriorityQueue
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
from PIL import ImageGrab

from gamble.decisionmaker.current_hand_memory import CurrentHandPreflopState, History
from gamble.decisionmaker.decisionmaker import Decision
from gamble.decisionmaker.montecarlo_python import run_montecarlo_wrapper
from gamble.gui.action_and_signals import StrategyHandler
from gamble.scraper.table_scraper import TableScraper
from gamble.scraper.table_screen_based import TableScreenBased
from gamble.tools.game_logger import GameLogger
from gamble.tools.helper import init_logger, get_config, get_dir
from gamble.tools.mongo_manager import MongoManager
from gamble.tools.mouse_mover import MouseMoverTableBased
from gamble.tools.keyboard_controller import KeyboardControllerTableBased
from gamble.tools.table_session import TableSession, TableSessionManager, TableState
from gamble.tools.update_checker import UpdateChecker
from gamble.tools import constants as const

log = logging.getLogger(__name__)

VERSION = 6.77  # Multi-table version


@dataclass
class PendingAction:
    """Action waiting to be executed."""
    priority: int
    table_id: int
    decision: str
    timestamp: float

    def __lt__(self, other):
        # Higher priority first (reverse order for PriorityQueue)
        return self.priority > other.priority


class MockSignal:
    """Mock signal that does nothing on emit."""
    def emit(self, *args, **kwargs):
        pass


class MockSignals:
    """Mock signals for headless operation."""

    def __init__(self):
        self.pause_thread = False
        self.exit_thread = False
        self.signal_status = MockSignal()
        self.signal_progressbar_increase = MockSignal()
        self.signal_progressbar_reset = MockSignal()

    class MockUI:
        class MockAutoAct:
            def isChecked(self):
                return True
        auto_act = MockAutoAct()

    ui = MockUI()


class MultiTableController:
    """
    Main controller for multi-table poker bot operation.

    Manages multiple poker tables simultaneously using:
    - Parallel state capture
    - Priority-based action execution
    - Shared decision logic

    Features:
    - Automatic table discovery
    - Dynamic priority calculation
    - Self-healing on errors
    - Detailed logging
    """

    def __init__(self, table_name: str = None, strategy_name: str = None,
                 auto_act: bool = True, input_method: str = 'mouse',
                 max_tables: int = 4, verbose: bool = True):
        """
        Initialize the multi-table controller.

        Args:
            table_name: Template name (default: from config)
            strategy_name: Strategy name (default: from config)
            auto_act: Whether to automatically execute actions
            input_method: 'mouse' or 'keyboard'
            max_tables: Maximum number of tables to manage
            verbose: Enable detailed logging
        """
        self.table_name = table_name
        self.strategy_name = strategy_name
        self.auto_act = auto_act
        self.input_method = input_method
        self.max_tables = max_tables
        self.verbose = verbose

        # State
        self.running = False
        self.paused = False
        self.thread = None
        self.signals = MockSignals()

        # Components (initialized on start)
        self.session_manager = None
        self.action_queue = PriorityQueue()
        self.executor = ThreadPoolExecutor(max_workers=max_tables)

        # Shared resources
        self.table_dict = None
        self.strategy = None
        self.preflop_sheet = None
        self.history = None
        self.game_logger = GameLogger()

        # Per-table resources
        self.table_scrapers: Dict[int, TableScraper] = {}
        self.table_objects: Dict[int, TableScreenBased] = {}
        self.input_controllers: Dict[int, Any] = {}  # Mouse or Keyboard

        # Stats
        self.total_hands = 0
        self.start_time = None
        self.last_action_time = None

        # Initialize logging
        if verbose:
            init_logger(screenlevel=logging.INFO, filename='dm_assistant', logdir='log')

    def _initialize(self):
        """Initialize shared resources."""
        log.info("=" * 60)
        log.info("Multi-Table Bot Starting")
        log.info("=" * 60)

        # Load table template
        mongo = MongoManager()
        if self.table_name:
            self.table_dict = mongo.get_table(self.table_name)
        else:
            config = get_config()
            self.table_name = config.config.get('main', 'table_scraper_name')
            self.table_dict = mongo.get_table(self.table_name)

        log.info(f"Loaded table: {self.table_name}")

        # Load strategy
        self.strategy = StrategyHandler()
        if self.strategy_name:
            self.strategy.read_strategy(self.strategy_name)
        else:
            self.strategy.read_strategy()

        log.info(f"Loaded strategy: {self.strategy.current_strategy}")

        # Load preflop sheet
        updater = UpdateChecker()
        self.history = History()
        preflop_url, preflop_url_backup = updater.get_preflop_sheet_url()
        try:
            self.history.preflop_sheet = pd.read_excel(preflop_url, sheet_name=None, engine='openpyxl')
        except:
            self.history.preflop_sheet = pd.read_excel(preflop_url_backup, sheet_name=None, engine='openpyxl')

        # Initialize session manager
        self.session_manager = TableSessionManager(self.table_dict, self.strategy)

        log.info("Multi-table controller initialized")

    def _get_or_create_table_resources(self, session: TableSession) -> Tuple[TableScraper, TableScreenBased, Any]:
        """
        Get or create resources for a specific table.

        Args:
            session: TableSession for the table

        Returns:
            Tuple of (scraper, table_object, input_controller)
        """
        table_id = session.table_id

        if table_id not in self.table_scrapers:
            # Create new resources for this table
            self.table_scrapers[table_id] = TableScraper(self.table_dict)
            self.table_objects[table_id] = TableScreenBased(
                self.strategy, self.table_dict, self.signals,
                self.game_logger, VERSION, None
            )

            if self.input_method == 'keyboard':
                self.input_controllers[table_id] = KeyboardControllerTableBased(self.table_dict)
            else:
                self.input_controllers[table_id] = MouseMoverTableBased(self.table_dict)

            log.debug(f"Created resources for table {table_id}")

        return (
            self.table_scrapers[table_id],
            self.table_objects[table_id],
            self.input_controllers[table_id]
        )

    def _capture_all_states(self, screenshot) -> Dict[int, TableState]:
        """
        Capture state of all tables in parallel.

        Args:
            screenshot: Full screen PIL Image

        Returns:
            Dict mapping table_id to TableState
        """
        # First, discover/update tables
        sessions = self.session_manager.discover_tables(screenshot)

        # Capture detailed state for tables that need action
        states = {}
        for session in sessions:
            if session.state.needs_action:
                scraper, table_obj, _ = self._get_or_create_table_resources(session)
                state = session.capture_full_state(screenshot, scraper)
            else:
                state = session.state

            states[session.table_id] = state

        return states

    def _process_table(self, session: TableSession) -> Optional[str]:
        """
        Process a single table - make decision and execute action.

        Args:
            session: TableSession to process

        Returns:
            Decision made, or None if no action taken
        """
        if not session.state.needs_action:
            return None

        # If cards not detected but we need action, fold to avoid timeout
        if len(session.state.my_cards) != 2:
            log.warning(f"Table {session.table_id}: Cards not detected - folding for safety")
            try:
                _, _, input_controller = self._get_or_create_table_resources(session)
                input_controller.mouse_action("Fold", session.state.tlc)
                self.stats['actions_taken'] += 1
                return "Fold"
            except Exception as e:
                log.error(f"Table {session.table_id}: Failed to fold - {e}")
                return None

        try:
            scraper, table_obj, input_controller = self._get_or_create_table_resources(session)

            # Set up table object with current state
            table_obj.screenshot = session.state.screenshot
            table_obj.tlc = session.state.tlc
            table_obj.mycards = session.state.my_cards
            table_obj.cardsOnTable = session.state.table_cards
            table_obj.gameStage = session.state.game_stage
            table_obj.totalPotValue = session.state.total_pot
            table_obj.minCall = session.state.min_call
            table_obj.minBet = session.state.min_bet
            table_obj.mt_tm = time.time()
            table_obj.montecarlo_timeout = 10

            # Run Monte Carlo for equity calculation
            config = get_config()
            preflop_state = CurrentHandPreflopState()

            run_montecarlo_wrapper(
                self.strategy, self.signals, config, None, table_obj,
                self.game_logger, preflop_state, self.history
            )

            # Make decision
            decision_maker = Decision(table_obj, self.history, self.strategy, self.game_logger)
            decision_maker.make_decision(table_obj, self.history, self.strategy, self.game_logger)

            decision = decision_maker.decision

            # Log decision
            log.info(f"Table {session.table_id}: {session.state.my_cards} -> {decision} "
                    f"(equity: {table_obj.equity*100:.1f}%)")

            # Execute action if auto_act enabled
            if self.auto_act:
                mouse_target = decision
                action_options = {}

                if mouse_target == 'Call' and getattr(table_obj, 'allInCallButton', False):
                    mouse_target = 'Call2'
                elif mouse_target == 'BetPlus':
                    action_options['increases_num'] = self.strategy.selected_strategy.get('BetPlusInc', 1)

                input_controller.mouse_action(mouse_target, session.state.tlc, action_options)
                log.info(f"Table {session.table_id}: Executed {mouse_target}")

                session.record_action(decision, True)
                self.total_hands += 1
                self.last_action_time = time.time()

            return decision

        except Exception as e:
            log.error(f"Table {session.table_id}: Error processing - {e}")
            import traceback
            traceback.print_exc()
            return None

    def _main_loop(self):
        """Main bot loop - runs in background thread."""
        log.info("Main loop started")
        self.start_time = time.time()

        while not self.signals.exit_thread:
            # Check for pause
            while self.paused and not self.signals.exit_thread:
                time.sleep(0.5)

            if self.signals.exit_thread:
                break

            try:
                # Take screenshot
                screenshot = ImageGrab.grab()

                # Capture all table states
                states = self._capture_all_states(screenshot)

                # Get tables needing action, sorted by priority
                action_sessions = self.session_manager.get_sessions_needing_action()

                if action_sessions:
                    log.debug(f"Tables needing action: {[s.table_id for s in action_sessions]}")

                    # Process highest priority table
                    # (Sequential to avoid mouse conflicts)
                    for session in action_sessions[:1]:  # Process one at a time
                        decision = self._process_table(session)
                        if decision:
                            # Brief pause between tables
                            time.sleep(0.3)

                # Brief pause before next cycle
                time.sleep(0.5)

            except Exception as e:
                log.error(f"Main loop error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

        log.info("Main loop stopped")
        self.running = False

    def start(self):
        """Start the multi-table bot (non-blocking)."""
        if self.running:
            log.warning("Bot already running")
            return False

        self._initialize()

        self.running = True
        self.paused = False
        self.signals.exit_thread = False
        self.signals.pause_thread = False

        self.thread = threading.Thread(target=self._main_loop, daemon=True)
        self.thread.start()

        log.info("Multi-table bot started")
        return True

    def stop(self):
        """Stop the bot."""
        if not self.running:
            log.warning("Bot not running")
            return False

        self.signals.exit_thread = True
        self.paused = False

        if self.thread:
            self.thread.join(timeout=5)

        self.running = False
        self.executor.shutdown(wait=False)

        log.info("Multi-table bot stopped")
        return True

    def pause(self):
        """Pause the bot."""
        self.paused = True
        log.info("Bot paused")

    def resume(self):
        """Resume the bot."""
        self.paused = False
        log.info("Bot resumed")

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status."""
        status = {
            'running': self.running,
            'paused': self.paused,
            'total_hands': self.total_hands,
            'uptime': time.time() - self.start_time if self.start_time else 0,
            'last_action': self.last_action_time,
            'table_name': self.table_name,
            'input_method': self.input_method,
            'auto_act': self.auto_act
        }

        if self.session_manager:
            status['tables'] = self.session_manager.get_status()

        return status


def run_multi_table(table_name: str = None, strategy_name: str = None,
                   input_method: str = 'mouse', max_tables: int = 4):
    """
    Convenience function to run multi-table bot.

    Args:
        table_name: Template name
        strategy_name: Strategy name
        input_method: 'mouse' or 'keyboard'
        max_tables: Maximum tables to manage

    Returns:
        MultiTableController instance
    """
    controller = MultiTableController(
        table_name=table_name,
        strategy_name=strategy_name,
        input_method=input_method,
        max_tables=max_tables
    )
    controller.start()
    return controller


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Multi-Table Poker Bot")
    parser.add_argument("--table", default=None, help="Table template name")
    parser.add_argument("--strategy", default=None, help="Strategy name")
    parser.add_argument("--input", choices=["mouse", "keyboard"], default="mouse",
                       help="Input method")
    parser.add_argument("--max-tables", type=int, default=4,
                       help="Maximum number of tables")

    args = parser.parse_args()

    print("=" * 60)
    print("Multi-Table Poker Bot")
    print("=" * 60)
    print(f"Table: {args.table or 'default'}")
    print(f"Strategy: {args.strategy or 'default'}")
    print(f"Input: {args.input}")
    print(f"Max tables: {args.max_tables}")
    print("=" * 60)

    controller = MultiTableController(
        table_name=args.table,
        strategy_name=args.strategy,
        input_method=args.input,
        max_tables=args.max_tables
    )

    controller.start()

    print("\nBot running. Press Ctrl+C to stop.\n")

    try:
        while controller.running:
            time.sleep(5)
            status = controller.get_status()
            tables = status.get('tables', {})
            print(f"Tables: {tables.get('visible_sessions', 0)} visible, "
                  f"{tables.get('needs_action', 0)} need action, "
                  f"Hands: {status['total_hands']}")
    except KeyboardInterrupt:
        print("\nStopping...")

    controller.stop()
    print("Done.")
