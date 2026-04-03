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

    Tenup/Drupal displays it in a field-label / field-item pattern,
    typically labelled 'Format', 'Tableur' or 'Tableau'.
    We look for the label first, then grab the adjacent value.
    """
    # Strategy 1: label → sibling value (Drupal field pattern)
    label_patterns = [
        re.compile(r'\bformat\b', re.I),
        re.compile(r'\btableur\b', re.I),
        re.compile(r'\btableau\b', re.I),
    ]
    for label_el in soup.find_all(class_=re.compile(r'field.label', re.I)):
        text = label_el.get_text()
        if any(p.search(text) for p in label_patterns):
            # Value is in the next sibling element
            value_el = label_el.find_next_sibling()
            if value_el:
                m = re.search(r'\b([1-7])\b', value_el.get_text())
                if m:
                    return m.group(1)

    # Strategy 2: any element whose text is exactly "Format X" or "Tableur X"
    for el in soup.find_all(string=re.compile(
        r'^(format|tableur|tableau)\s*:?\s*[1-7]$', re.I
    )):
        m = re.search(r'([1-7])', el)
        if m:
            return m.group(1)

    # Strategy 3: look for "Format" label in <dt>/<th> and value in <dd>/<td>
    for dt in soup.find_all(['dt', 'th']):
        if any(p.search(dt.get_text()) for p in label_patterns):
            sibling = dt.find_next_sibling(['dd', 'td'])
            if sibling:
                m = re.search(r'\b([1-7])\b', sibling.get_text())
                if m:
                    return m.group(1)

    # Strategy 4: structured data in page — look for explicit "Format N" near
    # known tournament-info containers only (not in global page text)
    info_containers = soup.find_all(class_=re.compile(
        r'(tournoi|tournament|field|info|detail)', re.I
    ))
    for container in info_containers:
        text = container.get_text(" ")
        # Must have a label keyword right before the digit
        m = re.search(r'(?:format|tableur|tableau)\s*[:\-]?\s*([1-7])\b', text, re.I)
        if m:
            return m.group(1)

    return None


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
        fmt = _extract_format(soup)
        if fmt:
            enriched["format"] = fmt
            logger.debug("Tournament %s → format %s", tournament.get("id"), fmt)
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
