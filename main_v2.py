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
import socket
import subprocess
import sys
import time
from datetime import datetime

import requests as _req

from scraper import TenupScraper
from storage import update_storage, load_json
from notify import notify
from generate_html import generate_html, generate_from_file  # default, remplacé si --generator v2/v3
from enrich import enrich_all, enrich_statut_all, fix_encoding_in_tournament
from enrich_geo import enrich_geo_all, reset_geo


COOKIE_SERVER_PORT = 5057


def _ensure_cookie_server(port: int = COOKIE_SERVER_PORT) -> bool:
    """Start cookie_server.py in background if not already listening on port."""
    try:
        with socket.create_connection(("localhost", port), timeout=1):
            logger.info("Serveur de cookies déjà actif (port %d).", port)
            return True
    except OSError:
        pass

    server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookie_server.py")
    if not os.path.exists(server_script):
        logger.warning("cookie_server.py introuvable (%s) — serveur non démarré.", server_script)
        return False

    logger.info("🚀 Démarrage automatique du serveur de cookies (port %d)...", port)
    try:
        kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([sys.executable, server_script], **kwargs)
    except Exception as exc:
        logger.warning("Impossible de démarrer cookie_server.py : %s", exc)
        return False

    for _ in range(10):
        time.sleep(0.5)
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                logger.info("✅ Serveur de cookies prêt.")
                return True
        except OSError:
            pass

    logger.warning("Serveur de cookies ne répond pas après 5s — continuez manuellement.")
    return False


def _generate_index(data_dir: str = "data") -> str:
    """Génère data/index.html listant tous les HTML de tournois (page d'accueil GitHub Pages)."""
    import glob
    files = sorted(glob.glob(os.path.join(data_dir, "tournaments_*.html")))
    items = []
    for f in files:
        name = os.path.basename(f)
        is_sm     = "_SM" in name
        is_mobile = "mobile" in name
        label = (name
                 .replace("tournaments_", "")
                 .replace("_100km", " · 100 km")
                 .replace("_300km", " · 300 km")
                 .replace("_1100km", " · 1100 km")
                 .replace("_150km", " · 150 km")
                 .replace("_mobile_SM", "")
                 .replace("_mobile", "")
                 .replace("_SM", "")
                 .replace(".html", "")
                 .replace("_", " "))
        badges = []
        if is_sm:
            badges.append('<span style="background:#6f42c1;color:#fff;padding:1px 7px;border-radius:10px;font-size:.75em;margin-left:6px">SM 11-14</span>')
        if is_mobile:
            badges.append('<span style="background:#0dcaf0;color:#000;padding:1px 7px;border-radius:10px;font-size:.75em;margin-left:4px">📱 mobile</span>')
        items.append(
            f'<li style="margin:.5em 0"><a href="{name}" style="color:#0d6efd;text-decoration:none">'
            f'{label}</a>{"".join(badges)}</li>'
        )
    stamp = datetime.now().strftime("%d/%m/%Y à %H:%M")
    content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tournois TenUp</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:680px;margin:2rem auto;padding:0 1.2rem;color:#212529}}
h1{{font-size:1.5rem;margin-bottom:.2rem}}
.ts{{color:#6c757d;font-size:.85rem;margin-bottom:1.8rem}}
ul{{padding-left:1.3rem;list-style:disc}}
a:hover{{text-decoration:underline!important}}
</style>
</head>
<body>
<h1>🎾 Tournois TenUp</h1>
<div class="ts">Mis à jour : {stamp}</div>
<ul>
{"".join(items)}
</ul>
</body>
</html>"""
    idx = os.path.join(data_dir, "index.html")
    os.makedirs(data_dir, exist_ok=True)
    with open(idx, "w", encoding="utf-8") as f:
        f.write(content)
    return idx


def _auto_push_html(html_file: str):
    """Commit et push le fichier HTML vers GitHub (sauvegarde cloud). Non bloquant."""
    import subprocess
    stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        # Régénérer l'index GitHub Pages et l'inclure dans le même commit
        data_dir = os.path.dirname(os.path.abspath(html_file))
        idx_file = _generate_index(data_dir)
        # Force-add même si data/ est dans .gitignore
        r = subprocess.run(["git", "add", "-f", html_file, idx_file],
                           capture_output=True, text=True)
        if r.returncode != 0:
            logger.warning("git add HTML échoué : %s", r.stderr.strip())
            return
        r = subprocess.run(["git", "commit", "-m", f"auto: rapport HTML — {stamp}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            combined = r.stdout + r.stderr
            if any(s in combined for s in ("nothing to commit", "rien à valider", "nothing added to commit")):
                logger.info("HTML inchangé — pas de commit git.")
            else:
                logger.warning("git commit HTML échoué : %s", (r.stderr or r.stdout).strip())
            return
        # Synchronise avec le remote avant de pousser (la branche peut avoir avancé)
        r = subprocess.run(["git", "pull", "--rebase"], capture_output=True, text=True)
        if r.returncode != 0:
            logger.warning("git pull --rebase échoué, push annulé : %s", r.stderr.strip())
            return
        r = subprocess.run(["git", "push"], capture_output=True, text=True)
        if r.returncode != 0:
            logger.warning("git push HTML échoué : %s", r.stderr.strip())
            # Annule le commit local pour ne pas l'accumuler au prochain run
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True).stdout.strip()
            subprocess.run(["git", "reset", "--hard", f"origin/{branch}"],
                           capture_output=True, text=True)
        else:
            logger.info("✅ HTML sauvegardé sur GitHub : %s", html_file)
    except Exception as e:
        logger.warning("Auto-push HTML non critique : %s", e)

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
        val = input(f"Distance max en km [{default_km}] : ").strip()
        km = int(val) if val else default_km
        return max(1, km)
    except (ValueError, EOFError, KeyboardInterrupt):
        return default_km


def _prompt_rue(default_rue: str, ville_label: str) -> str:
    hint = default_rue if default_rue else f"centre de {ville_label}"
    try:
        val = input(f"Rue de départ [{hint}] : ").strip()
        return val if val else hint
    except (EOFError, KeyboardInterrupt):
        return default_rue


def _gen_mobile(tournaments_or_file, out_path, from_file=False, **kwargs):
    """Generate mobile HTML if generator supports it; silently skips otherwise."""
    if generate_html_mobile is None:
        return
    try:
        if from_file:
            generate_mobile_from_file(tournaments_or_file, out_path, **kwargs)
        else:
            generate_html_mobile(tournaments_or_file, out_path, **kwargs)
        _auto_push_html(out_path)
    except Exception as e:
        logger.warning("Génération HTML mobile échouée : %s", e)


def _setup_logging():
    os.makedirs("logs", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%Hh%M%S")
    log_file = os.path.join("logs", f"tenup_{stamp}.log")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    return log_file

_log_file = _setup_logging()
logger = logging.getLogger(__name__)
logger.info("Log écrit dans : %s", _log_file)


def _make_save_callback(saved: dict, tournaments: list, data_file: str):
    """Retourne une fonction qui sauvegarde le JSON en cours d'enrichissement."""
    import json as _json
    def _save():
        saved["tournaments"] = tournaments
        os.makedirs(os.path.dirname(data_file) or ".", exist_ok=True)
        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(saved, f, ensure_ascii=False, indent=2)
    return _save


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
    p.add_argument("--force-pages", type=int, default=0, metavar="N",
                   help="Force scraping exactly N pages, ignoring duplicate-stop logic. "
                        "Use for large radii (ex: 1100km France entière) où TenUp cycle les résultats.")
    p.add_argument("--date-start", default=None, metavar="DD/MM/YY",
                   help="Start date for search (overrides config). Format: 01/04/26")
    p.add_argument("--date-end", default=None, metavar="DD/MM/YY",
                   help="End date for search (overrides config). Format: 01/09/26")
    p.add_argument("--no-prompt", action="store_true",
                   help="Never prompt interactively (use config values as-is)")
    p.add_argument("--city", default=None, metavar="NOM,CP",
                   help="Use this city label directly, e.g. 'BORDEAUX, 33000'")
    p.add_argument("--km", type=int, default=None, metavar="N",
                   help="Distance max in km (overrides config, sans prompt)")
    p.add_argument("--km-default", type=int, default=None, metavar="N",
                   help="Rayon suggéré dans le prompt km sans le forcer (ex: 100 pour enrichissement local)")
    p.add_argument("--lat", type=float, default=None, metavar="LAT",
                   help="Latitude of the city (overrides config)")
    p.add_argument("--lng", type=float, default=None, metavar="LNG",
                   help="Longitude of the city (overrides config)")
    p.add_argument("--enrich-geo", action="store_true",
                   help="Geocode installations + compute road distances from ref city (no cookies needed)")
    p.add_argument("--enrich-geo-only", action="store_true",
                   help="Only run geo enrichment on existing data, then regenerate HTML")
    p.add_argument("--reset-geo", action="store_true",
                   help="Reset all geo data (geo_lat/lng, road_km/min) before --enrich-geo-only")
    p.add_argument("--enrich-statut-only", action="store_true",
                   help="Refresh inscription status only (no scraping, no format re-fetch)")
    p.add_argument("--fix-encoding", action="store_true",
                   help="Fix corrupted UTF-8 strings in existing JSON data, then regenerate HTML")
    p.add_argument("--refresh", action="store_true",
                   help="Tout-en-un : fix-encoding + enrich-only (retries) + enrich-statut-only")
    p.add_argument("--generator", default="v1", choices=["v1", "v2", "v3", "v4", "v5", "v6"],
                   help="HTML generator version (default: v1)")
    return p.parse_args()


def main():
    args = parse_args()

    # Démarrer le serveur de cookies si --cookies est passé et que le serveur n'est pas actif
    if args.cookies:
        _ensure_cookie_server()

    # Sélection du générateur HTML
    global generate_html, generate_from_file, generate_html_mobile, generate_mobile_from_file
    generate_html_mobile = None
    generate_mobile_from_file = None
    if args.generator == "v2":
        from generate_html_v2 import generate_html, generate_from_file
    elif args.generator == "v3":
        from generate_html_v3 import generate_html, generate_from_file
        from generate_html_v3 import generate_html_mobile, generate_mobile_from_file
    elif args.generator == "v4":
        from generate_html_v4 import generate_html, generate_from_file
    elif args.generator == "v5":
        from generate_html_v5 import generate_html, generate_from_file
    elif args.generator == "v6":
        from generate_html_v6 import generate_html, generate_from_file

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

    do_scrape = not (args.html_only or args.enrich_only or args.enrich_geo_only
                     or args.enrich_statut_only or args.fix_encoding or args.refresh)

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
        default_km = args.km_default if args.km_default else config["search"]["ville"].get("distance_km", 100)
        config["search"]["ville"]["distance_km"] = _prompt_km(default_km)

    # Rue de départ (pour itinéraire Google Maps précis)
    if not args.no_prompt:
        default_rue = config["search"]["ville"].get("rue", "")
        new_rue = _prompt_rue(default_rue, config["search"]["ville"].get("label", ""))
        config["search"]["ville"]["rue"] = new_rue
        # Persist the rue in config.json so future runs use it as default
        if new_rue and new_rue != default_rue:
            try:
                with open(args.config, "w", encoding="utf-8") as _cf:
                    json.dump(config, _cf, ensure_ascii=False, indent=2)
            except OSError:
                pass

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
    html_file_sm        = os.path.join("data", f"tournaments_{slug}_SM.html")
    html_file_mobile    = os.path.join("data", f"tournaments_{slug}_mobile.html")
    html_file_mobile_sm = os.path.join("data", f"tournaments_{slug}_mobile_SM.html")
    html_dir     = "data"
    output_file  = config["notifications"]["output_file"]
    print_console = config["notifications"]["print_to_console"]
    logger.info("Fichiers ville : %s", slug)

    # ── Fix-encoding mode: repair corrupted UTF-8 in existing JSON ──────────
    if args.fix_encoding:
        if not os.path.exists(data_file):
            logger.error("No data file found at %s — run a full scrape first.", data_file)
            sys.exit(1)
        saved = load_json(data_file)
        tournaments = saved.get("tournaments", [])
        fixed_count = sum(1 for t in tournaments if fix_encoding_in_tournament(t))
        logger.info("Fixed encoding in %d / %d tournament(s).", fixed_count, len(tournaments))
        import json as _json
        saved["tournaments"] = tournaments
        os.makedirs(os.path.dirname(data_file) or ".", exist_ok=True)
        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(saved, f, ensure_ascii=False, indent=2)
        new_ids = set()  # fix-encoding: no new tournament detection
        only_natures = config["search"].get("epreuves") or None
        _fe_rue  = config["search"]["ville"].get("rue", "")
        _fe_city = config["search"]["ville"].get("label", "")
        _fe_addr = (_fe_rue if _fe_city.lower() in _fe_rue.lower() else f"{_fe_rue}, {_fe_city}") if _fe_rue else ""
        _kw = dict(new_ids=new_ids, fetched_at=saved.get("fetched_at", ""),
                   only_natures=only_natures,
                   ref_lat=config["search"]["ville"].get("lat", 0.0),
                   ref_lng=config["search"]["ville"].get("lng", 0.0),
                   ref_city=_fe_city,
                   ref_address=_fe_addr)
        generate_html(tournaments, html_file, **_kw)
        _auto_push_html(html_file)
        generate_html(tournaments, html_file_sm, **_kw, sm_only=True)
        _auto_push_html(html_file_sm)
        sys.exit(0)

    # ── Refresh mode : fix-encoding + enrich (retries) + statuts en une passe ─
    if args.refresh:
        if not os.path.exists(data_file):
            logger.error("No data file found at %s — run a full scrape first.", data_file)
            sys.exit(1)
        import json as _json, datetime as _dt
        saved       = load_json(data_file)
        tournaments = saved.get("tournaments", [])
        cookies_file = args.cookies or os.environ.get("TENUP_COOKIES_FILE")
        only_natures = config["search"].get("epreuves") or None

        # 1) Fix encodage des textes corrompus
        fixed_count = sum(1 for t in tournaments if fix_encoding_in_tournament(t))
        logger.info("[refresh] Encodage corrigé : %d / %d tournois", fixed_count, len(tournaments))

        # 2) Ré-enrichissement (formats manquants + retries de contenu)
        enrich_scraper = TenupScraper(config, cookies_file=cookies_file)
        enrich_all(
            tournaments, enrich_scraper.session,
            delay_s=1.5, max_enrich=args.enrich_max,
            cookies_file=cookies_file,
            save_callback=_make_save_callback(saved, tournaments, data_file),
        )

        # 3) Rafraîchissement des statuts d'inscription + commentaires (cookies requis)
        if cookies_file:
            enrich_statut_all(tournaments, enrich_scraper.session,
                              delay_s=1.5, cookies_file=cookies_file)

        # Sauvegarde
        saved["tournaments"] = tournaments
        saved["fetched_at"]  = saved.get("fetched_at", _dt.datetime.utcnow().isoformat())
        os.makedirs(os.path.dirname(data_file) or ".", exist_ok=True)
        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(saved, f, ensure_ascii=False, indent=2)

        history = load_json(history_file)
        new_ids = set()   # pas de détection de nouveaux tournois en mode refresh
        _ref_rue_r  = config["search"]["ville"].get("rue", "")
        _ref_city_r = config["search"]["ville"].get("label", "")
        _ref_addr_r = (_ref_rue_r if _ref_city_r.lower() in _ref_rue_r.lower() else f"{_ref_rue_r}, {_ref_city_r}") if _ref_rue_r else ""
        _kw = dict(new_ids=new_ids, fetched_at=saved.get("fetched_at", ""),
                   only_natures=only_natures,
                   ref_lat=config["search"]["ville"].get("lat", 0.0),
                   ref_lng=config["search"]["ville"].get("lng", 0.0),
                   ref_city=_ref_city_r,
                   ref_address=_ref_addr_r)
        generate_html(tournaments, html_file, **_kw)
        _auto_push_html(html_file)
        generate_html(tournaments, html_file_sm, **_kw, sm_only=True)
        _auto_push_html(html_file_sm)
        _gen_mobile(tournaments, html_file_mobile, **_kw)
        _gen_mobile(tournaments, html_file_mobile_sm, sm_only=True, **_kw)
        sys.exit(0)

    # ── HTML-only mode: just regenerate the report ──────────────────────────
    if args.html_only:
        if not os.path.exists(data_file):
            logger.error("No data file found at %s — run without --html-only first.", data_file)
            sys.exit(1)
        # Restore NEW badges from the last real scraping run
        _hist     = load_json(history_file)
        _new_ids  = set(_hist.get("last_new_ids", []))
        _only_nat = config["search"].get("epreuves") or None
        # Update ref_address in JSON with the rue entered at prompt
        _rue_now = config["search"]["ville"].get("rue", "")
        _ref_addr = f"{_rue_now}, {config['search']['ville'].get('label','')}" if _rue_now else ""
        import json as _json_ho
        _data_ho = load_json(data_file)
        _data_ho["ref_address"] = _ref_addr
        with open(data_file, "w", encoding="utf-8") as _fho:
            _json_ho.dump(_data_ho, _fho, ensure_ascii=False, indent=2)
        generate_from_file(data_file, html_file, new_ids=_new_ids, only_natures=_only_nat)
        _auto_push_html(html_file)
        generate_from_file(data_file, html_file_sm, new_ids=_new_ids, sm_only=True)
        _auto_push_html(html_file_sm)
        _gen_mobile(data_file, html_file_mobile, from_file=True, new_ids=_new_ids)
        _gen_mobile(data_file, html_file_mobile_sm, from_file=True, new_ids=_new_ids, sm_only=True)
        sys.exit(0)

    # ── Enrich-only mode: re-enrich + regenerate without re-scraping ─────────
    if args.enrich_only:
        if not os.path.exists(data_file):
            logger.error("No data file found at %s — run a full scrape first.", data_file)
            sys.exit(1)
        saved = load_json(data_file)
        tournaments = saved.get("tournaments", [])
        logger.info("Loaded %d tournaments from cache — running enrichment only.", len(tournaments))
        # Enrichment needs the queue-it bypass cookie — TenUp serves different
        # HTML (without epreuve-detail-format divs) to unauthenticated sessions.
        cookies_file = args.cookies or os.environ.get("TENUP_COOKIES_FILE")
        enrich_scraper = TenupScraper(config, cookies_file=cookies_file)
        enrich_all(
            tournaments, enrich_scraper.session,
            delay_s=1.5, max_enrich=args.enrich_max,
            cookies_file=cookies_file,
            save_callback=_make_save_callback(saved, tournaments, data_file),
        )
        # Save updated data
        import json as _json, datetime as _dt
        saved["tournaments"] = tournaments
        saved["fetched_at"] = saved.get("fetched_at", _dt.datetime.utcnow().isoformat())
        os.makedirs(os.path.dirname(data_file) or ".", exist_ok=True)
        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(saved, f, ensure_ascii=False, indent=2)
        new_ids = set()  # enrich-only: no new tournament detection
        _kw = dict(new_ids=new_ids, fetched_at=saved.get("fetched_at", ""),
                   ref_lat=config["search"]["ville"].get("lat", 0.0),
                   ref_lng=config["search"]["ville"].get("lng", 0.0),
                   ref_city=config["search"]["ville"].get("label", ""))
        generate_html(tournaments, html_file, **_kw)
        _auto_push_html(html_file)
        generate_html(tournaments, html_file_sm, **_kw, sm_only=True)
        _auto_push_html(html_file_sm)
        _gen_mobile(tournaments, html_file_mobile, **_kw)
        _gen_mobile(tournaments, html_file_mobile_sm, sm_only=True, **_kw)
        sys.exit(0)

    # ── Enrich-statut-only mode: refresh inscription status only ─────────────
    if args.enrich_statut_only:
        if not os.path.exists(data_file):
            logger.error("No data file found at %s — run a full scrape first.", data_file)
            sys.exit(1)
        saved = load_json(data_file)
        tournaments = saved.get("tournaments", [])
        logger.info("Loaded %d tournaments — refreshing inscription status.", len(tournaments))
        cookies_file = args.cookies or os.environ.get("TENUP_COOKIES_FILE")
        enrich_scraper = TenupScraper(config, cookies_file=cookies_file)
        enrich_statut_all(tournaments, enrich_scraper.session, delay_s=1.5,
                          cookies_file=cookies_file, min_age_hours=0)
        import json as _json
        saved["tournaments"] = tournaments
        os.makedirs(os.path.dirname(data_file) or ".", exist_ok=True)
        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(saved, f, ensure_ascii=False, indent=2)
        new_ids      = set()  # statut-only: no new tournament detection, don't show stale NEW badges
        only_natures = config["search"].get("epreuves") or None
        _kw = dict(new_ids=new_ids, fetched_at=saved.get("fetched_at", ""),
                   only_natures=only_natures,
                   ref_lat=config["search"]["ville"].get("lat", 0.0),
                   ref_lng=config["search"]["ville"].get("lng", 0.0),
                   ref_city=config["search"]["ville"].get("label", ""))
        generate_html(tournaments, html_file, **_kw)
        _auto_push_html(html_file)
        generate_html(tournaments, html_file_sm, **_kw, sm_only=True)
        _auto_push_html(html_file_sm)
        _gen_mobile(tournaments, html_file_mobile, **_kw)
        _gen_mobile(tournaments, html_file_mobile_sm, sm_only=True, **_kw)
        sys.exit(0)

    # ── Enrich-geo-only mode: geocode + road distances without re-scraping ───
    if args.enrich_geo_only:
        if not os.path.exists(data_file):
            logger.error("No data file found at %s — run a full scrape first.", data_file)
            sys.exit(1)
        saved = load_json(data_file)
        tournaments = saved.get("tournaments", [])
        logger.info("Loaded %d tournaments — running geo enrichment only.", len(tournaments))
        if args.reset_geo:
            reset_geo(tournaments)
        ref_lat = config["search"]["ville"].get("lat", 0.0)
        ref_lng = config["search"]["ville"].get("lng", 0.0)
        enrich_geo_all(tournaments, ref_lat, ref_lng)
        import json as _json
        saved["tournaments"] = tournaments
        os.makedirs(os.path.dirname(data_file) or ".", exist_ok=True)
        with open(data_file, "w", encoding="utf-8") as f:
            _json.dump(saved, f, ensure_ascii=False, indent=2)
        new_ids = set()  # enrich-geo-only: no new tournament detection
        only_natures = config["search"].get("epreuves") or None
        _kw = dict(new_ids=new_ids, fetched_at=saved.get("fetched_at", ""),
                   only_natures=only_natures, ref_lat=ref_lat, ref_lng=ref_lng,
                   ref_city=config["search"]["ville"].get("label", ""))
        generate_html(tournaments, html_file, **_kw)
        _auto_push_html(html_file)
        generate_html(tournaments, html_file_sm, **_kw, sm_only=True)
        _auto_push_html(html_file_sm)
        _gen_mobile(tournaments, html_file_mobile, **_kw)
        _gen_mobile(tournaments, html_file_mobile_sm, sm_only=True, **_kw)
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
        tournaments = scraper.fetch_all(max_pages=args.pages_max, force_pages=args.force_pages)
    except Exception as e:
        logger.error("Scraping failed: %s", e)
        sys.exit(1)

    if not tournaments:
        logger.warning("No tournaments returned. Check your search criteria or cookies.")
        sys.exit(0)

    # Tag each tournament with the reference city used for this search
    ref_city = config["search"]["ville"]["label"]
    for t in tournaments:
        t["_ref_city"] = ref_city

    # ── Merge previously enriched data (format, detail_url) ──────────────────
    # Look in the city-slug file first, then all same-city files with different
    # km radius (so changing 300km→1100km reuses existing enriched data),
    # then fall back to legacy tournaments.json.
    # Cache global : on récupère les enrichissements de TOUS les fichiers JSON
    # (pas seulement même ville), car les formats ne changent jamais.
    # Ainsi, enrichir Marseille 100km réutilise ce qui a déjà été enrichi
    # pour Vaires 100km ou toute autre ville, sans refaire les requêtes.
    import glob as _glob
    all_files = sorted(_glob.glob(os.path.join("data", "tournaments_*.json")))
    candidate_files = [data_file] + [f for f in all_files if f != data_file] + ["data/tournaments.json"]
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
    saved = {}  # will be populated by _make_save_callback intermediate saves
    if args.enrich:
        # Enrichment needs the queue-it bypass cookie — TenUp serves different
        # HTML (without epreuve-detail-format divs) to unauthenticated sessions.
        enrich_all(
            tournaments, scraper.session,
            delay_s=1.5, max_enrich=args.enrich_max,
            cookies_file=cookies_file,
            save_callback=_make_save_callback(saved, tournaments, data_file),
        )
        # Refresh inscription statuses (separate pass to avoid overloading TenUp)
        if cookies_file:
            enrich_statut_all(tournaments, scraper.session, delay_s=2.0, cookies_file=cookies_file)

    # ── Geo enrichment (road distance + travel time) ─────────────────────────
    if args.enrich_geo or args.enrich_geo_only:
        ref_lat = config["search"]["ville"].get("lat", 0.0)
        ref_lng = config["search"]["ville"].get("lng", 0.0)
        enrich_geo_all(tournaments, ref_lat, ref_lng)

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
    # Only display épreuve lines whose nature code is in the search config
    # e.g. ["SM"] — hides DD/DM/DX lines even if the tournament offers them
    only_natures = config["search"].get("epreuves") or None

    # Reference city for map view
    ref_lat  = config["search"]["ville"].get("lat", 0.0)
    ref_lng  = config["search"]["ville"].get("lng", 0.0)
    ref_city = config["search"]["ville"].get("label", "")
    ref_rue  = config["search"]["ville"].get("rue", "")
    if ref_rue:
        ref_address = ref_rue if ref_city.lower() in ref_rue.lower() else f"{ref_rue}, {ref_city}"
    else:
        ref_address = ""
    # Save ref coords + address in JSON so generate_from_file / --html-only can use them
    saved_data["ref_lat"]     = ref_lat
    saved_data["ref_lng"]     = ref_lng
    saved_data["ref_city"]    = ref_city
    saved_data["ref_address"] = ref_address
    import json as _json2
    with open(data_file, "w", encoding="utf-8") as _f:
        _json2.dump(saved_data, _f, ensure_ascii=False, indent=2)

    _html_kwargs = dict(
        new_ids=new_ids, fetched_at=fetched_at, only_natures=only_natures,
        ref_lat=ref_lat, ref_lng=ref_lng, ref_city=ref_city, ref_address=ref_address,
    )

    # 1a) Full report (fixed name → toujours le dernier)
    generate_html(tournaments, html_file, **_html_kwargs)
    _auto_push_html(html_file)

    # 1b) Light SM-only report (fixed name)
    generate_html(tournaments, html_file_sm, **_html_kwargs, sm_only=True)
    logger.info("Rapport SM 11-14 : %s", html_file_sm)
    _auto_push_html(html_file_sm)

    # 1c) Mobile reports (fixed names)
    _gen_mobile(tournaments, html_file_mobile, **_html_kwargs)
    logger.info("Rapport mobile : %s", html_file_mobile)
    _gen_mobile(tournaments, html_file_mobile_sm, sm_only=True, **_html_kwargs)
    logger.info("Rapport mobile SM : %s", html_file_mobile_sm)

    # 2) Full report horodaté
    all_stamped  = os.path.join(html_dir, f"tournois_{stamp}.html")
    generate_html(tournaments, all_stamped, **_html_kwargs)
    logger.info("Rapport complet horodaté : %s", all_stamped)

    # 3) Rapport "nouveaux seulement" horodaté (seulement si nouveaux)
    if new_tournaments:
        new_stamped = os.path.join(html_dir, f"nouveaux_{stamp}.html")
        all_new_ids = {t.get("originalId") or t.get("id", "") for t in new_tournaments}
        generate_html(
            new_tournaments, new_stamped,
            title="Nouveaux Tournois TenUp",
            **_html_kwargs | dict(new_ids=all_new_ids),
        )
        logger.info("Rapport nouveaux horodaté  : %s (%d tournois)", new_stamped, len(new_tournaments))


if __name__ == "__main__":
    main()
