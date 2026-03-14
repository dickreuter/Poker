# GTO Poker Research: Implementable Data for Poker Bot

**Date**: 2026-03-14
**Purpose**: Comprehensive GTO solver-derived data for `decisionmaker.py` and `range_equity.py`

---

## 1. PREFLOP OPENING RANGES (RFI) -- 6-Max, 100BB Deep

These are simplified GTO solver outputs (GTO Wizard / PokerCoaching). All choices are
binary (raise or fold) to be directly implementable. "Mixed" solver frequencies have been
resolved to pure strategies that preserve overall position percentages.

### Notation
- `AKs` = suited, `AKo` = offsuit, `AA` = pair
- In code we use uppercase: `AKS`, `AKO`, `AA`

### Recommended Open-Raise Sizes
| Position | Size (BB) |
|----------|-----------|
| UTG      | 2.0-2.5   |
| MP/HJ   | 2.0-2.5   |
| CO       | 2.3-2.5   |
| BTN      | 2.5       |
| SB       | 3.0       |

### UTG (Lojack) -- ~17.6% of hands
```
Pairs:  66+
Suited: A3s+, K8s+, Q9s+, J9s+, T9s
Offsuit: ATo+, KJo+, QJo

Eval7 string:
"66+, A3s+, K8s+, Q9s+, J9s+, T9s, ATo+, KJo+, QJo"
```

### MP (Hijack) -- ~21.4% of hands
```
Pairs:  55+
Suited: A2s+, K6s+, Q9s+, J9s+, T9s, 98s, 87s, 76s
Offsuit: ATo+, KTo+, QTo+

Eval7 string:
"55+, A2s+, K6s+, Q9s+, J9s+, T9s, 98s, 87s, 76s, ATo+, KTo+, QTo+"
```

### CO (Cutoff) -- ~27.8% of hands
```
Pairs:  33+
Suited: A2s+, K3s+, Q6s+, J8s+, T7s+, 97s+, 87s, 76s
Offsuit: A8o+, KTo+, QTo+, JTo

Eval7 string:
"33+, A2s+, K3s+, Q6s+, J8s+, T7s+, 97s+, 87s, 76s, A8o+, KTo+, QTo+, JTo"
```

### BTN (Button) -- ~43.5% of hands
```
Pairs:  33+
Suited: A2s+, K2s+, Q3s+, J4s+, T6s+, 96s+, 85s+, 75s+, 64s+, 53s+
Offsuit: A4o+, K8o+, Q9o+, J9o+, T8o+, 98o

Eval7 string:
"33+, A2s+, K2s+, Q3s+, J4s+, T6s+, 96s+, 85s+, 75s+, 64s+, 53s+, A4o+, K8o+, Q9o+, J9o+, T8o+, 98o"
```

### SB (Small Blind) -- ~42% raise-or-fold (no limping in GTO)
```
Pairs:  22+
Suited: A2s+, K2s+, Q4s+, J6s+, T7s+, 97s+, 86s+, 76s, 65s, 54s
Offsuit: A2o+, K5o+, Q8o+, J9o+, T9o

Eval7 string:
"22+, A2s+, K2s+, Q4s+, J6s+, T7s+, 97s+, 86s+, 76s, 65s, 54s, A2o+, K5o+, Q8o+, J9o+, T9o"
```

**Note on SB**: Solvers show SB opening ~40-50% when raising only (no limp).
Some solve for SB limp strategy which pushes total playable to ~62%.
We implement raise-or-fold for simplicity.

---

## 2. 3-BET RANGES BY POSITION

3-bet ranges are POLARIZED in GTO: a mix of value hands (for pot-building)
and bluff hands (suited wheel aces, suited connectors for blocker value + playability).

### 3-Bet Sizing
- IP (in position): 3.0x the open raise
- OOP (out of position): 3.5-4.0x the open raise
- From blinds vs BTN open: 3.5x

### vs UTG Open -- ~4-5% from any position
```
VALUE:  QQ+, AKs, AKo
BLUFF:  A5s, A4s  (30% freq each -- use random)

Eval7 string:
"QQ+, AKs, AKo"
(plus A5s/A4s at 30% frequency)
```

### vs MP Open -- ~5-6%
```
VALUE:  QQ+, AKs, AKo, AQs
BLUFF:  A5s, A4s, A3s (30% freq)

Eval7 string:
"QQ+, AKs, AKo, AQs"
```

### vs CO Open -- ~7-8%
```
VALUE:  JJ+, AQs+, AKo
BLUFF:  A5s-A2s (suited wheel aces), 76s, 65s (30% freq)

Eval7 string:
"JJ+, AQs+, AKo, A5s-A2s"
```

### vs BTN Open (from SB/BB) -- ~10-14%
```
VALUE:  TT+, ATs+, KQs, AQo+
BLUFF:  A9s, A8s, A5s-A2s, QJs, JTs, T9s, 98s, 87s, 76s, 65s, 54s

Eval7 string (BB vs BTN):
"TT+, ATs+, KQs, AQo+, A5s-A2s, 87s, 76s, 65s, 54s"
```

### Why Suited Wheel Aces (A5s-A2s) Are the Best Bluff 3-Bets
1. **Blocker**: Holding an Ace removes 3 combos of AA and reduces AK/AQ combos
2. **Equity**: ~35% equity vs a 4-bet calling range (decent runouts)
3. **Playability**: Can flop straights, pairs, and the nut flush draw
4. **A5s specifically**: Blocks 5x straight combos AND has the wheel straight draw

### 3-Bet Frequency Implementation
```python
# In gto_preflop_decision():
if hand in ('A5S', 'A4S', 'A3S', 'A2S', '76S', '65S', '54S'):
    # Mixed strategy: 3-bet ~30% of the time as bluff
    if random.random() < 0.30:
        return 'raise'
    else:
        return 'fold'  # These hands don't flat well OOP
```

---

## 3. BB DEFENSE (Calling) RANGES

BB gets a discount (already posted 1BB) so defends wider than any other position.

### BB vs UTG Open -- Defend ~30-35%
```
3-BET: QQ+, AKs, AKo, A5s-A4s (value + bluff)
CALL:  22-JJ, ATs-AQs, KJs+, QJs, JTs, T9s, 98s, 87s, 76s, AJo-AQo, KQo

Eval7 string (call):
"22-JJ, ATs-AQs, KJs+, QJs, JTs, T9s, 98s, 87s, 76s, AJo-AQo, KQo"
```

### BB vs CO Open -- Defend ~45-50%
```
3-BET: TT+, AQs+, AKo, A5s-A2s, 76s, 87s
CALL:  22-99, A2s-AJs, K9s+, Q9s+, J9s+, T8s+, 97s+, 86s+, 75s+, 65s, 54s,
       ATo-AJo, KTo+, QTo+, JTo

Eval7 string (call):
"22-99, A2s-AJs, K9s+, Q9s+, J9s+, T8s+, 97s+, 86s+, 75s+, 65s, 54s, ATo-AJo, KTo+, QTo+, JTo"
```

### BB vs BTN Open -- Defend ~55-60%
```
3-BET: TT+, ATs+, KQs, AQo+, A5s-A2s, 87s, 76s, 65s, 54s (~14% 3-bet)
CALL:  22-99, A2s-A9s, K2s+, Q5s+, J7s+, T7s+, 96s+, 85s+, 74s+, 64s+, 53s+, 43s,
       A2o-AJo, K5o+, Q8o+, J8o+, T8o+, 97o+, 87o

Eval7 string (call):
"22-99, A2s-A9s, K2s+, Q5s+, J7s+, T7s+, 96s+, 85s+, 74s+, 64s+, 53s+, 43s, A2o-AJo, K5o+, Q8o+, J8o+, T8o+, 97o+, 87o"
```

---

## 4. 4-BET RANGES

When facing a 3-bet, your range polarizes into value 4-bets and bluff 4-bets.

### 4-Bet Sizing
- Standard: 2.2-2.5x the 3-bet size
- OOP: 2.5x

### 4-Bet Value
```
AA, KK, QQ  (always, pure frequency)
AKs         (always)
JJ          (mixed ~50-70% depending on positions)
```

### 4-Bet Bluffs
```
A5s  (best bluff: blocks AA/AK, has equity, NOT dominated by AK calling range)
A4s  (second best bluff: same reasons)
A3s  (third)

Solver frequency: A5s 4-bets ~70% when facing a 3-bet
```

### Why A5s Not AKo for Bluffing
- AKo has too much equity to fold and too much value to bluff with
- AKo should mostly CALL the 3-bet (it has ~42% vs a 3-bet range)
- A5s blocks AA/55, has nut flush potential, and doesn't mind folding

### Facing a 4-Bet (What to Do with Our 3-Bet Range)
```
5-BET SHOVE: AA, KK (sometimes QQ at <100BB)
CALL:        QQ, JJ, AKs, AKo (at 100BB, these are too strong to fold)
FOLD:        All bluff 3-bets (A5s, A4s, 76s etc.)
```

### Implementation
```python
GTO_4BET = {
    'value': {'AA', 'KK', 'QQ', 'AKS'},  # Always 4-bet
    'mixed_value': {'JJ'},  # 4-bet ~60% (rest call)
    'bluff': {'A5S', 'A4S', 'A3S'},  # 4-bet ~70% (rest fold)
}

FACING_4BET = {
    'shove': {'AA', 'KK'},
    'call': {'QQ', 'JJ', 'AKS', 'AKO'},
    'fold': set()  # Everything else
}
```

---

## 5. BLOCKER THEORY -- Quantified

### Basic Combinatorics
| Hand Type | Default Combos | Holding 1 Blocker | Holding 2 Blockers |
|-----------|---------------|-------------------|--------------------|
| Pocket pair (AA)  | 6  | 3 (hold 1 Ace)  | 1 (hold 2 Aces) |
| Suited (AKs)      | 4  | 3 (hold A or K)  | 2 (hold A+K diff suits) |
| Offsuit (AKo)     | 12 | 9 (hold A or K)  | 6 (hold A+K) |
| Any AK (total)    | 16 | 12 (hold 1 Ace)  | -- |

### Key Blocker Effects for Implementation

**Holding one Ace:**
- Reduces AA from 6 to 3 combos (-50%)
- Reduces AK from 16 to 12 combos (-25%)
- Reduces AQ from 16 to 12 combos (-25%)
- Total "premium" combos blocked: significant

**Holding the Ace of a flush suit (e.g., As on Ks 9s 4s board):**
- Blocks the nut flush entirely (0 combos of Axs)
- Reduces opponent's flush combos by ~15-20%
- Makes bluffing with busted draws highly profitable

**Holding Kx on Ace-high board:**
- Blocks AK (12 -> 9 combos, -25%)
- Does NOT block AA, AQ, AJ
- Medium blocker value

### Blocker Scoring (for river decisions)

For BLUFFING (want to block value, unblock folds):
```python
BLOCKER_BLUFF_SCORE = {
    # Hand blocks these strong combos (good for bluffing)
    'nut_flush_blocker': 0.15,  # +15% fold equity when holding nut flush card
    'top_set_blocker': 0.08,    # Holding a board top card
    'straight_blocker': 0.05,   # Holding key straight card
    'overpair_blocker': 0.10,   # Holding one Ace/King blocks overpairs

    # Hand blocks these weak combos (bad for bluffing)
    'missed_draw_blocker': -0.10,  # Blocks hands that WOULD fold
    'low_pair_blocker': -0.05,     # Blocks weak hands that fold
}
```

For BLUFF-CATCHING (want to block bluffs, unblock value):
```python
BLOCKER_CALL_SCORE = {
    'blocks_flush_draw': 0.10,   # Holding card of flush draw suit
    'blocks_straight_draw': 0.05,
    'blocks_Ax_bluffs': 0.08,    # Ace blocks Ax suited bluffs
    'unblocks_value': 0.05,      # Not holding cards that are in value range
}
```

### Quantified Fold Equity Changes (from GTO Wizard data)
- Holding the 2s (low spade) on a spade board: **+5.93%** calling frequency from villain
  (BAD for bluffing -- we block trash that folds)
- Holding Ks8s: **+0.5%** combined calling from villain (minimal)
- Holding As (nut blocker) on 3-flush board: **~15% more fold equity** (GREAT for bluffing)

### Implementation in Decision Making
```python
def blocker_adjustment(hero_cards, board, action='bluff'):
    """Return equity adjustment based on blocker effects.

    Positive = favorable (more fold equity for bluffs, better odds for calls)
    Negative = unfavorable
    """
    adjustment = 0.0
    board_suits = [c[-1] for c in board]
    flush_suit = None
    from collections import Counter
    suit_counts = Counter(board_suits)
    for s, cnt in suit_counts.items():
        if cnt >= 3:
            flush_suit = s

    for card in hero_cards:
        rank, suit = card[0], card[-1]

        if action == 'bluff':
            # Blocking nut flush is great for bluffing
            if flush_suit and suit == flush_suit and rank == 'A':
                adjustment += 0.15
            elif flush_suit and suit == flush_suit:
                adjustment -= 0.05  # Blocking flush draws (their folds)

            # Blocking top pair / overpairs
            if rank == 'A':
                adjustment += 0.08  # Blocks AA, AK, AQ
            elif rank == 'K':
                adjustment += 0.05  # Blocks KK, AK

        elif action == 'call':
            # Blocking their bluffs is good for calling
            if flush_suit and suit == flush_suit:
                adjustment += 0.08  # Block missed flush draws
            if rank in ('A', 'K') and rank not in [c[0] for c in board]:
                adjustment -= 0.05  # Unblocking their value

    return adjustment
```

---

## 6. POSTFLOP C-BET STRATEGY BY BOARD TEXTURE

### C-Bet Frequency Guidelines (as PFR, heads-up, IP)

| Board Type | Frequency | Sizing | Example |
|-----------|-----------|--------|---------|
| Dry rainbow A-high | 70-80% | 25-33% pot | A72r, AK3r |
| Dry rainbow K-high | 65-75% | 33% pot | K83r, K72r |
| Dry rainbow low | 45-55% | 50-66% pot | 862r, 743r |
| Two-tone A/K-high | 60-70% | 33-50% pot | As8h3h |
| Two-tone connected | 40-55% | 50-66% pot | Js Th 8c |
| Wet connected | 30-45% | 66-75% pot | JT9ss, QJ8hh |
| Monotone | 25-35% | 33% pot | Jh8h3h |
| Paired A-high | 85-97% | 25-33% pot | AA5, AK8 paired |
| Paired low | 55-65% | 50-66% pot | K88, A55 |

### Board Texture Categories for Code

```python
BOARD_CATEGORIES = {
    'dry_high': {
        'description': 'A/K high, rainbow, disconnected',
        'examples': ['A72r', 'K83r', 'AJ2r'],
        'cbet_freq': 0.75,
        'cbet_size': 0.33,  # fraction of pot
        'check_raise_freq': 0.08,
    },
    'dry_low': {
        'description': 'Low cards, rainbow, disconnected',
        'examples': ['862r', '743r', '952r'],
        'cbet_freq': 0.50,
        'cbet_size': 0.55,
        'check_raise_freq': 0.12,
    },
    'two_tone_high': {
        'description': 'A/K high with flush draw possible',
        'examples': ['As8h3h', 'Kd7s4s'],
        'cbet_freq': 0.65,
        'cbet_size': 0.40,
        'check_raise_freq': 0.10,
    },
    'two_tone_connected': {
        'description': 'Connected cards with flush draw',
        'examples': ['JsTh8c', 'Qh9s8h'],
        'cbet_freq': 0.45,
        'cbet_size': 0.55,
        'check_raise_freq': 0.15,
    },
    'wet': {
        'description': 'Highly connected + flush draw',
        'examples': ['JT9ss', 'QJ8hh'],
        'cbet_freq': 0.35,
        'cbet_size': 0.66,
        'check_raise_freq': 0.18,
    },
    'monotone': {
        'description': 'All three cards same suit',
        'examples': ['Jh8h3h', 'Ks9s4s'],
        'cbet_freq': 0.27,
        'cbet_size': 0.33,
        'check_raise_freq': 0.12,
    },
    'paired_high': {
        'description': 'Paired board with high card',
        'examples': ['AA5', 'KK3', 'AK8p'],
        'cbet_freq': 0.90,
        'cbet_size': 0.30,
        'check_raise_freq': 0.05,
    },
    'paired_low': {
        'description': 'Paired board, low/medium',
        'examples': ['K88', 'A55', 'Q77'],
        'cbet_freq': 0.60,
        'cbet_size': 0.55,
        'check_raise_freq': 0.10,
    },
}
```

### Which Hands to C-Bet vs Check (General Rules)

**Always C-Bet (value + protection):**
- Overpairs (AA-TT on low boards)
- Top pair top kicker
- Sets / two pair
- Nut flush draws with overcards

**Usually C-Bet (thin value / semi-bluff):**
- Top pair medium kicker
- Second pair good kicker
- Flush draw + pair
- Open-ended straight draw + overcards

**Usually Check (trapping or giving up):**
- Top pair weak kicker (on wet boards)
- Middle pair (trap on dry boards)
- Backdoor draws only
- Overcards with no draws

**Always Check:**
- Complete air with no draws (on wet boards)
- Bottom pair no kicker

### Multiway Pot Adjustments
When 3+ players see flop:
- C-bet frequency drops to **25-35%** (from 50-75% heads-up)
- Only bet with **strong value or strong draws**
- Use **25-33% pot** sizing (not larger)
- No range-betting -- give up with air
- Equity realization is much lower (33% avg pot share per player)

---

## 7. VILLAIN RANGE BY STREET ACTION

These patterns are already partially in `range_equity.py` but here's the refined data.

### Action Pattern -> Range Implication

| Pattern | Range Description | Example Hands |
|---------|-------------------|---------------|
| UTG open, flop c-bet | Tight value + air | TT+, ATs+, AJo+, KQs, some air |
| UTG open, flop CHECK | Capped (no monsters) | AK no pair, 77-TT, suited connectors |
| Any open, flop bet + turn bet | Polarized (strong or draw) | Sets, overpairs, nut draws, some air |
| Bet flop, check turn | Medium / gave up | Top pair weak kicker, or gave up |
| Check flop, bet turn | Delayed c-bet / hit turn | 99+, ATs+, turned pair/draw |
| Bet-bet-bet (triple barrel) | Very polarized | Nuts or pure bluff |
| Check-raise flop | Very strong or draw | Sets, two pair, combo draws |
| Check-raise turn | Almost always strong | Sets+, nut straight/flush |
| Donk bet (non-raiser bets) | Medium strength or draw | Second pair, gutshot, weak TP |

### Capped Range Implementation

When villain checks back the flop as preflop raiser:
```python
CAPPED_RANGE = {
    'UTG_check_flop': 'AKo, AQo, AJs, KQs, 77-TT, suited connectors',
    'BTN_check_flop': '22-TT, A2s-ATs, K2s-KJs, Q2s-QJs, all suited connectors, all offsuit broadways',
}
# Key insight: NO sets, no overpairs, no top pair in checking range
# This means their range is MUCH weaker -> attack with delayed c-bet / probe
```

---

## 8. NASH EQUILIBRIUM PUSH/FOLD CHARTS

Already implemented in `range_equity.py` as `NASH_SHOVE_RANGES` and `CALL_RANGES_VS_SHOVE`.
The existing data is comprehensive. Key additions/refinements:

### ICM Adjustments for Tournaments

When on the bubble or near money:
```python
ICM_TIGHTENING = {
    'no_icm': 1.0,           # Cash game / early tournament
    'approaching_bubble': 0.85,  # Tighten by 15%
    'on_bubble': 0.70,          # Tighten by 30%
    'in_money': 0.90,           # Slightly tighter than chipEV
    'final_table': 0.75,        # Significant tightening
    'heads_up': 1.0,            # Back to chipEV
}

def icm_adjusted_shove(hand, position, stack_bb, icm_stage='no_icm'):
    """Check if hand is in the ICM-adjusted shove range."""
    # Get base Nash range
    base_in_range = lookup_push_fold(hand, position, stack_bb)

    factor = ICM_TIGHTENING.get(icm_stage, 1.0)

    if factor >= 1.0:
        return base_in_range

    # Tighten: Only shove if hand would be in a tighter stack's range
    # E.g., if factor=0.70, check if hand is in the range for stack_bb * 0.70
    tighter_stack = max(3, int(stack_bb * factor))
    return lookup_push_fold(hand, position, tighter_stack)
```

### Missing Stack Depths (4BB, 6BB, 7BB, 9BB, 11BB, 13BB, 14BB)

The existing code uses interpolation between defined depths (3, 5, 8, 10, 12, 15).
This is sufficient -- the `lookup_push_fold()` function handles intermediate stacks.

---

## 9. SPR (Stack-to-Pot Ratio) STRATEGY

### SPR Commitment Thresholds

| SPR | Equity Needed | Commit With | Fold |
|-----|---------------|-------------|------|
| < 1 | 33% | Almost anything | Almost nothing |
| 1-2 | 33-40% | Top pair+, most flush draws, OESDs | Gutshots alone, bottom pair |
| 2-4 | 40-43% | Top pair good kicker+, combo draws | Weak top pair, naked draws |
| 4-7 | 43%+ | Overpair+, nut draws | Top pair medium kicker is marginal |
| 7-13 | Flexible | Two pair+, nut draws | One pair usually folds to heavy action |
| 13+ | Flexible | Sets+, robust draws | Even overpairs fold to 3 streets of action |

### Hand Types by SPR Commitment

```python
SPR_COMMITMENT = {
    # SPR ranges -> minimum hand strength to get all-in
    (0, 2): ['top_pair', 'overpair', 'flush_draw', 'oesd', 'two_pair', 'set'],
    (2, 4): ['top_pair_good_kicker', 'overpair', 'combo_draw', 'two_pair', 'set'],
    (4, 7): ['overpair', 'top_two_pair', 'nut_flush_draw_with_pair', 'set'],
    (7, 13): ['two_pair_top', 'set', 'straight', 'flush', 'nut_draw_combo'],
    (13, 999): ['set', 'straight', 'flush', 'full_house'],
}
```

### SPR and Bet Sizing

```python
def spr_bet_sizing(spr, street, board_wetness):
    """Return recommended bet size as fraction of pot based on SPR."""
    if spr < 1.5:
        return 1.0  # Shove
    elif spr < 3.0:
        return 0.75  # Commit
    elif spr < 7.0:
        if street == 'flop':
            return 0.50 if board_wetness > 0.5 else 0.33
        elif street == 'turn':
            return 0.66
        else:
            return 0.75
    else:  # Deep SPR
        if street == 'flop':
            return 0.33 if board_wetness < 0.3 else 0.50
        elif street == 'turn':
            return 0.55
        else:
            return 0.66
```

### Robust vs Fragile Hands (SPR-Dependent)

**Robust (good at any SPR):**
- Draws to the nuts (nut flush draw, nut straight draw)
- Combo draws (pair + flush draw)
- Sets

**Fragile (fold at high SPR, commit at low SPR):**
- Top pair (even good kicker) -- committed at SPR<4, folding to heavy action at SPR>7
- Overpairs -- committed at SPR<6, marginal at SPR>13
- Middle pair -- only committed at SPR<2

---

## 10. BOARD TEXTURE CLASSIFICATION ALGORITHM

### Wetness Score (0.0 = bone dry, 1.0 = extremely wet)

The existing `_board_wetness()` in `decisionmaker.py` is a good start. Enhanced version:

```python
def board_wetness(board_cards):
    """Calculate board wetness score 0.0-1.0.

    Components:
    - Flush draw potential (suitedness)
    - Straight draw potential (connectedness)
    - Card height (broadway boards are wetter)
    - Pairing (paired boards are drier)
    """
    if not board_cards or len(board_cards) < 3:
        return 0.5

    rank_map = {r: i for i, r in enumerate('23456789TJQKA')}
    ranks, suits = [], []
    for card in board_cards[:3]:  # Flop only
        if len(card) >= 2:
            ranks.append(rank_map.get(card[0].upper(), 0))
            suits.append(card[-1].upper())

    if len(ranks) < 3:
        return 0.5

    wetness = 0.0

    # --- Flush potential ---
    from collections import Counter
    suit_counts = Counter(suits)
    top_suit_count = suit_counts.most_common(1)[0][1]
    if top_suit_count >= 3:
        wetness += 0.40  # Monotone (flush already possible)
    elif top_suit_count == 2:
        wetness += 0.15  # Two-tone (flush draw possible)
    # Rainbow: +0.0

    # --- Straight potential ---
    sorted_ranks = sorted(set(ranks))
    # Count cards within 5-card window
    max_in_window = 0
    for base in range(max(0, min(sorted_ranks) - 4), min(sorted_ranks) + 1):
        count = sum(1 for r in sorted_ranks if base <= r < base + 5)
        max_in_window = max(max_in_window, count)

    if max_in_window >= 3:
        wetness += 0.25  # 3 cards within 5 = many straight draws
    elif max_in_window == 2:
        # Check gaps
        gaps = [sorted_ranks[i+1] - sorted_ranks[i] for i in range(len(sorted_ranks)-1)]
        if min(gaps) <= 2:
            wetness += 0.15  # Some connectivity
        else:
            wetness += 0.05  # Minimal connectivity

    # --- Card height ---
    avg_rank = sum(ranks) / len(ranks)
    if avg_rank >= 10:  # Broadway-heavy (T or above avg)
        wetness += 0.10
    elif avg_rank >= 7:
        wetness += 0.05

    # --- Pairing ---
    if len(set(ranks)) < len(ranks):
        wetness -= 0.15  # Paired board = drier

    return max(0.0, min(1.0, wetness))
```

### Flush Draw Count
```python
def count_flush_draws(board_suits):
    """Count possible flush draws on this board.
    0 = rainbow (no draws), 1 = two-tone (1 draw), 2+ = monotone"""
    from collections import Counter
    counts = Counter(board_suits)
    return sum(1 for c in counts.values() if c >= 2)
```

### Straight Draw Count
```python
def count_straight_draws(board_ranks):
    """Approximate number of straight draws possible.
    Higher = wetter board."""
    sorted_r = sorted(set(board_ranks))
    draws = 0
    # Check all possible 5-card straight windows
    for base in range(0, 10):  # 2-high through A-high
        window = range(base, base + 5)
        cards_in_window = sum(1 for r in sorted_r if r in window)
        if cards_in_window >= 2:
            draws += cards_in_window - 1  # Each additional card = more draws
    return draws
```

---

## 11. MULTIWAY POT ADJUSTMENTS

### Key Rules (from GTO Wizard data)
1. **Stop range-betting** -- Only bet with strong value or strong draws
2. **Size down** -- Use 25-33% pot (never >50% unless nutted)
3. **Tighten value thresholds** -- Top pair is NOT a value bet 3-way
4. **Give up more** -- Fold rate should be higher with trash
5. **Deny equity** -- Bet draws that can improve but fold weak draws

### Implementation
```python
MULTIWAY_ADJUSTMENTS = {
    'cbet_freq_multiplier': {
        2: 1.0,    # Heads-up: normal
        3: 0.55,   # 3-way: cut c-bet freq nearly in half
        4: 0.35,   # 4-way: very selective
        5: 0.20,   # 5-way: only bet the nuts
    },
    'bet_size_max': {
        2: 1.0,    # Heads-up: up to pot
        3: 0.50,   # 3-way: max half pot
        4: 0.33,   # 4-way: max third pot
        5: 0.25,   # 5-way: quarter pot
    },
    'value_threshold': {
        # Minimum hand strength to value bet
        2: 'top_pair',
        3: 'top_pair_top_kicker',
        4: 'overpair',
        5: 'two_pair',
    },
}
```

---

## 12. INTEGRATION WITH EXISTING CODEBASE

### Files to Update

1. **`decisionmaker.py`**: The `GTO_OPEN` ranges should be updated with the refined
   ranges from Section 1. The current ranges are already close but differ slightly
   (e.g., UTG currently has A5S-A2S which is slightly wider than GTO Wizard's output).

2. **`range_equity.py`**: The `RFI_RANGES` should be synchronized with `GTO_OPEN`.
   Currently they're slightly different:
   - `RFI_RANGES['UTG']` = `'TT+, ATs+, KQs, AJo+'` (~12%)
   - `GTO_OPEN['UTG']` includes 66+, which is wider
   - **Recommendation**: Use the GTO Wizard ranges (66+) as they're from a more recent solver

3. **`range_equity.py`**: Add `FOUR_BET_RANGES` and `FACING_4BET_RANGES` (Section 4).

4. **`decisionmaker.py`**: Add blocker-based adjustments to river decisions (Section 5).

5. **`decisionmaker.py`**: Enhance `_board_wetness()` with the improved algorithm (Section 10).

6. **`range_equity.py`**: Add ICM adjustment function (Section 8).

7. **`decisionmaker.py`**: Add multiway pot adjustment logic (Section 11).

### Priority of Implementation
1. **HIGH**: Refined preflop ranges (direct EV impact)
2. **HIGH**: 4-bet ranges (currently missing entirely)
3. **HIGH**: Blocker adjustments for river decisions
4. **MEDIUM**: Enhanced board wetness algorithm
5. **MEDIUM**: SPR commitment logic (partially exists)
6. **MEDIUM**: Multiway pot adjustments
7. **LOW**: ICM adjustments (mainly for tournament play)

---

## SOURCES

- [GTO Wizard - Preflop Range Morphology](https://blog.gtowizard.com/preflop-range-morphology/)
- [GTO Wizard - Understanding Blockers](https://blog.gtowizard.com/understanding-blockers-in-poker/)
- [GTO Wizard - Blockers & Unblockers: Picking Great Bluffs](https://blog.gtowizard.com/blockers-unblockers-the-secret-to-picking-great-bluffs/)
- [GTO Wizard - 10 Tips for Multiway Pots](https://blog.gtowizard.com/10-tips-multiway-pots-in-poker/)
- [GTO Wizard - Stack-to-Pot Ratio](https://blog.gtowizard.com/stack-to-pot-ratio/)
- [PokerOffer - Poker Starting Hands 2026](https://thepokeroffer.com/poker-starting-hands-preflop-charts-2026/)
- [PokerOffer - C-Bet Strategy Guide 2026](https://thepokeroffer.com/poker-c-bet-strategy-guide-2026/)
- [FreeBetRange - 6max Open Raise Charts](https://blog.freebetrange.com/article/preflop-charts-open-raise-in-6-max-poker-cash-games)
- [Upswing Poker - 6-Max Strategy](https://upswingpoker.com/6-handed-max-poker-strategy/)
- [Upswing Poker - 3-Bet Strategy](https://upswingpoker.com/3-bet-strategy-aggressive-preflop/)
- [Upswing Poker - 4-Bet Strategy](https://upswingpoker.com/4-bet-size-strategy/)
- [Upswing Poker - Push-Fold Charts](https://upswingpoker.com/push-fold-tournament-strategy-charts/)
- [SplitSuit - SPR Strategy](https://www.splitsuit.com/spr-poker-strategy)
- [SplitSuit - Poker Combos & Blockers](https://www.splitsuit.com/poker-combos-blockers)
- [PokerCoaching - Implementable GTO Charts](https://poker-coaching.s3.amazonaws.com/tools/preflop-charts/online-6max-gto-charts.pdf)
- [HoldemResources - Nash Equilibrium](https://www.holdemresources.net/hune)
- [GamblingCalc - Push/Fold Calculator](https://gamblingcalc.com/poker/push-fold-chart/)
- [888poker - Board Textures](https://www.888poker.com/magazine/poker-board-textures)
- [poker.com - Nash Equilibrium Charts](https://poker.com/learn-poker/nash-equilibrium-pushbot-charts-for-poker-tournaments/)
- [BBZ Poker - ICM Bubble Strategy](https://bbzpoker.com/extreme-icm-bubble-strategy/)
