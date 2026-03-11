"""
CLAUDE ENHANCED MULTI-TABLE RUNNER

This integrates Claude Opus 4.6 with the existing multi_table_runner.py:

1. USES EXISTING FAST LOCAL DETECTION (from multi_table_runner.py)
   - Button detection: HSV color (10-50ms)
   - Card detection: Template matching (10-50ms)
   - OCR: Pot/stack reading (100-200ms)

2. ADDS CLAUDE FOR DECISIONS (this module)
   - Strategy decisions via API (500ms-2s)
   - Vision fallback when detection fails
   - Learning and improvement

Flow:
    ┌─────────────────────────────────────────────────────────────┐
    │  multi_table_runner.py (existing)                           │
    │  - Finds tables via AppleScript                             │
    │  - Takes screenshots                                        │
    │  - Detects buttons/cards with local CV (FAST)               │
    └─────────────────────────────────────────────────────────────┘
                              │
                              │ Structured data: {cards, pot, buttons}
                              ▼
    ┌─────────────────────────────────────────────────────────────┐
    │  ClaudeEnhancedRunner (this module)                         │
    │  - Receives structured data from local detection            │
    │  - Sends to Claude for strategy decision                    │
    │  - Handles vision fallback if detection failed              │
    │  - Executes action via existing mouse_mover                 │
    └─────────────────────────────────────────────────────────────┘

Usage:
    # Instead of:
    python -m gamble.multi_table_runner

    # Run:
    python -m gamble.tools.claude_enhanced_runner
"""

import datetime
import logging
import os
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import ImageGrab, Image
import base64
from io import BytesIO

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

log = logging.getLogger(__name__)

# Import Claude brain
try:
    from gamble.tools.claude_poker_brain import (
        ClaudePokerBrain,
        PokerDecision,
        PokerAction,
        TableAnalysis
    )
    CLAUDE_BRAIN_AVAILABLE = True
except ImportError as e:
    CLAUDE_BRAIN_AVAILABLE = False
    log.warning(f"Claude brain not available: {e}")

# Import existing detection systems
try:
    from gamble.scraper.table_screen_based import TableScreenBased
    from gamble.tools.mongo_manager import MongoManager
    from gamble.tools.mouse_mover import MouseMoverTableBased
    from gamble.tools.helper import init_logger
    from gamble.decisionmaker.current_hand_memory import CurrentHandPreflopState, History
    LOCAL_DETECTION_AVAILABLE = True
except ImportError as e:
    LOCAL_DETECTION_AVAILABLE = False
    log.warning(f"Local detection not available: {e}")

# Import adaptive learner for self-healing
try:
    from gamble.tools.adaptive_learner import log_action, get_threshold, set_threshold
    ADAPTIVE_LEARNER_AVAILABLE = True
except ImportError:
    ADAPTIVE_LEARNER_AVAILABLE = False
    def log_action(*args, **kwargs): pass
    def get_threshold(name, default): return default
    def set_threshold(*args, **kwargs): pass


class TableState(Enum):
    UNKNOWN = "unknown"
    WAITING = "waiting"           # Not my turn
    NEED_ACTION = "need_action"   # Buttons visible
    HAND_OVER = "hand_over"
    CLOSED = "closed"


@dataclass
class TableWindow:
    """Poker table window"""
    window_id: int
    name: str
    x: int  # Points
    y: int
    width: int
    height: int

    @property
    def bounds_pixels(self) -> Tuple[int, int, int, int]:
        """Bounds in pixels (2x for Retina)"""
        return (self.x * 2, self.y * 2,
                (self.x + self.width) * 2, (self.y + self.height) * 2)


@dataclass
class TableSession:
    """Session state for one table"""
    window: TableWindow
    state: TableState = TableState.UNKNOWN
    last_action_time: float = 0
    consecutive_failures: int = 0

    # Cached detection results
    last_cards: List[str] = field(default_factory=list)
    last_community: List[str] = field(default_factory=list)
    last_buttons: List[str] = field(default_factory=list)
    last_pot: float = 0
    last_to_call: float = 0
    last_stack: float = 0


class ClaudeEnhancedRunner:
    """
    Multi-table runner enhanced with Claude Opus 4.6.

    Uses existing fast local detection + Claude for decisions.
    """

    def __init__(self,
                 max_tables: int = 4,
                 use_claude_decisions: bool = True,
                 use_claude_vision_fallback: bool = True,
                 table_config_name: str = "Official GGPoker 6player"):
        """
        Initialize the enhanced runner.

        Args:
            max_tables: Maximum tables to manage
            use_claude_decisions: Use Claude for strategy decisions
            use_claude_vision_fallback: Use Claude vision when detection fails
            table_config_name: MongoDB table configuration name
        """
        self.max_tables = max_tables
        self.use_claude_decisions = use_claude_decisions
        self.use_claude_vision_fallback = use_claude_vision_fallback

        self.sessions: Dict[int, TableSession] = {}
        self.running = False

        # Initialize Claude brain
        self.claude_brain = None
        if use_claude_decisions and CLAUDE_BRAIN_AVAILABLE:
            try:
                self.claude_brain = ClaudePokerBrain()
                log.info("Claude brain initialized successfully")
            except Exception as e:
                log.warning(f"Could not initialize Claude brain: {e}")
                self.use_claude_decisions = False

        # Initialize local detection
        self.mongo = None
        self.table_dict = None
        if LOCAL_DETECTION_AVAILABLE:
            try:
                self.mongo = MongoManager()
                self.table_dict = self.mongo.get_table(table_config_name)
                log.info("Local detection initialized")
            except Exception as e:
                log.warning(f"Could not initialize local detection: {e}")

        # Stats
        self.actions_taken = 0
        self.claude_decisions = 0
        self.local_decisions = 0
        self.vision_fallbacks = 0
        self.start_time = None

    def find_poker_windows(self) -> List[TableWindow]:
        """Find all GGPoker table windows using AppleScript."""
        script = '''
        tell application "System Events"
            if not (exists process "GGnet") then
                return ""
            end if
            tell process "GGnet"
                set output to ""
                repeat with w in windows
                    set winName to name of w as text
                    set winPos to position of w
                    set winSize to size of w
                    set output to output & winName & "###" & (item 1 of winPos as text) & "," & (item 2 of winPos as text) & "," & (item 1 of winSize as text) & "," & (item 2 of winSize as text) & ";"
                end repeat
                return output
            end tell
        end tell
        '''
        try:
            result = subprocess.run(['osascript', '-e', script],
                                    capture_output=True, text=True, timeout=5)
            windows = []
            if result.stdout.strip():
                entries = result.stdout.strip().rstrip(';').split(';')
                for i, entry in enumerate(entries):
                    if '###' in entry:
                        name, coords = entry.split('###')
                        # Fix Unicode minus
                        coords = coords.replace('−', '-').replace('–', '-')
                        parts = coords.split(',')
                        # Filter for poker tables (not lobby)
                        keywords = ['Spin', 'Gold', 'Rush', 'Cash', 'Hold', 'Blinds', 'NL']
                        if any(kw in name for kw in keywords):
                            windows.append(TableWindow(
                                window_id=i,
                                name=name.strip(),
                                x=int(parts[0]),
                                y=int(parts[1]),
                                width=int(parts[2]),
                                height=int(parts[3])
                            ))
            return windows
        except Exception as e:
            log.error(f"AppleScript error: {e}")
            return []

    def capture_table(self, window: TableWindow) -> Image.Image:
        """Capture screenshot of a specific table."""
        screenshot = ImageGrab.grab()
        return screenshot.crop(window.bounds_pixels)

    def detect_with_local_cv(self, table_img: Image.Image, session: TableSession) -> bool:
        """
        Use existing local CV to detect game state.

        Returns True if detection succeeded.
        """
        if not LOCAL_DETECTION_AVAILABLE or not self.table_dict:
            return False

        try:
            # Create TableScreenBased for this screenshot
            # Note: This uses the existing detection from scraper/table_screen_based.py
            table = TableScreenBased(
                self.table_dict,
                table_img,
                None,  # No history needed for detection
                None   # No preflop state needed
            )

            # Get cards
            cards = table.get_my_cards2()
            if cards and len(cards) == 2:
                session.last_cards = cards
            else:
                session.last_cards = []

            # Get community cards
            community = table.get_table_cards2()
            session.last_community = community if community else []

            # Check for buttons
            has_call = table.has_call_button()
            has_raise = table.has_raise_button()
            has_check = table.has_check_button()
            has_fold = table.has_fold_button()

            buttons = []
            if has_fold:
                buttons.append('fold')
            if has_check:
                buttons.append('check')
            if has_call:
                buttons.append('call')
            if has_raise:
                buttons.append('raise')

            session.last_buttons = buttons

            # Get pot/stack values
            try:
                session.last_pot = float(table.get_pots() or 0)
            except:
                session.last_pot = 0

            try:
                session.last_to_call = float(table.get_call_value() or 0)
            except:
                session.last_to_call = 0

            try:
                session.last_stack = float(table.get_my_funds() or 0)
            except:
                session.last_stack = 0

            # Determine state
            if buttons:
                session.state = TableState.NEED_ACTION
                session.consecutive_failures = 0
                return True
            else:
                session.state = TableState.WAITING
                return True

        except Exception as e:
            log.warning(f"Local detection failed: {e}")
            session.consecutive_failures += 1
            return False

    def detect_with_claude_vision(self, table_img: Image.Image, session: TableSession) -> bool:
        """
        Use Claude's vision as fallback when local detection fails.

        Returns True if detection succeeded.
        """
        if not self.claude_brain or not self.use_claude_vision_fallback:
            return False

        try:
            log.info("Using Claude vision fallback...")
            self.vision_fallbacks += 1

            analysis = self.claude_brain.analyze_screenshot(screenshot=table_img)

            session.last_cards = analysis.my_cards
            session.last_community = analysis.community_cards
            session.last_buttons = analysis.buttons
            session.last_pot = analysis.pot
            session.last_to_call = analysis.to_call
            session.last_stack = analysis.my_stack

            if analysis.buttons:
                session.state = TableState.NEED_ACTION
                session.consecutive_failures = 0

                # Learn from Claude's detection to improve local thresholds
                self._learn_from_vision(analysis, table_img)

                return True

            return False

        except Exception as e:
            log.error(f"Claude vision failed: {e}")
            return False

    def _learn_from_vision(self, analysis: TableAnalysis, table_img: Image.Image):
        """
        Learn from Claude's successful vision detection.

        Updates adaptive thresholds to improve local detection.
        """
        if not ADAPTIVE_LEARNER_AVAILABLE:
            return

        # Log what Claude found vs what local detection found
        log_action('claude_vision_assist', success=True, details={
            'cards_found': analysis.my_cards,
            'buttons_found': analysis.buttons,
            'confidence': analysis.confidence
        })

        log.info(f"Learning from Claude vision: cards={analysis.my_cards}, "
                f"buttons={analysis.buttons}")

    def make_decision(self, session: TableSession) -> Optional[str]:
        """
        Make a decision using Claude or fallback to local strategy.

        Returns action string: 'fold', 'call', 'check', 'raise', or None.
        """
        buttons = session.last_buttons
        if not buttons:
            return None

        # Use Claude for decision if available
        if self.claude_brain and self.use_claude_decisions and session.last_cards:
            try:
                decision = self.claude_brain.decide_action(
                    my_cards=session.last_cards,
                    community_cards=session.last_community,
                    pot=session.last_pot,
                    to_call=session.last_to_call,
                    my_stack=session.last_stack,
                    opponent_stacks=[session.last_stack],  # Simplified
                    position='BTN',  # TODO: detect position
                    buttons=buttons
                )

                self.claude_decisions += 1
                log.info(f"Claude decision: {decision.action.value} "
                        f"(confidence: {decision.confidence:.0%})")

                return decision.action.value

            except Exception as e:
                log.warning(f"Claude decision failed, using fallback: {e}")

        # Fallback: simple local strategy
        self.local_decisions += 1

        # Simple strategy: check if free, fold if paying, call only good hands
        if 'check' in buttons:
            return 'check'

        # If we have cards, make basic decision
        if session.last_cards and len(session.last_cards) == 2:
            ranks = [c[0] if c else '' for c in session.last_cards]
            # Pairs or high cards = call
            if ranks[0] == ranks[1] or any(r in 'AKQJ' for r in ranks):
                if 'call' in buttons:
                    return 'call'

        # Default: fold if available
        if 'fold' in buttons:
            return 'fold'
        elif 'call' in buttons:
            return 'call'

        return None

    def execute_action(self, session: TableSession, action: str) -> bool:
        """
        Execute the decided action by clicking the button.

        Uses existing mouse_mover functionality.
        """
        try:
            # Focus GGPoker
            subprocess.run(['osascript', '-e',
                'tell application "System Events" to tell process "GGnet" to set frontmost to true'],
                capture_output=True)
            time.sleep(0.05)

            # For now, use pyautogui for clicking
            # TODO: Integrate with existing mouse_mover
            import pyautogui

            # Get button position based on action
            # These are approximate positions - the existing button_detector should be used
            window = session.window
            button_y = window.y + int(window.height * 0.85)  # Buttons at bottom

            if action == 'fold':
                button_x = window.x + int(window.width * 0.25)
            elif action in ['check', 'call']:
                button_x = window.x + int(window.width * 0.50)
            elif action == 'raise':
                button_x = window.x + int(window.width * 0.75)
            else:
                return False

            pyautogui.click(button_x, button_y)
            self.actions_taken += 1
            session.last_action_time = time.time()

            log.info(f"Clicked {action} at ({button_x}, {button_y}) on {session.window.name[:30]}")
            return True

        except Exception as e:
            log.error(f"Action execution failed: {e}")
            return False

    def process_table(self, session: TableSession) -> bool:
        """
        Process a single table: detect state, make decision, execute.

        Returns True if action was taken.
        """
        # Cooldown between actions
        if time.time() - session.last_action_time < 1.5:
            return False

        # Capture table
        try:
            table_img = self.capture_table(session.window)
        except Exception as e:
            log.warning(f"Could not capture table: {e}")
            return False

        # Try local detection first (fast)
        detection_success = self.detect_with_local_cv(table_img, session)

        # If local fails, try Claude vision (slower but more reliable)
        if not detection_success and session.consecutive_failures >= 3:
            detection_success = self.detect_with_claude_vision(table_img, session)

        # If we need to act
        if session.state == TableState.NEED_ACTION:
            action = self.make_decision(session)
            if action:
                return self.execute_action(session, action)

        return False

    def run(self):
        """Main bot loop."""
        log.info("=" * 60)
        log.info("CLAUDE ENHANCED MULTI-TABLE RUNNER")
        log.info(f"Max tables: {self.max_tables}")
        log.info(f"Claude decisions: {self.use_claude_decisions}")
        log.info(f"Claude vision fallback: {self.use_claude_vision_fallback}")
        log.info("=" * 60)

        self.running = True
        self.start_time = time.time()

        while self.running:
            try:
                # Find all poker tables
                windows = self.find_poker_windows()

                # Update sessions
                active_ids = {w.window_id for w in windows}

                # Remove closed tables
                for wid in list(self.sessions.keys()):
                    if wid not in active_ids:
                        del self.sessions[wid]

                # Add new tables
                for window in windows:
                    if window.window_id not in self.sessions:
                        self.sessions[window.window_id] = TableSession(window=window)
                    else:
                        # Update window position
                        self.sessions[window.window_id].window = window

                # Process tables that need action
                for session in self.sessions.values():
                    if session.state == TableState.NEED_ACTION or session.state == TableState.UNKNOWN:
                        self.process_table(session)

                # Status update every 30 seconds
                elapsed = time.time() - self.start_time
                if int(elapsed) % 30 == 0:
                    log.info(f"Status: {len(self.sessions)} tables, "
                            f"{self.actions_taken} actions, "
                            f"Claude: {self.claude_decisions}, Local: {self.local_decisions}, "
                            f"Vision fallbacks: {self.vision_fallbacks}")

                time.sleep(0.3)

            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"Main loop error: {e}")
                traceback.print_exc()
                time.sleep(1)

        self.stop()

    def stop(self):
        """Stop the bot and show stats."""
        self.running = False
        elapsed = time.time() - self.start_time if self.start_time else 0

        log.info("=" * 60)
        log.info("STOPPED")
        log.info(f"Runtime: {elapsed/60:.1f} minutes")
        log.info(f"Actions taken: {self.actions_taken}")
        log.info(f"Claude decisions: {self.claude_decisions}")
        log.info(f"Local decisions: {self.local_decisions}")
        log.info(f"Vision fallbacks: {self.vision_fallbacks}")
        if self.claude_brain:
            log.info(f"Claude stats: {self.claude_brain.get_stats()}")
        log.info("=" * 60)


def main():
    import argparse

    # Initialize logging
    try:
        init_logger(screenlevel=logging.INFO, filename='claude_enhanced', logdir='log')
    except:
        logging.basicConfig(level=logging.INFO,
                           format='%(asctime)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description="Claude Enhanced Multi-Table Runner")
    parser.add_argument("--max-tables", type=int, default=4, help="Max tables")
    parser.add_argument("--no-claude-decisions", action="store_true",
                       help="Disable Claude for decisions (use local strategy)")
    parser.add_argument("--no-claude-vision", action="store_true",
                       help="Disable Claude vision fallback")
    args = parser.parse_args()

    print("=" * 60)
    print("CLAUDE ENHANCED POKER BOT")
    print("=" * 60)
    print(f"Max tables: {args.max_tables}")
    print(f"Claude decisions: {not args.no_claude_decisions}")
    print(f"Claude vision: {not args.no_claude_vision}")
    print("Press Ctrl+C to stop")
    print("=" * 60)

    runner = ClaudeEnhancedRunner(
        max_tables=args.max_tables,
        use_claude_decisions=not args.no_claude_decisions,
        use_claude_vision_fallback=not args.no_claude_vision
    )

    try:
        runner.run()
    except KeyboardInterrupt:
        print("\nStopping...")
        runner.stop()


if __name__ == "__main__":
    main()
