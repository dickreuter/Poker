"""Live state writer — current OCR/decision state per table on disk.

The engine calls publish_state(window_name, state, hand_context) after each
table read. Result is written atomically to data/learning/live_state.json
so the tray app (or any monitor) can poll it once a second and show what
the bot is seeing in real time.

Atomic write via write-temp + rename means readers never see a partial file.
Per-window entries: keys are normalised window names, values are the most
recent snapshot. Stale entries (>30s old) are pruned on next write.
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile
import threading
from typing import Optional

_LOCK = threading.Lock()
_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'data', 'learning', 'live_state.json',
)
_STALE_SECONDS = 30


def _serialise(state, hand_context, window_name: str) -> dict:
    """Build the JSON-friendly snapshot for one table."""
    cards = list(getattr(state, 'my_cards', []) or [])
    board = list(getattr(state, 'board_cards', []) or [])
    street = state.street.value if hasattr(state.street, 'value') else str(state.street)
    hero_player = next((p for p in (state.players or []) if p.is_hero), None)

    # Action sequence — formatted with positions when available
    action_seq = ''
    is_3bet = False
    is_4bet = False
    n_raisers = 0
    if hand_context is not None:
        seq = getattr(hand_context, 'full_action_sequence', None) or []
        parts = []
        prev_street = ''
        for a in seq:
            if a.street != prev_street:
                parts.append(f"[{a.street}]")
                prev_street = a.street
            if a.is_hero:
                tag = 'HERO'
            elif a.position:
                tag = a.position
            else:
                tag = f"s{a.seat}"
            amt = f"{a.amount:g}" if a.amount else ''
            parts.append(f"{tag}-{a.action}{amt}")
        action_seq = ' '.join(parts)
        is_3bet = bool(getattr(hand_context, 'is_3bet_pot', False))
        is_4bet = bool(getattr(hand_context, 'is_4bet_pot', False))
        n_raisers = int(getattr(hand_context, 'num_preflop_raisers', 0) or 0)

    players = [
        {
            'seat': p.seat,
            'name': p.name or '',
            'stack': p.stack,
            'bet': p.current_bet or 0,
            'is_hero': bool(p.is_hero),
            'is_active': bool(p.is_active),
        }
        for p in (state.players or [])
    ]

    return {
        'window': window_name,
        'updated': datetime.datetime.utcnow().isoformat(timespec='seconds'),
        'is_my_turn': bool(getattr(state, 'is_my_turn', False)),
        'street': street,
        'position': getattr(state, 'position', 'UNKNOWN'),
        'cards': cards,
        'board': board,
        'pot': float(getattr(state, 'pot', 0) or 0),
        'call': float(getattr(state, 'call_amount', 0) or 0),
        'hero_stack': hero_player.stack if hero_player else None,
        'opponents_in_hand': int(getattr(state, 'opponents_in_hand', -1) or -1),
        'action_sequence': action_seq,
        'is_3bet_pot': is_3bet,
        'is_4bet_pot': is_4bet,
        'num_preflop_raisers': n_raisers,
        'players': players,
        'buttons': [a.action_type for a in (state.available_actions or [])],
        'latency_ms': float(getattr(state, 'ocr_latency_ms', 0) or 0),
    }


def publish_state(window_name: str, state, hand_context=None) -> None:
    """Atomically update the live-state file with this table's snapshot.

    Failures are silently swallowed — live state is observability, never
    block the engine's decision loop on it.
    """
    if not window_name:
        return
    try:
        snapshot = _serialise(state, hand_context, window_name)
    except Exception:
        return

    with _LOCK:
        # Read existing
        existing = {}
        try:
            with open(_PATH, 'r') as f:
                existing = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing = {}

        tables = existing.get('tables', {}) if isinstance(existing, dict) else {}

        # Prune stale entries before adding
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(seconds=_STALE_SECONDS)
        fresh = {}
        for k, v in tables.items():
            try:
                t = datetime.datetime.fromisoformat(v.get('updated', ''))
                if t >= cutoff:
                    fresh[k] = v
            except (ValueError, TypeError):
                pass

        fresh[window_name] = snapshot
        out = {
            'last_updated': datetime.datetime.utcnow().isoformat(timespec='seconds'),
            'tables': fresh,
        }

        # Atomic write — temp file + rename
        try:
            os.makedirs(os.path.dirname(_PATH), exist_ok=True)
            d = os.path.dirname(_PATH)
            fd, tmp = tempfile.mkstemp(prefix='.live_state_', suffix='.json', dir=d)
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(out, f, indent=2, default=str)
                os.replace(tmp, _PATH)
            except Exception:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
        except Exception:
            pass


def read_state() -> Optional[dict]:
    """Read the latest live state. Returns None if not available."""
    try:
        with open(_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
