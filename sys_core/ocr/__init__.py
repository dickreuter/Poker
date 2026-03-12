"""
OCR module - Unified game state extraction via Rust OCR binary or Python fallback.

Usage:
    from sys_core.ocr import RustOCRBridge, GameState

    bridge = RustOCRBridge()
    state = bridge.capture_table(window_id=12345)

    if state.is_my_turn:
        for action in state.available_actions:
            print(f"{action.action_type}: {action.amount}")
"""

from sys_core.ocr.game_state import (
    GameState,
    PlayerInfo,
    AvailableAction,
    Street,
)
from sys_core.ocr.rust_bridge import RustOCRBridge
from sys_core.ocr.table_reader import read_table
from sys_core.ocr.card_reader import read_player_cards

__all__ = [
    'GameState',
    'PlayerInfo',
    'AvailableAction',
    'Street',
    'RustOCRBridge',
    'read_table',
    'read_player_cards',
]
