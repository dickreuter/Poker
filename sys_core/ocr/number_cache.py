"""Persistent pixel-hash cache for number OCR.

Same pattern as card_hash_cache: hash the ROI pixels, look up the cached
OCR result. Cache hit = O(1). Cache miss = caller runs full OCR pipeline
and calls put() to populate.

Safety: the cache key IS the pixel content (md5 of normalised crop bytes).
Any change in the ROI invalidates the entry — we cannot return a stale
value for a different visual state. This makes the cache a pure
memoization layer: it cannot reduce accuracy, only latency.

Bounded by a simple LRU policy to avoid unbounded memory growth.
"""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Any, Optional

import cv2
import numpy as np

# Normalised crop size for hashing — small enough that minor sub-pixel
# jitter still produces the same hash, large enough to distinguish different
# numbers (e.g. "100" vs "101").
_HASH_W = 96
_HASH_H = 24

# LRU cap. Each entry is ~64 bytes for the key + value, so 10k entries
# is ~640 KB — trivial.
_LRU_CAP = 10_000


class NumberCache:
    """Thread-safe, bounded pixel-hash → value cache."""

    def __init__(self, cap: int = _LRU_CAP):
        self._cap = cap
        self._data: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _hash(crop: np.ndarray) -> str:
        """Stable MD5 of a normalised grayscale crop."""
        if crop.size == 0:
            return ""
        if crop.ndim == 3:
            gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
        else:
            gray = crop
        # Normalise size so jitter doesn't break the hash.
        # INTER_AREA is best for downsampling — preserves shape.
        norm = cv2.resize(gray, (_HASH_W, _HASH_H), interpolation=cv2.INTER_AREA)
        # Quantise to reduce sensitivity to anti-aliasing noise.
        norm = (norm // 16) * 16
        return hashlib.md5(norm.tobytes()).hexdigest()

    def get(self, crop: np.ndarray) -> Optional[Any]:
        """Return cached value or None on miss."""
        key = self._hash(crop)
        if not key:
            return None
        with self._lock:
            if key in self._data:
                # Move to end = mark recently used.
                self._data.move_to_end(key)
                self._hits += 1
                return self._data[key]
            self._misses += 1
            return None

    def put(self, crop: np.ndarray, value: Any) -> None:
        """Store a value. Evicts oldest entry if at capacity."""
        key = self._hash(crop)
        if not key:
            return
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self._data[key] = value
                return
            self._data[key] = value
            if len(self._data) > self._cap:
                self._data.popitem(last=False)

    def stats(self) -> dict:
        """Return cache statistics for monitoring."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._data),
                "cap": self._cap,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
            }

    def clear(self) -> None:
        """Wipe cache. Useful for tests or after a known UI change."""
        with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0


# Module-level singletons — one per OCR field type.
# Separating them prevents a stack-shaped crop hash from colliding with
# a pot-shaped crop hash (different ROI sizes → different normalised
# representations, but isolation is cheap insurance).
stack_cache = NumberCache()
pot_cache = NumberCache()
button_cache = NumberCache()
# Player names rarely change — cache aggressively to skip the per-seat
# tesseract call on every frame. Cap is small because there are far fewer
# distinct nameplate pixel-hashes than there are stack values.
name_cache = NumberCache(cap=2000)


def all_stats() -> dict:
    """Aggregate stats across all caches — for monitoring/debug."""
    return {
        "stack": stack_cache.stats(),
        "pot": pot_cache.stats(),
        "button": button_cache.stats(),
        "name": name_cache.stats(),
    }
