import sys
import os
import json
import signal
import subprocess
import datetime
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QPen, QPainterPath, QFont
from PyQt6.QtCore import QTimer, Qt, QRectF


def _draw_spade(painter: QPainter, cx: float, cy: float, size: float, color: QColor):
    """Draw a spade shape centered at (cx, cy)."""
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)

    s = size / 2.0
    path = QPainterPath()

    top_y = cy - s * 0.9
    lobe_y = cy + s * 0.2

    path.moveTo(cx, top_y)
    path.cubicTo(
        cx - s * 0.1, top_y + s * 0.3,
        cx - s * 1.15, cy - s * 0.2,
        cx - s * 0.5,  lobe_y
    )
    path.cubicTo(
        cx - s * 0.2, lobe_y + s * 0.4,
        cx - s * 0.05, lobe_y + s * 0.15,
        cx, lobe_y
    )
    path.cubicTo(
        cx + s * 0.05, lobe_y + s * 0.15,
        cx + s * 0.2,  lobe_y + s * 0.4,
        cx + s * 0.5,  lobe_y
    )
    path.cubicTo(
        cx + s * 1.15, cy - s * 0.2,
        cx + s * 0.1,  top_y + s * 0.3,
        cx, top_y
    )
    path.closeSubpath()
    painter.drawPath(path)

    stem_top = lobe_y - s * 0.05
    stem_bot = cy + s * 0.85
    tw = s * 0.12
    bw = s * 0.28
    stem = QPainterPath()
    stem.moveTo(cx - tw, stem_top)
    stem.lineTo(cx - bw, stem_bot)
    stem.lineTo(cx + bw, stem_bot)
    stem.lineTo(cx + tw, stem_top)
    stem.closeSubpath()
    painter.drawPath(stem)


def _make_icon(active: bool) -> QIcon:
    """Create a menu bar icon with a spade symbol. 22pt @2x for Retina."""
    sz = 44
    pixmap = QPixmap(sz, sz)
    pixmap.fill(QColor(0, 0, 0, 0))

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    spade_color = QColor(30, 30, 30)
    _draw_spade(p, sz / 2, sz / 2 - 2, sz * 0.65, spade_color)

    if active:
        dot_r = 6
        dot_cx = sz - dot_r - 2
        dot_cy = sz - dot_r - 2
        p.setBrush(QColor(255, 255, 255))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(dot_cx - dot_r - 1, dot_cy - dot_r - 1, (dot_r + 1) * 2, (dot_r + 1) * 2)
        p.setBrush(QColor(52, 199, 89))
        p.drawEllipse(dot_cx - dot_r, dot_cy - dot_r, dot_r * 2, dot_r * 2)

    p.end()
    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)


def _format_uptime(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, _ = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def _format_cards(cards: list) -> str:
    """Format card list like ['AH', 'KS'] -> 'AH KS'."""
    if not cards:
        return "?? ??"
    return " ".join(cards[:2])


def _pnl_indicator(val: float) -> str:
    if val > 0:
        return f"+{val:.1f} BB \u25b2"
    elif val < 0:
        return f"{val:.1f} BB \u25bc"
    return "0.0 BB \u2500"


STOP_FILE = "/tmp/poker_bot_stop"
STATS_PATH = None  # set in __init__
HANDS_PATH = None


class SystemServiceTray:
    def __init__(self):
        sys.stdout.reconfigure(line_buffering=True)

        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.project_root = os.path.dirname(os.path.abspath(__file__))
        os.chdir(self.project_root)

        self.stats_path = os.path.join(self.project_root, "data", "learning", "session_stats.json")
        self.hands_path = os.path.join(self.project_root, "data", "learning", "hand_history.jsonl")

        self._is_running = False
        self._start_time = None
        self._icon_active = _make_icon(active=True)
        self._icon_inactive = _make_icon(active=False)
        self._strategy = 'ev'  # 'ev' or 'deepcfr'

        # Cached data
        self._stats = None
        self._stats_mtime = 0
        self._recent_hands = []
        self._hands_mtime = 0

        # Create tray
        self.tray = QSystemTrayIcon(self._icon_inactive, self.app)
        self.tray.setToolTip("Poker Bot")

        # Build initial menu
        self._build_menu()
        self.tray.show()

        # Process status timer (3s)
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._check_status)
        self.status_timer.start(3000)

        # Stats reload timer (5s)
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._reload_data)
        self.stats_timer.start(5000)

        # Initial checks
        self._check_status()
        self._reload_data()

    def _build_menu(self):
        """Rebuild the entire menu from current state."""
        self.menu = QMenu()

        # --- Status section ---
        self.status_action = self._add_info("Bot: checking...")
        self.uptime_action = self._add_info("")
        self.uptime_action.setVisible(False)

        self.menu.addSeparator()

        # --- Session stats section ---
        self.stats_header = self._add_info("Session Stats")
        self.hands_pnl_action = self._add_info("  No session data")
        self.ev_action = self._add_info("")
        self.ev_action.setVisible(False)
        self.wl_action = self._add_info("")
        self.wl_action.setVisible(False)
        self.biggest_action = self._add_info("")
        self.biggest_action.setVisible(False)

        self.menu.addSeparator()

        # --- Decisions section ---
        self.decisions_header = self._add_info("Decisions")
        self.decisions_action = self._add_info("  --")
        self.decisions_header.setVisible(False)
        self.decisions_action.setVisible(False)

        self.menu.addSeparator()

        # --- Detection health ---
        self.detection_header = self._add_info("Detection Health")
        self.detection_action = self._add_info("  --")
        self.healing_action = self._add_info("  --")
        self.detection_header.setVisible(False)
        self.detection_action.setVisible(False)
        self.healing_action.setVisible(False)

        self.menu.addSeparator()

        # --- Recent hands ---
        self.hands_header = self._add_info("Recent Hands")
        self.hands_header.setVisible(False)
        self.hand_actions = []
        for _ in range(5):
            a = self._add_info("  --")
            a.setVisible(False)
            self.hand_actions.append(a)

        self.menu.addSeparator()

        # --- Strategy switch ---
        self.strategy_header = self._add_info("Strategy")
        self.strategy_ev = QAction("✓ EV Engine (eval7)")
        self.strategy_ev.triggered.connect(lambda: self._set_strategy('ev'))
        self.menu.addAction(self.strategy_ev)
        self.strategy_dcfr = QAction("   Deep CFR (neural net)")
        self.strategy_dcfr.triggered.connect(lambda: self._set_strategy('deepcfr'))
        self.menu.addAction(self.strategy_dcfr)

        self.menu.addSeparator()

        # --- Game info (populated from log) ---
        self.game_header = self._add_info("Table Info")
        self.game_type_action = self._add_info("  --")
        self.game_players_action = self._add_info("  --")
        self.game_position_action = self._add_info("  --")
        self.game_tournament_action = self._add_info("  --")
        self.game_header.setVisible(False)
        self.game_type_action.setVisible(False)
        self.game_players_action.setVisible(False)
        self.game_position_action.setVisible(False)
        self.game_tournament_action.setVisible(False)

        self.menu.addSeparator()

        # --- Controls ---
        self.start_action = QAction("Start Bot")
        self.start_action.triggered.connect(self.start_service)
        self.menu.addAction(self.start_action)

        self.stop_action = QAction("Stop Bot")
        self.stop_action.triggered.connect(self.stop_service)
        self.stop_action.setEnabled(False)
        self.menu.addAction(self.stop_action)

        self.menu.addSeparator()

        log_action = QAction("Open Log...")
        log_action.triggered.connect(self.open_log)
        self.menu.addAction(log_action)

        snapshots_action = QAction("View Hand Snapshots...")
        snapshots_action.triggered.connect(self.open_snapshots)
        self.menu.addAction(snapshots_action)

        self.menu.addSeparator()

        quit_action = QAction("Quit")
        quit_action.triggered.connect(self.quit_app)
        self.menu.addAction(quit_action)

        self.tray.setContextMenu(self.menu)

    def _add_info(self, text: str) -> QAction:
        """Add a disabled (info-only) menu item."""
        action = QAction(text)
        action.setEnabled(False)
        self.menu.addAction(action)
        return action

    # --- Process status ---

    def _is_bot_running(self) -> bool:
        try:
            output = subprocess.check_output(["ps", "aux"], timeout=5).decode()
            lines = [l for l in output.splitlines()
                     if ("sys_core.engine" in l or "sys_core/engine" in l)
                     and "grep" not in l and "sys_tray" not in l]
            return len(lines) > 0
        except Exception:
            return False

    def _check_status(self):
        is_running = self._is_bot_running()

        if is_running and not self._is_running:
            self._start_time = datetime.datetime.now()
        elif not is_running:
            self._start_time = None

        self._is_running = is_running
        self._update_status_display()

    def _update_status_display(self):
        if self._is_running:
            self.tray.setIcon(self._icon_active)
            self.status_action.setText("Bot: Running")
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(True)
            if self._start_time:
                elapsed = datetime.datetime.now() - self._start_time
                self.uptime_action.setText(f"  Uptime: {_format_uptime(elapsed.total_seconds())}")
                self.uptime_action.setVisible(True)
        else:
            self.tray.setIcon(self._icon_inactive)
            self.status_action.setText("Bot: Stopped")
            self.start_action.setEnabled(True)
            self.stop_action.setEnabled(False)
            self.uptime_action.setVisible(False)

        self._update_tooltip()

    # --- Data loading ---

    def _reload_data(self):
        self._load_session_stats()
        self._load_recent_hands()
        self._update_stats_display()
        self._update_hands_display()
        self._update_game_info()
        self._update_tooltip()

    def _load_session_stats(self):
        try:
            mtime = os.path.getmtime(self.stats_path)
            if mtime == self._stats_mtime:
                return
            self._stats_mtime = mtime
            with open(self.stats_path, 'r') as f:
                self._stats = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._stats = None

    def _load_recent_hands(self):
        try:
            mtime = os.path.getmtime(self.hands_path)
            if mtime == self._hands_mtime:
                return
            self._hands_mtime = mtime
            with open(self.hands_path, 'rb') as f:
                # Seek from end to get last ~4KB
                try:
                    f.seek(-4096, 2)
                except OSError:
                    f.seek(0)
                tail = f.read().decode('utf-8', errors='replace')

            lines = tail.strip().split('\n')
            # First line may be partial if we seeked, skip it unless we read from start
            if len(tail) >= 4096 and lines:
                lines = lines[1:]

            hands = []
            for line in lines[-5:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    hands.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            self._recent_hands = hands
        except (FileNotFoundError, OSError):
            self._recent_hands = []

    # --- Display updates ---

    def _update_stats_display(self):
        s = self._stats
        if not s:
            self.hands_pnl_action.setText("  No session data")
            self.ev_action.setVisible(False)
            self.wl_action.setVisible(False)
            self.biggest_action.setVisible(False)
            self.decisions_header.setVisible(False)
            self.decisions_action.setVisible(False)
            self.detection_header.setVisible(False)
            self.detection_action.setVisible(False)
            self.healing_action.setVisible(False)
            return

        # Hands + P&L
        hands = s.get('hands_played', 0)
        pnl = s.get('pnl_bb', 0.0)
        self.hands_pnl_action.setText(f"  Hands: {hands}  |  {_pnl_indicator(pnl)}")

        # EV
        ev = s.get('ev_total', 0.0)
        self.ev_action.setText(f"  EV: {_pnl_indicator(ev)}")
        self.ev_action.setVisible(True)

        # W/L
        won = s.get('hands_won', 0)
        lost = s.get('hands_lost', 0)
        self.wl_action.setText(f"  W/L: {won}/{lost}")
        self.wl_action.setVisible(True)

        # Biggest pots
        big_w = s.get('biggest_pot_won', 0.0)
        big_l = s.get('biggest_pot_lost', 0.0)
        self.biggest_action.setText(f"  Biggest: +{big_w:.0f} / {big_l:.0f} BB")
        self.biggest_action.setVisible(True)

        # Decisions
        d = s.get('decisions', {})
        parts = []
        for key in ['fold', 'call', 'check', 'raise', 'bet']:
            val = d.get(key, 0)
            if val > 0:
                parts.append(f"{key.title()}: {val}")
        if parts:
            self.decisions_header.setVisible(True)
            self.decisions_action.setText(f"  {' | '.join(parts)}")
            self.decisions_action.setVisible(True)

        # Detection health
        det = s.get('detection_success', {})
        rates = s.get('detection_rates', {})
        btn_rate = rates.get('button_success_rate', 0)
        card_rate = rates.get('card_success_rate', 0)

        self.detection_header.setVisible(True)
        self.detection_action.setText(f"  Buttons: {btn_rate:.0%}  Cards: {card_rate:.0%}")
        self.detection_action.setVisible(True)

        heal = s.get('self_healing', {})
        triggered = heal.get('triggered', 0)
        healed = heal.get('success', 0)
        if triggered > 0:
            self.healing_action.setText(f"  Self-heal: {triggered} triggered, {healed} fixed")
            self.healing_action.setVisible(True)
        else:
            self.healing_action.setVisible(False)

    def _update_hands_display(self):
        if not self._recent_hands:
            self.hands_header.setVisible(False)
            for a in self.hand_actions:
                a.setVisible(False)
            return

        self.hands_header.setVisible(True)
        for i, a in enumerate(self.hand_actions):
            if i < len(self._recent_hands):
                h = self._recent_hands[-(i + 1)]  # most recent first
                cards = _format_cards(h.get('cards', []))
                pos = h.get('pos', '??')
                dec = h.get('decision', '??')
                ev = h.get('ev', 0.0)
                ev_str = f"+{ev:.1f}" if ev > 0 else f"{ev:.1f}"
                a.setText(f"  {cards}  {pos:<3}  {dec:<10}  {ev_str} BB")
                a.setVisible(True)
            else:
                a.setVisible(False)

    def _set_strategy(self, strategy: str):
        """Switch between EV Engine and Deep CFR."""
        self._strategy = strategy
        if strategy == 'ev':
            self.strategy_ev.setText("✓ EV Engine (eval7)")
            self.strategy_dcfr.setText("   Deep CFR (neural net)")
        else:
            self.strategy_ev.setText("   EV Engine (eval7)")
            self.strategy_dcfr.setText("✓ Deep CFR (neural net)")
        # If bot is running, restart with new strategy
        if self._is_running:
            self.stop_service()
            QTimer.singleShot(2000, self.start_service)

    def _update_game_info(self):
        """Read latest game info from log."""
        try:
            log_path = os.path.join(self.project_root, "log", "multi_table.log")
            if not os.path.exists(log_path):
                return
            with open(log_path, 'r') as f:
                lines = f.readlines()[-200:]  # last 200 lines

            game_type = ''
            players = ''
            position = ''
            tournament = ''

            for line in reversed(lines):
                if 'game=' in line and not game_type:
                    # Extract game type
                    idx = line.find('game=')
                    if idx >= 0:
                        gt = line[idx+5:].split()[0].split('|')[0].strip()
                        game_type = gt.upper()

                if 'TOURNEY:' in line and not tournament:
                    idx = line.find('TOURNEY:')
                    tournament = line[idx:].split('|')[0].strip()

                if 'pos=' in line and not position:
                    idx = line.find('pos=')
                    if idx >= 0:
                        position = line[idx+4:].split()[0].split('|')[0].strip()

                if 'opp=' in line and not players:
                    idx = line.find('opp=')
                    if idx >= 0:
                        try:
                            opp = int(line[idx+4:].split()[0].split('|')[0].strip())
                            players = f"{opp + 1} players ({opp} opponents)"
                        except ValueError:
                            pass

                if 'Detected window:' in line:
                    # Extract tournament name
                    w = line.split('Detected window:')[1].strip().split('(')[0].strip()
                    if 'Bounty' in w:
                        game_type = 'BOUNTY TOURNAMENT'
                    elif 'Hyper' in w:
                        game_type = 'HYPER TOURNAMENT'
                    elif 'Spin' in w or 'Gold' in w:
                        game_type = 'SPIN & GO'
                    elif 'Rush' in w and 'Cash' in w:
                        game_type = 'CASH (Rush & Cash)'
                    break  # Window name is most reliable

            if game_type or players or position or tournament:
                self.game_header.setVisible(True)
                if game_type:
                    self.game_type_action.setText(f"  Type: {game_type}")
                    self.game_type_action.setVisible(True)
                if players:
                    self.game_players_action.setText(f"  {players}")
                    self.game_players_action.setVisible(True)
                if position:
                    self.game_position_action.setText(f"  Position: {position}")
                    self.game_position_action.setVisible(True)
                if tournament:
                    self.game_tournament_action.setText(f"  {tournament}")
                    self.game_tournament_action.setVisible(True)
        except Exception:
            pass

    def _update_tooltip(self):
        if not self._is_running:
            self.tray.setToolTip("Poker Bot - Stopped")
            return

        parts = ["\u2660"]  # spade
        if self._stats:
            pnl = self._stats.get('pnl_bb', 0.0)
            hands = self._stats.get('hands_played', 0)
            pnl_str = f"+{pnl:.1f}" if pnl > 0 else f"{pnl:.1f}"
            parts.append(f"{pnl_str} BB")
            parts.append(f"{hands} hands")
        if self._start_time:
            elapsed = (datetime.datetime.now() - self._start_time).total_seconds()
            parts.append(_format_uptime(elapsed))
        self.tray.setToolTip(" | ".join(parts))

    # --- Actions ---

    def start_service(self):
        # Remove any leftover stop file
        try:
            os.remove(STOP_FILE)
        except FileNotFoundError:
            pass

        # Start with selected strategy
        strategy_flag = f"--strategy {self._strategy}" if self._strategy != 'ev' else ""
        run_script = os.path.join(self.project_root, "run_sys.sh")
        env = os.environ.copy()
        env['BOT_STRATEGY'] = self._strategy
        subprocess.Popen(["bash", run_script], cwd=self.project_root,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=env)
        strategy_label = "EV Engine" if self._strategy == 'ev' else "Deep CFR"
        self.status_action.setText(f"Bot: Starting ({strategy_label})...")
        self.start_action.setEnabled(False)
        QTimer.singleShot(2000, self._check_status)

    def stop_service(self):
        self.status_action.setText("Bot: Stopping...")
        self.stop_action.setEnabled(False)

        # Step 1: Graceful stop via stop file (engine checks this)
        try:
            with open(STOP_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except OSError:
            pass

        # Step 2: Poll for exit, then force kill after 4s
        self._stop_poll_count = 0
        self._stop_timer = QTimer()
        self._stop_timer.timeout.connect(self._poll_stop)
        self._stop_timer.start(500)

    def _poll_stop(self):
        self._stop_poll_count += 1

        if not self._is_bot_running():
            # Stopped gracefully
            self._stop_timer.stop()
            self._cleanup_stop()
            self._check_status()
            return

        if self._stop_poll_count >= 8:  # 4 seconds elapsed
            # Force kill as last resort
            self._stop_timer.stop()
            try:
                output = subprocess.check_output(["ps", "aux"], timeout=5).decode()
                for line in output.splitlines():
                    if ("sys_core.engine" in line or "sys_core/engine" in line) \
                            and "grep" not in line and "sys_tray" not in line:
                        pid = int(line.split()[1])
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
            except Exception:
                pass

            # Give SIGTERM 1s, then SIGKILL
            QTimer.singleShot(1000, self._force_kill_remaining)

    def _force_kill_remaining(self):
        if self._is_bot_running():
            try:
                output = subprocess.check_output(["ps", "aux"], timeout=5).decode()
                for line in output.splitlines():
                    if ("sys_core.engine" in line or "sys_core/engine" in line) \
                            and "grep" not in line and "sys_tray" not in line:
                        pid = int(line.split()[1])
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
            except Exception:
                pass
        self._cleanup_stop()
        self._check_status()

    def _cleanup_stop(self):
        try:
            os.remove(STOP_FILE)
        except FileNotFoundError:
            pass

    def open_snapshots(self):
        snap_dir = os.path.join(self.project_root, "data", "learning", "hand_snapshots")
        os.makedirs(snap_dir, exist_ok=True)
        subprocess.Popen(["open", snap_dir])

    def open_log(self):
        log_path = os.path.join(self.project_root, "log", "multi_table.log")
        if not os.path.exists(log_path):
            for name in ["dm_assistant.log", "engine.log"]:
                alt = os.path.join(self.project_root, "log", name)
                if os.path.exists(alt):
                    log_path = alt
                    break
        subprocess.Popen(["open", "-a", "Console", log_path])

    def quit_app(self):
        self.tray.hide()
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    tray = SystemServiceTray()
    tray.run()
