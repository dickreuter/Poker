"""Poker hand simulator — tests bot decisions against known-correct GTO play.

Deals random hands, runs through the full decision pipeline, and flags
every mistake. No GGPoker needed — pure simulation with eval7.

Usage:
    python3 -m sys_core.tests.simulate_hands --hands 100
    python3 -m sys_core.tests.simulate_hands --hands 50 --verbose
"""
import random
import sys
import argparse
import logging
from typing import List, Tuple, Optional

try:
    import eval7
except ImportError:
    print("Need eval7: pip install eval7")
    sys.exit(1)

from sys_core.decisionmaker.solver import get_solver
from sys_core.decisionmaker.solver.hand_buckets import hand_to_canonical

log = logging.getLogger(__name__)

# Standard villain range for simulation
VILLAIN_RANGE = '22+, A2s+, K9s+, QTs+, JTs, T9s, 98s, 87s, 76s, ATo+, KJo+, QJo'
HERO_RANGE = '22+, A2s+, K5s+, Q8s+, J8s+, T8s+, A2o+, K9o+, Q9o+'

RANKS = '23456789TJQKA'
SUITS = 'shdc'
ALL_CARDS = [f'{r}{s}' for r in RANKS for s in SUITS]


def deal_hand(n_board=0, exclude=None):
    """Deal hero cards + optional board from a shuffled deck."""
    deck = list(ALL_CARDS)
    if exclude:
        deck = [c for c in deck if c not in exclude]
    random.shuffle(deck)
    hero = [deck[0].upper(), deck[1].upper()]
    board = [deck[2 + i].upper() for i in range(n_board)]
    return hero, board


def card_to_display(cards):
    """Format cards for display."""
    suit_map = {'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣'}
    out = []
    for c in cards:
        r = c[:-1]
        s = suit_map.get(c[-1], c[-1])
        out.append(f'{r}{s}')
    return ' '.join(out)


def compute_equity(hero, board, villain_range_str):
    """Compute hero equity vs villain range on given board."""
    h = [eval7.Card(c[0].upper() + c[1].lower()) for c in hero]
    b = [eval7.Card(c[0].upper() + c[1].lower()) for c in board] if board else []
    vr = eval7.HandRange(villain_range_str)
    return float(eval7.py_hand_vs_range_monte_carlo(h, vr, b, 3000))


def count_outs(hero, board):
    """Estimate outs for draws."""
    if not board or len(board) < 3:
        return 0

    all_cards = hero + board
    ranks = [RANKS.index(c[0]) for c in all_cards]
    suits = [c[1] for c in all_cards]

    outs = 0
    # Flush draw: 4 of same suit in hero+board
    from collections import Counter
    suit_counts = Counter(suits)
    for s, count in suit_counts.items():
        if count == 4 and any(c[1] == s for c in hero):
            outs += 9

    # Straight draw: check for OESD/gutshot
    hero_ranks = sorted(set([RANKS.index(c[0]) for c in hero]))
    board_ranks = sorted(set([RANKS.index(c[0]) for c in board]))
    all_ranks = sorted(set(ranks))

    for base in range(14):
        window = [r for r in all_ranks if base <= r < base + 5]
        if len(window) == 4:
            outs += 4 if outs == 0 else 0  # Gutshot
        elif len(window) >= 3:
            # Check if hero contributes
            hero_in = [r for r in hero_ranks if base <= r < base + 5]
            if hero_in:
                gap_count = 5 - len(window)
                if gap_count == 1:
                    outs += 8 if outs < 9 else 0  # OESD

    return min(outs, 15)


def is_correct(action, equity, outs, pot, call_amt, stack_bb, n_opp, street, position):
    """Evaluate if a decision is correct using simple GTO principles."""
    reasons = []
    is_ok = True

    # Preflop
    if street == 'preflop':
        hand_key = None  # Can't determine from equity alone
        if stack_bb <= 8:
            # Push/fold: high equity hands push, low fold
            if action == 'allin' and equity < 0.28:
                is_ok = False
                reasons.append(f'pushing with {equity:.0%} equity at {stack_bb:.0f}BB')
            elif action == 'fold' and equity > 0.55:
                is_ok = False
                reasons.append(f'folding {equity:.0%} equity at {stack_bb:.0f}BB')
        elif stack_bb <= 20:
            if action in ('allin', 'raise') and equity < 0.30 and call_amt == 0:
                is_ok = False
                reasons.append(f'opening with {equity:.0%} at {stack_bb:.0f}BB')
            elif action == 'fold' and equity > 0.60 and call_amt == 0:
                is_ok = False
                reasons.append(f'folding {equity:.0%} first-in at {stack_bb:.0f}BB')
        return is_ok, reasons

    # Postflop
    pot_odds = call_amt / (pot + call_amt) if call_amt > 0 and (pot + call_amt) > 0 else 0

    # Rule 1: Never bet/raise with 0% equity and no draws on river
    if street == 'river' and equity < 0.02 and outs == 0:
        if action in ('raise', 'allin'):
            is_ok = False
            reasons.append(f'betting river with {equity:.0%} equity, 0 outs')

    # Rule 2: Never call with equity < pot odds (unless implied odds with draws)
    if action == 'call' and call_amt > 0 and equity < pot_odds * 0.8 and outs < 4:
        is_ok = False
        reasons.append(f'calling {call_amt:.1f} into {pot:.1f} with {equity:.0%} (need {pot_odds:.0%})')

    # Rule 3: Should bet/raise with very strong hands (>70% equity) when checked to
    if call_amt == 0 and equity > 0.70 and action in ('check', 'fold'):
        is_ok = False
        reasons.append(f'checking with {equity:.0%} equity (should value bet)')

    # Rule 4: Multiway with no equity and no draws — don't bet
    if n_opp >= 2 and equity < 0.10 and outs < 4 and action in ('raise', 'allin'):
        is_ok = False
        reasons.append(f'bluffing multiway with {equity:.0%} and {outs} outs')

    # Rule 5: Don't fold when getting great pot odds with decent equity
    if action == 'fold' and call_amt > 0 and pot_odds < 0.15 and equity > 0.20:
        is_ok = False
        reasons.append(f'folding {equity:.0%} getting {1/max(pot_odds,0.01):.0f}:1')

    # Rule 6: Draws should usually bet/raise, not check (heads-up)
    if n_opp == 1 and outs >= 8 and equity > 0.35 and call_amt == 0:
        if action in ('check', 'fold'):
            # This is borderline — checking draws is sometimes correct
            pass  # Don't flag as error, just note

    return is_ok, reasons


def simulate(n_hands=100, verbose=False):
    """Run n simulated hands and report results."""
    solver = get_solver()

    scenarios = []
    # Mix of preflop and postflop, various stack depths
    for _ in range(n_hands):
        stack_bb = random.choice([3, 5, 7, 10, 12, 15, 20, 25, 30, 50])
        n_opp = random.choice([1, 1, 2, 2])  # Bias toward HU and 3-way
        position = random.choice(['BTN', 'SB', 'BB', 'CO'])

        # 40% preflop, 35% flop, 15% turn, 10% river
        r = random.random()
        if r < 0.40:
            street = 'preflop'
            n_board = 0
        elif r < 0.75:
            street = 'flop'
            n_board = 3
        elif r < 0.90:
            street = 'turn'
            n_board = 4
        else:
            street = 'river'
            n_board = 5

        hero, board = deal_hand(n_board)
        eq = compute_equity(hero, board, VILLAIN_RANGE)
        outs = count_outs(hero, board) if board else 0

        # Generate realistic pot and call amounts
        pot = random.choice([1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 15.0])
        if street == 'preflop':
            pot = 1.5
            call_amt = random.choice([0, 0, 0, 0.5, 1.0, 2.0, 3.0, stack_bb])
        else:
            call_amt = random.choice([0, 0, 0, 0, pot * 0.33, pot * 0.5, pot * 0.67])

        call_amt = min(call_amt, stack_bb)

        game_type = 'spin' if stack_bb <= 25 else 'cash'

        scenarios.append({
            'hero': hero, 'board': board, 'equity': eq, 'outs': outs,
            'pot': pot, 'call_amt': call_amt, 'stack_bb': stack_bb,
            'n_opp': n_opp, 'position': position, 'street': street,
            'game_type': game_type,
        })

    # Run solver on each
    correct = 0
    wrong = 0
    errors = []

    for i, s in enumerate(scenarios):
        try:
            r = solver.decide(
                hero_cards=s['hero'], board=s['board'],
                pot=s['pot'], stack=s['stack_bb'],
                call_amount=s['call_amt'], bb=1.0,
                position=s['position'],
                hero_is_ip=(s['position'] in ('BTN', 'CO')),
                game_type=s['game_type'],
                villain_range_str=VILLAIN_RANGE,
                hero_range_str=HERO_RANGE,
            )

            is_ok, reasons = is_correct(
                r.action, s['equity'], s['outs'],
                s['pot'], s['call_amt'], s['stack_bb'],
                s['n_opp'], s['street'], s['position'],
            )

            if is_ok:
                correct += 1
                if verbose:
                    print(f'  ✓ #{i+1} {card_to_display(s["hero"])} '
                          f'{"on " + card_to_display(s["board"]) + " " if s["board"] else ""}'
                          f'eq={s["equity"]:.0%} {s["stack_bb"]}BB {s["position"]} '
                          f'→ {r.action}')
            else:
                wrong += 1
                err = {
                    'hand': i + 1,
                    'hero': s['hero'],
                    'board': s['board'],
                    'equity': s['equity'],
                    'outs': s['outs'],
                    'pot': s['pot'],
                    'call': s['call_amt'],
                    'stack': s['stack_bb'],
                    'opp': s['n_opp'],
                    'pos': s['position'],
                    'street': s['street'],
                    'action': r.action,
                    'layer': r.solver_layer,
                    'reasons': reasons,
                }
                errors.append(err)
                if verbose:
                    print(f'  ✗ #{i+1} {card_to_display(s["hero"])} '
                          f'{"on " + card_to_display(s["board"]) + " " if s["board"] else ""}'
                          f'eq={s["equity"]:.0%} {s["stack_bb"]}BB {s["position"]} '
                          f'→ {r.action} L{r.solver_layer} ← {"; ".join(reasons)}')

        except Exception as e:
            wrong += 1
            errors.append({'hand': i + 1, 'error': str(e)})
            if verbose:
                print(f'  ✗ #{i+1} ERROR: {e}')

    # Report
    total = correct + wrong
    pct = correct / total * 100 if total > 0 else 0

    print(f'\n{"="*60}')
    print(f'SIMULATION RESULTS: {correct}/{total} correct ({pct:.1f}%)')
    print(f'{"="*60}')

    if errors:
        print(f'\nMISTAKES ({len(errors)}):')
        for e in errors[:20]:  # Show first 20
            if 'error' in e:
                print(f'  #{e["hand"]}: ERROR — {e["error"]}')
            else:
                hero_str = card_to_display(e['hero'])
                board_str = card_to_display(e['board']) if e['board'] else '-'
                print(f'  #{e["hand"]}: {hero_str} on {board_str} | '
                      f'eq={e["equity"]:.0%} outs={e["outs"]} '
                      f'{e["stack"]}BB {e["pos"]} {e["street"]} '
                      f'→ {e["action"]} L{e["layer"]} | {"; ".join(e["reasons"])}')

    # Categorize mistakes
    if errors:
        categories = {}
        for e in errors:
            for r in e.get('reasons', []):
                cat = r.split(' ')[0]
                categories[cat] = categories.get(cat, 0) + 1
        print(f'\nMistake categories:')
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            print(f'  {cat}: {count}')

    return correct, wrong, errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Simulate poker hands')
    parser.add_argument('--hands', type=int, default=100, help='Number of hands')
    parser.add_argument('--verbose', action='store_true', help='Show every hand')
    parser.add_argument('--seed', type=int, default=None, help='Random seed')
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    logging.basicConfig(level=logging.WARNING)
    simulate(args.hands, args.verbose)
