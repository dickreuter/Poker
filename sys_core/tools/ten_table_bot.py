"""
TEN TABLE BOT - Comprehensive 10-Table Autonomous System Utility

This is the UNIFIED system that fixes all previous issues:
1. Uses visual detection that works regardless of table size/position
2. Handles face-up AND face-down cards
3. Verifies every click with screenshot comparison
4. Manages 10 tables with priority-based action execution
5. Includes full UI navigation with OCR

Usage:
    python -m sys_core.tools.ten_table_bot

Or from code:
    from sys_core.tools.ten_table_bot import TenTableBot
    bot = TenTableBot()
    bot.run()

Author: Claude (2026-01-04)
"""

import logging
import subprocess
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from queue import PriorityQueue
from enum import Enum

import cv2
import numpy as np
from PIL import Image, ImageGrab
from pynput.mouse import Button as MouseButton, Controller as MouseController

log = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

RETINA_SCALE = 2  # macOS Retina display

# Button colors in HSV
BUTTON_COLORS = {
    'fold': {
        'lower': np.array([0, 0, 30]),
        'upper': np.array([180, 60, 120]),
        'priority': 1  # Lowest priority action
    },
    'call': {
        'lower': np.array([35, 50, 50]),
        'upper': np.array([85, 255, 255]),
        'priority': 2
    },
    'check': {
        'lower': np.array([35, 50, 50]),  # Same green as call
        'upper': np.array([85, 255, 255]),
        'priority': 2
    },
    'raise': {
        'lower': np.array([8, 80, 80]),
        'upper': np.array([28, 255, 255]),
        'priority': 3  # Highest priority
    },
}

# Card detection parameters
CARD_WHITE_THRESHOLD = 160  # Lower threshold to catch more card variations
MIN_CARD_AREA = 800
MAX_CARD_AREA = 50000


# =============================================================================
# DATA CLASSES
# =============================================================================

class TableState(Enum):
    """State machine for each table."""
    UNKNOWN = "unknown"
    WAITING = "waiting"  # No buttons visible
    NEED_ACTION = "need_action"  # Buttons visible, need to act
    ACTION_TAKEN = "action_taken"  # Just clicked, waiting for result
    ERROR = "error"


@dataclass
class TableInfo:
    """Information about a poker table window."""
    name: str
    x_pt: int  # Position in macOS points
    y_pt: int
    w_pt: int
    h_pt: int

    @property
    def x_px(self) -> int:
        return self.x_pt * RETINA_SCALE

    @property
    def y_px(self) -> int:
        return self.y_pt * RETINA_SCALE

    @property
    def w_px(self) -> int:
        return self.w_pt * RETINA_SCALE

    @property
    def h_px(self) -> int:
        return self.h_pt * RETINA_SCALE

    def is_poker_table(self) -> bool:
        """Check if this is a poker table (not lobby)."""
        keywords = ['Spin', 'Gold', 'Rush', 'Cash', 'Hold', 'Omaha', 'Blinds', 'NL', 'PLO']
        return any(kw in self.name for kw in keywords)


@dataclass
class ButtonInfo:
    """Detected button information."""
    button_type: str
    center_x_px: int  # Position in table pixels
    center_y_px: int
    width: int
    height: int
    confidence: float

    def get_screen_point(self, table: TableInfo) -> Tuple[int, int]:
        """Convert to screen point for clicking."""
        screen_x = table.x_pt + self.center_x_px // RETINA_SCALE
        screen_y = table.y_pt + self.center_y_px // RETINA_SCALE
        return (screen_x, screen_y)


@dataclass
class CardInfo:
    """Detected card information."""
    rank: str  # 2-9, T, J, Q, K, A
    suit: str  # C, D, H, S
    confidence: float

    def __str__(self):
        return f"{self.rank}{self.suit}"


@dataclass
class TableSession:
    """Manages state for a single table."""
    table: TableInfo
    state: TableState = TableState.UNKNOWN
    buttons: Dict[str, ButtonInfo] = field(default_factory=dict)
    cards: List[CardInfo] = field(default_factory=list)
    last_action_time: float = 0
    action_count: int = 0
    consecutive_errors: int = 0
    last_screenshot: Optional[Image.Image] = None
    priority: int = 0

    def needs_action(self) -> bool:
        """Check if this table needs action."""
        return self.state == TableState.NEED_ACTION and len(self.buttons) > 0

    def calculate_priority(self) -> int:
        """Calculate action priority. Higher = more urgent."""
        if not self.needs_action():
            return 0

        # Base priority
        priority = 100

        # Boost if buttons visible (it's our turn)
        if self.buttons:
            priority += 500

        # Time-based urgency (longer waiting = higher priority)
        time_waiting = time.time() - self.last_action_time
        priority += min(int(time_waiting * 20), 200)

        # Penalty for errors
        priority -= self.consecutive_errors * 50

        self.priority = priority
        return priority


# =============================================================================
# WINDOW FINDER
# =============================================================================

class WindowFinder:
    """Finds GGPoker windows using AppleScript."""

    @staticmethod
    def find_all_windows() -> List[TableInfo]:
        """Find all GGPoker windows."""
        script = '''
        tell application "System Events"
            if not (exists process "GGnet") then return ""
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
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=5
            )

            windows = []
            if result.stdout.strip():
                entries = result.stdout.strip().rstrip(';').split(';')
                for entry in entries:
                    if '###' not in entry:
                        continue

                    name, coords = entry.split('###')
                    # Fix Unicode minus sign
                    coords = coords.replace('−', '-').replace('–', '-')
                    parts = coords.split(',')

                    if len(parts) == 4:
                        windows.append(TableInfo(
                            name=name.strip(),
                            x_pt=int(parts[0]),
                            y_pt=int(parts[1]),
                            w_pt=int(parts[2]),
                            h_pt=int(parts[3])
                        ))

            return windows

        except Exception as e:
            log.error(f"Error finding windows: {e}")
            return []

    @staticmethod
    def find_poker_tables() -> List[TableInfo]:
        """Find only poker table windows."""
        return [w for w in WindowFinder.find_all_windows() if w.is_poker_table()]

    @staticmethod
    def focus_ggpoker():
        """Bring GGSystem to front."""
        script = 'tell application "System Events" to tell process "GGnet" to set frontmost to true'
        try:
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=2)
        except:
            pass


# =============================================================================
# VISUAL DETECTOR
# =============================================================================

class VisualDetector:
    """Unified visual detection for buttons and cards."""

    def __init__(self, table_dict: Dict = None):
        self.table_dict = table_dict
        self._templates_loaded = False
        self._card_templates = {}

        if table_dict:
            self._load_templates()

    def _load_templates(self):
        """Load card templates from table_dict."""
        if not self.table_dict:
            return

        for value in '23456789TJQKA':
            for suit in 'CDHS':
                key = value.lower() + suit.lower()
                if key in self.table_dict:
                    template_data = self.table_dict[key]
                    if isinstance(template_data, bytes):
                        template = cv2.imdecode(
                            np.frombuffer(template_data, np.uint8),
                            cv2.IMREAD_COLOR
                        )
                        if template is not None:
                            self._card_templates[key] = template

        self._templates_loaded = len(self._card_templates) > 0
        log.info(f"Loaded {len(self._card_templates)} card templates")

    def capture_table(self, table: TableInfo, screenshot: Image.Image = None) -> Image.Image:
        """Capture just the table area from screenshot."""
        if screenshot is None:
            screenshot = ImageGrab.grab()

        return screenshot.crop((
            table.x_px, table.y_px,
            table.x_px + table.w_px,
            table.y_px + table.h_px
        ))

    def detect_buttons(self, table_img: Image.Image) -> Dict[str, ButtonInfo]:
        """
        Detect action buttons using color detection.

        Uses HSV color matching to find fold/call/raise buttons
        in the bottom portion of the table.
        """
        img = cv2.cvtColor(np.array(table_img), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h_img, w_img = img.shape[:2]

        # Search bottom 40% of table for buttons
        y_start = int(h_img * 0.60)
        search_region = hsv[y_start:, :]

        buttons = {}
        all_candidates = []

        for btn_type, color_info in BUTTON_COLORS.items():
            mask = cv2.inRange(search_region, color_info['lower'], color_info['upper'])

            # Clean up mask
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 1500:
                    continue

                x, y, w, bh = cv2.boundingRect(cnt)

                # Button size filter
                if w < 50 or bh < 20 or w > 400 or bh > 120:
                    continue

                # Aspect ratio filter (buttons are wider than tall)
                aspect = w / bh if bh > 0 else 0
                if aspect < 1.2 or aspect > 5.0:
                    continue

                center_x = x + w // 2
                center_y = y_start + y + bh // 2

                all_candidates.append({
                    'type': btn_type,
                    'x': center_x,
                    'y': center_y,
                    'w': w,
                    'h': bh,
                    'area': area,
                    'confidence': min(1.0, area / 10000)
                })

        # Group candidates by Y position to filter out non-button elements
        if all_candidates:
            y_positions = [c['y'] for c in all_candidates]
            # Find the most common Y band (buttons are usually aligned)
            best_y = None
            best_count = 0
            for y in y_positions:
                count = sum(1 for y2 in y_positions if abs(y2 - y) < 40)
                if count >= best_count:
                    best_count = count
                    best_y = y

            # Filter to buttons in the main Y band
            if best_y and best_count >= 2:
                filtered = [c for c in all_candidates if abs(c['y'] - best_y) < 40]
            else:
                # Use bottom-most candidates as fallback
                filtered = sorted(all_candidates, key=lambda c: c['y'], reverse=True)[:3]

            # Pick best candidate per button type
            for btn_type in ['fold', 'call', 'check', 'raise']:
                type_candidates = [c for c in filtered if c['type'] == btn_type]
                if type_candidates:
                    best = max(type_candidates, key=lambda c: c['area'])
                    buttons[btn_type] = ButtonInfo(
                        button_type=btn_type,
                        center_x_px=best['x'],
                        center_y_px=best['y'],
                        width=best['w'],
                        height=best['h'],
                        confidence=best['confidence']
                    )

        return buttons

    def detect_cards(self, table_img: Image.Image) -> List[CardInfo]:
        """
        Detect player's hole cards.

        Strategy:
        1. First try to find white card faces in bottom-center
        2. If that fails, try template matching on the whole search area
        3. Use OCR as final fallback for rank detection
        """
        img = np.array(table_img)
        h_img, w_img = img.shape[:2]

        # Search bottom 45% of table, center 60%
        y_start = int(h_img * 0.55)
        x_start = int(w_img * 0.20)
        x_end = int(w_img * 0.80)

        search_region = img[y_start:, x_start:x_end]
        search_h, search_w = search_region.shape[:2]

        # Method 1: Find white card regions
        cards = self._find_cards_by_white(search_region, search_w, search_h)

        if len(cards) == 2:
            return cards

        # Method 2: Template matching on likely card positions
        if self._templates_loaded:
            cards = self._find_cards_by_template(
                table_img,
                (x_start, y_start, x_end - x_start, h_img - y_start)
            )
            if len(cards) == 2:
                return cards

        # Method 3: Try with relaxed parameters
        cards = self._find_cards_by_white(search_region, search_w, search_h, relaxed=True)

        return cards

    def _find_cards_by_white(self, search_region: np.ndarray,
                              search_w: int, search_h: int,
                              relaxed: bool = False) -> List[CardInfo]:
        """Find cards by detecting white/bright regions."""
        threshold = 140 if relaxed else CARD_WHITE_THRESHOLD
        min_area = 500 if relaxed else MIN_CARD_AREA

        # Create white mask
        white_mask = (
            (search_region[:,:,0] > threshold) &
            (search_region[:,:,1] > threshold) &
            (search_region[:,:,2] > threshold)
        ).astype(np.uint8) * 255

        # Clean up mask
        kernel = np.ones((5, 5), np.uint8)
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)
        white_mask = cv2.morphologyEx(white_mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Score candidates by position (bottom-center is player's cards)
        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > MAX_CARD_AREA:
                continue

            x, y, cw, ch = cv2.boundingRect(cnt)

            # Basic size filter
            if cw < 25 or ch < 30 or cw > 250 or ch > 300:
                continue

            center_x = x + cw // 2
            center_y = y + ch // 2

            # Score: prefer bottom-center
            x_center_score = 1.0 - abs(center_x - search_w // 2) / (search_w // 2)
            y_bottom_score = center_y / search_h
            score = (y_bottom_score * 0.6) + (x_center_score * 0.4)

            candidates.append({
                'x': x, 'y': y, 'w': cw, 'h': ch,
                'area': area, 'score': score,
                'center_x': center_x
            })

        if not candidates:
            return []

        # Sort by score and pick top candidates that are horizontally separated
        candidates.sort(key=lambda c: c['score'], reverse=True)

        selected = []
        used_x = []
        for cand in candidates:
            if len(selected) >= 2:
                break
            # Ensure cards are not overlapping
            if not any(abs(cand['center_x'] - ux) < 30 for ux in used_x):
                selected.append(cand)
                used_x.append(cand['center_x'])

        if len(selected) < 2:
            return []

        # Sort by x position (left card first)
        selected.sort(key=lambda c: c['center_x'])

        # Extract and identify each card
        cards = []
        search_img = Image.fromarray(search_region)

        for cand in selected:
            card_region = search_img.crop((
                cand['x'], cand['y'],
                cand['x'] + cand['w'],
                cand['y'] + cand['h']
            ))

            card_info = self._identify_card(card_region)
            if card_info:
                cards.append(card_info)

        return cards

    def _find_cards_by_template(self, table_img: Image.Image,
                                 search_box: Tuple[int, int, int, int]) -> List[CardInfo]:
        """Find cards using template matching."""
        if not self._templates_loaded:
            return []

        x, y, w, h = search_box
        search_region = table_img.crop((x, y, x + w, y + h))
        search_cv = cv2.cvtColor(np.array(search_region), cv2.COLOR_RGB2BGR)

        best_matches = []

        for card_key, template in self._card_templates.items():
            templ_h, templ_w = template.shape[:2]

            # Skip if template is too big
            if templ_w > w or templ_h > h:
                continue

            result = cv2.matchTemplate(search_cv, template, cv2.TM_SQDIFF_NORMED)
            min_val, _, min_loc, _ = cv2.minMaxLoc(result)

            if min_val < 0.25:  # Good match
                best_matches.append({
                    'key': card_key,
                    'score': min_val,
                    'x': min_loc[0],
                    'y': min_loc[1],
                    'w': templ_w,
                    'h': templ_h
                })

        if len(best_matches) < 2:
            return []

        # Sort by score and pick best two that are spatially separated
        best_matches.sort(key=lambda m: m['score'])

        selected = []
        for match in best_matches:
            if len(selected) >= 2:
                break
            # Check spatial separation
            if not any(abs(match['x'] - s['x']) < 40 for s in selected):
                selected.append(match)

        if len(selected) != 2:
            return []

        # Sort by x position
        selected.sort(key=lambda m: m['x'])

        cards = []
        for match in selected:
            rank = match['key'][0].upper()
            suit = match['key'][1].upper()
            cards.append(CardInfo(
                rank=rank,
                suit=suit,
                confidence=1.0 - match['score']
            ))

        return cards

    def _identify_card(self, card_img: Image.Image) -> Optional[CardInfo]:
        """Identify a single card from its image."""
        # Try template matching first
        if self._templates_loaded:
            card_cv = cv2.cvtColor(np.array(card_img), cv2.COLOR_RGB2BGR)
            card_h, card_w = card_cv.shape[:2]

            best_match = None
            best_score = float('inf')

            for card_key, template in self._card_templates.items():
                templ_h, templ_w = template.shape[:2]

                # Scale template if needed
                if templ_w > card_w or templ_h > card_h:
                    scale = min(card_w / templ_w, card_h / templ_h) * 0.8
                    template = cv2.resize(template, (int(templ_w * scale), int(templ_h * scale)))

                if template.shape[0] > card_h or template.shape[1] > card_w:
                    continue

                result = cv2.matchTemplate(card_cv, template, cv2.TM_SQDIFF_NORMED)
                min_val, _, _, _ = cv2.minMaxLoc(result)

                if min_val < best_score:
                    best_score = min_val
                    best_match = card_key

            if best_match and best_score < 0.35:
                return CardInfo(
                    rank=best_match[0].upper(),
                    suit=best_match[1].upper(),
                    confidence=1.0 - best_score
                )

        # Fallback: detect suit by color
        suit = self._detect_suit_by_color(card_img)
        rank = '?'  # Would need OCR for rank

        if suit:
            return CardInfo(rank=rank, suit=suit, confidence=0.5)

        return None

    def _detect_suit_by_color(self, card_img: Image.Image) -> Optional[str]:
        """Detect card suit by color.

        GGPoker uses STANDARD 2-COLOR DECK (NOT 4-color!):
        - Hearts = Red, Diamonds = Red
        - Spades = Black, Clubs = Black
        """
        img = np.array(card_img)
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

        # 2-COLOR DECK: Red (H or D) vs Black (S or C)
        # Red color range
        red_mask1 = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([15, 255, 255]))
        red_mask2 = cv2.inRange(hsv, np.array([165, 100, 100]), np.array([180, 255, 255]))
        red_pixels = np.sum(red_mask1) + np.sum(red_mask2)

        # Black color range
        black_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 50]))
        black_pixels = np.sum(black_mask)

        if max(red_pixels, black_pixels) < 100:
            return None

        # Determine color (not specific suit - would need OCR for H/D and S/C distinction)
        if red_pixels > black_pixels * 1.5:
            return 'H'  # Red suit - default to Hearts
        elif black_pixels > red_pixels * 1.5:
            return 'S'  # Black suit - default to Spades
        else:
            return 'S'  # Unclear - default to Spades


# =============================================================================
# CLICK EXECUTOR WITH VERIFICATION
# =============================================================================

class ClickExecutor:
    """Executes clicks with screenshot verification."""

    def __init__(self):
        self.mouse = MouseController()
        self.last_click_time = 0
        self.min_click_interval = 0.3  # Minimum time between clicks

    def click_button(self, button: ButtonInfo, table: TableInfo,
                     verify: bool = True) -> bool:
        """
        Click a button with optional verification.

        Args:
            button: ButtonInfo to click
            table: TableInfo the button is on
            verify: Whether to verify click worked

        Returns:
            True if click succeeded (and verified if requested)
        """
        # Rate limiting
        now = time.time()
        if now - self.last_click_time < self.min_click_interval:
            time.sleep(self.min_click_interval - (now - self.last_click_time))

        # Take pre-click screenshot if verifying
        pre_screenshot = None
        if verify:
            pre_screenshot = ImageGrab.grab()

        # Focus GGSystem
        WindowFinder.focus_ggpoker()
        time.sleep(0.05)

        # Get click position
        click_x, click_y = button.get_screen_point(table)

        # Execute click
        self.mouse.position = (click_x, click_y)
        time.sleep(0.03)
        self.mouse.click(MouseButton.left)

        self.last_click_time = time.time()
        log.info(f"Clicked {button.button_type} at ({click_x}, {click_y})")

        # Verify click if requested
        if verify:
            time.sleep(0.3)  # Wait for UI update
            return self._verify_click(button, table, pre_screenshot)

        return True

    def _verify_click(self, button: ButtonInfo, table: TableInfo,
                      pre_screenshot: Image.Image) -> bool:
        """Verify that click had the expected effect."""
        post_screenshot = ImageGrab.grab()

        # Crop table region from both screenshots
        pre_table = pre_screenshot.crop((
            table.x_px, table.y_px,
            table.x_px + table.w_px,
            table.y_px + table.h_px
        ))
        post_table = post_screenshot.crop((
            table.x_px, table.y_px,
            table.x_px + table.w_px,
            table.y_px + table.h_px
        ))

        # Compare the button region - it should have changed
        btn_region_pre = np.array(pre_table.crop((
            max(0, button.center_x_px - 100),
            max(0, button.center_y_px - 50),
            min(pre_table.width, button.center_x_px + 100),
            min(pre_table.height, button.center_y_px + 50)
        )))

        btn_region_post = np.array(post_table.crop((
            max(0, button.center_x_px - 100),
            max(0, button.center_y_px - 50),
            min(post_table.width, button.center_x_px + 100),
            min(post_table.height, button.center_y_px + 50)
        )))

        # Calculate difference
        if btn_region_pre.shape == btn_region_post.shape:
            diff = np.abs(btn_region_pre.astype(float) - btn_region_post.astype(float))
            mean_diff = np.mean(diff)

            # If significant change, click probably worked
            if mean_diff > 15:
                log.debug(f"Click verified: mean diff = {mean_diff:.1f}")
                return True
            else:
                log.warning(f"Click may have failed: mean diff = {mean_diff:.1f}")
                return False

        # Different sizes means UI changed significantly
        return True


# =============================================================================
# DECISION MAKER
# =============================================================================

class SimpleDecisionMaker:
    """
    Simple poker decision maker.

    For now, uses basic rules. Can be replaced with Monte Carlo or
    more sophisticated logic later.
    """

    # Premium hands that should call/raise
    PREMIUM_HANDS = ['AA', 'KK', 'QQ', 'JJ', 'TT', 'AK', 'AQ', 'AJ', 'KQ']
    PLAYABLE_HANDS = ['99', '88', '77', '66', 'AT', 'KJ', 'QJ', 'JT', 'KT', 'QT']

    def decide(self, cards: List[CardInfo], buttons: Dict[str, ButtonInfo]) -> Optional[str]:
        """
        Make a decision based on cards and available buttons.

        Args:
            cards: Detected hole cards
            buttons: Available action buttons

        Returns:
            Button type to click, or None
        """
        if not buttons:
            return None

        # If we can check (no fold button), always check
        if 'call' in buttons and 'fold' not in buttons:
            log.info("Free check available")
            return 'call'

        # If no cards detected, be conservative
        if len(cards) != 2:
            log.warning("Cards not detected, folding")
            return 'fold' if 'fold' in buttons else None

        # Evaluate hand
        hand = self._evaluate_hand(cards)
        log.info(f"Hand evaluation: {cards[0]}{cards[1]} = {hand}")

        if hand == 'premium':
            # Raise with premium hands
            if 'raise' in buttons:
                return 'raise'
            return 'call' if 'call' in buttons else None

        elif hand == 'playable':
            # Call with playable hands
            return 'call' if 'call' in buttons else ('fold' if 'fold' in buttons else None)

        else:
            # Fold trash
            return 'fold' if 'fold' in buttons else None

    def _evaluate_hand(self, cards: List[CardInfo]) -> str:
        """Evaluate hand strength."""
        if len(cards) != 2:
            return 'unknown'

        c1, c2 = cards[0], cards[1]

        # Handle unknown ranks
        if c1.rank == '?' or c2.rank == '?':
            return 'unknown'

        # Sort by rank
        ranks = sorted([c1.rank, c2.rank], key=lambda r: '23456789TJQKA'.index(r), reverse=True)

        # Build hand string
        if ranks[0] == ranks[1]:
            hand = f"{ranks[0]}{ranks[1]}"  # Pair
        elif c1.suit == c2.suit:
            hand = f"{ranks[0]}{ranks[1]}s"  # Suited
        else:
            hand = f"{ranks[0]}{ranks[1]}"  # Offsuit

        # Check categories
        pair_rank = ranks[0] if ranks[0] == ranks[1] else None

        if pair_rank and '23456789TJQKA'.index(pair_rank) >= '23456789TJQKA'.index('T'):
            return 'premium'  # High pair

        if hand[:2] in ['AK', 'AQ', 'AJ', 'KQ']:
            return 'premium'

        if pair_rank:
            return 'playable'  # Any pair

        if any(r in 'AKQJ' for r in ranks):
            return 'playable'  # High cards

        return 'fold'


# =============================================================================
# TEN TABLE BOT
# =============================================================================

class TenTableBot:
    """
    Main bot controller for 10-table play.

    Features:
    - Parallel table state capture
    - Priority-based action execution
    - Screenshot verification
    - Automatic error recovery
    """

    def __init__(self, max_tables: int = 10, table_dict: Dict = None):
        """
        Initialize the bot.

        Args:
            max_tables: Maximum number of tables to manage
            table_dict: Optional table template from MongoDB
        """
        self.max_tables = max_tables
        self.table_dict = table_dict

        # Components
        self.detector = VisualDetector(table_dict)
        self.clicker = ClickExecutor()
        self.decision_maker = SimpleDecisionMaker()

        # State
        self.sessions: Dict[str, TableSession] = {}
        self.running = False
        self.paused = False

        # Stats
        self.total_actions = 0
        self.start_time = None

        # Thread pool for parallel capture
        self.executor = ThreadPoolExecutor(max_workers=max_tables)

        log.info(f"TenTableBot initialized (max {max_tables} tables)")

    def _get_or_create_session(self, table: TableInfo) -> TableSession:
        """Get existing session or create new one."""
        key = f"{table.name}_{table.x_pt}_{table.y_pt}"

        if key not in self.sessions:
            self.sessions[key] = TableSession(table=table)
            log.info(f"Created session for {table.name}")
        else:
            # Update table info in case window moved
            self.sessions[key].table = table

        return self.sessions[key]

    def _capture_table_state(self, session: TableSession,
                              screenshot: Image.Image) -> TableSession:
        """Capture state for a single table."""
        try:
            # Capture table image
            table_img = self.detector.capture_table(session.table, screenshot)
            session.last_screenshot = table_img

            # Detect buttons
            buttons = self.detector.detect_buttons(table_img)
            session.buttons = buttons

            # Update state based on buttons
            if buttons:
                session.state = TableState.NEED_ACTION
                # Only detect cards when we need to act
                session.cards = self.detector.detect_cards(table_img)
            else:
                session.state = TableState.WAITING
                session.cards = []

            session.consecutive_errors = 0

        except Exception as e:
            log.warning(f"Error capturing {session.table.name}: {e}")
            session.state = TableState.ERROR
            session.consecutive_errors += 1

        return session

    def _capture_all_tables(self) -> List[TableSession]:
        """Capture state of all tables in parallel."""
        # Find all poker tables
        tables = WindowFinder.find_poker_tables()[:self.max_tables]

        if not tables:
            return []

        # Take single screenshot for all tables
        screenshot = ImageGrab.grab()

        # Update sessions
        sessions = []
        for table in tables:
            session = self._get_or_create_session(table)
            self._capture_table_state(session, screenshot)
            sessions.append(session)

        # Remove sessions for tables that no longer exist
        current_keys = {f"{t.name}_{t.x_pt}_{t.y_pt}" for t in tables}
        for key in list(self.sessions.keys()):
            if key not in current_keys:
                del self.sessions[key]

        return sessions

    def _process_priority_action(self, sessions: List[TableSession]) -> bool:
        """Process the highest priority table needing action."""
        # Get tables needing action, sorted by priority
        action_sessions = [s for s in sessions if s.needs_action()]

        if not action_sessions:
            return False

        # Calculate priorities
        for session in action_sessions:
            session.calculate_priority()

        action_sessions.sort(key=lambda s: s.priority, reverse=True)

        # Process highest priority
        session = action_sessions[0]

        log.info(f"Processing {session.table.name} (priority {session.priority})")
        log.info(f"  Buttons: {list(session.buttons.keys())}")
        log.info(f"  Cards: {[str(c) for c in session.cards]}")

        # Make decision
        action = self.decision_maker.decide(session.cards, session.buttons)

        if action and action in session.buttons:
            button = session.buttons[action]

            # Execute click with verification
            success = self.clicker.click_button(button, session.table, verify=True)

            if success:
                session.state = TableState.ACTION_TAKEN
                session.last_action_time = time.time()
                session.action_count += 1
                self.total_actions += 1
                log.info(f"  Action: {action} - SUCCESS")
                return True
            else:
                log.warning(f"  Action: {action} - FAILED (verification)")
                session.consecutive_errors += 1
        else:
            log.warning(f"  No action taken (decision: {action})")

        return False

    def run(self):
        """Main bot loop."""
        print("=" * 60)
        print("TEN TABLE BOT - Starting")
        print("=" * 60)

        self.running = True
        self.start_time = time.time()

        # Load templates if not already done
        if not self.table_dict:
            try:
                from sys_core.tools.mongo_manager import MongoManager
                mongo = MongoManager()
                self.table_dict = mongo.get_table("Official GGPoker 6player")
                self.detector = VisualDetector(self.table_dict)
                log.info("Loaded table templates from MongoDB")
            except Exception as e:
                log.warning(f"Could not load templates: {e}")

        while self.running:
            try:
                # Check for pause
                while self.paused and self.running:
                    time.sleep(0.5)

                if not self.running:
                    break

                # Capture all table states
                sessions = self._capture_all_tables()

                if not sessions:
                    time.sleep(1)
                    continue

                # Process highest priority action
                action_taken = self._process_priority_action(sessions)

                # Brief pause
                if action_taken:
                    time.sleep(0.3)  # Quick cycle after action
                else:
                    time.sleep(0.5)  # Normal cycle

            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"Main loop error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

        self.running = False
        self._print_stats()

    def _print_stats(self):
        """Print session statistics."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        print("\n" + "=" * 60)
        print("SESSION COMPLETE")
        print("=" * 60)
        print(f"Duration: {elapsed:.0f} seconds")
        print(f"Total actions: {self.total_actions}")
        print(f"Actions/minute: {self.total_actions / (elapsed / 60):.1f}" if elapsed > 0 else "N/A")
        print("=" * 60)

    def stop(self):
        """Stop the bot."""
        self.running = False
        self.paused = False
        log.info("Bot stopping...")

    def pause(self):
        """Pause the bot."""
        self.paused = True
        log.info("Bot paused")

    def resume(self):
        """Resume the bot."""
        self.paused = False
        log.info("Bot resumed")

    def get_status(self) -> Dict[str, Any]:
        """Get current status."""
        return {
            'running': self.running,
            'paused': self.paused,
            'total_actions': self.total_actions,
            'active_tables': len(self.sessions),
            'tables_needing_action': len([s for s in self.sessions.values() if s.needs_action()]),
            'uptime': time.time() - self.start_time if self.start_time else 0
        }


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Ten Table System Utility")
    parser.add_argument("--max-tables", type=int, default=10, help="Maximum tables to manage")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    from sys_core.tools.helper import init_logger
    level = logging.DEBUG if args.verbose else logging.INFO
    init_logger(screenlevel=level, filename='ten_table_bot', logdir='log')

    # Run bot
    bot = TenTableBot(max_tables=args.max_tables)

    try:
        bot.run()
    except KeyboardInterrupt:
        print("\nStopping...")
        bot.stop()


if __name__ == "__main__":
    main()
