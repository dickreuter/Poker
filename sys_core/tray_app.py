"""macOS menu bar app for controlling the poker bot.

Usage:
    python -m sys_core.tray_app

Shows a poker chip icon (♠) in the menu bar with controls for:
- Start / Stop bot
- Switch strategy (EV Engine / Deep CFR)
- See current status (tables, hands played)
"""

import rumps
import subprocess
import signal
import os
import sys
import threading
import time


class PokerBotApp(rumps.App):
    def __init__(self):
        super().__init__("♠", quit_button=None)

        self.bot_process = None
        self.strategy = 'ev'
        self.hands_played = 0
        self.tables_found = 0

        # Menu items
        self.start_stop = rumps.MenuItem("▶ Start Bot", callback=self.toggle_bot)
        self.strategy_ev = rumps.MenuItem("✓ EV Engine", callback=self.set_ev)
        self.strategy_dcfr = rumps.MenuItem("  Deep CFR", callback=self.set_deepcfr)
        self.status_item = rumps.MenuItem("Status: Stopped")
        self.status_item.set_callback(None)

        self.menu = [
            self.start_stop,
            None,  # separator
            rumps.MenuItem("Strategy:"),
            self.strategy_ev,
            self.strategy_dcfr,
            None,
            self.status_item,
            None,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

        # Monitor thread
        self._monitor = None

    def toggle_bot(self, sender):
        if self.bot_process and self.bot_process.poll() is None:
            self.stop_bot()
        else:
            self.start_bot()

    def start_bot(self):
        if self.bot_process and self.bot_process.poll() is None:
            rumps.notification("Poker Bot", "", "Bot is already running")
            return

        cmd = [
            sys.executable, '-m', 'sys_core.engine',
            '--no-standardize',
            '--strategy', self.strategy,
        ]

        self.bot_process = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        self.start_stop.title = "■ Stop Bot"
        self.title = "♠ ON"
        self.status_item.title = f"Status: Running ({self.strategy.upper()})"
        rumps.notification("Poker Bot", "", f"Started with {self.strategy.upper()} strategy")

        # Start monitoring
        self._monitor = threading.Thread(target=self._monitor_bot, daemon=True)
        self._monitor.start()

    def stop_bot(self):
        if self.bot_process and self.bot_process.poll() is None:
            self.bot_process.send_signal(signal.SIGTERM)
            try:
                self.bot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.bot_process.kill()

        # Also kill any other instances
        subprocess.run(['pkill', '-f', 'sys_core.engine'], capture_output=True)

        self.bot_process = None
        self.start_stop.title = "▶ Start Bot"
        self.title = "♠"
        self.status_item.title = "Status: Stopped"
        rumps.notification("Poker Bot", "", "Bot stopped")

    def set_ev(self, sender):
        self.strategy = 'ev'
        self.strategy_ev.title = "✓ EV Engine"
        self.strategy_dcfr.title = "  Deep CFR"

        # Restart if running
        if self.bot_process and self.bot_process.poll() is None:
            self.stop_bot()
            time.sleep(1)
            self.start_bot()
        else:
            rumps.notification("Poker Bot", "", "Strategy: EV Engine (will apply on next start)")

    def set_deepcfr(self, sender):
        self.strategy = 'deepcfr'
        self.strategy_ev.title = "  EV Engine"
        self.strategy_dcfr.title = "✓ Deep CFR"

        # Restart if running
        if self.bot_process and self.bot_process.poll() is None:
            self.stop_bot()
            time.sleep(1)
            self.start_bot()
        else:
            rumps.notification("Poker Bot", "", "Strategy: Deep CFR (will apply on next start)")

    def _monitor_bot(self):
        """Monitor bot process and update status."""
        while self.bot_process and self.bot_process.poll() is None:
            try:
                # Read log for stats
                log_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'log', 'multi_table.log'
                )
                if os.path.exists(log_path):
                    with open(log_path, 'r') as f:
                        lines = f.readlines()
                        decisions = sum(1 for l in lines if 'DECISION' in l)
                        tables = 0
                        for l in reversed(lines[-50:]):
                            if 'Found' in l and 'poker tables' in l:
                                try:
                                    tables = int(l.split('Found')[1].split('poker')[0].strip())
                                except:
                                    pass
                                break
                        self.status_item.title = f"Status: {decisions} hands | {tables} tables | {self.strategy.upper()}"
            except:
                pass
            time.sleep(5)

        # Bot exited
        self.start_stop.title = "▶ Start Bot"
        self.title = "♠"
        self.status_item.title = "Status: Stopped (bot exited)"

    def quit_app(self, sender):
        self.stop_bot()
        rumps.quit_application()


if __name__ == '__main__':
    PokerBotApp().run()
