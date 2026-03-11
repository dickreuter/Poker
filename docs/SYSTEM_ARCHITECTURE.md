# Gamble Bot - System Architecture & Mechanics Reference
**Last Updated:** March 11, 2026

This document provides a comprehensive technical overview of the Gamble bot's architecture, decision-making engines, and verification systems.

---

## 1. Multi-Table Runner Architecture
The `MultiTableRunner` (`gamble/multi_table_runner.py`) is the core orchestration layer capable of handling 10+ tables simultaneously.

### Key Components:
*   **Main Loop:** Polls all active poker windows every ~50-100ms.
*   **Parallel Processing:** Uses `ThreadPoolExecutor` to perform OCR and state detection on all tables in parallel to minimize latency.
*   **Window Management:** Uses AppleScript (on macOS) to find, resize, and tile windows into consistent positions for reliable detection.
*   **Priority Queue:** Decisions are prioritized based on urgency (e.g., all-in decisions or short time banks get higher priority).

---

## 2. OCR & State Detection
The bot uses a hybrid OCR pipeline to convert screen pixels into structured data.

### A. Detection Layers:
1.  **Rust Binary (`poker_ocr`):** High-speed (10-30ms) binary that performs the bulk of the image processing.
2.  **Python OCR Fallback:** Uses `pytesseract` and `OpenCV` if the Rust binary is unavailable or fails.
3.  **Claude Vision Fallback:** If local detection fails multiple times, the bot sends a screenshot to Claude (Anthropic API) for "intelligent" analysis, which then updates local thresholds.

### B. Verification (Big Pot Screenshots):
To ensure accuracy during critical moments, the bot automatically captures and saves screenshots to `data/learning/debug/` under these conditions:
*   **Big Pots:** When the pot exceeds **20 BB**.
*   **Detection Failures:** When cards or buttons cannot be identified after "self-healing" attempts.
*   **Showdown:** Captures the final board and revealed opponent cards for history verification.

---

## 3. Decision Engine: Eval7 & Nash Equilibrium
The bot's strategy is driven by a combination of Game Theory Optimal (GTO) ranges and real-time equity calculation.

### A. eval7 (Equity Calculation):
The `eval7` library is used for fast (1-2ms) hand vs. range equity simulations.
*   **Range-Based Equity:** Instead of just calculating "hand vs random," the bot estimates the opponent's range based on their position and action (e.g., "CO 3-bet range") and calculates equity against that specific set of hands.
*   **Blocker Awareness:** `eval7` automatically accounts for card removal (blockers), making equity calculations much more precise than simple Monte Carlo.

### B. Nash Equilibrium (Push/Fold):
For short-stack situations (≤15 BB), the bot employs Nash Equilibrium strategies found in `gamble/decisionmaker/range_equity.py`.
*   **NASH_SHOVE_RANGES:** Hardcoded ranges derived from solvers (HoldemResources/ICMIZER) that tell the bot exactly when to shove based on position and effective stack.
*   **Call-vs-Shove:** Uses `eval7` to compute the EV of calling a shove by simulating our hand against the opponent's likely Nash shove range.

---

## 4. Play Evaluation & Learning
The bot is designed to improve itself over time.

### A. Performance Tracking:
*   **`AdaptiveLearner`:** Logs every action (success/fail) to `data/learning/actions.jsonl`. It tracks success rates for card detection, button clicks, and rebuys.
*   **`SpotTracker`:** Real-time P&L tracking. It categorizes "spots" (e.g., "Facing 3-bet IP") and calculates the P&L for each specific situation to identify leaks.
*   **`SessionAnalyzer`:** Post-session tool that reads `hand_history.jsonl` to provide a summary of VPIP, PFR, and overall profitability.

### B. Self-Healing:
If detection fails (e.g., "no cards found"), the `SelfHealer` triggers:
1.  It tries adjusting HSV thresholds (lenient vs strict).
2.  It logs the working threshold for that specific session to `thresholds.json`.
3.  It reports the issue to the `AdaptiveLearner` for future optimization.

---

## 5. Verification & Debugging
If you suspect the bot is making mistakes:
1.  Check `data/learning/debug/` for screenshots of the hands in question.
2.  Review `data/learning/hand_history.jsonl` for the detailed reasoning behind every decision (Equity, EV, Opponent Range estimate).
3.  Verify that `eval7` is installed and functioning (`HAS_EVAL7` in logs).
