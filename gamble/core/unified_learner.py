"""
UNIFIED LEARNER - Single Source of Truth for All Adaptive Learning

Consolidates functionality from:
- tools/adaptive_learner.py (AdaptiveLearner class)
- tools/vision_analyzer.py (VisionAnalyzer class)
- tools/self_healer.py (SelfHealer class)

These three systems previously:
- All did similar things (analyze failures, update thresholds)
- Stored data in different files
- Didn't communicate with each other
- Were used by different bots inconsistently

This UNIFIED system:
- Has ONE threshold storage (thresholds.json)
- Has ONE action log (actions.jsonl)
- Has ONE stats tracker (stats.json)
- Combines vision analysis + self-healing into one flow
- Is used by ALL bots through the core module

Usage:
    from gamble.core import UnifiedLearner, get_learner

    learner = get_learner()

    # Get/set adaptive thresholds
    threshold = learner.get_threshold('white_pixel_min', 180)
    learner.set_threshold('white_pixel_min', 160, reason="Auto-healed")

    # Log actions for tracking success rates
    learner.log_action('card_detection', success=True, details={'cards': ['AH', 'KS']})

    # Self-healing when detection fails
    learner.heal_detection('buttons', screenshot)
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from PIL import Image
import cv2
import numpy as np

from gamble.core.constants import (
    THRESHOLDS_FILE,
    ACTIONS_LOG_FILE,
    STATS_FILE,
    CALIBRATION_FILE,
    WORKING_CONFIGS_FILE,
    FIXES_LOG_FILE,
    SCREENSHOTS_DIR,
    DEBUG_DIR,
    CARD_WHITE_THRESHOLD_DEFAULT,
    HSV_RANGES,
)

log = logging.getLogger(__name__)


class UnifiedLearner:
    """
    Unified learning system that combines:
    - Threshold management (from adaptive_learner)
    - Action logging and statistics (from adaptive_learner)
    - Vision analysis and auto-fixing (from vision_analyzer)
    - Self-healing detection (from self_healer)

    All in ONE coherent system.
    """

    def __init__(self):
        """Initialize the unified learner."""
        self._ensure_directories()
        self.thresholds = self._load_thresholds()
        self.stats = self._load_stats()
        self.calibration = self._load_calibration()
        self.working_configs = self._load_working_configs()
        self.session_actions = []

    def _ensure_directories(self):
        """Ensure all data directories exist."""
        for dir_path in [SCREENSHOTS_DIR, DEBUG_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # THRESHOLD MANAGEMENT
    # =========================================================================

    def _load_thresholds(self) -> Dict:
        """Load adaptive thresholds from file."""
        if THRESHOLDS_FILE.exists():
            try:
                return json.loads(THRESHOLDS_FILE.read_text())
            except Exception as e:
                log.warning(f"Could not load thresholds: {e}")

        # Default thresholds
        return {
            'white_pixel_min': CARD_WHITE_THRESHOLD_DEFAULT,
            'card_area_min': 1500,
            'card_area_max': 50000,
            'button_area_min': 1500,
            'match_score_max': 0.35,
            'action_cooldown': 1.5,
            'click_verify_delay': 0.3,
            'ocr_confidence_min': 60,
        }

    def _save_thresholds(self):
        """Save thresholds to file."""
        try:
            THRESHOLDS_FILE.parent.mkdir(parents=True, exist_ok=True)
            THRESHOLDS_FILE.write_text(json.dumps(self.thresholds, indent=2))
        except Exception as e:
            log.error(f"Could not save thresholds: {e}")

    def get_threshold(self, name: str, default: Any = None) -> Any:
        """
        Get an adaptive threshold value.

        Args:
            name: Threshold name
            default: Default value if not found

        Returns:
            Current threshold value
        """
        return self.thresholds.get(name, default)

    def set_threshold(self, name: str, value: Any, reason: str = ""):
        """
        Set a threshold and log the change.

        Args:
            name: Threshold name
            value: New value
            reason: Why this change was made
        """
        old_value = self.thresholds.get(name)
        self.thresholds[name] = value
        self._save_thresholds()

        log.info(f"Threshold '{name}' changed: {old_value} -> {value} ({reason})")
        self.log_action('threshold_change', success=True, details={
            'name': name,
            'old': old_value,
            'new': value,
            'reason': reason
        })

    # =========================================================================
    # ACTION LOGGING
    # =========================================================================

    def log_action(self, action_type: str, success: bool, details: Dict = None,
                   screenshot=None, save_on_fail: bool = True):
        """
        Log an action and its outcome.

        Args:
            action_type: Type of action (card_detection, button_click, etc.)
            success: Whether action succeeded
            details: Additional details
            screenshot: Optional image to save
            save_on_fail: Auto-save screenshot on failure
        """
        timestamp = datetime.now().isoformat()
        entry = {
            'timestamp': timestamp,
            'action': action_type,
            'success': success,
            'details': details or {}
        }

        # Save screenshot if provided or on failure
        if screenshot is not None:
            screenshot_path = self.save_screenshot(action_type, success, screenshot)
            entry['screenshot'] = str(screenshot_path) if screenshot_path else None
        elif not success and save_on_fail:
            entry['details']['note'] = 'screenshot_not_available'

        # Append to log file
        try:
            with open(ACTIONS_LOG_FILE, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            log.error(f"Could not log action: {e}")

        # Update session tracking
        self.session_actions.append(entry)

        # Update statistics
        self._update_stats(action_type, success)

    def _update_stats(self, action_type: str, success: bool):
        """Update success/failure statistics."""
        if action_type not in self.stats['by_type']:
            self.stats['by_type'][action_type] = {'success': 0, 'fail': 0}

        if success:
            self.stats['by_type'][action_type]['success'] += 1
            self.stats['successful_actions'] += 1
        else:
            self.stats['by_type'][action_type]['fail'] += 1

        self.stats['total_actions'] += 1
        self.stats['last_updated'] = datetime.now().isoformat()

        self._save_stats()

    def _load_stats(self) -> Dict:
        """Load statistics from file."""
        if STATS_FILE.exists():
            try:
                return json.loads(STATS_FILE.read_text())
            except:
                pass

        return {
            'total_actions': 0,
            'successful_actions': 0,
            'sessions': 0,
            'by_type': {},
            'last_updated': None
        }

    def _save_stats(self):
        """Save statistics to file."""
        try:
            STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATS_FILE.write_text(json.dumps(self.stats, indent=2))
        except Exception as e:
            log.error(f"Could not save stats: {e}")

    def get_success_rate(self, action_type: str) -> float:
        """Get success rate for an action type (0-1)."""
        if action_type not in self.stats['by_type']:
            return 0.0

        data = self.stats['by_type'][action_type]
        total = data['success'] + data['fail']
        if total == 0:
            return 0.0

        return data['success'] / total

    # =========================================================================
    # SCREENSHOT MANAGEMENT
    # =========================================================================

    def save_screenshot(self, action_type: str, success: bool, image=None) -> Optional[Path]:
        """
        Save a screenshot for learning/debugging.

        Args:
            action_type: Type of action
            success: Whether action succeeded
            image: PIL Image or numpy array

        Returns:
            Path to saved screenshot, or None
        """
        if image is None:
            return None

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        status = 'success' if success else 'fail'
        filename = f"{action_type}_{status}_{timestamp}.png"
        filepath = SCREENSHOTS_DIR / filename

        try:
            if isinstance(image, np.ndarray):
                cv2.imwrite(str(filepath), image)
            elif isinstance(image, Image.Image):
                image.save(filepath)
            else:
                log.warning(f"Unknown image type: {type(image)}")
                return None

            log.debug(f"Saved screenshot: {filepath}")
            return filepath
        except Exception as e:
            log.error(f"Could not save screenshot: {e}")
            return None

    def save_debug_screenshot(self, context: str, image, reason: str = ""):
        """
        Save a debug screenshot with annotation.

        Args:
            context: What was being done (card_detection, button_detection, etc.)
            image: PIL Image or numpy array
            reason: Why this screenshot was saved
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{context}_{reason}_{timestamp}.png"
        filepath = DEBUG_DIR / filename

        try:
            if isinstance(image, np.ndarray):
                cv2.imwrite(str(filepath), image)
            elif isinstance(image, Image.Image):
                image.save(filepath)

            log.info(f"Debug screenshot saved: {filepath}")
            return filepath
        except Exception as e:
            log.error(f"Could not save debug screenshot: {e}")
            return None

    # =========================================================================
    # CALIBRATION MANAGEMENT
    # =========================================================================

    def _load_calibration(self) -> Dict:
        """Load calibration data."""
        if CALIBRATION_FILE.exists():
            try:
                return json.loads(CALIBRATION_FILE.read_text())
            except:
                pass

        return {
            'button_colors': {},
            'card_regions': {},
            'last_calibrated': None
        }

    def _save_calibration(self):
        """Save calibration data."""
        try:
            CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
            CALIBRATION_FILE.write_text(json.dumps(self.calibration, indent=2))
        except Exception as e:
            log.error(f"Could not save calibration: {e}")

    def _load_working_configs(self) -> Dict:
        """Load working configurations."""
        if WORKING_CONFIGS_FILE.exists():
            try:
                return json.loads(WORKING_CONFIGS_FILE.read_text())
            except:
                pass

        return {
            'button_colors': {},
            'card_thresholds': {},
            'regions': {}
        }

    def _save_working_configs(self):
        """Save working configurations."""
        try:
            WORKING_CONFIGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            WORKING_CONFIGS_FILE.write_text(json.dumps(self.working_configs, indent=2))
        except Exception as e:
            log.error(f"Could not save working configs: {e}")

    # =========================================================================
    # SELF-HEALING / VISION ANALYSIS
    # =========================================================================

    def heal_detection(self, detection_type: str, image) -> Dict:
        """
        Attempt to self-heal failed detection by analyzing the image.

        This combines functionality from vision_analyzer and self_healer.

        Args:
            detection_type: 'buttons', 'cards', or 'all'
            image: PIL Image or numpy array to analyze

        Returns:
            Dict with healing results
        """
        if isinstance(image, Image.Image):
            img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        else:
            img = image

        log.info(f"SELF-HEALING: Attempting to heal {detection_type} detection...")

        if detection_type == 'buttons':
            return self._heal_button_detection(img)
        elif detection_type == 'cards':
            return self._heal_card_detection(img)
        elif detection_type == 'all':
            button_result = self._heal_button_detection(img)
            card_result = self._heal_card_detection(img)
            return {
                'buttons': button_result,
                'cards': card_result,
                'healed': button_result.get('healed') or card_result.get('healed')
            }
        else:
            log.warning(f"Unknown detection type: {detection_type}")
            return {'healed': False, 'reason': 'unknown_type'}

    def _heal_button_detection(self, img: np.ndarray) -> Dict:
        """
        Analyze image to find buttons and update thresholds.

        Scans for colored rectangles and generates new HSV ranges.
        """
        h, w = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Search bottom portion
        y_start = int(h * 0.60)
        search_region = hsv[y_start:, :]
        search_bgr = img[y_start:, :]

        found_buttons = {}

        # Use very broad ranges to find any colored rectangles
        broad_ranges = [
            ('green', np.array([20, 30, 30]), np.array([100, 255, 255])),
            ('orange', np.array([0, 50, 50]), np.array([35, 255, 255])),
            ('gray', np.array([0, 0, 20]), np.array([180, 100, 180])),
        ]

        for color_name, lower, upper in broad_ranges:
            mask = cv2.inRange(search_region, lower, upper)
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 1000:
                    continue

                x, y, bw, bh = cv2.boundingRect(cnt)
                if bw < 40 or bh < 20:
                    continue

                # Sample actual color at center
                cx, cy = x + bw // 2, y + bh // 2
                if cy < search_region.shape[0] and cx < search_region.shape[1]:
                    actual_hsv = search_region[cy, cx].tolist()

                    if color_name not in found_buttons:
                        found_buttons[color_name] = []
                    found_buttons[color_name].append({
                        'x': x,
                        'y': y + y_start,
                        'w': bw,
                        'h': bh,
                        'hsv': actual_hsv,
                        'area': area,
                    })

        if not found_buttons:
            return {'healed': False, 'reason': 'no_buttons_found'}

        # Update thresholds based on what we found
        color_to_btn = {'green': 'call', 'orange': 'raise', 'gray': 'fold'}
        updates = {}

        for color_name, detections in found_buttons.items():
            if not detections:
                continue

            btn_type = color_to_btn.get(color_name)
            if not btn_type:
                continue

            # Average HSV values
            hsv_values = [d['hsv'] for d in detections]
            avg_h = int(np.mean([h[0] for h in hsv_values]))
            avg_s = int(np.mean([h[1] for h in hsv_values]))
            avg_v = int(np.mean([h[2] for h in hsv_values]))

            # Create new ranges with margin
            margin_h, margin_s, margin_v = 15, 50, 50
            new_lower = [max(0, avg_h - margin_h), max(0, avg_s - margin_s), max(0, avg_v - margin_v)]
            new_upper = [min(180, avg_h + margin_h), min(255, avg_s + margin_s), min(255, avg_v + margin_v)]

            self.set_threshold(f'hsv_{btn_type}_lower', new_lower,
                              f"Auto-healed from {color_name} button detection")
            self.set_threshold(f'hsv_{btn_type}_upper', new_upper,
                              f"Auto-healed from {color_name} button detection")

            updates[btn_type] = {'lower': new_lower, 'upper': new_upper}
            log.info(f"SELF-HEALING: Updated {btn_type} HSV to avg ({avg_h}, {avg_s}, {avg_v})")

        # Save to calibration
        self.calibration['button_colors'] = {
            color: [d['hsv'] for d in dets]
            for color, dets in found_buttons.items()
        }
        self.calibration['last_calibrated'] = datetime.now().isoformat()
        self._save_calibration()

        # Log the fix
        self._log_fix('button_healing', {
            'buttons_found': sum(len(d) for d in found_buttons.values()),
            'updates': updates
        })

        return {
            'healed': True,
            'buttons_found': found_buttons,
            'thresholds_updated': updates
        }

    def _heal_card_detection(self, img: np.ndarray) -> Dict:
        """
        Try multiple white thresholds to find cards.
        """
        h, w = img.shape[:2]

        # Search card region
        y_start = int(h * 0.55)
        y_end = int(h * 0.90)
        x_start = int(w * 0.20)
        x_end = int(w * 0.80)

        search_region = img[y_start:y_end, x_start:x_end]

        # Try multiple thresholds
        for threshold in [200, 180, 160, 140, 120, 100]:
            gray = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            card_candidates = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 1500:
                    continue

                x, y, cw, ch = cv2.boundingRect(cnt)
                if ch == 0:
                    continue

                aspect = cw / ch
                if 0.4 < aspect < 1.0:  # Card-like
                    card_candidates.append((x, y, cw, ch))

            if len(card_candidates) >= 2:
                log.info(f"SELF-HEALING: Found {len(card_candidates)} cards at threshold {threshold}")

                # Update threshold
                self.set_threshold('white_pixel_min', threshold,
                                  f"Auto-healed: found cards at threshold {threshold}")

                # Save to working configs
                self.working_configs['card_thresholds'] = {
                    'white_pixel_min': threshold,
                    'cards_found': len(card_candidates)
                }
                self._save_working_configs()

                self._log_fix('card_healing', {
                    'threshold': threshold,
                    'cards_found': len(card_candidates)
                })

                return {
                    'healed': True,
                    'threshold': threshold,
                    'cards_found': card_candidates
                }

        return {'healed': False, 'reason': 'no_cards_at_any_threshold'}

    def _log_fix(self, fix_type: str, details: Dict):
        """Log a self-healing fix."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': fix_type,
            'details': details
        }

        try:
            with open(FIXES_LOG_FILE, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            log.error(f"Could not log fix: {e}")

    # =========================================================================
    # REPORTING
    # =========================================================================

    def report_issue(self, component: str, description: str,
                     screenshot_path: str = None, severity: str = 'medium'):
        """
        Report an issue for review.

        Args:
            component: Which component has the issue
            description: What went wrong
            screenshot_path: Path to screenshot showing the issue
            severity: 'low', 'medium', 'high'
        """
        issue = {
            'timestamp': datetime.now().isoformat(),
            'component': component,
            'description': description,
            'screenshot': screenshot_path,
            'severity': severity,
        }

        # Append to feedback file
        feedback_file = Path(__file__).parent.parent.parent / 'CLAUDE_FEEDBACK.md'

        try:
            if feedback_file.exists():
                content = feedback_file.read_text()
            else:
                content = "# Claude Feedback - Auto-Reported Issues\n\n"

            content += f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {component}\n"
            content += f"**Severity**: {severity}\n"
            content += f"**Description**: {description}\n"
            if screenshot_path:
                content += f"**Screenshot**: {screenshot_path}\n"

            feedback_file.write_text(content)
            log.info(f"Reported issue: {component} - {description}")
        except Exception as e:
            log.error(f"Could not report issue: {e}")

    def get_session_summary(self) -> Dict:
        """Get summary of current session actions."""
        if not self.session_actions:
            return {'total': 0, 'success': 0, 'fail': 0}

        total = len(self.session_actions)
        success = sum(1 for a in self.session_actions if a['success'])

        by_type = defaultdict(lambda: {'success': 0, 'fail': 0})
        for action in self.session_actions:
            if action['success']:
                by_type[action['action']]['success'] += 1
            else:
                by_type[action['action']]['fail'] += 1

        return {
            'total': total,
            'success': success,
            'fail': total - success,
            'success_rate': success / total if total > 0 else 0,
            'by_type': dict(by_type)
        }


# Singleton instance
_learner: Optional[UnifiedLearner] = None


def get_learner() -> UnifiedLearner:
    """Get the singleton UnifiedLearner instance."""
    global _learner
    if _learner is None:
        _learner = UnifiedLearner()
    return _learner


# Convenience functions for backward compatibility
def log_action(action_type: str, success: bool, details: Dict = None, **kwargs):
    """Log an action (convenience function)."""
    get_learner().log_action(action_type, success, details, **kwargs)


def get_threshold(name: str, default: Any = None) -> Any:
    """Get threshold (convenience function)."""
    return get_learner().get_threshold(name, default)


def set_threshold(name: str, value: Any, reason: str = ""):
    """Set threshold (convenience function)."""
    get_learner().set_threshold(name, value, reason)


def save_screenshot(action_type: str, success: bool, image=None):
    """Save screenshot (convenience function)."""
    return get_learner().save_screenshot(action_type, success, image)


def save_debug_screenshot(context: str, image, reason: str = ""):
    """Save debug screenshot (convenience function)."""
    return get_learner().save_debug_screenshot(context, image, reason)


def report_issue(component: str, description: str, **kwargs):
    """Report issue (convenience function)."""
    get_learner().report_issue(component, description, **kwargs)
