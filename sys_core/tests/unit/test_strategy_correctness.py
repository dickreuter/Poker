"""Strategy correctness tests for GTO preflop decisions.

Validates that gto_preflop_decision() returns correct actions for
known preflop spots across different positions and stack depths.
"""

import pytest
from sys_core.decisionmaker.decisionmaker import gto_preflop_decision, _normalize_hand


class TestNormalizeHand:
    """Test hand normalization logic."""

    def test_pair(self):
        assert _normalize_hand('AA', 'AA') == 'AA'

    def test_suited(self):
        assert _normalize_hand('AKS', 'AKS') == 'AKS'

    def test_offsuit(self):
        assert _normalize_hand('AKO', 'AKO') == 'AKO'

    def test_order_normalization(self):
        """Higher rank should come first."""
        result = _normalize_hand('KAS', 'KAS')
        assert result == 'AKS'

    def test_pair_from_second_arg(self):
        assert _normalize_hand('', 'QQ') == 'QQ'


class TestPremiumShield:
    """Premium hands should NEVER be folded preflop to a single raise."""

    PREMIUMS = ['AA', 'KK', 'QQ', 'JJ', 'TT', '99', 'AKS', 'AKO', 'AQS', 'AQO', 'AJS', 'KQS']

    @pytest.mark.parametrize("hand", PREMIUMS)
    def test_premium_never_folds_facing_raise(self, hand):
        """Premium hands must call or raise vs a single raise."""
        result = gto_preflop_decision(
            hand, hand, 'CO',
            has_raiser=True, call_amount=3.0,
            has_check=False, hero_stack=100.0
        )
        assert result in ('call', 'raise'), \
            f"Premium {hand} folded facing raise! Got: {result}"

    @pytest.mark.parametrize("hand", PREMIUMS)
    def test_premium_never_folds_any_position(self, hand):
        """Premiums should not fold from any position."""
        for pos in ('UTG', 'MP', 'CO', 'BTN', 'SB', 'BB'):
            result = gto_preflop_decision(
                hand, hand, pos,
                has_raiser=True, call_amount=3.0,
                has_check=False, hero_stack=100.0
            )
            assert result in ('call', 'raise'), \
                f"Premium {hand} from {pos} folded! Got: {result}"


class TestOpenRaise:
    """Test open-raise decisions (first to act, no raiser)."""

    @pytest.mark.parametrize("hand,position,expected", [
        # Strong hands should raise from any position
        ('AA', 'UTG', 'raise'),
        ('KK', 'MP', 'raise'),
        ('AKS', 'CO', 'raise'),
        ('AKO', 'BTN', 'raise'),
        ('QQ', 'SB', 'raise'),

        # Medium hands open from late position
        ('ATS', 'BTN', 'raise'),
        ('KJS', 'CO', 'raise'),

        # Weak hands fold from early position
        ('72O', 'UTG', 'fold'),
        ('83O', 'MP', 'fold'),
        ('J2O', 'UTG', 'fold'),
    ])
    def test_open_raise_decisions(self, hand, position, expected):
        result = gto_preflop_decision(
            hand, hand, position,
            has_raiser=False, call_amount=0,
            has_check=False, hero_stack=100.0
        )
        assert result == expected, \
            f"Open {hand} from {position}: got {result}, expected {expected}"


class TestFacingRaise:
    """Test decisions when facing a raise."""

    @pytest.mark.parametrize("hand,position,expected_options", [
        # Premium: always call or raise
        ('AA', 'BTN', {'call', 'raise'}),
        ('KK', 'CO', {'call', 'raise'}),
        ('AKS', 'SB', {'call', 'raise'}),

        # Trash: always fold
        ('72O', 'BTN', {'fold'}),
        ('83O', 'CO', {'fold'}),
        ('J2O', 'SB', {'fold'}),
    ])
    def test_facing_raise_correct(self, hand, position, expected_options):
        result = gto_preflop_decision(
            hand, hand, position,
            has_raiser=True, call_amount=3.0,
            has_check=False, hero_stack=100.0
        )
        assert result in expected_options, \
            f"{hand} from {position} vs raise: got {result}, expected one of {expected_options}"


class TestBBDefend:
    """Test BB defense range."""

    def test_bb_checks_unraised(self):
        """BB should check in unraised pot with weak hands."""
        result = gto_preflop_decision(
            '72O', '72O', 'BB',
            has_raiser=False, call_amount=0,
            has_check=True, hero_stack=100.0
        )
        assert result == 'check', f"BB with 72o unraised should check, got {result}"

    def test_bb_raises_strong_unraised(self):
        """BB should raise strong hands in unraised pot."""
        result = gto_preflop_decision(
            'AKS', 'AKS', 'BB',
            has_raiser=False, call_amount=0,
            has_check=True, hero_stack=100.0
        )
        assert result in ('raise', 'check'), f"BB with AKs unraised got {result}"

    def test_bb_defends_suited_connectors(self):
        """BB should defend suited connectors vs standard raise."""
        # 98s is in GTO_BB_DEFEND
        result = gto_preflop_decision(
            '98S', '98S', 'BB',
            has_raiser=True, call_amount=2.5,
            has_check=False, hero_stack=100.0
        )
        assert result in ('call', 'raise'), \
            f"BB with 98s vs 2.5x should defend, got {result}"


class TestNashPushFold:
    """Test Nash push/fold ranges for short stacks."""

    def test_nash_ranges_importable(self):
        """Nash tables should be importable."""
        from sys_core.decisionmaker.range_equity import NASH_SHOVE_RANGES, CALL_RANGES_VS_SHOVE
        assert 'UTG' in NASH_SHOVE_RANGES
        assert 'BTN' in NASH_SHOVE_RANGES
        assert 'SB' in NASH_SHOVE_RANGES
        assert 'BB' in CALL_RANGES_VS_SHOVE

    def test_nash_all_positions_have_3bb(self):
        """All positions should have 3BB shove range."""
        from sys_core.decisionmaker.range_equity import NASH_SHOVE_RANGES
        for pos in ('UTG', 'MP', 'CO', 'BTN', 'SB'):
            assert 3 in NASH_SHOVE_RANGES[pos], f"{pos} missing 3BB range"

    def test_nash_ranges_get_tighter_utg(self):
        """UTG ranges should be tighter than BTN at same stack depth."""
        from sys_core.decisionmaker.range_equity import NASH_SHOVE_RANGES
        # At 15BB, UTG should have fewer hands than BTN
        utg_range = NASH_SHOVE_RANGES['UTG'][15]
        btn_range = NASH_SHOVE_RANGES['BTN'][15]
        # Rough proxy: shorter range string = fewer hands
        assert len(utg_range) <= len(btn_range), \
            f"UTG range should be tighter than BTN at 15BB"


class TestMixedStrategy:
    """Test that bluff hands are correctly placed in 3-bet ranges."""

    def test_bluff_hands_3bet_when_in_range(self):
        """Bluff hands in 3-bet range should always raise (deterministic)."""
        # A5S is in GTO_3BET['vs_BTN'], so it should always 3-bet
        result = gto_preflop_decision(
            'A5S', 'A5S', 'BTN',
            has_raiser=True, call_amount=3.0,
            has_check=False, hero_stack=100.0
        )
        assert result == 'raise', \
            f"A5s (in 3-bet range) vs raise should raise, got {result}"

    def test_bluff_hands_in_3bet_ranges(self):
        """Standard bluff hands should appear in at least one 3-bet range."""
        from sys_core.decisionmaker.decisionmaker import GTO_3BET
        bluff_hands = {'A5S', 'A4S', 'A3S', '76S', '65S'}
        for hand in bluff_hands:
            found_in_range = any(hand in r for r in GTO_3BET.values())
            assert found_in_range, \
                f"Bluff hand {hand} not found in any 3-bet range"


class TestReturnValues:
    """Verify return value consistency."""

    VALID_RETURNS = {'raise', 'call', 'check', 'fold'}

    @pytest.mark.parametrize("hand,position", [
        ('AA', 'UTG'), ('72O', 'BTN'), ('AKS', 'BB'),
        ('55', 'SB'), ('QJO', 'CO'), ('T9S', 'MP'),
    ])
    def test_always_returns_valid_action(self, hand, position):
        """gto_preflop_decision must always return a valid action string."""
        for has_raiser in (True, False):
            for has_check in (True, False):
                result = gto_preflop_decision(
                    hand, hand, position,
                    has_raiser=has_raiser,
                    call_amount=3.0 if has_raiser else 0,
                    has_check=has_check,
                    hero_stack=100.0
                )
                assert result in self.VALID_RETURNS, \
                    f"Invalid return '{result}' for {hand}/{position}/raiser={has_raiser}/check={has_check}"
