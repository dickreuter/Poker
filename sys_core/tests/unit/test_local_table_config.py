"""Tests for local table configuration (MongoDB replacement)."""

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from sys_core.ocr.local_table_config import (
    build_local_table_dict,
    load_card_templates,
    RANKS,
    SUITS,
    REGIONS_PCT,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
TEMPLATE_DIR = PROJECT_ROOT / 'poker_ocr' / 'assets' / 'card_templates'


class TestLoadCardTemplates:

    def test_loads_templates_from_disk(self):
        templates = load_card_templates(TEMPLATE_DIR)
        assert len(templates) > 0

    def test_templates_are_bytes(self):
        templates = load_card_templates(TEMPLATE_DIR)
        for key, data in templates.items():
            assert isinstance(data, bytes), f"{key} should be bytes"

    def test_templates_are_valid_png(self):
        templates = load_card_templates(TEMPLATE_DIR)
        for key, data in templates.items():
            img = Image.open(io.BytesIO(data))
            assert img.size[0] > 0 and img.size[1] > 0, f"{key} should be valid image"

    def test_template_keys_are_lowercase(self):
        templates = load_card_templates(TEMPLATE_DIR)
        for key in templates:
            assert key == key.lower(), f"Key {key} should be lowercase"


class TestBuildLocalTableDict:

    def test_builds_successfully(self):
        td = build_local_table_dict(1600, 1200)
        assert isinstance(td, dict)
        assert len(td) > 52  # 52 cards + regions + templates

    def test_has_card_templates(self):
        td = build_local_table_dict(1600, 1200)
        # Check a few known cards
        for card in ['ah', 'ks', '2c', '10d']:
            if (TEMPLATE_DIR / f"{card.upper()}.png").exists():
                assert card in td, f"Should have template for {card}"
                assert isinstance(td[card], bytes)

    def test_has_card_areas(self):
        td = build_local_table_dict(1600, 1200)
        for area in ['my_cards_area', 'left_card_area', 'right_card_area']:
            assert area in td, f"Should have {area}"
            assert 'x1' in td[area]
            assert 'y1' in td[area]
            assert 'x2' in td[area]
            assert 'y2' in td[area]

    def test_card_areas_are_pixel_coordinates(self):
        td = build_local_table_dict(1600, 1200)
        area = td['my_cards_area']
        assert 0 <= area['x1'] < area['x2'] <= 1600
        assert 0 <= area['y1'] < area['y2'] <= 1200

    def test_has_button_areas(self):
        td = build_local_table_dict(1600, 1200)
        assert 'buttons_search_area' in td
        assert 'my_turn_search_area' in td

    def test_has_mouse_areas(self):
        td = build_local_table_dict(1600, 1200)
        for key in ['mouse_fold', 'mouse_call', 'mouse_check', 'mouse_raise']:
            assert key in td, f"Should have {key}"
            assert td[key]['x2'] > td[key]['x1']

    def test_has_dummy_templates(self):
        td = build_local_table_dict(1600, 1200)
        for key in ['topleft_corner', 'call_button', 'raise_button', 'check_button']:
            assert key in td, f"Should have dummy template for {key}"
            assert isinstance(td[key], bytes)

    def test_has_pot_areas(self):
        td = build_local_table_dict(1600, 1200)
        for key in ['total_pot_area', 'current_round_pot', 'call_value', 'raise_value']:
            assert key in td, f"Should have {key}"

    def test_has_player_areas(self):
        td = build_local_table_dict(1600, 1200)
        assert 'player_funds_area' in td
        assert 'player_pot_area' in td
        assert '0' in td['player_funds_area']
        assert '5' in td['player_funds_area']

    def test_scales_to_different_sizes(self):
        td_small = build_local_table_dict(800, 600)
        td_large = build_local_table_dict(1600, 1200)

        # Same percentage should give approximately proportional coordinates (int rounding)
        assert abs(td_large['my_cards_area']['x1'] - 2 * td_small['my_cards_area']['x1']) <= 1
        assert abs(td_large['my_cards_area']['y1'] - 2 * td_small['my_cards_area']['y1']) <= 1

    def test_max_players(self):
        td = build_local_table_dict(1600, 1200)
        assert td['max_players']['value'] == 6

    def test_compatible_with_binary_pil_to_cv2(self):
        """Card templates should work with the original binary_pil_to_cv2 function."""
        import cv2
        td = build_local_table_dict(1600, 1200)

        # Pick any card template that exists
        for key in ['ah', 'ks', '2c']:
            if key in td:
                data = td[key]
                img = Image.open(io.BytesIO(data))
                cv2_img = cv2.cvtColor(np.array(img), cv2.COLOR_BGR2RGB)
                assert cv2_img.shape[0] > 0
                assert cv2_img.shape[1] > 0
                break
