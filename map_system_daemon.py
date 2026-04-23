#!/usr/bin/env python3
import sys
import os
import subprocess
import time
import signal
import logging
import argparse
import configparser
from datetime import datetime

# Setup logging to stdout so Docker picks it up
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Define which section this specific script should look at
SCRIPT_SECTION = 'daemon'


class Daemon:
    def __init__(self, **kwargs):
        self.map_updater = kwargs.get('map_updater', './do_map_updates.sh')
        self.update_sleep = int(kwargs.get('update_sleep', 120))
        self.harvester = kwargs.get('harvester', './do_harvest_shipdata.sh')
        self.harvest_sleep = int(kwargs.get('harvest_sleep', 600))
        self.morning_time = kwargs.get('morning', '09:00')
        self.evening_time = kwargs.get('evening', '23:00')
        self.harvester_enabled = bool(kwargs.get('harvester_enabled', False))
        self.running = True

        # Signal handling for graceful Docker stops
        signal.signal(signal.SIGTERM, self.handle_exit)
        signal.signal(signal.SIGINT, self.handle_exit)

    def handle_exit(self, signum, frame):
        logger.info(f"Signal {signum} detected. Stopping daemon...")
        self.running = False

    def is_morning_shift(self):
        """Determines if current time falls between morning and evening start times."""
        now = datetime.now().strftime('%H:%M')
        # String comparison works for HH:MM format
        return self.morning_time <= now < self.evening_time

    def run(self):
        logger.info("World Map System Daemon Started")
        logger.info(f"Morning Shift ({self.morning_time}): {self.map_updater} (Sleep {self.update_sleep}s)")

        status_str = "ENABLED" if self.harvester_enabled else "DISABLED"
        logger.info(
            f"Evening Shift ({self.evening_time}): {self.harvester} ({status_str}, Sleep {self.harvest_sleep}s)")

        while self.running:
            if self.is_morning_shift():
                current_task = self.map_updater
                current_sleep = self.update_sleep
                mode_label = "MAP UPDATES"
                should_run = True
            else:
                current_task = self.harvester
                current_sleep = self.harvest_sleep
                mode_label = "SHIPPING HARVESTER"
                should_run = self.harvester_enabled

            # 2. Execute the task if enabled
            if should_run:
                try:
                    logger.info(f"[{mode_label}] Executing task...")
                    subprocess.run(current_task, shell=True, check=True)
                except subprocess.CalledProcessError as e:
                    logger.error(f"Task failed with exit code: {e.returncode}")
                except Exception as e:
                    logger.error(f"Unexpected error: {e}")
            else:
                logger.info(f"[{mode_label}] Harvesting is currently disabled. Skipping.")

            # 3. Step-based sleep to catch signals quickly
            if self.running:
                logger.info(f"Waiting {current_sleep}s before next cycle")
                stop_at = time.time() + current_sleep
                while time.time() < stop_at and self.running:
                    time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Map System Daemon")
    parser.add_argument("--config", required=True, help="Path to main config")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        logger.error(f"Config file not found at {args.config}")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(args.config)

    s = SCRIPT_SECTION

    # Ensure the section exists before trying to read from it
    if s not in config:
        logger.error(f"Section [{s}] not found in {args.config}. Using defaults.")
        # We can continue with an empty dict to use internal class defaults
        params = {}
    else:
        try:
            params = {
                'map_updater': config.get(s, 'map_updater', fallback='./do_map_updates.sh'),
                'update_sleep': config.getint(s, 'update_sleep', fallback=120),
                'harvester': config.get(s, 'harvester', fallback='./do_harvest_shipdata.sh'),
                'harvest_sleep': config.getint(s, 'harvest_sleep', fallback=600),
                'harvester_enabled': config.getboolean(s, 'harvester_enabled', fallback=False),
                'morning': config.get(s, 'morning', fallback='09:00'),
                'evening': config.get(s, 'evening', fallback='23:00')
            }
        except Exception as e:
            logger.critical(f"Failed to parse config section [{s}]: {e}")
            sys.exit(1)

    try:
        daemon = Daemon(**params)
        daemon.run()
    except Exception as e:
        logger.critical(f"World Map System Daemon crashed: {e}")
        sys.exit(1)
