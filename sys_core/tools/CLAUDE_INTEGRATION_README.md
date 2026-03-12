# Claude Opus 4.6 System Utility Integration

## Overview

This directory contains the Claude Opus 4.6 integration for the GGSystem bot. It provides intelligent decision-making while maintaining fast local detection for real-time play.

## Files

| File | Description |
|------|-------------|
| `claude_poker_brain.py` | Core Claude integration - decision making and vision |
| `claude_enhanced_runner.py` | Multi-table runner with Claude integration |
| `claude_brain.py` | Inter-session communication (existing) |
| `claude_session.py` | Session management (existing) |

## Quick Start

```bash
# Install dependencies
pip install anthropic

# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Run the bot
python -m sys_core.tools.claude_enhanced_runner
```

## Architecture

```
                    ┌─────────────────────┐
                    │   GGSystem Window    │
                    └──────────┬──────────┘
                               │
                               │ Screenshot (every 300ms)
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    LOCAL DETECTION (FAST)                     │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │   Button    │  │    Card     │  │    OCR      │          │
│  │  Detection  │  │  Detection  │  │   Values    │          │
│  │  (HSV)      │  │ (Template)  │  │ (Pot/Stack) │          │
│  │  10-50ms    │  │  10-50ms    │  │  100-200ms  │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
│                                                               │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            │ Structured data OR detection failure
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                  CLAUDE OPUS 4.6 LAYER                        │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              DECISION ENGINE (500ms-2s)                  │ │
│  │                                                          │ │
│  │  Input: {cards, community, pot, to_call, buttons}       │ │
│  │                                                          │ │
│  │  Adaptive Thinking:                                      │ │
│  │  - LOW: Free checks                                      │ │
│  │  - MEDIUM: Standard pots                                 │ │
│  │  - HIGH: Big pots (>20 BBs)                             │ │
│  │  - MAX: All-in decisions                                │ │
│  │                                                          │ │
│  │  Output: {action, amount, confidence, reasoning}        │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              VISION FALLBACK (1-3s)                      │ │
│  │                                                          │ │
│  │  When: Local detection fails 3+ times                   │ │
│  │  Input: Screenshot (base64)                             │ │
│  │  Output: Full table analysis                            │ │
│  │  Side effect: Updates local detection thresholds        │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            │ Action: fold/check/call/raise
                            ▼
                    ┌─────────────────────┐
                    │   Mouse Click       │
                    │   (mouse_mover.py)  │
                    └─────────────────────┘
```

## API Reference

### ClaudeSystemBrain

The main decision-making class.

```python
from sys_core.tools.claude_poker_brain import ClaudeSystemBrain, SystemDecision

# Initialize
brain = ClaudeSystemBrain(api_key="optional-override")

# Make a decision
decision: SystemDecision = brain.decide_action(
    my_cards=['AH', 'KS'],
    community_cards=['QH', 'JD', '2C'],
    pot=150.0,
    to_call=50.0,
    my_stack=500.0,
    opponent_stacks=[450.0, 600.0],
    position='BTN',
    buttons=['fold', 'call', 'raise'],
    game_history="Optional recent history"
)

# Access decision
print(decision.action)           # SystemAction.CALL
print(decision.amount)           # None (for calls) or bet amount
print(decision.confidence)       # 0.85
print(decision.reasoning)        # "Nut flush draw with 9 outs..."
print(decision.thinking_time_ms) # 850

# Vision fallback
from sys_core.tools.claude_poker_brain import TableAnalysis

analysis: TableAnalysis = brain.analyze_screenshot(
    screenshot=pil_image,  # PIL Image
    # OR
    screenshot_base64="base64-encoded-png"
)

print(analysis.my_cards)         # ['AH', 'KS']
print(analysis.buttons)          # ['fold', 'call', 'raise']
print(analysis.pot)              # 150.0
print(analysis.confidence)       # 0.9

# Get stats
stats = brain.get_stats()
print(stats['decisions_made'])
print(stats['avg_thinking_time_ms'])
```

### Quick Functions

```python
from sys_core.tools.claude_poker_brain import decide, analyze_table

# Quick decision (uses singleton brain)
decision = decide(
    my_cards=['AH', 'KS'],
    community_cards=[],
    pot=3.0,
    to_call=2.0,
    my_stack=100.0,
    buttons=['fold', 'call', 'raise']
)

# Quick vision analysis
analysis = analyze_table(screenshot_image)
```

### SystemAction Enum

```python
from sys_core.tools.claude_poker_brain import SystemAction

SystemAction.FOLD    # "fold"
SystemAction.CHECK   # "check"
SystemAction.CALL    # "call"
SystemAction.BET     # "bet"
SystemAction.RAISE   # "raise"
SystemAction.ALL_IN  # "all_in"
```

### EffortLevel Enum

```python
from sys_core.tools.claude_poker_brain import EffortLevel

EffortLevel.LOW     # Simple decisions
EffortLevel.MEDIUM  # Standard decisions
EffortLevel.HIGH    # Complex decisions
EffortLevel.MAX     # Critical decisions
```

## Configuration

### Environment Variables

```bash
# Required
ANTHROPIC_API_KEY="sk-ant-..."

# Optional
CLAUDE_POKER_MODEL="claude-opus-4-6"
```

### Thresholds

Effort level is automatically determined based on:

| Condition | Effort |
|-----------|--------|
| Free check available | LOW |
| All-in (>50% stack) | MAX |
| Big pot (>20 BBs) | HIGH |
| Everything else | MEDIUM |

Override with `force_effort` parameter:

```python
decision = brain.decide_action(
    ...,
    force_effort=EffortLevel.MAX
)
```

## Performance Tuning

### Reduce Latency

1. **Use lower effort for simple spots:**
   ```python
   # Auto-determined, but can force
   decision = brain.decide_action(..., force_effort=EffortLevel.LOW)
   ```

2. **Disable vision fallback:**
   ```bash
   python -m sys_core.tools.claude_enhanced_runner --no-claude-vision
   ```

3. **Use local strategy only:**
   ```bash
   python -m sys_core.tools.claude_enhanced_runner --no-claude-decisions
   ```

### Reduce API Costs

1. **Use local strategy for obvious spots:**
   - The runner already checks for free checks locally

2. **Limit vision fallbacks:**
   - Only triggers after 3 consecutive detection failures

3. **Batch decisions (future):**
   - Analyze multiple tables in one API call

## Error Handling

### Decision Failures

If Claude fails, the system falls back to safe local strategy:

```python
# Fallback priority:
1. If 'check' available → CHECK
2. If 'fold' available → FOLD
3. Otherwise → CALL
```

### Vision Failures

If vision analysis fails:
- Error is logged
- Local detection continues
- No action taken until detection succeeds

## Testing

```bash
# Test the brain directly
python -m sys_core.tools.claude_poker_brain

# Test with live tables
python -m sys_core.tools.claude_enhanced_runner --max-tables 1
```

## Logging

```python
import logging
logging.getLogger('sys_core.tools.claude_poker_brain').setLevel(logging.DEBUG)
```

Log locations:
- `log/claude_enhanced.log` - Main runner logs
- Console output - Real-time decisions

## Integration with Existing Systems

### Using with engine.py

The existing `engine.py` can be modified to use Claude:

```python
# In engine.py, add to imports:
from sys_core.tools.claude_poker_brain import ClaudeSystemBrain, SystemDecision

# In the class:
self.claude_brain = ClaudeSystemBrain()

# In make_decision():
decision = self.claude_brain.decide_action(
    my_cards=session.my_cards,
    # ... etc
)
return decision.action.value
```

### Using with adaptive_learner.py

Vision fallback automatically updates thresholds:

```python
from sys_core.tools.adaptive_learner import set_threshold

# When Claude detects something local CV missed:
set_threshold('white_pixel_min', 140)  # Lower threshold
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `ImportError: anthropic` | Library not installed | `pip install anthropic` |
| `ValueError: No API key` | Missing env var | `export ANTHROPIC_API_KEY=...` |
| `TimeoutError` | Slow network | Check connection, increase timeout |
| Wrong decisions | Bad input data | Verify local detection accuracy |
| High latency | Complex reasoning | Use lower effort level |

## Future Roadmap

1. **Agent Teams** - Parallel Claude instances per table
2. **Memory Tool** - Persistent learning across sessions
3. **Fast Mode** - Use Claude's 2.5x faster inference
4. **Opponent Modeling** - Track player tendencies
5. **Hand History Review** - Post-session analysis

## License

Part of the GGSystem Utility project. Internal use only.
