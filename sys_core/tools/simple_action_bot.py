#!/usr/bin/env python3
"""
Simple Action Bot - Just monitors for buttons and clicks them.

This is a minimal bot that:
1. Watches all poker tables
2. When action buttons appear, clicks based on simple logic
3. Works alongside the registration bot

Usage:
    python -m sys_core.tools.simple_action_bot

    # Or with specific action preference
    python -m sys_core.tools.simple_action_bot --default fold
    python -m sys_core.tools.simple_action_bot --default call
"""

import logging
import time
import sys
from typing import Optional
from sys_core.tools.dynamic_table_finder import DynamicTableFinder
from sys_core.tools.dynamic_mouse_mover import DynamicMouseMover

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


class SimpleActionBot:
    """Minimal bot that just clicks action buttons."""

    def __init__(self, default_action: str = 'fold'):
        self.finder = DynamicTableFinder()
        self.mover = DynamicMouseMover()
        self.default_action = default_action.lower()
        self.running = False
        self.actions_taken = 0
        self.last_action_time = {}  # Per table cooldown

    def get_action(self, buttons: dict) -> Optional[str]:
        """Decide which action to take based on available buttons."""
        # Priority: Check > Call > Fold
        # But if default is fold, prioritize fold

        if self.default_action == 'fold':
            if 'fold' in buttons:
                return 'Fold'
            elif 'call' in buttons:
                return 'Call'  # Call if no fold (might be check)
        else:
            # More aggressive: prefer call/check
            if 'call' in buttons:
                return 'Call'
            elif 'fold' in buttons:
                return 'Fold'

        return None

    def process_table(self, table, screenshot) -> bool:
        """Process a single table, return True if action taken."""
        table_id = f"{table.x_pt},{table.y_pt}"

        # Cooldown - don't spam clicks
        now = time.time()
        last = self.last_action_time.get(table_id, 0)
        if now - last < 2.0:  # 2 second cooldown per table
            return False

        buttons = self.finder.find_buttons(table, screenshot)

        if not buttons:
            return False

        action = self.get_action(buttons)
        if not action:
            return False

        log.info(f"[{table.name[:30]}] Taking action: {action}")
        log.info(f"  Buttons available: {list(buttons.keys())}")

        # Set current table and click
        self.mover.set_current_table(table)
        self.mover._cached_buttons = buttons
        self.mover.mouse_action(action)

        self.last_action_time[table_id] = now
        self.actions_taken += 1

        return True

    def run(self):
        """Main loop - monitor tables and take actions."""
        log.info("=" * 50)
        log.info("SIMPLE ACTION BOT STARTED")
        log.info(f"Default action: {self.default_action}")
        log.info("=" * 50)

        self.running = True

        try:
            while self.running:
                # Find all poker tables
                tables = self.finder.find_poker_tables()

                if not tables:
                    time.sleep(1)
                    continue

                # Take screenshot once for all tables
                screenshot = self.finder.capture_screenshot()

                # Process each table
                for table in tables:
                    try:
                        self.process_table(table, screenshot)
                    except Exception as e:
                        log.warning(f"Error processing table: {e}")

                # Brief pause between scans
                time.sleep(0.5)

        except KeyboardInterrupt:
            log.info("\nStopping...")

        self.running = False
        log.info(f"Bot stopped. Actions taken: {self.actions_taken}")

    def stop(self):
        self.running = False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Simple Action Bot")
    parser.add_argument("--default", choices=["fold", "call"], default="fold",
                       help="Default action when buttons appear")
    args = parser.parse_args()

    bot = SimpleActionBot(default_action=args.default)
    bot.run()


if __name__ == "__main__":
    main()
