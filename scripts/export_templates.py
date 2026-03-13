#!/usr/bin/env python3
"""
Export 52 card templates from MongoDB to PNG files for the Rust OCR engine.

Usage:
    python scripts/export_templates.py --output poker_ocr/assets/card_templates/
"""

import argparse
import io
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def export_templates(output_dir: str, table_name: str = "Official GGPoker 6player"):
    """Export card templates from MongoDB to PNG files.

    Each template is saved as {RANK}{SUIT}.png, e.g., AH.png, KS.png, 10D.png
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        from sys_core.tools.mongo_manager import MongoManager
        mongo = MongoManager()
    except Exception as e:
        log.error(f"Cannot connect to MongoDB: {e}")
        log.info("Make sure MongoDB is running and accessible")
        return 0

    # Get table configuration
    table_dict = mongo.get_table(table_name)
    if not table_dict:
        log.error(f"Table '{table_name}' not found in MongoDB")
        return 0

    # Card names as stored in MongoDB
    ranks = ['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']
    suits = ['H', 'D', 'C', 'S']

    count = 0
    for rank in ranks:
        for suit in suits:
            card_code = f"{rank}{suit}"

            try:
                # Try different key formats that MongoDB might use
                for key in [card_code, card_code.lower(), f"card_{card_code}"]:
                    if key in table_dict:
                        img_data = table_dict[key]
                        if isinstance(img_data, bytes):
                            from PIL import Image
                            img = Image.open(io.BytesIO(img_data))
                            out_path = output_path / f"{card_code}.png"
                            img.save(str(out_path))
                            count += 1
                            log.info(f"Exported {card_code} -> {out_path}")
                            break

                # Try getting from the templates collection
                if count == 0 or True:  # Always try
                    try:
                        img = mongo.get_screenshot(card_code)
                        if img is not None:
                            from PIL import Image
                            if not isinstance(img, Image.Image):
                                img = Image.open(io.BytesIO(img))
                            out_path = output_path / f"{card_code}.png"
                            img.save(str(out_path))
                            count += 1
                            log.info(f"Exported {card_code} -> {out_path}")
                    except Exception:
                        pass

            except Exception as e:
                log.warning(f"Failed to export {card_code}: {e}")

    log.info(f"\nExported {count}/52 card templates to {output_dir}")
    return count


def main():
    parser = argparse.ArgumentParser(description='Export card templates from MongoDB')
    parser.add_argument('--output', type=str,
                        default='poker_ocr/assets/card_templates/',
                        help='Output directory for template PNGs')
    parser.add_argument('--table', type=str,
                        default='Official GGPoker 6player',
                        help='MongoDB table name')

    args = parser.parse_args()
    count = export_templates(args.output, args.table)

    if count == 0:
        log.warning("No templates exported. The Rust OCR will work without templates "
                     "(using white region detection only).")


if __name__ == '__main__':
    main()
