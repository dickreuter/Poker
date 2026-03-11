# Original Poker Bot vs Current Implementation

## Source: https://github.com/dickreuter/Poker

---

## WHAT'S FROM THE ORIGINAL (dickreuter/Poker)

### scraper/ - Table Recognition (5 files)
These are the CORE working files from the original:

| File | Purpose | Status |
|------|---------|--------|
| `table_scraper.py` | Main table state reader - cards, pots, stacks, buttons | **ORIGINAL** - enhanced with fallbacks |
| `table_screen_based.py` | Screen-based table detection | **ORIGINAL** - fast fold disabled |
| `table_scraper_nn.py` | Neural network card detection | **ORIGINAL** - optional |
| `table.py` | Table data structures | **ORIGINAL** |
| `table_setup_actions_and_signals.py` | GUI setup signals | **ORIGINAL** |

### decisionmaker/ - Strategy Logic (12 files)
The brain of the bot - ALL from original:

| File | Purpose | Status |
|------|---------|--------|
| `decisionmaker.py` | Main decision engine - equity vs pot odds | **ORIGINAL** - untouched |
| `montecarlo_python.py` | Equity calculation (Python) | **ORIGINAL** |
| `montecarlo_numpy.py` | Equity calculation (NumPy - fast) | **ORIGINAL** |
| `montecarlo_numpy2.py` | Equity calculation (experimental) | **ORIGINAL** |
| `genetic_algorithm.py` | Strategy optimization | **ORIGINAL** |
| `outs_calculator.py` | Drawing hand calculations | **ORIGINAL** |
| `current_hand_memory.py` | Hand history tracking | **ORIGINAL** |
| `curvefitting.py` | Decision curve fitting | **ORIGINAL** |
| `implied_odds.py` | Implied odds calculation | **ORIGINAL** |
| `straight_draw.py` | Straight draw detection | **ORIGINAL** |
| `create_preflop_equity_ranking.py` | Preflop hand rankings | **ORIGINAL** |
| `preflop.xlsx` | Preflop strategy chart | **ORIGINAL** |

### gui/ - Qt GUI
The graphical interface - ALL from original:
- Strategy editor
- Table analyzer
- Log viewer
- Configuration forms

### Other Original Components
- `main.py` - GUI entry point
- `mongo_manager.py` - Template storage
- `mouse_mover.py` - Mouse control
- `update_checker.py` - Version checking
- `game_logger.py` - Hand logging

---

## WHAT'S NEW (Added for Multi-Table GGPoker)

### tools/ - 51 New Files!
These were added to extend the original for multi-table GGPoker:

#### Multi-Table Management
| File | Purpose |
|------|---------|
| `cli_controller.py` | **MAIN ENTRY** - Headless multi-table controller |
| `multi_table_controller.py` | Orchestrates multiple tables |
| `table_session.py` | Per-table state tracking |
| `ten_table_bot.py` | 10-table state machine |
| `master_bot.py` | Full lifecycle management |

#### Dynamic Detection (replaces hardcoded coords)
| File | Purpose |
|------|---------|
| `smart_card_detector.py` | Visual card detection (2-color deck) |
| `dynamic_table_finder.py` | Find tables by green felt |
| `dynamic_table_reader.py` | OCR pot/stack reading |
| `dynamic_card_detector.py` | Brightness-based cards |
| `button_detector.py` | HSV button detection |

#### Self-Learning System
| File | Purpose |
|------|---------|
| `adaptive_learner.py` | Logs actions, tracks success rates |
| `vision_analyzer.py` | Analyzes images, auto-fixes |
| `self_healer.py` | Real-time detection fixing |

#### UI Navigation (GGPoker specific)
| File | Purpose |
|------|---------|
| `dynamic_lobby_navigator.py` | OCR lobby navigation |
| `ui_navigator.py` | General UI automation |
| `gg_registration.py` | Table registration |
| `gg_automation.py` | GGPoker-specific actions |
| `smart_ui_automation.py` | Smart clicking |

#### Experimental Bots
| File | Purpose |
|------|---------|
| `auto_player.py` | Autonomous visual player |
| `ocr_player.py` | OCR-only button detection |
| `beast_mode.py` | Aggressive multi-table |
| `ultimate_bot.py` | Feature-complete attempt |
| `spin_grinder.py` | Spin & Gold focused |

### core/ - 6 New Files (Unified Detection)
Created to consolidate fragmented detection:

| File | Purpose |
|------|---------|
| `constants.py` | **SINGLE SOURCE OF TRUTH** for HSV ranges |
| `card_detector.py` | Unified card detection |
| `button_detector.py` | Unified button detection |
| `window_finder.py` | Unified window finding |
| `unified_learner.py` | Combined learning system |
| `base_bot.py` | Abstract base for all bots |

---

## ARCHITECTURE COMPARISON

### Original (dickreuter/Poker)
```
main.py (GUI)
    ↓
TableScraper → reads table state
    ↓
DecisionMaker → calculates equity, makes decision
    ↓
MouseMover → clicks button
```

**Limitations:**
- Single table only
- Hardcoded pixel coordinates
- GUI required
- PokerStars/PartyPoker focused

### Current (gamble/)
```
cli_controller.py multi (headless)
    ↓
MultiTableController → manages 10 tables
    ↓
TableScreenBased → original + dynamic fallbacks
    ↓
SmartCardDetector → visual detection (any table size)
    ↓
DecisionMaker → SAME as original
    ↓
DynamicMouseMover → color-based clicking
    ↓
AdaptiveLearner → self-improving
```

**Enhancements:**
- Multi-table (up to 10)
- Dynamic detection (no hardcoded coords)
- Headless operation (no GUI needed)
- GGPoker optimized
- Self-learning/healing

---

## WHAT'S USED vs WHAT'S IGNORED

### ACTIVELY USED (Core Decision Logic)
```python
# From original - THE BRAIN
from gamble.decisionmaker.decisionmaker import Decision
from gamble.decisionmaker.montecarlo_python import run_montecarlo_wrapper
from gamble.scraper.table_screen_based import TableScreenBased

# Decision flow (UNCHANGED from original):
# 1. Get cards → lookup in preflop chart
# 2. Calculate equity via Monte Carlo
# 3. Compare equity vs pot odds
# 4. Apply strategy rules
# 5. Return: fold/call/check/raise
```

### ENHANCED (Original + New)
```python
# table_scraper.py - added dynamic fallbacks
def get_my_cards2(self):
    # Try smart detection first (NEW)
    cards = SmartCardDetector.detect(...)
    if not cards:
        # Fall back to original template matching
        cards = original_template_match(...)

def get_pots(self):
    # Try original first
    pot = original_method()
    if not pot:
        # Fall back to OCR (NEW)
        pot = DynamicTableReader.get_pot()
```

### NOT ACTIVELY USED (42+ experimental bots)
Most of `tools/*.py` are experimental attempts that should be ignored:
- `beast_mode.py` - standalone, doesn't use DecisionMaker
- `ultimate_bot.py` - incomplete
- `spin_grinder.py` - redundant
- etc.

**USE ONLY:** `python -m gamble.tools.cli_controller multi`

---

## KEY DIFFERENCES

| Aspect | Original | Current |
|--------|----------|---------|
| Tables | 1 | Up to 10 |
| GUI | Required | Optional (headless) |
| Coords | Hardcoded pixels | Dynamic detection |
| Poker site | PokerStars/Party | GGPoker |
| Cards | Template only | Template + Visual + OCR |
| Deck | 4-color assumed | 2-color fixed |
| Learning | None | Self-improving |
| Fast fold | Enabled | **Disabled** (was causing issues) |

---

## FILES THAT SHOULD NOT BE MODIFIED

These are the original working files - don't break them:

1. `decisionmaker/decisionmaker.py` - Core decision logic
2. `decisionmaker/montecarlo_*.py` - Equity calculations
3. `decisionmaker/outs_calculator.py` - Draw calculations
4. `decisionmaker/genetic_algorithm.py` - Strategy optimization
5. `scraper/table_scraper.py` - Table state reading (only add fallbacks)

---

## RECOMMENDED APPROACH

1. **Use original decision logic** - It works, don't replace it
2. **Add dynamic detection as fallbacks** - Don't remove original methods
3. **Use core/constants.py** - Single source of truth for HSV ranges
4. **Run multi mode** - `cli_controller multi` uses everything correctly
5. **Ignore experimental bots** - 42+ files are redundant attempts
