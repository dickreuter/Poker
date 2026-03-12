"""
GGSystem Template Capture and Management System

Comprehensive system for capturing, storing, and managing UI element templates
for GGSystem automation. Captures templates from live GGSystem windows and stores
them with metadata for reliable matching.

Usage:
    from sys_core.tools.templates.template_manager import TemplateManager

    manager = TemplateManager()
    manager.capture_from_screen()  # Interactive capture
    manager.save_all()             # Save templates and manifest
"""

import os
import json
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from PIL import Image, ImageGrab
import cv2
import numpy as np

log = logging.getLogger(__name__)

# Directory for template storage
TEMPLATE_DIR = os.path.dirname(os.path.abspath(__file__))

# Retina display scaling
RETINA_SCALE = 2


@dataclass
class TemplateMetadata:
    """Metadata for a single template."""
    name: str
    filename: str
    description: str
    category: str  # 'button', 'tile', 'dialog', 'action'
    width: int
    height: int
    capture_date: str
    window_context: str  # e.g., 'lobby', 'table', 'dialog'
    color_signature: Optional[Dict] = None  # HSV color hints for matching
    match_threshold: float = 0.05  # Recommended matching threshold


@dataclass
class TemplateDefinition:
    """Definition of a template to capture."""
    name: str
    description: str
    category: str
    window_context: str
    color_hints: Optional[Dict] = None
    expected_location: Optional[str] = None  # e.g., 'bottom-center', 'top-right'


# Pre-defined templates to capture
TEMPLATE_DEFINITIONS = [
    TemplateDefinition(
        name="play_now_dark",
        description="Play Now button (dark with white text)",
        category="button",
        window_context="lobby",
        color_hints={"type": "dark_button", "text": "white"},
        expected_location="bottom-center"
    ),
    TemplateDefinition(
        name="play_now_insurance",
        description="Play Now with insurance button (colored/yellow)",
        category="button",
        window_context="lobby",
        color_hints={"type": "colored_button", "text": "dark"},
        expected_location="bottom-center"
    ),
    TemplateDefinition(
        name="tile_1_dollar",
        description="$1 Spin & Gold tile",
        category="tile",
        window_context="lobby",
        expected_location="grid"
    ),
    TemplateDefinition(
        name="tile_25_cents",
        description="$0.25 Spin & Gold tile",
        category="tile",
        window_context="lobby",
        expected_location="grid"
    ),
    TemplateDefinition(
        name="btn_fold",
        description="Fold button (during gameplay)",
        category="action",
        window_context="table",
        color_hints={"hsv_lower": [0, 0, 40], "hsv_upper": [180, 50, 120]},
        expected_location="bottom-right"
    ),
    TemplateDefinition(
        name="btn_call",
        description="Call button (during gameplay)",
        category="action",
        window_context="table",
        color_hints={"hsv_lower": [35, 50, 50], "hsv_upper": [85, 255, 255]},
        expected_location="bottom-right"
    ),
    TemplateDefinition(
        name="btn_raise",
        description="Raise button (during gameplay)",
        category="action",
        window_context="table",
        color_hints={"hsv_lower": [10, 80, 80], "hsv_upper": [25, 255, 255]},
        expected_location="bottom-right"
    ),
    TemplateDefinition(
        name="btn_close_x",
        description="Close/X button for dialogs",
        category="dialog",
        window_context="dialog",
        color_hints={"type": "x_button"},
        expected_location="top-right"
    ),
]


class TemplateManager:
    """
    Manages capture, storage, and retrieval of UI templates.
    """

    def __init__(self, template_dir: str = TEMPLATE_DIR):
        self.template_dir = template_dir
        self.templates: Dict[str, TemplateMetadata] = {}
        self.manifest_path = os.path.join(template_dir, "manifest.json")

        # Ensure directory exists
        os.makedirs(template_dir, exist_ok=True)

        # Load existing manifest if available
        self.load_manifest()

    def load_manifest(self) -> bool:
        """Load template manifest from disk."""
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, 'r') as f:
                    data = json.load(f)
                    for name, meta_dict in data.get('templates', {}).items():
                        self.templates[name] = TemplateMetadata(**meta_dict)
                log.info(f"Loaded {len(self.templates)} templates from manifest")
                return True
            except Exception as e:
                log.error(f"Failed to load manifest: {e}")
        return False

    def save_manifest(self) -> bool:
        """Save template manifest to disk."""
        try:
            manifest = {
                "version": "1.0",
                "created": datetime.now().isoformat(),
                "templates": {name: asdict(meta) for name, meta in self.templates.items()}
            }
            with open(self.manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
            log.info(f"Saved manifest with {len(self.templates)} templates")
            return True
        except Exception as e:
            log.error(f"Failed to save manifest: {e}")
            return False

    def get_ggpoker_window(self) -> Optional[Dict]:
        """
        Get GGSystem window position using AppleScript.
        Returns dict with x, y, width, height in both POINTS and PIXELS.
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
                    return winName & "###" & (item 1 of winPos as text) & "," & (item 2 of winPos as text) & "," & (item 1 of winSize as text) & "," & (item 2 of winSize as text)
                end repeat
            end tell
        end tell
        '''

        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=5
            )

            if result.stdout.strip() and '###' in result.stdout:
                name, coords = result.stdout.strip().split('###')
                # Fix Unicode minus sign (−) that macOS returns instead of ASCII minus (-)
                coords = coords.replace('−', '-').replace('–', '-')
                parts = coords.split(',')
                x_pt, y_pt, w_pt, h_pt = map(int, parts)

                return {
                    'name': name.strip(),
                    'x_pt': x_pt,
                    'y_pt': y_pt,
                    'w_pt': w_pt,
                    'h_pt': h_pt,
                    'x_px': x_pt * RETINA_SCALE,
                    'y_px': y_pt * RETINA_SCALE,
                    'w_px': w_pt * RETINA_SCALE,
                    'h_px': h_pt * RETINA_SCALE
                }
        except Exception as e:
            log.error(f"Failed to get GGSystem window: {e}")

        return None

    def capture_full_window(self, window: Optional[Dict] = None) -> Optional[Image.Image]:
        """Capture the GGSystem window from screen."""
        if window is None:
            window = self.get_ggpoker_window()

        if window is None:
            log.error("GGSystem window not found")
            return None

        screenshot = ImageGrab.grab()

        # Crop to window bounds (using pixel coordinates)
        cropped = screenshot.crop((
            window['x_px'],
            window['y_px'],
            window['x_px'] + window['w_px'],
            window['y_px'] + window['h_px']
        ))

        return cropped

    def capture_region(self,
                       x1_px: int, y1_px: int,
                       x2_px: int, y2_px: int,
                       window: Optional[Dict] = None) -> Optional[Image.Image]:
        """
        Capture a specific region from the GGSystem window.
        Coordinates are in pixels, relative to window top-left.
        """
        window_img = self.capture_full_window(window)
        if window_img is None:
            return None

        return window_img.crop((x1_px, y1_px, x2_px, y2_px))

    def save_template(self,
                      name: str,
                      image: Image.Image,
                      definition: TemplateDefinition,
                      color_signature: Optional[Dict] = None) -> bool:
        """Save a captured template to disk."""
        filename = f"{name}.png"
        filepath = os.path.join(self.template_dir, filename)

        try:
            image.save(filepath, 'PNG')

            metadata = TemplateMetadata(
                name=name,
                filename=filename,
                description=definition.description,
                category=definition.category,
                width=image.width,
                height=image.height,
                capture_date=datetime.now().isoformat(),
                window_context=definition.window_context,
                color_signature=color_signature or definition.color_hints,
                match_threshold=0.05
            )

            self.templates[name] = metadata
            log.info(f"Saved template '{name}' ({image.width}x{image.height}) to {filepath}")
            return True

        except Exception as e:
            log.error(f"Failed to save template '{name}': {e}")
            return False

    def load_template(self, name: str) -> Optional[Image.Image]:
        """Load a template image from disk."""
        if name not in self.templates:
            log.warning(f"Template '{name}' not in manifest")
            return None

        filepath = os.path.join(self.template_dir, self.templates[name].filename)

        if os.path.exists(filepath):
            return Image.open(filepath)

        log.warning(f"Template file not found: {filepath}")
        return None

    def load_template_cv2(self, name: str) -> Optional[np.ndarray]:
        """Load a template as OpenCV image (BGR)."""
        img = self.load_template(name)
        if img is not None:
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        return None

    def find_template_on_screen(self,
                                name: str,
                                screenshot: Optional[Image.Image] = None,
                                threshold: Optional[float] = None) -> Optional[Tuple[int, int, float]]:
        """
        Find a template on screen using template matching.

        Returns:
            (x, y, score) of best match, or None if not found.
            x, y are in PIXELS (screenshot coordinates).
        """
        template = self.load_template_cv2(name)
        if template is None:
            return None

        if screenshot is None:
            screenshot = ImageGrab.grab()

        screen_cv2 = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

        # Use metadata threshold if not specified
        if threshold is None and name in self.templates:
            threshold = self.templates[name].match_threshold
        threshold = threshold or 0.05

        result = cv2.matchTemplate(screen_cv2, template, cv2.TM_SQDIFF_NORMED)
        min_val, _, min_loc, _ = cv2.minMaxLoc(result)

        if min_val <= threshold:
            return (min_loc[0], min_loc[1], min_val)

        return None

    def get_template_info(self, name: str) -> Optional[TemplateMetadata]:
        """Get metadata for a template."""
        return self.templates.get(name)

    def list_templates(self, category: Optional[str] = None) -> List[str]:
        """List all templates, optionally filtered by category."""
        if category:
            return [name for name, meta in self.templates.items()
                    if meta.category == category]
        return list(self.templates.keys())

    def calculate_color_signature(self, image: Image.Image) -> Dict:
        """
        Calculate HSV color signature for an image.
        Useful for color-based matching as backup.
        """
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Calculate dominant color ranges
        h_mean = int(np.mean(hsv[:, :, 0]))
        s_mean = int(np.mean(hsv[:, :, 1]))
        v_mean = int(np.mean(hsv[:, :, 2]))

        h_std = int(np.std(hsv[:, :, 0]))
        s_std = int(np.std(hsv[:, :, 1]))
        v_std = int(np.std(hsv[:, :, 2]))

        return {
            "hsv_mean": [h_mean, s_mean, v_mean],
            "hsv_std": [h_std, s_std, v_std],
            "hsv_lower": [max(0, h_mean - h_std), max(0, s_mean - s_std), max(0, v_mean - v_std)],
            "hsv_upper": [min(180, h_mean + h_std), min(255, s_mean + s_std), min(255, v_mean + v_std)]
        }


class InteractiveCapture:
    """
    Interactive template capture from GGSystem screen.
    Guides user through capturing each template.
    """

    def __init__(self, manager: Optional[TemplateManager] = None):
        self.manager = manager or TemplateManager()
        self.window = None
        self.full_screenshot = None

    def start(self):
        """Start interactive capture session."""
        print("\n" + "="*60)
        print("GGSystem Template Capture System")
        print("="*60)

        # Find GGSystem window
        self.window = self.manager.get_ggpoker_window()
        if not self.window:
            print("\nERROR: GGSystem not found!")
            print("Please open GGSystem and make sure the Spin & Gold lobby is visible.")
            return False

        print(f"\nFound GGSystem window: {self.window['name']}")
        print(f"Position: ({self.window['x_pt']}, {self.window['y_pt']}) POINTS")
        print(f"Size: {self.window['w_pt']}x{self.window['h_pt']} POINTS")
        print(f"In pixels: ({self.window['x_px']}, {self.window['y_px']}) {self.window['w_px']}x{self.window['h_px']}")

        # Take initial screenshot
        self.full_screenshot = ImageGrab.grab()

        return True

    def capture_region_interactive(self,
                                   definition: TemplateDefinition,
                                   region_px: Tuple[int, int, int, int]) -> bool:
        """
        Capture a specific region for a template definition.
        region_px: (x1, y1, x2, y2) in pixels relative to window.
        """
        print(f"\nCapturing: {definition.description}")
        print(f"Region: {region_px}")

        x1, y1, x2, y2 = region_px

        # Crop from window
        window_img = self.manager.capture_full_window(self.window)
        if window_img is None:
            print("ERROR: Failed to capture window")
            return False

        template_img = window_img.crop((x1, y1, x2, y2))

        # Calculate color signature
        color_sig = self.manager.calculate_color_signature(template_img)

        # Save template
        success = self.manager.save_template(
            definition.name,
            template_img,
            definition,
            color_sig
        )

        if success:
            print(f"Saved: {definition.name}.png ({template_img.width}x{template_img.height})")

        return success

    def capture_at_coords(self,
                          name: str,
                          x1_px: int, y1_px: int,
                          x2_px: int, y2_px: int,
                          description: str = "",
                          category: str = "button",
                          window_context: str = "lobby") -> bool:
        """
        Capture a template at specific pixel coordinates.
        Coordinates are relative to the GGSystem window.
        """
        definition = TemplateDefinition(
            name=name,
            description=description or name,
            category=category,
            window_context=window_context
        )

        return self.capture_region_interactive(definition, (x1_px, y1_px, x2_px, y2_px))


def capture_lobby_templates():
    """
    Capture all lobby templates from current GGSystem Spin & Gold screen.

    Expected window position: (62, 127) POINTS = (124, 254) PIXELS
    Window size: 1200x720 POINTS = 2400x1440 PIXELS
    """
    manager = TemplateManager()
    capture = InteractiveCapture(manager)

    if not capture.start():
        return False

    print("\n" + "-"*60)
    print("Capturing Lobby Templates")
    print("-"*60)

    # Get window dimensions for reference
    w_px = capture.window['w_px']
    h_px = capture.window['h_px']

    captured = []

    # 1. Play Now button (dark) - typically at bottom center
    # Approximate location based on typical GGSystem layout
    print("\n1. Looking for 'Play Now' button (dark)...")
    # Search in bottom 25% of window, center area
    play_now_region = detect_dark_button(capture.full_screenshot, capture.window)
    if play_now_region:
        capture.capture_at_coords(
            "play_now_dark",
            *play_now_region,
            description="Play Now button (dark with white text)",
            category="button",
            window_context="lobby"
        )
        captured.append("play_now_dark")

    # 2. Play Now with Insurance button (colored/yellow)
    print("\n2. Looking for 'Play Now with Insurance' button...")
    insurance_region = detect_colored_button(capture.full_screenshot, capture.window, "yellow")
    if insurance_region:
        capture.capture_at_coords(
            "play_now_insurance",
            *insurance_region,
            description="Play Now with insurance button (colored)",
            category="button",
            window_context="lobby"
        )
        captured.append("play_now_insurance")

    # 3. $1 tile
    print("\n3. Looking for $1 tile...")
    dollar_tile = detect_stake_tile(capture.full_screenshot, capture.window, "$1")
    if dollar_tile:
        capture.capture_at_coords(
            "tile_1_dollar",
            *dollar_tile,
            description="$1 Spin & Gold tile",
            category="tile",
            window_context="lobby"
        )
        captured.append("tile_1_dollar")

    # 4. $0.25 tile
    print("\n4. Looking for $0.25 tile...")
    quarter_tile = detect_stake_tile(capture.full_screenshot, capture.window, "$0.25")
    if quarter_tile:
        capture.capture_at_coords(
            "tile_25_cents",
            *quarter_tile,
            description="$0.25 Spin & Gold tile",
            category="tile",
            window_context="lobby"
        )
        captured.append("tile_25_cents")

    # Save manifest
    manager.save_manifest()

    print("\n" + "="*60)
    print(f"Capture Complete: {len(captured)} templates saved")
    print(f"Templates: {', '.join(captured)}")
    print(f"Location: {TEMPLATE_DIR}")
    print("="*60)

    return captured


def detect_dark_button(screenshot: Image.Image, window: Dict) -> Optional[Tuple[int, int, int, int]]:
    """
    Detect dark button with white text in the window.
    Returns (x1, y1, x2, y2) in pixels relative to window.
    """
    # Crop to window area
    x, y = window['x_px'], window['y_px']
    w, h = window['w_px'], window['h_px']

    window_img = screenshot.crop((x, y, x + w, y + h))
    img = cv2.cvtColor(np.array(window_img), cv2.COLOR_RGB2BGR)

    # Look in bottom 30% of window
    search_area = img[int(h * 0.70):, :]

    # Convert to grayscale
    gray = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)

    # Find dark regions (button background)
    # Dark buttons have value 40-80 in grayscale
    _, dark_mask = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)

    # Morphological operations to clean up
    kernel = np.ones((5, 5), np.uint8)
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_CLOSE, kernel)

    # Find contours
    contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for contour in contours:
        cx, cy, cw, ch = cv2.boundingRect(contour)
        area = cw * ch

        # Button-like proportions: wider than tall, minimum size
        if cw > 100 and ch > 30 and ch < 100 and cw / ch > 1.5 and area > 5000:
            # Convert back to full window coordinates
            y_offset = int(h * 0.70)
            return (cx, y_offset + cy, cx + cw, y_offset + cy + ch)

    return None


def detect_colored_button(screenshot: Image.Image, window: Dict, color: str = "yellow") -> Optional[Tuple[int, int, int, int]]:
    """
    Detect colored button (yellow/green) in the window.
    Returns (x1, y1, x2, y2) in pixels relative to window.
    """
    x, y = window['x_px'], window['y_px']
    w, h = window['w_px'], window['h_px']

    window_img = screenshot.crop((x, y, x + w, y + h))
    img = cv2.cvtColor(np.array(window_img), cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Search in bottom 30%
    search_area = hsv[int(h * 0.70):, :]

    # Color ranges
    if color == "yellow":
        lower = np.array([20, 100, 100])
        upper = np.array([35, 255, 255])
    elif color == "green":
        lower = np.array([35, 80, 80])
        upper = np.array([85, 255, 255])
    else:
        return None

    mask = cv2.inRange(search_area, lower, upper)

    # Clean up
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for contour in contours:
        cx, cy, cw, ch = cv2.boundingRect(contour)
        area = cw * ch

        if cw > 100 and ch > 30 and ch < 100 and cw / ch > 1.5 and area > 5000:
            y_offset = int(h * 0.70)
            return (cx, y_offset + cy, cx + cw, y_offset + cy + ch)

    return None


def detect_stake_tile(screenshot: Image.Image, window: Dict, stake: str) -> Optional[Tuple[int, int, int, int]]:
    """
    Detect a stake tile by looking for text and tile pattern.
    Returns (x1, y1, x2, y2) in pixels relative to window.

    Note: This is a simplified detection. Real implementation should use OCR
    or template matching against known tiles.
    """
    x, y = window['x_px'], window['y_px']
    w, h = window['w_px'], window['h_px']

    window_img = screenshot.crop((x, y, x + w, y + h))

    # Tiles are typically in the center area (30-70% height, 20-80% width)
    # Return approximate regions based on typical Spin & Gold layout

    tile_height = 200  # Approximate tile height in pixels
    tile_width = 280   # Approximate tile width in pixels

    if stake == "$1":
        # $1 tile is typically in the middle-left area
        cx = int(w * 0.35)
        cy = int(h * 0.45)
        return (cx - tile_width//2, cy - tile_height//2,
                cx + tile_width//2, cy + tile_height//2)
    elif stake == "$0.25":
        # $0.25 tile is typically to the left
        cx = int(w * 0.20)
        cy = int(h * 0.45)
        return (cx - tile_width//2, cy - tile_height//2,
                cx + tile_width//2, cy + tile_height//2)

    return None


def capture_table_action_buttons():
    """
    Capture action buttons from an active poker table.
    Requires a table to be open with Fold/Call/Raise buttons visible.
    """
    manager = TemplateManager()
    capture = InteractiveCapture(manager)

    if not capture.start():
        return False

    print("\n" + "-"*60)
    print("Capturing Table Action Buttons")
    print("-"*60)
    print("\nMake sure a poker table is open with action buttons visible!")

    w_px = capture.window['w_px']
    h_px = capture.window['h_px']

    # Crop window image
    window_img = capture.manager.capture_full_window(capture.window)
    if window_img is None:
        print("ERROR: Could not capture window")
        return []

    img = cv2.cvtColor(np.array(window_img), cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    captured = []

    # Search in bottom-right area where action buttons are
    y_start = int(h_px * 0.70)
    x_start = int(w_px * 0.40)
    search_hsv = hsv[y_start:, x_start:]

    # 5. Fold button (gray/dark)
    print("\n5. Looking for Fold button...")
    # Fold in GGSystem is typically dark gray
    gray_lower = np.array([0, 0, 40])
    gray_upper = np.array([180, 50, 120])
    fold_mask = cv2.inRange(search_hsv, gray_lower, gray_upper)
    fold_btn = find_button_from_mask(fold_mask, x_start, y_start, "btn_fold")
    if fold_btn:
        capture.capture_at_coords(
            "btn_fold",
            *fold_btn,
            description="Fold button (during gameplay)",
            category="action",
            window_context="table"
        )
        captured.append("btn_fold")

    # 6. Call button (green)
    print("\n6. Looking for Call button...")
    green_lower = np.array([35, 50, 50])
    green_upper = np.array([85, 255, 255])
    call_mask = cv2.inRange(search_hsv, green_lower, green_upper)
    call_btn = find_button_from_mask(call_mask, x_start, y_start, "btn_call")
    if call_btn:
        capture.capture_at_coords(
            "btn_call",
            *call_btn,
            description="Call button (during gameplay)",
            category="action",
            window_context="table"
        )
        captured.append("btn_call")

    # 7. Raise button (orange/gold)
    print("\n7. Looking for Raise button...")
    orange_lower = np.array([10, 80, 80])
    orange_upper = np.array([25, 255, 255])
    raise_mask = cv2.inRange(search_hsv, orange_lower, orange_upper)
    raise_btn = find_button_from_mask(raise_mask, x_start, y_start, "btn_raise")
    if raise_btn:
        capture.capture_at_coords(
            "btn_raise",
            *raise_btn,
            description="Raise button (during gameplay)",
            category="action",
            window_context="table"
        )
        captured.append("btn_raise")

    # Save manifest
    manager.save_manifest()

    print("\n" + "="*60)
    print(f"Capture Complete: {len(captured)} action buttons saved")
    print(f"Templates: {', '.join(captured)}")
    print("="*60)

    return captured


def find_button_from_mask(mask: np.ndarray, x_offset: int, y_offset: int, name: str) -> Optional[Tuple[int, int, int, int]]:
    """Find button contour from color mask."""
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    best_area = 0

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h

        # Button proportions
        if w > 60 and h > 25 and h < 100 and w / h > 1.2 and area > 3000:
            if area > best_area:
                best = (x_offset + x, y_offset + y, x_offset + x + w, y_offset + y + h)
                best_area = area

    return best


def capture_close_button():
    """Capture close/X button from a dialog."""
    manager = TemplateManager()
    capture = InteractiveCapture(manager)

    if not capture.start():
        return False

    print("\n" + "-"*60)
    print("Capturing Close/X Button")
    print("-"*60)
    print("\nMake sure a dialog with X button is visible!")

    window_img = capture.manager.capture_full_window(capture.window)
    if window_img is None:
        print("ERROR: Could not capture window")
        return []

    img = cv2.cvtColor(np.array(window_img), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # X buttons are typically in top-right of dialogs
    # Search top 30%, right 40% of window
    search_area = gray[:int(h*0.30), int(w*0.60):]

    # Look for X pattern (bright on dark background)
    _, thresh = cv2.threshold(search_area, 150, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)

        # X button is roughly square, small
        if 20 < cw < 60 and 20 < ch < 60 and abs(cw - ch) < 15:
            # Add padding
            x1 = int(w * 0.60) + x - 5
            y1 = y - 5
            x2 = x1 + cw + 10
            y2 = y1 + ch + 10

            capture.capture_at_coords(
                "btn_close_x",
                x1, y1, x2, y2,
                description="Close/X button for dialogs",
                category="dialog",
                window_context="dialog"
            )

            manager.save_manifest()
            print("\nSaved btn_close_x")
            return ["btn_close_x"]

    print("X button not found")
    return []


def capture_all():
    """Capture all templates in one session."""
    print("\n" + "="*70)
    print(" GGSystem Template Capture - Full Session")
    print("="*70)

    all_captured = []

    # Lobby templates
    print("\n[STEP 1/3] Capturing lobby templates...")
    lobby = capture_lobby_templates()
    if lobby:
        all_captured.extend(lobby)

    # Action buttons (requires table to be open)
    print("\n[STEP 2/3] Capturing action buttons...")
    print("NOTE: If no poker table is open, action buttons will be skipped.")
    actions = capture_table_action_buttons()
    if actions:
        all_captured.extend(actions)

    # Close button
    print("\n[STEP 3/3] Capturing close button...")
    close = capture_close_button()
    if close:
        all_captured.extend(close)

    print("\n" + "="*70)
    print(" CAPTURE SESSION COMPLETE")
    print("="*70)
    print(f"\nTotal templates captured: {len(all_captured)}")
    print(f"Templates: {', '.join(all_captured)}")
    print(f"\nFiles saved to: {TEMPLATE_DIR}")
    print(f"Manifest: {os.path.join(TEMPLATE_DIR, 'manifest.json')}")

    return all_captured


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "lobby":
            capture_lobby_templates()
        elif cmd == "actions":
            capture_table_action_buttons()
        elif cmd == "close":
            capture_close_button()
        elif cmd == "all":
            capture_all()
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python template_manager.py [lobby|actions|close|all]")
    else:
        capture_all()
