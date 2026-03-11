# COMPREHENSIVE ARCHITECTURE ANALYSIS
## GGPoker Multi-Table Bot - Deep Dive

Generated: Jan 5, 2026

---

## 1. EXECUTIVE SUMMARY

The codebase has **42+ bot entry points** but shares core detection logic. The main issues are:

1. **Fragmentation**: Unified constants exist but aren't used everywhere
2. **Conflicting HSV ranges**: Fold button = GRAY in some files, RED in others
3. **6 card detection systems** with different approaches
4. **12 OCR implementations** with different configurations
5. **No consistent single source of truth** despite `core/constants.py` existing

---

## 2. THE ONE COMMAND THAT WORKS

```bash
python -m gamble.tools.cli_controller multi --max-tables 10 --input dynamic
```

This uses:
- `MultiTableController` → `TableScreenBased` → `SmartCardDetector`
- Original decision logic (Monte Carlo equity + strategy)
- 2-color deck detection (fixed)
- Fast fold disabled (fixed)

---

## 3. DETECTION FLOW MAP

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MULTI-TABLE BOT FLOW                             │
│                  python -m gamble.tools.cli_controller multi             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  cli_controller.py → MultiTableController                                │
│  - Takes --max-tables 10 --input dynamic                                │
│  - Creates TableScreenBased per table                                   │
│  - Creates Decision maker per hand                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  WINDOW DETECTION (AppleScript)                                         │
│  File: gamble/core/window_finder.py                                     │
│  - Finds GGPoker windows by process name "GGnet"                        │
│  - Returns positions in POINTS (macOS coordinates)                      │
│  - Filters for poker tables vs lobby                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  SCREENSHOT CAPTURE                                                      │
│  - PIL.ImageGrab.grab() → Full screen in PIXELS (3420x2224 on Retina)  │
│  - Crop to table region: POINTS * 2 = PIXELS                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ BUTTON DETECTION│    │ CARD DETECTION  │    │  POT/STACK OCR  │
│ (Hybrid: Color  │    │ (SmartCardDet.) │    │ (DynamicReader) │
│ + OCR fallback) │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
          │                         │                         │
          ▼                         ▼                         ▼
    HSV Ranges:              Template Match:             Pytesseract:
    - Call: Green            - 52 cards from            - Read numbers
    - Raise: Orange           MongoDB                   - Parse values
    - Fold: Gray             - TM_SQDIFF_NORMED         - Conf > 30
    - DealMeIn: Red          - Score < 0.35
          │                         │                         │
          │                  Suit Detection:                  │
          │                  - Red vs Black                   │
          │                  - OCR for ♠♥♦♣                   │
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  DECISION MAKING                                                         │
│  File: gamble/decisionmaker/decisionmaker.py                            │
│                                                                          │
│  Inputs:                                                                 │
│  - t.mycards: ['AH', 'KS']                                              │
│  - t.cardsOnTable: ['QD', '7C', '2H']                                   │
│  - t.totalPotValue: 150.0                                               │
│  - t.minCall: 30.0                                                      │
│  - t.minBet: 60.0                                                       │
│                                                                          │
│  Process:                                                                │
│  1. Hand lookup → "AKo" (Ace-King offsuit)                              │
│  2. Equity calc → 0.67 (67% win probability)                            │
│  3. Pot odds → pot / (pot + call) = 150/(150+30) = 0.83                │
│  4. Decision: equity > min_equity → RAISE                               │
│                                                                          │
│  Output: DecisionTypes.bet / .call / .check / .fold                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ACTION EXECUTION                                                        │
│  File: gamble/tools/mouse_mover.py                                      │
│                                                                          │
│  1. Map decision → button location (from detection)                     │
│  2. Move mouse with jitter (realistic movement)                         │
│  3. Click with random offset                                            │
│  4. Verify click worked (before/after screenshot)                       │
│  5. Log to adaptive_learner                                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  SELF-LEARNING                                                           │
│  Files: adaptive_learner.py, vision_analyzer.py, self_healer.py         │
│                                                                          │
│  On Success: Log action, update stats                                   │
│  On Failure: Analyze image → Generate new thresholds → Retry           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. CRITICAL ISSUES IDENTIFIED

### Issue #1: Conflicting HSV Ranges (CRITICAL)

The unified constants exist in `core/constants.py` but `tools/` modules have LOCAL definitions:

| File | Fold HSV Lower | Fold HSV Upper | Color |
|------|----------------|----------------|-------|
| core/constants.py | [0, 0, 30] | [180, 60, 120] | **GRAY** ✓ |
| smart_table_finder.py | [0, 80, 80] | [15, 255, 255] | **RED** ✗ |
| auto_player.py | [0, 0, 30] | [180, 60, 100] | **GRAY** ✓ |
| beast_mode.py | different | different | varies |
| ultimate_bot.py | different | different | varies |
| ten_table_bot.py | different | different | varies |
| button_detector.py (tools) | different | different | varies |

**Impact**: Some bots find Fold button, others don't.

**Fix Required**: All tools/ files should `from gamble.core.constants import HSV_RANGES`

### Issue #2: Files NOT Using Unified Constants

**Files that should import from core/constants.py but don't:**
- gamble/tools/ten_table_bot.py
- gamble/tools/dynamic_table_finder.py
- gamble/tools/auto_player.py
- gamble/tools/ultimate_bot.py
- gamble/tools/beast_mode.py
- gamble/tools/button_detector.py
- gamble/tools/smart_table_finder.py

**Files correctly using unified constants:**
- gamble/core/card_detector.py ✓
- gamble/core/base_bot.py ✓
- gamble/core/unified_learner.py ✓
- gamble/core/button_detector.py ✓
- gamble/core/window_finder.py ✓

### Issue #3: 6 Card Detection Systems

| System | File | Method | Status |
|--------|------|--------|--------|
| 1 | table_scraper.py | Template matching (MongoDB) | Original, working |
| 2 | smart_card_detector.py | White region + OCR suits | Fixed (2-color) |
| 3 | dynamic_card_detector.py | Brightness-based | Backup |
| 4 | ten_table_bot.py | VisualDetector class | Separate implementation |
| 5 | auto_player.py | White mask detection | Yet another |
| 6 | core/card_detector.py | Unified (combines 1-5) | RECOMMENDED |

**Impact**: Each bot may use different detection, leading to inconsistent behavior.

**Fix Required**: All bots should use `from gamble.core import CardDetector`

### Issue #4: 12 OCR Implementations

OCR is used in 12 different files with varying configurations:
- Confidence thresholds range from 30 to 70
- Some use pytesseract, some use tesserocr
- Different PSM modes
- Different whitelists

**Recommendation**: Consolidate to single OCR utility function

### Issue #5: Two ButtonDetector Classes

| Location | Purpose |
|----------|---------|
| gamble/core/button_detector.py | Unified, uses core/constants.py |
| gamble/tools/button_detector.py | Older, has LOCAL HSV ranges |

**Impact**: Which one gets used depends on import path.

---

## 5. OCR SYSTEM MAP

### Files Using OCR (12 total)

| File | What It Reads | Engine | Confidence |
|------|---------------|--------|------------|
| ocr_player.py | Buttons | pytesseract | 50 |
| dynamic_table_finder.py | Buttons (fallback) | pytesseract | 50 |
| dynamic_table_reader.py | Pot, Stacks, Cards | pytesseract | 30 |
| screen_operations.py | Card ranks | tesserocr | varies |
| dynamic_lobby_navigator.py | UI elements | pytesseract | 60 |
| ui_navigator.py | UI elements | pytesseract | 60 |
| smart_ui_automation.py | Buttons, text | pytesseract | 50 |
| self_healer.py | Buttons (fallback) | pytesseract | 50 |
| gg_registration.py | Game info | pytesseract | 60 |
| core/button_detector.py | Buttons (fallback) | pytesseract | 50 |
| table_scraper.py | Legacy pot/call | pytesseract | 60 |
| smart_card_detector.py | Suit symbols | pytesseract | varies |

### OCR Processing Pipeline

```
Image → Preprocess → Tesseract → Parse → Context Heuristics → Result

Preprocessing:
1. Resize (2x for better recognition)
2. Grayscale
3. Threshold (binary)
4. Invert (Tesseract prefers white on black)

Parsing:
- Numbers: Remove $, commas, K/M suffixes
- Buttons: Match keywords (call/fold/raise/check)
- Cards: Regex for rank+suit patterns
```

---

## 6. CARD DETECTION DEEP DIVE

### Template System

- **Source**: MongoDB at `https://dickreuter.com:7778/`
- **Table**: `Official GGPoker 6player`
- **Cards**: 52 templates, 50x70 pixels each
- **Format**: Base64-encoded PNG images
- **Algorithm**: cv2.matchTemplate with TM_SQDIFF_NORMED
- **Threshold**: Score < 0.35 = match

### 2-Color Deck Detection (FIXED)

GGPoker uses STANDARD 2-color deck:
- Hearts = Red
- Diamonds = Red
- Spades = Black
- Clubs = Black

**Detection flow**:
1. Extract card corner image
2. Convert to HSV
3. Count red vs black pixels
4. If red: OCR to distinguish ♥ vs ♦
5. If black: OCR to distinguish ♠ vs ♣

**Files with fix applied**:
- smart_card_detector.py ✓
- core/card_detector.py ✓
- ten_table_bot.py ✓

---

## 7. BUTTON DETECTION DEEP DIVE

### HSV Color Ranges (UNIFIED - from core/constants.py)

| Button | H Low | H High | S Low | S High | V Low | V High | Color |
|--------|-------|--------|-------|--------|-------|--------|-------|
| Call/Check | 35 | 85 | 50 | 255 | 50 | 255 | Green |
| Raise/Bet | 8 | 25 | 80 | 255 | 80 | 255 | Orange |
| Fold | 0 | 180 | 0 | 60 | 30 | 120 | Gray |
| Deal Me In | 0 | 15 | 100 | 255 | 100 | 255 | Red |

### Detection Strategy

1. **Primary**: HSV color detection (fast, ~90% success)
2. **Fallback**: OCR text detection (slower, more reliable)
3. **Self-Healing**: Vision analyzer (last resort, generates new thresholds)

### Click Verification

```python
# Before click
before_screenshot = ImageGrab.grab()

# Execute click
mouse.click(x, y)
time.sleep(0.3)

# After click
after_screenshot = ImageGrab.grab()

# Verify change
buttons_before = detect_buttons(before)
buttons_after = detect_buttons(after)
if len(buttons_after) < len(buttons_before):
    return SUCCESS  # Buttons disappeared = click worked
```

---

## 8. SELF-LEARNING SYSTEM

### Components

| Component | File | Purpose |
|-----------|------|---------|
| AdaptiveLearner | adaptive_learner.py | Logs actions, tracks success rates |
| VisionAnalyzer | vision_analyzer.py | Analyzes images, generates thresholds |
| SelfHealer | self_healer.py | Auto-fixes detection failures |
| UnifiedLearner | core/unified_learner.py | Combines all three |

### Data Files

```
data/learning/
├── thresholds.json      # Current adaptive thresholds
├── actions.jsonl        # All action logs
├── stats.json           # Success rate statistics
├── calibration.json     # Button color calibration
├── working_configs.json # Configs that worked
├── fixes.jsonl          # Auto-fix history
├── screenshots/         # Failure screenshots
└── debug/               # Annotated debug images
```

### Self-Healing Flow

```
Detection Fails
     ↓
VisionAnalyzer scans image
     ↓
Finds actual colors/positions
     ↓
Generates new HSV thresholds
     ↓
Updates adaptive_learner
     ↓
Retries detection
     ↓
Success → Saves working config
```

---

## 9. COORDINATE SYSTEM

### Retina Display (macOS)

```
POINTS = macOS coordinates (used for: AppleScript, mouse clicks)
PIXELS = actual image pixels (used for: screenshots, image processing)

Conversion:
- PIXELS = POINTS * 2 (screenshot crop)
- POINTS = PIXELS / 2 (mouse click)

Example:
- Window at (100, 200) POINTS
- Screenshot crop at (200, 400) PIXELS
- Button found at (300, 500) PIXELS in image
- Click at (100 + 300/2, 200 + 500/2) = (250, 450) POINTS
```

---

## 10. RECOMMENDATIONS

### Immediate Fixes

1. **Consolidate HSV ranges**: Update all tools/ files to import from core/constants.py
2. **Remove duplicate ButtonDetector**: Use core/button_detector.py everywhere
3. **Standardize OCR configs**: Create single OCR utility function

### Architecture Cleanup

1. **Deprecate redundant bots**: Keep only cli_controller.py as entry point
2. **Mark experimental files**: Add "_experimental" suffix to test files
3. **Enforce imports**: Use linting to ensure core/ imports

### Testing

1. **Create integration tests**: Verify detection works end-to-end
2. **Add visual regression tests**: Compare detection results across runs
3. **Monitor learning data**: Check stats.json for declining success rates

---

## 11. FILE INVENTORY

### Entry Points (42 total, use only 1)

| File | Purpose | Use? |
|------|---------|------|
| cli_controller.py | Multi-table + single | **YES** |
| ocr_player.py | OCR-only | Testing |
| auto_player.py | Visual detection | Testing |
| ten_table_bot.py | State machine | Testing |
| master_bot.py | Orchestrator | Testing |
| beast_mode.py | Aggressive | Testing |
| ultimate_bot.py | Feature-complete | Testing |
| spin_grinder.py | Spin & Gold | Testing |
| ... 34 more ... | Various | No |

### Detection Modules (use core/)

| Module | Location | Unified? |
|--------|----------|----------|
| CardDetector | core/card_detector.py | ✓ YES |
| ButtonDetector | core/button_detector.py | ✓ YES |
| WindowFinder | core/window_finder.py | ✓ YES |
| UnifiedLearner | core/unified_learner.py | ✓ YES |

---

## 12. QUICK REFERENCE

### Start Bot
```bash
python -m gamble.tools.cli_controller multi --max-tables 10
```

### Stop Bot
```bash
pkill -f "gamble.tools.cli_controller"
```

### Watch Logs
```bash
tail -f log/dm_assistant.log
```

### Check Learning Stats
```bash
cat data/learning/stats.json | python -m json.tool
```

### Check Thresholds
```bash
cat data/learning/thresholds.json | python -m json.tool
```
