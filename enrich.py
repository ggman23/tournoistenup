"""
Fetches individual tournament detail pages to extract additional info:
- Format (1-7, determines point coefficient)
"""

import logging
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://tenup.fft.fr"
TOURNAMENT_URL_PATTERN = BASE_URL + "/tournoi/{id}"


def get_tournament_url(tournament: dict) -> str:
    tid = tournament.get("id", "")
    return TOURNAMENT_URL_PATTERN.format(id=tid)


def _extract_format(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract the format number (1-7) from a tournament detail page.

    Tenup uses <div class="epreuve-detail-format"> with text like:
        "Format : 4 - 2 sets à 6 jeux ; pt décisif ; 3ème set = SJD à 10 pts"

    A tournament can have multiple épreuves with different formats.
    We return the most common format found (or the first if all equal).
    """
    # Primary: dedicated CSS class used by tenup
    formats_found = []
    for el in soup.find_all(class_="epreuve-detail-format"):
        # Remove button/tooltip elements before extracting text
        for btn in el.find_all(['button', 'span']):
            btn.decompose()
        text = el.get_text(" ", strip=True)
        # Text: "Format : 4 - 2 sets à 6 jeux..." → capture number + description
        m = re.search(r'Format\s*:\s*([1-7])\s*[-–]?\s*(.*)', text, re.I)
        if m:
            num  = m.group(1)
            desc = m.group(2).strip().rstrip(".")
            formats_found.append((num, desc))

    if formats_found:
        # Return (number, description) for the most frequent format
        best = max(set(f[0] for f in formats_found), key=lambda x: sum(1 for f in formats_found if f[0] == x))
        desc = next((f[1] for f in formats_found if f[0] == best), "")
        return best, desc

    return None, ""


def enrich_tournament(
    tournament: dict,
    session: requests.Session,
    delay_s: float = 1.5,
) -> dict:
    url = get_tournament_url(tournament)
    enriched = {"detail_url": url}

    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        fmt, fmt_desc = _extract_format(soup)
        if fmt:
            enriched["format"] = fmt
            enriched["format_desc"] = fmt_desc
            logger.debug("Tournament %s → format %s (%s)", tournament.get("id"), fmt, fmt_desc)
        else:
            logger.debug("Tournament %s → format not found", tournament.get("id"))
    except Exception as e:
        logger.warning("Could not enrich tournament %s: %s", tournament.get("id"), e)

    time.sleep(delay_s)
    tournament["enriched"] = enriched
    return tournament


def enrich_all(
    tournaments: list[dict],
    session: requests.Session,
    delay_s: float = 1.5,
    max_enrich: int = 0,
) -> list[dict]:
    """
    Enrich tournaments with detail page data.
    max_enrich=0 means no limit.
    """
    to_enrich = [t for t in tournaments if "enriched" not in t]
    if max_enrich:
        to_enrich = to_enrich[:max_enrich]

    total = len(to_enrich)
    if total == 0:
        logger.info("All tournaments already enriched.")
        return tournaments

    logger.info("Enriching %d tournaments (delay=%.1fs → ~%dm)",
                total, delay_s, int(total * delay_s / 60))

    for i, t in enumerate(to_enrich, 1):
        logger.info("[%d/%d] %s", i, total, t.get("libelle", "?"))
        enrich_tournament(t, session, delay_s=delay_s)

    # Ensure every tournament has at least the URL set
    for t in tournaments:
        if "enriched" not in t:
            t["enriched"] = {"detail_url": get_tournament_url(t)}

    return tournaments
