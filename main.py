#!/usr/bin/env python3
"""
TenUp tournament scraper — entry point.

Usage:
    python main.py                        # run with config.json
    python main.py --config my_cfg.json   # custom config
    python main.py --cookies cookies.json # inject browser cookies
    python main.py --reset                # reset known IDs (treat all as new)
    python main.py --dry-run              # fetch and display without saving
"""

import argparse
import json
import logging
import os
import sys

from scraper import TenupScraper
from storage import update_storage, load_json, save_json
from notify import notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser(description="Scrape tenup.fft.fr tournaments")
    p.add_argument("--config", default="config.json", help="Path to config file")
    p.add_argument("--cookies", default=None, help="Path to cookies JSON file")
    p.add_argument(
        "--reset",
        action="store_true",
        help="Reset history (all tournaments will appear as new)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and display without saving to disk",
    )
    return p.parse_args()


def main():
    args = parse_args()

    # Load config
    if not os.path.exists(args.config):
        logger.error("Config file not found: %s", args.config)
        sys.exit(1)

    with open(args.config) as f:
        config = json.load(f)

    data_file = config["storage"]["data_file"]
    history_file = config["storage"]["history_file"]
    output_file = config["notifications"]["output_file"]
    print_console = config["notifications"]["print_to_console"]

    # Reset history if requested
    if args.reset:
        if os.path.exists(history_file):
            os.remove(history_file)
            logger.info("History reset.")

    # Cookies: CLI flag takes precedence, then check env var
    cookies_file = args.cookies or os.environ.get("TENUP_COOKIES_FILE")

    # Run scraper
    scraper = TenupScraper(config, cookies_file=cookies_file)
    logger.info("Starting tournament fetch...")

    try:
        tournaments = scraper.fetch_all()
    except Exception as e:
        logger.error("Scraping failed: %s", e)
        sys.exit(1)

    if not tournaments:
        logger.warning("No tournaments returned. Check your search criteria or cookies.")
        sys.exit(0)

    if args.dry_run:
        print(f"\nDry run — {len(tournaments)} tournaments fetched (not saved).")
        for t in tournaments[:5]:
            print(f"  • {t.get('libelle')} — {t.get('installation', {}).get('ville')}")
        if len(tournaments) > 5:
            print(f"  ... and {len(tournaments) - 5} more.")
        sys.exit(0)

    # Persist and detect new
    new_tournaments, _ = update_storage(tournaments, data_file, history_file)

    # Notify
    notify(new_tournaments, output_file, print_to_console=print_console)


if __name__ == "__main__":
    main()
