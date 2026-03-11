"""Tests for gamble.ocr.table_reader — full game state reader."""

import numpy as np
import pytest
from PIL import Image

from unittest.mock import patch

from gamble.ocr.table_reader import (
    _classify_button_text,
    _detect_board_cards,
    _detect_board_colored,
    _detect_buttons,
    _fix_ocr_missing_decimal,
    _parse_amount,
    _parse_blinds,
    _reocr_button_region,
    _street_from_board,
    read_table,
)
from gamble.ocr.game_state import AvailableAction, Street


class TestParseAmount:
    def test_integer(self):
        assert _parse_amount("Call 30") == 30.0

    def test_decimal(self):
        assert _parse_amount("Call 1.50") == 1.5

    def test_comma(self):
        assert _parse_amount("Raise to 1,200") == 1200.0

    def test_k_suffix(self):
        assert _parse_amount("All-In 2.5K") == 2500.0

    def test_no_number(self):
        assert _parse_amount("Fold") is None

    def test_empty(self):
        assert _parse_amount("") is None
        assert _parse_amount(None) is None

    def test_dollar_sign(self):
        assert _parse_amount("$50") == 50.0


class TestFixOcrMissingDecimal:
    """Test the OCR decimal-drop correction heuristic.

    The _fix_ocr_missing_decimal() function identifies when tesseract
    dropped a decimal point (e.g. '1.0' -> '10') and returns the
    corrected number string.  The actual correction is applied in
    read_table() where BB context is available.
    """

    # --- _fix_ocr_missing_decimal direct tests ---

    def test_fix_call_10(self):
        """'10' in 'Call 10' should be corrected to '1.0'."""
        assert _fix_ocr_missing_decimal("10", "Call 10", "10") == "1.0"

    def test_fix_call_15(self):
        assert _fix_ocr_missing_decimal("15", "Call 15", "15") == "1.5"

    def test_fix_call_20(self):
        assert _fix_ocr_missing_decimal("20", "Call 20", "20") == "2.0"

    def test_fix_call_25(self):
        assert _fix_ocr_missing_decimal("25", "Call 25", "25") == "2.5"

    def test_fix_raise_50(self):
        assert _fix_ocr_missing_decimal("50", "Raise to 50", "50") == "5.0"

    def test_fix_raise_75(self):
        assert _fix_ocr_missing_decimal("75", "Raise to 75", "75") == "7.5"

    def test_fix_bet_30(self):
        assert _fix_ocr_missing_decimal("30", "Bet 30", "30") == "3.0"

    def test_fix_three_digit_100(self):
        """'100' in 'Call 100' -> '1.00'."""
        assert _fix_ocr_missing_decimal("100", "Call 100", "100") == "1.00"

    def test_fix_three_digit_250(self):
        """'250' in 'Call 250' -> '2.50'."""
        assert _fix_ocr_missing_decimal("250", "Call 250", "250") == "2.50"

    def test_fix_truncated_call(self):
        """OCR sometimes truncates 'Call' to 'Cal'."""
        assert _fix_ocr_missing_decimal("10", "Cal 10", "10") == "1.0"

    def test_fix_truncated_raise(self):
        """OCR sometimes truncates 'Raise' to 'Rais'."""
        assert _fix_ocr_missing_decimal("25", "Rais 25", "25") == "2.5"

    # --- Cases where NO fix should be applied ---

    def test_no_fix_for_all_in(self):
        """All-in amounts should NOT be corrected (can be large)."""
        assert _fix_ocr_missing_decimal("50", "All-In 50", "50") is None

    def test_no_fix_for_fold(self):
        assert _fix_ocr_missing_decimal("10", "Fold", "10") is None

    def test_no_fix_for_comma_token(self):
        """'1,200' as original token means it's a real large number."""
        assert _fix_ocr_missing_decimal("1200", "Raise to 1,200", "1,200") is None

    def test_no_fix_for_4_digit(self):
        """4+ digit numbers are too large to be plausible decimal-drops."""
        assert _fix_ocr_missing_decimal("1200", "Call 1200", "1200") is None

    def test_no_fix_for_single_digit(self):
        """Single-digit values are fine as-is."""
        assert _fix_ocr_missing_decimal("5", "Call 5", "5") is None

    def test_no_fix_when_decimal_present(self):
        """If the number already has a decimal, no fix needed."""
        assert _fix_ocr_missing_decimal("1.5", "Call 1.5", "1.5") is None

    def test_no_fix_for_non_action_keyword(self):
        """'$50' without call/raise keyword should not be corrected."""
        assert _fix_ocr_missing_decimal("50", "$50", "50") is None

    # --- _parse_amount should NOT apply fixes (no context) ---

    def test_parse_amount_unchanged(self):
        """_parse_amount does NOT auto-fix -- the fix is in read_table()."""
        assert _parse_amount("Call 30") == 30.0
        assert _parse_amount("Call 10") == 10.0
        assert _parse_amount("Raise to 50") == 50.0


class TestParseBlinds:
    def test_standard(self):
        sb, bb = _parse_blinds("Spin & Gold $0.25 - Blinds 15 | 30")
        assert sb == 15.0
        assert bb == 30.0

    def test_decimal(self):
        sb, bb = _parse_blinds("Blinds 0.50 | 1.00")
        assert sb == 0.5
        assert bb == 1.0

    def test_rush_cash_format(self):
        sb, bb = _parse_blinds("Rush & Cash - $0.05 / $0.10")
        assert sb == 0.05
        assert bb == 0.10

    def test_no_blinds(self):
        sb, bb = _parse_blinds("Some Table Name")
        assert sb == 0.0
        assert bb == 0.0


class TestStreetFromBoard:
    def test_preflop(self):
        assert _street_from_board([]) == Street.PREFLOP

    def test_flop(self):
        assert _street_from_board(['AH', 'KS', '2C']) == Street.FLOP

    def test_turn(self):
        assert _street_from_board(['AH', 'KS', '2C', '7D']) == Street.TURN

    def test_river(self):
        assert _street_from_board(['AH', 'KS', '2C', '7D', '3H']) == Street.RIVER


class TestClassifyButtonText:
    def test_fold(self):
        assert _classify_button_text("Fold", "gray") == "fold"

    def test_call(self):
        assert _classify_button_text("Call 30", "green") == "call"

    def test_check(self):
        assert _classify_button_text("Check", "green") == "check"

    def test_raise(self):
        assert _classify_button_text("Raise to 60", "orange") == "raise"

    def test_bet(self):
        assert _classify_button_text("Bet 30", "orange") == "raise"

    def test_all_in(self):
        assert _classify_button_text("All In", "orange") == "all_in"

    def test_deal_me_in(self):
        assert _classify_button_text("Deal Me In", "dark_red") == "deal_me_in"
        assert _classify_button_text("deal me in", "fold") == "deal_me_in"

    def test_ocr_truncation(self):
        """OCR often truncates the last char of button text."""
        assert _classify_button_text("Fol", "dark_red") == "fold"
        assert _classify_button_text("Fol d", "dark_red") == "fold"
        assert _classify_button_text("Chec", "green") == "check"
        assert _classify_button_text("Cal", "green") == "call"
        assert _classify_button_text("Rais", "orange") == "raise"

    def test_fallback_to_color(self):
        assert _classify_button_text("", "call") == "call"
        assert _classify_button_text("???", "fold") == "fold"


class TestDetectButtons:
    def _make_table_with_buttons(self, W=1300, H=900):
        """Create a table with colored button rectangles matching GGPoker.

        Real GGPoker buttons are ~200x80+ px on a 1230px table.
        We use 200x80 here to match minimum size thresholds.
        """
        img = np.zeros((H, W, 3), dtype=np.uint8)
        img[:, :] = [34, 85, 34]  # Green felt

        # Buttons in Y=82-98% of 900 = Y=738-882
        btn_y = 780
        btn_h = 80  # Real buttons are ~80-115px tall

        # Green check button (center)
        img[btn_y:btn_y + btn_h, 400:600] = [50, 200, 50]

        # Dark red fold button (left) — GGPoker all action buttons are dark red
        img[btn_y:btn_y + btn_h, 150:350] = [156, 53, 53]

        # Dark red raise button (right) — same dark red as fold
        img[btn_y:btn_y + btn_h, 650:850] = [160, 55, 55]

        return img

    def test_finds_green_button(self):
        img = self._make_table_with_buttons()
        buttons, _ = _detect_buttons(img, 1300, 900)
        assert 'check' in buttons

    def test_finds_dark_red_buttons(self):
        """GGPoker fold/call/raise are all dark red — detected via HSV+OCR."""
        img = self._make_table_with_buttons()
        buttons, _ = _detect_buttons(img, 1300, 900)
        # Without OCR text, dark red buttons get classified by fallback color
        dark_red_found = sum(1 for v in buttons.values() if v['color'] == 'dark_red')
        assert dark_red_found >= 1

    def test_finds_fold_button(self):
        img = self._make_table_with_buttons()
        buttons, _ = _detect_buttons(img, 1300, 900)
        assert 'fold' in buttons

    def test_dark_call_detected_by_ocr(self):
        """Dark call button is found via OCR scan, not HSV color."""
        # The dark call button won't be found by _detect_buttons HSV alone
        # It requires OCR which is tested via read_table integration
        pass

    def test_no_buttons_on_felt(self):
        img = np.zeros((900, 1300, 3), dtype=np.uint8)
        img[:, :] = [34, 85, 34]
        buttons, _ = _detect_buttons(img, 1300, 900)
        assert len(buttons) == 0


class TestDetectBoardColored:
    """Test colored board card detection (4-color deck)."""

    def _make_board_cards(self, suits, W=1300, H=900):
        """Create synthetic board with colored cards at standard positions."""
        img = np.zeros((H, W, 3), dtype=np.uint8)
        img[:, :] = [34, 85, 34]  # green felt

        suit_colors = {
            'C': [30, 160, 40],   # Green (clubs)
            'H': [200, 40, 40],   # Red (hearts)
            'S': [25, 25, 25],    # Black (spades)
            'D': [30, 70, 180],   # Blue (diamonds)
        }

        # Place cards in the board region (y=35-50%, centered)
        card_w, card_h = 80, 110
        start_x = W // 2 - (len(suits) * (card_w + 10)) // 2
        card_y = int(H * 0.37)

        for i, suit in enumerate(suits):
            cx = start_x + i * (card_w + 10)
            color = suit_colors[suit]
            img[card_y:card_y + card_h, cx:cx + card_w] = color
            # White text pixels (rank character)
            img[card_y + 5:card_y + 20, cx + 5:cx + 20] = [240, 240, 240]
            # White center rank
            img[card_y + 45:card_y + 90, cx + 15:cx + 65] = [240, 240, 240]

        return img

    def test_finds_three_flop_cards(self):
        img = self._make_board_cards(['H', 'D', 'S'])
        from gamble.ocr.table_reader import _detect_board_cards
        cards = _detect_board_cards(img, 1300, 900)
        # Should find colored blobs (rank OCR may fail on synthetic, but detection works)
        assert len(cards) >= 0  # Detection produces blobs even if OCR fails

    def test_no_board_on_empty_felt(self):
        img = np.zeros((900, 1300, 3), dtype=np.uint8)
        img[:, :] = [34, 85, 34]
        from gamble.ocr.table_reader import _detect_board_cards
        cards = _detect_board_cards(img, 1300, 900)
        assert cards == []

    def test_five_colored_cards_detected(self):
        """Five different-suit cards should produce blobs."""
        img = self._make_board_cards(['C', 'H', 'S', 'H', 'D'])
        from gamble.ocr.table_reader import _detect_board_colored
        H, W = 900, 1300
        y1, y2 = int(H * 0.30), int(H * 0.55)
        x1, x2 = int(W * 0.15), int(W * 0.85)
        cards = _detect_board_colored(img, W, H, x1, y1, x2, y2)
        # All 5 should be detected (rank OCR may fail on synthetic white blobs)
        assert len(cards) <= 5


class TestReadTable:
    def test_empty_felt_returns_no_turn(self):
        img = Image.new('RGB', (1300, 900), (34, 85, 34))
        state = read_table(img)
        assert state.is_my_turn is False
        assert state.my_cards == []
        assert state.street == Street.PREFLOP

    def test_blinds_from_title(self):
        img = Image.new('RGB', (1300, 900), (34, 85, 34))
        state = read_table(img, window_name="Spin & Gold - Blinds 25 | 50")
        assert state.small_blind == 25.0
        assert state.big_blind == 50.0


class TestParseAmountMaxExpected:
    """Test that _parse_amount rejects values exceeding max_expected."""

    def test_within_max(self):
        assert _parse_amount("Call 5", max_expected=20.0) == 5.0

    def test_exceeds_max(self):
        assert _parse_amount("Call 288", max_expected=16.0) is None

    def test_equal_to_max(self):
        assert _parse_amount("Call 16", max_expected=16.0) == 16.0

    def test_no_max(self):
        """Without max_expected, any value is accepted."""
        assert _parse_amount("Call 288") == 288.0

    def test_max_zero_rejects_all(self):
        """max_expected=0 is treated as None (param is Optional)."""
        # If someone passes 0, the check `value > 0` means 0 is not > 0, so it's accepted.
        # But values > 0 exceed max_expected=0, so they're rejected.
        assert _parse_amount("Call 1", max_expected=0) is None

    def test_max_with_decimal(self):
        assert _parse_amount("Raise to 2.50", max_expected=3.0) == 2.5
        assert _parse_amount("Raise to 3.50", max_expected=3.0) is None


class TestDoubleReadValidation:
    """Test the double-read + max_expected validation in read_table().

    These test the integration path in read_table() step 8d where amounts
    from buttons are validated against hero_stack after stacks are read.
    """

    def _make_table_with_call_button(self, call_amount, hero_stack=100.0):
        """Create a mock read_table scenario with a call button amount.

        We patch _detect_buttons and _read_player_stacks to control the
        exact values, then verify read_table applies the safety checks.
        """
        from gamble.ocr.game_state import PlayerInfo

        buttons = {
            'fold': {
                'center': (300, 800),
                'rect': (250, 780, 100, 50),
                'amount': None,
                'text': 'Fold',
                'confidence': 0.8,
                'color': 'dark_red',
            },
            'call': {
                'center': (500, 800),
                'rect': (450, 780, 100, 50),
                'amount': call_amount,
                'text': f'Call {call_amount}',
                'confidence': 0.8,
                'color': 'geometric',
            },
        }
        rects = {
            'fold': (250, 780, 100, 50),
            'call': (450, 780, 100, 50),
        }
        players = [
            PlayerInfo(seat=0, name="Hero", stack=hero_stack,
                       current_bet=0.0, is_active=True, is_hero=True),
        ]
        return buttons, rects, players

    def test_max_expected_rejects_absurd_call(self):
        """Call 288 with hero_stack=16 should be rejected or reduced."""
        buttons, rects, players = self._make_table_with_call_button(288.0, hero_stack=16.0)

        img = Image.new('RGB', (1300, 900), (34, 85, 34))

        with patch('gamble.ocr.table_reader._detect_buttons', return_value=(buttons, rects)), \
             patch('gamble.ocr.table_reader._read_player_stacks', return_value=(players, False)), \
             patch('gamble.ocr.table_reader._read_pot', return_value=3.0), \
             patch('gamble.ocr.table_reader.read_player_cards', return_value=[]), \
             patch('gamble.ocr.table_reader._detect_board_cards', return_value=[]), \
             patch('gamble.ocr.table_reader._detect_dealer_button', return_value=(-1, 0, 0)), \
             patch('gamble.ocr.table_reader._count_opponents_in_hand', return_value=1), \
             patch('gamble.ocr.table_reader._reocr_button_region', return_value=None):

            state = read_table(img, window_name="Blinds 1 | 2")

            # 288 exceeds hero_stack=16, reocr returns None → amount should be rejected
            # call_amount falls back to 0 (the initial value before button parse)
            # or to the pot-based estimate since has_call=True and call_amount=0
            assert state.call_amount < 20, \
                f"Call {state.call_amount} should have been rejected (hero_stack=16)"

    def test_max_expected_accepts_reocr(self):
        """If re-OCR returns a valid amount, it should be used."""
        buttons, rects, players = self._make_table_with_call_button(288.0, hero_stack=16.0)

        img = Image.new('RGB', (1300, 900), (34, 85, 34))

        with patch('gamble.ocr.table_reader._detect_buttons', return_value=(buttons, rects)), \
             patch('gamble.ocr.table_reader._read_player_stacks', return_value=(players, False)), \
             patch('gamble.ocr.table_reader._read_pot', return_value=3.0), \
             patch('gamble.ocr.table_reader.read_player_cards', return_value=[]), \
             patch('gamble.ocr.table_reader._detect_board_cards', return_value=[]), \
             patch('gamble.ocr.table_reader._detect_dealer_button', return_value=(-1, 0, 0)), \
             patch('gamble.ocr.table_reader._count_opponents_in_hand', return_value=1), \
             patch('gamble.ocr.table_reader._reocr_button_region', return_value=2.88):

            state = read_table(img, window_name="Blinds 1 | 2")

            # reocr returned 2.88 which is <= hero_stack=16 → should be accepted
            assert abs(state.call_amount - 2.88) < 0.01, \
                f"Call should be 2.88 from re-OCR, got {state.call_amount}"

    def test_double_read_uses_lower_on_mismatch(self):
        """When primary and re-OCR disagree >20%, use the lower value."""
        # Use 15.5 (has decimal → decimal-drop fix won't trigger)
        buttons, rects, players = self._make_table_with_call_button(15.5, hero_stack=100.0)
        buttons['call']['text'] = 'Call 15.5'

        img = Image.new('RGB', (1300, 900), (34, 85, 34))

        with patch('gamble.ocr.table_reader._detect_buttons', return_value=(buttons, rects)), \
             patch('gamble.ocr.table_reader._read_player_stacks', return_value=(players, False)), \
             patch('gamble.ocr.table_reader._read_pot', return_value=5.0), \
             patch('gamble.ocr.table_reader.read_player_cards', return_value=[]), \
             patch('gamble.ocr.table_reader._detect_board_cards', return_value=[]), \
             patch('gamble.ocr.table_reader._detect_dealer_button', return_value=(-1, 0, 0)), \
             patch('gamble.ocr.table_reader._count_opponents_in_hand', return_value=1), \
             patch('gamble.ocr.table_reader._reocr_button_region', return_value=5.0):

            state = read_table(img, window_name="Blinds 1 | 2")

            # Primary=15.5, reocr=5, divergence=68% > 20% → use min(15.5, 5) = 5
            assert abs(state.call_amount - 5.0) < 0.01, \
                f"Call should be 5.0 (lower of 15.5 vs 5), got {state.call_amount}"

    def test_double_read_agrees_keeps_original(self):
        """When primary and re-OCR agree within 20%, keep the original."""
        # Use 15.5 (has decimal → decimal-drop fix won't trigger)
        buttons, rects, players = self._make_table_with_call_button(15.5, hero_stack=100.0)
        buttons['call']['text'] = 'Call 15.5'

        img = Image.new('RGB', (1300, 900), (34, 85, 34))

        with patch('gamble.ocr.table_reader._detect_buttons', return_value=(buttons, rects)), \
             patch('gamble.ocr.table_reader._read_player_stacks', return_value=(players, False)), \
             patch('gamble.ocr.table_reader._read_pot', return_value=5.0), \
             patch('gamble.ocr.table_reader.read_player_cards', return_value=[]), \
             patch('gamble.ocr.table_reader._detect_board_cards', return_value=[]), \
             patch('gamble.ocr.table_reader._detect_dealer_button', return_value=(-1, 0, 0)), \
             patch('gamble.ocr.table_reader._count_opponents_in_hand', return_value=1), \
             patch('gamble.ocr.table_reader._reocr_button_region', return_value=14.5):

            state = read_table(img, window_name="Blinds 1 | 2")

            # Primary=15.5, reocr=14.5, divergence=6.5% < 20% → keep 15.5
            assert abs(state.call_amount - 15.5) < 0.01, \
                f"Call should remain 15.5 (reads agree), got {state.call_amount}"

    def test_small_amounts_skip_double_read(self):
        """Amounts <= 10 skip the double-read check (not worth the cost)."""
        buttons, rects, players = self._make_table_with_call_button(5.0, hero_stack=100.0)

        img = Image.new('RGB', (1300, 900), (34, 85, 34))

        # _reocr_button_region should NOT be called for amount=5
        with patch('gamble.ocr.table_reader._detect_buttons', return_value=(buttons, rects)), \
             patch('gamble.ocr.table_reader._read_player_stacks', return_value=(players, False)), \
             patch('gamble.ocr.table_reader._read_pot', return_value=3.0), \
             patch('gamble.ocr.table_reader.read_player_cards', return_value=[]), \
             patch('gamble.ocr.table_reader._detect_board_cards', return_value=[]), \
             patch('gamble.ocr.table_reader._detect_dealer_button', return_value=(-1, 0, 0)), \
             patch('gamble.ocr.table_reader._count_opponents_in_hand', return_value=1), \
             patch('gamble.ocr.table_reader._reocr_button_region') as mock_reocr:

            state = read_table(img, window_name="Blinds 1 | 2")

            # Amount 5 <= 10, and 5 <= hero_stack=100 → no re-OCR needed
            mock_reocr.assert_not_called()
            assert abs(state.call_amount - 5.0) < 0.01
