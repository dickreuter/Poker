# System Utility Analysis & Documentation

## Overview

This project is a fork of [dickreuter/System](https://github.com/dickreuter/System) - a fully functional poker automation tool that plays through image recognition and algorithmic decision-making.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  POKER BOT ARCHITECTURE                                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   MongoDB    │───▶│  Strategy    │───▶│  Decision    │  │
│  │  (remote)    │    │   Handler    │    │    Maker     │  │
│  │              │    │              │    │              │  │
│  │ - strategies │    │ - loads from │    │ - monte carlo│  │
│  │ - tables     │    │   remote DB  │    │ - curve fit  │  │
│  │ - templates  │    │ - 40+ params │    │ - outs calc  │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │    Table     │───▶│     GUI      │───▶│    Mouse     │  │
│  │   Scraper    │    │   (PyQt6)    │    │    Mover     │  │
│  │              │    │              │    │              │  │
│  │ - screenshot │    │ - displays   │    │ - clicks     │  │
│  │ - OCR        │    │   all state  │    │   buttons    │  │
│  │ - templates  │    │ - charts     │    │              │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## How It Works

### The Main Loop (Every 0.5-1 second)

```
1. SCREENSHOT              ──▶ PIL ImageGrab.grab()
2. TABLE DETECTION         ──▶ Template match "topleft_corner"
3. CARD DETECTION          ──▶ Template match all 52 cards
4. GAME STATE (OCR)        ──▶ Pot size, call amount, stacks
5. MONTE CARLO EQUITY      ──▶ 3000-5000 simulations
6. DECISION                ──▶ Fold/Call/Raise based on equity
7. CLICK BUTTON            ──▶ Mouse moves and clicks
8. REPEAT
```

### Decision Making (`decisionmaker/decisionmaker.py`)

Uses **curve fitting** to map equity to bet/call limits:

```python
# Example: 45% equity
equity = 0.45

maxCallLimit = curvefitting(
    equity=0.45,
    min_equity=0.20,  # Won't call below 20%
    max_equity=1.0,
    power=5           # Non-linear scaling
)

# If call amount < maxCallLimit → CALL
# Else → FOLD
```

**Key Parameters by Stage:**

| Stage | Min Call Equity | Min Bet Equity |
|-------|-----------------|----------------|
| PreFlop | 22% | 35% |
| Flop | 25% | 35% |
| Turn | 30% | 40% |
| River | 40% | 45% |

### Monte Carlo Equity (`decisionmaker/montecarlo_python.py`)

```python
def calculate_equity(my_cards, board, num_opponents):
    wins = 0
    for i in range(5000):
        # Randomly deal remaining cards
        # Evaluate all hands
        # Count wins
    return wins / 5000  # e.g., 0.45 = 45%
```

---

## Template System (CRITICAL)

### How Templates Work

The bot uses **OpenCV template matching** to find UI elements. From the documentation:

> "You'll need to teach it every card and every button etc."

This means:
- **ALL 52 card templates** must be captured
- Button templates (Call, Raise, Fold, Check)
- Area definitions (where to look for cards, pot, etc.)
- Top-left corner template (to locate the table)

### Template Storage

Templates are stored in a remote MongoDB database at `https://dickreuter.com:7778/`:

```python
# API endpoints
GET  /get_table?table_name=X           # Get all templates for table
GET  /load_table_image?image_name=ah&table_name=X  # Get specific card
POST /update_table_image               # Upload new template
```

### Template Matching Code

```python
# File: tools/screen_operations.py
def find_template_on_screen(template, screenshot, threshold):
    res = cv2.matchTemplate(screenshot, template, cv2.TM_SQDIFF_NORMED)
    # Lower score = better match
    # 0.000 = perfect
    # < 0.01 = excellent
    # < 0.15 = acceptable
    # > 0.25 = likely wrong
```

---

## Current Problems

### 1. Card Detection Failing
- Shows `['?H', '?H']` instead of actual cards
- **Cause**: Card templates don't match current GGSystem UI
- **Fix**: Need to capture ALL 52 card templates

### 2. OCR Failing
- Player funds showing as `-1.0`
- **Cause**: OCR areas not properly defined or Tesseract not finding text
- **Fix**: Verify OCR area coordinates, check image preprocessing

### 3. Template Matching Intermittent
- Sometimes score is 0.000 (perfect), sometimes 0.34 (fail)
- **Cause**: GGSystem UI changes slightly (focus border, animations)
- **Fix**: Use adaptive thresholds, multiple fallback methods

### 4. Dealer Position Not Found
- **Cause**: Dealer button template doesn't match
- **Fix**: Capture new dealer button template

---

## File Structure

### Core Files

| File | Purpose |
|------|---------|
| `main.py` | Original GUI entry point (PyQt6) |
| `tools/cli_controller.py` | Headless CLI entry point |
| `decisionmaker/decisionmaker.py` | Decision logic (29KB) |
| `decisionmaker/montecarlo_python.py` | Equity calculation (21KB) |
| `scraper/table_scraper.py` | Card/board detection |
| `tools/screen_operations.py` | Template matching, OCR |
| `tools/mongo_manager.py` | Remote database access |

### GUI Files

```
gui/
├── gui_launcher.py           # Loads UI files
├── action_and_signals.py     # Qt signals/slots
├── ui/
│   ├── main_form.ui          # Main bot window
│   ├── table_setup_form.ui   # Template capture (133KB)
│   └── strategy_manager_form.ui  # Strategy editor (214KB)
```

### Detection Files

| File | Purpose |
|------|---------|
| `tools/dynamic_table_finder.py` | AppleScript + color detection |
| `tools/smart_card_detector.py` | HSV-based card finding |
| `tools/button_detector.py` | Color-based button detection |
| `tools/dynamic_mouse_mover.py` | Clicks buttons by color |

---

## Setup Process (How It Should Work)

### 1. Use the Table Setup GUI

```bash
python -m sys_core.main
# Go to Table Setup in the GUI
```

The Table Setup GUI allows you to:
1. Take screenshots
2. Mark the top-left corner reference point
3. Define search areas for cards, buttons, pot
4. Capture all 52 card templates
5. Test template matching

### 2. Capture ALL Card Templates

For each of the 52 cards:
1. Wait for that card to appear in your hand
2. Screenshot and mark the card corner region
3. Upload to database

Cards needed: `as, ah, ad, ac, ks, kh, kd, kc, qs, qh, qd, qc, js, jh, jd, jc, ts, th, td, tc, 9s, 9h, 9d, 9c, 8s, 8h, 8d, 8c, 7s, 7h, 7d, 7c, 6s, 6h, 6d, 6c, 5s, 5h, 5d, 5c, 4s, 4h, 4d, 4c, 3s, 3h, 3d, 3c, 2s, 2h, 2d, 2c`

### 3. Define Search Areas

| Area | Purpose |
|------|---------|
| `topleft_corner` | Reference point for table detection |
| `my_cards_area` | Where your hole cards appear |
| `table_cards_area` | Where community cards appear |
| `total_pot_area` | Where pot value is shown |
| `call_value` | Where call amount is shown |
| `player_funds_area` | Where your stack is shown |

---

## Running the Bot

### GUI Mode (Original)
```bash
python -m sys_core.main
```

### CLI Mode (Headless)
```bash
# Test table detection
python -m sys_core.tools.cli_controller test

# Run single hand
python -m sys_core.tools.cli_controller single --input dynamic

# Run continuously
python -m sys_core.tools.cli_controller start --input dynamic

# Multi-table
python -m sys_core.tools.cli_controller multi --max-tables 4
```

---

## Coordinate Systems (Retina Display)

**CRITICAL for MacBook Pro:**

| Type | Description | Usage |
|------|-------------|-------|
| POINTS | macOS logical coordinates | Mouse clicks, window positions |
| PIXELS | Actual screen pixels | Screenshots, image operations |

```python
RETINA_SCALE = 2

# Points to Pixels (for screenshots)
pixel_x = point_x * 2

# Pixels to Points (for mouse clicks)
point_x = pixel_x // 2
```

---

## What Needs To Be Done

### Option 1: Use the GUI (Proper Way)
1. Run `python -m sys_core.main`
2. Open Table Setup
3. Capture all templates through the GUI
4. Configure strategy
5. Run bot

### Option 2: Programmatic Setup
1. Create a script to capture cards as they appear
2. Auto-upload to database
3. Build up template library over time

### Option 3: Fix the Code
1. Make card detection work without templates (pure visual/OCR)
2. Use color detection for suits
3. Use OCR for ranks
4. This is more complex but doesn't need 52 templates

---

## Logs & Debugging

```bash
# Watch logs
tail -f /Users/sebastian/Developer/Gamble/log/dm_assistant.log

# Filter for key events
tail -f log/dm_assistant.log | grep -E "My cards|equity|FOLD|CALL|RAISE"

# Debug images saved to
/tmp/poker_debug/
```

---

## Summary

The bot is a sophisticated poker automation tool, but it relies heavily on **template matching**. The current issue is that the templates stored in the remote database don't match the current GGSystem UI.

**The fix is NOT to patch code endlessly** - it's to properly capture all templates using the Table Setup GUI, as intended by the original author.
