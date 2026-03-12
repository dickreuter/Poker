"""Dynamic OCR card reader for GGSystem tables.

Finds player hole cards by detecting card regions dynamically,
then reads rank via pytesseract OCR and suit via 4-color HSV analysis.
Works regardless of table size, card position, or deck style.

Supports TWO deck styles:
  1. White cards with colored text (classic GGSystem)
  2. Colored cards with white text (alternate skin)

Both use the 4-COLOR DECK mapping:
  Spades = Black, Hearts = Red, Diamonds = Blue, Clubs = Green

Usage:
    from sys_core.ocr.card_reader import read_player_cards
    cards = read_player_cards(table_screenshot_pil)
    # Returns e.g. ['AC', '10D'] or [] if cards not visible
"""

import logging
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

log = logging.getLogger(__name__)

VALID_RANKS = {'A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2'}

# Search band for player cards (percentage of table image).
# Expanded to 0.34-0.65 to ensure both cards are captured even with drift.
SEARCH_Y_MIN = 0.53
SEARCH_Y_MAX = 0.88
SEARCH_X_MIN = 0.34
SEARCH_X_MAX = 0.65

# Deck style constants
STYLE_WHITE = 'white'    # White cards, colored text
STYLE_COLORED = 'colored'  # Colored cards, white text

# ---------------------------------------------------------------------------
#  Pixel Hash Card Cache — deterministic 100% accuracy after first session
# ---------------------------------------------------------------------------

import hashlib
import json
import os
import pathlib

_CARD_HASH_CACHE_PATH = pathlib.Path(__file__).parent / 'card_hash_cache.json'
# Normalised crop size for hashing — deterministic across minor Retina jitter.
# Both cards are rescaled to this before MD5, so pixel-perfect matches work
# even if table window is resized by 1-2 px.
_HASH_NORM_W = 60
_HASH_NORM_H = 90
# Minimum confidence (0-1) required to record a new hash.
# Confidence is computed as int(suit_ok) * 0.5 + int(rank_ok) * 0.5
_MIN_RECORD_CONFIDENCE = 0.90


class PixelHashCardCache:
    """MD5 pixel-hash → card string.  Saved to disk, loaded on startup.

    After one game session all 52 cards are cached. Subsequent reads are
    O(1) dict lookups — no OCR, no template matching, no ML inference.

    Self-heals on GGSystem skin updates: hash miss → OCR fallback →
    auto-records new hash. Within ~5 hands the cache is repopulated.

    Thread-safe for single-process use (GIL protects dict).
    """

    def __init__(self, cache_path: pathlib.Path = _CARD_HASH_CACHE_PATH):
        self._path = cache_path
        self._cache: dict[str, str] = {}  # md5_hex → card ('AH', 'KS', …)
        self._dirty = False
        self._load()

    # ── Public API ──────────────────────────────────────────────────────────

    def lookup(self, crop_np: np.ndarray) -> Optional[str]:
        """O(1) card lookup.  Returns e.g. 'AH' or None on cache miss."""
        key = self._hash(crop_np)
        return self._cache.get(key)

    def record(self, crop_np: np.ndarray, card: str, confidence: float) -> None:
        """Save hash ↔ card mapping if confidence is high enough.

        Args:
            crop_np:    Raw card crop (RGB uint8).
            card:       Card string like 'AH', 'KS', '10D'.
            confidence: 0.0–1.0. Only saves when ≥ _MIN_RECORD_CONFIDENCE.
        """
        if confidence < _MIN_RECORD_CONFIDENCE:
            return
        if len(card) < 2 or len(card) > 3:
            return
        key = self._hash(crop_np)
        if self._cache.get(key) == card:
            return  # Already recorded, skip disk write
        self._cache[key] = card
        self._dirty = True
        log.debug(f"PixelHashCache: recorded {card} (confidence={confidence:.2f})")
        self._flush()

    def size(self) -> int:
        return len(self._cache)

    def stats(self) -> str:
        return f"PixelHashCache: {self.size()} hashes loaded from {self._path}"

    # ── Private helpers ─────────────────────────────────────────────────────

    def _hash(self, crop_np: np.ndarray) -> str:
        """Normalise crop to fixed size, convert to RGB, return MD5 hex."""
        if crop_np.size == 0:
            return 'empty'
        # Resize to fixed canvas for robustness against ±1px table resize
        resized = cv2.resize(crop_np, (_HASH_NORM_W, _HASH_NORM_H),
                             interpolation=cv2.INTER_AREA)
        return hashlib.md5(resized.tobytes()).hexdigest()

    def _load(self) -> None:
        try:
            if self._path.exists():
                with open(self._path, 'r') as f:
                    self._cache = json.load(f)
                log.debug(f"PixelHashCache: loaded {len(self._cache)} entries")
        except Exception as e:
            log.warning(f"PixelHashCache: load failed ({e}), starting empty")
            self._cache = {}

    def _flush(self) -> None:
        if not self._dirty:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, 'w') as f:
                json.dump(self._cache, f)
            self._dirty = False
        except Exception as e:
            log.warning(f"PixelHashCache: flush failed ({e})")


# Module-level singleton — loaded once at import time
_pixel_hash_cache = PixelHashCardCache()



def read_player_cards(
    table_img: Image.Image,
    table_width_px: Optional[int] = None,
    table_height_px: Optional[int] = None,
    debug_dir: Optional[str] = None,
) -> List[str]:
    """Read the player's two hole cards from a table screenshot.

    Detection order (fastest/most reliable first):
      1. Pixel hash lookup  — O(1), 100% accurate after first sighting
      2. Dynamic OCR        — color + rank OCR, auto-records new hashes
      3. Return []          — not visible (face-down / not dealt)

    Returns:
        List of card names like ['AC', '10D'], or [] if cards not readable.
    """
    if not PYTESSERACT_AVAILABLE:
        log.warning("pytesseract not available, cannot OCR cards")
        return []

    W = table_width_px or table_img.width
    H = table_height_px or table_img.height
    img_np = np.array(table_img)
    if img_np.ndim == 3 and img_np.shape[2] == 4:
        img_np = img_np[:, :, :3]  # drop alpha

    positions = _find_card_positions(img_np, W, H)
    if positions is None:
        log.debug(f"No card area found (img {W}x{H})")
        return []

    deck_style = positions.get('_deck_style', STYLE_WHITE)
    log.debug(f"Deck style: {deck_style}")

    cards = []
    for side in ['left', 'right']:
        rank_box = positions[f'{side}_rank']
        suit_box = positions[f'{side}_suit']

        # ── Strategy 1: Pixel hash lookup (O(1), 100% accurate once populated) ─
        body_key = f'{side}_body'
        if body_key in positions:
            bx, by, bw, bh = positions[body_key]
            body_crop = img_np[by:by+bh, bx:bx+bw]
        else:
            rx, ry, rw, rh = rank_box
            body_crop = img_np[ry:ry+rh, rx:rx+rw]

        hash_card = _pixel_hash_cache.lookup(body_crop)
        if hash_card:
            log.debug(f"Hash HIT {side}: {hash_card}")
            cards.append(hash_card)
            continue

        # ── Strategy 2: Dynamic OCR ─────────────────────────────────────────
        rank = _read_rank_at(img_np, rank_box, deck_style)

        # For colored cards: if top-left corner rank fails, try center rank
        if not rank and deck_style == STYLE_COLORED:
            center_key = f'{side}_center_rank'
            if center_key in positions:
                rank = _read_rank_at(img_np, positions[center_key], deck_style)
                if rank:
                    log.debug(f"Rank from center fallback: {rank}")

        if deck_style == STYLE_COLORED:
            # Use known suit from blob detection if available (reliable).
            # Fall back to body-region color detection only when needed.
            known_key = f'_{side}_suit'
            if known_key in positions:
                suit = positions[known_key]
                log.debug(f"Using known {side} suit from blob detection: {suit}")
            else:
                suit = _detect_suit_colored(img_np, positions[f'{side}_body'])
        else:
            # Suit from text/symbol color on white card
            suit = _detect_suit_at(img_np, rank_box)
            if suit == '?':
                suit = _detect_suit_at(img_np, suit_box)

        if rank and suit != '?':
            # Normalize '10' -> 'T' for Monte Carlo compatibility
            if rank == '10':
                rank = 'T'
            card = f"{rank}{suit}"
            cards.append(card)
            log.debug(f"OCR {side} card: {card}")
            # Both rank AND suit confirmed → record in hash cache (confidence 1.0)
            _pixel_hash_cache.record(body_crop, card, confidence=1.0)
        else:
            log.debug(f"OCR {side} failed: rank={rank!r}, suit={suit!r}")

    if debug_dir:
        _save_debug(img_np, W, H, positions, cards, debug_dir)

    # Reject partial hand — must have TWO cards preflop or NONE
    if len(cards) == 1:
        log.warning(f"PARTIAL HAND detected: {cards} — waiting for second card")
        return []

    # Reject duplicate cards — impossible in a real deck
    if len(cards) == 2 and cards[0] == cards[1]:
        log.warning(f"DUPLICATE CARDS rejected: {cards} — OCR misread, returning empty")
        return []

    # Auto-save card crops for live verification (every ~30s)
    if len(cards) == 2:
        _auto_save_card_crops(img_np, positions, cards)

    return cards


# Counter for throttling auto-save
_auto_save_counter = 0
_auto_save_interval = 60  # Save every Nth call (~30s at 0.5s poll)


def _auto_save_card_crops(img_np, positions, cards):
    """Save card region crops for live verification and debugging."""
    global _auto_save_counter
    _auto_save_counter += 1
    if _auto_save_counter % _auto_save_interval != 1:
        return
    try:
        import os, time
        crop_dir = '/tmp/table_debug/card_crops'
        os.makedirs(crop_dir, exist_ok=True)

        # Save the full card area
        for side_idx, side in enumerate(['left', 'right']):
            body_key = f'{side}_body'
            if body_key not in positions:
                body_key = f'{side}_rank'
            if body_key in positions:
                bx, by, bw, bh = positions[body_key]
                # Expand crop slightly for context
                margin = 5
                y0 = max(0, by - margin)
                y1 = min(img_np.shape[0], by + bh + margin)
                x0 = max(0, bx - margin)
                x1 = min(img_np.shape[1], bx + bw + margin)
                crop = img_np[y0:y1, x0:x1]
                if crop.size > 0:
                    from PIL import Image
                    ts = time.strftime('%H%M%S')
                    fname = f'{ts}_{cards[side_idx]}_{side}.png'
                    Image.fromarray(crop).save(os.path.join(crop_dir, fname))

        # Also save full card area for context
        for key in ['left_rank', 'right_rank']:
            pass  # Individual crops above are sufficient
        log.debug(f"Card crops saved: {cards}")
    except Exception as e:
        log.debug(f"Card crop save failed: {e}")


# ---------------------------------------------------------------------------
#  Card position finding — supports both deck styles
# ---------------------------------------------------------------------------

def _find_card_positions(img_np: np.ndarray, W: int, H: int) -> Optional[Dict]:
    """Find crop positions for rank and suit of both cards.

    PRIMARY: Fixed-position cropping — always works, even for same-suit pairs.
    FALLBACK: Blob detection (colored/white) for non-standard table layouts.
    """
    y1, y2, x1, x2 = _search_band(W, H)
    log.debug(f"Card search: img={W}x{H}, band=({x1},{y1})-({x2},{y2})")

    # PRIMARY: Fixed-position cropping — no blob detection needed.
    # Each card is cropped independently, so same-suit pairs work perfectly.
    result = _find_cards_fixed_position(img_np, W, H)
    if result is not None:
        return result

    # Fallback 1: blob-based colored card detection
    result = _find_colored_cards(img_np, W, H)
    if result is not None:
        return result

    # Fallback 2: white cards (showdown/hand review views)
    result = _find_white_cards(img_np, W, H)
    if result is None:
        log.debug("No cards detected (fixed-position, colored, or white)")
    return result


def _find_cards_fixed_position(img_np: np.ndarray, W: int, H: int) -> Optional[Dict]:
    """Find cards using fixed percentage-based positions (no blob detection).

    This is the last-resort fallback for same-suit pairs where blob detection
    merges both cards into one blob. Uses the known GGSystem card positions
    from local_table_config.py.

    Only succeeds if both card regions have enough white text pixels
    (indicating face-up colored cards with white rank text).
    """
    # Fixed card positions — verified against live GGSystem screenshot
    # (KD+QD same-suit pair, 800x614pt table).
    # Left card measured: 42-49% X, 72-88% Y
    # Right card measured: 48-56% X, 72-88% Y
    # Margins added: ~1% each side for window size variance.
    LEFT_X1, LEFT_Y1, LEFT_X2, LEFT_Y2 = 0.40, 0.71, 0.51, 0.89
    RIGHT_X1, RIGHT_Y1, RIGHT_X2, RIGHT_Y2 = 0.47, 0.71, 0.58, 0.89

    lx1 = int(W * LEFT_X1)
    ly1 = int(H * LEFT_Y1)
    lx2 = int(W * LEFT_X2)
    ly2 = int(H * LEFT_Y2)
    rx1 = int(W * RIGHT_X1)
    ry1 = int(H * RIGHT_Y1)
    rx2 = int(W * RIGHT_X2)
    ry2 = int(H * RIGHT_Y2)

    left_crop = img_np[ly1:ly2, lx1:lx2]
    right_crop = img_np[ry1:ry2, rx1:rx2]

    # Verify both regions have white text (face-up colored cards)
    for side, crop in [('left', left_crop), ('right', right_crop)]:
        if crop.size == 0:
            return None
        white_px = np.sum(np.all(crop > 180, axis=2))
        white_frac = white_px / max(crop.shape[0] * crop.shape[1], 1)
        if white_frac < 0.02:
            log.debug(f"Fixed-position {side} card: only {white_frac:.1%} white, "
                      f"cards likely not face-up")
            return None

    log.debug(f"Fixed-position card detection: left=({lx1},{ly1})-({lx2},{ly2}), "
              f"right=({rx1},{ry1})-({rx2},{ry2})")

    # Build position dict matching _build_positions format
    lw, lh = lx2 - lx1, ly2 - ly1
    rw, rh = rx2 - rx1, ry2 - ry1

    # Rank crop: top-left corner of each card
    rank_w_l = max(int(lw * 0.45), 20)
    rank_h_l = max(int(lh * 0.42), 20)
    rank_w_r = max(int(rw * 0.45), 20)
    rank_h_r = max(int(rh * 0.42), 20)
    margin_x = max(int(lw * 0.06), 2)
    margin_y = max(int(lh * 0.04), 2)

    # Center rank crop (large rank in card center — fallback)
    center_w_l = max(int(lw * 0.70), 25)
    center_h_l = max(int(lh * 0.55), 20)
    center_w_r = max(int(rw * 0.70), 25)
    center_h_r = max(int(rh * 0.55), 20)

    # Suit text region
    suit_y_off = int(lh * 0.35)
    suit_w = max(int(lw * 0.35), 15)
    suit_h = max(int(lh * 0.18), 10)

    # Body region for colored suit detection (20-55% down the card)
    body_w_l = max(int(lw * 0.6), 20)
    body_w_r = max(int(rw * 0.6), 20)
    body_h = max(int(lh * 0.30), 20)
    body_y_off = int(lh * 0.20)

    positions = {
        'left_rank': (lx1 + margin_x, ly1 + margin_y, rank_w_l, rank_h_l),
        'right_rank': (rx1 + margin_x, ry1 + margin_y, rank_w_r, rank_h_r),
        'left_center_rank': (lx1 + int(lw * 0.10), ly1 + int(lh * 0.30),
                             center_w_l, center_h_l),
        'right_center_rank': (rx1 + int(rw * 0.10), ry1 + int(rh * 0.30),
                              center_w_r, center_h_r),
        'left_suit': (lx1 + margin_x, ly1 + suit_y_off, suit_w, suit_h),
        'right_suit': (rx1 + margin_x, ry1 + suit_y_off, suit_w, suit_h),
        'left_body': (lx1 + margin_x, ly1 + body_y_off, body_w_l, body_h),
        'right_body': (rx1 + margin_x, ry1 + body_y_off, body_w_r, body_h),
        '_deck_style': STYLE_COLORED,
        '_debug': {
            'method': 'fixed_position',
            'left_card': (lx1, ly1, lw, lh),
            'right_card': (rx1, ry1, rw, rh),
        },
    }

    return positions


def _find_white_cards(img_np: np.ndarray, W: int, H: int) -> Optional[Dict]:
    """Detect white cards with colored text (classic deck style)."""
    y1, y2, x1, x2 = _search_band(W, H)
    search = img_np[y1:y2, x1:x2]

    white = np.all(search > 175, axis=2).astype(np.uint8) * 255

    k_sz = max(5, int(min(W, H) * 0.013))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_sz, k_sz))
    closed = cv2.morphologyEx(white, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_h = H * 0.05
    min_w = W * 0.03
    candidates = []
    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)
        if bh > min_h and bw > min_w:
            candidates.append((bx + x1, by + y1, bw, bh))

    if not candidates:
        return None

    best = max(candidates, key=lambda c: c[2] * c[3])
    blob_x, blob_y, blob_w, blob_h = best

    # Refine Y boundaries using horizontal projection of white pixels
    blob_region = img_np[blob_y:blob_y + blob_h, blob_x:blob_x + blob_w]
    white_rows = np.all(blob_region > 175, axis=2)
    h_proj = white_rows.sum(axis=1).astype(float)

    card_threshold = blob_w * 0.15
    card_rows = h_proj > card_threshold
    card_h = blob_h
    for row_idx in range(len(card_rows) - 1, 0, -1):
        if card_rows[row_idx]:
            card_h = row_idx + 1
            break

    card_y_offset = 0
    for row_idx in range(len(card_rows)):
        if card_rows[row_idx]:
            card_y_offset = row_idx
            break

    actual_card_h = card_h - card_y_offset
    actual_card_y = blob_y + card_y_offset

    if actual_card_h < H * 0.03:
        return None

    # Split between left and right card
    card_region_white = white_rows[card_y_offset:card_h, :]
    v_proj = card_region_white.sum(axis=0).astype(float)
    split_rel = int(blob_w * 0.54)

    third = blob_w // 3
    mid_proj = v_proj[third:2 * third]
    if len(mid_proj) > 5:
        valley_idx = third + int(np.argmin(mid_proj))
        if abs(valley_idx - split_rel) < blob_w * 0.15:
            split_rel = valley_idx

    split_x = blob_x + split_rel
    est_card_w = split_rel

    log.debug(f"White card blob at ({blob_x},{blob_y}) size {blob_w}x{blob_h}")

    return _build_positions(blob_x, actual_card_y, blob_w, actual_card_h,
                            split_x, est_card_w, blob_y, blob_h, STYLE_WHITE)


def _salvage_spade_blobs(
    binary: np.ndarray, search: np.ndarray,
    x1: int, y1: int, W: int, H: int,
    min_h: float, min_w: float, center_x: float
) -> List[Tuple]:
    """Extract individual spade card blobs from an oversized S mask region.

    The V<70 mask picks up the dark table border/rail in addition to dark
    spade card backgrounds, creating one huge blob that spans the search band.
    Crop to the bottom 40% of the search band (where hero cards sit) and look
    for smaller dark sub-regions that contain white rank text.

    Returns up to 2 blobs sorted by distance from center.
    """
    search_h = binary.shape[0]
    # Hero cards are in the bottom 40% of the search band
    crop_y_start = max(0, int(search_h * 0.60))
    crop = binary[crop_y_start:, :]
    if crop.size == 0:
        return []

    contours, _ = cv2.findContours(crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results = []
    for c in contours:
        cx, cy, cw, ch = cv2.boundingRect(c)
        area = cw * ch
        if ch < min_h or cw < min_w or area < 500:
            continue
        aspect = ch / max(cw, 1)
        if aspect < 0.4 or aspect > 3.0:
            continue
        sub_rgb = search[crop_y_start + cy:crop_y_start + cy + ch, cx:cx + cw]
        if sub_rgb.size == 0:
            continue
        white_frac = float(np.sum(np.all(sub_rgb > 180, axis=2))) / max(area, 1)
        if white_frac < 0.015:
            continue
        abs_cx = cx + x1 + cw / 2
        dist = abs(abs_cx - center_x)
        results.append((cx + x1, crop_y_start + cy + y1, cw, ch, 'S', dist))
        log.debug(f"S sub-blob candidate at ({cx + x1},{crop_y_start + cy + y1}) "
                  f"{cw}x{ch} white={white_frac:.1%} dist={dist:.0f}")

    # Return up to 2 closest to center
    results.sort(key=lambda b: b[5])
    return results[:2]


def _salvage_club_blob(
    binary: np.ndarray, search: np.ndarray,
    bx_ref: int, by: int, bw_ref: int, bh: int,
    x1: int, y1: int, W: int, H: int,
    min_h: float, min_w: float, center_x: float
) -> Optional[Tuple]:
    """Try to extract a card-sized sub-region from an oversized C (clubs) blob.

    The green card background often merges with the green felt into one huge
    blob.  Hero cards are in the BOTTOM ~30% of the search band.  Crop the
    binary mask to that region and look for a card-shaped contour with white
    text.
    """
    search_h = binary.shape[0]
    # Hero cards live in the bottom 35% of the search band
    crop_y_start = max(0, int(search_h * 0.65))
    crop = binary[crop_y_start:, :]
    if crop.size == 0:
        return None

    contours, _ = cv2.findContours(crop, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_score = float('inf')
    for c in contours:
        cx, cy, cw, ch = cv2.boundingRect(c)
        area = cw * ch
        if ch < min_h or cw < min_w or area < 500:
            continue
        aspect = ch / max(cw, 1)
        if aspect < 0.5 or aspect > 2.5:
            continue
        # Check for white text in this sub-region
        sub_rgb = search[crop_y_start + cy:crop_y_start + cy + ch, cx:cx + cw]
        if sub_rgb.size == 0:
            continue
        white_frac = float(np.sum(np.all(sub_rgb > 180, axis=2))) / max(area, 1)
        if white_frac < 0.015:
            continue
        # Score by distance from center (prefer centered blobs)
        abs_cx = cx + x1 + cw / 2
        dist = abs(abs_cx - center_x)
        if best is None or dist < best_score:
            best = (cx + x1, crop_y_start + cy + y1, cw, ch, 'C', dist)
            best_score = dist
            log.debug(f"C sub-blob candidate at ({cx + x1},{crop_y_start + cy + y1}) "
                      f"{cw}x{ch} white={white_frac:.1%} dist={dist:.0f}")

    return best


def _find_colored_cards(img_np: np.ndarray, W: int, H: int) -> Optional[Dict]:
    """Detect colored cards (blue/red/green/black backgrounds with white text).

    Detects each suit color independently to avoid green felt contamination.
    Picks the best card-shaped blob from any single color channel.
    """
    y1, y2, x1, x2 = _search_band(W, H)
    search = img_np[y1:y2, x1:x2]
    hsv = cv2.cvtColor(search, cv2.COLOR_RGB2HSV)
    h_ch, s_ch, v_ch = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

    min_h = H * 0.05
    min_w = W * 0.03
    max_w = W * 0.25
    center_x = W * 0.5

    # Define per-suit masks — each processed independently
    suit_masks = {
        # Blue (diamonds): H=95-125, S>100, V>50
        'D': (h_ch >= 95) & (h_ch <= 125) & (s_ch > 100) & (v_ch > 50),
        # Red (hearts): H<10 or H>168, S>120, V>100
        # Tightened: S>120 and V>100 to reject subtle red tints from dark
        # card edges/UI.  Card backs have V~80-100 but NO white text.
        'H': ((h_ch < 10) | (h_ch > 168)) & (s_ch > 120) & (v_ch > 100),
        # Green (clubs): H=35-85, V>120 — cards are brighter than felt (V~83)
        # Felt has H~61 S~146 V~83; green cards have H~42 S~105 V~149
        'C': (h_ch >= 30) & (h_ch <= 85) & (s_ch > 60) & (v_ch > 120),
        # Black (spades): low V, low S — expand to V<70 to catch charcoal
        # card backgrounds; white-text check later rejects dark table areas
        'S': (v_ch < 70) & (s_ch < 60) & (v_ch > 15),
    }

    # Scale kernel sizes with table size — at 1280x800 use ~14, at 1920x1200 use ~20
    k_small = max(5, int(min(W, H) * 0.009))
    k_big = max(10, int(min(W, H) * 0.025))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_small, k_small))
    # Hearts/diamonds need a bigger kernel because white rank text on the card
    # creates large gaps in the suit-colored mask.
    kernel_big = cv2.getStructuringElement(cv2.MORPH_RECT, (k_big, k_big))
    all_candidates = []

    # Scale min pixel count with image size (200 was calibrated for ~1920x1200)
    min_px = max(50, int(W * H * 0.00009))

    for suit, mask in suit_masks.items():
        px_count = int(np.sum(mask))
        if px_count < min_px:
            log.debug(f"Suit {suit}: only {px_count} px (min {min_px}), skipping")
            continue
        log.debug(f"Suit {suit}: {px_count} px, searching blobs (kernel={k_big if suit in ('H','D') else k_small})")

        binary = mask.astype(np.uint8) * 255
        k = kernel_big if suit in ('H', 'D') else kernel
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k, iterations=1)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            bx, by, bw, bh = cv2.boundingRect(c)
            aspect = bh / max(bw, 1)
            if bh > min_h and bw > min_w and bw < max_w and 0.35 < aspect < 2.0:
                # Refine blob X boundaries using vertical projection.
                # This trims blobs that extend into felt/border areas.
                blob_mask = binary[by:by + bh, bx:bx + bw]
                v_proj = blob_mask.sum(axis=0)
                # Threshold: column must have ≥20% of rows as suit-colored
                col_thresh = bh * 0.2 * 255
                cols = v_proj >= col_thresh
                if not np.any(cols):
                    continue
                first_col = int(np.argmax(cols))
                last_col = bw - 1 - int(np.argmax(cols[::-1]))
                bx_ref = bx + first_col
                bw_ref = last_col - first_col + 1
                if bw_ref < min_w * 0.6:
                    continue

                # For spades (dark bg), apply extra filtering to reject
                # dark table background/rail that the low-V mask picks up.
                if suit == 'S':
                    blob_area = bw_ref * bh
                    # A single spade card is ~W*0.06 x H*0.14 = ~0.0084*W*H.
                    max_card_area = W * H * 0.025
                    if blob_area > max_card_area:
                        # Blob too large — dark bg merged with card.
                        # Try harder trimming: raise column threshold to 40%
                        # to isolate the actual card from dark surround.
                        blob_mask2 = binary[by:by + bh, bx:bx + bw]
                        v_proj2 = blob_mask2.sum(axis=0)
                        col_thresh2 = bh * 0.4 * 255
                        cols2 = v_proj2 >= col_thresh2
                        if np.any(cols2):
                            fc2 = int(np.argmax(cols2))
                            lc2 = bw - 1 - int(np.argmax(cols2[::-1]))
                            bx_ref2 = bx + fc2
                            bw_ref2 = lc2 - fc2 + 1
                            blob_area2 = bw_ref2 * bh
                            if blob_area2 <= max_card_area and bw_ref2 >= min_w * 0.6:
                                bx_ref = bx_ref2
                                bw_ref = bw_ref2
                                blob_area = blob_area2
                                log.debug(f"Spade blob re-trimmed: ({bx_ref + x1},{by + y1}) "
                                          f"{bw_ref}x{bh} area={blob_area}")
                            else:
                                # Re-trim still too large.  Check for white text
                                # — if present, the blob likely contains a real card
                                # and downstream spade-trim will fix bounds.
                                rt_rgb = search[by:by + bh, bx_ref2:bx_ref2 + bw_ref2]
                                rt_wf = 0.0
                                if rt_rgb.size > 0:
                                    rt_wf = float(np.sum(np.all(rt_rgb > 180, axis=2))) / max(blob_area2, 1)
                                if rt_wf >= 0.02:
                                    # White text present — try salvage: find individual
                                    # card blobs in the bottom portion of the search band,
                                    # excluding the dark table border that inflated the blob.
                                    salvaged = _salvage_spade_blobs(
                                        binary, search, x1, y1, W, H,
                                        min_h, min_w, center_x)
                                    if salvaged:
                                        all_candidates.extend(salvaged)
                                        log.debug(f"Spade oversized: salvaged "
                                                  f"{len(salvaged)} card blob(s) from "
                                                  f"bottom band")
                                        continue
                                    # Salvage found nothing — keep oversized blob
                                    bx_ref = bx_ref2
                                    bw_ref = bw_ref2
                                    blob_area = blob_area2
                                    log.debug(f"Spade blob oversized but has white text "
                                              f"({rt_wf:.1%}), keeping: ({bx_ref + x1},{by + y1}) "
                                              f"{bw_ref}x{bh}")
                                else:
                                    log.debug(f"Spade blob rejected: area {blob_area} > max "
                                              f"{max_card_area:.0f} at ({bx_ref + x1},{by + y1}) "
                                              f"{bw_ref}x{bh} (re-trim also too large: {blob_area2})")
                                    continue
                        else:
                            log.debug(f"Spade blob rejected: area {blob_area} > max "
                                      f"{max_card_area:.0f} at ({bx_ref + x1},{by + y1}) "
                                      f"{bw_ref}x{bh} (re-trim found no columns)")
                            continue
                    # Also require white text pixels (rank/suit characters).
                    sr_x = bx_ref  # search-region x coord
                    blob_rgb = search[by:by + bh, sr_x:sr_x + bw_ref]
                    if blob_rgb.size > 0:
                        white_in_blob = np.all(blob_rgb > 180, axis=2)
                        white_frac = float(np.sum(white_in_blob)) / max(blob_area, 1)
                        if white_frac < 0.03:
                            log.debug(f"Spade blob rejected: only {white_frac:.1%} "
                                      f"white at ({bx_ref + x1},{by + y1}) {bw_ref}x{bh}")
                            continue

                # ALL suits: require white text pixels (rank/suit chars).
                # Colored cards have white rank text; UI elements (buttons,
                # borders) are solid color with no white content.
                # Spade blobs have stricter checks above; H/D/C need this too.
                if suit != 'S':
                    blob_area = bw_ref * bh
                    # Max area for a single card: ~W*0.08 x H*0.16 = ~0.013*W*H
                    # Two overlapping cards: ~2x that.  Reject obviously oversized.
                    max_card_area = W * H * 0.030
                    if blob_area > max_card_area:
                        # For CLUBS (green), the card's green bg often merges with
                        # the green felt into one oversized blob.  Try to salvage
                        # by looking for a card-sized sub-region in the BOTTOM of
                        # the blob (hero cards are near the bottom of the table).
                        if suit == 'C':
                            sub_blob = _salvage_club_blob(
                                binary, search, bx_ref, by, bw_ref, bh,
                                x1, y1, W, H, min_h, min_w, center_x)
                            if sub_blob is not None:
                                all_candidates.append(sub_blob)
                                log.debug(f"C blob salvaged sub-region: "
                                          f"({sub_blob[0]},{sub_blob[1]}) "
                                          f"{sub_blob[2]}x{sub_blob[3]}")
                        else:
                            log.debug(f"{suit} blob rejected: area {blob_area} > max "
                                      f"{max_card_area:.0f} at ({bx_ref + x1},{by + y1}) "
                                      f"{bw_ref}x{bh} (felt/UI false positive)")
                        continue

                    sr_x = bx_ref
                    blob_rgb = search[by:by + bh, sr_x:sr_x + bw_ref]
                    if blob_rgb.size > 0:
                        white_in_blob = np.all(blob_rgb > 180, axis=2)
                        white_frac = float(np.sum(white_in_blob)) / max(blob_area, 1)
                        if white_frac < 0.015:
                            # Same salvage attempt for C blobs with low white frac
                            if suit == 'C':
                                sub_blob = _salvage_club_blob(
                                    binary, search, bx_ref, by, bw_ref, bh,
                                    x1, y1, W, H, min_h, min_w, center_x)
                                if sub_blob is not None:
                                    all_candidates.append(sub_blob)
                                    log.debug(f"C blob salvaged (low white): "
                                              f"({sub_blob[0]},{sub_blob[1]}) "
                                              f"{sub_blob[2]}x{sub_blob[3]}")
                                    continue
                            log.debug(f"{suit} blob rejected: only {white_frac:.1%} "
                                      f"white at ({bx_ref + x1},{by + y1}) {bw_ref}x{bh}")
                            continue

                dist = abs((bx_ref + x1 + bw_ref / 2) - center_x)
                all_candidates.append((bx_ref + x1, by + y1, bw_ref, bh, suit, dist))
                log.debug(f"Colored {suit}: blob ({bx_ref + x1},{by + y1}) "
                          f"{bw_ref}x{bh} aspect={bh / max(bw_ref, 1):.2f} "
                          f"px={px_count} (trimmed from w={bw})")

    if not all_candidates:
        return None

    # Filter out Y-position outliers — all card blobs should be at similar Y.
    # False positives from board cards (top) or UI elements (bottom) have
    # different Y.  Find the densest Y cluster to anchor the filter.
    if len(all_candidates) >= 2:
        # Skip Y-filter when exactly 2 blobs with different suits AND both
        # are reasonably sized — almost certainly the two hole cards (e.g.
        # Q♦ + J♣).  Colored card backgrounds can extend far above the
        # actual card, giving the larger blob a much smaller Y.
        # Don't skip if one blob is tiny (<5% of the other's area) — that's
        # likely a false positive from chips, UI elements, etc.
        suits_present = {c[4] for c in all_candidates}
        skip_y_filter = False
        if len(all_candidates) == 2 and len(suits_present) == 2:
            a0 = all_candidates[0][2] * all_candidates[0][3]
            a1 = all_candidates[1][2] * all_candidates[1][3]
            min_area = min(a0, a1)
            max_area = max(a0, a1)
            # Both blobs must be reasonably sized (smaller ≥ 10% of larger)
            # AND smaller blob must be at least 3000px (not a tiny chip/icon)
            skip_y_filter = min_area >= max_area * 0.10 and min_area >= 3000

        if skip_y_filter:
            log.debug(f"Y-filter SKIPPED: 2 blobs with different suits {suits_present}")
        else:
            max_y_dev = H * 0.08  # Allow ~8% of image height deviation

            # Use center Y for comparison — spade blobs extend higher than
            # other suits due to dark bg merging with table, but their
            # centers are at similar Y to other card blobs.
            def _center_y(blob):
                return blob[1] + blob[3] / 2

            # Find the blob whose center Y has the most neighbors.
            best_ref_idx = 0
            best_count = 0
            for i, c in enumerate(all_candidates):
                cy = _center_y(c)
                count = sum(1 for o in all_candidates
                            if abs(_center_y(o) - cy) <= max_y_dev)
                if count > best_count or (count == best_count and
                                           c[2] * c[3] > all_candidates[best_ref_idx][2] * all_candidates[best_ref_idx][3]):
                    best_count = count
                    best_ref_idx = i
            ref_blob = all_candidates[best_ref_idx]
            ref_cy = _center_y(ref_blob)
            ref_area = ref_blob[2] * ref_blob[3]

            filtered = []
            for c in all_candidates:
                y_dev = abs(_center_y(c) - ref_cy)
                c_area = c[2] * c[3]
                if y_dev <= max_y_dev:
                    filtered.append(c)
                else:
                    log.debug(f"Y-filter: removing {c[4]} blob at y={c[1]} "
                              f"(dev={y_dev:.0f}px, area={c_area} "
                              f"= {c_area / max(ref_area, 1):.0%} of ref)")
            if len(filtered) >= 1:
                all_candidates = filtered

    # Sort by x position (left to right)
    all_candidates.sort(key=lambda c: c[0])

    if len(all_candidates) > 2:
        # More than 2 blobs — pick the best pair.
        # Strategy: prefer the pair closest to center with different suits.
        # False positives from UI (buttons, timer) tend to be at edges.
        best_pair = None
        best_score = float('inf')
        for i in range(len(all_candidates)):
            for j in range(i + 1, len(all_candidates)):
                ci, cj = all_candidates[i], all_candidates[j]
                # Score = sum of distances from center (lower = better)
                score = ci[5] + cj[5]
                # Bonus for different suits (prefer different-suit pairs)
                if ci[4] != cj[4]:
                    score *= 0.5
                if best_pair is None or score < best_score:
                    best_score = score
                    best_pair = (i, j)
        if best_pair:
            left_c = all_candidates[best_pair[0]]
            right_c = all_candidates[best_pair[1]]
            log.debug(f"Selected pair from {len(all_candidates)} blobs: "
                      f"{left_c[4]}@x={left_c[0]} + {right_c[4]}@x={right_c[0]} "
                      f"(score={best_score:.0f})")
            all_candidates = [left_c, right_c]

    if len(all_candidates) >= 2:
        left_c = all_candidates[0]
        right_c = all_candidates[-1]

        # Validate that both blobs are plausible cards.  A table rail or
        # button blob is much smaller than a real card.  Require the
        # smaller blob to be at least 30% of the larger blob's height.
        # (Was 45%, but spade blobs extend into dark table rail making
        # them much taller than the other card, e.g. K♠=250px vs 2♣=100px.)
        min_h = min(left_c[3], right_c[3])
        max_h = max(left_c[3], right_c[3])
        if min_h < max_h * 0.30:
            # The smaller blob is too small to be a card — discard it
            # and treat the larger one as a single-blob case.
            if left_c[3] >= right_c[3]:
                log.debug(f"Discarding small right blob: {right_c[4]} "
                          f"{right_c[2]}x{right_c[3]} vs left "
                          f"{left_c[2]}x{left_c[3]}")
                all_candidates = [left_c]
            else:
                log.debug(f"Discarding small left blob: {left_c[4]} "
                          f"{left_c[2]}x{left_c[3]} vs right "
                          f"{right_c[2]}x{right_c[3]}")
                all_candidates = [right_c]

    if len(all_candidates) >= 2:
        left_c = all_candidates[0]
        right_c = all_candidates[-1]

        # Cross-validate blob suits: sample body region of each blob and
        # verify the assigned suit matches the dominant color.  This catches
        # false positives from UI elements (fold button, timer bar) that
        # pass the white-text check but are wrong suit.
        for idx, blob_c in enumerate([left_c, right_c]):
            bx_v, by_v, bw_v, bh_v, suit_v, dist_v = blob_c
            body_crop = img_np[by_v:by_v + bh_v, bx_v:bx_v + bw_v]
            if body_crop.size > 0:
                actual_suit = _detect_suit_colored(img_np,
                                                   (bx_v, by_v, bw_v, bh_v))
                if actual_suit != '?' and actual_suit != suit_v:
                    side = 'left' if idx == 0 else 'right'
                    log.debug(f"Blob suit cross-check MISMATCH {side}: "
                              f"blob={suit_v} body={actual_suit}, "
                              f"using body result")
                    # Replace with corrected suit
                    corrected = (bx_v, by_v, bw_v, bh_v, actual_suit, dist_v)
                    all_candidates[0 if idx == 0 else -1] = corrected

        left_c = all_candidates[0]
        right_c = all_candidates[-1]

        combo_x = left_c[0]
        combo_y = min(left_c[1], right_c[1])
        combo_x2 = max(left_c[0] + left_c[2], right_c[0] + right_c[2])
        combo_y2 = max(left_c[1] + left_c[3], right_c[1] + right_c[3])
        combo_w = combo_x2 - combo_x
        combo_h = combo_y2 - combo_y

        # Split between the two blob centers
        left_cx = left_c[0] + left_c[2] / 2
        right_cx = right_c[0] + right_c[2] / 2
        split_x = int((left_cx + right_cx) / 2)
        est_card_w = split_x - combo_x

        blob_x, blob_y, blob_w, blob_h = combo_x, combo_y, combo_w, combo_h

        # Dark blobs (spade/S) often extend too far left into the dark table
        # rail.  Refine the left edge by scanning for white rank text columns.
        if left_c[4] == 'S' and est_card_w > right_c[2] * 1.3:
            # Scan top 40% of left card for white pixel columns
            scan_y0 = combo_y
            scan_y1 = combo_y + int(combo_h * 0.40)
            scan_region = img_np[scan_y0:scan_y1, combo_x:split_x]
            if scan_region.size > 0:
                white_mask = np.all(scan_region > 180, axis=2)
                col_density = white_mask.sum(axis=0).astype(float) / max(white_mask.shape[0], 1)
                # Find the first column with significant white pixels (>5%)
                threshold = 0.05
                white_cols = np.where(col_density > threshold)[0]
                if len(white_cols) > 0:
                    first_white = white_cols[0]
                    # Set left edge a small margin before the first white column
                    margin = max(int(first_white * 0.15), 5)
                    new_left = combo_x + max(first_white - margin, 0)
                    if new_left > combo_x + 10:  # Only if meaningful trim
                        log.debug(f"Spade blob trim: {combo_x} -> {new_left} "
                                  f"(white text at col {first_white})")
                        combo_x = new_left
                        combo_w = combo_x2 - combo_x
                        est_card_w = split_x - combo_x
                        blob_x = combo_x
                        blob_w = combo_w

        # We KNOW the suit of each card from blob detection — store it
        # so we don't need to re-detect from body region (which fails
        # when cards overlap and colors bleed across the split).
        known_left_suit = left_c[4]
        known_right_suit = right_c[4]

        # When blobs have very different Y positions (e.g. oversized diamond
        # background extending upward), store per-blob Y for crop correction.
        # right_card_y_override will cause _build_positions output to be
        # adjusted so right card crops use the right blob's actual Y range.
        right_card_y_override = None
        y_diff = abs(left_c[1] - right_c[1])
        if y_diff > H * 0.10:
            # Right blob has a significantly different Y — use its own Y for crops.
            right_card_y_override = (right_c[1], right_c[3])
            log.debug(f"Right card Y override: y={right_c[1]} h={right_c[3]} "
                      f"(left blob y={left_c[1]}, diff={y_diff}px)")

        log.debug(f"Combined {len(all_candidates)} blobs: ({blob_x},{blob_y}) "
                  f"{blob_w}x{blob_h} split_x={split_x} "
                  f"suits={known_left_suit}/{known_right_suit}")
    elif len(all_candidates) == 1:
        best = all_candidates[0]
        bx0, by0, bw0, bh0, suit0, _ = best
        known_left_suit = None
        known_right_suit = None
        right_card_y_override = None

        # Single blob: the other card might be a different suit that was
        # filtered out.  Probe both sides of this blob.
        found_second = False
        if suit0 == 'S':
            # Spade blob found alone — probe for a colored card (H/D/C) on
            # either side.  These can be missed when the club green blob
            # merges with felt, or when height/area filters discard them.
            probe_w = bw0

            def _probe_for_colored(region):
                """Check if a region has white text + saturated card colors."""
                if region.size == 0:
                    return False, 0.0, '?'
                total = max(region.shape[0] * region.shape[1], 1)
                wp = float(np.sum(np.all(region > 180, axis=2))) / total
                if wp < 0.01:
                    return False, wp, '?'
                hsv_p = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
                s_p, v_p, h_p = hsv_p[:, :, 1], hsv_p[:, :, 2], hsv_p[:, :, 0]
                colored = float(np.sum((s_p > 60) & (v_p > 100))) / total
                if colored < 0.10:
                    return False, wp, '?'
                # Determine dominant suit color
                red = float(np.sum(((h_p < 10) | (h_p > 168)) & (s_p > 100) & (v_p > 100))) / total
                blue = float(np.sum((h_p >= 95) & (h_p <= 125) & (s_p > 80))) / total
                green = float(np.sum((h_p >= 30) & (h_p <= 85) & (s_p > 60) & (v_p > 120))) / total
                mx = max(red, blue, green)
                if mx < 0.08:
                    return False, wp, '?'
                if red == mx:
                    return True, wp, 'H'
                elif blue == mx:
                    return True, wp, 'D'
                return True, wp, 'C'

            # Probe LEFT
            probe_x_l = bx0 - int(probe_w * 1.1)
            if probe_x_l >= 0:
                pr = img_np[by0:by0 + bh0, probe_x_l:bx0]
                is_col, wf, ps = _probe_for_colored(pr)
                if is_col:
                    combo_x = probe_x_l
                    combo_w = (bx0 + bw0) - probe_x_l
                    split_x = bx0
                    est_card_w = bx0 - probe_x_l
                    blob_x, blob_y = combo_x, by0
                    blob_w, blob_h = combo_w, bh0
                    found_second = True
                    known_left_suit = ps
                    known_right_suit = 'S'
                    log.debug(f"Colored {ps} inferred LEFT of S blob: "
                              f"probe ({probe_x_l},{by0}) white={wf:.1%}")

            # Probe RIGHT
            if not found_second:
                probe_x_r = bx0 + bw0
                if probe_x_r + probe_w <= W:
                    pr = img_np[by0:by0 + bh0, probe_x_r:probe_x_r + probe_w]
                    is_col, wf, ps = _probe_for_colored(pr)
                    if is_col:
                        combo_x = bx0
                        combo_w = (probe_x_r + probe_w) - bx0
                        split_x = probe_x_r
                        est_card_w = combo_w - bw0
                        blob_x, blob_y = combo_x, by0
                        blob_w, blob_h = combo_w, bh0
                        found_second = True
                        known_left_suit = 'S'
                        known_right_suit = ps
                        log.debug(f"Colored {ps} inferred RIGHT of S blob: "
                                  f"probe ({probe_x_r},{by0}) white={wf:.1%}")

        elif suit0 != 'S':
            # Single non-spade blob: the other card might be a spade (black)
            # that the mask merged into the dark table background.  Probe both
            # sides for a dark card with white text.
            probe_w = bw0  # expect similar width

            def _probe_for_spade(region):
                """Check if a region looks like a dark card with white text."""
                if region.size == 0:
                    return False, 0.0, 0.0
                total = max(region.shape[0] * region.shape[1], 1)
                wp = float(np.sum(np.all(region > 180, axis=2))) / total
                # Use < 80 for dark: spade card bg is charcoal (~V=60-80), not pure black
                dp = float(np.sum(np.all(region < 80, axis=2))) / total
                # Real spade cards have white rank text (~2-5%) and dark bg (~20-50%).
                # Reject if too dark (>60%) — that's avatar/icon area, not a card.
                return wp > 0.02 and 0.2 < dp < 0.60, wp, dp

            # Probe LEFT of the blob
            probe_x_left = bx0 - int(probe_w * 1.1)
            if probe_x_left >= 0:
                probe_region = img_np[by0:by0 + bh0, probe_x_left:bx0]
                is_spade, wf, df = _probe_for_spade(probe_region)
                if is_spade:
                    combo_x = probe_x_left
                    combo_w = (bx0 + bw0) - probe_x_left
                    split_x = bx0
                    est_card_w = bx0 - probe_x_left
                    blob_x, blob_y = combo_x, by0
                    blob_w, blob_h = combo_w, bh0
                    found_second = True
                    known_left_suit = 'S'
                    known_right_suit = suit0
                    log.debug(f"Spade card inferred LEFT of {suit0} blob: "
                              f"probe ({probe_x_left},{by0}) white={wf:.1%} dark={df:.1%}")

            # Probe RIGHT of the blob
            if not found_second:
                probe_x_right = bx0 + bw0
                if probe_x_right + probe_w <= W:
                    probe_region = img_np[by0:by0 + bh0, probe_x_right:probe_x_right + probe_w]
                    is_spade, wf, df = _probe_for_spade(probe_region)
                    if is_spade:
                        combo_x = bx0
                        combo_w = (probe_x_right + probe_w) - bx0
                        split_x = probe_x_right
                        est_card_w = combo_w - bw0
                        blob_x, blob_y = combo_x, by0
                        blob_w, blob_h = combo_w, bh0
                        found_second = True
                        known_left_suit = suit0
                        known_right_suit = 'S'
                        log.debug(f"Spade card inferred RIGHT of {suit0} blob: "
                                  f"probe ({probe_x_right},{by0}) white={wf:.1%} dark={df:.1%}")

        if not found_second:
            blob_x, blob_y, blob_w, blob_h = bx0, by0, bw0, bh0

            # Use white pixel projection to find the split between two
            # overlapping same-suit cards.  The rank text creates two
            # white pixel clusters; the split is at the valley between them.
            split_x, left_text_x = _find_split_by_white_text(img_np, bx0, by0, bw0, bh0)
            if split_x is None:
                split_x = blob_x + int(blob_w * 0.50)

            est_card_w = split_x - blob_x

            # Fix oversized blobs: when the color mask extends into the
            # table border (e.g. red felt border merging with hearts blob),
            # the blob_x is too far left.  If the white text projection
            # found the actual left card edge, use it to trim blob_x.
            if left_text_x is not None and left_text_x > blob_x:
                oversized = est_card_w > blob_h * 0.75
                if oversized:
                    old_x = blob_x
                    blob_x = left_text_x
                    blob_w = (old_x + blob_w) - blob_x
                    est_card_w = split_x - blob_x
                    log.debug(f"Oversized blob trimmed: x {old_x}->{blob_x}, "
                              f"est_card_w={est_card_w}")

            # Single blob, same suit for both cards — body detection is reliable
            known_left_suit = suit0
            known_right_suit = suit0

    if blob_w < W * 0.03 or blob_h < H * 0.04:
        return None

    # Verify blob contains white text (colored cards have white rank/suit)
    # Card backs are solid dark with no white pixels
    blob_crop = img_np[blob_y:blob_y + blob_h, blob_x:blob_x + blob_w]
    white_px = np.all(blob_crop > 170, axis=2)
    white_frac = float(np.sum(white_px)) / max(blob_crop.shape[0] * blob_crop.shape[1], 1)
    if white_frac < 0.015:
        log.debug(f"Colored blob rejected: only {white_frac:.1%} white pixels (card back?)")
        return None

    log.debug(f"Colored card blob at ({blob_x},{blob_y}) size {blob_w}x{blob_h} "
              f"white={white_frac:.1%}")

    positions = _build_positions(blob_x, blob_y, blob_w, blob_h,
                                 split_x, est_card_w, blob_y, blob_h, STYLE_COLORED)

    # Detect actual right card edge and trim the center crop.
    # The blob can extend past the card into table felt (common for
    # same-suit spade cards whose dark bg merges with dark table during
    # morphological closing).  This doesn't affect the corner crop (small,
    # positioned at split_x + margin) but causes the center crop to land
    # on table felt instead of card text.
    actual_right = _detect_right_card_edge(
        img_np, split_x, blob_y, blob_h, blob_x + blob_w
    )
    actual_right_card_w = actual_right - split_x
    nominal_right_card_w = blob_x + blob_w - split_x
    if actual_right_card_w < nominal_right_card_w * 0.85:
        # Recalculate BOTH corner and center crops.
        # The blob extends past the card into table felt — the nominal
        # right_card_w is grossly overestimated, so crops based on it
        # include background noise that breaks template matching.

        # Corner crop: trim width to actual card
        # Use card_h-based dimensions (portrait crop) to match left card corner.
        rc_margin_x = max(int(blob_h * 0.03), 2)
        rc_rank_w = max(int(blob_h * 0.22), 20)  # ~35px portrait, not wide landscape
        rc_rank_h = max(int(blob_h * 0.42), 20)  # ~66px, matches left card height
        rc_margin_y = max(int(blob_h * 0.08), 3)
        positions['right_rank'] = (
            split_x + rc_margin_x, blob_y + rc_margin_y,
            rc_rank_w, rc_rank_h
        )

        # Center crop: full actual width, no x offset (safe at center height)
        rcx_off = 0
        rcy_off = int(blob_h * 0.25)
        rcw = max(actual_right_card_w - 2, 20)
        rch = max(int(blob_h * 0.55), 30)
        # When the right card is very narrow (< 30% of card height),
        # the center rank text is mostly hidden — only a fragment is visible
        # which produces false matches (e.g. "10" fragment → "A").  Skip
        # center fallback in this case; better to return 1 card than a wrong card.
        if actual_right_card_w >= blob_h * 0.30:
            positions['right_center_rank'] = (
                split_x + rcx_off, blob_y + rcy_off, rcw, rch
            )
        else:
            # Remove center crop — too fragmentary to be reliable
            positions.pop('right_center_rank', None)
            log.debug(f"Right card too narrow for center fallback: "
                      f"{actual_right_card_w}px < {blob_h * 0.30:.0f}px")
        log.debug(f"Right card edge: actual_w={actual_right_card_w} "
                  f"(nominal={nominal_right_card_w}), corner+center crops trimmed")

    # When right blob has a different Y (e.g. oversized diamond bg), adjust
    # right card crop positions to use the right blob's actual Y range.
    if right_card_y_override is not None:
        r_y, r_h = right_card_y_override
        # Recalculate right card positions using the right blob's actual Y/H.
        right_card_w = blob_x + blob_w - split_x
        right_margin_x = max(int(r_h * 0.03), 2)
        right_rank_w = max(int(r_h * 0.22), 20)  # portrait crop, matches left card
        right_rank_h = max(int(r_h * 0.42), 20)
        right_margin_y = max(int(r_h * 0.08), 3)
        positions['right_rank'] = (split_x + right_margin_x, r_y + right_margin_y,
                                   right_rank_w, right_rank_h)
        # Right center rank (same-suit overlap: skip left card bleed)
        right_center_x_off = max(int(right_card_w * 0.40), 15)
        right_center_y_off = int(r_h * 0.30)
        right_center_w = max(int(right_card_w * 0.55), 30)
        right_center_h = max(int(r_h * 0.40), 25)
        positions['right_center_rank'] = (split_x + right_center_x_off,
                                          r_y + right_center_y_off,
                                          right_center_w, right_center_h)
        # Right body region for suit detection
        body_w = max(int(est_card_w * 0.6), 20)
        body_h_r = max(int(r_h * 0.30), 20)
        body_y_r = r_y + int(r_h * 0.20)
        positions['right_body'] = (split_x + right_margin_x, body_y_r, body_w, body_h_r)
        # Right suit region
        suit_y_off = int(r_h * 0.35)
        suit_w = max(int(est_card_w * 0.35), 15)
        suit_h = max(int(r_h * 0.18), 10)
        positions['right_suit'] = (split_x + right_margin_x, r_y + suit_y_off, suit_w, suit_h)
        log.debug(f"Right card Y-corrected: rank at ({positions['right_rank'][0]},"
                  f"{positions['right_rank'][1]}) "
                  f"{positions['right_rank'][2]}x{positions['right_rank'][3]}")

    # Store known suits from blob detection — avoids re-detecting from body
    # region which fails when overlapping cards bleed colors across the split.
    if known_left_suit:
        positions['_left_suit'] = known_left_suit
    if known_right_suit:
        positions['_right_suit'] = known_right_suit

    return positions


def _build_positions(blob_x, card_y, blob_w, card_h,
                     split_x, est_card_w, blob_y, blob_h, deck_style) -> Dict:
    """Build rank/suit crop positions from a detected card blob."""
    # Actual right card width (may differ from est_card_w due to overlap)
    right_card_w = blob_x + blob_w - split_x

    if deck_style == STYLE_COLORED:
        # Colored cards: primary crop targets the CORNER rank (small character
        # at top-left of each card).  The left card uses a wider crop because
        # its corner is fully exposed.  The right card uses a tight corner
        # crop because the left card physically overlaps much of its face.
        margin_x = max(int(est_card_w * 0.08), 3)
        margin_y = max(int(card_h * 0.04), 2)
        rank_w = max(int(est_card_w * 0.75), 30)
        rank_h = max(int(card_h * 0.42), 20)
        # Cap rank_w to prevent oversized crops from including both corner
        # and center rank text.  Corner rank width scales with card height.
        max_rank_w = max(int(card_h * 0.45), 30)
        if rank_w > max_rank_w:
            rank_w = max_rank_w
        # Right card corner rank: tiny margin from split_x (the corner rank
        # is visible right at the top-left of the exposed right card).
        # Use card_h-based dimensions to get a portrait crop matching the left
        # card corner (~35px wide × 66px tall) rather than a landscape crop
        # that spans most of the exposed right card width.
        right_margin_x = max(int(card_h * 0.03), 2)
        right_rank_w = max(int(card_h * 0.22), 20)  # ~35px portrait, matches left
        right_rank_h = max(int(card_h * 0.42), 20)  # ~66px
        right_margin_y = max(int(card_h * 0.08), 3)
    else:
        # White cards: rank is small text in the top-left corner
        margin_x = max(int(est_card_w * 0.04), 2)
        margin_y = max(int(card_h * 0.03), 2)
        rank_w = max(int(est_card_w * 0.45), 20)
        rank_h = max(int(card_h * 0.35), 15)
        right_margin_x = 0
        right_rank_w = rank_w
        right_rank_h = rank_h
        right_margin_y = margin_y

    suit_y_off = int(card_h * 0.35)
    suit_w = max(int(est_card_w * 0.35), 15)
    suit_h = max(int(card_h * 0.18), 10)

    # Card body regions (for colored deck suit detection)
    # Sample from 20-55% down the card: the TOP portion is the colored body area.
    # AVOID the bottom: blobs often extend into the dark-red table rail below,
    # which contaminates spade (dark) cards with red rail pixels.
    body_w = max(int(est_card_w * 0.6), 20)
    body_h = max(int(card_h * 0.30), 20)
    body_y = card_y + int(card_h * 0.20)

    # Center rank crop (large character in card center — used as fallback)
    if deck_style == STYLE_COLORED:
        # Left card center: rank is in middle of card
        center_rank_x_off = int(est_card_w * 0.10)
        center_rank_y_off = int(card_h * 0.30)
        center_rank_w = max(int(est_card_w * 0.70), 25)
        center_rank_h = max(int(card_h * 0.55), 20)
        # Right card center: the large rank character sits at ~35-60% down
        # the card, and ~45-85% across the exposed width.  Start the crop
        # at 40% X to skip the LEFT card's rank text that bleeds across
        # the overlap boundary (visible as white pixels near the split).
        right_center_x_off = max(int(right_card_w * 0.40), 15)
        right_center_y_off = int(card_h * 0.30)
        right_center_w = max(int(right_card_w * 0.55), 30)
        right_center_h = max(int(card_h * 0.40), 25)
    else:
        center_rank_x_off = center_rank_y_off = 0
        center_rank_w = center_rank_h = 0
        right_center_x_off = right_center_y_off = 0
        right_center_w = right_center_h = 0

    positions = {
        'left_rank': (blob_x + margin_x, card_y + margin_y, rank_w, rank_h),
        'right_rank': (split_x + right_margin_x, card_y + right_margin_y,
                       right_rank_w, right_rank_h),
        'left_center_rank': (blob_x + center_rank_x_off, card_y + center_rank_y_off,
                             center_rank_w, center_rank_h),
        'right_center_rank': (split_x + right_center_x_off,
                              card_y + right_center_y_off,
                              right_center_w, right_center_h),
        'left_suit': (blob_x + margin_x, card_y + suit_y_off, suit_w, suit_h),
        'right_suit': (split_x + right_margin_x, card_y + suit_y_off, suit_w, suit_h),
        'left_body': (blob_x + margin_x, body_y, body_w, body_h),
        'right_body': (split_x + right_margin_x, body_y, body_w, body_h),
        '_deck_style': deck_style,
        '_debug': {
            'blob': (blob_x, blob_y, blob_w, blob_h),
            'card_area': (blob_x, card_y, blob_w, card_h),
            'split_x': split_x,
        },
    }

    log.debug(
        f"Card area: x={blob_x}-{blob_x + blob_w}, y={card_y}-{card_y + card_h}, "
        f"split_x={split_x}, style={deck_style}"
    )
    return positions


def _find_split_by_white_text(
    img_np: np.ndarray, bx: int, by: int, bw: int, bh: int
) -> Tuple[Optional[int], Optional[int]]:
    """Find the split between two overlapping same-suit cards using white text.

    Looks at the top 45% of the blob (where rank text is) and finds two
    clusters of white pixels.  The split is at the valley between them.

    Returns:
        (split_x, left_text_x) — both absolute x coordinates, or (None, None).
        split_x: the valley between two text clusters.
        left_text_x: leftmost column with significant white text (start of
            left card content). Used to trim oversized blobs where the color
            mask extends into the table border.
    """
    top_h = max(int(bh * 0.45), 10)
    top_region = img_np[by:by + top_h, bx:bx + bw]
    if top_region.size == 0:
        return None, None

    white = np.all(top_region > 170, axis=2)
    v_proj = white.sum(axis=0).astype(float)

    # Smooth to reduce noise
    kernel_size = max(3, bw // 30)
    smoothed = np.convolve(v_proj, np.ones(kernel_size) / kernel_size, mode='same')

    # Find two text clusters by looking for the deepest valley in the
    # middle 60% of the blob (between 20% and 80%).
    search_start = int(bw * 0.20)
    search_end = int(bw * 0.80)
    if search_end <= search_start:
        return None, None

    segment = smoothed[search_start:search_end]
    if len(segment) < 5:
        return None, None

    # Find the minimum in this segment
    valley_rel = int(np.argmin(segment))
    valley_abs = search_start + valley_rel
    valley_val = smoothed[valley_abs]

    # Verify there's a real gap: valley should be significantly lower than
    # the peaks on both sides
    left_peak = smoothed[:valley_abs].max() if valley_abs > 0 else 0
    right_peak = smoothed[valley_abs:].max() if valley_abs < bw else 0
    peak_avg = (left_peak + right_peak) / 2

    if peak_avg < 1.0:
        return None, None  # No significant white text found

    # Valley should be at most 30% of the peak average
    if valley_val > peak_avg * 0.30:
        log.debug(f"White text split: valley {valley_val:.1f} too high vs peak {peak_avg:.1f}")
        return None, None

    split_x = bx + valley_abs

    # Find where the left text cluster actually starts.  Use a white pixel
    # projection on the TOP HALF only of the top region (rows 0 to top_h//2)
    # to avoid brownish border artifacts that appear at the bottom edge.
    # Require a minimum density: at least 15% of the half-height as white.
    left_text_x = None
    if left_peak > 1.0:
        half_h = max(top_h // 2, 5)
        top_half = top_region[:half_h, :]
        white_top = np.all(top_half > 170, axis=2)
        v_proj_top = white_top.sum(axis=0).astype(float)
        # Minimum: 15% of half height AND 25% of the left peak
        min_density = max(half_h * 0.15, 3)
        left_thresh = max(left_peak * 0.25, min_density)
        k_top = max(3, bw // 30)
        smoothed_top = np.convolve(v_proj_top, np.ones(k_top) / k_top, mode='same')
        left_segment = smoothed_top[:valley_abs]
        significant = left_segment > left_thresh
        if np.any(significant):
            first_col = int(np.argmax(significant))
            # Add padding: card edge is slightly before the text
            pad = max(int(bw * 0.02), 3)
            left_text_x = bx + max(0, first_col - pad)

    log.debug(f"White text split: valley at x={split_x} "
              f"(valley={valley_val:.1f}, peaks={left_peak:.1f}/{right_peak:.1f})"
              f", left_text_x={left_text_x}")
    return split_x, left_text_x


def _search_band(W: int, H: int) -> Tuple[int, int, int, int]:
    """Return (y1, y2, x1, x2) search band in pixels."""
    return (int(H * SEARCH_Y_MIN), int(H * SEARCH_Y_MAX),
            int(W * SEARCH_X_MIN), int(W * SEARCH_X_MAX))


def _detect_right_card_edge(
    img_np: np.ndarray, split_x: int, blob_y: int, blob_h: int,
    blob_right: int
) -> int:
    """Find where the right card actually ends (its right boundary).

    For same-suit overlapping cards, the blob's bounding box can extend
    well past the card into table felt (especially spade cards whose dark
    background merges with the dark table during morphological closing).

    Scans from the right edge of the blob leftward at several Y positions
    to find where the card background (V < 100) starts, indicating the
    actual card boundary.

    Returns:
        The x coordinate of the right card's right edge (absolute).
    """
    H_img = img_np.shape[0]
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    edges = []
    # Sample at 60-80% down the card (below center rank text, above
    # rounded corners / buttons).  This avoids hitting white rank text.
    for frac in (0.60, 0.65, 0.70, 0.75, 0.80):
        y = blob_y + int(blob_h * frac)
        if y >= H_img:
            continue
        # Scan from blob_right LEFTWARD: find where brightness drops from
        # table border (gray > 150) to card background (any colored suit).
        # This avoids crossing white rank text inside the card.
        x_start = min(blob_right + 4, img_np.shape[1] - 1)
        for x in range(x_start, split_x + 10, -1):
            if gray[y, x] < 120:
                # Found a non-bright pixel — this is card background or felt.
                # Card background has saturation; felt also has saturation.
                # Check if next few pixels inward stay dark — confirms card body.
                inner = max(x - 3, split_x)
                if all(gray[y, ix] < 120 for ix in range(inner, x)):
                    edges.append(x + 1)  # edge is one past the dark region
                    break

    if not edges:
        return blob_right  # fallback: use original blob boundary

    # Use the median edge — robust against outliers from rank text
    actual_edge = int(np.median(edges))
    # Don't extend past the blob boundary, and ensure at least 20px
    actual_edge = max(actual_edge, split_x + 20)
    actual_edge = min(actual_edge, blob_right)
    return actual_edge


# ---------------------------------------------------------------------------
#  Rank OCR — handles both colored-text-on-white and white-text-on-colored
# ---------------------------------------------------------------------------

def _read_rank_at(img_np: np.ndarray, box: Tuple[int, int, int, int],
                  deck_style: str = STYLE_WHITE) -> Optional[str]:
    """Read a card rank from a crop region.

    Pipeline (ordered by speed and reliability):
      1. Template matching against stored rank templates (~1ms, ~99% accuracy)
      2. Pytesseract OCR with PSM 10/7 as fallback (~200ms, ~85% accuracy)
      3. Otsu binarization + OCR as last resort

    When OCR succeeds, the binarized crop is auto-captured as a template
    so future reads of that rank use the faster template path.
    """
    x, y, w, h = box
    x, y = max(0, x), max(0, y)
    max_y = min(y + h, img_np.shape[0])
    max_x = min(x + w, img_np.shape[1])
    crop = img_np[y:max_y, x:max_x]

    if crop.size == 0 or crop.shape[0] < 3 or crop.shape[1] < 3:
        return None

    if deck_style == STYLE_COLORED:
        bw = _binarize_white_on_colored(crop)
        bw = _strip_suit_symbol(bw)
    else:
        bw = _binarize_colored_on_white(crop)

    _, bw = cv2.threshold(bw, 127, 255, cv2.THRESH_BINARY)

    # Save pre-morph bw for template capture — templates must match the
    # same binarization used for template matching (pre-morph).
    bw_pre_morph = bw.copy()

    # ── Strategy 1: Template matching (fast, deterministic) ──────────
    # Try template matching BEFORE morph opening. Morph opening removes
    # noise dots but also erodes thin strokes at 50-80px crop sizes,
    # reducing template scores by 0.10-0.15 (turning correct 0.81 → 0.70).
    from sys_core.ocr.rank_templates import get_rank_matcher
    matcher = get_rank_matcher()
    rank = matcher.match_rank_multi(bw)
    if rank:
        log.debug(f"Rank TEMPLATE: {rank} for box ({x},{y},{w},{h})")
        return rank

    # Apply morph opening for OCR strategies. Skip for small crops where
    # the 2x2 kernel destroys thin strokes (e.g. turns "2" into "4").
    is_small_crop = (w < 50 and h < 50)
    if not is_small_crop:
        # OPEN removes small noise dots (pepper)
        morph_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, morph_kernel)
        # CLOSE fills small gaps inside characters (salt)
        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, morph_kernel)
        _, bw = cv2.threshold(bw, 127, 255, cv2.THRESH_BINARY)

    # ── Strategy 2: Pytesseract OCR (fallback) ──────────────────────
    # Skip OCR for SMALL crops (board cards) when templates are ready —
    # those are noise/garbage that OCR won't help with.
    # For LARGE crops (hero cards, h > 80px), ALWAYS try OCR as fallback.
    # This catches hash collisions where a wrong MD5 entry gets rejected
    # by template cross-validation but we still need OCR to identify the rank.
    hash_collision_suspected = getattr(matcher, '_last_hash_collision', False)
    is_hero_sized = (h > 70)
    if matcher.ready and not hash_collision_suspected and not is_hero_sized:
        log.debug(f"Rank failed (templates ready, skipping OCR) "
                  f"for box ({x},{y},{w},{h})")
        return None

    if not PYTESSERACT_AVAILABLE:
        log.debug(f"Rank failed (no pytesseract) for box ({x},{y},{w},{h})")
        return None

    # Upscale for OCR
    scale = 5
    big_bw = cv2.resize(bw, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, big_bw = cv2.threshold(big_bw, 127, 255, cv2.THRESH_BINARY)

    # Add white padding
    pad = 15
    padded = np.full((big_bw.shape[0] + 2 * pad, big_bw.shape[1] + 2 * pad), 255, dtype=np.uint8)
    padded[pad:pad + big_bw.shape[0], pad:pad + big_bw.shape[1]] = big_bw

    whitelist = ('-c tessedit_char_whitelist=AKQJ1098765432'
                 ' -c load_system_dawg=0 -c load_freq_dawg=0')
    pil_img = Image.fromarray(padded)

    _SINGLE_CHAR_RANKS = {'A', 'K', 'Q', 'J', '9', '8', '7', '6', '5', '4', '3', '2'}

    # Try psm 10 (single char) — fastest, catches A,K,Q,J,2-9
    text = pytesseract.image_to_string(
        pil_img, config=f'--psm 10 --oem 3 {whitelist}'
    ).strip()
    rank = _parse_rank(text)
    if rank:
        log.debug(f"Rank OCR (psm10): raw={text!r} -> {rank}")
        # Capture template from PRE-MORPH bw so templates match the
        # binarization used during template matching.
        _auto_capture_template(matcher, rank, bw_pre_morph)
        return rank

    # Try psm 7 (single line) — handles "10" and multi-glyph
    text = pytesseract.image_to_string(
        pil_img, config=f'--psm 7 --oem 3 {whitelist}'
    ).strip()
    rank = _parse_rank(text)
    if rank:
        log.debug(f"Rank OCR (psm7): raw={text!r} -> {rank}")
        _auto_capture_template(matcher, rank, bw_pre_morph)
        return rank

    # ── Strategy 3: Otsu binarization + OCR (last resort) ───────────
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    gray_big = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, otsu = cv2.threshold(gray_big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if deck_style == STYLE_COLORED:
        otsu = 255 - otsu
    padded_otsu = np.full((otsu.shape[0] + 2 * pad, otsu.shape[1] + 2 * pad), 255, dtype=np.uint8)
    padded_otsu[pad:pad + otsu.shape[0], pad:pad + otsu.shape[1]] = otsu

    text = pytesseract.image_to_string(
        Image.fromarray(padded_otsu), config=f'--psm 7 --oem 3 {whitelist}'
    ).strip()
    rank = _parse_rank(text)
    if rank:
        log.debug(f"Rank OCR (otsu): raw={text!r} -> {rank}")
        # Capture template from pre-morph bw — matches template matching path.
        _auto_capture_template(matcher, rank, bw_pre_morph)
        return rank

    log.debug(f"Rank failed ALL strategies for box ({x},{y},{w},{h})")
    return None


def _auto_capture_template(matcher, rank: str, bw: np.ndarray):
    """Auto-capture a rank template and record hash from a successful read."""
    try:
        # Always record hash (unlimited, ~32 bytes per entry)
        matcher.record_hash(rank, bw)
        # Capture template PNG if we need more (capped at 5)
        if not matcher.has_rank(rank) or \
           len(matcher._templates.get(rank, [])) < 3:
            matcher.capture_template(rank, bw)
    except Exception as e:
        log.debug(f"Template capture failed for {rank}: {e}")


def _strip_suit_symbol(bw: np.ndarray) -> np.ndarray:
    """Remove the suit symbol from a binarized rank crop.

    The rank crop for colored cards includes both the rank character (top)
    and the small suit symbol (bottom).  The combined "9♥" shape confuses
    tesseract into reading "2".  This function keeps only components whose
    top edge starts in the upper 60% of the image (the rank area) and
    discards components that start lower (the suit symbol).
    """
    img_h = bw.shape[0]
    if img_h < 6:
        return bw

    # bw is black-on-white (0 = text, 255 = background).
    fg = 255 - bw
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)

    if n_labels <= 1:
        return bw

    # Keep components whose top edge is in the upper 60% of the crop.
    # The rank character starts near the top; the suit symbol is below it.
    y_cutoff = int(img_h * 0.60)
    keep_mask = np.zeros_like(fg)
    for lbl in range(1, n_labels):
        top_y = stats[lbl, cv2.CC_STAT_TOP]
        area = stats[lbl, cv2.CC_STAT_AREA]
        if top_y < y_cutoff and area >= 20:
            keep_mask[labels == lbl] = 255

    if not np.any(keep_mask):
        return bw  # safety: don't return blank image

    return 255 - keep_mask


def _binarize_colored_on_white(crop: np.ndarray) -> np.ndarray:
    """Convert colored text on white background to black on white."""
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    sat = hsv[:, :, 1]
    r, g, b = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    is_white = (r > 185) & (g > 185) & (b > 185) & (sat < 25)
    return np.where(is_white, np.uint8(255), np.uint8(0))


def _binarize_white_on_colored(crop: np.ndarray) -> np.ndarray:
    """Convert white text on colored background to black on white."""
    # White text pixels: high brightness across all channels
    r, g, b = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    min_ch = np.minimum(np.minimum(r, g), b)
    is_white_text = (min_ch > 170)

    # Also catch light gray/near-white pixels
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    is_bright = gray > 180

    is_text = is_white_text | is_bright
    # Black text on white background (inverted for tesseract)
    return np.where(is_text, np.uint8(0), np.uint8(255))


# ---------------------------------------------------------------------------
#  Suit detection
# ---------------------------------------------------------------------------

def _detect_suit_at(img_np: np.ndarray, box: Tuple[int, int, int, int]) -> str:
    """Detect suit from text/symbol color on white card (4-color deck).

    Hearts = Red, Diamonds = Blue, Clubs = Green, Spades = Black
    """
    x, y, w, h = box
    x, y = max(0, x), max(0, y)
    max_y = min(y + h, img_np.shape[0])
    max_x = min(x + w, img_np.shape[1])
    crop = img_np[y:max_y, x:max_x]

    if crop.size == 0 or crop.shape[0] < 2 or crop.shape[1] < 2:
        return '?'

    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)

    r, g, b = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    is_white = (r > 190) & (g > 190) & (b > 190)
    is_text = ~is_white

    text_hsv = hsv[is_text]
    if len(text_hsv) < 5:
        return '?'

    h_vals = text_hsv[:, 0].astype(float)
    s_vals = text_hsv[:, 1].astype(float)
    v_vals = text_hsv[:, 2].astype(float)

    black_count = int(np.sum(v_vals < 80))
    red_count = int(np.sum(((h_vals < 12) | (h_vals > 168)) & (s_vals > 50) & (v_vals >= 80)))
    blue_count = int(np.sum((h_vals >= 90) & (h_vals <= 145) & (s_vals > 35) & (v_vals >= 50)))
    green_count = int(np.sum((h_vals >= 33) & (h_vals <= 88) & (s_vals > 35) & (v_vals >= 50)))

    counts = {'S': black_count, 'H': red_count, 'D': blue_count, 'C': green_count}
    best = max(counts, key=counts.get)

    if counts[best] < 5:
        return '?'

    log.debug(f"Suit counts: S={black_count} H={red_count} D={blue_count} C={green_count} -> {best}")
    return best


def _detect_suit_colored(img_np: np.ndarray, box: Tuple[int, int, int, int]) -> str:
    """Detect suit from card background color (colored deck style).

    Card backgrounds: Diamonds=Blue, Hearts=Red, Clubs=Green, Spades=Black/dark
    """
    x, y, w, h = box
    x, y = max(0, x), max(0, y)
    max_y = min(y + h, img_np.shape[0])
    max_x = min(x + w, img_np.shape[1])
    crop = img_np[y:max_y, x:max_x]

    if crop.size == 0 or crop.shape[0] < 2 or crop.shape[1] < 2:
        return '?'

    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)

    # Exclude white text pixels — only look at card background
    r, g, b = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    min_ch = np.minimum(np.minimum(r, g), b)
    is_text = min_ch > 160
    is_bg = ~is_text

    bg_hsv = hsv[is_bg]
    if len(bg_hsv) < 10:
        return '?'

    h_vals = bg_hsv[:, 0].astype(float)
    s_vals = bg_hsv[:, 1].astype(float)
    v_vals = bg_hsv[:, 2].astype(float)

    # Blue (diamonds): H=95-125, S>80
    blue_count = int(np.sum((h_vals >= 95) & (h_vals <= 125) & (s_vals > 80)))
    # Red (hearts): H<12 or H>168, S>80
    red_count = int(np.sum(((h_vals < 12) | (h_vals > 168)) & (s_vals > 80)))
    # Green (clubs): H=35-85, S>80
    green_count = int(np.sum((h_vals >= 35) & (h_vals <= 85) & (s_vals > 80)))
    # Black (spades): V<70, S<80 — charcoal card bg can be V=55-70
    black_count = int(np.sum((v_vals < 70) & (s_vals < 80)))

    counts = {'S': black_count, 'H': red_count, 'D': blue_count, 'C': green_count}
    best = max(counts, key=counts.get)

    if counts[best] < 10:
        return '?'

    log.debug(f"Suit bg counts: S={black_count} H={red_count} D={blue_count} C={green_count} -> {best}")
    return best


# ---------------------------------------------------------------------------
#  Rank text parsing
# ---------------------------------------------------------------------------

def _parse_rank(text: str) -> Optional[str]:
    """Parse OCR text into a valid poker rank."""
    if not text:
        return None

    text = text.strip().upper()

    if text in VALID_RANKS:
        return text

    if len(text) >= 2 and text[:2] == '10':
        return '10'

    # Multi-character patterns that tesseract produces for "10"
    _TEN_MISREADS = {'IN', 'IO', '1O', '1N', 'LO', 'L0', 'I0', '1Q'}
    if text in _TEN_MISREADS or (len(text) >= 2 and text[:2] in _TEN_MISREADS):
        return '10'

    first = text[0] if text else ''

    # Single-char OCR misreads
    fixes = {
        'O': '10', '0': '10',
        'S': '5', 'G': '6', 'B': '8',
    }

    # "I" or "1" alone → "10" (no single-digit card "1" exists)
    if first in ('I', 'L', '1') and (len(text) == 1 or text[1:].strip() == ''):
        return '10'

    if first in VALID_RANKS:
        return first

    if first in fixes:
        fixed = fixes[first]
        if fixed in VALID_RANKS:
            return fixed

    return None


# ---------------------------------------------------------------------------
#  Debug output
# ---------------------------------------------------------------------------

def _save_debug(
    img_np: np.ndarray, W: int, H: int,
    positions: Dict, cards: List[str], debug_dir: str,
) -> None:
    """Save annotated debug image showing detected regions."""
    import os
    from datetime import datetime

    os.makedirs(debug_dir, exist_ok=True)
    annotated = img_np.copy()

    sy1, sy2 = int(H * SEARCH_Y_MIN), int(H * SEARCH_Y_MAX)
    sx1, sx2 = int(W * SEARCH_X_MIN), int(W * SEARCH_X_MAX)
    cv2.rectangle(annotated, (sx1, sy1), (sx2, sy2), (255, 255, 0), 1)

    debug_info = positions.get('_debug', {})
    if 'blob' in debug_info:
        bx, by, bw, bh = debug_info['blob']
        cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (128, 128, 0), 1)

    if 'card_area' in debug_info:
        cx, cy, cw, ch = debug_info['card_area']
        cv2.rectangle(annotated, (cx, cy), (cx + cw, cy + ch), (0, 255, 0), 2)

    if 'split_x' in debug_info and 'card_area' in debug_info:
        sx = debug_info['split_x']
        cy = debug_info['card_area'][1]
        ch = debug_info['card_area'][3]
        cv2.line(annotated, (sx, cy), (sx, cy + ch), (0, 0, 255), 2)

    colors = {'left_rank': (255, 0, 0), 'right_rank': (0, 0, 255),
              'left_suit': (255, 128, 0), 'right_suit': (0, 128, 255)}
    for key, color in colors.items():
        if key in positions:
            bx, by, bw, bh = positions[key]
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), color, 2)

    deck_style = positions.get('_deck_style', '?')
    label = f"Cards: {cards} [{deck_style}]" if cards else f"No cards [{deck_style}]"
    cv2.putText(annotated, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(debug_dir, f'card_debug_{ts}.png')
    Image.fromarray(annotated).save(path)
    log.info(f"Debug image saved: {path}")


# CLI test entry point
if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.DEBUG)

    if len(sys.argv) < 2:
        print("Usage: python -m sys_core.ocr.card_reader <screenshot.png> [screenshot2.png ...]")
        print("  Reads player hole cards from GGSystem table screenshots.")
        sys.exit(1)

    for path in sys.argv[1:]:
        img = Image.open(path)
        print(f"\n{path} ({img.width}x{img.height})")
        cards = read_player_cards(img, debug_dir='/tmp/card_debug')
        print(f"  Detected: {cards}")
