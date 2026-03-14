# Poker Tournament Format Strategy Guide

Research compiled from GTO Wizard, Upswing Poker, BBZ Poker, PokerNews, and other sources.
Last updated: 2026-03-14.

---

## Table of Contents

1. [Bounty/Knockout Tournaments](#1-bountyknockout-tournaments)
2. [9-Handed vs 6-Handed](#2-9-handed-vs-6-handed)
3. [3-Handed (Spin & Go)](#3-3-handed-spin--go)
4. [Hyper Turbo Tournaments](#4-hyper-turbo-tournaments)
5. [Deep Stack Tournaments](#5-deep-stack-tournaments)
6. [Testing & Verification Framework](#6-testing--verification-framework)

---

## 1. Bounty/Knockout Tournaments

### Format Types

| Format | How Bounty Works | Instant Payout |
|--------|-----------------|----------------|
| Standard KO (SKO) | Fixed bounty per player, full bounty paid on elimination | 100% of bounty |
| Progressive KO (PKO) | Bounty grows as you eliminate players | 50% paid, 50% added to your bounty |
| Mystery Bounty | Random bounty revealed on elimination (0.5x to 1000x buy-in) | 100% of drawn bounty |

### GGPoker Bounty Hunters (PKO)

On GGPoker, buy-in is split roughly 50/50 between regular prize pool and bounty pool. When you eliminate someone:
- You receive **50% of their bounty instantly** (credited to your account)
- The other **50% is added to your own bounty**, making you a bigger target

Example: Eliminate a player with $50 bounty -> $25 cash instantly, $25 added to your head.

### The Math: Bounty-to-Chip Conversion

**Core Formula (BBZ Poker):**

```
Bounty_in_Chips = (Immediate_Payout / Total_Entry_Fee_excl_rake) x Starting_Chips
```

**Example:** $109 PKO ($100 entry, $50 bounty pool per player):
- Immediate bounty payout = $25 (half of opponent's $50 bounty)
- Chip value = (25 / 100) x 10,000 = **2,500 chips**

### Bounty Power Formula (GTO Wizard)

```
Bounty_Power = Total_Chips_in_Play / (Remaining_Bounty_Pool + Remaining_Prize_Pool)
```

This converts dollar bounty values to big blind equivalents:

```
Bounty_in_BB = Opponent_Bounty_$ x Bounty_Power
```

**Example from GTO Wizard (70% field remaining):**
- Bounty Power = 0.191
- $50 bounty = 50 x 0.191 = **9.55 BB** added to pot

### How Bounties Change Pot Odds

**Without bounty:**
- To call: 12 BB, pot after calling: 27.5 BB
- Required equity: 12 / 27.5 = **43.6%**

**With $50 bounty (9.55 BB value):**
- Effective pot: 27.5 + 9.55 = 37.05 BB
- Required equity: 12 / 37.05 = **32.4%**

**Result:** Equity threshold drops by ~11 percentage points. Hands like A4o, A7o, Q7s, and 54s become profitable calls.

### Equity Drop by Format

From GTO Wizard Part 3 calculations:

| Format | Bounty % of Buy-in | Equity Drop | Equivalent Chip Bonus |
|--------|-------------------|-------------|----------------------|
| 25% SKO | 25% | ~6.25% | 2,500 chips (on 10k start) |
| 50% SKO | 50% | ~12.5% | 5,000 chips |
| 50% PKO | 25% (instant half) | ~6.25% | 2,500 chips |

### Risk Premium Changes

In PKO tournaments, risk premiums can go **negative** for covering stacks, meaning you are incentivized to gamble:

| Scenario | Classic MTT Risk Premium | PKO Risk Premium |
|----------|-------------------------|-----------------|
| Standard spot | +1.4% | +0.7% |
| SB vs BTN (covering) | Positive | **-4.6%** |
| SB vs BB (covering) | Positive | **-6.2%** |

Negative risk premium = winning the bounty helps you MORE than losing your chips hurts you.

### Calling Range Expansion (BBZ Poker data)

| Stage | Stack Depth | Classic MTT Call % | PKO Call % | Difference |
|-------|------------|-------------------|-----------|------------|
| Early (1000 players) | 100bb | 61.6% (BB defense) | 65.1% | +3.5% |
| Mid (50% field) | 35bb, LJ vs BTN AI | 26.8% | 36.3% | **+9.5%** |

### Implementable Rules for Bot

```python
def adjust_for_bounty(equity_required, opponent_bounty, bounty_power, my_stack_covers):
    """Adjust required equity when we cover opponent in PKO."""
    if not my_stack_covers:
        return equity_required  # No bounty adjustment if we don't cover

    bounty_bb = opponent_bounty * bounty_power
    # Add bounty value to effective pot
    # This reduces equity_required by roughly:
    #   reduction = bounty_bb / (pot + bounty_bb)
    return equity_required  # Apply the formula in pot odds calculation

# Simplified rule of thumb:
# - Early PKO: Call ~5% wider when covering opponent
# - Mid PKO: Call ~10% wider when covering opponent
# - When opponent's bounty > 15BB equivalent: call VERY wide (top 60-70%)
# - When NOT covering: play standard ranges (slight tightening)
```

### Key Strategic Rules

1. **Cover = Aggression.** When your stack covers opponents, play wider and more aggressively.
2. **Covered = Caution.** When opponents cover you, tighten up -- your bounty is at risk.
3. **Early stage:** Bounties are worth the most relative to blinds. Hunt aggressively.
4. **Late stage:** Bounties depreciate relative to blind size. Shift toward regular MTT play.
5. **Never risk tournament life for a small bounty.** The future bounty EV of staying alive matters.

---

## 2. 9-Handed vs 6-Handed

### Position Names (9-Handed)

```
Seat 1: UTG (Under the Gun)
Seat 2: UTG+1
Seat 3: UTG+2 / MP (Middle Position)
Seat 4: MP+1 / LJ (Lojack)
Seat 5: HJ (Hijack)
Seat 6: CO (Cutoff)
Seat 7: BTN (Button)
Seat 8: SB (Small Blind)
Seat 9: BB (Big Blind)
```

### Opening Range Percentages

**6-Max (100bb cash, GTO Wizard / BBZ):**

| Position | Open % | ~Combos |
|----------|--------|---------|
| UTG (LJ) | ~17% | 226 |
| UTG+1 (HJ) | ~19-21% | 260 |
| CO | ~27-28% | 370 |
| BTN | ~43-50% | 570-660 |
| SB | ~40-83%* | varies |

*SB range varies widely: raise-or-fold strategy in tournaments can be very wide.

**9-Max (100bb cash, compiled from multiple sources):**

| Position | Open % | Notes |
|----------|--------|-------|
| UTG | ~6-10% | 22+, ATs+, KQs, AQo+ (tightest) |
| UTG+1 | ~10-11% | Add A9s, KJs, QJs |
| UTG+2 | ~12-13% | Add 88+, suited broadways |
| MP (LJ) | ~14-16% | Add suited connectors T9s+ |
| HJ | ~18-20% | Similar to 6-max UTG |
| CO | ~25-28% | Similar to 6-max CO |
| BTN | ~40-50% | Wide stealing range |
| SB | ~40-50% | Raise or fold vs BB |

**Key difference:** UTG in 9-max (~8%) is roughly HALF the range of UTG in 6-max (~17%). The 3 extra positions compress all early/middle ranges significantly.

### Specific Hand Adjustments (9-Max vs 6-Max)

| Hand | 6-Max UTG | 9-Max UTG | 9-Max MP | 9-Max CO |
|------|-----------|-----------|----------|----------|
| 77 | Open | Open | Open | Open |
| 66 | Open | Fold/Open | Open | Open |
| 55 | Marginal | Fold | Fold/Open | Open |
| AJo | Open | Fold | Open | Open |
| KQo | Open | Fold | Marginal | Open |
| T9s | Open | Fold | Fold | Open |
| 87s | Fold | Fold | Fold | Open |
| A5s | Open | Open | Open | Open |

### 3-Bet Ranges (9-Max vs 6-Max)

In 9-max, 3-bet ranges are tighter because opener ranges are tighter:
- **vs UTG open in 9-max:** 3-bet only QQ+, AKs (value heavy, ~3-4%)
- **vs UTG open in 6-max:** 3-bet QQ+, AKs, some suited Ax bluffs (~5-6%)
- **vs CO open:** Similar in both formats (~8-10%)
- **vs BTN open:** Similar in both formats (~10-12%)

### Postflop Differences

1. **Multiway pots more frequent** in 9-max (more callers between opener and blinds)
2. **Stronger ranges on average** -> bigger pots tend to be nut-vs-nut
3. **Less bluffing** from early positions because ranges are face-up tight
4. **Position premium increases** -> BTN and CO are even more valuable

### Implementable Rules

```python
# 9-max position adjustment multiplier for opening ranges
NINE_MAX_OPEN_MULTIPLIER = {
    'UTG':   0.50,  # Half of 6-max UTG range
    'UTG1':  0.55,
    'UTG2':  0.65,
    'MP':    0.80,
    'HJ':    0.95,  # Nearly identical to 6-max UTG
    'CO':    1.00,  # Same as 6-max CO
    'BTN':   1.00,  # Same as 6-max BTN
    'SB':    1.00,
}

def get_open_range_pct(position, num_players):
    """Return opening range % based on position and table size."""
    if num_players <= 6:
        base_ranges = {'UTG': 17, 'HJ': 21, 'CO': 28, 'BTN': 45, 'SB': 45}
    else:  # 7-9 players
        base_ranges = {
            'UTG': 8, 'UTG1': 10, 'UTG2': 13,
            'MP': 15, 'HJ': 19, 'CO': 27,
            'BTN': 45, 'SB': 45
        }
    return base_ranges.get(position, 15)
```

---

## 3. 3-Handed (Spin & Go / Spin & Gold)

### Format Overview

- **Starting stack:** 25bb (standard) or 15bb (Flash/Nitro)
- **Blind levels:** 2-3 minutes (standard) or 1 minute (Flash)
- **Structure:** 3 players, winner-take-all for >95% of games
- **Multiplier distribution:** Most games are 2x (winner takes all)

### Multiplier and ICM Impact

| Multiplier | Payout Structure | ICM Applies? | Strategy Impact |
|------------|-----------------|--------------|-----------------|
| 2x | Winner takes all | **No** (ChipEV = $EV) | Play to win, no ICM |
| 3x-5x | Winner takes all | **No** | Same as 2x |
| 10x+ | 2nd and 3rd place pay | **Yes** | Avoid marginal all-ins |
| 100x+ | Significant 2nd/3rd prizes | **Heavy ICM** | Survival matters, tighten calling |

**Critical insight:** In 2x games (the vast majority), there is NO ICM. Play pure chip-EV poker. This is identical to a cash game in terms of decision theory.

### BTN Strategy (3-Handed, 25bb)

**Open range: ~35-50% of hands** with a min-raise (2bb).

At 25bb, BTN strategy is raise-or-fold only (no limping). The range includes:
- All pairs
- All suited aces
- Most suited kings and queens
- Suited connectors down to about 54s
- Broadway offsuit hands (ATo+, KJo+, QJo)
- Some suited gappers (T8s, 97s, 86s)

**At 18bb and below:** Open-shoving becomes the preferred action with certain hands (medium-strength hands that don't play well postflop, like K7o, Q9o).

### SB Strategy (3-Handed, vs BTN Open)

**The SB almost never flats.** Strategy is almost entirely 3-bet or fold.

- **3-bet shove range (at 15-25bb):** Wide -- includes many Ax hands, pairs, suited connectors
- **3-bet to ~6bb (non-all-in):** Strong hands that benefit from postflop play (AA, KK, QQ, AKs, AQs)
- **Flat call:** Rarely, only with hands that play well postflop and are too strong to fold but don't want to bloat the pot OOP

**SB 3-bet frequency vs BTN open:** Approximately 20-30% of hands

### BB Strategy (3-Handed)

**BB defense vs SB raise:** Significantly tighter than in cash games because of positional disadvantage and tournament dynamics.

- **vs SB open:** Defend ~40-50% (call or 3-bet)
- **vs BTN open (after SB folds):** Defend ~55-65%

### Heads-Up Phase (When One Player Busts)

When it goes heads-up, ranges widen dramatically:
- **SB/BTN open: ~70-80%** of hands (raise or fold, almost no limping at 15bb+)
- **BB defense: ~55-65%** of hands
- **SB open-shove below 10bb:** ~60-80% of hands depending on exact stack

### Push/Fold Thresholds (3-Handed)

| Stack (BB) | BTN Shove % | SB Shove % (folded to) | BB Call vs BTN % | BB Call vs SB % |
|-----------|-------------|----------------------|-----------------|-----------------|
| 15bb | ~25-30% | ~40-50% | ~20-25% | ~25-30% |
| 10bb | ~40-50% | ~55-65% | ~30-35% | ~35-40% |
| 8bb | ~50-60% | ~65-75% | ~35-40% | ~40-45% |
| 6bb | ~65-75% | ~75-85% | ~40-50% | ~45-55% |
| 4bb | ~80-90% | ~85-95% | ~55-65% | ~60-70% |

### Nash Equilibrium HU Push/Fold (Key Hands)

From Primedope Nash charts, maximum stack size (in BB) for profitable shove:

| Hand | SB Shove (BB) | Notes |
|------|--------------|-------|
| AA-TT | 50+ | Always shove |
| 99-77 | 20-35 | Shove medium stacks |
| 66-22 | 8-15 | Shove short stacks only |
| AKs-AQs | 50+ | Always shove |
| AJs-ATs | 25-40 | Shove most stacks |
| A9s-A2s | 15-30 | Shove when short-medium |
| KQs | 30+ | Strong shove |
| 76s | ~29 | Surprisingly wide |
| AKo | 50+ | Always shove |
| AQo-AJo | 30-50 | Shove most stacks |
| KQo | 20-25 | Medium depth shove |
| K6o | ~15 | Short stack only |

**BB Call vs SB Shove (10BB effective):**
Call with approximately top 45% of hands: all pairs, all suited aces, most offsuit aces, broadway hands, suited kings, some offsuit kings, high suited connectors.

### Implementable Rules

```python
def spin_and_go_btn_action(hand, stack_bb, num_players):
    """Decide BTN action in 3-handed Spin & Go."""
    if num_players == 3:
        if stack_bb >= 18:
            # Min-raise with top ~45% of hands, fold rest
            return 'raise' if hand_percentile <= 45 else 'fold'
        elif stack_bb >= 10:
            # Mix of min-raise and shove
            if hand_is_premium(hand):
                return 'raise'  # Strong hands: raise for value
            elif hand_percentile <= 35:
                return 'shove'  # Medium hands: shove for fold equity
            else:
                return 'fold'
        else:  # < 10bb
            # Pure push/fold
            return 'shove' if hand_percentile <= 50 + (10 - stack_bb) * 5 else 'fold'
    elif num_players == 2:
        # Heads-up: much wider
        if stack_bb >= 15:
            return 'raise' if hand_percentile <= 70 else 'fold'
        else:
            return 'shove' if hand_percentile <= 60 + (15 - stack_bb) * 3 else 'fold'

def spin_and_go_sb_vs_btn(hand, stack_bb):
    """SB response to BTN open in 3-handed."""
    # Almost never flat. 3-bet or fold.
    if stack_bb <= 12:
        # Shove or fold
        return 'shove' if hand_percentile <= 25 else 'fold'
    else:
        # 3-bet to ~6bb or fold
        if hand_is_premium(hand):  # Top ~8% (TT+, AQs+, AKo)
            return '3bet'
        elif hand_percentile <= 22:
            return '3bet'  # Wider 3-bet bluffs (suited Ax, small pairs)
        else:
            return 'fold'
```

---

## 4. Hyper Turbo Tournaments

### Structure

| Parameter | Turbo | Hyper Turbo |
|-----------|-------|-------------|
| Starting stack | 100-250bb | 15-25bb |
| Blind level duration | ~5 minutes | ~3 minutes |
| Push/fold mode | After several levels | Almost immediately |
| Skill edge | Moderate | Lower (higher variance) |
| Typical format | MTT, SNG | SNG, Spin & Go |

### Stage-by-Stage Strategy

**Level 1-2 (25bb -> 15bb):**
- Play tight from early position
- Steal blinds aggressively from BTN/CO with ~35-40% of hands
- Avoid calling 3-bets without premium holdings
- Do NOT slow-play -- fast play strong hands for value
- Set mining is marginal (need ~15:1 implied odds, rarely available)

**Level 3-4 (15bb -> 8bb):**
- Transition to push/fold from most positions
- Open-shove from BTN with ~40% of hands
- Open-shove from SB with ~50% of hands
- Only min-raise with very strong hands (AA, KK) to induce
- Defend BB wider than normal -- you're getting good odds

**Level 5+ (<8bb):**
- Pure push/fold
- Shove ANY two cards from SB at 3-4bb
- Call shoves very wide in BB (getting ~2:1)
- First-in fold equity is everything

### Key Numbers

- **Below 10bb:** Pure push/fold territory
- **10-15bb:** Raise/fold from late position, push/fold from EP
- **15-20bb:** Standard play but avoid deep postflop decisions
- **20-25bb:** Can play normally but keep pots small

### Calling Rule of Thumb

When facing a shove and holding ~10bb:
- Call with approximately **30% of the hands you expect villain to shove**
- If villain shoves 60% from BTN, you call with top ~20% from BB
- If villain shoves 40% from CO, you call with top ~12% from BB

### ICM in Hyper Turbos

ICM matters MORE in hyper turbos because:
1. Stacks are shallow, so every all-in risks elimination
2. Pay jumps come fast (quick to reach the money)
3. On the bubble: tighten significantly against big stacks
4. With a big stack on bubble: apply maximum pressure on medium stacks

### Implementable Rules

```python
def hyper_turbo_strategy(hand, stack_bb, position, phase):
    """
    Hyper turbo decision framework.
    phase: 'early' (>15bb), 'mid' (8-15bb), 'late' (<8bb)
    """
    if phase == 'late' or stack_bb < 8:
        # Pure push/fold
        shove_threshold = get_shove_threshold(position, stack_bb)
        return 'shove' if hand_percentile <= shove_threshold else 'fold'

    elif phase == 'mid' or stack_bb < 15:
        if position in ('BTN', 'CO', 'SB'):
            # Aggressive stealing
            if hand_percentile <= 40:
                return 'shove' if stack_bb < 12 else 'raise'
            return 'fold'
        else:
            # Tight from EP
            return 'raise' if hand_percentile <= 12 else 'fold'

    else:  # early, >15bb
        # Standard but tight opening
        ranges = {'UTG': 12, 'MP': 15, 'CO': 25, 'BTN': 40, 'SB': 35}
        threshold = ranges.get(position, 15)
        return 'raise' if hand_percentile <= threshold else 'fold'

def get_shove_threshold(position, stack_bb):
    """Push/fold shove threshold by position and stack."""
    # Base percentages at 8bb
    base = {'UTG': 15, 'MP': 20, 'CO': 35, 'BTN': 50, 'SB': 60, 'BB': 0}
    pct = base.get(position, 20)
    # Wider as stack shrinks
    if stack_bb <= 4:
        pct = min(pct * 1.8, 95)
    elif stack_bb <= 6:
        pct = min(pct * 1.4, 85)
    return pct
```

---

## 5. Deep Stack Tournaments

### Structure

- **Starting stack:** 150-300bb (typically 200bb)
- **Blind levels:** 30-60 minutes
- **Character:** Postflop skill matters most; preflop is relatively cheap

### Key Strategic Differences from Standard (50-100bb)

| Aspect | Standard (50-100bb) | Deep (200bb+) |
|--------|---------------------|---------------|
| Preflop importance | High | Low (cheap relative to stacks) |
| Postflop importance | High | **Very high** |
| Set mining | Sometimes | **Always** (huge implied odds) |
| Suited connectors | Position-dependent | **Very valuable** in position |
| Top pair strength | Often good for stacks | **Dangerous** (reverse implied odds) |
| Position importance | Important | **Critical** |
| 3-bet pot SPR | ~2-4 | ~5-8 (much more postflop play) |

### Opening Range Adjustments

**Hands that GAIN value deep:**
- Small/medium pairs (22-88): Set mining is hugely profitable (need ~15:1, easily available at 200bb)
- Suited connectors (54s-T9s): Can make straights/flushes for massive pots
- Suited aces (A2s-A5s): Nut flush draws play perfectly deep
- Suited one-gappers (T8s, 97s, 86s): Similar to suited connectors

**Hands that LOSE value deep:**
- AKo, AQo: Makes top pair but hard to play 200bb pot with one pair
- KJo, QJo: Dominated often, reverse implied odds
- Weak broadways OOP: Get into trouble with marginal made hands

### Position-Specific Deep Stack Ranges

**In Position (CO/BTN):** Open significantly wider than standard
- Add all suited connectors down to 43s
- Add all suited one-gappers
- All pairs
- Suited K/Q/J hands
- Open range: ~35-55% from BTN

**Out of Position (UTG/EP):** Only slightly wider than standard
- Add small pairs (if they fold to 3-bet, this is marginal)
- Suited connectors from MP+ only
- Open range: ~15-20% from UTG (not much wider than normal)

### Postflop Adjustments

1. **Pot control is paramount.** Don't build huge pots with one pair.
2. **Bet sizing can be larger** -- more room for multi-street betting.
3. **Check-raise more** -- deep stacks allow for more complex lines.
4. **Slow-play strong hands** -- opponents can pay off big later.
5. **Bluff more** -- deeper stacks mean more fold equity and more fear.

### Implementable Rules

```python
def deep_stack_range_adjustment(hand, stack_bb, position):
    """Adjust ranges for deep stacks (>150bb)."""
    depth_bonus = 0  # Extra % to add to opening range

    if stack_bb >= 200:
        if hand.is_pocket_pair():
            depth_bonus = 5  # Always open pairs for set value
        elif hand.is_suited_connector():
            if position in ('CO', 'BTN', 'SB'):
                depth_bonus = 10  # Very profitable IP
            else:
                depth_bonus = 3  # Marginal OOP
        elif hand.is_suited_ace():
            depth_bonus = 5  # Nut flush draw potential
        elif hand.is_offsuit_broadway():
            depth_bonus = -3  # REDUCE -- reverse implied odds

    return depth_bonus

def deep_stack_postflop_adjustment(hand_strength, stack_bb, pot_size):
    """Deep stack postflop bet sizing guidance."""
    spr = stack_bb / max(pot_size, 1)  # Stack to pot ratio

    if spr > 10:
        # Very deep relative to pot. Pot control with medium hands.
        if hand_strength == 'top_pair':
            return 'check_or_small_bet'  # Don't build pot with TPTK
        elif hand_strength in ('set', 'flush', 'straight'):
            return 'bet_for_value'  # Build pot with monsters
        elif hand_strength == 'draw':
            return 'semi_bluff'  # Use fold equity
    elif spr > 4:
        # Standard play
        return 'standard_cbet'
    else:
        # Committed -- standard strategy applies
        return 'standard'
```

---

## 6. Testing & Verification Framework

### eval7: Python Equity Calculator

**Install:** `pip install eval7`

**Core API:**

```python
import eval7

# Hand evaluation
hand = [eval7.Card(s) for s in ('As', 'Kh', 'Qd', 'Jc', 'Ts', '2h', '3d')]
score = eval7.evaluate(hand)
ranking = eval7.handtype(score)  # 'Straight'

# Hand range parsing (PokerStove notation)
from eval7 import HandRange
villains = HandRange("TT+, AQs+, AKo")  # 144 combos
wide = HandRange("22+, A2s+, KTs+, QTs+, JTs, T9s, 98s, 87s, 76s, ATo+, KJo+")

# Equity calculations
equity = eval7.py_hand_vs_range_exact(
    [eval7.Card('Ah'), eval7.Card('Kd')],  # Our hand
    HandRange("QQ+, AKs"),                   # Villain range
    [],                                       # Board cards
    100000                                    # Iterations (Monte Carlo)
)
```

### Verification Test Cases

Use these to verify the bot makes correct decisions:

```python
# Test 1: Premium hands never fold preflop
assert decide('AA', preflop=True) != 'fold'
assert decide('KK', preflop=True) != 'fold'
assert decide('AKs', preflop=True) != 'fold'

# Test 2: Pot odds calls
# Getting 3:1 odds, need 25% equity. ATo vs random has ~58% equity.
assert decide('ATo', pot=300, to_call=100, villain_range='random') == 'call'

# Test 3: Bounty adjustment
# In PKO, 10bb bounty means we need ~10% less equity to call
assert pko_decide('Q7s', pot=200, to_call=100, bounty_bb=10) == 'call'  # Would fold without bounty

# Test 4: Push/fold at 8bb
assert decide('A5s', stack_bb=8, position='BTN') == 'shove'
assert decide('72o', stack_bb=8, position='UTG') == 'fold'

# Test 5: Deep stack set mining
assert decide('44', stack_bb=200, position='BTN', facing='raise') == 'call'  # Set mine
```

### Other Tools for Verification

| Tool | Purpose | Free? |
|------|---------|-------|
| eval7 (Python) | Equity calculation, hand evaluation | Yes |
| PioSOLVER | GTO solver (compute optimal strategies) | No (~$250) |
| GTO Wizard | Pre-solved GTO solutions, training | No (subscription) |
| ICMizer | ICM/push-fold calculations | Free tier available |
| HoldemResources Calculator | Nash equilibrium push/fold | Free tier available |
| PokerStove | Basic equity calculator | Yes (old but works) |
| Equilab | Range equity calculator | Yes |

### Automated Testing Pipeline

```python
import eval7

def verify_decision(hero_hand, villain_range, board, pot, to_call, decision):
    """Verify a bot decision is +EV."""
    hero = [eval7.Card(c) for c in hero_hand]
    board_cards = [eval7.Card(c) for c in board] if board else []

    equity = eval7.py_hand_vs_range_monte_carlo(
        hero,
        eval7.HandRange(villain_range),
        board_cards,
        10000  # iterations
    )

    pot_odds = to_call / (pot + to_call)

    if decision == 'call':
        assert equity >= pot_odds, f"Bad call: {equity:.1%} equity < {pot_odds:.1%} pot odds"
    elif decision == 'fold':
        assert equity < pot_odds, f"Bad fold: {equity:.1%} equity >= {pot_odds:.1%} pot odds"

    return equity, pot_odds

# Run verification
verify_decision(['Ah', 'Kd'], 'QQ+, AKs', ['Qs', 'Jh', '2c'], 150, 50, 'call')
```

---

## Summary: Key Differences by Format

| Factor | 6-Max Cash | 9-Max | Spin & Go (3h) | PKO | Hyper Turbo | Deep Stack |
|--------|-----------|-------|----------------|-----|-------------|------------|
| UTG open % | ~17% | ~8-10% | N/A | Same + bounty adj | ~12% | ~18% |
| BTN open % | ~45% | ~45% | ~35-50% | Same + bounty adj | ~40% | ~50% |
| ICM applies | No | Sometimes | Rarely (WTA) | Yes + bounty | Yes (heavy) | Rarely early |
| Call shove equity needed | Standard | Standard | Standard (WTA) | **-5 to -12%** | Standard + ICM | Standard |
| Key skill | Postflop | Tight EP play | Push/fold | Bounty math | Push/fold | Postflop, pot control |
| Speculative hands | Normal | Tighter EP | Rarely (shallow) | Normal | Never (shallow) | **Very valuable** |
| Position value | High | Very high | Extreme | High | Extreme | Critical |

---

## Sources

### Bounty/PKO Strategy
- [GTO Wizard: Theory of Progressive Knockout Tournaments](https://blog.gtowizard.com/the-theory-of-progressive-knockout-tournaments/)
- [GTO Wizard: Bounty Tournament Theory Part 3 - Key Calculations](https://blog.gtowizard.com/the-theory-of-bounty-tournaments-part-3-key-calculations/)
- [GTO Wizard: Bounty Models Explained](https://blog.gtowizard.com/bounty-models-explained-solving-knockout-tournaments/)
- [GTO Wizard: Champion's Guide to Knockout Formats](https://blog.gtowizard.com/a-champions-guide-to-knockout-poker-formats/)
- [BBZ Poker: Ultimate Guide to PKO Tournament Strategy](https://bbzpoker.com/ultimate-guide-to-pko-tournament-strategy/)
- [PokerNews: Guide to Knockout Poker Formats](https://www.pokernews.com/strategy/your-guide-to-knockout-poker-formats-47675.htm)
- [GGPoker: Understanding Bounty Hunters](https://help.ggpoker.com/article/978-understanding-bounty-hunters)
- [Upswing Poker: Knockout Bounty Tournaments](https://upswingpoker.com/knockout-bounty-tournaments-progressive-ko/)

### 9-Handed Strategy
- [GTO Wizard: Preflop Range Morphology](https://blog.gtowizard.com/preflop-range-morphology/)
- [BBZ Poker: GTO Poker Charts](https://bbzpoker.com/poker-charts/)
- [GipsyTeam: 9-Max Poker](https://www.gipsyteam.com/poker/9-max-in-poker)
- [Run It Once: Full Ring RFI Ranges](https://www.runitonce.com/nlhe/solid-full-ring-rfi-ranges/)
- [Freebetrange: 9-Max Preflop Charts](https://blog.freebetrange.com/article/9-max-poker-preflop-charts-for-texas-holdem)

### Spin & Go Strategy
- [GTO Wizard: Introduction to Spin & Gos](https://blog.gtowizard.com/an-introduction-to-spin-gos/)
- [Poker Sciences: 3 Simple Spin & Go Strategies](https://www.pokersciences.com/en/learn/spin/part-3/chapter-11)
- [Poker Sciences: Spin & Go Preflop Charts](https://www.pokersciences.com/en/bibliotheque-tableaux)
- [PokerEnergy: Spin & Go Preflop Charts and Strategy](https://pokerenergy.net/edu/item/charts-spin)
- [GGPoker: Spin & Gold Strategy](https://ggpoker.com/blog/ggpoker-spin-gold-strategy/)
- [Simple GTO: 25bb Spin & Go Solutions](https://simplegto.com/product/25bb-spin-go-preflop-solution/)

### Hyper Turbo Strategy
- [PokerNews: Adjusting for Turbo/Hyper-Turbo](https://www.pokernews.com/strategy/adjusting-your-strategy-for-turbo-and-hyper-turbo-tournament-37048.htm)
- [PokerCode: Hyper Turbo Tournaments](https://www.pokercode.com/blog/hyper-turbo-tournaments)
- [GGPoker: Hyper-Turbo Strategy](https://ggpoker.com/blog/hyper-turbo-tournaments-how-to-develop-a-winning-poker-strategy/)
- [Sit and Go Planet: Hyper Turbo SNG Strategy](https://www.sitandgoplanet.com/sitandgo/hyper-and-super-turbo-sng-strategy.html)

### Deep Stack Strategy
- [GTO Wizard: How Stack Sizes Change Your Range](https://blog.gtowizard.com/how-stack-sizes-change-your-range/)
- [Upswing Poker: Deep Stack Strategy Tips](https://upswingpoker.com/deep-stack-strategy-tips/)
- [PokerCode: Deep Stack Strategy Adjustments](https://www.pokercode.com/blog/deep-stack-poker-strategy)
- [Pokerology: Deep Stack Strategy](https://www.pokerology.com/poker/strategy/deep-stack/)
- [MyPokerCoaching: Deep Stack Poker Strategy](https://www.mypokercoaching.com/deep-stack-poker/)

### Push/Fold Charts
- [Primedope: Equilibrium Pushbot Charts](https://www.primedope.com/equilibrium-pushbot-charts/)
- [Upswing Poker: Push Fold Charts](https://upswingpoker.com/push-fold-tournament-strategy-charts/)
- [MyPokerCoaching: Push Fold Chart](https://www.mypokercoaching.com/push-fold-chart/)
- [PushFoldCharts.com](http://pushfoldcharts.com/)

### Testing Tools
- [eval7 on PyPI](https://pypi.org/project/eval7/)
- [pyeval7 on GitHub](https://github.com/julianandrews/pyeval7)
- [GTO CLI Tool (Monte Carlo equity)](https://github.com/sol5000/gto)
