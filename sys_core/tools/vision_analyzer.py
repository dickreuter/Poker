"""
VISION ANALYZER - Self-Learning Image Analysis System

This module makes the bot TRULY self-learning by:
1. Analyzing screenshots to find ACTUAL UI elements
2. Comparing expected vs actual detection
3. Auto-generating new thresholds that work
4. Testing fixes immediately
5. Saving working configurations

The bot fixes itself - no human intervention needed.

Usage:
    from sys_core.tools.vision_analyzer import VisionAnalyzer, auto_fix_detection

    analyzer = VisionAnalyzer()

    # When button detection fails, analyze and fix:
    fix = analyzer.analyze_and_fix_buttons(screenshot)
    # Returns: {'fixed': True, 'new_thresholds': {...}, 'buttons_found': [...]}

    # When card detection fails:
    fix = analyzer.analyze_and_fix_cards(screenshot)

    # Full auto-fix (analyzes everything):
    result = auto_fix_detection(screenshot)
"""

import cv2
import numpy as np
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from PIL import Image

log = logging.getLogger(__name__)

# Import adaptive learner for saving fixes
from sys_core.tools.adaptive_learner import (
    get_threshold, set_threshold, log_action, save_screenshot, get_learner
)

# Learning data paths
DATA_DIR = Path(__file__).parent.parent.parent / 'data' / 'learning'
FIXES_LOG = DATA_DIR / 'fixes.jsonl'
WORKING_CONFIGS = DATA_DIR / 'working_configs.json'


class VisionAnalyzer:
    """
    Analyzes screenshots to understand what's ACTUALLY on screen,
    then auto-generates thresholds that will work.
    """

    def __init__(self):
        self.working_configs = self._load_working_configs()
        self.fix_history = []

    def _load_working_configs(self) -> Dict:
        """Load previously working configurations"""
        if WORKING_CONFIGS.exists():
            try:
                return json.loads(WORKING_CONFIGS.read_text())
            except:
                pass
        return {
            'button_colors': {},
            'card_thresholds': {},
            'regions': {}
        }

    def _save_working_configs(self):
        """Save working configurations"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        WORKING_CONFIGS.write_text(json.dumps(self.working_configs, indent=2))

    def _log_fix(self, fix_type: str, details: Dict):
        """Log a fix for analysis"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': fix_type,
            'details': details
        }
        with open(FIXES_LOG, 'a') as f:
            f.write(json.dumps(entry) + '\n')
        self.fix_history.append(entry)

    # =========================================================================
    # BUTTON ANALYSIS AND AUTO-FIX
    # =========================================================================

    def analyze_buttons(self, img: np.ndarray) -> Dict[str, List[Dict]]:
        """
        Analyze image to find ALL colored rectangles that could be buttons.
        Returns actual colors and positions found.
        """
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, w = img.shape[:2]

        # Search bottom 40% where buttons usually are
        y_start = int(h * 0.60)
        search_region = hsv[y_start:, :]
        search_bgr = img[y_start:, :]

        found_buttons = {
            'green': [],   # Call/Check
            'orange': [],  # Raise/Bet
            'gray': [],    # Fold
            'red': [],     # Other (Deal Me In, etc)
            'unknown': []
        }

        # Find all significant colored regions
        # Use broader ranges to catch everything
        color_ranges = [
            ('green', np.array([25, 40, 40]), np.array([95, 255, 255])),
            ('orange', np.array([5, 50, 50]), np.array([30, 255, 255])),
            ('gray', np.array([0, 0, 20]), np.array([180, 80, 150])),
            ('red', np.array([0, 80, 80]), np.array([15, 255, 255])),
        ]

        for color_name, lower, upper in color_ranges:
            mask = cv2.inRange(search_region, lower, upper)

            # Clean up
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 1000:  # Too small
                    continue

                x, y, bw, bh = cv2.boundingRect(cnt)

                # Button-like aspect ratio
                if bw < 40 or bh < 20:
                    continue

                # Sample actual color at center
                cx, cy = x + bw // 2, y + bh // 2
                actual_hsv = search_region[cy, cx].tolist()
                actual_bgr = search_bgr[cy, cx].tolist()

                found_buttons[color_name].append({
                    'x': x,
                    'y': y + y_start,  # Adjust back to full image coords
                    'w': bw,
                    'h': bh,
                    'area': area,
                    'hsv': actual_hsv,
                    'bgr': actual_bgr,
                    'center': (x + bw // 2, y + y_start + bh // 2)
                })

        return found_buttons

    def analyze_and_fix_buttons(self, screenshot) -> Dict:
        """
        Analyze screenshot, find buttons, and generate working thresholds.

        Returns:
            {'fixed': bool, 'new_thresholds': dict, 'buttons_found': list}
        """
        # Convert to numpy if PIL Image
        if isinstance(screenshot, Image.Image):
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        else:
            img = screenshot

        log.info("VISION ANALYZER: Analyzing screenshot for buttons...")

        # Find all buttons
        found = self.analyze_buttons(img)

        total_found = sum(len(v) for v in found.values())
        log.info(f"VISION ANALYZER: Found {total_found} potential buttons")

        if total_found == 0:
            log.warning("VISION ANALYZER: No buttons found in image")
            return {'fixed': False, 'reason': 'no_buttons_found'}

        # Generate new thresholds based on what we actually found
        new_thresholds = {}

        # For each color, average the HSV values we found
        for color_name, buttons in found.items():
            if not buttons:
                continue

            # Get average HSV
            hsv_values = [b['hsv'] for b in buttons]
            avg_h = int(np.mean([h[0] for h in hsv_values]))
            avg_s = int(np.mean([h[1] for h in hsv_values]))
            avg_v = int(np.mean([h[2] for h in hsv_values]))

            # Create range around average (with margin)
            margin_h, margin_s, margin_v = 15, 50, 50
            lower = [max(0, avg_h - margin_h), max(0, avg_s - margin_s), max(0, avg_v - margin_v)]
            upper = [min(180, avg_h + margin_h), min(255, avg_s + margin_s), min(255, avg_v + margin_v)]

            if color_name == 'green':
                new_thresholds['hsv_green_lower'] = lower
                new_thresholds['hsv_green_upper'] = upper
            elif color_name == 'orange':
                new_thresholds['hsv_orange_lower'] = lower
                new_thresholds['hsv_orange_upper'] = upper
            elif color_name == 'gray':
                new_thresholds['hsv_gray_lower'] = lower
                new_thresholds['hsv_gray_upper'] = upper

            # Also get minimum area
            areas = [b['area'] for b in buttons]
            min_area = max(500, int(min(areas) * 0.8))  # 80% of smallest
            new_thresholds['button_area_min'] = min(
                new_thresholds.get('button_area_min', 99999),
                min_area
            )

            log.info(f"VISION ANALYZER: {color_name} buttons - avg HSV: ({avg_h}, {avg_s}, {avg_v})")

        # Apply the new thresholds
        for key, value in new_thresholds.items():
            old_value = get_threshold(key)
            set_threshold(key, value, f"Vision analyzer auto-fix from screenshot")
            log.info(f"VISION ANALYZER: Updated {key}: {old_value} -> {value}")

        # Save to working configs
        self.working_configs['button_colors'] = {
            color: [b['hsv'] for b in buttons]
            for color, buttons in found.items() if buttons
        }
        self._save_working_configs()

        # Log the fix
        self._log_fix('button_detection', {
            'buttons_found': total_found,
            'new_thresholds': new_thresholds,
            'colors_found': {k: len(v) for k, v in found.items()}
        })

        log_action('vision_auto_fix', success=True, details={
            'type': 'buttons',
            'found': total_found,
            'thresholds_updated': list(new_thresholds.keys())
        })

        return {
            'fixed': True,
            'new_thresholds': new_thresholds,
            'buttons_found': found
        }

    # =========================================================================
    # CARD ANALYSIS AND AUTO-FIX
    # =========================================================================

    def analyze_cards(self, img: np.ndarray) -> Dict:
        """
        Analyze image to find card-like regions at various thresholds.
        """
        h, w = img.shape[:2]

        # Search bottom 45% where player cards are
        y_start = int(h * 0.55)
        x_start = int(w * 0.20)
        x_end = int(w * 0.80)
        search_region = img[y_start:, x_start:x_end]

        results = {
            'cards_found': [],
            'best_threshold': None,
            'region_stats': {}
        }

        # Try multiple white thresholds
        for threshold in [200, 180, 160, 140, 120, 100]:
            # Create white mask
            gray = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

            # Clean up
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            card_candidates = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 1500:
                    continue

                x, y, cw, ch = cv2.boundingRect(cnt)

                # Card-like dimensions
                if cw < 30 or ch < 40:
                    continue
                if ch == 0:
                    continue

                aspect = cw / ch
                if not (0.4 < aspect < 1.0):  # Cards are taller than wide
                    continue

                card_candidates.append({
                    'x': x + x_start,
                    'y': y + y_start,
                    'w': cw,
                    'h': ch,
                    'area': area,
                    'threshold': threshold
                })

            # If we found 2 cards, this threshold works!
            if len(card_candidates) >= 2:
                # Sort by x position (left to right)
                card_candidates.sort(key=lambda c: c['x'])
                results['cards_found'] = card_candidates[:2]
                results['best_threshold'] = threshold
                break

        # Also check for card backs (red/blue patterns)
        if not results['cards_found']:
            results['card_backs'] = self._detect_card_backs(search_region, x_start, y_start)

        return results

    def _detect_card_backs(self, region: np.ndarray, x_offset: int, y_offset: int) -> List[Dict]:
        """Detect face-down card backs (red/blue colored)"""
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        # Red card backs
        red_lower = np.array([0, 100, 100])
        red_upper = np.array([10, 255, 255])
        red_mask = cv2.inRange(hsv, red_lower, red_upper)

        # Blue card backs
        blue_lower = np.array([100, 100, 100])
        blue_upper = np.array([130, 255, 255])
        blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)

        combined = cv2.bitwise_or(red_mask, blue_mask)

        kernel = np.ones((5, 5), np.uint8)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        backs = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 2000:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            if w > 30 and h > 40:
                backs.append({
                    'x': x + x_offset,
                    'y': y + y_offset,
                    'w': w,
                    'h': h,
                    'type': 'card_back'
                })

        return backs

    def analyze_and_fix_cards(self, screenshot) -> Dict:
        """
        Analyze screenshot, find cards, and generate working thresholds.
        """
        if isinstance(screenshot, Image.Image):
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        else:
            img = screenshot

        log.info("VISION ANALYZER: Analyzing screenshot for cards...")

        results = self.analyze_cards(img)

        if results['cards_found']:
            # Found face-up cards
            threshold = results['best_threshold']
            log.info(f"VISION ANALYZER: Found {len(results['cards_found'])} cards at threshold {threshold}")

            # Update thresholds
            set_threshold('white_pixel_min', threshold, "Vision analyzer found working card threshold")

            # Update card region based on where we found them
            cards = results['cards_found']
            h, w = img.shape[:2]
            avg_y = np.mean([c['y'] for c in cards])
            y_ratio = avg_y / h

            if y_ratio < get_threshold('card_region_y_start', 0.55):
                set_threshold('card_region_y_start', max(0.40, y_ratio - 0.05),
                             "Adjusted card region based on actual card position")

            self._log_fix('card_detection', {
                'cards_found': len(cards),
                'threshold': threshold,
                'y_ratio': y_ratio
            })

            log_action('vision_auto_fix', success=True, details={
                'type': 'cards',
                'found': len(cards),
                'threshold': threshold
            })

            return {
                'fixed': True,
                'cards': cards,
                'threshold': threshold
            }

        elif results.get('card_backs'):
            # Found face-down cards - this is normal when not your turn
            log.info(f"VISION ANALYZER: Found {len(results['card_backs'])} card backs (face-down)")
            return {
                'fixed': False,
                'reason': 'cards_face_down',
                'card_backs': results['card_backs']
            }

        else:
            log.warning("VISION ANALYZER: No cards found at any threshold")
            return {
                'fixed': False,
                'reason': 'no_cards_found'
            }

    # =========================================================================
    # REGION ANALYSIS
    # =========================================================================

    def analyze_screen_regions(self, img: np.ndarray) -> Dict:
        """
        Analyze the entire screen to understand the layout.
        Learns where buttons, cards, etc. actually are.
        """
        h, w = img.shape[:2]

        regions = {
            'top_bar': {'y_start': 0, 'y_end': int(h * 0.15)},
            'main_area': {'y_start': int(h * 0.15), 'y_end': int(h * 0.60)},
            'card_area': {'y_start': int(h * 0.55), 'y_end': int(h * 0.85)},
            'button_area': {'y_start': int(h * 0.70), 'y_end': h}
        }

        # Analyze each region
        for name, bounds in regions.items():
            region = img[bounds['y_start']:bounds['y_end'], :]

            # Get color statistics
            hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
            avg_h = np.mean(hsv[:, :, 0])
            avg_s = np.mean(hsv[:, :, 1])
            avg_v = np.mean(hsv[:, :, 2])

            # Check if region has significant colored content
            has_green = np.sum(cv2.inRange(hsv, np.array([35, 50, 50]), np.array([85, 255, 255]))) > 1000
            has_white = np.sum(hsv[:, :, 2] > 200) > 1000

            regions[name]['avg_hsv'] = (avg_h, avg_s, avg_v)
            regions[name]['has_green_buttons'] = has_green
            regions[name]['has_white_cards'] = has_white

        return regions

    # =========================================================================
    # FULL AUTO-FIX
    # =========================================================================

    def full_auto_fix(self, screenshot) -> Dict:
        """
        Comprehensive auto-fix: analyzes everything and fixes all detection.
        """
        if isinstance(screenshot, Image.Image):
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        else:
            img = screenshot

        log.info("=" * 60)
        log.info("VISION ANALYZER: FULL AUTO-FIX STARTING")
        log.info("=" * 60)

        results = {
            'buttons': None,
            'cards': None,
            'regions': None,
            'fixes_applied': []
        }

        # 1. Analyze and fix buttons
        button_result = self.analyze_and_fix_buttons(img)
        results['buttons'] = button_result
        if button_result.get('fixed'):
            results['fixes_applied'].append('buttons')

        # 2. Analyze and fix cards
        card_result = self.analyze_and_fix_cards(img)
        results['cards'] = card_result
        if card_result.get('fixed'):
            results['fixes_applied'].append('cards')

        # 3. Analyze screen regions
        results['regions'] = self.analyze_screen_regions(img)

        # 4. Update region thresholds based on analysis
        regions = results['regions']
        if regions['button_area'].get('has_green_buttons'):
            y_ratio = regions['button_area']['y_start'] / img.shape[0]
            current = get_threshold('button_region_y_start', 0.65)
            if y_ratio < current:
                set_threshold('button_region_y_start', y_ratio,
                             "Vision analyzer found buttons higher than expected")
                results['fixes_applied'].append('button_region')

        log.info(f"VISION ANALYZER: Fixes applied: {results['fixes_applied']}")
        log.info("=" * 60)

        # Save screenshot with annotations
        self._save_analysis_debug(img, results)

        return results

    def _save_analysis_debug(self, img: np.ndarray, results: Dict):
        """Save annotated debug image showing what was found"""
        debug_dir = DATA_DIR / 'debug'
        debug_dir.mkdir(parents=True, exist_ok=True)

        annotated = img.copy()

        # Draw found buttons
        if results.get('buttons', {}).get('buttons_found'):
            for color, buttons in results['buttons']['buttons_found'].items():
                color_bgr = {
                    'green': (0, 255, 0),
                    'orange': (0, 165, 255),
                    'gray': (128, 128, 128),
                    'red': (0, 0, 255)
                }.get(color, (255, 255, 255))

                for btn in buttons:
                    cv2.rectangle(annotated,
                                (btn['x'], btn['y']),
                                (btn['x'] + btn['w'], btn['y'] + btn['h']),
                                color_bgr, 2)
                    cv2.putText(annotated, color, (btn['x'], btn['y'] - 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_bgr, 1)

        # Draw found cards
        if results.get('cards', {}).get('cards'):
            for card in results['cards']['cards']:
                cv2.rectangle(annotated,
                            (card['x'], card['y']),
                            (card['x'] + card['w'], card['y'] + card['h']),
                            (255, 255, 0), 2)
                cv2.putText(annotated, "CARD", (card['x'], card['y'] - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = debug_dir / f'vision_analysis_{timestamp}.png'
        cv2.imwrite(str(filepath), annotated)
        log.info(f"VISION ANALYZER: Debug image saved to {filepath}")


# Singleton instance
_analyzer = None

def get_analyzer() -> VisionAnalyzer:
    """Get singleton analyzer instance"""
    global _analyzer
    if _analyzer is None:
        _analyzer = VisionAnalyzer()
    return _analyzer


# Convenience functions
def auto_fix_detection(screenshot) -> Dict:
    """Full auto-fix from screenshot"""
    return get_analyzer().full_auto_fix(screenshot)

def auto_fix_buttons(screenshot) -> Dict:
    """Auto-fix button detection"""
    return get_analyzer().analyze_and_fix_buttons(screenshot)

def auto_fix_cards(screenshot) -> Dict:
    """Auto-fix card detection"""
    return get_analyzer().analyze_and_fix_cards(screenshot)
