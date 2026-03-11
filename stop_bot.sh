#!/bin/bash

# Find and kill the poker bot (multi_table_runner)
# Searches for the module name or the filename

# List processes before killing
PROCS=$(ps aux | grep -E "gamble.multi_table_runner|multi_table_runner.py" | grep -v grep | awk '{print $2}')

if [ -z "$PROCS" ]; then
    echo "No poker bot process found running."
else
    echo "Stopping poker bot (PIDs: $PROCS)..."
    echo "$PROCS" | xargs kill -9
    echo "Bot stopped."
fi
