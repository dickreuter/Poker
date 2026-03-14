# GTO Poker Strategy Reference -- Implementable Knowledge

This document contains Game Theory Optimal (GTO) poker strategy data compiled
from solver outputs, Nash equilibrium calculators, and modern poker theory.
All data is organized for direct implementation in the bot's decision engine.

**How this relates to the codebase**: Most of the ranges and formulas below are
already partially implemented in `sys_core/decisionmaker/range_equity.py` and
`sys_core/decisionmaker/decisionmaker.py`. This document serves as the reference
source for verifying, extending, and tuning those implementations.

---

## 1. Nash Equilibrium Push/Fold

### 1.1 When to Use Push/Fold

Pure push/fold strategy becomes optimal when effective stacks fall below ~10BB.
Between 10-15BB, it is nearly optimal and far simpler than open-raising.
Above 15BB, standard open-raise strategy is preferred.

**Already implemented**: `range_equity.py` has `NASH_SHOVE_RANGES` and
`CALL_RANGES_VS_SHOVE` covering 3-15BB for all positions.

### 1.2 Open-Shove Ranges by Position and Stack Depth

These are Nash equilibrium ranges for open-shoving (folded to you).
Approximate hand count percentages are shown.

#### UTG (Under the Gun)

| Stack | Range | ~% |
|-------|-------|----|
| 3 BB  | 22+, A2s+, K5s+, Q8s+, J8s+, T8s+, 98s, A2o+, K8o+, Q9o+, JTo | ~38% |
| 5 BB  | 22+, A2s+, K9s+, QTs+, JTs, A7o+, KTo+ | ~22% |
| 8 BB  | 44+, A7s+, KTs+, QJs, A9o+, KQo | ~14% |
| 10 BB | 55+, A4s+, K9s+, QTs+, J9s+, T9s, A9o+, KJo+ | ~16% |
| 12 BB | 55+, A8s+, KTs+, QJs, ATo+, KQo | ~12% |
| 15 BB | 66+, ATs+, KJs+, AJo+, KQo | ~9% |

#### MP (Middle Position)

| Stack | Range | ~% |
|-------|-------|----|
| 3 BB  | 22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 97s+, 87s, 76s, A2o+, K5o+, Q8o+, J9o+, T9o | ~52% |
| 5 BB  | 22+, A2s+, K7s+, Q9s+, J9s+, T9s, 98s, A4o+, KTo+, QJo | ~28% |
| 8 BB  | 22+, A2s+, K9s+, Q9s+, J9s+, T9s, A8o+, KTo+, QJo | ~24% |
| 10 BB | 33+, A2s+, K9s+, Q9s+, J9s+, T9s, A9o+, KJo+, QJo | ~20% |
| 12 BB | 55+, A5s+, KTs+, QJs, JTs, ATo+, KQo | ~14% |
| 15 BB | 66+, A9s+, KTs+, QJs, AJo+, KQo | ~11% |

#### CO (Cutoff)

| Stack | Range | ~% |
|-------|-------|----|
| 3 BB  | 22+, A2s+, K2s+, Q2s+, J4s+, T6s+, 96s+, 86s+, 75s+, 65s, 54s, A2o+, K2o+, Q5o+, J7o+, T8o+, 98o | ~62% |
| 5 BB  | 22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 97s+, 87s, 76s, A2o+, K5o+, Q8o+, J9o+, T9o | ~45% |
| 8 BB  | 22+, A2s+, K8s+, Q9s+, J9s+, T9s, A5o+, KTo+, QJo | ~28% |
| 10 BB | 44+, A5s+, KTs+, QJs, JTs, ATo+, KQo | ~15% |
| 12 BB | 55+, A8s+, KTs+, QJs, JTs, AJo+, KQo | ~12% |
| 15 BB | 66+, ATs+, KJs+, AJo+, KQo | ~9% |

#### BTN (Button)

| Stack | Range | ~% |
|-------|-------|----|
| 3 BB  | 22+, A2s+, K2s+, Q2s+, J2s+, T4s+, 95s+, 85s+, 74s+, 64s+, 53s+, 43s, A2o+, K2o+, Q2o+, J5o+, T7o+, 97o+, 87o | ~78% |
| 5 BB  | 22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 97s+, 86s+, 76s, 65s, A2o+, K7o+, Q9o+, JTo | ~48% |
| 8 BB  | 22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 97s+, 87s, 76s, A2o+, K7o+, Q9o+, JTo | ~42% |
| 10 BB | 22+, A2s+, K4s+, Q7s+, J8s+, T8s+, 98s, A2o+, K9o+, QTo+, JTo | ~34% |
| 12 BB | 22+, A2s+, K5s+, Q8s+, J8s+, T8s+, 98s, A2o+, K9o+, QTo+, JTo | ~30% |
| 15 BB | 22+, A2s+, K5s+, Q8s+, J8s+, T8s+, 98s, 87s, A4o+, KTo+, QJo | ~28% |

#### SB (Small Blind)

| Stack | Range | ~% |
|-------|-------|----|
| 3 BB  | Nearly any two cards (~90%) | ~90% |
| 5 BB  | 22+, A2s+, K2s+, Q2s+, J4s+, T6s+, 96s+, 86s+, 75s+, 65s, 54s, A2o+, K2o+, Q5o+, J8o+, T8o+ | ~65% |
| 8 BB  | 22+, A2s+, K2s+, Q4s+, J6s+, T6s+, 96s+, 86s+, 75s+, 65s, 54s, A2o+, K2o+, Q5o+, J8o+, T8o+ | ~60% |
| 10 BB | 22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 97s+, 86s+, 76s, 65s, A2o+, K4o+, Q8o+, J9o+, T9o | ~50% |
| 12 BB | 22+, A2s+, K2s+, Q4s+, J6s+, T7s+, 97s+, 86s+, 76s, 65s, A2o+, K3o+, Q8o+, J9o+, T9o | ~48% |
| 15 BB | 22+, A2s+, K2s+, Q4s+, J6s+, T7s+, 97s+, 86s+, 76s, 65s, A2o+, K5o+, Q8o+, J9o+, T9o | ~45% |

### 1.3 Call-vs-Shove Ranges

When facing a shove, call ranges are tighter because you must invest more
chips and your hand must beat their shoving range.

#### BB Calling vs Various Positions (at 10BB)

| Shover Position | BB Calling Range |
|-----------------|-----------------|
| UTG shove       | 77+, ATs+, KQs, AJo+ |
| MP shove        | 66+, ATs+, KQs, AJo+, KQo |
| CO shove        | 55+, A9s+, KJs+, ATo+, KQo |
| BTN shove       | 44+, A7s+, KTs+, QJs, A9o+, KJo+ |
| SB shove        | 33+, A5s+, K9s+, Q9s+, J9s+, T9s, A8o+, KTo+, QJo |

### 1.4 Push/Fold Math

The EV of shoving all-in:

```
EV(shove) = P(everyone folds) * (blinds + antes)
           + P(called) * [P(win|called) * (pot_if_win) - P(lose|called) * (stack)]

Where:
  P(everyone folds) = product of fold probability for each remaining player
  P(called) = 1 - P(everyone folds)  (simplified, assuming max 1 caller)
  pot_if_win = stack + call_amount + blinds + antes
```

For a simple SB vs BB calculation at 10BB:
```
EV(shove) = P(fold) * 1.5BB + P(call) * [equity * (20BB + 1.5BB) - (1 - equity) * 10BB]
```

### 1.5 ICM Modifications to Push/Fold

ICM (Independent Chip Model) modifies Nash ranges in tournaments:

**Bubble Factor**: Ratio of equity lost by busting vs equity gained by doubling.
- Cash game: Bubble Factor = 1.0 (chips are chips)
- Early tournament: ~1.1-1.3
- Bubble: 1.5-3.0 (or higher for short stacks)
- Final table: 1.3-2.5

**How to adjust**:
```python
# ICM adjustment: tighten ranges by bubble factor
# If BF = 2.0, you need twice the edge to profitably shove
required_equity = 0.50 * bubble_factor / (1 + bubble_factor)

# Example: BF=2.0 -> need 66.7% equity to call (vs 50% in cash)
# BF=1.5 -> need 60% equity
# BF=1.0 -> need 50% equity (cash game)
```

**Practical adjustments**:
- Short stack on bubble: Tighten shove range by ~30-40%
- Big stack on bubble: Widen shove range by ~10-20% (can apply pressure)
- Near pay jumps: Tighten proportionally to pay jump size

---

## 2. Preflop GTO Ranges (100BB Deep, 6-Max)

### 2.1 Open-Raise (RFI) Ranges by Position

Standard raise size: 2.5BB from all positions, 3.0BB from SB.

#### UTG (~15-17% of hands)

```
Pairs:    66+
Suited:   A2s+, KTs+, QJs, JTs, T9s, 98s, 87s, 76s
Offsuit:  AJo+, KQo
```

Note: Some solvers include 55, 44 and hands like A5s-A3s, K9s. The tighter
range above is more robust for implementation.

#### MP (~19-22% of hands)

```
Pairs:    55+
Suited:   A2s+, K9s+, Q9s+, J9s+, T9s, T8s, 98s, 87s, 76s, 65s
Offsuit:  ATo+, KQo
```

#### CO (~27-30% of hands)

```
Pairs:    22+
Suited:   A2s+, K8s+, Q9s+, J9s+, T8s+, 97s+, 87s, 86s, 76s, 75s, 65s, 54s
Offsuit:  ATo+, KJo+, QJo, JTo
```

#### BTN (~40-48% of hands)

```
Pairs:    22+
Suited:   A2s+, K5s+, Q7s+, J8s+, T7s+, 96s+, 86s+, 75s+, 65s, 64s, 54s, 53s, 43s
Offsuit:  A2o+, K9o+, Q9o+, J9o+, T9o
```

#### SB (~36-45% of hands, mix of raise and limp in some strategies)

```
Raise range:
Pairs:    22+
Suited:   A2s+, K5s+, Q8s+, J8s+, T8s+, 97s+, 86s+, 75s+, 65s, 54s
Offsuit:  A7o+, K9o+, QTo+, JTo
```

### 2.2 3-Bet Ranges by Position

3-bet sizing: 3x the open (IP), 4x the open (OOP).
Example: Facing 2.5BB open, 3-bet to 7.5BB IP or 10BB OOP.

#### vs UTG open (~3% 3-bet)

```
Value:  QQ+, AKs, AKo
Bluffs: (very few -- A5s occasionally)
```

#### vs MP open (~4-5% 3-bet)

```
Value:  QQ+, AKs, AKo, AQs
Bluffs: A5s, A4s (wheel suited aces as blockers)
```

#### vs CO open (~6-7% 3-bet)

```
Value:  JJ+, AQs+, AKo
Bluffs: A5s-A2s, 76s, 87s (suited connectors + blocker aces)
```

#### vs BTN open (~9-11% 3-bet)

```
Value:  TT+, ATs+, KQs, AQo+
Bluffs: A5s-A2s, 76s, 87s, 98s, K9s, Q9s (wider bluffs)
```

#### SB vs BTN open (~14-18% 3-bet)

```
Value:  TT+, ATs+, KJs+, AJo+, KQo
Bluffs: A5s-A2s, K9s-K7s, 76s-54s, J9s, T9s
```

**Key principle**: 3-bet bluff hands should have blocker value:
- Axs blocks AA, AK (opponent less likely to 4-bet)
- Kxs blocks KK, AK
- Suited connectors have playability when called

### 2.3 Calling Ranges vs a Raise

#### BB Defending vs BTN 2.5x open (~40-50% defend)

```
Call:  22-99, A2s-ATs, K7s+, Q9s+, J9s+, T8s+, 97s+, 86s+, 76s, 65s, 54s,
      A9o-AJo, KTo+, QTo+, JTo
3-bet: (see above)
Fold:  the rest
```

#### BB Defending vs UTG 2.5x open (~25-30% defend)

```
Call:  22-JJ, ATs-AQs, KQs, KJs, QJs, JTs, T9s, 98s, 87s, AJo-AQo, KQo
3-bet: QQ+, AKs, AKo (see above)
Fold:  most offsuit broadways, weak suited hands
```

### 2.4 Stack Depth Adjustments

| Stack Depth | Key Changes |
|-------------|------------|
| 15 BB       | Pure push/fold. No open-raising. See Section 1. |
| 25 BB       | Tight open ranges. 3-bet = shove. No flatting 3-bets. Open 2x-2.2x. |
| 50 BB       | Standard ranges but tighter. Can flat 3-bets with position. Reduced implied odds. |
| 100 BB      | Full standard ranges (above). Full postflop play. Maximum implied odds. |
| 150+ BB     | Speculative hands gain value (suited connectors, small pairs). Overpairs lose relative value. |

At 25BB specifically:
- Open to 2x-2.2x (not 2.5x) to risk less
- 3-bet = all-in with value range (TT+, AQs+, AKo)
- 3-bet bluff range shrinks (can't afford to fold to 4-bet)
- Suited connectors lose value (not enough stack to extract implied odds)

---

## 3. Postflop GTO Concepts

### 3.1 C-Bet Strategy by Board Texture

#### Dry Boards (e.g., K72r, A83r)

```
Sizing:    25-33% of pot
Frequency: 70-90% of range
Reason:    Raiser has massive range advantage. Small bets extract thin value,
           deny equity cheaply, and are hard to exploit.
```

**Implementation**:
```python
if board_wetness < 0.3:
    cbet_size = 0.33 * pot  # 1/3 pot
    cbet_frequency = 0.80   # Bet ~80% of range
```

#### Wet/Connected Boards (e.g., JT9ss, 876ss)

```
Sizing:    50-75% of pot (or check more often)
Frequency: 40-60% of range
Reason:    Both players connect. Range advantage is smaller.
           Need larger sizing to charge draws.
```

**Implementation**:
```python
if board_wetness > 0.7:
    cbet_size = 0.66 * pot  # 2/3 pot
    cbet_frequency = 0.50   # Bet only ~50%
```

#### Paired Boards (e.g., KK4, 772)

```
Sizing:    50-75% of pot
Frequency: 55-70% of range
Reason:    Raiser has more big card combos. Can bet large since
           defender rarely has trips.
```

#### Monotone Boards (e.g., Jh 8h 3h)

```
Sizing:    25-40% of pot
Frequency: 50-65% of range
Reason:    Many draws available. Small bets are efficient.
           Having the nut flush draw blocker (Ah) is critical.
           Bet more when you hold the highest card of that suit.
```

### 3.2 Board Wetness Calculation

For implementation, compute a 0.0-1.0 wetness score:

```python
def board_wetness(board_cards):
    """Calculate 0.0 (dry) to 1.0 (wet) board texture score."""
    score = 0.0
    ranks = sorted([card_rank_value(c) for c in board_cards])

    # Flush draw potential: 2+ same suit
    suits = [card_suit(c) for c in board_cards]
    max_same_suit = max(Counter(suits).values())
    if max_same_suit >= 3:
        score += 0.4  # Monotone
    elif max_same_suit >= 2:
        score += 0.2  # Two-tone

    # Straight draw potential: connected ranks
    if len(ranks) >= 3:
        gaps = [ranks[i+1] - ranks[i] for i in range(len(ranks)-1)]
        min_gap = min(gaps)
        if min_gap <= 1:
            score += 0.3  # Very connected
        elif min_gap <= 2:
            score += 0.15  # Semi-connected

    # High card texture: more medium cards = wetter
    mid_count = sum(1 for r in ranks if 5 <= r <= 10)
    score += mid_count * 0.05

    # Broadway-heavy boards
    broadway_count = sum(1 for r in ranks if r >= 10)
    score += broadway_count * 0.03

    return min(1.0, score)
```

### 3.3 Pot Odds and Equity Required

```
Pot odds = amount_to_call / (pot + amount_to_call)

If pot = 100 and you must call 50:
  pot_odds = 50 / (100 + 50) = 33.3%
  You need >= 33.3% equity to call profitably.
```

Common bet sizes and required equity:

| Bet Size (% pot) | Required Equity to Call |
|-------------------|----------------------|
| 25% pot          | 16.7% |
| 33% pot          | 20.0% |
| 50% pot          | 25.0% |
| 66% pot          | 28.6% |
| 75% pot          | 30.0% |
| 100% pot (pot)   | 33.3% |
| 150% pot         | 37.5% |
| 200% pot (2x)    | 40.0% |

**Implementation**:
```python
def pot_odds(call_amount, pot_before_call):
    return call_amount / (pot_before_call + call_amount)

def should_call(equity, call_amount, pot):
    return equity >= pot_odds(call_amount, pot)
```

### 3.4 Check-Raise Strategy

GTO check-raise frequency by board type (BB vs IP c-bet):

| Board Type | Check-Raise Frequency | Hands to Check-Raise |
|------------|----------------------|---------------------|
| Dry (K72r) | 5-8% of range | Sets, two pair, occasional gutshot bluff |
| Medium (QT4ss) | 10-15% of range | Sets, two pair, flush draws, open-enders |
| Wet (JT9ss) | 12-18% of range | Sets, straights, combo draws, flush draws |
| Low connected (765) | 15-20% of range | Two pair, straights, pair + straight draw |
| Paired (KK4) | 3-6% of range | Trips, full houses only |

**Check-raise hand selection**:
- Value: Sets, two pair, straights, flushes (top of range)
- Semi-bluff: Flush draws, open-ended straight draws, combo draws
- Ratio: ~60% value, ~40% bluff (on flop)
- Turn/River: ratio shifts to ~70% value, ~30% bluff

### 3.5 SPR (Stack-to-Pot Ratio) Strategy

```
SPR = Effective_Stack / Pot_on_Flop
```

| SPR | Category | Commitment Threshold | Strategy |
|-----|----------|---------------------|----------|
| < 1 | Ultra-low | Any pair | Already committed. Shove flop with any piece. |
| 1-4 | Low | Top pair+ | One pair hands are strong enough to stack off. Single big bet decides the hand. |
| 4-7 | Medium-Low | Top pair top kicker+ | TPTK is still good. Two pair/sets are monsters. |
| 7-13 | Medium | Two pair+ | Need two pair or better to commit full stack. Top pair is a bluff-catcher. |
| 13+ | High | Sets+ | Only sets, straights, flushes justify getting stacks in. Speculative hands shine. |

**SPR and hand selection**:
```python
def hand_strength_needed_for_stack_off(spr):
    if spr < 1:
        return 'any_pair'
    elif spr < 4:
        return 'top_pair'
    elif spr < 7:
        return 'top_pair_top_kicker'
    elif spr < 13:
        return 'two_pair'
    else:
        return 'set_or_better'
```

**SPR and preflop hand value**:
- Low SPR (<4): Big pairs (AA, KK, QQ) are premium. AK is strong.
- Medium SPR (4-13): Big pairs good but vulnerable. AK needs to hit.
- High SPR (13+): Suited connectors (78s, 9Ts) and small pairs (22-66) gain
  value from implied odds. Big pairs lose relative value.

---

## 4. Opponent Range Estimation

### 4.1 Preflop Range Assignment by Action

**Already implemented**: `range_equity.py` has `PLAYER_TYPE_RANGES` and
`estimate_villain_range()` covering all these scenarios.

| Action | Estimated Range | ~% Hands |
|--------|----------------|----------|
| UTG open raise | 77+, ATs+, KQs, AJo+, KQo | ~15% |
| MP open raise | 55+, A9s+, KTs+, QJs, JTs, ATo+, KQo | ~20% |
| CO open raise | 22+, A2s+, K8s+, Q9s+, J9s+, T8s+, ATo+, KJo+, QJo | ~28% |
| BTN open raise | 22+, A2s+, K5s+, Q7s+, J8s+, ATo+, K9o+, Q9o+, J9o+, T9o | ~42% |
| 3-bet (generic) | TT+, AQs+, AKo, (+ bluffs: A5s-A2s, 76s) | ~6-10% |
| 4-bet | QQ+, AKs, AKo (+ rare bluffs: A5s) | ~3% |
| Cold call (IP) | 22-JJ, ATs-AQs, KQs, KJs, QJs, JTs, T9s, 98s, AJo-AQo | ~12% |
| Limp (fish) | 22+, Axs, Kxs, many suited, random offsuit | ~40-70% |

### 4.2 Postflop Range Narrowing by Action

| Opponent Action | What it means | Range narrowing |
|-----------------|--------------|-----------------|
| C-bet on dry board | Continuation bet, wide range | Keep ~70-80% of preflop range |
| C-bet on wet board | Needs equity, narrower | Keep ~50-60% of preflop range |
| Check-back flop (IP) | Weak/medium, gave up initiative | Remove strong hands (sets, top pair), keep medium/weak |
| Bet large on turn | Polarized: nuts or bluff | Keep strong value + draws/air |
| Small bet on river | Thin value or blocking bet | Keep medium-strong hands |
| Large bet on river | Polarized: nuts or bluff | Keep very strong value + missed draws |
| Check-raise flop | Sets, two pair, or semi-bluff | Keep top 5-15% of range + draws |
| Overbet river | Very polarized, nut-heavy | Keep nut hands + best bluff candidates |

### 4.3 Blocker Effects

Blockers reduce the number of possible combinations an opponent can hold.

| Card You Hold | What It Blocks | Strategic Implication |
|--------------|---------------|---------------------|
| Ah | Opponent has fewer AA, AK, AQ combos | Better bluff candidate; less likely to face strong Ax |
| Kh | Blocks KK, AK | Good 3-bet bluff hand; opponent less likely to have KK |
| Ah on 3-flush board | Blocks nut flush | Can bluff more (opponent can't have nut flush) |
| Board pair + you hold one | Blocks full houses/trips | Opponent less likely to have trips |
| Kd on Kh 9d 4d board | Blocks top pair + flush draw | Opponent range is weakened |

**Combo counting**:
```
Pocket pairs:  6 combos each (e.g., AA = AhAs, AhAd, AhAc, AsAd, AsAc, AdAc)
  If you hold Ah: AA = 3 combos (As-Ad, As-Ac, Ad-Ac)

Suited hands:  4 combos each (AKs = AhKh, AsKs, AdKd, AcKc)
  If you hold Ah: AKs = 3 combos (only AsKs, AdKd, AcKc)

Offsuit hands: 12 combos each (AKo = 16 total - 4 suited = 12)
  If you hold Ah: AKo = 9 combos (remove 3 that include Ah)
```

---

## 5. Bet Sizing Theory

### 5.1 Geometric Bet Sizing

**Already implemented**: `range_equity.py` has `geometric_bet_fraction()`.

The geometric bet size is the single pot fraction that, bet on every remaining
street, gets exactly all-in on the last street.

```python
def geometric_bet_fraction(pot, stack, streets_remaining):
    """
    Returns fraction of pot to bet each street to get all-in by river.

    Formula: fraction = 0.5 * ((pot + 2*stack) / pot)^(1/streets) - 0.5
    """
    if streets_remaining <= 0 or pot <= 0 or stack <= 0:
        return 0.0
    growth = (pot + 2 * stack) / pot
    return max(0.0, 0.5 * (growth ** (1.0 / streets_remaining) - 1))
```

Examples (100BB effective, 6.5BB pot on flop, 93.5BB behind):

| Streets Left | Geometric Size | As % of Pot |
|-------------|---------------|-------------|
| 3 (flop)    | ~75% pot      | Bet 4.9BB into 6.5BB |
| 2 (turn)    | ~110% pot     | Bet ~18BB into ~16BB |
| 1 (river)   | ~200% pot     | Bet ~100BB into ~52BB |

### 5.2 When to Use Each Bet Size

| Sizing | When to Use | Range Type |
|--------|-------------|-----------|
| 25-33% pot | Dry boards, high c-bet frequency, range bets | Merged/linear |
| 50% pot | Medium-texture boards, thin value, standard spots | Slightly merged |
| 66-75% pot | Wet boards, protecting equity, standard value | Balanced polar |
| 100% pot | Turn barrels, building pot for river shove | Polarized |
| 125-200% pot (overbet) | River with nut advantage, no opponent nutted hands | Highly polarized |

### 5.3 Nut Advantage and Sizing

**Nut advantage**: When your range contains more nutted hands than opponent's.

```
High nut advantage (you have nuts, they don't):
  -> Bet BIG (75-200% pot)
  -> Opponent can't raise effectively
  -> Extract maximum value

Low nut advantage (both ranges connect):
  -> Bet SMALL (25-50% pot)
  -> More hands can bet profitably
  -> Higher frequency makes up for smaller size

No nut advantage (opponent has nuts, you don't):
  -> CHECK frequently
  -> Use small blocking bets occasionally
  -> Avoid building the pot
```

### 5.4 Polarized vs Merged Ranges

**Polarized range** (nuts + air):
- Use large bet sizes (66%+ pot)
- Bluff-to-value ratio determined by pot odds you give opponent
- Example: Bet pot -> opponent needs 33% equity -> bet 2 value : 1 bluff

**Merged/Linear range** (strong to medium hands):
- Use small bet sizes (25-50% pot)
- Bet with high frequency
- All hands have some value/equity denial purpose

**Key formula for bluff-to-value ratio**:
```python
def bluff_to_value_ratio(bet_size_fraction):
    """
    Given bet size as fraction of pot, return how many bluffs per value bet.
    Based on: opponent must be indifferent to calling.

    bet_size_fraction: e.g., 0.75 for 75% pot bet
    """
    # Pot odds opponent gets
    odds = bet_size_fraction / (1 + bet_size_fraction)
    # Bluffs per value bet
    return odds / (1 - odds)

# Examples:
# 33% pot bet -> 0.25 bluffs per value bet (4:1 value heavy)
# 50% pot bet -> 0.33 bluffs per value bet (3:1)
# 66% pot bet -> 0.40 bluffs per value bet (2.5:1)
# 75% pot bet -> 0.43 bluffs per value bet (2.3:1)
# 100% pot bet -> 0.50 bluffs per value bet (2:1)
# 200% pot bet -> 0.67 bluffs per value bet (1.5:1)
```

### 5.5 Street-by-Street Sizing Heuristic

```
FLOP:
  - Small (25-40% pot) with high frequency on dry boards
  - Medium (50-66% pot) on wet boards, lower frequency
  - Solvers rarely use large flop bets except on very dynamic boards

TURN:
  - Larger than flop (66-80% pot)
  - Polarize: only bet strong hands and bluffs
  - Check medium-strength hands
  - Set up river geometric sizing

RIVER:
  - Polarized: either bet big (75%+ pot) or check
  - Overbet when you have nut advantage
  - Value bet size = same as bluff size (balance)
```

---

## 6. EV Calculations

### 6.1 Basic EV Formulas

```python
def ev_call(equity, pot, call_amount):
    """EV of calling a bet."""
    return equity * (pot + call_amount) - (1 - equity) * call_amount

def ev_fold():
    """EV of folding is always 0 (you give up your investment)."""
    return 0

def ev_raise(fold_equity, equity_when_called, pot, raise_amount, call_amount):
    """EV of raising, considering fold equity."""
    # Case 1: Opponent folds
    ev_fold_part = fold_equity * pot

    # Case 2: Opponent calls
    new_pot = pot + raise_amount + call_amount  # Total pot if called
    ev_call_part = (1 - fold_equity) * (
        equity_when_called * new_pot - (1 - equity_when_called) * raise_amount
    )

    return ev_fold_part + ev_call_part
```

### 6.2 Fold Equity

```python
def fold_equity(opponent_fold_pct, pot):
    """EV gained purely from opponent folding."""
    return opponent_fold_pct * pot
```

Estimated fold frequencies by opponent type:

| Opponent Type | Fold to C-bet (flop) | Fold to Turn Barrel | Fold to River Bet |
|--------------|---------------------|--------------------|--------------------|
| Nit          | 60-70% | 55-65% | 50-60% |
| TAG          | 45-55% | 50-60% | 45-55% |
| LAG          | 35-45% | 40-50% | 35-45% |
| Fish passive | 25-35% | 30-40% | 25-35% |
| Fish aggro   | 30-40% | 35-45% | 30-40% |
| Maniac       | 20-30% | 25-35% | 20-30% |

### 6.3 Implied Odds

```python
def effective_odds_with_implied(call_amount, pot, expected_future_winnings):
    """
    Implied pot odds: what you effectively need to call
    considering future bets you'll win when you hit.
    """
    total_potential = pot + call_amount + expected_future_winnings
    return call_amount / total_potential

# Example: Pot=100, call=50, expect to win 200 more if you hit
# Regular pot odds: 50/150 = 33.3%
# Implied odds: 50/350 = 14.3% (much better!)
```

**When implied odds matter most**:
- Drawing to flushes/straights on flop/turn
- Deep stacks (high SPR) with speculative hands
- Opponent is aggressive/will pay off big hands
- You have position (can extract more value)

**When implied odds are minimal**:
- Short stacks (no more money to win)
- Opponent is tight/will fold to aggression
- You are out of position
- Obvious draw completes (opponent will check behind)

### 6.4 Minimum Defense Frequency (MDF)

MDF tells you how often you must call/raise to prevent opponent from profitably
bluffing with any two cards.

```python
def mdf(bet_size_fraction):
    """
    Minimum Defense Frequency.

    bet_size_fraction: bet as fraction of pot (e.g., 0.75 for 75% pot)
    Returns: fraction of range you must continue with (call or raise)
    """
    return 1.0 / (1.0 + bet_size_fraction)
```

| Bet Size | MDF (must defend) | Can Fold |
|----------|------------------|----------|
| 25% pot  | 80% | 20% |
| 33% pot  | 75% | 25% |
| 50% pot  | 67% | 33% |
| 66% pot  | 60% | 40% |
| 75% pot  | 57% | 43% |
| 100% pot | 50% | 50% |
| 150% pot | 40% | 60% |
| 200% pot | 33% | 67% |

**Alpha (break-even bluff frequency)**:
```python
def alpha(bet_size_fraction):
    """How often opponent must fold for a pure bluff (0% equity) to break even."""
    return bet_size_fraction / (1.0 + bet_size_fraction)

# 50% pot bet: opponent must fold 33% for bluff to break even
# 100% pot bet: opponent must fold 50%
# 200% pot bet: opponent must fold 67%
```

---

## 7. Tournament-Specific Strategy

### 7.1 ICM Basics

**Chip value in tournaments is non-linear**:
- Doubling your chips does NOT double your equity
- Losing all chips = eliminated (catastrophic)
- First chip is most valuable, each additional chip worth slightly less

```python
def icm_equity(stacks, payouts):
    """
    Independent Chip Model: converts chip stacks to $ equity.
    Uses Malmuth-Harville method (recursive probability).

    stacks: [5000, 3000, 2000]  # chip counts
    payouts: [50, 30, 20]       # prize pool distribution

    Returns: [equity_player1, equity_player2, equity_player3]
    """
    total = sum(stacks)
    n = len(stacks)
    equities = [0.0] * n

    def _prob_finish(player, place, remaining, total_remaining):
        if place == 0:
            return remaining[player] / total_remaining
        # Probability of finishing exactly in this place
        # (recursive over all possible elimination orders)
        # ... (standard ICM recursion)
        pass

    # First place probability = chip_count / total_chips
    for i in range(n):
        for place in range(min(n, len(payouts))):
            # ... recursion
            pass

    return equities
```

### 7.2 Bubble Strategy Adjustments

On the money bubble:

| Your Stack | Strategy Adjustment |
|-----------|-------------------|
| Big stack (>40% avg) | Widen aggression range by 10-20%. Put pressure on medium stacks. |
| Medium stack (60-120% avg) | TIGHTEN significantly (20-40%). Avoid coinflips. Fold marginal spots. |
| Short stack (<40% avg) | Play push/fold. Shove wider than Nash from late position. You need chips. |
| Very short (<10BB) | Desperate shove range. Any ace, any pair, any two broadway from BTN/SB. |

### 7.3 Spin & Go / Spin & Gold Strategy

Format: 3-handed, typically winner-take-all (low multipliers), hyper-turbo.

**Key differences from standard play**:
1. **Winner-take-all = ChipEV = $EV**: No ICM in low-multiplier games
2. **Shallow stacks**: Start at 25BB, blinds rise fast
3. **3-handed**: Position is critical, ranges are wider than 6-max
4. **Fast transitions**: Go from open-raise to push/fold within 3-5 levels

#### Starting strategy (25BB, 3-handed)

| Position | Open Range | 3-bet Range |
|----------|-----------|------------|
| BTN | ~55-60% of hands | AA-TT, AQs+, AKo (shove: TT-77, AJ, KQ) |
| SB | ~40-50% of hands | "3-bet or fold" preferred. Limping allowed vs aggressive BB. |
| BB | Defend ~50-60% vs BTN open | 3-bet wide vs SB open (15-20%) |

#### Transition to push/fold (10BB)

At 10BB, go pure push/fold:
- BTN: ~35-40% shove
- SB: ~50-60% shove (heads up vs BB)
- BB: Call shoves with Nash calling range

#### SB vs BB heads-up (when 3rd player busts)

When heads-up, ranges widen dramatically:
- SB at 10BB: shove ~75% of hands
- BB: call shoves per Nash HU chart (~40-50% at 10BB)

#### Key Spin & Go principles

1. **Aggression wins**: The format rewards stealing blinds and antes
2. **Position is everything**: BTN open nearly 60% of hands 3-handed
3. **3-bet or fold from SB**: Don't flat call OOP -- 3-bet or fold
4. **Push/fold below 10BB**: No min-raising, no limping
5. **Chip lead = fold equity**: Use your stack to pressure shorter stacks
6. **Don't slow-play**: Extract value fast, stacks are too shallow for trapping

---

## 8. Key Preflop Hand Equity Matchups

Reference equities for common preflop scenarios:

| Matchup | Equity (approx) |
|---------|-----------------|
| AA vs KK | 82% - 18% |
| AA vs random hand | 85% - 15% |
| KK vs AKo | 70% - 30% |
| QQ vs AKo | 57% - 43% |
| JJ vs AKs | 54% - 46% |
| TT vs AKo | 57% - 43% |
| AKs vs 88 | 47% - 53% |
| AKo vs 88 | 45% - 55% |
| AKs vs AQs | 70% - 30% |
| KQs vs AJo | 47% - 53% |
| Overpair vs underpair | ~80% - 20% |
| Pair vs two overcards | ~53% - 47% |
| Pair vs one overcard | ~70% - 30% |
| Dominated hand (AK vs AJ) | ~73% - 27% |
| Suited connector vs random | ~42% - 58% |

---

## 9. Implementation Checklist

### Already in the codebase (range_equity.py):
- [x] Nash push/fold shove ranges (NASH_SHOVE_RANGES)
- [x] Nash call-vs-shove ranges (CALL_RANGES_VS_SHOVE)
- [x] RFI ranges by position (RFI_RANGES)
- [x] 3-bet ranges (THREE_BET_RANGES)
- [x] Player type ranges (PLAYER_TYPE_RANGES)
- [x] Geometric bet sizing (geometric_bet_fraction)
- [x] Board-texture-aware bet sizing (compute_bet_size_bb)
- [x] Preflop raise sizing (preflop_raise_size_bb)
- [x] Range equity calculation via eval7
- [x] Board-aware range filtering
- [x] Villain range estimation (estimate_villain_range)

### Needs implementation or improvement:
- [ ] Board wetness calculation (quantitative, not just dry/wet binary)
- [ ] MDF-based defense decisions (currently uses raw equity only)
- [ ] Implied odds calculation (adjust call EV for deep stacks)
- [ ] SPR-based commitment logic (adjust stack-off threshold)
- [ ] Blocker-aware bluffing (select bluff hands by blockers held)
- [ ] Check-raise frequency by board texture
- [ ] ICM equity calculator for bubble play
- [ ] Spin & Go specific adjustments (3-handed ranges, WTA mode)
- [ ] EV comparison engine (compute EV of each action, pick highest)
- [ ] Overbet sizing when holding nut advantage

---

## Sources

- [MyPokerCoaching Push Fold Charts](https://www.mypokercoaching.com/push-fold-chart/)
- [HoldemResources Nash Equilibrium](https://www.holdemresources.net/hune)
- [GamblingCalc Push/Fold Calculator](https://gamblingcalc.com/poker/push-fold-chart/)
- [Primedope Equilibrium Charts](https://www.primedope.com/equilibrium-pushbot-charts/)
- [Upswing Poker Push Fold Charts](https://upswingpoker.com/push-fold-tournament-strategy-charts/)
- [FreeBetRange 6-Max Preflop Charts](https://blog.freebetrange.com/article/preflop-charts-open-raise-in-6-max-poker-cash-games)
- [BBZ Poker GTO Charts](https://bbzpoker.com/poker-charts/)
- [GTO Wizard Preflop Range Morphology](https://blog.gtowizard.com/preflop-range-morphology/)
- [GTO Wizard C-Bet Sizing Mechanics](https://blog.gtowizard.com/the-mechanics-of-c-bet-sizing/)
- [GTO Wizard Pot Geometry](https://blog.gtowizard.com/pot-geometry/)
- [GTO Wizard MDF & Alpha](https://blog.gtowizard.com/mdf-alpha/)
- [GTO Wizard Stack-to-Pot Ratio](https://blog.gtowizard.com/stack-to-pot-ratio/)
- [GTO Wizard Turn Check-Raise Heuristics](https://blog.gtowizard.com/turn-check-raise-heuristics/)
- [Upswing Poker 3-Bet Strategy](https://upswingpoker.com/3-bet-strategy-aggressive-preflop/)
- [Upswing Poker 6-Max Strategy](https://upswingpoker.com/6-handed-max-poker-strategy/)
- [Upswing Poker Geometric Bet Sizing](https://upswingpoker.com/geometric-bet-sizing/)
- [SplitSuit EV Formula](https://www.splitsuit.com/simple-poker-expected-value-formula)
- [SplitSuit SPR Strategy](https://www.splitsuit.com/spr-poker-strategy)
- [SplitSuit 3-Bet Ranges](https://www.splitsuit.com/understanding-3-bet-ranges)
- [MicroGrinder 6-Max Pre-Flop Ranges](https://microgrinder.com/poker-strategy-articles/6-max-pre-flop-ranges/)
- [888poker ICM Guide](https://www.888poker.com/magazine/strategy/poker-tournament/icm-in-poker-tournaments)
- [BBZ Poker ICM Bubble Strategy](https://bbzpoker.com/extreme-icm-bubble-strategy/)
- [GGPoker Spin & Gold Strategy](https://ggpoker.com/blog/ggpoker-spin-gold-strategy/)
- [PokerStrategy Spin & Go Facts](https://www.pokerstrategy.com/strategy/sit-and-go/spin-n-go-facts-strategy/)
- [MyPokerCoaching Spin and Go Strategy](https://www.mypokercoaching.com/spin-and-go-strategy-jackpot-sng/)
- [CardFight GTO Strategy Guide](https://www.cardfight.com/gto_strategy.html)
- [PokerNerve Post-Flop Bet Sizing Guide](https://pokernerve.com/how-to-find-the-right-bet-size-post-flop-in-2022-the-3-step-guide/)
