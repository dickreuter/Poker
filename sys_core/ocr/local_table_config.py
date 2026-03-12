"""
Local table configuration that replaces MongoDB dependency.

Loads card templates from disk and uses percentage-based regions
that scale to the actual table window size.

This eliminates the need for dickreuter.com:7778 MongoDB server.
"""

import io
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from PIL import Image

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
TEMPLATE_DIR = PROJECT_ROOT / 'poker_ocr' / 'assets' / 'card_templates'

# All 52 cards in the format used by the original bot
RANKS = ['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']
SUITS = ['H', 'D', 'C', 'S']

# Percentage-based regions for GGSystem Rush & Cash / Spin & Gold tables.
# These are relative to the table image (0.0 - 1.0).
#
# MEASURED from actual GGSystem screenshot (1700x1228px / 850x614pt):
#   Both cards:  x=43.4%-56.8%, y=73.0%-86.6%
#   Left card:   x=43.4%-50.7%, y=73.0%-86.6%
#   Right card:  x=50.7%-56.8%, y=73.0%-86.6%
#   Fold button: x=61.1%-73.3%, y=88.2%-98.0%
#   Call button: x=73.9%-86.1%, y=88.2%-98.0%
#   Raise btn:   x=86.6%-98.9%, y=88.2%-98.0%
#   Pot label:   x=30.2%, y=41.6%
REGIONS_PCT = {
    # Player hole cards (bottom center of table)
    # Search area: covers both cards with generous margin
    'my_cards_area': {'x1': 0.38, 'y1': 0.70, 'x2': 0.62, 'y2': 0.92},
    # Individual card positions (measured + margin for window size variance)
    'left_card_area': {'x1': 0.40, 'y1': 0.71, 'x2': 0.52, 'y2': 0.90},
    'right_card_area': {'x1': 0.48, 'y1': 0.71, 'x2': 0.60, 'y2': 0.90},

    # Community cards (board, center of table)
    'table_cards_area': {'x1': 0.20, 'y1': 0.35, 'x2': 0.80, 'y2': 0.55},

    # Pot/value OCR regions (measured: pot label at ~30% X, ~42% Y)
    'total_pot_area': {'x1': 0.28, 'y1': 0.38, 'x2': 0.72, 'y2': 0.48},
    'current_round_pot': {'x1': 0.28, 'y1': 0.38, 'x2': 0.72, 'y2': 0.48},
    'call_value': {'x1': 0.70, 'y1': 0.88, 'x2': 0.90, 'y2': 0.98},
    'raise_value': {'x1': 0.84, 'y1': 0.88, 'x2': 1.00, 'y2': 0.98},

    # Button search areas (buttons are in bottom-right, y=88-98%)
    'buttons_search_area': {'x1': 0.55, 'y1': 0.85, 'x2': 1.00, 'y2': 1.00},
    'my_turn_search_area': {'x1': 0.55, 'y1': 0.85, 'x2': 1.00, 'y2': 1.00},

    # Mouse click areas (fallback — SmartMouseAction uses color detection first)
    # Measured: Fold=61-73%, Call=74-86%, Raise=87-99% X, all at y=88-98%
    'mouse_fold': {'x1': 0.61, 'y1': 0.88, 'x2': 0.73, 'y2': 0.98},
    'mouse_call': {'x1': 0.74, 'y1': 0.88, 'x2': 0.86, 'y2': 0.98},
    'mouse_call2': {'x1': 0.74, 'y1': 0.88, 'x2': 0.86, 'y2': 0.98},
    'mouse_check': {'x1': 0.74, 'y1': 0.88, 'x2': 0.86, 'y2': 0.98},
    'mouse_raise': {'x1': 0.87, 'y1': 0.88, 'x2': 0.99, 'y2': 0.98},
    'mouse_increase': {'x1': 0.90, 'y1': 0.84, 'x2': 0.96, 'y2': 0.86},
    'mouse_half_pot': {'x1': 0.61, 'y1': 0.82, 'x2': 0.65, 'y2': 0.88},
    'mouse_3bb': {'x1': 0.66, 'y1': 0.82, 'x2': 0.70, 'y2': 0.88},
    'mouse_4bb': {'x1': 0.71, 'y1': 0.82, 'x2': 0.75, 'y2': 0.88},
    'mouse_full_pot': {'x1': 0.76, 'y1': 0.82, 'x2': 0.80, 'y2': 0.88},
    'mouse_all_in': {'x1': 0.66, 'y1': 0.82, 'x2': 0.72, 'y2': 0.88},
    'mouse_imback': {'x1': 0.40, 'y1': 0.50, 'x2': 0.60, 'y2': 0.60},
    'mouse_resume_hand': {'x1': 0.40, 'y1': 0.50, 'x2': 0.60, 'y2': 0.60},

    # Player fund/bet areas (6 players, indexed 0-5)
    # Measured from screenshot: hero stack at ~37-44% X, ~68-70% Y
    'player_funds_area': {
        '0': {'x1': 0.35, 'y1': 0.68, 'x2': 0.50, 'y2': 0.72},
        '1': {'x1': 0.03, 'y1': 0.53, 'x2': 0.18, 'y2': 0.58},
        '2': {'x1': 0.03, 'y1': 0.18, 'x2': 0.18, 'y2': 0.23},
        '3': {'x1': 0.35, 'y1': 0.05, 'x2': 0.50, 'y2': 0.10},
        '4': {'x1': 0.82, 'y1': 0.18, 'x2': 0.97, 'y2': 0.23},
        '5': {'x1': 0.82, 'y1': 0.53, 'x2': 0.97, 'y2': 0.58},
    },
    'player_pot_area': {
        '0': {'x1': 0.35, 'y1': 0.48, 'x2': 0.50, 'y2': 0.52},
        '1': {'x1': 0.15, 'y1': 0.43, 'x2': 0.30, 'y2': 0.48},
        '2': {'x1': 0.15, 'y1': 0.28, 'x2': 0.30, 'y2': 0.33},
        '3': {'x1': 0.35, 'y1': 0.18, 'x2': 0.50, 'y2': 0.23},
        '4': {'x1': 0.70, 'y1': 0.28, 'x2': 0.85, 'y2': 0.33},
        '5': {'x1': 0.70, 'y1': 0.43, 'x2': 0.85, 'y2': 0.48},
    },
}


def _pil_to_binary(img: Image.Image) -> bytes:
    """Convert PIL image to binary PNG bytes (same format as MongoDB)."""
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _create_dummy_template(width: int = 29, height: int = 43) -> bytes:
    """Create a small dummy template image for button/UI templates we don't have."""
    img = Image.new('RGB', (width, height), (128, 128, 128))
    return _pil_to_binary(img)


def _scale_region(region_pct: dict, width: int, height: int) -> dict:
    """Convert percentage-based region to pixel coordinates."""
    return {
        'x1': int(region_pct['x1'] * width),
        'y1': int(region_pct['y1'] * height),
        'x2': int(region_pct['x2'] * width),
        'y2': int(region_pct['y2'] * height),
    }


def _scale_player_regions(regions_pct: dict, width: int, height: int) -> dict:
    """Convert percentage-based player regions to pixel coordinates."""
    return {k: _scale_region(v, width, height) for k, v in regions_pct.items()}


_template_cache: Dict[str, Dict[str, bytes]] = {}


def load_card_templates(template_dir: Optional[Path] = None) -> Dict[str, bytes]:
    """Load all 52 card templates from disk as binary PNG data.

    Returns dict keyed by lowercase card name (e.g. 'ah', 'ks', '10d').
    Results are cached so repeated calls don't re-read from disk.
    """
    if template_dir is None:
        template_dir = TEMPLATE_DIR

    cache_key = str(template_dir)
    if cache_key in _template_cache:
        return _template_cache[cache_key]

    templates = {}
    loaded = 0

    for rank in RANKS:
        for suit in SUITS:
            card_name = f"{rank}{suit}"
            card_key = card_name.lower()
            png_path = template_dir / f"{card_name}.png"

            if png_path.exists():
                templates[card_key] = png_path.read_bytes()
                loaded += 1
            else:
                log.debug(f"Template not found: {png_path}")

    log.info(f"Loaded {loaded}/52 card templates from {template_dir}")
    _template_cache[cache_key] = templates
    return templates


def build_local_table_dict(
    table_width_px: int = 1600,
    table_height_px: int = 1200,
    template_dir: Optional[Path] = None,
) -> dict:
    """Build a table_dict that works without MongoDB.

    This creates the same structure that MongoManager.get_table() returns,
    but using local card templates and percentage-based coordinates.

    Args:
        table_width_px: Table width in PIXELS (800pt * 2 for Retina = 1600)
        table_height_px: Table height in PIXELS (600pt * 2 for Retina = 1200)
        template_dir: Path to card template PNGs (default: poker_ocr/assets/card_templates/)

    Returns:
        dict compatible with TableScraper(table_dict)
    """
    table_dict = {}

    # Load card templates from disk
    templates = load_card_templates(template_dir)
    table_dict.update(templates)

    # Scale percentage-based regions to actual pixel size
    w, h = table_width_px, table_height_px

    for key, region in REGIONS_PCT.items():
        if key in ('player_funds_area', 'player_pot_area'):
            table_dict[key] = _scale_player_regions(region, w, h)
        else:
            table_dict[key] = _scale_region(region, w, h)

    # Dummy templates for UI elements (button detection uses color fallback anyway)
    dummy = _create_dummy_template()
    for tpl_key in ['topleft_corner', 'call_button', 'raise_button', 'check_button',
                     'bet_button', 'my_turn', 'im_back', 'resume_hand',
                     'fast_fold_button', 'lost_everything', 'all_in_call_button',
                     'covered_card']:
        table_dict[tpl_key] = dummy

    # Config
    table_dict['max_players'] = {'value': 6}

    log.info(f"Built local table dict: {len(templates)} card templates, "
             f"table size {w}x{h}px")

    return table_dict
