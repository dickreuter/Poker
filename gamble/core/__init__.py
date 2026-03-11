"""
UNIFIED CORE MODULE - Single Source of Truth

This module consolidates all detection, learning, and bot functionality into
ONE unified system. All bots should import from here instead of using their
own implementations.

Created: Jan 4, 2026
Purpose: Fix the fragmented architecture where 6+ card detectors, 7+ button
         detectors, and 3+ learning systems were all incompatible.

USAGE:
    from gamble.core import (
        # Detection
        CardDetector,
        ButtonDetector,
        WindowFinder,
        TableWindow,

        # Learning
        UnifiedLearner,
        get_learner,

        # Bot base class
        BaseBot,

        # Constants
        RETINA_SCALE,
        HSV_RANGES,
    )

WHY THIS EXISTS:
    Before this module, the codebase had:
    - 6 different card detection systems (template, white mask, neural net, etc.)
    - 7 different button detection systems (each with different HSV ranges)
    - 3 different window finders (each reimplementing AppleScript)
    - 3 different learning systems (that didn't talk to each other)
    - 8 different bots (each with different decision logic)

    Now there is ONE of each, used by ALL bots.
"""

from gamble.core.constants import RETINA_SCALE, HSV_RANGES, BUTTON_KEYWORDS
from gamble.core.window_finder import WindowFinder, TableWindow
from gamble.core.button_detector import ButtonDetector
from gamble.core.card_detector import CardDetector
from gamble.core.unified_learner import UnifiedLearner, get_learner
from gamble.core.base_bot import BaseBot

__all__ = [
    # Constants
    'RETINA_SCALE',
    'HSV_RANGES',
    'BUTTON_KEYWORDS',

    # Window finding
    'WindowFinder',
    'TableWindow',

    # Detection
    'ButtonDetector',
    'CardDetector',

    # Learning
    'UnifiedLearner',
    'get_learner',

    # Bot base
    'BaseBot',
]
