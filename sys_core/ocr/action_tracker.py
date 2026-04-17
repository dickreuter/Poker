"""Per-frame action sequence detection.

Watches chip postings + active-seat snapshots across frames and emits
discrete poker actions as they occur — not just at street boundaries.

The existing HandContext only records a single villain action per street
transition, so a "MP raise → CO 3-bet → BTN call" preflop sequence
collapses to one event. ActionTracker preserves the full sequence,
which range-estimation downstream needs to distinguish a single open
from a 3-bet pot.

How detection works:
    Each frame supplies (chip_postings, active_seats, street).
    chip_postings is the current chip stack each seat has on the felt
    (in BB).  active_seats is the set of seats with card backs visible.

    Bet/raise/call comes from chip postings:
      seat appeared with amount > previous → bet/raise/call
      decided by comparing amount to street's current max
    Fold comes from card-back disappearance:
      seat was active last frame, not active now → fold
    Street transitions reset the per-seat posting baseline (chips
      get collected into the pot between streets).

Designed to be cheap (~0.1ms per frame) and stateless aside from the
per-window memory it owns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class TrackedAction:
    """A single observed poker action during a hand."""
    street: str          # 'preflop' | 'flop' | 'turn' | 'river'
    seat: int            # seat index that acted
    action: str          # 'bet' | 'raise' | 'call' | 'fold' | 'check'
    amount: float        # bet amount in BB (0 for fold/check)
    is_hero: bool = False  # True if this was the hero's action
    position: str = ''   # 'BTN'|'SB'|'BB'|'UTG'|'UTG+1'|'MP'|'HJ'|'CO' if known

    def __repr__(self):
        h = '★' if self.is_hero else ' '
        who = self.position if self.position else f"seat{self.seat}"
        return f"<{self.street[:2]}{h} {who} {self.action} {self.amount}BB>"


class ActionTracker:
    """Stateful action sequence detector for one table session.

    Lifetime: one instance per TableSession (one per window). Reset on
    new hand (typically when hero cards change).
    """

    def __init__(self, hero_seat: int = 0):
        self.hero_seat = hero_seat
        self._reset_full()

    def _reset_full(self) -> None:
        """Wipe all state — call this when a new hand begins."""
        self.actions: List[TrackedAction] = []
        self._last_postings: Dict[int, float] = {}
        self._last_active: Set[int] = set()
        self._last_street: str = ""
        self._street_max: float = 0.0

    def reset_for_new_hand(self) -> None:
        """Public API: caller signals a new hand started."""
        self._reset_full()

    def prime_blinds(self, sb_seat: int, sb_amount: float,
                     bb_seat: int, bb_amount: float) -> None:
        """Mark the SB/BB postings as initial state, not voluntary actions.

        Without this, the very first frame's chip postings (which contain
        the mandatory blinds) get classified as bet/raise, polluting the
        action sequence with non-events. Engine should call this once
        when a new hand starts and SB/BB seats are detected.

        After priming, the next actor matching BB amount is a limp/call,
        and the next actor exceeding BB is a raise — exactly what poker
        rules say.
        """
        if sb_seat >= 0 and sb_amount > 0:
            self._last_postings[sb_seat] = sb_amount
        if bb_seat >= 0 and bb_amount > 0:
            self._last_postings[bb_seat] = bb_amount
            if bb_amount > self._street_max:
                self._street_max = bb_amount

    def update(
        self,
        chip_postings: List[Tuple[float, int]],
        active_seats: Set[int],
        street: str,
        seat_positions: Optional[Dict[int, str]] = None,
    ) -> List[TrackedAction]:
        """Diff against last frame and append any newly observed actions.

        Args:
            chip_postings: list of (amount_bb, seat_idx) from
                _detect_blinds_from_chips. Each seat appears at most once
                with their CURRENT bet on the felt.
            active_seats: seats with visible card backs (still in hand).
                For preflop where card-back detection is lossy, pass the
                set of seats whose stacks were OCR'd.
            street: 'preflop' | 'flop' | 'turn' | 'river'.
            seat_positions: optional {seat_idx: 'BTN'|'SB'|'BB'|...} so
                emitted events carry readable position names ('UTG raise')
                instead of bare seat indices.

        Returns: the list of NEW actions detected this frame (may be empty).
        """
        seat_positions = seat_positions or {}
        new_events: List[TrackedAction] = []

        # Street transition: chips collected into pot, baseline resets.
        # Don't infer folds here — folded players from last street are
        # gone for good and shouldn't keep generating fold events.
        if street != self._last_street and self._last_street:
            self._last_postings = {}
            self._street_max = 0.0
        self._last_street = street

        current = {seat: amt for amt, seat in chip_postings}

        # 1. Bets / raises / calls from chip-amount changes.
        # Iterate in ascending posting amount so simultaneous actions in one
        # frame (e.g. CO bet 2 + hero call 2 between polls) are classified
        # in the order they would have happened — smaller amount first.
        for seat, amt in sorted(current.items(), key=lambda kv: kv[1]):
            last_amt = self._last_postings.get(seat, 0.0)
            if amt <= last_amt:
                continue  # No change, or chips reduced (shouldn't happen)
            # Classify by comparison to running street max BEFORE this update.
            if amt > self._street_max + 0.01:  # epsilon for float compare
                action = 'raise' if self._street_max > 0 else 'bet'
            else:
                action = 'call'
            ev = TrackedAction(
                street=street, seat=seat, action=action, amount=amt,
                is_hero=(seat == self.hero_seat),
                position=seat_positions.get(seat, ''),
            )
            new_events.append(ev)
            self.actions.append(ev)
            # Update street max in-line so subsequent same-frame events see it.
            if amt > self._street_max:
                self._street_max = amt

        # 2. Folds — seats that had card backs last frame, gone now.
        # Only meaningful within the same street (between streets, all
        # folded players' cards are mucked anyway).
        if self._last_active and active_seats:
            folded = self._last_active - active_seats
            # Skip the hero — bot folding itself is recorded by the engine
            # via _record_hero_action_in_context, not by visual disappearance.
            folded.discard(self.hero_seat)
            for seat in folded:
                ev = TrackedAction(
                    street=street, seat=seat, action='fold', amount=0.0,
                    is_hero=False,
                    position=seat_positions.get(seat, ''),
                )
                new_events.append(ev)
                self.actions.append(ev)

        self._last_postings = current
        self._last_active = set(active_seats)
        return new_events

    def summary(self) -> str:
        """Compact one-liner for logging — full hand sequence with positions."""
        if not self.actions:
            return "(no actions)"
        parts = []
        prev_street = ""
        for a in self.actions:
            if a.street != prev_street:
                parts.append(f"[{a.street}]")
                prev_street = a.street
            if a.is_hero:
                tag = 'HERO'
            elif a.position:
                tag = a.position
            else:
                tag = f's{a.seat}'
            if a.action in ('fold', 'check'):
                parts.append(f"{tag}-{a.action}")
            else:
                parts.append(f"{tag}-{a.action}{a.amount:g}")
        return ' '.join(parts)
