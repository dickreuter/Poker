# Bot Operational Guide - How to Use, Monitor, and Verify
**Date:** March 11, 2026

This guide explains how to operate the bot, monitor its performance in real-time, and verify its decisions after a session.

---

## 1. How to Start the Bot

### For Multi-Table Play (Recommended)
The multi-table runner is the most advanced version of the bot. It handles multiple tables, window tiling, and parallel OCR.

```bash
# Standard multi-table run
python -m sys_core.engine

# With Claude-enhanced decisions (High-IQ mode)
python -m sys_core.tools.claude_enhanced_runner
```

### For Single-Table Testing
If you want to test the bot on a single table with full GUI feedback:
```bash
python sys_core/main.py
```

---

## 2. How to Monitor in Real-Time

Watch the console output for the **DECISION** lines. These tell you exactly why the bot is acting:

```text
DECISION: Bet pot | cards=['AH', 'KS'] board=['QH', 'JD', '2C'] | pot=12.5 call=0.0 | equity=0.620 abs_eq=0.580 | EV=+4.2 BB | stage=Flop pos=BTN opp=2 init=Y
```

*   **equity=0.620:** This is the hand's strength against the opponent's estimated range.
*   **EV=+4.2 BB:** The estimated profit (in Big Blinds) of the chosen action.
*   **init=Y:** "Y" means we have the initiative (we were the last raiser).

---

## 3. How to Verify Big Pots & Card Accuracy

The bot automatically saves evidence for every major hand to help you verify that the OCR read the cards correctly.

### Step 1: Find the Evidence
Go to `data/learning/debug/`. You will see files named:
*   `card_detection_big_pot_...png`: Full screenshot of the table during a high-stakes hand (>20 BB).
*   `showdown_verification_...png`: Captured at the end of a hand when cards are revealed.

### Step 2: Compare OCR vs. Image
Open `data/learning/hand_history.jsonl` and find the entry matching the timestamp of the screenshot.
*   **Check the `cards` array:** Does it match the cards visible in the screenshot?
*   **Check the `pot` value:** Does it match the table?

**If you find a mismatch:** The bot's "Self-Healing" logic uses these failures to adjust its HSV thresholds for the next hand.

---

## 4. How to Evaluate Your Play

After a session, use the built-in analysis tools to see if the bot is winning and where it might be leaking money.

### Run the Session Analyzer
This tool reads your entire hand history and provides a professional poker report:
```bash
python -m sys_core.tools.session_analyzer
```
It will output:
*   **VPIP / PFR / 3-Bet %:** Are we playing too loose or too tight?
*   **P&L by Position:** Are we losing money from the Small Blind?
*   **Big Pot Efficiency:** How much EV did we realize in pots > 50 BB?

### Check the Spot Tracker
The `SpotTracker` (logged at the end of the `engine` output) tells you how we are doing in specific tactical situations:
```text
SPOT P&L: Facing 3-bet IP: +120.5 BB | Defending BB vs BTN: -45.0 BB
```
If a specific spot is heavily negative, the bot's `AdaptiveLearner` will automatically tighten the ranges for that situation in future hands.

---

## 5. How to Tune the Bot

If the bot is consistently missing a specific color (e.g., it doesn't see the "Fold" button on a new theme):
1.  Open `sys_core/core/constants.py`.
2.  Adjust the `HSV_RANGES` for that button.
3.  The bot will reload these constants automatically on the next cycle.
