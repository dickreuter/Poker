"""
Deep CFR Decision Wrapper

Bridges the poker bot's game state to the pretrained Deep CFR model.
Loads the model once, runs inference with torch.no_grad(), and returns
a decision in the bot's DecisionTypes format.

Usage:
    from sys_core.decisionmaker.deepcfr_wrapper import deepcfr_decision, is_available

    if is_available():
        result = deepcfr_decision(t, h, p)
        # result = {'decision': 'Call', 'confidence': 0.72,
        #           'probs': {'fold': 0.05, 'check_call': 0.72, ...},
        #           'inference_ms': 3.2}
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional

import numpy as np

log = logging.getLogger('deepcfr')

# ---------------------------------------------------------------------------
# Lazy globals — model loaded once on first call
# ---------------------------------------------------------------------------
_model = None
_model_loaded = False
_load_error: Optional[str] = None

_MODEL_PATH = Path(__file__).parent / 'models' / 'deepcfr_6max.pt'

# Action index mapping for the 4-output model
# 0=Fold, 1=Check/Call, 2=Raise 0.5x pot, 3=Raise 1x pot
_ACTION_NAMES = ['fold', 'check_call', 'raise_half', 'raise_pot']


def _load_model():
    """Load pretrained Deep CFR model. Called once lazily."""
    global _model, _model_loaded, _load_error

    if _model_loaded:
        return _model is not None

    _model_loaded = True

    try:
        import torch
        from sys_core.decisionmaker.deepcfr_model import DeepCFRNetwork

        if not _MODEL_PATH.exists():
            _load_error = f"Model file not found: {_MODEL_PATH}"
            log.warning(f"Deep CFR: {_load_error}")
            return False

        checkpoint = torch.load(str(_MODEL_PATH), map_location='cpu', weights_only=False)

        # Use the advantage network — it produces more polarized (better)
        # action probabilities than the strategy network for this checkpoint.
        # The strategy net outputs near-uniform distributions, while the
        # advantage net correctly differentiates strong vs weak hands.
        if 'advantage_net' in checkpoint:
            state_dict = checkpoint['advantage_net']
            log.info("Deep CFR: Using advantage network")
        elif 'strategy_net' in checkpoint:
            state_dict = checkpoint['strategy_net']
            log.info("Deep CFR: Using strategy network (fallback)")
        else:
            _load_error = "Checkpoint has no 'strategy_net' or 'advantage_net'"
            log.warning(f"Deep CFR: {_load_error}")
            return False

        # Strip any module prefix from state_dict keys
        cleaned = {}
        for k, v in state_dict.items():
            clean_key = k.replace('strategy_net.', '').replace('advantage_net.', '')
            cleaned[clean_key] = v

        net = DeepCFRNetwork(input_size=156, hidden_size=256, num_actions=4)
        net.load_state_dict(cleaned)
        net.eval()

        _model = net
        iteration = checkpoint.get('iteration', '?')
        log.info(f"Deep CFR: Model loaded (iteration {iteration}, "
                 f"{sum(p.numel() for p in net.parameters())} params)")
        return True

    except ImportError:
        _load_error = "PyTorch not installed (pip install torch)"
        log.warning(f"Deep CFR: {_load_error}")
        return False
    except Exception as e:
        _load_error = str(e)
        log.error(f"Deep CFR: Failed to load model: {e}")
        return False


def is_available() -> bool:
    """Check if Deep CFR model can be used."""
    return _load_model()


def deepcfr_decision(t, h, p) -> Optional[Dict]:
    """
    Run Deep CFR inference on the current game state.

    Args:
        t: TableScreenBased instance (has my_cards, cardsOnTable, equity, etc.)
        h: History instance
        p: StrategyHandler instance

    Returns:
        Dict with keys:
            'decision': str — one of 'Fold', 'Check', 'Call', 'Bet', 'Bet half pot', 'Bet pot'
            'confidence': float — probability of chosen action
            'probs': dict — all action probabilities
            'inference_ms': float — inference time in milliseconds
        Or None if model unavailable or error
    """
    if not _load_model():
        return None

    try:
        import torch
        from sys_core.decisionmaker.deepcfr_model import encode_game_state

        t0 = time.perf_counter()

        # --- Extract game state from table object ---
        hero_cards = getattr(t, 'my_cards', []) or getattr(t, 'mycards', []) or []
        if len(hero_cards) != 2:
            log.debug("Deep CFR: Need exactly 2 hero cards")
            return None

        board = getattr(t, 'cardsOnTable', []) or getattr(t, 'table_cards', []) or []
        stage = getattr(t, 'gameStage', 'PreFlop') or 'PreFlop'
        pot = float(getattr(t, 'totalPotValue', 0) or 0)
        hero_stack = float(getattr(t, 'myFunds', 100) or 100)
        min_call = float(getattr(t, 'minCall', 0) or getattr(t, 'currentCallValue', 0) or 0)
        min_bet = float(getattr(t, 'minBet', 0) or getattr(t, 'currentBetValue', 0) or 0)

        # Hero current bet this street (approximate from pot data)
        hero_bet = 0.0
        if hasattr(t, 'player_pots') and t.player_pots:
            try:
                hero_bet = float(t.player_pots[0]) if t.player_pots[0] else 0.0
            except (IndexError, TypeError, ValueError):
                pass

        # Villain info
        villain_stacks = []
        villain_bets = []
        villain_active = []

        player_funds = getattr(t, 'player_funds', [])
        player_pots = getattr(t, 'player_pots', [])
        players_in_game = getattr(t, 'players_in_game', [])

        for i in range(1, 6):  # seats 1-5 are villains
            if i < len(player_funds) and player_funds[i]:
                villain_stacks.append(float(player_funds[i]))
            else:
                villain_stacks.append(0.0)

            if i < len(player_pots) and player_pots[i]:
                villain_bets.append(float(player_pots[i]))
            else:
                villain_bets.append(0.0)

            if i < len(players_in_game):
                villain_active.append(bool(players_in_game[i]))
            else:
                villain_active.append(False)

        # Pad to exactly 5 villains
        while len(villain_stacks) < 5:
            villain_stacks.append(0.0)
            villain_bets.append(0.0)
            villain_active.append(False)

        # Button & hero seat
        button_seat = int(getattr(t, 'dealer_position', 0) or 0)
        hero_seat = 0  # hero is always seat 0 in our representation

        # Legal actions
        has_check = bool(getattr(t, 'checkButton', False))
        has_call = bool(getattr(t, 'callButton', False))
        has_raise = bool(getattr(t, 'raiseButton', False))
        can_fold = has_call or has_raise  # can always fold when facing a bet
        can_check = has_check
        can_call = has_call
        can_raise = has_raise

        # Encode state
        state_vec = encode_game_state(
            hero_cards=hero_cards,
            community_cards=board,
            stage=stage,
            pot=pot,
            hero_stack=hero_stack,
            hero_bet=hero_bet,
            villain_stacks=villain_stacks,
            villain_bets=villain_bets,
            villain_active=villain_active,
            button_seat=button_seat,
            hero_seat=hero_seat,
            min_bet=min_call,  # min_bet in the encoding = amount to call
            can_fold=can_fold,
            can_check=can_check,
            can_call=can_call,
            can_raise=can_raise,
        )

        # Run inference
        with torch.no_grad():
            x = torch.FloatTensor(state_vec).unsqueeze(0)
            logits = _model(x)  # shape (1, 4)
            probs = torch.softmax(logits, dim=1)[0].numpy()

        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Mask illegal actions
        legal_mask = np.array([
            1.0 if can_fold else 0.0,       # 0: fold
            1.0 if (can_check or can_call) else 0.0,  # 1: check/call
            1.0 if can_raise else 0.0,       # 2: raise half pot
            1.0 if can_raise else 0.0,       # 3: raise pot
        ], dtype=np.float32)

        masked_probs = probs * legal_mask
        total = masked_probs.sum()
        if total > 0:
            masked_probs /= total
        else:
            # No legal actions? Default to check/call
            masked_probs = np.array([0.0, 1.0, 0.0, 0.0])

        # Pick highest-probability legal action
        best_idx = int(np.argmax(masked_probs))
        confidence = float(masked_probs[best_idx])

        # Map to our DecisionTypes
        if best_idx == 0:
            decision = 'Fold'
        elif best_idx == 1:
            decision = 'Check' if can_check else 'Call'
        elif best_idx == 2:
            decision = 'Bet half pot'
        elif best_idx == 3:
            decision = 'Bet pot'
        else:
            decision = 'Call'

        prob_dict = {
            'fold': float(masked_probs[0]),
            'check_call': float(masked_probs[1]),
            'raise_half': float(masked_probs[2]),
            'raise_pot': float(masked_probs[3]),
        }

        log.info(f"Deep CFR: {hero_cards} on {board or 'preflop'} | "
                 f"pot={pot:.1f} call={min_call:.1f} | "
                 f"=> {decision} ({confidence:.0%}) | {elapsed_ms:.1f}ms")
        log.debug(f"  Probs: {prob_dict}")

        return {
            'decision': decision,
            'confidence': confidence,
            'probs': prob_dict,
            'inference_ms': elapsed_ms,
        }

    except Exception as e:
        log.error(f"Deep CFR inference error: {e}")
        return None


def get_status() -> str:
    """Return a human-readable status string for the Deep CFR engine."""
    if not _model_loaded:
        return "Deep CFR: Not loaded yet"
    if _model is not None:
        return "Deep CFR: Ready"
    return f"Deep CFR: Unavailable ({_load_error})"
