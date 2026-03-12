"""
Post-session hand history analyzer.

Reads data/learning/hand_history.jsonl and prints a leak report.

Usage:
    ./venv/bin/python -m sys_core.tools.session_analyzer
    ./venv/bin/python -m sys_core.tools.session_analyzer --last 200
    ./venv/bin/python -m sys_core.tools.session_analyzer --since 2026-03-08
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime


HAND_HISTORY_PATH = os.path.join('data', 'learning', 'hand_history.jsonl')


def load_hands(path=HAND_HISTORY_PATH, last_n=None, since=None):
    if not os.path.exists(path):
        print(f"No hand history found at {path}")
        sys.exit(1)

    hands = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                hands.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if since:
        hands = [h for h in hands if h.get('ts', '') >= since]

    if last_n:
        hands = hands[-last_n:]

    return hands


def classify_decision(dec):
    dec_lower = dec.lower() if dec else ''
    if 'fold' in dec_lower:
        return 'fold'
    elif 'call' in dec_lower or 'check' in dec_lower:
        return 'call'
    else:
        return 'raise'


def analyze(hands):
    total = len(hands)
    if total == 0:
        print("No hands to analyze.")
        return

    folds = [h for h in hands if classify_decision(h.get('decision', '')) == 'fold']
    calls = [h for h in hands if classify_decision(h.get('decision', '')) == 'call']
    raises = [h for h in hands if classify_decision(h.get('decision', '')) == 'raise']

    print("=" * 65)
    print("SESSION REPORT")
    print("=" * 65)
    print(f"Hands: {total} | Folds: {len(folds)} ({len(folds)/total*100:.1f}%) "
          f"| Calls: {len(calls)} ({len(calls)/total*100:.1f}%) "
          f"| Raises: {len(raises)} ({len(raises)/total*100:.1f}%)")

    # Time range
    timestamps = [h.get('ts', '') for h in hands if h.get('ts')]
    if timestamps:
        print(f"Period: {timestamps[0][:19]} to {timestamps[-1][:19]}")
    print()

    # --- EV Dashboard ---
    hands_with_ev = [h for h in hands if 'ev' in h]
    if hands_with_ev:
        total_ev = sum(h['ev'] for h in hands_with_ev)
        avg_ev = total_ev / len(hands_with_ev)
        print("EV DASHBOARD:")
        print(f"  Total decision EV:  {total_ev:+.2f} BB  ({len(hands_with_ev)} hands)")
        print(f"  Avg EV per hand:    {avg_ev:+.4f} BB")

        # EV by decision type
        ev_by_type = defaultdict(list)
        for h in hands_with_ev:
            ev_by_type[classify_decision(h.get('decision', ''))].append(h['ev'])
        for dtype in ('fold', 'call', 'raise'):
            evs = ev_by_type.get(dtype, [])
            if evs:
                print(f"    {dtype:6s}: {sum(evs):+8.2f} BB total | "
                      f"{sum(evs)/len(evs):+.4f} avg | n={len(evs)}")

        # EV by street
        ev_by_street = defaultdict(list)
        for h in hands_with_ev:
            ev_by_street[h.get('street', '?')].append(h['ev'])
        print("  EV by street:")
        for street in ('PreFlop', 'Flop', 'Turn', 'River'):
            evs = ev_by_street.get(street, [])
            if evs:
                print(f"    {street:8s}: {sum(evs):+8.2f} BB | "
                      f"{sum(evs)/len(evs):+.4f} avg | n={len(evs)}")

        # Worst and best decisions
        worst = sorted(hands_with_ev, key=lambda h: h['ev'])[:5]
        best = sorted(hands_with_ev, key=lambda h: -h['ev'])[:5]
        print("  Worst decisions:")
        for h in worst:
            print(f"    EV={h['ev']:+.2f} | {h.get('decision','?'):15s} | "
                  f"cards={h.get('cards',[])} board={h.get('board',[])} | "
                  f"eq={h.get('equity',0):.2f} pot={h.get('pot',0):.1f} "
                  f"call={h.get('call',0):.1f} | {h.get('street','?')}")
        print("  Best decisions:")
        for h in best:
            print(f"    EV={h['ev']:+.2f} | {h.get('decision','?'):15s} | "
                  f"cards={h.get('cards',[])} board={h.get('board',[])} | "
                  f"eq={h.get('equity',0):.2f} pot={h.get('pot',0):.1f} "
                  f"call={h.get('call',0):.1f} | {h.get('street','?')}")
        print()

    # --- Pot odds analysis ---
    print("POT ODDS ANALYSIS:")
    paid_calls = [h for h in calls if h.get('call', 0) > 0]
    good_calls = [h for h in paid_calls if h.get('equity', 0) >= h.get('pot_odds', 1)]
    bad_calls = [h for h in paid_calls if h.get('equity', 0) < h.get('pot_odds', 1)]

    if paid_calls:
        print(f"  Correct calls (eq >= pot_odds): {len(good_calls)}/{len(paid_calls)} "
              f"({len(good_calls)/len(paid_calls)*100:.0f}%)")
        print(f"  Bad calls (eq < pot_odds):      {len(bad_calls)}/{len(paid_calls)} "
              f"({len(bad_calls)/len(paid_calls)*100:.0f}%) {'<-- leak' if len(bad_calls) > len(paid_calls) * 0.15 else ''}")
    else:
        print("  No paid calls recorded.")

    fold_with_odds = [h for h in folds
                      if h.get('call', 0) > 0
                      and h.get('equity', 0) >= h.get('pot_odds', 1)]
    if folds:
        print(f"  Correct folds (eq < pot_odds):  {len(folds) - len(fold_with_odds)}/{len(folds)} "
              f"({(len(folds) - len(fold_with_odds))/len(folds)*100:.0f}%)")
        print(f"  Missed value (eq >= pot_odds but folded): {len(fold_with_odds)}/{len(folds)} "
              f"({len(fold_with_odds)/len(folds)*100:.0f}%) {'<-- leak' if len(fold_with_odds) > len(folds) * 0.05 else ''}")
    print()

    # --- SPR analysis ---
    hands_with_spr = [h for h in hands if h.get('spr') is not None and h.get('street') != 'PreFlop']
    if hands_with_spr:
        print("SPR (Stack-to-Pot Ratio) ANALYSIS:")
        spr_buckets = {
            'Committed (SPR < 3)': [h for h in hands_with_spr if h['spr'] < 3],
            'Medium (SPR 3-7)': [h for h in hands_with_spr if 3 <= h['spr'] < 7],
            'Deep (SPR 7+)': [h for h in hands_with_spr if h['spr'] >= 7],
        }
        for label, bucket in spr_buckets.items():
            if not bucket:
                continue
            n = len(bucket)
            f_count = sum(1 for h in bucket if classify_decision(h.get('decision', '')) == 'fold')
            c_count = sum(1 for h in bucket if classify_decision(h.get('decision', '')) == 'call')
            r_count = sum(1 for h in bucket if classify_decision(h.get('decision', '')) == 'raise')
            avg_eq = sum(h.get('equity', 0) for h in bucket) / n
            print(f"  {label:22s}: fold {f_count/n*100:.0f}% call {c_count/n*100:.0f}% "
                  f"raise {r_count/n*100:.0f}%  avg_eq={avg_eq:.2f}  (n={n})")

        # SPR leak: folding when committed
        spr_fold_committed = [h for h in hands_with_spr
                              if h['spr'] < 3 and classify_decision(h.get('decision', '')) == 'fold'
                              and h.get('equity', 0) >= 0.30]
        if spr_fold_committed:
            print(f"  Folding when committed (SPR<3, eq>=30%): {len(spr_fold_committed)} hands  <-- leak")

        # SPR leak: building big pot with marginal hand
        spr_big_pot_marginal = [h for h in hands_with_spr
                                if h['spr'] > 6 and classify_decision(h.get('decision', '')) == 'raise'
                                and 0.35 <= h.get('equity', 0) < 0.55]
        if spr_big_pot_marginal:
            print(f"  Raising deep-stacked with marginal hand (SPR>6, eq 35-55%): "
                  f"{len(spr_big_pot_marginal)} hands  <-- potential leak")
        print()

    # --- By position (VPIP/PFR only from preflop) ---
    print("BY POSITION (action %):")
    pos_stats = defaultdict(lambda: {'fold': 0, 'call': 0, 'raise': 0})
    pos_preflop = defaultdict(lambda: {'fold': 0, 'call': 0, 'raise': 0})
    for h in hands:
        pos = h.get('pos', '?')
        cat = classify_decision(h.get('decision', ''))
        pos_stats[pos][cat] += 1
        if h.get('street', '') == 'PreFlop':
            pos_preflop[pos][cat] += 1

    pos_order = ['UTG', 'MP', 'CO', 'BTN', 'SB', 'BB', '?']
    for pos in pos_order:
        if pos not in pos_stats:
            continue
        stats = pos_stats[pos]
        n = sum(stats.values())
        if n == 0:
            continue
        # VPIP/PFR from preflop only
        pf = pos_preflop.get(pos, {'fold': 0, 'call': 0, 'raise': 0})
        pf_n = sum(pf.values())
        if pf_n > 0:
            vpip = (pf['call'] + pf['raise']) / pf_n * 100
            pfr = pf['raise'] / pf_n * 100
            vpip_str = f"VPIP={vpip:.0f}% PFR={pfr:.0f}%"
        else:
            vpip_str = ""
        print(f"  {pos:>5s}: fold {stats['fold']/n*100:.0f}%, "
              f"call {stats['call']/n*100:.0f}%, "
              f"raise {stats['raise']/n*100:.0f}%  "
              f"{vpip_str}  (n={n})")
    # Show any other positions not in standard order
    for pos in sorted(pos_stats.keys()):
        if pos not in pos_order:
            stats = pos_stats[pos]
            n = sum(stats.values())
            if n == 0:
                continue
            print(f"  {pos:>5s}: fold {stats['fold']/n*100:.0f}%, "
                  f"call {stats['call']/n*100:.0f}%, "
                  f"raise {stats['raise']/n*100:.0f}%  (n={n})")
    print()

    # --- By street ---
    print("BY STREET:")
    street_stats = defaultdict(lambda: {'fold': 0, 'call': 0, 'raise': 0, 'total': 0})
    for h in hands:
        street = h.get('street', '?')
        cat = classify_decision(h.get('decision', ''))
        street_stats[street][cat] += 1
        street_stats[street]['total'] += 1

    for street in ['PreFlop', 'Flop', 'Turn', 'River']:
        s = street_stats.get(street)
        if not s or s['total'] == 0:
            continue
        n = s['total']
        print(f"  {street:>8s}: fold {s['fold']/n*100:.0f}%, "
              f"call {s['call']/n*100:.0f}%, "
              f"raise {s['raise']/n*100:.0f}%  (n={n})")

    # C-bet rate (flop raises when we could check)
    flop_hands = [h for h in hands if h.get('street') == 'Flop']
    flop_checks_available = [h for h in flop_hands if h.get('call', 0) == 0]
    flop_bets = [h for h in flop_checks_available if classify_decision(h.get('decision', '')) == 'raise']
    if flop_checks_available:
        print(f"\n  Flop c-bet rate: {len(flop_bets)}/{len(flop_checks_available)} "
              f"({len(flop_bets)/len(flop_checks_available)*100:.0f}%) (target: 50-65%)")

    # Turn barrel rate
    turn_hands = [h for h in hands if h.get('street') == 'Turn']
    turn_checks_available = [h for h in turn_hands if h.get('call', 0) == 0]
    turn_bets = [h for h in turn_checks_available if classify_decision(h.get('decision', '')) == 'raise']
    if turn_checks_available:
        print(f"  Turn barrel rate: {len(turn_bets)}/{len(turn_checks_available)} "
              f"({len(turn_bets)/len(turn_checks_available)*100:.0f}%) (target: 40-55%)")

    # River bet rate
    river_hands = [h for h in hands if h.get('street') == 'River']
    river_checks_available = [h for h in river_hands if h.get('call', 0) == 0]
    river_bets = [h for h in river_checks_available if classify_decision(h.get('decision', '')) == 'raise']
    if river_checks_available:
        print(f"  River bet rate: {len(river_bets)}/{len(river_checks_available)} "
              f"({len(river_bets)/len(river_checks_available)*100:.0f}%) (target: 25-40%)")

    # Bluff stats
    bluffs = [h for h in hands if 'bluff' in h.get('decision', '').lower()]
    postflop = [h for h in hands if h.get('street') != 'PreFlop']
    if postflop:
        bluff_rate = len(bluffs) / len(postflop) * 100
        print(f"  Bluff rate (postflop): {len(bluffs)}/{len(postflop)} ({bluff_rate:.0f}%) (target: 10-20%)")

    # Semi-bluffs
    semi_bluffs = [h for h in hands
                   if h.get('street') in ('Flop', 'Turn')
                   and 'bet half' in h.get('decision', '').lower()
                   and 0.25 <= h.get('equity', 0) <= 0.50]
    if semi_bluffs:
        print(f"  Semi-bluffs (draws): {len(semi_bluffs)} hands")
    print()

    # --- Board texture analysis ---
    hands_with_wetness = [h for h in hands if h.get('wetness') is not None and h.get('street') != 'PreFlop']
    if hands_with_wetness:
        print("BOARD TEXTURE ANALYSIS:")
        dry = [h for h in hands_with_wetness if h['wetness'] < 0.3]
        medium = [h for h in hands_with_wetness if 0.3 <= h['wetness'] < 0.5]
        wet = [h for h in hands_with_wetness if h['wetness'] >= 0.5]

        for label, bucket in [('Dry (<0.3)', dry), ('Medium (0.3-0.5)', medium), ('Wet (0.5+)', wet)]:
            if not bucket:
                continue
            n = len(bucket)
            r_count = sum(1 for h in bucket if classify_decision(h.get('decision', '')) == 'raise')
            f_count = sum(1 for h in bucket if classify_decision(h.get('decision', '')) == 'fold')
            print(f"  {label:18s}: raise {r_count/n*100:.0f}%, fold {f_count/n*100:.0f}%  (n={n})")
        print()

    # --- Outs analysis ---
    hands_with_outs = [h for h in hands if h.get('outs', 0) > 0 and h.get('street') in ('Flop', 'Turn')]
    if hands_with_outs:
        print("DRAW ANALYSIS:")
        big_draws = [h for h in hands_with_outs if h['outs'] >= 8]
        small_draws = [h for h in hands_with_outs if 4 <= h['outs'] < 8]

        for label, bucket in [('Big draws (8+ outs)', big_draws), ('Small draws (4-7 outs)', small_draws)]:
            if not bucket:
                continue
            n = len(bucket)
            r_count = sum(1 for h in bucket if classify_decision(h.get('decision', '')) == 'raise')
            c_count = sum(1 for h in bucket if classify_decision(h.get('decision', '')) == 'call')
            f_count = sum(1 for h in bucket if classify_decision(h.get('decision', '')) == 'fold')
            print(f"  {label:22s}: raise {r_count}, call {c_count}, fold {f_count}  (n={n})")

        # Leak: folding big draws with good odds
        folded_big_draws = [h for h in big_draws
                            if classify_decision(h.get('decision', '')) == 'fold'
                            and h.get('pot_odds', 1) <= 0.25]
        if folded_big_draws:
            print(f"  Folding big draws with good odds: {len(folded_big_draws)} hands  <-- leak")
        print()

    # --- Blocker analysis ---
    hands_with_blockers = [h for h in hands if h.get('blocker_score', 0) > 0]
    if hands_with_blockers:
        print("BLOCKER ANALYSIS:")
        print(f"  Hands with blockers: {len(hands_with_blockers)}/{total}")

        block_counts = defaultdict(int)
        for h in hands_with_blockers:
            for b in h.get('blocks', []):
                block_counts[b] += 1
        if block_counts:
            print("  Blocker frequency:")
            for btype, count in sorted(block_counts.items(), key=lambda x: -x[1]):
                print(f"    {btype:15s}: {count:4d}")

        # Blocker effectiveness: bluff rate when we have blockers vs without
        postflop_with_blockers = [h for h in hands_with_blockers
                                  if h.get('street') != 'PreFlop']
        bluffs_with = [h for h in postflop_with_blockers
                       if classify_decision(h.get('decision', '')) == 'raise'
                       and h.get('equity', 0) < 0.40]
        postflop_no_blockers = [h for h in hands
                                if h.get('blocker_score', 0) == 0
                                and h.get('street') != 'PreFlop']
        bluffs_without = [h for h in postflop_no_blockers
                          if classify_decision(h.get('decision', '')) == 'raise'
                          and h.get('equity', 0) < 0.40]
        if postflop_with_blockers and postflop_no_blockers:
            rate_with = len(bluffs_with) / len(postflop_with_blockers) * 100
            rate_without = len(bluffs_without) / len(postflop_no_blockers) * 100
            print(f"  Bluff rate WITH blockers:    {rate_with:.0f}% ({len(bluffs_with)}/{len(postflop_with_blockers)})")
            print(f"  Bluff rate WITHOUT blockers: {rate_without:.0f}% ({len(bluffs_without)}/{len(postflop_no_blockers)})")
            if rate_with <= rate_without:
                print("  NOTE: Not leveraging blockers for bluffs  <-- potential leak")
        print()

    # --- Opponent range estimation ---
    hands_with_opp = [h for h in hands if h.get('opp_likely')]
    if hands_with_opp:
        print("OPPONENT RANGE ESTIMATION:")
        print(f"  Hands with range estimate: {len(hands_with_opp)}/{total}")

        range_counts = defaultdict(int)
        for h in hands_with_opp:
            for cat in h.get('opp_likely', []):
                range_counts[cat] += 1
        print("  Most common opponent ranges:")
        for cat, count in sorted(range_counts.items(), key=lambda x: -x[1])[:8]:
            print(f"    {cat:22s}: {count:4d}")

        bluff_pcts = [h['opp_bluff_pct'] for h in hands_with_opp if 'opp_bluff_pct' in h]
        if bluff_pcts:
            print(f"  Avg opponent bluff estimate:  {sum(bluff_pcts)/len(bluff_pcts):.2f}")

        narrow_vals = [h['opp_range_narrow'] for h in hands_with_opp if 'opp_range_narrow' in h]
        if narrow_vals:
            print(f"  Avg range narrowness:         {sum(narrow_vals)/len(narrow_vals):.2f}")

        # Hero-bluff vs opponent bluff estimate correlation
        hero_bluffs_vs_high_bluff_opp = [
            h for h in hands_with_opp
            if h.get('opp_bluff_pct', 0) >= 0.30
            and classify_decision(h.get('decision', '')) == 'call'
            and h.get('street') != 'PreFlop']
        hero_folds_vs_high_bluff_opp = [
            h for h in hands_with_opp
            if h.get('opp_bluff_pct', 0) >= 0.30
            and classify_decision(h.get('decision', '')) == 'fold'
            and h.get('street') != 'PreFlop']
        if hero_bluffs_vs_high_bluff_opp or hero_folds_vs_high_bluff_opp:
            total_hbo = len(hero_bluffs_vs_high_bluff_opp) + len(hero_folds_vs_high_bluff_opp)
            call_rate = len(hero_bluffs_vs_high_bluff_opp) / total_hbo * 100
            print(f"  Call rate vs high bluff opponents (>=30%): {call_rate:.0f}% "
                  f"({len(hero_bluffs_vs_high_bluff_opp)}/{total_hbo})")
        print()

    # --- Top leaks ---
    print("TOP LEAKS:")
    leaks = []

    # Leak: calling river with low equity at bad pot odds
    river_bad_calls = [h for h in hands
                       if h.get('street') == 'River'
                       and classify_decision(h.get('decision', '')) == 'call'
                       and h.get('equity', 0) < 0.30
                       and h.get('pot_odds', 0) > 0.25]
    if river_bad_calls:
        leaks.append(f"Calling river w/ <30% eq at >25% pot odds: {len(river_bad_calls)} hands")

    # Leak: folding with flush draw getting good odds
    fold_with_draws = [h for h in folds
                       if h.get('equity', 0) >= 0.30
                       and h.get('pot_odds', 1) <= 0.25
                       and h.get('street') in ('Flop', 'Turn')]
    if fold_with_draws:
        leaks.append(f"Folding flop/turn w/ 30%+ eq getting <25% pot odds: {len(fold_with_draws)} hands")

    # Leak: checking 80%+ equity on flop (slow-play leak)
    slow_plays = [h for h in hands
                  if h.get('street') == 'Flop'
                  and h.get('equity', 0) >= 0.80
                  and classify_decision(h.get('decision', '')) == 'call'
                  and h.get('call', 0) == 0]  # check = call with 0 call amount
    if slow_plays:
        leaks.append(f"Checking 80%+ equity on flop (slow-play): {len(slow_plays)} hands")

    # Leak: never raising postflop
    postflop = [h for h in hands if h.get('street') != 'PreFlop']
    postflop_raises = [h for h in postflop if classify_decision(h.get('decision', '')) == 'raise']
    if postflop and len(postflop_raises) / max(len(postflop), 1) < 0.10:
        leaks.append(f"Postflop raise rate only {len(postflop_raises)/max(len(postflop),1)*100:.0f}% (target: >15%)")

    # Leak: folding when pot-committed (SPR < 3)
    spr_fold_committed = [h for h in hands
                          if h.get('spr') is not None and h['spr'] < 3
                          and classify_decision(h.get('decision', '')) == 'fold'
                          and h.get('equity', 0) >= 0.25
                          and h.get('street') != 'PreFlop']
    if spr_fold_committed:
        leaks.append(f"Folding when pot-committed (SPR<3, eq>=25%): {len(spr_fold_committed)} hands")

    # Leak: no turn barreling
    if turn_checks_available and len(turn_bets) / max(len(turn_checks_available), 1) < 0.30:
        leaks.append(f"Turn barrel rate too low: {len(turn_bets)/max(len(turn_checks_available),1)*100:.0f}% (target: >40%)")

    # Leak: over-betting marginal hands deep
    deep_marginal_bets = [h for h in hands
                          if h.get('spr') is not None and h['spr'] > 8
                          and classify_decision(h.get('decision', '')) == 'raise'
                          and 0.35 <= h.get('equity', 0) < 0.50
                          and h.get('street') in ('Turn', 'River')]
    if len(deep_marginal_bets) > 5:
        leaks.append(f"Betting marginal hands when deep (SPR>8, eq 35-50%): {len(deep_marginal_bets)} hands")

    if leaks:
        for i, leak in enumerate(leaks, 1):
            print(f"  {i}. {leak}")
    else:
        print("  No major leaks detected!")

    print()

    # --- Decision quality score ---
    print("DECISION QUALITY SCORE:")
    score = 100
    deductions = []

    if paid_calls and len(bad_calls) / len(paid_calls) > 0.15:
        penalty = int((len(bad_calls) / len(paid_calls) - 0.15) * 100)
        score -= penalty
        deductions.append(f"-{penalty} bad calls")

    if folds and len(fold_with_odds) / len(folds) > 0.05:
        penalty = int((len(fold_with_odds) / len(folds) - 0.05) * 80)
        score -= penalty
        deductions.append(f"-{penalty} missed value folds")

    if slow_plays:
        penalty = min(len(slow_plays) * 3, 15)
        score -= penalty
        deductions.append(f"-{penalty} slow-plays")

    if spr_fold_committed:
        penalty = min(len(spr_fold_committed) * 5, 20)
        score -= penalty
        deductions.append(f"-{penalty} folding when committed")

    if postflop and len(postflop_raises) / max(len(postflop), 1) < 0.10:
        score -= 10
        deductions.append(f"-10 passive postflop")

    score = max(0, min(100, score))
    grade = 'A+' if score >= 95 else 'A' if score >= 90 else 'B+' if score >= 85 else \
            'B' if score >= 80 else 'C+' if score >= 75 else 'C' if score >= 70 else \
            'D' if score >= 60 else 'F'

    print(f"  Score: {score}/100 ({grade})")
    if deductions:
        print(f"  Deductions: {', '.join(deductions)}")

    print()
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description='Analyze poker hand history for leaks')
    parser.add_argument('--last', type=int, help='Analyze last N hands')
    parser.add_argument('--since', type=str, help='Analyze hands since date (YYYY-MM-DD)')
    parser.add_argument('--file', type=str, default=HAND_HISTORY_PATH, help='Path to hand history file')
    args = parser.parse_args()

    hands = load_hands(path=args.file, last_n=args.last, since=args.since)
    print(f"Loaded {len(hands)} hands from {args.file}")
    print()
    analyze(hands)


if __name__ == '__main__':
    main()
