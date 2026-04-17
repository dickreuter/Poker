"""
GameState - Core data model for complete poker table state.

This is the contract between the Rust OCR binary and Python decision layer.
The Rust binary outputs JSON matching this schema, and Python deserializes it.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple

log = logging.getLogger('game_state')


# ---------------------------------------------------------------------------
#  Hand Context — tracks full action history within a single hand
# ---------------------------------------------------------------------------

@dataclass
class HandAction:
    """A single action taken during a hand."""
    street: str           # 'preflop', 'flop', 'turn', 'river'
    actor: str            # 'hero' or 'villain'
    action: str           # 'raise', 'call', 'check', 'bet', 'fold', '3bet', '4bet'
    amount: float = 0.0   # Amount in BB (0 for checks)
    pot_after: float = 0.0  # Pot size after this action


@dataclass
class HandContext:
    """Full action context for the current hand — persists across streets.

    Built incrementally by the engine as new information arrives each poll
    cycle.  Passed into DecisionMaker and range estimation so they can
    produce context-aware villain ranges (e.g. UTG open + flop c-bet + turn
    barrel -> narrow/polarized range).
    """
    # --- Preflop context ---
    preflop_raiser_seat: int = -1       # -1 = limped pot / no raiser detected
    preflop_raiser_position: str = ''   # 'UTG', 'MP', 'CO', 'BTN', 'SB', 'BB', or ''
    hero_was_raiser: bool = False       # Did hero raise preflop?
    hero_was_caller: bool = False       # Did hero flat-call preflop?
    hero_was_3bettor: bool = False      # Did hero 3-bet preflop?
    num_players_to_flop: int = 2        # How many players saw the flop
    preflop_pot_bb: float = 0.0         # Pot going to flop (in BB)

    # --- Per-street villain actions ---
    # Each list contains the villain actions observed on that street.
    # Example: villain_actions['flop'] = ['bet'], villain_actions['turn'] = ['bet']
    # means villain double-barreled.
    villain_actions: Dict[str, List[str]] = field(
        default_factory=lambda: {'preflop': [], 'flop': [], 'turn': [], 'river': []}
    )

    # --- Per-street hero actions ---
    hero_actions: Dict[str, List[str]] = field(
        default_factory=lambda: {'preflop': [], 'flop': [], 'turn': [], 'river': []}
    )

    # --- Full action sequence ---
    action_history: List[HandAction] = field(default_factory=list)

    # Per-frame action sequence from ActionTracker (richer than action_history,
    # which only captures street-transition events). Populated by the engine
    # when ActionTracker is enabled. Format: list of TrackedAction objects
    # (street, seat, action, amount, is_hero).
    full_action_sequence: list = field(default_factory=list)

    # Multi-raiser preflop detection — derived from full_action_sequence.
    # 3-bet pots have ~5x narrower villain ranges than single-raise pots
    # (e.g. JJ+/AK vs 22+/A2s+/K9s+) so this single bool meaningfully
    # changes equity calculations downstream.
    is_3bet_pot: bool = False
    is_4bet_pot: bool = False
    num_preflop_raisers: int = 0

    # --- Derived context (updated after each street) ---
    hero_has_initiative: bool = False   # Is hero the last aggressor?
    villain_has_initiative: bool = False  # Is villain the last aggressor?
    is_cbet_spot: bool = False          # Preflop raiser betting flop
    is_donk_bet: bool = False           # Non-raiser betting into raiser
    streets_of_aggression: int = 0      # How many streets villain has bet/raised
    is_multiway: bool = False           # 3+ players to flop
    hero_is_ip: bool = False             # Hero is in position (acts last postflop)

    def record_action(self, street: str, actor: str, action: str,
                      amount: float = 0.0, pot_after: float = 0.0):
        """Record an action and update derived context."""
        ha = HandAction(street=street, actor=actor, action=action,
                        amount=amount, pot_after=pot_after)
        self.action_history.append(ha)

        if actor == 'hero':
            self.hero_actions.setdefault(street, []).append(action)
        else:
            self.villain_actions.setdefault(street, []).append(action)

        # Update initiative tracking
        if action in ('raise', 'bet', '3bet', '4bet'):
            if actor == 'hero':
                self.hero_has_initiative = True
                self.villain_has_initiative = False
            else:
                self.villain_has_initiative = True
                self.hero_has_initiative = False
        elif action == 'call':
            pass  # Caller does NOT gain initiative

        # Count villain streets of aggression
        self.streets_of_aggression = sum(
            1 for s_actions in self.villain_actions.values()
            if any(a in ('bet', 'raise', '3bet', '4bet') for a in s_actions)
        )

        # Detect c-bet spot: preflop raiser bets flop
        if street == 'flop' and action == 'bet':
            if actor == 'villain' and self.villain_has_initiative and self.preflop_raiser_position:
                self.is_cbet_spot = True
            elif actor == 'hero' and self.hero_was_raiser:
                self.is_cbet_spot = True

        # Detect donk bet: non-preflop-raiser bets into the raiser
        if street == 'flop' and action == 'bet':
            if actor == 'villain' and self.hero_was_raiser:
                self.is_donk_bet = True
            elif actor == 'hero' and not self.hero_was_raiser and self.preflop_raiser_position:
                self.is_donk_bet = True

    @property
    def villain_pattern(self) -> str:
        """Summarize villain's multi-street action pattern.

        Returns strings like:
          'bet-bet'      (flop bet + turn bet = double barrel)
          'bet-bet-bet'  (triple barrel)
          'check-bet'    (checked flop, bet turn = delayed c-bet)
          'bet-check'    (bet flop, gave up turn)
          'raise'        (check-raised or raised our bet)
        """
        parts = []
        for s in ('flop', 'turn', 'river'):
            actions = self.villain_actions.get(s, [])
            if not actions:
                continue  # Street hasn't happened yet
            # Summarize: take the most aggressive action on this street
            if any(a in ('raise', '3bet', '4bet') for a in actions):
                parts.append('raise')
            elif 'bet' in actions:
                parts.append('bet')
            elif 'call' in actions:
                parts.append('call')
            elif 'check' in actions:
                parts.append('check')
        return '-'.join(parts) if parts else ''

    def to_dict(self) -> dict:
        """Serialize for logging."""
        return {
            'preflop_raiser_position': self.preflop_raiser_position,
            'hero_was_raiser': self.hero_was_raiser,
            'hero_was_caller': self.hero_was_caller,
            'num_players_to_flop': self.num_players_to_flop,
            'villain_pattern': self.villain_pattern,
            'streets_of_aggression': self.streets_of_aggression,
            'hero_has_initiative': self.hero_has_initiative,
            'villain_has_initiative': self.villain_has_initiative,
            'is_cbet_spot': self.is_cbet_spot,
            'is_multiway': self.is_multiway,
            'action_count': len(self.action_history),
        }


@dataclass
class ReadConfidence:
    """Per-field confidence scores for OCR reads (0.0–1.0).

    Used to gate decisions: if overall < 0.5, re-read; if < 0.4, default to check/fold.
    """
    cards: float = 0.0       # hash hit=1.0, template=0.85, OCR=0.7, cached=0.5
    pot: float = 0.0         # double-read match=1.0, single=0.6, estimated=0.3
    call_amount: float = 0.0 # parsed cleanly=0.9, heuristic-corrected=0.5
    stacks: float = 0.0      # OCR success=0.8, cached=0.5, default=0.3
    buttons: float = 0.0     # color-detected=0.9, OCR-text=0.7

    @property
    def overall(self) -> float:
        """Minimum of the critical fields (cards, pot, call_amount)."""
        return min(self.cards, self.pot, self.call_amount)

    def __repr__(self):
        return (f"Conf(cards={self.cards:.2f} pot={self.pot:.2f} "
                f"call={self.call_amount:.2f} overall={self.overall:.2f})")


class Street(Enum):
    PREFLOP = "Preflop"
    FLOP = "Flop"
    TURN = "Turn"
    RIVER = "River"
    SHOWDOWN = "Showdown"
    UNKNOWN = "Unknown"


@dataclass
class PlayerInfo:
    seat: int
    name: str
    stack: float
    current_bet: float
    is_active: bool
    is_hero: bool

    @classmethod
    def from_json(cls, data: dict) -> 'PlayerInfo':
        return cls(
            seat=data.get('seat', 0),
            name=data.get('name', ''),
            stack=float(data.get('stack', 0)),
            current_bet=float(data.get('current_bet', 0)),
            is_active=data.get('is_active', False),
            is_hero=data.get('is_hero', False),
        )


@dataclass
class AvailableAction:
    action_type: str  # 'fold', 'call', 'check', 'raise', 'bet', 'all_in'
    amount: Optional[float]
    screen_x_pt: int  # Screen click point in macOS points
    screen_y_pt: int
    confidence: float
    rel_x: float = 0.0 # Relative X in cropped image (0.0 to 1.0)
    rel_y: float = 0.0 # Relative Y in cropped image (0.0 to 1.0)

    @classmethod
    def from_json(cls, data: dict) -> 'AvailableAction':
        return cls(
            action_type=data.get('action_type', ''),
            amount=data.get('amount'),
            screen_x_pt=int(data.get('screen_x_pt', 0)),
            screen_y_pt=int(data.get('screen_y_pt', 0)),
            rel_x=float(data.get('rel_x', 0.0)),
            rel_y=float(data.get('rel_y', 0.0)),
            confidence=float(data.get('confidence', 0)),
        )


@dataclass
class GameState:
    """Complete state of a poker table at a point in time."""

    # Window info
    window_id: int = 0
    window_name: str = ""
    table_x_pt: int = 0
    table_y_pt: int = 0
    table_w_pt: int = 0
    table_h_pt: int = 0

    # Cards
    my_cards: List[str] = field(default_factory=list)
    board_cards: List[str] = field(default_factory=list)
    cards_face_down: bool = False

    # Pot and betting
    pot: float = 0.0
    current_street_pot: float = 0.0
    call_amount: float = 0.0
    min_raise_amount: float = 0.0
    small_blind: float = 0.0
    big_blind: float = 0.0

    # Players
    players: List[PlayerInfo] = field(default_factory=list)
    hero_seat: int = -1
    dealer_seat: int = -1
    num_seats: int = 6  # 3 / 6 / 9 — table size, used for position math
    sb_seat: int = -1   # small blind seat (preflop only; -1 if unknown)
    bb_seat: int = -1   # big blind seat (preflop only; -1 if unknown)

    # Actions
    available_actions: List[AvailableAction] = field(default_factory=list)

    # Game state
    street: Street = Street.UNKNOWN
    is_my_turn: bool = False
    position: str = "UNKNOWN"  # BTN, SB, BB, UTG, MP, CO

    # Preflop action detection (from chip postings on felt)
    preflop_raiser_seat: int = -1       # Physical seat of the raiser (-1 = no raise)
    preflop_raiser_position: str = ""   # Position name of raiser (UTG/MP/CO/BTN/SB/BB)
    chip_postings: List[Tuple[float, int]] = field(default_factory=list)  # [(amount_bb, seat)]

    # Opponent detection
    opponents_in_hand: int = -1  # -1 = unknown, 0+ = from card-back detection

    # Tournament info (from info bar OCR)
    game_type: str = "unknown"  # 'cash', 'tournament', 'spin'
    is_tournament: bool = False
    tournament_level: Optional[int] = None    # Blind level (e.g., 9)
    tournament_rank: Optional[int] = None     # My rank (e.g., 12)
    tournament_total: Optional[int] = None    # Total players (e.g., 546)
    tournament_prize: Optional[float] = None  # 1st prize in dollars (e.g., 1172.0)
    tournament_players_paid: Optional[int] = None  # Places paid count
    icm_pressure: float = 0.0  # 0.0 (no pressure) to 1.0 (extreme bubble/FT)
    tournament_subtype: str = "unknown"  # 'hyper', 'turbo', 'double_stack', 'bounty', 'spin', 'regular', 'unknown'

    # Metadata
    ocr_latency_ms: float = 0.0
    ocr_source: str = "unknown"

    # Safety flags
    hero_stack_is_estimated: bool = False  # True when hero stack OCR failed → default 100 BB

    # Confidence metadata — populated by read_table()
    confidence: ReadConfidence = field(default_factory=ReadConfidence)

    # Hand context — full action history for this hand (built by engine.py)
    hand_context: Optional[HandContext] = None

    # -- Backward-compatible properties for existing code --

    @property
    def has_call_button(self) -> bool:
        return any(a.action_type in ('call', 'check') for a in self.available_actions)

    @property
    def has_raise_button(self) -> bool:
        return any(a.action_type in ('raise', 'bet') for a in self.available_actions)

    @property
    def has_fold_button(self) -> bool:
        return any(a.action_type == 'fold' for a in self.available_actions)

    @property
    def has_check_button(self) -> bool:
        for a in self.available_actions:
            if a.action_type == 'check':
                return True
            # Call with amount 0 is effectively a check
            if a.action_type == 'call' and (a.amount is None or a.amount == 0):
                return True
        return False

    @property
    def hero_stack(self) -> float:
        for p in self.players:
            if p.is_hero:
                return p.stack
        return 0.0

    @property
    def other_active_players(self) -> int:
        """Count of active opponents (non-hero)."""
        return sum(1 for p in self.players if p.is_active and not p.is_hero)

    @property
    def game_stage(self) -> str:
        # DecisionMaker expects "PreFlop" (capital F), not "Preflop"
        stage_map = {
            Street.PREFLOP: "PreFlop",
            Street.FLOP: "Flop",
            Street.TURN: "Turn",
            Street.RIVER: "River",
        }
        return stage_map.get(self.street, "PreFlop")

    @property
    def num_board_cards(self) -> int:
        return len(self.board_cards)

    def get_action_by_type(self, action_type: str) -> Optional[AvailableAction]:
        for a in self.available_actions:
            if a.action_type == action_type:
                return a
        return None

    def to_table_scraper_compat(self, t) -> None:
        """Populate a TableScraper-like object's attributes for DecisionMaker compatibility.

        Args:
            t: A TableScreenBased or similar object with standard attributes.
        """
        from copy import copy

        # Cards
        if self.my_cards and len(self.my_cards) == 2:
            t.mycards = self.my_cards
        t.cardsOnTable = self.board_cards

        # --- BB normalization ---
        # DecisionMaker expects everything in BB units.
        #
        # GGPoker client has "BB display" enabled — ALL table types (Rush & Cash,
        # Spin & Gold, tournaments) show values in BB on screen.  OCR values are
        # therefore ALWAYS in BB already.  No normalization needed.
        _to_bb = lambda v: v
        log.debug(f"BB display ON: OCR values already in BB, no normalization "
                  f"(window blinds: {self.small_blind}/{self.big_blind})")
        bb_size = 0.0  # Used by downstream safety thresholds as "1 BB = 1.0"

        # Pot (normalized to BB)
        t.totalPotValue = _to_bb(self.pot)
        t.currentRoundPotValue = _to_bb(self.current_street_pot)
        t.round_pot_value = _to_bb(self.current_street_pot) if self.current_street_pot else t.totalPotValue

        # Betting — ensure call/bet values are never 0 when buttons exist.
        call_val = self.call_amount
        if call_val == 0 and self.has_call_button and not self.has_check_button:
            # Call button visible but OCR failed to parse amount — default to 1 BB
            call_val = bb_size if bb_size > 0 else 1.0
        # --- Format-agnostic call amount validation (ratio-based) ---
        # Safety checks use RAW values (ratios are unit-agnostic)
        raw_ocr_call = call_val
        hero_stk = self.hero_stack
        is_preflop = not self.board_cards
        stack_reliable = hero_stk > 0 and not self.hero_stack_is_estimated

        # RULE 1: call <= hero_stack (ALWAYS)
        if hero_stk > 0 and call_val > hero_stk:
            log.warning(f"SAFETY: Call {call_val} > hero stack {hero_stk}, capping at stack")
            call_val = hero_stk

        # RULE 2: call vs pot ratio (works across all formats/stack depths)
        # Preflop: call <= 4x pot (covers 5-bet jams)
        # Postflop: call <= 3x pot (extreme overbets)
        pot = self.pot
        # Threshold scales with blind level (0.5 BB in raw units)
        half_bb_raw = bb_size * 0.5 if bb_size > 0 else 0.5
        if pot > half_bb_raw:
            max_ratio = 4.0 if is_preflop else 3.0
            if call_val > pot * max_ratio:
                log.warning(f"SAFETY: Call {call_val} > {max_ratio}x pot {pot}, capping to {max_ratio}x pot")
                call_val = pot * max_ratio

        # RULE 3: No reliable anchors → ultra-conservative
        two_bb_raw = bb_size * 2.0 if bb_size > 0 else 2.0
        if not stack_reliable and pot <= half_bb_raw and call_val > two_bb_raw:
            log.error(f"NO ANCHORS: stack=est, pot={pot}, call={call_val} → 1 BB")
            call_val = bb_size if bb_size > 0 else 1.0

        was_safety_capped = (call_val != raw_ocr_call)
        if was_safety_capped:
            log.warning(f"OCR call validated: raw={raw_ocr_call} → capped={call_val}")
        # Store raw value for logging downstream
        self._raw_ocr_call = raw_ocr_call
        self._was_safety_capped = was_safety_capped

        # Normalize call/bet to BB after safety checks
        t.currentCallValue = _to_bb(call_val)
        bet_val = self.min_raise_amount
        if bet_val == 0 and self.has_raise_button:
            # Raise button visible but no amount — default to 2x call or 2 BB
            bet_val = max(call_val * 2, bb_size * 2 if bb_size > 0 else 2.0) if call_val > 0 else (bb_size * 2 if bb_size > 0 else 2.0)
        elif bet_val == 0 and not self.has_raise_button:
            # No raise button — set high so betting conditions never trigger
            bet_val = 9999.0
        t.currentBetValue = _to_bb(bet_val)

        # Blinds — after normalization, everything is in BB units
        t.smallBlind = 0.5  # Always 0.5 BB
        t.bigBlind = 1.0    # Always 1.0 BB

        # Buttons
        t.checkButton = self.has_check_button
        t.callButton = self.has_call_button
        t.raiseButton = self.has_raise_button
        t.allInCallButton = any(
            a.action_type == 'all_in' for a in self.available_actions
        )

        # Players — build the list-of-dicts that DecisionMaker expects
        active_opponents = [p for p in self.players if p.is_active and not p.is_hero]
        all_active = [p for p in self.players if p.is_active]

        other_player_template = {
            'utg_position': 0, 'name': '', 'status': '',
            'funds': '', 'pot': '', 'decision': '', 'abs_position': 0,
        }
        t.other_players = []
        for i, p in enumerate(active_opponents):
            op = copy(other_player_template)
            op['abs_position'] = i
            op['utg_position'] = i
            op['name'] = p.name
            op['funds'] = _to_bb(p.stack)
            op['pot'] = _to_bb(p.current_bet)
            op['status'] = 1  # active
            t.other_players.append(op)

        t.playersAtTable = len(all_active)
        t.total_players = max(len(self.players), 2)  # max seats (use actual count, not hardcoded 6)

        # Pad other_players to total_players-1 entries so Monte Carlo loops
        # (which iterate range(total_players-1)) don't IndexError.
        while len(t.other_players) < t.total_players - 1:
            pad = copy(other_player_template)
            pad['abs_position'] = len(t.other_players)
            pad['utg_position'] = len(t.other_players)
            pad['status'] = 0  # inactive / folded
            pad['funds'] = 0
            pad['pot'] = 0
            t.other_players.append(pad)

        # Accurate opponent count is CRITICAL for Monte Carlo equity.
        # Running against 4 opponents when heads-up destroys equity for
        # draws and made hands (e.g. nut flush shows 24% instead of 85%).
        raw_active = len(active_opponents)
        if self.opponents_in_hand >= 0:
            # Card-back detection: the most accurate signal both pre and post
            # flop. opponents_in_hand counts visible card backs at opponent
            # seats — folded opponents have no cards even though their stack
            # is still readable, so this beats raw_active for accuracy.
            t.other_active_players = max(self.opponents_in_hand, 1)
            log.info(f"Opponents from card-back detection: {self.opponents_in_hand}")
        elif self.board_cards and len(self.board_cards) >= 1:
            # Postflop fallback when card-back detection unavailable:
            # heuristic from pot size. Cap at 2 for Rush & Cash.
            pot_in_bb = self.pot if self.pot > 0 else 3
            if pot_in_bb <= 6:
                estimated_opponents = 1
            else:
                estimated_opponents = 2
            t.other_active_players = min(estimated_opponents, raw_active)
        else:
            # Preflop with no card-back data: assume all seated opponents
            # are still in. Pessimistic — may overcount (some already folded).
            t.other_active_players = raw_active

        t.isHeadsUp = t.other_active_players <= 1

        # --- Action tracking: initiative, position, raiser inference ---
        import numpy as _np
        call_val = t.currentCallValue

        # Determine if opponent has initiative (they bet/raised to us)
        is_postflop = bool(self.board_cards and len(self.board_cards) >= 1)
        if is_postflop:
            # Postflop: initiative = we face a bet (call button without check)
            t.other_player_has_initiative = call_val > 0 and not self.has_check_button
        else:
            # Preflop: initiative = facing a raise (call > 1 BB beyond our blind)
            # If we're BB facing a raise, call > 0 and pot > 2.5
            # If we're SB, we posted 0.5, a raise makes call > 0.5
            pot_bb = t.totalPotValue  # already normalized to BB
            t.other_player_has_initiative = (call_val > 1.0) or (pot_bb > 3.0 and call_val > 0)

        # Position-based tracking for playersAhead / playersBehind
        # Works for 6-max and 8/9-max (UTG positions map to 0)
        _pos_order = {'UTG': 0, 'MP': 1, 'CO': 2, 'BTN': 3, 'SB': 4, 'BB': 5}
        hero_order = _pos_order.get(self.position, 3)

        if is_postflop:
            # Postflop: position order is SB→BB→UTG→...→BTN
            # If we face a bet, at least 1 player acted ahead
            if t.other_player_has_initiative:
                t.playersAhead = 1  # at least the bettor
            else:
                t.playersAhead = 0
            t.playersBehind = max(t.other_active_players - 1 - t.playersAhead, 0)
        else:
            # Preflop: estimate playersAhead from position
            # UTG acts first (0 ahead), BB acts last (5 ahead)
            t.playersAhead = min(hero_order, t.other_active_players)
            t.playersBehind = max(t.other_active_players - t.playersAhead, 0)

        # --- Raiser/caller inference for opponent range estimation ---
        # first_raiser_utg: UTG position of the first raiser (0=UTG...5=BB)
        # Used by Monte Carlo to select opponent range tables
        #
        # PREFER ground-truth OCR data from chip postings on the felt.
        # Fall back to heuristic when OCR didn't detect a raiser.
        _raiser_pos_to_utg = {
            'UTG': 0, 'MP': 1, 'CO': 2, 'BTN': 3, 'SB': 4, 'BB': 5}
        if (self.preflop_raiser_position
                and self.preflop_raiser_position in _raiser_pos_to_utg
                and not is_postflop):
            # Ground-truth raiser detected from chip posting OCR
            t.first_raiser_utg = float(
                _raiser_pos_to_utg[self.preflop_raiser_position])
            t.first_raiser = 1
            t._raiser_already_set = True
            t.first_caller_utg = _np.nan
            log.info(f"Raiser from OCR: {self.preflop_raiser_position} "
                     f"(seat {self.preflop_raiser_seat}) "
                     f"-> first_raiser_utg={t.first_raiser_utg}")
        elif t.other_player_has_initiative and not is_postflop:
            # Preflop raise detected — estimate raiser position from call size
            # and hero's position. The last aggressor (facing us) matters most.
            _call = call_val
            if _call > 15:
                # 4-bet+: very tight range regardless of position
                t.first_raiser_utg = 0  # UTG-equivalent (tight)
            elif _call > 5:
                # 3-bet: if we're LP, villain is likely blinds; if EP, villain is LP
                if hero_order >= 3:  # Hero is BTN/SB/BB → villain 3-bet from blinds
                    t.first_raiser_utg = 5  # BB 3-bet
                else:  # Hero is UTG/MP/CO → villain 3-bet from LP
                    t.first_raiser_utg = 3  # BTN 3-bet
            elif hero_order >= 4:
                # Hero in blinds facing open → raiser is likely BTN/CO (steal)
                t.first_raiser_utg = 3  # BTN range
            elif hero_order >= 2:
                # Hero in CO/BTN facing open → raiser is EP/MP
                t.first_raiser_utg = max(hero_order - 2, 0)
            else:
                # Hero in EP facing open → raiser is before us
                t.first_raiser_utg = max(hero_order - 1, 0)
            t.first_raiser = 1
            t._raiser_already_set = True
            t.first_caller_utg = _np.nan  # unknown
        elif t.other_player_has_initiative and is_postflop:
            # Postflop bet — raiser position from preflop context
            t.first_raiser_utg = _np.nan
            t.first_raiser = 0
            t.first_caller_utg = _np.nan
        else:
            t.first_raiser_utg = _np.nan
            t.first_raiser = 0
            t.first_caller_utg = _np.nan
        t.second_raiser_utg = _np.nan  # can't detect from OCR

        log.debug(f"Action tracking: initiative={t.other_player_has_initiative} "
                  f"ahead={t.playersAhead} behind={getattr(t, 'playersBehind', '?')} "
                  f"raiser_utg={t.first_raiser_utg} headsUp={t.isHeadsUp}")

        # Hero funds (in BB) — never set to 0, or low-stack-multiplier will call everything
        hero_bb = _to_bb(self.hero_stack) if self.hero_stack > 0 else 100.0
        t.myFunds = hero_bb
        t.myBetAmount = 0.0

        # Dealer
        t.dealer_position = self.dealer_seat

        # Game stage
        t.gameStage = self.game_stage

        # Attributes expected by Monte Carlo / DecisionMaker
        import time as _time
        t.mt_tm = _time.time()
        t.montecarlo_timeout = 10
        t.abs_equity = 0.5  # default until MC runs
        t.equity = 0.5
        t.relative_equity = 0.5

        # Map position name to UTG+ numbering for preflop sheet lookup
        # Sheet "1"=UTG, "2"=MP, "3"=CO, "4"=BTN, "5"=SB, "6"=BB
        _pos_to_utg = {
            'UTG': 0, 'MP': 1, 'CO': 2, 'BTN': 3, 'SB': 4, 'BB': 5,
            'UNKNOWN': 0,
        }
        t.position_utg_plus = _pos_to_utg.get(self.position, 0)
        t._gto_position = self.position  # Pass raw position string for GTO ranges

        # Infer raiser/caller from call amount (in BB units).
        # Use sanitized call_val (not raw self.call_amount) to avoid OCR misreads.
        # In BB: call_amount > 0 with a call button means someone raised.
        # In other positions: call > 1.1 BB means someone raised (call=1.0 is just BB).
        _is_bb = (self.position == 'BB')
        _has_call = self.has_call_button and not self.has_check_button
        if _is_bb:
            # BB already posted 1BB. Any call amount > 0 means someone raised.
            _has_raiser = call_val > 0.1 and _has_call
        else:
            # Other positions: call > 1BB means a raise happened
            _has_raiser = call_val > 1.1
        t.first_caller = False
        t.second_raiser = False
        # Only update raiser fields if the FIRST inference block (lines 353-376)
        # didn't already set them.  That block uses call-size + hero position
        # (more accurate); this block uses pot size (less accurate).
        if not hasattr(t, '_raiser_already_set') or not t._raiser_already_set:
            t.first_raiser = _has_raiser
            if _has_raiser:
                _pot_bb = t.totalPotValue if t.totalPotValue > 0 else 3
                if _pot_bb <= 4:
                    _est_pos = max(0, t.position_utg_plus - 1)
                elif _pot_bb <= 6:
                    _est_pos = max(0, t.position_utg_plus - 2)
                else:
                    _est_pos = 0
                t.first_raiser_utg = float(_est_pos)
            else:
                t.first_raiser_utg = _np.nan
        t.first_caller_utg = _np.nan
        t.second_raiser_utg = _np.nan
        t.other_player_has_initiative = _has_raiser
        t.max_X = 0.95 if self.street == Street.PREFLOP else 1.0
        t.PlayerNames = [p.name for p in active_opponents]
        t.entireScreenPIL = None  # placeholder for error screenshots

        # Tournament info — passed to DecisionMaker for ICM-aware decisions
        t._game_type = self.game_type
        t._is_tournament = self.is_tournament
        t._tournament_level = self.tournament_level
        t._tournament_rank = self.tournament_rank
        t._tournament_total = self.tournament_total
        t._tournament_prize = self.tournament_prize
        t._tournament_players_paid = self.tournament_players_paid
        t._icm_pressure = self.icm_pressure
        t._tournament_subtype = self.tournament_subtype

        # derive_preflop_sheet_name is inherited from Table — no action needed

    @classmethod
    def from_json(cls, data: dict) -> 'GameState':
        """Deserialize from the Rust OCR binary JSON output."""
        street_str = data.get('street', 'Unknown')
        try:
            street = Street(street_str)
        except ValueError:
            street = Street.UNKNOWN

        players = [
            PlayerInfo.from_json(p) for p in data.get('players', [])
        ]
        actions = [
            AvailableAction.from_json(a) for a in data.get('available_actions', [])
        ]

        return cls(
            window_id=data.get('window_id', 0),
            window_name=data.get('window_name', ''),
            table_x_pt=data.get('table_x_pt', 0),
            table_y_pt=data.get('table_y_pt', 0),
            table_w_pt=data.get('table_w_pt', 0),
            table_h_pt=data.get('table_h_pt', 0),
            my_cards=data.get('my_cards', []),
            board_cards=data.get('board_cards', []),
            cards_face_down=data.get('cards_face_down', False),
            pot=float(data.get('pot', 0)),
            current_street_pot=float(data.get('current_street_pot', 0)),
            call_amount=float(data.get('call_amount', 0)),
            min_raise_amount=float(data.get('min_raise_amount', 0)),
            small_blind=float(data.get('small_blind', 0)),
            big_blind=float(data.get('big_blind', 0)),
            players=players,
            hero_seat=data.get('hero_seat', -1),
            dealer_seat=data.get('dealer_seat', -1),
            available_actions=actions,
            street=street,
            is_my_turn=data.get('is_my_turn', False),
            ocr_latency_ms=float(data.get('ocr_latency_ms', 0)),
            ocr_source=data.get('ocr_source', 'unknown'),
            hero_stack_is_estimated=data.get('hero_stack_is_estimated', False),
        )

    def to_json(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            'window_id': self.window_id,
            'window_name': self.window_name,
            'table_x_pt': self.table_x_pt,
            'table_y_pt': self.table_y_pt,
            'table_w_pt': self.table_w_pt,
            'table_h_pt': self.table_h_pt,
            'my_cards': self.my_cards,
            'board_cards': self.board_cards,
            'cards_face_down': self.cards_face_down,
            'pot': self.pot,
            'current_street_pot': self.current_street_pot,
            'call_amount': self.call_amount,
            'min_raise_amount': self.min_raise_amount,
            'small_blind': self.small_blind,
            'big_blind': self.big_blind,
            'players': [
                {
                    'seat': p.seat,
                    'name': p.name,
                    'stack': p.stack,
                    'current_bet': p.current_bet,
                    'is_active': p.is_active,
                    'is_hero': p.is_hero,
                }
                for p in self.players
            ],
            'hero_seat': self.hero_seat,
            'dealer_seat': self.dealer_seat,
            'available_actions': [
                {
                    'action_type': a.action_type,
                    'amount': a.amount,
                    'screen_x_pt': a.screen_x_pt,
                    'screen_y_pt': a.screen_y_pt,
                    'rel_x': a.rel_x,
                    'rel_y': a.rel_y,
                    'confidence': a.confidence,
                }
                for a in self.available_actions
            ],
            'street': self.street.value,
            'is_my_turn': self.is_my_turn,
            'ocr_latency_ms': self.ocr_latency_ms,
            'ocr_source': self.ocr_source,
            'hero_stack_is_estimated': self.hero_stack_is_estimated,
        }
