# Bot Fixes and Mechanics Reference
**Date:** March 11, 2026

This document details critical fixes and mechanics implemented to address issues with "Deal Me In" detection and premature folding of premium hands.

## 1. "Deal Me In" Detection & Rejoining

**Problem:** The bot was sometimes failing to detect the "Deal Me In" or "I'm Back" buttons, causing it to sit out indefinitely. This was due to:
*   Reliance on template matching which failed when the button appearance shifted slightly.
*   Missing color definitions in the `TableReader`.
*   Unnecessary delays in the mouse movement logic.

**Solution:** A multi-layered detection strategy was implemented.

### A. Color-Based Fallback (Primary Fix)
*   **File:** `sys_core/scraper/table_scraper.py`
*   **Method:** `im_back()`
*   **Logic:**
    1.  First tries the original template matching.
    2.  If that fails, it falls back to `ButtonDetector.detect_deal_me_in()`.
    3.  If a red button is found in the expected region, it's flagged as "Deal Me In".
    4.  The specific coordinates are stored in `table_dict['last_deal_me_in_pos']`.

### B. OCR Detection (Multi-Table Runner)
*   **File:** `sys_core/ocr/table_reader.py`
*   **Change:** Added `deal_me_in` to the `BUTTON_HSV` dictionary.
*   **Values:** Uses the unified **Red** color range from `sys_core/core/constants.py`:
    *   Lower: `[0, 100, 100]`
    *   Upper: `[15, 255, 255]`
*   **Logic:** The `read_table` function now actively scans for this color range and confirms it with OCR text ("Deal", "Back", "Sit").

### C. Fast Action Execution
*   **File:** `sys_core/tools/mouse_mover.py`
*   **Change:** The `Imback` action now checks for `last_deal_me_in_pos`.
*   **Improvement:** Instead of clicking a hardcoded config coordinate (which might be wrong) and waiting 0-3 seconds, it immediately clicks the exact detected pixel coordinates of the button.

---

## 2. Premium Hand Safety Exemption

**Problem:** The bot was folding premium hands (AA, KK, etc.) preflop.
*   **Cause:** A "Safety" check in the decision logic was designed to prevent the bot from acting on card misreads (e.g., seeing "5S 5S" and thinking it's a pair, when it's actually a glitch).
*   **Failure Mode:** If the bot read your cards as **AA**, but the equity calculation (Monte Carlo) returned a low value (perhaps due to a board read error or a range calculation bug), the safety check `if equity < 0.22: fold` would override the strategy and fold the Aces.

**Solution:** Explicit "Premium Exemption" in safety floors.

### Logic Implementation
*   **File:** `sys_core/decisionmaker/decisionmaker.py`
*   **Method:** `preflop_table_analyser`
*   **Code:**
    ```python
    # PREMIUM EXEMPTION: Never fold premium hands due to safety floors
    PREMIUMS = {'AA', 'KK', 'QQ', 'JJ', 'AKS', 'AKO', 'AQS'}
    hand_norm = _normalize_hand(crd1, crd2)
    is_premium_hand = hand_norm in PREMIUMS

    if self.decision in (DecisionTypes.bet3, DecisionTypes.bet4):
        # Only fold if equity is low AND it's NOT a premium hand
        if t.equity < 0.22 and not is_premium_hand:
            log.info(f'Preflop raise overridden to FOLD: equity {t.equity:.3f} < 0.22')
            self.decision = DecisionTypes.fold
    ```

**Impact:** Even if the equity calculation glitches and says AA has 10% equity, the bot will **NOT** fold it because AA is in the `PREMIUMS` set.

---

## 3. Multi-Table Runner Mechanics

The `MultiTableRunner` (`sys_core/engine.py`) uses a specialized pipeline:

1.  **Fast Scan (`_fast_deal_me_in_scan`):**
    *   Takes **one** full-screen screenshot.
    *   Crops to each table's button region.
    *   Runs fast HSV color detection for Red "Deal Me In" buttons.
    *   If found, clicks immediately via `pyautogui` without waiting for the full decision cycle.

2.  **State Check (`check_table_state`):**
    *   If `PYTHON_OCR_AVAILABLE` is True, it uses `capture_game_state`.
    *   This now leverages the updated `table_reader.py` (see Section 1B) to reliably find buttons.

---

## 4. Key Configuration Files

*   **`sys_core/core/constants.py`**: The single source of truth for color ranges (HSV) and thresholds. Modify this file to tune detection sensitivity.
*   **`sys_core/ocr/table_reader.py`**: Controls the computer vision pipeline for reading buttons, cards, and pots.
*   **`sys_core/decisionmaker/decisionmaker.py`**: Contains the core strategy logic, GTO lookups, and the new safety exemptions.
