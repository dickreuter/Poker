"""Supervised rank template capture tool.

Two modes:
1. CAPTURE: Grabs card crops from live play, saves as numbered PNGs
2. LABEL:   You tell us what rank each PNG is, we save verified templates

Usage:
    # Step 1: Capture crops (runs for 60 seconds, capturing unique cards)
    python -m sys_core.ocr.capture_templates capture

    # Step 2: View crops and label them
    python -m sys_core.ocr.capture_templates label
"""

import json
import os
import subprocess
import sys
import time
import hashlib

import cv2
import numpy as np
from pathlib import Path
from PIL import Image, ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sys_core.ocr.card_reader import (
    _binarize_white_on_colored, _strip_suit_symbol,
    _find_card_positions, _detect_suit_colored, STYLE_COLORED,
)
from sys_core.ocr.rank_templates import get_rank_matcher, _extract_glyph, _normalize_glyph

TEMPLATE_DIR = Path(__file__).parent / 'rank_template_data'
CAPTURE_DIR = Path('/tmp/card_captures')
ALL_RANKS = ['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']


def find_ggpoker_window():
    """Find GGPoker table window via AppleScript."""
    script = '''
    tell application "System Events"
        tell process "GGnet"
            set wins to {}
            repeat with w in windows
                set winName to name of w as text
                if winName contains "Rush" or winName contains "Cash" or winName contains "Spin" or winName contains "Hold" or winName contains "NL" then
                    set pos to position of w
                    set sz to size of w
                    set end of wins to {winName, item 1 of pos, item 2 of pos, item 1 of sz, item 2 of sz}
                end if
            end repeat
            return wins
        end tell
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', script],
                                capture_output=True, text=True, timeout=5)
        output = result.stdout.strip().replace('\u2212', '-').replace('\u2013', '-')
        if not output:
            return None
        parts = [p.strip() for p in output.split(',')]
        if len(parts) >= 5:
            return {'name': parts[0], 'x': int(parts[1]), 'y': int(parts[2]),
                    'w': int(parts[3]), 'h': int(parts[4])}
    except Exception as e:
        print(f"Error: {e}")
    return None


def capture_table_screenshot(win):
    """Capture the table area."""
    full = ImageGrab.grab()
    scale = 2  # Retina
    x1, y1 = win['x'] * scale, win['y'] * scale
    x2, y2 = x1 + win['w'] * scale, y1 + win['h'] * scale
    return full.crop((x1, y1, x2, y2))


def extract_rank_crops(table_img):
    """Extract rank crops from hole cards."""
    img_np = np.array(table_img)
    if img_np.ndim == 3 and img_np.shape[2] == 4:
        img_np = img_np[:, :, :3]

    W, H = table_img.width, table_img.height
    positions = _find_card_positions(img_np, W, H)
    if not positions:
        return []

    crops = []
    for side in ['left', 'right']:
        rank_key = f'{side}_rank'
        body_key = f'{side}_body'
        if rank_key not in positions:
            continue

        rx, ry, rw, rh = positions[rank_key]
        crop_color = img_np[ry:ry+rh, rx:rx+rw]
        if crop_color.size == 0 or crop_color.shape[0] < 5:
            continue

        bw = _binarize_white_on_colored(crop_color)
        bw = _strip_suit_symbol(bw)
        _, bw = cv2.threshold(bw, 127, 255, cv2.THRESH_BINARY)

        suit = '?'
        if body_key in positions:
            suit = _detect_suit_colored(img_np, positions[body_key])

        crops.append({
            'side': side,
            'bw': bw,
            'color': crop_color,
            'suit': suit,
        })

    return crops


def do_capture(duration=90):
    """Capture unique card crops for the specified duration."""
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

    # Clear old captures
    for f in CAPTURE_DIR.glob('card_*.png'):
        f.unlink()
    for f in CAPTURE_DIR.glob('bw_*.png'):
        f.unlink()

    print(f"Capturing card crops for {duration} seconds...")
    print("Make sure you're playing Rush & Cash so cards keep changing.")
    print()

    seen_hashes = set()
    card_count = 0
    start = time.time()

    while time.time() - start < duration:
        win = find_ggpoker_window()
        if not win:
            time.sleep(1)
            continue

        try:
            table_img = capture_table_screenshot(win)
            crops = extract_rank_crops(table_img)
        except Exception as e:
            time.sleep(0.5)
            continue

        for crop_info in crops:
            bw = crop_info['bw']
            # Hash to avoid duplicates
            h = hashlib.md5(bw.tobytes()).hexdigest()[:12]
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            card_count += 1
            suit_char = crop_info['suit']

            # Save color version (for human viewing)
            color_path = CAPTURE_DIR / f'card_{card_count:03d}_{suit_char}.png'
            cv2.imwrite(str(color_path), cv2.cvtColor(crop_info['color'], cv2.COLOR_RGB2BGR))

            # Save bw version (for template creation)
            bw_path = CAPTURE_DIR / f'bw_{card_count:03d}_{suit_char}.png'
            cv2.imwrite(str(bw_path), bw)

            elapsed = int(time.time() - start)
            print(f"  [{elapsed}s] Card #{card_count} ({crop_info['side']}, suit={suit_char}) → {color_path.name}")

        time.sleep(0.5)

    print(f"\nDone! Captured {card_count} unique card crops.")
    print(f"View them at: {CAPTURE_DIR}")
    print(f"\nNext step: look at the card_*.png files and run:")
    print(f"  python -m sys_core.ocr.capture_templates label")


def do_label():
    """Label captured crops and save as verified templates."""
    if not CAPTURE_DIR.exists():
        print("No captures found. Run 'capture' first.")
        return

    color_files = sorted(CAPTURE_DIR.glob('card_*.png'))
    bw_files = sorted(CAPTURE_DIR.glob('bw_*.png'))

    if not color_files:
        print("No card images found. Run 'capture' first.")
        return

    # Build mapping: card_NNN_S.png → bw_NNN_S.png
    pairs = []
    for cf in color_files:
        stem = cf.stem.replace('card_', 'bw_')
        bf = CAPTURE_DIR / f'{stem}.png'
        if bf.exists():
            pairs.append((cf, bf))

    print(f"Found {len(pairs)} card crops to label.")
    print(f"Open {CAPTURE_DIR} in Finder to view the color images.")
    print()

    # Check existing templates
    captured = set()
    for rank in ALL_RANKS:
        safe = rank if rank != '10' else 'T'
        if list(TEMPLATE_DIR.glob(f'rank_{safe}_*.png')):
            captured.add(rank)

    remaining = [r for r in ALL_RANKS if r not in captured]
    print(f"Already have templates for: {sorted(captured) if captured else 'none'}")
    print(f"Still need: {remaining}")
    print()

    # Label file for batch processing
    label_file = CAPTURE_DIR / 'labels.json'
    labels = {}
    if label_file.exists():
        with open(label_file) as f:
            labels = json.load(f)

    print("Enter labels for each card. Format: card_001=A card_002=K card_003=Q ...")
    print("Or type them one per line. Type 'done' when finished.")
    print("Type 'show' to list unlabeled files.")
    print()

    while True:
        cmd = input("> ").strip()
        if cmd.lower() == 'done':
            break
        if cmd.lower() == 'show':
            unlabeled = [cf.stem for cf, _ in pairs if cf.stem not in labels]
            for name in unlabeled[:20]:
                print(f"  {name}.png")
            print(f"  ({len(unlabeled)} unlabeled)")
            continue
        if cmd.lower() == 'q':
            break

        # Parse "card_001=A card_002=K" or just "A" for next unlabeled
        if '=' in cmd:
            for part in cmd.split():
                if '=' in part:
                    name, rank = part.split('=', 1)
                    rank = rank.upper()
                    if rank == 'T':
                        rank = '10'
                    if rank in ALL_RANKS:
                        # Find matching file
                        name = name.replace('.png', '')
                        labels[name] = rank
                        print(f"  {name} = {rank}")
                    else:
                        print(f"  Invalid rank: {rank}")
        else:
            # Label next unlabeled
            rank = cmd.upper()
            if rank == 'T':
                rank = '10'
            if rank in ALL_RANKS:
                unlabeled = [(cf, bf) for cf, bf in pairs if cf.stem not in labels]
                if unlabeled:
                    cf, bf = unlabeled[0]
                    labels[cf.stem] = rank
                    print(f"  {cf.stem} = {rank}")
                else:
                    print("  All cards labeled!")
            else:
                print(f"  Invalid rank: {rank}. Use: {', '.join(ALL_RANKS)}")

    # Save labels
    with open(label_file, 'w') as f:
        json.dump(labels, f, indent=2)
    print(f"\nSaved {len(labels)} labels to {label_file}")

    # Create templates from labels
    print("\nCreating verified templates...")
    matcher = get_rank_matcher()
    created = set()

    for cf, bf in pairs:
        if cf.stem not in labels:
            continue
        rank = labels[cf.stem]
        bw = cv2.imread(str(bf), cv2.IMREAD_GRAYSCALE)
        if bw is None:
            continue

        _, bw = cv2.threshold(bw, 127, 255, cv2.THRESH_BINARY)

        # Save template
        safe = rank if rank != '10' else 'T'
        existing = list(TEMPLATE_DIR.glob(f'rank_{safe}_*.png'))
        if len(existing) >= 3:
            if rank not in created:
                print(f"  {rank}: already have {len(existing)} templates, skipping")
            continue

        glyph = _extract_glyph(bw)
        if glyph is None:
            normalized = cv2.resize(bw, (40, 56), interpolation=cv2.INTER_CUBIC)
        else:
            normalized = _normalize_glyph(glyph)

        idx = len(existing)
        out_path = TEMPLATE_DIR / f'rank_{safe}_{idx}.png'
        cv2.imwrite(str(out_path), normalized)

        # Record hash
        matcher.record_hash(rank, bw)

        if rank not in created:
            print(f"  {rank}: saved template #{idx} → {out_path.name}")
            created.add(rank)

    # Update manifest
    manifest = {}
    for rank in ALL_RANKS:
        safe = rank if rank != '10' else 'T'
        count = len(list(TEMPLATE_DIR.glob(f'rank_{safe}_*.png')))
        manifest[rank] = {'count': count, 'trusted': count >= 1}
    with open(TEMPLATE_DIR / 'manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)

    covered = [r for r in ALL_RANKS if manifest[r]['trusted']]
    missing = [r for r in ALL_RANKS if not manifest[r]['trusted']]
    print(f"\nTemplates ready for: {covered}")
    if missing:
        print(f"Still need: {missing}")
    else:
        print("\nALL 13 RANKS COVERED! Template-only matching is ready.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'label':
        do_label()
    elif len(sys.argv) > 1 and sys.argv[1] == 'capture':
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 90
        do_capture(duration)
    else:
        print("Usage:")
        print("  python -m sys_core.ocr.capture_templates capture [seconds]")
        print("  python -m sys_core.ocr.capture_templates label")
        print()
        print("Step 1: Run 'capture' while playing Rush & Cash (~90 seconds)")
        print("Step 2: Open /tmp/card_captures/ and view the card_*.png files")
        print("Step 3: Run 'label' and type the rank for each card")


if __name__ == '__main__':
    main()
