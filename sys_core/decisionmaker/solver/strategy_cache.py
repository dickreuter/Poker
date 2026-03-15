"""Persistent strategy cache for solved spots.

Saves CFR solutions to disk so they accumulate over time.
Key = (board_category, hero_range_hash, villain_range_hash, spr_bucket)
"""
import hashlib
import logging
import os
import pickle
import time
from typing import Dict, Optional, Tuple

log = logging.getLogger(__name__)

_CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'solver', 'postflop_cache')
_memory_cache: Dict[str, dict] = {}
_cache_loaded = False


def _board_category(board_cards) -> str:
    """Classify board into a coarse category for caching."""
    if not board_cards:
        return 'preflop'

    rank_map = {r: i for i, r in enumerate('23456789TJQKA')}
    ranks, suits = [], []
    for c in board_cards[:3]:
        if c and len(c) >= 2:
            r = c[0].upper()
            if r == '1':
                r = 'T'
            ranks.append(rank_map.get(r, 0))
            suits.append(c[-1].upper())

    if len(ranks) < 3:
        return 'unknown'

    # Pairing
    from collections import Counter
    rank_counts = Counter(ranks)
    paired = max(rank_counts.values()) >= 2

    # Suits
    suit_counts = Counter(suits)
    monotone = max(suit_counts.values()) >= 3
    two_tone = max(suit_counts.values()) == 2

    # Connectivity
    sorted_r = sorted(set(ranks))
    connected = len(sorted_r) >= 2 and (sorted_r[-1] - sorted_r[0]) <= 4

    # Height
    high = max(ranks) >= 10  # T or higher

    if monotone:
        return 'monotone'
    if paired and high:
        return 'paired_high'
    if paired:
        return 'paired_low'
    if connected and two_tone:
        return 'wet'
    if high and not two_tone:
        return 'dry_high'
    if not high and not two_tone:
        return 'dry_low'
    if two_tone and high:
        return 'twotone_high'
    return 'twotone_low'


def _spr_bucket(spr: float) -> str:
    """Bucket SPR into coarse categories."""
    if spr < 2:
        return 'spr_1'
    elif spr < 4:
        return 'spr_3'
    elif spr < 7:
        return 'spr_5'
    elif spr < 12:
        return 'spr_10'
    else:
        return 'spr_15'


def _range_hash(range_str: str) -> str:
    """Short hash of a range string."""
    return hashlib.md5(range_str.encode()).hexdigest()[:8]


def cache_key(board_cards, hero_range_str, villain_range_str, spr) -> str:
    """Build a cache key for a postflop spot."""
    cat = _board_category(board_cards)
    spr_b = _spr_bucket(spr)
    hr = _range_hash(hero_range_str or '')
    vr = _range_hash(villain_range_str or '')
    street = {3: 'flop', 4: 'turn', 5: 'river'}.get(len(board_cards), 'flop')
    return f'{street}_{cat}_{spr_b}_{hr}_{vr}'


def get_cached_strategy(key: str) -> Optional[dict]:
    """Look up a cached strategy. Returns None if not found."""
    _load_cache()
    return _memory_cache.get(key)


def save_strategy(key: str, strategy: dict, metadata: dict = None):
    """Save a solved strategy to cache."""
    entry = {
        'strategy': strategy,
        'timestamp': time.time(),
        'metadata': metadata or {},
    }
    _memory_cache[key] = entry
    _save_to_disk(key, entry)


def _load_cache():
    """Load all cached strategies from disk on first access."""
    global _cache_loaded
    if _cache_loaded:
        return

    os.makedirs(_CACHE_DIR, exist_ok=True)
    count = 0
    try:
        for fname in os.listdir(_CACHE_DIR):
            if fname.endswith('.pkl'):
                fpath = os.path.join(_CACHE_DIR, fname)
                try:
                    with open(fpath, 'rb') as f:
                        entry = pickle.load(f)
                    key = fname[:-4]  # Remove .pkl
                    _memory_cache[key] = entry
                    count += 1
                except Exception:
                    continue
    except Exception:
        pass

    _cache_loaded = True
    if count > 0:
        log.info(f"STRATEGY CACHE: loaded {count} cached solutions")


def _save_to_disk(key: str, entry: dict):
    """Save one strategy to disk."""
    os.makedirs(_CACHE_DIR, exist_ok=True)
    safe_key = key.replace('/', '_').replace('\\', '_')[:100]
    fpath = os.path.join(_CACHE_DIR, f'{safe_key}.pkl')
    try:
        with open(fpath, 'wb') as f:
            pickle.dump(entry, f)
    except Exception as e:
        log.debug(f"Cache save failed: {e}")


def cache_stats() -> dict:
    """Return cache statistics."""
    _load_cache()
    return {
        'n_entries': len(_memory_cache),
        'cache_dir': _CACHE_DIR,
    }
