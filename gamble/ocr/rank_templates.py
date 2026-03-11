"""Template-based rank recognition for poker cards.

Replaces pytesseract OCR with deterministic template matching for card ranks.
Since GGPoker renders cards with a fixed font, the same rank always produces
identical pixels.

Architecture (three-tier cascade):
    1. Binarize the rank crop (white text on colored bg -> black on white)
    2. Extract the largest connected component (the rank glyph)
    3. Normalize to a fixed size (TEMPLATE_W x TEMPLATE_H)
    4. **Tier 1**: Exact byte hash lookup — O(1), 100% when binarization is deterministic
    5. **Tier 2**: dHash perceptual matching (Hamming distance ≤ 5) — catches 1-3px drift
    6. **Tier 3**: cv2.matchTemplate TM_CCOEFF_NORMED — probabilistic fallback

Templates are auto-captured from successful reads during gameplay and stored
as small PNG files. The system bootstraps itself: first few reads use
pytesseract, then switch to template matching once templates are captured.

Usage:
    from gamble.ocr.rank_templates import get_rank_matcher
    matcher = get_rank_matcher()
    rank = matcher.match_rank(binarized_crop)  # returns 'A', 'K', ..., '2' or None
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)

# Normalized template dimensions (after extracting glyph bounding box)
TEMPLATE_W = 40
TEMPLATE_H = 56

# All valid ranks
RANKS = ['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']

# Minimum match score to accept a template match (TM_CCOEFF_NORMED, 0-1).
# Balance: high enough to avoid confusing similar-looking ranks (5/8, 2/3,
# 6/9), low enough to catch correct matches with slight rendering variance.
# The margin check (MIN_MATCH_MARGIN) prevents ambiguous matches.
MIN_MATCH_SCORE = 0.45

# Minimum margin between best and second-best match scores.
# Prevents ambiguous matches where two ranks score similarly.
MIN_MATCH_MARGIN = 0.08

# Template storage directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
TEMPLATE_DIR = PROJECT_ROOT / 'gamble' / 'ocr' / 'rank_template_data'

# How many successful captures before we trust a template.
# 1 is safe: capture_template() cross-validates via hash comparison and
# consensus scoring before saving. 2 caused a cold-start problem: first
# hand played got zero template-matching benefit.
MIN_CAPTURES_FOR_TRUST = 1


def _extract_glyph(bw: np.ndarray) -> Optional[np.ndarray]:
    """Extract the largest connected component (the rank character) from a
    binarized black-on-white image.

    Returns the glyph region cropped tightly, or None if no glyph found.
    """
    if bw is None or bw.size == 0:
        return None

    # Foreground = black pixels (the text)
    fg = 255 - bw
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)

    if n_labels <= 1:
        return None

    # Find the largest component (skip label 0 = background)
    best_label = -1
    best_area = 0
    for lbl in range(1, n_labels):
        area = stats[lbl, cv2.CC_STAT_AREA]
        if area > best_area:
            best_area = area
            best_label = lbl

    if best_label < 0 or best_area < 10:
        return None

    # For "10", we need to include the second-largest component too.
    # Check if there are 2 large components that together form "10".
    components = []
    for lbl in range(1, n_labels):
        area = stats[lbl, cv2.CC_STAT_AREA]
        if area >= best_area * 0.15:  # at least 15% of largest
            components.append(lbl)

    if len(components) >= 2:
        # Multiple significant components - include all of them (handles "10")
        mask = np.zeros_like(fg)
        for lbl in components:
            mask[labels == lbl] = 255
    else:
        # Single component
        mask = np.zeros_like(fg)
        mask[labels == best_label] = 255

    # Crop to bounding box of the mask
    coords = cv2.findNonZero(mask)
    if coords is None:
        return None
    x, y, w, h = cv2.boundingRect(coords)

    # Add small padding
    pad = 2
    x = max(0, x - pad)
    y = max(0, y - pad)
    w = min(mask.shape[1] - x, w + 2 * pad)
    h = min(mask.shape[0] - y, h + 2 * pad)

    glyph = mask[y:y+h, x:x+w]
    if glyph.size == 0 or glyph.shape[0] < 3 or glyph.shape[1] < 3:
        return None

    # Invert back: black glyph on white background
    return 255 - glyph


def _normalize_glyph(glyph: np.ndarray) -> np.ndarray:
    """Resize a glyph image to the standard template size while preserving
    aspect ratio (pad with white to fill).
    """
    h, w = glyph.shape[:2]
    if h == 0 or w == 0:
        return np.full((TEMPLATE_H, TEMPLATE_W), 255, dtype=np.uint8)

    # Scale to fit within TEMPLATE_W x TEMPLATE_H
    scale = min(TEMPLATE_W / w, TEMPLATE_H / h)
    new_w = max(int(w * scale), 1)
    new_h = max(int(h * scale), 1)

    resized = cv2.resize(glyph, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Center on white canvas
    canvas = np.full((TEMPLATE_H, TEMPLATE_W), 255, dtype=np.uint8)
    x_off = (TEMPLATE_W - new_w) // 2
    y_off = (TEMPLATE_H - new_h) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized

    # Re-binarize to ensure clean black/white
    _, canvas = cv2.threshold(canvas, 127, 255, cv2.THRESH_BINARY)
    return canvas


class RankTemplateMatcher:
    """Matches binarized rank crops against stored templates.

    Auto-captures templates from successful OCR reads. Once all 13 ranks
    have templates, pytesseract is no longer needed for rank detection.
    """

    def __init__(self, template_dir: Optional[Path] = None):
        self.template_dir = template_dir or TEMPLATE_DIR
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.template_dir / 'manifest.json'
        self.hash_store_path = self.template_dir / 'hash_store.json'

        # rank -> list of normalized template images (multiple captures per rank)
        self._templates: Dict[str, List[np.ndarray]] = {}
        # rank -> averaged/consensus template
        self._consensus: Dict[str, np.ndarray] = {}
        # Manifest tracking capture counts
        self._manifest: Dict = {}

        # Tier 1: exact byte hash -> rank (all individual template variants)
        # Key = md5 hex digest of normalized glyph bytes
        self._exact_hash: Dict[bytes, str] = {}
        # Persistent hash store: md5_hex -> rank (unlimited, survives restarts)
        self._hash_store: Dict[str, str] = {}
        # Tier 2: dHash -> rank (all individual template variants)
        self._dhash_table: Dict[int, str] = {}

        self._load()

    def _load(self):
        """Load templates, manifest, and hash store from disk."""
        # Load manifest
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path) as f:
                    self._manifest = json.load(f)
            except Exception:
                self._manifest = {}

        # Load persistent hash store
        if self.hash_store_path.exists():
            try:
                with open(self.hash_store_path) as f:
                    self._hash_store = json.load(f)
            except Exception:
                self._hash_store = {}

        # Load template images
        for rank in RANKS:
            safe_name = rank if rank != '10' else 'T'
            pattern = f'rank_{safe_name}_*.png'
            files = sorted(self.template_dir.glob(pattern))
            templates = []
            for fp in files:
                img = cv2.imread(str(fp), cv2.IMREAD_GRAYSCALE)
                if img is not None and img.shape == (TEMPLATE_H, TEMPLATE_W):
                    templates.append(img)
            if templates:
                self._templates[rank] = templates
                self._build_consensus(rank)

        loaded = {r: len(t) for r, t in self._templates.items()}
        if loaded:
            log.info(f"Loaded rank templates: {loaded}")

        self._build_hash_tables()

    def _build_hash_tables(self):
        """Build exact-hash and dHash lookup tables from templates + hash store."""
        self._exact_hash.clear()
        self._dhash_table.clear()

        # Add from template PNG files
        for rank, templates in self._templates.items():
            if not self._manifest.get(rank, {}).get('trusted', False):
                continue
            for t in templates:
                _, clean = cv2.threshold(t, 127, 255, cv2.THRESH_BINARY)
                key = clean.tobytes()
                self._exact_hash[key] = rank
                dh = _dhash(clean)
                self._dhash_table[dh] = rank

        # Add consensus templates
        for rank, consensus in self._consensus.items():
            if not self._manifest.get(rank, {}).get('trusted', False):
                continue
            _, clean = cv2.threshold(consensus, 127, 255, cv2.THRESH_BINARY)
            key = clean.tobytes()
            self._exact_hash[key] = rank
            dh = _dhash(clean)
            self._dhash_table[dh] = rank

        # Add from persistent hash store (unlimited glyph variants)
        # Hash store maps md5_hex -> rank.  We need to also index by raw bytes,
        # so we store a parallel md5->rank lookup for the match_rank_hash method.
        self._md5_to_rank: Dict[str, str] = dict(self._hash_store)

        n_templates = len(self._exact_hash)
        n_store = len(self._hash_store)
        n_dhash = len(self._dhash_table)
        if n_templates or n_store:
            log.info(f"Hash tables: {n_templates} byte-exact, "
                     f"{n_store} md5-store, {n_dhash} dHash")

    def _build_consensus(self, rank: str):
        """Build an averaged consensus template from multiple captures."""
        templates = self._templates.get(rank, [])
        if not templates:
            return

        if len(templates) == 1:
            self._consensus[rank] = templates[0].copy()
            return

        # Average all captures and re-binarize
        acc = np.zeros((TEMPLATE_H, TEMPLATE_W), dtype=np.float32)
        for t in templates:
            acc += t.astype(np.float32)
        avg = (acc / len(templates)).astype(np.uint8)
        _, consensus = cv2.threshold(avg, 127, 255, cv2.THRESH_BINARY)
        self._consensus[rank] = consensus

    def _save_manifest(self):
        with open(self.manifest_path, 'w') as f:
            json.dump(self._manifest, f, indent=2)

    def capture_template(self, rank: str, bw_crop: np.ndarray) -> bool:
        """Capture a rank template from a binarized crop that was successfully
        identified (e.g., by pytesseract).

        Args:
            rank: The identified rank ('A', 'K', ..., '2', '10')
            bw_crop: Binarized black-on-white image of the rank region

        Returns:
            True if template was successfully captured
        """
        if rank not in RANKS:
            return False

        glyph = _extract_glyph(bw_crop)
        if glyph is None:
            return False

        normalized = _normalize_glyph(glyph)

        # Check if this is substantially different from existing templates
        # (avoid storing duplicates)
        existing = self._templates.get(rank, [])
        if len(existing) >= 5:
            # Already have enough captures
            return False

        # Save to disk
        safe_name = rank if rank != '10' else 'T'
        idx = len(existing)
        out_path = self.template_dir / f'rank_{safe_name}_{idx}.png'
        cv2.imwrite(str(out_path), normalized)

        # Update in-memory
        if rank not in self._templates:
            self._templates[rank] = []
        self._templates[rank].append(normalized)
        self._build_consensus(rank)

        # Update manifest
        self._manifest[rank] = {
            'count': len(self._templates[rank]),
            'trusted': len(self._templates[rank]) >= MIN_CAPTURES_FOR_TRUST,
        }
        self._save_manifest()

        # Rebuild hash tables with new template
        self._build_hash_tables()

        log.info(f"Captured rank template: {rank} (#{idx}, "
                 f"total={len(self._templates[rank])})")
        return True

    def match_rank(self, bw_crop: np.ndarray) -> Optional[str]:
        """Match a binarized rank crop against stored templates.

        Args:
            bw_crop: Binarized black-on-white image (rank region, any size)

        Returns:
            Best matching rank string, or None if no confident match
        """
        if not self._consensus:
            return None  # No templates loaded yet

        glyph = _extract_glyph(bw_crop)
        if glyph is None:
            return None

        query = _normalize_glyph(glyph)

        best_rank = None
        best_score = -1.0
        scores = {}

        for rank, template in self._consensus.items():
            # Only use trusted templates (captured at least MIN_CAPTURES_FOR_TRUST times)
            if not self._manifest.get(rank, {}).get('trusted', False):
                continue

            # Template matching with normalized cross-correlation
            result = cv2.matchTemplate(
                query, template, cv2.TM_CCOEFF_NORMED
            )
            score = float(result[0, 0])
            scores[rank] = score

            if score > best_score:
                best_score = score
                best_rank = rank

        if best_score >= MIN_MATCH_SCORE and best_rank is not None:
            # Check margin: best should be clearly better than second-best
            sorted_scores = sorted(scores.values(), reverse=True)
            margin = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else 1.0

            if margin < MIN_MATCH_MARGIN:
                log.debug(f"Template match AMBIGUOUS: {best_rank} "
                          f"score={best_score:.3f} margin={margin:.3f} "
                          f"< {MIN_MATCH_MARGIN}")
                return None

            log.debug(f"Template match: {best_rank} score={best_score:.3f} "
                      f"margin={margin:.3f}")
            return best_rank

        log.debug(f"Template match failed: best={best_rank} "
                  f"score={best_score:.3f} < {MIN_MATCH_SCORE}")
        return None

    def match_rank_hash(self, bw_crop: np.ndarray) -> Optional[str]:
        """Three-tier hash-based matching for maximum accuracy.

        Tier 1a: Exact byte hash lookup (from template PNGs)
        Tier 1b: MD5 hash lookup (from persistent hash store — unlimited variants)
        Tier 2: dHash perceptual matching — catches 1-3px drift
        Tier 3: Falls through to caller for matchTemplate

        Returns rank string or None.
        """
        glyph = _extract_glyph(bw_crop)
        if glyph is None:
            return None

        query = _normalize_glyph(glyph)
        _, query = cv2.threshold(query, 127, 255, cv2.THRESH_BINARY)

        # Tier 1a: Exact byte hash (from template PNGs)
        key = query.tobytes()
        rank = self._exact_hash.get(key)
        if rank is not None:
            log.debug(f"Rank HASH-EXACT: {rank}")
            return rank

        # Tier 1b: MD5 hash (from persistent hash store)
        # Every MD5 hit is cross-validated against consensus templates
        # to catch poisoned entries (wrong rank mappings).
        md5 = hashlib.md5(key).hexdigest()
        rank = self._md5_to_rank.get(md5)
        if rank is not None:
            if self._consensus and rank in self._consensus:
                tmpl = self._consensus[rank]
                result = cv2.matchTemplate(query, tmpl, cv2.TM_CCOEFF_NORMED)
                score = float(result[0, 0])
                if score >= 0.40:
                    log.debug(f"Rank HASH-MD5: {rank} (verified, score={score:.3f})")
                    return rank
                else:
                    # Poisoned entry — try all templates to find correct rank
                    best_r, best_s = None, -1.0
                    for r, c in self._consensus.items():
                        s = float(cv2.matchTemplate(query, c, cv2.TM_CCOEFF_NORMED)[0, 0])
                        if s > best_s:
                            best_s = s
                            best_r = r
                    if best_r and best_s >= 0.55:
                        log.warning(f"MD5 POISONED: hash said {rank} (score={score:.3f})"
                                    f" -> corrected to {best_r} (score={best_s:.3f})")
                        # Fix the poisoned entry in-place
                        self._hash_store[md5] = best_r
                        self._md5_to_rank[md5] = best_r
                        try:
                            with open(self.hash_store_path, 'w') as f:
                                json.dump(self._hash_store, f)
                        except Exception:
                            pass
                        return best_r
                    log.warning(f"MD5 POISONED: hash said {rank} (score={score:.3f})"
                                f" — no good template match, skipping")
                    self._last_hash_collision = True
                    # Fall through to dHash/template
            else:
                log.debug(f"Rank HASH-MD5: {rank} (no consensus to verify)")
                return rank

        # Tier 2: dHash with Hamming distance
        if self._dhash_table:
            query_dh = _dhash(query)
            best_rank = None
            best_dist = 999
            second_dist = 999

            for stored_dh, r in self._dhash_table.items():
                dist = _hamming_distance(query_dh, stored_dh)
                if dist < best_dist:
                    second_dist = best_dist
                    best_dist = dist
                    best_rank = r
                elif dist < second_dist and r != best_rank:
                    second_dist = dist

            max_dhash_dist = 5
            min_dhash_margin = 2
            if (best_rank is not None
                    and best_dist <= max_dhash_dist
                    and (second_dist - best_dist) >= min_dhash_margin):
                log.debug(f"Rank HASH-DHASH: {best_rank} dist={best_dist} "
                          f"margin={second_dist - best_dist}")
                return best_rank

        return None

    def record_hash(self, rank: str, bw_crop: np.ndarray) -> bool:
        """Record a glyph hash in the persistent hash store.

        Only records if the glyph cross-validates against the rank's
        consensus template (score >= 0.40), preventing poisoned entries.
        """
        if rank not in RANKS:
            return False

        glyph = _extract_glyph(bw_crop)
        if glyph is None:
            return False

        normalized = _normalize_glyph(glyph)
        _, normalized = cv2.threshold(normalized, 127, 255, cv2.THRESH_BINARY)

        # Cross-validate before recording
        if self._consensus and rank in self._consensus:
            tmpl = self._consensus[rank]
            result = cv2.matchTemplate(normalized, tmpl, cv2.TM_CCOEFF_NORMED)
            score = float(result[0, 0])
            if score < 0.40:
                log.debug(f"Refusing to record hash for {rank}: "
                          f"template score {score:.3f} < 0.40")
                return False

        md5 = hashlib.md5(normalized.tobytes()).hexdigest()

        if md5 in self._hash_store:
            return False  # Already recorded

        self._hash_store[md5] = rank
        self._md5_to_rank[md5] = rank

        # Persist to disk
        try:
            with open(self.hash_store_path, 'w') as f:
                json.dump(self._hash_store, f)
        except Exception as e:
            log.warning(f"Failed to save hash store: {e}")

        log.debug(f"Recorded hash for {rank} (store size: {len(self._hash_store)})")
        return True

    def match_rank_multi(self, bw_crop: np.ndarray) -> Optional[str]:
        """Match using multiple strategies for maximum reliability.

        Tries (in order):
        1. Hash-based matching (exact hash + dHash)
        2. Standard glyph extraction + matchTemplate
        3. Raw resize + matchTemplate (no glyph extraction)

        Returns the best match across all strategies.
        """
        if not self._consensus and not self._exact_hash:
            return None

        self._last_hash_collision = False

        # Strategy 1: Hash-based matching (Tier 1 + 2)
        hash_result = self.match_rank_hash(bw_crop)

        # Strategy 2: Standard glyph extraction + matchTemplate (Tier 3)
        template_result = self.match_rank(bw_crop)

        if hash_result and template_result:
            if hash_result == template_result:
                return hash_result  # Both agree — high confidence
            # Disagreement: hash says one rank, template says another.
            # Template matching is more reliable than MD5 hash (hash
            # collisions can map different glyphs to the wrong rank).
            log.warning(f"HASH vs TEMPLATE CONFLICT: hash={hash_result} "
                        f"template={template_result} — using template")
            return template_result

        if hash_result:
            # Cross-validate: check that template matching at least weakly
            # agrees with the hash.  If best template score for the hash's
            # rank is very low, this is likely a hash collision.
            if self._consensus and hash_result in self._consensus:
                glyph = _extract_glyph(bw_crop)
                if glyph is not None:
                    query = _normalize_glyph(glyph)
                    _, query = cv2.threshold(query, 127, 255, cv2.THRESH_BINARY)
                    tmpl = self._consensus[hash_result]
                    result = cv2.matchTemplate(query, tmpl, cv2.TM_CCOEFF_NORMED)
                    score = float(result[0, 0])
                    if score < 0.40:
                        # Hash claims this rank but template disagrees.
                        # Try ALL consensus templates to find correct rank.
                        best_alt_rank = None
                        best_alt_score = -1.0
                        for r, c_tmpl in self._consensus.items():
                            if r == hash_result:
                                continue
                            res = cv2.matchTemplate(query, c_tmpl, cv2.TM_CCOEFF_NORMED)
                            s = float(res[0, 0])
                            if s > best_alt_score:
                                best_alt_score = s
                                best_alt_rank = r
                        if best_alt_rank and best_alt_score >= 0.55:
                            log.warning(f"HASH COLLISION FIXED: hash={hash_result} "
                                        f"(score={score:.3f}) → {best_alt_rank} "
                                        f"(score={best_alt_score:.3f})")
                            return best_alt_rank
                        log.warning(f"HASH COLLISION SUSPECT: hash={hash_result} "
                                    f"but template score={score:.3f} < 0.40 — "
                                    f"rejecting hash, falling through to OCR")
                        self._last_hash_collision = True
                        return None  # Fall through to OCR in _read_rank_at
            return hash_result

        if template_result:
            return template_result

        # Strategy 3: Try without glyph extraction (raw resize of full crop)
        if bw_crop.size > 0 and bw_crop.shape[0] >= 3 and bw_crop.shape[1] >= 3:
            raw_normalized = _normalize_glyph(bw_crop)
            best_rank = None
            best_score = -1.0

            scores = {}
            for rank, template in self._consensus.items():
                if not self._manifest.get(rank, {}).get('trusted', False):
                    continue
                result = cv2.matchTemplate(
                    raw_normalized, template, cv2.TM_CCOEFF_NORMED
                )
                score = float(result[0, 0])
                scores[rank] = score
                if score > best_score:
                    best_score = score
                    best_rank = rank

            if best_score >= MIN_MATCH_SCORE and best_rank:
                sorted_scores = sorted(scores.values(), reverse=True)
                margin = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else 1.0
                if margin >= MIN_MATCH_MARGIN:
                    log.debug(f"Raw template match: {best_rank} "
                              f"score={best_score:.3f} margin={margin:.3f}")
                    return best_rank

        return None

    @property
    def ready(self) -> bool:
        """True if we have trusted templates for all 13 ranks."""
        return all(
            self._manifest.get(r, {}).get('trusted', False)
            for r in RANKS
        )

    @property
    def coverage(self) -> str:
        """Human-readable coverage status."""
        have = len(self._consensus)
        trusted = sum(1 for r in RANKS
                      if self._manifest.get(r, {}).get('trusted', False))
        missing = [r for r in RANKS if r not in self._consensus]
        s = f"Templates: {have}/13 ranks, {trusted}/13 trusted"
        if missing:
            s += f", missing: {missing}"
        return s

    def has_rank(self, rank: str) -> bool:
        return rank in self._consensus


def _dhash(img: np.ndarray, hash_size: int = 16) -> int:
    """Compute a difference hash (dHash) of a grayscale image.

    Resizes to (hash_size+1, hash_size), compares adjacent horizontal pixels,
    returns a hash_size*hash_size bit integer.
    """
    resized = cv2.resize(img, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    # Compare: is pixel to the left brighter than pixel to the right?
    diff = resized[:, 1:] > resized[:, :-1]
    # Pack into integer
    h = 0
    for bit in diff.flatten():
        h = (h << 1) | int(bit)
    return h


def _hamming_distance(a: int, b: int) -> int:
    """Count differing bits between two integers."""
    return bin(a ^ b).count('1')


# Singleton
_matcher: Optional[RankTemplateMatcher] = None


def get_rank_matcher() -> RankTemplateMatcher:
    global _matcher
    if _matcher is None:
        _matcher = RankTemplateMatcher()
    return _matcher
