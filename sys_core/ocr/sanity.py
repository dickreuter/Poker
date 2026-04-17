"""Per-frame sanity checks on OCR output.

Returns a list of (severity, field, message) warnings. Used to flag
"these reads are suspicious — strategy should NOT trust them" so the
bot can fall back to safe defaults instead of acting on garbage.

Concrete bugs this catches (all observed in real session logs):
  - "stk 8959 BB" — decimal point lost in hero stack OCR (real: 85.9)
  - "bets:[BB=255.0]" — 2.55 BB bet read as 255 BB
  - "BTN=55.0" when stack is 80 BB — likely 5.5 misread as 55
  - All-in flag (s with !) when stack is over 5 BB
  - position UNKNOWN postflop with no fallback
"""
from __future__ import annotations

from typing import List, Tuple

# Heuristic ceiling for "max plausible" values per game-type.
# A live cash game player can show 500 BB stacks (deep), but Spin/Rush/
# tournaments cap around 200 BB. Anything above 1000 BB is almost
# certainly a decimal-point misread (85.9 → 8590 or 8959).
MAX_PLAUSIBLE_STACK_BB = 1000
MAX_PLAUSIBLE_BET_BB = 250  # 200 BB shove from a deep stack is the realistic max
MIN_PLAUSIBLE_BET_BB = 0.4  # Sub-blind bets aren't possible


def check_state(state) -> List[Tuple[str, str, str]]:
    """Run sanity checks on a GameState; return list of warnings.

    Each warning is (severity, field, message):
      severity: 'high' (acting on this would cost money) | 'medium' | 'low'
      field:    the data field that's suspicious
      message:  human-readable explanation
    """
    warnings: List[Tuple[str, str, str]] = []

    # 1. Hero stack ceiling — the #1 bug from real logs (8959 BB).
    hero = next((p for p in (state.players or []) if p.is_hero), None)
    if hero and hero.stack and hero.stack > MAX_PLAUSIBLE_STACK_BB:
        warnings.append((
            'high', 'hero_stack',
            f"hero stack {hero.stack:.0f} BB exceeds {MAX_PLAUSIBLE_STACK_BB} BB ceiling — "
            f"likely decimal-point OCR error (real value probably {hero.stack/100:.1f} BB)"
        ))

    # 2. Opponent stack ceiling — same pattern for opponents.
    for p in (state.players or []):
        if p.is_hero:
            continue
        if p.stack and p.stack > MAX_PLAUSIBLE_STACK_BB:
            warnings.append((
                'medium', f'seat_{p.seat}_stack',
                f"opponent at seat {p.seat} ({p.name or '?'}) stack {p.stack:.0f} BB "
                f"exceeds ceiling — likely decimal misread (real ~{p.stack/100:.1f} BB)"
            ))

    # 3. Bet sanity — bets larger than the player's stack are impossible.
    for p in (state.players or []):
        if p.current_bet and p.stack and p.current_bet > p.stack * 1.5:
            warnings.append((
                'high', f'seat_{p.seat}_bet',
                f"seat {p.seat} bet {p.current_bet:.1f} BB exceeds stack "
                f"{p.stack:.1f} BB by 50%+ — bet OCR likely wrong"
            ))
        if p.current_bet and p.current_bet > MAX_PLAUSIBLE_BET_BB:
            warnings.append((
                'high', f'seat_{p.seat}_bet',
                f"seat {p.seat} bet {p.current_bet:.0f} BB exceeds {MAX_PLAUSIBLE_BET_BB} BB max — "
                f"likely decimal misread (real ~{p.current_bet/100:.1f} BB)"
            ))

    # 4. Pot must be ≥ posted blinds (preflop) and not absurd.
    if state.pot and state.pot > MAX_PLAUSIBLE_STACK_BB * 6:  # 6 players × max stack
        warnings.append((
            'medium', 'pot',
            f"pot {state.pot:.0f} BB exceeds 6×stack ceiling — pot OCR likely wrong"
        ))

    # 5. Call amount sanity — call > pot * 5 is rare and suspicious.
    if state.call_amount and state.pot:
        if state.call_amount > state.pot * 10 and state.call_amount > 10:
            warnings.append((
                'medium', 'call_amount',
                f"call {state.call_amount:.1f} BB > 10x pot {state.pot:.1f} BB — "
                f"likely unusual or OCR wrong"
            ))

    # 6. Position UNKNOWN when it's our turn — strategy will misread ranges.
    if state.is_my_turn and getattr(state, 'position', '') == 'UNKNOWN':
        warnings.append((
            'high', 'position',
            "position=UNKNOWN with action — range estimation will fall back to defaults"
        ))

    # 7. No buttons but is_my_turn = True (impossible — should be is_my_turn=False).
    if state.is_my_turn and not state.available_actions:
        warnings.append((
            'medium', 'buttons',
            "is_my_turn=True but no buttons detected — state inconsistent"
        ))

    # 8. Cards detected but cannot be cards (e.g. parsing artifact).
    for c in (state.my_cards or []):
        if len(c) != 2 or c[0] not in '23456789TJQKA' or c[1] not in 'SHDC':
            warnings.append((
                'high', 'hero_cards',
                f"hero card {c!r} malformed — should be 2 chars (rank+suit)"
            ))

    return warnings


def is_safe_to_act(state) -> bool:
    """Return False if any high-severity warning means we shouldn't trust this state."""
    for sev, _, _ in check_state(state):
        if sev == 'high':
            return False
    return True


def summary_line(state) -> str:
    """One-line summary of warnings for log/tray display. Empty if all clean."""
    warnings = check_state(state)
    if not warnings:
        return ''
    high = sum(1 for w in warnings if w[0] == 'high')
    med = sum(1 for w in warnings if w[0] == 'medium')
    if high:
        return f"⚠️  {high} HIGH severity warning{'s' if high != 1 else ''}"
    return f"⚠ {med} medium warning{'s' if med != 1 else ''}"
