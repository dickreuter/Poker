"""
UNIFIED AUTONOMOUS MULTI-TABLE BOT

This is the ONE bot that combines:
1. ORIGINAL bot's COMPLETE logic (25+ checks, full history, preflop learning)
2. Multi-table orchestration (handle 10 tables)
3. Self-learning/healing (auto-fix detection failures)
4. Window standardization (resize/tile for consistent detection)

Based on https://github.com/dickreuter/System - we IMPROVE on the original, not replace it.

Architecture:
    engine.py (THIS FILE)
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

import cv2
import numpy as np
import pandas as pd
from PIL import ImageGrab

# Original bot imports
from sys_core.decisionmaker.current_hand_memory import CurrentHandPreflopState, History
from sys_core.decisionmaker.decisionmaker import Decision
from sys_core.decisionmaker.montecarlo_python import run_montecarlo_wrapper
from sys_core.gui.action_and_signals import StrategyHandler
from sys_core.scraper.table_screen_based import TableScreenBased
from sys_core.tools.game_logger import GameLogger
from sys_core.tools.helper import init_logger, get_config
from sys_core.tools.mongo_manager import MongoManager
from sys_core.tools.mouse_mover import MouseMoverTableBased

# Self-learning imports
try:
    from sys_core.tools.adaptive_learner import log_action, get_threshold, get_learner, set_threshold, report_issue, save_debug_screenshot
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
    from sys_core.tools.vision_analyzer import auto_fix_buttons, auto_fix_cards
    VISION_ANALYZER_AVAILABLE = True
except ImportError:
    VISION_ANALYZER_AVAILABLE = False
    def auto_fix_buttons(img): return {'fixed': False}
    def auto_fix_cards(img): return {'fixed': False}

try:
    from sys_core.tools.self_healer import get_healer
    SELF_HEALER_AVAILABLE = True
except ImportError:
    SELF_HEALER_AVAILABLE = False
    def get_healer(): return None

# Lobby navigation
try:
    from sys_core.tools.dynamic_lobby_navigator import DynamicLobbyNavigator
    LOBBY_NAV_AVAILABLE = True
except ImportError:
    LOBBY_NAV_AVAILABLE = False

# Opponent modeling
try:
    from sys_core.decisionmaker.opponent_modeler import get_modeler as get_opponent_modeler
    OPPONENT_MODELER_AVAILABLE = True
except ImportError:
    OPPONENT_MODELER_AVAILABLE = False
    def get_opponent_modeler(): return None

# Deep CFR neural network strategy
try:
    from sys_core.decisionmaker.deepcfr_wrapper import deepcfr_decision, is_available as deepcfr_is_available, get_status as deepcfr_get_status
    DEEPCFR_AVAILABLE = True
except ImportError:
    DEEPCFR_AVAILABLE = False
    def deepcfr_decision(t, h, p): return None
    def deepcfr_is_available(): return False
    def deepcfr_get_status(): return "Deep CFR: Not installed"

# Rust OCR bridge
try:
    from sys_core.ocr.rust_bridge import RustOCRBridge
    from sys_core.ocr.game_state import GameState
    RUST_OCR_AVAILABLE = True
except ImportError:
    RUST_OCR_AVAILABLE = False

# Python OCR pipeline (table_reader)
try:
    from sys_core.ocr.table_reader import read_table, _detect_buttons
    from sys_core.ocr.game_state import GameState, AvailableAction, HandContext
    PYTHON_OCR_AVAILABLE = True
except ImportError:
    PYTHON_OCR_AVAILABLE = False

# Local table config (replaces MongoDB dependency)
try:
    from sys_core.ocr.local_table_config import build_local_table_dict
    LOCAL_TABLE_CONFIG_AVAILABLE = True
except ImportError:
    LOCAL_TABLE_CONFIG_AVAILABLE = False

# Template collector (auto-captures real card templates during play)
try:
    from sys_core.ocr.template_collector import get_collector as get_template_collector
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
    from sys_core.tools.update_checker import UpdateChecker
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

    # Hand context — full action tracking across streets within one hand
    _hand_context: Optional[object] = None  # HandContext, created per hand
    _hand_context_last_street: str = ""  # Prevents re-recording same street


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
                 max_tables: int = 12,
                 target_tables: int = 9,
                 table_scraper_name: str = "Official GGPoker 6player",
                 dry_run: bool = False,
                 strategy_mode: str = 'ev'):
        self.max_tables = max_tables
        self.target_tables = target_tables
        self.table_scraper_name = table_scraper_name
        self.dry_run = dry_run
        self.strategy_mode = strategy_mode  # 'ev' or 'deepcfr'

        self.sessions: Dict[int, TableSession] = {}  # window_id -> session
        self._session_lock = threading.Lock()  # Protects session dict mutations
        self._last_tile_time = 0  # Grid Lockdown Timer
        self.running = False

        # Bankroll protection (Phase 5)
        self._session_rebuys = 0
        self._max_session_rebuys = 10
        self._buyins_lost = 0
        self._max_buyins_loss = 8  # 8 buy-ins = reasonable for Rush & Cash variance

        # Standard table size for consistent detection (must be set before table config)
        # GGSystem enforces minimum 850x615pt — can't go smaller.
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
        # Increase required equity when facing a raiser/caller.
        # A raiser has top 12-25% of hands, so our equity requirement should
        # jump significantly (was 0.03, far too small).
        s['pre_flop_equity_increase_if_bet'] = 0.10   # +10% equity needed vs raiser
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

        # Strategy mode: 'ev' (default EV engine) or 'deepcfr' (neural network)
        log.info(f"Strategy mode: {self.strategy_mode}")
        if self.strategy_mode == 'deepcfr':
            if DEEPCFR_AVAILABLE and deepcfr_is_available():
                log.info(f"Deep CFR engine: READY ({deepcfr_get_status()})")
            else:
                log.warning(f"Deep CFR requested but unavailable ({deepcfr_get_status()}), "
                           f"will fall back to EV engine")

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
        # Log avatar exclusion zones once per new session (for debugging)
        try:
            self._log_avatar_zones(session)
        except Exception:
            pass
        return session

    def grab_full_screen(self):
        """Grab one full-screen screenshot (shared across all tables).
        Note: mss is faster but returns 1x on Retina (breaks coordinate system).
        Sticking with PIL ImageGrab which returns correct 2x Retina pixels.
        """
        return ImageGrab.grab()

    def get_table_screenshot(self, window: TableWindow, full_screen=None):
        """Crop a table from a full-screen screenshot.

        If full_screen is provided, reuses it (fast — no new capture).
        Otherwise captures a fresh full screen (~80ms).
        Does NOT focus/raise the window.
        """
        if full_screen is None:
            full_screen = self.grab_full_screen()
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
                        # Reset hand context for new hand
                        session._hand_context = None
                        session._hand_context_last_street = ""

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
                    if self._is_avatar_zone(deal_me_in.screen_x_pt, deal_me_in.screen_y_pt, session):
                        log.warning(f"AVATAR GUARD: Deal Me In at ({deal_me_in.screen_x_pt}, {deal_me_in.screen_y_pt}) "
                                    f"overlaps avatar — skipping")
                    else:
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

        # Close any popup windows (Smart HUD, player profiles) that block the view
        # Only check every 10 seconds to avoid overhead
        now_ts = time.time()
        if now_ts - getattr(session, '_last_popup_check', 0) > 10:
            session._last_popup_check = now_ts
            self._close_popups(session)

        if PYTHON_OCR_AVAILABLE:
            state = self.capture_game_state(session, full_screen=full_screen)
            if state is not None:
                session._cached_game_state = state

                # Cache cards whenever successfully detected (warm cache for process_table)
                if state.my_cards and len(state.my_cards) == 2:
                    session._cached_cards = list(state.my_cards)
                elif not state.board_cards or len(state.board_cards) == 0:
                    # New hand started and no cards visible — clear stale cache
                    if not state.is_my_turn:
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
                            from sys_core.decisionmaker.decisionmaker import _normalize_hand
                            h_norm = _normalize_hand(state.my_cards[0], state.my_cards[1])
                            if h_norm in trash:
                                log.info(f"AUTO-FOLD: checking 'Fold to any bet' for trash hand {h_norm}")
                                import pyautogui
                                if not self._is_avatar_zone(pre_fold_pos[0], pre_fold_pos[1], session):
                                    pyautogui.click(pre_fold_pos[0], pre_fold_pos[1])
                                else:
                                    log.warning(f"AVATAR GUARD: Pre-fold checkbox overlaps avatar — skipping")
                                session._pre_fold_checkbox = None # Only click once per hand

                # Save verification screenshot periodically
                self._maybe_save_verification(session, state, full_screen)

                return session.state

        # Fallback to original check
        return self.check_table_state(session)

    def _maybe_save_verification(self, session: TableSession, state, full_screen):
        """Save card crops for live verification (~every 5s per table).

        Saves:
          1. Full table screenshot with detected cards/board in filename
          2. Individual hero card crops (left + right) for visual audit
          3. Board card region crop (when board is detected)
        """
        if not state.my_cards or len(state.my_cards) < 1:
            return

        now = time.time()
        last_save = getattr(session, '_last_verify_save', 0)
        if now - last_save < 5:
            return
        session._last_verify_save = now

        try:
            verify_dir = Path('/tmp/table_debug/card_verify')
            verify_dir.mkdir(parents=True, exist_ok=True)

            # Crop the table from full screen
            w = session.window
            bounds = w.bounds_pixels
            table_img = full_screen.crop(bounds)
            table_np = np.array(table_img)
            H, W = table_np.shape[:2]

            # Save full table with cards/board annotation in filename
            cards_str = '_'.join(state.my_cards)
            board_str = '_'.join(state.board_cards) if state.board_cards else 'preflop'
            ts = datetime.datetime.now().strftime('%H%M%S')
            filename = f"{ts}_{cards_str}_board_{board_str}.png"
            table_img.save(str(verify_dir / filename))
            log.debug(f"Saved verification: {filename}")

            # Save hero card region crop (Y=53-88%, X=34-65%)
            hero_y1, hero_y2 = int(H * 0.53), int(H * 0.88)
            hero_x1, hero_x2 = int(W * 0.34), int(W * 0.65)
            hero_crop = table_np[hero_y1:hero_y2, hero_x1:hero_x2]
            if hero_crop.size > 0:
                cv2.imwrite(str(verify_dir / f"{ts}_hero_{cards_str}.png"),
                            cv2.cvtColor(hero_crop, cv2.COLOR_RGB2BGR))

            # ALWAYS save board region crop (Y=30-55%, X=15-85%) for audit
            # even when board=[] so we can see what should have been detected
            board_y1, board_y2 = int(H * 0.30), int(H * 0.55)
            board_x1, board_x2 = int(W * 0.15), int(W * 0.85)
            board_crop = table_np[board_y1:board_y2, board_x1:board_x2]
            if board_crop.size > 0:
                cv2.imwrite(str(verify_dir / f"{ts}_board_{board_str}.png"),
                            cv2.cvtColor(board_crop, cv2.COLOR_RGB2BGR))

            # Keep only last 100 files to avoid filling disk
            files = sorted(verify_dir.glob('*.png'))
            for old_file in files[:-100]:
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
                        if self._is_avatar_zone(screen_x, screen_y, session):
                            log.warning(f"AVATAR GUARD: FAST Deal Me In at ({screen_x}, {screen_y}) "
                                        f"overlaps avatar — skipping")
                            break
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
        Uses a per-session deep copy to avoid race conditions when multiple
        tables with different game types are active.
        """
        import copy as _copy

        # Deep-copy the base strategy into a per-session snapshot so
        # concurrent tables with different game types don't clobber
        # each other's parameters.
        if not hasattr(session, '_strategy_snapshot'):
            session._strategy_snapshot = _copy.deepcopy(self.strategy.selected_strategy)

        s = session._strategy_snapshot
        preset = self._STRATEGY_PRESETS.get(game_type, self._STRATEGY_PRESETS['cash'])

        # Apply all preset values to the SESSION-LOCAL copy
        for key, val in preset.items():
            if key == '_pos_ranges':
                for i in range(6):
                    s[f'range_utg{i}'] = val.get(i, 0.25)
            else:
                s[key] = val

        # Point the shared strategy at this session's snapshot during decision.
        # This is safe because process_table_new_ocr runs sequentially per table.
        self.strategy.selected_strategy = s

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
            self.stats['detection_success']['buttons_fail'] += 1
            return False

        # Track successful button detection
        self.stats['detection_success']['buttons'] += 1

        # --- CONFIDENCE GATE (Phase 1B): Don't act on bad OCR data ---
        conf = getattr(state, 'confidence', None)
        # Skip re-read if: (a) only call/pot OCR failed (cards fine), or
        # (b) no cards AND no pot (hand likely not started — Deal Me In screen).
        if conf and conf.overall < 0.5 and conf.cards < 0.7 \
                and not (len(state.my_cards) == 0 and state.pot <= 0):
            log.warning(f"Low confidence {conf} — re-reading table {session.window.name}")
            retry_state = self.capture_game_state(session)
            if retry_state and retry_state.is_my_turn:
                retry_conf = getattr(retry_state, 'confidence', None)
                if retry_conf and retry_conf.overall >= 0.4:
                    state = retry_state
                    conf = retry_conf
                    log.info(f"Confidence improved after re-read: {conf}")
                elif retry_conf and retry_conf.overall < 0.4:
                    # Still bad — if free check available, take it; else skip
                    available_types = {a.action_type for a in (retry_state or state).available_actions}
                    if 'check' in available_types:
                        check_action = next(a for a in (retry_state or state).available_actions if a.action_type == 'check')
                        log.warning(f"Very low confidence {retry_conf} — clicking free check")
                        self._click_action(check_action, session, retry_state or state, "low_conf_check")
                        return True
                    # Don't just skip — fold to avoid timing out
                    if 'fold' in available_types:
                        fold_action = next(a for a in (retry_state or state).available_actions if a.action_type == 'fold')
                        log.warning(f"Very low confidence {retry_conf} — folding to avoid timeout")
                        self._click_action(fold_action, session, retry_state or state, "low_conf_fold")
                        return True
                    log.warning(f"Very low confidence {retry_conf} — skipping decision")
                    return False

        # Dedup guard: don't act twice on the exact same situation.
        # Include pot size (rounded) so a 3-bet/re-raise creates a new key.
        cards_key = ','.join(sorted(state.my_cards)) if state.my_cards and len(state.my_cards) == 2 else ''
        board_count = len(state.board_cards) if state.board_cards else 0
        pot_key = round(state.pot, 1) if state.pot else 0
        actions_key = ','.join(sorted(a.action_type for a in state.available_actions))
        current_key = f"{cards_key}|{board_count}|{pot_key}|{actions_key}"
        if current_key and current_key == session._last_acted_key:
            log.debug(f"Dedup: already acted on {current_key}, skipping")
            return False

        # Create a FRESH TableScreenBased per call for thread safety.
        # When multiple tables run process_table_new_ocr concurrently via
        # ThreadPoolExecutor, sharing session._table causes data races
        # (one thread's cards/equity overwriting another's).
        t = TableScreenBased(
            self.strategy, session.table_dict,
            MockSignalsMC(), session.game_logger,
            version=6.76, nn_model=None
        )
        if self.preflop_sheet is not None:
            session.history.preflop_sheet = self.preflop_sheet

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
            # Only reuse cached cards if pot > 0 (we're actually in a hand).
            # When pot=0 and cards=[], we're between hands — don't reuse stale cache.
            cached = getattr(session, '_cached_cards', None)
            if cached and len(cached) == 2 and state.pot > 0:
                log.info(f"Using cached cards {cached} (OCR failed, reusing same-hand cache)")
                state.my_cards = list(cached)
            elif cached and state.pot <= 0:
                log.debug(f"Clearing stale card cache {cached} (pot=0, likely between hands)")
                session._cached_cards = None

        # If no cards yet, retry with increasing delays (animation timing)
        if not state.my_cards or len(state.my_cards) != 2:
            if not hasattr(session, '_no_cards_retries'):
                session._no_cards_retries = 0

            partial = state.my_cards if state.my_cards else []
            log.warning(f"Incomplete card detection: {partial} — retrying up to 5 times")

            retry_delays = [0.15, 0.30, 0.45, 0.60, 0.80]
            for attempt, delay in enumerate(retry_delays):
                session._no_cards_retries += 1
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
        # If we reach here and still don't have cards, check if we can free-check.
        if not state.my_cards or len(state.my_cards) != 2:
            # Fix: Temporal Consistency Check
            if not hasattr(session, '_no_cards_count'): session._no_cards_count = 0
            session._no_cards_count += 1
            if session._no_cards_count < 2:
                log.info(f"Blink Protection: No cards detected once for {session.window.name}, retrying next frame...")
                return False

            # Free-check fallback: if CHECK is available, clicking it is always +EV
            # (it's free). Don't waste the turn just because cards are unreadable.
            available_action_types = {a.action_type for a in state.available_actions}
            if 'check' in available_action_types:
                check_action = next(a for a in state.available_actions if a.action_type == 'check')
                log.info(f"Cards unreadable but CHECK available — checking (free) for {session.window.name}")
                self._click_action(check_action, session, state, "free_check_no_cards")
                session._no_cards_count = 0
                return True

            # Small-blind call fallback: if call ≤ 1 BB, just call (better than timeout)
            if 'call' in available_action_types:
                call_action = next(a for a in state.available_actions if a.action_type == 'call')
                if call_action.amount is not None and call_action.amount <= 1.0:
                    log.warning(f"Cards unreadable, calling small blind ({call_action.amount} BB) for {session.window.name}")
                    self._click_action(call_action, session, state, "blind_call_no_cards")
                    session._no_cards_count = 0
                    self.stats['detection_success']['cards_fail'] += 1
                    return True

            # Explicit fold (better than timeout which wastes time bank)
            if 'fold' in available_action_types:
                fold_action = next(a for a in state.available_actions if a.action_type == 'fold')
                log.warning(f"Cards unreadable — folding explicitly for {session.window.name} (better than timeout)")
                self._click_action(fold_action, session, state, "fold_no_cards")
                session._no_cards_count = 0
                self.stats['detection_success']['cards_fail'] += 1
                return True

            log.warning(f"Aborting decision for {session.window.name}: No valid hole cards and no actionable buttons after {session._no_cards_count} frames.")
            self.stats['detection_success']['cards_fail'] += 1
            return False

        # Reset protection if cards found
        session._no_cards_count = 0
        # Track successful card detection
        self.stats['detection_success']['cards'] += 1

        # --- HAND CONFIRMATION (lightweight) ---
        # We already validated 2 cards exist above + did up to 4 retries.
        # Frame voting (requiring 2 consecutive identical reads) was removed
        # because it wasted 0.5-1.0s EVERY hand in Rush & Cash — a significant
        # speed penalty. The card retry loop above already ensures reliability.
        # If cached cards match current cards, we're confident. If they differ,
        # trust the fresh read (it passed all validation already).
        if hasattr(session, '_hand_votes'):
            del session._hand_votes  # Clean up old attribute

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
                    # Retry up to 3 times with progressive delays.
                    # Board animations on GGSystem can take 0.3-0.5s.
                    import time as _rt
                    board_fixed = False
                    for board_attempt in range(3):
                        _rt.sleep(0.15 + board_attempt * 0.15)  # 0.15, 0.30, 0.45s
                        retry_state = self.capture_game_state(session)
                        if retry_state and retry_state.board_cards:
                            rb = retry_state.board_cards
                            if len(rb) >= expected_board.get(stage, 0):
                                t.cardsOnTable = rb
                                log.info(f"Board retry #{board_attempt+1} succeeded: {rb}")
                                board_fixed = True
                                break
                            elif len(rb) > board_len:
                                t.cardsOnTable = rb
                                board_len = len(rb)
                                log.info(f"Board retry #{board_attempt+1} partial improvement: {rb}")
                    if not board_fixed:
                        log.warning(f"Board still incomplete after 3 retries ({board_len} cards), skipping")
                        return False

                # Always set _table_name so ICM/tournament detection works
                # even if opponent modeler is disabled.
                t._table_name = getattr(session.window, 'name', '') if session.window else ''

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
                        if profile.get('type', 'unknown') != 'unknown':
                            log.info(f"OPP_PROFILE: {villain_id} = {profile['type']} "
                                     f"(VPIP={profile['vpip']:.0%} PFR={profile['pfr']:.0%} "
                                     f"AF={profile['af']:.1f} hands={profile['hands']})")
                    except Exception as e:
                        log.debug(f"Opponent modeling error (pre-MC): {e}")

                # Update hand context (tracks full action sequence across streets)
                self._update_hand_context(session, state, t)

                # Run Monte Carlo with timeout to prevent table starvation.
                # If MC hangs (bad card encoding, infinite loop), we abort
                # after 8 seconds and use whatever equity we have.
                mock_signals = MockSignalsMC()
                config = get_config()
                mc_error = [None]

                # Reset equity BEFORE MC so stale value from previous hand
                # doesn't leak through if MC fails/times out.
                t.equity = 0

                # Use threading.Event for clean synchronization — the MC
                # thread signals when equity is finalized, preventing races
                # where we read t.equity while the daemon is still writing.
                equity_ready = threading.Event()

                def _run_mc():
                    try:
                        run_montecarlo_wrapper(
                            p, mock_signals, config, None,
                            t, session.game_logger,
                            session.preflop_state, h,
                        )
                    except Exception as e:
                        mc_error[0] = e
                    finally:
                        equity_ready.set()

                mc_thread = threading.Thread(target=_run_mc, daemon=True)
                mc_thread.start()
                equity_ready.wait(timeout=8.0)

                if not equity_ready.is_set():
                    log.error(f"MONTE CARLO TIMEOUT (8s) for {session.window.name} — "
                              f"using default equity {t.equity:.3f}")
                    # Snapshot whatever equity exists, then set conservative default
                    equity_snapshot = t.equity
                    if equity_snapshot == 0:
                        t.equity = 0.35  # Conservative — call only with pot odds
                        log.warning(f"MC TIMEOUT: Using default equity 0.35")
                    else:
                        t.equity = equity_snapshot  # Use partial result
                        log.warning(f"MC TIMEOUT: Using partial equity {equity_snapshot:.3f}")
                elif mc_error[0]:
                    log.error(f"Monte Carlo error: {mc_error[0]}")
                    if not hasattr(t, 'equity') or t.equity == 0:
                        t.equity = 0.35
                        log.warning(f"MC ERROR: Using default equity 0.35")

                # Make decision
                d = Decision(t, h, p, session.game_logger)

                # Attach opponent profile to decision object
                if opp_profile:
                    d._opp_profile = opp_profile

                d._spot_adj = self.spot_tracker.compute_adjustments()

                # Multi-street planning: pass previous street info to decision
                d._we_bet_prev_street = getattr(session, '_we_bet_last_street', False)
                d._prev_street_equity = getattr(session, '_last_equity', None)

                # Hand context: full action history for context-aware ranges
                d._hand_context = session._hand_context

                d.make_decision(t, h, p, session.game_logger)

                # Track our action for multi-street planning
                dec_str = str(d.decision).lower() if d.decision else ''
                session._we_bet_last_street = ('bet' in dec_str or 'raise' in dec_str)
                session._last_equity = t.equity

                # Record hero action in hand context
                self._record_hero_action_in_context(
                    session, dec_str, t.gameStage,
                    amount=getattr(t, 'currentCallValue', 0) or 0,
                    pot=getattr(t, 'totalPotValue', 0) or 0,
                )

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

                # Tournament context for logging
                tourney_log = ''
                if state.is_tournament and state.tournament_rank:
                    tourney_log = (f" | TOURNEY: rank={state.tournament_rank}"
                                   f"/{state.tournament_total}"
                                   f" ICM={state.icm_pressure:.2f}")

                # Hand context summary for logging
                _ctx = session._hand_context
                _ctx_str = ""
                if _ctx is not None:
                    _vp = _ctx.villain_pattern
                    if _vp:
                        _ctx_str = (f" ctx=[{_vp} aggro={_ctx.streets_of_aggression}"
                                    f" pf_raiser={_ctx.preflop_raiser_position or '-'}"
                                    f" cbet={'Y' if _ctx.is_cbet_spot else 'N'}"
                                    f" mw={'Y' if _ctx.is_multiway else 'N'}]")

                # Multi-street planning info
                _ms_str = ""
                _ms_info = getattr(d, '_multi_street_info', None)
                if _ms_info is None:
                    # Check if compute_ev_decision stored it in the result
                    _ev_res = getattr(d, '_last_ev_result', None)
                    if _ev_res and isinstance(_ev_res, dict):
                        _ms_info = _ev_res.get('multi_street')
                if _ms_info and isinstance(_ms_info, dict):
                    _ms_str = (f" | PLAN: check_ev={_ms_info.get('total_ev_check', 0):+.1f}"
                               f" bet_ev={_ms_info.get('total_ev_bet', 0):+.1f}"
                               f" ({_ms_info.get('simulations', 0)} runouts,"
                               f" {_ms_info.get('time_ms', 0):.0f}ms,"
                               f" improves {_ms_info.get('improvement_rate', 0):.0%})")

                log.info(f"DECISION: {mouse_target} | cards={state.my_cards} "
                         f"board={state.board_cards} | pot={state.pot:.1f} call={state.call_amount:.1f} "
                         f"| equity={equity_val:.3f} abs_eq={abs_eq_val:.3f} "
                         f"| EV={ev:+.2f} BB"
                         f"| callLim={d.finalCallLimit:.1f} betLim={d.finalBetLimit:.1f} "
                         f"| stage={t.gameStage} pos={getattr(state, 'position', '?')}"
                         f" opp={t.other_active_players} init={'Y' if t.other_player_has_initiative else 'N'}"
                         f"{_ctx_str}{blocker_str}{opp_str}{tourney_log}{_ms_str}")

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

                # --- HAND SNAPSHOT: Screenshot + detection overlay for verification ---
                try:
                    self._save_hand_snapshot(session, state, mouse_target,
                                            equity_val, abs_eq_val, decision_obj=d)
                except Exception as e:
                    log.debug(f"Failed to save hand snapshot: {e}")

                # Log hand to local history file
                try:
                    self._log_hand_locally(state, mouse_target, equity_val, abs_eq_val,
                                          decision_obj=d)
                except Exception:
                    pass  # Never let logging break decision flow

                # Ghost board warning (no forced fold — board OCR is primary now)
                board_len_check = len(state.board_cards) if state.board_cards else 0
                pot_check = state.pot or 0
                if board_len_check == 0 and pot_check > 20:
                    log.warning(f"GHOST BOARD: pot={pot_check:.1f}BB but 0 board cards. "
                                f"Board detection may have failed. Proceeding with decision anyway.")

                # --- POT-COMMITTED OVERRIDE ---
                # If hero has <= 3 BB left and there's a pot, NEVER fold.
                # You're pot-committed — calling is mathematically correct
                # regardless of hand strength. This prevents the bot from
                # folding after raising with 1 BB behind.
                hero_stack_now = state.hero_stack if state.hero_stack else 0
                pot_now = state.pot if state.pot else 0
                call_now = state.call_amount if state.call_amount else 0
                target_str_check = str(mouse_target).split('.')[-1].lower() if hasattr(mouse_target, 'name') else str(mouse_target).lower()

                if target_str_check == 'fold' and hero_stack_now <= 3.0 and pot_now > 0:
                    log.warning(f"POT-COMMITTED OVERRIDE: Decision was Fold but hero has "
                                f"only {hero_stack_now:.1f} BB with pot={pot_now:.1f} BB — "
                                f"FORCING CALL (pot committed)")
                    mouse_target = 'call'

                # Also: never fold when call amount is <= 1 BB and pot is large
                if target_str_check == 'fold' and call_now <= 1.0 and pot_now >= 4.0:
                    log.warning(f"POT-ODDS OVERRIDE: Decision was Fold but call={call_now:.1f} "
                                f"into pot={pot_now:.1f} (getting {pot_now/max(call_now,0.1):.0f}:1) — "
                                f"FORCING CALL (great pot odds)")
                    mouse_target = 'call'

                # --- IRON-CLAD EXECUTION FLOW (Safe Version) ---
                # Map DecisionMaker output to available action
                action = self._map_decision_to_action(state, mouse_target)
                target_str = str(mouse_target).split('.')[-1].lower() if hasattr(mouse_target, 'name') else str(mouse_target).lower()

                # NOTE: DecisionTypes.check means "check if free, call if not" —
                # it maps to the Call button. No safety guard needed here;
                # the old guard caused infinite retry loops when call_amount > 0.

                # GUARANTEED ACTION: ONLY for 'Fold'. 
                # We can safely fallback to a coordinate click for Fold to save the hand.
                # We NEVER fallback for Call/Raise because clicking the wrong spot costs money.
                if not action and target_str == 'fold':
                    log.warning(f"Iron-Clad: No Fold button found, using coordinate fallback.")
                    tx = 0.15 # Standard Fold position
                    from sys_core.ocr.game_state import AvailableAction
                    action = AvailableAction(
                        action_type='fold',
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
                # FALLBACK: Check if free, fold otherwise (better than timeout)
                try:
                    if not state.available_actions:
                        log.error("FALLBACK: No available_actions detected — cannot act, will timeout")
                        return False
                    available_types = {a.action_type for a in state.available_actions}
                    if 'check' in available_types:
                        check_action = next(a for a in state.available_actions if a.action_type == 'check')
                        log.warning("FALLBACK: Decision crashed, checking (free)")
                        self._click_action(check_action, session, state, "fallback_check")
                        return True
                    elif 'fold' in available_types:
                        fold_action = next(a for a in state.available_actions if a.action_type == 'fold')
                        log.warning("FALLBACK: Decision crashed, folding")
                        self._click_action(fold_action, session, state, "fallback_fold")
                        return True
                except Exception as fallback_err:
                    log.error(f"Fallback action also failed: {fallback_err}")
                return False

        # No cards after all retries — DO NOT ACT.
        # It is safer to wait than to check/fold blindly.
        log.warning(f"Aborting decision for {session.window.name}: No valid hand identified after all retries.")
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

        # 3. Raise/Bet logic (PRIORITIZE AGGRESSION)
        if any(kw in target_str for kw in ('raise', 'bet', '3bet', '4bet', 'allin', 'bluff')):
            # Prioritize raise/bet buttons strictly
            btn = (state.get_action_by_type('raise') or
                   state.get_action_by_type('bet') or
                   state.get_action_by_type('all_in'))
            
            if btn:
                log.debug(f"MAP: {mouse_target} -> {btn.action_type}")
                return btn
            
            # NO FALLBACK TO CALL/CHECK. If we want to raise, we wait for the raise button.
            return None

        # 4. Lobby/Special buttons
        if 'imback' in target_str:
            return state.get_action_by_type('im_back') or state.get_action_by_type('deal_me_in')

        return None

    # --- Avatar exclusion zones ---
    # Derived from SEAT_REGIONS_6MAX in table_reader.py.
    # Each entry: (x_center_frac, y_center_frac, width_frac, height_frac)
    # We expand by a margin to cover the full avatar+name area above the stack text.
    _SEAT_FRACTIONS_6MAX = [
        (0.500, 0.930, 0.14, 0.040),  # Seat 0: Hero (bottom center)
        (0.068, 0.765, 0.16, 0.060),  # Seat 1: Left-bottom
        (0.150, 0.370, 0.16, 0.060),  # Seat 2: Left-top
        (0.500, 0.268, 0.16, 0.060),  # Seat 3: Top center
        (0.870, 0.370, 0.16, 0.060),  # Seat 4: Right-top
        (0.915, 0.765, 0.16, 0.060),  # Seat 5: Right-bottom
    ]

    # Margin in points added around each seat region to cover avatar + name.
    # The SEAT_REGIONS_6MAX centers on the stack *text* line, but the clickable
    # avatar is ~40-60pt above that. We extend upward more than downward.
    _AVATAR_MARGIN_TOP_PT = 55   # avatar is above the stack text
    _AVATAR_MARGIN_BOTTOM_PT = 15
    _AVATAR_MARGIN_X_PT = 20

    def _get_avatar_zones(self, session) -> list:
        """Return avatar exclusion zones as [(x1_pt, y1_pt, x2_pt, y2_pt), ...].

        Coordinates are absolute macOS screen POINTS.
        Excludes seat 0 (hero) because action buttons overlap the hero area.
        """
        w = session.window if hasattr(session, 'window') else session
        zones = []
        for idx, (xf, yf, wf, hf) in enumerate(self._SEAT_FRACTIONS_6MAX):
            if idx == 0:
                continue  # Skip hero seat — buttons overlap this area
            # Convert fractions to points relative to window
            cx_pt = w.x + xf * w.width
            cy_pt = w.y + yf * w.height
            half_w = (wf * w.width) / 2 + self._AVATAR_MARGIN_X_PT
            top = cy_pt - self._AVATAR_MARGIN_TOP_PT
            bot = cy_pt + (hf * w.height) / 2 + self._AVATAR_MARGIN_BOTTOM_PT
            zones.append((
                cx_pt - half_w,
                top,
                cx_pt + half_w,
                bot,
            ))
        return zones

    def _is_avatar_zone(self, x_pt: float, y_pt: float, session) -> bool:
        """Check if screen-point (x_pt, y_pt) falls inside any player avatar zone.

        Returns True if clicking there would open a Smart HUD popup.
        """
        zones = self._get_avatar_zones(session)
        for (x1, y1, x2, y2) in zones:
            if x1 <= x_pt <= x2 and y1 <= y_pt <= y2:
                return True
        return False

    def _log_avatar_zones(self, session):
        """Print avatar exclusion zones for debugging. Call once on startup."""
        zones = self._get_avatar_zones(session)
        # Seat 0 (hero) is excluded — zones correspond to seats 1-5 only
        seat_names = ['Seat1:Left-bottom', 'Seat2:Left-top',
                      'Seat3:Top-center', 'Seat4:Right-top', 'Seat5:Right-bottom']
        w = session.window if hasattr(session, 'window') else session
        log.info(f"AVATAR ZONES for table {w.width}x{w.height}pt at ({w.x},{w.y}) "
                 f"[{len(zones)} opponent zones, hero excluded]:")
        for (x1, y1, x2, y2), name in zip(zones, seat_names):
            log.info(f"  {name}: ({x1:.0f},{y1:.0f}) - ({x2:.0f},{y2:.0f})  "
                     f"[{x2-x1:.0f}x{y2-y1:.0f} pt]")

    def _reliable_click(self, x_pt: int, y_pt: int, label: str = "", session=None):
        """Click at macOS POINT coordinates with move-before-click.

        More reliable than pyautogui.click() because:
        1. Moves mouse to position first (prevents teleport-swallowed clicks)
        2. Sets kCGMouseEventClickState for proper click registration
        3. Small delay between down/up events
        4. Checks avatar exclusion zones to prevent Smart HUD popups
        """
        # Avatar zone guard — skip click if it would hit a player avatar
        # EXEMPT: action buttons (fold/call/raise/check/bet), input fields, shortcuts
        _exempt_labels = {'fold', 'call', 'raise', 'check', 'bet', 'all_in',
                          'input_field_center', 'input_focus', 'shortcut',
                          'deal_me_in', 'confirm', 'prefold'}
        label_lower = (label or '').lower().strip()
        is_exempt = any(ex in label_lower for ex in _exempt_labels)
        if not is_exempt and session is not None and self._is_avatar_zone(x_pt, y_pt, session):
            log.warning(f"AVATAR GUARD: Blocked click '{label}' at ({x_pt}, {y_pt}) — "
                        f"would hit player avatar zone")
            return
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
            # Loose match because GGSystem titles change (blinds/table ID)
            return window_name in front_name or front_name in window_name
        except Exception:
            return False

    def _activate_table_window(self, session: TableSession):
        """Bring the specific table window to front before clicking.

        Matches by window name AND position to disambiguate tables with
        identical names (common in multi-table). Falls back to name-only
        matching if position matching fails.

        Caches the last activated window ID to skip redundant AppleScript
        calls when processing the same table consecutively.
        """
        try:
            wid = session.window.window_id
            name = session.window.name
            wx, wy = session.window.x, session.window.y

            # Skip if this window is already frontmost (by window ID, not name)
            if self._last_activated_window == wid:
                log.debug(f"Window already active: {name} (id={wid})")
                return True

            log.debug(f"Activating window: {name} (id={wid} pos={wx},{wy})")

            # Escape double quotes in window name for AppleScript
            escaped_name = name.replace('"', '\\"')

            # Match by window name AND position to disambiguate same-named tables.
            # Position matching uses a ±20pt tolerance for window manager drift.
            script = f'''
            tell application "System Events"
                tell process "GGnet"
                    set frontmost to true
                    repeat with w in windows
                        if name of w contains "{escaped_name}" then
                            set p to position of w
                            set px to item 1 of p
                            set py to item 2 of p
                            if (px - {wx}) > -20 and (px - {wx}) < 20 and (py - {wy}) > -20 and (py - {wy}) < 20 then
                                perform action "AXRaise" of w
                                return "ok_pos"
                            end if
                        end if
                    end repeat
                    -- Fallback: name-only match (position may have changed)
                    repeat with w in windows
                        if name of w contains "{escaped_name}" then
                            perform action "AXRaise" of w
                            return "ok_name"
                        end if
                    end repeat
                end tell
            end tell
            return "not_found"
            '''
            result = subprocess.run(['osascript', '-e', script],
                                    capture_output=True, text=True, timeout=2)

            if 'ok' in result.stdout:
                # Quick settle time for the window manager
                time.sleep(0.05)
                self._last_activated_window = wid
                if 'ok_name' in result.stdout and 'ok_pos' not in result.stdout:
                    log.debug(f"Window matched by name only (position changed?)")
                return True

            # Fallback: just bring the process to front (better than nothing)
            log.warning(f"Window match failed for '{name}', using frontmost fallback")
            time.sleep(0.05)
            self._last_activated_window = wid
            return True  # Process is frontmost at least
        except Exception as e:
            log.debug(f"Window activation failed: {e}")
            return False

    def _verify_button_color(self, x_pt: int, y_pt: int) -> bool:
        """Quick color check at click target to verify a button is still there.

        GGSystem action buttons are dark red (H=10-16, S>80, V>90).
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
        """Click an action button using screen coordinates from GameState.

        Uses _click_lock to serialize window activation + clicking across
        parallel table-processing threads (only one mouse cursor).
        """
        import pyautogui
        import time as _time

        with self._click_lock:
            self._click_action_inner(action, session, state, decision_label, high_pressure)

    def _click_action_inner(self, action, session: TableSession, state, decision_label: str, high_pressure: bool = False):
        """Inner click logic, called under _click_lock."""
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
            actions_key = ','.join(sorted(a.action_type for a in state.available_actions)) if state.available_actions else ''
            session._last_acted_key = f"{cards_key}|{board_count}|{pot_key}|{actions_key}"
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
        if not self._activate_table_window(session):
            log.warning(f"Could not focus {session.window.name}, but trying click anyway.")
        
        # Mandatory delay for macOS focus to register
        _time.sleep(0.3)

        # Recompute raise amount (may differ from dry-run computation above
        # if state was updated during window activation).
        target_amount = self._compute_raise_amount(state, decision_label)

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
                # GGSystem macOS Calibration (Mar 14 2026):
                # The input box is ~51 points LEFT and ~59 points ABOVE the raise button center.
                input_x = bet_btn.screen_x_pt - 51
                input_y = bet_btn.screen_y_pt - 59
            else:
                # Use the passed-in action (even if it's the fallback)
                input_x = action.screen_x_pt - 51
                input_y = action.screen_y_pt - 59

            # BB display mode is ON — input field expects BB amounts directly
            bb_amount = round(target_amount, 1)
            amount_str = str(bb_amount)

            # -- FOCUS SHIELD: ensure this table is active before typing --
            if not self._activate_table_window(session):
                log.error(f"Sizing ABORTED: Could not get stable focus on {session.window.name}")
                return

            # --- POT SIZE SHORTCUTS (Fast Path) ---
            # Only use shortcuts when POSTFLOP and the computed target_amount
            # matches the pot-fraction amount within tolerance.
            # Preflop sizing uses GTO open/3bet/4bet which rarely matches pot %.
            # Offsets calibrated from live GGPoker Rush & Cash (Mar 14 2026):
            #   33%:  ref_x - 259, ref_y - 58
            #   50%:  ref_x - 217, ref_y - 58
            #   75%:  ref_x - 175, ref_y - 58
            #   100%: ref_x - 136, ref_y - 58
            ref_x = bet_btn.screen_x_pt if bet_btn else action.screen_x_pt
            ref_y = bet_btn.screen_y_pt if bet_btn else action.screen_y_pt

            shortcut_used = False
            # Only use shortcuts postflop — preflop needs precise GTO sizing
            if not is_preflop:
                shortcut_map = {
                    0.33: (-259, -58, 'shortcut_33%'),
                    0.50: (-217, -58, 'shortcut_50%'),
                    0.75: (-175, -58, 'shortcut_75%'),
                    1.00: (-136, -58, 'shortcut_100%'),
                }
                # Check if target_amount is close to any pot-fraction shortcut
                for frac, (dx, dy, label) in shortcut_map.items():
                    shortcut_amount = pot_bb * frac
                    # Allow 15% tolerance for matching
                    if shortcut_amount > 0 and abs(bb_amount - shortcut_amount) / max(shortcut_amount, 1) < 0.15:
                        self._reliable_click(ref_x + dx, ref_y + dy, label, session=session)
                        shortcut_used = True
                        log.info(f"Using {frac:.0%} POT shortcut (target={bb_amount:.1f}BB "
                                 f"≈ {frac:.0%} pot={shortcut_amount:.1f}BB)")
                        break

            if not shortcut_used and not is_preflop:
                # Log why shortcut was NOT used (for debugging)
                log.debug(f"No shortcut match: target={bb_amount:.1f}BB pot={pot_bb:.1f}BB "
                          f"(33%={pot_bb*0.33:.1f} 50%={pot_bb*0.50:.1f} "
                          f"75%={pot_bb*0.75:.1f} 100%={pot_bb:.1f})")

            if shortcut_used:
                _time.sleep(0.2)
                # Click the raise/bet button to confirm the shortcut amount
                self._reliable_click(action.screen_x_pt, action.screen_y_pt, 'confirm_raise_shortcut', session=session)
                log.info(f"EXECUTION: Clicked {action.action_type} via shortcut for decision {decision_label}")
                # Post-click verification (wait for GGPoker animation)
                _time.sleep(0.40)
                if self._verify_button_color(action.screen_x_pt, action.screen_y_pt):
                    log.warning(f"Click may not have registered — {action.action_type} button still visible. Retrying.")
                    self._reliable_click(action.screen_x_pt - 3, action.screen_y_pt - 1, action.action_type, session=session)
                session.last_action_time = datetime.datetime.utcnow()
                cards_key = ','.join(sorted(state.my_cards)) if state.my_cards else ''
                board_count = len(state.board_cards) if state.board_cards else 0
                pot_key = round(state.pot, 1) if state.pot else 0
                actions_key = ','.join(sorted(a.action_type for a in state.available_actions)) if state.available_actions else ''
                session._last_acted_key = f"{cards_key}|{board_count}|{pot_key}|{actions_key}"
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
            self._reliable_click(input_x, input_y, 'input_field_center', session=session)
            _time.sleep(0.1)
            # Triple click to select all (standard Mac/GGSystem behavior)
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
            # Use 2 retries for all-in (critical), 1 for normal bets (speed)
            hero_stack = state.hero_stack if state.hero_stack and state.hero_stack > 0 else 100
            is_allin = (decision_label == 'Allin' or target_amount >= hero_stack * 0.9)
            max_typing_retries = 2 if is_allin else 1
            typing_success = False
            
            for t_attempt in range(max_typing_retries):
                log.info(f"Typing Attempt {t_attempt+1}/{max_typing_retries}: {amount_str} BB")
                
                # Ensure focus
                self._reliable_click(input_x, input_y, 'input_focus', session=session)
                pyautogui.hotkey('command', 'a')
                pyautogui.press('backspace')
                _time.sleep(0.2)
                
                # Type character by character with optimized cadence (30ms)
                for char in amount_str:
                    pyautogui.typewrite(char)
                    _time.sleep(0.03) 
                
                _time.sleep(0.1)
                pyautogui.press('enter')
                
                # HIGH PRESSURE SKIP
                if high_pressure:
                    typing_success = True
                    break

                _time.sleep(0.3) # Optimized wait for UI
                
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
                                # GGSystem +/- buttons are usually on the far ends of the input box
                                # (input_x - 100, input_y) for Minus, (input_x + 100, input_y) for Plus
                                btn_x = input_x + (80 if diff > 0 else -80)
                                clicks = int(abs(diff) / 0.1) # Assuming 0.1 BB per click
                                for _ in range(min(clicks, 10)):
                                    self._reliable_click(btn_x, input_y, 'fine_tune_button', session=session)
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

            # DIALOG SHIELD removed — the hardcoded (43%, 62%) position
            # hits the hero avatar, opening the profile popup.
            # _handle_bet_confirmation (called after FINAL CLICK) handles dialogs.

        # FINAL CLICK (Double-tap for reliability)
        self._reliable_click(action.screen_x_pt, action.screen_y_pt, action.action_type, session=session)

        # Only double-tap if it's a critical bet or if we are not in high pressure
        if not high_pressure or action.action_type in ('raise', 'bet', 'all_in'):
            _time.sleep(0.05)
            self._reliable_click(action.screen_x_pt + 2, action.screen_y_pt + 1, action.action_type, session=session)
        
        log.info(f"EXECUTION: Clicked {action.action_type} for decision {decision_label}")

        # --- Post-click verification (Phase 4A) ---
        # For ALL actions, check if the button is still visible after clicking.
        # If it is, the click didn't register — retry once.
        # GGPoker button animations take ~0.3-0.5s to disappear, so wait longer
        # before checking. Previous 0.15s caused constant false "click failed" logs.
        # Post-click: just wait for the animation. Color-based verification
        # was causing false "CLICK FAILED" because GGPoker button colors
        # persist during animation. Trust the Quartz click events.
        _time.sleep(0.30)
        
        # Handle confirmation dialog
        if action.action_type in ('raise', 'bet'):
            _time.sleep(0.2)
            self._handle_bet_confirmation(session)

        session.last_action_time = datetime.datetime.utcnow()
        # Track what we acted on to prevent duplicate actions on same situation
        cards_key = ','.join(sorted(state.my_cards)) if state.my_cards else ''
        board_count = len(state.board_cards) if state.board_cards else 0
        pot_key = round(state.pot, 1) if state.pot else 0
        actions_key = ','.join(sorted(a.action_type for a in state.available_actions)) if state.available_actions else ''
        session._last_acted_key = f"{cards_key}|{board_count}|{pot_key}|{actions_key}"

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
            
            # GGSystem confirmation dialogs appear in the center of the table
            cx1, cy1 = w.x * 2 + int(w.width * 0.3 * 2), w.y * 2 + int(w.height * 0.4 * 2)
            cx2, cy2 = w.x * 2 + int(w.width * 0.7 * 2), w.y * 2 + int(w.height * 0.8 * 2)
            
            img = ImageGrab.grab(bbox=(cx1, cy1, cx2, cy2))
            pix = np.array(img)
            
            # Look for the large red button (GGSystem Red: ~150, 40, 40)
            mask = (pix[:,:,0] > 140) & (pix[:,:,1] < 60) & (pix[:,:,2] < 60)
            coords = np.argwhere(mask)
            
            if coords.size > 500: # Threshold to ensure it's a button, not just a few pixels
                center_y, center_x = coords.mean(axis=0)
                # Convert back to points: (pixel_start + offset) / 2
                click_x = (cx1 + center_x) / 2
                click_y = (cy1 + center_y) / 2
                
                log.info(f"AUTONOMOUS: Detected 'Are you sure?' dialog. Clicking RED BET BUTTON at ({click_x:.1f}, {click_y:.1f})")

                # Small random offset for human-like click (reduced from ±5 to ±2)
                import random
                final_x = click_x + random.randint(-2, 2)
                final_y = click_y + random.randint(-2, 2)
                # Avatar zone guard
                if self._is_avatar_zone(final_x, final_y, session):
                    log.warning(f"AVATAR GUARD: Bet confirmation at ({final_x:.1f}, {final_y:.1f}) "
                                f"overlaps avatar zone — using exact center instead")
                    final_x, final_y = click_x, click_y
                pyautogui.click(final_x, final_y)
                _time.sleep(0.3)
                # One more click just in case
                final_x2 = click_x + random.randint(-2, 2)
                final_y2 = click_y + random.randint(-2, 2)
                if self._is_avatar_zone(final_x2, final_y2, session):
                    final_x2, final_y2 = click_x, click_y
                pyautogui.click(final_x2, final_y2)
                return True
            return False
        except Exception as e:
            log.debug(f"Bet confirmation check failed: {e}")
        return False

    def _close_popups(self, session: TableSession):
        """Detect and close any popup windows (Smart HUD, player profiles, etc.).

        GGPoker opens a popup when you click a player avatar showing VPIP/PFR
        stats. These popups block the table view and must be closed by clicking
        the X button in their top-right corner, or by finding and closing the
        popup window via AppleScript.
        """
        try:
            # Method 1: Close any non-table GGPoker windows via AppleScript
            # The Smart HUD popup is a separate window with the player's name
            script = '''tell application "System Events"
                tell process "GGnet"
                    set popupsClosed to 0
                    repeat with w in windows
                        set winName to name of w as text
                        -- Close windows that are NOT the main table or lobby
                        if winName does not contain "Rush" and winName does not contain "Cash" and winName does not contain "Spin" and winName does not contain "Gold" and winName does not contain "GGPoker" and winName does not contain "Hold" and winName does not contain "Blinds" and winName does not contain "Masters" and winName does not contain "NL" and winName does not contain "Cashier" then
                            -- This is likely a popup (player profile, Smart HUD, etc.)
                            click (first button of w whose subrole is "AXCloseButton")
                            set popupsClosed to popupsClosed + 1
                        end if
                    end repeat
                    return popupsClosed
                end tell
            end tell'''
            result = subprocess.run(['osascript', '-e', script],
                                    capture_output=True, text=True, timeout=3)
            closed = result.stdout.strip()
            if closed and closed != '0':
                log.info(f"POPUP: Closed {closed} popup window(s)")
        except Exception as e:
            # Fallback: try clicking top-right X of any overlay
            try:
                import pyautogui
                w = session.window
                # Smart HUD popup X button is typically at top-right of a popup
                # that overlaps the table. Try clicking a likely X position.
                # The popup is roughly centered on the clicked player.
                # Just press Escape which closes most GGPoker popups.
                pyautogui.press('escape')
                log.debug(f"POPUP: Pressed Escape to close popup ({e})")
            except Exception:
                pass

    def _maybe_auto_adjust(self):
        """Autonomous feedback loop: reload/retune strategy adjustments."""
        hands = self.stats['hands_played']

        # Reload cached adjustments every N hands
        if hands - self._last_adj_reload >= self._adj_reload_interval:
            self._last_adj_reload = hands
            try:
                from sys_core.decisionmaker.decisionmaker import _strategy_adj
                import sys_core.decisionmaker.decisionmaker as dm_module
                dm_module._strategy_adj = None  # Force reload on next _get_adj()
                log.info(f"AUTO-ADJUST: Reloaded strategy adjustments (hand #{hands})")
            except Exception as e:
                log.debug(f"AUTO-ADJUST reload failed: {e}")

        # Auto-run strategy adjuster every M hands
        if hands - self._last_adj_retune >= self._adj_retune_interval:
            self._last_adj_retune = hands
            try:
                from sys_core.tools.strategy_adjuster import load_adjustments, analyze_and_adjust, save_adjustments, HAND_HISTORY_PATH
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
                    import sys_core.decisionmaker.decisionmaker as dm_module
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
            # Reset hand context for new hand
            session._hand_context = None
            session._hand_context_last_street = ""

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
                from sys_core.decisionmaker.range_equity import (
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

    def _update_hand_context(self, session: TableSession, state, t):
        """Build and update the HandContext for the current hand.

        Called each time we detect it's our turn.  Infers villain actions
        from the game state and records them into session._hand_context.
        Hero actions are recorded separately after we make our decision.
        """
        try:
            if not PYTHON_OCR_AVAILABLE:
                return

            # Create new hand context if needed (new hand or first call)
            if session._hand_context is None:
                session._hand_context = HandContext()
                session._hand_context_last_street = ""

            ctx = session._hand_context

            # --- Populate preflop context ---
            _raiser_utg = getattr(t, 'first_raiser_utg', float('nan'))
            _utg_to_pos = {0: 'UTG', 1: 'MP', 2: 'CO', 3: 'BTN', 4: 'SB', 5: 'BB'}
            has_raiser = not np.isnan(_raiser_utg) if isinstance(_raiser_utg, float) else True

            hero_pos = getattr(t, '_gto_position', getattr(state, 'position', 'CO'))
            curr_board = getattr(state, 'board_cards', []) or []
            is_preflop = not curr_board
            opp_has_init = getattr(t, 'other_player_has_initiative', False)
            call_val = getattr(t, 'currentCallValue', 0) or 0
            pot_val = getattr(t, 'totalPotValue', 0) or 0

            # Determine current street name
            if is_preflop:
                street_name = 'preflop'
            elif len(curr_board) == 3:
                street_name = 'flop'
            elif len(curr_board) == 4:
                street_name = 'turn'
            else:
                street_name = 'river'

            # Set preflop raiser info (once per hand)
            if not ctx.preflop_raiser_position and has_raiser:
                ctx.preflop_raiser_seat = int(_raiser_utg) if not np.isnan(_raiser_utg) else -1
                ctx.preflop_raiser_position = _utg_to_pos.get(
                    int(_raiser_utg), 'CO') if not np.isnan(_raiser_utg) else ''

            # Detect if hero raised preflop (when we see postflop for the first time)
            if is_preflop and state.is_my_turn:
                # If we're facing a raise, hero hasn't acted yet.
                # If call_val > 1.0 BB, someone raised and we're deciding
                if call_val > 1.1 and hero_pos not in ('BB',):
                    pass  # We haven't acted yet
                elif call_val <= 0.1 and has_raiser:
                    # No call amount but raiser detected = we might be the raiser
                    # This is ambiguous; will be set after hero decision
                    pass

            # Number of active opponents
            n_opp = getattr(t, 'other_active_players', 1)
            if not ctx.is_multiway and n_opp >= 2:
                ctx.is_multiway = True
                ctx.num_players_to_flop = n_opp + 1

            # Record preflop pot going to flop
            if street_name == 'flop' and ctx.preflop_pot_bb == 0:
                ctx.preflop_pot_bb = pot_val
                ctx.num_players_to_flop = max(n_opp + 1, ctx.num_players_to_flop)

            # --- Record villain action on current street (deduplicated) ---
            if session._hand_context_last_street != street_name:
                if opp_has_init and street_name != 'preflop':
                    # Villain bet into us on this street
                    v_action = 'bet'
                    # Check if this is a raise (we already bet this street)
                    hero_street_actions = ctx.hero_actions.get(street_name, [])
                    if any(a in ('bet', 'raise') for a in hero_street_actions):
                        v_action = 'raise'
                    ctx.record_action(street_name, 'villain', v_action,
                                      amount=call_val, pot_after=pot_val)
                elif opp_has_init and street_name == 'preflop' and has_raiser:
                    # Villain raised preflop
                    if call_val > 5:
                        v_action = '3bet'
                    else:
                        v_action = 'raise'
                    ctx.record_action('preflop', 'villain', v_action,
                                      amount=call_val, pot_after=pot_val)
                elif not opp_has_init and street_name != 'preflop':
                    # No initiative = villain checked (or we're first to act)
                    # Only record check if villain had the opportunity (they acted before us)
                    has_check_btn = getattr(t, 'checkButton', False)
                    if has_check_btn:
                        # We have check available = nobody bet before us
                        # If villain was supposed to act first (e.g. we have position),
                        # they checked to us
                        if hero_pos in ('BTN', 'CO', 'SB') or (hero_pos == 'BB' and len(curr_board) > 0):
                            # Heuristic: in position means villain checked to us
                            ctx.record_action(street_name, 'villain', 'check',
                                              amount=0, pot_after=pot_val)

                session._hand_context_last_street = street_name

            # Attach context to state for downstream consumption
            if hasattr(state, 'hand_context'):
                state.hand_context = ctx

            log.debug(f"HAND_CTX: street={street_name} pattern='{ctx.villain_pattern}' "
                      f"aggro_streets={ctx.streets_of_aggression} "
                      f"hero_init={ctx.hero_has_initiative} v_init={ctx.villain_has_initiative} "
                      f"pf_raiser={ctx.preflop_raiser_position} cbet={ctx.is_cbet_spot}")

        except Exception as e:
            log.debug(f"Hand context update failed: {e}")

    def _record_hero_action_in_context(self, session: TableSession, decision_str: str,
                                        street: str, amount: float = 0, pot: float = 0):
        """Record hero's decision into the hand context after it's made."""
        try:
            ctx = session._hand_context
            if ctx is None:
                return

            # Map decision to action type
            dec_lower = decision_str.lower() if decision_str else ''
            if 'fold' in dec_lower:
                action = 'fold'
            elif 'call' in dec_lower or 'check' in dec_lower:
                if amount <= 0:
                    action = 'check'
                else:
                    action = 'call'
            elif 'bet' in dec_lower or 'raise' in dec_lower or 'allin' in dec_lower:
                action = 'bet'
            else:
                return  # Unknown action, skip

            ctx.record_action(street, 'hero', action, amount=amount, pot_after=pot)

            # Update hero_was_raiser / hero_was_caller
            _street_map = {'PreFlop': 'preflop', 'Flop': 'flop', 'Turn': 'turn', 'River': 'river'}
            norm_street = _street_map.get(street, street.lower())
            if norm_street == 'preflop':
                if action == 'bet':
                    ctx.hero_was_raiser = True
                elif action == 'call':
                    ctx.hero_was_caller = True

        except Exception as e:
            log.debug(f"Record hero action failed: {e}")

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
        GGSystem shows a popup with Share / Play Again / Close buttons.
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
        """Detect and handle the GGSystem 'Add Chips' rebuy dialog.

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
                    from sys_core.ocr.card_reader import CardReader
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
        from sys_core.decisionmaker.range_equity import compute_bet_size_bb, preflop_raise_size_bb

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

    def _save_hand_snapshot(self, session, state, decision_label, equity, abs_equity,
                            decision_obj=None):
        """Save an annotated screenshot + JSON sidecar for every decision.

        Draws EVERYTHING OCR read onto the screenshot so you can visually
        cross-reference detection vs reality:
        - Hero cards, board cards
        - All player stacks (in BB) at their seat positions
        - Pot size, call amount, min raise
        - Blinds, hero BB stack
        - Equity, EV, decision
        - Position, street, dealer button seat
        - Detected button locations
        - Opponents in hand count
        """
        import json as _json
        from PIL import Image
        snap_dir = os.path.join('data', 'learning', 'hand_snapshots')
        os.makedirs(snap_dir, exist_ok=True)

        # Limit folder size: keep at most 500 snapshots (delete oldest)
        try:
            existing = sorted(f for f in os.listdir(snap_dir) if f.endswith('.png'))
            if len(existing) > 500:
                for old in existing[:len(existing) - 500]:
                    try:
                        os.remove(os.path.join(snap_dir, old))
                        json_old = old.replace('.png', '.json')
                        try:
                            os.remove(os.path.join(snap_dir, json_old))
                        except FileNotFoundError:
                            pass
                    except OSError:
                        pass
        except OSError:
            pass

        # Build filename
        ts = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        cards_str = '_'.join(state.my_cards) if state.my_cards else 'XX_XX'
        dec_str = str(decision_label).split('.')[-1] if decision_label else 'none'
        base_name = f"{ts}_{cards_str}_{dec_str}"

        # Capture the table screenshot
        screenshot = self.get_table_screenshot(session.window)
        img = np.array(screenshot).copy()
        h_img, w_img = img.shape[:2]

        font = cv2.FONT_HERSHEY_SIMPLEX
        white = (255, 255, 255)
        green = (0, 255, 0)
        yellow = (0, 255, 255)
        orange = (0, 165, 255)
        red = (0, 0, 255)
        cyan = (255, 255, 0)
        gray = (180, 180, 180)

        # --- Semi-transparent info panel at top ---
        panel_h = 170
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (w_img, panel_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.65, img, 0.35, 0, img)

        y = 20  # current text y position
        line_h = 22  # line height

        # Row 1: Hero cards + Board
        cards_text = ' '.join(state.my_cards) if state.my_cards else '?? ??'
        board_text = ' '.join(state.board_cards) if state.board_cards else '--'
        cv2.putText(img, f"HERO: {cards_text}", (10, y), font, 0.65, green, 2)
        cv2.putText(img, f"BOARD: {board_text}", (250, y), font, 0.65, yellow, 2)
        y += line_h

        # Row 2: Pot, Call, Min Raise
        pot = state.pot or 0
        call_amt = state.call_amount or 0
        min_raise = getattr(state, 'min_raise_amount', 0) or 0
        cv2.putText(img, f"Pot: {pot:.1f} BB", (10, y), font, 0.6, white, 2)
        cv2.putText(img, f"Call: {call_amt:.1f} BB", (180, y), font, 0.6,
                    red if call_amt > 0 else green, 2)
        if min_raise > 0:
            cv2.putText(img, f"MinRaise: {min_raise:.1f} BB", (350, y), font, 0.6, orange, 2)
        y += line_h

        # Row 3: Hero stack, Blinds
        hero_stack = getattr(state, 'hero_stack', 0) or 0
        sb = getattr(state, 'small_blind', 0) or 0
        bb = getattr(state, 'big_blind', 0) or 0
        estimated = getattr(state, 'hero_stack_is_estimated', False)
        stack_flag = ' (est!)' if estimated else ''
        cv2.putText(img, f"Hero Stack: {hero_stack:.1f} BB{stack_flag}", (10, y), font, 0.6, white, 2)
        if bb > 0:
            cv2.putText(img, f"Blinds: {sb}/{bb}", (350, y), font, 0.6, gray, 2)
        y += line_h

        # Row 4: Equity, EV, Decision
        ev = getattr(decision_obj, 'decision_ev', 0) if decision_obj else 0
        ev_str = f"+{ev:.2f}" if ev > 0 else f"{ev:.2f}"
        dec_color = green if 'raise' in dec_str.lower() or 'bet' in dec_str.lower() else \
                    yellow if 'call' in dec_str.lower() or 'check' in dec_str.lower() else red
        cv2.putText(img, f"Eq: {equity:.1%}  AbsEq: {abs_equity:.1%}", (10, y), font, 0.6, cyan, 2)
        cv2.putText(img, f"EV: {ev_str} BB", (350, y), font, 0.6,
                    green if ev > 0 else red, 2)
        y += line_h

        # Row 5: Position, Street, Dealer, Opponents, Decision
        pos = getattr(state, 'position', '?')
        stage = getattr(state, 'game_stage', '?')
        dealer = getattr(state, 'dealer_seat', '?')
        opps = getattr(state, 'other_active_players', '?')
        opps_in = getattr(state, 'opponents_in_hand', -1)
        opps_str = f"Opps: {opps}"
        if opps_in >= 0:
            opps_str += f" (in hand: {opps_in})"
        cv2.putText(img, f"Pos: {pos}  Street: {stage}  Dealer: Seat {dealer}",
                    (10, y), font, 0.55, gray, 1)
        cv2.putText(img, opps_str, (450, y), font, 0.55, gray, 1)
        y += line_h

        # Row 6: Call/Bet limits from strategy
        if decision_obj:
            cl = getattr(decision_obj, 'finalCallLimit', 0)
            bl = getattr(decision_obj, 'finalBetLimit', 0)
            cv2.putText(img, f"CallLimit: {cl:.1%}  BetLimit: {bl:.1%}", (10, y),
                        font, 0.5, gray, 1)

        # Row 7: DECISION in large text
        cv2.putText(img, f"=> {dec_str.upper()}", (w_img - 250, 35), font, 0.9, dec_color, 3)

        # --- Player stacks around the table ---
        # 6-max seat layout (approximate % positions on table image)
        # Seat 0 = hero (bottom center), seats go clockwise
        seat_positions = {
            0: (0.50, 0.88),  # Hero - bottom center
            1: (0.15, 0.70),  # Left bottom
            2: (0.10, 0.35),  # Left top
            3: (0.40, 0.22),  # Top left
            4: (0.70, 0.22),  # Top right  (was 0.60)
            5: (0.88, 0.35),  # Right top
        }
        # Additional position for 6th opponent if present
        # seat 6 wraps or seat 5 might be right-bottom
        # Adjust if 3-max: only seats 0, 3, (and maybe 1)

        players = getattr(state, 'players', []) or []
        for p in players:
            seat = getattr(p, 'seat', -1)
            stack = getattr(p, 'stack', 0) or 0
            bet = getattr(p, 'current_bet', 0) or 0
            is_hero = getattr(p, 'is_hero', False)
            is_active = getattr(p, 'is_active', True)
            name = getattr(p, 'name', '')

            if seat in seat_positions:
                sx, sy = seat_positions[seat]
                px = int(sx * w_img)
                py = int(sy * h_img)

                # Background box
                box_w, box_h = 140, 45
                bx1 = max(0, px - box_w // 2)
                by1 = max(0, py - 5)
                bx2 = min(w_img, bx1 + box_w)
                by2 = min(h_img, by1 + box_h)
                overlay2 = img.copy()
                border_color = green if is_hero else (cyan if is_active else (100, 100, 100))
                cv2.rectangle(overlay2, (bx1, by1), (bx2, by2), (0, 0, 0), -1)
                cv2.addWeighted(overlay2, 0.6, img, 0.4, 0, img)
                cv2.rectangle(img, (bx1, by1), (bx2, by2), border_color, 2)

                # Stack text
                label = "HERO" if is_hero else (name[:8] if name else f"S{seat}")
                cv2.putText(img, f"{label}: {stack:.1f}", (bx1 + 4, by1 + 18),
                            font, 0.45, white, 1)
                # Current bet
                if bet > 0:
                    cv2.putText(img, f"Bet: {bet:.1f}", (bx1 + 4, by1 + 36),
                                font, 0.4, orange, 1)
                elif is_hero:
                    cv2.putText(img, f"({stack:.0f} BB)", (bx1 + 4, by1 + 36),
                                font, 0.4, gray, 1)

        # --- Draw detected button locations ---
        if state.available_actions:
            for act in state.available_actions:
                ax = getattr(act, 'rel_x', None)
                ay = getattr(act, 'rel_y', None)
                atype = getattr(act, 'action_type', '?')
                amt = getattr(act, 'amount', None)
                conf = getattr(act, 'confidence', 0)
                if ax is not None and ay is not None:
                    bpx = int(ax * w_img)
                    bpy = int(ay * h_img)
                    btn_color = green if 'call' in atype or 'check' in atype else \
                                orange if 'raise' in atype or 'bet' in atype else \
                                red if 'fold' in atype else gray
                    cv2.circle(img, (bpx, bpy), 10, btn_color, -1)
                    cv2.circle(img, (bpx, bpy), 10, white, 1)
                    amt_str = f" {amt:.1f}" if amt else ''
                    cv2.putText(img, f"{atype}{amt_str} ({conf:.0%})",
                                (bpx + 14, bpy + 5), font, 0.45, btn_color, 1)

        # Save annotated screenshot
        annotated = Image.fromarray(img)
        annotated.save(os.path.join(snap_dir, f"{base_name}.png"), optimize=True)

        # --- Save JSON sidecar with EVERYTHING ---
        sidecar = {
            'ts': datetime.datetime.utcnow().isoformat(),
            'window': state.window_name if hasattr(state, 'window_name') else session.window.name,
            # Cards
            'hero_cards': state.my_cards,
            'board_cards': state.board_cards,
            'cards_face_down': getattr(state, 'cards_face_down', False),
            # Street & Position
            'street': stage,
            'position': pos,
            'dealer_seat': dealer,
            'opponents_active': opps,
            'opponents_in_hand': opps_in,
            # Money (all in BB)
            'pot': round(pot, 2),
            'call_amount': round(call_amt, 2),
            'min_raise': round(min_raise, 2),
            'hero_stack': round(hero_stack, 2),
            'hero_stack_estimated': estimated,
            'small_blind': sb,
            'big_blind': bb,
            # All players
            'players': [],
            # Buttons detected
            'buttons': [],
            # Strategy
            'equity': round(equity, 4),
            'abs_equity': round(abs_equity, 4),
            'decision': str(decision_label),
        }

        # All player details
        for p in players:
            sidecar['players'].append({
                'seat': getattr(p, 'seat', -1),
                'name': getattr(p, 'name', ''),
                'stack': round(getattr(p, 'stack', 0) or 0, 2),
                'bet': round(getattr(p, 'current_bet', 0) or 0, 2),
                'is_hero': getattr(p, 'is_hero', False),
                'is_active': getattr(p, 'is_active', True),
            })

        # All button details
        for act in (state.available_actions or []):
            sidecar['buttons'].append({
                'type': getattr(act, 'action_type', '?'),
                'amount': round(getattr(act, 'amount', 0) or 0, 2),
                'rel_x': round(getattr(act, 'rel_x', 0) or 0, 4),
                'rel_y': round(getattr(act, 'rel_y', 0) or 0, 4),
                'confidence': round(getattr(act, 'confidence', 0) or 0, 3),
            })

        # Decision details
        if decision_obj:
            sidecar['ev'] = round(getattr(decision_obj, 'decision_ev', 0), 3)
            sidecar['call_limit'] = round(getattr(decision_obj, 'finalCallLimit', 0), 3)
            sidecar['bet_limit'] = round(getattr(decision_obj, 'finalBetLimit', 0), 3)
            sidecar['outs'] = getattr(decision_obj, 'outs', 0)
            blockers = getattr(decision_obj, 'blockers_info', {})
            if blockers:
                sidecar['blocker_score'] = round(blockers.get('blocker_score', 0), 2)
            opp_range = getattr(decision_obj, 'opponent_range_estimate', {})
            if opp_range:
                sidecar['opp_likely'] = opp_range.get('likely_hands', [])[:3]
                sidecar['opp_bluff_pct'] = round(opp_range.get('bluff_probability', 0), 2)
            opp_prof = getattr(decision_obj, '_opp_profile', None)
            if opp_prof and opp_prof.get('type', 'unknown') != 'unknown':
                sidecar['opp_type'] = opp_prof['type']

        # OCR diagnostics
        sidecar['ocr_latency_ms'] = round(getattr(state, 'ocr_latency_ms', 0), 1)
        sidecar['ocr_source'] = getattr(state, 'ocr_source', '?')

        with open(os.path.join(snap_dir, f"{base_name}.json"), 'w') as f:
            _json.dump(sidecar, f, indent=2)

        log.debug(f"Hand snapshot saved: {base_name}")

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
            # PRIMARY: Use OCR-based colored card detection (reliable on GGPoker).
            # MongoDB template matching (get_table_cards2) uses hardcoded regions
            # that don't match the current table layout, so it misses cards constantly.
            table_cards = []
            try:
                from sys_core.ocr.table_reader import _detect_board_cards
                img = np.array(screenshot)
                if img.ndim == 3 and img.shape[2] == 4:
                    img = img[:, :, :3]
                H_img, W_img = img.shape[:2]
                table_cards = _detect_board_cards(img, W_img, H_img) or []
                if table_cards:
                    log.info(f"Board cards detected: {table_cards}")
            except Exception as e:
                log.debug(f"OCR board detection failed: {e}")

            # FALLBACK: Try old template matching if OCR found nothing
            if not table_cards:
                t.get_table_cards2()
                table_cards = getattr(t, 'cardsOnTable', None) or getattr(t, 'table_cards', None) or []

            t.cardsOnTable = table_cards
            t.table_cards = table_cards

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

            # Always set _table_name so ICM/tournament detection works
            t._table_name = getattr(session.window, 'name', '') if session.window else ''

            # === MONTE CARLO EQUITY CALCULATION ===
            # Set mycards alias (montecarlo uses mycards, we use my_cards)
            t.mycards = t.my_cards
            t.cardsOnTable = getattr(t, 'cardsOnTable', []) or []
            t.mt_tm = time.time()  # Set monte carlo timer start
            config = get_config()
            # Use module-level MockSignalsMC for montecarlo (it expects signal_status.emit())
            mock_signals = MockSignalsMC()

            # --- SMART RANGE ESTIMATION (Phase 2 Unification) ---
            smart_range = None
            try:
                from sys_core.decisionmaker.range_equity import get_range_equity
                re = get_range_equity()
                opp_profile = getattr(session, '_opp_profile', None) or {}
                ptype = opp_profile.get('type', 'unknown') if opp_profile.get('hands', 0) >= 10 else 'unknown'

                # Villain action estimation
                v_action = 'check'
                if t.allInCallButton: v_action = 'all_in'
                elif t.minCall > 0:
                    if getattr(t, 'first_raiser', False): v_action = '3bet'
                    else: v_action = 'open' if t.gameStage == 'PreFlop' else 'bet'
                
                # Villain position estimation
                _utg_to_pos = {0: 'UTG', 1: 'MP', 2: 'CO', 3: 'BTN', 4: 'SB', 5: 'BB'}
                _hero_pos = getattr(t, '_gto_position', 'CO')
                _raiser_utg = getattr(t, 'first_raiser_utg', float('nan'))
                import math as _math
                if not _math.isnan(_raiser_utg):
                    v_position = _utg_to_pos.get(int(_raiser_utg), 'CO')
                else:
                    v_position = 'BTN' if _hero_pos in ('BB', 'SB') else 'CO'

                smart_range = re.estimate_villain_range_str(
                    position=v_position,
                    action=v_action,
                    player_type=ptype,
                    street=t.gameStage.lower() if t.gameStage != 'PreFlop' else 'preflop'
                )
                log.info(f"UNIFIED RANGE: {v_position} {v_action} ({ptype}) -> {smart_range[:50]}...")
            except Exception as e:
                log.debug(f"Smart range estimation failed: {e}")

            m = run_montecarlo_wrapper(
                p, mock_signals, config, None, t,
                session.game_logger, session.preflop_state, h,
                smart_range=smart_range
            )

            # === DECISION MAKING ===
            # Deep CFR mode: use neural network, fall back to EV on failure
            _used_deepcfr = False
            if self.strategy_mode == 'deepcfr' and DEEPCFR_AVAILABLE:
                try:
                    cfr_result = deepcfr_decision(t, h, p)
                    if cfr_result and cfr_result.get('decision'):
                        # Create a Decision object with the Deep CFR result
                        d = Decision(t, h, p, session.game_logger)
                        d.decision = cfr_result['decision']
                        d._deepcfr_probs = cfr_result.get('probs', {})
                        d._deepcfr_confidence = cfr_result.get('confidence', 0)
                        d._deepcfr_inference_ms = cfr_result.get('inference_ms', 0)
                        log.info(f"DEEP CFR decision: {d.decision} "
                                 f"(conf={d._deepcfr_confidence:.0%}, "
                                 f"{d._deepcfr_inference_ms:.1f}ms)")
                        _used_deepcfr = True
                except Exception as e:
                    log.warning(f"Deep CFR failed, falling back to EV: {e}")

            if not _used_deepcfr:
                # EV engine (original decision path)
                d = Decision(t, h, p, session.game_logger)

                # Multi-street planning: pass previous street info to decision
                d._we_bet_prev_street = getattr(session, '_we_bet_last_street', False)
                d._prev_street_equity = getattr(session, '_last_equity', None)

                # Pass Bayesian villain range from runner → DecisionMaker
                if session._bayesian_villain_range is not None:
                    d._bayesian_villain_range = session._bayesian_villain_range

                # Hand context: full action history for context-aware ranges
                d._hand_context = session._hand_context

                d.make_decision(t, h, p, session.game_logger)

            # Track our action for multi-street planning
            dec_str = str(d.decision).lower() if d.decision else ''
            session._we_bet_last_street = ('bet' in dec_str or 'raise' in dec_str)
            session._last_equity = t.equity

            # Record hero action in hand context
            self._record_hero_action_in_context(
                session, dec_str, t.gameStage,
                amount=getattr(t, 'currentCallValue', 0) or 0,
                pot=getattr(t, 'totalPotValue', 0) or 0,
            )

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

            # FALLBACK: check if free, fold otherwise (better than timeout)
            self._fallback_action(session)

            # DON'T CRASH - return False and continue
            return False

    def _fallback_action(self, session: TableSession):
        """Shared fallback: check if free, fold otherwise.

        Used by both process_table (pipeline 2) and process_table_new_ocr
        (pipeline 1) when the decision pipeline crashes.
        """
        try:
            t = session._table
            if t is not None:
                if t.has_check_button():
                    log.warning("FALLBACK: Decision crashed, checking (free)")
                    if session._mouse is None:
                        session._mouse = MouseMoverTableBased(session.table_dict)
                    tlc = (session.window.x, session.window.y)
                    session._mouse.mouse_action("Check", tlc)
                elif t.has_call_button():
                    log.warning("FALLBACK: Decision crashed, folding")
                    self._click_fold(session)
        except Exception as fallback_err:
            log.error(f"Fallback action also failed: {fallback_err}")

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
        # user's other windows and causes the GGSystem window to flash/minimize
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
        self._click_lock = threading.Lock()
        self._last_activated_window = None

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
            from sys_core.decisionmaker.range_equity import build_preflop_equity_table, build_push_fold_table
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

                # 1. Find all poker windows (cached — only refresh every 3s)
                # Window detection via Quartz takes ~2s. Caching avoids this
                # on every loop, letting the bot poll table state much faster.
                now_t = time.time()
                if not hasattr(self, '_cached_windows') or now_t - getattr(self, '_windows_cache_time', 0) > 3.0:
                    try:
                        windows = self.find_poker_windows()
                        self._cached_windows = windows
                        self._windows_cache_time = now_t
                        current_window_ids = {w.window_id for w in windows}
                    except Exception as e:
                        log.error(f"Window detection failed: {e}")
                        time.sleep(2)
                        continue
                    log.debug(f"Found {len(windows)} poker tables")
                else:
                    windows = self._cached_windows
                    current_window_ids = {w.window_id for w in windows}

                # 2. Update sessions - remove closed, add new (thread-safe)
                try:
                    with self._session_lock:
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

                # 4. Process ALL urgent tables in PARALLEL
                # Decision computation (OCR + Monte Carlo) runs concurrently;
                # the actual click step is serialized via _click_lock.
                urgent_tables = [s for s in self.sessions.values()
                                if s.state == TableState.NEED_ACTION]

                if urgent_tables:
                    # Sort by priority (highest first)
                    urgent_tables.sort(key=lambda s: s.priority, reverse=True)

                    def _process_one(session):
                        if PYTHON_OCR_AVAILABLE or self.rust_ocr is not None:
                            return self.process_table_new_ocr(session)
                        else:
                            return self.process_table(session)

                    max_workers = min(len(urgent_tables), 4)
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = {
                            executor.submit(_process_one, ut): ut
                            for ut in urgent_tables
                        }
                        for future in as_completed(futures):
                            table = futures[future]
                            try:
                                success = future.result()
                                if success:
                                    self.actions_count += 1
                            except Exception as e:
                                log.error(f"Process failed for {table.window.name}: {e}")
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

                # Adaptive sleep: faster polling when tables need action
                if any(s.state == TableState.NEED_ACTION for s in self.sessions.values()):
                    time.sleep(0.01)  # 10ms when action needed
                elif any(s.state == TableState.WAITING for s in self.sessions.values()):
                    time.sleep(0.03)  # 30ms when tables active
                else:
                    time.sleep(0.10)  # 100ms when idle

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
        python -m sys_core.engine --replay data/learning/screenshots/some_hand.png
        python -m sys_core.engine --replay data/learning/screenshots/  # all PNGs in dir
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
        from sys_core.decisionmaker.range_equity import build_preflop_equity_table, build_push_fold_table
        build_preflop_equity_table()
        build_push_fold_table()
        log.info("Preflop equity + push/fold tables built")
    except Exception as e:
        log.warning(f"Preflop equity table failed: {e}")

    # Try to load preflop sheet
    preflop_sheet = None
    try:
        from sys_core.tools.update_checker import UpdateChecker
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

    parser = argparse.ArgumentParser(description='Multi-Table System Utility Runner')
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
    parser.add_argument('--strategy', type=str, default='ev', choices=['ev', 'deepcfr'],
                       help='Decision engine: "ev" (default EV engine) or "deepcfr" (neural network)')
    args = parser.parse_args()

    # Screenshot replay mode — process a single image and exit
    if args.replay:
        init_logger(screenlevel=logging.INFO, filename='replay', logdir='log')
        _run_replay(args.replay)
        return

    # Initialize logging
    init_logger(screenlevel=logging.INFO, filename='multi_table', logdir='log')

    mode_str = " [DRY-RUN — NO CLICKS]" if args.dry_run else ""
    strategy_str = f" [STRATEGY: {args.strategy.upper()}]"
    log.info("=" * 60)
    log.info(f"MULTI-TABLE RUNNER{mode_str}{strategy_str}")
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
        strategy_mode=args.strategy,
    )

    try:
        runner.run(standardize_on_startup=not args.no_standardize)
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        runner.stop()


if __name__ == '__main__':
    main()
