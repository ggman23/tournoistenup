#!/usr/bin/env python3
"""
Batch perso — 4 villes favorites.

Enchaîne pour chaque ville :
  scraping TenUp → enrichissement formats → distances routières → HTML v3

Usage:
    python run_batch_mes_villes.py --cookies cookies.json
    python run_batch_mes_villes.py --enrich-only --cookies cookies.json
    python run_batch_mes_villes.py --enrich-geo-only
    python run_batch_mes_villes.py --enrich-statut-only --cookies cookies.json
    python run_batch_mes_villes.py --html-only
    python run_batch_mes_villes.py --cookies cookies.json --no-enrich --no-geo  # scraping seul
"""

import argparse
import json
import logging
import subprocess
import sys
import urllib.parse
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Définition des 4 villes ──────────────────────────────────────────────────
#
# lat / lng : coordonnées de secours (utilisées si le géocodage automatique
#             échoue au démarrage). Le géocodage via geo.api.gouv.fr est tenté
#             en premier pour obtenir des coordonnées exactes.
#
CITIES = [
    {
        "label":      "VAIRES SUR MARNE, 77360",
        "lat":        48.873284,   # coordonnées vérifiées
        "lng":        2.638373,
        "km":         100,
        "date_start": "01/04/26",
        "date_end":   "31/12/26",
        "comment":    "Ville principale — Île-de-France",
    },
    {
        "label":      "MONCE EN BELIN, 72230",
        "lat":        47.879,      # approximatif — sera géocodé au démarrage
        "lng":        0.197,
        "km":         150,
        "date_start": "01/04/26",
        "date_end":   "31/12/26",
        "comment":    "Sarthe",
    },
    {
        "label":      "SAINT JEAN DE MONTS, 85160",
        "lat":        46.794,      # approximatif — sera géocodé au démarrage
        "lng":        -2.058,
        "km":         150,
        "date_start": "15/06/26",
        "date_end":   "31/08/26",
        "comment":    "Vendée — période estivale seulement",
    },
    {
        "label":      "MONCHY CAYEUX, 62134",
        "lat":        50.320,      # approximatif — sera géocodé au démarrage
        "lng":        2.350,
        "km":         150,
        "date_start": "01/04/26",
        "date_end":   "31/12/26",
        "comment":    "Pas-de-Calais",
    },
]


# ── Géocodage automatique ─────────────────────────────────────────────────────

def _geocode_city(label: str) -> tuple[float, float] | None:
    """
    Géocode une ville via geo.api.gouv.fr.
    Paramètre : label au format 'NOM COMMUNE, CODE_POSTAL'
    Retourne (lat, lng) ou None si échec.
    """
    parts = label.split(",", 1)
    nom = parts[0].strip()
    cp  = parts[1].strip() if len(parts) > 1 else ""
    url = (
        "https://geo.api.gouv.fr/communes"
        f"?nom={urllib.parse.quote(nom)}"
        f"&codePostal={cp}"
        "&fields=nom,centre&format=json&geometry=centre&limit=1"
    )
    try:
        with urllib.request.urlopen(url, timeout=6) as r:
            data = json.loads(r.read())
        if data:
            coords = data[0]["centre"]["coordinates"]
            return round(coords[1], 6), round(coords[0], 6)   # lat, lng
    except Exception as e:
        logger.debug("Géocodage impossible pour '%s' : %s", label, e)
    return None


def geocode_all_cities(cities: list[dict]) -> None:
    """
    Tente de géocoder chaque ville au démarrage.
    Met à jour lat/lng en place si le géocodage réussit.
    """
    logger.info("Géocodage des coordonnées via geo.api.gouv.fr…")
    for city in cities:
        result = _geocode_city(city["label"])
        if result:
            old_lat, old_lng = city["lat"], city["lng"]
            city["lat"], city["lng"] = result
            if abs(city["lat"] - old_lat) > 0.05 or abs(city["lng"] - old_lng) > 0.05:
                logger.info(
                    "  %-40s → lat=%.6f  lng=%.6f  (corrigé depuis approximatif)",
                    city["label"], city["lat"], city["lng"],
                )
            else:
                logger.info(
                    "  %-40s → lat=%.6f  lng=%.6f  ✓",
                    city["label"], city["lat"], city["lng"],
                )
        else:
            logger.warning(
                "  %-40s → géocodage échoué, coordonnées approx utilisées (lat=%.3f, lng=%.3f)",
                city["label"], city["lat"], city["lng"],
            )


# ── Exécution d'une ville ─────────────────────────────────────────────────────

def run_city(city: dict, args: argparse.Namespace) -> bool:
    """Lance main.py pour une ville. Retourne True si succès."""
    label   = city["label"]
    lat     = city["lat"]
    lng     = city["lng"]
    km      = city["km"]
    comment = city.get("comment", "")

    logger.info("")
    logger.info("=" * 62)
    logger.info("  VILLE  : %s  (%d km)", label, km)
    logger.info("  NOTE   : %s", comment)
    logger.info("  COORDS : lat=%.6f  lng=%.6f", lat, lng)
    logger.info("=" * 62)

    base = [
        sys.executable, "main.py",
        "--no-prompt",
        "--generator", "v3",
        "--city",  label,
        "--lat",   str(lat),
        "--lng",   str(lng),
        "--km",    str(km),
    ]

    if args.html_only:
        cmd = base + ["--html-only"]

    elif args.enrich_statut_only:
        cmd = base + ["--enrich-statut-only"]
        if args.cookies:
            cmd += ["--cookies", args.cookies]

    elif args.enrich_geo_only:
        cmd = base + ["--enrich-geo-only"]

    elif args.enrich_only:
        cmd = base + ["--enrich-only"]
        if args.cookies:
            cmd += ["--cookies", args.cookies]

    else:
        # Scraping complet
        cmd = base + [
            "--date-start", city["date_start"],
            "--date-end",   city["date_end"],
        ]
        if args.cookies:
            cmd += ["--cookies", args.cookies]
        if not args.no_enrich:
            cmd.append("--enrich")
        if not args.no_geo:
            cmd.append("--enrich-geo")

    logger.info("CMD : %s", " ".join(cmd))
    result = subprocess.run(cmd)
    ok = result.returncode == 0
    if not ok:
        logger.error("❌ ÉCHEC pour %s (exit code %d)", label, result.returncode)
    return ok


# ── Argument parser ───────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Batch mes 4 villes favorites — scraping + enrichissement + HTML v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :

  # Run complet (scraping + formats + distances) — usage principal, cookies obligatoires
  python run_batch_mes_villes.py --cookies cookies.json

  # Scraping seul, sans enrichissement (plus rapide, sans format F1-F7 ni distances)
  python run_batch_mes_villes.py --cookies cookies.json --no-enrich --no-geo

  # Re-enrichir uniquement les formats (cookies requis, scraping déjà fait)
  python run_batch_mes_villes.py --enrich-only --cookies cookies.json

  # Re-calculer uniquement les distances routières (pas de cookies)
  python run_batch_mes_villes.py --enrich-geo-only

  # Rafraîchir uniquement les statuts d'inscription (cookies requis)
  python run_batch_mes_villes.py --enrich-statut-only --cookies cookies.json

  # Régénérer uniquement les 4 HTMLs (aucun téléchargement)
  python run_batch_mes_villes.py --html-only
""",
    )
    p.add_argument(
        "--cookies", default=None,
        help="Fichier cookies JSON (nécessaire pour le scraping et l'enrichissement formats)",
    )
    p.add_argument(
        "--no-enrich", action="store_true",
        help="Ne pas enrichir les formats F1-F7 après le scraping",
    )
    p.add_argument(
        "--no-geo", action="store_true",
        help="Ne pas calculer les distances routières après le scraping",
    )
    p.add_argument(
        "--enrich-only", action="store_true",
        help="Uniquement enrichir les formats (pas de re-scraping) — cookies requis",
    )
    p.add_argument(
        "--enrich-geo-only", action="store_true",
        help="Uniquement calculer les distances routières — pas de cookies",
    )
    p.add_argument(
        "--enrich-statut-only", action="store_true",
        help="Uniquement rafraîchir les statuts d'inscription — cookies requis",
    )
    p.add_argument(
        "--html-only", action="store_true",
        help="Uniquement régénérer les 4 HTMLs — aucun téléchargement",
    )
    p.add_argument(
        "--skip", default="", metavar="INDICES",
        help="Ignorer certaines villes par indice (0-3), séparés par virgule. Ex: --skip 1,2",
    )
    return p.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Avertissement cookies
    if (not args.cookies
            and not args.html_only
            and not args.enrich_geo_only):
        logger.warning("⚠  Aucun --cookies fourni — le scraping sera bloqué par la salle d'attente queue-it.")
        logger.warning("   Lance d'abord : python cookie_server.py  (dans un autre terminal)")

    # Sélection des villes (--skip)
    cities = list(CITIES)
    if args.skip:
        skip_indices = set()
        for s in args.skip.split(","):
            s = s.strip()
            if s.isdigit():
                skip_indices.add(int(s))
        cities = [c for i, c in enumerate(CITIES) if i not in skip_indices]
        if len(cities) < len(CITIES):
            skipped = [CITIES[i]["label"] for i in skip_indices if i < len(CITIES)]
            logger.info("Villes ignorées (--skip) : %s", ", ".join(skipped))

    logger.info("")
    logger.info("=== Batch mes villes — %d ville(s) à traiter ===", len(cities))

    # Géocodage automatique des coordonnées
    geocode_all_cities(cities)

    successes: list[str] = []
    failures:  list[str] = []

    for i, city in enumerate(cities, 1):
        logger.info("[%d/%d] Démarrage : %s", i, len(cities), city["label"])
        ok = run_city(city, args)
        if ok:
            successes.append(city["label"])
        else:
            failures.append(city["label"])

    # Résumé
    logger.info("")
    logger.info("=" * 62)
    logger.info("  RÉSUMÉ BATCH")
    logger.info("=" * 62)
    logger.info("✅ Succès : %d/%d", len(successes), len(cities))
    for label in successes:
        logger.info("     ✓ %s", label)
    if failures:
        logger.warning("❌ Échecs : %d/%d", len(failures), len(cities))
        for label in failures:
            logger.warning("     ✗ %s", label)
        logger.warning("")
        logger.warning("Pour relancer uniquement les villes en échec, utilise --skip avec les indices des villes réussies.")
    else:
        logger.info("  Tous les HTMLs ont été générés avec succès.")
    logger.info("")

    # HTMLs générés
    logger.info("Fichiers HTML générés :")
    import re, os
    for city in cities:
        km    = city["km"]
        label = city["label"]
        slug  = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        html  = os.path.join("data", f"tournaments_{slug}_{km}km.html")
        exists = "✓" if os.path.exists(html) else "✗ absent"
        logger.info("  [%s] %s", exists, html)


if __name__ == "__main__":
    main()
