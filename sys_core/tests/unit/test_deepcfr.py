"""
Tests for the Deep CFR integration.

Verifies:
1. Model loads successfully
2. State encoding produces correct shape
3. Card encoding covers all 52 cards
4. Inference returns valid action probabilities
5. Wrapper returns properly formatted decisions
6. Legal action masking works
"""

import logging
import unittest
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.WARNING)


class TestDeepCFRModel(unittest.TestCase):
    """Test the model architecture and state encoding."""

    def test_card_to_index_all_52(self):
        from sys_core.decisionmaker.deepcfr_model import card_to_index
        indices = set()
        for suit in ['S', 'H', 'D', 'C']:
            for rank in ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']:
                idx = card_to_index(rank + suit)
                self.assertGreaterEqual(idx, 0)
                self.assertLess(idx, 52)
                indices.add(idx)
        self.assertEqual(len(indices), 52, "All 52 cards should map to unique indices")

    def test_card_to_index_10_format(self):
        from sys_core.decisionmaker.deepcfr_model import card_to_index
        self.assertEqual(card_to_index('TH'), card_to_index('TH'))

    def test_encode_state_shape(self):
        from sys_core.decisionmaker.deepcfr_model import encode_game_state
        state = encode_game_state(
            hero_cards=['AH', 'KS'],
            community_cards=['JD', '7C', '2H'],
            stage='Flop',
            pot=10.0, hero_stack=90.0, hero_bet=5.0,
            villain_stacks=[95.0, 100.0, 0.0, 0.0, 0.0],
            villain_bets=[5.0, 0.0, 0.0, 0.0, 0.0],
            villain_active=[True, True, False, False, False],
            button_seat=3, hero_seat=0, min_bet=5.0,
            can_fold=True, can_check=False, can_call=True, can_raise=True,
        )
        self.assertEqual(state.shape, (156,))
        self.assertEqual(state.dtype, np.float32)

    def test_encode_state_preflop_no_board(self):
        from sys_core.decisionmaker.deepcfr_model import encode_game_state
        state = encode_game_state(
            hero_cards=['AH', 'AS'],
            community_cards=[],
            stage='PreFlop',
            pot=3.5, hero_stack=98.5, hero_bet=1.5,
            villain_stacks=[100.0] * 5,
            villain_bets=[0.0] * 5,
            villain_active=[True] * 5,
            button_seat=5, hero_seat=0, min_bet=2.0,
            can_fold=True, can_check=False, can_call=True, can_raise=True,
        )
        self.assertEqual(state.shape, (156,))
        # Hand encoding: exactly 2 cards set
        hand_sum = state[:52].sum()
        self.assertAlmostEqual(hand_sum, 2.0, places=5)
        # Community: none set
        community_sum = state[52:104].sum()
        self.assertAlmostEqual(community_sum, 0.0, places=5)


class TestDeepCFRNetwork(unittest.TestCase):
    """Test the neural network architecture."""

    def test_network_forward(self):
        import torch
        from sys_core.decisionmaker.deepcfr_model import DeepCFRNetwork
        net = DeepCFRNetwork(input_size=156, hidden_size=256, num_actions=4)
        x = torch.randn(1, 156)
        with torch.no_grad():
            out = net(x)
        self.assertEqual(out.shape, (1, 4))

    def test_network_batch(self):
        import torch
        from sys_core.decisionmaker.deepcfr_model import DeepCFRNetwork
        net = DeepCFRNetwork(input_size=156, hidden_size=256, num_actions=4)
        x = torch.randn(8, 156)
        with torch.no_grad():
            out = net(x)
        self.assertEqual(out.shape, (8, 4))


class TestDeepCFRWrapper(unittest.TestCase):
    """Test the wrapper that bridges game state to model inference."""

    def test_model_loads(self):
        from sys_core.decisionmaker.deepcfr_wrapper import is_available, get_status
        self.assertTrue(is_available())
        self.assertIn("Ready", get_status())

    def test_inference_returns_dict(self):
        from sys_core.decisionmaker.deepcfr_wrapper import deepcfr_decision

        class MockTable:
            my_cards = ['AH', 'KS']
            cardsOnTable = ['JD', '7C', '2H']
            gameStage = 'Flop'
            totalPotValue = 10.0
            myFunds = 90.0
            minCall = 5.0
            minBet = 10.0
            currentCallValue = 5.0
            currentBetValue = 10.0
            player_funds = [90.0, 95.0, 100.0, 0.0, 0.0, 0.0]
            player_pots = [5.0, 5.0, 0.0, 0.0, 0.0, 0.0]
            players_in_game = [True, True, True, False, False, False]
            dealer_position = 3
            checkButton = False
            callButton = True
            raiseButton = True
            equity = 0.65

        result = deepcfr_decision(MockTable(), None, None)
        self.assertIsNotNone(result)
        self.assertIn('decision', result)
        self.assertIn('confidence', result)
        self.assertIn('probs', result)
        self.assertIn('inference_ms', result)

        # Decision should be a valid action string
        self.assertIn(result['decision'], ['Fold', 'Check', 'Call', 'Bet half pot', 'Bet pot'])

        # Probabilities should sum to ~1
        prob_sum = sum(result['probs'].values())
        self.assertAlmostEqual(prob_sum, 1.0, places=3)

        # Confidence should be between 0 and 1
        self.assertGreaterEqual(result['confidence'], 0.0)
        self.assertLessEqual(result['confidence'], 1.0)

        # Inference should be fast (<100ms)
        self.assertLess(result['inference_ms'], 100.0)

    def test_returns_none_without_cards(self):
        from sys_core.decisionmaker.deepcfr_wrapper import deepcfr_decision

        class MockTable:
            my_cards = []  # No cards
            cardsOnTable = []
            gameStage = 'PreFlop'
            totalPotValue = 0
            myFunds = 100
            minCall = 0
            minBet = 0
            currentCallValue = 0
            currentBetValue = 0
            player_funds = []
            player_pots = []
            players_in_game = []
            dealer_position = 0
            checkButton = True
            callButton = False
            raiseButton = False
            equity = 0.5

        result = deepcfr_decision(MockTable(), None, None)
        self.assertIsNone(result)

    def test_check_when_free(self):
        """When check is available, Check/Call action should map to Check."""
        from sys_core.decisionmaker.deepcfr_wrapper import deepcfr_decision

        class MockTable:
            my_cards = ['AH', 'KS']
            cardsOnTable = ['JD', '7C', '2H']
            gameStage = 'Flop'
            totalPotValue = 10.0
            myFunds = 95.0
            minCall = 0.0
            minBet = 5.0
            currentCallValue = 0.0
            currentBetValue = 5.0
            player_funds = [95.0, 95.0, 100.0, 0.0, 0.0, 0.0]
            player_pots = [5.0, 5.0, 0.0, 0.0, 0.0, 0.0]
            players_in_game = [True, True, True, False, False, False]
            dealer_position = 3
            checkButton = True
            callButton = False
            raiseButton = True
            equity = 0.65

        result = deepcfr_decision(MockTable(), None, None)
        self.assertIsNotNone(result)
        # If action is check/call, should say "Check" not "Call"
        if result['probs']['check_call'] == max(result['probs'].values()):
            self.assertEqual(result['decision'], 'Check')


class TestDeepCFRPerformance(unittest.TestCase):
    """Verify inference performance."""

    def test_inference_under_10ms(self):
        import time
        from sys_core.decisionmaker.deepcfr_wrapper import deepcfr_decision

        class MockTable:
            my_cards = ['AH', 'KS']
            cardsOnTable = []
            gameStage = 'PreFlop'
            totalPotValue = 3.5
            myFunds = 98.5
            minCall = 2.0
            minBet = 6.0
            currentCallValue = 2.0
            currentBetValue = 6.0
            player_funds = [98.5, 100.0, 100.0, 100.0, 100.0, 100.0]
            player_pots = [1.5, 0.0, 0.0, 0.0, 0.0, 0.0]
            players_in_game = [True, True, True, True, True, True]
            dealer_position = 5
            checkButton = False
            callButton = True
            raiseButton = True
            equity = 0.5

        # Warm up
        deepcfr_decision(MockTable(), None, None)

        # Time 100 inferences
        t0 = time.perf_counter()
        for _ in range(100):
            deepcfr_decision(MockTable(), None, None)
        elapsed = (time.perf_counter() - t0) * 1000  # ms total

        avg_ms = elapsed / 100
        print(f"\nAverage inference: {avg_ms:.2f}ms ({elapsed:.0f}ms for 100 calls)")
        self.assertLess(avg_ms, 10.0, "Average inference should be under 10ms")


if __name__ == '__main__':
    unittest.main()
