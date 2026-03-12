"""
Spin & Gold $1 Tournament Grinder
Fully automated tournament registration and play loop

BEAST MODE AUTOMATION
- Registers for $1 Spin & Gold tournaments
- Plays them using the existing system service
- Auto-registers for next tournament when done
- Loops forever

Usage:
    python3 -m sys_core.tools.spin_gold_grinder
    python3 -m sys_core.tools.spin_gold_grinder --buy-in 1.0 --max-tables 1
"""
import logging
import time
from sys_core.tools.gg_automation import GGSystemAutomation
from sys_core.tools.cli_controller import BotController, INPUT_FAST
from sys_core.tools.helper import init_logger

log = logging.getLogger(__name__)


class SpinGoldGrinder:
    """
    Automated Spin & Gold tournament grinding.

    This is the BEAST MODE automation:
    1. Scans for GGSystem windows
    2. Navigates to Spin & Gold lobby
    3. Registers for $1 tournament
    4. Waits for table to open
    5. Plays using existing bot (Monte Carlo + strategy)
    6. When tournament ends, registers for next one
    7. Repeats forever

    Usage:
        grinder = SpinGoldGrinder(buy_in=1.0)
        grinder.start()  # Runs forever, registering and playing
    """

    def __init__(self, buy_in: float = 1.0, max_tables: int = 1):
        """
        Initialize the grinder.

        Args:
            buy_in: Tournament buy-in amount (default $1)
            max_tables: Maximum concurrent tables (default 1)
        """
        self.buy_in = buy_in
        self.max_tables = max_tables
        self.automation = GGSystemAutomation()
        self.bot = None
        self.tournaments_played = 0
        self.tournaments_won = 0
        self.total_profit = 0.0
        self.running = False
        self.start_time = None

    def start(self):
        """Start the grinding loop - runs forever until stopped"""
        log.info("=" * 60)
        log.info("SPIN & GOLD GRINDER - BEAST MODE ACTIVATED")
        log.info(f"Buy-in: ${self.buy_in} | Max tables: {self.max_tables}")
        log.info("=" * 60)

        self.running = True
        self.start_time = time.time()

        while self.running:
            try:
                # Step 1: Scan current state
                self.automation.scan_windows()
                tables = self.automation.get_tables()

                log.debug(f"Found {len(tables)} active table(s)")

                # Step 2: If no active tables, register for one
                if len(tables) < self.max_tables:
                    log.info("=" * 40)
                    log.info("Registering for new tournament...")
                    self._register_tournament()
                    time.sleep(2)
                    continue

                # Step 3: If tables exist, make sure bot is running
                if not self.bot or not self.bot.running:
                    log.info("Starting bot for active table...")
                    self.bot = BotController(input_method=INPUT_FAST, auto_act=True, verbose=True)
                    self.bot.start()

                # Step 4: Check if tournament ended (table closed)
                time.sleep(5)
                self.automation.scan_windows()
                new_tables = self.automation.get_tables()

                if len(new_tables) < len(tables):
                    log.info("=" * 40)
                    log.info("TOURNAMENT ENDED!")
                    self.tournaments_played += 1

                    # Log stats
                    uptime = time.time() - self.start_time
                    log.info(f"Tournaments played: {self.tournaments_played}")
                    log.info(f"Uptime: {uptime/60:.1f} minutes")
                    log.info(f"Rate: {self.tournaments_played / (uptime/3600):.1f} tournaments/hour")
                    log.info("=" * 40)

                    # Stop the bot
                    if self.bot:
                        self.bot.stop()
                        self.bot = None

                    # Small delay before registering next
                    time.sleep(2)

            except KeyboardInterrupt:
                log.info("Keyboard interrupt received")
                break
            except Exception as e:
                log.error(f"Error in grinder loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)

        self.stop()

    def _register_tournament(self):
        """Navigate and register for tournament"""
        try:
            # Open Spin & Gold section
            log.info("Opening Spin & Gold lobby...")
            self.automation.open_spin_gold()
            time.sleep(0.5)

            # Register for $1 tournament
            log.info(f"Registering for ${self.buy_in} tournament...")
            self.automation.register_spin_gold_1_dollar()

            # Wait for table to open
            log.info("Waiting for table to open...")
            if self.automation.wait_for_table_window(timeout=60):
                log.info("Table opened! Starting play...")
            else:
                log.warning("Table did not open in time")

        except Exception as e:
            log.error(f"Error registering: {e}")

    def stop(self):
        """Stop the grinder and print final stats"""
        self.running = False

        if self.bot:
            self.bot.stop()
            self.bot = None

        # Final stats
        if self.start_time:
            uptime = time.time() - self.start_time
            log.info("=" * 60)
            log.info("GRINDER STOPPED - FINAL STATS")
            log.info("=" * 60)
            log.info(f"Total tournaments: {self.tournaments_played}")
            log.info(f"Total uptime: {uptime/60:.1f} minutes")
            if self.tournaments_played > 0:
                log.info(f"Rate: {self.tournaments_played / (uptime/3600):.1f} tournaments/hour")
            log.info("=" * 60)

    def status(self):
        """Get current status"""
        uptime = time.time() - self.start_time if self.start_time else 0
        return {
            "running": self.running,
            "tournaments_played": self.tournaments_played,
            "uptime_seconds": uptime,
            "uptime_minutes": uptime / 60,
            "bot_running": self.bot.running if self.bot else False,
            "tables_active": len(self.automation.get_tables()) if self.automation else 0
        }


def main():
    """Main entry point for CLI"""
    import argparse

    # Initialize logging
    init_logger(screenlevel=logging.INFO, filename='dm_assistant', logdir='log')

    parser = argparse.ArgumentParser(
        description="Spin & Gold $1 Tournament Grinder - BEAST MODE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 -m sys_core.tools.spin_gold_grinder
    python3 -m sys_core.tools.spin_gold_grinder --buy-in 1.0 --max-tables 1
    python3 -m sys_core.tools.spin_gold_grinder --buy-in 5.0 --max-tables 2

Monitor logs:
    tail -f log/dm_assistant.log | grep -E "GRINDER|Register|tournament|SUCCESS"
        """
    )
    parser.add_argument("--buy-in", type=float, default=1.0,
                       help="Buy-in amount in dollars (default: 1.0)")
    parser.add_argument("--max-tables", type=int, default=1,
                       help="Maximum concurrent tables (default: 1)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("=" * 60)
    print("SPIN & GOLD GRINDER - BEAST MODE")
    print("=" * 60)
    print(f"Buy-in: ${args.buy_in}")
    print(f"Max tables: {args.max_tables}")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()

    grinder = SpinGoldGrinder(buy_in=args.buy_in, max_tables=args.max_tables)

    try:
        grinder.start()
    except KeyboardInterrupt:
        print("\nStopping grinder...")
        grinder.stop()


if __name__ == "__main__":
    main()
