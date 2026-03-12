"""Tests for the automatic card template collector."""

import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from sys_core.ocr.template_collector import TemplateCollector


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def collector(temp_dir):
    return TemplateCollector(template_dir=temp_dir)


def make_card_image(width=60, height=80):
    """Create a fake card: white rectangle with some dark pixels (rank/suit)."""
    img = Image.new('RGB', (width, height), (255, 255, 255))
    arr = np.array(img)
    arr[5:20, 5:15] = [50, 50, 50]   # Dark "rank" area
    arr[22:35, 8:18] = [180, 30, 30]  # Red "suit" area
    return Image.fromarray(arr)


def make_table_with_cards():
    """Create a fake table image with two white cards on green felt."""
    table = Image.new('RGB', (800, 600), (30, 100, 50))
    card1 = make_card_image()
    card2 = make_card_image()
    table.paste(card1, (300, 400))
    table.paste(card2, (380, 400))
    return table


class TestTemplateCollector:

    def test_initial_status(self, collector):
        assert collector.get_real_count() == 0
        assert not collector.is_complete()
        assert "Real: 0/52" in collector.status()

    def test_collect_single_card(self, collector):
        table = make_table_with_cards()
        n = collector.collect_from_screenshot(
            table, ['AH'], [(300, 400, 60, 80)]
        )
        assert n == 1
        assert collector.get_real_count() == 1
        assert not collector.needs_card('AH')
        assert (Path(collector.template_dir) / 'AH.png').exists()

    def test_collect_two_cards(self, collector):
        table = make_table_with_cards()
        n = collector.collect_from_screenshot(
            table, ['AH', 'KS'], [(300, 400, 60, 80), (380, 400, 60, 80)]
        )
        assert n == 2
        assert collector.get_real_count() == 2

    def test_rejects_invalid_card_name(self, collector):
        table = make_table_with_cards()
        n = collector.collect_from_screenshot(
            table, ['XX'], [(300, 400, 60, 80)]
        )
        assert n == 0

    def test_rejects_mismatched_lengths(self, collector):
        table = make_table_with_cards()
        n = collector.collect_from_screenshot(
            table, ['AH', 'KS'], [(300, 400, 60, 80)]
        )
        assert n == 0

    def test_rejects_dark_region(self, collector):
        """A dark region (not a card) should be rejected."""
        table = Image.new('RGB', (800, 600), (20, 20, 20))
        n = collector.collect_from_screenshot(
            table, ['AH'], [(300, 400, 60, 80)]
        )
        assert n == 0

    def test_manifest_persists(self, temp_dir):
        c1 = TemplateCollector(template_dir=temp_dir)
        table = make_table_with_cards()
        c1.collect_from_screenshot(table, ['AH'], [(300, 400, 60, 80)])
        assert c1.get_real_count() == 1

        # New instance should load manifest
        c2 = TemplateCollector(template_dir=temp_dir)
        assert c2.get_real_count() == 1
        assert not c2.needs_card('AH')

    def test_quality_increases_on_recollection(self, collector):
        table = make_table_with_cards()
        collector.collect_from_screenshot(table, ['AH'], [(300, 400, 60, 80)])
        q1 = collector.manifest['real']['AH']['quality']
        assert q1 == 1

        collector.collect_from_screenshot(table, ['AH'], [(300, 400, 60, 80)])
        q2 = collector.manifest['real']['AH']['quality']
        assert q2 == 2

    def test_numpy_input(self, collector):
        """Should accept numpy arrays too."""
        table = np.array(make_table_with_cards())
        n = collector.collect_from_screenshot(
            table, ['AH'], [(300, 400, 60, 80)]
        )
        assert n == 1

    def test_saved_template_is_correct_size(self, collector):
        table = make_table_with_cards()
        collector.collect_from_screenshot(table, ['AH'], [(300, 400, 60, 80)])
        saved = Image.open(Path(collector.template_dir) / 'AH.png')
        assert saved.size == (29, 43)
        assert saved.mode == 'RGB'

    def test_needs_card_returns_true_for_missing(self, collector):
        assert collector.needs_card('AH')
        assert collector.needs_card('KS')

    def test_needs_card_returns_false_after_collection(self, collector):
        table = make_table_with_cards()
        collector.collect_from_screenshot(table, ['AH'], [(300, 400, 60, 80)])
        assert not collector.needs_card('AH')
        assert collector.needs_card('KS')  # Still needs this one
