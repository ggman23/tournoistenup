"""
Fetches individual tournament detail pages to extract additional info:
- Format (1-7, determines point coefficient)
- Any other fields not in the search results
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
    """Build the detail URL for a tournament."""
    tid = tournament.get("id", "")
    return TOURNAMENT_URL_PATTERN.format(id=tid)


def _extract_format(soup: BeautifulSoup) -> Optional[str]:
    """
    Look for the format number (1-7) in the tournament detail page.
    Tenup displays it as 'Format X' near the tournament info block.
    """
    # Try various selectors / patterns
    text = soup.get_text(" ", strip=True)

    # Pattern: "Format 3" or "format : 3"
    m = re.search(r'[Ff]ormat\s*[:\-]?\s*([1-7])\b', text)
    if m:
        return m.group(1)

    # Try specific HTML elements
    for el in soup.find_all(class_=re.compile(r'format', re.I)):
        m = re.search(r'([1-7])', el.get_text())
        if m:
            return m.group(1)

    return None


def _extract_extra_fields(soup: BeautifulSoup) -> dict:
    """Extract any fields visible on the detail page but not in search results."""
    extra = {}

    fmt = _extract_format(soup)
    if fmt:
        extra["format"] = fmt

    return extra


def enrich_tournament(
    tournament: dict,
    session: requests.Session,
    delay_s: float = 1.5,
) -> dict:
    """
    Fetch the detail page for one tournament and add enriched fields.
    Returns the tournament dict with an 'enriched' sub-dict added.
    """
    url = get_tournament_url(tournament)
    enriched = {"detail_url": url}

    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        extra = _extract_extra_fields(soup)
        enriched.update(extra)
        logger.debug("Enriched %s: %s", tournament.get("id"), extra)
    except Exception as e:
        logger.warning("Could not enrich tournament %s: %s", tournament.get("id"), e)

    time.sleep(delay_s)
    tournament["enriched"] = enriched
    return tournament


def enrich_all(
    tournaments: list[dict],
    session: requests.Session,
    delay_s: float = 1.5,
) -> list[dict]:
    """Enrich all tournaments with detail page data."""
    total = len(tournaments)
    for i, t in enumerate(tournaments, 1):
        if "enriched" not in t:
            logger.info("Enriching %d/%d: %s", i, total, t.get("libelle", "?"))
            enrich_tournament(t, session, delay_s=delay_s)
        else:
            # Already enriched, just ensure URL is set
            t["enriched"].setdefault("detail_url", get_tournament_url(t))
    return tournaments
