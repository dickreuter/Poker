# deep_cfr.py — Original Deep CFR agent from /tmp/deepcfr/src/core/deep_cfr.py
# Copied for reference. The `pokers` (Rust) library is required for training.
# For inference only, use deepcfr_wrapper.py instead.
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
import random
try:
    import pokers as pkrs
except ImportError:
    pkrs = None  # Not needed for inference-only usage
from collections import deque
from sys_core.decisionmaker.deepcfr_model_original import PokerNetwork, encode_state, VERBOSE, set_verbose

# These are optional — only needed for training
STRICT_CHECKING = False
def log_game_error(*args, **kwargs): return None


def _resolve_model_save_path(path_prefix, iteration):
    """Accept either a path prefix or an explicit .pt filename."""
    if str(path_prefix).endswith(".pt"):
        return str(path_prefix)
    return f"{path_prefix}_iteration_{iteration}.pt"

class PrioritizedMemory:
    """Enhanced memory buffer with prioritized experience replay."""
    def __init__(self, capacity, alpha=0.6):
        """
        Initialize memory buffer with prioritized experience replay.
        
        Args:
            capacity: Maximum number of experiences to store
            alpha: Controls how much prioritization is used (0 = no prioritization, 1 = full prioritization)
        """
        self.capacity = capacity
        self.alpha = alpha
        self.buffer = []
        self.priorities = []
        self.position = 0
        self._max_priority = 1.0  # Initial max priority for new experiences
        
    def add(self, experience, priority=None):
        """
        Add a new experience to memory with its priority.
        
        Args:
            experience: Tuple of (state, opponent_features, action_type, bet_size, regret)
            priority: Optional explicit priority value (defaults to max priority if None)
        """
        if priority is None:
            priority = self._max_priority
            
        if len(self.buffer) < self.capacity:
            self.buffer.append(experience)
            self.priorities.append(priority ** self.alpha)
        else:
            # Replace the oldest entry
            self.buffer[self.position] = experience
            self.priorities[self.position] = priority ** self.alpha
            
        self.position = (self.position + 1) % self.capacity
        
    def sample(self, batch_size, beta=0.4):
        """
        Sample a batch of experiences based on their priorities.
        
        Args:
            batch_size: Number of experiences to sample
            beta: Controls importance sampling correction (0 = no correction, 1 = full correction)
                 Should be annealed from ~0.4 to 1 during training
                 
        Returns:
            Tuple of (samples, indices, importance_sampling_weights)
        """
        if len(self.buffer) < batch_size:
            # If we don't have enough samples, return all with equal weights
            return self.buffer, list(range(len(self.buffer))), np.ones(len(self.buffer))
        
        # Convert priorities to probabilities
        total_priority = sum(self.priorities)
        probabilities = [p / total_priority for p in self.priorities]
        
        # Sample indices based on priorities
        indices = np.random.choice(len(self.buffer), batch_size, p=probabilities, replace=False)
        samples = [self.buffer[idx] for idx in indices]
        
        # Calculate importance sampling weights
        weights = []
        for idx in indices:
            # P(i) = p_i^α / sum_k p_k^α
            # weight = (1/N * 1/P(i))^β = (N*P(i))^-β
            sample_prob = self.priorities[idx] / total_priority
            weight = (len(self.buffer) * sample_prob) ** -beta
            weights.append(weight)
        
        # Normalize weights to have maximum weight = 1
        # This ensures we only scale down updates, never up
        max_weight = max(weights)
        weights = [w / max_weight for w in weights]
        
        return samples, indices, np.array(weights, dtype=np.float32)
        
    def update_priority(self, index, priority):
        """
        Update the priority of an experience.
        
        Args:
            index: Index of the experience to update
            priority: New priority value (before alpha adjustment)
        """
        # Clip priority to be positive
        priority = max(1e-8, priority)
        
        # Keep track of max priority for new experience initialization
        self._max_priority = max(self._max_priority, priority)
        
        # Store alpha-adjusted priority
        self.priorities[index] = priority ** self.alpha
        
    def __len__(self):
        """Return the current size of the memory."""
        return len(self.buffer)
        
    def get_memory_stats(self):
        """Get statistics about the current memory buffer."""
        if not self.priorities:
            return {"min": 0, "max": 0, "mean": 0, "median": 0, "size": 0}
            
        raw_priorities = [p ** (1/self.alpha) for p in self.priorities]
        return {
            "min": min(raw_priorities),
            "max": max(raw_priorities),
            "mean": sum(raw_priorities) / len(raw_priorities),
            "median": sorted(raw_priorities)[len(raw_priorities) // 2],
            "size": len(self.buffer)
        }

class DeepCFRAgent:
    def __init__(self, player_id=0, num_players=6, memory_size=300000, device='cpu'):
        self.player_id = player_id
        self.num_players = num_players
        self.device = device
        
        # Define action types (Fold, Check/Call, Raise)
        self.num_actions = 3
        
        # Calculate input size based on state encoding
        input_size = 52 + 52 + 5 + 1 + num_players + num_players + num_players*4 + 1 + 4 + 5
        
        # Create advantage network with bet sizing
        self.advantage_net = PokerNetwork(input_size=input_size, hidden_size=256, num_actions=self.num_actions).to(device)
        
        # Use a smaller learning rate for more stable training
        self.optimizer = optim.Adam(self.advantage_net.parameters(), lr=1e-6, weight_decay=1e-5)
        
        # Create prioritized memory buffer
        self.advantage_memory = PrioritizedMemory(memory_size)
        
        # Strategy network
        self.strategy_net = PokerNetwork(input_size=input_size, hidden_size=256, num_actions=self.num_actions).to(device)
        self.strategy_optimizer = optim.Adam(self.strategy_net.parameters(), lr=0.00005, weight_decay=1e-5)
        self.strategy_memory = deque(maxlen=memory_size)
        
        # For keeping statistics
        self.iteration_count = 0
        
        # Regret normalization tracker
        self.max_regret_seen = 1.0
        
        # Bet sizing bounds (as multipliers of pot)
        self.min_bet_size = 0.1
        self.max_bet_size = 3.0

    def action_type_to_pokers_action(self, action_type, state, bet_size_multiplier=None):
        """
        Convert action type and optional bet size to Pokers action.
        (Refined Raise Logic with Float Safeguard)
        """
        # Access VERBOSE, assuming it's set globally or accessible (e.g., self.verbose if it's an instance attr)
        # For this example, I'll assume VERBOSE is a global imported from your model.py or utils
        # If VERBOSE is an instance variable like self.verbose, use that instead.
        # from src.core.model import VERBOSE # Make sure this import is at the top of the file or VERBOSE is otherwise in scope

        try:
            if action_type == 0:  # Fold
                if pkrs.ActionEnum.Fold in state.legal_actions:
                    return pkrs.Action(pkrs.ActionEnum.Fold)
                # Fallback logic for Fold
                if pkrs.ActionEnum.Check in state.legal_actions: return pkrs.Action(pkrs.ActionEnum.Check)
                if pkrs.ActionEnum.Call in state.legal_actions: return pkrs.Action(pkrs.ActionEnum.Call)
                if VERBOSE: print(f"DeepCFRAgent WARNING: Fold chosen but no other legal fallback. Returning Fold anyway.")
                return pkrs.Action(pkrs.ActionEnum.Fold) # Last resort

            elif action_type == 1:  # Check/Call
                if pkrs.ActionEnum.Check in state.legal_actions:
                    return pkrs.Action(pkrs.ActionEnum.Check)
                elif pkrs.ActionEnum.Call in state.legal_actions:
                    return pkrs.Action(pkrs.ActionEnum.Call)
                # Fallback logic for Check/Call
                if pkrs.ActionEnum.Fold in state.legal_actions: return pkrs.Action(pkrs.ActionEnum.Fold)
                if VERBOSE: print(f"DeepCFRAgent WARNING: Check/Call chosen but neither legal, nor Fold. Returning Check anyway.")
                return pkrs.Action(pkrs.ActionEnum.Check) # Last resort

            elif action_type == 2:  # Raise
                if pkrs.ActionEnum.Raise not in state.legal_actions:
                    # If Raise is not legal, fall back
                    if VERBOSE: print(f"DeepCFRAgent INFO: Raise (type 2) chosen, but Raise not in legal_actions. Falling back.")
                    if pkrs.ActionEnum.Call in state.legal_actions: return pkrs.Action(pkrs.ActionEnum.Call)
                    if pkrs.ActionEnum.Check in state.legal_actions: return pkrs.Action(pkrs.ActionEnum.Check)
                    return pkrs.Action(pkrs.ActionEnum.Fold)

                player_state = state.players_state[state.current_player]
                current_bet = player_state.bet_chips        # What player already has in pot this round
                available_stake = player_state.stake        # Player's remaining chips

                call_amount = max(0.0, state.min_bet - current_bet) # Additional chips needed to call

                min_raise_increment = 1.0
                if hasattr(state, 'bb') and state.bb is not None and float(state.bb) > 0:
                    min_raise_increment = max(1.0, float(state.bb))
                elif state.min_bet > 0 : # If no BB, use min_bet if it implies a raise size
                     # This part is a bit heuristic if BB is not well-defined.
                     # The idea is that a raise should be somewhat meaningful.
                     # If last bet was X, min_raise_increment is often X.
                     # For simplicity, we'll stick to a small fixed minimum or BB.
                     # A more robust way might involve looking at the previous raise amount.
                     min_raise_increment = max(1.0, state.min_bet - current_bet if state.min_bet > current_bet else 1.0)


                # --- Initial Check: Can the player make ANY valid raise? ---
                # A valid raise means calling and then adding at least min_raise_increment.
                if available_stake < call_amount + min_raise_increment:
                    if VERBOSE:
                        print(f"DeepCFRAgent INFO: Raise (type 2) chosen, but cannot make a valid min_raise_increment. "
                              f"AvailableStake({available_stake:.2f}) < CallAmt({call_amount:.2f}) + MinInc({min_raise_increment:.2f}). Switching to Call.")
                    if pkrs.ActionEnum.Call in state.legal_actions:
                        return pkrs.Action(pkrs.ActionEnum.Call)
                    else:
                        if VERBOSE: print(f"DeepCFRAgent WARNING: Cannot Call (not legal after failing raise check), falling back to Fold.")
                        return pkrs.Action(pkrs.ActionEnum.Fold)
                # --- End Initial Check ---

                remaining_stake_after_call = available_stake - call_amount

                # Get target additional raise from network's bet_size_multiplier
                pot_size = max(1.0, state.pot)

                if bet_size_multiplier is None:
                    bet_size_multiplier = 1.0 # Default if not provided
                else:
                    bet_size_multiplier = float(bet_size_multiplier)
                    # Optional: self.adjust_bet_size(state, bet_size_multiplier) if you use it

                bet_size_multiplier = max(self.min_bet_size, min(self.max_bet_size, bet_size_multiplier))
                network_desired_additional_raise = pot_size * bet_size_multiplier

                # Determine chosen_additional_amount based on network and game rules
                chosen_additional_amount = network_desired_additional_raise
                # Clip 1: Cannot raise more than all-in (remaining_stake_after_call)
                chosen_additional_amount = min(chosen_additional_amount, remaining_stake_after_call)
                # Clip 2: Must raise at least min_raise_increment
                chosen_additional_amount = max(chosen_additional_amount, min_raise_increment)

                # Safeguard: If due to clipping (e.g. min_raise_increment was > remaining_stake_after_call,
                # which shouldn't happen if initial check was correct), ensure it's not > remaining_stake_after_call.
                # This makes it an all-in if min_raise_increment forces it.
                if chosen_additional_amount > remaining_stake_after_call:
                    chosen_additional_amount = remaining_stake_after_call
                
                # --- START: FLOAT SAFEGUARD ---
                total_chips_player_would_commit_this_turn = call_amount + chosen_additional_amount
                epsilon = 0.00001  # Tolerance for float comparisons

                if total_chips_player_would_commit_this_turn > available_stake + epsilon:
                    if VERBOSE:
                        print(f"DeepCFRAgent INFO: Float Safeguard in action_type_to_pokers_action triggered.")
                        print(f"  Initial chosen_additional_amount: {chosen_additional_amount:.6f}")
                        print(f"  Total commit ({total_chips_player_would_commit_this_turn:.6f}) > available_stake ({available_stake:.6f})")

                    chosen_additional_amount = available_stake - call_amount
                    chosen_additional_amount = max(0.0, chosen_additional_amount) # Ensure not negative

                    if VERBOSE:
                        print(f"  Adjusted chosen_additional_amount: {chosen_additional_amount:.6f}")
                        print(f"  New total commit: {(call_amount + chosen_additional_amount):.6f}")
                # --- END: FLOAT SAFEGUARD ---

                # Ensure chosen_additional_amount is not negative after all adjustments
                chosen_additional_amount = max(0.0, chosen_additional_amount)

                if VERBOSE:
                    print(f"--- DeepCFRAgent Raise Calculation (FINAL PRE-RETURN) ---")
                    print(f"  Player ID: {state.current_player}, Stage: {state.stage}")
                    print(f"  Available Stake: {available_stake:.6f}, Current Bet In Pot: {current_bet:.6f}")
                    print(f"  State Min Bet (to call): {state.min_bet:.6f}, Pot Size: {state.pot:.6f}")
                    print(f"  Calculated Call Amount: {call_amount:.6f}")
                    print(f"  Min Raise Increment: {min_raise_increment:.6f}")
                    print(f"  Remaining Stake After Call: {remaining_stake_after_call:.6f}")
                    print(f"  Bet Size Multiplier (from net, raw): {float(bet_size_multiplier) if bet_size_multiplier is not None else 'N/A'}, (used, clipped): {bet_size_multiplier:.6f}")
                    print(f"  Network Desired Additional Raise (pot * mult): {network_desired_additional_raise:.6f}")
                    print(f"  Chosen Additional Raise Amount (pre-float-guard): {network_desired_additional_raise:.6f} -> clipped by rules to -> {chosen_additional_amount+epsilon if total_chips_player_would_commit_this_turn > available_stake + epsilon else chosen_additional_amount:.6f}") # Show value before float guard if it triggered
                    print(f"  Final Chosen Additional Raise Amount (post-float-guard): {chosen_additional_amount:.6f}")
                    _total_chips_this_action = call_amount + chosen_additional_amount
                    print(f"  Total Chips for this action (call + additional): {_total_chips_this_action:.6f}")
                    _is_exact_all_in = abs(_total_chips_this_action - available_stake) < epsilon
                    print(f"  Is this an exact all-in (post-safeguard)? {_is_exact_all_in}")
                    if _is_exact_all_in: print(f"    All-in Difference: {(_total_chips_this_action - available_stake):.10f}")
                    print(f"--------------------------------------------------------------------")

                return pkrs.Action(pkrs.ActionEnum.Raise, chosen_additional_amount)

            else: # Should not be reached if action_type is 0, 1, or 2
                if VERBOSE: print(f"DeepCFRAgent ERROR: Unknown action type: {action_type}")
                if pkrs.ActionEnum.Call in state.legal_actions: return pkrs.Action(pkrs.ActionEnum.Call)
                if pkrs.ActionEnum.Check in state.legal_actions: return pkrs.Action(pkrs.ActionEnum.Check)
                return pkrs.Action(pkrs.ActionEnum.Fold)

        except Exception as e:
            # Ensure VERBOSE is accessible here or handle its absence
            try:
                is_verbose = VERBOSE
            except NameError:
                is_verbose = False # Default if VERBOSE is not defined in this scope

            if is_verbose: # Or self.verbose if it's an instance attribute
                print(f"DeepCFRAgent CRITICAL ERROR in action_type_to_pokers_action: Type {action_type} for player {self.player_id}: {e}")
                print(f"  State: current_player={state.current_player}, stage={state.stage}, legal_actions={state.legal_actions}")
                if hasattr(state, 'players_state') and self.player_id < len(state.players_state):
                    print(f"  Player {self.player_id} stake: {state.players_state[self.player_id].stake}, bet: {state.players_state[self.player_id].bet_chips}")
                else:
                    print(f"  Player state for player {self.player_id} not accessible.")
                import traceback
                traceback.print_exc()

            # Fall back to a safe action
            if hasattr(state, 'legal_actions'):
                if pkrs.ActionEnum.Call in state.legal_actions: return pkrs.Action(pkrs.ActionEnum.Call)
                if pkrs.ActionEnum.Check in state.legal_actions: return pkrs.Action(pkrs.ActionEnum.Check)
                if pkrs.ActionEnum.Fold in state.legal_actions: return pkrs.Action(pkrs.ActionEnum.Fold)
            
            # Absolute last resort if state.legal_actions is not even available or empty
            return pkrs.Action(pkrs.ActionEnum.Fold)

    def adjust_bet_size(self, state, base_multiplier):
        """
        Dynamically adjust bet size multiplier based on game state.
        
        Args:
            state: Current poker game state
            base_multiplier: Base bet size multiplier from the model
            
        Returns:
            Adjusted bet size multiplier
        """
        # Default adjustment factor
        adjustment = 1.0
        
        # Adjust based on game stage
        if int(state.stage) >= 2:  # Turn or River
            adjustment *= 1.2  # Increase bets in later streets
        
        # Adjust based on pot size relative to starting stack
        initial_stake = state.players_state[0].stake + state.players_state[0].bet_chips
        pot_ratio = state.pot / initial_stake
        if pot_ratio > 0.5:  # Large pot
            adjustment *= 1.1  # Bet bigger in large pots
        elif pot_ratio < 0.1:  # Small pot
            adjustment *= 0.9  # Bet smaller in small pots
        
        # Adjust based on position (more aggressive in late position)
        btn_distance = (state.current_player - state.button) % len(state.players_state)
        if btn_distance <= 1:  # Button or cutoff
            adjustment *= 1.15  # More aggressive in late position
        elif btn_distance >= 4:  # Early position
            adjustment *= 0.9  # Less aggressive in early position
        
        # Adjust for number of active players (larger with fewer players)
        active_players = sum(1 for p in state.players_state if p.active)
        if active_players <= 2:
            adjustment *= 1.2  # Larger bets heads-up
        elif active_players >= 5:
            adjustment *= 0.9  # Smaller bets multiway
        
        # Apply adjustment to base multiplier
        adjusted_multiplier = base_multiplier * adjustment
        
        # Ensure we stay within bounds
        return max(self.min_bet_size, min(self.max_bet_size, adjusted_multiplier))

    def get_legal_action_types(self, state):
        """Get the legal action types for the current state."""
        legal_action_types = []
        
        # Check each action type
        if pkrs.ActionEnum.Fold in state.legal_actions:
            legal_action_types.append(0)
            
        if pkrs.ActionEnum.Check in state.legal_actions or pkrs.ActionEnum.Call in state.legal_actions:
            legal_action_types.append(1)
            
        if pkrs.ActionEnum.Raise in state.legal_actions:
            legal_action_types.append(2)
        
        return legal_action_types

    def cfr_traverse(self, state, iteration, random_agents, depth=0):
        """
        Traverse the game tree using external sampling MCCFR with continuous bet sizing.
        
        Args:
            state: Current game state
            iteration: Current training iteration
            random_agents: List of opponent agents
            depth: Current recursion depth
            
        Returns:
            Expected value for the current player
        """
        # Add recursion depth protection
        max_depth = 1000
        if depth > max_depth:
            if VERBOSE:
                print(f"WARNING: Max recursion depth reached ({max_depth}). Returning zero value.")
            return 0
        
        if state.final_state:
            # Return payoff for the trained agent
            return state.players_state[self.player_id].reward
        
        current_player = state.current_player
        
        # If it's the trained agent's turn
        if current_player == self.player_id:
            legal_action_types = self.get_legal_action_types(state)
            
            if not legal_action_types:
                if VERBOSE:
                    print(f"WARNING: No legal actions found for player {current_player} at depth {depth}")
                return 0
                
            # Encode the base state
            state_tensor = torch.FloatTensor(encode_state(state, self.player_id)).to(self.device)
            
            # Get advantages and bet sizing prediction from network
            with torch.no_grad():
                advantages, bet_size_pred = self.advantage_net(state_tensor.unsqueeze(0))
                advantages = advantages[0].cpu().numpy()
                bet_size_multiplier = bet_size_pred[0][0].item()
            
            # Use regret matching to compute strategy for action types
            advantages_masked = np.zeros(self.num_actions)
            for a in legal_action_types:
                advantages_masked[a] = max(advantages[a], 0)
                
            # Choose an action based on the strategy
            if sum(advantages_masked) > 0:
                strategy = advantages_masked / sum(advantages_masked)
            else:
                strategy = np.zeros(self.num_actions)
                for a in legal_action_types:
                    strategy[a] = 1.0 / len(legal_action_types)
            
            # Choose actions and traverse
            action_values = np.zeros(self.num_actions)
            for action_type in legal_action_types:
                try:
                    # Use the predicted bet size for raise actions
                    if action_type == 2:  # Raise
                        pokers_action = self.action_type_to_pokers_action(action_type, state, bet_size_multiplier)
                    else:
                        pokers_action = self.action_type_to_pokers_action(action_type, state)
                    
                    new_state = state.apply_action(pokers_action)
                    
                    # Check if the action was valid
                    if new_state.status != pkrs.StateStatus.Ok:
                        log_file = log_game_error(state, pokers_action, f"State status not OK ({new_state.status})")
                        if STRICT_CHECKING:
                            raise ValueError(f"State status not OK ({new_state.status}) during CFR traversal. Details logged to {log_file}")
                        elif VERBOSE:
                            print(f"WARNING: Invalid action {action_type} at depth {depth}. Status: {new_state.status}")
                            print(f"Player: {current_player}, Action: {pokers_action.action}, Amount: {pokers_action.amount if pokers_action.action == pkrs.ActionEnum.Raise else 'N/A'}")
                            print(f"Current bet: {state.players_state[current_player].bet_chips}, Stake: {state.players_state[current_player].stake}")
                            print(f"Details logged to {log_file}")
                        continue  # Skip this action and try others in non-strict mode
                        
                    action_values[action_type] = self.cfr_traverse(new_state, iteration, random_agents, depth + 1)
                except Exception as e:
                    if VERBOSE:
                        print(f"ERROR in traversal for action {action_type}: {e}")
                    action_values[action_type] = 0
                    if STRICT_CHECKING:
                        raise  # Re-raise in strict mode
            
            # Compute counterfactual regrets and add to memory
            ev = sum(strategy[a] * action_values[a] for a in legal_action_types)
            
            # Calculate normalization factor
            max_abs_val = max(abs(max(action_values)), abs(min(action_values)), 1.0)
            
            for action_type in legal_action_types:
                # Calculate regret
                regret = action_values[action_type] - ev
                
                # Normalize and clip regret
                normalized_regret = regret / max_abs_val
                clipped_regret = np.clip(normalized_regret, -10.0, 10.0)
                
                # Apply scaling
                scale_factor = np.sqrt(iteration) if iteration > 1 else 1.0  # Linear CFR
                weighted_regret = clipped_regret * scale_factor
                
                # Store in prioritized memory with regret magnitude as priority
                priority = abs(weighted_regret) + 0.01  # Add small constant to ensure non-zero priority
                
                # For raise actions, store the bet size multiplier
                if action_type == 2:
                    self.advantage_memory.add(
                        (encode_state(state, self.player_id), 
                         np.zeros(20),  # placeholder for opponent features 
                         action_type, 
                         bet_size_multiplier, 
                         weighted_regret),
                        priority
                    )
                else:
                    self.advantage_memory.add(
                        (encode_state(state, self.player_id),
                         np.zeros(20),  # placeholder for opponent features
                         action_type, 
                         0.0,  # Default bet size for non-raise actions 
                         weighted_regret),
                        priority
                    )
            
            # Add to strategy memory
            strategy_full = np.zeros(self.num_actions)
            for a in legal_action_types:
                strategy_full[a] = strategy[a]
            
            self.strategy_memory.append((
                encode_state(state, self.player_id),
                np.zeros(20),  # placeholder for opponent features
                strategy_full,
                bet_size_multiplier if 2 in legal_action_types else 0.0,
                iteration
            ))
            
            return ev
            
        # If it's another player's turn (random agent)
        else:
            try:
                # Let the random agent choose an action
                action = random_agents[current_player].choose_action(state)
                new_state = state.apply_action(action)
                
                # Check if the action was valid
                if new_state.status != pkrs.StateStatus.Ok:
                    log_file = log_game_error(state, action, f"State status not OK ({new_state.status})")
                    if STRICT_CHECKING:
                        raise ValueError(f"State status not OK ({new_state.status}) from random agent. Details logged to {log_file}")
                    if VERBOSE:
                        print(f"WARNING: Random agent made invalid action at depth {depth}. Status: {new_state.status}")
                        print(f"Details logged to {log_file}")
                    return 0
                    
                return self.cfr_traverse(new_state, iteration, random_agents, depth + 1)
            except Exception as e:
                if VERBOSE:
                    print(f"ERROR in random agent traversal: {e}")
                if STRICT_CHECKING:
                    raise  # Re-raise in strict mode
                return 0

    def train_advantage_network(self, batch_size=128, epochs=3, beta_start=0.4, beta_end=1.0):
        """
        Train the advantage network using prioritized experience replay.
        """
        if len(self.advantage_memory) < batch_size:
            return 0
        
        self.advantage_net.train()
        total_loss = 0
        
        # Calculate current beta for importance sampling
        progress = min(1.0, self.iteration_count / 10000)
        beta = beta_start + progress * (beta_end - beta_start)
        
        for epoch in range(epochs):
            # Sample batch from prioritized memory with current beta
            batch, indices, weights = self.advantage_memory.sample(batch_size, beta=beta)
            states, opponent_features, action_types, bet_sizes, regrets = zip(*batch)
            
            # [DEBUG 1] Log regret values in memory
            if self.iteration_count % 10 == 0 and epoch == 0:
                regret_array = np.array(regrets)
                print(f"[DEBUG-MEMORY] Regret stats: min={np.min(regret_array):.2f}, max={np.max(regret_array):.2f}, mean={np.mean(regret_array):.2f}")
            
            # Convert to tensors
            state_tensors = torch.FloatTensor(np.array(states)).to(self.device)
            opponent_feature_tensors = torch.FloatTensor(np.array(opponent_features)).to(self.device)
            action_type_tensors = torch.LongTensor(np.array(action_types)).to(self.device)
            bet_size_tensors = torch.FloatTensor(np.array(bet_sizes)).unsqueeze(1).to(self.device)
            regret_tensors = torch.FloatTensor(np.array(regrets)).to(self.device)
            weight_tensors = torch.FloatTensor(weights).to(self.device)
            
            # Forward pass
            action_advantages, bet_size_preds = self.advantage_net(state_tensors, opponent_feature_tensors)
            
            # [DEBUG 2] Log network raw outputs to identify explosion
            if self.iteration_count % 10 == 0 and epoch == 0:
                with torch.no_grad():
                    max_adv = torch.max(action_advantages).item()
                    min_adv = torch.min(action_advantages).item()
                    print(f"[DEBUG-NETWORK] Network outputs: min={min_adv:.2f}, max={max_adv:.2f}")
            
            # Compute action type loss (for all actions)
            predicted_regrets = action_advantages.gather(1, action_type_tensors.unsqueeze(1)).squeeze(1)
            
            # [DEBUG 3] Log gathered predictions
            if self.iteration_count % 10 == 0 and epoch == 0:
                with torch.no_grad():
                    max_pred = torch.max(predicted_regrets).item()
                    min_pred = torch.min(predicted_regrets).item()
                    max_target = torch.max(regret_tensors).item()
                    min_target = torch.min(regret_tensors).item()
                    print(f"[DEBUG-PRED] Predictions: min={min_pred:.2f}, max={max_pred:.2f}")
                    print(f"[DEBUG-TARGET] Targets: min={min_target:.2f}, max={max_target:.2f}")
            
            action_loss = F.smooth_l1_loss(predicted_regrets, regret_tensors, reduction='none')
            
            # [DEBUG 4] Log raw loss values before weighting
            if self.iteration_count % 10 == 0 and epoch == 0:
                with torch.no_grad():
                    max_loss = torch.max(action_loss).item()
                    mean_loss = torch.mean(action_loss).item()
                    print(f"[DEBUG-LOSS] Raw loss values: max={max_loss:.2f}, mean={mean_loss:.2f}")
            
            weighted_action_loss = (action_loss * weight_tensors).mean()
            
            # [DEBUG 5] Log weighted loss
            if self.iteration_count % 10 == 0 and epoch == 0:
                print(f"[DEBUG-WEIGHTED] Weighted action loss: {weighted_action_loss.item():.2f}")
                
                # Check for weight outliers
                max_weight = torch.max(weight_tensors).item()
                min_weight = torch.min(weight_tensors).item()
                print(f"[DEBUG-WEIGHTS] Weight range: min={min_weight:.4f}, max={max_weight:.4f}")
            
            # Compute bet sizing loss (only for raise actions)
            raise_mask = (action_type_tensors == 2)
            if torch.any(raise_mask):
                # Calculate loss for all bet sizes
                all_bet_losses = F.smooth_l1_loss(bet_size_preds, bet_size_tensors, reduction='none')
                
                # Only count losses for raise actions, zero out others
                masked_bet_losses = all_bet_losses * raise_mask.float().unsqueeze(1)
                
                # Calculate weighted average loss
                raise_count = raise_mask.sum().item()
                if raise_count > 0:
                    weighted_bet_size_loss = (masked_bet_losses.squeeze() * weight_tensors).sum() / raise_count
                    combined_loss = weighted_action_loss + 0.5 * weighted_bet_size_loss
                    
                    # [DEBUG 6] Log bet size loss
                    if self.iteration_count % 10 == 0 and epoch == 0:
                        print(f"[DEBUG-BET] Weighted bet size loss: {weighted_bet_size_loss.item():.2f}")
                else:
                    combined_loss = weighted_action_loss
            else:
                combined_loss = weighted_action_loss
            
            # [DEBUG 7] Log final combined loss
            if self.iteration_count % 10 == 0 and epoch == 0:
                print(f"[DEBUG-COMBINED] Combined loss before clipping: {combined_loss.item():.2f}")
            
            # Backward pass and optimize
            self.optimizer.zero_grad()
            combined_loss.backward()
            
            # [DEBUG 8] Check for gradient explosion before clipping
            if self.iteration_count % 10 == 0 and epoch == 0:
                total_grad_norm = 0
                max_layer_norm = 0
                max_layer_name = ""
                for name, param in self.advantage_net.named_parameters():
                    if param.grad is not None:
                        grad_norm = param.grad.norm().item()
                        total_grad_norm += grad_norm * grad_norm
                        if grad_norm > max_layer_norm:
                            max_layer_norm = grad_norm
                            max_layer_name = name
                
                total_grad_norm = np.sqrt(total_grad_norm)
                print(f"[DEBUG-GRAD] Before clipping - Total grad norm: {total_grad_norm:.2f}")
                print(f"[DEBUG-GRAD] Largest layer grad: {max_layer_name} = {max_layer_norm:.2f}")
            
            # Apply gradient clipping (your existing code)
            torch.nn.utils.clip_grad_norm_(self.advantage_net.parameters(), max_norm=0.5)
            
            # [DEBUG 9] Check effect of gradient clipping
            if self.iteration_count % 10 == 0 and epoch == 0:
                total_grad_norm = 0
                for name, param in self.advantage_net.named_parameters():
                    if param.grad is not None:
                        grad_norm = param.grad.norm().item()
                        total_grad_norm += grad_norm * grad_norm
                
                total_grad_norm = np.sqrt(total_grad_norm)
                print(f"[DEBUG-GRAD] After clipping - Total grad norm: {total_grad_norm:.2f}")
            
            self.optimizer.step()
            
            # [DEBUG 10] Check for extreme parameter values after update
            if self.iteration_count % 50 == 0 and epoch == 0:
                with torch.no_grad():
                    max_param_val = -float('inf')
                    max_param_name = ""
                    for name, param in self.advantage_net.named_parameters():
                        param_max = torch.max(torch.abs(param)).item()
                        if param_max > max_param_val:
                            max_param_val = param_max
                            max_param_name = name
                    
                    print(f"[DEBUG-PARAMS] Largest parameter value: {max_param_name} = {max_param_val:.2f}")
            
            # Update priorities
            with torch.no_grad():
                # Calculate new errors for priority updates
                new_action_errors = F.smooth_l1_loss(predicted_regrets, regret_tensors, reduction='none')
                
                # For raise actions, include bet sizing errors
                if torch.any(raise_mask):
                    # Calculate normalized bet size errors for each sample
                    new_bet_errors = torch.zeros_like(new_action_errors)
                    
                    # Only add bet sizing errors for raise actions
                    raise_indices = torch.where(raise_mask)[0]
                    for i in raise_indices:
                        new_bet_errors[i] = F.smooth_l1_loss(
                            bet_size_preds[i], bet_size_tensors[i], reduction='mean'
                        )
                    
                    # Combined error with smaller weight for bet sizing
                    combined_errors = new_action_errors + 0.5 * new_bet_errors
                else:
                    combined_errors = new_action_errors
                
                # [DEBUG 11] Check priority values
                if self.iteration_count % 10 == 0 and epoch == 0:
                    combined_errors_np = combined_errors.cpu().numpy()
                    max_priority = np.max(combined_errors_np) + 0.01
                    min_priority = np.min(combined_errors_np) + 0.01
                    mean_priority = np.mean(combined_errors_np) + 0.01
                    print(f"[DEBUG-PRIORITY] Priorities: min={min_priority:.2f}, max={max_priority:.2f}, mean={mean_priority:.2f}")
                
                # Update priorities (your existing code)
                combined_errors_np = combined_errors.cpu().numpy()
                for i, idx in enumerate(indices):
                    self.advantage_memory.update_priority(idx, combined_errors_np[i] + 0.01)
            
            total_loss += combined_loss.item()
        
        # Return average loss
        return total_loss / epochs

    def train_strategy_network(self, batch_size=128, epochs=3):
        """
        Train the strategy network using collected samples.
        
        Args:
            batch_size: Size of training batches
            epochs: Number of training epochs per call
            
        Returns:
            Average training loss
        """
        if len(self.strategy_memory) < batch_size:
            return 0
        
        self.strategy_net.train()
        total_loss = 0
        
        for _ in range(epochs):
            # Sample batch from memory
            batch = random.sample(self.strategy_memory, batch_size)
            states, opponent_features, strategies, bet_sizes, iterations = zip(*batch)
            
            # Convert to tensors
            state_tensors = torch.FloatTensor(np.array(states)).to(self.device)
            opponent_feature_tensors = torch.FloatTensor(np.array(opponent_features)).to(self.device)
            strategy_tensors = torch.FloatTensor(np.array(strategies)).to(self.device)
            bet_size_tensors = torch.FloatTensor(np.array(bet_sizes)).unsqueeze(1).to(self.device)
            iteration_tensors = torch.FloatTensor(iterations).to(self.device).unsqueeze(1)
            
            # Weight samples by iteration (Linear CFR)
            weights = iteration_tensors / torch.sum(iteration_tensors)
            
            # Forward pass
            action_logits, bet_size_preds = self.strategy_net(state_tensors)
            predicted_strategies = F.softmax(action_logits, dim=1)
            
            # Action type loss (weighted cross-entropy)
            # Add small epsilon to prevent log(0)
            action_loss = -torch.sum(weights * torch.sum(strategy_tensors * torch.log(predicted_strategies + 1e-8), dim=1))
            
            # Bet size loss (only for states with raise actions)
            raise_mask = (strategy_tensors[:, 2] > 0)
            if raise_mask.sum() > 0:
                raise_indices = torch.nonzero(raise_mask).squeeze(1)
                raise_bet_preds = bet_size_preds[raise_indices]
                raise_bet_targets = bet_size_tensors[raise_indices]
                raise_weights = weights[raise_indices]
                
                # Use huber loss for bet sizing to be more robust to outliers
                bet_size_loss = F.smooth_l1_loss(raise_bet_preds, raise_bet_targets, reduction='none')
                weighted_bet_size_loss = torch.sum(raise_weights * bet_size_loss.squeeze())
                
                # Combine losses with appropriate weighting
                combined_loss = action_loss + 0.5 * weighted_bet_size_loss
            else:
                combined_loss = action_loss
            
            # Backward pass and optimize
            self.strategy_optimizer.zero_grad()
            combined_loss.backward()
            
            # Apply gradient clipping
            torch.nn.utils.clip_grad_norm_(self.strategy_net.parameters(), max_norm=0.5)
            
            self.strategy_optimizer.step()
            
            total_loss += combined_loss.item()
        
        # Return average loss
        return total_loss / epochs

    def choose_action(self, state):
        """Choose an action for the given state during actual play."""
        legal_action_types = self.get_legal_action_types(state)
        
        if not legal_action_types:
            # Default to call if no legal actions (shouldn't happen)
            if pkrs.ActionEnum.Call in state.legal_actions:
                return pkrs.Action(pkrs.ActionEnum.Call)
            elif pkrs.ActionEnum.Check in state.legal_actions:
                return pkrs.Action(pkrs.ActionEnum.Check)
            else:
                return pkrs.Action(pkrs.ActionEnum.Fold)
            
        state_tensor = torch.FloatTensor(encode_state(state, self.player_id)).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            logits, bet_size_pred = self.strategy_net(state_tensor)
            probs = F.softmax(logits, dim=1)[0].cpu().numpy()
            bet_size_multiplier = bet_size_pred[0][0].item()
        
        # Filter to only legal actions
        legal_probs = np.array([probs[a] for a in legal_action_types])
        if np.sum(legal_probs) > 0:
            legal_probs = legal_probs / np.sum(legal_probs)
        else:
            legal_probs = np.ones(len(legal_action_types)) / len(legal_action_types)
        
        # Choose action based on probabilities
        action_idx = np.random.choice(len(legal_action_types), p=legal_probs)
        action_type = legal_action_types[action_idx]
        
        # Use the predicted bet size for raise actions
        if action_type == 2:  # Raise
            return self.action_type_to_pokers_action(action_type, state, bet_size_multiplier)
        else:
            return self.action_type_to_pokers_action(action_type, state)

    def save_model(self, path_prefix):
        """Save the model to disk."""
        model_path = _resolve_model_save_path(path_prefix, self.iteration_count)
        torch.save({
            'iteration': self.iteration_count,
            'advantage_net': self.advantage_net.state_dict(),
            'strategy_net': self.strategy_net.state_dict(),
            'min_bet_size': self.min_bet_size,
            'max_bet_size': self.max_bet_size
        }, model_path)
        
    def load_model(self, path):
        """Load the model from disk."""
        checkpoint = torch.load(path, map_location=self.device)
        self.iteration_count = checkpoint['iteration']
        self.advantage_net.load_state_dict(checkpoint['advantage_net'])
        self.strategy_net.load_state_dict(checkpoint['strategy_net'])
        
        # Load bet size bounds if available in the checkpoint
        if 'min_bet_size' in checkpoint:
            self.min_bet_size = checkpoint['min_bet_size']
        if 'max_bet_size' in checkpoint:
            self.max_bet_size = checkpoint['max_bet_size']
