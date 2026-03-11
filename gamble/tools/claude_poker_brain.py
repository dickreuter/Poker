"""
CLAUDE POKER BRAIN - Opus 4.6 Integration for Real-Time Poker

This module integrates Claude Opus 4.6 with the existing poker bot for:
1. FAST LOCAL DETECTION (existing) - milliseconds
2. CLAUDE STRATEGY DECISIONS - 500ms-2s (acceptable for poker's 15-30s time bank)
3. CLAUDE VISION FALLBACK - when local detection fails

Architecture:
    ┌─────────────────────────────────────────────┐
    │     LOCAL DETECTION (fast, existing)        │
    │  - HSV button detection (10-50ms)           │
    │  - Template card matching (10-50ms)         │
    │  - OCR pot/stack reading (100-200ms)        │
    └─────────────────────────────────────────────┘
                         │
                         │ Structured data: {cards, pot, buttons, stacks}
                         ▼
    ┌─────────────────────────────────────────────┐
    │     CLAUDE OPUS 4.6 DECISION LAYER          │
    │  - Adaptive thinking for strategy           │
    │  - GTO-based decision making                │
    │  - Opponent modeling                        │
    │  - Latency: 500ms-2s (OK for poker)         │
    └─────────────────────────────────────────────┘
                         │
                         │ If local detection fails
                         ▼
    ┌─────────────────────────────────────────────┐
    │     CLAUDE VISION FALLBACK                  │
    │  - Send screenshot for analysis             │
    │  - Auto-heal detection thresholds           │
    │  - Learn from failures                      │
    └─────────────────────────────────────────────┘

Usage:
    from gamble.tools.claude_poker_brain import ClaudePokerBrain

    brain = ClaudePokerBrain()

    # Fast decision using structured data (recommended)
    action = brain.decide_action(
        my_cards=['AH', 'KS'],
        community_cards=['QH', 'JD', '2C'],
        pot=150,
        to_call=50,
        my_stack=500,
        opponent_stacks=[450, 600],
        position='BTN',
        buttons=['fold', 'call', 'raise']
    )

    # Vision fallback when detection fails
    result = brain.analyze_screenshot(screenshot_base64)
"""

import os
import json
import time
import base64
import logging
from io import BytesIO
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)

# Check for anthropic library
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    log.warning("anthropic library not installed. Run: pip install anthropic")

# Try to import PIL for image handling
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class PokerAction(Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"
    ALL_IN = "all_in"


class EffortLevel(Enum):
    """Effort levels for Claude's adaptive thinking"""
    LOW = "low"      # Simple decisions (free check)
    MEDIUM = "medium"  # Standard decisions
    HIGH = "high"    # Complex decisions (big pots)
    MAX = "max"      # Critical all-in decisions


@dataclass
class PokerDecision:
    """Result of Claude's decision"""
    action: PokerAction
    amount: Optional[float] = None  # For bet/raise amounts
    confidence: float = 0.0
    reasoning: str = ""
    thinking_time_ms: int = 0


@dataclass
class TableAnalysis:
    """Result of Claude's visual analysis"""
    my_cards: List[str]
    community_cards: List[str]
    buttons: List[str]
    pot: float
    to_call: float
    my_stack: float
    opponent_stacks: List[float]
    confidence: float
    raw_response: str


class ClaudePokerBrain:
    """
    Claude Opus 4.6 integration for poker decision making.

    Uses adaptive thinking to balance speed and intelligence:
    - LOW effort: Simple decisions (check when free)
    - MEDIUM effort: Standard pot decisions
    - HIGH effort: Big pot or complex situations
    - MAX effort: Tournament-critical or all-in decisions
    """

    def __init__(self, api_key: str = None):
        """
        Initialize the Claude Poker Brain.

        Args:
            api_key: Anthropic API key. If not provided, uses ANTHROPIC_API_KEY env var.
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic library not installed. Run: pip install anthropic")

        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("No API key provided. Set ANTHROPIC_API_KEY environment variable.")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = "claude-opus-4-6"  # Opus 4.6 for best computer use

        # Session stats
        self.decisions_made = 0
        self.total_thinking_time = 0
        self.vision_calls = 0

        # Caching for similar situations
        self._decision_cache = {}

        log.info(f"ClaudePokerBrain initialized with model: {self.model}")

    def _determine_effort(self,
                          pot: float,
                          to_call: float,
                          my_stack: float,
                          buttons: List[str]) -> EffortLevel:
        """
        Determine appropriate effort level based on situation.

        Higher effort = more thinking = better decisions but slower.
        """
        # Free check = minimal thinking
        if buttons == ['check'] or (to_call == 0 and 'check' in buttons):
            return EffortLevel.LOW

        # All-in situation = maximum thinking
        if to_call >= my_stack * 0.5:
            return EffortLevel.MAX

        # Big pot (> 20 BBs) = high thinking
        # Assuming BB = pot / 10 for estimation
        estimated_bb = pot / 10 if pot > 0 else 1
        if pot > estimated_bb * 20:
            return EffortLevel.HIGH

        # Standard situation
        return EffortLevel.MEDIUM

    def decide_action(self,
                      my_cards: List[str],
                      community_cards: List[str],
                      pot: float,
                      to_call: float,
                      my_stack: float,
                      opponent_stacks: List[float],
                      position: str,
                      buttons: List[str],
                      game_history: str = "",
                      force_effort: EffortLevel = None) -> PokerDecision:
        """
        Make a poker decision using Claude Opus 4.6 with adaptive thinking.

        This is the main decision method - uses structured data from local detection.
        Latency: 500ms-2s depending on effort level.

        Args:
            my_cards: Player's hole cards ['AH', 'KS']
            community_cards: Community cards ['QH', 'JD', '2C']
            pot: Current pot size
            to_call: Amount to call
            my_stack: Player's stack
            opponent_stacks: Opponent stack sizes
            position: Position (BTN, SB, BB, UTG, etc.)
            buttons: Available actions ['fold', 'call', 'raise']
            game_history: Optional recent hand history for context
            force_effort: Override automatic effort determination

        Returns:
            PokerDecision with action, amount, confidence, and reasoning
        """
        start_time = time.time()

        # Determine effort level
        effort = force_effort or self._determine_effort(pot, to_call, my_stack, buttons)

        # Build the decision prompt
        prompt = self._build_decision_prompt(
            my_cards=my_cards,
            community_cards=community_cards,
            pot=pot,
            to_call=to_call,
            my_stack=my_stack,
            opponent_stacks=opponent_stacks,
            position=position,
            buttons=buttons,
            game_history=game_history
        )

        try:
            # Call Claude with adaptive thinking
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                thinking={"type": "adaptive"},
                # Map effort levels to Claude's effort parameter
                # Note: This is the new Opus 4.6 feature
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Parse the response
            decision = self._parse_decision_response(response, buttons)

            thinking_time = int((time.time() - start_time) * 1000)
            decision.thinking_time_ms = thinking_time

            # Update stats
            self.decisions_made += 1
            self.total_thinking_time += thinking_time

            log.info(f"Claude decision: {decision.action.value} "
                    f"(confidence: {decision.confidence:.0%}, time: {thinking_time}ms)")

            return decision

        except Exception as e:
            log.error(f"Claude decision failed: {e}")
            # Fallback to safe action
            return self._safe_fallback(buttons)

    def _build_decision_prompt(self,
                               my_cards: List[str],
                               community_cards: List[str],
                               pot: float,
                               to_call: float,
                               my_stack: float,
                               opponent_stacks: List[float],
                               position: str,
                               buttons: List[str],
                               game_history: str = "") -> str:
        """Build the decision prompt for Claude."""

        # Format cards nicely
        hole_cards = ' '.join(my_cards) if my_cards else "Unknown"
        board = ' '.join(community_cards) if community_cards else "None (Preflop)"

        # Determine game stage
        num_community = len(community_cards)
        if num_community == 0:
            stage = "Preflop"
        elif num_community == 3:
            stage = "Flop"
        elif num_community == 4:
            stage = "Turn"
        else:
            stage = "River"

        # Calculate pot odds
        pot_odds = to_call / (pot + to_call) if (pot + to_call) > 0 else 0

        # Calculate stack-to-pot ratio
        spr = my_stack / pot if pot > 0 else float('inf')

        prompt = f"""You are an expert poker player making a real-time decision. Be concise.

CURRENT SITUATION:
- Stage: {stage}
- My Cards: {hole_cards}
- Board: {board}
- Position: {position}

MONEY:
- Pot: ${pot:.2f}
- To Call: ${to_call:.2f}
- My Stack: ${my_stack:.2f}
- Opponents: {', '.join(f'${s:.2f}' for s in opponent_stacks)}
- Pot Odds: {pot_odds:.1%}
- SPR: {spr:.1f}

AVAILABLE ACTIONS: {', '.join(buttons)}

{f"RECENT HISTORY: {game_history}" if game_history else ""}

Analyze this situation and decide the best action. Consider:
1. Hand strength and potential
2. Position advantage
3. Pot odds vs equity
4. Opponent tendencies
5. Stack depths

Respond in this exact JSON format:
{{
    "action": "fold|check|call|bet|raise|all_in",
    "amount": null or number (for bet/raise),
    "confidence": 0.0 to 1.0,
    "reasoning": "brief explanation"
}}"""

        return prompt

    def _parse_decision_response(self, response, buttons: List[str]) -> PokerDecision:
        """Parse Claude's response into a PokerDecision."""
        try:
            # Extract text content
            text = response.content[0].text

            # Try to parse JSON
            # Handle potential markdown code blocks
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]

            data = json.loads(text.strip())

            # Map action string to enum
            action_map = {
                'fold': PokerAction.FOLD,
                'check': PokerAction.CHECK,
                'call': PokerAction.CALL,
                'bet': PokerAction.BET,
                'raise': PokerAction.RAISE,
                'all_in': PokerAction.ALL_IN,
                'all-in': PokerAction.ALL_IN,
            }

            action = action_map.get(data.get('action', '').lower(), PokerAction.FOLD)

            # Validate action is available
            if action.value not in buttons and action != PokerAction.ALL_IN:
                # Try to find closest valid action
                if 'call' in buttons:
                    action = PokerAction.CALL
                elif 'check' in buttons:
                    action = PokerAction.CHECK
                else:
                    action = PokerAction.FOLD

            return PokerDecision(
                action=action,
                amount=data.get('amount'),
                confidence=float(data.get('confidence', 0.5)),
                reasoning=data.get('reasoning', '')
            )

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            log.warning(f"Failed to parse Claude response: {e}")
            return self._safe_fallback(buttons)

    def _safe_fallback(self, buttons: List[str]) -> PokerDecision:
        """Return a safe fallback decision when parsing fails."""
        if 'check' in buttons:
            return PokerDecision(
                action=PokerAction.CHECK,
                confidence=0.5,
                reasoning="Fallback: free check"
            )
        elif 'fold' in buttons:
            return PokerDecision(
                action=PokerAction.FOLD,
                confidence=0.5,
                reasoning="Fallback: safe fold"
            )
        else:
            return PokerDecision(
                action=PokerAction.CALL,
                confidence=0.5,
                reasoning="Fallback: forced call"
            )

    def analyze_screenshot(self,
                           screenshot: 'Image.Image' = None,
                           screenshot_base64: str = None) -> TableAnalysis:
        """
        Use Claude's vision to analyze a poker table screenshot.

        This is the FALLBACK method when local detection fails.
        Latency: 1-3 seconds (use sparingly).

        Args:
            screenshot: PIL Image of the table
            screenshot_base64: Or base64 encoded image

        Returns:
            TableAnalysis with detected game state
        """
        if not PIL_AVAILABLE and screenshot is not None:
            raise ImportError("PIL not available for image handling")

        self.vision_calls += 1

        # Convert screenshot to base64 if needed
        if screenshot is not None and screenshot_base64 is None:
            buffer = BytesIO()
            screenshot.save(buffer, format='PNG')
            screenshot_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

        if not screenshot_base64:
            raise ValueError("No screenshot provided")

        prompt = """Analyze this poker table screenshot and extract:

1. My hole cards (bottom center, e.g., "AH KS" for Ace of Hearts, King of Spades)
2. Community cards on the board (center, if any)
3. Available action buttons (Fold, Call, Check, Raise, Bet, All-In)
4. Pot size (number shown in center)
5. Amount to call (shown on Call button)
6. My stack size (my chip count)
7. Opponent stack sizes (other players' chips)

Return JSON:
{
    "my_cards": ["AH", "KS"],
    "community_cards": ["QH", "JD", "2C"],
    "buttons": ["fold", "call", "raise"],
    "pot": 150.0,
    "to_call": 50.0,
    "my_stack": 500.0,
    "opponent_stacks": [450.0, 600.0],
    "confidence": 0.9
}

Use standard card notation: A/K/Q/J/T/9-2 for ranks, H/D/C/S for suits.
If you can't detect something clearly, use null or empty array."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": screenshot_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )

            return self._parse_vision_response(response)

        except Exception as e:
            log.error(f"Claude vision analysis failed: {e}")
            raise

    def _parse_vision_response(self, response) -> TableAnalysis:
        """Parse Claude's vision response into TableAnalysis."""
        try:
            text = response.content[0].text

            # Handle markdown code blocks
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]

            data = json.loads(text.strip())

            return TableAnalysis(
                my_cards=data.get('my_cards', []),
                community_cards=data.get('community_cards', []),
                buttons=data.get('buttons', []),
                pot=float(data.get('pot', 0)),
                to_call=float(data.get('to_call', 0)),
                my_stack=float(data.get('my_stack', 0)),
                opponent_stacks=[float(s) for s in data.get('opponent_stacks', [])],
                confidence=float(data.get('confidence', 0.5)),
                raw_response=text
            )

        except (json.JSONDecodeError, KeyError) as e:
            log.error(f"Failed to parse vision response: {e}")
            raise

    def decide_from_game_state(self, state) -> 'PokerDecision':
        """Make a decision from a GameState object (from Rust OCR).

        Args:
            state: gamble.ocr.game_state.GameState instance

        Returns:
            PokerDecision with action, amount, confidence, and reasoning
        """
        buttons = [a.action_type for a in state.available_actions]
        opponent_stacks = [p.stack for p in state.players if not p.is_hero and p.is_active]

        return self.decide_action(
            my_cards=state.my_cards,
            community_cards=state.board_cards,
            pot=state.pot,
            to_call=state.call_amount,
            my_stack=state.hero_stack,
            opponent_stacks=opponent_stacks,
            position='BTN',  # TODO: determine from dealer_seat
            buttons=buttons,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get brain statistics."""
        avg_time = (self.total_thinking_time / self.decisions_made
                    if self.decisions_made > 0 else 0)
        return {
            'decisions_made': self.decisions_made,
            'vision_calls': self.vision_calls,
            'avg_thinking_time_ms': avg_time,
            'total_thinking_time_ms': self.total_thinking_time
        }


# Singleton instance
_brain: Optional[ClaudePokerBrain] = None

def get_brain() -> ClaudePokerBrain:
    """Get or create the singleton Claude brain."""
    global _brain
    if _brain is None:
        _brain = ClaudePokerBrain()
    return _brain


# Quick access functions
def decide(my_cards: List[str],
           community_cards: List[str],
           pot: float,
           to_call: float,
           my_stack: float,
           buttons: List[str],
           **kwargs) -> PokerDecision:
    """Quick decision using the singleton brain."""
    return get_brain().decide_action(
        my_cards=my_cards,
        community_cards=community_cards,
        pot=pot,
        to_call=to_call,
        my_stack=my_stack,
        buttons=buttons,
        **kwargs
    )


def analyze_table(screenshot: 'Image.Image') -> TableAnalysis:
    """Quick vision analysis using the singleton brain."""
    return get_brain().analyze_screenshot(screenshot=screenshot)


if __name__ == "__main__":
    # Test the brain
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("CLAUDE POKER BRAIN - Test")
    print("=" * 60)

    try:
        brain = ClaudePokerBrain()

        # Test decision making
        print("\nTesting decision making...")
        decision = brain.decide_action(
            my_cards=['AH', 'KH'],
            community_cards=['QH', 'JH', '2C'],
            pot=100,
            to_call=50,
            my_stack=500,
            opponent_stacks=[450],
            position='BTN',
            buttons=['fold', 'call', 'raise']
        )

        print(f"Decision: {decision.action.value}")
        print(f"Amount: {decision.amount}")
        print(f"Confidence: {decision.confidence:.0%}")
        print(f"Reasoning: {decision.reasoning}")
        print(f"Thinking time: {decision.thinking_time_ms}ms")

        print(f"\nStats: {brain.get_stats()}")

    except Exception as e:
        print(f"Error: {e}")
        print("Make sure ANTHROPIC_API_KEY is set")
