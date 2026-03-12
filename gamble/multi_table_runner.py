"""
UNIFIED AUTONOMOUS MULTI-TABLE BOT

This is the ONE bot that combines:
1. ORIGINAL bot's COMPLETE logic (25+ checks, full history, preflop learning)
2. Multi-table orchestration (handle 10 tables)
3. Self-learning/healing (auto-fix detection failures)
4. Window standardization (resize/tile for consistent detection)

Based on https://github.com/dickreuter/Poker - we IMPROVE on the original, not replace it.

Architecture:
    multi_table_runner.py (THIS FILE)
           │
           ├── Finds all poker windows via AppleScript
           ├── Resizes/tiles windows for consistent detection
           ├── Creates TableSession for each window
           ├── Prioritizes tables by urgency
           │
           ├── For each table, uses ORIGINAL bot components:
           │   ├── scraper/table_screen_based.py (full 25+ checks)
           │   ├── decisionmaker/decisionmaker.py (equity + strategy)
           │   └── tools/mouse_mover.py (click execution)
           │
           └── Self-learning layer:
               ├── adaptive_learner.py (logs actions, tracks stats)
               ├── vision_analyzer.py (auto-fixes detection)
               └── self_healer.py (real-time healing)
"""

import datetime
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from copy import copy

import numpy as np
import pandas as pd
from PIL import ImageGrab

# Original bot imports
from gamble.decisionmaker.current_hand_memory import CurrentHandPreflopState, History
from gamble.decisionmaker.decisionmaker import Decision
from gamble.decisionmaker.montecarlo_python import run_montecarlo_wrapper
from gamble.gui.action_and_signals import StrategyHandler
from gamble.scraper.table_screen_based import TableScreenBased
from gamble.tools.game_logger import GameLogger
from gamble.tools.helper import init_logger, get_config
from gamble.tools.mongo_manager import MongoManager
from gamble.tools.mouse_mover import MouseMoverTableBased

# Self-learning imports
try:
    from gamble.tools.adaptive_learner import log_action, get_threshold, get_learner, set_threshold, report_issue, save_debug_screenshot
    ADAPTIVE_LEARNER_AVAILABLE = True
except ImportError:
    ADAPTIVE_LEARNER_AVAILABLE = False
    def log_action(*args, **kwargs): pass
    def get_threshold(name, default): return default
    def set_threshold(*args, **kwargs): pass
    def get_learner(): return None
    def report_issue(*args, **kwargs): pass
    def save_debug_screenshot(*args, **kwargs): pass

try:
    from gamble.tools.vision_analyzer import auto_fix_buttons, auto_fix_cards
    VISION_ANALYZER_AVAILABLE = True
except ImportError:
    VISION_ANALYZER_AVAILABLE = False
    def auto_fix_buttons(img): return {'fixed': False}
    def auto_fix_cards(img): return {'fixed': False}

try:
    from gamble.tools.self_healer import get_healer
    SELF_HEALER_AVAILABLE = True
except ImportError:
    SELF_HEALER_AVAILABLE = False
    def get_healer(): return None

# Lobby navigation
try:
    from gamble.tools.dynamic_lobby_navigator import DynamicLobbyNavigator
    LOBBY_NAV_AVAILABLE = True
except ImportError:
    LOBBY_NAV_AVAILABLE = False

# Opponent modeling
try:
    from gamble.decisionmaker.opponent_modeler import get_modeler as get_opponent_modeler
    OPPONENT_MODELER_AVAILABLE = True
except ImportError:
    OPPONENT_MODELER_AVAILABLE = False
    def get_opponent_modeler(): return None

# Rust OCR bridge
try:
    from gamble.ocr.rust_bridge import RustOCRBridge
    from gamble.ocr.game_state import GameState
    RUST_OCR_AVAILABLE = True
except ImportError:
    RUST_OCR_AVAILABLE = False

# Python OCR pipeline (table_reader)
try:
    from gamble.ocr.table_reader import read_table, _detect_buttons
    from gamble.ocr.game_state import GameState, AvailableAction
    PYTHON_OCR_AVAILABLE = True
except ImportError:
    PYTHON_OCR_AVAILABLE = False

# Local table config (replaces MongoDB dependency)
try:
    from gamble.ocr.local_table_config import build_local_table_dict
    LOCAL_TABLE_CONFIG_AVAILABLE = True
except ImportError:
    LOCAL_TABLE_CONFIG_AVAILABLE = False

# Template collector (auto-captures real card templates during play)
try:
    from gamble.ocr.template_collector import get_collector as get_template_collector
    TEMPLATE_COLLECTOR_AVAILABLE = True
except ImportError:
    TEMPLATE_COLLECTOR_AVAILABLE = False
    def get_template_collector(): return None

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False


# Preflop sheet loading
try:
    from gamble.tools.update_checker import UpdateChecker
    UPDATE_CHECKER_AVAILABLE = True
except ImportError:
    UPDATE_CHECKER_AVAILABLE = False

log = logging.getLogger(__name__)


class SpotTracker:
    """Track win/loss by decision type for live threshold tuning.

    Categories: preflop_call, preflop_raise, postflop_call, postflop_bet,
    cbet, bluff, check_raise, value_bet, fold
    """

    def __init__(self):
        self._spots = {}  # {category: {'wins': 0, 'losses': 0, 'total_bb': 0.0}}
        self._adj = {}    # {param_name: offset_value}

    def record(self, category, won, bb_delta):
        """Record outcome for a decision category."""
        if category not in self._spots:
            self._spots[category] = {'wins': 0, 'losses': 0, 'total_bb': 0.0}
        s = self._spots[category]
        if won:
            s['wins'] += 1
        else:
            s['losses'] += 1
        s['total_bb'] += bb_delta

    def get_win_rate(self, category):
        """Get win rate for a category. Returns None if < 10 samples."""
        s = self._spots.get(category)
        if not s or (s['wins'] + s['losses']) < 10:
            return None
        total = s['wins'] + s['losses']
        return s['wins'] / total

    def get_bb_per_spot(self, category):
        """Get avg BB won/lost per spot. Returns None if < 10 samples."""
        s = self._spots.get(category)
        if not s or (s['wins'] + s['losses']) < 10:
            return None
        total = s['wins'] + s['losses']
        return s['total_bb'] / total

    def compute_adjustments(self):
        """Compute live strategy adjustments from spot results.

        Returns a dict of offset adjustments that the decision maker
        should apply. Positive = tighter (need more equity), negative = looser.
        """
        adj = {}

        # If postflop calls are losing money, tighten calling threshold
        call_bb = self.get_bb_per_spot('postflop_call')
        if call_bb is not None:
            if call_bb < -0.5:
                adj['call_equity_offset'] = 0.03  # Need 3% more equity to call
            elif call_bb < -0.2:
                adj['call_equity_offset'] = 0.01
            elif call_bb > 0.3:
                adj['call_equity_offset'] = -0.02  # Can call lighter

        # If c-bets are losing, reduce frequency
        cbet_bb = self.get_bb_per_spot('cbet')
        if cbet_bb is not None:
            if cbet_bb < -0.3:
                adj['cbet_freq_offset'] = -0.10
            elif cbet_bb > 0.2:
                adj['cbet_freq_offset'] = 0.05

        # If bluffs are losing, tighten bluff threshold
        bluff_bb = self.get_bb_per_spot('bluff')
        if bluff_bb is not None:
            if bluff_bb < -0.5:
                adj['bluff_fold_eq_offset'] = 0.05  # Need more fold equity
            elif bluff_bb > 0.1:
                adj['bluff_fold_eq_offset'] = -0.03

        # If preflop calls are losing, tighten preflop
        pf_call_bb = self.get_bb_per_spot('preflop_call')
        if pf_call_bb is not None:
            if pf_call_bb < -0.3:
                adj['preflop_call_offset'] = 0.02
            elif pf_call_bb > 0.2:
                adj['preflop_call_offset'] = -0.01

        self._adj = adj
        return adj

    def get_adjustment(self, param_name, default=0.0):
        """Get a specific adjustment value."""
        return self._adj.get(param_name, default)

    def summary(self):
        """Return summary string for logging."""
        parts = []
        for cat, s in sorted(self._spots.items()):
            total = s['wins'] + s['losses']
            if total == 0:
                continue
            wr = s['wins'] / total * 100
            bb = s['total_bb']
            parts.append(f"{cat}: {wr:.0f}%W ({bb:+.1f}BB, n={total})")
        return ' | '.join(parts) if parts else 'no data yet'


class MockSignalsMC:
    """Mock signals for montecarlo that handles chained attribute access like signal_status.emit()"""
    def __getattr__(self, name):
        # Return self for any attribute access to handle chaining
        return self

    def __call__(self, *args, **kwargs):
        # Make it callable for signal emit
        return None

    def emit(self, *args, **kwargs):
        # Handle explicit .emit() calls
        pass


class TableState(Enum):
    """State of each table"""
    UNKNOWN = "unknown"
    WAITING = "waiting"           # Not my turn
    NEED_ACTION = "need_action"   # Buttons visible, my turn
    HAND_OVER = "hand_over"       # Hand finished
    CLOSED = "closed"             # Window closed


@dataclass
class TableWindow:
    """Represents a detected poker table window"""
    window_id: int
    name: str
    x: int  # Position in POINTS
    y: int
    width: int
    height: int

    @property
    def bounds_pixels(self) -> Tuple[int, int, int, int]:
        """Return bounds in PIXELS for screenshot cropping (Retina 2x)"""
        return (self.x * 2, self.y * 2,
                (self.x + self.width) * 2, (self.y + self.height) * 2)


@dataclass
class TableSession:
    """Session state for ONE poker table - wraps original bot components"""
    window: TableWindow
    table_dict: dict
    history: History = field(default_factory=History)
    preflop_state: CurrentHandPreflopState = field(default_factory=CurrentHandPreflopState)
    game_logger: GameLogger = field(default_factory=GameLogger)
    state: TableState = TableState.UNKNOWN
    last_action_time: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    priority: int = 0  # Higher = more urgent

    # Original bot components (created on first use)
    _table: Optional[TableScreenBased] = None
    _mouse: Optional[MouseMoverTableBased] = None
    _cached_game_state: Optional[object] = None  # GameState from check, reused by process
    _last_acted_key: str = ""  # "cards|board_count" — prevents acting twice on same street

    # Bayesian range tracking (beyond-GTO exploitative engine)
    _bayesian_villain_range: Optional[dict] = None
    _bayesian_last_street: str = ""  # Prevents re-narrowing same street


class MultiTableRunner:
    """
    Main orchestrator for autonomous multi-table play.

    This class manages concurrent poker sessions by wrapping the core decision-making
    and OCR logic in a high-performance orchestration layer.

    OPTIMIZATIONS FOR MULTI-TABLING:
    1. Single-Screenshot "Fast Scans":
       Instead of capturing each table individually (high I/O), the bot takes one 
       full-screen grab and crops it for "Deal Me In" buttons.
    2. Parallel OCR Pipeline:
       Uses ThreadPoolExecutor to run GameState detection on all active tables 
       simultaneously, reducing the "time-to-decision" under load.
    3. Priority-Based Execution:
       Tables with visible action buttons are prioritized (higher Priority score).
       Urgent decisions (shoves, low time banks) are processed before passive ones.
    4. Window Normalization:
       Standardizes window sizes via AppleScript to ensure consistent percentage-based 
       OCR regions regardless of initial table scaling.
    5. Differential Processing:
       Only triggers expensive board/card OCR if action buttons (our turn) are detected.
    """

    def __init__(self,
                 max_tables: int = 10,
                 target_tables: int = 1,
                 table_scraper_name: str = "Official GGPoker 6player",
                 dry_run: bool = False):
        self.max_tables = max_tables
        self.target_tables = target_tables
        self.table_scraper_name = table_scraper_name
        self.dry_run = dry_run

        self.sessions: Dict[int, TableSession] = {}  # window_id -> session
        self._last_tile_time = 0  # Grid Lockdown Timer
        self.running = False

        # Bankroll protection (Phase 5)
        self._session_rebuys = 0
        self._max_session_rebuys = 10
        self._buyins_lost = 0
        self._max_buyins_loss = 8  # 8 buy-ins = reasonable for Rush & Cash variance

        # Standard table size for consistent detection (must be set before table config)
        # GGPoker enforces minimum 850x615pt — can't go smaller.
        # Screen is 1710x1112pt.  2 cols × 2 rows with 118pt overlap between rows.
        self.standard_width = 855
        self.standard_height = 615
        self.tile_columns = 2
        self.tile_y_offset = 0  # Start at very top to maximize vertical space
        # Row spacing: 1112 - 615 = 497pt between row starts (bottom row flush with screen edge)
        self.tile_row_height = 497

        # Original bot components
        self.strategy = StrategyHandler()
        self.strategy.read_strategy()

        # Override strategy for Rush & Cash 6-max GTO:
        # GGPoker displays ALL values in BB units (pot, stacks, call/raise amounts).
        # Set bigBlind=1.0 so strategy math stays consistent with displayed values.
        s = self.strategy.selected_strategy
        s['bigBlind'] = 1.0  # Everything is in BB units on screen
        s['smallBlind'] = 0.5
        s['initialFunds'] = 100.0   # 100 BB buyin (max call limit)
        s['initialFunds2'] = 100.0  # 100 BB buyin (max bet limit)

        # === PREFLOP ===
        # GTO 6-max: open ~40% of hands from BTN, ~25% from UTG.
        # These are minimum equity thresholds AFTER position adjustments.
        s['PreFlopMinCallEquity'] = 0.17   # Call with 17%+ equity (defend wider)
        s['PreFlopMinBetEquity'] = 0.22    # Raise with 22%+ equity (open wider)
        s['PreFlopMaxBetEquity'] = 1.0     # Never cap preflop bet — always raise premiums
        s['PreFlopCallPower'] = 2          # Curve steepness for call sizing
        s['PreFlopBetPower'] = 2           # Curve steepness for bet sizing

        # === FLOP ===
        # GTO c-bet ~55-65% of range, call with decent draws/pairs
        s['FlopMinCallEquity'] = 0.30      # Call with 30%+ equity (includes draws)
        s['FlopMinBetEquity'] = 0.40       # Bet with 40%+ equity (value + semi-bluffs)
        s['FlopCallPower'] = 2
        s['FlopBetPower'] = 2

        # === TURN ===
        # Tighten slightly: barrel with strong hands + good draws
        s['TurnMinCallEquity'] = 0.33      # Call with 33%+ equity
        s['TurnMinBetEquity'] = 0.43       # Bet with 43%+ equity
        s['TurnCallPower'] = 2
        s['TurnBetPower'] = 2

        # === RIVER ===
        # Value-heavy on river, need decent hand to continue
        s['RiverMinCallEquity'] = 0.35     # Call with 35%+ equity
        s['RiverMinBetEquity'] = 0.48      # Bet with 48%+ equity
        s['RiverCallPower'] = 2
        s['RiverBetPower'] = 2

        # === RE-RAISING (3-bet, 4-bet) ===
        # secondRoundAdjustment adds to equity requirement when acting again on same street.
        # Default was 100 (= impossible). Set low so bot CAN re-raise with strong hands.
        s['secondRoundAdjustmentPreFlop'] = 0.08  # Need 8% more equity to 3-bet/4-bet preflop
        s['secondRoundAdjustment'] = 0.05          # Need 5% more equity to re-raise post-flop
        s['secondRoundAdjustmentPowerIncrease'] = 1  # Slight power increase on re-raise

        # === BET SIZING ===
        s['minimum_bet_size'] = 3          # Min bet = half pot (bet3) post-flop
        s['increased_preflop_betting'] = 2  # Enable bet3 (half pot) preflop opens
        s['BetPlusInc'] = 3.0              # BetPlus increment in BB
        s['use_pot_multiples'] = 0         # Use absolute values, not pot multiples

        # === POSITION ADJUSTMENTS ===
        # Reduce required equity by ~2% per position closer to BTN
        s['pre_flop_equity_reduction_by_position'] = 0.02
        # Increase required equity by 3% when facing a raiser, 2% when facing a caller
        s['pre_flop_equity_increase_if_bet'] = 0.03
        s['pre_flop_equity_increase_if_call'] = 0.02

        # === POT ADJUSTMENTS ===
        # Reduce required equity when pot is large (more incentive to play)
        s['potAdjustment'] = 1.0
        s['maxPotAdjustment'] = 0.10
        s['potAdjustmentPreFlop'] = 1.0
        s['maxPotAdjustmentPreFlop'] = 0.05

        # === ALWAYS CALL THRESHOLD ===
        s['alwaysCallEquity'] = 0.80       # Always call with 80%+ equity
        s['always_call_low_stack_multiplier'] = 6  # Call if pot > ~17% of stack (raised from 4)

        # === OPPONENT RANGES ===
        s['range_multiple_players'] = 0.25  # Opponents play ~25% of hands
        s['range_preflop'] = 0.50           # Preflop range width
        s['use_relative_equity'] = 0        # Disabled — not implemented (crashes postflop)
        s['range_of_range'] = 0             # Don't filter range further
        s['collusion'] = 0                  # No collusion cards
        # Per-position opponent ranges (UTG=0 through BB=5)
        # GTO open ranges: UTG~15%, MP~18%, CO~27%, BTN~40%, SB~35%, BB~25% defend
        _pos_ranges = {0: 0.15, 1: 0.18, 2: 0.27, 3: 0.40, 4: 0.35, 5: 0.25}
        for i in range(6):
            s[f'range_utg{i}'] = _pos_ranges.get(i, 0.25)

        # === BLUFFING (GTO requires balanced bluffs) ===
        s['FlopBluffMinEquity'] = 0.20      # Bluff with 20-40% equity on flop
        s['FlopBluffMaxEquity'] = 0.40
        s['TurnBluffMinEquity'] = 0.15      # Bluff with 15-35% equity on turn
        s['TurnBluffMaxEquity'] = 0.35
        s['RiverBluffMinEquity'] = 0.10     # Bluff with 10-30% equity on river
        s['RiverBluffMaxEquity'] = 0.30
        # Bluffing conditions: 0 = always allow, 1 = only when no opponent initiative
        s['flop_bluffing_condidion_1'] = 0
        s['turn_bluffing_condidion_1'] = 0
        s['turn_bluffing_condidion_2'] = 0
        s['river_bluffing_condidion_1'] = 0
        s['river_bluffing_condidion_2'] = 0

        # === CHECK DECEPTION (slow-play strong hands) ===
        s['FlopCheckDeceptionMinEquity'] = 0.75   # Slow-play with 75%+ equity on flop
        s['TurnCheckDeceptionMinEquity'] = 0.80   # Slow-play with 80%+ on turn
        s['RiverCheckDeceptionMinEquity'] = 0.85  # Slow-play with 85%+ on river

        # === OPPONENT INITIATIVE (betting conditions) ===
        # 0 = bet regardless of opponent initiative, 1 = only bet when we have initiative
        s['flop_betting_condidion_1'] = 0
        s['turn_betting_condidion_1'] = 0
        s['river_betting_condidion_1'] = 0
        s['opponent_raised_without_initiative_flop'] = 0.0
        s['opponent_raised_without_initiative_turn'] = 0.0
        s['opponent_raised_without_initiative_river'] = 0.0

        # === RIVER VALUE BETS ===
        s['secondRiverBetPotMinEquity'] = 0.70     # 2nd river bet with 70%+ equity
        s['betPotRiverEquity'] = 0.65               # Pot-size river bet with 65%+ equity
        s['betPotRiverEquityMaxBBM'] = 50            # Up to 50 BB pot

        # === BULLY MODE ===
        s['minBullyEquity'] = 0.45
        s['maxBullyEquity'] = 0.55
        s['bullyDivider'] = 50.0  # Bully when opponent has > 50 BB

        # === OUTS ===
        s['out_multiplier'] = 1.0  # Count outs toward equity

        # === PREFLOP TABLE ===
        s['preflop_override'] = 1  # Use preflop lookup table

        log.info(f"GTO strategy overrides applied: BB={s['bigBlind']}, "
                 f"preflop call/bet={s['PreFlopMinCallEquity']}/{s['PreFlopMinBetEquity']}, "
                 f"3bet_adj={s['secondRoundAdjustmentPreFlop']}, "
                 f"bluff flop={s['FlopBluffMinEquity']}-{s['FlopBluffMaxEquity']}")

        # Game type tracking — detected from window name, adapts strategy
        self._detected_game_type = None  # 'cash', 'mtt', 'spin', 'rush'

        # Load table config: try MongoDB first, fall back to local disk templates
        self.table_dict = None
        self.using_local_config = False
        try:
            self.mongo = MongoManager()
            self.table_dict = self.mongo.get_table(table_scraper_name)
            log.info("Loaded table config from MongoDB")
        except Exception as e:
            log.warning(f"MongoDB unavailable ({e}), using local table config")
            self.mongo = None

        if self.table_dict is None and LOCAL_TABLE_CONFIG_AVAILABLE:
            # Build table_dict from local card templates + percentage-based regions.
            # This is a default; create_session() will rebuild for actual window size.
            self.table_dict = build_local_table_dict(
                table_width_px=self.standard_width * 2,
                table_height_px=self.standard_height * 2,
            )
            self.using_local_config = True
            log.info("Using local table config with disk-based card templates")
        elif self.table_dict is None:
            raise RuntimeError(
                "Cannot load table config: MongoDB unreachable and local_table_config not available. "
                "Ensure poker_ocr/assets/card_templates/ has 52 PNG files."
            )

        # === PREFLOP SHEET LOADING (CRITICAL - from main.py) ===
        self.preflop_sheet = None
        if UPDATE_CHECKER_AVAILABLE:
            try:
                self.updater = UpdateChecker()
                preflop_url, preflop_url_backup = self.updater.get_preflop_sheet_url()
                try:
                    self.preflop_sheet = pd.read_excel(preflop_url, sheet_name=None, engine='openpyxl')
                    log.info(f"Loaded preflop sheet from primary URL")
                except Exception as e:
                    log.warning(f"Primary preflop URL failed: {e}, trying backup")
                    self.preflop_sheet = pd.read_excel(preflop_url_backup, sheet_name=None, engine='openpyxl')
                    log.info(f"Loaded preflop sheet from backup URL")
            except Exception as e:
                log.error(f"Failed to load preflop sheets: {e}")
        else:
            log.warning("UpdateChecker not available, preflop sheets not loaded")

        # === SELF-LEARNING SYSTEMS ===
        self.learner = get_learner() if ADAPTIVE_LEARNER_AVAILABLE else None
        self.healer = get_healer() if SELF_HEALER_AVAILABLE else None

        # Load learned thresholds (these improve over time)
        self.white_pixel_min = get_threshold('white_pixel_min', 180)
        self.button_area_min = get_threshold('button_area_min', 2000)

        log.info(f"Self-learning: learner={self.learner is not None}, healer={self.healer is not None}")
        log.info(f"Learned thresholds: white_pixel_min={self.white_pixel_min}, button_area_min={self.button_area_min}")

        # === RUST OCR BRIDGE ===
        # Disabled: Rust binary exists but window_id mapping not implemented yet.
        # AppleScript returns sequential indices, but Rust needs CGWindowID.
        # Python OCR works well — re-enable Rust once CGWindowID is resolved.
        self.rust_ocr = None

        # Lobby navigation
        self.lobby_nav = DynamicLobbyNavigator() if LOBBY_NAV_AVAILABLE else None

        # Opponent modeling
        self.opponent_modeler = get_opponent_modeler() if OPPONENT_MODELER_AVAILABLE else None

        # Screenshot directory
        self.screenshot_dir = Path("log/screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        # === SESSION STATS TRACKING ===
        self.stats = {
            'session_start': datetime.datetime.utcnow().isoformat(),
            'hands_played': 0,
            'decisions': {'fold': 0, 'call': 0, 'check': 0, 'raise': 0, 'bet': 0},
            'detection_success': {'buttons': 0, 'buttons_fail': 0, 'cards': 0, 'cards_fail': 0},
            'self_healing': {'triggered': 0, 'success': 0, 'failed': 0},
            'clicks': {'success': 0, 'failed': 0, 'retries': 0},
            'errors': [],
            'pnl_bb': 0.0,          # Running P&L in big blinds
            'ev_total': 0.0,        # Sum of all decision EVs
            'hands_won': 0,
            'hands_lost': 0,
            'biggest_pot_won': 0.0,
            'biggest_pot_lost': 0.0,
        }
        self.stats_file = Path("data/learning/session_stats.json")
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)

        # Live spot-type P&L tracker
        self.spot_tracker = SpotTracker()

        # Autonomous feedback loop: reload adjustments every N hands
        self._adj_reload_interval = 50   # Reload strategy adjustments every 50 hands
        self._adj_retune_interval = 200  # Auto-run strategy adjuster every 200 hands
        self._last_adj_reload = 0
        self._last_adj_retune = 0

        log.info(f"MultiTableRunner initialized: max={max_tables}, target={target_tables}")
        log.info(f"Features: preflop_sheets={self.preflop_sheet is not None}, lobby_nav={self.lobby_nav is not None}")

    def resize_window(self, window_name: str, width: int, height: int, x: int, y: int) -> bool:
        """Resize a specific poker window using AppleScript"""
        script = f'''
        tell application "System Events"
            tell process "GGnet"
                repeat with w in windows
                    if name of w contains "{window_name}" then
                        set position of w to {{{x}, {y}}}
                        set size of w to {{{width}, {height}}}
                        return "resized"
                    end if
                end repeat
            end tell
        end tell
        return "not found"
        '''
        try:
            result = subprocess.run(['osascript', '-e', script],
                                   capture_output=True, text=True, timeout=5)
            success = "resized" in result.stdout
            if success:
                log.info(f"Resized '{window_name}' to {width}x{height} at ({x},{y})")
            return success
        except Exception as e:
            log.error(f"Failed to resize window: {e}")
            return False

    def tile_all_tables(self) -> int:
        """
        Resize all poker tables to standard size and arrange in grid.
        Uses a single AppleScript to tile by window index (handles same-name windows).
        Returns number of tables tiled.
        """
        tw = self.standard_width
        th = self.standard_height
        rh = getattr(self, 'tile_row_height', th)  # row spacing (may be less than th for overlap)
        cols = self.tile_columns
        y_off = self.tile_y_offset
        # Single AppleScript: iterate all windows, assign grid positions by index
        # Exclude lobby ("GGPoker") and cashier windows
        # Also raise all table windows to front after tiling
        script = f'''
        tell application "System Events"
            tell process "GGnet"
                set idx to 0
                set tableWindows to {{}}
                repeat with aWin in windows
                    set winName to name of aWin as text
                    if winName is not "GGPoker" and winName is not "Cashier" then
                        if winName contains "Rush" or winName contains "Cash" or winName contains "Spin" or winName contains "Hold" or winName contains "NL" or winName contains "Blinds" or winName contains "Table" or winName contains "Gold" then
                            set colNum to idx mod {cols}
                            set rowNum to idx div {cols}
                            set xPos to colNum * {tw}
                            set yPos to {y_off} + rowNum * {rh}
                            set position of aWin to {{xPos, yPos}}
                            set size of aWin to {{{tw}, {th}}}
                            set end of tableWindows to aWin
                            set idx to idx + 1
                        end if
                    end if
                end repeat
                -- Bring all table windows to front
                repeat with tWin in tableWindows
                    perform action "AXRaise" of tWin
                end repeat
                return idx
            end tell
        end tell
        '''
        try:
            result = subprocess.run(['osascript', '-e', script],
                                    capture_output=True, text=True, timeout=10)
            count_str = result.stdout.strip()
            count = int(count_str) if count_str.isdigit() else 0
            log.info(f"Tiled {count} tables in {cols} columns ({tw}x{th} each)")
            return count
        except Exception as e:
            log.error(f"Tile tables failed: {e}")
            return 0

    def standardize_tables(self) -> int:
        """
        On startup: resize all tables to standard size for consistent detection.
        This makes all coordinate-based detection work reliably.
        """
        log.info("Standardizing all tables to consistent size...")
        return self.tile_all_tables()

    def find_poker_windows(self) -> List[TableWindow]:
        """
        Find all open GGPoker table windows using Quartz (macOS native).
        Bypasses Accessibility permission issues that plague AppleScript.
        Returns list of TableWindow objects.
        """
        try:
            import Quartz
            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID
            )
            
            # GGPoker can use these names for the owner process
            target_owners = ('GGPoker', 'GGnet')
            keywords = ("Spin", "Hold", "NL", "Blinds", "Table", "Highlight", "Gold", "$")
            
            windows = []
            for w in window_list:
                owner = w.get('kCGWindowOwnerName', '')
                if owner not in target_owners:
                    continue
                
                name = w.get('kCGWindowName', '')
                bounds = w.get('kCGWindowBounds', {})
                x = int(bounds.get('X', 0))
                y = int(bounds.get('Y', 0))
                width = int(bounds.get('Width', 0))
                height = int(bounds.get('Height', 0))
                wid = int(w.get('kCGWindowNumber', 0))
                
                # Filter for poker tables (not lobby, chat, or mini-widgets)
                is_poker_table = False
                if any(k in name for k in keywords):
                    is_poker_table = True

                # EXPLICIT LOBBY EXCLUSION: Skip the main window
                if name == "GGPoker" or name == "GGnet" or "Lobby" in name:
                    is_poker_table = False

                # Size-based fallback (Lobby is usually 1200x740, tables vary)
                # Tables are typically > 700 width and > 500 height
                if is_poker_table is False and width > 750 and width < 2000 and height > 500:
                    # Double check it's not the lobby before accepting by size
                    if name != "GGPoker" and name != "GGnet":
                        is_poker_table = True                
                # Filter out pure-black overlays or 0-size ghosts
                if is_poker_table and width > 0 and height > 0:
                    windows.append(TableWindow(
                        name=name or f"Table_{wid}",
                        x=x, y=y, width=width, height=height,
                        window_id=wid
                    ))
                    log.debug(f"Detected window: {name} ({width}x{height}) at {x},{y}")
                    
            return windows

        except ImportError:
            log.warning("Quartz not available — falling back to legacy AppleScript")
            # [Old AppleScript fallback here if needed, but we used Quartz in diagnostic]
            return []
        except Exception as e:
            log.error(f"Quartz window detection failed: {e}")
            return []
            remaining = output.strip()
            idx = 0
            while remaining:
                # Match: ..., x, y, width, height at the END of remaining
                m = re.search(r',\s*(-?\d+),\s*(-?\d+),\s*(\d+),\s*(\d+)\s*$', remaining)
                if not m:
                    break
                x, y, w, h = m.group(1), m.group(2), m.group(3), m.group(4)
                name = remaining[:m.start()].strip()
                remaining = ''

                # If name contains earlier windows (another set of coords),
                # split at the last complete window boundary
                # Check if name itself has trailing coords from a previous window
                m2 = re.search(r',\s*(-?\d+),\s*(-?\d+),\s*(\d+),\s*(\d+),\s*', name)
                if m2:
                    # Everything after the last coords+comma is the current name
                    # Find the rightmost such pattern
                    last_m2 = None
                    for m2 in re.finditer(r',\s*(-?\d+),\s*(-?\d+),\s*(\d+),\s*(\d+),\s*', name):
                        last_m2 = m2
                    if last_m2:
                        remaining = name[:last_m2.start()]
                        name = name[last_m2.end():].strip()
                        # The coords in last_m2 belong to the previous window entry
                        remaining = remaining + ',' + ','.join(
                            [last_m2.group(1), last_m2.group(2), last_m2.group(3), last_m2.group(4)])

                windows.append(TableWindow(
                    window_id=idx,
                    name=name.strip().strip(',').strip(),
                    x=int(x),
                    y=int(y),
                    width=int(w),
                    height=int(h)
                ))
                log.debug(f"Found table: {name} at ({x},{y}) {w}x{h}")
                idx += 1

            return windows

        except subprocess.TimeoutExpired:
            log.warning("AppleScript timeout finding windows")
            return []
        except Exception as e:
            log.error(f"Error finding windows: {e}")
            return []

    def create_session(self, window: TableWindow) -> TableSession:
        """Create a new TableSession for a window.

        When using local config, builds a table_dict scaled to the actual
        window size (in pixels) so percentage-based regions map correctly.
        """
        if self.using_local_config and LOCAL_TABLE_CONFIG_AVAILABLE:
            # Build table_dict for this window's actual pixel dimensions
            td = build_local_table_dict(
                table_width_px=window.width * 2,   # points -> pixels (Retina)
                table_height_px=window.height * 2,
            )
        else:
            td = self.table_dict

        session = TableSession(
            window=window,
            table_dict=td,
        )
        log.info(f"Created session for table: {window.name} ({window.width}x{window.height}pt)")
        return session

    def grab_full_screen(self):
        """Grab one full-screen screenshot (shared across all tables)."""
        return ImageGrab.grab()

    def get_table_screenshot(self, window: TableWindow, full_screen=None):
        """Crop a table from a full-screen screenshot.

        If full_screen is provided, reuses it (fast — no new capture).
        Otherwise captures a fresh full screen (~80ms).
        Does NOT focus/raise the window.
        """
        if full_screen is None:
            full_screen = ImageGrab.grab()
        bounds = window.bounds_pixels
        return full_screen.crop(bounds)

    def check_table_state(self, session: TableSession) -> TableState:
        """
        Check if table needs action using the new Python OCR pipeline.
        Falls back to original bot's button detection if OCR unavailable.
        """
        # Cooldown: don't re-check too soon after taking an action
        # (Rush & Cash needs ~2s to deal next hand after action)
        seconds_since_action = (datetime.datetime.utcnow() - session.last_action_time).total_seconds()
        if seconds_since_action < 2.0:
            session.state = TableState.WAITING
            session.priority = 1
            return session.state

        if PYTHON_OCR_AVAILABLE:
            # Use new OCR pipeline — captures full GameState including buttons
            state = self.capture_game_state(session)
            if state is not None:
                # Cache the GameState so process_table_new_ocr can reuse it
                session._cached_game_state = state

                # Clear cached cards when board is empty (new hand started)
                if not state.board_cards or len(state.board_cards) == 0:
                    if state.my_cards and len(state.my_cards) == 2:
                        session._cached_cards = list(state.my_cards)
                    elif not state.is_my_turn:
                        # Not our turn + no board = between hands, clear cache
                        session._cached_cards = None
                        session._last_acted_key = ""  # Reset dedup for new hand

                # Handle "Add Chips" rebuy dialog — check BEFORE Deal Me In
                # because both may be visible simultaneously after busting.
                # Only check when we appear to be sitting out (deal_me_in visible
                # or no action buttons at all) to avoid expensive OCR every cycle.
                if not state.is_my_turn:
                    action_types = {a.action_type for a in state.available_actions}
                    poker_btns = action_types & {'fold', 'call', 'check', 'raise', 'bet', 'all_in'}
                    sitting_out = 'deal_me_in' in action_types or len(poker_btns) == 0
                    if sitting_out:
                        rebuy_handled = self._detect_and_handle_rebuy(session)
                        if rebuy_handled:
                            session.last_action_time = datetime.datetime.utcnow()
                            session.state = TableState.WAITING
                            session.priority = 1
                            return session.state

                        # Tournament result popup: "Play Again" button
                        # Appears after elimination in Mystery Battle Royale etc.
                        play_again = self._detect_play_again(session)
                        if play_again:
                            session.last_action_time = datetime.datetime.utcnow()
                            session.state = TableState.WAITING
                            session.priority = 1
                            return session.state

                # Handle "Deal Me In" button — click it immediately to rejoin
                deal_me_in = state.get_action_by_type('deal_me_in')
                if deal_me_in and not state.is_my_turn:
                    import pyautogui
                    pyautogui.click(deal_me_in.screen_x_pt, deal_me_in.screen_y_pt)
                    log.info(f"Table {session.window.name}: Clicked 'Deal Me In' at "
                             f"({deal_me_in.screen_x_pt}, {deal_me_in.screen_y_pt})")
                    session.last_action_time = datetime.datetime.utcnow()
                    session.state = TableState.WAITING
                    session.priority = 1
                    return session.state

                # Check for showdown (opponent cards visible after hand)
                if not state.is_my_turn:
                    if not sitting_out:
                        self._check_showdown(session, state)

                if state.is_my_turn:
                    actions = [a.action_type for a in state.available_actions]
                    poker_actions = {'fold', 'call', 'check', 'raise', 'bet', 'all_in'}
                    real_actions = [a for a in actions if a in poker_actions]

                    # In Rush & Cash, when it's truly your turn you see at least 2 buttons
                    # (e.g. fold+call, fold+check, check+raise). A single "fold" alone
                    # usually means buttons haven't fully rendered yet or it's a
                    # pre-action checkbox. Wait for proper button set.
                    # EXCEPTION: If cards are detected AND fold is visible, this might
                    # be a real action state where call/raise buttons weren't detected
                    # (all dark-red buttons merge). Retry once before giving up.
                    if len(real_actions) < 2:
                        has_cards = state.my_cards and len(state.my_cards) == 2
                        fold_retry = getattr(session, '_fold_only_retries', 0)
                        if has_cards and 'fold' in real_actions and fold_retry < 2:
                            session._fold_only_retries = fold_retry + 1
                            log.info(f"Table {session.window.name}: Only fold detected but "
                                     f"cards={state.my_cards} visible, retry #{fold_retry+1}")
                            session.state = TableState.WAITING
                            session.priority = 8  # High priority retry
                            return session.state
                        log.debug(f"Table {session.window.name}: Only {real_actions} detected, "
                                  f"waiting for full button set")
                        session._fold_only_retries = 0
                        session.state = TableState.WAITING
                        session.priority = 2  # Slightly higher than normal waiting
                        return session.state
                    session._fold_only_retries = 0  # Reset on success

                    session.state = TableState.NEED_ACTION
                    session.priority = 10
                    log.info(f"Table {session.window.name}: NEED_ACTION "
                             f"(actions={actions}, cards={state.my_cards})")
                else:
                    session.state = TableState.WAITING
                    session.priority = 1
                    log.debug(f"Table {session.window.name}: WAITING")
                return session.state

        # Fallback: old TableScreenBased button detection
        screenshot = self.get_table_screenshot(session.window)

        if session._table is None:
            session._table = TableScreenBased(
                self.strategy,
                session.table_dict,
                MockSignalsMC(),
                session.game_logger,
                version=6.76,
                nn_model=None
            )
            if self.preflop_sheet is not None:
                session.history.preflop_sheet = self.preflop_sheet

        session._table.entireScreenPIL = screenshot
        session._table.screenshot = screenshot
        session._table.tlc = (0, 0)

        has_call = session._table.has_call_button()
        has_raise = session._table.has_raise_button()
        has_check = session._table.has_check_button()

        if has_call or has_raise or has_check:
            session.state = TableState.NEED_ACTION
            session.priority = 10
            log.info(f"Table {session.window.name}: NEED_ACTION (call={has_call}, raise={has_raise}, check={has_check})")
        else:
            session.state = TableState.WAITING
            session.priority = 1
            log.debug(f"Table {session.window.name}: WAITING")

        return session.state

    def _check_table_state_with_screen(self, session: TableSession, full_screen):
        """Check table state using a pre-captured full-screen image.

        This avoids re-capturing the screen for each table, saving ~80ms per table.
        The OCR (read_table) runs on the cropped table image — this method is
        thread-safe because each table gets its own crop and session object.
        """
        # Cooldown check (same as check_table_state)
        seconds_since_action = (datetime.datetime.utcnow() - session.last_action_time).total_seconds()
        if seconds_since_action < 2.0:
            session.state = TableState.WAITING
            session.priority = 1
            return session.state

        if PYTHON_OCR_AVAILABLE:
            state = self.capture_game_state(session, full_screen=full_screen)
            if state is not None:
                session._cached_game_state = state

                # Clear cached cards when board is empty (new hand started)
                if not state.board_cards or len(state.board_cards) == 0:
                    if state.my_cards and len(state.my_cards) == 2:
                        session._cached_cards = list(state.my_cards)
                    elif not state.is_my_turn:
                        session._cached_cards = None
                        session._last_acted_key = ""

                # Handle rebuy/play-again (only when sitting out)
                if not state.is_my_turn:
                    action_types = {a.action_type for a in state.available_actions}
                    poker_btns = action_types & {'fold', 'call', 'check', 'raise', 'bet', 'all_in'}
                    sitting_out = 'deal_me_in' in action_types or len(poker_btns) == 0
                    if sitting_out:
                        rebuy_handled = self._detect_and_handle_rebuy(session)
                        if rebuy_handled:
                            session.last_action_time = datetime.datetime.utcnow()
                            session.state = TableState.WAITING
                            session.priority = 1
                            return session.state

                        play_again = self._detect_play_again(session)
                        if play_again:
                            session.last_action_time = datetime.datetime.utcnow()

                # Determine state from detected actions
                action_types = {a.action_type for a in state.available_actions}
                poker_btns = action_types & {'fold', 'call', 'check', 'raise', 'bet', 'all_in'}

                if poker_btns and state.is_my_turn:
                    # Retry logic when only fold detected but cards visible
                    if poker_btns == {'fold'} and state.my_cards and len(state.my_cards) >= 1:
                        retry_count = getattr(session, '_fold_only_retries', 0) + 1
                        session._fold_only_retries = retry_count
                        if retry_count <= 2:
                            log.info(f"Table {session.window.name}: Only fold detected but "
                                     f"cards={state.my_cards} visible, retry #{retry_count}")
                            session.state = TableState.WAITING
                            session.priority = 5
                            return session.state

                    session._fold_only_retries = 0
                    session.state = TableState.NEED_ACTION
                    session.priority = 10
                    log.info(f"Table {session.window.name}: NEED_ACTION "
                             f"(actions={list(poker_btns)}, cards={state.my_cards})")
                else:
                    session._fold_only_retries = 0
                    session.state = TableState.WAITING
                    session.priority = 1
                    
                    # --- NEW: AUTO-FOLD EXECUTION ---
                    # If it's NOT our turn, but we have seen our cards, and they are garbage,
                    # click the 'Fold to any bet' checkbox if detected.
                    if not state.is_my_turn and state.my_cards and len(state.my_cards) == 2:
                        pre_fold_pos = getattr(session, '_pre_fold_checkbox', None)
                        if pre_fold_pos:
                            # Use a very simplified equity check for pre-folding
                            # (Avoid heavy MC here, just check if hand is total trash)
                            trash = {'72O', '82O', '92O', 'T2O', 'J2O', 'Q2O', '73O', '83O'}
                            from gamble.decisionmaker.decisionmaker import _normalize_hand
                            h_norm = _normalize_hand(state.my_cards[0], state.my_cards[1])
                            if h_norm in trash:
                                log.info(f"AUTO-FOLD: checking 'Fold to any bet' for trash hand {h_norm}")
                                import pyautogui
                                pyautogui.click(pre_fold_pos[0], pre_fold_pos[1])
                                session._pre_fold_checkbox = None # Only click once per hand

                # Save verification screenshot periodically
                self._maybe_save_verification(session, state, full_screen)

                return session.state

        # Fallback to original check
        return self.check_table_state(session)

    def _maybe_save_verification(self, session: TableSession, state, full_screen):
        """Periodically save card crops for live verification (~every 15s per table)."""
        if not state.my_cards or len(state.my_cards) < 1:
            return

        now = time.time()
        last_save = getattr(session, '_last_verify_save', 0)
        if now - last_save < 15:
            return
        session._last_verify_save = now

        try:
            verify_dir = Path('/tmp/table_debug/card_verify')
            verify_dir.mkdir(parents=True, exist_ok=True)

            # Crop the table from full screen
            w = session.window
            bounds = w.bounds_pixels
            table_img = full_screen.crop(bounds)

            # Save full table with cards/board annotation in filename
            cards_str = '_'.join(state.my_cards)
            board_str = '_'.join(state.board_cards) if state.board_cards else 'preflop'
            ts = datetime.datetime.now().strftime('%H%M%S')
            filename = f"{ts}_{cards_str}_board_{board_str}.png"
            table_img.save(str(verify_dir / filename))
            log.debug(f"Saved verification: {filename}")

            # Keep only last 50 files to avoid filling disk
            files = sorted(verify_dir.glob('*.png'))
            for old_file in files[:-50]:
                old_file.unlink(missing_ok=True)
        except Exception as e:
            log.debug(f"Verify save failed: {e}")

    def _fast_deal_me_in_scan(self, sessions_to_check: list, full_screen=None):
        """Fast Deal Me In scan — one screenshot, check all tables at once.

        Takes a single full-screen screenshot and crops each table's button
        region to check for "Deal Me In" buttons using HSV + quick OCR.
        This is MUCH faster than running full check_table_state per table
        because it avoids per-table AppleScript focus + separate screenshots.
        """
        if not PYTHON_OCR_AVAILABLE or not sessions_to_check:
            return

        if full_screen is None:
            try:
                full_screen = ImageGrab.grab()
            except Exception:
                return

        for session in sessions_to_check:
            try:
                w = session.window
                bounds = w.bounds_pixels
                table_img = full_screen.crop(bounds)
                img = np.array(table_img)
                if img.ndim == 3 and img.shape[2] == 4:
                    img = img[:, :, :3]
                W, H = table_img.width, table_img.height
                if W < 100 or H < 100:
                    continue

                # Fast button detection (~3ms, no full OCR)
                # Pass deal_me_in_only=True to search the larger 40% region safely
                buttons, _ = _detect_buttons(img, W, H, deal_me_in_only=True)
                if not buttons:
                    continue

                # Check if any detected button is "Deal Me In"
                for btn_type, info in buttons.items():
                    if btn_type == 'deal_me_in':
                        # CLICK COOLDOWN: Don't spam click "Deal Me In"
                        now = datetime.datetime.utcnow()
                        last_click = getattr(session, '_last_deal_me_in_click', datetime.datetime.min)
                        if (now - last_click).total_seconds() < 5.0:
                            continue
                        
                        cx_px, cy_px = info['center']
                        
                        # Correct coordinate conversion: (window points / image pixels)
                        # This works for both Retina (2x) and standard (1x) displays.
                        scale_x = w.width / W
                        scale_y = w.height / H
                        screen_x = w.x + int(cx_px * scale_x)
                        screen_y = w.y + int(cy_px * scale_y)
                        
                        import pyautogui
                        pyautogui.click(screen_x, screen_y)
                        log.info(f"FAST Deal Me In: clicked on {w.name} "
                                 f"at ({screen_x}, {screen_y}) (ratio {scale_x:.2f})")
                        
                        session._last_deal_me_in_click = now
                        session.last_action_time = now
                        session.state = TableState.WAITING
                        session.priority = 1
                        break
            except Exception as e:
                log.debug(f"Fast Deal Me In scan failed for {session.window.name}: {e}")

    def capture_game_state(self, session: TableSession, full_screen=None) -> 'Optional[GameState]':
        """Capture game state using Rust OCR binary or Python OCR pipeline.

        Args:
            session: The table session.
            full_screen: Optional pre-captured full-screen image (avoids re-grab).

        Returns:
            GameState if OCR succeeded, None otherwise (fall back to old Python).
        """
        # Try Rust binary first (fastest)
        if self.rust_ocr is not None:
            state = self.rust_ocr.capture_table(session.window.window_id)
            if state is not None:
                log.debug(f"Rust OCR: {state.ocr_latency_ms:.0f}ms, turn={state.is_my_turn}, "
                          f"cards={state.my_cards}, actions={len(state.available_actions)}")
                return state

        # Fall back to Python OCR pipeline (read_table)
        if PYTHON_OCR_AVAILABLE:
            try:
                screenshot = self.get_table_screenshot(session.window, full_screen=full_screen)
                w = session.window
                state = read_table(
                    table_img=screenshot,
                    window_name=w.name,
                    window_id=w.window_id,
                    table_x_pt=w.x,
                    table_y_pt=w.y,
                    table_w_pt=w.width,
                    table_h_pt=w.height,
                )
                state.ocr_source = 'python'
                
                # --- NEW: AUTO-ACTION (Pre-betting) Detection ---
                # Scan for 'Fold to any bet' and 'Check/Fold' checkboxes.
                # These appear when it's NOT our turn yet.
                if not state.is_my_turn:
                    try:
                        img_np = np.array(screenshot)
                        hsv = cv2.cvtColor(img_np, cv2.COLOR_RGB2HSV)
                        # Fold checkbox is usually in the bottom-right action area.
                        # HSV for unchecked gray box: [0, 0, 100-200]
                        y1, y2 = int(w.height * 0.85 * 2), int(w.height * 0.95 * 2)
                        x1, x2 = int(w.width * 0.60 * 2), int(w.width * 0.98 * 2)
                        if y2 <= hsv.shape[0] and x2 <= hsv.shape[1]:
                            roi = hsv[y1:y2, x1:x2]
                            # Look for small gray square (unchecked) or green square (checked)
                            gray_mask = cv2.inRange(roi, np.array([0, 0, 100]), np.array([180, 30, 200]))
                            cnts, _ = cv2.findContours(gray_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                            for c in cnts:
                                area = cv2.contourArea(c)
                                if 100 < area < 1000: # Typical checkbox size
                                    M = cv2.moments(c)
                                    if M["m00"] != 0:
                                        cx = int(M["m10"] / M["m00"]) + x1
                                        cy = int(M["m01"] / M["m00"]) + y1
                                        session._pre_fold_checkbox = (w.x + cx/2, w.y + cy/2)
                                        break
                    except Exception:
                        pass

                log.debug(f"Python OCR: {state.ocr_latency_ms:.0f}ms, turn={state.is_my_turn}, "
                          f"cards={state.my_cards}, board={state.board_cards}, "
                          f"actions={[a.action_type for a in state.available_actions]}")
                return state
            except Exception as e:
                log.error(f"Python OCR failed: {e}")
                return None

        return None

    # ── Game type detection & strategy adaptation ────────────────────────

    # Strategy presets keyed by game type — applied before EVERY decision
    # so multiple table types can run simultaneously.
    _STRATEGY_PRESETS = {
        'mtt': {
            # MTT / Tournament: tighter ranges, ICM-aware, less bluffing
            'PreFlopMinCallEquity': 0.20,
            'PreFlopMinBetEquity': 0.25,
            'secondRoundAdjustmentPreFlop': 0.10,
            'FlopMinCallEquity': 0.33,
            'FlopMinBetEquity': 0.43,
            'TurnMinCallEquity': 0.33,
            'TurnMinBetEquity': 0.45,
            'RiverMinCallEquity': 0.32,
            'RiverMinBetEquity': 0.48,
            'FlopBluffMinEquity': 0.25,
            'FlopBluffMaxEquity': 0.35,
            'TurnBluffMinEquity': 0.20,
            'TurnBluffMaxEquity': 0.30,
            'RiverBluffMinEquity': 0.15,
            'RiverBluffMaxEquity': 0.25,
            'alwaysCallEquity': 0.82,
            '_pos_ranges': {0: 0.12, 1: 0.14, 2: 0.22, 3: 0.33, 4: 0.30, 5: 0.22},
        },
        'spin': {
            # Spin & Gold: 3-handed, aggressive, wide opens
            'PreFlopMinCallEquity': 0.15,
            'PreFlopMinBetEquity': 0.18,
            'FlopMinCallEquity': 0.27,
            'FlopMinBetEquity': 0.35,
            'TurnMinCallEquity': 0.27,
            'TurnMinBetEquity': 0.38,
            'RiverMinCallEquity': 0.25,
            'RiverMinBetEquity': 0.40,
            'FlopBluffMinEquity': 0.15,
            'FlopBluffMaxEquity': 0.45,
            'TurnBluffMinEquity': 0.10,
            'TurnBluffMaxEquity': 0.40,
            'RiverBluffMinEquity': 0.08,
            'RiverBluffMaxEquity': 0.35,
            'alwaysCallEquity': 0.78,
            '_pos_ranges': {0: 0.25, 1: 0.30, 2: 0.35, 3: 0.50, 4: 0.45, 5: 0.35},
        },
        'rush': {
            # Rush & Cash: standard GTO 6-max
            'PreFlopMinCallEquity': 0.17,
            'PreFlopMinBetEquity': 0.22,
            'secondRoundAdjustmentPreFlop': 0.08,
            'FlopMinCallEquity': 0.30,
            'FlopMinBetEquity': 0.40,
            'TurnMinCallEquity': 0.30,
            'TurnMinBetEquity': 0.42,
            'RiverMinCallEquity': 0.28,
            'RiverMinBetEquity': 0.45,
            'FlopBluffMinEquity': 0.20,
            'FlopBluffMaxEquity': 0.40,
            'TurnBluffMinEquity': 0.15,
            'TurnBluffMaxEquity': 0.35,
            'RiverBluffMinEquity': 0.10,
            'RiverBluffMaxEquity': 0.30,
            'alwaysCallEquity': 0.80,
            '_pos_ranges': {0: 0.15, 1: 0.18, 2: 0.27, 3: 0.40, 4: 0.35, 5: 0.25},
        },
        'cash': {
            # Regular cash: same as rush
            'PreFlopMinCallEquity': 0.17,
            'PreFlopMinBetEquity': 0.22,
            'secondRoundAdjustmentPreFlop': 0.08,
            'FlopMinCallEquity': 0.30,
            'FlopMinBetEquity': 0.40,
            'TurnMinCallEquity': 0.30,
            'TurnMinBetEquity': 0.42,
            'RiverMinCallEquity': 0.28,
            'RiverMinBetEquity': 0.45,
            'FlopBluffMinEquity': 0.20,
            'FlopBluffMaxEquity': 0.40,
            'TurnBluffMinEquity': 0.15,
            'TurnBluffMaxEquity': 0.35,
            'RiverBluffMinEquity': 0.10,
            'RiverBluffMaxEquity': 0.30,
            'alwaysCallEquity': 0.80,
            '_pos_ranges': {0: 0.15, 1: 0.18, 2: 0.27, 3: 0.40, 4: 0.35, 5: 0.25},
        },
    }

    @staticmethod
    def detect_game_type(window_name: str) -> str:
        """Detect game type from window title.

        Returns: 'mtt', 'spin', 'rush', 'cash'

        Recognizes all GGPoker formats:
          MTT: WSOP, Express, GTD, Bounty, GGMasters, Satellite, Freeroll,
               Flip & Go, Battle Royale, Daily Hyper, Step, Freezeout,
               Multi-Flight, any "Blinds X | Y" level format
          Spin: Spin & Gold, Spin & Go
          Rush: Rush & Cash
          Cash: anything with "$X / $Y" blind format
        """
        name = window_name.upper()

        # Spin & Gold (check before MTT — some spins have "GTD" in name)
        if ('SPIN' in name and 'GOLD' in name) or ('SPIN' in name and 'GO' in name):
            return 'spin'

        # Rush & Cash
        if 'RUSH' in name:
            return 'rush'

        # MTT indicators — comprehensive GGPoker tournament keywords
        _mtt_kw = (
            'GTD', 'STEP', 'WSOP', 'EXPRESS', 'BOUNTY', 'FREEZEOUT',
            'MY RANK', 'SATELLITE', 'FREEROLL', 'GGMASTERS', 'BATTLE ROYALE',
            'MULTI-FLIGHT', 'FLIP & GO', 'FLIP&GO', 'DAILY HYPER',
            'PROGRESSIVE', 'KNOCKOUT', 'PKO', 'MYSTERY BOUNTY',
            'PHASED', 'TURBO', 'HYPER', 'DEEPSTACK', 'SHORT DECK',
        )
        if any(kw in name for kw in _mtt_kw):
            return 'mtt'

        # "Blinds 50 | 100" or "Level X" → tournament
        import re
        if re.search(r'Blinds\s+\d+\s*\|\s*\d+', name):
            return 'mtt'
        if re.search(r'Level\s+\d+', name):
            return 'mtt'
        # "Buy-in $X" without "$X / $Y" → tournament
        if 'BUY-IN' in name or 'BUY IN' in name:
            return 'mtt'

        # Regular cash (has blinds like $0.01 / $0.02)
        if '$' in name and '/' in name:
            return 'cash'

        return 'cash'

    def _apply_strategy_preset(self, game_type: str, session: TableSession):
        """Apply strategy preset for this table's game type.

        Called BEFORE every decision so multiple game types work simultaneously.
        Only logs on first detection per session.
        """
        s = self.strategy.selected_strategy
        preset = self._STRATEGY_PRESETS.get(game_type, self._STRATEGY_PRESETS['cash'])

        # Apply all preset values
        for key, val in preset.items():
            if key == '_pos_ranges':
                for i in range(6):
                    s[f'range_utg{i}'] = val.get(i, 0.25)
            else:
                s[key] = val

        # Log on first detection per session
        session_gt = getattr(session, '_game_type', None)
        if session_gt != game_type:
            session._game_type = game_type
            log.info(f"STRATEGY: {game_type.upper()} mode for [{session.window.name[:50]}]")
            if game_type == 'mtt':
                log.info("  Tighter ranges, ICM-aware, less bluffing, 8-max positions")
            elif game_type == 'spin':
                log.info("  Aggressive 3-handed, wide opens, more bluffs")
            elif game_type == 'rush':
                log.info("  Standard GTO 6-max, wait for spots")

    def _update_blinds_from_window(self, session: TableSession):
        """Auto-detect blinds and game type from window name.

        Game type detection runs every call (cheap) and applies the correct
        strategy preset BEFORE each decision — so MTT + cash can coexist.
        """
        import re
        name = session.window.name

        # --- Game type detection & strategy adaptation (per-session) ---
        game_type = self.detect_game_type(name)
        self._apply_strategy_preset(game_type, session)

        # --- Blind detection ---
        # Match patterns like "$0.01 / $0.02" or "$0.25 / $0.50"
        m = re.search(r'\$(\d+\.?\d*)\s*/\s*\$(\d+\.?\d*)', name)
        if m:
            sb_dollars = float(m.group(1))
            bb_dollars = float(m.group(2))
            if not hasattr(self, '_blinds_logged'):
                log.info(f"Blinds from window: SB=${sb_dollars}, BB=${bb_dollars}")
                self._blinds_logged = True

    def process_table_new_ocr(self, session: TableSession) -> bool:
        """Process a table using the new OCR GameState pipeline.

        ALWAYS takes a fresh screenshot for card detection to avoid stale cache.
        Feeds GameState into the original DecisionMaker via to_table_scraper_compat().

        Returns:
            True if an action was taken, False otherwise.
        """
        import time as _time
        t0 = _time.time() # Start decision timer
        
        # High-pressure mode: If decision takes too long, skip slow verification steps
        def is_high_pressure():
            return (_time.time() - t0) > 10.0

        # Auto-detect blinds from window name
        self._update_blinds_from_window(session)

        # Use cached state from check_table_state if it already has what we need.
        # Re-capturing is risky: in Rush & Cash the opponent may act in <1s,
        # so the 0.3s sleep + re-capture can miss our turn entirely.
        cached_state = getattr(session, '_cached_game_state', None)
        has_cached_cards = (cached_state and cached_state.is_my_turn
                           and cached_state.my_cards and len(cached_state.my_cards) == 2)
        has_cached_board = (cached_state and cached_state.board_cards
                            and len(cached_state.board_cards) >= 3)

        if has_cached_cards:
            # Cards already detected — use cached state directly (no re-capture)
            state = cached_state
            log.debug(f"Using cached state: cards={state.my_cards} board={state.board_cards}")
        elif has_cached_board and cached_state.is_my_turn:
            # Postflop but no cards — use cached state (cards may be in cache)
            state = cached_state
            log.debug(f"Using cached postflop state (no cards yet): board={state.board_cards}")
        else:
            # Preflop or no cached state — re-capture with animation delay
            _time.sleep(0.10)  # Brief delay for card animation (GGPoker deals in ~100ms)
            state = self.capture_game_state(session)

        # Clear stale cache
        session._cached_game_state = None

        if state is None:
            return self.process_table(session)

        if not state.is_my_turn:
            return False

        # Require at least 2 real poker actions before proceeding.
        # A single "fold" likely means buttons haven't rendered yet.
        poker_actions = {'fold', 'call', 'check', 'raise', 'bet', 'all_in'}
        real_actions = [a for a in state.available_actions if a.action_type in poker_actions]
        if len(real_actions) < 2:
            log.debug(f"Only {[a.action_type for a in real_actions]} detected in process, "
                      f"waiting for full button set")
            return False

        # Dedup guard: don't act twice on the exact same situation.
        # Include pot size (rounded) so a 3-bet/re-raise creates a new key.
        cards_key = ','.join(sorted(state.my_cards)) if state.my_cards and len(state.my_cards) == 2 else ''
        board_count = len(state.board_cards) if state.board_cards else 0
        pot_key = round(state.pot, 1) if state.pot else 0
        current_key = f"{cards_key}|{board_count}|{pot_key}"
        if current_key and current_key == session._last_acted_key:
            log.debug(f"Dedup: already acted on {current_key}, skipping")
            return False

        # Ensure table object exists
        if session._table is None:
            session._table = TableScreenBased(
                self.strategy, session.table_dict,
                MockSignalsMC(), session.game_logger,
                version=6.76, nn_model=None
            )
            if self.preflop_sheet is not None:
                session.history.preflop_sheet = self.preflop_sheet

        t = session._table
        h = session.history
        p = self.strategy

        # Populate the TableScraper-compatible attributes from GameState
        state.to_table_scraper_compat(t)
        session._last_game_state = state  # For enhanced logging (Phase 6.1)

        # Initialize round tracking (needed by Decision)
        t.get_round_number(h)

        # Card caching: when cards detected, save them for later streets
        if state.my_cards and len(state.my_cards) == 2:
            session._cached_cards = list(state.my_cards)
            session._no_cards_retries = 0
        elif not state.my_cards or len(state.my_cards) != 2:
            cached = getattr(session, '_cached_cards', None)
            if cached and len(cached) == 2:
                has_board = state.board_cards and len(state.board_cards) >= 3
                if has_board:
                    log.info(f"Using cached cards {cached} (OCR failed but board visible: {state.board_cards})")
                    state.my_cards = list(cached)

        # If no cards yet, retry with increasing delays (animation timing)
        if not state.my_cards or len(state.my_cards) != 2:
            if not hasattr(session, '_no_cards_retries'):
                session._no_cards_retries = 0

            partial = state.my_cards if state.my_cards else []
            log.warning(f"Incomplete card detection: {partial} — retrying up to 4 times")

            for attempt in range(4):
                session._no_cards_retries += 1
                delay = 0.15 + attempt * 0.15  # 0.15, 0.30, 0.45, 0.60s
                _time.sleep(delay)
                retry_state = self.capture_game_state(session)
                if retry_state and retry_state.is_my_turn and retry_state.my_cards and len(retry_state.my_cards) == 2:
                    log.info(f"Card retry #{session._no_cards_retries} succeeded after {delay:.1f}s: {retry_state.my_cards}")
                    state = retry_state
                    session._cached_cards = list(state.my_cards)
                    session._no_cards_retries = 0
                    # Re-populate table from fresh state
                    state.to_table_scraper_compat(t)
                    break
                retry_cards = getattr(retry_state, 'my_cards', []) if retry_state else []
                log.debug(f"Card retry #{session._no_cards_retries} failed (delay={delay:.1f}s), "
                          f"cards={retry_cards}")
            else:
                session._no_cards_retries = 0
                # Save debug screenshot for analysis
                try:
                    screenshot = self.get_table_screenshot(session.window)
                    debug_path = os.path.join('data', 'learning', 'debug',
                                              f'card_fail_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
                    os.makedirs(os.path.dirname(debug_path), exist_ok=True)
                    screenshot.save(debug_path)
                    log.warning(f"Card detection failed 2x — saved debug: {debug_path}")
                except Exception:
                    pass

        # FINAL VALIDATION: We MUST have 2 cards to act.
        # If we reach here and still don't have cards, abort the decision to avoid
        # incorrect folds/checks.
        if not state.my_cards or len(state.my_cards) != 2:
            log.warning(f"Aborting decision for {session.window.name}: No valid hole cards detected.")
            return False

        # --- FRAME VOTING (Hand Confirmation) ---
        # To prevent folding premium hands due to OCR flicker (seeing 1 card instead of 2),
        # we require consecutive agreement before acting.
        current_cards = sorted(state.my_cards) if state.my_cards else []
        if not hasattr(session, '_hand_votes'):
            session._hand_votes = {}
        
        cards_str = ",".join(current_cards)
        session._hand_votes[cards_str] = session._hand_votes.get(cards_str, 0) + 1
        
        # Require 2 consecutive frames of the same cards before acting
        # In Rush & Cash, we can't wait too long, so 2 is the sweet spot.
        if session._hand_votes[cards_str] < 2:
            log.debug(f"Hand Voting: '{cards_str}' has {session._hand_votes[cards_str]} votes. Waiting for confirmation.")
            return False
        
        # Reset votes for other hand combinations
        for k in list(session._hand_votes.keys()):
            if k != cards_str:
                del session._hand_votes[k]

        # If we have cards, run the original decision maker
        if state.my_cards and len(state.my_cards) == 2:
            try:
                t.mycards = state.my_cards
                t.cardsOnTable = state.board_cards or []

                # Board empty = preflop, regardless of pot size.
                # Standard raises create pots of 4-12+ BB with no board cards.
                # Previously this forced Flop stage with 0.5 equity, which
                # bypassed GTO preflop ranges — a massive leak.

                # SAFETY NET: Incomplete board detection — wrong card count for street.
                # Monte Carlo with partial board gives wildly wrong equity.
                expected_board = {'Flop': 3, 'Turn': 4, 'River': 5}
                stage = t.gameStage
                board_len = len(t.cardsOnTable)
                if stage in expected_board and 0 < board_len < expected_board[stage]:
                    log.warning(f"Board incomplete: {board_len} cards on {stage} "
                                f"(expected {expected_board[stage]}), board={t.cardsOnTable}")
                    # Re-capture once — maybe OCR was partial
                    import time as _rt
                    _rt.sleep(0.1)
                    retry_state = self.capture_game_state(session)
                    if retry_state and retry_state.board_cards:
                        rb = retry_state.board_cards
                        if len(rb) >= expected_board.get(stage, 0):
                            t.cardsOnTable = rb
                            log.info(f"Board retry succeeded: {rb}")
                        elif len(rb) > board_len:
                            t.cardsOnTable = rb
                            log.info(f"Board retry partial improvement: {rb}")
                        else:
                            log.warning("Board still incomplete after retry, skipping")
                            return False
                    else:
                        # Retry also failed to find board — skip decision
                        log.warning(f"Board retry found no cards (had {board_len}), skipping")
                        return False

                # Fetch opponent profile BEFORE Monte Carlo so VPIP can
                # override the static opponent_range parameter.
                opp_profile = None
                if self.opponent_modeler:
                    try:
                        self._track_opponent(session, state, t)
                        villain_id = self._get_villain_id(session, state)
                        profile = self.opponent_modeler.get_profile(villain_id)
                        adj = self.opponent_modeler.get_adjustment(villain_id)
                        profile['fold_equity_bonus'] = adj.get('fold_equity_bonus', 0.0)
                        opp_profile = profile
                        t._opp_profile = opp_profile  # For range-based MC equity
                        t._table_name = getattr(session.window, 'name', '') if session.window else ''
                        if profile.get('type', 'unknown') != 'unknown':
                            log.info(f"OPP_PROFILE: {villain_id} = {profile['type']} "
                                     f"(VPIP={profile['vpip']:.0%} PFR={profile['pfr']:.0%} "
                                     f"AF={profile['af']:.1f} hands={profile['hands']})")
                    except Exception as e:
                        log.debug(f"Opponent modeling error (pre-MC): {e}")

                # Run Monte Carlo
                mock_signals = MockSignalsMC()
                config = get_config()
                run_montecarlo_wrapper(
                    p, mock_signals, config, None,
                    t, session.game_logger,
                    session.preflop_state, h,
                )

                # Make decision
                d = Decision(t, h, p, session.game_logger)

                # Attach opponent profile to decision object
                if opp_profile:
                    d._opp_profile = opp_profile

                d._spot_adj = self.spot_tracker.compute_adjustments()

                # Multi-street planning: pass previous street info to decision
                d._we_bet_prev_street = getattr(session, '_we_bet_last_street', False)
                d._prev_street_equity = getattr(session, '_last_equity', None)

                d.make_decision(t, h, p, session.game_logger)

                # Track our action for multi-street planning
                dec_str = str(d.decision).lower() if d.decision else ''
                session._we_bet_last_street = ('bet' in dec_str or 'raise' in dec_str)
                session._last_equity = t.equity

                mouse_target = d.decision
                # Push/fold shove: override to Allin so runner types full stack
                if getattr(d, 'push_fold_shove', False) and mouse_target == 'Bet pot':
                    mouse_target = 'Allin'
                    log.info("PUSH/FOLD SHOVE → Allin override")
                session._last_decision = mouse_target  # For outcome correlation
                session._last_street = t.gameStage       # For spot classification
                equity_val = getattr(t, 'equity', 0)
                abs_eq_val = getattr(t, 'abs_equity', 0)
                # EV and analysis logging
                ev = getattr(d, 'decision_ev', 0)
                blockers = getattr(d, 'blockers_info', {})
                opp_range = getattr(d, 'opponent_range_estimate', {})
                blocker_str = ''
                if blockers.get('blocker_score', 0) > 0:
                    parts = []
                    if blockers.get('blocks_nut_flush'): parts.append('NutFlush')
                    if blockers.get('blocks_top_pair'): parts.append('TopPair')
                    if blockers.get('blocks_overpair'): parts.append('Overpair')
                    if blockers.get('blocks_sets'): parts.append('Sets')
                    blocker_str = f" | blockers=[{','.join(parts)}]({blockers['blocker_score']:.2f})"

                opp_str = ''
                if opp_range.get('likely_hands'):
                    opp_type = ''
                    if d._opp_profile and d._opp_profile.get('type', 'unknown') != 'unknown':
                        opp_type = f" ({d._opp_profile['type']})"
                    opp_str = (f" | opp_range={opp_range['likely_hands'][:3]} "
                               f"bluff%={opp_range.get('bluff_probability', 0):.0%}{opp_type}")

                log.info(f"DECISION: {mouse_target} | cards={state.my_cards} "
                         f"board={state.board_cards} | pot={state.pot:.1f} call={state.call_amount:.1f} "
                         f"| equity={equity_val:.3f} abs_eq={abs_eq_val:.3f} "
                         f"| EV={ev:+.2f} BB"
                         f"| callLim={d.finalCallLimit:.1f} betLim={d.finalBetLimit:.1f} "
                         f"| stage={t.gameStage} pos={getattr(state, 'position', '?')}"
                         f" opp={t.other_active_players} init={'Y' if t.other_player_has_initiative else 'N'}"
                         f"{blocker_str}{opp_str}")

                # Track P&L (stack changes between hands)
                try:
                    self._track_pnl(session, state, decision_obj=d)
                except Exception:
                    pass

                # --- VERIFICATION SCREENSHOT (Big Pots) ---
                # Save screenshot if pot is large to allow for post-hand audit.
                # Threshold: > 20 BB is considered a "Big Pot".
                if state.pot and state.pot > 20.0:
                    try:
                        screenshot = self.get_table_screenshot(session.window)
                        save_debug_screenshot('big_pot', screenshot, reason=f'pot_{state.pot:.1f}bb')
                        log.info(f"BIG POT DETECTED ({state.pot:.1f} BB) - saved verification screenshot")
                    except Exception as e:
                        log.debug(f"Failed to save big pot screenshot: {e}")

                # Cache opponent estimate for showdown verification
                session._last_opp_estimate = opp_range
                session._cached_board = state.board_cards or []

                # Log hand to local history file
                try:
                    self._log_hand_locally(state, mouse_target, equity_val, abs_eq_val,
                                          decision_obj=d)
                except Exception:
                    pass  # Never let logging break decision flow

                # --- IRON-CLAD EXECUTION FLOW ---
                # Map DecisionMaker output to available action
                action = self._map_decision_to_action(state, mouse_target)
                target_str = str(mouse_target).split('.')[-1].lower() if hasattr(mouse_target, 'name') else str(mouse_target).lower()

                # GUARANTEED ACTION: If it's a Fold or Check, and we can't find the button,
                # use hardcoded coordinates immediately. We CANNOT loop on these.
                if not action and target_str in ('fold', 'check', 'call'):
                    log.warning(f"Iron-Clad: No button found for {target_str}, using coordinate fallback.")
                    x_map = {'fold': 0.15, 'check': 0.50, 'call': 0.50}
                    tx = x_map.get(target_str, 0.15)
                    from gamble.ocr.game_state import AvailableAction
                    action = AvailableAction(
                        action_type=target_str,
                        screen_x_pt=session.window.x + int(session.window.width * tx),
                        screen_y_pt=session.window.y + int(session.window.height * 0.91),
                        amount=None, confidence=0.1, rel_x=tx, rel_y=0.91
                    )

                # Execute the action
                if action:
                    self._click_action(action, session, state, mouse_target, high_pressure=is_high_pressure())
                    return True
                else:
                    log.warning(f"No action button found for '{mouse_target}', recapturing...")
                    return False

            except Exception as e:
                log.error(f"Decision failed: {e}\n{traceback.format_exc()}")
                # Decision crashed but we have cards — don't just fold.
                # Try push/fold as a fallback before giving up.
                if state.my_cards and len(state.my_cards) == 2:
                    try:
                        from gamble.decisionmaker.range_equity import lookup_push_fold
                        pf_result = lookup_push_fold(
                            state.my_cards,
                            getattr(state, 'hero_position', 'CO') or 'CO',
                            getattr(t, 'myFunds', 10) or 10
                        )
                        if pf_result:
                            log.info(f"CRASH FALLBACK: push/fold says {pf_result} for {state.my_cards}")
                            if pf_result == 'shove':
                                # Shove — find raise or all-in button
                                for btn_type in ('raise', 'all_in', 'call'):
                                    fb = state.get_action_by_type(btn_type)
                                    if fb:
                                        self._click_action(fb, session, state, 'crash_shove')
                                        return True
                            # push/fold says fold — continue to fold logic below
                        elif state.has_check_button:
                            fb = state.get_action_by_type('check')
                            if fb:
                                self._click_action(fb, session, state, 'crash_check')
                                return True
                    except Exception as e2:
                        log.error(f"Crash fallback also failed: {e2}")

        # No cards after all retries — take safe action
        if state.has_check_button:
            action = state.get_action_by_type('check')
            if action:
                self._click_action(action, session, state, 'check_no_cards')
                return True

        # No cards = can't evaluate hand.
        # DO NOT auto-fold (prevents folding AA if OCR misses cards).
        # Return False to trigger a retry/wait instead.
        return False

    def _map_decision_to_action(self, state, mouse_target):
        """Map DecisionMaker decision string or enum to an AvailableAction."""
        if not mouse_target:
            return None

        # Handle both Enum and String inputs
        target_str = str(mouse_target).split('.')[-1].lower() if hasattr(mouse_target, 'name') else str(mouse_target).lower()

        # 1. Fold logic (Safety: Never fold if check is possible)
        if target_str == 'fold':
            # Check for standard poker buttons
            check_btn = state.get_action_by_type('check') or state.get_action_by_type('call')
            if check_btn and state.has_check_button:
                log.info("MAP: Decision was Fold but Check is available - checking instead.")
                return check_btn
            return state.get_action_by_type('fold')

        # 2. Call/Check logic
        if target_str in ('call', 'call2', 'call deception', 'check', 'check deception'):
            # Prioritize matching button, then fallback to anything that doesn't cost more
            return (state.get_action_by_type('check') or 
                    state.get_action_by_type('call') or 
                    state.get_action_by_type('fold')) # Final safety fallback

        # 3. Raise/Bet logic
        if any(kw in target_str for kw in ('raise', 'bet', '3bet', '4bet', 'allin', 'bluff')):
            # Prioritize best betting buttons
            btn = (state.get_action_by_type('raise') or
                   state.get_action_by_type('bet') or
                   state.get_action_by_type('all_in') or
                   state.get_action_by_type('call') or
                   state.get_action_by_type('check'))
            if btn:
                log.debug(f"MAP: {mouse_target} -> {btn.action_type}")
                return btn

        # 4. Lobby/Special buttons
        if 'imback' in target_str:
            return state.get_action_by_type('im_back') or state.get_action_by_type('deal_me_in')

        return None

    def _reliable_click(self, x_pt: int, y_pt: int, label: str = ""):
        """Click at macOS POINT coordinates with move-before-click.

        More reliable than pyautogui.click() because:
        1. Moves mouse to position first (prevents teleport-swallowed clicks)
        2. Sets kCGMouseEventClickState for proper click registration
        3. Small delay between down/up events
        """
        try:
            from Quartz import (
                CGEventCreateMouseEvent, CGEventPost, CGPoint,
                kCGEventLeftMouseDown, kCGEventLeftMouseUp,
                kCGEventMouseMoved, kCGHIDEventTap, kCGMouseButtonLeft,
                CGEventSetIntegerValueField,
            )
            from Quartz import kCGMouseEventClickState
            import time as _t
            point = CGPoint(x_pt, y_pt)
            # Move mouse first
            move_evt = CGEventCreateMouseEvent(None, kCGEventMouseMoved, point, kCGMouseButtonLeft)
            CGEventPost(kCGHIDEventTap, move_evt)
            _t.sleep(0.02)
            # Mouse down
            down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(down, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, down)
            _t.sleep(0.05)
            # Mouse up
            up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, kCGMouseButtonLeft)
            CGEventSetIntegerValueField(up, kCGMouseEventClickState, 1)
            CGEventPost(kCGHIDEventTap, up)
            log.debug(f"ReliableClick '{label}' at ({x_pt}, {y_pt})")
        except ImportError:
            import pyautogui
            pyautogui.click(x_pt, y_pt)

    def _is_window_active(self, window_name: str) -> bool:
        """Check if the named window is the frontmost window on the system."""
        try:
            script = f'''
            tell application "System Events"
                tell (first process whose frontmost is true)
                    return name of window 1
                end tell
            end tell
            '''
            res = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=1)
            front_name = res.stdout.strip()
            # Loose match because GGPoker titles change (blinds/table ID)
            return window_name in front_name or front_name in window_name
        except Exception:
            return False

    def _activate_table_window(self, session: TableSession):
        """Bring the specific table window to front before clicking."""
        try:
            wid = session.window.window_id
            name = session.window.name
            log.debug(f"Activating window: {name} (wid={wid})")
            
            # Use AXRaise which is more reliable for multi-window focus on macOS
            script = f'''
            tell application "System Events"
                tell process "GGnet"
                    set frontmost to true
                    perform action "AXRaise" of window {wid}
                end tell
            end tell
            '''
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=2)
            
            # Verification loop (wait up to 0.5s)
            for _ in range(5):
                if self._is_window_active(name):
                    return True
                time.sleep(0.1)
                
            log.warning(f"Focus verification failed for {name}")
            return False
        except Exception as e:
            log.debug(f"Window activation failed (wid={session.window.window_id}): {e}")
            return False

    def _verify_button_color(self, x_pt: int, y_pt: int) -> bool:
        """Quick color check at click target to verify a button is still there.

        GGPoker action buttons are dark red (H=10-16, S>80, V>90).
        Returns True if the pixel looks like a button, False if it looks
        like felt/avatar/profile text.
        """
        try:
            from PIL import ImageGrab
            # Grab a tiny 5x5 region around the click point (in pixels = points * 2)
            px, py = x_pt * 2, y_pt * 2
            region = ImageGrab.grab(bbox=(px - 4, py - 4, px + 5, py + 5))
            arr = np.array(region)
            if arr.size == 0:
                return True  # Can't verify, proceed anyway
            # Check average color — buttons are saturated, felt/avatars are not
            avg = arr.mean(axis=(0, 1))
            r, g, b = avg[0], avg[1], avg[2]
            # Dark red button: R > G and R > B, and R > 60
            is_dark_red = r > g * 1.3 and r > b * 1.3 and r > 60
            # Green button: G > R and G > B
            is_green = g > r * 1.2 and g > b * 1.2 and g > 80
            # Yellow/orange button
            is_orange = r > 100 and g > 60 and b < 80
            if is_dark_red or is_green or is_orange:
                return True
            log.warning(f"Pre-click color guard FAILED at ({x_pt},{y_pt}): "
                        f"RGB=({r:.0f},{g:.0f},{b:.0f}) — not a button color")
            return False
        except Exception as e:
            log.debug(f"Color guard exception: {e}")
            return True  # Can't verify, proceed anyway

    def _click_action(self, action, session: TableSession, state, decision_label: str, high_pressure: bool = False):
        """Click an action button using screen coordinates from GameState."""
        import pyautogui
        import time as _time
        w = session.window

        if high_pressure:
            log.warning(f"HIGH PRESSURE MODE active for {w.name} - skipping verification")

        # 1. Bring window to front
        if not self._activate_table_window(session):
            log.error(f"Sizing ABORTED: Could not get stable focus on {w.name}")
            return

        # 2. SAFETY: Dynamic button validation.
        if not (0 <= action.screen_x_pt <= w.x + w.width and 0 <= action.screen_y_pt <= w.y + w.height):
            log.error(f"ABORT CLICK: {action.action_type} at ({action.screen_x_pt},{action.screen_y_pt}) "
                      f"is OUTSIDE table bounds — skipping")
            return

        # 3. SAFETY: Color guard DISABLED (Trust OCR detection)
        # Previously too strict for some themes, causing silent aborts.
        log.debug(f"Color guard skipped for {action.action_type} at ({action.screen_x_pt},{action.screen_y_pt})")

        # Compute desired raise amount for bet sizing decisions
        target_amount = self._compute_raise_amount(state, decision_label)
        log.info(f"ACTION START: label={decision_label} type={action.action_type} target={target_amount:.1f}BB")

        if self.dry_run:
            # === DRY-RUN: log what WOULD happen, don't click ===
            raise_info = f" raise_to={target_amount:.1f}BB" if target_amount else ""
            log.info(f"DRY-RUN WOULD CLICK: {action.action_type} at ({action.screen_x_pt}, {action.screen_y_pt}) "
                     f"[decision={decision_label}{raise_info}] | "
                     f"cards={state.my_cards} board={state.board_cards} "
                     f"pot={state.pot:.1f} call={state.call_amount:.1f}")
            session.last_action_time = datetime.datetime.utcnow()
            cards_key = ','.join(sorted(state.my_cards)) if state.my_cards else ''
            board_count = len(state.board_cards) if state.board_cards else 0
            pot_key = round(state.pot, 1) if state.pot else 0
            session._last_acted_key = f"{cards_key}|{board_count}|{pot_key}"
            self.stats['hands_played'] += 1
            action_key = action.action_type
            if action_key in self.stats['decisions']:
                self.stats['decisions'][action_key] += 1
            # Save screenshot with overlay for review
            try:
                self._save_dry_run_screenshot(session, state, action, decision_label, target_amount)
            except Exception as e:
                log.debug(f"Dry-run screenshot save failed: {e}")
            return

        # --- Activate the table window and verify before clicking ---
        self._activate_table_window(session)

        # Pre-click color guard: verify the action button is still there
        if not self._verify_button_color(action.screen_x_pt, action.screen_y_pt):
            log.warning(f"ABORT CLICK: button color guard failed for {action.action_type} "
                        f"at ({action.screen_x_pt},{action.screen_y_pt}), skipping action")
            return

        if target_amount and target_amount > 0 and action.action_type in ('raise', 'bet'):
            raise_x = action.screen_x_pt
            raise_y = action.screen_y_pt
            # BB display mode: pot is already in BB, no conversion needed
            pot_bb = max(state.pot or 0, 0.01)
            is_preflop = not state.board_cards or len(state.board_cards) == 0

            # Vertical offset: the sizing field is usually located above the 'raise' or 'bet' button.
            # We use the detected position of the primary action button to triangulate the input field.
            # This is 100% immune to window-position drift.
            
            # Find the 'bet' or 'raise' button center
            bet_btn = state.get_action_by_type('bet') or state.get_action_by_type('raise')
            if bet_btn:
                # GGPoker macOS Calibration:
                # The input box is ~45 pixels (points) ABOVE and ~50 pixels LEFT of the raise button center.
                input_x = bet_btn.screen_x_pt - 50
                input_y = bet_btn.screen_y_pt - 45
            else:
                # Use the passed-in action (even if it's the fallback)
                input_x = action.screen_x_pt - 50
                input_y = action.screen_y_pt - 45

            # BB display mode is ON — input field expects BB amounts directly
            bb_amount = round(target_amount, 1)
            amount_str = str(bb_amount)

            # -- FOCUS SHIELD: ensure this table is active before typing --
            if not self._activate_table_window(session):
                log.error(f"Sizing ABORTED: Could not get stable focus on {session.window.name}")
                return

            # --- POT SIZE SHORTCUTS (Fast Path) ---
            # Use standard UI buttons for standard sizes (33, 50, 75, 100) for 100% reliability.
            ref_x = bet_btn.screen_x_pt if bet_btn else action.screen_x_pt
            ref_y = bet_btn.screen_y_pt if bet_btn else action.screen_y_pt

            shortcut_used = False
            # Decision mapping to GGPoker standard shortcuts
            # (x_offset, label_match)
            if 'half pot' in decision_label.lower():
                self._reliable_click(ref_x - 120, ref_y - 45, 'shortcut_50%')
                shortcut_used = True
            elif 'bet pot' in decision_label.lower() or '100%' in decision_label.lower():
                self._reliable_click(ref_x - 35, ref_y - 45, 'shortcut_100%')
                shortcut_used = True
            elif 'bet 33%' in decision_label.lower():
                self._reliable_click(ref_x - 170, ref_y - 45, 'shortcut_33%')
                shortcut_used = True
            elif 'bet 75%' in decision_label.lower():
                self._reliable_click(ref_x - 80, ref_y - 45, 'shortcut_75%')
                shortcut_used = True

            if shortcut_used:
                log.info(f"Using {decision_label} POT shortcut button (Fast Path)")
                _time.sleep(0.2)
                # Confirm the raise immediately
                self._reliable_click(action.screen_x_pt, action.screen_y_pt, 'confirm_raise_shortcut')
                return True

            # --- FINE-TUNE INPUT POSITION ---
            # Scan a 40x40 region around (input_x, input_y) for the white/light-gray 
            # background of the input box to ensure we click inside it.
            try:
                from PIL import ImageGrab
                # Points to Pixels (Retina)
                search_x, search_y = input_x * 2, input_y * 2
                region = ImageGrab.grab(bbox=(search_x - 40, search_y - 40, search_x + 40, search_y + 40))
                pix = np.array(region)
                # Input boxes are usually very bright (white/off-white)
                mask = (pix[:,:,0] > 200) & (pix[:,:,1] > 200) & (pix[:,:,2] > 200)
                coords = np.argwhere(mask)
                if coords.size > 0:
                    center_y, center_x = coords.mean(axis=0)
                    # Convert back to relative points
                    fine_x = input_x + (center_x - 40) / 2
                    fine_y = input_y + (center_y - 40) / 2
                    log.info(f"Fine-tuned input box: ({input_x},{input_y}) -> ({fine_x:.1f},{fine_y:.1f})")
                    input_x, input_y = int(fine_x), int(fine_y)
            except Exception as e:
                log.debug(f"Input fine-tuning failed: {e}")

            # Click input field (Multiple dithered clicks to ensure focus)
            log.info(f"PREPARING to type {bb_amount:.1f} BB into {session.window.name}")
            self._reliable_click(input_x, input_y, 'input_field_center')
            _time.sleep(0.1)
            # Triple click to select all (standard Mac/GGPoker behavior)
            pyautogui.click(clicks=3, interval=0.05)
            _time.sleep(0.2)
            
            # -- BRUTE FORCE CLEAR (V4) --
            pyautogui.hotkey('command', 'a') # Select all
            _time.sleep(0.1)
            pyautogui.press('backspace')
            pyautogui.hotkey('command', 'backspace') # Mac line clear
            for _ in range(10): pyautogui.press('backspace')
            _time.sleep(0.2)
            
            # --- VERIFIED TYPING LOOP ---
            max_typing_retries = 3
            typing_success = False
            
            for t_attempt in range(max_typing_retries):
                log.info(f"Typing Attempt {t_attempt+1}/{max_typing_retries}: {amount_str} BB")
                
                # Ensure focus
                self._reliable_click(input_x, input_y, 'input_focus')
                pyautogui.hotkey('command', 'a')
                pyautogui.press('backspace')
                _time.sleep(0.2)
                
                # Type character by character with optimized cadence
                # Use slightly slower delay (0.1s) for higher reliability
                for char in amount_str:
                    pyautogui.typewrite(char)
                    _time.sleep(0.1) 
                
                _time.sleep(0.3)
                pyautogui.press('enter')
                
                # HIGH PRESSURE SKIP: Don't wait for UI or verify if running out of time
                if high_pressure:
                    log.info("HIGH PRESSURE: Skipping verification, clicking raise immediately")
                    typing_success = True
                    break

                _time.sleep(0.6) # Wait for UI to reflect change
                
                # VERIFICATION: Read the 'Raise' button text to see the resulting amount
                try:
                    v_state = self.capture_game_state(session)
                    raise_btn = v_state.get_action_by_type('raise') or v_state.get_action_by_type('bet')
                    
                    if raise_btn and raise_btn.amount:
                        v_amt = float(raise_btn.amount)
                        # LENIENT VERIFICATION: 
                        # 1. Close enough (rounding)
                        # 2. Common OCR decimal errors (e.g. 2.0 read as 20 or vice versa)
                        is_match = abs(v_amt - bb_amount) < 0.15
                        if not is_match:
                            # Check for 10x multiplier/divisor (missing decimal)
                            if abs(v_amt/10.0 - bb_amount) < 0.15 or abs(v_amt*10.0 - bb_amount) < 0.15:
                                log.info(f"OCR Leniency: {v_amt} BB looks like {bb_amount} BB with decimal error. Proceeding.")
                                is_match = True

                        if is_match:
                            log.info(f"BET VERIFIED: Intended {bb_amount} BB, Screen shows {v_amt} BB. Proceeding.")
                            typing_success = True
                            action = raise_btn
                            break
                        else:
                            # --- NEW: Fine-Tune Correction ---
                            # If we are close (within 1.0 BB), use the +/- buttons to adjust
                            # instead of re-typing everything.
                            diff = bb_amount - v_amt
                            if abs(diff) <= 1.0 and abs(diff) >= 0.05:
                                log.info(f"Fine-tuning bet: diff={diff:+.2f} BB. Using +/- buttons.")
                                # GGPoker +/- buttons are usually on the far ends of the input box
                                # (input_x - 100, input_y) for Minus, (input_x + 100, input_y) for Plus
                                btn_x = input_x + (80 if diff > 0 else -80)
                                clicks = int(abs(diff) / 0.1) # Assuming 0.1 BB per click
                                for _ in range(min(clicks, 10)):
                                    self._reliable_click(btn_x, input_y, 'fine_tune_button')
                                    _time.sleep(0.1)
                                
                                # Quick re-verify after fine-tune
                                _time.sleep(0.3)
                                v_state2 = self.capture_game_state(session)
                                r_btn2 = v_state2.get_action_by_type('raise') or v_state2.get_action_by_type('bet')
                                if r_btn2 and r_btn2.amount and abs(float(r_btn2.amount) - bb_amount) < 0.15:
                                    log.info(f"Fine-tune SUCCESS: Now shows {r_btn2.amount} BB")
                                    typing_success = True
                                    action = r_btn2
                                    break

                            log.error(f"BET MISMATCH: Intended {bb_amount} BB, but screen shows {v_amt} BB! RETRYING...")
                    else:
                        log.warning("Verification failed: Could not read Raise button amount. Retrying typing...")
                except Exception as e:
                    log.error(f"Verification error: {e}")
                
                _time.sleep(0.5)

            if not typing_success:
                log.warning(f"Failed to verify bet after {max_typing_retries} attempts. FORCING action anyway to avoid loop.")
                typing_success = True # Force success to click whatever is there

            # --- DIALOG SHIELD ---
            dialog_x = session.window.x + int(session.window.width * 0.43)
            dialog_y = session.window.y + int(session.window.height * 0.62)
            self._reliable_click(dialog_x, dialog_y, 'dismiss_bet_dialog')
            _time.sleep(0.3)

        # FINAL CLICK
        self._reliable_click(action.screen_x_pt, action.screen_y_pt, action.action_type)
        log.info(f"Clicked {action.action_type} at ({action.screen_x_pt}, {action.screen_y_pt}) "
                 f"[decision={decision_label}]")
        
        # --- NEW: Post-Action Verification (Flawless Execution) ---
        # After clicking, we wait a moment and verify the buttons are gone.
        # If they are still there, the click failed (UI lag).
        _time.sleep(0.4)
        v_state = self.capture_game_state(session)
        if v_state and v_state.is_my_turn:
            # Still our turn? The action didn't register.
            log.warning(f"ACTION FAILED: {action.action_type} still visible on {session.window.name}. RE-CLICKING.")
            # Re-click with a small offset to hit a different part of the button
            self._reliable_click(action.screen_x_pt + 5, action.screen_y_pt + 2, action.action_type)
            _time.sleep(0.3)
        
        # --- NEW: Handle "Are you sure?" dialog ---
        if action.action_type in ('raise', 'bet'):
            _time.sleep(0.2)
            if self._handle_bet_confirmation(session):
                log.info("Handled confirmation dialog via verification path")

        session.last_action_time = datetime.datetime.utcnow()
        # Track what we acted on to prevent duplicate actions on same situation
        cards_key = ','.join(sorted(state.my_cards)) if state.my_cards else ''
        board_count = len(state.board_cards) if state.board_cards else 0
        pot_key = round(state.pot, 1) if state.pot else 0
        session._last_acted_key = f"{cards_key}|{board_count}|{pot_key}"

        self.stats['hands_played'] += 1
        action_key = action.action_type
        if action_key in self.stats['decisions']:
            self.stats['decisions'][action_key] += 1

        log_action('new_ocr_action', success=True, details={
            'decision': decision_label,
            'action': action.action_type,
            'cards': state.my_cards,
            'board': state.board_cards,
            'pot': state.pot,
            'raise_target': target_amount,
            'latency_ms': state.ocr_latency_ms,
        })

        # --- Autonomous feedback loop ---
        self._maybe_auto_adjust()

    def _handle_bet_confirmation(self, session: TableSession):
        """Detect and click the red 'Bet $X.XX' confirmation button in popups."""
        try:
            from PIL import ImageGrab
            import pyautogui
            w = session.window
            
            # GGPoker confirmation dialogs appear in the center of the table
            cx1, cy1 = w.x * 2 + int(w.width * 0.3 * 2), w.y * 2 + int(w.height * 0.4 * 2)
            cx2, cy2 = w.x * 2 + int(w.width * 0.7 * 2), w.y * 2 + int(w.height * 0.8 * 2)
            
            img = ImageGrab.grab(bbox=(cx1, cy1, cx2, cy2))
            pix = np.array(img)
            
            # Look for the large red button (GGPoker Red: ~150, 40, 40)
            mask = (pix[:,:,0] > 140) & (pix[:,:,1] < 60) & (pix[:,:,2] < 60)
            coords = np.argwhere(mask)
            
            if coords.size > 500: # Threshold to ensure it's a button, not just a few pixels
                center_y, center_x = coords.mean(axis=0)
                # Convert back to points: (pixel_start + offset) / 2
                click_x = (cx1 + center_x) / 2
                click_y = (cy1 + center_y) / 2
                
                log.info(f"AUTONOMOUS: Detected 'Are you sure?' dialog. Clicking RED BET BUTTON at ({click_x:.1f}, {click_y:.1f})")
                
                # Small random offset for human-like click
                import random
                pyautogui.click(click_x + random.randint(-5, 5), click_y + random.randint(-5, 5))
                _time.sleep(0.3)
                # One more click just in case
                pyautogui.click(click_x + random.randint(-5, 5), click_y + random.randint(-5, 5))
                return True
            return False
        except Exception as e:
            log.debug(f"Bet confirmation check failed: {e}")
        return False

    def _maybe_auto_adjust(self):
        """Autonomous feedback loop: reload/retune strategy adjustments."""
        hands = self.stats['hands_played']

        # Reload cached adjustments every N hands
        if hands - self._last_adj_reload >= self._adj_reload_interval:
            self._last_adj_reload = hands
            try:
                from gamble.decisionmaker.decisionmaker import _strategy_adj
                import gamble.decisionmaker.decisionmaker as dm_module
                dm_module._strategy_adj = None  # Force reload on next _get_adj()
                log.info(f"AUTO-ADJUST: Reloaded strategy adjustments (hand #{hands})")
            except Exception as e:
                log.debug(f"AUTO-ADJUST reload failed: {e}")

        # Auto-run strategy adjuster every M hands
        if hands - self._last_adj_retune >= self._adj_retune_interval:
            self._last_adj_retune = hands
            try:
                from gamble.tools.strategy_adjuster import load_adjustments, analyze_and_adjust, save_adjustments, HAND_HISTORY_PATH
                import json as _json
                hand_records = []
                if os.path.exists(HAND_HISTORY_PATH):
                    with open(HAND_HISTORY_PATH) as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    hand_records.append(_json.loads(line))
                                except _json.JSONDecodeError:
                                    continue
                if len(hand_records) >= 30:
                    # Analyze last 500 hands
                    recent = hand_records[-500:]
                    adj = analyze_and_adjust(recent)
                    save_adjustments(adj)
                    leaks = adj.get('detected_leaks', [])
                    log.info(f"AUTO-ADJUST: Analyzed {len(recent)} hands, "
                             f"found {len(leaks)} leaks, saved adjustments")
                    for leak in leaks:
                        log.info(f"  LEAK: {leak}")
                    # Force reload
                    import gamble.decisionmaker.decisionmaker as dm_module
                    dm_module._strategy_adj = None
            except Exception as e:
                log.error(f"AUTO-ADJUST retune failed: {e}")

        # Save session stats periodically
        if hands % 25 == 0 and hands > 0:
            self._save_session_stats()

    def _save_dry_run_screenshot(self, session, state, action, decision_label, target_amount):
        """Save annotated screenshot for dry-run review."""
        try:
            screenshot = self.get_table_screenshot(session.window)
            import cv2
            img = np.array(screenshot)

            # Draw a circle where we WOULD click
            cx, cy = action.screen_x_pt - session.window.x, action.screen_y_pt - session.window.y
            # Scale to pixels (Retina 2x)
            px, py = cx * 2, cy * 2
            if 0 <= px < img.shape[1] and 0 <= py < img.shape[0]:
                cv2.circle(img, (px, py), 20, (0, 255, 0), 3)
                cv2.putText(img, f"{decision_label}", (px - 40, py - 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Add info text at top
            info = (f"cards={state.my_cards} board={state.board_cards} "
                    f"pot={state.pot:.1f} call={state.call_amount:.1f} "
                    f"eq={getattr(session._table, 'equity', 0):.3f}")
            cv2.putText(img, info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = os.path.join('data', 'learning', 'dry_run')
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f'{ts}_{decision_label}_{state.my_cards}.png')
            from PIL import Image
            Image.fromarray(img).save(path)
            log.info(f"DRY-RUN screenshot: {path}")
        except Exception as e:
            log.debug(f"Dry-run screenshot failed: {e}")

    def _get_villain_id(self, session, state):
        """Determine the best villain ID to use for opponent lookup.

        In Rush & Cash, opponents change every hand, so we use table-level
        pool stats. For Spin & Gold / cash games, we track individual
        opponents by their player name from OCR.
        """
        table_name = getattr(session.window, 'name', '') if session.window else ''
        is_rush = ('Rush' in table_name or 'rush' in table_name)

        if is_rush:
            # Rush & Cash: pool-level tracking (opponents change every hand)
            if '$0.01' in table_name or '$0.02' in table_name:
                return 'pool_rush_2nl'
            elif '$0.05' in table_name or '$0.10' in table_name:
                return 'pool_rush_10nl'
            else:
                return 'pool_rush_default'

        # Non-Rush: try to get individual opponent name
        if state and hasattr(state, 'players') and state.players:
            # Find the primary active non-hero opponent
            active_villains = [p for p in state.players
                               if p.is_active and not p.is_hero and p.name]
            if active_villains:
                # Use the first active villain's name as the ID
                # Clean the name: strip whitespace, lowercase for consistency
                villain_name = active_villains[0].name.strip()
                if villain_name and len(villain_name) >= 2:
                    return f"player_{villain_name}"

        # Fallback to pool-level
        if 'Spin' in table_name or 'Gold' in table_name:
            return 'pool_spin'
        return 'villain_default'

    def _track_opponent(self, session, state, t):
        """Infer and record opponent actions from game state changes.

        Compares current state vs previous state to determine what the
        opponent did, then records it in the opponent modeler.
        """
        if not self.opponent_modeler:
            return

        villain_id = self._get_villain_id(session, state)
        if villain_id.startswith('player_'):
            log.debug(f"Tracking individual opponent: {villain_id}")

        # Estimate villain's position for position-specific stats
        villain_position = None
        if state and hasattr(state, 'players') and state.players:
            active_villains = [p for p in state.players
                               if p.is_active and not p.is_hero]
            if active_villains and hasattr(state, 'dealer_seat'):
                # Simple position estimate based on seat relative to dealer
                # This is approximate — exact position depends on who folded
                villain_position = getattr(state, 'position', None)
                # Invert: if we're BTN, villain is likely BB/SB; if we're BB, villain could be BTN
                _pos_inverse = {
                    'BTN': 'BB', 'SB': 'UTG', 'BB': 'BTN',
                    'UTG': 'CO', 'MP': 'BTN', 'CO': 'SB',
                }
                if villain_position:
                    villain_position = _pos_inverse.get(villain_position, None)

        prev_state = getattr(session, '_last_game_state', None)

        # Detect new hand: cards changed or board reset
        prev_cards = getattr(prev_state, 'my_cards', None) if prev_state else None
        curr_cards = state.my_cards
        is_new_hand = (prev_cards != curr_cards and curr_cards and len(curr_cards) == 2)

        if is_new_hand:
            self.opponent_modeler.new_hand([villain_id])
            # Reset Bayesian range for new hand
            session._bayesian_villain_range = None
            session._bayesian_last_street = ""
            session._last_opp_track_key = None  # Reset dedup for new hand

        if prev_state is None:
            return

        # Infer opponent action from state change
        prev_board = getattr(prev_state, 'board_cards', []) or []
        curr_board = getattr(state, 'board_cards', []) or []
        prev_pot = getattr(prev_state, 'pot', 0) or 0
        curr_pot = getattr(state, 'pot', 0) or 0
        is_preflop = not curr_board

        # Did opponent have initiative? (we were facing a bet)
        opp_has_init = getattr(t, 'other_player_has_initiative', False)
        has_raiser = not np.isnan(getattr(t, 'first_raiser_utg', np.nan))

        # Deduplicate: only record opponent action once per street per hand
        # _track_opponent is called every poll cycle (~0.5s), not just once
        _track_key = f"{len(curr_board)}_{is_preflop}_{opp_has_init}_{curr_pot:.1f}"
        _last_key = getattr(session, '_last_opp_track_key', None)
        if _track_key == _last_key:
            return  # Already recorded this action
        session._last_opp_track_key = _track_key

        # If it's our turn and opponent raised/bet into us
        if state.is_my_turn and opp_has_init:
            pot_increase = curr_pot - prev_pot
            if is_preflop and has_raiser:
                # Opponent raised preflop
                self.opponent_modeler.record_preflop_action(
                    villain_id, 'raise', has_raiser_before=False,
                    position=villain_position)
            elif not is_preflop and pot_increase > 0:
                # Opponent bet or raised postflop
                # Determine if it was a c-bet (preflop raiser betting flop)
                is_cbet = (len(curr_board) == 3 and has_raiser)
                self.opponent_modeler.record_postflop_action(
                    villain_id, 'bet', is_cbet=is_cbet)

        # If opponent called our previous bet (pot grew but it's our turn again)
        elif state.is_my_turn and not opp_has_init and prev_pot > 0:
            pot_increase = curr_pot - prev_pot
            if pot_increase > 0.5 and len(curr_board) == len(prev_board):
                # Same street, pot grew, opponent called
                if is_preflop:
                    self.opponent_modeler.record_preflop_action(
                        villain_id, 'call', has_raiser_before=True,
                        position=villain_position)
                else:
                    # Was our bet a c-bet?
                    was_cbet = (len(curr_board) == 3 and
                                getattr(session, '_we_were_preflop_raiser', False))
                    self.opponent_modeler.record_postflop_action(
                        villain_id, 'call', facing_cbet=was_cbet)

        # Track if we raised preflop (for c-bet detection)
        if is_preflop and state.is_my_turn:
            session._we_were_preflop_raiser = has_raiser  # Simplified heuristic

        # ── Bayesian range narrowing (Phase 4) ──
        # When villain acts postflop, narrow their combo range
        if not is_preflop and state.is_my_turn and curr_board and len(curr_board) >= 3:
            try:
                from gamble.decisionmaker.range_equity import (
                    get_bayesian_tracker, should_use_bayesian,
                )
                hero_cards = getattr(state, 'my_cards', None) or []
                if len(hero_cards) == 2:
                    hero_stack_bb = 0
                    bb = getattr(state, 'big_blind', 0) or 1.0
                    hero_stack = getattr(state, 'hero_stack', 0) or 0
                    hero_stack_bb = hero_stack / bb if bb > 0 else 0
                    pot_bb = (curr_pot / bb) if bb > 0 else 0
                    n_actions = len((session._bayesian_villain_range or {}).get('history', []))

                    # Get opponent profile if available
                    opp_hands = 0
                    opp_type = 'unknown'
                    if self.opponent_modeler:
                        profile = self.opponent_modeler.get_profile(villain_id)
                        if profile:
                            opp_hands = profile.get('hands', 0)
                            opp_type = profile.get('type', 'unknown')

                    street_map_b = {3: 'flop', 4: 'turn', 5: 'river'}
                    street_name = street_map_b.get(len(curr_board), 'flop')

                    activation = should_use_bayesian(
                        hero_stack_bb=hero_stack_bb,
                        pot_bb=pot_bb,
                        street=street_name,
                        num_villain_actions=n_actions,
                        has_check_button=getattr(state, 'check_button', False),
                        hero_equity=0.5,  # Unknown yet, will be computed later
                        opponent_hands_seen=opp_hands,
                    )

                    if activation['use']:
                        tracker = get_bayesian_tracker()

                        # Create initial range if needed
                        if session._bayesian_villain_range is None:
                            v_pos = 'CO'  # Default, refined below
                            pf_action = 'open'
                            if villain_position:
                                v_pos = villain_position
                            session._bayesian_villain_range = tracker.create_initial_range(
                                position=v_pos, preflop_action=pf_action,
                                player_type=opp_type, hero_cards=hero_cards,
                                board=curr_board,
                            )
                            log.debug(f"BAYESIAN: Created initial range for villain "
                                      f"({len(session._bayesian_villain_range.get('combos', {}))} combos)")

                        # Determine villain action and narrow
                        if session._bayesian_last_street != street_name:
                            if opp_has_init:
                                v_action = 'bet'
                                v_bet_pct = (curr_pot - prev_pot) / max(prev_pot, 0.01) if prev_pot > 0 else 0.5
                            elif not opp_has_init and (curr_pot - prev_pot) > 0.5 and len(curr_board) == len(prev_board):
                                v_action = 'call'
                                v_bet_pct = 0.0
                            else:
                                v_action = 'check'
                                v_bet_pct = 0.0

                            session._bayesian_villain_range = tracker.narrow_range(
                                session._bayesian_villain_range,
                                curr_board, v_action, v_bet_pct, street_name,
                                player_type=opp_type,
                            )
                            session._bayesian_last_street = street_name
                            n_combos = sum(1 for _, _, w in session._bayesian_villain_range.get('combos', []) if w > 0.001)
                            log.debug(f"BAYESIAN: Narrowed to {n_combos} combos after {v_action} on {street_name}")

            except Exception as e:
                log.debug(f"Bayesian range narrowing in runner failed: {e}")

    def _track_pnl(self, session, state, decision_obj=None):
        """Track P&L by comparing stack between decisions.

        Called after each decision. Computes stack delta since last action.
        Also records hand outcome back to hand history and opponent modeler.
        """
        hero_stack = getattr(state, 'hero_stack', 0) or 0
        prev_stack = getattr(session, '_prev_stack', None)

        if prev_stack is not None and hero_stack > 0 and prev_stack > 0:
            delta = hero_stack - prev_stack
            if abs(delta) > 0.01:  # Ignore tiny rounding
                self.stats['pnl_bb'] += delta
                if delta > 0:
                    self.stats['hands_won'] += 1
                    if delta > self.stats['biggest_pot_won']:
                        self.stats['biggest_pot_won'] = delta
                    # Record win in opponent modeler (opponent lost at showdown)
                    if self.opponent_modeler:
                        villain_id = self._get_villain_id(session, state)
                        self.opponent_modeler.record_showdown(villain_id, won=False)
                elif delta < 0:
                    self.stats['hands_lost'] += 1
                    if abs(delta) > abs(self.stats['biggest_pot_lost']):
                        self.stats['biggest_pot_lost'] = delta
                    # Record loss (opponent won at showdown)
                    if self.opponent_modeler:
                        villain_id = self._get_villain_id(session, state)
                        self.opponent_modeler.record_showdown(villain_id, won=True)

                # Log outcome back to hand history
                self._log_hand_outcome(session, delta, state)

                # Record spot type for live learning
                last_dec = getattr(session, '_last_decision', '')
                last_street = getattr(session, '_last_street', 'PreFlop')
                spot_cat = self._classify_spot(last_dec, last_street)
                if spot_cat:
                    self.spot_tracker.record(spot_cat, delta > 0, delta)

        if hero_stack > 0:
            session._prev_stack = hero_stack

        # Track EV
        if decision_obj and hasattr(decision_obj, 'decision_ev'):
            self.stats['ev_total'] += decision_obj.decision_ev

    def _log_hand_outcome(self, session, delta, state):
        """Append outcome record to hand history for decision quality feedback."""
        import json as _json
        try:
            record = {
                'ts': datetime.datetime.utcnow().isoformat(),
                'type': 'outcome',
                'result': 'win' if delta > 0 else 'loss',
                'delta_bb': round(delta, 2),
                'table': session.window.name if session.window else '?',
            }
            # Include our last decision for correlation
            last_decision = getattr(session, '_last_decision', None)
            if last_decision:
                record['last_action'] = last_decision
            last_cards = getattr(session, '_cached_cards', None)
            if last_cards:
                record['cards'] = last_cards

            path = os.path.join('data', 'learning', 'hand_history.jsonl')
            with open(path, 'a') as f:
                f.write(_json.dumps(record) + '\n')
        except Exception:
            pass

    def _classify_spot(self, decision, street):
        """Classify a decision into a spot category for tracking."""
        if not decision:
            return None
        dec = decision.lower() if isinstance(decision, str) else str(decision).lower()
        is_preflop = street == 'PreFlop' if street else True

        if 'fold' in dec:
            return 'fold'
        elif 'call' in dec or 'check' in dec:
            return 'preflop_call' if is_preflop else 'postflop_call'
        elif 'bluff' in dec:
            return 'bluff'
        elif 'bet' in dec or 'raise' in dec:
            return 'preflop_raise' if is_preflop else 'postflop_bet'
        return None

    def _save_session_stats(self):
        """Save running session stats to disk."""
        import json as _json
        try:
            hands = self.stats['hands_played']
            pnl = self.stats['pnl_bb']
            bb_per_100 = (pnl / hands * 100) if hands > 0 else 0
            self.stats['bb_per_100'] = round(bb_per_100, 2)
            self.stats['session_hands'] = hands

            with open(self.stats_file, 'w') as f:
                _json.dump(self.stats, f, indent=2, default=str)
            log.info(f"SESSION: {hands} hands | P&L: {pnl:+.1f} BB | "
                     f"BB/100: {bb_per_100:+.1f} | EV: {self.stats['ev_total']:+.1f} | "
                     f"W/L: {self.stats['hands_won']}/{self.stats['hands_lost']}")
        except Exception as e:
            log.debug(f"Stats save failed: {e}")

    def _detect_play_again(self, session: TableSession) -> bool:
        """Detect tournament result popup and click 'Play Again' to re-register.

        After elimination in Mystery Battle Royale and other tournaments,
        GGPoker shows a popup with Share / Play Again / Close buttons.
        We OCR the bottom of the table to find 'Play Again' text and click it.
        """
        try:
            import pyautogui
            screenshot = self.get_table_screenshot(session.window)
            if screenshot is None:
                return False

            img_np = np.array(screenshot)
            H_img, W_img = img_np.shape[:2]

            # Only scan the bottom 20% where buttons appear
            bottom_region = img_np[int(H_img * 0.80):, :]
            if bottom_region.size == 0:
                return False

            if not PYTESSERACT_AVAILABLE:
                return False

            import pytesseract
            from PIL import Image
            pil_region = Image.fromarray(bottom_region)
            data = pytesseract.image_to_data(pil_region, output_type=pytesseract.Output.DICT)

            play_found = False
            play_x, play_y = 0, 0
            for i, text in enumerate(data['text']):
                t_lower = text.strip().lower()
                if t_lower in ('play', 'again'):
                    # Found one of the words — use it as click target
                    px = data['left'][i] + data['width'][i] // 2
                    py = int(H_img * 0.80) + data['top'][i] + data['height'][i] // 2
                    if t_lower == 'play' or not play_found:
                        play_x, play_y = px, py
                        play_found = True

            if not play_found:
                return False

            # Convert pixel position to screen points
            table_x_pt = session.window.x
            table_y_pt = session.window.y
            screen_x = table_x_pt + play_x // 2
            screen_y = table_y_pt + play_y // 2

            if self.dry_run:
                log.info(f"DRY-RUN: Would click 'Play Again' at ({screen_x}, {screen_y})")
                return True

            pyautogui.click(screen_x, screen_y)
            log.info(f"TOURNAMENT RE-REGISTER: Clicked 'Play Again' at "
                     f"({screen_x}, {screen_y}) for {session.window.name}")
            self.stats['hands_played'] += 0  # Don't count this as a hand
            return True

        except Exception as e:
            log.debug(f"Play Again detection failed: {e}")
            return False

    def _detect_and_handle_rebuy(self, session: TableSession) -> bool:
        """Detect and handle the GGPoker 'Add Chips' rebuy dialog.

        When the player loses their stack in Rush & Cash, a popup appears
        with a slider to select the rebuy amount. We click "Max" then "OK".

        Returns True if a rebuy dialog was detected and handled.
        """
        import time as _time
        try:
            import pytesseract
        except ImportError:
            return False

        # Cooldown: don't spam rebuy detection
        last_rebuy = getattr(session, '_last_rebuy_attempt', 0)
        if time.time() - last_rebuy < 5.0:
            return False

        try:
            screenshot = self.get_table_screenshot(session.window)
        except Exception:
            return False

        # Convert PIL image to numpy for OCR
        import numpy as np
        img_np = np.array(screenshot)
        h_img, w_img = img_np.shape[:2]

        # OCR the center of the table where the dialog appears
        # The dialog is roughly in the center 60% of the table
        x_start = int(w_img * 0.20)
        x_end = int(w_img * 0.80)
        y_start = int(h_img * 0.15)
        y_end = int(h_img * 0.85)
        dialog_region = screenshot.crop((x_start, y_start, x_end, y_end))

        try:
            text = pytesseract.image_to_string(dialog_region)
        except Exception:
            return False

        text_lower = text.lower()

        # Check for rebuy dialog keywords
        if 'add chip' not in text_lower and 'amount to add' not in text_lower:
            return False

        log.info(f"Table {session.window.name}: REBUY DIALOG DETECTED")
        session._last_rebuy_attempt = time.time()

        # Phase 5.1+5.2: Rebuy cap and session stop-loss
        self._session_rebuys += 1
        self._buyins_lost += 1
        if self._session_rebuys > self._max_session_rebuys:
            log.error(f"REBUY LIMIT ({self._max_session_rebuys}) reached — NOT rebuying")
            return False
        if self._buyins_lost >= self._max_buyins_loss:
            log.error(f"SESSION STOP-LOSS: lost {self._buyins_lost} buy-ins, stopping bot")
            self.running = False
            return False
        log.info(f"Rebuy {self._session_rebuys}/{self._max_session_rebuys} | "
                 f"Stop-loss: {self._buyins_lost}/{self._max_buyins_loss} buy-ins")

        # Use pytesseract word-level detection to find "Max" button position
        import pyautogui
        from PIL import Image

        try:
            data = pytesseract.image_to_data(dialog_region, output_type=pytesseract.Output.DICT)
        except Exception:
            return False

        w = session.window

        # Find "Max" button and click it
        max_clicked = False
        for i, word in enumerate(data['text']):
            w_lower = word.strip().lower()
            if w_lower.startswith('max') or w_lower == 'max':
                # Get pixel position within dialog_region
                wx = data['left'][i] + data['width'][i] // 2
                wy = data['top'][i] + data['height'][i] // 2
                # Convert to full screenshot coordinates
                sx = x_start + wx
                sy = y_start + wy
                # Convert to screen points (Retina 2x)
                click_x = w.x + sx // 2
                click_y = w.y + sy // 2
                pyautogui.click(click_x, click_y)
                log.info(f"Table {session.window.name}: Clicked 'Max' at ({click_x}, {click_y})")
                max_clicked = True
                _time.sleep(0.3)
                break

        if not max_clicked:
            # Fallback: if we can't find "Max" text, look for it by position.
            # In the dialog, "Max" button is to the right of the slider,
            # roughly at 75% width, 65% height of the dialog.
            fallback_x = x_start + int((x_end - x_start) * 0.78)
            fallback_y = y_start + int((y_end - y_start) * 0.58)
            click_x = w.x + fallback_x // 2
            click_y = w.y + fallback_y // 2
            pyautogui.click(click_x, click_y)
            log.info(f"Table {session.window.name}: Clicked 'Max' (fallback) at ({click_x}, {click_y})")
            _time.sleep(0.3)

        # Now find and click the green "OK" button
        # Re-capture after clicking Max to get updated dialog
        screenshot2 = screenshot
        try:
            screenshot2 = self.get_table_screenshot(session.window)
            dialog2 = screenshot2.crop((x_start, y_start, x_end, y_end))
            data2 = pytesseract.image_to_data(dialog2, output_type=pytesseract.Output.DICT)
        except Exception:
            data2 = data  # Use original data as fallback

        ok_clicked = False
        for i, word in enumerate(data2['text']):
            if word.strip().lower() == 'ok':
                wx = data2['left'][i] + data2['width'][i] // 2
                wy = data2['top'][i] + data2['height'][i] // 2
                sx = x_start + wx
                sy = y_start + wy
                click_x = w.x + sx // 2
                click_y = w.y + sy // 2
                pyautogui.click(click_x, click_y)
                log.info(f"Table {session.window.name}: Clicked 'OK' at ({click_x}, {click_y})")
                ok_clicked = True
                _time.sleep(0.5)
                break

        if not ok_clicked:
            # Fallback: OK button is green, find it by color in the dialog area
            import cv2
            img2 = np.array(screenshot2)
            dialog_img = img2[y_start:y_end, x_start:x_end]
            hsv = cv2.cvtColor(dialog_img, cv2.COLOR_RGB2HSV)
            # Green OK button: H=35-85, S=50+, V=80+
            green_mask = cv2.inRange(hsv, (35, 50, 80), (85, 255, 255))
            contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            # Find the largest green region (the OK button)
            best_contour = None
            best_area = 0
            for c in contours:
                area = cv2.contourArea(c)
                if area > best_area and area > 500:
                    best_area = area
                    best_contour = c

            if best_contour is not None:
                bx, by, bw, bh = cv2.boundingRect(best_contour)
                cx = x_start + bx + bw // 2
                cy = y_start + by + bh // 2
                click_x = w.x + cx // 2
                click_y = w.y + cy // 2
                pyautogui.click(click_x, click_y)
                log.info(f"Table {session.window.name}: Clicked 'OK' (green button) at ({click_x}, {click_y})")
                ok_clicked = True
                _time.sleep(0.5)

        if ok_clicked:
            log.info(f"Table {session.window.name}: REBUY COMPLETE — waiting for Deal Me In")
            log_action('rebuy', success=True, details={'table': session.window.name})
            return True
        else:
            log.warning(f"Table {session.window.name}: REBUY DIALOG detected but could not click OK")
            log_action('rebuy', success=False, details={'table': session.window.name})
            return False

    def _check_showdown(self, session, state):
        """Detect showdown and log opponent cards for range estimate verification.

        Called when hand appears to be over (no buttons, not our turn).
        Looks for opponent cards displayed face-up on the table.
        """
        import time as _time

        # Cooldown
        last_check = getattr(session, '_last_showdown_check', 0)
        if _time.time() - last_check < 5.0:
            return
        session._last_showdown_check = _time.time()

        # Only check if we had cards this hand (we were in the hand)
        if not getattr(session, '_cached_cards', None):
            return

        try:
            screenshot = self.get_table_screenshot(session.window)
            img = np.array(screenshot)
            h, w = img.shape[:2]

            # Opponent cards appear in the top 60% of the table
            # (our cards are in the bottom 30%)
            opp_region = img[:int(h * 0.60), int(w * 0.20):int(w * 0.80)]

            # Try to detect cards using Python OCR card reader
            opp_cards = []
            if PYTHON_OCR_AVAILABLE:
                try:
                    from gamble.ocr.card_reader import CardReader
                    reader = CardReader()
                    from PIL import Image
                    opp_img = Image.fromarray(opp_region)
                    detected = reader.read_cards(opp_img)
                    # Filter out our own cards and board cards
                    my_cards = set(session._cached_cards or [])
                    board = set(getattr(session, '_cached_board', []) or [])
                    known = my_cards | board
                    opp_cards = [c for c in detected if c not in known]
                except Exception as e:
                    log.debug(f"Showdown card detection failed: {e}")

            if len(opp_cards) >= 2:
                # We found opponent cards at showdown!
                opp_hand = opp_cards[:2]  # Take first two
                log.info(f"SHOWDOWN: Opponent cards detected: {opp_hand} "
                         f"(our cards: {session._cached_cards})")

                # Log showdown record
                try:
                    import json as _json
                    record = {
                        'ts': datetime.datetime.utcnow().isoformat(),
                        'type': 'showdown',
                        'our_cards': session._cached_cards,
                        'opp_cards': opp_hand,
                        'board': getattr(session, '_cached_board', []),
                    }

                    # Score our range prediction if we had one
                    last_opp_est = getattr(session, '_last_opp_estimate', {})
                    if last_opp_est:
                        record['predicted_range'] = last_opp_est.get('likely_hands', [])
                        record['predicted_bluff_pct'] = last_opp_est.get('bluff_probability', 0)
                        # Simple scoring: did their actual hand match our prediction?
                        actual_strength = self._classify_showdown_hand(opp_hand,
                            getattr(session, '_cached_board', []))
                        predicted = last_opp_est.get('likely_hands', [])
                        record['actual_category'] = actual_strength
                        record['prediction_correct'] = actual_strength in predicted

                    path = os.path.join('data', 'learning', 'hand_history.jsonl')
                    with open(path, 'a') as f:
                        f.write(_json.dumps(record) + '\n')
                except Exception:
                    pass

                # Feed showdown cards into opponent modeler for type refinement
                if self.opponent_modeler:
                    villain_id = self._get_villain_id(session, state)
                    last_street = getattr(session, '_last_street', 'unknown')
                    last_action = 'bet' if not getattr(session, '_cached_check_opp', False) else 'check'
                    self.opponent_modeler.record_showdown(
                        villain_id, won=False,
                        cards=opp_hand, action=last_action, street=last_street
                    )

                # ── Bayesian showdown validation (Phase 5) ──
                # Check if the actual hand was in our predicted range
                v_range = session._bayesian_villain_range
                if v_range and len(v_range.get('combos', [])) > 0:
                    try:
                        import eval7
                        # Convert opponent cards to eval7 strings for comparison
                        opp_e7_0 = str(eval7.Card(opp_hand[0]))
                        opp_e7_1 = str(eval7.Card(opp_hand[1]))
                        opp_set = {opp_e7_0, opp_e7_1}

                        combos = v_range['combos']  # list of (c0, c1, weight) tuples
                        # Find this combo's weight (match by set of card strings)
                        actual_weight = 0.0
                        for c0, c1, w in combos:
                            if {c0, c1} == opp_set:
                                actual_weight = w
                                break

                        total_weight = sum(w for _, _, w in combos)
                        in_range = actual_weight > 0.001

                        # Calculate rank: what percentile was this combo?
                        if total_weight > 0 and in_range:
                            rank_pct = actual_weight / total_weight
                        else:
                            rank_pct = 0.0

                        log.info(f"BAYESIAN SHOWDOWN: {opp_hand} "
                                 f"{'IN' if in_range else 'NOT IN'} predicted range "
                                 f"(weight={actual_weight:.3f}, rank={rank_pct:.1%})")

                        # Log calibration data for learning
                        import json as _json2
                        cal_record = {
                            'ts': datetime.datetime.utcnow().isoformat(),
                            'type': 'bayesian_showdown',
                            'opp_cards': opp_hand,
                            'board': getattr(session, '_cached_board', []),
                            'in_range': in_range,
                            'weight': actual_weight,
                            'total_weight': total_weight,
                            'num_combos': sum(1 for _, _, w in combos if w > 0.001),
                            'history': v_range.get('history', []),
                        }
                        cal_path = os.path.join('data', 'learning', 'range_calibration.jsonl')
                        with open(cal_path, 'a') as f:
                            f.write(_json2.dumps(cal_record, default=str) + '\n')
                    except Exception as e:
                        log.debug(f"Bayesian showdown validation failed: {e}")

        except Exception as e:
            log.debug(f"Showdown check error: {e}")

    def _classify_showdown_hand(self, cards, board):
        """Classify opponent's showdown hand into a category.

        Returns: 'premium_pair', 'overpair', 'top_pair', 'middle_pair',
                 'two_pair', 'flush_draw', 'bluff', etc.
        """
        if not cards or len(cards) < 2 or not board:
            return 'unknown'

        rank_order = '23456789TJQKA'
        try:
            card_ranks = [rank_order.index(c[0].upper()) for c in cards if len(c) >= 2]
            board_ranks = [rank_order.index(c[0].upper()) for c in board if len(c) >= 2]
        except (ValueError, IndexError):
            return 'unknown'

        if len(card_ranks) < 2:
            return 'unknown'

        # Pocket pair
        if card_ranks[0] == card_ranks[1]:
            pair_rank = card_ranks[0]
            if pair_rank >= 10:  # JJ+
                return 'premium_pair'
            if board_ranks and pair_rank > max(board_ranks):
                return 'overpair'
            return 'middle_pair'

        # Check for pairs with board
        board_set = set(board_ranks)
        if card_ranks[0] in board_set or card_ranks[1] in board_set:
            matched_rank = card_ranks[0] if card_ranks[0] in board_set else card_ranks[1]
            if board_ranks and matched_rank == max(board_ranks):
                return 'top_pair'
            return 'middle_pair'

        # High cards with no pair
        if max(card_ranks) >= 12:  # A or K high
            return 'big_ace'

        return 'bluff'

    def _compute_raise_amount(self, state, decision_label: str) -> float:
        """Compute the target raise amount in BB using geometric + texture-aware sizing.

        Returns the desired raise-to amount in BB, or 0 if no sizing needed.

        Preflop: Uses preflop_raise_size_bb() — GTO open/3bet/4bet sizing.
        Postflop: Uses compute_bet_size_bb() — geometric sizing to get
                  all-in by river, adjusted for board texture, SPR, and position.
        """
        from gamble.decisionmaker.range_equity import compute_bet_size_bb, preflop_raise_size_bb

        # BB display mode is ALWAYS ON — OCR values (pot, call, stack)
        # are already in BB units. Do NOT divide by big_blind (which is
        # the dollar value from the window title, e.g. $0.02).
        # state.big_blind comes from _parse_blinds() and is in DOLLARS,
        # but all on-screen values are in BB. Use bb_size=1.0.
        bb_size = 1.0
        pot = state.pot or 1.5
        call = state.call_amount or 0
        hero_stack = state.hero_stack if state.hero_stack and state.hero_stack > 0 else 100
        position = getattr(state, 'position', 'UNKNOWN')
        is_oop = position in ('BB', 'SB', 'UTG')
        is_preflop = not state.board_cards or len(state.board_cards) == 0

        # All-in: just return hero's stack
        if decision_label == 'Allin':
            return hero_stack

        # No sizing needed for non-bet actions
        if decision_label in ('Fold', 'Call', 'Check', 'Call Deception', 'Check Deception'):
            return 0

        if is_preflop:
            # Determine preflop action type from call amount
            if call <= 0:
                action = 'open'
            elif call <= 1.0:
                # If we are in BB and call=1.0, it's an open facing us (someone raised to 2BB)
                # If we are NOT in blinds and call=1.0, it's a limp
                is_facing_raise = not state.has_check_button and position == 'BB'
                action = '3bet' if is_facing_raise else 'open'
            elif call <= 5.0:
                action = '3bet'
            else:
                action = '4bet'

            pos = position if position in ('UTG', 'MP', 'CO', 'BTN', 'SB', 'BB') else 'CO'
            size = preflop_raise_size_bb(
                action=action,
                position=pos,
                num_limpers=0,
                prev_raise_bb=max(call, 2.0), # Assume at least 2BB open if facing raise
            )
            # 3-bet scaling: ensure we actually raise significantly over the call
            # Total raise size should be ~3-4x the PREVIOUS TOTAL RAISE
            if action == '3bet':
                # BB correction: if we already have 1 BB in, the open of 3 BB only shows call=2.
                # Standard 3bet vs 3BB is 9-12BB.
                already_in = 1.0 if pos == 'BB' else 0.5 if pos == 'SB' else 0.0
                total_open = call + already_in
                
                multiplier = 4.2 if is_oop else 3.5
                size = total_open * multiplier
                
                # Squeeze adjustment: add 1BB per limper/caller
                if state.other_active_players > 2:
                    size += (state.other_active_players - 2) * 2.0
                    log.info(f"SQUEEZE adjustment: size → {size:.1f} BB")

                if size < 7.0: # Absolute minimum 3bet
                   size = 7.0
            # SAFETY: preflop raise can never exceed hero stack
            if size > hero_stack:
                log.warning(f"PREFLOP SIZE CAP: {size:.1f} > stack {hero_stack:.1f}, capping")
                size = hero_stack
            # SAFETY: preflop open/3bet should never exceed ~30 BB
            if action == 'open' and size > 10:
                log.warning(f"PREFLOP SANITY: open raise {size:.1f} BB > 10 — capping at 4 BB")
                size = 4.0
            elif action == '3bet' and size > 30:
                log.warning(f"PREFLOP SANITY: 3bet {size:.1f} BB > 30 — capping at 15 BB")
                size = 15.0
            log.info(f"PREFLOP SIZING: {action} from {pos}, prev_raise={call:.1f} → {size:.1f} BB")
            return round(size, 1)
        else:
            # Postflop: geometric + texture-aware sizing
            n_board = len(state.board_cards) if state.board_cards else 0
            street = 'flop' if n_board == 3 else 'turn' if n_board == 4 else 'river'
            wetness = self._compute_board_wetness(state.board_cards)
            spr = hero_stack / max(pot, 0.5)
            is_ip = not is_oop

            # Map decision label to hand_strength and is_value for sizing
            if decision_label in ('Bet pot', 'BetPlus', 'Bet3', 'Raise'):
                hand_strength = 'very_strong'
                is_value = True
            elif decision_label in ('Bet Bluff',):
                hand_strength = 'medium'
                is_value = False  # bluff — same size as value for balance
            elif decision_label == 'Bet half pot':
                hand_strength = 'medium'
                is_value = True
            else:
                hand_strength = 'medium'
                is_value = True

            bet = compute_bet_size_bb(
                pot_bb=pot,
                stack_bb=hero_stack,
                street=street,
                board_wetness=wetness,
                spr=spr,
                is_ip=is_ip,
                hand_strength=hand_strength,
                is_value=is_value,
            )
            bet = max(round(bet, 1), 2.0)  # Minimum 2 BB
            # SAFETY: postflop bet can never exceed hero stack
            if bet > hero_stack:
                log.warning(f"POSTFLOP SIZE CAP: {bet:.1f} > stack {hero_stack:.1f}, capping")
                bet = hero_stack
            log.info(f"POSTFLOP SIZING: {street} wet={wetness:.2f} spr={spr:.1f} "
                     f"{hand_strength} {'value' if is_value else 'bluff'} → {bet:.1f} BB ({bet/max(pot,0.01):.0%} pot)")
            return bet

    def _compute_board_wetness(self, board_cards):
        """0.0=bone dry, 1.0=extremely wet. Uses flop cards only."""
        if not board_cards or len(board_cards) < 3:
            return 0.5
        rank_map = {r: i for i, r in enumerate('23456789TJQKA')}
        ranks, suits = [], []
        for card in board_cards[:3]:
            if len(card) >= 2:
                ranks.append(rank_map.get(card[0].upper(), 0))
                suits.append(card[1].upper())
        if len(ranks) < 3:
            return 0.5
        wetness = 0.0
        from collections import Counter
        top_suit = Counter(suits).most_common(1)[0][1]
        if top_suit >= 3: wetness += 0.4
        elif top_suit >= 2: wetness += 0.2
        sr = sorted(ranks)
        gaps = [sr[i+1] - sr[i] for i in range(len(sr)-1)]
        if all(g <= 2 for g in gaps): wetness += 0.2
        if all(g == 1 for g in gaps): wetness += 0.1
        if sum(ranks)/len(ranks) >= 10: wetness += 0.1
        if len(set(ranks)) < len(ranks): wetness -= 0.15
        return max(0.0, min(1.0, wetness))

    def _log_hand_locally(self, state, decision_label, equity, abs_equity,
                          decision_obj=None):
        """Append one JSON record per decision to local hand history."""
        import json
        pot = state.pot or 0
        call = state.call_amount or 0
        hero_stack = getattr(state, 'hero_stack', 0) or 0
        spr = hero_stack / pot if pot > 0 else 20.0

        record = {
            'ts': datetime.datetime.utcnow().isoformat(),
            'cards': state.my_cards,
            'board': state.board_cards,
            'street': state.game_stage,
            'pos': getattr(state, 'position', '?'),
            'pot': round(pot, 2),
            'call': round(call, 2),
            'equity': round(equity, 4),
            'abs_equity': round(abs_equity, 4),
            'pot_odds': round(call / (pot + call), 4) if (pot + call) > 0 else 0,
            'decision': decision_label,
            'hero_stack': round(hero_stack, 2),
            'spr': round(spr, 1),
            'is_hu': getattr(state, 'is_heads_up', None),
        }

        # Add decision context if available
        if decision_obj:
            record['outs'] = getattr(decision_obj, 'outs', 0)
            record['wetness'] = round(decision_obj._board_wetness(
                state.board_cards) if state.board_cards else 0.5, 2)
            # EV of this decision
            record['ev'] = round(getattr(decision_obj, 'decision_ev', 0), 3)
            # Blocker analysis
            blockers = getattr(decision_obj, 'blockers_info', {})
            if blockers:
                record['blocker_score'] = round(blockers.get('blocker_score', 0), 2)
                record['blocks'] = [k.replace('blocks_', '') for k, v in blockers.items()
                                    if k.startswith('blocks_') and v is True]
            # Opponent range estimate
            opp = getattr(decision_obj, 'opponent_range_estimate', {})
            if opp:
                record['opp_likely'] = opp.get('likely_hands', [])[:3]
                record['opp_bluff_pct'] = round(opp.get('bluff_probability', 0), 2)
                record['opp_range_narrow'] = round(opp.get('range_narrowness', 0), 2)
            # Opponent type from modeler
            opp_prof = getattr(decision_obj, '_opp_profile', None)
            if opp_prof and opp_prof.get('type', 'unknown') != 'unknown':
                record['opp_type'] = opp_prof['type']

        path = os.path.join('data', 'learning', 'hand_history.jsonl')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'a') as f:
            f.write(json.dumps(record) + '\n')

    def process_table(self, session: TableSession) -> bool:
        """
        Process ONE table using the ORIGINAL bot logic with self-healing.
        This is the complete inner loop from main.py with all 25+ checks.
        """
        log.info(f"Processing table: {session.window.name}")

        try:
            t = session._table
            h = session.history
            p = self.strategy

            # Take fresh screenshot
            screenshot = self.get_table_screenshot(session.window)
            t.entireScreenPIL = screenshot
            t.screenshot = screenshot
            t.tlc = (0, 0)

            # === ORIGINAL BOT DETECTION CHAIN ===
            # (From main.py lines 172-199)

            # Get cards with SELF-HEALING
            t.get_my_cards2()

            # === SELF-HEALING: If cards not detected, try vision analyzer ===
            if len(t.my_cards) != 2 and VISION_ANALYZER_AVAILABLE:
                log.info(f"SELF-HEALING: Card detection failed on {session.window.name}, running vision analyzer...")
                try:
                    fix_result = auto_fix_cards(np.array(screenshot))

                    if fix_result.get('fixed'):
                        # Update white pixel threshold
                        new_threshold = fix_result.get('threshold', 160)
                        set_threshold('white_pixel_min', new_threshold, 'auto_fix_cards')
                        log.info(f"SELF-HEALING: Updated white_pixel_min to {new_threshold}")

                        # RETRY detection
                        t.get_my_cards2()

                        if len(t.my_cards) == 2:
                            log.info(f"SELF-HEALING: SUCCESS! Cards found: {t.my_cards}")
                            log_action('card_detection', success=True, details={
                                'method': 'self_healed',
                                'cards': t.my_cards,
                                'table': session.window.name
                            })
                        else:
                            log.warning(f"SELF-HEALING: Still no cards after fix")
                            log_action('card_detection', success=False, details={
                                'reason': 'self_heal_failed',
                                'table': session.window.name
                            })
                            # Report to CLAUDE_FEEDBACK.md for human review
                            report_issue(
                                'card_detection',
                                f'Card detection failed on {session.window.name} even after self-healing. '
                                f'Tried threshold {new_threshold} but still no cards found.',
                                severity='high'
                            )
                            # Save screenshot for analysis
                            save_debug_screenshot('card_detection', screenshot, reason='self_heal_failed')
                    elif fix_result.get('reason') == 'cards_face_down':
                        log.info(f"Cards are face-down (not your turn yet)")
                        return False
                except Exception as e:
                    log.error(f"SELF-HEALING error: {e}")

            # Final check - if still no cards, fold safely
            if len(t.my_cards) != 2:
                log.warning("Cards not detected after self-healing, folding for safety")
                log_action('card_detection', success=False, details={
                    'reason': 'no_cards',
                    'table': session.window.name
                })
                if t.has_call_button() or t.has_check_button():
                    self._click_fold(session)
                return False

            # Log successful card detection
            log_action('card_detection', success=True, details={
                'cards': t.my_cards,
                'table': session.window.name
            })

            # === AUTO-COLLECT CARD TEMPLATES ===
            # When Python OCR successfully detects cards, capture the real
            # card corners to replace synthetic templates for the Rust engine.
            if TEMPLATE_COLLECTOR_AVAILABLE and len(t.my_cards) == 2:
                try:
                    collector = get_template_collector()
                    if collector and not collector.is_complete():
                        table_dict = getattr(t, 'table_dict', None)
                        if table_dict and screenshot:
                            regions = []
                            for area_key in ['left_card_area', 'right_card_area']:
                                area = table_dict.get(area_key)
                                if area:
                                    regions.append((
                                        int(area.get('x1', 0)), int(area.get('y1', 0)),
                                        int(area.get('x2', 0)) - int(area.get('x1', 0)),
                                        int(area.get('y2', 0)) - int(area.get('y1', 0)),
                                    ))
                            if len(regions) == 2:
                                n = collector.collect_from_screenshot(
                                    screenshot, t.my_cards, regions
                                )
                                if n > 0:
                                    log.info(f"TEMPLATE COLLECTOR: Captured {n} real card templates. {collector.status()}")
                except Exception as e:
                    log.debug(f"Template collection error (non-fatal): {e}")

            # Get table cards (community cards)
            t.get_table_cards2()

            # Determine game stage from table cards
            table_cards = getattr(t, 'cardsOnTable', None) or getattr(t, 'table_cards', None) or []

            # FALLBACK: If template matching found 0 cards, try OCR detection
            if len(table_cards) == 0:
                try:
                    from gamble.ocr.table_reader import _detect_board_cards
                    img = np.array(screenshot)
                    if img.ndim == 3 and img.shape[2] == 4:
                        img = img[:, :, :3]
                    H_img, W_img = img.shape[:2]
                    ocr_board = _detect_board_cards(img, W_img, H_img)
                    if ocr_board:
                        table_cards = ocr_board
                        t.cardsOnTable = ocr_board
                        t.table_cards = ocr_board
                        log.info(f"OCR fallback detected board cards: {ocr_board}")
                except Exception as e:
                    log.debug(f"OCR board fallback failed: {e}")

            num_table_cards = len(table_cards)
            if num_table_cards == 0:
                t.gameStage = 'PreFlop'
            elif num_table_cards == 3:
                t.gameStage = 'Flop'
            elif num_table_cards == 4:
                t.gameStage = 'Turn'
            else:
                t.gameStage = 'River'

            # Get dealer position
            t.get_dealer_position2()

            # === ADDITIONAL CHECKS FROM ORIGINAL (main.py) ===
            # Get round number for history tracking
            try:
                t.get_round_number(h)
            except:
                pass

            # Initialize other players info
            try:
                t.init_get_other_players_info()
                t.get_other_player_status(self.strategy, h)
                t.get_other_player_funds(self.strategy)
            except Exception as e:
                log.debug(f"Player info gathering partial: {e}")

            # Get pots (with fallback to OCR)
            t.get_pots()
            try:
                t.get_total_pot_value(h)
                t.get_round_pot_value(h)
            except:
                pass

            # Get player info
            t.get_players_in_game()
            t.get_players_funds()
            t.get_player_pots()

            # Get call/raise values
            t.get_call_value()
            t.get_raise_value()

            # Check button states
            try:
                t.check_for_call()
                t.check_for_betbutton()
                t.check_for_allincall()
            except:
                pass

            # === ENSURE ALL REQUIRED ATTRIBUTES ARE SET ===
            # Set fallback values for any missing attributes to prevent errors
            if not hasattr(t, 'round_pot_value') or t.round_pot_value is None:
                t.round_pot_value = getattr(t, 'current_round_pot', 0) or 0
            if not hasattr(t, 'totalPotValue') or t.totalPotValue is None:
                t.totalPotValue = getattr(t, 'total_pot', 0) or 0
            if not hasattr(t, 'bigBlind') or t.bigBlind is None:
                t.bigBlind = 2  # Default big blind for spin & gold
            if not hasattr(t, 'currentCallValue'):
                t.currentCallValue = getattr(t, 'call_value', 0) or 0
            if not hasattr(t, 'currentBetValue'):
                t.currentBetValue = getattr(t, 'raise_value', 0) or t.bigBlind * 2
            if not hasattr(t, 'checkButton'):
                t.checkButton = getattr(t, 'check_button', False)
            if not hasattr(t, 'callButton'):
                t.callButton = getattr(t, 'call_button', False)
            if not hasattr(t, 'raiseButton'):
                t.raiseButton = getattr(t, 'raise_button', False)
            if not hasattr(t, 'allInCallButton'):
                t.allInCallButton = False
            # Position attributes
            if not hasattr(t, 'position_utg_plus'):
                t.position_utg_plus = 0
            if not hasattr(t, 'total_players'):
                t.total_players = 6  # Rush & Cash is 6-max
            if not hasattr(t, 'dealer_position'):
                t.dealer_position = 0
            if not hasattr(t, 'first_raiser'):
                t.first_raiser = 0
            if not hasattr(t, 'second_raiser'):
                t.second_raiser = 0
            if not hasattr(t, 'first_caller'):
                t.first_caller = 0
            if not hasattr(t, 'first_raiser_utg'):
                t.first_raiser_utg = np.nan  # nan = no raiser detected
            if not hasattr(t, 'first_caller_utg'):
                t.first_caller_utg = np.nan  # nan = no caller detected
            if not hasattr(t, 'second_raiser_utg'):
                t.second_raiser_utg = np.nan
            # Decision-making attributes
            if not hasattr(t, 'max_X'):
                t.max_X = 0.95 if t.gameStage == 'PreFlop' else 1.0
            if not hasattr(t, 'power1'):
                t.power1 = 2
            if not hasattr(t, 'power2'):
                t.power2 = 2
            if not hasattr(t, 'maxEquityCall'):
                t.maxEquityCall = 1.0
            if not hasattr(t, 'minEquityBet'):
                t.minEquityBet = 0.0
            if not hasattr(t, 'maxEquityBet'):
                t.maxEquityBet = 1.0
            if not hasattr(t, 'potStretch'):
                t.potStretch = 1.0
            if not hasattr(t, 'minBetAmountIfAboveLimit'):
                t.minBetAmountIfAboveLimit = 0
            if not hasattr(t, 'other_player_has_initiative'):
                t.other_player_has_initiative = False  # No opponent initiative by default
            if not hasattr(t, 'smallBlind'):
                t.smallBlind = t.bigBlind / 2 if hasattr(t, 'bigBlind') and t.bigBlind else 1
            # HeadsUp and player info attributes
            if not hasattr(t, 'isHeadsUp'):
                t.isHeadsUp = (t.total_players == 2) if hasattr(t, 'total_players') else False
            if not hasattr(t, 'PlayerNames'):
                t.PlayerNames = ['Player0', 'Player1', 'Player2', 'Player3', 'Player4', 'Player5']
            if not hasattr(t, 'other_players'):
                t.other_players = []
            if not hasattr(t, 'abs_equity'):
                t.abs_equity = getattr(t, 'equity', 0.5)
            if not hasattr(t, 'relative_equity'):
                t.relative_equity = getattr(t, 'equity', 0.5)
            if not hasattr(t, 'minCallAmountIfAboveLimit'):
                t.minCallAmountIfAboveLimit = t.bigBlind * 2 if hasattr(t, 'bigBlind') else 4
            if not hasattr(t, 'opponentBetIncreases'):
                t.opponentBetIncreases = 0
            if not hasattr(t, 'assumedPlayers'):
                t.assumedPlayers = 2
            if not hasattr(t, 'myFunds'):
                # Try to get from player_funds[0], or default to initial funds
                t.myFunds = t.player_funds[0] if hasattr(t, 'player_funds') and len(t.player_funds) > 0 and t.player_funds[0] > 0 else float(p.selected_strategy.get('initialFunds', 500))
            if not hasattr(t, 'minBet'):
                t.minBet = getattr(t, 'currentBetValue', 0) or t.bigBlind * 2 if hasattr(t, 'bigBlind') else 4
            if not hasattr(t, 'minCall'):
                t.minCall = getattr(t, 'currentCallValue', 0) or 0

            # === MONTE CARLO EQUITY CALCULATION ===
            # Set mycards alias (montecarlo uses mycards, we use my_cards)
            t.mycards = t.my_cards
            t.cardsOnTable = getattr(t, 'cardsOnTable', []) or []
            t.mt_tm = time.time()  # Set monte carlo timer start
            config = get_config()
            # Use module-level MockSignalsMC for montecarlo (it expects signal_status.emit())
            mock_signals = MockSignalsMC()
            m = run_montecarlo_wrapper(
                p, mock_signals, config, None, t,
                session.game_logger, session.preflop_state, h
            )

            # === DECISION MAKING (Original) ===
            d = Decision(t, h, p, session.game_logger)

            # Multi-street planning: pass previous street info to decision
            d._we_bet_prev_street = getattr(session, '_we_bet_last_street', False)
            d._prev_street_equity = getattr(session, '_last_equity', None)

            # Pass Bayesian villain range from runner → DecisionMaker
            if session._bayesian_villain_range is not None:
                d._bayesian_villain_range = session._bayesian_villain_range

            d.make_decision(t, h, p, session.game_logger)

            # Track our action for multi-street planning
            dec_str = str(d.decision).lower() if d.decision else ''
            session._we_bet_last_street = ('bet' in dec_str or 'raise' in dec_str)
            session._last_equity = t.equity

            # === PER-HAND SAFETY OVERRIDE (Phase 5.3) ===
            _ph_call = getattr(t, 'minCall', 0) or 0
            _ph_funds = max(getattr(t, 'myFunds', 1.0), 1.0)
            _ph_call_to_stack = _ph_call / _ph_funds
            _ph_equity = getattr(t, 'equity', 0.5)
            if _ph_call_to_stack > 0.50 and _ph_equity < 0.55:
                log.warning(f"PER-HAND OVERRIDE: call={_ph_call} ({_ph_call_to_stack:.0%} stack), "
                           f"equity={_ph_equity:.3f} < 0.55 → FOLD")
                d.decision = 'Fold'
            elif _ph_call_to_stack > 0.25 and _ph_equity < 0.40:
                log.warning(f"PER-HAND OVERRIDE: call={_ph_call} ({_ph_call_to_stack:.0%} stack), "
                           f"equity={_ph_equity:.3f} < 0.40 → FOLD")
                d.decision = 'Fold'

            # === ENHANCED DECISION LOGGING (Phase 6.1) ===
            # Retrieve OCR safety info from GameState if available
            _gs = getattr(session, '_last_game_state', None)
            _raw_call = getattr(_gs, '_raw_ocr_call', _ph_call) if _gs else _ph_call
            _was_capped = getattr(_gs, '_was_safety_capped', False) if _gs else False
            _stack_est = getattr(_gs, 'hero_stack_is_estimated', False) if _gs else False

            log.info(f"{'='*50}")
            log.info(f"Table: {session.window.name}")
            log.info(f"Cards: {t.my_cards} | Board: {t.cardsOnTable}")
            log.info(f"Equity: {t.equity * 100:.1f}% -> {int(getattr(t, 'assumedPlayers', 0))} players")
            log.info(f"Pot: {getattr(t, 'totalPotValue', 0)} | Call: {t.minCall} | Raise: {t.minBet}")
            log.info(f"call_to_stack={_ph_call_to_stack:.0%} | raw_ocr_call={_raw_call} | "
                     f"validated_call={_ph_call} | was_safety_capped={_was_capped} | "
                     f"hero_stack_estimated={_stack_est}")
            log.info(f"Final Call Limit: {getattr(d, 'finalCallLimit', 'N/A')} | Final Bet Limit: {getattr(d, 'finalBetLimit', 'N/A')}")
            log.info(f"Rebuys: {self._session_rebuys}/{self._max_session_rebuys} | "
                     f"Stop-loss: {self._buyins_lost}/{self._max_buyins_loss} buy-ins")
            log.info(f"{'+'*20} Decision: {d.decision} {'+'*20}")

            # === UPDATE STATS ===
            self.stats['hands_played'] += 1
            decision_key = str(d.decision).lower().replace('bet', 'raise')  # Normalize bet/raise
            if decision_key in self.stats['decisions']:
                self.stats['decisions'][decision_key] += 1

            # === EXECUTE ACTION WITH OPTIONS ===
            mouse_target = d.decision
            action_options = {}

            # Handle all-in call button (from main.py)
            if mouse_target == 'Call' and getattr(t, 'allInCallButton', False):
                mouse_target = 'Call2'
                log.info("Using Call2 for all-in call button")

            # Handle BetPlus increment
            elif mouse_target == 'BetPlus':
                try:
                    action_options['increases_num'] = self.strategy.selected_strategy['BetPlusInc']
                except:
                    pass

            self._execute_action(session, mouse_target, t, action_options)

            # Record action time
            t.time_action_completed = datetime.datetime.utcnow()

            # === SAVE SCREENSHOT (from main.py) ===
            try:
                filename = f"{h.GameID}_{t.gameStage}_{getattr(h, 'round_number', 0)}.png"
                screenshot.save(self.screenshot_dir / filename)
                log.debug(f"Saved screenshot: {filename}")
            except Exception as e:
                log.debug(f"Screenshot save failed: {e}")

            # === DATABASE LOGGING (from main.py - runs in background) ===
            try:
                t_log_db = threading.Thread(
                    name='t_log_db',
                    target=session.game_logger.write_log_file,
                    args=[self.strategy, h, t, d]
                )
                t_log_db.daemon = True
                t_log_db.start()
            except Exception as e:
                log.debug(f"DB logging failed: {e}")

            # === FULL HISTORY UPDATE (from main.py lines 257-272) ===
            h.previousPot = getattr(t, 'totalPotValue', 0)
            h.histGameStage = t.gameStage
            h.histDecision = d.decision
            h.histEquity = t.equity
            h.histMinCall = t.minCall
            h.histMinBet = t.minBet

            # Additional history fields (were missing!)
            h.hist_other_players = getattr(t, 'other_players', [])
            h.first_raiser = getattr(t, 'first_raiser', None)
            h.first_caller = getattr(t, 'first_caller', None)
            h.previous_decision = d.decision
            h.lastRoundGameID = h.GameID
            h.previous_round_pot_value = getattr(t, 'round_pot_value', 0)
            h.last_round_bluff = False if getattr(t, 'currentBluff', 0) == 0 else True

            # === PREFLOP LEARNING (CRITICAL - was missing!) ===
            if t.gameStage == 'PreFlop':
                try:
                    session.preflop_state.update_values(t, d.decision, h, d)
                    log.debug("Updated preflop state for learning")
                except Exception as e:
                    log.debug(f"Preflop state update failed: {e}")

            # === STATS TRACKING ===
            try:
                self.mongo.increment_plays(self.table_scraper_name)
            except:
                pass

            # Log decision to adaptive learner
            log_action('decision_made', success=True, details={
                'table': session.window.name,
                'decision': d.decision,
                'equity': t.equity,
                'cards': t.my_cards,
                'pot': getattr(t, 'totalPotValue', 0),
                'game_stage': t.gameStage
            })

            session.last_action_time = datetime.datetime.utcnow()
            log.info(f"{'='*50} Round End {'='*50}")

            return True

        except Exception as e:
            log.error(f"Error processing table {session.window.name}: {e}")
            log.error(traceback.format_exc())

            # Log the error for learning
            log_action('process_table_error', success=False, details={
                'error': str(e),
                'table': session.window.name
            })

            # DON'T CRASH - return False and continue
            return False

    def _execute_action(self, session: TableSession, action: str, table, action_options: dict = None):
        """
        Execute the decided action by clicking the button.
        SELF-LEARNING: Retries up to 3 times if click verification fails.
        """
        if action_options is None:
            action_options = {}

        # Create mouse mover if needed
        if session._mouse is None:
            session._mouse = MouseMoverTableBased(session.table_dict)

        mouse = session._mouse

        # Convert table-relative coords to screen coords
        # TLC is window position in POINTS
        tlc = (session.window.x, session.window.y)

        log.info(f"Executing action: {action} on {session.window.name}")

        # NOTE: Do NOT use AXRaise/frontmost here — it steals focus from the
        # user's other windows and causes the GGPoker window to flash/minimize
        # other apps.  pyautogui.click() sends the click to the correct screen
        # coordinates regardless of which window is in front.

        # Get click verify delay from learned thresholds
        click_delay = get_threshold('click_verify_delay', 0.3) if ADAPTIVE_LEARNER_AVAILABLE else 0.3
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # Take screenshot BEFORE click for verification
                screenshot_before = None
                try:
                    from PIL import ImageGrab
                    screenshot_before = ImageGrab.grab()
                except Exception:
                    pass

                # Execute the click
                mouse.mouse_action(action, tlc, action_options)

                # Wait for UI to update
                time.sleep(click_delay)

                # Verify click worked by checking if buttons changed
                click_verified = True
                if screenshot_before:
                    try:
                        screenshot_after = ImageGrab.grab()

                        # Crop to button area and compare
                        # Simple check: if screenshots are very similar, click may have failed
                        before_arr = np.array(screenshot_before)
                        after_arr = np.array(screenshot_after)

                        # Check bottom portion of screen where buttons are
                        h = before_arr.shape[0]
                        before_bottom = before_arr[int(h*0.7):, :]
                        after_bottom = after_arr[int(h*0.7):, :]

                        # Calculate difference
                        diff = np.abs(before_bottom.astype(float) - after_bottom.astype(float)).mean()

                        # If very little changed, click might have failed
                        if diff < 5:  # Threshold for "no change"
                            click_verified = False
                            log.warning(f"Click verification: Low change detected (diff={diff:.2f}), may have failed")
                        else:
                            log.debug(f"Click verification: Change detected (diff={diff:.2f}), click succeeded")

                    except Exception as e:
                        log.debug(f"Click verification error: {e}")

                if click_verified or attempt == max_retries - 1:
                    # Log successful click
                    log_action('button_click', success=click_verified, details={
                        'button': action,
                        'table': session.window.name,
                        'options': action_options,
                        'attempt': attempt + 1,
                        'verified': click_verified
                    })
                    if click_verified:
                        return  # Success!
                    else:
                        log.warning(f"Click not verified after {max_retries} attempts")
                        return

                # Retry
                log.info(f"SELF-LEARNING: Click not verified, retrying ({attempt + 2}/{max_retries})...")
                time.sleep(0.2)  # Brief pause before retry

            except Exception as e:
                log.error(f"Click failed (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    log_action('button_click', success=False, details={
                        'button': action,
                        'table': session.window.name,
                        'error': str(e),
                        'attempt': attempt + 1
                    })

    def save_stats(self):
        """Save session stats to JSON file for review"""
        try:
            import json
            self.stats['session_end'] = datetime.datetime.utcnow().isoformat()
            self.stats['uptime_seconds'] = (datetime.datetime.utcnow() -
                datetime.datetime.fromisoformat(self.stats['session_start'])).total_seconds()

            # Calculate rates
            uptime_min = self.stats['uptime_seconds'] / 60
            if uptime_min > 0:
                self.stats['hands_per_minute'] = self.stats['hands_played'] / uptime_min
                self.stats['actions_per_minute'] = self.actions_count / uptime_min if hasattr(self, 'actions_count') else 0

            # Detection success rates
            btn_total = self.stats['detection_success']['buttons'] + self.stats['detection_success']['buttons_fail']
            card_total = self.stats['detection_success']['cards'] + self.stats['detection_success']['cards_fail']
            self.stats['detection_rates'] = {
                'button_success_rate': self.stats['detection_success']['buttons'] / btn_total if btn_total > 0 else 0,
                'card_success_rate': self.stats['detection_success']['cards'] / card_total if card_total > 0 else 0,
            }

            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=2)
            log.debug(f"Stats saved to {self.stats_file}")
        except Exception as e:
            log.debug(f"Failed to save stats: {e}")

    def update_stats(self, category: str, key: str, increment: int = 1):
        """Update a specific stat counter"""
        try:
            if category in self.stats and key in self.stats[category]:
                self.stats[category][key] += increment
        except Exception:
            pass

    def _click_fold(self, session: TableSession):
        """Emergency fold when detection fails"""
        try:
            if session._mouse is None:
                session._mouse = MouseMoverTableBased(session.table_dict)
            tlc = (session.window.x, session.window.y)
            session._mouse.mouse_action("Fold", tlc)
            log.info(f"Emergency fold on {session.window.name}")
            self.update_stats('decisions', 'fold')
        except Exception as e:
            log.error(f"Failed to fold: {e}")

    def open_new_table(self):
        """Open a new table via lobby navigation."""
        if not self.lobby_nav:
            log.warning("Lobby navigation not available")
            return False

        try:
            # Determine game type from existing tables
            is_rush_cash = any(
                'Rush' in sess.window.name or 'Cash' in sess.window.name
                for sess in self.sessions.values()
            )

            if is_rush_cash or not self.sessions:
                # Open Rush & Cash table (default)
                log.info("Opening new Rush & Cash table...")
                return self.lobby_nav.open_rush_and_cash(stake='0.01/0.02')
            else:
                # Open Spin & Gold table
                log.info("Opening new Spin & Gold table...")
                self.lobby_nav.register_for_spin_gold(stake_index=0)
                return True
        except Exception as e:
            log.error(f"Failed to open new table: {e}")
            return False

    def _start_hotkey_listener(self):
        """Start background thread listening for Ctrl+Shift+Q to stop the bot."""
        try:
            from pynput import keyboard

            def on_activate():
                log.info("HOTKEY Ctrl+Shift+Q pressed — shutting down")
                self.running = False

            pressed_keys = set()

            def on_press(key):
                pressed_keys.add(key)
                # Ctrl + < to stop (need both held)
                ctrl_held = (keyboard.Key.ctrl_l in pressed_keys or
                             keyboard.Key.ctrl_r in pressed_keys)
                if ctrl_held and hasattr(key, 'char') and key.char in ('<', '§'):
                    log.info("Ctrl+< pressed — shutting down")
                    self.running = False
                    return False

            def on_release(key):
                pressed_keys.discard(key)

            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()
            log.info("Hotkey listener started: Ctrl+< to stop")
        except Exception as e:
            log.warning(f"Hotkey listener failed (use stop file instead): {e}")

    def run(self, standardize_on_startup: bool = True):
        """
        Main multi-table loop - NEVER STOPS unless explicitly told to.

        1. Find all poker windows
        2. Standardize/tile windows
        3. Update/create sessions
        4. Check which tables need action
        5. Process most urgent table (with self-healing)
        6. Open new tables if needed
        7. Repeat forever
        """
        self.running = True
        self.start_time = datetime.datetime.utcnow()
        self.actions_count = 0
        self.errors_count = 0

        # Remove stale stop file from previous runs
        stop_file = '/tmp/poker_bot_stop'
        if os.path.exists(stop_file):
            os.remove(stop_file)

        # Global hotkey: Ctrl+Shift+Q to stop the bot
        self._start_hotkey_listener()

        log.info("=" * 60)
        if self.dry_run:
            log.info("DRY-RUN MODE — WATCHING ONLY, NO CLICKS")
        else:
            log.info("UNIFIED AUTONOMOUS MULTI-TABLE BOT STARTING")
        log.info("=" * 60)
        log.info(">>> Press Ctrl+< to stop, or: touch /tmp/poker_bot_stop")
        log.info(f"Target: {self.target_tables} tables | Max: {self.max_tables} tables")
        log.info(f"Dry-run: {self.dry_run} | Self-learning: {ADAPTIVE_LEARNER_AVAILABLE} | Vision: {VISION_ANALYZER_AVAILABLE}")
        log.info(f"Python OCR: {PYTHON_OCR_AVAILABLE} | Rust OCR: {self.rust_ocr is not None}")
        log.info(f"Preflop sheets: {self.preflop_sheet is not None}")

        # Build pre-computed preflop equity tables (~7s, enables instant preflop lookups)
        try:
            from gamble.decisionmaker.range_equity import build_preflop_equity_table, build_push_fold_table
            import time as _t
            _start = _t.time()
            build_preflop_equity_table()
            build_push_fold_table()
            log.info(f"Preflop equity + push/fold tables built in {_t.time() - _start:.1f}s")
        except Exception as e:
            log.warning(f"Preflop equity table failed (will use live calc): {e}")

        # Standardize all tables on startup (resize and tile)
        if standardize_on_startup:
            try:
                count = self.standardize_tables()
                log.info(f"Standardized {count} tables to {self.standard_width}x{self.standard_height}")
            except Exception as e:
                log.warning(f"Table standardization failed (continuing anyway): {e}")

        while self.running:
            try:
                # 0. Check stop file
                if os.path.exists('/tmp/poker_bot_stop'):
                    log.info("STOP FILE detected (/tmp/poker_bot_stop) — shutting down")
                    os.remove('/tmp/poker_bot_stop')
                    self.running = False
                    break

                # 1. Find all poker windows
                try:
                    windows = self.find_poker_windows()
                    current_window_ids = {w.window_id for w in windows}
                except Exception as e:
                    log.error(f"Window detection failed: {e}")
                    time.sleep(2)
                    continue  # Don't crash, retry

                log.debug(f"Found {len(windows)} poker tables")

                # 2. Update sessions - remove closed, add new
                try:
                    closed_ids = set(self.sessions.keys()) - current_window_ids
                    for wid in closed_ids:
                        log.info(f"Table closed: {self.sessions[wid].window.name}")
                        del self.sessions[wid]

                    new_windows_found = False
                    for window in windows:
                        if window.window_id not in self.sessions:
                            new_windows_found = True
                            self.sessions[window.window_id] = self.create_session(window)
                        else:
                            # Update window position (may have moved)
                            self.sessions[window.window_id].window = window

                    # Re-tile all tables when new ones appear or every 60s (Lockdown)
                    now = time.time()
                    if new_windows_found or (now - self._last_tile_time) > 60.0:
                        try:
                            self.tile_all_tables()
                            self._last_tile_time = now
                            if not new_windows_found:
                                log.info("GRID LOCKDOWN: re-aligned windows to grid")
                        except Exception:
                            pass
                except Exception as e:
                    log.error(f"Session update failed: {e}")

                # 2b. ONE screenshot for ALL tables — then parallel OCR
                # Grab screen once (~80ms) instead of once per table.
                full_screen = self.grab_full_screen()

                # Fast Deal Me In scan (uses shared screenshot)
                waiting_tables = [s for s in self.sessions.values()
                                  if s.state in (TableState.WAITING, TableState.UNKNOWN)]
                if waiting_tables:
                    try:
                        self._fast_deal_me_in_scan(waiting_tables, full_screen=full_screen)
                    except Exception as e:
                        log.debug(f"Fast Deal Me In scan error: {e}")

                # 3. Parallel OCR: check all tables simultaneously using threads
                sessions_to_check = list(self.sessions.values())
                if len(sessions_to_check) <= 1:
                    # Single table — no threading overhead needed
                    for session in sessions_to_check:
                        try:
                            self._check_table_state_with_screen(session, full_screen)
                        except Exception as e:
                            log.error(f"State check failed for {session.window.name}: {e}")
                else:
                    # Multiple tables — parallel OCR via ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=len(sessions_to_check)) as executor:
                        futures = {
                            executor.submit(
                                self._check_table_state_with_screen, session, full_screen
                            ): session
                            for session in sessions_to_check
                        }
                        for future in as_completed(futures):
                            session = futures[future]
                            try:
                                future.result()
                            except Exception as e:
                                log.error(f"State check failed for {session.window.name}: {e}")

                # 4. Process ALL urgent tables (not just one)
                urgent_tables = [s for s in self.sessions.values()
                                if s.state == TableState.NEED_ACTION]

                if urgent_tables:
                    # Sort by priority (highest first)
                    urgent_tables.sort(key=lambda s: s.priority, reverse=True)

                    for urgent_table in urgent_tables:
                        try:
                            # Use new OCR pipeline if available, else old path
                            if PYTHON_OCR_AVAILABLE or self.rust_ocr is not None:
                                success = self.process_table_new_ocr(urgent_table)
                            else:
                                success = self.process_table(urgent_table)
                            if success:
                                self.actions_count += 1
                        except Exception as e:
                            log.error(f"Process failed for {urgent_table.window.name}: {e}")
                            self.errors_count += 1
                            # DON'T CRASH - try next table

                # 5. Auto-open new tables DISABLED — play only what's already open.
                #    The lobby navigator steals focus and disrupts the user.
                #    The bot adapts to however many tables the user has open.
                pass

                # 6. Periodic stats logging (every 60 seconds)
                uptime = (datetime.datetime.utcnow() - self.start_time).total_seconds()
                if int(uptime) % 60 == 0:  # Every minute
                    actions_per_min = self.actions_count / (uptime / 60) if uptime > 0 else 0
                    log.info(f"STATS: Uptime={uptime/60:.1f}min | Actions={self.actions_count} | "
                            f"APM={actions_per_min:.1f} | Errors={self.errors_count} | Tables={len(self.sessions)}")
                    log.info(f"STATS: Hands={self.stats['hands_played']} | "
                            f"Decisions={self.stats['decisions']}")
                    # Spot tracker summary
                    spot_sum = self.spot_tracker.summary()
                    if spot_sum != 'no data yet':
                        log.info(f"SPOT P&L: {spot_sum}")
                        adj = self.spot_tracker.compute_adjustments()
                        if adj:
                            log.info(f"SPOT ADJ: {adj}")
                    # Save stats to file
                    self.save_stats()

                # Small delay — fast enough to never miss a hand
                # (GGPoker gives 15-30s per decision, we poll every ~100ms)
                time.sleep(0.05)

            except KeyboardInterrupt:
                log.info("Keyboard interrupt, stopping gracefully...")
                self.running = False
            except Exception as e:
                log.error(f"MAIN LOOP ERROR (continuing anyway): {e}")
                log.error(traceback.format_exc())
                self.errors_count += 1

                # Log error for learning
                log_action('main_loop_error', success=False, details={'error': str(e)})

                time.sleep(1)  # Brief pause before retry
                # NEVER STOP - just continue

        # Cleanup on shutdown
        log.info("=" * 60)
        log.info("SHUTTING DOWN")
        log.info(f"Final stats: Actions={self.actions_count} | Errors={self.errors_count}")
        log.info("=" * 60)

        # Save opponent profiles
        if self.opponent_modeler:
            try:
                self.opponent_modeler.save_profiles()
                active = self.opponent_modeler.active_profiles_summary()
                if active:
                    log.info(f"Opponent profiles saved ({len(active)} classified):")
                    for pid, prof in active.items():
                        log.info(f"  {pid}: {prof['type']} VPIP={prof['vpip']:.0%} "
                                 f"PFR={prof['pfr']:.0%} AF={prof['af']:.1f} "
                                 f"({prof['hands']} hands)")
            except Exception:
                pass

        # End learning session
        if self.learner:
            try:
                self.learner.end_session()
            except:
                pass

    def stop(self):
        """Stop the runner"""
        self.running = False


def _run_replay(path: str):
    """Replay a screenshot (or directory of screenshots) through the full pipeline.

    Runs: screenshot → Python OCR → GameState → to_table_scraper_compat → Monte Carlo →
    DecisionMaker → logs decision.  No clicking, no live table needed.

    Usage:
        python -m gamble.multi_table_runner --replay data/learning/screenshots/some_hand.png
        python -m gamble.multi_table_runner --replay data/learning/screenshots/  # all PNGs in dir
    """
    from PIL import Image

    if not PYTHON_OCR_AVAILABLE:
        log.error("Python OCR not available — can't replay screenshots")
        return

    # Collect files
    files = []
    if os.path.isdir(path):
        for f in sorted(os.listdir(path)):
            if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                files.append(os.path.join(path, f))
    elif os.path.isfile(path):
        files = [path]
    else:
        log.error(f"Path not found: {path}")
        return

    if not files:
        log.error(f"No image files found in {path}")
        return

    log.info(f"REPLAY MODE: processing {len(files)} screenshot(s)")
    log.info("=" * 60)

    # Set up strategy (same as live bot)
    strategy = StrategyHandler()
    strategy.read_strategy()
    s = strategy.selected_strategy
    s['bigBlind'] = 1.0
    s['smallBlind'] = 0.5
    s['initialFunds'] = 100.0
    s['initialFunds2'] = 100.0
    s['PreFlopMinCallEquity'] = 0.17
    s['PreFlopMinBetEquity'] = 0.22
    s['PreFlopMaxBetEquity'] = 1.0
    s['PreFlopCallPower'] = 2
    s['PreFlopBetPower'] = 2
    s['FlopMinCallEquity'] = 0.30
    s['FlopMinBetEquity'] = 0.40
    s['FlopMaxBetEquity'] = 1.0
    s['FlopCallPower'] = 2
    s['FlopBetPower'] = 2
    s['TurnMinCallEquity'] = 0.30
    s['TurnMinBetEquity'] = 0.42
    s['TurnMaxBetEquity'] = 1.0
    s['TurnCallPower'] = 2
    s['TurnBetPower'] = 2
    s['RiverMinCallEquity'] = 0.28
    s['RiverMinBetEquity'] = 0.45
    s['RiverMaxBetEquity'] = 1.0
    s['RiverCallPower'] = 2
    s['RiverBetPower'] = 2

    # Position ranges
    _pos_ranges = {0: 0.15, 1: 0.18, 2: 0.27, 3: 0.40, 4: 0.35, 5: 0.25}
    for i in range(6):
        s[f'range_utg{i}'] = _pos_ranges.get(i, 0.25)

    # Build preflop equity + push/fold tables
    try:
        from gamble.decisionmaker.range_equity import build_preflop_equity_table, build_push_fold_table
        build_preflop_equity_table()
        build_push_fold_table()
        log.info("Preflop equity + push/fold tables built")
    except Exception as e:
        log.warning(f"Preflop equity table failed: {e}")

    # Try to load preflop sheet
    preflop_sheet = None
    try:
        from gamble.tools.update_checker import UpdateChecker
        updater = UpdateChecker()
        url, backup = updater.get_preflop_sheet_url()
        preflop_sheet = pd.read_excel(url, sheet_name=None, engine='openpyxl')
    except Exception:
        pass

    results = {'total': 0, 'action': 0, 'no_turn': 0, 'no_cards': 0, 'error': 0}

    for filepath in files:
        results['total'] += 1
        fname = os.path.basename(filepath)
        try:
            screenshot = Image.open(filepath)
            img_w, img_h = screenshot.size
            # Assume standard table size (855x615 pt → 1710x1230 px)
            table_w_pt = img_w // 2
            table_h_pt = img_h // 2

            state = read_table(
                table_img=screenshot,
                window_name='Replay',
                window_id=0,
                table_x_pt=0, table_y_pt=0,
                table_w_pt=table_w_pt, table_h_pt=table_h_pt,
            )
            state.ocr_source = 'replay'

            if not state.is_my_turn:
                log.info(f"[{fname}] Not our turn — buttons={[a.action_type for a in state.available_actions]}")
                results['no_turn'] += 1
                continue

            if not state.my_cards or len(state.my_cards) != 2:
                log.info(f"[{fname}] No cards detected — actions={[a.action_type for a in state.available_actions]}")
                results['no_cards'] += 1
                continue

            # Create table object and populate from GameState
            t = TableScreenBased(strategy, {}, MockSignalsMC(), GameLogger(), version=6.76, nn_model=None)
            if preflop_sheet is not None:
                h = History()
                h.preflop_sheet = preflop_sheet
            else:
                h = History()

            state.to_table_scraper_compat(t)
            t.mycards = state.my_cards
            t.cardsOnTable = state.board_cards or []
            t.get_round_number(h)

            # Run Monte Carlo
            config = get_config()
            mock_signals = MockSignalsMC()
            preflop_state = CurrentHandPreflopState()
            run_montecarlo_wrapper(strategy, mock_signals, config, None, t, GameLogger(), preflop_state, h)

            # Make decision
            d = Decision(t, h, strategy, GameLogger())
            d.make_decision(t, h, strategy, GameLogger())

            results['action'] += 1
            log.info(f"[{fname}] DECISION: {d.decision} | "
                     f"cards={state.my_cards} board={state.board_cards} | "
                     f"pot={state.pot:.1f} call={state.call_amount:.1f} | "
                     f"equity={t.equity:.3f} abs_eq={t.abs_equity:.3f} | "
                     f"stage={t.gameStage} pos={state.position} | "
                     f"callLim={d.finalCallLimit:.1f} betLim={d.finalBetLimit:.1f}")

        except Exception as e:
            results['error'] += 1
            log.error(f"[{fname}] ERROR: {e}")
            import traceback as _tb
            log.debug(_tb.format_exc())

    log.info("=" * 60)
    log.info(f"REPLAY COMPLETE: {results['total']} screenshots")
    log.info(f"  Actions decided: {results['action']}")
    log.info(f"  Not our turn:    {results['no_turn']}")
    log.info(f"  No cards:        {results['no_cards']}")
    log.info(f"  Errors:          {results['error']}")
    log.info("=" * 60)


def main():
    """Entry point for multi-table runner"""
    import argparse

    parser = argparse.ArgumentParser(description='Multi-Table Poker Bot Runner')
    parser.add_argument('--max-tables', type=int, default=10, help='Maximum tables to play')
    parser.add_argument('--target-tables', type=int, default=0,
                       help='Target number of tables (0 = auto-detect from open windows)')
    parser.add_argument('--table-name', type=str, default='Official GGPoker 6player',
                       help='Table scraper name from MongoDB')
    parser.add_argument('--no-standardize', action='store_true',
                       help='Skip table resizing/tiling on startup')
    parser.add_argument('--dry-run', action='store_true',
                       help='Watch tables and make decisions but NEVER click. '
                            'Full pipeline test: OCR → equity → decision → log.')
    parser.add_argument('--replay', type=str, default=None,
                       help='Replay a screenshot through the full pipeline (no live tables needed)')
    args = parser.parse_args()

    # Screenshot replay mode — process a single image and exit
    if args.replay:
        init_logger(screenlevel=logging.INFO, filename='replay', logdir='log')
        _run_replay(args.replay)
        return

    # Initialize logging
    init_logger(screenlevel=logging.INFO, filename='multi_table', logdir='log')

    mode_str = " [DRY-RUN — NO CLICKS]" if args.dry_run else ""
    log.info("=" * 60)
    log.info(f"MULTI-TABLE RUNNER{mode_str}")
    log.info("=" * 60)

    target = args.target_tables
    if target == 0:
        # Auto-detect: count currently open poker windows
        try:
            import subprocess
            script = ('tell application "System Events" to tell process "GGnet" '
                      'to name of every window')
            result = subprocess.run(['osascript', '-e', script],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                names = [n.strip() for n in result.stdout.strip().split(',')]
                poker_kw = ['Blinds', 'NL', 'Rush', 'Cash', 'Spin', 'Gold',
                            'Hold', 'PLO']
                table_count = sum(1 for n in names
                                 if any(k in n for k in poker_kw))
                target = max(table_count, 1)
                log.info(f"Auto-detected {table_count} poker tables, target={target}")
            else:
                target = 1
        except Exception:
            target = 1

    runner = MultiTableRunner(
        max_tables=args.max_tables,
        target_tables=target,
        table_scraper_name=args.table_name,
        dry_run=args.dry_run,
    )

    try:
        runner.run(standardize_on_startup=not args.no_standardize)
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        runner.stop()


if __name__ == '__main__':
    main()
