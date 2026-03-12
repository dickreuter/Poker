"""
Bridge between the new OCR GameState and the existing adaptive learner.

Logs OCR results and updates thresholds based on detection success/failure.
"""

import logging
from typing import Optional

from sys_core.ocr.game_state import GameState

log = logging.getLogger(__name__)

try:
    from sys_core.tools.adaptive_learner import log_action, get_threshold, set_threshold
    LEARNER_AVAILABLE = True
except ImportError:
    LEARNER_AVAILABLE = False


def log_ocr_result(state: GameState, expected_turn: Optional[bool] = None):
    """Log an OCR result to the adaptive learner.

    Args:
        state: The detected game state
        expected_turn: If known, whether it should be our turn (for validation)
    """
    if not LEARNER_AVAILABLE:
        return

    success = True
    details = {
        'source': state.ocr_source,
        'latency_ms': state.ocr_latency_ms,
        'cards': state.my_cards,
        'board': state.board_cards,
        'is_turn': state.is_my_turn,
        'actions': len(state.available_actions),
        'face_down': state.cards_face_down,
    }

    if expected_turn is not None and state.is_my_turn != expected_turn:
        success = False
        details['expected_turn'] = expected_turn

    log_action('ocr_detection', success=success, details=details)


def get_ocr_thresholds() -> dict:
    """Get current thresholds from the adaptive learner."""
    if not LEARNER_AVAILABLE:
        return {}

    return {
        'white_pixel_min': get_threshold('white_pixel_min', 180),
        'card_area_min': get_threshold('card_area_min', 1500),
        'button_area_min': get_threshold('button_area_min', 1500),
        'match_score_max': get_threshold('match_score_max', 0.35),
    }
