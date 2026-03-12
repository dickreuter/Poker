#!/bin/bash

# Start the Poker Bot Menu Bar Tray App
cd "$(dirname "$0")"

# Use venv python to run the tray app in the background
# We use nohup to keep it running after terminal closes
nohup venv/bin/python bot_tray.py > /dev/null 2>&1 &

echo "Poker Bot Manager Tray App started in background."
echo "Look for the poker icon in your macOS menu bar."
