"""
Persistent opponent modeling with real-time adaptation.

Tracks opponent tendencies (VPIP, PFR, aggression, fold-to-cbet) across
hands AND across sessions via JSON persistence. Provides player profiles
that directly feed into decision adjustments.

Usage:
    modeler = get_modeler()
    modeler.record_preflop_action('player123', 'raise', has_raiser_before=False)
    profile = modeler.get_profile('player123')
    # profile = {'vpip': 0.35, 'pfr': 0.22, 'af': 2.1, 'type': 'lag', ...}

Persistence:
    Profiles auto-save to data/learning/opponent_profiles.json every 10 hands.
    On startup, existing profiles are loaded and merged with new session data.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

# Persistence path
_PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'data', 'learning')
_PROFILE_PATH = os.path.join(_PROFILE_DIR, 'opponent_profiles.json')


class PlayerProfile:
    """Tracked stats for one opponent."""
    __slots__ = (
        'hands_seen', 'vpip_count', 'pfr_count',
        'postflop_bets', 'postflop_calls', 'postflop_checks', 'postflop_folds',
        'cbet_opportunities', 'cbet_count',
        'fold_to_cbet_opportunities', 'fold_to_cbet_count',
        'three_bet_opportunities', 'three_bet_count',
        'went_to_showdown', 'won_at_showdown',
        'last_seen',
        '_pos_stats',
        '_recent_vpip',
        '_recent_pfr',
        '_recent_af_actions',
        '_shown_hands',
    )

    def __init__(self):
        self.hands_seen = 0
        self.vpip_count = 0
        self.pfr_count = 0
        self.postflop_bets = 0
        self.postflop_calls = 0
        self.postflop_checks = 0
        self.postflop_folds = 0
        self.cbet_opportunities = 0
        self.cbet_count = 0
        self.fold_to_cbet_opportunities = 0
        self.fold_to_cbet_count = 0
        self.three_bet_opportunities = 0
        self.three_bet_count = 0
        self.went_to_showdown = 0
        self.won_at_showdown = 0
        self.last_seen = 0.0
        # Per-position stats: {pos: {'hands': N, 'vpip': N, 'pfr': N}}
        self._pos_stats = {}
        from collections import deque
        self._recent_vpip = deque(maxlen=15)
        self._recent_pfr = deque(maxlen=15)
        self._shown_hands = []  # List of {'cards': ['AH','KS'], 'action': 'bet', 'street': 'river'}
        self._recent_af_actions = deque(maxlen=20)

    @property
    def vpip(self):
        return min(self.vpip_count / max(self.hands_seen, 1), 1.0)

    @property
    def pfr(self):
        return min(self.pfr_count / max(self.hands_seen, 1), 1.0)

    @property
    def af(self):
        """Aggression factor: bets+raises / calls. Higher = more aggressive."""
        return self.postflop_bets / max(self.postflop_calls, 1)

    @property
    def cbet_pct(self):
        return self.cbet_count / max(self.cbet_opportunities, 1)

    @property
    def fold_to_cbet(self):
        return self.fold_to_cbet_count / max(self.fold_to_cbet_opportunities, 1)

    @property
    def three_bet_pct(self):
        return self.three_bet_count / max(self.three_bet_opportunities, 1)

    @property
    def wtsd(self):
        return self.went_to_showdown / max(self.hands_seen, 1)

    @property
    def wsd(self):
        return self.won_at_showdown / max(self.went_to_showdown, 1)

    @property
    def recent_vpip(self):
        """VPIP from last 15 hands (EMA-like weighting via recency)."""
        if len(self._recent_vpip) < 5:
            return self.vpip  # Not enough recent data, use lifetime
        return sum(self._recent_vpip) / len(self._recent_vpip)

    @property
    def recent_pfr(self):
        if len(self._recent_pfr) < 5:
            return self.pfr
        return sum(self._recent_pfr) / len(self._recent_pfr)

    @property
    def recent_af(self):
        if len(self._recent_af_actions) < 5:
            return self.af
        bets = sum(a[0] for a in self._recent_af_actions)
        calls = sum(a[1] for a in self._recent_af_actions)
        return bets / max(calls, 1)

    @property
    def behavior_changed(self):
        """Detect if recent behavior differs significantly from lifetime."""
        if self.hands_seen < 20 or len(self._recent_vpip) < 10:
            return False
        vpip_diff = abs(self.recent_vpip - self.vpip)
        af_diff = abs(self.recent_af - self.af)
        return vpip_diff > 0.15 or af_diff > 1.5

    def classify(self):
        """Classify player type, using recent stats if behavior changed."""
        if self.hands_seen < 8:
            return 'unknown'

        # Use recent stats if we have enough data AND behavior shifted
        if self.behavior_changed:
            vpip = self.recent_vpip
            af = self.recent_af
            pfr = self.recent_pfr
        else:
            vpip = self.vpip
            af = self.af
            pfr = self.pfr

        if vpip < 0.18:
            return 'nit'
        elif vpip < 0.28 and pfr > 0.15:
            return 'tag'
        elif vpip < 0.35 and pfr > 0.15 and af > 2.0:
            return 'lag'  # VPIP 28-35%, aggressive — loose-aggressive
        elif vpip >= 0.35 and pfr > 0.20 and af > 2.0:
            return 'lag'
        elif vpip >= 0.40 and af < 1.5:
            return 'fish_passive'
        elif vpip >= 0.40 and af >= 2.5:
            return 'maniac'
        elif vpip >= 0.35 and af >= 1.5:
            return 'fish_aggro'
        elif vpip >= 0.28:
            return 'fish_passive'  # VPIP 28-35% but passive — loose-passive
        else:
            return 'tag'

    def to_dict(self):
        return {
            'hands': self.hands_seen,
            'vpip': round(self.vpip, 3),
            'pfr': round(self.pfr, 3),
            'af': round(self.af, 2),
            'cbet': round(self.cbet_pct, 3),
            'fold_to_cbet': round(self.fold_to_cbet, 3),
            'three_bet': round(self.three_bet_pct, 3),
            'wtsd': round(self.wtsd, 3),
            'wsd': round(self.wsd, 3),
            'type': self.classify(),
            'behavior_changed': self.behavior_changed,
            'recent_vpip': round(self.recent_vpip, 3) if len(self._recent_vpip) >= 5 else None,
            'recent_af': round(self.recent_af, 2) if len(self._recent_af_actions) >= 5 else None,
            'last_seen': self.last_seen,
            'pos_stats': {pos: {
                'hands': s['hands'],
                'vpip': round(s['vpip'] / max(s['hands'], 1), 3),
                'pfr': round(s['pfr'] / max(s['hands'], 1), 3),
            } for pos, s in self._pos_stats.items() if s['hands'] >= 5},
        }

    def to_persist(self):
        """Serialize all raw counters for persistence."""
        return {
            'hands_seen': self.hands_seen,
            'vpip_count': self.vpip_count,
            'pfr_count': self.pfr_count,
            'postflop_bets': self.postflop_bets,
            'postflop_calls': self.postflop_calls,
            'postflop_checks': self.postflop_checks,
            'postflop_folds': self.postflop_folds,
            'cbet_opportunities': self.cbet_opportunities,
            'cbet_count': self.cbet_count,
            'fold_to_cbet_opportunities': self.fold_to_cbet_opportunities,
            'fold_to_cbet_count': self.fold_to_cbet_count,
            'three_bet_opportunities': self.three_bet_opportunities,
            'three_bet_count': self.three_bet_count,
            'went_to_showdown': self.went_to_showdown,
            'won_at_showdown': self.won_at_showdown,
            'last_seen': self.last_seen,
            '_pos_stats': self._pos_stats,
            '_recent_vpip': list(self._recent_vpip),
            '_recent_pfr': list(self._recent_pfr),
            '_recent_af_actions': list(self._recent_af_actions),
            '_shown_hands': self._shown_hands[-50:],
        }

    @classmethod
    def from_persist(cls, data):
        """Restore from persisted counters."""
        p = cls()
        for key in ('hands_seen', 'vpip_count', 'pfr_count',
                     'postflop_bets', 'postflop_calls', 'postflop_checks', 'postflop_folds',
                     'cbet_opportunities', 'cbet_count',
                     'fold_to_cbet_opportunities', 'fold_to_cbet_count',
                     'three_bet_opportunities', 'three_bet_count',
                     'went_to_showdown', 'won_at_showdown', 'last_seen'):
            if key in data:
                setattr(p, key, data[key])
        p._pos_stats = data.get('_pos_stats', {})
        from collections import deque
        p._recent_vpip = deque(data.get('_recent_vpip', []), maxlen=15)
        p._recent_pfr = deque(data.get('_recent_pfr', []), maxlen=15)
        raw_af = data.get('_recent_af_actions', [])
        p._recent_af_actions = deque((tuple(x) if isinstance(x, list) else x for x in raw_af), maxlen=20)
        p._shown_hands = data.get('_shown_hands', [])
        return p

    def merge(self, other):
        """Merge another profile's counters into this one (additive)."""
        self.hands_seen += other.hands_seen
        self.vpip_count += other.vpip_count
        self.pfr_count += other.pfr_count
        self.postflop_bets += other.postflop_bets
        self.postflop_calls += other.postflop_calls
        self.postflop_checks += other.postflop_checks
        self.postflop_folds += other.postflop_folds
        self.cbet_opportunities += other.cbet_opportunities
        self.cbet_count += other.cbet_count
        self.fold_to_cbet_opportunities += other.fold_to_cbet_opportunities
        self.fold_to_cbet_count += other.fold_to_cbet_count
        self.three_bet_opportunities += other.three_bet_opportunities
        self.three_bet_count += other.three_bet_count
        self.went_to_showdown += other.went_to_showdown
        self.won_at_showdown += other.won_at_showdown
        self.last_seen = max(self.last_seen, other.last_seen)
        for pos, stats in other._pos_stats.items():
            if pos not in self._pos_stats:
                self._pos_stats[pos] = {'hands': 0, 'vpip': 0, 'pfr': 0}
            self._pos_stats[pos]['hands'] += stats.get('hands', 0)
            self._pos_stats[pos]['vpip'] += stats.get('vpip', 0)
            self._pos_stats[pos]['pfr'] += stats.get('pfr', 0)
        self._recent_vpip.extend(other._recent_vpip)
        self._recent_pfr.extend(other._recent_pfr)
        self._recent_af_actions.extend(other._recent_af_actions)

    def record_position(self, position, vpip=False, pfr=False):
        """Record a hand at a specific position."""
        if position not in self._pos_stats:
            self._pos_stats[position] = {'hands': 0, 'vpip': 0, 'pfr': 0}
        self._pos_stats[position]['hands'] += 1
        if vpip:
            self._pos_stats[position]['vpip'] += 1
        if pfr:
            self._pos_stats[position]['pfr'] += 1

    def get_position_stats(self, position):
        """Get VPIP/PFR for a specific position. Returns None if < 5 hands."""
        ps = self._pos_stats.get(position)
        if not ps or ps['hands'] < 5:
            return None
        return {
            'hands': ps['hands'],
            'vpip': ps['vpip'] / max(ps['hands'], 1),
            'pfr': ps['pfr'] / max(ps['hands'], 1),
        }


class OpponentModeler:
    """Persistent opponent tracker with real-time adaptation."""

    def __init__(self):
        self._profiles = {}  # player_id -> PlayerProfile
        self._current_hand = {}
        self._hands_since_save = 0
        self._save_interval = 10  # Auto-save every N hands
        self._load_profiles()

    def _load_profiles(self):
        """Load persisted profiles from disk."""
        if not os.path.exists(_PROFILE_PATH):
            return
        try:
            with open(_PROFILE_PATH, 'r') as f:
                data = json.load(f)
            for pid, pdata in data.items():
                self._profiles[pid] = PlayerProfile.from_persist(pdata)
            log.info(f"Loaded {len(self._profiles)} opponent profiles from disk")
        except Exception as e:
            log.warning(f"Could not load opponent profiles: {e}")

    def save_profiles(self):
        """Persist all profiles to disk."""
        try:
            os.makedirs(_PROFILE_DIR, exist_ok=True)
            data = {pid: p.to_persist() for pid, p in self._profiles.items()}
            # Prune stale profiles (not seen in 30 days)
            cutoff = time.time() - 30 * 86400
            data = {pid: d for pid, d in data.items()
                    if d.get('last_seen', 0) > cutoff or d.get('hands_seen', 0) > 50}
            with open(_PROFILE_PATH, 'w') as f:
                json.dump(data, f, indent=1)
            log.debug(f"Saved {len(data)} opponent profiles")
        except Exception as e:
            log.warning(f"Could not save opponent profiles: {e}")

    def _maybe_save(self):
        """Auto-save periodically."""
        self._hands_since_save += 1
        if self._hands_since_save >= self._save_interval:
            self.save_profiles()
            self._hands_since_save = 0

    def _get(self, player_id):
        if player_id not in self._profiles:
            self._profiles[player_id] = PlayerProfile()
        self._profiles[player_id].last_seen = time.time()
        return self._profiles[player_id]

    def new_hand(self, player_ids):
        """Call at start of each hand with list of players at the table."""
        self._current_hand = {pid: [] for pid in player_ids}
        for pid in player_ids:
            self._get(pid).hands_seen += 1
        self._maybe_save()

    def record_preflop_action(self, player_id, action, has_raiser_before=False, position=None):
        """Record a preflop action.

        action: 'fold', 'call', 'raise', 'check'
        has_raiser_before: True if someone raised before this player
        """
        p = self._get(player_id)
        act = action.lower()

        if act in ('call', 'raise'):
            p.vpip_count += 1
        if act == 'raise':
            p.pfr_count += 1

        p._recent_vpip.append(act in ('call', 'raise'))
        p._recent_pfr.append(act == 'raise')

        if has_raiser_before:
            p.three_bet_opportunities += 1
            if act == 'raise':
                p.three_bet_count += 1

        if position:
            p.record_position(position, vpip=(act in ('call', 'raise')), pfr=(act == 'raise'))

    def record_postflop_action(self, player_id, action, is_cbet=False,
                                facing_cbet=False):
        """Record a postflop action.

        action: 'fold', 'call', 'raise', 'check', 'bet'
        is_cbet: True if this is a continuation bet by the preflop raiser
        facing_cbet: True if this player is facing a c-bet
        """
        p = self._get(player_id)
        act = action.lower()

        if act in ('bet', 'raise'):
            p.postflop_bets += 1
        elif act == 'call':
            p.postflop_calls += 1
        elif act == 'check':
            p.postflop_checks += 1
        elif act == 'fold':
            p.postflop_folds += 1

        if act in ('bet', 'raise'):
            p._recent_af_actions.append((1, 0))
        elif act == 'call':
            p._recent_af_actions.append((0, 1))

        if is_cbet:
            p.cbet_opportunities += 1
            if act in ('bet', 'raise'):
                p.cbet_count += 1

        if facing_cbet:
            p.fold_to_cbet_opportunities += 1
            if act == 'fold':
                p.fold_to_cbet_count += 1

    def record_showdown(self, player_id, won=False, cards=None, action=None, street=None):
        """Record that a player went to showdown, optionally with their actual cards."""
        p = self._get(player_id)
        p.went_to_showdown += 1
        if won:
            p.won_at_showdown += 1
        if cards and len(cards) >= 2:
            p._shown_hands.append({
                'cards': cards[:2],
                'action': action or 'unknown',
                'street': street or 'unknown',
                'won': won,
            })
            # Keep last 50 showdown hands max
            if len(p._shown_hands) > 50:
                p._shown_hands = p._shown_hands[-50:]

    def get_profile(self, player_id):
        """Get player profile dict. Returns defaults for unknown players."""
        if player_id not in self._profiles:
            return {
                'hands': 0, 'vpip': 0.30, 'pfr': 0.20, 'af': 1.5,
                'cbet': 0.55, 'fold_to_cbet': 0.45, 'three_bet': 0.08,
                'wtsd': 0.25, 'wsd': 0.50, 'type': 'unknown',
                'last_seen': 0,
            }
        return self._profiles[player_id].to_dict()

    def get_adjustment(self, player_id):
        """Get strategy adjustments based on opponent type."""
        profile = self.get_profile(player_id)
        ptype = profile['type']
        adj = {
            'bluff_more': False,
            'value_bet_thinner': False,
            'fold_more_to_aggression': False,
            'call_down_lighter': False,
            'cbet_more': False,
            'fold_equity_bonus': 0.0,
        }

        if ptype == 'nit':
            adj['bluff_more'] = True
            adj['fold_more_to_aggression'] = True
            adj['fold_equity_bonus'] = 0.10
        elif ptype == 'fish_passive':
            adj['value_bet_thinner'] = True
            adj['bluff_more'] = False
            adj['cbet_more'] = True
            adj['fold_equity_bonus'] = -0.10
        elif ptype == 'maniac':
            adj['call_down_lighter'] = True
            adj['bluff_more'] = False
            adj['fold_equity_bonus'] = -0.05
        elif ptype == 'lag':
            adj['call_down_lighter'] = True
            adj['fold_equity_bonus'] = 0.0
        elif ptype == 'tag':
            adj['fold_more_to_aggression'] = True
            adj['fold_equity_bonus'] = 0.05

        if profile['fold_to_cbet'] > 0.60:
            adj['cbet_more'] = True
            adj['fold_equity_bonus'] = max(adj['fold_equity_bonus'], 0.05)
        elif profile['fold_to_cbet'] < 0.30:
            adj['cbet_more'] = False

        return adj

    def infer_opponent_action(self, prev_state, curr_state):
        """Infer what the opponent did between two game states.

        Compares pot sizes, board cards, and game stage to determine
        whether the opponent folded, called, raised, checked, or bet.

        Returns: (action_str, is_preflop, has_raiser_before) or None
        """
        if prev_state is None or curr_state is None:
            return None

        prev_pot = getattr(prev_state, 'pot', 0) or 0
        curr_pot = getattr(curr_state, 'pot', 0) or 0
        prev_board = getattr(prev_state, 'board_cards', []) or []
        curr_board = getattr(curr_state, 'board_cards', []) or []
        prev_stage = len(prev_board)
        curr_stage = len(curr_board)

        # If board changed, a new street started — opponent likely called/checked previous street
        if curr_stage > prev_stage:
            pot_increase = curr_pot - prev_pot
            if pot_increase > 0.5:
                return ('call', prev_stage == 0, False)
            else:
                return ('check', prev_stage == 0, False)

        # Same street — pot change tells us what happened
        pot_diff = curr_pot - prev_pot
        if pot_diff > 0.5:
            # Pot grew — opponent bet or raised
            # If we were the one who bet, this is a raise; otherwise a bet
            if getattr(prev_state, 'is_my_turn', False):
                # We had action last — this is opponent responding
                return ('call', curr_stage == 0, False)
            else:
                return ('bet', curr_stage == 0, curr_stage == 0)
        elif pot_diff <= 0 and curr_stage == prev_stage:
            # No pot change, same street — check
            return ('check', curr_stage == 0, False)

        return None

    def summary(self):
        """Return summary of all tracked players."""
        return {pid: p.to_dict() for pid, p in self._profiles.items()}

    def active_profiles_summary(self):
        """Summary of profiles with 10+ hands (useful for logging)."""
        return {pid: p.to_dict() for pid, p in self._profiles.items()
                if p.hands_seen >= 10}


# Module-level singleton
_modeler = None


def get_modeler():
    global _modeler
    if _modeler is None:
        _modeler = OpponentModeler()
    return _modeler
