# src/code/model.py
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

VERBOSE = False

def set_verbose(verbose_mode):
    """Set the global verbosity level"""
    global VERBOSE
    VERBOSE = verbose_mode

class PokerNetwork(nn.Module):
    """Poker network with continuous bet sizing capabilities."""
    def __init__(self, input_size=500, hidden_size=256, num_actions=3):
        super().__init__()
        # Shared feature extraction layers
        self.base = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU()
        )
        # Action type prediction (fold, check/call, raise)
        self.action_head = nn.Linear(hidden_size, num_actions)
        # Continuous bet sizing prediction
        self.sizing_head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.Tanh(),
            nn.Linear(hidden_size // 2, 1),
            nn.Sigmoid()  # Output between 0-1
        )
    
    def forward(self, x, opponent_features=None): # NOTE: We are accepting and ignoring opponent_features because not used in train.py but I think keeping the call the same will help with future potencial crossplay.
        """
        Forward pass through the network.
        
        Args:
            x: The state representation tensor
            opponent_features: Optional opponent modeling features (ignored in base class)
            
        Returns:
            Tuple of (action_logits, bet_size_prediction)
        """
        # Process base features
        features = self.base(x)
        
        # Output action logits and bet sizing
        action_logits = self.action_head(features)
        bet_size = 0.1 + 2.9 * self.sizing_head(features)
        
        return action_logits, bet_size

def encode_state(state, player_id=0):
    """
    Convert a Pokers state to a neural network input tensor.
    
    Args:
        state: The Pokers state
        player_id: The ID of the player for whom we're encoding
    """
    encoded = []
    num_players = len(state.players_state)
    
    # Print debug info only if verbose
    if VERBOSE:
        print(f"Encoding state: current_player={state.current_player}, stage={state.stage}")
        print(f"Player states: {[(p.player, p.stake, p.bet_chips) for p in state.players_state]}")
        print(f"Pot: {state.pot}")
    
    # Encode player's hole cards
    hand_cards = state.players_state[player_id].hand
    hand_enc = np.zeros(52)
    for card in hand_cards:
        card_idx = int(card.suit) * 13 + int(card.rank)
        hand_enc[card_idx] = 1
    encoded.append(hand_enc)
    
    # Encode community cards
    community_enc = np.zeros(52)
    for card in state.public_cards:
        card_idx = int(card.suit) * 13 + int(card.rank)
        community_enc[card_idx] = 1
    encoded.append(community_enc)
    
    # Encode game stage
    stage_enc = np.zeros(5)  # Preflop, Flop, Turn, River, Showdown
    stage_enc[int(state.stage)] = 1
    encoded.append(stage_enc)
    
    # Get initial stake - prevent division by zero
    initial_stake = state.players_state[0].stake
    if initial_stake <= 0:
        if VERBOSE:
            print(f"WARNING: Initial stake is zero or negative: {initial_stake}")
        initial_stake = 1.0  # Use 1.0 as a fallback to prevent division by zero
    
    # Encode pot size (normalized by initial stake)
    pot_enc = [state.pot / initial_stake]
    encoded.append(pot_enc)
    
    # Encode button position
    button_enc = np.zeros(num_players)
    button_enc[state.button] = 1
    encoded.append(button_enc)
    
    # Encode current player
    current_player_enc = np.zeros(num_players)
    current_player_enc[state.current_player] = 1
    encoded.append(current_player_enc)
    
    # Encode player states
    for p in range(num_players):
        player_state = state.players_state[p]
        
        # Active status
        active_enc = [1.0 if player_state.active else 0.0]
        
        # Current bet
        bet_enc = [player_state.bet_chips / initial_stake]
        
        # Pot chips (already won)
        pot_chips_enc = [player_state.pot_chips / initial_stake]
        
        # Remaining stake
        stake_enc = [player_state.stake / initial_stake]
        
        encoded.append(np.concatenate([active_enc, bet_enc, pot_chips_enc, stake_enc]))
    
    # Encode minimum bet
    min_bet_enc = [state.min_bet / initial_stake]
    encoded.append(min_bet_enc)
    
    # Encode legal actions
    legal_actions_enc = np.zeros(4)  # Fold, Check, Call, Raise
    for action_enum in state.legal_actions:
        legal_actions_enc[int(action_enum)] = 1
    encoded.append(legal_actions_enc)
    
    # Encode previous action if available
    prev_action_enc = np.zeros(4 + 1)  # Action type + normalized amount
    if state.from_action is not None:
        prev_action_enc[int(state.from_action.action.action)] = 1
        prev_action_enc[4] = state.from_action.action.amount / initial_stake
    encoded.append(prev_action_enc)
    
    # Concatenate all features
    return np.concatenate(encoded)