"""
Python fallback OCR - Uses existing CardDetector, ButtonDetector, and DynamicTableReader
to produce GameState when the Rust binary is unavailable.
"""

import logging
import re
import time
from typing import List, Optional, Tuple

from sys_core.ocr.game_state import (
    AvailableAction,
    GameState,
    PlayerInfo,
    Street,
)

log = logging.getLogger(__name__)

# Lazy imports to avoid circular dependencies and hard failures
_CARD_DETECTOR = None
_BUTTON_DETECTOR = None


def _get_card_detector():
    global _CARD_DETECTOR
    if _CARD_DETECTOR is None:
        try:
            from sys_core.core.card_detector import CardDetector
            _CARD_DETECTOR = CardDetector()
        except Exception as e:
            log.warning(f"Could not load CardDetector: {e}")
    return _CARD_DETECTOR


def _get_button_detector():
    global _BUTTON_DETECTOR
    if _BUTTON_DETECTOR is None:
        try:
            from sys_core.core.button_detector import ButtonDetector
            _BUTTON_DETECTOR = ButtonDetector()
        except Exception as e:
            log.warning(f"Could not load ButtonDetector: {e}")
    return _BUTTON_DETECTOR


def _parse_blinds_from_title(title: str) -> Tuple[float, float]:
    """Extract blinds from window title like 'Spin & Gold $0.25 - Blinds 15 | 30'."""
    match = re.search(r'Blinds\s+(\d+(?:\.\d+)?)\s*\|\s*(\d+(?:\.\d+)?)', title)
    if match:
        return float(match.group(1)), float(match.group(2))
    return 0.0, 0.0


def _street_from_board(board_cards: List[str]) -> Street:
    n = len(board_cards)
    if n == 0:
        return Street.PREFLOP
    elif n == 3:
        return Street.FLOP
    elif n == 4:
        return Street.TURN
    elif n >= 5:
        return Street.RIVER
    return Street.UNKNOWN


class PythonOCRFallback:
    """Fallback OCR using existing Python detection components."""

    def capture_table(self, table_img, window_id: int = 0,
                      window_name: str = "", table_x_pt: int = 0,
                      table_y_pt: int = 0, table_w_pt: int = 0,
                      table_h_pt: int = 0) -> GameState:
        """Analyze a table screenshot and return GameState.

        Args:
            table_img: numpy array (BGR) or PIL Image of the table
            window_id: CGWindowID
            window_name: Window title
            table_x_pt, table_y_pt: Window position in macOS points
            table_w_pt, table_h_pt: Window size in macOS points

        Returns:
            GameState with whatever could be detected
        """
        import numpy as np

        start = time.time()

        # Convert PIL to numpy if needed
        if hasattr(table_img, 'mode'):
            import cv2
            img = np.array(table_img)
            if len(img.shape) == 3 and img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            elif len(img.shape) == 3 and img.shape[2] == 3:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        else:
            img = table_img

        # Detect cards
        my_cards = []
        board_cards = []
        cards_face_down = False

        card_det = _get_card_detector()
        if card_det:
            try:
                detected = card_det.detect_player_cards(img)
                if detected:
                    my_cards = [c.code if hasattr(c, 'code') else str(c) for c in detected]
                else:
                    cards_face_down = True
            except Exception as e:
                log.debug(f"Card detection failed: {e}")
                cards_face_down = True

            try:
                board_detected = card_det.detect_board_cards(img)
                if board_detected:
                    board_cards = [c.code if hasattr(c, 'code') else str(c) for c in board_detected]
            except Exception:
                pass

        # Detect buttons
        available_actions = []
        btn_det = _get_button_detector()
        if btn_det:
            try:
                buttons = btn_det.detect(img)
                if buttons:
                    for btn_type, btn_info in buttons.items():
                        if isinstance(btn_info, dict):
                            center = btn_info.get('center', (0, 0))
                            # Convert pixel center to screen points
                            screen_x = table_x_pt + center[0] // 2
                            screen_y = table_y_pt + center[1] // 2
                            available_actions.append(AvailableAction(
                                action_type=btn_type,
                                amount=btn_info.get('amount'),
                                screen_x_pt=screen_x,
                                screen_y_pt=screen_y,
                                confidence=btn_info.get('confidence', 0.5),
                            ))
                        elif hasattr(btn_info, 'button_type'):
                            screen_x = table_x_pt + btn_info.center_px[0] // 2
                            screen_y = table_y_pt + btn_info.center_px[1] // 2
                            available_actions.append(AvailableAction(
                                action_type=btn_info.button_type,
                                amount=None,
                                screen_x_pt=screen_x,
                                screen_y_pt=screen_y,
                                confidence=btn_info.confidence,
                            ))
            except Exception as e:
                log.debug(f"Button detection failed: {e}")

        # Parse blinds from window title
        sb, bb = _parse_blinds_from_title(window_name)

        # Determine street
        street = _street_from_board(board_cards)

        is_my_turn = len(available_actions) > 0

        elapsed_ms = (time.time() - start) * 1000

        return GameState(
            window_id=window_id,
            window_name=window_name,
            table_x_pt=table_x_pt,
            table_y_pt=table_y_pt,
            table_w_pt=table_w_pt,
            table_h_pt=table_h_pt,
            my_cards=my_cards,
            board_cards=board_cards,
            cards_face_down=cards_face_down,
            pot=0.0,
            current_street_pot=0.0,
            call_amount=0.0,
            min_raise_amount=0.0,
            small_blind=sb,
            big_blind=bb,
            players=[],
            hero_seat=-1,
            dealer_seat=-1,
            available_actions=available_actions,
            street=street,
            is_my_turn=is_my_turn,
            ocr_latency_ms=elapsed_ms,
            ocr_source='python_fallback',
        )
