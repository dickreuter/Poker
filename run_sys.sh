#!/bin/bash

# Start the system service using absolute paths
# Runs in the background

PROJECT_ROOT="/Users/sebastian/Developer/Gamble"
cd "$PROJECT_ROOT"

# Stop existing if running
./stop_sys.sh

echo "Starting system service..."
# Use absolute path to venv python
# BOT_STRATEGY env var set by tray app (defaults to 'ev')
STRATEGY_FLAG=""
if [ -n "$BOT_STRATEGY" ] && [ "$BOT_STRATEGY" != "ev" ]; then
    STRATEGY_FLAG="--strategy $BOT_STRATEGY"
fi
"$PROJECT_ROOT/venv/bin/python" -m sys_core.engine --no-standardize $STRATEGY_FLAG > /dev/null 2> "$PROJECT_ROOT/log/sys_err.log" &

echo "Service started (strategy: ${BOT_STRATEGY:-ev})."
