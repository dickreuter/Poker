#!/usr/bin/env python3
"""
AUTONOMOUS RUNNER - Self-Improving Bot System

This script runs the poker bot continuously and automatically calls Claude
to fix issues when they occur. No human intervention needed.

How it works:
1. Starts the poker bot
2. Monitors logs and screenshots in real-time
3. When success rate drops → saves debug screenshots
4. Calls Claude Code to analyze and fix issues
5. Restarts bot with fixes applied
6. Repeats forever

To run:
    python -m gamble.tools.autonomous_runner --tables 4

Requirements:
    - Claude Code CLI installed and authenticated
    - GGPoker open with tables
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data' / 'learning'
LOG_DIR = PROJECT_ROOT / 'log'
FEEDBACK_FILE = PROJECT_ROOT / 'CLAUDE_FEEDBACK.md'
STATS_FILE = DATA_DIR / 'stats.json'
DEBUG_DIR = DATA_DIR / 'debug'

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger('autonomous_runner')


class AutonomousRunner:
    """
    Runs the poker bot autonomously with self-improvement via Claude.
    """

    def __init__(self, max_tables: int = 4, check_interval: int = 60,
                 fix_threshold: float = 0.7):
        """
        Args:
            max_tables: Maximum number of tables to play
            check_interval: How often to check stats (seconds)
            fix_threshold: Success rate below this triggers Claude fix
        """
        self.max_tables = max_tables
        self.check_interval = check_interval
        self.fix_threshold = fix_threshold
        self.bot_process: Optional[subprocess.Popen] = None
        self.running = True
        self.fixes_applied = 0
        self.sessions_run = 0

    def start_bot(self) -> bool:
        """Start the poker bot process."""
        log.info(f"Starting poker bot with {self.max_tables} tables...")

        try:
            self.bot_process = subprocess.Popen(
                [
                    sys.executable, '-m', 'gamble.tools.cli_controller',
                    'start', '--input', 'dynamic'
                ],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            self.sessions_run += 1
            log.info(f"Bot started (PID: {self.bot_process.pid})")
            return True
        except Exception as e:
            log.error(f"Failed to start bot: {e}")
            return False

    def stop_bot(self):
        """Stop the poker bot process."""
        if self.bot_process:
            log.info("Stopping bot...")
            self.bot_process.terminate()
            try:
                self.bot_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.bot_process.kill()
            self.bot_process = None
            log.info("Bot stopped")

    def check_bot_health(self) -> bool:
        """Check if bot is still running."""
        if self.bot_process is None:
            return False
        return self.bot_process.poll() is None

    def get_stats(self) -> Dict:
        """Load current stats from file."""
        if STATS_FILE.exists():
            try:
                return json.loads(STATS_FILE.read_text())
            except:
                pass
        return {'by_type': {}, 'total_actions': 0}

    def get_low_success_actions(self) -> List[str]:
        """Get action types with success rate below threshold."""
        stats = self.get_stats()
        low_success = []

        for action_type, type_stats in stats.get('by_type', {}).items():
            total = type_stats.get('success', 0) + type_stats.get('fail', 0)
            if total >= 10:  # Need enough data
                rate = type_stats.get('success', 0) / total
                if rate < self.fix_threshold:
                    low_success.append({
                        'action': action_type,
                        'rate': rate,
                        'total': total
                    })

        return low_success

    def get_recent_debug_screenshots(self) -> List[Path]:
        """Get debug screenshots from last hour."""
        if not DEBUG_DIR.exists():
            return []

        cutoff = time.time() - 3600  # Last hour
        screenshots = []

        for f in DEBUG_DIR.glob('*.png'):
            if f.stat().st_mtime > cutoff:
                screenshots.append(f)

        return sorted(screenshots, key=lambda f: f.stat().st_mtime, reverse=True)[:10]

    def call_claude_to_fix(self, issues: List[Dict]) -> bool:
        """
        Call Claude Code to analyze and fix issues.

        This sends the issues to Claude and asks it to fix the code.
        """
        if not issues:
            return False

        log.info(f"Calling Claude to fix {len(issues)} issue(s)...")

        # Build the prompt
        prompt = """AUTONOMOUS FIX REQUEST

The poker bot is running but some actions are failing. Please analyze and fix:

## Issues Detected

"""
        for issue in issues:
            prompt += f"- **{issue['action']}**: {issue['rate']:.0%} success rate ({issue['total']} attempts)\n"

        # Add recent screenshots
        screenshots = self.get_recent_debug_screenshots()
        if screenshots:
            prompt += f"\n## Recent Debug Screenshots\n\nSaved in: {DEBUG_DIR}\n"
            for ss in screenshots[:5]:
                prompt += f"- {ss.name}\n"

        prompt += """

## Instructions

1. Read the debug screenshots to understand what failed
2. Check the relevant detection code
3. Adjust thresholds or detection logic
4. Make the minimal fix needed
5. The bot will restart automatically after you're done

Focus on making the detection MORE reliable, not more complex.
"""

        # Call Claude Code
        try:
            result = subprocess.run(
                ['claude', '--print', prompt],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode == 0:
                log.info("Claude analysis complete")
                self.fixes_applied += 1
                return True
            else:
                log.error(f"Claude returned error: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            log.error("Claude timed out")
            return False
        except FileNotFoundError:
            log.error("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code")
            return False
        except Exception as e:
            log.error(f"Failed to call Claude: {e}")
            return False

    def run_cycle(self):
        """Run one monitoring cycle."""
        # Check bot health
        if not self.check_bot_health():
            log.warning("Bot not running, restarting...")
            self.start_bot()
            time.sleep(30)  # Let bot initialize
            return

        # Check for issues
        issues = self.get_low_success_actions()

        if issues:
            log.warning(f"Found {len(issues)} low-success actions")
            for issue in issues:
                log.warning(f"  - {issue['action']}: {issue['rate']:.0%}")

            # Stop bot, fix, restart
            self.stop_bot()
            time.sleep(2)

            if self.call_claude_to_fix(issues):
                log.info("Fixes applied, restarting bot...")
            else:
                log.warning("Could not apply fixes, restarting anyway...")

            time.sleep(5)
            self.start_bot()
        else:
            stats = self.get_stats()
            log.info(f"Bot healthy - {stats.get('total_actions', 0)} total actions")

    def run(self):
        """Main run loop."""
        log.info("=" * 60)
        log.info("AUTONOMOUS RUNNER STARTING")
        log.info(f"Max tables: {self.max_tables}")
        log.info(f"Check interval: {self.check_interval}s")
        log.info(f"Fix threshold: {self.fix_threshold:.0%}")
        log.info("=" * 60)

        # Create directories
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)

        # Start bot
        self.start_bot()
        time.sleep(30)  # Let bot initialize

        try:
            while self.running:
                self.run_cycle()
                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            log.info("Stopping (Ctrl+C)...")
        finally:
            self.stop_bot()
            log.info(f"Autonomous runner stopped. Sessions: {self.sessions_run}, Fixes: {self.fixes_applied}")


def main():
    parser = argparse.ArgumentParser(description="Autonomous Poker Bot Runner")
    parser.add_argument('--tables', type=int, default=4,
                       help='Maximum number of tables')
    parser.add_argument('--check-interval', type=int, default=60,
                       help='How often to check stats (seconds)')
    parser.add_argument('--fix-threshold', type=float, default=0.7,
                       help='Success rate below this triggers fix')

    args = parser.parse_args()

    runner = AutonomousRunner(
        max_tables=args.tables,
        check_interval=args.check_interval,
        fix_threshold=args.fix_threshold
    )
    runner.run()


if __name__ == '__main__':
    main()
