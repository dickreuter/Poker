"""
Screenshot replay testing - run OCR on saved screenshots and compare results.

Usage:
    python -m sys_core.ocr.replay --dir data/learning/screenshots/ --limit 10
    python -m sys_core.ocr.replay --screenshot /path/to/image.png
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from sys_core.ocr.game_state import GameState
from sys_core.ocr.rust_bridge import RustOCRBridge
from sys_core.ocr.fallback import PythonOCRFallback

log = logging.getLogger(__name__)


class OCRReplay:
    """Replay screenshots through OCR pipelines and compare results."""

    def __init__(self):
        self.rust_bridge = RustOCRBridge()
        self.python_fallback = PythonOCRFallback()

    def replay_screenshot(self, path: str) -> Dict:
        """Run both Rust and Python OCR on a screenshot and compare.

        Returns:
            Dict with 'rust_state', 'python_state', 'comparison'
        """
        result = {'path': path, 'rust_state': None, 'python_state': None}

        # Rust OCR
        if self.rust_bridge.available:
            start = time.time()
            rust_state = self.rust_bridge.capture_screenshot(path)
            rust_ms = (time.time() - start) * 1000
            if rust_state:
                result['rust_state'] = rust_state.to_json()
                result['rust_ms'] = rust_ms
        else:
            result['rust_available'] = False

        # Python OCR
        try:
            import cv2
            import numpy as np
            img = cv2.imread(path)
            if img is not None:
                start = time.time()
                py_state = self.python_fallback.capture_table(img)
                py_ms = (time.time() - start) * 1000
                result['python_state'] = py_state.to_json()
                result['python_ms'] = py_ms
        except Exception as e:
            result['python_error'] = str(e)

        # Compare
        if result.get('rust_state') and result.get('python_state'):
            result['comparison'] = self._compare_states(
                result['rust_state'], result['python_state']
            )

        return result

    def run_directory(self, directory: str, limit: int = 50) -> List[Dict]:
        """Process all screenshots in a directory.

        Returns:
            List of replay results
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            log.error(f"Directory not found: {directory}")
            return []

        screenshots = sorted(
            [f for f in dir_path.iterdir() if f.suffix.lower() == '.png'],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )[:limit]

        results = []
        for i, screenshot in enumerate(screenshots):
            print(f"[{i+1}/{len(screenshots)}] Processing {screenshot.name}...", end=' ')
            result = self.replay_screenshot(str(screenshot))

            rust_ms = result.get('rust_ms', 0)
            py_ms = result.get('python_ms', 0)
            rust_actions = len(result.get('rust_state', {}).get('available_actions', []))
            rust_cards = len(result.get('rust_state', {}).get('my_cards', []))

            print(f"Rust: {rust_ms:.0f}ms ({rust_actions} actions, {rust_cards} cards) | "
                  f"Python: {py_ms:.0f}ms")
            results.append(result)

        return results

    def print_summary(self, results: List[Dict]):
        """Print a summary of replay results."""
        if not results:
            print("No results to summarize.")
            return

        rust_times = [r['rust_ms'] for r in results if 'rust_ms' in r]
        py_times = [r['python_ms'] for r in results if 'python_ms' in r]

        print(f"\n{'='*60}")
        print(f"OCR Replay Summary ({len(results)} screenshots)")
        print(f"{'='*60}")

        if rust_times:
            print(f"\nRust OCR:")
            print(f"  Avg latency: {sum(rust_times)/len(rust_times):.1f}ms")
            print(f"  Min latency: {min(rust_times):.1f}ms")
            print(f"  Max latency: {max(rust_times):.1f}ms")
            rust_turn = sum(1 for r in results if r.get('rust_state', {}).get('is_my_turn', False))
            print(f"  Tables with action: {rust_turn}/{len(rust_times)}")

        if py_times:
            print(f"\nPython OCR:")
            print(f"  Avg latency: {sum(py_times)/len(py_times):.1f}ms")
            print(f"  Min latency: {min(py_times):.1f}ms")
            print(f"  Max latency: {max(py_times):.1f}ms")

        if rust_times and py_times:
            speedup = (sum(py_times)/len(py_times)) / (sum(rust_times)/len(rust_times))
            print(f"\nRust is {speedup:.1f}x faster than Python")

    def _compare_states(self, rust: dict, python: dict) -> dict:
        """Compare two GameState dicts field by field."""
        comparison = {}
        for key in ['is_my_turn', 'street', 'cards_face_down']:
            if rust.get(key) != python.get(key):
                comparison[key] = {'rust': rust.get(key), 'python': python.get(key)}

        # Compare card counts
        rust_cards = len(rust.get('my_cards', []))
        py_cards = len(python.get('my_cards', []))
        if rust_cards != py_cards:
            comparison['my_cards_count'] = {'rust': rust_cards, 'python': py_cards}

        # Compare action counts
        rust_actions = len(rust.get('available_actions', []))
        py_actions = len(python.get('available_actions', []))
        if rust_actions != py_actions:
            comparison['action_count'] = {'rust': rust_actions, 'python': py_actions}

        comparison['match'] = len(comparison) == 0
        return comparison


def main():
    parser = argparse.ArgumentParser(description='OCR Screenshot Replay Testing')
    parser.add_argument('--dir', type=str, help='Directory of screenshots to process')
    parser.add_argument('--screenshot', type=str, help='Single screenshot to process')
    parser.add_argument('--limit', type=int, default=50, help='Max screenshots to process')
    parser.add_argument('--json', action='store_true', help='Output JSON')

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    replay = OCRReplay()

    if args.screenshot:
        result = replay.replay_screenshot(args.screenshot)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Screenshot: {args.screenshot}")
            if result.get('rust_state'):
                rs = result['rust_state']
                print(f"  Rust ({result.get('rust_ms', 0):.0f}ms):")
                print(f"    Turn: {rs.get('is_my_turn')}, Cards: {rs.get('my_cards')}, "
                      f"Board: {rs.get('board_cards')}, Actions: {len(rs.get('available_actions', []))}")
            if result.get('python_state'):
                ps = result['python_state']
                print(f"  Python ({result.get('python_ms', 0):.0f}ms):")
                print(f"    Turn: {ps.get('is_my_turn')}, Cards: {ps.get('my_cards')}, "
                      f"Board: {ps.get('board_cards')}, Actions: {len(ps.get('available_actions', []))}")

    elif args.dir:
        results = replay.run_directory(args.dir, args.limit)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            replay.print_summary(results)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
