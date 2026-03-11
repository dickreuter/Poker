"""
Smart UI Automation for GGPoker - Robust Visual Detection System

This module provides a comprehensive, self-correcting UI automation system that:
1. Works regardless of window size/position using visual detection
2. Handles macOS Retina display (2x scaling) coordinate conversion
3. Uses multiple detection strategies (template matching, color detection, OCR)
4. Has extensive logging and verification
5. Self-corrects when clicks fail

Usage:
    from gamble.tools.smart_ui_automation import SmartUIAutomation

    ui = SmartUIAutomation()

    # Find and click any button by its visual appearance
    success = ui.find_and_click_button("Fold")

    # Or use specific detection methods
    button = ui.find_button_by_template("fold_button.png")
    button = ui.find_button_by_text("FOLD")
    button = ui.find_button_by_color("red")

Author: Claude Code (2026)
"""

import logging
import subprocess
import time
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union, Callable
from functools import wraps

import cv2
import numpy as np
from PIL import Image, ImageGrab

try:
    from pynput.mouse import Button as MouseButton, Controller as MouseController
except ImportError:
    MouseController = None
    MouseButton = None

try:
    from tesserocr import PyTessBaseAPI, PSM, OEM
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

# Configure logging
log = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS - Retina Display Configuration
# ============================================================================

class DisplayConfig:
    """Configuration for macOS Retina display handling."""

    # Retina scale factor (2x for standard Retina MacBooks)
    RETINA_SCALE: int = 2

    # Screen dimensions in POINTS (what macOS reports)
    SCREEN_POINTS: Tuple[int, int] = (1710, 1112)

    # Screen dimensions in PIXELS (actual screenshot size)
    SCREEN_PIXELS: Tuple[int, int] = (3420, 2224)

    # GGPoker window defaults
    GGPOKER_WINDOW_POINTS: Dict[str, int] = {
        'x': 62, 'y': 127, 'width': 1200, 'height': 720
    }

    @classmethod
    def points_to_pixels(cls, x_pt: int, y_pt: int) -> Tuple[int, int]:
        """Convert macOS POINTS to screenshot PIXELS."""
        return (x_pt * cls.RETINA_SCALE, y_pt * cls.RETINA_SCALE)

    @classmethod
    def pixels_to_points(cls, x_px: int, y_px: int) -> Tuple[int, int]:
        """Convert screenshot PIXELS to macOS POINTS for clicking."""
        return (x_px // cls.RETINA_SCALE, y_px // cls.RETINA_SCALE)


class DetectionMethod(Enum):
    """Available detection methods for finding UI elements."""
    TEMPLATE_MATCHING = "template_matching"
    COLOR_DETECTION = "color_detection"
    OCR_TEXT = "ocr_text"
    EDGE_DETECTION = "edge_detection"
    COMBINED = "combined"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Point:
    """Represents a point with both pixel and point coordinates."""
    x_px: int  # X coordinate in PIXELS
    y_px: int  # Y coordinate in PIXELS

    @property
    def x_pt(self) -> int:
        """X coordinate in POINTS for clicking."""
        return self.x_px // DisplayConfig.RETINA_SCALE

    @property
    def y_pt(self) -> int:
        """Y coordinate in POINTS for clicking."""
        return self.y_px // DisplayConfig.RETINA_SCALE

    @property
    def as_pixels(self) -> Tuple[int, int]:
        return (self.x_px, self.y_px)

    @property
    def as_points(self) -> Tuple[int, int]:
        return (self.x_pt, self.y_pt)

    def __repr__(self):
        return f"Point(px=({self.x_px},{self.y_px}), pt=({self.x_pt},{self.y_pt}))"


@dataclass
class BoundingBox:
    """Represents a rectangular region with coordinates in pixels."""
    x_px: int
    y_px: int
    width_px: int
    height_px: int

    @property
    def center(self) -> Point:
        """Center point of the bounding box."""
        return Point(
            self.x_px + self.width_px // 2,
            self.y_px + self.height_px // 2
        )

    @property
    def as_tuple(self) -> Tuple[int, int, int, int]:
        """Returns (x, y, width, height) in pixels."""
        return (self.x_px, self.y_px, self.width_px, self.height_px)

    def __repr__(self):
        return f"BoundingBox(x={self.x_px}, y={self.y_px}, w={self.width_px}, h={self.height_px})"


@dataclass
class DetectionResult:
    """Result of a UI element detection attempt."""
    found: bool
    confidence: float = 0.0
    location: Optional[Point] = None
    bounding_box: Optional[BoundingBox] = None
    method_used: Optional[DetectionMethod] = None
    element_name: str = ""
    additional_info: Dict = field(default_factory=dict)

    def __bool__(self):
        return self.found


@dataclass
class ClickResult:
    """Result of a click action with verification."""
    success: bool
    click_location: Optional[Point] = None
    verification_passed: bool = False
    retry_count: int = 0
    error_message: str = ""

    def __bool__(self):
        return self.success


# ============================================================================
# COLOR PROFILES FOR GGPOKER BUTTONS
# ============================================================================

class ButtonColorProfiles:
    """HSV color profiles for GGPoker button detection."""

    # Button colors in HSV (Hue, Saturation, Value)
    # Note: OpenCV uses H: 0-180, S: 0-255, V: 0-255

    PROFILES = {
        'fold': {
            'primary': {
                'lower': np.array([0, 0, 40]),      # Dark gray
                'upper': np.array([180, 60, 130])
            },
            'text_color': 'white'
        },
        'call': {
            'primary': {
                'lower': np.array([35, 60, 60]),    # Green
                'upper': np.array([85, 255, 255])
            },
            'text_color': 'white'
        },
        'check': {
            'primary': {
                'lower': np.array([35, 60, 60]),    # Same as Call (green)
                'upper': np.array([85, 255, 255])
            },
            'text_color': 'white'
        },
        'raise': {
            'primary': {
                'lower': np.array([10, 80, 80]),    # Orange/gold
                'upper': np.array([30, 255, 255])
            },
            'text_color': 'white'
        },
        'bet': {
            'primary': {
                'lower': np.array([10, 80, 80]),    # Orange/gold (same as Raise)
                'upper': np.array([30, 255, 255])
            },
            'text_color': 'white'
        },
        'allin': {
            'primary': {
                'lower': np.array([0, 100, 100]),   # Red
                'upper': np.array([15, 255, 255])
            },
            'secondary': {
                'lower': np.array([165, 100, 100]), # Red wraps around in HSV
                'upper': np.array([180, 255, 255])
            },
            'text_color': 'white'
        },
        'register': {
            'primary': {
                'lower': np.array([35, 80, 80]),    # Green (brighter)
                'upper': np.array([80, 255, 255])
            },
            'text_color': 'white'
        },
        'cancel': {
            'primary': {
                'lower': np.array([0, 0, 30]),      # Dark gray
                'upper': np.array([180, 50, 100])
            },
            'text_color': 'white'
        }
    }

    @classmethod
    def get_profile(cls, button_name: str) -> Optional[Dict]:
        """Get color profile for a button name (case-insensitive)."""
        return cls.PROFILES.get(button_name.lower())


# ============================================================================
# DECORATORS FOR LOGGING AND RETRY
# ============================================================================

def with_logging(func):
    """Decorator to add comprehensive logging to functions."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        log.debug(f"[{func_name}] Starting with args={args[1:] if args else ()}, kwargs={kwargs}")
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            log.debug(f"[{func_name}] Completed in {elapsed:.3f}s with result={result}")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            log.error(f"[{func_name}] Failed after {elapsed:.3f}s with error: {e}")
            raise
    return wrapper


def with_retry(max_attempts: int = 3, delay: float = 0.5):
    """Decorator to retry failed operations."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    log.warning(f"[{func.__name__}] Attempt {attempt + 1}/{max_attempts} failed: {e}")
                    if attempt < max_attempts - 1:
                        time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator


# ============================================================================
# WINDOW FINDER - Uses macOS AppleScript
# ============================================================================

class WindowFinder:
    """Finds GGPoker windows using macOS AppleScript."""

    @staticmethod
    @with_logging
    def find_ggpoker_windows() -> List[Dict]:
        """
        Find all GGPoker windows using macOS AppleScript.
        Returns list of dicts with position/size in POINTS.
        """
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
                    set output to output & winName & "###" & ¬
                        (item 1 of winPos as text) & "," & ¬
                        (item 2 of winPos as text) & "," & ¬
                        (item 1 of winSize as text) & "," & ¬
                        (item 2 of winSize as text) & ";"
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
                    if '###' in entry:
                        name, coords = entry.split('###')
                        # Fix Unicode minus sign (−) that macOS returns instead of ASCII minus (-)
                        coords = coords.replace('−', '-').replace('–', '-')
                        x, y, w, h = map(int, coords.split(','))
                        windows.append({
                            'name': name.strip(),
                            'x_pt': x, 'y_pt': y,
                            'width_pt': w, 'height_pt': h,
                            'x_px': x * DisplayConfig.RETINA_SCALE,
                            'y_px': y * DisplayConfig.RETINA_SCALE,
                            'width_px': w * DisplayConfig.RETINA_SCALE,
                            'height_px': h * DisplayConfig.RETINA_SCALE
                        })

            log.info(f"Found {len(windows)} GGPoker window(s)")
            return windows

        except subprocess.TimeoutExpired:
            log.error("Timeout finding GGPoker windows")
            return []
        except Exception as e:
            log.error(f"Error finding windows: {e}")
            return []

    @staticmethod
    def get_poker_tables() -> List[Dict]:
        """Filter windows to only include poker table windows."""
        keywords = ['Spin', 'Gold', 'Rush', 'Cash', 'Hold', 'Omaha', 'Blinds', 'NL', 'PLO']
        windows = WindowFinder.find_ggpoker_windows()
        return [w for w in windows if any(kw in w['name'] for kw in keywords)]

    @staticmethod
    def focus_window(window_name_contains: str) -> bool:
        """Bring a window to front by partial name match."""
        script = f'''
        tell application "System Events"
            tell process "GGnet"
                set frontmost to true
                repeat with w in windows
                    if name of w contains "{window_name_contains}" then
                        perform action "AXRaise" of w
                        return true
                    end if
                end repeat
            end tell
        end tell
        return false
        '''
        try:
            result = subprocess.run(['osascript', '-e', script],
                                   capture_output=True, text=True, timeout=3)
            return 'true' in result.stdout.lower()
        except:
            return False


# ============================================================================
# TEMPLATE MATCHER - OpenCV-based visual detection
# ============================================================================

class TemplateMatcher:
    """Template matching with confidence scoring and multi-scale support."""

    def __init__(self, templates_dir: Optional[str] = None):
        self.templates_dir = templates_dir
        self._template_cache: Dict[str, np.ndarray] = {}

    @with_logging
    def match_template(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        confidence_thresholds: List[float] = None,
        search_region: Optional[BoundingBox] = None
    ) -> DetectionResult:
        """
        Find template in screenshot with adaptive confidence threshold.

        Args:
            screenshot: CV2 BGR image to search in
            template: CV2 BGR template image to find
            confidence_thresholds: List of thresholds to try (lower = stricter)
            search_region: Optional region to limit search

        Returns:
            DetectionResult with location and confidence
        """
        if confidence_thresholds is None:
            confidence_thresholds = [0.01, 0.03, 0.05, 0.10, 0.15, 0.20, 0.25]

        # Limit search to region if specified
        if search_region:
            x, y, w, h = search_region.as_tuple
            search_area = screenshot[y:y+h, x:x+w]
            offset = (x, y)
        else:
            search_area = screenshot
            offset = (0, 0)

        # Verify sizes are compatible
        if template.shape[0] > search_area.shape[0] or template.shape[1] > search_area.shape[1]:
            log.warning(f"Template size {template.shape[:2]} larger than search area {search_area.shape[:2]}")
            return DetectionResult(found=False)

        # Perform template matching
        result = cv2.matchTemplate(search_area, template, cv2.TM_SQDIFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # For TM_SQDIFF_NORMED, lower score = better match
        best_score = min_val
        best_loc = min_loc

        log.debug(f"Template match best score: {best_score:.6f}")

        # Try each threshold from strictest to most permissive
        for threshold in confidence_thresholds:
            if best_score <= threshold:
                # Calculate center of matched region
                template_h, template_w = template.shape[:2]
                center_x = offset[0] + best_loc[0] + template_w // 2
                center_y = offset[1] + best_loc[1] + template_h // 2

                log.info(f"Template match SUCCESS: score={best_score:.6f}, threshold={threshold}")

                return DetectionResult(
                    found=True,
                    confidence=1.0 - best_score,  # Convert to confidence (higher = better)
                    location=Point(center_x, center_y),
                    bounding_box=BoundingBox(
                        offset[0] + best_loc[0],
                        offset[1] + best_loc[1],
                        template_w,
                        template_h
                    ),
                    method_used=DetectionMethod.TEMPLATE_MATCHING,
                    additional_info={'score': best_score, 'threshold': threshold}
                )

        log.debug(f"Template match FAILED: best score {best_score:.6f} exceeds all thresholds")
        return DetectionResult(
            found=False,
            confidence=1.0 - best_score,
            method_used=DetectionMethod.TEMPLATE_MATCHING,
            additional_info={'score': best_score}
        )

    @with_logging
    def match_template_multi_scale(
        self,
        screenshot: np.ndarray,
        template: np.ndarray,
        scales: List[float] = None,
        confidence_threshold: float = 0.15
    ) -> DetectionResult:
        """
        Match template at multiple scales to handle resolution differences.
        """
        if scales is None:
            scales = [0.8, 0.9, 1.0, 1.1, 1.2]

        best_result = DetectionResult(found=False)
        best_score = float('inf')

        for scale in scales:
            # Resize template
            h, w = template.shape[:2]
            new_w, new_h = int(w * scale), int(h * scale)

            if new_w < 10 or new_h < 10:
                continue

            scaled_template = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)

            result = self.match_template(screenshot, scaled_template, [confidence_threshold])

            if result.found:
                score = result.additional_info.get('score', 1.0)
                if score < best_score:
                    best_score = score
                    best_result = result
                    best_result.additional_info['scale'] = scale
                    log.debug(f"Better match at scale {scale}: score={score:.6f}")

        return best_result


# ============================================================================
# COLOR DETECTOR - Find buttons by HSV color
# ============================================================================

class ColorDetector:
    """Detects UI elements by their color using HSV color space."""

    @with_logging
    def find_by_color(
        self,
        screenshot: np.ndarray,
        color_lower: np.ndarray,
        color_upper: np.ndarray,
        min_area: int = 2000,
        max_area: int = 50000,
        aspect_ratio_range: Tuple[float, float] = (1.5, 8.0),
        search_region: Optional[BoundingBox] = None
    ) -> List[DetectionResult]:
        """
        Find regions matching a color range.

        Args:
            screenshot: CV2 BGR image
            color_lower: Lower HSV bounds
            color_upper: Upper HSV bounds
            min_area: Minimum contour area
            max_area: Maximum contour area
            aspect_ratio_range: (min, max) width/height ratio for buttons
            search_region: Optional region to limit search

        Returns:
            List of DetectionResults for each matching region
        """
        # Apply search region if specified
        if search_region:
            x, y, w, h = search_region.as_tuple
            search_area = screenshot[y:y+h, x:x+w]
            offset = (x, y)
        else:
            search_area = screenshot
            offset = (0, 0)

        # Convert to HSV
        hsv = cv2.cvtColor(search_area, cv2.COLOR_BGR2HSV)

        # Create mask for the color range
        mask = cv2.inRange(hsv, color_lower, color_upper)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results = []

        for contour in contours:
            area = cv2.contourArea(contour)

            if area < min_area or area > max_area:
                continue

            x_c, y_c, w_c, h_c = cv2.boundingRect(contour)

            # Check aspect ratio (buttons are typically wider than tall)
            aspect_ratio = w_c / h_c if h_c > 0 else 0
            if not (aspect_ratio_range[0] <= aspect_ratio <= aspect_ratio_range[1]):
                continue

            # Calculate center
            center_x = offset[0] + x_c + w_c // 2
            center_y = offset[1] + y_c + h_c // 2

            # Calculate confidence based on how well the shape matches expectations
            confidence = min(1.0, area / max_area)

            results.append(DetectionResult(
                found=True,
                confidence=confidence,
                location=Point(center_x, center_y),
                bounding_box=BoundingBox(
                    offset[0] + x_c,
                    offset[1] + y_c,
                    w_c, h_c
                ),
                method_used=DetectionMethod.COLOR_DETECTION,
                additional_info={'area': area, 'aspect_ratio': aspect_ratio}
            ))

        # Sort by area (larger = more likely to be the button)
        results.sort(key=lambda r: r.additional_info.get('area', 0), reverse=True)

        log.debug(f"Color detection found {len(results)} matches")
        return results

    @with_logging
    def find_button_by_name(
        self,
        screenshot: np.ndarray,
        button_name: str,
        search_region: Optional[BoundingBox] = None
    ) -> DetectionResult:
        """
        Find a button by name using its color profile.

        Args:
            screenshot: CV2 BGR image
            button_name: Name of button (fold, call, raise, bet, etc.)
            search_region: Optional region to limit search

        Returns:
            DetectionResult for the button
        """
        profile = ButtonColorProfiles.get_profile(button_name)

        if not profile:
            log.warning(f"No color profile for button: {button_name}")
            return DetectionResult(found=False, element_name=button_name)

        # Try primary color range
        results = self.find_by_color(
            screenshot,
            profile['primary']['lower'],
            profile['primary']['upper'],
            search_region=search_region
        )

        # Try secondary color range if exists and primary failed
        if not results and 'secondary' in profile:
            results = self.find_by_color(
                screenshot,
                profile['secondary']['lower'],
                profile['secondary']['upper'],
                search_region=search_region
            )

        if results:
            best = results[0]
            best.element_name = button_name
            log.info(f"Found {button_name} button at {best.location}")
            return best

        log.debug(f"Button '{button_name}' not found by color")
        return DetectionResult(found=False, element_name=button_name)


# ============================================================================
# OCR DETECTOR - Find buttons by text
# ============================================================================

class OCRDetector:
    """Detects UI elements by reading their text using OCR."""

    def __init__(self, tesseract_path: Optional[str] = None):
        self.tesseract_available = TESSERACT_AVAILABLE
        self._api = None

        if self.tesseract_available:
            try:
                # Initialize tesseract API
                tessdata = tesseract_path or os.path.join(
                    os.path.dirname(os.path.dirname(__file__)), 'tessdata'
                )
                if os.path.exists(tessdata):
                    self._api = PyTessBaseAPI(path=tessdata, psm=PSM.SINGLE_LINE, oem=OEM.LSTM_ONLY)
                else:
                    log.warning(f"Tesseract data not found at {tessdata}")
                    self.tesseract_available = False
            except Exception as e:
                log.warning(f"Failed to initialize Tesseract: {e}")
                self.tesseract_available = False

    def _preprocess_for_ocr(self, image: np.ndarray) -> Image.Image:
        """Preprocess image for better OCR results."""
        # Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Resize for better OCR (300 DPI equivalent)
        scale = 3
        resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # Apply thresholding
        _, thresh = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        return Image.fromarray(thresh)

    @with_logging
    def find_text_region(
        self,
        screenshot: np.ndarray,
        text_to_find: str,
        search_region: Optional[BoundingBox] = None,
        case_sensitive: bool = False
    ) -> DetectionResult:
        """
        Find a region containing specific text.

        Args:
            screenshot: CV2 BGR image
            text_to_find: Text to search for
            search_region: Optional region to limit search
            case_sensitive: Whether to match case

        Returns:
            DetectionResult for the text region
        """
        if not self.tesseract_available:
            log.warning("Tesseract not available for OCR")
            return DetectionResult(found=False, element_name=text_to_find)

        # Apply search region if specified
        if search_region:
            x, y, w, h = search_region.as_tuple
            search_area = screenshot[y:y+h, x:x+w]
            offset = (x, y)
        else:
            search_area = screenshot
            offset = (0, 0)

        try:
            # Preprocess and run OCR
            processed = self._preprocess_for_ocr(search_area)
            self._api.SetImage(processed)

            # Get text and boxes
            recognized_text = self._api.GetUTF8Text().strip()

            # Check for match
            search_text = text_to_find if case_sensitive else text_to_find.lower()
            found_text = recognized_text if case_sensitive else recognized_text.lower()

            if search_text in found_text:
                # Get bounding boxes for words
                boxes = self._api.GetComponentImages(2, True)  # RIL_WORD level

                for box_img, box_data, _, _ in boxes:
                    box_text = self._api.GetUTF8Text().strip()
                    if search_text in (box_text if case_sensitive else box_text.lower()):
                        x_b, y_b, w_b, h_b = box_data['x'], box_data['y'], box_data['w'], box_data['h']

                        # Scale back and add offset
                        x_b, y_b = x_b // 3, y_b // 3
                        w_b, h_b = w_b // 3, h_b // 3

                        return DetectionResult(
                            found=True,
                            confidence=0.9,
                            location=Point(offset[0] + x_b + w_b // 2, offset[1] + y_b + h_b // 2),
                            bounding_box=BoundingBox(offset[0] + x_b, offset[1] + y_b, w_b, h_b),
                            method_used=DetectionMethod.OCR_TEXT,
                            element_name=text_to_find,
                            additional_info={'recognized_text': recognized_text}
                        )

                # Text found but couldn't get exact box
                log.info(f"Text '{text_to_find}' found in OCR result")
                return DetectionResult(
                    found=True,
                    confidence=0.7,
                    method_used=DetectionMethod.OCR_TEXT,
                    element_name=text_to_find,
                    additional_info={'recognized_text': recognized_text}
                )

        except Exception as e:
            log.error(f"OCR error: {e}")

        return DetectionResult(found=False, element_name=text_to_find)


# ============================================================================
# CLICK EXECUTOR - Handles clicking with verification
# ============================================================================

class ClickExecutor:
    """Executes clicks with coordinate conversion and verification."""

    def __init__(self):
        if MouseController is None:
            raise ImportError("pynput is required for clicking. Install with: pip install pynput")
        self.mouse = MouseController()

    @with_logging
    def click_at_point(
        self,
        point: Point,
        button: str = 'left',
        double_click: bool = False,
        focus_window: bool = True
    ) -> bool:
        """
        Click at a point (using POINTS coordinates for macOS).

        Args:
            point: Point object with coordinates
            button: 'left' or 'right'
            double_click: Whether to double-click
            focus_window: Whether to focus GGPoker first

        Returns:
            True if click was executed successfully
        """
        try:
            # Focus GGPoker window if requested
            if focus_window:
                self._focus_ggpoker()
                time.sleep(0.1)

            # Get click position in POINTS
            x_pt, y_pt = point.as_points

            log.info(f"Clicking at ({x_pt}, {y_pt}) POINTS (from {point.as_pixels} PIXELS)")

            # Move mouse
            self.mouse.position = (x_pt, y_pt)
            time.sleep(0.05)

            # Click
            mouse_button = MouseButton.left if button == 'left' else MouseButton.right
            clicks = 2 if double_click else 1
            self.mouse.click(mouse_button, clicks)

            return True

        except Exception as e:
            log.error(f"Click failed: {e}")
            return False

    def _focus_ggpoker(self):
        """Focus the GGPoker application."""
        script = '''
        tell application "System Events"
            tell process "GGnet" to set frontmost to true
        end tell
        '''
        try:
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=2)
        except:
            pass

    @with_logging
    def click_at_pixels(
        self,
        x_px: int,
        y_px: int,
        window_offset: Optional[Tuple[int, int]] = None,
        **kwargs
    ) -> bool:
        """
        Click at pixel coordinates, converting to points automatically.

        Args:
            x_px: X coordinate in pixels
            y_px: Y coordinate in pixels
            window_offset: Optional (x, y) offset for window position in pixels
            **kwargs: Additional arguments for click_at_point

        Returns:
            True if click was executed successfully
        """
        # Apply window offset if provided
        if window_offset:
            x_px += window_offset[0]
            y_px += window_offset[1]

        point = Point(x_px, y_px)
        return self.click_at_point(point, **kwargs)


# ============================================================================
# MAIN SMART UI AUTOMATION CLASS
# ============================================================================

class SmartUIAutomation:
    """
    Main class for smart UI automation with self-correction.

    Combines multiple detection methods and handles Retina display
    coordinate conversion automatically.
    """

    def __init__(
        self,
        ggpoker_window: Optional[Dict] = None,
        max_retries: int = 3,
        verification_delay: float = 0.5
    ):
        """
        Initialize the Smart UI Automation system.

        Args:
            ggpoker_window: Optional window info dict. If None, will auto-detect.
            max_retries: Maximum retries for failed clicks
            verification_delay: Delay before verification after click
        """
        self.window = ggpoker_window
        self.max_retries = max_retries
        self.verification_delay = verification_delay

        # Initialize components
        self.window_finder = WindowFinder()
        self.template_matcher = TemplateMatcher()
        self.color_detector = ColorDetector()
        self.ocr_detector = OCRDetector()
        self.click_executor = ClickExecutor()

        # Caches
        self._last_screenshot: Optional[np.ndarray] = None
        self._last_screenshot_time: float = 0
        self._screenshot_cache_duration: float = 0.1  # seconds

        log.info("SmartUIAutomation initialized")

    def take_screenshot(self, force_new: bool = False) -> np.ndarray:
        """
        Take a screenshot, with optional caching.

        Args:
            force_new: Force taking a new screenshot even if cached

        Returns:
            CV2 BGR image
        """
        current_time = time.time()

        if (not force_new and
            self._last_screenshot is not None and
            current_time - self._last_screenshot_time < self._screenshot_cache_duration):
            return self._last_screenshot

        # Take new screenshot
        pil_screenshot = ImageGrab.grab()
        cv2_screenshot = cv2.cvtColor(np.array(pil_screenshot), cv2.COLOR_RGB2BGR)

        self._last_screenshot = cv2_screenshot
        self._last_screenshot_time = current_time

        log.debug(f"Screenshot taken: {cv2_screenshot.shape}")
        return cv2_screenshot

    def get_button_search_region(self, window: Optional[Dict] = None) -> BoundingBox:
        """
        Get the search region for buttons (bottom-right area of table).

        Args:
            window: Window info dict

        Returns:
            BoundingBox for button search region
        """
        if window is None:
            window = self.window or self._detect_window()

        if window is None:
            # Return full screen bottom half
            screenshot = self.take_screenshot()
            h, w = screenshot.shape[:2]
            return BoundingBox(int(w * 0.3), int(h * 0.65), int(w * 0.7), int(h * 0.35))

        # Buttons are in bottom area of window (78%+ to exclude pot slider)
        x = window['x_px'] + int(window['width_px'] * 0.15)
        y = window['y_px'] + int(window['height_px'] * 0.78)
        w = int(window['width_px'] * 0.85)
        h = int(window['height_px'] * 0.22)

        return BoundingBox(x, y, w, h)

    def _detect_window(self) -> Optional[Dict]:
        """Auto-detect GGPoker window."""
        windows = self.window_finder.find_ggpoker_windows()

        # Prefer poker tables over lobby
        tables = [w for w in windows if any(
            kw in w['name'] for kw in ['Spin', 'Gold', 'Rush', 'Cash', 'Hold']
        )]

        if tables:
            self.window = tables[0]
            log.info(f"Auto-detected table: {tables[0]['name']}")
            return tables[0]
        elif windows:
            self.window = windows[0]
            log.info(f"Using window: {windows[0]['name']}")
            return windows[0]

        log.warning("No GGPoker window detected")
        return None

    @with_logging
    def find_button(
        self,
        button_name: str,
        method: DetectionMethod = DetectionMethod.COMBINED,
        screenshot: Optional[np.ndarray] = None
    ) -> DetectionResult:
        """
        Find a button using the specified detection method.

        Args:
            button_name: Name of button (fold, call, raise, bet, check, etc.)
            method: Detection method to use
            screenshot: Optional pre-taken screenshot

        Returns:
            DetectionResult with button location
        """
        if screenshot is None:
            screenshot = self.take_screenshot(force_new=True)

        # Detect window if not set
        if self.window is None:
            self._detect_window()

        search_region = self.get_button_search_region()

        result = DetectionResult(found=False, element_name=button_name)

        if method == DetectionMethod.COLOR_DETECTION or method == DetectionMethod.COMBINED:
            result = self.color_detector.find_button_by_name(
                screenshot, button_name, search_region
            )
            if result.found:
                return result

        if method == DetectionMethod.OCR_TEXT or (method == DetectionMethod.COMBINED and not result.found):
            result = self.ocr_detector.find_text_region(
                screenshot, button_name.upper(), search_region
            )
            if result.found:
                return result

        # For fold button, try finding it relative to call button
        if button_name.lower() == 'fold' and not result.found:
            result = self._find_fold_relative_to_call(screenshot, search_region)
            if result.found:
                return result

        log.warning(f"Button '{button_name}' not found with method {method}")
        return result

    def _find_fold_relative_to_call(
        self,
        screenshot: np.ndarray,
        search_region: BoundingBox
    ) -> DetectionResult:
        """
        Find Fold button by looking to the left of Call button.
        GGPoker's Fold button is dark gray, hard to detect by color.
        """
        # First find Call button (green, easy to detect)
        call_result = self.color_detector.find_button_by_name(
            screenshot, 'call', search_region
        )

        if not call_result.found:
            return DetectionResult(found=False, element_name='fold')

        # Fold is typically to the left of Call, at same Y
        call_x = call_result.location.x_px
        call_y = call_result.location.y_px
        button_width = call_result.bounding_box.width_px if call_result.bounding_box else 120

        # Estimate Fold position: call_x - (button_width + gap)
        fold_x = call_x - button_width - 40  # 40px gap estimate

        log.info(f"Estimated Fold position based on Call: ({fold_x}, {call_y})")

        return DetectionResult(
            found=True,
            confidence=0.7,
            location=Point(fold_x, call_y),
            method_used=DetectionMethod.COLOR_DETECTION,
            element_name='fold',
            additional_info={'derived_from': 'call_position'}
        )

    @with_logging
    def find_and_click_button(
        self,
        button_name: str,
        method: DetectionMethod = DetectionMethod.COMBINED,
        verify: bool = True,
        retry_count: int = 0
    ) -> ClickResult:
        """
        Find and click a button with optional verification.

        Args:
            button_name: Name of button to find and click
            method: Detection method to use
            verify: Whether to verify the click worked
            retry_count: Current retry attempt number

        Returns:
            ClickResult with success status and details
        """
        if retry_count >= self.max_retries:
            return ClickResult(
                success=False,
                retry_count=retry_count,
                error_message=f"Max retries ({self.max_retries}) exceeded"
            )

        # Find the button
        detection = self.find_button(button_name, method)

        if not detection.found:
            log.warning(f"Cannot click '{button_name}': button not found")
            return ClickResult(
                success=False,
                error_message=f"Button '{button_name}' not found"
            )

        # Click the button
        click_success = self.click_executor.click_at_point(
            detection.location,
            focus_window=True
        )

        if not click_success:
            log.error(f"Click on '{button_name}' failed")
            return ClickResult(
                success=False,
                click_location=detection.location,
                error_message="Click execution failed"
            )

        result = ClickResult(
            success=True,
            click_location=detection.location,
            retry_count=retry_count
        )

        # Verify the click if requested
        if verify:
            time.sleep(self.verification_delay)
            verification = self._verify_click(button_name, detection)
            result.verification_passed = verification

            if not verification and retry_count < self.max_retries:
                log.warning(f"Click verification failed, retrying ({retry_count + 1}/{self.max_retries})")
                return self.find_and_click_button(
                    button_name, method, verify, retry_count + 1
                )

        log.info(f"Successfully clicked '{button_name}' at {detection.location}")
        return result

    def _verify_click(self, button_name: str, original_detection: DetectionResult) -> bool:
        """
        Verify that a click had the expected effect.

        For poker buttons, we verify by checking if the button is no longer visible
        (since clicking Fold/Call/Raise should dismiss the action buttons).
        """
        # Take a new screenshot
        new_screenshot = self.take_screenshot(force_new=True)

        # Try to find the button again
        new_detection = self.find_button(button_name, screenshot=new_screenshot)

        # If button is no longer found, click likely worked
        if not new_detection.found:
            log.debug(f"Verification: '{button_name}' no longer visible (good)")
            return True

        # If button is still found at same location, it might not have worked
        if new_detection.location and original_detection.location:
            orig_loc = original_detection.location.as_pixels
            new_loc = new_detection.location.as_pixels

            # Allow small movement (within 10 pixels)
            if abs(orig_loc[0] - new_loc[0]) < 10 and abs(orig_loc[1] - new_loc[1]) < 10:
                log.warning(f"Verification: '{button_name}' still at same location")
                return False

        return True

    # ========================================================================
    # CONVENIENCE METHODS FOR COMMON ACTIONS
    # ========================================================================

    def fold(self, verify: bool = True) -> ClickResult:
        """Click the Fold button."""
        return self.find_and_click_button('fold', verify=verify)

    def call(self, verify: bool = True) -> ClickResult:
        """Click the Call button."""
        return self.find_and_click_button('call', verify=verify)

    def check(self, verify: bool = True) -> ClickResult:
        """Click the Check button."""
        return self.find_and_click_button('check', verify=verify)

    def raise_bet(self, verify: bool = True) -> ClickResult:
        """Click the Raise/Bet button."""
        result = self.find_and_click_button('raise', verify=verify)
        if not result.success:
            result = self.find_and_click_button('bet', verify=verify)
        return result

    def take_action(self, action: str, verify: bool = True) -> ClickResult:
        """
        Execute a poker action by name.

        Args:
            action: Action name (Fold, Call, Check, Raise, Bet, etc.)
            verify: Whether to verify the click

        Returns:
            ClickResult
        """
        action_map = {
            'fold': self.fold,
            'call': self.call,
            'call2': self.call,
            'check': self.check,
            'raise': self.raise_bet,
            'bet': self.raise_bet,
            'bet bluff': self.raise_bet,
            'bet half pot': self.raise_bet,
            'bet pot': self.raise_bet,
            'bet max': self.raise_bet,
            'betplus': self.raise_bet,
        }

        action_lower = action.lower()

        if action_lower in action_map:
            return action_map[action_lower](verify=verify)

        # Try to find and click the button by name directly
        log.warning(f"Unknown action '{action}', attempting direct button search")
        return self.find_and_click_button(action_lower, verify=verify)

    # ========================================================================
    # DEBUGGING METHODS
    # ========================================================================

    def save_debug_screenshot(self, filename: str = 'debug_screenshot.png'):
        """Save current screenshot with detected elements marked."""
        screenshot = self.take_screenshot(force_new=True)

        # Find all buttons and mark them
        buttons_to_find = ['fold', 'call', 'check', 'raise', 'bet']
        marked_screenshot = screenshot.copy()

        for button_name in buttons_to_find:
            result = self.find_button(button_name, screenshot=screenshot)
            if result.found and result.bounding_box:
                bb = result.bounding_box
                color = (0, 255, 0) if result.confidence > 0.8 else (0, 255, 255)
                cv2.rectangle(
                    marked_screenshot,
                    (bb.x_px, bb.y_px),
                    (bb.x_px + bb.width_px, bb.y_px + bb.height_px),
                    color, 2
                )
                if result.location:
                    cv2.circle(marked_screenshot, result.location.as_pixels, 5, (0, 0, 255), -1)
                cv2.putText(
                    marked_screenshot, button_name,
                    (bb.x_px, bb.y_px - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
                )

        # Save
        cv2.imwrite(filename, marked_screenshot)
        log.info(f"Debug screenshot saved to {filename}")

        return filename

    def print_status(self):
        """Print current detection status for debugging."""
        print("\n" + "="*60)
        print("SmartUIAutomation Status")
        print("="*60)

        # Window info
        windows = self.window_finder.find_ggpoker_windows()
        print(f"\nGGPoker Windows: {len(windows)}")
        for w in windows:
            print(f"  - {w['name']}")
            print(f"    Position: ({w['x_pt']}, {w['y_pt']}) POINTS")
            print(f"    Size: {w['width_pt']}x{w['height_pt']} POINTS")

        # Current screenshot info
        screenshot = self.take_screenshot(force_new=True)
        print(f"\nScreenshot Size: {screenshot.shape[1]}x{screenshot.shape[0]} PIXELS")
        print(f"Retina Scale: {DisplayConfig.RETINA_SCALE}x")

        # Button detection
        print("\nButton Detection:")
        for button_name in ['fold', 'call', 'check', 'raise', 'bet']:
            result = self.find_button(button_name, screenshot=screenshot)
            status = "FOUND" if result.found else "NOT FOUND"
            location = f"at {result.location}" if result.location else ""
            confidence = f"(confidence: {result.confidence:.2f})" if result.found else ""
            print(f"  {button_name:8s}: {status} {location} {confidence}")

        print("\n" + "="*60)


# ============================================================================
# STANDALONE TEST / DEMO
# ============================================================================

if __name__ == '__main__':
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )

    print("SmartUIAutomation - Test Mode")
    print("-" * 40)

    # Initialize
    ui = SmartUIAutomation()

    # Print status
    ui.print_status()

    # Save debug screenshot
    debug_file = ui.save_debug_screenshot('/tmp/smart_ui_debug.png')
    print(f"\nDebug screenshot saved: {debug_file}")

    # Test button detection
    print("\nTesting button detection...")
    for button in ['fold', 'call', 'raise']:
        result = ui.find_button(button)
        if result.found:
            print(f"  {button}: Found at {result.location} (confidence: {result.confidence:.2f})")
        else:
            print(f"  {button}: Not found")

    print("\nTo test clicking, uncomment the lines below:")
    # result = ui.fold()
    # print(f"Fold result: {result}")
