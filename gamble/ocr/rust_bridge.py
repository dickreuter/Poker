"""
RustOCRBridge - Subprocess wrapper for the Rust poker_ocr binary.

Calls the compiled Rust binary and deserializes JSON output into GameState.
Falls back to Python OCR if the binary is unavailable.
"""

import json
import logging
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from gamble.ocr.game_state import GameState

log = logging.getLogger(__name__)

# Possible locations for the poker_ocr binary
_BINARY_SEARCH_PATHS = [
    Path(__file__).parent.parent.parent / 'poker_ocr' / 'target' / 'release' / 'poker_ocr',
    Path(__file__).parent.parent.parent / 'poker_ocr' / 'target' / 'debug' / 'poker_ocr',
    Path.home() / '.local' / 'bin' / 'poker_ocr',
]

_SUBPROCESS_TIMEOUT = 2.0  # seconds


def _find_binary() -> Optional[str]:
    """Find the poker_ocr binary in known locations or PATH."""
    # Check PATH first
    path_binary = shutil.which('poker_ocr')
    if path_binary:
        return path_binary

    # Check known build locations
    for p in _BINARY_SEARCH_PATHS:
        if p.exists() and os.access(str(p), os.X_OK):
            return str(p)

    return None


class RustOCRBridge:
    """Bridge to the Rust poker_ocr binary for fast game state extraction."""

    def __init__(self, binary_path: Optional[str] = None):
        self._binary = binary_path or _find_binary()
        self._available = (
            self._binary is not None
            and os.path.isfile(self._binary)
            and os.access(self._binary, os.X_OK)
        )
        if self._available:
            log.info(f"Rust OCR binary found: {self._binary}")
        else:
            log.warning("Rust OCR binary not found. Use Python fallback.")

    @property
    def available(self) -> bool:
        return self._available

    def capture_table(self, window_id: int, mode: str = 'full') -> Optional[GameState]:
        """Capture and analyze a single poker table.

        Args:
            window_id: macOS CGWindowID
            mode: 'full' for complete analysis, 'buttons_only' for quick turn check

        Returns:
            GameState or None if capture failed
        """
        if not self._available:
            return None

        try:
            result = subprocess.run(
                [self._binary, '--window-id', str(window_id), '--mode', mode],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )

            if result.returncode != 0:
                log.warning(f"poker_ocr failed (code {result.returncode}): {result.stderr[:200]}")
                return None

            data = json.loads(result.stdout)
            state = GameState.from_json(data)
            state.ocr_source = 'rust'
            return state

        except subprocess.TimeoutExpired:
            log.warning(f"poker_ocr timed out for window {window_id}")
            return None
        except json.JSONDecodeError as e:
            log.warning(f"poker_ocr invalid JSON: {e}")
            return None
        except Exception as e:
            log.error(f"poker_ocr unexpected error: {e}")
            return None

    def capture_screenshot(self, screenshot_path: str, mode: str = 'full') -> Optional[GameState]:
        """Process a saved screenshot file (for testing/replay).

        Args:
            screenshot_path: Path to a PNG screenshot
            mode: 'full' for complete analysis

        Returns:
            GameState or None if processing failed
        """
        if not self._available:
            return None

        try:
            result = subprocess.run(
                [self._binary, '--screenshot', screenshot_path, '--mode', mode],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )

            if result.returncode != 0:
                log.warning(f"poker_ocr screenshot failed: {result.stderr[:200]}")
                return None

            data = json.loads(result.stdout)
            state = GameState.from_json(data)
            state.ocr_source = 'rust'
            return state

        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            log.warning(f"poker_ocr screenshot error: {e}")
            return None

    def capture_all_tables(self, window_ids: List[int], mode: str = 'full') -> List[GameState]:
        """Capture multiple tables in parallel using --multi flag.

        Args:
            window_ids: List of CGWindowIDs
            mode: 'full' or 'buttons_only'

        Returns:
            List of GameState for successfully captured tables
        """
        if not self._available or not window_ids:
            return []

        # Use the --multi flag for batch processing
        ids_str = ','.join(str(wid) for wid in window_ids)

        try:
            result = subprocess.run(
                [self._binary, '--multi', ids_str, '--mode', mode],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT * 2,
            )

            if result.returncode != 0:
                log.warning(f"poker_ocr multi failed: {result.stderr[:200]}")
                # Fall back to individual captures
                return self._capture_individual(window_ids, mode)

            # Output is a JSON array
            data_list = json.loads(result.stdout)
            states = []
            for data in data_list:
                state = GameState.from_json(data)
                state.ocr_source = 'rust'
                states.append(state)
            return states

        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            log.warning(f"poker_ocr multi error: {e}, falling back to individual")
            return self._capture_individual(window_ids, mode)

    def _capture_individual(self, window_ids: List[int], mode: str) -> List[GameState]:
        """Fall back to capturing tables one at a time via threads."""
        states = []
        with ThreadPoolExecutor(max_workers=min(len(window_ids), 4)) as executor:
            futures = {
                executor.submit(self.capture_table, wid, mode): wid
                for wid in window_ids
            }
            for future in as_completed(futures):
                state = future.result()
                if state:
                    states.append(state)
        return states

    def list_windows(self) -> List[Dict]:
        """List all GGPoker windows.

        Returns:
            List of dicts with window_id, name, x, y, width, height
        """
        if not self._available:
            return []

        try:
            result = subprocess.run(
                [self._binary, '--list-windows'],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )

            if result.returncode != 0:
                return []

            return json.loads(result.stdout)

        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            return []
