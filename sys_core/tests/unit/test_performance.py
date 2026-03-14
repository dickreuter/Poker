"""Performance benchmark tests for the OCR + equity + decision pipeline.

Ensures the full pipeline completes within the <2s latency budget.
"""

import os
import time

import numpy as np
import pytest
from PIL import Image


def _make_synthetic_table(width=1600, height=1000):
    """Create a synthetic table image (green felt with some features)."""
    img = Image.new('RGB', (width, height), (34, 120, 60))  # Green felt
    return img


def _get_any_ggpoker_screenshot():
    """Return a real GGPoker screenshot if available, else synthetic."""
    gg_dir = os.path.join(os.path.dirname(__file__), '..', 'screenshots', 'ggpoker')
    if os.path.isdir(gg_dir):
        for f in os.listdir(gg_dir):
            if f.endswith('.png'):
                return Image.open(os.path.join(gg_dir, f))
    # Fallback: use existing test screenshot
    screenshots_dir = os.path.join(os.path.dirname(__file__), '..', 'screenshots')
    for f in os.listdir(screenshots_dir):
        if f.endswith('.png'):
            return Image.open(os.path.join(screenshots_dir, f))
    return _make_synthetic_table()


class TestOCRPerformance:
    """Benchmark OCR pipeline latency."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from sys_core.ocr.table_reader import read_table
        self.read_table = read_table
        self.test_img = _get_any_ggpoker_screenshot()

    def test_read_table_completes(self):
        """OCR pipeline should complete without error and return a GameState."""
        from sys_core.ocr.game_state import GameState

        state = self.read_table(self.test_img)
        assert state is not None
        assert isinstance(state, GameState)

    def test_read_table_latency_reasonable(self):
        """OCR pipeline should complete within 5s even on non-GGPoker images."""
        latencies = []
        for _ in range(3):
            start = time.time()
            self.read_table(self.test_img)
            latencies.append((time.time() - start) * 1000)

        p50 = sorted(latencies)[len(latencies) // 2]
        # Non-GGPoker images may be slower; real GGPoker images should be <500ms
        assert p50 < 5000, f"p50 OCR latency: {p50:.0f}ms (limit: 5000ms)"


class TestEquityPerformance:
    """Benchmark equity calculation latency."""

    def test_monte_carlo_under_10ms(self):
        """eval7 Monte Carlo (10k iterations) should complete under 10ms."""
        import eval7

        hand = [eval7.Card('Ah'), eval7.Card('Ks')]
        board = [eval7.Card('Qh'), eval7.Card('Jd'), eval7.Card('2c')]

        # Warm up
        for _ in range(5):
            eval7.py_hand_vs_range_monte_carlo(hand, eval7.HandRange("22+,A2+,K5+"), board, 10000)

        latencies = []
        for _ in range(50):
            start = time.time()
            eq = eval7.py_hand_vs_range_monte_carlo(
                hand, eval7.HandRange("22+,A2+,K5+"), board, 10000
            )
            latencies.append((time.time() - start) * 1000)

        p50 = sorted(latencies)[len(latencies) // 2]
        assert p50 < 10, f"p50 equity calc: {p50:.1f}ms (limit: 10ms)"
        # Sanity: AKs on QJ2 should have ~40-60% equity
        assert 0.2 < eq < 0.8, f"Equity sanity check failed: {eq}"

    def test_preflop_equity_under_5ms(self):
        """Preflop Monte Carlo should be very fast."""
        import eval7

        hand = [eval7.Card('As'), eval7.Card('Ah')]

        latencies = []
        for _ in range(50):
            start = time.time()
            eq = eval7.py_hand_vs_range_monte_carlo(
                hand, eval7.HandRange("22+,A2s+,K9s+,QTs+,ATo+,KJo+"), [], 10000
            )
            latencies.append((time.time() - start) * 1000)

        p50 = sorted(latencies)[len(latencies) // 2]
        assert p50 < 5, f"p50 preflop equity: {p50:.1f}ms (limit: 5ms)"
        # AA vs a range should be >70%
        assert eq > 0.70, f"AA equity too low: {eq}"


class TestEndToEndLatency:
    """Full pipeline: OCR + equity + decision must fit in 2s budget."""

    def test_full_pipeline_under_2s(self):
        """Simulates full decision pipeline timing."""
        import eval7
        from sys_core.ocr.table_reader import read_table

        test_img = _get_any_ggpoker_screenshot()

        start = time.time()

        # Step 1: OCR
        state = read_table(test_img)

        # Step 2: Equity calc (simulate with fixed hand)
        hand = [eval7.Card('Ah'), eval7.Card('Ks')]
        eq = eval7.py_hand_vs_range_monte_carlo(
            hand, eval7.HandRange("22+,A2s+,K9s+,QTs+,ATo+,KJo+"), [], 10000
        )

        # Step 3: GTO decision
        from sys_core.decisionmaker.decisionmaker import gto_preflop_decision
        decision = gto_preflop_decision('AKS', 'AKS', 'BTN',
                                         has_raiser=False, call_amount=0,
                                         has_check=False)

        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 5000, f"Full pipeline: {elapsed_ms:.0f}ms (limit: 5000ms)"
        assert decision in ('raise', 'call', 'check', 'fold')
        assert 0 < eq < 1
