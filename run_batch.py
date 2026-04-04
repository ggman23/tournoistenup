#!/usr/bin/env python3
"""
Batch runner: scrapes all cities from cities_france.json, then generates
a combined France-wide HTML report.

Usage:
    python run_batch.py --cookies cookies.json
    python run_batch.py --cookies cookies.json --enrich
    python run_batch.py --cookies cookies.json --date-start 01/04/26 --date-end 01/09/26
    python run_batch.py --html-only          # regenerate all HTMLs without scraping
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CITIES_FILE = "cities_france.json"
DATA_DIR    = "data"


def load_cities() -> list[dict]:
    if not os.path.exists(CITIES_FILE):
        logger.error("Cities file not found: %s", CITIES_FILE)
        sys.exit(1)
    with open(CITIES_FILE) as f:
        return json.load(f)


def run_city(city: dict, args: argparse.Namespace) -> bool:
    """Run main.py for a single city. Returns True on success."""
    label = city["label"]
    lat   = city["lat"]
    lng   = city["lng"]
    km    = city.get("distance_km", 300)

    cmd = [
        sys.executable, "main.py",
        "--no-prompt",
        "--city", label,
        "--km", str(km),
        "--lat", str(lat),
        "--lng", str(lng),
    ]

    if args.enrich_only:
        # Enrich-only: no scraping, no cookies needed
        cmd.append("--enrich-only")
    else:
        if args.cookies:
            cmd += ["--cookies", args.cookies]
        if args.enrich:
            cmd.append("--enrich")
        if args.date_start:
            cmd += ["--date-start", args.date_start]
        if args.date_end:
            cmd += ["--date-end", args.date_end]
        if args.pages_max:
            cmd += ["--pages-max", str(args.pages_max)]
        if args.html_only:
            cmd.append("--html-only")

    logger.info("=== Ville: %s (%dkm) ===", label, km)
    logger.info("CMD: %s", " ".join(cmd))

    result = subprocess.run(cmd)
    if result.returncode != 0:
        logger.error("FAILED for %s (exit code %d)", label, result.returncode)
        return False
    return True


def merge_and_generate(args: argparse.Namespace):
    """Merge all city JSON files (deduplicated) → generate combined HTML."""
    import json as _json
    from storage import load_json
    from generate_html import generate_html

    # Read only_natures from config so the combined HTML respects the same filter
    only_natures = None
    if os.path.exists("config.json"):
        try:
            with open("config.json") as f:
                _cfg = _json.load(f)
            only_natures = _cfg.get("search", {}).get("epreuves") or None
        except Exception:
            pass

    logger.info("=== Génération rapport France entière ===")

    # Find all city data files
    json_files = [
        os.path.join(DATA_DIR, f)
        for f in os.listdir(DATA_DIR)
        if f.startswith("tournaments_") and f.endswith(".json")
        and not f.startswith("tournaments_france")
    ]

    if not json_files:
        logger.warning("Aucun fichier de données trouvé dans %s", DATA_DIR)
        return

    logger.info("Fichiers à fusionner: %d", len(json_files))

    all_tournaments: dict = {}   # id → tournament (keep nearest city)
    fetched_at = ""

    def _dist_km(t: dict) -> float:
        raw = t.get("distanceEnMetres", "0 km")
        try:
            return float(raw.replace(",", ".").replace(" km", "").replace("\xa0", "").strip() or 0)
        except ValueError:
            return 9999.0

    for jf in sorted(json_files):
        data = load_json(jf)
        if not isinstance(data, dict):
            continue
        if not fetched_at:
            fetched_at = data.get("fetched_at", "")
        for t in data.get("tournaments", []):
            tid = t.get("originalId") or t.get("id", "")
            if not tid:
                continue
            if tid not in all_tournaments:
                all_tournaments[tid] = t
            else:
                # Keep the entry with the shorter distance (= more relevant ref city)
                if _dist_km(t) < _dist_km(all_tournaments[tid]):
                    all_tournaments[tid] = t

    tournaments = list(all_tournaments.values())
    logger.info("Total unique tournaments France entière: %d", len(tournaments))

    stamp    = datetime.now().strftime("%Y%m%d_%Hh%M")
    out_file = os.path.join(DATA_DIR, "tournaments_france_entiere.html")
    out_stamped = os.path.join(DATA_DIR, f"france_entiere_{stamp}.html")

    generate_html(
        tournaments, out_file,
        new_ids=set(),
        title="Tournois TenUp — France entière",
        fetched_at=fetched_at,
        only_natures=only_natures,
    )
    logger.info("Rapport France entière : %s (%d tournois)", out_file, len(tournaments))

    generate_html(
        tournaments, out_stamped,
        new_ids=set(),
        title="Tournois TenUp — France entière",
        fetched_at=fetched_at,
        only_natures=only_natures,
    )
    logger.info("Rapport France entière horodaté : %s", out_stamped)


def parse_args():
    p = argparse.ArgumentParser(
        description="Batch scraper — toutes les villes de France",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Workflow recommandé (2 phases) :

  # Phase 1 — collecter les listes de tournois pour chaque ville (cookies requis, ~30-60 min)
  python run_batch.py --cookies cookies.json --date-start 01/04/26 --date-end 01/09/26

  # Phase 2 — enrichir (pages publiques, sans cookies, ~2h, peut s'interrompre/reprendre)
  python run_batch.py --enrich-only

  # Ou tout en une seule commande (cookies valables ~24h-7j)
  python run_batch.py --cookies cookies.json --enrich --date-start 01/04/26 --date-end 01/09/26
""",
    )
    p.add_argument("--cookies", default=None,
                   help="Path to cookies JSON file (required for scraping phase)")
    p.add_argument("--enrich", action="store_true",
                   help="Enrich each city's tournaments after scraping (no cookies needed)")
    p.add_argument("--enrich-only", action="store_true",
                   help="Only enrich existing city data files, no scraping (no cookies needed)")
    p.add_argument("--date-start", default=None, metavar="DD/MM/YY",
                   help="Start date (e.g. 01/04/26) — passed to main.py")
    p.add_argument("--date-end", default=None, metavar="DD/MM/YY",
                   help="End date (e.g. 01/09/26) — passed to main.py")
    p.add_argument("--pages-max", type=int, default=0, metavar="N",
                   help="Limit pages per city (for testing)")
    p.add_argument("--html-only", action="store_true",
                   help="Regenerate all city HTMLs + combined HTML without scraping")
    p.add_argument("--cities-file", default=CITIES_FILE,
                   help=f"JSON file listing cities (default: {CITIES_FILE})")
    p.add_argument("--no-combine", action="store_true",
                   help="Skip the France-wide combined HTML generation")
    p.add_argument("--city-filter", default=None, metavar="LABEL",
                   help="Only process cities whose label contains this string (case-insensitive)")
    return p.parse_args()


def main():
    args = parse_args()

    cities = load_cities()
    logger.info("Villes à traiter: %d", len(cities))

    if args.city_filter:
        pattern = args.city_filter.lower()
        cities = [c for c in cities if pattern in c["label"].lower()]
        logger.info("Filtre appliqué '%s' → %d ville(s)", args.city_filter, len(cities))
        if not cities:
            logger.error("Aucune ville ne correspond au filtre.")
            sys.exit(1)

    successes = 0
    failures  = []

    for i, city in enumerate(cities, 1):
        logger.info("[%d/%d] Traitement de %s...", i, len(cities), city["label"])
        ok = run_city(city, args)
        if ok:
            successes += 1
        else:
            failures.append(city["label"])

    logger.info("=== Résumé batch ===")
    logger.info("Succès: %d/%d", successes, len(cities))
    if failures:
        logger.warning("Échecs: %s", ", ".join(failures))

    if not args.no_combine:
        merge_and_generate(args)
    else:
        logger.info("Génération combinée ignorée (--no-combine).")


if __name__ == "__main__":
    main()
