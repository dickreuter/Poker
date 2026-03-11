# GGPoker Bot - Current Status & Instructions

---
## ⭐⭐⭐ THE ONE COMMAND TO RUN THE BOT ⭐⭐⭐

```bash
# START UNIFIED AUTONOMOUS MULTI-TABLE BOT
python -m gamble.multi_table_runner

# With options:
python -m gamble.multi_table_runner --target-tables 4 --max-tables 10

# Skip window resizing (if tables already positioned):
python -m gamble.multi_table_runner --no-standardize

# STOP BOT
pkill -f "gamble.multi_table_runner"

# CHECK STATUS
tail -f log/multi_table.log
```

**This is the ONLY command you need.** The unified bot combines EVERYTHING.

### What This Command Does:
1. Uses **ORIGINAL bot's COMPLETE logic** (all 25+ checks from main.py)
2. **Full preflop learning** (preflop_state.update_values called)
3. **Full history tracking** (all 13 fields updated)
4. **Multi-table support** (handles up to 10 tables simultaneously)
5. **Self-learning** (vision_analyzer auto-fixes detection failures)
6. **Self-healing** (adaptive_learner adjusts thresholds in real-time)
7. **Window standardization** (resizes/tiles tables on startup)
8. **Never crashes** (error handling at every level)
9. Uses **2-color deck** detection (Hearts/Diamonds=Red, Spades/Clubs=Black)
10. **Fast fold DISABLED** - strategy makes all decisions

### Recent Fixes (Jan 5, 2026):
- ✅ **UNIFIED BOT CREATED** - `multi_table_runner.py` now has COMPLETE original logic
- ✅ Added preflop sheet loading (was missing!)
- ✅ Added full verification chain (25+ checks from main.py)
- ✅ Added full history updates (13 fields, was only 6)
- ✅ Added preflop learning (update_values was not being called!)
- ✅ Added action options (Call2 for all-in, BetPlus increment)
- ✅ Added database logging (background thread)
- ✅ Added screenshot saving (log/screenshots/)
- ✅ Wired in self-learning (vision_analyzer, adaptive_learner)
- ✅ Added window standardization on startup
- ✅ Added never-stop error handling
- ✅ Fixed suit detection (was 4-color, now 2-color)
- ✅ Disabled fast fold (was causing premature folds)

### Files in the Unified System:
| File | Purpose |
|------|---------|
| `multi_table_runner.py` | **THE ONE BOT** - unified entry point |
| `scraper/table_screen_based.py` | Original detection (used by wrapper) |
| `decisionmaker/decisionmaker.py` | Original equity + strategy |
| `tools/adaptive_learner.py` | Self-learning (thresholds) |
| `tools/vision_analyzer.py` | Self-healing (auto-fix) |
| `data/learning/thresholds.json` | Learned parameters |

---
## 🚨 UNIFIED CORE MODULE - USE THIS FOR ALL NEW CODE 🚨

### Jan 4, 2026: Major Architecture Consolidation Complete

The codebase had **severe fragmentation**:
- 6 different card detection systems
- 7 different button detection systems
- 3 different window finders
- 3 overlapping learning systems
- 8 different bots with different decision logic

**NOW there is ONE unified system in `gamble/core/`**

### The New Architecture

```
gamble/core/
├── __init__.py           # Import everything from here
├── constants.py          # ALL shared constants (HSV ranges, thresholds)
├── window_finder.py      # UNIFIED window finding (replaces 3 implementations)
├── button_detector.py    # UNIFIED button detection (replaces 7 implementations)
├── card_detector.py      # UNIFIED card detection (replaces 6 implementations)
├── unified_learner.py    # UNIFIED learning (replaces 3 systems)
└── base_bot.py           # Abstract base class for ALL bots
```

### How to Use the Unified Module

```python
from gamble.core import (
    # Window finding
    WindowFinder,
    TableWindow,

    # Detection
    CardDetector,
    ButtonDetector,

    # Learning
    UnifiedLearner,
    get_learner,

    # Bot base class
    BaseBot,

    # Constants
    RETINA_SCALE,
    HSV_RANGES,
)

# Create a bot that uses unified systems
class MyBot(BaseBot):
    def run(self):
        while True:
            tables = self.find_tables()
            for table in tables:
                screenshot = self.capture_screenshot()
                self.process_table(table, screenshot)

    def process_table(self, table, screenshot):
        table_img = self.capture_table(table, screenshot)

        # Use unified detectors (inherited from BaseBot)
        cards = self.detect_cards(table_img, table)      # Returns ['AH', 'KS']
        buttons = self.detect_buttons(table_img, table)   # Returns {'call': {...}, 'fold': {...}}

        # Make decision (uses equity if DecisionMaker available)
        action = self.decide_action(cards, buttons)

        # Execute with verification
        if action and action in buttons:
            self.click_button(buttons[action], table)
```

### What the Unified Systems Provide

| Module | What It Does | Replaces |
|--------|--------------|----------|
| `WindowFinder` | Find GGPoker windows via AppleScript | 3 different WindowFinder classes |
| `ButtonDetector` | HSV color + OCR fallback + self-healing | 7 button detection implementations |
| `CardDetector` | Template + white region + self-healing | 6 card detection implementations |
| `UnifiedLearner` | Thresholds + logging + self-healing | adaptive_learner + vision_analyzer + self_healer |
| `BaseBot` | Abstract base with unified access | 8 different bot architectures |

### IMPORTANT: Don't Create New Detection Code!

❌ **WRONG** - Creating new detection in your bot:
```python
def my_find_buttons(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # ... yet another implementation ...
```

✅ **RIGHT** - Use the unified detector:
```python
from gamble.core import ButtonDetector
detector = ButtonDetector()
buttons = detector.detect(img, table_window)
```

### Self-Healing is Built In

When detection fails, the unified systems automatically:
1. Try multiple thresholds
2. Analyze the actual image
3. Generate new working thresholds
4. Save them for future use
5. Retry detection

You don't need to implement this yourself - it's in `UnifiedLearner.heal_detection()`.

---
## ⚠️ CRITICAL: READ THIS FIRST - FOR ALL CLAUDE SESSIONS ⚠️

### WE ARE IMPROVING THE ORIGINAL BOT, NOT REPLACING IT

The **ORIGINAL bot** (`gamble/scraper/table_scraper.py`) already has:
- ✅ **Equity calculations** - calculates hand strength
- ✅ **Opponent tracking** - reads all player stack sizes
- ✅ **Pot tracking** - current pot, total pot
- ✅ **Board reading** - flop/turn/river cards
- ✅ **Position tracking** - dealer button, player positions
- ✅ **Strategy logic** - when to fold/call/raise based on equity
- ✅ **Template matching** - 52 card templates in MongoDB

### WHAT WE ARE ADDING (not replacing):
1. **Multi-table support** - handle 10 tables simultaneously
2. **Dynamic UI navigation** - OCR-based lobby navigation (no hardcoded coords)
3. **Dynamic card detection** - find cards visually (any table size)
4. **Click verification** - confirm actions worked
5. **Unicode minus fix** - macOS AppleScript bug
6. **Self-improving system** - adaptive learning with automatic threshold adjustment
7. **Vision Analyzer** - bot analyzes its own screenshots and fixes detection automatically

---

## FULLY AUTONOMOUS SELF-LEARNING (VisionAnalyzer)

### The Bot Fixes ITSELF - No Human Needed!

When detection fails, the bot:
1. **Takes screenshot** of actual game state
2. **Analyzes image** to find what's REALLY there (actual colors, positions)
3. **Compares** expected vs actual detection
4. **Auto-generates** new thresholds that work
5. **Applies fix** immediately
6. **Retries** with new parameters
7. **Saves** working configurations for future

### How It Works In Real-Time

```
[Button detection fails]
     ↓
[Vision Analyzer activates]
     ↓
[Scans image for ALL colored rectangles]
     ↓
[Finds: "Green button at (500,600) HSV=(45,180,200)"]
     ↓
[Current threshold HSV=(35,80,80) missed it!]
     ↓
[Auto-generates new threshold: HSV=(30,130,150)]
     ↓
[Applies fix to adaptive_learner thresholds]
     ↓
[Retries detection - SUCCESS!]
     ↓
[Saves working config for next time]
```

### Files Involved

| File | Purpose |
|------|---------|
| `tools/vision_analyzer.py` | Core vision analysis and auto-fix |
| `tools/adaptive_learner.py` | Stores and applies learned thresholds |
| `data/learning/working_configs.json` | Successful configurations |
| `data/learning/fixes.jsonl` | History of all auto-fixes |
| `data/learning/debug/` | Annotated screenshots showing what was found |

### Vision Analyzer API

```python
from gamble.tools.vision_analyzer import (
    auto_fix_detection,   # Full auto-fix (buttons + cards + regions)
    auto_fix_buttons,     # Fix button detection only
    auto_fix_cards,       # Fix card detection only
    get_analyzer          # Get singleton analyzer
)

# When button detection fails:
result = auto_fix_buttons(screenshot)
# Returns: {
#   'fixed': True,
#   'new_thresholds': {'hsv_green_lower': [30, 130, 150], ...},
#   'buttons_found': {'green': [{x, y, w, h, hsv}, ...]}
# }

# When card detection fails:
result = auto_fix_cards(screenshot)
# Returns: {
#   'fixed': True,
#   'cards': [{x, y, w, h}, ...],
#   'threshold': 160  # Working white pixel threshold
# }

# Full analysis:
result = auto_fix_detection(screenshot)
# Fixes buttons, cards, and screen regions all at once
```

### What Gets Auto-Fixed

| Detection Type | What It Analyzes | What It Fixes |
|----------------|------------------|---------------|
| **Buttons** | Scans for colored rectangles | HSV ranges, min area |
| **Cards** | Tries white thresholds 200→100 | white_pixel_min, card region |
| **Card Backs** | Detects red/blue patterns | Knows when cards face-down |
| **Regions** | Analyzes screen layout | button_region_y_start, etc |
| **Click Offset** | Compares expected vs actual | click_offset_x/y |

### Integration in Main Bot

The bot automatically uses vision analyzer when detection fails:

```python
# In auto_player.py process_table():

buttons = self.find_buttons(table_img, table)

# === SELF-LEARNING: If no buttons, auto-fix ===
if not buttons:
    log.info("SELF-LEARNING: No buttons found, running vision analyzer...")
    fix_result = auto_fix_buttons(table_img)

    if fix_result.get('fixed'):
        log.info("SELF-LEARNING: Thresholds updated, retrying...")
        self.button_area_min = get_threshold('button_area_min', 2000)
        buttons = self.find_buttons(table_img, table)  # Retry!

        if buttons:
            log.info("SELF-LEARNING: SUCCESS! Found buttons after auto-fix")
```

### Debug Output

Vision analyzer saves annotated images showing what it found:
```
data/learning/debug/vision_analysis_20260104_170530.png
```

These show:
- Green boxes around detected green buttons
- Orange boxes around detected orange buttons
- Yellow boxes around detected cards
- Labels for each detection

### Self-Learning Loop

```
┌─────────────────────────────────────────────────────────────┐
│                    BOT RUNNING                              │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │   Try Detection     │
              └─────────────────────┘
                         │
            ┌────────────┴────────────┐
            │                         │
            ▼                         ▼
      [SUCCESS]                 [FAILURE]
            │                         │
            ▼                         ▼
    ┌───────────────┐     ┌─────────────────────┐
    │ Take action   │     │ Vision Analyzer     │
    │ Log success   │     │ analyzes screenshot │
    └───────────────┘     └─────────────────────┘
                                   │
                                   ▼
                          ┌─────────────────────┐
                          │ Find actual colors  │
                          │ Find actual positions│
                          └─────────────────────┘
                                   │
                                   ▼
                          ┌─────────────────────┐
                          │ Generate new        │
                          │ thresholds          │
                          └─────────────────────┘
                                   │
                                   ▼
                          ┌─────────────────────┐
                          │ Apply fix           │
                          │ Save to thresholds  │
                          └─────────────────────┘
                                   │
                                   ▼
                          ┌─────────────────────┐
                          │ RETRY DETECTION     │──→ [SUCCESS!]
                          └─────────────────────┘
```

### Claude's Role (Minimal Now!)

Claude only needs to intervene for:
1. **Major code bugs** - actual Python errors
2. **New UI layouts** - if GGPoker redesigns completely
3. **New game types** - adding support for new games

The bot handles:
- ✅ Color threshold adjustments
- ✅ Position/region adjustments
- ✅ Size threshold adjustments
- ✅ OCR confidence tuning
- ✅ Click offset learning
- ✅ Table size adaptation

---

## SELF-IMPROVING SYSTEM (AdaptiveLearner)

### How It Works
The bot learns and adapts in real-time:
1. **Logs all actions** - button detection, card detection, clicks
2. **Tracks success/failure rates** - per action type
3. **Adjusts thresholds dynamically** - if detection fails, thresholds change
4. **Reports issues to CLAUDE_FEEDBACK.md** - for Claude to read and fix

### Files Involved
| File | Purpose |
|------|---------|
| `tools/adaptive_learner.py` | Core learning system |
| `data/learning/actions.jsonl` | All actions log |
| `data/learning/thresholds.json` | Current adaptive thresholds |
| `data/learning/stats.json` | Success rate statistics |
| `data/learning/screenshots/` | Screenshots of failures for Claude to analyze |
| `CLAUDE_FEEDBACK.md` | Issues for Claude to fix |

### Screenshot Evidence
When detection fails, the system automatically saves screenshots:
- `card_detection_fail_YYYYMMDD_HHMMSS.png` - Table when cards not detected
- `button_detection_fail_YYYYMMDD_HHMMSS.png` - Table when buttons not found
- `spin_gold_detection_fail_YYYYMMDD_HHMMSS.png` - Lobby when icon not found

Claude should look at these to understand WHY detection failed.

### How Claude Uses This
1. **Read CLAUDE_FEEDBACK.md** at start of session
2. **Check data/learning/stats.json** for low success rates
3. **Fix issues** reported by the adaptive learner
4. **Improve thresholds** in adaptive_learner.py if needed

### Adaptive Thresholds
```python
# In data/learning/thresholds.json
{
    "white_pixel_min": 180,      # For card detection (lowered if cards not detected)
    "card_area_min": 2000,       # Minimum card region size
    "button_area_min": 1500,     # Minimum button size
    "match_score_max": 0.35,     # Template matching threshold
    "action_cooldown": 1.5,      # Seconds between actions
    "click_verify_delay": 0.3    # Wait before verifying click
}
```

### Auto-Adjustment Rules
- **card_detection < 50% success** → Lower `white_pixel_min` by 10
- **button_click < 70% success** → Increase `click_verify_delay` by 0.1

### Usage in Bots
```python
from gamble.tools.adaptive_learner import log_action, report_issue, get_threshold

# Get adaptive threshold
white_min = get_threshold('white_pixel_min', 180)

# Log action result
log_action('card_detection', success=True, details={'cards': ['AH', 'KS']})

# Report issue for Claude to fix
report_issue('card_detection', 'Cards face-down but buttons visible')
```

### Game Type Tracking
The system tracks which game type is being played:
- `spin_gold` - Spin & Gold tournaments
- `rush_cash` - Rush & Cash fast-fold
- `tournament` - Regular tournaments
- `cash` - Regular cash games

This helps identify game-specific detection issues.

### Debug Screenshots (for Claude to analyze)
```python
from gamble.tools.adaptive_learner import save_debug_screenshot

# Save when detection fails - Claude can look at these later
save_debug_screenshot('table_detection', table_image, reason='not_ready')
save_debug_screenshot('card_detection', table_image, reason='no_cards')
```

Debug screenshots saved to: `data/learning/debug/`

### Complete API Reference
```python
from gamble.tools.adaptive_learner import (
    log_action,           # Log any action with success/fail
    report_issue,         # Report issue for Claude to fix
    get_threshold,        # Get adaptive threshold value
    save_screenshot,      # Save screenshot for learning
    save_debug_screenshot,# Save debug screenshot with reason
    get_learner           # Get the singleton learner instance
)

# Full log_action signature
log_action(
    action_type='card_detection',  # What action
    success=True,                   # Did it work?
    details={'cards': ['AH', 'KS']},# Extra info
    screenshot=table_img,           # Optional: save image
    save_on_fail=True               # Auto-save screenshot on failure
)

# Full report_issue signature
report_issue(
    component='card_detection',
    description='Cards showing but not detected',
    screenshot_path='/path/to/image.png',
    severity='high'  # low, medium, high
)
```

### What Claude Should Do Each Session
1. **Check CLAUDE_FEEDBACK.md** for reported issues
2. **Check data/learning/stats.json** for low success rates:
   ```bash
   cat data/learning/stats.json
   ```
3. **Look at failure screenshots**:
   ```bash
   ls -la data/learning/screenshots/
   ls -la data/learning/debug/
   ```
4. **Fix issues** based on what you see in the images
5. **Update thresholds** if needed in adaptive_learner.py

---

## AUTONOMOUS SELF-HEALING SYSTEM (SelfHealer)

### The Bot Fixes Itself - No Human Needed!

When detection fails, the bot doesn't just log it and wait for Claude.
**It fixes itself in real-time:**

1. **Takes screenshot** of actual game state
2. **Analyzes** what's really on screen (colors, shapes, text)
3. **Auto-adjusts** thresholds, color ranges, search regions
4. **Retries** with new parameters
5. **Saves** successful calibrations for future use

### How It Works

```python
from gamble.tools.self_healer import get_healer, heal_buttons, heal_cards, auto_heal

# When button detection fails:
healer = get_healer()
buttons = healer.heal_button_detection(table_screenshot)
# Returns: {'call': {x, y, w, h, color}, 'fold': {...}, ...}

# When card detection fails:
cards = healer.heal_card_detection(table_screenshot)
# Returns: {'cards': [{x, y, w, h}, ...], 'threshold': 160}

# Full auto-heal (finds everything):
result = healer.auto_heal_table(table_screenshot)
# Returns: {'buttons': {...}, 'cards': {...}, 'healed': True}
```

### Button Healing Process

1. **Sample colors** from bottom of screen
2. **Find all colored rectangles** (buttons are colorful)
3. **Classify by color**:
   - Green → Call/Check
   - Orange → Raise/Bet
   - Gray → Fold
4. **Update calibration** with found colors
5. **Fallback to OCR** if color detection fails

### Card Healing Process

1. **Try multiple white thresholds**: 200, 180, 160, 140, 120
2. **Find white card-shaped rectangles**
3. **Update threshold** when cards are found
4. **Detect card backs** (red/blue patterns) if face-down

### Auto-Calibration

The system learns button colors from the actual game:

```json
// data/learning/calibration.json
{
  "button_colors": {
    "call": [[45, 200, 180], [42, 195, 175], ...],  // HSV samples
    "fold": [[0, 50, 100], [5, 45, 95], ...]
  },
  "card_regions": {
    "y_start_pct": 0.65,
    "y_end_pct": 0.85
  }
}
```

These samples are averaged to update HSV color ranges automatically.

### Integration with Main Bot

The self-healer is integrated into `cli_controller.py`:

```python
# In the fallback detection loop:
if not buttons:
    log.info("SELF-HEALING: Button detection failed, attempting auto-heal...")
    buttons = healer.heal_button_detection(table_img)
    if buttons:
        log.info(f"SELF-HEALING: Successfully found {list(buttons.keys())}")

if not cards:
    log.info("SELF-HEALING: Card detection failed, attempting auto-heal...")
    healed_cards = healer.heal_card_detection(table_img)
```

### Files Involved

| File | Purpose |
|------|---------|
| `tools/self_healer.py` | Main self-healing system |
| `data/learning/calibration.json` | Saved calibrations |
| `data/learning/thresholds.json` | Updated by self-healer |

### Self-Healing Actions Logged

The self-healer logs all its actions:
- `self_heal_buttons` - Button healing attempts
- `self_heal_cards` - Card healing attempts
- `threshold_change` - When thresholds are auto-adjusted
- `calibration_update` - When colors are learned

### Why This Matters

**Before**: Bot fails → logs error → waits for Claude → Claude fixes it hours later
**Now**: Bot fails → self-healer kicks in → fixes itself in milliseconds → keeps playing

---

### THE ORIGINAL BOT READS ALL THIS:
```python
# From table_scraper.py - DO NOT LOSE THIS FUNCTIONALITY
self.my_cards = None           # Player's hole cards
self.table_cards = None        # Community cards (flop/turn/river)
self.current_round_pot = None  # Current street pot
self.total_pot = None          # Total pot size
self.dealer_position = None    # Button position
self.players_in_game = None    # Who's still in hand
self.player_funds = None       # All stack sizes
self.player_pots = None        # Current bets per player
self.call_value = None         # Amount to call
self.raise_value = None        # Raise amount
```

### DO NOT:
- ❌ Create simplified bots that only fold/call (we did this by mistake)
- ❌ Ignore opponent information
- ❌ Skip pot/equity calculations
- ❌ Remove existing functionality

### DO:
- ✅ Improve TableScraper with dynamic detection
- ✅ Keep all opponent/pot/equity tracking
- ✅ Add multi-table orchestration ON TOP of original
- ✅ Use OCR for UI navigation, not card reading

### ARCHITECTURE - HOW IT FITS TOGETHER:
```
┌─────────────────────────────────────────────────────────────┐
│                    MASTER CONTROLLER                        │
│  (multi_table_controller.py / master_bot.py)               │
│  - Manages 10 tables simultaneously                         │
│  - Priority queue for actions                               │
│  - Opens new tables when needed                             │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   TABLE 1     │    │   TABLE 2     │    │   TABLE N     │
│ TableScraper  │    │ TableScraper  │    │ TableScraper  │
│ (ORIGINAL)    │    │ (ORIGINAL)    │    │ (ORIGINAL)    │
└───────────────┘    └───────────────┘    └───────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│              DYNAMIC DETECTION LAYER (NEW)                  │
│  - smart_card_detector.py - finds cards visually            │
│  - dynamic_table_finder.py - finds tables by green felt     │
│  - OCR for pot sizes, stack sizes                           │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│              UI NAVIGATION (NEW)                            │
│  - ui_navigator.py / dynamic_lobby_navigator.py             │
│  - OCR to find "Spin & Gold", "Play Now" buttons            │
│  - Registers for new tables                                 │
└─────────────────────────────────────────────────────────────┘
```

### KEY FILES - ORIGINAL (keep these):
| File | Purpose |
|------|---------|
| `scraper/table_scraper.py` | Reads ALL game state (cards, pots, opponents) |
| `decisionmaker/decisionmaker.py` | Equity calculations, strategy |
| `tools/mongo_manager.py` | Card templates from MongoDB |

### KEY FILES - NEW (improvements):
| File | Purpose |
|------|---------|
| `tools/smart_card_detector.py` | Dynamic card detection |
| `tools/dynamic_table_finder.py` | Find tables by green felt + OCR hybrid button detection |
| `tools/dynamic_lobby_navigator.py` | OCR lobby navigation |
| `tools/dynamic_table_reader.py` | **NEW** - Full table OCR (pot, stacks, call/raise values) |
| `tools/ten_table_bot.py` | Multi-table orchestration |

### INTEGRATION COMPLETED (Jan 4, 2026)

The following integrations have been made to keep the ORIGINAL bot working with dynamic detection:

#### 1. OCR Button Detection in `dynamic_table_finder.py`
- Added `find_buttons_ocr()` - finds buttons by text (Check, Fold, Call, Raise)
- Added `find_buttons_hybrid()` - OCR first, color fallback
- `DynamicMouseMover` now uses hybrid detection

#### 2. Dynamic Table Reader in `dynamic_table_reader.py`
New file that provides full-table OCR reading:
- `get_pot()` - reads pot from top-center of table
- `get_stacks()` - reads all player stack sizes
- `get_call_amount()` - reads call value from button text
- `get_raise_amount()` - reads raise value from button text
- `get_board_cards()` - OCR for community cards
- `get_hole_cards()` - OCR for player's cards

#### 3. TableScraper Fallbacks in `table_scraper.py`
Original methods now have dynamic fallbacks:
- `get_pots()` → falls back to `DynamicTableReader.get_pot()`
- `get_call_value()` → falls back to `DynamicTableReader.get_call_amount()`
- `get_raise_value()` → falls back to `DynamicTableReader.get_raise_amount()`
- Button detection → falls back to color detection

#### How It Works Now:
```
1. Original template-based detection runs FIRST
2. If template detection fails (returns 0 or None):
   - DynamicTableReader kicks in
   - Uses OCR to scan entire table
   - Parses all numbers and text
   - Returns values based on position heuristics
3. Equity calculations and strategy continue as before
```

---

## STATUS: NEW SYSTEMS CREATED (Jan 4, 2026)

### NEW: Complete 10-Table System

Three new unified systems have been created to fix all previous issues:

#### 1. `ten_table_bot.py` - Autonomous Multi-Table Player
```bash
python -m gamble.tools.ten_table_bot --max-tables 10
```

Features:
- **Unified visual detection** - works regardless of table size/position
- **Screenshot verification** - verifies every click worked
- **Priority-based actions** - handles most urgent table first
- **Handles face-up AND face-down cards**

#### 2. `ui_navigator.py` - Lobby Navigation with OCR
```bash
python -m gamble.tools.ui_navigator --action startup --tables 5
```

Features:
- **OCR-based text finding** - clicks buttons by reading their text
- **Color-based button detection** - finds green/orange buttons visually
- **Automatic table registration** - navigates to Spin & Gold and registers
- **Popup handling** - closes error dialogs automatically

#### 3. `master_bot.py` - Complete Autonomous System
```bash
python -m gamble.tools.master_bot --tables 10 --stake "$1"
```

Features:
- **Full lifecycle management** - opens tables, plays, maintains count
- **Auto-recovery** - reopens tables if they close
- **Stats tracking** - actions per minute, uptime, etc.

### KEY FIXES APPLIED

1. **Unicode minus bug** - Fixed in ALL files (macOS returns − instead of -)
2. **Card detection** - Uses visual white-region detection, not hardcoded coords
3. **Button detection** - HSV color matching with smart filtering
4. **Click verification** - Screenshot before/after comparison
5. **Multi-table priority** - Processes highest-urgency table first

---

## PREVIOUS STATUS (for reference)

### What Previously Worked
- 52/52 card templates uploaded to MongoDB (50x70 pixels each)
- Table window detection via AppleScript
- Button color detection (fold=gray, call=green, raise=orange)
- Template matching infrastructure

### What Previously Did NOT Work (NOW FIXED)
- **Card detection fails on live tables** - FIXED: now uses visual detection
- The `left_card_area` and `right_card_area` coordinates are HARDCODED - FIXED: dynamic detection
- Different table sizes = different card positions - FIXED: percentage-based search areas

---

## THE PROBLEM

The system uses HARDCODED pixel coordinates for card areas:
```python
# In MongoDB table config - THESE ARE WRONG
left_card_area: {'x1': 800, 'y1': 955, 'x2': 840, 'y2': 1010}
right_card_area: {'x1': 885, 'y1': 955, 'x2': 925, 'y2': 1010}
```

These coordinates only work for ONE specific table size. When the table is different size or position, the coordinates point to the WRONG place (table felt instead of cards).

---

## THE SOLUTION

**Make card detection FULLY DYNAMIC.** Don't use hardcoded coordinates.

### How Cards Should Be Found:
1. Get table window position via AppleScript (already works)
2. Crop table from screenshot (already works)
3. **Find white card rectangles dynamically** - cards are white, table is green
4. Extract rank+suit corner from each found card
5. Match against templates

### Implementation Plan:

```python
def find_player_cards_dynamic(table_img):
    """Find cards by detecting white rectangles on green felt"""
    img = np.array(table_img)

    # Cards are in bottom 30% of table, center 40%
    h, w = img.shape[:2]
    search_area = img[int(h*0.70):, int(w*0.30):int(w*0.70)]

    # Find white regions (cards)
    white_mask = (search_area[:,:,0] > 200) & \
                 (search_area[:,:,1] > 200) & \
                 (search_area[:,:,2] > 200)

    # Find contours of white regions
    contours = cv2.findContours(...)

    # Filter for card-shaped rectangles (aspect ratio ~0.7)
    cards = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if 0.6 < h/w < 0.8 and area > 3000:  # Card-shaped
            cards.append((x, y, w, h))

    # Extract rank+suit corner (top-left 50x70 pixels)
    card_corners = [extract_corner(card) for card in cards]

    # Match against templates
    return [match_template(corner) for corner in card_corners]
```

---

## FILE STRUCTURE

```
gamble/tools/
├── cli_controller.py      # Main bot entry point - NEEDS FIX
├── smart_card_detector.py # Has dynamic detection - USE THIS
├── beast_mode.py          # Standalone bot with color detection
├── mongo_manager.py       # Template storage API
├── screen_operations.py   # Template matching functions
└── constants.py           # Screen/retina constants
```

---

## KEY FILES TO MODIFY

### 1. cli_controller.py (line ~200-300)
Current card detection uses fixed coordinates. Change to:
```python
from gamble.tools.smart_card_detector import SmartCardDetector

detector = SmartCardDetector(table_dict)
my_cards = detector.detect_player_cards(table_screenshot)
```

### 2. smart_card_detector.py
The `SmartCardDetector` class has the RIGHT approach:
- `_find_white_card_regions()` - finds cards by color
- `_match_card_template()` - matches against templates
- Make sure it searches the CORRECT region (bottom center of table)

---

## RUNNING THE BOT

```bash
# Test table detection only
python -m gamble.tools.cli_controller test

# Run bot (after fixing card detection)
python -m gamble.tools.cli_controller start --input dynamic

# Alternative: beast_mode.py (simpler, color-based)
python -m gamble.tools.beast_mode --max-tables 1
```

---

## COORDINATE SYSTEM (IMPORTANT)

Retina display = 2x scaling:
- **POINTS** = macOS coordinates (for mouse clicks, window positions)
- **PIXELS** = actual image pixels (for screenshots, cropping)

```python
# Window position from AppleScript = POINTS
# Screenshot crop = POINTS * 2 = PIXELS
# Mouse click = PIXELS / 2 = POINTS

RETINA_SCALE = 2

# Example:
window_x_pt = 100  # Points (from AppleScript)
pixel_x = window_x_pt * RETINA_SCALE  # 200 pixels (for image crop)
click_x = pixel_x // RETINA_SCALE  # 100 points (for mouse)
```

---

## BUTTON DETECTION (Works)

Buttons are detected by color in HSV:
```python
BUTTON_COLORS = {
    'call': {'lower': [35, 50, 50], 'upper': [85, 255, 255]},   # Green
    'raise': {'lower': [10, 80, 80], 'upper': [25, 255, 255]},  # Orange
    'fold': {'lower': [0, 0, 40], 'upper': [180, 50, 120]},     # Gray
}
```

See `beast_mode.py:find_buttons()` for working implementation.

---

## TEMPLATE INFO

All 52 card templates stored in MongoDB at `https://dickreuter.com:7778/`
- Table name: `Official GGPoker 6player`
- Template size: 50x70 pixels (rank+suit corner)
- GGPoker uses 4-color deck: spades=black, hearts=red, diamonds=blue, clubs=green

---

## NEXT STEPS (IN ORDER)

1. **Fix SmartCardDetector** to search correct region for player cards
2. **Integrate SmartCardDetector** into cli_controller.py
3. **Test with live table** - verify cards are found
4. **Test button clicking** - verify actions work
5. **Add multi-table support** - process multiple windows

---

## QUICK DEBUG

```bash
# Check if GGPoker is running
osascript -e 'tell application "System Events" to name of processes' | grep -i gg

# List all GGPoker windows
osascript -e 'tell application "System Events" to tell process "GGnet" to name of every window'

# Watch logs
tail -f /Users/sebastian/Developer/Gamble/gamble/log/dm_assistant.log
```

---

## DO NOT

- Use hardcoded pixel coordinates for cards
- Assume table is always same size
- Skip the coordinate conversion (points vs pixels)
- Ignore the SmartCardDetector - it has the right approach
- Remove or modify this document - ALWAYS ADD to it

---

## SESSION LOG - Jan 4, 2026

### What Was Done
1. **Fixed all 52 card templates** - uploaded to MongoDB at correct 50x70 size
2. **Created auto_player.py** - new bot with dynamic detection
3. **Bot successfully played** - clicking Fold and Deal Me In buttons
4. **Card detection NOT working** - white mask detection finds contours but not matching cards

### auto_player.py Location
`/Users/sebastian/Developer/Gamble/gamble/tools/auto_player.py`

### Bot Output (Working)
```
INFO - Loaded 102 templates
INFO - Buttons found: ['fold']
INFO - Cards not detected
INFO - Clicked Fold at (322, 624)
INFO - Buttons found: ['raise', 'fold']
INFO - Cards not detected
INFO - Clicked Fold at (322, 624)
```

### Known Issues
1. **Card detection returns empty** - `detect_cards()` finds white contours but no cards matched
2. **Button detection sometimes false positive** - Deal Me In detected when it shouldn't be
3. **No call button detected** - only fold and raise show up

### Debug Steps Taken
1. Took table screenshot → `/tmp/debug/table.png`
2. Extracted search region (bottom 40%) → `/tmp/debug/search.png`
3. Created white mask → `/tmp/debug/white.png`
4. Found contours but no card-shaped ones matched

### Card Detection Algorithm (in auto_player.py)
```python
def detect_cards(self, table_img):
    # Search bottom 40% of table
    search_y_start = int(h_img * 0.60)
    search_region = img[search_y_start:, :]

    # Find white pixels (cards are white)
    white_mask = (
        (search_region[:,:,0] > 180) &
        (search_region[:,:,1] > 180) &
        (search_region[:,:,2] > 180)
    )

    # Find contours and filter for card-shaped
    # Match against templates
```

### What Still Needs Fixing
1. **Card detection** - find why white regions aren't being matched as cards
2. **Template matching** - verify templates work with extracted card regions
3. **Call button detection** - HSV range may be wrong
4. **Multi-table support** - handle multiple windows

### How to Run
```bash
# Start the bot
python -m gamble.tools.auto_player

# Watch logs
tail -f /Users/sebastian/Developer/Gamble/gamble/log/auto_player.log

# Kill bot
pkill -f auto_player
```

### Registration Flow (manual)
1. Focus GGPoker lobby
2. Click on Spin & Gold tile ($0.25 is first)
3. Click "Play Now" button
4. Wait for table to open (~8 seconds)

---

## CRITICAL RULES FOR FUTURE SESSIONS

1. **NEVER remove content from this file** - only add
2. **NEVER use hardcoded sizes** - buttons and cards can be any size
3. **ALWAYS use color detection** - not pixel coordinates
4. **ALWAYS handle Retina** - multiply by 2 for pixels, divide by 2 for clicks
5. **ALWAYS test with live table** - don't assume
6. **LOG EVERYTHING** - add to this file what was tried

---

## GGPoker Window Names

- Main lobby: `"GGPoker"`
- Poker table: Contains keywords like `"Spin"`, `"Gold"`, `"Hold"`, `"Cash"`, `"Blinds"`, `"NL"`
- Cashier: `"Cashier"`

### AppleScript to Find Tables
```applescript
tell application "System Events"
    tell process "GGnet"
        repeat with w in windows
            set winName to name of w as text
            if winName contains "Spin" or winName contains "Gold" then
                -- This is a poker table
            end if
        end repeat
    end tell
end tell
```

---

## Color Ranges (HSV)

### Buttons
- **Call/Check (Green)**: H=35-85, S=80-255, V=80-255
- **Raise/Bet (Orange)**: H=8-25, S=100-255, V=100-255
- **Fold (Gray)**: H=0-180, S=0-60, V=30-100

### Cards
- **White background**: R>180, G>180, B>180

### Suits (STANDARD 2-color deck)
- **Spades**: Black
- **Hearts**: Red
- **Diamonds**: Red
- **Clubs**: Black

**NOTE**: Previous session incorrectly assumed 4-color deck - THIS WAS WRONG!

---

## LESSON LEARNED: COORDINATE MISTAKES (Jan 4, 2026 evening)

### The Problem
I kept clicking wrong positions because I was GUESSING coordinates by looking at screenshots.

### Why It Failed
1. Screenshots are in PIXELS (2x scale on Retina)
2. Click positions need POINTS (1x scale)
3. Visually estimating positions from screenshots is INACCURATE

### The Solution
**NEVER guess coordinates. ALWAYS use visual detection:**
1. Use color detection to find buttons/tiles
2. Use template matching to find specific UI elements
3. Use contour detection to find shapes

### Example: Finding "Play Now" Button
```python
# WRONG: Guessing coordinates
play_x = lobby_x + 350  # This is a guess and will be wrong

# RIGHT: Find green button by color
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
green_mask = cv2.inRange(hsv, (35, 80, 80), (85, 255, 255))
contours = cv2.findContours(green_mask, ...)
# Find largest green rectangle = Play Now button
```

### Retina Display Conversion (MEMORIZE THIS)
```
POINTS = what macOS/AppleScript gives you
PIXELS = what screenshots show (POINTS * 2)

To click: use POINTS
To crop screenshot: use PIXELS (POINTS * 2)
To convert pixel position to click: divide by 2
```

---

## FAILURE LOG - Jan 4, 2026 (29 min wasted on card detection)

### What Went Wrong
1. **Spent 29 minutes "debugging" but never actually fixed it**
2. **Kept tweaking thresholds instead of understanding the actual problem**
3. **Didn't look at the actual card images to see what they look like**
4. **Hardcoded values (white threshold 150-180) instead of adaptive detection**

### The REAL Problem
Looking at the table screenshot:
- Player cards at bottom show CARD BACKS (dark pattern), NOT white cards
- Only face-up cards (opponents, board) are white
- White detection will NEVER find face-down cards

### What Should Have Been Done
1. **LOOK at the screenshot first** - understand what you're detecting
2. **Cards are face-down** when it's not your turn to act
3. **Need to detect card backs OR wait until cards are face-up**
4. **OR use the "Show" button text which reveals card values (9♥ 4♠)**

### The Fix Required
Don't look for white cards at player position. Instead:
1. Look for the "Check/Call/Fold/Raise" buttons which indicate it's your turn
2. When buttons are visible, cards should be face-up
3. OR read the card values from the "Show X♥ Y♠" buttons at bottom

### STOP DOING THIS
- Don't spend 30 minutes tweaking numbers
- Don't guess - LOOK at the actual images
- Don't assume cards are white - they might be face-down
- Don't keep running the same broken code hoping it works

---

## CRITICAL: ALWAYS DO THIS BEFORE CLICKING

### 1. Take FULL SCREEN screenshot first
```python
from PIL import ImageGrab
screenshot = ImageGrab.grab()  # Full screen in PIXELS (3420x2224 on Retina)
screenshot.save('/tmp/debug/full_screen.png')
```

### 2. Get CURRENT window position (it MOVES!)
```python
# Window positions CHANGE - never assume!
script = '''tell application "System Events" to tell process "GGnet" to position of window 1'''
result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
# Returns POINTS - multiply by 2 for PIXELS
```

### 3. LOOK at the screenshot before clicking
- Open the image and MEASURE pixel positions
- Don't guess coordinates
- The full screen is 3420x2224 PIXELS = 1710x1112 POINTS

### 4. Convert properly
```
PIXEL position on full screen → divide by 2 → POINT position for clicking
Window position from AppleScript = already in POINTS
```

### 5. Verify click target
- Draw a dot on the screenshot at your calculated position
- Make sure it's actually on the button

---

## USE OCR - NOT COORDINATES! (THIS WORKS)

**Coordinates NEVER work reliably. USE OCR instead.**

### Find buttons by text with pytesseract:
```python
import pytesseract
from PIL import ImageGrab

screenshot = ImageGrab.grab()
data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)

for i, text in enumerate(data['text']):
    if 'Play' in text and 'Now' in text:
        x, y = data['left'][i], data['top'][i]  # PIXELS
        click_x, click_y = x // 2, y // 2  # Convert to POINTS
        # Click there!
```

### Why OCR works:
- Finds text WHEREVER it is on screen
- Doesn't matter if window moved
- Doesn't require coordinate guessing
- Works with any screen resolution

### What can be found with OCR:
- "Play Now" buttons
- "Fold", "Call", "Check", "Raise" buttons
- Card values ("A♠", "K♥", etc.)
- Pot size, stack sizes
- Player names

### ALWAYS USE OCR FOR:
- Finding UI elements
- Reading card values
- Finding action buttons

---

## SESSION LOG - Jan 4, 2026 (Evening Session - MAJOR FIXES)

### BUGS FIXED

#### 1. Unicode Minus Sign Bug (CRITICAL)
**Problem**: macOS AppleScript returns Unicode minus sign `−` (U+2212) instead of ASCII minus `-` (U+002D) for negative window positions. This caused `int()` to fail with "invalid literal".

**Fixed in these files**:
- `dynamic_table_finder.py:141`
- `gg_automation.py:152`
- `beast_mode.py:114`
- `spin_grinder.py:110`
- `ultimate_bot.py:213`
- `auto_player.py:110`

**Fix applied**:
```python
# Fix Unicode minus sign (−) that macOS returns instead of ASCII minus (-)
coords = coords.replace('−', '-').replace('–', '-')
```

#### 2. Created Dynamic Lobby Navigator
**New file**: `gamble/tools/dynamic_lobby_navigator.py`

Features:
- Finds GGPoker lobby window dynamically
- Detects Spin & Gold icon by gold/yellow color in top bar
- Detects game tiles by color (gold, blue, purple, red, teal)
- Detects Play Now buttons by white text on dark background
- Handles Retina display correctly (points vs pixels)
- No hardcoded coordinates!

**Usage**:
```bash
# Test detection
python -m gamble.tools.dynamic_lobby_navigator --test

# Register for Spin & Gold
python -m gamble.tools.dynamic_lobby_navigator --register --stake 0
```

### CRITICAL DISCOVERY: CARD BACKS vs CARD FACES

**The REAL reason card detection fails**: Cards show BACKS (face-down) when not player's turn!

![Card Backs](Cards show red GG-pattern backs, not white faces)

**Evidence from live table capture**:
- Detected card region at (735,901) 228x167
- Both cards extracted showed RED CARD BACKS with GG watermark
- Template matching failed because we're matching card templates against card backs

**The Rule**:
```
Cards are FACE-UP (white, readable) ONLY when:
1. It is YOUR turn to act
2. Action buttons (Fold/Call/Raise) are visible

Cards are FACE-DOWN (red backs) when:
1. Waiting for other players
2. Not your turn
3. Hand is over but not yet mucked
```

**The Fix**:
```python
def process_table(table_img):
    # FIRST: Check for action buttons
    buttons = find_buttons(table_img)

    if buttons:  # It's your turn - cards should be face-up
        cards = detect_cards(table_img)  # NOW try to read cards
        decide_action(buttons, cards)
    else:
        # Not your turn - don't bother trying to read cards
        pass
```

### RESEARCH FINDINGS (Best Practices)

From web research on poker bot development:

1. **Retina Display Handling**:
   - Use MSS library (10x faster than PIL ImageGrab)
   - Divide coordinates by 2 for clicking
   - Screenshots are in PIXELS, clicks are in POINTS

2. **Card Detection**:
   - Hybrid approach: Color for suits + Template for ranks
   - Multi-scale template matching for different window sizes
   - Use relative coordinates (% of window size)

3. **Window Size Independence**:
   - Never use hardcoded pixel coordinates
   - Use color/shape detection instead
   - Store coordinates as % of window dimensions

4. **macOS Permissions**:
   - Screen Recording permission required
   - Accessibility permission for clicking

### FILES CREATED/MODIFIED

| File | Status | Description |
|------|--------|-------------|
| `dynamic_table_finder.py` | Fixed | Unicode minus bug |
| `gg_automation.py` | Fixed | Unicode minus bug |
| `beast_mode.py` | Fixed | Unicode minus bug |
| `spin_grinder.py` | Fixed | Unicode minus bug |
| `ultimate_bot.py` | Fixed | Unicode minus bug |
| `auto_player.py` | Fixed | Unicode minus bug |
| `dynamic_lobby_navigator.py` | NEW | Dynamic lobby navigation |

### DEBUG FILES LOCATION

All debug images saved to `/tmp/gg_debug/`:
- `lobby_original.png` - Raw lobby screenshot
- `lobby_annotated.png` - Lobby with detected elements marked
- `table_capture.png` - Poker table screenshot
- `table_cards_marked.png` - Table with card region marked
- `both_cards.png` - Extracted card region
- `left_card.png`, `right_card.png` - Split cards (showing backs)

### WHAT STILL NEEDS FIXING

1. **Card detection timing**: Only read cards when action buttons visible
2. **Template matching accuracy**: Scores too high (0.58+), need < 0.30
3. **Split card detection**: Currently finds both cards as one region
4. **Multi-table support**: Handle multiple table windows simultaneously

### HOW TO RUN THE SYSTEM

```bash
# 1. Test lobby detection (no clicking)
python -m gamble.tools.dynamic_lobby_navigator --test --debug

# 2. Register for Spin & Gold (will click)
python -m gamble.tools.dynamic_lobby_navigator --register --stake 0

# 3. Run auto player on open tables
python -m gamble.tools.auto_player

# 4. Watch logs
tail -f /Users/sebastian/Developer/Gamble/log/auto_player.log
```

### VERIFIED WORKING

- ✅ Window detection (GGPoker lobby and tables)
- ✅ Unicode minus fix (no more parseInt errors)
- ✅ Spin & Gold icon detection (in top bar)
- ✅ Game tile detection (colored tiles in grid)
- ✅ Play Now button detection (white text approach)
- ✅ Card region detection (finds white areas)
- ❌ Card reading (fails when cards are face-down)
- ⚠️ Button clicking (works but needs action button check first)

---

## OCR PLAYER - WORKING! (Jan 4, 2026 16:35+)

### THE BREAKTHROUGH
**OCR-based button detection WORKS!** Using pytesseract to find button text instead of guessing coordinates.

### New File Created
`gamble/tools/ocr_player.py` - OCR-based poker player

### How It Works
```python
import pytesseract
from PIL import ImageGrab

screenshot = ImageGrab.grab()
data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)

# Find text like "Check", "Fold", "Call", "Raise"
for i, text in enumerate(data['text']):
    if text.lower() in ['check', 'fold', 'call', 'raise']:
        x, y = data['left'][i], data['top'][i]  # PIXELS
        click_x = x // 2  # Convert to POINTS
        click_y = y // 2
        # Click there!
```

### Bot Output (WORKING!)
```
Found buttons: ['bet', 'fold', 'check']
Clicked Check at (1596, 676)
Found buttons: ['check', 'call', 'bet']
Clicked Check at (1232, 676)
Found buttons: ['call', 'raise', 'fold']
Clicked Fold at (778, 985)
```

### Decision Logic
1. If CHECK available → Click Check (it's FREE)
2. If must pay (CALL+FOLD visible) → Click Fold (conservative)
3. If only CALL visible → Click Call (might be all-in)

### To Run OCR Player
```bash
python -m gamble.tools.ocr_player
```

### Why OCR Works Better Than Coordinates
- Finds buttons wherever they are
- Works with any window position/size
- No hardcoding required
- Adapts to UI changes automatically

### VERIFIED WORKING
- ✅ OCR button detection (Check, Fold, Call, Raise)
- ✅ Clicking detected buttons
- ✅ Playing poker hands automatically
- ✅ Handling free checks vs paid calls

---

## SESSION: Card Detection Testing (Jan 4, 2026 ~16:40)

### What Was Tested
Attempted to read player's hole cards from a live Spin & Gold table.

### Results: CARDS NOT DETECTED
**Cards showed FACE-DOWN BACKS, not readable faces.**

Evidence from `/tmp/gg_debug/`:
| File | Contents |
|------|----------|
| `table_capture.png` | Full poker table screenshot |
| `both_cards.png` | RED card backs with GG watermark |
| `left_card.png` | Face-down card (red back) |
| `right_card.png` | Face-down card (red back) |

Template matching returned WRONG results:
- Left card: 7C (score: 0.58) - WRONG
- Right card: QH (score: 0.69) - WRONG
- Scores should be < 0.30 for valid match

### Why Cards Were Face-Down
**It was NOT the player's turn to act.** Cards only show faces when:
1. Action buttons (Fold/Call/Raise) are visible
2. It's YOUR turn to make a decision

### Fix Applied to auto_player.py
Updated `decide_action()` to ALWAYS take action when buttons visible:
```python
# Old: required cards to be detected → often did nothing
# New: fold if cards unknown, raise/call if good cards detected
if 'fold' in buttons:
    return 'fold'  # Safe default when cards unknown
```

### Key Lesson for Team
**Don't debug card detection when cards are face-down!**
1. First verify it's your turn (buttons visible)
2. Then attempt to read cards
3. Check `/tmp/gg_debug/*.png` to see actual card images

### Which Bot to Use
| Bot | Use Case |
|-----|----------|
| `ten_table_bot.py` | **NEW** - 1148 lines, unified 10-table system |
| `ocr_player.py` | OCR-based, works for buttons |
| `auto_player.py` | Color-based detection, decision logic fixed |
| `dynamic_lobby_navigator.py` | Lobby navigation only |

---

## CRITICAL ISSUES IDENTIFIED (Jan 4, 2026)

### Issue #1: Multiple Detection Systems - NO UNIFIED APPROACH
Different files use different card detection:
- `table_scraper.py` - Template-based (hardcoded MongoDB coords)
- `smart_card_detector.py` - White region detection
- `auto_player.py` - White mask detection
- `dynamic_table_finder.py` - Brightness-based
- `table_screen_based.py` - Neural network option

**Each Claude session picks a different approach. No unified system.**

### Issue #2: Cards Face-Down When Not Your Turn
- Cards only readable when action buttons visible
- White detection fails on face-down cards (red backs)
- Must check for buttons FIRST, then read cards

### Issue #3: Unicode Minus Bug
macOS AppleScript returns `−` (U+2212) not `-` (U+002D).
**Fixed in**: dynamic_table_finder.py, gg_automation.py, beast_mode.py, spin_grinder.py, ultimate_bot.py, auto_player.py, smart_ui_automation.py, constants.py, smart_table_finder.py, template_manager.py, gg_registration.py

### Issue #4: No Click Verification
Bot clicks but doesn't verify the action worked. Need:
1. Pre-click screenshot
2. Click
3. Post-click screenshot
4. Verify change occurred

### Issue #5: Multi-Table Sequential Not Parallel
Current code processes tables one at a time. For 10 tables need parallel screenshot analysis.

### Issue #6: Retina Display Confusion
POINTS vs PIXELS confusion causes clicks to miss.

---

## TEN TABLE BOT CREATED (Jan 4, 2026 16:43)

**New file**: `gamble/tools/ten_table_bot.py` (1148 lines)

### Features
1. Unified visual detection (works any table size)
2. Handles face-up AND face-down cards
3. Click verification with screenshots
4. 10-table priority-based management
5. Full UI navigation with OCR
6. State machine per table

### To Run
```bash
python -m gamble.tools.ten_table_bot
```

### Architecture
- `TableState` enum: LOBBY, WAITING, NEED_ACTION, etc.
- `TableSession` class: Per-table state tracking
- `TenTableBot` class: Orchestrates all tables
- Parallel screenshot capture
- Sequential action execution (one mouse)

---

## COORDINATION FOR TEAM

### What's Working
- ✅ OCR button detection (ocr_player.py)
- ✅ Unicode minus fix (all files)
- ✅ Dynamic lobby navigation
- ✅ Window detection

### What Needs Testing
- ⚠️ ten_table_bot.py (new, untested)
- ⚠️ Card reading when it's your turn
- ⚠️ Multi-table coordination

### DO NOT
- Create yet another detection approach
- Remove existing code without documenting
- Assume cards are readable (check if face-up first)
- Use hardcoded coordinates

---

## COMPLETE SYSTEM DOCUMENTATION (Jan 4, 2026)

### ALL BOT FILES - COMPLETE INVENTORY

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| **MAIN BOTS** ||||
| `cli_controller.py` | 37925 | Main bot entry point, integrates all systems | ✅ Primary |
| `auto_player.py` | 26488 | Autonomous player with self-learning | ✅ Working |
| `ten_table_bot.py` | 38077 | 10-table management system | ⚠️ Testing |
| `ocr_player.py` | 4791 | OCR-based button detection player | ✅ Working |
| `master_bot.py` | 9602 | Full lifecycle table management | ⚠️ Testing |
| **DETECTION** ||||
| `vision_analyzer.py` | 21419 | Self-healing vision analysis | ✅ NEW |
| `self_healer.py` | 32521 | Auto-fix detection failures | ✅ Working |
| `adaptive_learner.py` | 23503 | Learning system, threshold management | ✅ Working |
| `smart_card_detector.py` | 16511 | Dynamic card detection | ✅ Working |
| `dynamic_table_finder.py` | 24074 | Find tables by green felt + buttons | ✅ Working |
| `button_detector.py` | 13931 | HSV-based button detection | ✅ Working |
| `dynamic_card_detector.py` | 10512 | Alternative card detection | ⚠️ Backup |
| **NAVIGATION** ||||
| `dynamic_lobby_navigator.py` | 39273 | OCR lobby navigation, Spin & Gold | ✅ Working |
| `ui_navigator.py` | 29253 | UI automation and navigation | ✅ Working |
| `gg_registration.py` | 39033 | Table registration automation | ✅ Working |
| `gg_automation.py` | 18187 | GGPoker-specific automation | ✅ Working |
| `smart_ui_automation.py` | 48250 | Smart UI detection and clicking | ✅ Working |
| **READING** ||||
| `dynamic_table_reader.py` | 15994 | OCR pot/stack/card reading | ✅ Working |
| `screen_operations.py` | 18801 | Screenshot and template matching | ✅ Working |
| **UTILITIES** ||||
| `mouse_mover.py` | 9558 | Mouse movement and clicking | ✅ Working |
| `dynamic_mouse_mover.py` | 7305 | Dynamic mouse operations | ✅ Working |
| `fast_clicker.py` | 16418 | Fast clicking operations | ✅ Working |
| `action_verifier.py` | 11287 | Verify clicks worked | ✅ Working |
| `constants.py` | 3721 | Screen constants, Retina scale | ✅ Working |
| `mongo_manager.py` | 7975 | MongoDB template storage | ✅ Working |
| **EXPERIMENTAL** ||||
| `beast_mode.py` | 15799 | Aggressive standalone bot | ⚠️ Testing |
| `ultimate_bot.py` | 24342 | Feature-complete bot attempt | ⚠️ Testing |
| `spin_grinder.py` | 9705 | Spin & Gold focused | ⚠️ Testing |
| `claude_brain.py` | 25730 | Claude AI integration | ⚠️ Experimental |
| `ultrathink.py` | 33665 | Advanced decision making | ⚠️ Experimental |

### HOW TO RUN EACH BOT

```bash
# === RECOMMENDED: Main bot with self-learning ===
python -m gamble.tools.cli_controller start

# === OCR-based player (simple, reliable) ===
python -m gamble.tools.ocr_player

# === Auto player with vision analyzer ===
python -m gamble.tools.auto_player

# === 10-table management ===
python -m gamble.tools.ten_table_bot --max-tables 10

# === Lobby navigation only (register for Spin & Gold) ===
python -m gamble.tools.dynamic_lobby_navigator --register --stake 0

# === Test lobby detection (no clicking) ===
python -m gamble.tools.dynamic_lobby_navigator --test --debug
```

### SELF-LEARNING DATA STRUCTURE

```
data/learning/
├── actions.jsonl          # All action logs (132KB+)
├── thresholds.json        # Current adaptive thresholds
├── working_configs.json   # Learned button colors (HSV)
├── stats.json             # Success/failure rates
├── fixes.jsonl            # Auto-fix history
├── issues.jsonl           # Reported issues for Claude
├── screenshots/           # 219+ failure screenshots
└── debug/                 # 116+ annotated debug images
```

### CURRENT LEARNED THRESHOLDS

```json
{
  "white_pixel_min": 120,        // Lowered from 180 - cards detected better
  "card_area_min": 2000,
  "button_area_min": 852,        // Learned from actual buttons
  "match_score_max": 0.35,
  "hsv_green_lower": [42, 61, 4],   // Call/Check button
  "hsv_green_upper": [72, 161, 104],
  "hsv_orange_lower": [0, 75, 103], // Raise/Bet button
  "hsv_orange_upper": [25, 175, 203],
  "hsv_gray_lower": [41, 14, 19],   // Fold button
  "hsv_gray_upper": [71, 114, 119],
  "action_cooldown": 1.5,
  "click_verify_delay": 0.3,
  "table_width_min": 400,
  "icon_bar_height_ratio": 0.16
}
```

### LEARNED BUTTON COLORS (HSV samples from actual game)

The system has learned these HSV values from real GGPoker buttons:

| Button | HSV Samples Collected |
|--------|----------------------|
| Green (Call/Check) | 7 samples |
| Orange (Raise/Bet) | 4 samples |
| Gray (Fold) | 22 samples |
| Red (Cancel/All-in) | 8 samples |

These are stored in `data/learning/working_configs.json` and automatically averaged to update detection thresholds.

### DEBUG DIRECTORIES

| Directory | Contents |
|-----------|----------|
| `/tmp/gg_debug/` | Live debug images (lobby, tables, cards) |
| `data/learning/debug/` | Vision analyzer annotated outputs |
| `data/learning/screenshots/` | Failure screenshots for analysis |
| `log/` | All log files |
| `log/pics/` | Session screenshots |

### QUICK COMMANDS

```bash
# Watch live logs
tail -f log/dm_assistant.log
tail -f log/auto_player.log
tail -f log/dynamic_lobby.log

# Kill all bots
pkill -f "python -m gamble"

# Check if GGPoker running
pgrep -l GGnet

# List GGPoker windows
osascript -e 'tell application "System Events" to tell process "GGnet" to name of every window'

# Check learning stats
cat data/learning/stats.json

# Check current thresholds
cat data/learning/thresholds.json

# Count screenshots taken
ls data/learning/screenshots/ | wc -l

# Count debug images
ls data/learning/debug/ | wc -l
```

### SYSTEM FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER STARTS BOT                              │
│                    python -m gamble.tools.X                          │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      LOBBY NAVIGATION                                │
│  dynamic_lobby_navigator.py                                          │
│  - Find Spin & Gold icon (gold color detection)                      │
│  - Click game tile (stake selection)                                 │
│  - Click Play Now (green button detection)                           │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      TABLE DETECTION                                 │
│  dynamic_table_finder.py                                             │
│  - Find poker table windows (AppleScript)                            │
│  - Capture table screenshots                                         │
│  - Detect table state                                                │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      BUTTON DETECTION                                │
│  auto_player.py / button_detector.py                                 │
│  - HSV color detection (green=call, orange=raise, gray=fold)         │
│  - OCR text detection (backup)                                       │
│  - Contour filtering for button shapes                               │
└─────────────────────────────────────────────────────────────────────┘
                                  │
            ┌─────────────────────┴─────────────────────┐
            │                                           │
            ▼                                           ▼
      [BUTTONS FOUND]                           [NO BUTTONS]
            │                                           │
            ▼                                           ▼
┌───────────────────────┐               ┌───────────────────────────┐
│   CARD DETECTION      │               │   SELF-HEALING            │
│   smart_card_detector │               │   vision_analyzer.py      │
│   - White region scan │               │   - Analyze actual colors │
│   - Template matching │               │   - Generate new thresh   │
│   - OCR card values   │               │   - Apply fix             │
└───────────────────────┘               │   - Retry detection       │
            │                           └───────────────────────────┘
            ▼                                           │
┌───────────────────────┐                               │
│   DECISION MAKING     │◄──────────────────────────────┘
│   - Equity calc       │
│   - Opponent tracking │
│   - Strategy logic    │
└───────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                         ACTION EXECUTION                               │
│   - Click button (convert PIXELS to POINTS for Retina)                 │
│   - Verify click worked (screenshot comparison)                        │
│   - Log action to adaptive_learner                                     │
│   - Save screenshot if failed                                          │
└───────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                         LEARNING LOOP                                  │
│   adaptive_learner.py                                                  │
│   - Log success/failure                                                │
│   - Update thresholds if needed                                        │
│   - Save working configs                                               │
│   - Report issues for Claude                                           │
└───────────────────────────────────────────────────────────────────────┘
```

### FILE SIZE REFERENCE

Total codebase in `gamble/tools/`: **~600KB** across 45 Python files

Largest files (most functionality):
1. `smart_ui_automation.py` - 48KB
2. `dynamic_lobby_navigator.py` - 39KB
3. `gg_registration.py` - 39KB
4. `ten_table_bot.py` - 38KB
5. `cli_controller.py` - 37KB
6. `ultrathink.py` - 33KB
7. `self_healer.py` - 32KB

### IMPORTS REFERENCE

```python
# === For any new bot, import these: ===

# Self-learning system
from gamble.tools.adaptive_learner import (
    log_action, get_threshold, report_issue, save_screenshot
)

# Vision analyzer (auto-fix)
from gamble.tools.vision_analyzer import (
    auto_fix_detection, auto_fix_buttons, auto_fix_cards
)

# Table detection
from gamble.tools.dynamic_table_finder import (
    DynamicTableFinder, find_poker_tables
)

# Button detection
from gamble.tools.button_detector import ButtonDetector

# Card detection
from gamble.tools.smart_card_detector import SmartCardDetector

# Lobby navigation
from gamble.tools.dynamic_lobby_navigator import DynamicLobbyNavigator

# Constants
from gamble.tools.constants import RETINA_SCALE  # = 2
```

---

## COMPLETE SYSTEM MAP (Jan 4, 2026)

### All Detection Systems (For Reference)

**The OLD way (fragmented)** - These still exist but should be deprecated:

| System | File | Status |
|--------|------|--------|
| Card Detection 1 | `scraper/table_scraper.py` | Template matching (original) |
| Card Detection 2 | `scraper/table_scraper_nn.py` | Neural network |
| Card Detection 3 | `tools/smart_card_detector.py` | White region |
| Card Detection 4 | `tools/dynamic_card_detector.py` | Brightness |
| Card Detection 5 | `tools/auto_player.py` | White mask |
| Card Detection 6 | `tools/ten_table_bot.py` | VisualDetector |
| Button Detection 1 | `tools/button_detector.py` | HSV color |
| Button Detection 2 | `tools/auto_calibrate.py` | Different HSV |
| Button Detection 3 | `tools/smart_ui_automation.py` | ColorDetector |
| Button Detection 4 | `tools/dynamic_table_finder.py` | Hybrid |
| Button Detection 5 | `tools/vision_analyzer.py` | Analyzer |
| Button Detection 6 | `tools/self_healer.py` | Healer |
| Button Detection 7 | `tools/ocr_player.py` | OCR |
| Learning 1 | `tools/adaptive_learner.py` | Logging + thresholds |
| Learning 2 | `tools/vision_analyzer.py` | Analysis + fixes |
| Learning 3 | `tools/self_healer.py` | Real-time healing |

**The NEW way (unified)** - All new code should use these:

| System | File | Purpose |
|--------|------|---------|
| **Card Detection** | `core/card_detector.py` | Combines all 6 approaches |
| **Button Detection** | `core/button_detector.py` | Combines all 7 approaches |
| **Window Finding** | `core/window_finder.py` | Single implementation |
| **Learning** | `core/unified_learner.py` | Combines all 3 systems |
| **Base Bot** | `core/base_bot.py` | All bots inherit this |
| **Constants** | `core/constants.py` | All shared values |

### Bot Entry Points (All 8)

| Bot | File | Use Case | Uses Unified Core? |
|-----|------|----------|-------------------|
| Main GUI | `main.py` | Original with GUI | No (needs migration) |
| CLI Controller | `tools/cli_controller.py` | Headless original | No (needs migration) |
| Auto Player | `tools/auto_player.py` | Autonomous color-based | Partial |
| OCR Player | `tools/ocr_player.py` | OCR-based | No |
| Beast Mode | `tools/beast_mode.py` | Multi-table | No |
| Ultimate Bot | `tools/ultimate_bot.py` | Multi-table | No |
| Ten Table Bot | `tools/ten_table_bot.py` | State machine | No |
| Master Bot | `tools/master_bot.py` | Orchestrator | No |

**Recommended**: Create new bots by inheriting from `gamble.core.BaseBot`

### Data Files

| File | Purpose |
|------|---------|
| `data/learning/thresholds.json` | All adaptive thresholds |
| `data/learning/actions.jsonl` | Action log for analysis |
| `data/learning/stats.json` | Success rate statistics |
| `data/learning/calibration.json` | Button color calibration |
| `data/learning/working_configs.json` | Configs that worked |
| `data/learning/fixes.jsonl` | Self-healing history |
| `data/learning/screenshots/` | Screenshots of failures |
| `data/learning/debug/` | Annotated debug images |

### The Complete Data Flow

```
1. WINDOW FINDING
   WindowFinder.find_poker_tables()
   → AppleScript queries GGnet process
   → Returns List[TableWindow] with POINT coordinates
   → Each TableWindow can convert to PIXELS for image processing

2. SCREENSHOT CAPTURE
   ImageGrab.grab() → Full screen in PIXELS (3420x2224 on Retina)
   table.capture(screenshot) → Cropped table image

3. BUTTON DETECTION
   ButtonDetector.detect(table_img, table_window)
   → Strategy 1: HSV color detection (fast)
   → Strategy 2: OCR text detection (fallback)
   → Strategy 3: Self-healing analysis (last resort)
   → Returns: {'call': {x, y, w, h, screen_pt}, ...}

4. CARD DETECTION
   CardDetector.detect_player_cards(table_img, table_window)
   → Strategy 1: Template matching (if templates loaded)
   → Strategy 2: White region detection
   → Strategy 3: Self-healing (try multiple thresholds)
   → Returns: ['AH', 'KS'] or []

5. DECISION MAKING
   BaseBot.decide_action(cards, buttons, table_state)
   → If DecisionMaker available: Use MonteCarlo equity
   → Otherwise: Simple heuristics (fold weak, call medium, raise strong)
   → Returns: 'call', 'raise', 'fold', or None

6. ACTION EXECUTION
   BaseBot.click_button(button, table_window)
   → Take screenshot BEFORE
   → Click at screen_pt using Quartz
   → Take screenshot AFTER
   → Verify screen changed
   → Log to UnifiedLearner

7. LEARNING & SELF-HEALING
   UnifiedLearner tracks all actions
   → If detection fails: heal_detection() analyzes image
   → Generates new thresholds that work
   → Saves to thresholds.json
   → Next time, uses learned values
```

### Coordinate System Reference

```
POINTS (macOS):
- AppleScript window positions
- Mouse click coordinates
- Divide by 2 when converting from pixels

PIXELS (Screenshots):
- ImageGrab.grab() output
- Image processing coordinates
- Multiply by 2 when converting from points

Example:
  Window at (100, 200) POINTS
  → Screenshot crop at (200, 400) PIXELS
  → Found button at (300, 500) PIXELS in cropped image
  → Click at (100 + 300/2, 200 + 500/2) = (250, 450) POINTS
```

### CRITICAL REMINDERS

1. **RETINA DISPLAY**: Always divide pixel coords by 2 for clicking
2. **UNICODE MINUS**: Replace `−` (U+2212) with `-` in AppleScript output
3. **CARDS FACE-DOWN**: Only read cards when action buttons visible
4. **SELF-LEARNING**: Bot fixes itself - check `data/learning/` for what it learned
5. **NO HARDCODING**: Use color/OCR detection, never pixel coordinates
6. **ADD DON'T REMOVE**: Only add to this file, never delete sections
7. **USE UNIFIED CORE**: Import from `gamble.core` for all new code

---

## SESSION LOG - Jan 4, 2026 (Evening - CRITICAL FIXES)

### BUGS FOUND AND FIXED

#### 1. Fast Fold Bug - Bot Always Folding
**Problem**: Bot was folding EVERY hand regardless of card strength.

**Root Cause**: `check_fast_fold()` in `table_screen_based.py` line 221-225:
```python
if found_card == '':
    mouse_target = "Fold"
    mouse.mouse_action(mouse_target, self.tlc)
    log.info("-------- FAST FOLD -------")
    return False
```

When card detection was wrong, the hand lookup failed, and bot folded.

**Fix Applied**: Disabled fast fold entirely in `table_screen_based.py`:
```python
def check_fast_fold(self, h, p, mouse):
    log.info("Fast fold DISABLED - letting strategy decide all hands")
    return True  # Always return True to skip fast fold
```

**File**: `gamble/scraper/table_screen_based.py` line 189-203

#### 2. Wrong Deck Color Assumption - 4-Color vs 2-Color
**Problem**: Bot detected "TD" (Ten Diamonds) when card was actually "TS" (Ten Spades).

**Root Cause**: `smart_card_detector.py` line 291 assumed 4-color deck:
```python
# GGPoker uses 4-color deck: Spades=black, Hearts=red, Diamonds=blue, Clubs=green
```

But GGPoker uses **STANDARD 2-COLOR DECK**:
- Hearts = Red, Diamonds = Red
- Spades = Black, Clubs = Black

The detector was checking for blue pixels (diamonds in 4-color) but finding none, then guessing wrong.

**Fix Applied**: Changed to 2-color logic with OCR for suit distinction:
```python
# GGPoker uses STANDARD 2-color deck:
# - Hearts = Red, Diamonds = Red
# - Spades = Black, Clubs = Black
# We need to use suit SHAPE detection to distinguish H/D and S/C

if red_total > black_total * 1.5:  # Clearly red
    suit = self._distinguish_red_suit(card_img)  # Uses OCR
elif black_total > red_total * 1.5:  # Clearly black
    suit = self._distinguish_black_suit(card_img)  # Uses OCR
```

**File**: `gamble/tools/smart_card_detector.py` lines 282-318

#### 3. Added Suit Self-Learning
**Problem**: No way to track/improve suit detection errors.

**Fix Applied**: Added `_log_suit_detection()` method that:
- Logs all suit detections to adaptive_learner
- Saves failed suit detection images to `data/learning/suit_errors/`
- Tracks success/failure rates

**File**: `gamble/tools/smart_card_detector.py` lines 434-464

### WHY THE BOT WAS ALWAYS FOLDING - FULL ANALYSIS

Chain of failures:
1. **Cards detected wrong** - TS (Ten Spades) → TD (Ten Diamonds)
2. **Hand lookup fails** - "JsTd" not in preflop chart (or wrong hand)
3. **Fast fold triggers** - `found_card == ''` so bot folds
4. **Every hand folded** - Even playable suited hands!

The suit error was CRITICAL because:
- JS + TS = suited (possible flush draw) = PLAYABLE
- JS + TD = offsuit = much weaker hand = often folded

### FILES MODIFIED

| File | Change |
|------|--------|
| `gamble/scraper/table_screen_based.py` | Disabled fast fold |
| `gamble/tools/smart_card_detector.py` | Fixed 2-color deck, added OCR suit detection, added self-learning |
| `gamble/core/card_detector.py` | Fixed 2-color deck (was 4-color) |
| `gamble/tools/ten_table_bot.py` | Fixed 2-color deck (was 4-color) |

### NEW METHODS ADDED

```python
# In smart_card_detector.py:

def _distinguish_red_suit(card_img) -> str:
    """Distinguish Hearts from Diamonds using OCR"""

def _distinguish_black_suit(card_img) -> str:
    """Distinguish Spades from Clubs using OCR"""

def _ocr_suit_symbol(card_img) -> str:
    """Read suit symbol (♠♥♦♣) using pytesseract"""

def _log_suit_detection(card_img, suit, ocr_text, success=True):
    """SELF-LEARNING: Log suit detection for analysis"""
```

### SELF-LEARNING DATA LOCATIONS

| Directory | Purpose |
|-----------|---------|
| `data/learning/suit_errors/` | NEW - Failed suit detection images |
| `data/learning/screenshots/` | Failed table detections |
| `data/learning/debug/` | Annotated debug images |
| `data/learning/thresholds.json` | Learned thresholds |
| `data/learning/actions.jsonl` | All action logs |

---

## DEEP ANALYSIS - REMAINING ISSUES

### ⚠️ WARNING: DecisionMaker Also Has Preflop Folding
**Location**: `gamble/decisionmaker/decisionmaker.py` lines 345-349

```python
else:
    self.decision = DecisionTypes.fold
    log.info('Preflop folding, hands not found in preflop table')
```

This is a SECOND preflop folding mechanism (separate from `check_fast_fold`).
If cards are detected wrong, this can also cause unnecessary folds.
**This is NOT disabled** - it's in the strategy decision maker.

### Issue #1: Strategy Not Using Equity Properly
**Symptom**: Bot may still make wrong decisions even with correct cards.

**Location**: `gamble/decisionmaker/decisionmaker.py`

**What to check**:
- Is equity being calculated correctly?
- Are opponent ranges being considered?
- Is position being used in decisions?

### Issue #2: Click Verification Not Always Working
**Symptom**: Bot clicks but action doesn't register in game.

**Locations**:
- `gamble/tools/action_verifier.py`
- `gamble/tools/mouse_mover.py`

**What to check**:
- Is before/after screenshot comparison working?
- Are retries happening on failed clicks?
- Is timing correct (click too fast/slow)?

### Issue #3: Multiple Card Detection Paths
**Symptom**: Different code paths may give different results.

**Detection methods in codebase**:
1. `table_scraper.py` - Template matching from MongoDB
2. `smart_card_detector.py` - Visual white region + OCR (FIXED)
3. `dynamic_card_detector.py` - Alternative detection
4. `gamble/core/card_detector.py` - Unified detector

**What to check**:
- Which path is actually being used?
- Are they all using 2-color deck logic now?
- Should consolidate to ONE detection method

### Issue #4: Self-Learning Not Always Triggering
**Symptom**: SELF-LEARNING logs don't appear when expected.

**When self-learning triggers**:
- Card detection fails completely (len != 2) → YES
- Card detection succeeds but wrong → NOW YES (suit logging added)
- Button detection fails → YES (via vision_analyzer)
- Click fails to register → PARTIALLY

**What to check**:
- Is the code actually reaching self-learning branches?
- Are exceptions being silently caught?
- Is logging level set to show INFO messages?

### Issue #5: Pot/Stack OCR May Be Inaccurate
**Symptom**: Equity calculations may use wrong pot sizes.

**Locations**:
- `gamble/tools/dynamic_table_reader.py`
- `gamble/scraper/table_scraper.py`

**What to check**:
- Is pot being read correctly?
- Are opponent stacks accurate?
- Is call amount correct?

### Issue #6: Table Detection Race Condition
**Symptom**: Bot might process same table twice or miss tables.

**Location**: `gamble/tools/cli_controller.py` main loop

**What to check**:
- Is table list being refreshed correctly?
- Are closed tables being removed?
- Is priority queue working?

---

## RECOMMENDED NEXT STEPS

### Immediate (Before Running Bot Again)
1. ✅ Fast fold disabled
2. ✅ Suit detection fixed
3. ⬜ Verify strategy is making reasonable decisions (not just folding everything)
4. ⬜ Check that click verification works

### Short-term
1. ⬜ Consolidate card detection to ONE method
2. ⬜ Add self-learning for incorrect pot/stack reads
3. ⬜ Test with multiple tables
4. ⬜ Review CLAUDE_FEEDBACK.md for reported issues

### Long-term
1. ⬜ Re-enable fast fold once card detection is reliable
2. ⬜ Add opponent tracking/modeling
3. ⬜ Implement bankroll management
4. ⬜ Add session statistics tracking

---

## HOW TO VERIFY FIXES ARE WORKING

```bash
# 1. Start the bot
python -m gamble.tools.cli_controller start --input dynamic

# 2. Watch for these log messages:
tail -f log/dm_assistant.log | grep -E "(SELF-LEARNING|Fast fold DISABLED|Detected.*suit|strategy)"

# Expected output:
# "Fast fold DISABLED - letting strategy decide all hands"
# "Detected BLACK suit -> S"
# "OCR suit symbol: '♠' -> S"

# 3. Check suit detection logs:
ls -la data/learning/suit_errors/

# 4. Check learned thresholds:
cat data/learning/thresholds.json
```

---

## CRITICAL: 2-COLOR DECK RULE

**GGPoker uses STANDARD 2-COLOR deck:**

| Suit | Color | Symbol |
|------|-------|--------|
| Spades | Black | ♠ |
| Clubs | Black | ♣ |
| Hearts | Red | ♥ |
| Diamonds | Red | ♦ |

**NOT 4-color deck** (which would have blue diamonds and green clubs).

When detecting suits:
1. First determine RED or BLACK by color
2. Then use OCR to read the suit symbol to distinguish:
   - Red: Hearts ♥ vs Diamonds ♦
   - Black: Spades ♠ vs Clubs ♣

---

## UNIFIED MULTI-TABLE SYSTEM (Jan 5, 2026)

### THE CORRECT APPROACH: Wrap Original Bot

**The original bot WORKS.** Don't replace it - WRAP it for multi-table support.

### New File: `gamble/multi_table_runner.py`

This is a **wrapper** around the ORIGINAL bot that:
1. Finds ALL open poker windows (not just one)
2. Creates a TableSession for each window
3. Uses ORIGINAL bot components for each table:
   - `TableScreenBased` for detection
   - `Decision` for equity + strategy
   - `MouseMoverTableBased` for clicking
4. Processes tables by priority (most urgent first)
5. Opens new tables via lobby navigation

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    multi_table_runner.py                             │
│                         (NEW WRAPPER)                                │
│                                                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                    Main Loop                                 │   │
│   │  1. find_poker_windows() → List[TableWindow]                │   │
│   │  2. For each window: create/update TableSession             │   │
│   │  3. check_table_state() → NEED_ACTION or WAITING            │   │
│   │  4. process_table() on most urgent                          │   │
│   │  5. open_new_table() if count < target                      │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│              Uses ORIGINAL bot for each table:                       │
│                              │                                       │
│   ┌──────────────────────────┼──────────────────────────────────┐   │
│   │                          ▼                                   │   │
│   │  ┌─────────────────────────────────────────────────────┐    │   │
│   │  │           ORIGINAL BOT COMPONENTS                    │    │   │
│   │  │                                                      │    │   │
│   │  │  scraper/table_screen_based.py                       │    │   │
│   │  │    └─ get_my_cards2()                                │    │   │
│   │  │    └─ get_table_cards2()                             │    │   │
│   │  │    └─ get_pots()                                     │    │   │
│   │  │    └─ has_call_button() / has_raise_button()         │    │   │
│   │  │                                                      │    │   │
│   │  │  decisionmaker/decisionmaker.py                      │    │   │
│   │  │    └─ Decision.make_decision()                       │    │   │
│   │  │    └─ Equity calculations                            │    │   │
│   │  │    └─ Strategy logic                                 │    │   │
│   │  │                                                      │    │   │
│   │  │  tools/mouse_mover.py                                │    │   │
│   │  │    └─ mouse_action(decision, tlc)                    │    │   │
│   │  └─────────────────────────────────────────────────────┘    │   │
│   └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### How To Run

```bash
# Multi-table with original bot decision making
python -m gamble.multi_table_runner --target-tables 4 --max-tables 10

# Arguments:
#   --target-tables N  : Maintain N tables open (default: 4)
#   --max-tables N     : Maximum tables to ever open (default: 10)
#   --table-name NAME  : MongoDB table config name
```

### Key Classes

```python
class TableWindow:
    """Represents a detected poker window"""
    window_id: int
    name: str
    x: int          # Position in POINTS
    y: int
    width: int
    height: int

class TableSession:
    """Session state for ONE table"""
    window: TableWindow
    table_dict: dict
    history: History              # From original bot
    preflop_state: CurrentHandPreflopState
    state: TableState             # WAITING, NEED_ACTION, etc.
    priority: int                 # Higher = more urgent

    # Original bot components (lazy-loaded)
    _table: TableScreenBased      # Card/button detection
    _mouse: MouseMoverTableBased  # Click execution

class MultiTableRunner:
    """Main orchestrator"""
    sessions: Dict[int, TableSession]

    def find_poker_windows() -> List[TableWindow]
    def check_table_state(session) -> TableState
    def process_table(session) -> bool  # Uses ORIGINAL bot logic
    def open_new_table() -> bool        # Via lobby navigation
    def run()                           # Main loop
```

### Processing Priority

Tables are processed in this order:
1. **NEED_ACTION** (buttons visible) - Priority 10
2. **WAITING** (not my turn) - Priority 1
3. **HAND_OVER** / **CLOSED** - Removed

### Why This Works

1. **Uses PROVEN code**: The original TableScraper, Decision, MouseMover all work
2. **No reinventing**: We don't recreate button/card detection
3. **Single mouse**: Actions are sequential (one cursor)
4. **Parallel detection**: Could parallelize screenshots later
5. **Maintains count**: Opens new tables when below target

### Files Involved

| File | Purpose |
|------|---------|
| `multi_table_runner.py` | NEW - Multi-table wrapper |
| `main.py` | Original single-table entry (still works) |
| `scraper/table_screen_based.py` | Original table detection |
| `scraper/table_scraper.py` | Original card/button reading |
| `decisionmaker/decisionmaker.py` | Original equity + strategy |
| `tools/mouse_mover.py` | Original click execution |
| `tools/dynamic_lobby_navigator.py` | Opens new tables |

### The Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                         MAIN LOOP                               │
│                                                                 │
│  while running:                                                 │
│    1. windows = find_poker_windows()  # AppleScript            │
│    2. Update sessions (remove closed, add new)                  │
│    3. For each session: check_table_state()                     │
│    4. urgent = [s for s if s.state == NEED_ACTION]             │
│    5. if urgent: process_table(urgent[0])  # ORIGINAL BOT      │
│    6. if len(sessions) < target: open_new_table()              │
│    7. sleep(0.5)                                               │
└─────────────────────────────────────────────────────────────────┘
```

### Integration with Self-Learning

The multi-table wrapper can use the self-learning systems:

```python
# In check_table_state() when detection fails:
from gamble.tools.vision_analyzer import auto_fix_buttons
fix_result = auto_fix_buttons(screenshot)

# In process_table() for logging:
from gamble.tools.adaptive_learner import log_action
log_action('table_processed', success=True, details={'table': session.window.name})
```

### This Is The Correct Way

**DO NOT:**
- Create new bot files with different detection
- Replace original DecisionMaker
- Build separate card/button detection

**DO:**
- Use `multi_table_runner.py` as the entry point
- Let it wrap the ORIGINAL bot components
- Add improvements to the ORIGINAL files if needed

---

## SIZE-AGNOSTIC DETECTION

### Problem: Hardcoded Coordinates

Original bot uses fixed pixel coordinates that only work for ONE table size:
```python
'left_card_area': {'x1': 800, 'y1': 955, 'x2': 840, 'y2': 1010}  # Only works at 1500x1100
```

### Solution 1: Percentage-Based Regions

```python
# Convert to percentages of table size:
left_card_pct = {
    'x1': 800/1500,   # 53.3%
    'y1': 955/1100,   # 86.8%
    'x2': 840/1500,   # 56.0%
    'y2': 1010/1100   # 91.8%
}

# Scale to ANY table size:
def scale_region(region_pct, table_width, table_height):
    return {
        'x1': int(region_pct['x1'] * table_width),
        'y1': int(region_pct['y1'] * table_height),
        'x2': int(region_pct['x2'] * table_width),
        'y2': int(region_pct['y2'] * table_height),
    }
```

### Solution 2: Color Detection (Fully Size-Agnostic)

```python
def find_buttons_any_size(table_img):
    """Find buttons by color - works ANY table size"""
    h, w = table_img.shape[:2]

    # Buttons always in bottom 40%
    search_region = table_img[int(h*0.6):, :]
    hsv = cv2.cvtColor(search_region, cv2.COLOR_BGR2HSV)

    # Green = Call/Check
    green = cv2.inRange(hsv, (35,50,50), (85,255,255))

    # Orange = Raise/Bet
    orange = cv2.inRange(hsv, (8,80,80), (28,255,255))

    return find_contours(green), find_contours(orange)
```

### Solution 3: Multi-Scale Template Matching

```python
def match_any_scale(image, template, scales=[0.5, 0.75, 1.0, 1.25, 1.5]):
    best = None
    for scale in scales:
        scaled = cv2.resize(template, None, fx=scale, fy=scale)
        result = cv2.matchTemplate(image, scaled, cv2.TM_SQDIFF_NORMED)
        score = cv2.minMaxLoc(result)[0]
        if best is None or score < best[0]:
            best = (score, scale)
    return best
```

---

## WINDOW RESIZING (AppleScript)

### Resize One Window

```python
def resize_window(window_name: str, width: int, height: int, x: int, y: int):
    script = f'''
    tell application "System Events"
        tell process "GGnet"
            repeat with w in windows
                if name of w contains "{window_name}" then
                    set position of w to {{{x}, {y}}}
                    set size of w to {{{width}, {height}}}
                end if
            end repeat
        end tell
    end tell
    '''
    subprocess.run(['osascript', '-e', script])
```

### Tile All Tables in Grid

```python
def tile_all_tables(columns=3, width=800, height=600):
    """Resize and arrange all poker tables in a grid"""
    windows = find_poker_windows()
    for i, win in enumerate(windows):
        x = (i % columns) * width
        y = (i // columns) * height
        resize_window(win.name, width, height, x, y)
```

### Recommended: Standardize on Startup

```python
STANDARD_SIZE = (800, 600)  # All tables same size

def standardize_tables():
    """On bot startup: resize all tables to standard size"""
    tile_all_tables(columns=3, width=800, height=600)
    # Now ALL detection can use fixed coordinates!
```

### Benefits of Standardization

1. **No scaling needed** - All tables identical
2. **Fixed coordinates work** - Same regions for all
3. **Fast detection** - No multi-scale search
4. **Grid layout** - Easy visual monitoring
5. **Consistent templates** - Templates match exactly

---

## THE COMPLETE FLOW

```
┌─────────────────────────────────────────────────────────────────┐
│                     BOT STARTUP                                  │
│  1. Find all poker windows (AppleScript)                        │
│  2. Resize ALL to standard size (800x600)                       │
│  3. Tile in grid (3 columns)                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MAIN LOOP                                    │
│  For each table:                                                │
│    1. Screenshot (fixed size = fast)                            │
│    2. Button detection (HSV color OR fixed coords)              │
│    3. If buttons visible:                                       │
│       a. Card detection (template OR position)                  │
│       b. OCR (pot, call, raise values)                         │
│       c. Monte Carlo equity                                     │
│       d. Decision (original decisionmaker)                      │
│       e. Click (mouse_action)                                   │
│    4. If tables < target: open new via lobby                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## RUN THE MULTI-TABLE BOT

```bash
# Default: 4 target tables, auto-standardize on startup
python -m gamble.multi_table_runner

# With options:
python -m gamble.multi_table_runner --target-tables 6 --max-tables 10

# Skip auto-resize (if tables already positioned):
python -m gamble.multi_table_runner --no-standardize
```
