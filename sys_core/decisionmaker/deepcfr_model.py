"""
Deep CFR Poker Network — adapted from /tmp/deepcfr/src/core/model.py

The pretrained checkpoint uses a 6-layer FC architecture with:
  - Input:  156 features (52 hand + 52 community + 5 stage + 1 pot + 6 button
            + 6 current_player + 24 player_states + 1 min_bet + 4 legal + 5 prev_action)
  - Hidden: 256 units per layer (fc1-fc5)
  - Output: 4 action logits (Fold, Check/Call, Raise 0.5x pot, Raise 1x pot)

This file defines the network architecture that matches the saved weights,
plus the state-encoding function adapted for our bot's data format.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class DeepCFRNetwork(nn.Module):
    """
    6-layer FC network matching the pretrained checkpoint structure.
    Layer names: fc1..fc6 (not nn.Sequential), matching saved state_dict keys.
    """

    def __init__(self, input_size: int = 156, hidden_size: int = 256, num_actions: int = 4):
        super().__init__()
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.fc3 = nn.Linear(hidden_size, hidden_size)
        self.fc4 = nn.Linear(hidden_size, hidden_size)
        self.fc5 = nn.Linear(hidden_size, hidden_size)
        self.fc6 = nn.Linear(hidden_size, num_actions)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Returns raw logits of shape (batch, num_actions)."""
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        x = F.relu(self.fc4(x))
        x = F.relu(self.fc5(x))
        return self.fc6(x)


# ---------------------------------------------------------------------------
# Card encoding helpers
# ---------------------------------------------------------------------------

# Rank order: 2=0, 3=1, ..., 10=8, J=9, Q=10, K=11, A=12
_RANK_MAP = {
    '2': 0, '3': 1, '4': 2, '5': 3, '6': 4, '7': 5, '8': 6,
    '9': 7, 'T': 8, '10': 8, 'J': 9, 'Q': 10, 'K': 11, 'A': 12,
}

# Suit order must match the original Deep CFR training code (pokers crate):
# Spades=0, Hearts=1, Diamonds=2, Clubs=3
_SUIT_MAP = {'S': 0, 'H': 1, 'D': 2, 'C': 3}


def card_to_index(card_str: str) -> int:
    """
    Convert a card string like 'AH', 'TD', '2C' to a 0-51 index.
    Index = suit * 13 + rank.
    """
    card_str = card_str.upper().strip()
    if len(card_str) == 2:
        rank_ch, suit_ch = card_str[0], card_str[1]
    elif len(card_str) == 3 and card_str[:2] == '10':
        rank_ch, suit_ch = 'T', card_str[2]
    else:
        raise ValueError(f"Cannot parse card: {card_str!r}")

    rank = _RANK_MAP.get(rank_ch)
    suit = _SUIT_MAP.get(suit_ch)
    if rank is None:
        raise ValueError(f"Unknown rank '{rank_ch}' in card '{card_str}'")
    if suit is None:
        raise ValueError(f"Unknown suit '{suit_ch}' in card '{card_str}'")
    return suit * 13 + rank


# ---------------------------------------------------------------------------
# State encoder — mirrors encode_state() from the original Deep CFR code
# but accepts our bot's game-state dict instead of a `pokers` State object.
# ---------------------------------------------------------------------------

def encode_game_state(
    hero_cards: list,           # ['AH', 'KS']
    community_cards: list,      # ['JD', '7C', '2H'] or []
    stage: str,                 # 'PreFlop', 'Flop', 'Turn', 'River'
    pot: float,                 # total pot in BB
    hero_stack: float,          # hero remaining stack in BB
    hero_bet: float,            # hero's current-street bet in BB
    villain_stacks: list,       # [stack_bb, ...] for each opponent seat
    villain_bets: list,         # [bet_bb, ...] for each opponent seat
    villain_active: list,       # [True/False, ...] for each opponent seat
    button_seat: int,           # 0-5 which seat has the button
    hero_seat: int,             # 0-5 hero's seat index
    min_bet: float,             # minimum bet to call in BB
    can_fold: bool,
    can_check: bool,
    can_call: bool,
    can_raise: bool,
    prev_action_type: int = -1, # -1=none, 0=fold, 1=check, 2=call, 3=raise
    prev_action_amount: float = 0.0,
    num_players: int = 6,
) -> np.ndarray:
    """
    Encode game state into a 156-dim feature vector matching the
    Deep CFR training format (for 6-max).

    The encoding order follows the original `encode_state()`:
      [hand_52] [community_52] [stage_5] [pot_1] [button_6] [current_player_6]
      [player_states_6×4] [min_bet_1] [legal_actions_4] [prev_action_5]
    Total: 52 + 52 + 5 + 1 + 6 + 6 + 24 + 1 + 4 + 5 = 156
    """
    encoded = []

    # 1. Hero hand (52-bit one-hot)
    hand_enc = np.zeros(52, dtype=np.float32)
    for c in hero_cards:
        try:
            hand_enc[card_to_index(c)] = 1.0
        except ValueError:
            pass  # skip unparseable cards
    encoded.append(hand_enc)

    # 2. Community cards (52-bit one-hot)
    community_enc = np.zeros(52, dtype=np.float32)
    for c in community_cards:
        try:
            community_enc[card_to_index(c)] = 1.0
        except ValueError:
            pass
    encoded.append(community_enc)

    # 3. Game stage (5-dim one-hot: preflop, flop, turn, river, showdown)
    stage_enc = np.zeros(5, dtype=np.float32)
    stage_map = {'preflop': 0, 'flop': 1, 'turn': 2, 'river': 3, 'showdown': 4}
    stage_idx = stage_map.get(stage.lower(), 0)
    stage_enc[stage_idx] = 1.0
    encoded.append(stage_enc)

    # 4. Pot (normalized by initial stake = hero_stack + hero_bet as proxy)
    initial_stake = max(hero_stack + hero_bet, 1.0)
    pot_enc = np.array([pot / initial_stake], dtype=np.float32)
    encoded.append(pot_enc)

    # 5. Button position (6-dim one-hot)
    button_enc = np.zeros(num_players, dtype=np.float32)
    button_enc[min(button_seat, num_players - 1)] = 1.0
    encoded.append(button_enc)

    # 6. Current player = hero (6-dim one-hot)
    current_enc = np.zeros(num_players, dtype=np.float32)
    current_enc[min(hero_seat, num_players - 1)] = 1.0
    encoded.append(current_enc)

    # 7. Player states: for each of 6 seats, encode [active, bet, pot_chips, stake]
    # We map hero to seat 0 conceptually, and fill villains from our data.
    # Order: iterate seat 0..5 in the game. Hero is at hero_seat.
    for p in range(num_players):
        if p == hero_seat:
            active = 1.0
            bet = hero_bet / initial_stake
            pot_chips = 0.0  # we don't track won side-pots mid-hand
            stake = hero_stack / initial_stake
        else:
            # Map to villain index
            v_idx = p if p < hero_seat else p - 1
            if v_idx < len(villain_stacks):
                active = 1.0 if villain_active[v_idx] else 0.0
                bet = villain_bets[v_idx] / initial_stake if v_idx < len(villain_bets) else 0.0
                pot_chips = 0.0
                stake = villain_stacks[v_idx] / initial_stake
            else:
                active = 0.0
                bet = 0.0
                pot_chips = 0.0
                stake = 0.0
        encoded.append(np.array([active, bet, pot_chips, stake], dtype=np.float32))

    # 8. Min bet (normalized)
    min_bet_enc = np.array([min_bet / initial_stake], dtype=np.float32)
    encoded.append(min_bet_enc)

    # 9. Legal actions (4-dim: Fold, Check, Call, Raise)
    legal_enc = np.zeros(4, dtype=np.float32)
    if can_fold:
        legal_enc[0] = 1.0
    if can_check:
        legal_enc[1] = 1.0
    if can_call:
        legal_enc[2] = 1.0
    if can_raise:
        legal_enc[3] = 1.0
    encoded.append(legal_enc)

    # 10. Previous action (4 one-hot + 1 amount = 5 dims)
    prev_enc = np.zeros(5, dtype=np.float32)
    if 0 <= prev_action_type <= 3:
        prev_enc[prev_action_type] = 1.0
        prev_enc[4] = prev_action_amount / initial_stake
    encoded.append(prev_enc)

    return np.concatenate(encoded)
