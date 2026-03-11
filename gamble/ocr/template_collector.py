"""
Automatic card template collector.

During normal gameplay, when the existing Python OCR successfully identifies
a card (e.g. "AH"), this module captures the actual card corner from the
screenshot and saves it as a real template PNG.

Over time, all 52 synthetic templates get replaced with real GGPoker captures.
This bootstraps the Rust OCR engine using the existing working Python detection.

Usage:
    collector = TemplateCollector()

    # Call this whenever Python OCR successfully detects cards
    collector.collect_from_detection(table_img, detected_cards, card_regions)

    # Check progress
    print(collector.status())  # "Real: 12/52, Synthetic: 40/52"
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_TEMPLATE_DIR = PROJECT_ROOT / 'poker_ocr' / 'assets' / 'card_templates'

# All 52 cards
RANKS = ['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']
SUITS = ['H', 'D', 'C', 'S']
ALL_CARDS = [f"{r}{s}" for r in RANKS for s in SUITS]

# Corner crop size - the top-left corner of a card showing rank + suit
CORNER_WIDTH = 29
CORNER_HEIGHT = 43


class TemplateCollector:
    """Collects real card templates from live gameplay."""

    def __init__(self, template_dir: Optional[str] = None):
        self.template_dir = Path(template_dir) if template_dir else DEFAULT_TEMPLATE_DIR
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.template_dir / 'manifest.json'
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> Dict:
        """Load manifest tracking which templates are real vs synthetic."""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"real": {}, "synthetic": list(ALL_CARDS)}

    def _save_manifest(self):
        with open(self.manifest_path, 'w') as f:
            json.dump(self.manifest, f, indent=2)

    def collect_from_screenshot(
        self,
        table_img: Image.Image,
        detected_cards: List[str],
        card_regions: List[Tuple[int, int, int, int]],
    ) -> int:
        """Collect card templates from a successful detection.

        Args:
            table_img: The full table image (PIL Image or numpy array)
            detected_cards: Cards identified by Python OCR, e.g. ['AH', 'KS']
            card_regions: Bounding boxes [(x, y, w, h), ...] for each card

        Returns:
            Number of new templates collected
        """
        if len(detected_cards) != len(card_regions):
            return 0

        if isinstance(table_img, np.ndarray):
            table_img = Image.fromarray(table_img)

        collected = 0
        for card_name, (x, y, w, h) in zip(detected_cards, card_regions):
            card_name = card_name.upper()
            if card_name not in ALL_CARDS:
                continue

            # Skip if we already have a high-quality real template
            if card_name in self.manifest.get("real", {}) and \
               self.manifest["real"][card_name].get("quality", 0) >= 3:
                continue

            try:
                corner = self._extract_corner(table_img, x, y, w, h)
                if corner is None:
                    continue

                # Validate: corner should be mostly white background with some dark content
                if not self._validate_corner(corner):
                    continue

                # Save template
                out_path = self.template_dir / f"{card_name}.png"
                corner.save(str(out_path))

                # Update manifest
                quality = self.manifest.get("real", {}).get(card_name, {}).get("quality", 0) + 1
                if "real" not in self.manifest:
                    self.manifest["real"] = {}
                self.manifest["real"][card_name] = {
                    "collected_at": time.strftime("%Y%m%d_%H%M%S"),
                    "quality": min(quality, 5),
                    "source_region": [x, y, w, h],
                }

                # Remove from synthetic list
                if "synthetic" in self.manifest and card_name in self.manifest["synthetic"]:
                    self.manifest["synthetic"].remove(card_name)

                self._save_manifest()
                collected += 1
                log.info(f"Collected real template: {card_name} (quality={quality})")

            except Exception as e:
                log.debug(f"Failed to collect {card_name}: {e}")

        return collected

    def _extract_corner(self, table_img: Image.Image, x: int, y: int, w: int, h: int) -> Optional[Image.Image]:
        """Extract the top-left corner of a card (rank + suit symbol)."""
        # The corner is the top-left portion of the card region
        # Crop a small area from the card's top-left
        corner_w = min(CORNER_WIDTH, w)
        corner_h = min(CORNER_HEIGHT, h)

        if corner_w < 15 or corner_h < 30:
            return None

        try:
            corner = table_img.crop((x, y, x + corner_w, y + corner_h))
            # Resize to standard size
            corner = corner.resize((CORNER_WIDTH, CORNER_HEIGHT), Image.LANCZOS)
            return corner.convert('RGB')
        except Exception:
            return None

    def _validate_corner(self, corner: Image.Image) -> bool:
        """Check if extracted corner looks like a card corner."""
        arr = np.array(corner)

        # Should have white background (mean brightness > 150)
        mean_brightness = arr.mean()
        if mean_brightness < 120:
            return False

        # Should have some dark content (rank/suit text)
        dark_pixels = (arr.mean(axis=2) < 100).sum()
        if dark_pixels < 20:
            return False  # Too uniform, probably just white

        # Should have mostly white pixels
        white_pixels = (arr.mean(axis=2) > 200).sum()
        total_pixels = arr.shape[0] * arr.shape[1]
        if white_pixels < total_pixels * 0.3:
            return False  # Not enough white background

        return True

    def collect_from_white_regions(
        self,
        table_img: Image.Image,
        card_name: str,
        white_rect: Tuple[int, int, int, int],
    ) -> bool:
        """Collect a single card template from a detected white card region.

        Use this when you know what card it is (from any detection method)
        and have found the white rectangle bounding it.
        """
        return self.collect_from_screenshot(
            table_img, [card_name], [white_rect]
        ) > 0

    def status(self) -> str:
        """Return human-readable collection status."""
        real = self.manifest.get("real", {})
        real_count = len(real)
        synthetic_count = 52 - real_count
        missing = [c for c in ALL_CARDS if c not in real]

        status = f"Real: {real_count}/52, Synthetic: {synthetic_count}/52"
        if missing and len(missing) <= 10:
            status += f"\nMissing: {', '.join(missing)}"
        elif missing:
            status += f"\nMissing: {len(missing)} cards"
        else:
            status += "\nAll 52 templates collected!"

        return status

    def get_real_count(self) -> int:
        return len(self.manifest.get("real", {}))

    def is_complete(self) -> bool:
        return self.get_real_count() >= 52

    def needs_card(self, card_name: str) -> bool:
        """Check if we still need a real template for this card."""
        card_name = card_name.upper()
        real = self.manifest.get("real", {})
        return card_name not in real


# Singleton
_collector = None

def get_collector() -> TemplateCollector:
    global _collector
    if _collector is None:
        _collector = TemplateCollector()
    return _collector
