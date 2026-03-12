"""Tests for sys_core.ocr.card_reader — dynamic OCR card detection."""

import numpy as np
import pytest
from PIL import Image

from sys_core.ocr.card_reader import (
    _detect_suit_at,
    _detect_suit_colored,
    _find_card_positions,
    _parse_rank,
    read_player_cards,
)


class TestParseRank:
    def test_valid_ranks(self):
        for rank in ['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']:
            assert _parse_rank(rank) == rank

    def test_whitespace(self):
        assert _parse_rank(' K ') == 'K'
        assert _parse_rank('Q\n') == 'Q'

    def test_lowercase(self):
        assert _parse_rank('a') == 'A'
        assert _parse_rank('k') == 'K'

    def test_first_char_valid(self):
        assert _parse_rank('Qx') == 'Q'
        assert _parse_rank('A!') == 'A'
        assert _parse_rank('10.') == '10'

    def test_ocr_misreads(self):
        assert _parse_rank('O') == '10'
        assert _parse_rank('0') == '10'
        assert _parse_rank('S') == '5'
        assert _parse_rank('B') == '8'
        assert _parse_rank('G') == '6'

    def test_ten_misreads(self):
        """Common tesseract misreads of '10'."""
        assert _parse_rank('IN') == '10'
        assert _parse_rank('IO') == '10'
        assert _parse_rank('1O') == '10'
        assert _parse_rank('1N') == '10'
        assert _parse_rank('LO') == '10'
        assert _parse_rank('L0') == '10'
        assert _parse_rank('I0') == '10'
        assert _parse_rank('1Q') == '10'
        # Standalone "1" or "I" → 10 (no single-digit "1" card)
        assert _parse_rank('I') == '10'
        assert _parse_rank('1') == '10'
        assert _parse_rank('L') == '10'

    def test_empty(self):
        assert _parse_rank('') is None
        assert _parse_rank(None) is None

    def test_garbage(self):
        assert _parse_rank('xyz') is None
        assert _parse_rank('---') is None


class TestDetectSuit:
    def _make_patch(self, fg_rgb, bg_rgb=(255, 255, 255), size=20, fg_frac=0.5):
        """Create a test image with colored foreground on white background."""
        img = np.ones((size, size, 3), dtype=np.uint8) * np.array(bg_rgb, dtype=np.uint8)
        s = int(size * (1 - fg_frac) / 2)
        e = size - s
        img[s:e, s:e] = np.array(fg_rgb, dtype=np.uint8)
        return img

    def test_spades_black(self):
        img = self._make_patch((15, 15, 15))
        assert _detect_suit_at(img, (0, 0, 20, 20)) == 'S'

    def test_hearts_red(self):
        img = self._make_patch((220, 30, 30))
        assert _detect_suit_at(img, (0, 0, 20, 20)) == 'H'

    def test_diamonds_blue(self):
        img = self._make_patch((30, 70, 220))
        assert _detect_suit_at(img, (0, 0, 20, 20)) == 'D'

    def test_clubs_green(self):
        img = self._make_patch((30, 180, 50))
        assert _detect_suit_at(img, (0, 0, 20, 20)) == 'C'

    def test_all_white_returns_unknown(self):
        img = np.ones((20, 20, 3), dtype=np.uint8) * 255
        assert _detect_suit_at(img, (0, 0, 20, 20)) == '?'

    def test_empty_region(self):
        img = np.zeros((5, 5, 3), dtype=np.uint8)
        assert _detect_suit_at(img, (0, 0, 0, 0)) == '?'


class TestFindCardPositions:
    def _make_table(self, W=1300, H=900,
                    left_card=(540, 520, 110, 200),
                    right_card=(635, 520, 110, 200)):
        """Create a synthetic table image with two white cards."""
        img = np.zeros((H, W, 3), dtype=np.uint8)
        img[:, :] = [34, 85, 34]  # Green felt

        lx, ly, lw, lh = left_card
        img[ly:ly + lh, lx:lx + lw] = 240

        rx, ry, rw, rh = right_card
        img[ry:ry + rh, rx:rx + rw] = 240

        return img

    def test_finds_card_area(self):
        img = self._make_table()
        pos = _find_card_positions(img, 1300, 900)
        assert pos is not None
        assert 'left_rank' in pos
        assert 'right_rank' in pos

    def test_returns_none_without_cards(self):
        img = np.zeros((900, 1300, 3), dtype=np.uint8)
        img[:, :] = [34, 85, 34]  # Just green felt
        pos = _find_card_positions(img, 1300, 900)
        assert pos is None

    def test_left_rank_before_right(self):
        img = self._make_table()
        pos = _find_card_positions(img, 1300, 900)
        assert pos is not None
        assert pos['left_rank'][0] < pos['right_rank'][0]

    def test_different_table_sizes(self):
        """Detection should work at different table resolutions."""
        for W, H, lx, ly, lw, lh in [
            (1700, 1228, 740, 730, 120, 210),
            (1698, 1228, 725, 730, 120, 210),
            (1300, 900, 540, 520, 110, 200),
            (1600, 1200, 640, 680, 115, 205),
        ]:
            img = np.zeros((H, W, 3), dtype=np.uint8)
            img[:, :] = [34, 85, 34]
            # Left card
            img[ly:ly + lh, lx:lx + lw] = 240
            # Right card (overlapping)
            rx = lx + int(lw * 0.85)
            img[ly:ly + lh, rx:rx + lw] = 240

            pos = _find_card_positions(img, W, H)
            assert pos is not None, f"Failed for {W}x{H}"

    def test_face_down_returns_none(self):
        """Cards face-down (dark red backs) should not be detected."""
        img = np.zeros((900, 1300, 3), dtype=np.uint8)
        img[:, :] = [34, 85, 34]
        # Dark red card backs
        img[520:720, 540:650] = [80, 20, 20]
        img[520:720, 635:745] = [80, 20, 20]
        pos = _find_card_positions(img, 1300, 900)
        assert pos is None


class TestDetectSuitColored:
    """Test suit detection from card background color (colored deck)."""

    def _make_colored_card(self, bg_rgb, size=40):
        """Create a card with colored background and some white text pixels."""
        img = np.zeros((size, size, 3), dtype=np.uint8)
        img[:, :] = bg_rgb
        # Add white text-like pixels (10% of area)
        s = size // 4
        img[s:s + 5, s:s + 8] = [240, 240, 240]
        return img

    def test_blue_diamonds(self):
        img = self._make_colored_card((30, 70, 180))
        assert _detect_suit_colored(img, (0, 0, 40, 40)) == 'D'

    def test_red_hearts(self):
        img = self._make_colored_card((200, 40, 40))
        assert _detect_suit_colored(img, (0, 0, 40, 40)) == 'H'

    def test_green_clubs(self):
        img = self._make_colored_card((30, 160, 40))
        assert _detect_suit_colored(img, (0, 0, 40, 40)) == 'C'

    def test_black_spades(self):
        img = self._make_colored_card((20, 20, 20))
        assert _detect_suit_colored(img, (0, 0, 40, 40)) == 'S'


class TestFindColoredCards:
    """Test colored card blob detection doesn't match green felt."""

    def _make_colored_table(self, card_rgb, W=1300, H=900):
        """Create a table with colored cards (white text on colored bg)."""
        img = np.zeros((H, W, 3), dtype=np.uint8)
        img[:, :] = [34, 85, 34]  # Green felt
        # Two overlapping colored cards in search band
        lx, ly, lw, lh = 540, 520, 110, 160
        img[ly:ly + lh, lx:lx + lw] = card_rgb
        rx = lx + int(lw * 0.85)
        img[ly:ly + lh, rx:rx + lw] = card_rgb
        # Add white text pixels on cards (rank/suit)
        img[ly + 10:ly + 30, lx + 10:lx + 30] = [240, 240, 240]
        img[ly + 10:ly + 30, rx + 10:rx + 30] = [240, 240, 240]
        return img

    def test_blue_cards_detected(self):
        img = self._make_colored_table((30, 70, 180))
        pos = _find_card_positions(img, 1300, 900)
        assert pos is not None
        assert pos.get('_deck_style') == 'colored'

    def test_red_cards_detected(self):
        img = self._make_colored_table((200, 40, 40))
        pos = _find_card_positions(img, 1300, 900)
        assert pos is not None
        assert pos.get('_deck_style') == 'colored'

    def test_green_felt_not_detected(self):
        """Pure green felt (no cards) should not produce colored card results."""
        img = np.zeros((900, 1300, 3), dtype=np.uint8)
        img[:, :] = [34, 85, 34]
        pos = _find_card_positions(img, 1300, 900)
        assert pos is None

    def test_dark_red_backs_not_detected(self):
        """Dark red card backs should not be detected as colored cards."""
        img = np.zeros((900, 1300, 3), dtype=np.uint8)
        img[:, :] = [34, 85, 34]
        # Dark red backs with no white text
        img[520:680, 540:650] = [80, 20, 20]
        img[520:680, 635:745] = [80, 20, 20]
        pos = _find_card_positions(img, 1300, 900)
        assert pos is None


class TestReadPlayerCards:
    def test_returns_empty_for_green_felt(self):
        """No cards visible = empty list."""
        img = Image.new('RGB', (1300, 900), (34, 85, 34))
        assert read_player_cards(img) == []

    def test_returns_empty_for_face_down(self):
        """Face-down cards (dark red) = empty list."""
        img_np = np.zeros((900, 1300, 3), dtype=np.uint8)
        img_np[:, :] = [34, 85, 34]
        img_np[520:720, 540:650] = [100, 30, 30]
        img_np[520:720, 635:745] = [100, 30, 30]
        img = Image.fromarray(img_np)
        assert read_player_cards(img) == []
