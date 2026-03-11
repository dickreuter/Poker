"""Tests for PixelHashCardCache — the O(1) pixel-hash card lookup system.

These tests validate all the properties that make the cache reliable:
 - Empty cache returns None
 - record + lookup roundtrip works correctly
 - Low-confidence crops are NOT saved
 - Persistence: save to disk, reload, lookup still works
 - Different images get different hashes (no spurious collisions)
 - Duplicate record calls don't corrupt the cache
 - Invalid card strings are rejected
"""
import json
import pathlib
import tempfile

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_crop(seed: int, shape=(90, 60, 3)) -> np.ndarray:
    """Make a deterministic synthetic card crop from a seed."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=shape, dtype=np.uint8)


# ---------------------------------------------------------------------------
# Import the module under test (import after helpers so errors surface cleanly)
# ---------------------------------------------------------------------------

from gamble.ocr.card_reader import PixelHashCardCache, _MIN_RECORD_CONFIDENCE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_cache(tmp_path):
    """Return a fresh PixelHashCardCache backed by a temp file."""
    cache_path = tmp_path / "test_hash_cache.json"
    return PixelHashCardCache(cache_path=cache_path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPixelHashCacheBasics:
    def test_empty_cache_returns_none(self, tmp_cache):
        crop = _make_crop(1)
        assert tmp_cache.lookup(crop) is None

    def test_size_starts_at_zero(self, tmp_cache):
        assert tmp_cache.size() == 0

    def test_record_high_confidence_saves(self, tmp_cache):
        crop = _make_crop(2)
        tmp_cache.record(crop, "AH", confidence=1.0)
        assert tmp_cache.lookup(crop) == "AH"

    def test_record_exact_threshold_saves(self, tmp_cache):
        crop = _make_crop(3)
        tmp_cache.record(crop, "KS", confidence=_MIN_RECORD_CONFIDENCE)
        assert tmp_cache.lookup(crop) == "KS"

    def test_record_low_confidence_does_not_save(self, tmp_cache):
        crop = _make_crop(4)
        low = _MIN_RECORD_CONFIDENCE - 0.01
        tmp_cache.record(crop, "QD", confidence=low)
        assert tmp_cache.lookup(crop) is None

    def test_record_zero_confidence_does_not_save(self, tmp_cache):
        crop = _make_crop(5)
        tmp_cache.record(crop, "2C", confidence=0.0)
        assert tmp_cache.lookup(crop) is None

    def test_different_crops_different_results(self, tmp_cache):
        crop_a = _make_crop(6)
        crop_b = _make_crop(7)
        tmp_cache.record(crop_a, "AH", confidence=1.0)
        tmp_cache.record(crop_b, "KS", confidence=1.0)
        assert tmp_cache.lookup(crop_a) == "AH"
        assert tmp_cache.lookup(crop_b) == "KS"

    def test_same_card_different_images_get_different_hashes(self, tmp_cache):
        """Two different crops should not produce the same hash (basic sanity)."""
        crop_a = _make_crop(8)
        crop_b = _make_crop(9)
        # They return different cards — hash must differ
        tmp_cache.record(crop_a, "AH", confidence=1.0)
        tmp_cache.record(crop_b, "KD", confidence=1.0)
        assert tmp_cache.lookup(crop_a) == "AH"
        assert tmp_cache.lookup(crop_b) == "KD"

    def test_size_increments_on_new_records(self, tmp_cache):
        for i, card in enumerate(["AH", "KS", "QD", "JC"]):
            tmp_cache.record(_make_crop(10 + i), card, confidence=1.0)
        assert tmp_cache.size() == 4

    def test_duplicate_record_doesnt_change_result(self, tmp_cache):
        crop = _make_crop(20)
        tmp_cache.record(crop, "AH", confidence=1.0)
        tmp_cache.record(crop, "AH", confidence=1.0)  # same, shouldn't error
        assert tmp_cache.lookup(crop) == "AH"
        assert tmp_cache.size() == 1

    def test_invalid_card_string_too_short_rejected(self, tmp_cache):
        crop = _make_crop(21)
        tmp_cache.record(crop, "A", confidence=1.0)  # 1 char, invalid
        assert tmp_cache.lookup(crop) is None

    def test_invalid_card_string_too_long_rejected(self, tmp_cache):
        crop = _make_crop(22)
        tmp_cache.record(crop, "AHKK", confidence=1.0)  # 4 chars, invalid
        assert tmp_cache.lookup(crop) is None


class TestPixelHashCachePersistence:
    def test_lookup_after_reload(self, tmp_path):
        """Records written to disk are available after loading a new instance."""
        cache_path = tmp_path / "persist_test.json"
        crop = _make_crop(30)

        # Write with first instance
        cache1 = PixelHashCardCache(cache_path=cache_path)
        cache1.record(crop, "10D", confidence=1.0)

        # Load with second instance — should find the record
        cache2 = PixelHashCardCache(cache_path=cache_path)
        assert cache2.lookup(crop) == "10D"

    def test_cache_file_is_valid_json(self, tmp_path):
        cache_path = tmp_path / "json_test.json"
        cache = PixelHashCardCache(cache_path=cache_path)
        cache.record(_make_crop(31), "AS", confidence=1.0)

        with open(cache_path) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert len(data) == 1

    def test_all_52_cards_can_be_stored(self, tmp_path):
        """Confirm the cache can hold all 52 distinct card records."""
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
        suits = ['H', 'D', 'C', 'S']
        all_cards = [r + s for r in ranks for s in suits]
        assert len(all_cards) == 52

        cache_path = tmp_path / "full_deck.json"
        cache = PixelHashCardCache(cache_path=cache_path)
        for i, card in enumerate(all_cards):
            cache.record(_make_crop(100 + i), card, confidence=1.0)

        assert cache.size() == 52

        # Verify random samples survive
        for i, card in enumerate(all_cards[:10]):
            assert cache.lookup(_make_crop(100 + i)) == card


class TestPixelHashCacheEdgeCases:
    def test_empty_crop_does_not_crash(self, tmp_cache):
        """An empty numpy array shouldn't raise, should return None."""
        empty = np.zeros((0, 0, 3), dtype=np.uint8)
        result = tmp_cache.lookup(empty)
        assert result is None

    def test_single_pixel_crop(self, tmp_cache):
        """A 1x1 crop should hash without error."""
        tiny = np.array([[[255, 0, 0]]], dtype=np.uint8)
        tmp_cache.record(tiny, "AH", confidence=1.0)
        assert tmp_cache.lookup(tiny) == "AH"

    def test_stats_returns_string(self, tmp_cache):
        result = tmp_cache.stats()
        assert isinstance(result, str)
        assert "PixelHashCache" in result
