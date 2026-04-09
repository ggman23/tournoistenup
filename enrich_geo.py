"""
Geographic enrichment: geocode tournament installations and compute
road distances + travel time from a reference city.

APIs used (free, no API key required):
  - Geocoding : https://api-adresse.data.gouv.fr  (French government, batch CSV)
  - Routing   : http://router.project-osrm.org     (OSRM public demo, table endpoint)

Enriched fields added to t["enriched"]:
  geo_lat   : float   latitude of tournament installation
  geo_lng   : float   longitude of tournament installation
  road_km   : float   road distance in km from ref_city
  road_min  : int     travel time in minutes from ref_city
"""

import csv
import io
import logging
import time

import requests

logger = logging.getLogger(__name__)

GEOCODE_URL   = "https://api-adresse.data.gouv.fr/search/csv/"
OSRM_TABLE    = "http://router.project-osrm.org/table/v1/driving/{coords}"
OSRM_BATCH    = 90     # max destinations per OSRM request on public server
GEO_SCORE_MIN = 0.1    # min geocoding confidence — city-level geocoding (~0.4) is enough


# ── Step 1 : Batch geocoding ────────────────────────────────────────────────

def _batch_geocode(tournaments: list) -> int:
    """
    Geocode tournament installations using the French government address API.
    Sends all addresses in one CSV POST → returns lat/lng per tournament.
    Only processes tournaments that don't already have geo_lat/geo_lng.
    """
    to_geocode = [
        t for t in tournaments
        if not t.get("enriched", {}).get("geo_lat")
    ]
    if not to_geocode:
        logger.info("Géocodage : tous les tournois ont déjà des coordonnées.")
        return 0

    logger.info("Géocodage batch de %d installations...", len(to_geocode))

    # Build CSV: single 'adresse' column = "VILLE CP" (e.g. "US 95450")
    # Combining ville+cp in one field handles short/ambiguous city names far
    # better than using ville alone — "US 95450" is unambiguous, "US" alone is not.
    csv_rows = ["id,adresse"]
    for t in to_geocode:
        install = t.get("installation", {})
        ville   = install.get("ville", "").replace('"', "'").strip()
        cp      = install.get("codePostal", "").strip()
        q       = f"{ville} {cp}".strip().replace('"', "'")
        tid     = str(t.get("id", ""))
        csv_rows.append(f'{tid},"{q}"')

    csv_body = "\n".join(csv_rows)

    try:
        resp = requests.post(
            GEOCODE_URL,
            files={"data": ("addr.csv", csv_body.encode("utf-8"), "text/csv")},
            data=[("columns", "adresse")],
            timeout=120,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error("Géocodage batch échoué : %s", e)
        return 0

    # Validate response looks like CSV (not an HTML error page)
    if not resp.text.strip().startswith("id,"):
        logger.error("Réponse géocodage inattendue (pas du CSV) : %s", resp.text[:200])
        return 0

    # Build id → tournament map
    t_by_id = {str(t.get("id", "")): t for t in to_geocode}

    geocoded = 0
    try:
        reader = csv.DictReader(io.StringIO(resp.text))
        for row in reader:
            tid   = row.get("id", "").strip()
            lat   = row.get("latitude", "").strip()
            lng   = row.get("longitude", "").strip()
            score = float(row.get("result_score", 0) or 0)

            if not lat or not lng or score < GEO_SCORE_MIN:
                continue
            t = t_by_id.get(tid)
            if t is None:
                continue

            if "enriched" not in t:
                t["enriched"] = {}
            t["enriched"]["geo_lat"] = float(lat)
            t["enriched"]["geo_lng"] = float(lng)
            geocoded += 1
    except Exception as e:
        logger.error("Parsing réponse géocodage : %s", e)

    logger.info("Géocodage : %d/%d réussis", geocoded, len(to_geocode))
    return geocoded


# ── Step 2 : OSRM road distance + duration ──────────────────────────────────

def _batch_road_distances(tournaments: list, ref_lat: float, ref_lng: float) -> int:
    """
    Compute road distance (km) and travel time (min) from ref_city to each
    tournament using the OSRM table API.

    OSRM table sends all destinations in one request → very fast.
    Batched in groups of OSRM_BATCH to respect public server limits.
    Only processes tournaments that have geo_lat/geo_lng but no road_km yet.
    """
    to_route = [
        t for t in tournaments
        if t.get("enriched", {}).get("geo_lat")
        and t.get("enriched", {}).get("road_km") is None
    ]
    if not to_route:
        logger.info("Distances routières : tous les tournois sont déjà calculés.")
        return 0

    logger.info("Calcul distances routières (OSRM) pour %d tournois...", len(to_route))

    computed = 0
    total_batches = (len(to_route) + OSRM_BATCH - 1) // OSRM_BATCH

    for batch_idx in range(0, len(to_route), OSRM_BATCH):
        batch = to_route[batch_idx:batch_idx + OSRM_BATCH]
        bn    = batch_idx // OSRM_BATCH + 1
        logger.info("  Batch OSRM %d/%d (%d tournois)...", bn, total_batches, len(batch))

        # Coordinates: ref_city at index 0, then all tournaments
        coord_parts = [f"{ref_lng},{ref_lat}"]
        for t in batch:
            e = t["enriched"]
            coord_parts.append(f"{e['geo_lng']},{e['geo_lat']}")
        coords = ";".join(coord_parts)

        url = OSRM_TABLE.format(coords=coords)
        try:
            resp = requests.get(
                url,
                params={"sources": "0", "annotations": "duration,distance"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("  OSRM batch %d échoué : %s", bn, e)
            time.sleep(2)
            continue

        if data.get("code") != "Ok":
            logger.warning("  OSRM code inattendu : %s", data.get("code"))
            continue

        # durations[0] = row for source 0 (ref_city) → all destinations
        durations = (data.get("durations") or [[]])[0]
        distances = (data.get("distances") or [[]])[0]

        for j, t in enumerate(batch):
            idx = j + 1  # offset by 1 because index 0 = ref_city itself
            if idx >= len(durations):
                continue
            dur_s  = durations[idx]
            dist_m = distances[idx] if distances and idx < len(distances) else None

            if dur_s is None:
                # OSRM couldn't find a route (island, ferry required, etc.)
                t["enriched"]["road_km"]  = None
                t["enriched"]["road_min"] = None
                continue

            t["enriched"]["road_min"] = round(dur_s / 60)
            if dist_m is not None:
                t["enriched"]["road_km"] = round(dist_m / 1000, 1)
            computed += 1

        time.sleep(0.5)  # polite delay between batches on public server

    logger.info("Distances routières : %d/%d calculées", computed, len(to_route))
    return computed


# ── Public entry point ───────────────────────────────────────────────────────

def reset_geo(tournaments: list):
    """Remove geo_lat/geo_lng/road_km/road_min from all tournaments (force re-geocode)."""
    count = 0
    for t in tournaments:
        e = t.get("enriched", {})
        removed = False
        for key in ("geo_lat", "geo_lng", "road_km", "road_min"):
            if key in e:
                del e[key]
                removed = True
        if removed:
            count += 1
    logger.info("Reset géo : %d tournois remis à zéro", count)


def enrich_geo_all(tournaments: list, ref_lat: float, ref_lng: float):
    """
    Full geographic enrichment pipeline:
      1. Geocode all tournament installations (batch, skips already done)
      2. Compute road distances from ref_city (batch, skips already done)

    Results are stored directly in each tournament's enriched dict.
    Safe to call multiple times: already-computed values are skipped.
    """
    logger.info("=== Enrichissement géographique ===")
    geo_count  = _batch_geocode(tournaments)
    road_count = _batch_road_distances(tournaments, ref_lat, ref_lng)
    logger.info(
        "=== Géo terminé : %d géocodés, %d distances routières ===",
        geo_count, road_count
    )
