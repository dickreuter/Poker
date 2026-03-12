"""
ADAPTIVE LEARNER - Self-Improving Bot System

This module makes the bot learn and adapt in real-time:
1. Logs all actions and outcomes
2. Tracks detection success/failure rates
3. Adjusts thresholds dynamically
4. Reports issues for Claude to fix

Usage:
    from sys_core.tools.adaptive_learner import AdaptiveLearner
    learner = AdaptiveLearner()

    # Log an action
    learner.log_action('card_detection', success=True, details={'cards': ['AH', 'KS']})

    # Get adaptive threshold
    threshold = learner.get_threshold('white_pixel_min', default=180)

    # Report issue for Claude
    learner.report_issue('card_detection', 'Cards face-down but buttons visible')
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict

log = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / 'data' / 'learning'
ACTIONS_LOG = DATA_DIR / 'actions.jsonl'
THRESHOLDS_FILE = DATA_DIR / 'thresholds.json'
ISSUES_FILE = DATA_DIR / 'issues.jsonl'
STATS_FILE = DATA_DIR / 'stats.json'
SCREENSHOTS_DIR = DATA_DIR / 'screenshots'
CLAUDE_FEEDBACK_FILE = Path(__file__).parent.parent.parent / 'CLAUDE_FEEDBACK.md'


class AdaptiveLearner:
    """
    Self-improving learning system for the system service.

    Tracks:
    - Action success rates (card detection, button clicks, etc.)
    - Detection thresholds that work
    - Issues that need attention
    - Performance stats over time
    """

    def __init__(self):
        self._ensure_dirs()
        self.thresholds = self._load_thresholds()
        self.stats = self._load_stats()
        self.session_start = time.time()
        self.session_actions = defaultdict(lambda: {'success': 0, 'fail': 0})
        # Track file modification time for real-time updates
        self._thresholds_mtime = THRESHOLDS_FILE.stat().st_mtime if THRESHOLDS_FILE.exists() else 0

    def _check_thresholds_changed(self):
        """Check if thresholds.json was modified and reload if so (REAL-TIME UPDATES)"""
        try:
            if THRESHOLDS_FILE.exists():
                current_mtime = THRESHOLDS_FILE.stat().st_mtime
                if current_mtime > self._thresholds_mtime:
                    log.info("REAL-TIME: thresholds.json changed, reloading...")
                    self.thresholds = self._load_thresholds()
                    self._thresholds_mtime = current_mtime
                    return True
        except Exception as e:
            log.debug(f"Threshold check error: {e}")
        return False

    def _ensure_dirs(self):
        """Create data directories if needed"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    def _load_thresholds(self) -> Dict[str, Any]:
        """Load adaptive thresholds"""
        if THRESHOLDS_FILE.exists():
            try:
                return json.loads(THRESHOLDS_FILE.read_text())
            except:
                pass
        # Default thresholds - ALL aspects of the bot
        return {
            # === CARD DETECTION ===
            'white_pixel_min': 180,
            'card_area_min': 2000,
            'card_area_max': 15000,
            'card_aspect_min': 0.5,
            'card_aspect_max': 0.9,
            'match_score_max': 0.35,

            # === BUTTON DETECTION ===
            'button_area_min': 1500,
            'button_area_max': 50000,
            'hsv_green_lower': [35, 80, 80],
            'hsv_green_upper': [85, 255, 255],
            'hsv_orange_lower': [8, 100, 100],
            'hsv_orange_upper': [25, 255, 255],
            'hsv_gray_lower': [0, 0, 30],
            'hsv_gray_upper': [180, 60, 100],

            # === TABLE SIZE ADAPTATION ===
            'table_width_min': 600,
            'table_width_max': 1400,
            'table_height_min': 400,
            'table_height_max': 900,
            'known_table_sizes': [],  # List of (width, height) that work

            # === SCREEN POSITIONS ===
            'card_region_y_start': 0.55,  # % from top where cards start
            'card_region_y_end': 0.95,
            'card_region_x_start': 0.25,
            'card_region_x_end': 0.75,
            'button_region_y_start': 0.65,
            'button_region_y_end': 1.0,
            'icon_bar_height_ratio': 0.12,

            # === OCR SETTINGS ===
            'ocr_confidence_min': 60,
            'ocr_scale_factor': 2,
            'ocr_blur_kernel': 1,
            'ocr_threshold_value': 127,

            # === TIMING ===
            'action_cooldown': 1.5,
            'click_verify_delay': 0.3,
            'table_scan_interval': 0.3,
            'lobby_scan_interval': 1.0,

            # === CLICK POSITIONS (learned offsets) ===
            'click_offset_x': 0,
            'click_offset_y': 0,

            # === GAME TYPE SPECIFIC ===
            'spin_gold': {
                'card_region_y_start': 0.55,
                'button_region_y_start': 0.65,
            },
            'rush_cash': {
                'card_region_y_start': 0.50,
                'button_region_y_start': 0.60,
            },
        }

    def _save_thresholds(self):
        """Save thresholds to file"""
        THRESHOLDS_FILE.write_text(json.dumps(self.thresholds, indent=2))

    def _load_stats(self) -> Dict[str, Any]:
        """Load performance stats"""
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
        """Save stats to file"""
        self.stats['last_updated'] = datetime.now().isoformat()
        STATS_FILE.write_text(json.dumps(self.stats, indent=2))

    def get_threshold(self, name: str, default: Any = None) -> Any:
        """Get an adaptive threshold value (checks for file changes = REAL-TIME)"""
        self._check_thresholds_changed()  # Reload if file was modified
        return self.thresholds.get(name, default)

    def set_threshold(self, name: str, value: Any, reason: str = ""):
        """Set a threshold and log the change"""
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

    def save_screenshot(self, action_type: str, success: bool,
                         image=None, region=None) -> Optional[str]:
        """Save a screenshot for learning reference.

        Args:
            action_type: Type of action (card_detection, button_click, etc.)
            success: Whether the action succeeded
            image: PIL Image or numpy array to save
            region: Optional crop region (x1, y1, x2, y2)

        Returns:
            Path to saved screenshot or None
        """
        try:
            from PIL import Image, ImageGrab
            import numpy as np

            # If no image provided, take a screenshot
            if image is None:
                image = ImageGrab.grab()

            # Convert numpy array to PIL if needed
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)

            # Crop if region specified
            if region:
                image = image.crop(region)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            status = 'ok' if success else 'fail'
            filename = f"{action_type}_{status}_{timestamp}.png"
            filepath = SCREENSHOTS_DIR / filename

            # Save image
            image.save(filepath)
            log.debug(f"Saved screenshot: {filepath}")

            # Clean up old screenshots (keep last 100 per action type)
            self._cleanup_old_screenshots(action_type, keep=100)

            return str(filepath)

        except Exception as e:
            log.warning(f"Could not save screenshot: {e}")
            return None

    def _cleanup_old_screenshots(self, action_type: str, keep: int = 100):
        """Remove old screenshots, keeping only the most recent ones"""
        try:
            pattern = f"{action_type}_*.png"
            files = sorted(SCREENSHOTS_DIR.glob(pattern), key=lambda f: f.stat().st_mtime)
            if len(files) > keep:
                for f in files[:-keep]:
                    f.unlink()
        except Exception:
            pass

    def log_action(self, action_type: str, success: bool, details: Dict = None,
                   screenshot=None, save_on_fail: bool = True):
        """Log an action and its outcome, optionally with screenshot.

        Args:
            action_type: Type of action
            success: Whether action succeeded
            details: Additional details dict
            screenshot: PIL Image or numpy array to save
            save_on_fail: Auto-save screenshot on failure (default True)
        """
        screenshot_path = None

        # Save screenshot if provided, or auto-save on failure
        if screenshot is not None or (not success and save_on_fail):
            screenshot_path = self.save_screenshot(action_type, success, screenshot)

        entry = {
            'timestamp': datetime.now().isoformat(),
            'type': action_type,
            'success': success,
            'details': details or {},
            'screenshot': screenshot_path
        }

        # Append to log file
        with open(ACTIONS_LOG, 'a') as f:
            f.write(json.dumps(entry) + '\n')

        # Update session stats
        if success:
            self.session_actions[action_type]['success'] += 1
        else:
            self.session_actions[action_type]['fail'] += 1

        # Update global stats
        self.stats['total_actions'] += 1
        if success:
            self.stats['successful_actions'] += 1

        if action_type not in self.stats['by_type']:
            self.stats['by_type'][action_type] = {'success': 0, 'fail': 0}
        if success:
            self.stats['by_type'][action_type]['success'] += 1
        else:
            self.stats['by_type'][action_type]['fail'] += 1

        # Check if we need to adapt
        self._check_adaptation(action_type)

    def _check_adaptation(self, action_type: str):
        """Check if we should adapt thresholds based on success rates.

        This is the CORE of the self-learning system. It automatically adjusts
        ALL parameters based on what's working and what's not.
        """
        type_stats = self.stats['by_type'].get(action_type, {})
        total = type_stats.get('success', 0) + type_stats.get('fail', 0)

        if total < 10:  # Need enough data
            return

        success_rate = type_stats.get('success', 0) / total

        # === CARD DETECTION ADAPTATION ===
        if action_type == 'card_detection' and success_rate < 0.5:
            # Lower white threshold if cards not being detected
            current = self.get_threshold('white_pixel_min', 180)
            if current > 120:
                self.set_threshold('white_pixel_min', current - 10,
                                   f"card_detection success rate {success_rate:.1%}")
            # Also try expanding card region
            y_start = self.get_threshold('card_region_y_start', 0.55)
            if y_start > 0.45:
                self.set_threshold('card_region_y_start', y_start - 0.05,
                                   f"Expanding card search region")

        # === BUTTON DETECTION ADAPTATION ===
        elif action_type == 'button_detection' and success_rate < 0.6:
            # Adjust button area thresholds
            min_area = self.get_threshold('button_area_min', 1500)
            if min_area > 500:
                self.set_threshold('button_area_min', min_area - 200,
                                   f"button_detection success rate {success_rate:.1%}")
            # Expand button search region
            y_start = self.get_threshold('button_region_y_start', 0.65)
            if y_start > 0.50:
                self.set_threshold('button_region_y_start', y_start - 0.05,
                                   f"Expanding button search region")

        # === BUTTON CLICK ADAPTATION ===
        elif action_type == 'button_click' and success_rate < 0.7:
            # Increase click verify delay if clicks not registering
            current = self.get_threshold('click_verify_delay', 0.3)
            if current < 1.0:
                self.set_threshold('click_verify_delay', current + 0.1,
                                   f"button_click success rate {success_rate:.1%}")
            # Also adjust click offset if consistently missing
            # (would need click position data to do this properly)

        # === TABLE DETECTION ADAPTATION ===
        elif action_type == 'table_detection' and success_rate < 0.8:
            # Expand table size range
            min_w = self.get_threshold('table_width_min', 600)
            if min_w > 400:
                self.set_threshold('table_width_min', min_w - 50,
                                   f"table_detection expanding size range")

        # === OCR ADAPTATION ===
        elif action_type == 'ocr_detection' and success_rate < 0.6:
            # Lower OCR confidence threshold
            conf = self.get_threshold('ocr_confidence_min', 60)
            if conf > 30:
                self.set_threshold('ocr_confidence_min', conf - 10,
                                   f"ocr_detection success rate {success_rate:.1%}")
            # Adjust scale factor
            scale = self.get_threshold('ocr_scale_factor', 2)
            if scale < 4:
                self.set_threshold('ocr_scale_factor', scale + 1,
                                   f"Increasing OCR scale for better accuracy")

        # === LOBBY NAVIGATION ADAPTATION ===
        elif action_type == 'spin_gold_detection' and success_rate < 0.7:
            # Expand icon bar search area
            ratio = self.get_threshold('icon_bar_height_ratio', 0.12)
            if ratio < 0.20:
                self.set_threshold('icon_bar_height_ratio', ratio + 0.02,
                                   f"Expanding icon bar search")

        # === TIMING ADAPTATION ===
        elif action_type == 'action_timeout' and success_rate < 0.8:
            cooldown = self.get_threshold('action_cooldown', 1.5)
            if cooldown < 3.0:
                self.set_threshold('action_cooldown', cooldown + 0.5,
                                   f"Increasing action cooldown")

    def learn_table_size(self, width: int, height: int, success: bool):
        """Learn which table sizes work well."""
        known_sizes = self.get_threshold('known_table_sizes', [])

        if success:
            # Add successful size if not already known
            size = [width, height]
            if size not in known_sizes:
                known_sizes.append(size)
                self.set_threshold('known_table_sizes', known_sizes,
                                   f"Learned new working table size {width}x{height}")
        else:
            # Log failure for analysis
            log.warning(f"Table size {width}x{height} failed - may need adjustment")

    def learn_click_offset(self, expected_x: int, expected_y: int,
                           actual_x: int, actual_y: int, success: bool):
        """Learn click position offsets for better accuracy."""
        if not success:
            # Calculate offset needed
            offset_x = actual_x - expected_x
            offset_y = actual_y - expected_y

            # Update running average
            current_x = self.get_threshold('click_offset_x', 0)
            current_y = self.get_threshold('click_offset_y', 0)

            # Weighted average (80% old, 20% new)
            new_x = int(current_x * 0.8 + offset_x * 0.2)
            new_y = int(current_y * 0.8 + offset_y * 0.2)

            if abs(new_x - current_x) > 1 or abs(new_y - current_y) > 1:
                self.set_threshold('click_offset_x', new_x, "Learning click offset")
                self.set_threshold('click_offset_y', new_y, "Learning click offset")

    def learn_game_type_settings(self, game_type: str, setting: str,
                                  value: float, success: bool):
        """Learn game-type specific settings (Spin & Gold vs Rush & Cash etc)."""
        game_settings = self.get_threshold(game_type, {})

        if success:
            game_settings[setting] = value
            self.set_threshold(game_type, game_settings,
                               f"Learned {game_type} {setting}={value}")

    def report_issue(self, component: str, description: str,
                     screenshot_path: str = None, severity: str = 'medium'):
        """Report an issue for Claude to fix"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'component': component,
            'description': description,
            'screenshot': screenshot_path,
            'severity': severity,
            'resolved': False
        }

        # Append to issues file
        with open(ISSUES_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')

        # Also write to CLAUDE_FEEDBACK.md for visibility
        self._update_claude_feedback(entry)

        log.warning(f"Issue reported: [{component}] {description}")

    def _update_claude_feedback(self, issue: Dict):
        """Update CLAUDE_FEEDBACK.md with new issue"""
        header = """# Bot Feedback - Issues for Claude to Fix

This file is auto-generated by the adaptive learner.
Claude should read this and fix the reported issues.

---

"""
        existing = ""
        if CLAUDE_FEEDBACK_FILE.exists():
            existing = CLAUDE_FEEDBACK_FILE.read_text()
            if existing.startswith("# Bot Feedback"):
                # Remove header
                existing = existing.split("---\n", 1)[-1] if "---\n" in existing else ""

        new_entry = f"""
## [{issue['severity'].upper()}] {issue['component']} - {issue['timestamp'][:16]}

**Issue:** {issue['description']}

**Screenshot:** {issue.get('screenshot', 'None')}

**Status:** {'Resolved' if issue['resolved'] else 'OPEN'}

---
"""

        CLAUDE_FEEDBACK_FILE.write_text(header + new_entry + existing)

    def get_success_rate(self, action_type: str = None) -> float:
        """Get success rate for an action type or overall"""
        if action_type:
            type_stats = self.stats['by_type'].get(action_type, {})
            total = type_stats.get('success', 0) + type_stats.get('fail', 0)
            if total == 0:
                return 0.0
            return type_stats.get('success', 0) / total
        else:
            if self.stats['total_actions'] == 0:
                return 0.0
            return self.stats['successful_actions'] / self.stats['total_actions']

    def get_session_summary(self) -> Dict:
        """Get summary of current session"""
        duration = time.time() - self.session_start
        total_actions = sum(
            s['success'] + s['fail']
            for s in self.session_actions.values()
        )

        return {
            'duration_seconds': duration,
            'total_actions': total_actions,
            'actions_per_minute': total_actions / (duration / 60) if duration > 0 else 0,
            'by_type': dict(self.session_actions),
            'thresholds': self.thresholds
        }

    def end_session(self):
        """End session and save all data"""
        self.stats['sessions'] += 1
        self._save_stats()
        self._save_thresholds()

        summary = self.get_session_summary()
        log.info(f"Session ended: {summary['total_actions']} actions in "
                 f"{summary['duration_seconds']:.0f}s "
                 f"({summary['actions_per_minute']:.1f}/min)")

        return summary

    def get_recommendations(self) -> List[str]:
        """Get recommendations based on stats"""
        recommendations = []

        for action_type, stats in self.stats['by_type'].items():
            total = stats['success'] + stats['fail']
            if total < 5:
                continue
            rate = stats['success'] / total

            if rate < 0.5:
                recommendations.append(
                    f"❌ {action_type} has low success rate ({rate:.0%}). "
                    f"Consider adjusting detection parameters."
                )
            elif rate < 0.8:
                recommendations.append(
                    f"⚠️ {action_type} success rate is {rate:.0%}. "
                    f"Room for improvement."
                )

        if not recommendations:
            recommendations.append("✅ All action types performing well!")

        return recommendations


# Singleton instance
_learner = None

def get_learner() -> AdaptiveLearner:
    """Get the singleton learner instance"""
    global _learner
    if _learner is None:
        _learner = AdaptiveLearner()
    return _learner


# Convenience functions
def log_action(action_type: str, success: bool, details: Dict = None,
               screenshot=None, save_on_fail: bool = True):
    """Log an action with optional screenshot"""
    get_learner().log_action(action_type, success, details, screenshot, save_on_fail)

def report_issue(component: str, description: str, **kwargs):
    """Report an issue"""
    get_learner().report_issue(component, description, **kwargs)

def save_screenshot(action_type: str, success: bool, image=None, region=None):
    """Save a screenshot for learning reference"""
    return get_learner().save_screenshot(action_type, success, image, region)

def save_debug_screenshot(action_type: str, image, reason: str = "failure"):
    """
    Save a debug screenshot when detection fails.

    Claude can look at these screenshots to understand what went wrong
    and improve the detection code.

    Args:
        action_type: e.g., 'table_detection', 'card_detection'
        image: PIL Image to save
        reason: Why this screenshot was saved (e.g., 'not_ready', 'no_cards')

    Returns:
        Path to saved screenshot or None
    """
    from datetime import datetime

    debug_dir = DATA_DIR / 'debug'
    debug_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{action_type}_{reason}_{timestamp}.png"
    filepath = debug_dir / filename

    try:
        image.save(filepath)
        log.info(f"Debug screenshot saved: {filepath}")
        return str(filepath)
    except Exception as e:
        log.error(f"Failed to save debug screenshot: {e}")
        return None

def get_threshold(name: str, default: Any = None) -> Any:
    """Get adaptive threshold"""
    return get_learner().get_threshold(name, default)

def set_threshold(name: str, value: Any, reason: str = ""):
    """Set an adaptive threshold"""
    get_learner().set_threshold(name, value, reason)

def learn_table_size(width: int, height: int, success: bool):
    """Learn which table sizes work"""
    get_learner().learn_table_size(width, height, success)

def learn_click_offset(expected_x: int, expected_y: int,
                       actual_x: int, actual_y: int, success: bool):
    """Learn click position offsets"""
    get_learner().learn_click_offset(expected_x, expected_y, actual_x, actual_y, success)

def learn_game_type(game_type: str, setting: str, value: float, success: bool):
    """Learn game-type specific settings"""
    get_learner().learn_game_type_settings(game_type, setting, value, success)

def get_all_thresholds() -> Dict:
    """Get all current thresholds"""
    return get_learner().thresholds

def get_stats() -> Dict:
    """Get all learning stats"""
    return get_learner().stats

def get_success_rate(action_type: str = None) -> float:
    """Get success rate for an action type or overall"""
    return get_learner().get_success_rate(action_type)

def end_session():
    """End session and save all learning data"""
    return get_learner().end_session()
