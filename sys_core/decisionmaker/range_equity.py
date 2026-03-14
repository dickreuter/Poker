"""
Range-based equity calculator using eval7 and Nash Equilibrium.

STRATEGY ENGINES:
1. eval7 Integration:
   - Replaces traditional Monte Carlo (200-500ms) with high-speed (1-3ms) 
     exact or simulation-based equity calculation.
   - Automatically handles BLOCKERS (card removal) by evaluating our hole cards 
     against the opponent's full range string.
2. Board-Aware Filtering:
   - Evaluates each combo in the villain's range on the community cards.
   - Removes hands that are too weak to bet (based on board texture) to 
     calculate a realistic "Facing Action" equity.
3. Nash Equilibrium (Push/Fold):
   - Contains hardcoded optimal shove/call ranges for stacks ≤ 15 BB.
   - Ranges are derived from GTO solvers (HoldemResources/ICMIZER).
   - Dynamically selects the best range based on position and effective stack.
"""
import logging
import random
from typing import List, Optional, Tuple

log = logging.getLogger('decisionmaker')

try:
    import eval7
    HAS_EVAL7 = True
except ImportError:
    HAS_EVAL7 = False
    log.warning("eval7 not installed — range equity disabled. pip install eval7")


# ── Preflop ranges by position and action ──────────────────────────────────

# RFI (Raise First In) ranges by position
RFI_RANGES = {
    'UTG':  'TT+, ATs+, KQs, AJo+, KQo',                    # ~12%
    'MP':   '77+, A9s+, KJs+, QJs, JTs, T9s, ATo+, KQo',    # ~17%
    'CO':   '22+, A2s+, K9s+, Q9s+, J9s+, T8s+, 97s+, 87s, 76s, 65s, ATo+, KJo+, QJo',  # ~27%
    'BTN':  '22+, A2s+, K5s+, Q7s+, J8s+, T7s+, 96s+, 85s+, 75s+, 64s+, 54s, A2o+, K9o+, Q9o+, J9o+, T9o',  # ~40%
    'SB':   '22+, A2s+, K5s+, Q8s+, J8s+, T8s+, 97s+, 86s+, 75s+, 65s, 54s, A7o+, K9o+, QTo+, JTo',  # ~36%
    'BB':   '22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 96s+, 85s+, 74s+, 64s+, 53s+, 43s, A2o+, K5o+, Q8o+, J8o+, T8o+, 97o+, 87o',  # BB defend ~50%
}

# 3-bet ranges
THREE_BET_RANGES = {
    'vs_UTG':  'QQ+, AKs, AKo',                              # ~3%
    'vs_MP':   'QQ+, AKs, AKo, AQs',                         # ~4%
    'vs_CO':   'JJ+, AQs+, AKo, A5s-A2s',                    # ~6%
    'vs_BTN':  'TT+, ATs+, KQs, AQo+, A5s-A2s, 76s, 87s',  # ~9%
    'default': 'QQ+, AKs, AKo, AQs',                          # ~4%
}

# Ranges after calling preflop (flatted a raise)
CALL_RANGES = {
    'tight':   '22-TT, ATs-AQs, KQs, AJo-AQo, KQo',         # nit/TAG call
    'medium':  '22-JJ, A2s-AQs, KTs+, QTs+, JTs, T9s, 98s, ATo+, KJo+, QJo',  # standard
    'wide':    '22+, A2s+, K5s+, Q8s+, J8s+, T8s+, 97s+, 86s+, A2o+, K9o+, Q9o+',  # fish
}

# Postflop action ranges (narrowing)
# These are MULTIPLIERS on the existing range (1.0 = keep, 0.0 = remove)
# Applied to each hand based on its strength category
POSTFLOP_NARROWING = {
    'bet_small': {  # 25-40% pot — merged, many hands
        'monster': 0.7, 'strong': 1.0, 'medium': 1.0, 'weak': 0.5, 'air': 0.3,
    },
    'bet_large': {  # 66%+ pot — polarized
        'monster': 1.0, 'strong': 0.8, 'medium': 0.3, 'weak': 0.1, 'air': 0.4,
    },
    'check_call': {  # checking range is capped
        'monster': 0.3, 'strong': 0.7, 'medium': 1.0, 'weak': 0.8, 'air': 0.3,
    },
    'check_raise': {  # polarized — nuts or semi-bluff
        'monster': 1.0, 'strong': 0.3, 'medium': 0.1, 'weak': 0.0, 'air': 0.5,
    },
    'all_in': {  # very narrow and strong
        'monster': 1.0, 'strong': 0.6, 'medium': 0.1, 'weak': 0.0, 'air': 0.2,
    },
}

# ── Player type → range adjustment ─────────────────────────────────────────

# All range strings MUST be eval7-compatible (no descriptive words)
PLAYER_TYPE_RANGES = {
    'nit': {
        'open': 'TT+, AQs+, AKo',
        'call_preflop': '77-99, AJs-AQs, KQs, AQo',
        '3bet': 'QQ+, AKs',
        'flop_bet': 'TT+, AQs+, AKo',
        'turn_bet': 'JJ+, AQs+, AKo',
        'river_bet': 'QQ+, AKs, AKo',
        'all_in': 'QQ+, AKs',
    },
    'tag': {
        'open': '55+, A9s+, KTs+, QJs, JTs, ATo+, KQo',
        'call_preflop': '22-TT, ATs-AQs, KQs, AJo-AQo',
        '3bet': 'JJ+, AQs+, AKo',
        'flop_bet': '55+, A9s+, KTs+, QJs, ATo+, KQo',
        'turn_bet': '77+, ATs+, KQs, AJo+, KQo',
        'river_bet': 'TT+, AQs+, AKo',
        'all_in': 'JJ+, AQs+, AKo',
    },
    'lag': {
        'open': '22+, A2s+, K7s+, Q9s+, J9s+, T8s+, 97s+, 86s+, A7o+, K9o+, QTo+',
        'call_preflop': '22+, A2s+, K9s+, QTs+, JTs, T9s, 98s, 87s, 76s',
        '3bet': 'TT+, A9s+, KJs+, AJo+, KQo, A5s-A2s',
        'flop_bet': '22+, A2s+, K7s+, Q9s+, J9s+, T8s+, A7o+, K9o+',
        'turn_bet': '55+, A8s+, KTs+, QJs, ATo+, KJo+',
        'river_bet': '77+, ATs+, KQs, AJo+',
        'all_in': 'TT+, AQs+, AKo, A5s-A2s',
    },
    'fish_passive': {
        'open': '22+, A2s+, A2o+, K5s+, K8o+, Q8s+, Q9o+, J8s+, T8s+, 97s+, 86s+',
        'call_preflop': '22+, A2s+, A2o+, K8s+, K9o+, Q9s+, QTo+, J9s+, JTo, T9s',
        '3bet': 'JJ+, AKs, AKo',
        'flop_bet': '22+, A2s+, A8o+, K9s+, KTo+, Q9s+',
        'turn_bet': '55+, A9s+, KTs+, ATo+, KJo+',
        'river_bet': '77+, ATs+, KQs, AJo+',
        'all_in': 'TT+, AQs+, AKo',
    },
    'fish_aggro': {
        'open': '22+, A2s+, A2o+, K2s+, K5o+, Q5s+, Q8o+, J7s+, T7s+, 96s+, 85s+',
        'call_preflop': '22+, A2s+, A2o+, K5s+, K8o+, Q8s+, Q9o+, J8s+, T8s+',
        '3bet': 'TT+, AQs+, AKo, A5s-A2s',
        'flop_bet': '22+, A2s+, K5s+, Q8s+, J8s+, A5o+, K9o+',
        'turn_bet': '22+, A2s+, K9s+, ATo+, KJo+, QJo',
        'river_bet': '55+, A9s+, KTs+, ATo+',
        'all_in': '88+, ATs+, KQs, AJo+, KQo',
    },
    'maniac': {
        'open': '22+, A2s+, A2o+, K2s+, K2o+, Q2s+, Q5o+, J5s+, J7o+, T6s+, T8o+, 96s+, 85s+, 74s+, 63s+',
        'call_preflop': '22+, A2s+, A2o+, K2s+, K5o+, Q5s+, Q8o+, J7s+, T7s+',
        '3bet': '88+, A5s+, KTs+, ATo+, KQo, 76s, 87s, 98s',
        'flop_bet': '22+, A2s+, A2o+, K2s+, K5o+, Q5s+, J7s+, T7s+',
        'turn_bet': '22+, A2s+, A5o+, K7s+, K9o+, Q9s+, QTo+',
        'river_bet': '55+, A7s+, KTs+, A9o+, KJo+',
        'all_in': '77+, A9s+, KJs+, ATo+, KQo',
    },
    'unknown': {
        'open': '22+, A2s+, K9s+, Q9s+, J9s+, T9s, A8o+, KTo+, QJo',
        'call_preflop': '22-JJ, A2s-AQs, KTs+, QTs+, JTs, ATo+, KJo+',
        '3bet': 'TT+, AQs+, AKo',
        'flop_bet': '22+, A2s+, K9s+, Q9s+, A8o+, KTo+',
        'turn_bet': '55+, ATs+, KQs, AJo+, KQo',
        'river_bet': '77+, ATs+, KQs, AJo+',
        'all_in': 'TT+, AQs+, AKo',
    },
}


def _convert_card(card_str: str) -> Optional['eval7.Card']:
    """Convert our card format (e.g. 'AH', 'TS', '10D') to eval7 Card."""
    if not HAS_EVAL7 or not card_str:
        return None
    card = card_str.upper().strip()
    # Handle '10X' format
    if card.startswith('10'):
        card = 'T' + card[2:]
    # eval7 wants lowercase suit: 'Ah' not 'AH'
    if len(card) == 2:
        return eval7.Card(card[0] + card[1].lower())
    return None


class RangeEquity:
    """Fast range-based equity calculator."""

    def __init__(self):
        if not HAS_EVAL7:
            log.error("eval7 not available — RangeEquity will return 0.5 for all queries")

    def equity_vs_range(
        self,
        hero: List[str],
        board: List[str],
        villain_range_str: str,
        iterations: int = 10000,
    ) -> float:
        """Calculate hero's equity vs a villain range.

        Args:
            hero: ['AH', 'KS'] — hero's hole cards
            board: ['QH', 'JD', '2C'] — community cards (0-5)
            villain_range_str: eval7 range string, e.g. 'QQ+, AKs, AKo'
            iterations: Monte Carlo iterations (10k = ~1ms)

        Returns:
            Equity as float 0.0-1.0
        """
        if not HAS_EVAL7:
            return 0.5

        try:
            hero_cards = [_convert_card(c) for c in hero if c]
            board_cards = [_convert_card(c) for c in board if c]

            hero_cards = [c for c in hero_cards if c is not None]
            board_cards = [c for c in board_cards if c is not None]

            if len(hero_cards) != 2:
                log.warning(f"RangeEquity: bad hero cards {hero}")
                return 0.5

            villain = eval7.HandRange(villain_range_str)
            if len(villain) == 0:
                log.warning(f"RangeEquity: empty villain range '{villain_range_str}'")
                return 0.5

            # Use exact calculation on river (fast enough), Monte Carlo otherwise
            if len(board_cards) == 5:
                eq = eval7.py_hand_vs_range_exact(hero_cards, villain, board_cards)
            else:
                eq = eval7.py_hand_vs_range_monte_carlo(
                    hero_cards, villain, board_cards, iterations
                )
            return float(eq)

        except Exception as e:
            log.warning(f"RangeEquity error: {e}")
            return 0.5

    def equity_vs_board_aware_range(
        self,
        hero: List[str],
        board: List[str],
        villain_range_str: str,
        street: str = 'river',
        action: str = 'bet',
        player_type: str = 'unknown',
    ) -> Tuple[float, str]:
        """Calculate equity vs a board-aware filtered villain range.

        Instead of computing equity vs the full static range, this:
        1. Evaluates each combo in villain's range on the actual board
        2. Filters out hands villain wouldn't bet on this board
        3. Computes equity against only the realistic betting range

        On board AKJTA with villain range '77+, ATs+, KQs, AJo+':
        - 77/88/99 make weak two pair → removed (wouldn't bet river)
        - QX makes straight → kept (value bet)
        - AX makes trips → kept (value bet)
        - Hero K4 equity drops from ~34% to ~15% (correct!)

        Args:
            hero: ['KS', '4S'] — hero's hole cards
            board: ['TC', 'AH', 'JC', 'KH', 'AS'] — community cards (3-5)
            villain_range_str: eval7 range string
            street: 'flop', 'turn', 'river'
            action: 'bet', 'raise', 'all_in', 'check'
            player_type: 'nit', 'tag', 'lag', 'fish_passive', etc.

        Returns:
            (equity, info_string) — equity 0.0-1.0 and description
        """
        if not HAS_EVAL7:
            return 0.5, "no eval7"

        try:
            hero_cards = [_convert_card(c) for c in hero if c]
            board_cards = [_convert_card(c) for c in board if c]
            hero_cards = [c for c in hero_cards if c is not None]
            board_cards = [c for c in board_cards if c is not None]

            if len(hero_cards) != 2:
                return 0.5, "bad hero cards"
            if len(board_cards) < 3:
                return self.equity_vs_range(hero, board, villain_range_str), "preflop"

            villain_range = eval7.HandRange(villain_range_str)
            if len(villain_range) == 0:
                return 0.5, "empty range"

            dead_strs = set(str(c) for c in hero_cards + board_cards)

            # Evaluate each villain combo on the board
            combos = []
            for (cards, weight) in villain_range.hands:
                if str(cards[0]) in dead_strs or str(cards[1]) in dead_strs:
                    continue
                hand = list(cards) + board_cards
                score = eval7.evaluate(hand)
                combos.append((cards, weight, score))

            if not combos:
                return 0.5, "all combos dead"

            # Sort by hand strength (descending)
            combos.sort(key=lambda x: x[2], reverse=True)

            # Board-only score (river only — need exactly 5 cards)
            board_score = eval7.evaluate(board_cards) if len(board_cards) == 5 else 0

            # Filtering parameters by player type
            # Nits bet tighter (only the very best), maniacs bet wider
            if player_type == 'nit':
                value_pct = 0.45
                bluff_pct = 0.05
            elif player_type == 'tag':
                value_pct = 0.55
                bluff_pct = 0.12
            elif player_type in ('lag', 'fish_aggro'):
                value_pct = 0.70
                bluff_pct = 0.25
            elif player_type == 'maniac':
                value_pct = 0.80
                bluff_pct = 0.35
            elif player_type == 'fish_passive':
                value_pct = 0.60
                bluff_pct = 0.08
            else:  # unknown
                value_pct = 0.60
                bluff_pct = 0.18

            # All-in = tighter than a bet
            if action == 'all_in':
                value_pct *= 0.70
                bluff_pct *= 0.50

            # Street-specific adjustment
            if street == 'river' and len(board_cards) == 5:
                # River: polarized. Use improving/non-improving split.
                improving = [(c, w, s) for c, w, s in combos if s > board_score]
                non_improving = [(c, w, s) for c, w, s in combos if s <= board_score]

                n_val = max(1, int(len(improving) * value_pct))
                n_bluff = max(0, int(len(non_improving) * bluff_pct))

                filtered = improving[:n_val]
                if n_bluff > 0:
                    filtered += non_improving[-n_bluff:]

            elif street == 'turn':
                # Turn: merged, use percentile on all combos
                n_val = max(1, int(len(combos) * min(value_pct + 0.10, 0.90)))
                n_bluff = max(0, int(len(combos) * bluff_pct * 0.5))
                filtered = combos[:n_val]
                if n_bluff > 0:
                    filtered += combos[-n_bluff:]
            else:
                # Flop: c-bet wide
                n_val = max(1, int(len(combos) * min(value_pct + 0.20, 0.95)))
                n_bluff = max(0, int(len(combos) * bluff_pct * 0.3))
                filtered = combos[:n_val]
                if n_bluff > 0:
                    filtered += combos[-n_bluff:]

            if not filtered:
                filtered = combos[:max(1, len(combos) // 3)]

            # Remove duplicates (a combo might appear in both value and bluff
            # if lists overlap, though they shouldn't with proper splits)
            seen = set()
            unique_filtered = []
            for item in filtered:
                key = (str(item[0][0]), str(item[0][1]))
                if key not in seen:
                    seen.add(key)
                    unique_filtered.append(item)
            filtered = unique_filtered

            # Compute equity against filtered range
            if len(board_cards) == 5:
                # River: exact calculation (instant)
                hero_score = eval7.evaluate(hero_cards + board_cards)
                wins = 0.0
                total_w = 0.0
                for (cards, weight, score) in filtered:
                    total_w += weight
                    if hero_score > score:
                        wins += weight
                    elif hero_score == score:
                        wins += weight * 0.5
                equity = wins / total_w if total_w > 0 else 0.5
            else:
                # Turn/Flop: reconstruct HandRange, use Monte Carlo
                try:
                    combo_strs = [f"{c[0]}{c[1]}" for c, w, s in filtered]
                    filtered_range_str = ", ".join(combo_strs)
                    filtered_hr = eval7.HandRange(filtered_range_str)
                    iters = 10000 if len(board_cards) == 4 else 5000
                    equity = float(eval7.py_hand_vs_range_monte_carlo(
                        hero_cards, filtered_hr, board_cards, iters))
                except Exception as e:
                    log.debug(f"HandRange reconstruction failed: {e}")
                    equity = self.equity_vs_range(hero, board, villain_range_str)

            # Build info string
            n_total = len(combos)
            n_kept = len(filtered)
            from collections import Counter
            type_counts = Counter()
            for (cards, weight, score) in filtered:
                type_counts[eval7.handtype(score)] += 1
            top_types = dict(type_counts.most_common(4))
            info = (f"{n_kept}/{n_total} combos ({street}, vs {player_type}), "
                    f"types: {top_types}")

            return equity, info

        except Exception as e:
            log.warning(f"Board-aware equity error: {e}")
            return self.equity_vs_range(hero, board, villain_range_str), f"fallback: {e}"

    def estimate_villain_range_str(
        self,
        position: str = 'CO',
        action: str = 'open',
        player_type: str = 'unknown',
        street: str = 'preflop',
    ) -> str:
        """Estimate the villain's likely range based on position and action.

        Returns a string compatible with eval7.HandRange.
        """
        pos = position.upper()
        
        # Base range from player type
        p_ranges = PLAYER_TYPE_RANGES.get(player_type, PLAYER_TYPE_RANGES['unknown'])
        
        if street == 'preflop':
            if action == 'open':
                # Use position-specific RFI range, modified by player tightness
                base = RFI_RANGES.get(pos, RFI_RANGES['CO'])
                if player_type == 'nit': return p_ranges['open']
                return base
            elif action == '3bet':
                # Use 3-bet ranges
                r_key = f'vs_{pos}'
                return THREE_BET_RANGES.get(r_key, THREE_BET_RANGES['default'])
            elif action == 'call':
                if player_type == 'nit': return CALL_RANGES['tight']
                if player_type in ('fish_passive', 'fish_aggro'): return CALL_RANGES['wide']
                return CALL_RANGES['medium']
            elif action == 'all_in':
                return p_ranges['all_in']
        
        # Postflop (Flop/Turn/River)
        if action == 'all_in':
            return p_ranges['all_in']
        elif action in ('bet', 'raise'):
            if street == 'flop': return p_ranges['flop_bet']
            if street == 'turn': return p_ranges['turn_bet']
            return p_ranges['river_bet']
        elif action == 'check':
            # Checking ranges are wider/weaker
            return '22+, A2s+, K2s+, Q2s+, J2s+, T2s+, A2o+, K2o+, Q2o+'
            
        return '22+, A2s+, K2s+, Q2s+, J2s+, T2s+, A2o+, K2o+, Q2o+'

    def estimate_villain_range(
        self,
        position: str = 'unknown',
        action: str = 'open',
        player_type: str = 'unknown',
        street: str = 'preflop',
        bet_size_pct: float = 0.0,
    ) -> str:
        """Estimate villain's range based on their action and profile.

        Args:
            position: 'UTG', 'MP', 'CO', 'BTN', 'SB', 'BB'
            action: 'open', 'call', '3bet', '4bet', 'bet', 'check', 'raise', 'all_in'
            player_type: 'nit', 'tag', 'lag', 'fish_passive', 'fish_aggro', 'maniac', 'unknown'
            street: 'preflop', 'flop', 'turn', 'river'
            bet_size_pct: bet as fraction of pot (0.33, 0.66, 1.0, etc.)

        Returns:
            eval7-compatible range string
        """
        ptype = player_type if player_type in PLAYER_TYPE_RANGES else 'unknown'
        pos = position.upper() if position else 'CO'

        if street == 'preflop':
            if action == 'open':
                # Use position-based RFI range, adjusted for player type
                base = RFI_RANGES.get(pos, RFI_RANGES['CO'])
                if ptype == 'nit':
                    return PLAYER_TYPE_RANGES['nit']['open']
                elif ptype in ('fish_passive', 'fish_aggro', 'maniac'):
                    return PLAYER_TYPE_RANGES[ptype]['open']
                return base

            elif action == '3bet':
                return THREE_BET_RANGES.get(f'vs_{pos}', THREE_BET_RANGES['default'])

            elif action == 'call':
                if ptype in ('fish_passive', 'fish_aggro', 'maniac'):
                    return CALL_RANGES['wide']
                elif ptype == 'nit':
                    return CALL_RANGES['tight']
                return CALL_RANGES['medium']

            elif action == '4bet':
                return 'QQ+, AKs, AKo'

        else:
            # Postflop — use player type ranges with street-specific keys
            type_ranges = PLAYER_TYPE_RANGES.get(ptype, PLAYER_TYPE_RANGES['unknown'])

            if action == 'all_in':
                return type_ranges.get('all_in', 'TT+, AQs+, AKo')
            elif action in ('bet', 'raise'):
                # Narrow range based on bet sizing (POSTFLOP_NARROWING proxy):
                # Large bets are polarized → use tighter range key
                # Small bets are merged → use wider range key
                if bet_size_pct >= 0.90:
                    key = 'all_in'
                elif bet_size_pct >= 0.66:
                    key = 'river_bet'
                elif bet_size_pct >= 0.40:
                    # Medium bet: use current street or one tighter
                    _tighter = {'flop': 'turn_bet', 'turn': 'river_bet', 'river': 'river_bet'}
                    key = _tighter.get(street, 'turn_bet')
                else:
                    # Small bet (< 40% pot): use the normal street range
                    key = f'{street}_bet'
                return type_ranges.get(key, type_ranges.get('turn_bet', type_ranges['open']))
            elif action == 'call':
                # Postflop call = their betting range for the PREVIOUS street
                # (they'd only call with hands they'd bet the prior street)
                street_order = {'flop': 'flop_bet', 'turn': 'flop_bet', 'river': 'turn_bet'}
                key = street_order.get(street, 'flop_bet')
                return type_ranges.get(key, type_ranges.get('call_preflop', type_ranges['open']))
            elif action == 'check':
                return type_ranges['open']

        return RFI_RANGES.get('CO', '22+, A2s+, KTo+, QJo')

    def estimate_villain_range_with_context(
        self,
        hand_context,  # HandContext from game_state.py
        street: str = 'flop',
        current_action: str = 'bet',
        bet_size_pct: float = 0.50,
        player_type: str = 'unknown',
        num_opponents: int = 1,
    ) -> str:
        """Context-aware villain range estimation using full hand history.

        This method uses the full action sequence to produce a much more
        accurate range than the single-action estimate_villain_range().

        Key scenarios that produce different ranges:
        - UTG open + flop c-bet on dry board -> tight (overpairs, TPGK, AK)
        - BTN open + flop c-bet on dry board -> wide (any pair, overcards, air)
        - Villain bets flop + turn (double barrel) -> polarized
        - Villain checks flop, bets turn -> delayed c-bet / medium strength
        - 3-way pot, villain bets -> much tighter than heads-up
        - Villain check-raises -> very strong or strong draw
        """
        if hand_context is None:
            # Fallback to basic estimation
            return self.estimate_villain_range(
                position='CO', action=current_action,
                player_type=player_type, street=street,
                bet_size_pct=bet_size_pct,
            )

        ptype = player_type if player_type in PLAYER_TYPE_RANGES else 'unknown'
        type_ranges = PLAYER_TYPE_RANGES.get(ptype, PLAYER_TYPE_RANGES['unknown'])

        # --- Preflop: use existing logic with raiser position ---
        if street == 'preflop':
            pos = hand_context.preflop_raiser_position or 'CO'
            return self.estimate_villain_range(
                position=pos, action=current_action,
                player_type=ptype, street='preflop',
                bet_size_pct=bet_size_pct,
            )

        # --- Postflop: context-aware narrowing ---
        pf_raiser_pos = hand_context.preflop_raiser_position or 'CO'
        v_pattern = hand_context.villain_pattern  # e.g. 'bet-bet', 'check-bet'
        n_streets_aggro = hand_context.streets_of_aggression
        is_cbet = hand_context.is_cbet_spot
        is_donk = hand_context.is_donk_bet
        is_multiway = num_opponents >= 2 or hand_context.is_multiway

        # Start from the preflop range (villain's starting range)
        base_range = self.estimate_villain_range(
            position=pf_raiser_pos,
            action='open' if hand_context.preflop_raiser_position else 'call',
            player_type=ptype,
            street='preflop',
        )

        # --- Scenario-based narrowing ---
        # Scenarios are checked in priority order. More specific matches first.

        # SCENARIO 7: Check-raise (any street) — highest priority
        if current_action == 'raise':
            v_street_actions = hand_context.villain_actions.get(street, [])
            if 'check' in v_street_actions and 'raise' in v_street_actions:
                # Check-raise = polarized: very strong or strong draw
                if is_multiway:
                    return 'TT+, AQs+, AKo'  # Multiway CR = nuts
                return 'JJ+, AKs, AQs, AKo, 99, 88'  # Sets + overpairs + bluffs

            # Non-check-raise (raised our bet directly)
            if is_multiway:
                return 'TT+, AQs+, AKo'
            if street == 'flop':
                return '99+, AJs+, AQo+'
            elif street == 'turn':
                return 'TT+, AQs+, AKo'
            else:
                return 'JJ+, AKs, AKo'

        # SCENARIO 4: Triple barrel (bet flop + turn + river)
        if v_pattern in ('bet-bet-bet',) and street == 'river':
            if is_multiway:
                return 'QQ+, AKs'  # Multiway triple barrel = nuts
            if bet_size_pct >= 0.75:
                # Large triple barrel = polarized (nuts or bluff)
                return 'TT+, AQs+, AKo'
            return 'JJ+, AKs, AQs, AKo'

        # SCENARIO 3: Double barrel (bet flop + bet turn)
        if v_pattern in ('bet-bet',) and street == 'turn':
            if is_multiway:
                # Multiway double barrel = very strong
                return 'TT+, AQs+, AKo'
            if pf_raiser_pos in ('UTG', 'MP'):
                # EP double barrel = very strong or draw
                return 'JJ+, AKs, AQs, AKo'
            # Polarized: strong hands + semi-bluffs
            if bet_size_pct >= 0.66:
                return 'TT+, AJs+, AQo+, KQs'  # Bigger bets = more polarized
            return '88+, ATs+, KQs, AJo+'

        # SCENARIO 8: Multiway pot adjustment (before c-bet, because multiway
        # c-bets are much tighter than heads-up c-bets)
        if is_multiway and current_action in ('bet',):
            if street == 'flop':
                return 'TT+, ATs+, KQs, AJo+'
            elif street == 'turn':
                return 'JJ+, AQs+, AKo'
            else:
                return 'QQ+, AKs'

        # SCENARIO 2: Donk bet (non-raiser betting into raiser)
        if is_donk and street == 'flop':
            # Donk bets are often medium-strength hands or draws
            if ptype in ('fish_passive', 'fish_aggro'):
                return '22+, A2s+, K2s+, Q2s+, J2s+, T2s+, A2o+, K2o+'  # Fish donk wide
            return '77+, A8s+, KTs+, QJs, ATo+, KJo+'

        # SCENARIO 1: C-bet on flop (preflop raiser betting flop)
        if is_cbet and street == 'flop' and current_action in ('bet',):
            if pf_raiser_pos in ('UTG', 'MP'):
                # EP raiser c-bets: tight range (overpairs, top pair+, AK)
                return 'TT+, ATs+, AJo+, KQs'
            elif pf_raiser_pos in ('CO', 'BTN'):
                # LP raiser c-bets: wide range (any pair, overcards, draws, air)
                return type_ranges.get('flop_bet', '77+, A2s+, K9s+, QTs+, JTs, T9s, A9o+, KTo+')
            else:
                # Blind raiser c-bets: medium range
                return '88+, A8s+, KTs+, QJs, ATo+, KJo+'

        # SCENARIO 5: Checked flop, bet turn (delayed c-bet / trapping)
        if v_pattern == 'check-bet' and street == 'turn':
            # Delayed aggression often means:
            # - Trapping with strong hand
            # - Hitting turn card
            # - Giving up bluffs, betting value
            return '99+, ATs+, KQs, AJo+'

        # SCENARIO 6: Bet flop, check turn (gave up or trapping)
        # This is informational for when villain bets river after checking turn
        if v_pattern == 'bet-check' and street == 'river':
            # Checked turn but now betting river = strong or thin value/bluff
            return '88+, ATs+, KJs+, ATo+'

        # SCENARIO 9: Generic postflop with street-of-aggression count
        if n_streets_aggro >= 2:
            # Multiple streets of aggression = range is narrowing
            if street == 'turn':
                return '99+, ATs+, KQs, AJo+'
            elif street == 'river':
                return 'TT+, AQs+, AKo'
        elif n_streets_aggro == 1 and current_action in ('bet', 'raise'):
            # First street of aggression postflop
            return type_ranges.get(f'{street}_bet',
                                   type_ranges.get('flop_bet', '77+, A8s+, KTs+, QTs+, ATo+'))

        # Default: fall back to basic estimation
        return self.estimate_villain_range(
            position=pf_raiser_pos, action=current_action,
            player_type=ptype, street=street,
            bet_size_pct=bet_size_pct,
        )


# ── Geometric bet sizing ───────────────────────────────────────────────────

def geometric_bet_fraction(pot: float, stack: float, streets: int) -> float:
    """Calculate bet size as fraction of pot to get all-in by river.

    Each street bets the same fraction, creating a geometric progression
    that naturally uses your entire stack by the last street.

    Args:
        pot: Current pot size
        stack: Effective stack remaining
        streets: Betting streets remaining (3=flop, 2=turn, 1=river)

    Returns:
        Fraction of pot to bet (e.g., 0.75 means bet 75% pot)
    """
    if streets <= 0 or pot <= 0 or stack <= 0:
        return 0.0
    growth = (pot + 2 * stack) / pot
    return max(0.0, 0.5 * (growth ** (1.0 / streets) - 1))


def compute_bet_size_bb(
    pot_bb: float,
    stack_bb: float,
    street: str,
    board_wetness: float = 0.5,
    spr: float = 10.0,
    is_ip: bool = True,
    hand_strength: str = 'medium',
    is_value: bool = True,
) -> float:
    """Compute optimal bet size in BB.

    Returns the bet amount (not pot fraction) in big blinds.
    """
    streets_map = {'flop': 3, 'turn': 2, 'river': 1, 'preflop': 0}
    streets_left = streets_map.get(street, 1)

    if streets_left == 0:
        return 0.0

    geo = geometric_bet_fraction(pot_bb, stack_bb, streets_left)

    # Board texture sizing
    if street == 'flop':
        if board_wetness < 0.3:
            base_frac = 0.33  # Dry board: small, high frequency
        elif board_wetness > 0.7:
            base_frac = 0.75  # Wet board: large, deny equity
        else:
            base_frac = 0.50
    elif street == 'turn':
        # Turn: lean toward geometric to set up river
        base_frac = min(geo, 0.80)
    else:
        # River: polarize
        if is_value and hand_strength in ('monster', 'very_strong'):
            base_frac = 0.75  # Big value bet
        elif is_value:
            base_frac = 0.50  # Thin value
        else:
            base_frac = 0.75  # Bluff (same size as value to be balanced)

    # SPR adjustment: low SPR → bigger (commit), high SPR → standard
    if spr < 1.5:
        base_frac = 1.0  # Just shove
    elif spr < 3.0:
        base_frac = max(base_frac, geo)  # Go for stacks

    # Position adjustment
    if not is_ip and street != 'river':
        base_frac = min(base_frac + 0.10, 1.0)  # Bet slightly bigger OOP

    bet = base_frac * pot_bb
    return min(bet, stack_bb)  # Can't bet more than our stack


# ── Preflop raise sizing ──────────────────────────────────────────────────

def preflop_raise_size_bb(
    action: str,
    position: str,
    num_limpers: int = 0,
    prev_raise_bb: float = 0.0,
    big_blind: float = 1.0,
) -> float:
    """Calculate preflop raise size in BB.

    Args:
        action: 'open', '3bet', '4bet', 'squeeze'
        position: 'UTG', 'MP', 'CO', 'BTN', 'SB', 'BB'
        num_limpers: number of limpers before us
        prev_raise_bb: previous raise amount in BB (for 3bet/4bet)
        big_blind: size of one big blind

    Returns:
        Raise amount in BB
    """
    if action == 'open':
        base = 2.5
        if position in ('SB', 'BB'):
            base = 3.0  # OOP, size up
        # Add 1 BB per limper
        return base + num_limpers

    elif action == '3bet':
        if position in ('SB', 'BB', 'UTG', 'MP'):
            # OOP: 4-4.5x the open
            return prev_raise_bb * 4.0
        else:
            # IP: 3-3.5x the open
            return prev_raise_bb * 3.0

    elif action == '4bet':
        # 2.2-2.5x the 3-bet
        return prev_raise_bb * 2.3

    elif action == 'squeeze':
        # 4x open + 1BB per caller
        return prev_raise_bb * 4.0

    return 2.5  # Default open


# ── Pre-computed equity tables ────────────────────────────────────────────

# All 169 canonical starting hands (13 pairs + 78 suited + 78 offsuit)
_ALL_HANDS_169 = []
_RANKS = '23456789TJQKA'
for i in range(13):
    for j in range(i, 13):
        if i == j:
            _ALL_HANDS_169.append(f'{_RANKS[j]}{_RANKS[i]}')  # Pair
        else:
            _ALL_HANDS_169.append(f'{_RANKS[j]}{_RANKS[i]}s')  # Suited
            _ALL_HANDS_169.append(f'{_RANKS[j]}{_RANKS[i]}o')  # Offsuit

# Cache: {(hand_key, range_str): equity}
_equity_cache: dict = {}
_cache_built = False


def _hand_to_eval7_cards(hand_key: str):
    """Convert canonical hand like 'AKs' to two eval7 cards for equity calc."""
    if not HAS_EVAL7:
        return None, None
    r1 = hand_key[0]
    r2 = hand_key[1] if len(hand_key) >= 2 else hand_key[0]
    is_suited = hand_key.endswith('s')
    is_pair = (r1 == r2)

    if is_pair:
        # Use two different suits: e.g. AhAs
        c1 = eval7.Card(f'{r1}h')
        c2 = eval7.Card(f'{r2}s')
    elif is_suited:
        c1 = eval7.Card(f'{r1}h')
        c2 = eval7.Card(f'{r2}h')
    else:
        c1 = eval7.Card(f'{r1}h')
        c2 = eval7.Card(f'{r2}s')
    return c1, c2


def build_preflop_equity_table(player_types: list = None, iterations: int = 5000):
    """Pre-compute equity for all 169 hands vs every range string that
    estimate_villain_range() can return preflop.

    Caches by (hand_key, range_string) so lookup_preflop_equity() gets instant hits.
    """
    global _equity_cache, _cache_built
    if not HAS_EVAL7:
        log.warning("eval7 not available — cannot build equity tables")
        return

    if player_types is None:
        player_types = list(PLAYER_TYPE_RANGES.keys())

    # Collect every unique range string that estimate_villain_range() can return preflop
    re = RangeEquity()
    unique_ranges = set()
    positions = list(RFI_RANGES.keys())
    actions = ('open', 'call', '3bet', '4bet')
    for pos in positions:
        for act in actions:
            for ptype in player_types:
                r = re.estimate_villain_range(position=pos, action=act,
                                              player_type=ptype, street='preflop')
                if r:
                    unique_ranges.add(r)

    count = 0
    for v_range in unique_ranges:
        try:
            hr = eval7.HandRange(v_range)
        except Exception:
            continue
        for hand in _ALL_HANDS_169:
            cache_key = (hand, v_range)
            if cache_key in _equity_cache:
                continue
            c1, c2 = _hand_to_eval7_cards(hand)
            if c1 is None:
                continue
            try:
                eq = eval7.py_hand_vs_range_monte_carlo(
                    [c1, c2], hr, [], iterations
                )
                _equity_cache[cache_key] = float(eq)
                count += 1
            except Exception:
                _equity_cache[cache_key] = 0.5
                count += 1

    _cache_built = True
    log.info(f"PREFLOP TABLE: built {count} entries for {len(unique_ranges)} unique ranges")


def lookup_preflop_equity(hero_cards: List[str], villain_range: str) -> Optional[float]:
    """Fast lookup from pre-computed table. Returns None if not cached."""
    if not _cache_built or not hero_cards or len(hero_cards) != 2:
        return None

    # Convert hero cards to canonical 169-hand format
    rank_order = {r: i for i, r in enumerate(_RANKS)}
    c1, c2 = hero_cards[0].upper(), hero_cards[1].upper()
    r1, s1 = c1[:-1].replace('10', 'T'), c1[-1]
    r2, s2 = c2[:-1].replace('10', 'T'), c2[-1]

    # Ensure higher rank first
    if rank_order.get(r1, 0) < rank_order.get(r2, 0):
        r1, s1, r2, s2 = r2, s2, r1, s1

    if r1 == r2:
        hand_key = f'{r1}{r2}'
    elif s1 == s2:
        hand_key = f'{r1}{r2}s'
    else:
        hand_key = f'{r1}{r2}o'

    return _equity_cache.get((hand_key, villain_range))


# ── Push/Fold system ─────────────────────────────────────────────────────
#
# Nash-equilibrium push/fold for short stacks (≤15 BB).
# At short stacks, poker is solved: shove all-in or fold.
# No open-raising to 2.5x — that bleeds chips when you get 3-bet.
#
# Two components:
# 1. SHOVE decision: hardcoded Nash ranges (from solver output)
# 2. CALL-vs-SHOVE decision: eval7 equity vs villain's Nash shove range
#

# ── Nash open-shove ranges by position and stack depth ────────────────────
# Source: Nash equilibrium solutions (HoldemResources, ICMIZER, Primedope)
# Format: {position: {stack_bb: range_string}}
# These are for OPEN-SHOVE (folded to you). Not for calling.

NASH_SHOVE_RANGES = {
    'UTG': {
        3:  '22+, A2s+, K5s+, Q8s+, J8s+, T8s+, 98s, A2o+, K8o+, Q9o+, JTo',
        5:  '22+, A2s+, K9s+, QTs+, JTs, A7o+, KTo+',
        8:  '44+, A7s+, KTs+, QJs, A9o+, KQo',
        10: '55+, A4s+, K9s+, QTs+, J9s+, T9s, A9o+, KJo+',
        12: '55+, A8s+, KTs+, QJs, ATo+, KQo',
        15: '66+, ATs+, KJs+, AJo+, KQo',
    },
    'MP': {
        3:  '22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 97s+, 87s, 76s, A2o+, K5o+, Q8o+, J9o+, T9o',
        5:  '22+, A2s+, K7s+, Q9s+, J9s+, T9s, 98s, A4o+, KTo+, QJo',
        8:  '22+, A2s+, K9s+, Q9s+, J9s+, T9s, A8o+, KTo+, QJo',
        10: '33+, A2s+, K9s+, Q9s+, J9s+, T9s, A9o+, KJo+, QJo',
        12: '55+, A5s+, KTs+, QJs, JTs, ATo+, KQo',
        15: '66+, A9s+, KTs+, QJs, AJo+, KQo',
    },
    'CO': {
        3:  '22+, A2s+, K2s+, Q2s+, J4s+, T6s+, 96s+, 86s+, 75s+, 65s, 54s, A2o+, K2o+, Q5o+, J7o+, T8o+, 98o',
        5:  '22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 97s+, 87s, 76s, A2o+, K5o+, Q8o+, J9o+, T9o',
        8:  '22+, A2s+, K8s+, Q9s+, J9s+, T9s, A5o+, KTo+, QJo',
        10: '44+, A5s+, KTs+, QJs, JTs, ATo+, KQo',
        12: '55+, A8s+, KTs+, QJs, JTs, AJo+, KQo',
        15: '66+, ATs+, KJs+, AJo+, KQo',
    },
    'BTN': {
        3:  '22+, A2s+, K2s+, Q2s+, J2s+, T4s+, 95s+, 85s+, 74s+, 64s+, 53s+, 43s, A2o+, K2o+, Q2o+, J5o+, T7o+, 97o+, 87o',
        5:  '22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 97s+, 86s+, 76s, 65s, A2o+, K7o+, Q9o+, JTo',
        8:  '22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 97s+, 87s, 76s, A2o+, K7o+, Q9o+, JTo',
        10: '22+, A2s+, K4s+, Q7s+, J8s+, T8s+, 98s, A2o+, K9o+, QTo+, JTo',
        12: '22+, A2s+, K5s+, Q8s+, J8s+, T8s+, 98s, A2o+, K9o+, QTo+, JTo',
        15: '22+, A2s+, K5s+, Q8s+, J8s+, T8s+, 98s, 87s, A4o+, KTo+, QJo',
    },
    'SB': {
        3:  '22+, A2s+, K2s+, Q2s+, J2s+, T2s+, 92s+, 82s+, 72s+, 62s+, 52s+, 42s+, 32s, A2o+, K2o+, Q2o+, J2o+, T4o+, 95o+, 86o+, 76o',
        5:  '22+, A2s+, K2s+, Q2s+, J4s+, T6s+, 96s+, 86s+, 75s+, 65s, 54s, A2o+, K2o+, Q5o+, J8o+, T8o+',
        8:  '22+, A2s+, K2s+, Q4s+, J6s+, T6s+, 96s+, 86s+, 75s+, 65s, 54s, A2o+, K2o+, Q5o+, J8o+, T8o+',
        10: '22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 97s+, 86s+, 76s, 65s, A2o+, K4o+, Q8o+, J9o+, T9o',
        12: '22+, A2s+, K2s+, Q4s+, J6s+, T7s+, 97s+, 86s+, 76s, 65s, A2o+, K3o+, Q8o+, J9o+, T9o',
        15: '22+, A2s+, K2s+, Q4s+, J6s+, T7s+, 97s+, 86s+, 76s, 65s, A2o+, K5o+, Q8o+, J9o+, T9o',
    },
}

# Calling ranges when facing a shove (by caller position and stack depth)
CALL_RANGES_VS_SHOVE = {
    'BB': {
        3:  '22+, A2s+, K2s+, Q4s+, J7s+, T7s+, 97s+, 87s, A2o+, K5o+, Q8o+, J9o+',
        5:  '22+, A2s+, K7s+, Q9s+, JTs, A4o+, KTo+, QJo',
        8:  '33+, A7s+, KTs+, QJs, ATo+, KQo',
        10: '55+, A9s+, KJs+, ATo+, KQo',
        12: '66+, ATs+, KQs, AJo+, KQo',
        15: '77+, ATs+, KQs, AJo+',
    },
    'SB': {
        3:  '22+, A2s+, K5s+, Q8s+, J9s+, T9s, A2o+, K8o+, QTo+, JTo',
        5:  '33+, A2s+, K9s+, QTs+, JTs, A7o+, KTo+, QJo',
        8:  '55+, A8s+, KTs+, QJs, ATo+, KQo',
        10: '66+, ATs+, KJs+, AJo+, KQo',
        12: '77+, ATs+, KQs, AJo+',
        15: '88+, AJs+, KQs, AQo+',
    },
    'default': {
        3:  '33+, A2s+, K8s+, QTs+, JTs, A5o+, KTo+, QJo',
        5:  '55+, A5s+, KTs+, QJs, A9o+, KQo',
        8:  '66+, A9s+, KJs+, ATo+, KQo',
        10: '77+, ATs+, KQs, AJo+',
        12: '88+, AJs+, KQs, AQo+',
        15: '99+, AQs+, AKo',
    },
}

_POSITIONS = ['UTG', 'MP', 'CO', 'BTN', 'SB']
_PUSH_FOLD_STACKS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]

# Parsed cache: {(position, stack): set of canonical hands}
_shove_range_sets: dict = {}
_push_fold_built = False


def _parse_range_to_hands(range_str: str) -> set:
    """Parse a range string into a set of canonical hand keys.

    Handles: 'AA', 'AKs', 'AKo', '22+', 'A2s+', 'AJo+', 'A2s-A5s',
             'K5s+', etc.
    """
    hands = set()
    rank_order = '23456789TJQKA'
    rank_idx = {r: i for i, r in enumerate(rank_order)}

    for part in range_str.split(','):
        part = part.strip()
        if not part:
            continue

        # Handle range like 'A2s-A5s'
        if '-' in part and len(part) > 4:
            halves = part.split('-')
            if len(halves) == 2:
                lo, hi = halves[0].strip(), halves[1].strip()
                if len(lo) >= 3 and len(hi) >= 3:
                    r1 = lo[0]
                    suffix = lo[-1]  # 's' or 'o'
                    lo_r2 = lo[1]
                    hi_r2 = hi[1]
                    lo_idx = rank_idx.get(lo_r2, 0)
                    hi_idx = rank_idx.get(hi_r2, 0)
                    for i in range(min(lo_idx, hi_idx), max(lo_idx, hi_idx) + 1):
                        if i != rank_idx.get(r1, -1):
                            hands.add(f'{r1}{rank_order[i]}{suffix}')
                continue

        # Handle '+' notation
        if part.endswith('+'):
            base = part[:-1]
            if len(base) == 2:
                r1, r2 = base[0], base[1]
                if r1 == r2:
                    # Pair+: e.g., '55+' means 55,66,77,...,AA
                    start = rank_idx.get(r1, 0)
                    for i in range(start, 13):
                        hands.add(f'{rank_order[i]}{rank_order[i]}')
                else:
                    # Unpaired no suit specified: both suited and offsuit
                    r1_idx = rank_idx.get(r1, 0)
                    r2_idx = rank_idx.get(r2, 0)
                    hi = max(r1_idx, r2_idx)
                    lo = min(r1_idx, r2_idx)
                    for i in range(lo, hi):
                        hands.add(f'{rank_order[hi]}{rank_order[i]}s')
                        hands.add(f'{rank_order[hi]}{rank_order[i]}o')
            elif len(base) == 3:
                r1, r2, suffix = base[0], base[1], base[2]
                r1_idx = rank_idx.get(r1, 0)
                r2_idx = rank_idx.get(r2, 0)
                hi = max(r1_idx, r2_idx)
                lo = min(r1_idx, r2_idx)
                # e.g., 'K5s+' → K5s, K6s, ..., KQs
                for i in range(lo, hi):
                    hands.add(f'{rank_order[hi]}{rank_order[i]}{suffix}')
        else:
            # Exact hand
            if len(part) == 2:
                r1, r2 = part[0], part[1]
                if r1 == r2:
                    hands.add(part)  # Pair
                else:
                    # No suit = both
                    hi = max(rank_idx.get(r1, 0), rank_idx.get(r2, 0))
                    lo = min(rank_idx.get(r1, 0), rank_idx.get(r2, 0))
                    hands.add(f'{rank_order[hi]}{rank_order[lo]}s')
                    hands.add(f'{rank_order[hi]}{rank_order[lo]}o')
            elif len(part) == 3:
                r1, r2, suffix = part[0], part[1], part[2]
                hi = max(rank_idx.get(r1, 0), rank_idx.get(r2, 0))
                lo = min(rank_idx.get(r1, 0), rank_idx.get(r2, 0))
                hands.add(f'{rank_order[hi]}{rank_order[lo]}{suffix}')

    return hands


def _hero_to_canonical(hero_cards: List[str]) -> Optional[str]:
    """Convert hero cards like ['AH', 'KS'] to canonical '169' key like 'AKo'."""
    if not hero_cards or len(hero_cards) != 2:
        return None
    rank_order = {r: i for i, r in enumerate(_RANKS)}
    c1, c2 = hero_cards[0].upper(), hero_cards[1].upper()
    r1, s1 = c1[:-1].replace('10', 'T'), c1[-1]
    r2, s2 = c2[:-1].replace('10', 'T'), c2[-1]

    if rank_order.get(r1, 0) < rank_order.get(r2, 0):
        r1, s1, r2, s2 = r2, s2, r1, s1

    if r1 == r2:
        return f'{r1}{r2}'
    elif s1 == s2:
        return f'{r1}{r2}s'
    else:
        return f'{r1}{r2}o'


def build_push_fold_table():
    """Parse Nash shove ranges into fast-lookup sets.

    Called at startup. Instant (just string parsing, no eval7 needed).
    """
    global _shove_range_sets, _push_fold_built
    if _push_fold_built:
        return

    for pos in _POSITIONS:
        pos_ranges = NASH_SHOVE_RANGES.get(pos, {})
        for stack_bb, range_str in pos_ranges.items():
            _shove_range_sets[(pos, stack_bb)] = _parse_range_to_hands(range_str)

    _push_fold_built = True

    # Log range sizes at 10BB
    sizes = {}
    for pos in _POSITIONS:
        s = _shove_range_sets.get((pos, 10), set())
        sizes[pos] = f"{len(s)}/{len(_ALL_HANDS_169)}"
    log.info(f"PUSH/FOLD TABLE: parsed. Shove hands at 10BB: {sizes}")


def lookup_push_fold(
    hero_cards: List[str],
    position: str,
    stack_bb: float,
) -> Optional[dict]:
    """Look up Nash push/fold decision.

    Args:
        hero_cards: ['AH', 'KS']
        position: 'UTG', 'MP', 'CO', 'BTN', 'SB'
        stack_bb: hero's stack in big blinds

    Returns:
        dict with 'action' ('shove'/'fold'), 'hand', 'stack', 'position'
        or None if stack > 15 BB (not in push/fold territory).
    """
    if not _push_fold_built:
        build_push_fold_table()

    if not hero_cards or len(hero_cards) != 2:
        return None
    if stack_bb > 15:
        return None

    hand_key = _hero_to_canonical(hero_cards)
    if not hand_key:
        return None

    pos = position.upper()
    if pos == 'BB':
        return None  # BB doesn't open-shove (they already posted)
    if pos not in _POSITIONS:
        pos = 'CO'

    stack_int = max(3, min(15, int(round(stack_bb))))

    # Find closest defined stack depths for interpolation
    defined = sorted(NASH_SHOVE_RANGES.get(pos, {}).keys())
    if not defined:
        return None

    # Find lower and upper bracket stack depths
    lower = defined[0]
    upper = defined[-1]
    for d in defined:
        if d <= stack_int:
            lower = d
        else:
            upper = d
            break
    else:
        upper = lower  # stack_int >= all defined depths

    # Check if hand is in range at each bracket
    in_lower = hand_key in _shove_range_sets.get((pos, lower), set())
    in_upper = hand_key in _shove_range_sets.get((pos, upper), set())

    if lower == upper or (in_lower == in_upper):
        # Not a boundary hand — clear shove or fold
        is_shove = in_lower
    else:
        # Boundary hand: in range at one depth but not the other.
        # Interpolate — more likely to shove at the lower (shorter) stack depth.
        frac = (stack_bb - lower) / (upper - lower) if upper > lower else 0
        # At lower depth → shove; at upper depth → fold.
        # in_lower=True, in_upper=False: shove with prob (1 - frac)
        # in_lower=False, in_upper=True: shove with prob frac
        if in_lower:
            is_shove = random.random() > frac  # More likely to shove at lower depth
        else:
            is_shove = random.random() < frac  # More likely to shove at upper depth
        log.info(f"PUSH/FOLD INTERP: {hand_key} stack={stack_bb:.1f}BB "
                 f"[{lower}BB={'Y' if in_lower else 'N'}, {upper}BB={'Y' if in_upper else 'N'}] "
                 f"frac={frac:.2f} → {'shove' if is_shove else 'fold'}")

    shove_set = _shove_range_sets.get((pos, lower), set())
    return {
        'action': 'shove' if is_shove else 'fold',
        'hand': hand_key,
        'stack': stack_int,
        'position': pos,
        'range_size': len(shove_set),
    }


def lookup_call_shove(
    hero_cards: List[str],
    shover_position: str,
    stack_bb: float,
    pot_bb: float = 1.5,
) -> Optional[dict]:
    """Decide whether to call an opponent's all-in shove.

    Uses eval7 to compute equity vs the shover's estimated range,
    then checks pot odds.

    Args:
        hero_cards: ['AH', 'KS']
        shover_position: position of the all-in player
        stack_bb: cost to call (the shover's stack or our remaining stack)
        pot_bb: current pot before our call

    Returns:
        dict with 'action' ('call'/'fold'), 'equity', 'pot_odds', 'ev'
        or None if eval7 unavailable.
    """
    if not HAS_EVAL7 or not hero_cards or len(hero_cards) != 2:
        return None

    # Shover's range: use Nash shove ranges from the lookup table
    pos = shover_position.upper() if shover_position else 'CO'
    if pos not in _POSITIONS:
        pos = 'CO'
    stack_int = max(3, min(15, int(round(stack_bb))))

    # Find closest defined stack depth for this position
    defined = sorted(NASH_SHOVE_RANGES.get(pos, {}).keys())
    if defined:
        best = defined[0]
        for d in defined:
            if d <= stack_int:
                best = d
            else:
                if stack_int - best > d - stack_int:
                    best = d
                break
        shover_range_str = NASH_SHOVE_RANGES[pos][best]
    else:
        # Fallback: use a standard shoving range
        shover_range_str = '22+, A2s+, K9s+, QTs+, JTs, A7o+, KTo+'

    try:
        hero_e7 = [_convert_card(c) for c in hero_cards if c]
        hero_e7 = [c for c in hero_e7 if c is not None]
        if len(hero_e7) != 2:
            return None

        shover_range = eval7.HandRange(shover_range_str)
        equity = float(eval7.py_hand_vs_range_monte_carlo(
            hero_e7, shover_range, [], 10000
        ))

        # Pot odds: we risk stack_bb to win pot_bb + stack_bb
        total_pot = pot_bb + 2 * stack_bb
        pot_odds = stack_bb / total_pot

        ev = equity * total_pot - stack_bb

        return {
            'action': 'call' if equity >= pot_odds else 'fold',
            'equity': equity,
            'pot_odds': pot_odds,
            'ev': ev,
            'vs_range': shover_range_str[:80],
            'range_size': len(shover_range),
        }

    except Exception as e:
        log.warning(f"Call-shove lookup error: {e}")
        return None


# ── Dynamic shove EV with blockers ────────────────────────────────────────
#
# For scenarios beyond simple open-shove (reshove, over limpers, facing 3bet),
# we compute EV dynamically using eval7 with full card-removal (blockers).
#
# EV(shove) = P(fold) × dead_money + P(call) × [equity × total_pot - cost]
#
# eval7 handles blockers automatically: when hero holds A♠K♥, all combos
# in villain's range using those cards are excluded from both the opening
# range and calling range counts. This changes fold equity naturally.
#

# What an opener calls a reshove with, by their position and effective stack.
# Tighter than their open range — they only call our all-in with premium.
OPENER_CALL_VS_RESHOVE = {
    # Calling ranges vs reshove — WIDER at smaller effective stacks because
    # villain gets better pot odds.  At 12BB reshove vs 2.5BB open, villain
    # calls ~9.5BB more into ~28BB pot = only needs ~34% equity.
    # Previous ranges were far too tight (e.g. UTG calling only KK+ at 12BB),
    # which inflated fold equity and let trash hands reshove profitably.
    'UTG': {
        3: 'TT+, AKs, AKo',
        5: 'TT+, AKs, AKo',
        8: 'JJ+, AKs, AKo',
        10: 'JJ+, AKs, AKo, AQs',
        12: 'QQ+, AKs, AKo, AQs',
        15: 'QQ+, AKs, AKo',
    },
    'MP': {
        3: '99+, AQs+, AKo',
        5: '99+, AQs+, AKo',
        8: 'TT+, AKs, AKo, AQs',
        10: 'TT+, AKs, AKo, AQs',
        12: 'JJ+, AKs, AKo, AQs',
        15: 'QQ+, AKs, AKo',
    },
    'CO': {
        3: '77+, ATs+, KQs, AJo+',
        5: '88+, AJs+, KQs, AKo',
        8: '99+, AQs+, AKo, KQs',
        10: 'TT+, AQs+, AKo',
        12: 'JJ+, AKs, AKo, AQs',
        15: 'QQ+, AKs, AKo',
    },
    'BTN': {
        3: '55+, A9s+, KJs+, ATo+, KQo',
        5: '77+, ATs+, KQs, AJo+',
        8: '88+, AJs+, KQs, AQo+',
        10: '99+, AQs+, AKo, KQs',
        12: 'TT+, AQs+, AKo',
        15: 'JJ+, AKs, AKo',
    },
    'SB': {
        3: '55+, A8s+, KTs+, ATo+, KQo',
        5: '66+, A9s+, KJs+, ATo+, KQo',
        8: '77+, ATs+, KQs, AJo+',
        10: '88+, AJs+, AQo+, KQs',
        12: 'TT+, AQs+, AKo',
        15: 'JJ+, AKs, AKo',
    },
}

# What a limper calls our shove with (they limped weak, but might trap)
LIMPER_CALL_VS_SHOVE = {
    3: '77+, ATs+, KQs, AJo+',
    5: '88+, ATs+, KQs, AJo+',
    8: 'TT+, AQs+, AKo',
    10: 'JJ+, AKs, AKo',
    12: 'QQ+, AKs',
    15: 'QQ+, AKs',
}

# Limp range: what hands limp preflop (wide, passive)
LIMPER_RANGE = '22+, A2s+, K5s+, Q8s+, J8s+, T8s+, 97s+, 86s+, A2o+, K8o+, Q9o+, JTo'


def _count_combos(range_str: str, dead_cards: list) -> int:
    """Count combos in a range after removing dead cards (blockers)."""
    if not HAS_EVAL7:
        return 0
    try:
        hr = eval7.HandRange(range_str)
        dead = set(str(c) for c in dead_cards)
        return sum(1 for cards, w in hr.hands
                   if str(cards[0]) not in dead and str(cards[1]) not in dead)
    except Exception:
        return 0


def compute_shove_ev(
    hero_cards: List[str],
    hero_stack_bb: float,
    pot_bb: float,
    villain_range_str: str,
    villain_call_range_str: str,
    villain_stack_bb: float = 100.0,
    already_invested_bb: float = 0.0,
) -> Optional[dict]:
    """Compute EV of shoving all-in with full blocker math.

    This is the core calculation for all short-stack preflop decisions:
    open-shove, reshove, shove over limpers, 4-bet shove.

    eval7 handles blockers automatically — when hero holds A♠K♥,
    combos in villain's range using those cards are excluded.

    Args:
        hero_cards: ['AH', 'KS']
        hero_stack_bb: hero's stack in BB
        pot_bb: current pot (blinds + dead money from limpers/raises)
        villain_range_str: villain's full range (opening/limping range)
        villain_call_range_str: what villain calls our shove with
        villain_stack_bb: villain's stack (for effective stack)
        already_invested_bb: what hero already put in (e.g. BB posted)

    Returns:
        dict with 'ev', 'fold_equity', 'equity_when_called', 'action', etc.
    """
    if not HAS_EVAL7:
        return None

    try:
        hero_e7 = [_convert_card(c) for c in hero_cards if c]
        hero_e7 = [c for c in hero_e7 if c is not None]
        if len(hero_e7) != 2:
            return None

        dead = hero_e7  # For card removal

        # Count combos with blockers
        full_combos = _count_combos(villain_range_str, dead)
        call_combos = _count_combos(villain_call_range_str, dead)

        if full_combos == 0:
            return None

        # Fold equity (with blockers baked in)
        fold_equity = 1.0 - (call_combos / full_combos) if full_combos > 0 else 0.5

        # Effective stack (can't win more than villain has)
        eff_stack = min(hero_stack_bb, villain_stack_bb)

        # What we risk: our stack minus what's already invested
        risk = eff_stack - already_invested_bb

        # What we win when everyone folds: the pot (includes blinds + dead money)
        fold_profit = pot_bb - already_invested_bb

        # What happens when called:
        # Total pot = current pot + our shove + villain's call
        # But effective stack limits it
        call_pot = pot_bb + 2 * eff_stack - 2 * already_invested_bb
        # Hmm, let me recalculate more carefully:
        # We shove eff_stack total (already_invested is part of that)
        # Villain calls eff_stack total
        # Pot already has pot_bb
        # But pot_bb may already include our investment + villain's raise
        # Simplify: total pot when called = pot_bb + (eff_stack - already_invested_bb) * 2
        # Wait, more precisely:
        # pot_bb already includes all dead money (blinds, limps, raises including ours)
        # When villain calls our shove:
        #   - We put in (eff_stack - already_invested_bb) more
        #   - Villain puts in (eff_stack - villain_already_invested) more
        # For simplicity, treat total pot when called as:
        total_pot_called = pot_bb + 2 * (eff_stack - already_invested_bb)

        # Equity vs calling range
        call_range = eval7.HandRange(villain_call_range_str)
        if len(call_range) == 0:
            # Nobody calls → pure fold equity play
            ev = fold_profit
            return {
                'ev': ev,
                'action': 'shove' if ev > 0 else 'fold',
                'fold_equity': 1.0,
                'equity_when_called': 0.0,
                'full_combos': full_combos,
                'call_combos': 0,
                'pot_bb': pot_bb,
                'eff_stack': eff_stack,
            }

        equity_called = float(eval7.py_hand_vs_range_monte_carlo(
            hero_e7, call_range, [], 10000
        ))

        # EV calculation
        ev_fold_part = fold_equity * fold_profit
        ev_call_part = (1 - fold_equity) * (equity_called * total_pot_called - risk)
        ev = ev_fold_part + ev_call_part

        return {
            'ev': ev,
            'action': 'shove' if ev > 0 else 'fold',
            'fold_equity': fold_equity,
            'equity_when_called': equity_called,
            'full_combos': full_combos,
            'call_combos': call_combos,
            'pot_bb': pot_bb,
            'eff_stack': eff_stack,
        }

    except Exception as e:
        log.warning(f"Shove EV computation error: {e}")
        return None


def _find_nearest_stack(defined_stacks: dict, stack_bb: float) -> int:
    """Find nearest defined stack depth key."""
    stack_int = max(3, min(15, int(round(stack_bb))))
    keys = sorted(defined_stacks.keys())
    if not keys:
        return 10
    best = keys[0]
    for k in keys:
        if k <= stack_int:
            best = k
        else:
            if stack_int - best > k - stack_int:
                best = k
            break
    return best


def reshove_decision(
    hero_cards: List[str],
    hero_stack_bb: float,
    hero_position: str,
    opener_position: str,
    raise_size_bb: float,
    pot_bb: float,
    opener_stack_bb: float = 100.0,
    player_type: str = 'unknown',
) -> Optional[dict]:
    """Decide whether to reshove (3-bet all-in) vs an opener.

    When someone opens and hero has ≤15 BB, the options are shove or fold.
    Flatting with a short stack is a leak — no fold equity postflop.

    Uses dynamic EV with blockers via eval7.

    Args:
        hero_cards: ['AH', 'KS']
        hero_stack_bb: hero's stack in BB
        hero_position: hero's position (for logging)
        opener_position: opener's position (determines their range)
        raise_size_bb: opener's raise size in BB
        pot_bb: current pot (blinds + raise + any dead money)
        opener_stack_bb: opener's remaining stack
        player_type: opener's player type (adjusts ranges)

    Returns:
        dict with 'action' ('shove'/'fold'), 'ev', 'fold_equity', etc.
    """
    if not HAS_EVAL7 or hero_stack_bb > 15:
        return None

    pos = opener_position.upper() if opener_position else 'CO'
    if pos not in OPENER_CALL_VS_RESHOVE:
        pos = 'CO'

    # Opener's full range (what they opened with)
    ptype = player_type if player_type in PLAYER_TYPE_RANGES else 'unknown'
    opener_range = PLAYER_TYPE_RANGES[ptype].get('open', RFI_RANGES.get(pos, RFI_RANGES['CO']))

    # Opener's calling range vs our reshove
    stack_key = _find_nearest_stack(OPENER_CALL_VS_RESHOVE[pos], hero_stack_bb)
    call_range = OPENER_CALL_VS_RESHOVE[pos][stack_key]

    # Adjust calling range for player type
    if ptype == 'nit':
        # Nits call reshoves super tight
        call_range = OPENER_CALL_VS_RESHOVE.get('UTG', OPENER_CALL_VS_RESHOVE[pos]).get(
            stack_key, call_range)
    elif ptype in ('fish_passive', 'fish_aggro', 'maniac'):
        # Fish/maniacs call wider — use one stack depth lower (wider range)
        wider_key = _find_nearest_stack(OPENER_CALL_VS_RESHOVE[pos], max(3, hero_stack_bb - 3))
        call_range = OPENER_CALL_VS_RESHOVE[pos].get(wider_key, call_range)

    # Hero has already invested: just the blind if in BB/SB, 0 otherwise
    already_in = 1.0 if hero_position == 'BB' else 0.5 if hero_position == 'SB' else 0.0

    result = compute_shove_ev(
        hero_cards=hero_cards,
        hero_stack_bb=hero_stack_bb,
        pot_bb=pot_bb,
        villain_range_str=opener_range,
        villain_call_range_str=call_range,
        villain_stack_bb=opener_stack_bb,
        already_invested_bb=already_in,
    )

    if result:
        result['opener_range'] = opener_range[:60]
        result['call_range'] = call_range[:60]
        result['opener_position'] = pos

        # SAFETY: Block reshove when equity-when-called is too low.
        # Even with high fold equity, reshoving with < 30% equity vs calling
        # range is extremely high variance and relies on optimistic FE estimates.
        # Two independent gates:
        #   1) Hard floor: eq_called < 28% always blocks (no hand is worth it)
        #   2) Soft floor: eq_called < 35% blocks unless EV is very high (>1.5BB)
        eq_called = result.get('equity_when_called', 0)
        if result['action'] == 'shove':
            hero_canonical = _hero_to_canonical(hero_cards)
            if eq_called < 0.28:
                log.info(f"RESHOVE BLOCKED (hard floor): {hero_canonical} vs {pos} open "
                         f"(eq_called={eq_called:.0%} < 28% minimum, "
                         f"EV={result['ev']:+.2f}BB)")
                result['action'] = 'fold'
            elif eq_called < 0.35 and result['ev'] < 1.5:
                log.info(f"RESHOVE BLOCKED (soft floor): {hero_canonical} vs {pos} open "
                         f"(eq_called={eq_called:.0%} < 35%, "
                         f"EV={result['ev']:+.2f}BB < 1.5BB)")
                result['action'] = 'fold'

        log.info(f"RESHOVE: {_hero_to_canonical(hero_cards)} vs {pos} open "
                 f"(FE={result['fold_equity']:.0%}, eq_called={result['equity_when_called']:.0%}, "
                 f"EV={result['ev']:+.2f}BB) → {result['action'].upper()}")

    return result


def shove_over_limpers_decision(
    hero_cards: List[str],
    hero_stack_bb: float,
    hero_position: str,
    num_limpers: int,
    pot_bb: float,
    player_type: str = 'unknown',
) -> Optional[dict]:
    """Decide whether to shove over limpers.

    Dead money from limpers makes shoving more profitable.
    Each limper adds ~1 BB of dead money that we win uncontested when they fold.

    Args:
        hero_cards: ['AH', 'KS']
        hero_stack_bb: hero's stack in BB
        hero_position: hero's position
        num_limpers: number of limpers before us
        pot_bb: current pot (blinds + limps)
        player_type: limper type (adjusts calling range)

    Returns:
        dict with 'action', 'ev', 'fold_equity', etc.
    """
    if not HAS_EVAL7 or hero_stack_bb > 15 or num_limpers < 1:
        return None

    # Limper's range (wide, passive)
    limper_range = LIMPER_RANGE

    # What a limper calls our shove with
    stack_key = _find_nearest_stack(LIMPER_CALL_VS_SHOVE, hero_stack_bb)
    call_range = LIMPER_CALL_VS_SHOVE[stack_key]

    # With multiple limpers, at least one is more likely to have a hand
    # Approximate by widening the calling range slightly
    if num_limpers >= 3:
        wider_key = _find_nearest_stack(LIMPER_CALL_VS_SHOVE, max(3, hero_stack_bb - 3))
        call_range = LIMPER_CALL_VS_SHOVE.get(wider_key, call_range)

    # Fish limp-call wider
    if player_type in ('fish_passive', 'fish_aggro'):
        wider_key = _find_nearest_stack(LIMPER_CALL_VS_SHOVE, max(3, hero_stack_bb - 2))
        call_range = LIMPER_CALL_VS_SHOVE.get(wider_key, call_range)

    already_in = 1.0 if hero_position == 'BB' else 0.5 if hero_position == 'SB' else 0.0

    result = compute_shove_ev(
        hero_cards=hero_cards,
        hero_stack_bb=hero_stack_bb,
        pot_bb=pot_bb,
        villain_range_str=limper_range,
        villain_call_range_str=call_range,
        villain_stack_bb=100.0,  # Limpers usually cover us
        already_invested_bb=already_in,
    )

    if result:
        result['num_limpers'] = num_limpers

        # SAFETY: Block shove when equity-when-called is terrible.
        # Hard floor at 25%: even with high fold equity, shoving with < 25%
        # equity vs the calling range is too high variance.
        eq_called = result.get('equity_when_called', 0)
        if result['action'] == 'shove':
            hero_canonical = _hero_to_canonical(hero_cards)
            if eq_called < 0.25 and result['ev'] < 0.8:
                log.info(f"SHOVE OVER LIMPERS BLOCKED: {hero_canonical} "
                         f"(eq_called={eq_called:.0%} < 25%, "
                         f"EV={result['ev']:+.2f}BB too marginal)")
                result['action'] = 'fold'

        log.info(f"SHOVE OVER {num_limpers} LIMPER(S): {_hero_to_canonical(hero_cards)} "
                 f"(FE={result['fold_equity']:.0%}, eq_called={result['equity_when_called']:.0%}, "
                 f"EV={result['ev']:+.2f}BB, dead={pot_bb:.1f}BB) → {result['action'].upper()}")

    return result


def fourbet_shove_decision(
    hero_cards: List[str],
    hero_stack_bb: float,
    hero_position: str,
    threebettor_position: str,
    pot_bb: float,
    threebettor_stack_bb: float = 100.0,
    player_type: str = 'unknown',
) -> Optional[dict]:
    """Decide whether to 4-bet shove after hero opened and got 3-bet.

    When hero opened and villain 3-bets, with ≤15 BB effective:
    4-bet shove or fold. Flatting a 3-bet short-stacked is terrible.

    Args:
        hero_cards: ['AH', 'KS']
        hero_stack_bb: hero's remaining stack
        hero_position: hero's position (we opened from here)
        threebettor_position: villain's position
        pot_bb: current pot
        threebettor_stack_bb: villain's stack
        player_type: villain's player type

    Returns:
        dict with 'action', 'ev', etc.
    """
    if not HAS_EVAL7 or hero_stack_bb > 15:
        return None

    # 3-bettor's range (depends on their position relative to us)
    pos_key = f'vs_{hero_position.upper()}'
    threeb_range = THREE_BET_RANGES.get(pos_key, THREE_BET_RANGES['default'])

    # Adjust for player type
    ptype = player_type if player_type in PLAYER_TYPE_RANGES else 'unknown'
    if ptype in ('lag', 'maniac', 'fish_aggro'):
        threeb_range = PLAYER_TYPE_RANGES[ptype].get('3bet', threeb_range)
    elif ptype == 'nit':
        threeb_range = 'QQ+, AKs'

    # What 3-bettor calls our 4-bet shove with (top of their 3-bet range)
    # 3-bettors call 4-bet shoves very tight
    call_range_map = {
        3: 'QQ+, AKs, AKo',
        5: 'QQ+, AKs',
        8: 'KK+, AKs',
        10: 'KK+, AKs',
        12: 'KK+',
        15: 'AA',
    }
    if ptype in ('fish_passive', 'fish_aggro', 'maniac'):
        call_range_map = {
            3: 'TT+, AQs+, AKo',
            5: 'JJ+, AKs, AKo',
            8: 'QQ+, AKs, AKo',
            10: 'QQ+, AKs',
            12: 'KK+, AKs',
            15: 'KK+',
        }

    stack_key = _find_nearest_stack(call_range_map, hero_stack_bb)
    call_range = call_range_map[stack_key]

    # Hero already invested the open raise (~2.5 BB typically)
    already_in = 2.5 if hero_position not in ('SB', 'BB') else 3.0

    result = compute_shove_ev(
        hero_cards=hero_cards,
        hero_stack_bb=hero_stack_bb,
        pot_bb=pot_bb,
        villain_range_str=threeb_range,
        villain_call_range_str=call_range,
        villain_stack_bb=threebettor_stack_bb,
        already_invested_bb=already_in,
    )

    if result:
        result['threeb_range'] = threeb_range[:60]
        result['call_range'] = call_range[:40]
        log.info(f"4BET SHOVE: {_hero_to_canonical(hero_cards)} vs {threebettor_position} 3bet "
                 f"(FE={result['fold_equity']:.0%}, eq_called={result['equity_when_called']:.0%}, "
                 f"EV={result['ev']:+.2f}BB) → {result['action'].upper()}")

    return result


# ── eval7 Bluff Fold Equity & Optimal Sizing ─────────────────────────────
#
# Given villain's estimated range on a specific board, use eval7 to compute
# what fraction of that range can profitably call a bet of size X.
# Hands with equity < pot_odds fold → fold equity.
#
# This replaces the heuristic _estimate_fold_equity() with hard math.


def _board_to_eval7(board_cards: List[str]) -> list:
    """Convert board cards ['QH', 'JD', '2C'] to eval7 Card list."""
    if not HAS_EVAL7:
        return []
    return [c for c in (_convert_card(s) for s in board_cards) if c is not None]


def compute_range_fold_equity(
    hero_cards: List[str],
    board_cards: List[str],
    villain_range_str: str,
    bet_fraction: float = 0.67,
) -> Optional[dict]:
    """Compute fold equity using eval7 hand evaluation.

    Two models are combined:

    1. **Equity model** (flop/turn): For each villain hand, compute equity vs
       hero.  Hands with equity < pot_odds fold.  Works well when draws and
       outs create genuine equity differences.

    2. **Hand-strength model** (river + pure bluffs): Rank every villain hand
       by absolute hand value.  The bottom (1-MDF) of their range folds.
       This models the fact that villain doesn't know hero's exact hand —
       they fold their weakest holdings at a frequency dictated by bet size.

    The final fold equity is the MAX of the two models.  This ensures pure
    bluffs still get credit for fold equity (hand-strength model) while
    semi-bluffs/value bets get accurate equity-based fold equity.

    Args:
        hero_cards: ['AH', 'KS']
        board_cards: ['QH', 'JD', '2C'] (3-5 cards)
        villain_range_str: eval7-compatible range string
        bet_fraction: bet size as fraction of pot (0.33, 0.5, 0.67, 0.75, 1.0)

    Returns:
        dict with 'fold_equity', 'equity_when_called', 'total_combos',
        'folding_combos', 'calling_combos', 'pot_odds', 'mdf'
    """
    if not HAS_EVAL7 or not hero_cards or len(hero_cards) < 2:
        return None
    if not board_cards or len(board_cards) < 3:
        return None

    import random as _rnd

    hero_e7 = [_convert_card(c) for c in hero_cards]
    if None in hero_e7:
        return None
    board_e7 = _board_to_eval7(board_cards)
    if len(board_e7) != len(board_cards):
        return None

    hero_set = set(str(c) for c in hero_e7)
    board_set = set(str(c) for c in board_e7)
    dead = hero_set | board_set

    # Pot odds: villain needs equity >= f / (1 + 2f)
    pot_odds = bet_fraction / (1.0 + 2.0 * bet_fraction)
    # Minimum defense frequency: 1 / (1 + f)
    mdf = 1.0 / (1.0 + bet_fraction)

    try:
        vr = eval7.HandRange(villain_range_str)
    except Exception:
        return None

    # Get all remaining cards for sampling
    all_cards = [eval7.Card(s) for s in (
        r + suit for r in 'AKQJT98765432' for suit in 'shdc'
    )]
    remaining = [c for c in all_cards if str(c) not in dead]

    n_board = len(board_e7)
    cards_needed = 5 - n_board  # 0 for river, 1 for turn, 2 for flop
    N_SAMPLES = 1 if cards_needed == 0 else (150 if cards_needed == 1 else 100)

    # -- Pass 1: compute equity and hand value for each villain combo --
    equity_fold = 0       # Combos that fold by equity model
    hand_values = []      # (hand_value, v_equity_vs_hero) for hand-strength model
    total_equity_called_eq = 0.0
    total_combos = 0

    hero_val_cache = None  # Cache hero hand value (river only)

    for v_cards, _w in vr.hands:
        v0, v1 = str(v_cards[0]), str(v_cards[1])
        if v0 in dead or v1 in dead:
            continue
        total_combos += 1

        v_dead = dead | {v0, v1}
        avail = [c for c in remaining if str(c) not in v_dead]

        if cards_needed == 0:
            # River: exact evaluation
            if hero_val_cache is None:
                hero_val_cache = eval7.evaluate(list(hero_e7) + list(board_e7))
            v_val = eval7.evaluate(list(v_cards) + list(board_e7))
            v_equity = 1.0 if v_val > hero_val_cache else (0.5 if v_val == hero_val_cache else 0.0)
            hand_values.append((v_val, v_equity))
        else:
            # Flop/Turn: sample runouts
            wins = 0
            ties = 0
            v_strength_sum = 0
            for _ in range(N_SAMPLES):
                runout = _rnd.sample(avail, cards_needed)
                full_board = list(board_e7) + runout
                h_val = eval7.evaluate(list(hero_e7) + full_board)
                v_val = eval7.evaluate(list(v_cards) + full_board)
                v_strength_sum += v_val
                if v_val > h_val:
                    wins += 1
                elif v_val == h_val:
                    ties += 1
            v_equity = (wins + ties * 0.5) / N_SAMPLES
            avg_strength = v_strength_sum / N_SAMPLES
            hand_values.append((avg_strength, v_equity))

        if v_equity < pot_odds:
            equity_fold += 1
        else:
            total_equity_called_eq += v_equity

    if total_combos == 0:
        return None

    # -- Model 1: Equity-based fold equity --
    fe_equity = equity_fold / total_combos

    # -- Model 2: Hand-strength-based fold equity (MDF model) --
    # Sort villain hands by absolute strength; bottom (1-MDF) fold
    # because they're the weakest holdings in villain's range.
    hand_values.sort(key=lambda x: x[0])
    max_fold_frac = 1.0 - mdf  # How much of range villain folds at GTO
    n_fold_strength = int(total_combos * max_fold_frac)
    # The hands that fold are the weakest in villain's range
    # Compute hero's equity vs the calling portion (top MDF of range)
    calling_hands = hand_values[n_fold_strength:]
    if calling_hands:
        hero_eq_hs = sum(1.0 - eq for _, eq in calling_hands) / len(calling_hands)
    else:
        hero_eq_hs = 0.5
    fe_strength = n_fold_strength / total_combos if total_combos > 0 else 0.0

    # -- Combine: use the higher of the two models --
    # Equity model is more accurate for semi-bluffs (hero has draws/outs)
    # Hand-strength model is more accurate for pure bluffs (hero has nothing)
    fold_equity = max(fe_equity, fe_strength)

    # Hero's equity when called: use the model that produced fold_equity
    if fe_equity >= fe_strength:
        # Equity model: calling combos are those with equity >= pot_odds
        calling_combos = total_combos - equity_fold
        hero_eq_called = (1.0 - total_equity_called_eq / calling_combos
                          if calling_combos > 0 else 0.5)
    else:
        # Hand-strength model: calling combos are top MDF of range
        calling_combos = total_combos - n_fold_strength
        hero_eq_called = hero_eq_hs

    folding_combos = total_combos - calling_combos

    return {
        'fold_equity': fold_equity,
        'equity_when_called': hero_eq_called,
        'total_combos': total_combos,
        'folding_combos': folding_combos,
        'calling_combos': calling_combos,
        'pot_odds': pot_odds,
        'mdf': mdf,
        'bet_fraction': bet_fraction,
        'fe_equity_model': round(fe_equity, 3),
        'fe_strength_model': round(fe_strength, 3),
    }


def compute_bluff_ev(
    hero_cards: List[str],
    board_cards: List[str],
    villain_range_str: str,
    pot_bb: float,
    hero_stack_bb: float = 100.0,
    bet_fractions: Optional[List[float]] = None,
) -> Optional[dict]:
    """Compute bluff EV at multiple bet sizes using eval7 fold equity.

    For each bet size:
        bluff_ev = fold_eq × pot + (1 - fold_eq) × (hero_eq × (pot + 2×bet) - bet)
        check_ev = hero_eq_vs_full_range × pot

    Args:
        hero_cards: ['AH', 'KS']
        board_cards: ['QH', 'JD', '2C']
        villain_range_str: eval7-compatible range
        pot_bb: current pot in BB
        hero_stack_bb: hero's remaining stack
        bet_fractions: list of bet sizes as fractions of pot (default: common sizes)

    Returns:
        dict with 'optimal_size', 'optimal_ev', 'check_ev', 'sizings' (list per size)
    """
    if not HAS_EVAL7 or not hero_cards or not board_cards:
        return None

    if bet_fractions is None:
        bet_fractions = [0.33, 0.50, 0.67, 0.75, 1.0]

    # Filter out bet sizes that exceed our stack
    max_bet_bb = hero_stack_bb
    bet_fractions = [f for f in bet_fractions if f * pot_bb <= max_bet_bb]
    if not bet_fractions:
        bet_fractions = [max_bet_bb / pot_bb] if pot_bb > 0 else [0.5]

    # Compute check equity (hero vs full villain range, no bet)
    try:
        h_cards = [_convert_card(c) for c in hero_cards]
        b_cards = _board_to_eval7(board_cards)
        if None in h_cards:
            return None
        check_eq = eval7.py_hand_vs_range_monte_carlo(
            h_cards, eval7.HandRange(villain_range_str), b_cards, 5000
        )
    except Exception:
        check_eq = 0.5
    check_ev = check_eq * pot_bb

    sizings = []
    best_ev = check_ev
    best_size = None

    for frac in bet_fractions:
        fe_result = compute_range_fold_equity(
            hero_cards, board_cards, villain_range_str, frac
        )
        if not fe_result:
            continue

        bet_bb = frac * pot_bb
        fold_eq = fe_result['fold_equity']
        hero_eq_called = fe_result['equity_when_called']

        # EV when villain folds
        ev_fold = fold_eq * pot_bb
        # EV when villain calls
        ev_called = (1 - fold_eq) * (
            hero_eq_called * (pot_bb + 2 * bet_bb) - bet_bb
        )
        bluff_ev = ev_fold + ev_called
        ev_gain = bluff_ev - check_ev

        sizing_info = {
            'bet_fraction': frac,
            'bet_bb': round(bet_bb, 1),
            'fold_equity': fold_eq,
            'hero_eq_called': hero_eq_called,
            'bluff_ev': round(bluff_ev, 3),
            'check_ev': round(check_ev, 3),
            'ev_gain': round(ev_gain, 3),
            'profitable': ev_gain > 0,
        }
        sizings.append(sizing_info)

        if bluff_ev > best_ev:
            best_ev = bluff_ev
            best_size = sizing_info

    action = 'bet' if best_size and best_size['ev_gain'] > 0 else 'check'
    result = {
        'action': action,
        'check_ev': round(check_ev, 3),
        'check_equity': round(check_eq, 3),
        'optimal_size': best_size,
        'sizings': sizings,
    }

    if best_size:
        log.info(f"BLUFF ANALYSIS: {_hero_to_canonical(hero_cards)} on "
                 f"{' '.join(board_cards)} → {action.upper()} "
                 f"(best={best_size['bet_fraction']:.0%}pot, "
                 f"FE={best_size['fold_equity']:.0%}, "
                 f"EV={best_size['ev_gain']:+.2f}BB)")

    return result


# ── Tournament Math: Urgency, Wait Equity, Blind Pressure ────────────────
#
# In tournaments (Spin & Gold, SNG, MTT), chip EV ≠ $ EV.
# These functions compute how urgently hero needs to act given:
# - Stack depth (M-ratio)
# - Blind increases (time pressure)
# - Probability of getting a better hand (wait equity)
# - ICM pressure (survival value)

# Spin & Gold blind structure (GGSystem, BB display mode)
# Each level lasts ~3 minutes. Stacks start at 25 BB (500 chips at 10/20).
SPIN_GOLD_LEVELS = [
    # (level, bb_chips, duration_sec)
    (1, 20, 180),
    (2, 30, 180),
    (3, 40, 180),
    (4, 60, 180),
    (5, 100, 180),
    (6, 150, 180),
    (7, 200, 180),
    (8, 300, 180),
    (9, 400, 180),
    (10, 600, 180),
]

# Probability of being dealt a hand at least as strong as X
# Based on 169 distinct starting hands (1326 combos)
# These are the cumulative probabilities for hand categories
HAND_CATEGORY_PROBS = {
    'AA':           6 / 1326,       # 0.45%
    'KK+':          12 / 1326,      # 0.90%
    'QQ+':          18 / 1326,      # 1.36%
    'JJ+':          24 / 1326,      # 1.81%
    'TT+':          30 / 1326,      # 2.26%
    '99+':          36 / 1326,      # 2.71%
    '77+':          48 / 1326,      # 3.62%
    '55+':          60 / 1326,      # 4.52%
    '22+':          78 / 1326,      # 5.88%
    'AKs':          4 / 1326,       # 0.30%
    'AK':           16 / 1326,      # 1.21%
    'top_10pct':    0.10,           # top 10% of hands
    'top_20pct':    0.20,
    'top_30pct':    0.30,
    'top_50pct':    0.50,
}


def m_ratio(hero_stack_bb: float, num_players: int = 6) -> dict:
    """Calculate M-ratio and Harrington zone.

    M = stack / cost_per_orbit
    cost_per_orbit = SB + BB + antes = 1.5 BB (no antes in most GGSystem games)

    Zones:
        Green:  M > 20  — Full strategy, all options open
        Yellow: 10 < M ≤ 20 — Avoid marginal spots, tighten ranges
        Orange: 6 < M ≤ 10 — Start shoving wider, no flat-calling
        Red:    1 < M ≤ 6  — Push/fold mode, shove or fold
        Dead:   M ≤ 1  — Forced all-in on next blind

    Args:
        hero_stack_bb: hero's stack in BB
        num_players: players at table (affects orbit cost with antes)

    Returns:
        dict with 'm', 'zone', 'orbits_left', 'hands_left', 'urgency'
    """
    cost_per_orbit = 1.5  # SB(0.5) + BB(1.0), no antes
    m = hero_stack_bb / cost_per_orbit if cost_per_orbit > 0 else 999

    if m > 20:
        zone = 'green'
        urgency = 0.0
    elif m > 10:
        zone = 'yellow'
        urgency = 0.2
    elif m > 6:
        zone = 'orange'
        urgency = 0.5
    elif m > 1:
        zone = 'red'
        urgency = 0.8
    else:
        zone = 'dead'
        urgency = 1.0

    hands_per_orbit = num_players
    hands_left = m * hands_per_orbit

    return {
        'm': round(m, 1),
        'zone': zone,
        'orbits_left': round(m, 1),
        'hands_left': round(hands_left, 0),
        'urgency': urgency,
        'cost_per_orbit': cost_per_orbit,
    }


def hands_until_blind(hero_position: str, num_players: int = 6) -> dict:
    """How many hands until hero pays BB and SB.

    In a 6-max game, positions rotate: UTG→MP→CO→BTN→SB→BB
    After posting BB, hero has (num_players - 1) hands before paying BB again.

    Args:
        hero_position: 'UTG', 'MP', 'CO', 'BTN', 'SB', 'BB'
        num_players: players at table

    Returns:
        dict with 'hands_to_bb', 'hands_to_sb', 'blind_cost_next_orbit'
    """
    pos_order = ['UTG', 'MP', 'CO', 'BTN', 'SB', 'BB']
    # Trim to actual number of players (short-handed)
    if num_players <= len(pos_order):
        pos_order = pos_order[len(pos_order) - num_players:]

    try:
        idx = pos_order.index(hero_position)
    except ValueError:
        idx = 0

    bb_idx = pos_order.index('BB')
    sb_idx = pos_order.index('SB')

    hands_to_bb = (bb_idx - idx) % len(pos_order)
    hands_to_sb = (sb_idx - idx) % len(pos_order)
    if hands_to_bb == 0:
        hands_to_bb = len(pos_order)  # Just paid BB, full orbit until next
    if hands_to_sb == 0:
        hands_to_sb = len(pos_order)

    return {
        'hands_to_bb': hands_to_bb,
        'hands_to_sb': hands_to_sb,
        'blind_cost_next_orbit': 1.5,  # SB + BB
    }


def wait_for_better_spot(
    hero_cards: List[str],
    hero_stack_bb: float,
    hero_position: str,
    num_players: int = 6,
    current_shove_ev: float = 0.0,
    hands_per_blind_level: int = 30,
) -> dict:
    """Should hero take this marginal spot or wait for a better hand?

    Calculates the EV of folding and waiting vs. playing now.

    The "wait EV" accounts for:
    1. Blind erosion: hero loses BB/SB each orbit
    2. Hand distribution: probability of premium hands in next N hands
    3. Stack shrinkage: lower stack = less fold equity = worse shove EV
    4. Blind increases: stack in BB terms shrinks even if chip count stays same

    Key insight: the cost of folding = blind_cost × P(paying blind before
    getting a better spot). If hero is BTN with 5 hands to BB, folding
    costs nothing immediately. If hero IS BB, folding costs 1 BB.

    Args:
        hero_cards: current hand ['AH', 'KS']
        hero_stack_bb: current stack in BB
        hero_position: current position
        num_players: players at table
        current_shove_ev: EV of shoving this hand (from push/fold calc)
        hands_per_blind_level: approx hands per blind level (~30 for Spin & Gold)

    Returns:
        dict with 'wait_ev', 'play_ev', 'recommendation', 'premium_prob',
        'hands_until_critical', etc.
    """
    blind_info = hands_until_blind(hero_position, num_players)
    m_info = m_ratio(hero_stack_bb, num_players)

    # Cost of folding this hand: 0 unless we're in the blinds right now
    fold_cost = 0.0
    if hero_position == 'BB':
        fold_cost = 0.0  # Already posted, no additional cost
    elif hero_position == 'SB':
        fold_cost = 0.0  # Already posted

    # Blind erosion: how much stack shrinks per orbit
    blind_per_orbit = 1.5
    orbits_left = hero_stack_bb / blind_per_orbit

    # Probability of getting a "good enough" hand in N hands
    # For push/fold, what hands are +EV to shove?
    # At 10 BB, ~30-50% of hands are +EV shoves from late position
    # At 5 BB, ~60-80% of hands are +EV shoves
    # At 15 BB, ~15-25% of hands are +EV shoves
    if hero_stack_bb <= 5:
        good_hand_prob = 0.70   # Almost anything is +EV
    elif hero_stack_bb <= 8:
        good_hand_prob = 0.45
    elif hero_stack_bb <= 10:
        good_hand_prob = 0.35
    elif hero_stack_bb <= 12:
        good_hand_prob = 0.25
    else:
        good_hand_prob = 0.20

    # Premium hand probability (hands that are clearly better than current)
    hand_str = _hero_to_canonical(hero_cards)
    if hand_str in ('AA', 'KK', 'QQ', 'AKs', 'AKo'):
        premium_prob = 0.01  # Already premium — almost nothing is better
    elif hand_str in ('JJ', 'TT', 'AQs', 'AQo', 'AJs'):
        premium_prob = 0.03  # ~3% chance of getting AA-QQ or AK
    elif hand_str and hand_str[0] == 'A':
        premium_prob = 0.06  # ~6% of getting top 7% hand
    else:
        premium_prob = 0.10  # ~10% of getting top 10% hand

    # Expected number of hands until a premium hand
    expected_hands_to_premium = 1.0 / premium_prob if premium_prob > 0 else 100

    # Blind cost until premium: how many BB we lose waiting
    blind_cost_waiting = 0.0
    hands_waited = 0
    stack_after = hero_stack_bb
    for h in range(1, int(expected_hands_to_premium) + 1):
        # Every num_players hands, we pay SB + BB
        if h % num_players == blind_info['hands_to_bb']:
            blind_cost_waiting += 1.0  # BB
            stack_after -= 1.0
        elif h % num_players == blind_info['hands_to_sb']:
            blind_cost_waiting += 0.5  # SB
            stack_after -= 0.5
        hands_waited = h
        if stack_after <= 1.0:
            break  # Would be blinded out

    # EV of waiting: premium_prob × stack_ev_with_premium - blind_erosion
    # When we get premium, we shove with high equity (~70-85% when called)
    # Stack EV of premium shove ≈ 0.5 × hero_stack (conservative estimate)
    premium_shove_ev = max(1.0, hero_stack_bb * 0.15)  # ~15% of stack
    wait_ev = -blind_cost_waiting + (premium_prob * hands_waited) * premium_shove_ev

    # Compare play_now EV vs wait EV
    play_ev = current_shove_ev
    ev_diff = play_ev - wait_ev

    if play_ev > 0 and play_ev > wait_ev:
        recommendation = 'play'
    elif m_info['zone'] in ('red', 'dead'):
        recommendation = 'play'  # Can't afford to wait
    elif play_ev <= 0:
        recommendation = 'wait'
    else:
        recommendation = 'wait' if wait_ev > play_ev else 'play'

    # How many hands until stack becomes critically low
    hands_to_critical = 0
    s = hero_stack_bb
    for i in range(1, 100):
        if i % num_players in (0, 1):  # Roughly BB + SB
            s -= 1.5
        if s <= 5:
            hands_to_critical = i
            break

    return {
        'play_ev': round(play_ev, 2),
        'wait_ev': round(wait_ev, 2),
        'recommendation': recommendation,
        'm_ratio': m_info['m'],
        'zone': m_info['zone'],
        'hands_left': m_info['hands_left'],
        'premium_prob': round(premium_prob, 3),
        'expected_hands_to_premium': round(expected_hands_to_premium, 1),
        'blind_cost_waiting': round(blind_cost_waiting, 1),
        'stack_after_waiting': round(stack_after, 1),
        'hands_to_critical': hands_to_critical,
        'hands_to_bb': blind_info['hands_to_bb'],
        'urgency': m_info['urgency'],
    }


def blind_increase_pressure(
    hero_stack_chips: float,
    current_bb_chips: float,
    level_index: int = 0,
) -> dict:
    """Calculate pressure from upcoming blind increases.

    In Spin & Gold, blinds increase every ~3 minutes.
    If hero has 500 chips at 20 BB (25 BB), after blinds go to 30,
    hero has 500/30 = 16.7 BB — stack shrinks by 33%.

    Args:
        hero_stack_chips: hero's stack in chips
        current_bb_chips: current BB in chips
        level_index: current blind level (0-based index into SPIN_GOLD_LEVELS)

    Returns:
        dict with current BB stack, next level stack, pressure factor
    """
    current_bb_stack = hero_stack_chips / current_bb_chips if current_bb_chips > 0 else 25

    # Find next level
    if level_index + 1 < len(SPIN_GOLD_LEVELS):
        next_bb_chips = SPIN_GOLD_LEVELS[level_index + 1][1]
        next_bb_stack = hero_stack_chips / next_bb_chips
        stack_loss_pct = 1.0 - (next_bb_stack / current_bb_stack) if current_bb_stack > 0 else 0
    else:
        next_bb_chips = current_bb_chips
        next_bb_stack = current_bb_stack
        stack_loss_pct = 0.0

    # Pressure: how much worse off we'll be after blind increase
    # If we go from 15 BB to 10 BB, that's a big deal (orange → red zone)
    current_m = m_ratio(current_bb_stack)
    next_m = m_ratio(next_bb_stack)

    zone_changed = current_m['zone'] != next_m['zone']

    return {
        'current_bb_stack': round(current_bb_stack, 1),
        'next_bb_stack': round(next_bb_stack, 1),
        'stack_loss_pct': round(stack_loss_pct * 100, 1),
        'current_zone': current_m['zone'],
        'next_zone': next_m['zone'],
        'zone_changes': zone_changed,
        'should_widen_now': zone_changed and next_m['zone'] in ('red', 'dead'),
        'seconds_per_level': SPIN_GOLD_LEVELS[level_index][2] if level_index < len(SPIN_GOLD_LEVELS) else 180,
    }


# ── Bayesian Range Tracker: Beyond-GTO Exploitative Engine ──────────────
#
# If villain plays GTO, their actions are predictable signals:
#   - Big bet on wet board → polarized range (nuts or air)
#   - Check → capped range (no monsters)
#   - Call → medium-strength draws/pairs
#   - Raise → polarized (strong value or semi-bluff)
#
# By tracking every action and narrowing the range combo-by-combo,
# we can PREDICT their hand and EXPLOIT the narrowed range.
#
# This goes BEYOND GTO: instead of playing a balanced strategy,
# we deviate to maximize EV against villain's revealed range.

# Action likelihood: P(action | hand_category)
# How likely is a rational player to take action X with hand category Y?
ACTION_LIKELIHOOD = {
    'bet_large': {  # 66%+ pot — polarized
        'monster': 0.95, 'strong': 0.40, 'medium': 0.10,
        'weak': 0.05,   'air': 0.30,    'draw': 0.70,
    },
    'bet_medium': {  # 40-65% pot — slightly polarized
        'monster': 0.75, 'strong': 0.80, 'medium': 0.40,
        'weak': 0.12,   'air': 0.20,    'draw': 0.55,
    },
    'bet_small': {  # <40% pot — merged
        'monster': 0.55, 'strong': 0.85, 'medium': 0.65,
        'weak': 0.25,   'air': 0.15,    'draw': 0.40,
    },
    'check': {
        'monster': 0.10, 'strong': 0.35, 'medium': 0.75,
        'weak': 0.70,   'air': 0.60,    'draw': 0.35,
    },
    'call': {
        'monster': 0.30, 'strong': 0.80, 'medium': 0.70,
        'weak': 0.15,   'air': 0.05,    'draw': 0.80,
    },
    'raise': {
        'monster': 0.90, 'strong': 0.15, 'medium': 0.03,
        'weak': 0.00,   'air': 0.20,    'draw': 0.50,
    },
    'all_in': {
        'monster': 0.95, 'strong': 0.25, 'medium': 0.05,
        'weak': 0.00,   'air': 0.15,    'draw': 0.40,
    },
}

# Player type modifiers — multiply the base likelihood
PLAYER_LIKELIHOOD_MOD = {
    'nit':          {'air': 0.1, 'draw': 0.5, 'weak': 0.3, 'medium': 0.7, 'strong': 1.2, 'monster': 1.3},
    'tag':          {'air': 0.6, 'draw': 0.9, 'weak': 0.5, 'medium': 0.9, 'strong': 1.1, 'monster': 1.1},
    'lag':          {'air': 1.5, 'draw': 1.3, 'weak': 1.2, 'medium': 1.0, 'strong': 1.0, 'monster': 1.0},
    'fish_passive': {'air': 0.3, 'draw': 0.4, 'weak': 0.6, 'medium': 1.2, 'strong': 1.3, 'monster': 1.0},
    'fish_aggro':   {'air': 1.3, 'draw': 1.2, 'weak': 1.1, 'medium': 1.0, 'strong': 1.0, 'monster': 0.9},
    'maniac':       {'air': 2.0, 'draw': 1.5, 'weak': 1.5, 'medium': 1.0, 'strong': 0.8, 'monster': 0.8},
    'unknown':      {'air': 1.0, 'draw': 1.0, 'weak': 1.0, 'medium': 1.0, 'strong': 1.0, 'monster': 1.0},
}

# Later streets = fewer bluffs (bluff decay)
STREET_BLUFF_DECAY = {'flop': 1.0, 'turn': 0.7, 'river': 0.5}


def _classify_combo_on_board(combo_cards, board_e7, hero_set, board_set):
    """Classify a combo's strength + draw status on the board.

    Args:
        combo_cards: eval7 card pair from HandRange.hands
        board_e7: list of eval7 Card for the board
        hero_set: set of hero card strings (for dead card check)
        board_set: set of board card strings

    Returns:
        dict with 'score', 'category', 'has_draw', 'draw_type', 'draw_outs'
        or None if combo is dead.
    """
    if not HAS_EVAL7:
        return None

    v0, v1 = str(combo_cards[0]), str(combo_cards[1])
    dead = hero_set | board_set
    if v0 in dead or v1 in dead:
        return None

    hand = list(combo_cards) + list(board_e7)
    score = eval7.evaluate(hand)
    hand_type = eval7.handtype(score)

    # Board-only score for comparison (5 cards needed)
    n_board = len(board_e7)

    # Classify into categories
    # eval7 hand types: 'High Card','Pair','Two Pair','Trips',
    #   'Straight','Flush','Full House','Quads','Straight Flush'
    if hand_type in ('Straight Flush', 'Quads'):
        category = 'monster'
    elif hand_type == 'Full House':
        category = 'monster'
    elif hand_type == 'Flush':
        category = 'strong'
    elif hand_type == 'Straight':
        category = 'strong'
    elif hand_type == 'Trips':
        category = 'strong'
    elif hand_type == 'Two Pair':
        # Check if both cards contribute (not just board two pair)
        board_only = eval7.evaluate(list(board_e7) + [combo_cards[0]]) if n_board >= 4 else 0
        if score > board_only + 1000:
            category = 'medium'
        else:
            category = 'weak'
    elif hand_type == 'Pair':
        # Top pair or overpair = medium, lower pairs = weak
        if n_board >= 3:
            board_ranks = sorted([int(str(c)[0] in 'AKQJT') or ord(str(c)[0]) for c in board_e7], reverse=True)
            r1 = str(combo_cards[0])[0].upper()
            r2 = str(combo_cards[1])[0].upper()
            top_board_rank = str(board_e7[0])[0] if board_e7 else '2'
            # Rough check: if hero rank matches top board rank → top pair
            rank_vals = {'A': 14, 'K': 13, 'Q': 12, 'J': 11, 'T': 10,
                         '9': 9, '8': 8, '7': 7, '6': 6, '5': 5, '4': 4, '3': 3, '2': 2}
            hero_ranks = [rank_vals.get(r1, 0), rank_vals.get(r2, 0)]
            board_rank_vals = [rank_vals.get(str(c)[0].upper(), 0) for c in board_e7]
            max_board = max(board_rank_vals) if board_rank_vals else 0
            max_hero = max(hero_ranks)
            if max_hero > max_board:
                category = 'medium'  # overpair
            elif max_hero == max_board:
                category = 'medium'  # top pair
            else:
                category = 'weak'    # underpair or low pair
        else:
            category = 'weak'
    else:
        # High card
        category = 'air'

    # Draw detection (flop/turn only)
    has_draw = False
    draw_type = None
    draw_outs = 0

    if n_board <= 4:  # draws only matter pre-river
        all_cards_str = [v0, v1] + [str(c) for c in board_e7]
        suits = [c[-1] for c in all_cards_str]
        ranks_str = [c[0].upper() for c in all_cards_str]
        rank_vals = {'A': 14, 'K': 13, 'Q': 12, 'J': 11, 'T': 10,
                     '9': 9, '8': 8, '7': 7, '6': 6, '5': 5, '4': 4, '3': 3, '2': 2}

        # Flush draw: 4 of same suit (hero contributes ≥1)
        from collections import Counter
        suit_counts = Counter(suits)
        hero_suits = [v0[-1], v1[-1]]
        for s, cnt in suit_counts.items():
            if cnt >= 4 and s in hero_suits:
                if hand_type != 'Flush':  # not already a flush
                    has_draw = True
                    draw_type = 'flush_draw'
                    draw_outs = 9
                    break

        # Straight draw (OESD = 8 outs, gutshot = 4 outs)
        if not has_draw and hand_type not in ('Straight', 'Straight Flush'):
            unique_ranks = sorted(set(rank_vals.get(r, 0) for r in ranks_str), reverse=True)
            # Add ace-low (A=1) for wheel draws
            if 14 in unique_ranks:
                unique_ranks.append(1)
            # Check for 4 in a row (OESD) or 4 in 5 (gutshot)
            for start in range(len(unique_ranks) - 3):
                window = unique_ranks[start:start + 4]
                span = window[0] - window[-1]
                if span == 3 and len(set(window)) == 4:
                    # 4 consecutive ranks = OESD (open-ended)
                    has_draw = True
                    draw_type = 'oesd'
                    draw_outs = 8
                    break
                elif span == 4 and len(set(window)) == 4:
                    # 4 ranks spanning 5 = gutshot
                    has_draw = True
                    draw_type = 'gutshot'
                    draw_outs = 4
                    break

    # Draws can upgrade the category
    if has_draw and category == 'air':
        category = 'draw'
    elif has_draw and category == 'weak':
        category = 'draw'  # weak pair + draw = treat as draw

    return {
        'score': score,
        'hand_type': hand_type,
        'category': category,
        'has_draw': has_draw,
        'draw_type': draw_type,
        'draw_outs': draw_outs,
    }


def _action_to_likelihood_key(action: str, bet_size_pct: float) -> str:
    """Map action + sizing to likelihood table key."""
    if action in ('check',):
        return 'check'
    if action in ('call',):
        return 'call'
    if action in ('raise',):
        return 'raise'
    if action in ('all_in',):
        return 'all_in'
    # bet: classify by size
    if bet_size_pct >= 0.66:
        return 'bet_large'
    elif bet_size_pct >= 0.40:
        return 'bet_medium'
    return 'bet_small'


class BayesianRangeTracker:
    """Track and narrow villain's range across streets using Bayesian updates.

    The core insight: if villain plays GTO (or close to it), every action
    they take is a signal that narrows their range. A big bet means polarized
    (strong value + bluffs), a check means capped (no monsters), a call
    means medium strength.

    By tracking these signals across streets, we can predict their hand
    with increasing accuracy and deviate from GTO to exploit the prediction.
    """

    def __init__(self):
        self._re = RangeEquity()

    def create_initial_range(
        self,
        position: str,
        preflop_action: str,
        player_type: str,
        hero_cards: List[str],
        board: Optional[List[str]] = None,
    ) -> dict:
        """Create the starting villain range from preflop action.

        Returns a VillainRange dict with:
            'combos': list of (card1_str, card2_str, weight)
            'history': []
            'initial_range_str': str
            'player_type': str
            'position': str
        """
        range_str = self._re.estimate_villain_range(
            position=position,
            action=preflop_action,
            player_type=player_type,
            street='preflop',
        )

        combos = []
        if HAS_EVAL7:
            try:
                hr = eval7.HandRange(range_str)
                hero_e7 = [_convert_card(c) for c in hero_cards if c]
                hero_set = set(str(c) for c in hero_e7 if c)
                board_set = set()
                if board:
                    board_set = set(str(c) for c in
                                    [_convert_card(b) for b in board if b] if c)
                dead = hero_set | board_set

                for cards, _w in hr.hands:
                    c0, c1 = str(cards[0]), str(cards[1])
                    if c0 not in dead and c1 not in dead:
                        combos.append((c0, c1, 1.0))
            except Exception as e:
                log.debug(f"BayesianTracker: init range failed: {e}")

        return {
            'combos': combos,
            'history': [],
            'initial_range_str': range_str,
            'player_type': player_type,
            'position': position,
        }

    def narrow_range(
        self,
        villain_range: dict,
        board_cards: List[str],
        action: str,
        bet_size_pct: float,
        street: str,
        player_type: Optional[str] = None,
    ) -> dict:
        """Narrow the range based on an observed action.

        For each combo, compute P(action | hand) and multiply the weight.
        Hands unlikely to take this action get their weight reduced.

        Args:
            villain_range: dict from create_initial_range or previous narrow
            board_cards: current board ['QH', 'JD', '2C']
            action: 'bet', 'check', 'raise', 'call', 'all_in'
            bet_size_pct: bet as fraction of pot (0.0 for check)
            street: 'flop', 'turn', 'river'
            player_type: override player type

        Returns:
            Updated villain_range dict with narrowed weights
        """
        if not HAS_EVAL7 or not villain_range.get('combos'):
            return villain_range

        ptype = player_type or villain_range.get('player_type', 'unknown')
        board_e7 = _board_to_eval7(board_cards)
        if not board_e7:
            return villain_range

        hero_set = set()  # hero cards already excluded at creation
        board_set = set(str(c) for c in board_e7)

        # Get likelihood table
        lik_key = _action_to_likelihood_key(action, bet_size_pct)
        base_lik = ACTION_LIKELIHOOD.get(lik_key, ACTION_LIKELIHOOD['check'])
        ptype_mod = PLAYER_LIKELIHOOD_MOD.get(ptype, PLAYER_LIKELIHOOD_MOD['unknown'])
        bluff_decay = STREET_BLUFF_DECAY.get(street, 1.0)

        combos_before = sum(1 for _, _, w in villain_range['combos'] if w > 0.01)
        new_combos = []

        for c0, c1, old_weight in villain_range['combos']:
            if old_weight < 0.01:
                new_combos.append((c0, c1, 0.0))
                continue

            # Classify this combo on the board
            try:
                combo_e7 = [eval7.Card(c0), eval7.Card(c1)]
                info = _classify_combo_on_board(combo_e7, board_e7, hero_set, board_set)
            except Exception:
                new_combos.append((c0, c1, old_weight))
                continue

            if info is None:
                new_combos.append((c0, c1, 0.0))
                continue

            cat = info['category']

            # Compute likelihood P(action | this hand category)
            lik = base_lik.get(cat, 0.5)

            # Apply player type modifier
            lik *= ptype_mod.get(cat, 1.0)

            # Apply bluff decay for air/draw on later streets
            if cat in ('air', 'draw'):
                lik *= bluff_decay

            # Clamp to [0.01, 1.0] — never fully eliminate
            lik = max(0.01, min(1.0, lik))

            # Bayesian update: new_weight = old_weight * P(action | hand)
            new_weight = old_weight * lik
            new_combos.append((c0, c1, new_weight))

        # Normalize weights so max = 1.0
        max_w = max((w for _, _, w in new_combos), default=1.0)
        if max_w > 0:
            new_combos = [(c0, c1, w / max_w) for c0, c1, w in new_combos]

        combos_after = sum(1 for _, _, w in new_combos if w > 0.10)

        # Record action in history
        history = list(villain_range.get('history', []))
        history.append({
            'street': street,
            'action': action,
            'sizing': round(bet_size_pct, 2),
            'combos_before': combos_before,
            'combos_after': combos_after,
        })

        result = dict(villain_range)
        result['combos'] = new_combos
        result['history'] = history

        log.info(f"BAYESIAN NARROW: {street} {action} {bet_size_pct:.0%}pot "
                 f"→ {combos_before}→{combos_after} combos "
                 f"(type={ptype}, lik_key={lik_key})")

        return result

    def get_range_analysis(
        self,
        villain_range: dict,
        board_cards: List[str],
        hero_cards: List[str],
    ) -> Optional[dict]:
        """Analyze the current narrowed range.

        Returns dict with equity, range composition, exploit recommendation.
        """
        if not HAS_EVAL7 or not villain_range.get('combos'):
            return None

        board_e7 = _board_to_eval7(board_cards)
        if not board_e7:
            return None

        hero_e7 = [_convert_card(c) for c in hero_cards if c]
        hero_e7 = [c for c in hero_e7 if c is not None]
        if len(hero_e7) != 2:
            return None

        hero_set = set(str(c) for c in hero_e7)
        board_set = set(str(c) for c in board_e7)
        hero_score = eval7.evaluate(list(hero_e7) + list(board_e7)) if len(board_e7) == 5 else None

        # Analyze each weighted combo
        cat_weights = {'monster': 0, 'strong': 0, 'medium': 0,
                       'weak': 0, 'air': 0, 'draw': 0}
        total_weight = 0.0
        wins = 0.0
        top_combos = []
        n_active = 0

        for c0, c1, w in villain_range['combos']:
            if w < 0.10:
                continue
            n_active += 1

            try:
                combo_e7 = [eval7.Card(c0), eval7.Card(c1)]
                info = _classify_combo_on_board(combo_e7, board_e7, hero_set, board_set)
            except Exception:
                continue

            if info is None:
                continue

            cat_weights[info['category']] += w
            total_weight += w

            # Hero equity: check if hero beats this combo
            if hero_score is not None:
                # River: exact
                if info['score'] < hero_score:
                    wins += w
                elif info['score'] == hero_score:
                    wins += w * 0.5
            else:
                # Flop/turn: approximate — hero beats worse categories
                hero_is_better = info['category'] in ('air', 'weak')
                if hero_is_better:
                    wins += w * 0.65
                elif info['category'] == 'draw':
                    wins += w * 0.55
                elif info['category'] == 'medium':
                    wins += w * 0.40
                else:
                    wins += w * 0.25

            # Track top combos
            top_combos.append((c0, c1, w, info['category']))

        if total_weight == 0:
            return None

        equity = wins / total_weight
        # Normalize category percentages
        cat_pcts = {k: v / total_weight for k, v in cat_weights.items()}

        # Sort top combos by weight
        top_combos.sort(key=lambda x: x[2], reverse=True)
        top_5 = [(f"{c0[0]}{c1[0]}", cat, round(w / total_weight * 100))
                  for c0, c1, w, cat in top_combos[:8]]

        # Range classification
        value_pct = cat_pcts.get('monster', 0) + cat_pcts.get('strong', 0)
        bluff_pct = cat_pcts.get('air', 0) + cat_pcts.get('draw', 0) * 0.5
        is_capped = cat_pcts.get('monster', 0) < 0.05
        is_polarized = value_pct > 0.30 and bluff_pct > 0.20 and cat_pcts.get('medium', 0) < 0.25
        is_merged = not is_polarized and not is_capped

        return {
            'equity': round(equity, 3),
            'num_combos': n_active,
            'value_pct': round(value_pct, 3),
            'bluff_pct': round(bluff_pct, 3),
            'draw_pct': round(cat_pcts.get('draw', 0), 3),
            'medium_pct': round(cat_pcts.get('medium', 0), 3),
            'weak_pct': round(cat_pcts.get('weak', 0), 3),
            'is_capped': is_capped,
            'is_polarized': is_polarized,
            'is_merged': is_merged,
            'top_combos': top_5,
            'categories': {k: round(v, 3) for k, v in cat_pcts.items()},
            'history': villain_range.get('history', []),
        }

    def get_exploit_recommendation(
        self,
        analysis: dict,
        hero_equity: float,
        hero_hand_strength: str,
        pot_bb: float,
        stack_bb: float,
        street: str,
        is_ip: bool,
    ) -> dict:
        """Given the range analysis, recommend the exploitative play.

        Args:
            analysis: dict from get_range_analysis()
            hero_equity: hero's equity vs the narrowed range
            hero_hand_strength: from _classify_hand() — 'weak','medium','strong','monster'
            pot_bb: current pot
            stack_bb: hero's remaining stack
            street: 'flop', 'turn', 'river'
            is_ip: True if hero is in position

        Returns:
            dict with 'action', 'sizing_pct', 'confidence', 'reasoning', 'exploits'
        """
        if not analysis:
            return {'action': 'check', 'sizing_pct': 0.0, 'confidence': 0.0,
                    'reasoning': 'No analysis available', 'exploits': []}

        exploits = []
        action = 'check'
        sizing_pct = 0.0
        confidence = 0.0
        reasoning_parts = []

        is_capped = analysis.get('is_capped', False)
        is_polarized = analysis.get('is_polarized', False)
        bluff_pct = analysis.get('bluff_pct', 0)
        value_pct = analysis.get('value_pct', 0)
        num_combos = analysis.get('num_combos', 0)

        # ── Exploit 1: Capped range → attack with larger bets ──
        if is_capped and hero_hand_strength in ('medium', 'strong', 'monster', 'very_strong'):
            # Villain's range has no monsters → we can bet big for value
            # or bluff big since they can't have the nuts
            if hero_hand_strength in ('strong', 'monster', 'very_strong'):
                action = 'bet'
                sizing_pct = 0.75 if street == 'river' else 0.66
                confidence = 0.70
                reasoning_parts.append("Villain range capped (no monsters after check)")
                exploits.append({'type': 'capped_range', 'exploit': 'overbet_value'})
            elif hero_hand_strength == 'medium':
                action = 'bet'
                sizing_pct = 0.50  # thinner value bet
                confidence = 0.55
                reasoning_parts.append("Villain capped — thin value bet")
                exploits.append({'type': 'capped_range', 'exploit': 'thin_value'})

        # ── Exploit 2: Too many bluffs → call down with bluff-catchers ──
        elif bluff_pct > 0.35 and hero_hand_strength in ('medium', 'marginal'):
            action = 'call'
            confidence = min(0.80, 0.50 + bluff_pct)
            reasoning_parts.append(f"Villain range is {bluff_pct:.0%} bluffs — call as bluff-catcher")
            exploits.append({'type': 'too_many_bluffs', 'exploit': 'call_down'})

        # ── Exploit 3: Polarized range → raise with value, fold weak ──
        elif is_polarized:
            if hero_hand_strength in ('strong', 'monster', 'very_strong'):
                action = 'raise'
                sizing_pct = 2.5  # raise to 2.5x their bet
                confidence = 0.65
                reasoning_parts.append("Villain polarized — raise for value (they call with value, fold bluffs)")
                exploits.append({'type': 'polarized_range', 'exploit': 'raise_value'})
            elif hero_hand_strength == 'weak' and hero_equity < 0.25:
                action = 'fold'
                confidence = 0.60
                reasoning_parts.append("Villain polarized and we're weak — fold to save chips")
                exploits.append({'type': 'polarized_range', 'exploit': 'fold_weak'})
            else:
                # Medium strength vs polarized: call and let bluffs pay off
                action = 'call'
                confidence = 0.50
                reasoning_parts.append("Villain polarized — call with medium (catch bluffs)")
                exploits.append({'type': 'polarized_range', 'exploit': 'bluff_catch'})

        # ── Exploit 4: Narrow strong range → fold marginals, no bluffs ──
        elif value_pct > 0.70 and num_combos < 30:
            if hero_hand_strength in ('monster', 'very_strong'):
                action = 'call'  # or raise if very strong
                confidence = 0.50
                reasoning_parts.append("Villain range narrow and strong — only continue with the nuts")
            else:
                action = 'fold'
                confidence = 0.65
                reasoning_parts.append(f"Villain range narrow ({num_combos} combos, {value_pct:.0%} value) — fold non-nuts")
                exploits.append({'type': 'narrow_strong', 'exploit': 'fold'})

        # ── Exploit 5: Wide weak range → bluff more, value bet thin ──
        elif analysis.get('weak_pct', 0) + analysis.get('medium_pct', 0) > 0.60:
            if hero_hand_strength in ('medium', 'strong', 'monster', 'very_strong'):
                action = 'bet'
                sizing_pct = 0.66
                confidence = 0.60
                reasoning_parts.append("Villain range mostly weak/medium — value bet wider")
                exploits.append({'type': 'wide_weak', 'exploit': 'value_bet'})
            elif hero_hand_strength in ('weak', 'marginal') and hero_equity < 0.30:
                action = 'bet'
                sizing_pct = 0.50  # bluff since they're weak
                confidence = 0.45
                reasoning_parts.append("Villain mostly weak — bluff")
                exploits.append({'type': 'wide_weak', 'exploit': 'bluff'})

        # ── Exploit 6: Pure bluff opportunity (hero has nothing, villain capped) ──
        if is_capped and hero_hand_strength in ('weak', 'marginal') and action == 'check':
            if is_ip and hero_equity < 0.20:
                action = 'bet'
                sizing_pct = 0.75  # large bluff since they're capped
                confidence = 0.45
                reasoning_parts.append("In position, villain capped — stab as bluff")
                exploits.append({'type': 'capped_bluff', 'exploit': 'position_bluff'})

        # Position bonus
        if is_ip and action == 'bet':
            confidence = min(1.0, confidence + 0.05)

        # Confidence boost based on number of actions observed
        n_actions = len(analysis.get('history', []))
        if n_actions >= 2:
            confidence = min(1.0, confidence + 0.10)
        if n_actions >= 3:
            confidence = min(1.0, confidence + 0.10)

        reasoning = '; '.join(reasoning_parts) if reasoning_parts else 'Standard play'

        result = {
            'action': action,
            'sizing_pct': round(sizing_pct, 2),
            'confidence': round(confidence, 2),
            'reasoning': reasoning,
            'exploits': exploits,
            'range_type': 'capped' if is_capped else ('polarized' if is_polarized else 'merged'),
            'combos_remaining': num_combos,
        }

        if exploits:
            log.info(f"EXPLOIT: {action.upper()} ({confidence:.0%} conf) — "
                     f"{reasoning} [combos={num_combos}]")

        return result

    def predict_hand(
        self,
        villain_range: dict,
        board_cards: List[str],
        hero_cards: List[str],
        top_n: int = 5,
    ) -> List[dict]:
        """After narrowing, predict the most likely villain holdings.

        Returns list of top combos with probabilities.
        """
        if not villain_range.get('combos'):
            return []

        board_e7 = _board_to_eval7(board_cards)
        hero_e7 = [_convert_card(c) for c in hero_cards if c]
        hero_set = set(str(c) for c in hero_e7 if c)
        board_set = set(str(c) for c in board_e7)

        weighted = []
        total_w = 0
        for c0, c1, w in villain_range['combos']:
            if w < 0.10:
                continue
            total_w += w
            # Classify for display
            try:
                combo_e7 = [eval7.Card(c0), eval7.Card(c1)]
                info = _classify_combo_on_board(combo_e7, board_e7, hero_set, board_set)
                cat = info['category'] if info else '?'
                hand_type = info['hand_type'] if info else '?'
            except Exception:
                cat = '?'
                hand_type = '?'
            weighted.append({
                'cards': f"{c0[0].upper()}{c0[-1]}·{c1[0].upper()}{c1[-1]}",
                'weight': w,
                'category': cat,
                'hand_type': hand_type,
            })

        if not weighted or total_w == 0:
            return []

        weighted.sort(key=lambda x: x['weight'], reverse=True)
        for item in weighted:
            item['probability'] = round(item['weight'] / total_w * 100, 1)

        top = weighted[:top_n]

        if top:
            combos_str = ', '.join(f"{c['cards']}({c['probability']:.0f}%)" for c in top)
            log.info(f"HAND PREDICTION: Top {len(top)}: {combos_str}")

        return top


# ── Activation Logic: WHEN to use Bayesian tracking ─────────────────────
#
# Not every hand is worth the analysis. The Bayesian engine adds value when:
#   - Stack is deep enough (>15 BB — below that, push/fold is solved)
#   - Pot is significant (>3 BB — tiny pots aren't worth complex analysis)
#   - We've seen ≥1 villain action postflop (need signal to narrow)
#   - Board has ≥3 cards (need eval7 hand classification)
#
# We SKIP Bayesian when:
#   - Short-stacked (≤15 BB) — push/fold handles this
#   - Preflop — ranges are static, no board to classify
#   - Free check available with trash hand — not worth analysis
#   - Very small pot — EV of exploitation is tiny

def should_use_bayesian(
    hero_stack_bb: float,
    pot_bb: float,
    street: str,
    num_villain_actions: int = 0,
    has_check_button: bool = False,
    hero_equity: float = 0.5,
    opponent_hands_seen: int = 0,
) -> dict:
    """Decide whether to activate Bayesian range tracking for this spot.

    Returns:
        dict with:
            'use': bool — whether to activate
            'reason': str — why/why not
            'priority': float — 0.0-1.0, how valuable the analysis is
              Higher = more valuable. Used to decide analysis depth.
    """
    # Always skip preflop (ranges are static, handled by preflop tables)
    if street == 'preflop':
        return {'use': False, 'reason': 'preflop (static ranges)', 'priority': 0.0}

    # Skip very short stacks — push/fold handles these
    if hero_stack_bb <= 15:
        return {'use': False, 'reason': f'short stack ({hero_stack_bb:.0f}BB, push/fold)', 'priority': 0.0}

    # Skip tiny pots — not worth the analysis
    if pot_bb < 3.0:
        return {'use': False, 'reason': f'tiny pot ({pot_bb:.1f}BB)', 'priority': 0.0}

    # Calculate priority based on multiple factors
    priority = 0.0

    # Factor 1: Pot size relative to stack (bigger pot = more important)
    pot_to_stack = pot_bb / max(hero_stack_bb, 1)
    if pot_to_stack > 0.30:
        priority += 0.35  # Big pot — critical decision
    elif pot_to_stack > 0.15:
        priority += 0.20  # Medium pot
    elif pot_to_stack > 0.05:
        priority += 0.10  # Small but non-trivial
    else:
        priority += 0.03  # Very small

    # Factor 2: Number of villain actions observed (more = better data)
    if num_villain_actions >= 3:
        priority += 0.25  # 3+ actions = very narrow range
    elif num_villain_actions >= 2:
        priority += 0.18  # 2 actions = good signal
    elif num_villain_actions >= 1:
        priority += 0.10  # 1 action = some info
    # 0 actions = no data yet

    # Factor 3: Street (later = more valuable, range more defined)
    street_bonus = {'flop': 0.05, 'turn': 0.15, 'river': 0.25}
    priority += street_bonus.get(street, 0.05)

    # Factor 4: Opponent profile quality
    if opponent_hands_seen >= 30:
        priority += 0.10  # Good read
    elif opponent_hands_seen >= 10:
        priority += 0.05  # Decent read

    # Factor 5: Decision complexity
    # Close equity decisions benefit most from Bayesian
    if 0.30 <= hero_equity <= 0.65:
        priority += 0.10  # Marginal spot = high value from better info

    # Minimum threshold: use if priority > 0.20
    # This means we need at least a medium pot + 1 action, or a big pot
    use = priority >= 0.20

    if not use:
        reason = f'low priority ({priority:.2f}) — spot too small/early'
    else:
        reason = f'activated (priority={priority:.2f})'

    return {'use': use, 'reason': reason, 'priority': round(priority, 2)}


# Singleton tracker
_tracker_instance = None

def get_bayesian_tracker() -> BayesianRangeTracker:
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = BayesianRangeTracker()
    return _tracker_instance


# ── Hand History JSONL Logger ───────────────────────────────────────────
import json
import os
from datetime import datetime

_HAND_HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'learning', 'hand_analysis.jsonl'
)

def log_hand_analysis(
    hero_cards: List[str],
    board_cards: List[str],
    street: str,
    decision: str,
    equity: float,
    pot_bb: float = 0.0,
    call_bb: float = 0.0,
    stack_bb: float = 0.0,
    range_analysis: Optional[dict] = None,
    exploit_rec: Optional[dict] = None,
    hand_prediction: Optional[list] = None,
    extra: Optional[dict] = None,
):
    """Log a structured hand analysis entry to JSONL file.

    Each line is a complete snapshot of the decision at one point.
    """
    entry = {
        'ts': datetime.now().isoformat(),
        'hero': hero_cards,
        'board': board_cards,
        'street': street,
        'decision': decision,
        'equity': round(equity, 3),
        'pot_bb': round(pot_bb, 1),
        'call_bb': round(call_bb, 1),
        'stack_bb': round(stack_bb, 1),
    }
    if range_analysis:
        entry['range_analysis'] = {
            k: v for k, v in range_analysis.items()
            if k not in ('history',)  # skip verbose history
        }
    if exploit_rec:
        entry['exploit'] = exploit_rec
    if hand_prediction:
        entry['prediction'] = hand_prediction[:5]
    if extra:
        entry.update(extra)

    try:
        os.makedirs(os.path.dirname(_HAND_HISTORY_PATH), exist_ok=True)
        with open(_HAND_HISTORY_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception as e:
        log.debug(f"Hand history log failed: {e}")


# ── Singleton for easy import ──────────────────────────────────────────────

_instance = None

def get_range_equity() -> RangeEquity:
    global _instance
    if _instance is None:
        _instance = RangeEquity()
    return _instance
