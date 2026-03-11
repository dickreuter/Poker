
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gamble.decisionmaker.decisionmaker import Decision, DecisionTypes
from gamble.multi_table_runner import MultiTableRunner, TableSession
from gamble.scraper.table import Table
from gamble.tools.strategy_handler import StrategyHandler

class BugReproductionTests(unittest.TestCase):
    def setUp(self):
        self.strategy = StrategyHandler()
        self.strategy.read_strategy('Trial 1')
        self.logger = MagicMock()
        self.history = MagicMock()

    def test_premium_hand_defense(self):
        """Reproduce Bug: Folding KK when facing a small raise in SB/BB."""
        # Table needs specific constructor args
        table = Table(self.strategy, {}, MagicMock(), self.logger, version=1.0)
        table.mycards = ['KS', 'KH']
        table.gameStage = 'PreFlop'
        table._gto_position = 'SB'
        table.position_utg_plus = 4 
        table.bigBlind = 0.02
        table.myFunds = 4.0  # 200 BB
        table.totalPotValue = 0.08 
        table.currentCallValue = 0.06 
        table.first_raiser = True
        table.first_raiser_utg = 3 
        table.checkButton = False
        table.other_players = [] 
        table.round_pot_value = 0.08
        table.equity = 0.60 # Estimated equity for KK vs range
        table.abs_equity = 0.60
        table.cardsOnTable = [] # Preflop board is empty
        table.first_caller_utg = float('nan') # No callers
        table.isHeadsUp = False
        
        # Mock Decision to check internal logic
        d = Decision(table, self.history, self.strategy, self.logger)
        d.preflop_table_analyser(table, self.history, self.strategy)
        
        print(f"\n[TEST] Premium Hand (KK) Decision: {d.decision}")
        self.assertIn(d.decision, [DecisionTypes.bet3, DecisionTypes.bet4, DecisionTypes.call], 
                     f"ERROR: Folded KK preflop! Decision was {d.decision}")

    @patch('pyautogui.typewrite')
    @patch('gamble.multi_table_runner.MultiTableRunner.capture_game_state')
    def test_slider_verification_logic(self, mock_capture, mock_type):
        """Reproduce Bug: Slider mistyping logic verification."""
        runner = MultiTableRunner()
        # Mock session and its window
        session = MagicMock(spec=TableSession)
        session.window = MagicMock()
        session.window.x = 0
        session.window.y = 0
        session.window.width = 800
        session.window.height = 600
        session.window.name = "Test Table"
        
        # Mock capture_game_state to return mismatching amount
        mock_btn = MagicMock()
        mock_btn.amount = 23.0 
        mock_btn.action_type = 'raise'
        
        v_state = MagicMock()
        v_state.get_action_by_type.return_value = mock_btn
        mock_capture.return_value = v_state
        pass 

    def test_missing_cards_wait(self):
        """Reproduce Bug: Instant fold when cards are missing."""
        runner = MultiTableRunner()
        # Ensure we don't try to actually take screenshots or crop
        with patch.object(runner, 'get_table_screenshot'), \
             patch.object(runner, '_update_blinds_from_window'):
            
            session = TableSession(MagicMock(), {}, None)
            session.window = MagicMock()
            session.window.name = "Rush & Cash $0.01/$0.02" 
            session.window.x = 0
            session.window.y = 0
            session.window.width = 800
            session.window.height = 600
            
            state = MagicMock()
            state.my_cards = [] 
            state.board_cards = []
            state.is_my_turn = True
            state.available_actions = [MagicMock(action_type='fold'), MagicMock(action_type='call')]
            
            # Mock _click_action to see if it gets called
            with patch.object(runner, '_click_action') as mock_click:
                session._cached_game_state = state
                result = runner.process_table_new_ocr(session)
                
                print(f"\n[TEST] Missing Cards Action Result: {result}")
                
                calls = [args[3] for args, kwargs in mock_click.call_args_list if len(args) > 3]
                self.assertNotIn('fold_no_cards', calls, "ERROR: Bot folded because cards were missing!")

if __name__ == '__main__':
    unittest.main()
