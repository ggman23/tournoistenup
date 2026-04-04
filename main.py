#!/usr/bin/env python3
"""
TenUp tournament scraper — entry point.

Usage:
    python main.py                          # run with config.json
    python main.py --config my_cfg.json     # custom config
    python main.py --cookies cookies.json   # inject browser cookies
    python main.py --reset                  # reset history (all = new)
    python main.py --dry-run                # fetch without saving
    python main.py --enrich                 # fetch detail pages (format 1-7)
    python main.py --html-only              # regenerate HTML from existing data
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

from scraper import TenupScraper
from storage import update_storage, load_json
from notify import notify
from generate_html import generate_html, generate_from_file
from enrich import enrich_all

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
    p.add_argument("--reset", action="store_true",
                   help="Reset history (all tournaments appear as new)")
    p.add_argument("--dry-run", action="store_true",
                   help="Fetch and display without saving to disk")
    p.add_argument("--enrich", action="store_true",
                   help="Fetch individual tournament pages to get format (1-7) etc.")
    p.add_argument("--enrich-max", type=int, default=0, metavar="N",
                   help="Limit enrichment to first N tournaments (0 = all)")
    p.add_argument("--html-only", action="store_true",
                   help="Regenerate HTML from existing data file (no scraping)")
    p.add_argument("--enrich-only", action="store_true",
                   help="Re-enrich existing data (no scraping) then regenerate HTML")
    p.add_argument("--pages-max", type=int, default=0, metavar="N",
                   help="Stop scraping after N pages (0 = all). Use to test pagination quickly.")
    p.add_argument("--date-start", default=None, metavar="DD/MM/YY",
                   help="Start date for search (overrides config). Format: 01/04/26")
    p.add_argument("--date-end", default=None, metavar="DD/MM/YY",
                   help="End date for search (overrides config). Format: 01/09/26")
    p.add_argument("--no-prompt", action="store_true",
                   help="Never prompt interactively (use config dates as-is)")
    return p.parse_args()


def main():
    args = parse_args()

    # Load config
    if not os.path.exists(args.config):
        logger.error("Config file not found: %s", args.config)
        sys.exit(1)

    with open(args.config) as f:
        config = json.load(f)

    # ── Date prompts (interactive if not supplied via CLI or --no-prompt) ────────
    def _ask_date(label: str, default: str) -> str:
        """Prompt user for a date; return default if empty input."""
        try:
            val = input(f"{label} [{default}] : ").strip()
        except (EOFError, KeyboardInterrupt):
            return default
        return val if val else default

    if args.html_only or args.enrich_only:
        pass  # no scraping → no date needed
    else:
        cfg_start = config["search"].get("date_start", "")
        cfg_end   = config["search"].get("date_end", "")
        if args.date_start:
            config["search"]["date_start"] = args.date_start
        elif not args.no_prompt:
            config["search"]["date_start"] = _ask_date("Date de début (DD/MM/YY)", cfg_start)
        if args.date_end:
            config["search"]["date_end"] = args.date_end
        elif not args.no_prompt:
            config["search"]["date_end"] = _ask_date("Date de fin   (DD/MM/YY)", cfg_end)
        logger.info("Plage de recherche : %s → %s",
                    config["search"]["date_start"], config["search"]["date_end"])

    data_file    = config["storage"]["data_file"]
    history_file = config["storage"]["history_file"]
    output_file  = config["notifications"]["output_file"]
    print_console = config["notifications"]["print_to_console"]
    html_file    = config["notifications"].get("html_file", "data/tournaments.html")

    # ── HTML-only mode: just regenerate the report ──────────────────────────
    if args.html_only:
        if not os.path.exists(data_file):
            logger.error("No data file found at %s — run without --html-only first.", data_file)
            sys.exit(1)
        history = load_json(history_file)
        new_ids = set(history.get("last_new_ids", []))
        generate_from_file(data_file, html_file, new_ids=new_ids)
        sys.exit(0)

    # ── Enrich-only mode: re-enrich + regenerate without re-scraping ─────────
    if args.enrich_only:
        if not os.path.exists(data_file):
            logger.error("No data file found at %s — run a full scrape first.", data_file)
            sys.exit(1)
        cookies_file = args.cookies or os.environ.get("TENUP_COOKIES_FILE")
        scraper = TenupScraper(config, cookies_file=cookies_file)
        saved = load_json(data_file)
        tournaments = saved.get("tournaments", [])
        logger.info("Loaded %d tournaments from cache — running enrichment only.", len(tournaments))
        enrich_all(
            tournaments, scraper.session,
            delay_s=1.5, max_enrich=args.enrich_max,
        )
        # Save updated data
        import json as _json, datetime as _dt
        saved["tournaments"] = tournaments
        saved["fetched_at"] = saved.get("fetched_at", _dt.datetime.utcnow().isoformat())
        os.makedirs(os.path.dirname(data_file) or ".", exist_ok=True)
        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(saved, f, ensure_ascii=False, indent=2)
        history = load_json(history_file)
        new_ids = set(history.get("last_new_ids", []))
        generate_html(
            tournaments, html_file, new_ids=new_ids,
            fetched_at=saved.get("fetched_at", ""),
        )
        sys.exit(0)

    # ── Reset history ────────────────────────────────────────────────────────
    if args.reset:
        if os.path.exists(history_file):
            os.remove(history_file)
            logger.info("History reset.")

    # ── Cookies ──────────────────────────────────────────────────────────────
    cookies_file = args.cookies or os.environ.get("TENUP_COOKIES_FILE")

    # ── Scrape ───────────────────────────────────────────────────────────────
    scraper = TenupScraper(config, cookies_file=cookies_file)
    logger.info("Starting tournament fetch...")

    try:
        tournaments = scraper.fetch_all(max_pages=args.pages_max)
    except Exception as e:
        logger.error("Scraping failed: %s", e)
        sys.exit(1)

    if not tournaments:
        logger.warning("No tournaments returned. Check your search criteria or cookies.")
        sys.exit(0)

    # ── Post-filter: drop tournaments that START before date_start ────────────
    raw_start = config["search"].get("date_start", "")
    try:
        # Config format is DD/MM/YY (e.g. "01/04/26")
        cutoff = datetime.strptime(raw_start, "%d/%m/%y")
        before = [t for t in tournaments
                  if datetime.fromisoformat(
                      t.get("dateDebut", {}).get("date", "9999-01-01")[:10]
                  ) < cutoff]
        if before:
            names = [t.get("libelle", "?") for t in before]
            logger.info("Filtered out %d tournament(s) starting before %s: %s",
                        len(before), cutoff.strftime("%d/%m/%Y"), names)
        tournaments = [t for t in tournaments if t not in before]
    except Exception as e:
        logger.debug("Date post-filter skipped: %s", e)

    # ── Merge previously enriched data (format, detail_url) ──────────────────
    # Fresh scraped data has no 'enriched' key. Reload from the saved file so
    # format badges persist across runs even without --enrich.
    if os.path.exists(data_file):
        prev = load_json(data_file)
        enriched_cache = {
            (t.get("originalId") or t.get("id")): t["enriched"]
            for t in prev.get("tournaments", [])
            if t.get("enriched")
        }
        merged = 0
        for t in tournaments:
            tid = t.get("originalId") or t.get("id")
            if tid in enriched_cache:
                t["enriched"] = enriched_cache[tid]
                merged += 1
        if merged:
            logger.info("Reloaded cached enriched data for %d tournaments.", merged)

    # ── Dry run ──────────────────────────────────────────────────────────────
    if args.dry_run:
        print(f"\nDry run — {len(tournaments)} tournaments fetched (not saved).")
        for t in tournaments[:5]:
            print(f"  • {t.get('libelle')} — {t.get('installation', {}).get('ville')}")
        if len(tournaments) > 5:
            print(f"  ... and {len(tournaments) - 5} more.")
        sys.exit(0)

    # ── Enrich (format 1-7 + detail URL) ─────────────────────────────────────
    if args.enrich:
        enrich_all(
            tournaments, scraper.session,
            delay_s=1.5, max_enrich=args.enrich_max,
        )

    # ── Persist & detect new ─────────────────────────────────────────────────
    new_tournaments, current_ids = update_storage(tournaments, data_file, history_file)

    # Store new IDs in history for html-only regeneration
    history = load_json(history_file)
    new_ids = {t.get("originalId") or t.get("id", "") for t in new_tournaments}
    history["last_new_ids"] = sorted(new_ids)
    import json as _json
    os.makedirs(os.path.dirname(history_file) or ".", exist_ok=True)
    with open(history_file, "w") as f:
        _json.dump(history, f, indent=2)

    # ── Terminal notification ─────────────────────────────────────────────────
    notify(new_tournaments, output_file, print_to_console=print_console)

    # ── Generate HTML report ──────────────────────────────────────────────────
    generate_html(
        tournaments,
        html_file,
        new_ids=new_ids,
        fetched_at=load_json(data_file).get("fetched_at", ""),
    )


if __name__ == "__main__":
    main()
