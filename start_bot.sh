#!/bin/bash

# Start the poker bot (multi_table_runner) using the project's venv
# Runs in the background and logs output to multi_table.log

# Ensure we're in the project root
cd "$(dirname "$0")"

# Check for venv
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment 'venv' not found. Please create it first."
    exit 1
fi

# Stop existing bot if running
./stop_bot.sh

echo "Starting poker bot (multi_table_runner)..."
# Start the bot in the background
venv/bin/python -m gamble.multi_table_runner > /dev/null 2> /tmp/runner_err.log &

# Get the PID
NEW_PID=$!
echo "Bot started with PID $NEW_PID."
echo "Logs are being written to log/multi_table.log"
echo "To follow logs: tail -f log/multi_table.log"
echo "To stop: ./stop_bot.sh"
