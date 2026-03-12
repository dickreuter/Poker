#!/usr/bin/env python3
"""
Generate 52 card templates matching GGSystem card corner style.

Creates synthetic rank+suit corner images that match the existing templates
found in sys_core/tests/test_cards/ (20x43 or 29x43 pixels, white background,
dark rank text with suit symbol below).

These templates are used by the Rust OCR engine for card detection via
template matching (TM_SQDIFF_NORMED).

Usage:
    python scripts/generate_card_templates.py
    python scripts/generate_card_templates.py --output poker_ocr/assets/card_templates/
"""

import argparse
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# Card definitions
RANKS = ['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']
SUITS = {
    'H': {'symbol': '\u2665', 'color': (180, 30, 30)},   # Hearts - dark red
    'D': {'symbol': '\u2666', 'color': (180, 30, 30)},   # Diamonds - dark red
    'C': {'symbol': '\u2663', 'color': (50, 50, 50)},    # Clubs - dark/black
    'S': {'symbol': '\u2660', 'color': (50, 50, 50)},    # Spades - dark/black
}

# Template dimensions matching existing templates
# Narrow ranks (2-7, 9): 20x43
# Wide ranks (A, K, Q, J, 8, 10): 29x43
NARROW_RANKS = {'2', '3', '4', '5', '6', '7', '9'}
WIDE_RANKS = {'A', 'K', 'Q', 'J', '8', '10'}
TEMPLATE_HEIGHT = 43
NARROW_WIDTH = 20
WIDE_WIDTH = 29

# Background color (white card)
BG_COLOR = (255, 255, 255)


def find_font(size: int):
    """Find a suitable font for card rendering."""
    # Try common macOS fonts that look like poker card text
    font_paths = [
        '/System/Library/Fonts/Helvetica.ttc',
        '/System/Library/Fonts/HelveticaNeue.ttc',
        '/System/Library/Fonts/SFNSText.ttf',
        '/System/Library/Fonts/SFCompact.ttf',
        '/System/Library/Fonts/SFNS.ttf',
        '/Library/Fonts/Arial.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/System/Library/Fonts/Supplemental/Helvetica.ttc',
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    # Fallback to default
    return ImageFont.load_default()


def find_symbol_font(size: int):
    """Find a font that renders suit symbols well."""
    # Suit symbols are Unicode, need a font that supports them
    font_paths = [
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
        '/System/Library/Fonts/Apple Symbols.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        '/System/Library/Fonts/SFNS.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_card_template(rank: str, suit: str, output_dir: Path) -> Path:
    """Generate a single card corner template."""
    suit_info = SUITS[suit]
    is_wide = rank in WIDE_RANKS
    width = WIDE_WIDTH if is_wide else NARROW_WIDTH
    height = TEMPLATE_HEIGHT

    img = Image.new('RGB', (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Rank text - positioned at top
    rank_size = 18 if rank != '10' else 14
    rank_font = find_font(rank_size)

    # Get rank text bounds
    rank_bbox = draw.textbbox((0, 0), rank, font=rank_font)
    rank_w = rank_bbox[2] - rank_bbox[0]
    rank_h = rank_bbox[3] - rank_bbox[1]

    # Center rank horizontally, position near top
    rank_x = (width - rank_w) // 2
    rank_y = 1 - rank_bbox[1]  # Offset by top bearing

    # Rank color matches suit color (red for H/D, black for S/C)
    draw.text((rank_x, rank_y), rank, fill=suit_info['color'], font=rank_font)

    # Suit symbol - positioned below rank
    suit_size = 16
    suit_font = find_symbol_font(suit_size)
    symbol = suit_info['symbol']

    suit_bbox = draw.textbbox((0, 0), symbol, font=suit_font)
    suit_w = suit_bbox[2] - suit_bbox[0]

    suit_x = (width - suit_w) // 2
    suit_y = rank_y + rank_h + 1

    draw.text((suit_x, suit_y), symbol, fill=suit_info['color'], font=suit_font)

    # Save
    card_code = f"{rank}{suit}"
    out_path = output_dir / f"{card_code}.png"
    img.save(str(out_path))
    return out_path


def generate_all_templates(output_dir: str) -> int:
    """Generate all 52 card templates."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for rank in RANKS:
        for suit in SUITS:
            try:
                path = generate_card_template(rank, suit, output_path)
                count += 1
                print(f"  Generated {rank}{suit} -> {path}")
            except Exception as e:
                print(f"  FAILED {rank}{suit}: {e}")

    print(f"\nGenerated {count}/52 templates in {output_dir}")
    return count


def copy_existing_templates(test_cards_dir: str, output_dir: str) -> int:
    """Copy existing real templates from test_cards, overwriting synthetic ones.

    Skips known mislabeled files (8S.png is actually QS).
    """
    test_path = Path(test_cards_dir)
    output_path = Path(output_dir)
    count = 0

    # Known mislabeled templates - skip these
    SKIP = {'8S.png'}  # 8S.png is actually a copy of QS.png

    if not test_path.exists():
        return 0

    for png in test_path.glob('*.png'):
        if png.name in SKIP:
            print(f"  Skipped mislabeled: {png.name}")
            continue
        dest = output_path / png.name
        img = Image.open(png)
        img.save(str(dest))
        count += 1
        print(f"  Copied real template: {png.name}")

    return count


def main():
    parser = argparse.ArgumentParser(description='Generate card templates for Rust OCR')
    parser.add_argument('--output', type=str,
                        default='poker_ocr/assets/card_templates/',
                        help='Output directory for template PNGs')
    parser.add_argument('--use-existing', action='store_true', default=True,
                        help='Copy existing real templates over synthetic ones')
    parser.add_argument('--test-cards-dir', type=str,
                        default='sys_core/tests/test_cards/',
                        help='Directory with existing real card templates')

    args = parser.parse_args()

    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    print(f"Generating 52 card templates...")
    count = generate_all_templates(args.output)

    if args.use_existing:
        print(f"\nOverwriting with real templates from {args.test_cards_dir}...")
        real_count = copy_existing_templates(args.test_cards_dir, args.output)
        print(f"Copied {real_count} real templates (these are more accurate)")

    print(f"\nDone! {count} templates in {args.output}")
    print("Real templates: AH, 2H, 5C, 6C, 8S, JC, QS")
    print("Synthetic templates: remaining 45 cards")


if __name__ == '__main__':
    main()
