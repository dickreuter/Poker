"""
Table Session - Per-Table State Management for Multi-Table Support

Each TableSession represents one poker table and manages:
- Table position on screen (top-left corner)
- Current hand state (cards, pot, buttons)
- History for this table
- Decision making for this table

Usage:
    from sys_core.tools.table_session import TableSession

    session = TableSession(
        table_id=0,
        table_dict=mongo.get_table("Official GGSystem 6player"),
        strategy=strategy,
        window=(14, 850, 1200, 800)
    )

    state = session.capture_state(screenshot)
    if state['needs_action']:
        action = session.decide()
        session.execute(action)
"""

import datetime
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
from PIL import Image

from sys_core.tools import constants as const
from sys_core.tools.screen_operations import crop_screenshot_with_topleft_corner, binary_pil_to_cv2
from sys_core.tools.button_detector import ButtonDetector

log = logging.getLogger(__name__)


@dataclass
class TableState:
    """Current state of a poker table."""
    visible: bool = False
    tlc: Optional[Tuple[int, int]] = None  # Top-left corner position
    screenshot: Optional[Image.Image] = None

    # Cards
    my_cards: List[str] = field(default_factory=list)
    table_cards: List[str] = field(default_factory=list)

    # Game state
    dealer_position: int = 0
    players_in_game: List[int] = field(default_factory=list)
    my_funds: float = 0.0
    total_pot: float = 0.0
    round_pot: float = 0.0

    # Buttons
    button_active: bool = False  # Is it our turn?
    has_fold: bool = False
    has_call: bool = False
    has_check: bool = False
    has_bet: bool = False

    # Action info
    min_call: float = 0.0
    min_bet: float = 0.0

    # Meta
    needs_action: bool = False
    last_update: float = 0.0
    game_stage: str = 'PreFlop'


class TableSession:
    """
    Manages a single poker table session.

    Handles state capture, decision making, and action execution
    for one table in a multi-table setup.
    """

    def __init__(self, table_id: int, table_dict: Dict, strategy, window: Tuple[int, int, int, int] = None):
        """
        Initialize a table session.

        Args:
            table_id: Unique identifier for this table
            table_dict: Table template from MongoDB
            strategy: Strategy handler for decision making
            window: Optional (x, y, width, height) of table window
        """
        self.table_id = table_id
        self.table_dict = table_dict
        self.strategy = strategy
        self.window = window

        # State
        self.state = TableState()
        self.last_known_tlc = None

        # History
        self.hands_played = 0
        self.last_decision = None
        self.last_decision_time = None
        self.hand_history = []

        # Detection
        self.button_detector = ButtonDetector()
        self.topleft_corner = binary_pil_to_cv2(table_dict['topleft_corner'])

        log.info(f"TableSession {table_id} initialized")

    def capture_state(self, screenshot: Image.Image) -> TableState:
        """
        Capture current state of this table from screenshot.

        Args:
            screenshot: Full screen PIL Image

        Returns:
            TableState object with current table state
        """
        self.state = TableState()
        self.state.last_update = time.time()

        # Find table on screen
        cropped, tlc = crop_screenshot_with_topleft_corner(
            screenshot, self.topleft_corner, useSleep=False
        )

        if cropped is None:
            log.debug(f"Table {self.table_id}: not visible")
            self.state.visible = False
            return self.state

        self.state.visible = True
        self.state.tlc = tlc
        self.state.screenshot = cropped
        self.last_known_tlc = tlc

        # Update window position (store actual crop dimensions used)
        crop_w = cropped.width
        crop_h = cropped.height
        if self.window is None or self.window[0:2] != tlc:
            self.window = (tlc[0], tlc[1], crop_w, crop_h)
            log.debug(f"Table {self.table_id}: position updated to {tlc}, size {crop_w}x{crop_h}")

        # Detect buttons on the CROPPED screenshot using RELATIVE coordinates (0,0 based)
        # This fixes the coordinate mismatch bug - we're searching within the cropped table image
        buttons = self.button_detector.find_all_buttons(cropped, (0, 0, crop_w, crop_h))
        self.state.has_fold = buttons.get('fold') is not None
        self.state.has_call = buttons.get('call') is not None
        self.state.has_bet = buttons.get('bet') is not None

        # It's our turn if we have action buttons
        self.state.button_active = self.state.has_fold or self.state.has_call or self.state.has_bet

        # Needs action if buttons visible (cards detection done separately for speed)
        self.state.needs_action = self.state.button_active

        return self.state

    def capture_full_state(self, screenshot: Image.Image, table_scraper) -> TableState:
        """
        Capture complete state including cards, pots, players.
        This is more expensive - only call when action is needed.

        Args:
            screenshot: Full screen PIL Image
            table_scraper: TableScraper instance for this table

        Returns:
            TableState with full information
        """
        # First get basic state
        state = self.capture_state(screenshot)

        if not state.visible or not state.needs_action:
            return state

        # Now get detailed info using table_scraper
        try:
            table_scraper.screenshot = state.screenshot

            # Get cards
            table_scraper.get_my_cards2()
            state.my_cards = table_scraper.my_cards or []

            # Get table cards
            table_scraper.get_table_cards2()
            state.table_cards = table_scraper.table_cards or []

            # Determine game stage
            if len(state.table_cards) == 0:
                state.game_stage = 'PreFlop'
            elif len(state.table_cards) == 3:
                state.game_stage = 'Flop'
            elif len(state.table_cards) == 4:
                state.game_stage = 'Turn'
            elif len(state.table_cards) == 5:
                state.game_stage = 'River'

            # Get pots
            table_scraper.get_pots()
            state.total_pot = table_scraper.total_pot or 0.0
            state.round_pot = table_scraper.current_round_pot or 0.0

            # Get call/bet values
            if table_scraper.has_call_button():
                table_scraper.get_call_value()
                state.min_call = table_scraper.call_value or 0.0

            if table_scraper.has_bet_button() or table_scraper.has_raise_button():
                table_scraper.get_raise_value()
                state.min_bet = table_scraper.raise_value or 0.0

            # Needs action if buttons are visible (we'll fold if cards unknown)
            # Don't require cards to be detected - that causes missed timeouts
            state.needs_action = state.button_active

        except Exception as e:
            log.warning(f"Table {self.table_id}: Error capturing full state: {e}")

        return state

    def get_priority(self) -> int:
        """
        Calculate action priority for this table.

        Higher priority = more urgent action needed.

        Returns:
            Priority score (higher = more urgent)
        """
        score = 0

        # Base priority if we need action
        if self.state.needs_action:
            score += 100

        # Higher priority if it's our turn
        if self.state.button_active:
            score += 500

        # Higher priority for preflop (faster decisions)
        if self.state.game_stage == 'PreFlop':
            score += 50

        # Time-based priority (longer waiting = higher priority)
        time_since_update = time.time() - self.state.last_update
        score += min(int(time_since_update * 10), 100)

        return score

    def record_action(self, decision: str, result: bool = True):
        """
        Record an action taken on this table.

        Args:
            decision: The decision made (Fold, Call, etc.)
            result: Whether the action was executed successfully
        """
        self.last_decision = decision
        self.last_decision_time = datetime.datetime.utcnow()

        if decision in ['Fold', 'Call', 'Check']:
            self.hands_played += 1

        self.hand_history.append({
            'time': self.last_decision_time,
            'decision': decision,
            'cards': self.state.my_cards.copy() if self.state.my_cards else [],
            'table_cards': self.state.table_cards.copy() if self.state.table_cards else [],
            'game_stage': self.state.game_stage,
            'pot': self.state.total_pot,
            'result': result
        })

        log.info(f"Table {self.table_id}: Recorded {decision}")

    def get_status(self) -> Dict[str, Any]:
        """Get current status of this table session."""
        return {
            'table_id': self.table_id,
            'visible': self.state.visible,
            'position': self.state.tlc,
            'needs_action': self.state.needs_action,
            'button_active': self.state.button_active,
            'cards': self.state.my_cards,
            'game_stage': self.state.game_stage,
            'hands_played': self.hands_played,
            'last_decision': self.last_decision,
            'priority': self.get_priority()
        }

    def __repr__(self):
        return f"TableSession(id={self.table_id}, visible={self.state.visible}, needs_action={self.state.needs_action})"


class TableSessionManager:
    """
    Manages multiple table sessions.

    Provides methods to:
    - Discover tables on screen
    - Create/destroy sessions
    - Get priority-ordered list of tables needing action
    """

    def __init__(self, table_dict: Dict, strategy):
        """
        Initialize the session manager.

        Args:
            table_dict: Table template from MongoDB (shared by all tables)
            strategy: Strategy handler (shared by all tables)
        """
        self.table_dict = table_dict
        self.strategy = strategy
        self.sessions: Dict[int, TableSession] = {}
        self.next_id = 0

    def discover_tables(self, screenshot: Image.Image) -> List[TableSession]:
        """
        Find all tables on screen and create sessions for new ones.

        Args:
            screenshot: Full screen PIL Image

        Returns:
            List of all active sessions
        """
        from sys_core.tools.screen_operations import crop_screenshot_with_topleft_corner_multi

        topleft_corner = binary_pil_to_cv2(self.table_dict['topleft_corner'])
        tables = crop_screenshot_with_topleft_corner_multi(screenshot, topleft_corner)

        # Match found tables to existing sessions
        found_positions = set()
        for cropped, tlc in tables:
            found_positions.add(tlc)

            # Check if we already have a session at this position
            existing = self._find_session_at_position(tlc)

            if existing:
                # Update existing session
                existing.state.visible = True
                existing.state.tlc = tlc
                existing.state.screenshot = cropped

                # Detect buttons during discovery to know if action needed
                self._detect_buttons_for_session(existing, cropped)
            else:
                # Create new session with actual cropped dimensions
                crop_w = cropped.width
                crop_h = cropped.height
                session = TableSession(
                    table_id=self.next_id,
                    table_dict=self.table_dict,
                    strategy=self.strategy,
                    window=(tlc[0], tlc[1], crop_w, crop_h)
                )
                session.state.visible = True
                session.state.tlc = tlc
                session.state.screenshot = cropped
                session.last_known_tlc = tlc

                # Detect buttons during discovery to know if action needed
                self._detect_buttons_for_session(session, cropped)

                self.sessions[self.next_id] = session
                self.next_id += 1
                log.info(f"Discovered new table at {tlc}, assigned ID {session.table_id}, "
                        f"needs_action={session.state.needs_action}")

        # Mark sessions no longer visible
        for session in self.sessions.values():
            if session.last_known_tlc and session.last_known_tlc not in found_positions:
                session.state.visible = False

        return list(self.sessions.values())

    def _find_session_at_position(self, tlc: Tuple[int, int], tolerance: int = 50) -> Optional[TableSession]:
        """Find existing session near a position."""
        for session in self.sessions.values():
            if session.last_known_tlc:
                dx = abs(session.last_known_tlc[0] - tlc[0])
                dy = abs(session.last_known_tlc[1] - tlc[1])
                if dx < tolerance and dy < tolerance:
                    return session
        return None

    def _detect_buttons_for_session(self, session: TableSession, cropped: Image.Image):
        """
        Detect buttons on a table to determine if action is needed.

        Args:
            session: The table session to update
            cropped: Cropped screenshot of the table
        """
        try:
            # Use relative coordinates (0,0) since we're searching the cropped image
            crop_w = cropped.width
            crop_h = cropped.height
            buttons = session.button_detector.find_all_buttons(cropped, (0, 0, crop_w, crop_h))

            session.state.has_fold = buttons.get('fold') is not None
            session.state.has_call = buttons.get('call') is not None
            session.state.has_bet = buttons.get('bet') is not None

            # It's our turn if we have action buttons
            session.state.button_active = (
                session.state.has_fold or
                session.state.has_call or
                session.state.has_bet
            )

            # Needs action if buttons visible
            session.state.needs_action = session.state.button_active

            if session.state.needs_action:
                log.debug(f"Table {session.table_id}: action needed (fold={session.state.has_fold}, "
                         f"call={session.state.has_call}, bet={session.state.has_bet})")

        except Exception as e:
            log.debug(f"Table {session.table_id}: button detection error: {e}")

    def get_sessions_needing_action(self) -> List[TableSession]:
        """
        Get sessions that need action, sorted by priority.

        Returns:
            List of sessions sorted by priority (highest first)
        """
        active = [s for s in self.sessions.values() if s.state.visible and s.state.needs_action]
        return sorted(active, key=lambda s: s.get_priority(), reverse=True)

    def get_all_sessions(self) -> List[TableSession]:
        """Get all active sessions."""
        return [s for s in self.sessions.values() if s.state.visible]

    def get_session(self, table_id: int) -> Optional[TableSession]:
        """Get session by ID."""
        return self.sessions.get(table_id)

    def remove_session(self, table_id: int):
        """Remove a session."""
        if table_id in self.sessions:
            del self.sessions[table_id]
            log.info(f"Removed table session {table_id}")

    def get_status(self) -> Dict[str, Any]:
        """Get status of all sessions."""
        return {
            'total_sessions': len(self.sessions),
            'visible_sessions': len([s for s in self.sessions.values() if s.state.visible]),
            'needs_action': len(self.get_sessions_needing_action()),
            'sessions': [s.get_status() for s in self.sessions.values()]
        }


if __name__ == "__main__":
    # Test table session
    from PIL import ImageGrab
    from sys_core.tools.mongo_manager import MongoManager

    print("Loading table template...")
    mongo = MongoManager()
    table_dict = mongo.get_table("Official GGSystem 6player")

    print("Creating session manager...")
    manager = TableSessionManager(table_dict, None)

    print("Taking screenshot...")
    screenshot = ImageGrab.grab()

    print("Discovering tables...")
    sessions = manager.discover_tables(screenshot)

    print(f"\nFound {len(sessions)} table(s):")
    for session in sessions:
        status = session.get_status()
        print(f"  Table {status['table_id']}: position={status['position']}, "
              f"needs_action={status['needs_action']}, priority={status['priority']}")

    print("\nManager status:")
    print(manager.get_status())
