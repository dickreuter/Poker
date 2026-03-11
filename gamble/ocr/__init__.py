"""
OCR module - Unified game state extraction via Rust OCR binary or Python fallback.

Usage:
    from gamble.ocr import RustOCRBridge, GameState

    bridge = RustOCRBridge()
    state = bridge.capture_table(window_id=12345)

    if state.is_my_turn:
        for action in state.available_actions:
            print(f"{action.action_type}: {action.amount}")
"""

from gamble.ocr.game_state import (
    GameState,
    PlayerInfo,
    AvailableAction,
    Street,
)
from gamble.ocr.rust_bridge import RustOCRBridge
from gamble.ocr.table_reader import read_table
from gamble.ocr.card_reader import read_player_cards

__all__ = [
    'GameState',
    'PlayerInfo',
    'AvailableAction',
    'Street',
    'RustOCRBridge',
    'read_table',
    'read_player_cards',
]
