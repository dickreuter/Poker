"""
Strategy feedback loop.

Reads hand history, detects leaks, and writes adjustments to
data/learning/strategy_adjustments.json that the bot reads on startup.

Usage:
    ./venv/bin/python -m sys_core.tools.strategy_adjuster
    ./venv/bin/python -m sys_core.tools.strategy_adjuster --last 500
    ./venv/bin/python -m sys_core.tools.strategy_adjuster --reset

The bot reads adjustments via load_adjustments() and applies them
to fold equity estimates, c-bet frequency, bluff thresholds, etc.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

HAND_HISTORY_PATH = os.path.join('data', 'learning', 'hand_history.jsonl')
ADJUSTMENTS_PATH = os.path.join('data', 'learning', 'strategy_adjustments.json')

# Defaults — what the code uses when no adjustments exist
DEFAULTS = {
    'fold_equity_offset': 0.0,       # Added to all fold equity estimates
    'cbet_freq_offset': 0.0,         # Added to c-bet frequency (positive = more c-bets)
    'bluff_min_fold_eq_offset': 0.0, # Added to minimum fold equity for bluffing
    'river_value_threshold': 0.60,   # Minimum equity for river value bet
    'thin_value_threshold': 0.50,    # Minimum equity for thin value bet
    'pot_control_spr_threshold': 6.0,# SPR above which we pot-control marginal hands
    'barrel_equity_threshold': 0.55, # Minimum equity for value barrel
    'check_raise_freq_offset': 0.0,  # Added to check-raise frequency
    'last_updated': None,
    'hands_analyzed': 0,
    'detected_leaks': [],
}


def load_adjustments():
    """Load strategy adjustments. Called by the bot on startup."""
    if not os.path.exists(ADJUSTMENTS_PATH):
        return dict(DEFAULTS)
    try:
        with open(ADJUSTMENTS_PATH) as f:
            adj = json.load(f)
        # Merge with defaults for any missing keys
        for k, v in DEFAULTS.items():
            if k not in adj:
                adj[k] = v
        return adj
    except (json.JSONDecodeError, IOError):
        return dict(DEFAULTS)


def save_adjustments(adj):
    """Save strategy adjustments."""
    os.makedirs(os.path.dirname(ADJUSTMENTS_PATH), exist_ok=True)
    with open(ADJUSTMENTS_PATH, 'w') as f:
        json.dump(adj, f, indent=2)


def classify_decision(dec):
    dec_lower = dec.lower() if dec else ''
    if 'fold' in dec_lower:
        return 'fold'
    elif 'call' in dec_lower or 'check' in dec_lower:
        return 'call'
    else:
        return 'raise'


def analyze_and_adjust(hands):
    """Analyze hands and produce strategy adjustments."""
    adj = dict(DEFAULTS)
    total = len(hands)
    if total < 30:
        print(f"Only {total} hands — need at least 30 for reliable adjustments.")
        return adj

    adj['hands_analyzed'] = total
    leaks = []

    folds = [h for h in hands if classify_decision(h.get('decision', '')) == 'fold']
    calls = [h for h in hands if classify_decision(h.get('decision', '')) == 'call']
    raises = [h for h in hands if classify_decision(h.get('decision', '')) == 'raise']
    postflop = [h for h in hands if h.get('street') != 'PreFlop']

    # --- Bluff rate analysis ---
    bluffs = [h for h in hands if 'bluff' in h.get('decision', '').lower()]
    if postflop:
        bluff_rate = len(bluffs) / len(postflop)
        if bluff_rate > 0.25:
            # Bluffing too much — raise the bar
            adj['bluff_min_fold_eq_offset'] = 0.05
            adj['fold_equity_offset'] = -0.03  # Be more conservative in fold equity estimates
            leaks.append(f"Bluff rate {bluff_rate*100:.0f}% too high (target: 10-20%), tightening")
        elif bluff_rate < 0.08:
            # Not bluffing enough — lower the bar
            adj['bluff_min_fold_eq_offset'] = -0.05
            adj['fold_equity_offset'] = 0.02
            leaks.append(f"Bluff rate {bluff_rate*100:.0f}% too low (target: 10-20%), loosening")

    # --- C-bet rate analysis ---
    flop_hands = [h for h in hands if h.get('street') == 'Flop']
    flop_checks_available = [h for h in flop_hands if h.get('call', 0) == 0]
    flop_bets = [h for h in flop_checks_available if classify_decision(h.get('decision', '')) == 'raise']
    if len(flop_checks_available) >= 10:
        cbet_rate = len(flop_bets) / len(flop_checks_available)
        if cbet_rate > 0.70:
            adj['cbet_freq_offset'] = -0.10
            leaks.append(f"C-bet rate {cbet_rate*100:.0f}% too high (target: 50-65%), reducing")
        elif cbet_rate < 0.40:
            adj['cbet_freq_offset'] = 0.10
            leaks.append(f"C-bet rate {cbet_rate*100:.0f}% too low (target: 50-65%), increasing")

    # --- Bad calls analysis ---
    paid_calls = [h for h in calls if h.get('call', 0) > 0]
    bad_calls = [h for h in paid_calls if h.get('equity', 0) < h.get('pot_odds', 1)]
    if len(paid_calls) >= 10:
        bad_call_rate = len(bad_calls) / len(paid_calls)
        if bad_call_rate > 0.25:
            leaks.append(f"Bad call rate {bad_call_rate*100:.0f}% (calling without pot odds)")

    # --- Missed value analysis ---
    fold_with_odds = [h for h in folds
                      if h.get('call', 0) > 0
                      and h.get('equity', 0) >= h.get('pot_odds', 1)]
    if len(folds) >= 10:
        missed_value_rate = len(fold_with_odds) / len(folds)
        if missed_value_rate > 0.10:
            leaks.append(f"Missed value rate {missed_value_rate*100:.0f}% (folding with good pot odds)")

    # --- Postflop aggression ---
    postflop_raises = [h for h in postflop if classify_decision(h.get('decision', '')) == 'raise']
    if postflop:
        raise_rate = len(postflop_raises) / len(postflop)
        if raise_rate < 0.12:
            adj['check_raise_freq_offset'] = 0.05
            leaks.append(f"Postflop raise rate {raise_rate*100:.0f}% too passive (target: >15%)")
        elif raise_rate > 0.35:
            adj['check_raise_freq_offset'] = -0.05
            leaks.append(f"Postflop raise rate {raise_rate*100:.0f}% too aggressive (target: 15-30%)")

    # --- SPR leaks ---
    hands_with_spr = [h for h in hands if h.get('spr') is not None and h.get('street') != 'PreFlop']
    spr_fold_committed = [h for h in hands_with_spr
                          if h['spr'] < 3 and classify_decision(h.get('decision', '')) == 'fold'
                          and h.get('equity', 0) >= 0.25]
    if spr_fold_committed:
        leaks.append(f"Folding when committed (SPR<3): {len(spr_fold_committed)} hands")

    # --- River value betting ---
    river_checks = [h for h in hands
                    if h.get('street') == 'River'
                    and h.get('call', 0) == 0  # Had check option
                    and classify_decision(h.get('decision', '')) == 'call'  # Checked
                    and h.get('equity', 0) >= 0.55]
    if river_checks:
        # Checking back strong hands on river — lower the value bet threshold
        adj['river_value_threshold'] = 0.55
        adj['thin_value_threshold'] = 0.45
        leaks.append(f"Checking back river with 55%+ equity: {len(river_checks)} hands (should value bet)")

    # --- Turn barrel rate ---
    turn_checks_available = [h for h in hands
                             if h.get('street') == 'Turn' and h.get('call', 0) == 0]
    turn_bets = [h for h in turn_checks_available
                 if classify_decision(h.get('decision', '')) == 'raise']
    if len(turn_checks_available) >= 10:
        turn_barrel_rate = len(turn_bets) / len(turn_checks_available)
        if turn_barrel_rate < 0.30:
            adj['barrel_equity_threshold'] = 0.50  # Lower threshold to barrel more
            leaks.append(f"Turn barrel rate {turn_barrel_rate*100:.0f}% too low (target: >40%)")

    adj['detected_leaks'] = leaks
    from datetime import datetime
    adj['last_updated'] = datetime.utcnow().isoformat()

    return adj


def main():
    parser = argparse.ArgumentParser(description='Auto-adjust strategy based on hand history')
    parser.add_argument('--last', type=int, help='Analyze last N hands')
    parser.add_argument('--since', type=str, help='Analyze hands since date (YYYY-MM-DD)')
    parser.add_argument('--file', type=str, default=HAND_HISTORY_PATH)
    parser.add_argument('--reset', action='store_true', help='Reset adjustments to defaults')
    args = parser.parse_args()

    if args.reset:
        save_adjustments(dict(DEFAULTS))
        print(f"Reset adjustments to defaults: {ADJUSTMENTS_PATH}")
        return

    if not os.path.exists(args.file):
        print(f"No hand history at {args.file}")
        sys.exit(1)

    hands = []
    with open(args.file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                hands.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if args.since:
        hands = [h for h in hands if h.get('ts', '') >= args.since]
    if args.last:
        hands = hands[-args.last:]

    print(f"Analyzing {len(hands)} hands from {args.file}")
    print()

    adj = analyze_and_adjust(hands)
    save_adjustments(adj)

    print("STRATEGY ADJUSTMENTS:")
    print(f"  fold_equity_offset:       {adj['fold_equity_offset']:+.2f}")
    print(f"  cbet_freq_offset:         {adj['cbet_freq_offset']:+.2f}")
    print(f"  bluff_min_fold_eq_offset: {adj['bluff_min_fold_eq_offset']:+.2f}")
    print(f"  river_value_threshold:    {adj['river_value_threshold']:.2f}")
    print(f"  thin_value_threshold:     {adj['thin_value_threshold']:.2f}")
    print(f"  barrel_equity_threshold:  {adj['barrel_equity_threshold']:.2f}")
    print(f"  check_raise_freq_offset:  {adj['check_raise_freq_offset']:+.2f}")
    print()

    if adj['detected_leaks']:
        print("DETECTED LEAKS:")
        for i, leak in enumerate(adj['detected_leaks'], 1):
            print(f"  {i}. {leak}")
    else:
        print("No leaks detected.")

    print()
    print(f"Saved to: {ADJUSTMENTS_PATH}")
    print("The bot will read these adjustments on next startup.")


if __name__ == '__main__':
    main()
