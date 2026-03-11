"""
Tests that card templates can be reliably discriminated from each other.

Each template should match itself strongly and not match other templates.
This catches the "2D detected 52 times" bias problem.
"""

import os
import pytest
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / 'poker_ocr' / 'assets' / 'card_templates'
RANKS = ['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']
SUITS = ['H', 'D', 'C', 'S']


class TestCardTemplateDiscrimination:

    def test_all_52_templates_exist(self):
        """All 52 card templates must be present."""
        missing = []
        for rank in RANKS:
            for suit in SUITS:
                card = f"{rank}{suit}"
                path = TEMPLATE_DIR / f"{card}.png"
                if not path.exists():
                    missing.append(card)

        assert not missing, f"Missing templates: {missing}"

    def test_templates_are_valid_images(self):
        """All templates must be loadable as images."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("PIL not installed")

        for rank in RANKS:
            for suit in SUITS:
                card = f"{rank}{suit}"
                path = TEMPLATE_DIR / f"{card}.png"
                if path.exists():
                    img = Image.open(path)
                    assert img.size[0] > 0 and img.size[1] > 0, f"{card} has zero dimension"
                    assert img.size[1] > img.size[0], f"{card} should be taller than wide (card corner)"

    def test_templates_have_consistent_height(self):
        """All templates should have the same height (43px)."""
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("PIL not installed")

        heights = set()
        for png in TEMPLATE_DIR.glob('*.png'):
            img = Image.open(png)
            heights.add(img.size[1])

        assert len(heights) == 1, f"Templates have inconsistent heights: {heights}"

    def test_no_duplicate_templates(self):
        """No two templates should be pixel-identical."""
        try:
            from PIL import Image
            import numpy as np
        except ImportError:
            pytest.skip("PIL/numpy not installed")

        templates = {}
        for png in sorted(TEMPLATE_DIR.glob('*.png')):
            img = Image.open(png).convert('RGB')
            # Resize all to same size for comparison
            img = img.resize((29, 43))
            arr = np.array(img)
            templates[png.stem] = arr

        duplicates = []
        names = list(templates.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                if np.array_equal(templates[names[i]], templates[names[j]]):
                    duplicates.append((names[i], names[j]))

        assert not duplicates, f"Duplicate templates found: {duplicates}"

    def test_same_suit_templates_share_color(self):
        """Templates of same suit should have similar color profiles."""
        try:
            from PIL import Image
            import numpy as np
        except ImportError:
            pytest.skip("PIL/numpy not installed")

        # Hearts and Diamonds should be reddish
        for suit in ['H', 'D']:
            for rank in RANKS:
                path = TEMPLATE_DIR / f"{rank}{suit}.png"
                if path.exists():
                    img = np.array(Image.open(path).convert('RGB'))
                    # Check that some non-white pixels are reddish
                    non_white = img[img.mean(axis=2) < 200]
                    if len(non_white) > 10:
                        avg_r = non_white[:, 0].mean()
                        avg_b = non_white[:, 2].mean()
                        assert avg_r > avg_b, (
                            f"{rank}{suit}: Red suit should have more red than blue "
                            f"(R={avg_r:.0f}, B={avg_b:.0f})"
                        )

        # Spades and Clubs should be dark
        for suit in ['S', 'C']:
            for rank in RANKS:
                path = TEMPLATE_DIR / f"{rank}{suit}.png"
                if path.exists():
                    img = np.array(Image.open(path).convert('RGB'))
                    non_white = img[img.mean(axis=2) < 200]
                    if len(non_white) > 10:
                        avg = non_white.mean()
                        assert avg < 150, (
                            f"{rank}{suit}: Black suit should be dark (avg={avg:.0f})"
                        )
