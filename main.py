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
import re
import sys
from datetime import datetime

import requests as _req

from scraper import TenupScraper
from storage import update_storage, load_json
from notify import notify
from generate_html import generate_html, generate_from_file
from enrich import enrich_all

def _search_city_fr(name: str) -> list[dict]:
    """Search French communes via geo.api.gouv.fr."""
    try:
        url = (
            "https://geo.api.gouv.fr/communes"
            f"?nom={_req.utils.quote(name)}&fields=nom,codesPostaux,centre"
            "&format=json&geometry=centre&boost=population&limit=10"
        )
        r = _req.get(url, timeout=8)
        r.raise_for_status()
        results = []
        for city in r.json():
            coords = city.get("centre", {}).get("coordinates", [None, None])
            if len(coords) < 2 or None in coords:
                continue
            lng, lat = coords[0], coords[1]
            postal = city.get("codesPostaux", ["?"])[0]
            nom    = city["nom"].upper()
            label  = f"{nom}, {postal}"
            results.append({"label": label, "value": label,
                            "lat": round(lat, 6), "lng": round(lng, 6), "country": "fr"})
        return results
    except Exception as e:
        logging.getLogger(__name__).warning("City search failed: %s", e)
        return []


def _city_slug(ville_cfg: dict) -> str:
    """Filesystem-safe slug: 'bordeaux_33000_50km'."""
    label = ville_cfg.get("label", "default")
    km    = ville_cfg.get("distance_km", 100)
    slug  = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return f"{slug}_{km}km"


def _prompt_city(default_ville: dict) -> dict:
    while True:
        try:
            name = input(f"Ville [{default_ville.get('label','')}] : ").strip()
        except (EOFError, KeyboardInterrupt):
            return default_ville
        if not name:
            return default_ville
        cities = _search_city_fr(name)
        if not cities:
            print("  Aucune ville trouvée, réessaye.")
            continue
        for i, c in enumerate(cities, 1):
            print(f"  {i}. {c['label']}")
        print("  0. Autre recherche")
        try:
            choice = int(input("Choix : ").strip())
        except (ValueError, EOFError, KeyboardInterrupt):
            return default_ville
        if choice == 0:
            continue
        if 1 <= choice <= len(cities):
            return cities[choice - 1]
        print("  Numéro invalide.")


def _prompt_km(default_km: int) -> int:
    try:
        val = input(f"Distance max en km (1-300) [{default_km}] : ").strip()
        km = int(val) if val else default_km
        return max(1, min(300, km))
    except (ValueError, EOFError, KeyboardInterrupt):
        return default_km


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
                   help="Never prompt interactively (use config values as-is)")
    p.add_argument("--city", default=None, metavar="NOM,CP",
                   help="Use this city label directly, e.g. 'BORDEAUX, 33000'")
    p.add_argument("--km", type=int, default=None, metavar="N",
                   help="Distance max in km (overrides config)")
    p.add_argument("--lat", type=float, default=None, metavar="LAT",
                   help="Latitude of the city (overrides config)")
    p.add_argument("--lng", type=float, default=None, metavar="LNG",
                   help="Longitude of the city (overrides config)")
    return p.parse_args()


def main():
    args = parse_args()

    # Load config
    if not os.path.exists(args.config):
        logger.error("Config file not found: %s", args.config)
        sys.exit(1)

    with open(args.config) as f:
        config = json.load(f)

    # ── Interactive prompts (city → km → dates) ──────────────────────────────
    def _ask_date(label: str, default: str) -> str:
        try:
            val = input(f"{label} [{default}] (format DD/MM/YY) : ").strip()
        except (EOFError, KeyboardInterrupt):
            return default
        if not val:
            return default
        # Normalize DD/MM/YYYY → DD/MM/YY
        parts = val.replace("-", "/").split("/")
        if len(parts) == 3 and len(parts[2]) == 4:
            parts[2] = parts[2][2:]
            val = "/".join(parts)
        return val

    do_scrape = not (args.html_only or args.enrich_only)

    # City
    if args.city:
        config["search"]["ville"]["label"] = args.city
        config["search"]["ville"]["value"] = args.city
        if args.lat is not None:
            config["search"]["ville"]["lat"] = args.lat
        if args.lng is not None:
            config["search"]["ville"]["lng"] = args.lng
    elif not args.no_prompt:
        ville = _prompt_city(config["search"]["ville"])
        config["search"]["ville"].update(ville)

    # KM
    if args.km:
        config["search"]["ville"]["distance_km"] = args.km
    elif not args.no_prompt:
        config["search"]["ville"]["distance_km"] = _prompt_km(
            config["search"]["ville"].get("distance_km", 100)
        )

    # Dates (only needed for actual scraping)
    if do_scrape:
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
        logger.info("Plage : %s → %s | Ville : %s %dkm",
                    config["search"]["date_start"], config["search"]["date_end"],
                    config["search"]["ville"]["label"],
                    config["search"]["ville"]["distance_km"])

    # ── Per-city file paths ───────────────────────────────────────────────────
    slug         = _city_slug(config["search"]["ville"])
    data_file    = os.path.join("data", f"tournaments_{slug}.json")
    history_file = os.path.join("data", f"history_{slug}.json")
    html_file    = os.path.join("data", f"tournaments_{slug}.html")
    html_dir     = "data"
    output_file  = config["notifications"]["output_file"]
    print_console = config["notifications"]["print_to_console"]
    logger.info("Fichiers ville : %s", slug)

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
        saved = load_json(data_file)
        tournaments = saved.get("tournaments", [])
        logger.info("Loaded %d tournaments from cache — running enrichment only.", len(tournaments))
        # Tournament pages are public — no cookies needed for enrichment.
        import requests as _req2
        enrich_session = _req2.Session()
        enrich_session.headers.update({
            "User-Agent": config["scraper"]["user_agent"],
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
        })
        enrich_all(
            tournaments, enrich_session,
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

    # ── Merge previously enriched data (format, detail_url) ──────────────────
    # Look in the city-slug file first, then fall back to legacy tournaments.json
    # so existing enriched data is reused after the rename.
    candidate_files = [data_file, "data/tournaments.json"]
    enriched_cache: dict = {}
    for cfile in candidate_files:
        if os.path.exists(cfile):
            prev = load_json(cfile)
            for t in prev.get("tournaments", []):
                if t.get("enriched"):
                    tid = t.get("originalId") or t.get("id")
                    if tid and tid not in enriched_cache:
                        enriched_cache[tid] = t["enriched"]
            if cfile != data_file:
                logger.info("Fallback: loaded enriched cache from legacy %s", cfile)
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
        # Tournament detail pages are public — use a fresh session without
        # cookies so enrichment never fails due to cookie expiry.
        import requests as _req2
        enrich_session = _req2.Session()
        enrich_session.headers.update({
            "User-Agent": config["scraper"]["user_agent"],
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
        })
        enrich_all(
            tournaments, enrich_session,
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
    saved_data   = load_json(data_file)
    fetched_at   = saved_data.get("fetched_at", "")
    stamp        = datetime.now().strftime("%Y%m%d_%Hh%M")

    # 1) Full report (fixed name → toujours le dernier)
    generate_html(tournaments, html_file, new_ids=new_ids, fetched_at=fetched_at)

    # 2) Full report horodaté
    all_stamped  = os.path.join(html_dir, f"tournois_{stamp}.html")
    generate_html(tournaments, all_stamped, new_ids=new_ids, fetched_at=fetched_at)
    logger.info("Rapport complet horodaté : %s", all_stamped)

    # 3) Rapport "nouveaux seulement" horodaté (seulement si nouveaux)
    if new_tournaments:
        new_stamped = os.path.join(html_dir, f"nouveaux_{stamp}.html")
        all_new_ids = {t.get("originalId") or t.get("id", "") for t in new_tournaments}
        generate_html(
            new_tournaments, new_stamped,
            new_ids=all_new_ids, fetched_at=fetched_at,
            title="Nouveaux Tournois TenUp",
        )
        logger.info("Rapport nouveaux horodaté  : %s (%d tournois)", new_stamped, len(new_tournaments))


if __name__ == "__main__":
    main()
