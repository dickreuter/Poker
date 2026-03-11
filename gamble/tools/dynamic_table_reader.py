"""
Dynamic Table Reader - Extracts ALL game state from poker table using OCR.

This module provides dynamic reading of:
- Pot values (total pot, round pot)
- Player stacks (all players)
- Call/raise values (from button text)
- Card values (hole cards, board)
- Player positions and bets

Uses pytesseract OCR to scan the entire table and parse all visible information.
This is used as FALLBACK when template-based detection fails.

Integration with original TableScraper:
    # In TableScraper.get_pots():
    if not self.total_pot:  # Template-based failed
        reader = DynamicTableReader(self.screenshot)
        self.total_pot = reader.get_pot()
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from PIL import Image
import numpy as np

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

log = logging.getLogger(__name__)


class DynamicTableReader:
    """
    Reads ALL game state from a poker table screenshot using OCR.

    This provides dynamic reading without hardcoded coordinates.
    """

    def __init__(self, screenshot: Image.Image = None):
        self.screenshot = screenshot
        self._ocr_data = None
        self._parsed_numbers = []
        self._parsed_texts = []

    def set_screenshot(self, screenshot: Image.Image):
        """Set/update the screenshot to analyze."""
        self.screenshot = screenshot
        self._ocr_data = None  # Reset cached data
        self._parsed_numbers = []
        self._parsed_texts = []

    def _run_ocr(self) -> Dict:
        """Run OCR on screenshot and cache results."""
        if not OCR_AVAILABLE:
            log.error("pytesseract not installed - OCR unavailable")
            return {}

        if self._ocr_data is not None:
            return self._ocr_data

        if self.screenshot is None:
            log.error("No screenshot set")
            return {}

        try:
            self._ocr_data = pytesseract.image_to_data(
                self.screenshot,
                output_type=pytesseract.Output.DICT
            )
            self._parse_ocr_results()
        except Exception as e:
            log.error(f"OCR failed: {e}")
            self._ocr_data = {}

        return self._ocr_data

    def _parse_ocr_results(self):
        """Parse OCR results into structured data."""
        if not self._ocr_data:
            return

        img_h, img_w = self.screenshot.size[1], self.screenshot.size[0]

        for i, text in enumerate(self._ocr_data['text']):
            text_str = str(text).strip()
            if not text_str:
                continue

            conf = self._ocr_data['conf'][i]
            if conf < 30:  # Skip very low confidence
                continue

            x = self._ocr_data['left'][i]
            y = self._ocr_data['top'][i]
            w = self._ocr_data['width'][i]
            h = self._ocr_data['height'][i]

            # Calculate relative position (0-1) on table
            rel_x = (x + w/2) / img_w
            rel_y = (y + h/2) / img_h

            # Try to parse as number (handle currency formats)
            number = self._parse_number(text_str)

            entry = {
                'text': text_str,
                'x': x, 'y': y, 'w': w, 'h': h,
                'rel_x': rel_x, 'rel_y': rel_y,
                'conf': conf,
                'number': number
            }

            if number is not None:
                self._parsed_numbers.append(entry)
            else:
                self._parsed_texts.append(entry)

    def _parse_number(self, text: str) -> Optional[float]:
        """Parse text as a number (handles $, K, M, etc.)."""
        # Remove currency symbols and whitespace
        cleaned = text.replace('$', '').replace(',', '').replace(' ', '')
        cleaned = cleaned.replace('€', '').replace('£', '')

        # Handle K/M suffixes
        multiplier = 1
        if cleaned.upper().endswith('K'):
            multiplier = 1000
            cleaned = cleaned[:-1]
        elif cleaned.upper().endswith('M'):
            multiplier = 1000000
            cleaned = cleaned[:-1]

        try:
            return float(cleaned) * multiplier
        except ValueError:
            return None

    def get_pot(self) -> Optional[float]:
        """
        Get the total pot value.

        Heuristic: The pot is typically:
        - In the top 40% of the table (vertically)
        - In the center 60% (horizontally)
        - One of the larger numbers on screen
        """
        self._run_ocr()

        # Filter numbers in pot region (top-center)
        pot_candidates = [
            n for n in self._parsed_numbers
            if 0.15 < n['rel_y'] < 0.45  # Top 15-45% vertically
            and 0.25 < n['rel_x'] < 0.75  # Center 50% horizontally
            and n['number'] is not None
            and n['number'] > 0
        ]

        if not pot_candidates:
            log.debug("No pot candidates found")
            return None

        # Pick the largest number in the pot region
        # (pot is usually the biggest number shown on table)
        pot_candidates.sort(key=lambda x: x['number'], reverse=True)

        pot = pot_candidates[0]['number']
        log.info(f"Dynamic pot read: {pot} (from '{pot_candidates[0]['text']}' at rel_y={pot_candidates[0]['rel_y']:.2f})")

        return pot

    def get_stacks(self) -> Dict[str, float]:
        """
        Get all player stack sizes.

        Heuristic: Stacks are positioned:
        - Around the edges of the table (not center)
        - At consistent vertical positions for each seat

        Returns dict with estimated position -> stack value
        """
        self._run_ocr()

        stacks = {}

        # Stacks are NOT in the pot region and NOT at button area
        stack_candidates = [
            n for n in self._parsed_numbers
            if n['number'] is not None
            and n['number'] > 0
            and not (0.25 < n['rel_y'] < 0.45 and 0.35 < n['rel_x'] < 0.65)  # Not pot
            and not (n['rel_y'] > 0.85)  # Not buttons at very bottom
        ]

        # Group by rough position (6-max table positions)
        positions = {
            'hero': (0.5, 0.85),      # Bottom center
            'btn': (0.8, 0.7),        # Bottom right
            'co': (0.9, 0.5),         # Right side
            'mp': (0.8, 0.25),        # Top right
            'utg': (0.2, 0.25),       # Top left
            'sb': (0.1, 0.5),         # Left side
            'bb': (0.2, 0.7),         # Bottom left
        }

        # Assign each candidate to nearest position
        for pos_name, (px, py) in positions.items():
            closest = None
            closest_dist = float('inf')

            for n in stack_candidates:
                dist = ((n['rel_x'] - px) ** 2 + (n['rel_y'] - py) ** 2) ** 0.5
                if dist < closest_dist and dist < 0.2:  # Within 20% of expected position
                    closest = n
                    closest_dist = dist

            if closest:
                stacks[pos_name] = closest['number']
                log.debug(f"Stack {pos_name}: {closest['number']} (dist={closest_dist:.2f})")

        log.info(f"Dynamic stacks read: {stacks}")
        return stacks

    def get_hero_stack(self) -> Optional[float]:
        """Get hero's (player's own) stack - bottom center of table."""
        self._run_ocr()

        # Hero stack is at bottom center
        hero_candidates = [
            n for n in self._parsed_numbers
            if n['rel_y'] > 0.70  # Bottom 30%
            and 0.35 < n['rel_x'] < 0.65  # Center
            and n['number'] is not None
            and n['number'] > 0
        ]

        if not hero_candidates:
            return None

        # Take the one closest to expected position
        hero_candidates.sort(key=lambda x: abs(x['rel_x'] - 0.5) + abs(x['rel_y'] - 0.8))

        return hero_candidates[0]['number']

    def get_call_amount(self) -> Optional[float]:
        """
        Get the call amount from button text.

        Looks for patterns like "Call $X" or just a number on a green button area.
        """
        self._run_ocr()

        # Look for "call" text and nearby number
        for t in self._parsed_texts:
            if 'call' in t['text'].lower():
                # Find number near this text
                for n in self._parsed_numbers:
                    if (abs(n['x'] - t['x']) < 150 and abs(n['y'] - t['y']) < 30):
                        log.info(f"Call amount: {n['number']} (near 'call' text)")
                        return n['number']

        # Fallback: look for numbers in button area (bottom 20%, right-center)
        button_numbers = [
            n for n in self._parsed_numbers
            if n['rel_y'] > 0.80  # Very bottom
            and 0.4 < n['rel_x'] < 0.7  # Center-right (call button area)
            and n['number'] is not None
        ]

        if button_numbers:
            # Usually the call amount is shown on the button
            return button_numbers[0]['number']

        return None

    def get_raise_amount(self) -> Optional[float]:
        """Get the raise/bet amount from button text."""
        self._run_ocr()

        # Look for "raise" or "bet" text and nearby number
        for t in self._parsed_texts:
            if 'raise' in t['text'].lower() or 'bet' in t['text'].lower():
                # Find number near this text
                for n in self._parsed_numbers:
                    if (abs(n['x'] - t['x']) < 150 and abs(n['y'] - t['y']) < 30):
                        log.info(f"Raise amount: {n['number']} (near raise/bet text)")
                        return n['number']

        # Fallback: look for numbers in right button area
        button_numbers = [
            n for n in self._parsed_numbers
            if n['rel_y'] > 0.80  # Very bottom
            and n['rel_x'] > 0.6  # Right side (raise button area)
            and n['number'] is not None
        ]

        if button_numbers:
            return button_numbers[0]['number']

        return None

    def get_board_cards(self) -> List[str]:
        """
        Get board cards (flop, turn, river) using OCR.

        Looks for card notation patterns like "As", "Kh", "2c", etc.
        """
        self._run_ocr()

        cards = []
        card_pattern = re.compile(r'^([2-9TJQKA])([shdc♠♥♦♣])$', re.IGNORECASE)

        # Board cards are in top-center area
        for t in self._parsed_texts:
            if 0.25 < t['rel_y'] < 0.50 and 0.20 < t['rel_x'] < 0.80:
                match = card_pattern.match(t['text'])
                if match:
                    rank, suit = match.groups()
                    # Normalize suit symbols
                    suit_map = {'s': 's', 'h': 'h', 'd': 'd', 'c': 'c',
                               '♠': 's', '♥': 'h', '♦': 'd', '♣': 'c'}
                    suit = suit_map.get(suit.lower(), suit.lower())
                    cards.append(rank.upper() + suit)

        log.info(f"Board cards found: {cards}")
        return cards

    def get_hole_cards(self) -> List[str]:
        """
        Get hero's hole cards using OCR.

        Looks for card notation at the bottom-center of table.
        """
        self._run_ocr()

        cards = []
        card_pattern = re.compile(r'^([2-9TJQKA])([shdc♠♥♦♣])$', re.IGNORECASE)

        # Hole cards are at bottom-center
        for t in self._parsed_texts:
            if t['rel_y'] > 0.65 and 0.35 < t['rel_x'] < 0.65:
                match = card_pattern.match(t['text'])
                if match:
                    rank, suit = match.groups()
                    suit_map = {'s': 's', 'h': 'h', 'd': 'd', 'c': 'c',
                               '♠': 's', '♥': 'h', '♦': 'd', '♣': 'c'}
                    suit = suit_map.get(suit.lower(), suit.lower())
                    cards.append(rank.upper() + suit)

        log.info(f"Hole cards found: {cards}")
        return cards

    def get_buttons_with_values(self) -> Dict[str, Dict]:
        """
        Get all action buttons with their text AND associated values.

        Returns dict like:
        {
            'call': {'text': 'Call', 'amount': 100, 'x': 500, 'y': 900},
            'fold': {'text': 'Fold', 'x': 300, 'y': 900},
            'raise': {'text': 'Raise', 'amount': 200, 'x': 700, 'y': 900},
        }
        """
        self._run_ocr()

        buttons = {}
        keywords = {
            'check': 'check',
            'call': 'call',
            'fold': 'fold',
            'raise': 'raise',
            'bet': 'raise',  # 'bet' maps to raise
            'all': 'allin',
        }

        for t in self._parsed_texts:
            text_lower = t['text'].lower()

            for kw, btn_key in keywords.items():
                if kw in text_lower and btn_key not in buttons:
                    buttons[btn_key] = {
                        'text': t['text'],
                        'x': t['x'] + t['w'] // 2,
                        'y': t['y'] + t['h'] // 2,
                        'conf': t['conf']
                    }

                    # Look for associated amount
                    for n in self._parsed_numbers:
                        if (abs(n['x'] - t['x']) < 200 and abs(n['y'] - t['y']) < 50):
                            buttons[btn_key]['amount'] = n['number']
                            break

        log.info(f"Buttons found: {list(buttons.keys())}")
        return buttons

    def get_all_numbers_debug(self) -> List[Dict]:
        """
        Debug method: return all numbers found with their positions.
        Useful for understanding what OCR sees.
        """
        self._run_ocr()
        return self._parsed_numbers

    def get_all_text_debug(self) -> List[Dict]:
        """
        Debug method: return all text found with positions.
        """
        self._run_ocr()
        return self._parsed_texts


def integrate_with_table_scraper():
    """
    Example of how to integrate DynamicTableReader with existing TableScraper.

    Add these fallback methods to TableScraper class.
    """
    example = '''
    # In TableScraper.get_pots():
    def get_pots(self):
        """Get current and total pot - with dynamic fallback."""
        # Try template-based first
        self.current_round_pot = ocr(self.screenshot, 'current_round_pot', self.table_dict, fast=True)
        self.total_pot = ocr(self.screenshot, 'total_pot_area', self.table_dict)

        # Fallback to dynamic OCR if failed
        if not self.total_pot or self.total_pot == 0:
            from gamble.tools.dynamic_table_reader import DynamicTableReader
            reader = DynamicTableReader(self.screenshot)
            dynamic_pot = reader.get_pot()
            if dynamic_pot:
                self.total_pot = dynamic_pot
                log.info(f"Using dynamic pot: {self.total_pot}")

        log.info(f"Current round pot {self.current_round_pot}")
        log.info(f"Total pot {self.total_pot}")
    '''
    return example


# Standalone test
if __name__ == '__main__':
    from PIL import ImageGrab
    import time

    logging.basicConfig(level=logging.INFO)

    print("Taking screenshot in 3 seconds...")
    time.sleep(3)

    screenshot = ImageGrab.grab()
    reader = DynamicTableReader(screenshot)

    print("\n=== DYNAMIC TABLE READER TEST ===\n")

    print(f"Pot: {reader.get_pot()}")
    print(f"Hero stack: {reader.get_hero_stack()}")
    print(f"All stacks: {reader.get_stacks()}")
    print(f"Call amount: {reader.get_call_amount()}")
    print(f"Raise amount: {reader.get_raise_amount()}")
    print(f"Buttons: {reader.get_buttons_with_values()}")
    print(f"Hole cards: {reader.get_hole_cards()}")
    print(f"Board cards: {reader.get_board_cards()}")

    print("\n=== DEBUG: All numbers found ===")
    for n in reader.get_all_numbers_debug()[:20]:
        print(f"  {n['text']:10} = {n['number']:>10.2f} at ({n['rel_x']:.2f}, {n['rel_y']:.2f})")
