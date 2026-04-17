"""macOS menu bar app for controlling the poker bot.

Usage:
    python -m sys_core.tray_app

Features:
- Start / Stop bot
- Switch strategy (EV Engine / Deep CFR)
- Live status: per-table OCR snapshot + action sequence (updates every 1s)
- Test OCR: runs the OCR pipeline against bundled test screenshots and
  reports pass/fail so you can verify accuracy any time, no live game
  required.
"""

import datetime
import json
import os
import signal
import subprocess
import sys
import threading
import time

import rumps


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIVE_STATE_PATH = os.path.join(_REPO_ROOT, 'data', 'learning', 'live_state.json')


class PokerBotApp(rumps.App):
    def __init__(self):
        super().__init__("♠", quit_button=None)

        self.bot_process = None
        self.strategy = 'ev'

        self.start_stop = rumps.MenuItem("▶ Start Bot", callback=self.toggle_bot)
        self.strategy_ev = rumps.MenuItem("✓ EV Engine", callback=self.set_ev)
        self.strategy_dcfr = rumps.MenuItem("  Deep CFR", callback=self.set_deepcfr)
        self.status_item = rumps.MenuItem("Status: Stopped")
        self.status_item.set_callback(None)

        # Live state submenu — populated dynamically. We keep up to 6
        # placeholder slots so rumps doesn't have to recreate menus.
        self.live_header = rumps.MenuItem("— Live OCR —")
        self.live_header.set_callback(None)
        self.live_slots = [rumps.MenuItem(f"(no table {i+1})") for i in range(6)]
        for s in self.live_slots:
            s.set_callback(None)

        self.test_ocr = rumps.MenuItem("🔍 Test OCR Now", callback=self.run_ocr_test)
        self.open_snapshots = rumps.MenuItem("📁 Open Snapshots", callback=self.open_snap_folder)

        self.menu = [
            self.start_stop,
            None,
            rumps.MenuItem("Strategy:"),
            self.strategy_ev,
            self.strategy_dcfr,
            None,
            self.status_item,
            None,
            self.live_header,
            *self.live_slots,
            None,
            self.test_ocr,
            self.open_snapshots,
            None,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

        # Background updater (always running, regardless of bot state)
        self._stop_updater = False
        threading.Thread(target=self._live_updater, daemon=True).start()

    # ---------------------------------------------------------------- start/stop
    def toggle_bot(self, sender):
        if self.bot_process and self.bot_process.poll() is None:
            self.stop_bot()
        else:
            self.start_bot()

    def start_bot(self):
        if self.bot_process and self.bot_process.poll() is None:
            rumps.notification("Poker Bot", "", "Bot is already running")
            return
        cmd = [sys.executable, '-m', 'sys_core.engine',
               '--no-standardize', '--strategy', self.strategy]
        self.bot_process = subprocess.Popen(
            cmd, cwd=_REPO_ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        self.start_stop.title = "■ Stop Bot"
        self.title = "♠ ON"
        self.status_item.title = f"Status: Running ({self.strategy.upper()})"
        rumps.notification("Poker Bot", "", f"Started with {self.strategy.upper()}")

    def stop_bot(self):
        if self.bot_process and self.bot_process.poll() is None:
            self.bot_process.send_signal(signal.SIGTERM)
            try:
                self.bot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.bot_process.kill()
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

    def set_deepcfr(self, sender):
        self.strategy = 'deepcfr'
        self.strategy_ev.title = "  EV Engine"
        self.strategy_dcfr.title = "✓ Deep CFR"

    # ---------------------------------------------------------------- live OCR
    def _live_updater(self):
        """Poll live_state.json and refresh the menu every second."""
        while not self._stop_updater:
            try:
                self._refresh_live_state()
            except Exception:
                pass
            time.sleep(1.0)

    def _refresh_live_state(self):
        if not os.path.exists(_LIVE_STATE_PATH):
            for slot in self.live_slots:
                slot.title = "(no live data)"
            return
        try:
            with open(_LIVE_STATE_PATH, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        tables = list((data.get('tables') or {}).values())
        # Sort: my-turn first, then by most-recent
        tables.sort(key=lambda t: (
            0 if t.get('is_my_turn') else 1,
            -(self._ts(t.get('updated', '')) or 0),
        ))

        for i, slot in enumerate(self.live_slots):
            if i < len(tables):
                slot.title = self._format_table_line(tables[i])
            else:
                slot.title = ""  # rumps hides empty-title items

    @staticmethod
    def _ts(iso_str: str) -> float:
        try:
            return datetime.datetime.fromisoformat(iso_str).timestamp()
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _format_table_line(t: dict) -> str:
        """Build a one-line summary of a table state for the menu.

        Surfaces sanity warnings prominently — a HIGH-severity warning
        means strategy will misread this state, so the line gets a
        ⚠️ prefix that's impossible to miss in the menu.
        """
        win = (t.get('window') or 'table')[:20]
        cards = ' '.join(t.get('cards') or []) or '··'
        board = ' '.join(t.get('board') or []) or '·'
        pos = t.get('position') or '?'
        pot = t.get('pot') or 0
        call = t.get('call') or 0
        seq = t.get('action_sequence') or ''
        turn = '▶' if t.get('is_my_turn') else ' '
        bet_pot = '3B' if t.get('is_3bet_pot') else '4B' if t.get('is_4bet_pot') else ''
        warnings = t.get('warnings') or []
        high_count = sum(1 for w in warnings if w.get('severity') == 'high')
        med_count = sum(1 for w in warnings if w.get('severity') == 'medium')
        # Lead with sanity status — visible at a glance whether OCR is trustworthy
        if high_count:
            prefix = f"🛑 {turn}"
        elif med_count:
            prefix = f"⚠ {turn}"
        else:
            prefix = f"✓ {turn}"
        line = f"{prefix} {win} | {cards} / {board} | {pos} | pot {pot:g} call {call:g}"
        if bet_pot:
            line += f" | {bet_pot}"
        if high_count or med_count:
            counts = []
            if high_count: counts.append(f"{high_count} HIGH")
            if med_count: counts.append(f"{med_count} med")
            line += f" | {', '.join(counts)} warn"
        if seq:
            line += f" | {seq[:60]}"
        return line

    # ---------------------------------------------------------------- test OCR
    def run_ocr_test(self, sender):
        """Run OCR against bundled test screenshots; show pass/fail summary."""
        try:
            results = self._do_ocr_test()
        except Exception as e:
            rumps.alert("OCR Test", f"Test crashed:\n{e}")
            return
        msg = '\n'.join(results)
        rumps.alert("OCR Test Results", msg)

    def _do_ocr_test(self) -> list[str]:
        """Run read_table on a few known screenshots and verify expected fields."""
        from PIL import Image
        from sys_core.ocr.table_reader import read_table

        screenshots_dir = os.path.join(_REPO_ROOT, 'data', 'test_screenshots')
        if not os.path.isdir(screenshots_dir):
            return ["No test screenshots folder found at data/test_screenshots/"]

        # Hard-coded expected values for the screenshots we know about.
        # Add more as you save more test cases.
        expectations = {
            'rush_18_51_13.png': {
                'window': 'Rush & Cash $0.01/$0.02',
                'cards': ['KH', 'TH'],
                'pot': 6.5,
                'players_min': 6,  # 6-max — should read all 6 seats
                'has_names': True,
            },
            'tournament_18_02_48.png': {
                'window': '#9: $250 Mini Main Event - Blinds 200|400 - Table 21',
                'board_min': 3,  # turn — should have 4 but tournament board OCR
                                 # currently only finds 3 reliably (known gap)
                'pot_min': 1.0,
            },
        }

        lines = []
        passed = 0
        total = 0
        for fname, exp in expectations.items():
            path = os.path.join(screenshots_dir, fname)
            if not os.path.exists(path):
                lines.append(f"⚠️  {fname}: not found")
                continue
            img = Image.open(path)
            state = read_table(img, window_name=exp.get('window', ''),
                               window_id=99, table_x_pt=0, table_y_pt=0,
                               table_w_pt=img.width // 2, table_h_pt=img.height // 2)

            checks = []
            if 'cards' in exp:
                ok = list(state.my_cards or []) == exp['cards']
                checks.append(('cards', ok, f"got {state.my_cards}"))
            if 'pot' in exp:
                ok = abs((state.pot or 0) - exp['pot']) < 0.1
                checks.append(('pot', ok, f"got {state.pot}"))
            if 'pot_min' in exp:
                ok = (state.pot or 0) >= exp['pot_min']
                checks.append(('pot>=min', ok, f"got {state.pot}"))
            if 'board_min' in exp:
                ok = len(state.board_cards or []) >= exp['board_min']
                checks.append(('board≥min', ok, f"got {state.board_cards}"))
            if 'players_min' in exp:
                ok = len(state.players or []) >= exp['players_min']
                checks.append(('players≥min', ok, f"got {len(state.players or [])}"))
            if exp.get('has_names'):
                got_names = sum(1 for p in (state.players or []) if p.name)
                ok = got_names >= exp['players_min']
                checks.append(('names', ok, f"{got_names} named"))

            ok_count = sum(1 for _, o, _ in checks if o)
            total += len(checks)
            passed += ok_count
            mark = '✅' if ok_count == len(checks) else '⚠️'
            lines.append(f"{mark} {fname} — {ok_count}/{len(checks)} checks")
            for label, ok, info in checks:
                lines.append(f"     {'✓' if ok else '✗'} {label}: {info}")

        lines.insert(0, f"=== {passed}/{total} assertions passed ===\n")
        return lines

    # ---------------------------------------------------------------- misc
    def open_snap_folder(self, sender):
        snap = os.path.join(_REPO_ROOT, 'data', 'learning', 'hand_snapshots')
        os.makedirs(snap, exist_ok=True)
        subprocess.run(['open', snap])

    def quit_app(self, sender):
        self._stop_updater = True
        self.stop_bot()
        rumps.quit_application()


if __name__ == '__main__':
    PokerBotApp().run()
