"""
MASTER BOT - Complete Autonomous System System

This is the master controller that combines:
1. UI Navigator - For lobby navigation and table registration
2. Ten Table Bot - For autonomous play on multiple tables
3. Session Manager - For maintaining target table count

Features:
- Automatically opens and maintains target number of tables
- Plays autonomously on all tables with priority-based actions
- Recovers from errors and popup interruptions
- Screenshot verification for all clicks

Usage:
    python -m sys_core.tools.master_bot --tables 10

Or:
    from sys_core.tools.master_bot import MasterBot
    bot = MasterBot(target_tables=10)
    bot.run()

Author: Claude (2026-01-04)
"""

import logging
import threading
import time
import signal
import sys
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


class MasterBot:
    """
    Master controller for complete autonomous poker operation.

    Manages the full lifecycle:
    1. Startup: Navigate lobby and open tables
    2. Play: Run multi-table bot
    3. Maintenance: Keep target table count, handle errors
    4. Shutdown: Clean exit
    """

    def __init__(self, target_tables: int = 10, stake_level: str = None):
        """
        Initialize the master bot.

        Args:
            target_tables: Target number of tables to maintain
            stake_level: Optional stake level (e.g., "$1", "$5")
        """
        self.target_tables = target_tables
        self.stake_level = stake_level

        # Components (lazy loaded)
        self._navigator = None
        self._player = None
        self._table_dict = None

        # State
        self.running = False
        self.paused = False
        self.last_maintenance = 0
        self.maintenance_interval = 60  # Check table count every 60 seconds

        # Stats
        self.start_time = None
        self.tables_opened = 0
        self.total_actions = 0

        log.info(f"MasterBot initialized (target: {target_tables} tables)")

    @property
    def navigator(self):
        """Lazy load UI navigator."""
        if self._navigator is None:
            from sys_core.tools.ui_navigator import UINavigator
            self._navigator = UINavigator()
        return self._navigator

    @property
    def player(self):
        """Lazy load table player."""
        if self._player is None:
            from sys_core.tools.ten_table_bot import TenTableBot
            self._player = TenTableBot(
                max_tables=self.target_tables,
                table_dict=self._table_dict
            )
        return self._player

    def _load_table_dict(self):
        """Load table templates from MongoDB."""
        try:
            from sys_core.tools.mongo_manager import MongoManager
            mongo = MongoManager()
            self._table_dict = mongo.get_table("Official GGPoker 6player")
            log.info("Loaded table templates from MongoDB")
            return True
        except Exception as e:
            log.warning(f"Could not load table templates: {e}")
            return False

    def _ensure_tables(self) -> int:
        """
        Ensure target number of tables are open.

        Returns:
            Current number of open tables
        """
        current = self.navigator._count_poker_tables()

        if current < self.target_tables:
            log.info(f"Need more tables: {current}/{self.target_tables}")

            # Try to open more tables
            needed = self.target_tables - current
            for _ in range(min(needed, 3)):  # Open max 3 at a time
                if self.navigator.navigate_to_spin_gold():
                    if self.navigator.register_new_table(self.stake_level):
                        if self.navigator.wait_for_table(timeout=15):
                            self.tables_opened += 1
                            current = self.navigator._count_poker_tables()
                            log.info(f"Opened table, now at {current}")
                        else:
                            # Check for popup
                            self.navigator.close_popup()

                # Brief pause between registrations
                time.sleep(1)

        return current

    def _run_maintenance(self):
        """Run periodic maintenance tasks."""
        now = time.time()

        if now - self.last_maintenance < self.maintenance_interval:
            return

        self.last_maintenance = now
        log.debug("Running maintenance check...")

        # Check table count
        current = self.navigator._count_poker_tables()
        if current < self.target_tables:
            log.info(f"Maintenance: Only {current}/{self.target_tables} tables, opening more")
            self._ensure_tables()

        # Close any popups that might have appeared
        self.navigator.close_popup()

    def run(self):
        """Main run loop."""
        print("=" * 70)
        print("MASTER BOT - Complete Autonomous System System")
        print("=" * 70)
        print(f"Target tables: {self.target_tables}")
        print(f"Stake level: {self.stake_level or 'default'}")
        print("=" * 70)

        self.running = True
        self.start_time = time.time()

        # Load templates
        self._load_table_dict()

        # Phase 1: Startup - Open tables
        print("\n[PHASE 1] Opening tables...")
        initial_tables = self._ensure_tables()

        if initial_tables == 0:
            print("ERROR: Could not open any tables!")
            print("Make sure GGSystem is running and logged in.")
            return False

        print(f"Opened {initial_tables} table(s)")

        # Phase 2: Play
        print("\n[PHASE 2] Starting autonomous play...")
        print("Press Ctrl+C to stop\n")

        # Start player in background thread
        player_thread = threading.Thread(target=self._player_loop, daemon=True)
        player_thread.start()

        # Main loop - maintenance and monitoring
        try:
            while self.running:
                # Run maintenance
                self._run_maintenance()

                # Update stats from player
                if self._player:
                    status = self._player.get_status()
                    self.total_actions = status.get('total_actions', 0)

                # Status output
                elapsed = time.time() - self.start_time
                tables = self.navigator._count_poker_tables()
                print(f"\r[{elapsed:.0f}s] Tables: {tables}/{self.target_tables} | "
                      f"Actions: {self.total_actions} | "
                      f"Rate: {self.total_actions / (elapsed/60):.1f}/min" + " " * 10,
                      end='', flush=True)

                time.sleep(2)

        except KeyboardInterrupt:
            print("\n\nShutting down...")

        self.running = False

        # Stop player
        if self._player:
            self._player.stop()

        # Wait for player thread
        player_thread.join(timeout=5)

        self._print_final_stats()

        return True

    def _player_loop(self):
        """Player loop running in background thread."""
        while self.running:
            try:
                if self.paused:
                    time.sleep(0.5)
                    continue

                # Run one cycle of the player
                if self._player:
                    self._player.running = True
                    sessions = self._player._capture_all_tables()

                    if sessions:
                        self._player._process_priority_action(sessions)

                time.sleep(0.3)

            except Exception as e:
                log.error(f"Player loop error: {e}")
                time.sleep(1)

    def _print_final_stats(self):
        """Print final session statistics."""
        elapsed = time.time() - self.start_time if self.start_time else 0

        print("\n" + "=" * 70)
        print("SESSION COMPLETE")
        print("=" * 70)
        print(f"Duration: {elapsed/60:.1f} minutes")
        print(f"Tables opened: {self.tables_opened}")
        print(f"Total actions: {self.total_actions}")
        if elapsed > 0:
            print(f"Actions per minute: {self.total_actions / (elapsed/60):.1f}")
        print("=" * 70)

    def stop(self):
        """Stop the bot."""
        self.running = False

    def pause(self):
        """Pause the bot."""
        self.paused = True
        if self._player:
            self._player.pause()

    def resume(self):
        """Resume the bot."""
        self.paused = False
        if self._player:
            self._player.resume()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Master System Utility")
    parser.add_argument("--tables", type=int, default=10, help="Target number of tables")
    parser.add_argument("--stake", type=str, default=None, help="Stake level (e.g., '$1')")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Setup logging
    from sys_core.tools.helper import init_logger
    level = logging.DEBUG if args.verbose else logging.INFO
    init_logger(screenlevel=level, filename='master_bot', logdir='log')

    # Handle Ctrl+C gracefully
    bot = MasterBot(target_tables=args.tables, stake_level=args.stake)

    def signal_handler(sig, frame):
        print("\nReceived interrupt signal...")
        bot.stop()

    signal.signal(signal.SIGINT, signal_handler)

    # Run
    success = bot.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
