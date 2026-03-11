"""
UNIFIED CONSTANTS - Single Source of Truth for All Detection Parameters

This file contains ALL constants used across the codebase. Previously these
were scattered across 15+ files with slightly different values, causing
detection failures.

IMPORTANT: If you need to change a threshold, change it HERE, not in
individual bot files.
"""

import numpy as np

# =============================================================================
# DISPLAY CONSTANTS
# =============================================================================

# Retina display scaling factor (macOS)
# Screenshots are in PIXELS (2x), mouse clicks are in POINTS (1x)
RETINA_SCALE = 2

# =============================================================================
# BUTTON DETECTION - HSV COLOR RANGES
# =============================================================================

# These are the UNIFIED HSV ranges that work for GGPoker
# Format: {'lower': [H, S, V], 'upper': [H, S, V]}
#
# Previous problem: Different files used different ranges:
#   - auto_player.py used [35, 80, 80] for green
#   - ultimate_bot.py used [25, 40, 40] for green
#   - vision_analyzer.py used [25, 40, 40] for green
# This caused some bots to find buttons while others couldn't.

HSV_RANGES = {
    'call': {
        'lower': np.array([35, 50, 50]),    # Green - Call/Check buttons
        'upper': np.array([85, 255, 255]),
        'color_name': 'green',
        'button_types': ['Call', 'Check', 'call', 'check'],
    },
    'raise': {
        'lower': np.array([8, 80, 80]),     # Orange - Raise/Bet buttons
        'upper': np.array([25, 255, 255]),
        'color_name': 'orange',
        'button_types': ['Raise', 'Bet', 'raise', 'bet', 'All-In', 'all-in'],
    },
    'fold': {
        'lower': np.array([0, 0, 30]),      # Gray - Fold button
        'upper': np.array([180, 60, 120]),
        'color_name': 'gray',
        'button_types': ['Fold', 'fold'],
    },
    'deal_me_in': {
        'lower': np.array([0, 100, 100]),   # Red - Deal Me In / I'm Back
        'upper': np.array([15, 255, 255]),
        'color_name': 'red',
        'button_types': ['Deal Me In', 'I\'m Back', 'deal', 'back'],
    },
}

# Button text keywords for OCR detection
BUTTON_KEYWORDS = {
    'call': ['call', 'check'],
    'raise': ['raise', 'bet', 'all-in', 'allin'],
    'fold': ['fold'],
    'deal_me_in': ['deal', 'back', 'sit'],
}

# =============================================================================
# CARD DETECTION THRESHOLDS
# =============================================================================

# White pixel threshold for detecting face-up cards
# Cards are white rectangles on green felt
# Lower = more lenient (finds darker cards), Higher = stricter
CARD_WHITE_THRESHOLD_DEFAULT = 180
CARD_WHITE_THRESHOLD_MIN = 100
CARD_WHITE_THRESHOLD_MAX = 220

# Card region search area (percentage of table height/width)
CARD_REGION_Y_START = 0.55  # Start looking for cards at 55% down
CARD_REGION_Y_END = 0.90    # Stop looking at 90% down
CARD_REGION_X_START = 0.20  # Start at 20% from left
CARD_REGION_X_END = 0.80    # End at 80% from left

# Card size constraints (in pixels)
CARD_MIN_AREA = 1500
CARD_MAX_AREA = 50000
CARD_ASPECT_RATIO_MIN = 0.5  # width/height ratio
CARD_ASPECT_RATIO_MAX = 0.9

# Template matching threshold (lower = stricter match required)
TEMPLATE_MATCH_THRESHOLD = 0.35

# =============================================================================
# BUTTON DETECTION THRESHOLDS
# =============================================================================

# Button search region (percentage of table height)
BUTTON_REGION_Y_START = 0.60  # Buttons are in bottom 40%

# Button size constraints
BUTTON_MIN_AREA = 1500
BUTTON_MAX_AREA = 100000
BUTTON_MIN_WIDTH = 50
BUTTON_MIN_HEIGHT = 25

# =============================================================================
# WINDOW DETECTION
# =============================================================================

# GGPoker process name on macOS
GGPOKER_PROCESS_NAME = "GGnet"

# Keywords that identify a poker TABLE window (vs lobby)
# Window names like "Spin & Gold $0.25 - Blinds 15 | 30"
POKER_TABLE_KEYWORDS = [
    'Blinds',      # Active tables always show blinds
    'Spin',        # Spin & Gold
    'Gold',
    'Rush',        # Rush & Cash
    'Cash',
    'Hold',        # Hold'em
    'Omaha',
    'NL',          # No Limit
    'PLO',         # Pot Limit Omaha
    'Jackpot',
]

# Keywords that indicate NOT a poker table
POKER_TABLE_EXCLUDE = [
    'Highlight',   # Prize multiplier popup (not a table!)
    'Cashier',
    'Settings',
    'Options',
]

# =============================================================================
# TIMING CONSTANTS
# =============================================================================

# Minimum time between actions (prevent double-clicking)
ACTION_COOLDOWN = 1.5  # seconds

# Time to wait after click before verifying
CLICK_VERIFY_DELAY = 0.3  # seconds

# Maximum time to wait for table state change
STATE_CHANGE_TIMEOUT = 5.0  # seconds

# =============================================================================
# OCR SETTINGS
# =============================================================================

# Tesseract OCR confidence threshold
OCR_CONFIDENCE_MIN = 60  # 0-100

# Scale factor for OCR preprocessing
OCR_SCALE_FACTOR = 2

# =============================================================================
# FILE PATHS
# =============================================================================

import os
from pathlib import Path

# Base paths
GAMBLE_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = GAMBLE_ROOT / 'data'
LEARNING_DIR = DATA_DIR / 'learning'

# Learning data files
THRESHOLDS_FILE = LEARNING_DIR / 'thresholds.json'
ACTIONS_LOG_FILE = LEARNING_DIR / 'actions.jsonl'
STATS_FILE = LEARNING_DIR / 'stats.json'
CALIBRATION_FILE = LEARNING_DIR / 'calibration.json'
WORKING_CONFIGS_FILE = LEARNING_DIR / 'working_configs.json'
FIXES_LOG_FILE = LEARNING_DIR / 'fixes.jsonl'

# Screenshot directories
SCREENSHOTS_DIR = LEARNING_DIR / 'screenshots'
DEBUG_DIR = LEARNING_DIR / 'debug'

# Ensure directories exist
for dir_path in [LEARNING_DIR, SCREENSHOTS_DIR, DEBUG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)
