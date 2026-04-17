"""_fix_stack_decimal tests using bug examples from session logs."""
import pytest

from sys_core.ocr.table_reader import _fix_stack_decimal


# --- Stack decimal fixes (from real session logs) -----------------------------

def test_8959_to_89_59():
    """Hero stack OCR'd as 8959 BB on a $0.01/$0.02 table — real ~89.59."""
    assert _fix_stack_decimal(8959) == pytest.approx(89.59, abs=0.01)


def test_9959_to_99_59():
    assert _fix_stack_decimal(9959) == pytest.approx(99.59, abs=0.01)


def test_9859_to_98_59():
    assert _fix_stack_decimal(9859) == pytest.approx(98.59, abs=0.01)


def test_8590_to_85_9():
    """Decimal fully lost: 85.9 → 8590."""
    assert _fix_stack_decimal(8590) == pytest.approx(85.9, abs=0.01)


def test_already_plausible_unchanged():
    """No fix needed for values in plausible range."""
    assert _fix_stack_decimal(89) == 89
    assert _fix_stack_decimal(689.5) == 689.5
    assert _fix_stack_decimal(150) == 150


def test_picks_closest_to_typical_buyin():
    """1234 has 3 candidates: 1.234, 12.34, 123.4. Pick closest to 100."""
    assert _fix_stack_decimal(1234) == pytest.approx(123.4, abs=0.01)


def test_custom_prefer_near_for_bets():
    """When tuning for bets (prefer near 5 BB), 255 should pick 2.55."""
    assert _fix_stack_decimal(255, plausible_min=0.25, plausible_max=200,
                               prefer_near=5.0) == pytest.approx(2.55, abs=0.01)


def test_custom_prefer_near_for_bets_550():
    """550 BB bet → real 5.50 BB."""
    assert _fix_stack_decimal(550, plausible_min=0.25, plausible_max=200,
                               prefer_near=5.0) == pytest.approx(5.50, abs=0.01)
