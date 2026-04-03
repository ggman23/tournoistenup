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

# Maps text on detail page → API nature code
_NATURE_TEXT_TO_CODE = {
    "simple messieurs": "SM",
    "simple dames":     "SD",
    "double messieurs": "DM",
    "double dames":     "DD",
    "double mixte":     "DX",
}

# Maps age-range pattern found in text → categorieAge.id from API
_AGE_PATTERN_TO_ID = [
    (r"\b9.?10\b",   110),
    (r"\b11.?12\b",  120),
    (r"\b12.?13\b",  125),
    (r"\b13.?14\b",  140),
    (r"\b14.?15\b",  145),
    (r"\b15.?16\b",  160),
    (r"\b17.?18\b",  180),
    (r"\bsenior|adulte\b", 200),
]


def get_tournament_url(tournament: dict) -> str:
    tid = tournament.get("id", "")
    return TOURNAMENT_URL_PATTERN.format(id=tid)


def _epreuve_key_from_text(text: str) -> Optional[str]:
    """Return 'NATURE_ageid' string if both nature and age are found in text."""
    lower = text.lower()
    nature_code = None
    for phrase, code in _NATURE_TEXT_TO_CODE.items():
        if phrase in lower:
            nature_code = code
            break
    if not nature_code:
        return None
    for pattern, age_id in _AGE_PATTERN_TO_ID:
        if re.search(pattern, lower):
            return f"{nature_code}_{age_id}"
    return None


def _extract_formats(soup: BeautifulSoup) -> tuple:
    """
    Extract format numbers from a tournament detail page.

    Returns:
        (best_num, best_desc, formats_list)
        - best_num   : most common format number as string, or None
        - best_desc  : description for best_num
        - formats_list: list of {"num": "5", "desc": "..."} in DOM order,
                        one entry per epreuve-detail-format div found.
          Optionally each entry has "epreuve_key" if the épreuve could be
          identified from surrounding text (e.g. "SM_120").
    """
    fmt_divs = soup.find_all(class_="epreuve-detail-format")
    formats_list = []

    for el in fmt_divs:
        # Work on a copy so decompose() doesn't mutate the original tree
        el_copy = BeautifulSoup(str(el), "lxml")
        for btn in el_copy.find_all(['button', 'span']):
            btn.decompose()
        text = el_copy.get_text(" ", strip=True)

        m = re.search(r'Format\s*:\s*([1-7])\s*[-–]?\s*(.*)', text, re.I)
        if not m:
            continue

        entry = {
            "num":  m.group(1),
            "desc": m.group(2).strip().rstrip("."),
        }

        # Walk up the DOM (max 8 levels) to find the épreuve identity.
        # Stop as soon as we find a node whose text contains BOTH a nature
        # phrase and an age range — that's the per-épreuve block.
        node = el.parent
        for _ in range(8):
            if node is None or node.name in ("html", "body", "[document]"):
                break
            node_text = node.get_text(" ", strip=True)
            key = _epreuve_key_from_text(node_text)
            if key:
                # Make sure this level isn't so high that it contains
                # more than one format div (which would mean we overshot).
                if len(node.find_all(class_="epreuve-detail-format")) == 1:
                    entry["epreuve_key"] = key
                    break
            node = node.parent

        formats_list.append(entry)

    if not formats_list:
        return None, "", []

    best = max(
        set(f["num"] for f in formats_list),
        key=lambda x: sum(1 for f in formats_list if f["num"] == x),
    )
    best_desc = next((f["desc"] for f in formats_list if f["num"] == best), "")
    return best, best_desc, formats_list


def enrich_tournament(
    tournament: dict,
    session: requests.Session,
    delay_s: float = 1.5,
) -> dict:
    url = get_tournament_url(tournament)
    enriched = {"detail_url": url}
    tid = tournament.get("id", "?")
    name = tournament.get("libelle", "?")

    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()

        # Detect auth redirect (page title contains "connexion" / "login")
        if any(kw in resp.text[:2000].lower() for kw in ["connexion", "se connecter", "login"]):
            logger.warning("[%s] %s → redirected to login page, cookies may be expired", tid, name)
            tournament["enriched"] = enriched
            return tournament

        soup = BeautifulSoup(resp.text, "lxml")

        # Count how many epreuve-detail-format divs exist
        fmt_divs = soup.find_all(class_="epreuve-detail-format")
        logger.info("[%s] %s → found %d epreuve-detail-format div(s)", tid, name, len(fmt_divs))

        fmt, fmt_desc, formats_list = _extract_formats(soup)
        if fmt:
            enriched["format"]       = fmt
            enriched["format_desc"]  = fmt_desc
            enriched["formats_list"] = formats_list
            keys = [f.get("epreuve_key", "?") for f in formats_list]
            logger.info("[%s] %s → formats %s (keys: %s)", tid, name,
                        [f["num"] for f in formats_list], keys)
        else:
            logger.warning("[%s] %s → format not found (page fetched OK)", tid, name)

    except Exception as e:
        logger.warning("[%s] %s → request failed: %s", tid, name, e)

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
    # Prioritize: never enriched first, then enriched-but-no-format
    without_any    = [t for t in tournaments if "enriched" not in t]
    without_format = [t for t in tournaments
                      if "enriched" in t and (
                          "format" not in t.get("enriched", {}) or
                          "formats_list" not in t.get("enriched", {})
                      )]
    to_enrich = without_any + without_format
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
