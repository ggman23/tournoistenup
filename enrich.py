"""
Fetches individual tournament detail pages to extract additional info:
- Format (1-7, determines point coefficient)
- Statut d'inscription (ouvert, clôturé, bientôt, etc.)
"""

import logging
import os
import re
import time
from datetime import datetime, timezone
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
    (r"\b11\s*/?\s*12\b", 120),  # 11/12 ans (before single "11" or "12")
    (r"\b13\s*/?\s*14\b", 140),  # 13/14 ans
    (r"\b14\s*/?\s*15\b", 145),  # 14/15 → mapped to 14 ans
    (r"\b15\s*/?\s*16\b", 160),
    (r"\b17\s*/?\s*18\b", 180),
    (r"\b11\b",      110),       # 11 ans seul
    (r"\b12\b",      125),       # 12 ans seul
    (r"\b13\b",      130),       # 13 ans seul
    (r"\b14\b",      145),       # 14 ans seul
    (r"\bsenior|adulte\b", 200),
]


def _normalize_statut(text: str, is_closed: bool = False) -> str:
    """Normalize raw status text to a category code."""
    t = text.strip().lower()
    if not t:
        return "cloture" if is_closed else "ouvert"
    if "débutent" in t or "debutent" in t or "à partir" in t or "a partir" in t or "ouvrent" in t:
        return "bientot"
    if "liste d'attente" in t or "liste d attente" in t or "attente" in t:
        return "attente"
    if "clôtur" in t or "clotur" in t or "fermé" in t or "ferme" in t or "close" in t:
        return "cloture"
    if "classement" in t and ("bornes" in t or "compris" in t or "possédez" in t or "possedez" in t):
        return "hors_bornes"
    if ("pas possible" in t or "non disponible" in t) and ("en ligne" in t or "inscri" in t):
        return "impossible"
    if "déjà inscrit" in t or "deja inscrit" in t:
        return "deja_inscrit"
    if ("ne pouvez pas" in t or "ne peut pas" in t) and ("dame" in t or "messieu" in t or "genre" in t):
        return "ineligible"
    if "âge sportif" in t or "age sportif" in t or "ne vous permet pas" in t:
        return "ineligible"
    return "autre"


def _epreuve_key_from_detail(nature_code: str, titre: str) -> Optional[str]:
    """Build 'NATURE_ageid' key from nature code and épreuve title (e.g. 'SM_140')."""
    if not nature_code:
        return None
    lower = titre.lower()
    for pattern, age_id in _AGE_PATTERN_TO_ID:
        if re.search(pattern, lower):
            return f"{nature_code}_{age_id}"
    return None


def _extract_statut_inscription(soup: BeautifulSoup) -> dict:
    """
    Extract inscription status per épreuve from the detail page.

    Structure: div.epreuve-step-0 [class may include 'title-closed']
                 └── div.epreuve-detail
                       └── div.epreuve-titre-info-wrapper
                             ├── div.epreuve-detail-nature       → "SM"
                             ├── div.epreuve-detail-titre        → "Simple Messieurs 13/14 ans"
                             └── div.epreuve-detail-info         → status text (empty = ouvert)

    Returns:
        {
          "statuts": { "SM_140": {"statut": "bientot", "message": "...", "nature": "SM", "titre": "..."}, ... },
          "commentaire_club": "...",
        }
    """
    statuts = {}

    for block in soup.find_all(class_=re.compile(r"\bepreuve-step-0\b")):
        classes = block.get("class") or []
        is_closed = "title-closed" in classes

        nature_div = block.find(class_="epreuve-detail-nature")
        nature_code = nature_div.get_text(strip=True) if nature_div else ""

        titre_div = block.find(class_="epreuve-detail-titre")
        titre = titre_div.get_text(" ", strip=True) if titre_div else ""

        info_div = block.find(class_="epreuve-detail-info")
        info_text = info_div.get_text(" ", strip=True) if info_div else ""

        statut_code = _normalize_statut(info_text, is_closed=is_closed)

        entry = {
            "statut":  statut_code,
            "message": info_text,
            "nature":  nature_code,
            "titre":   titre,
        }

        ep_key = _epreuve_key_from_detail(nature_code, titre)
        key = ep_key if ep_key else (nature_code or f"ep_{len(statuts)}")
        statuts[key] = entry

    comment_div = soup.find(class_="tournoi-detail-page-comment-content")
    commentaire = comment_div.get_text(" ", strip=True) if comment_div else ""

    return {"statuts": statuts, "commentaire_club": commentaire}


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
        # Fallback: scan the full page text for any "Format : N" occurrence
        page_text = soup.get_text(" ", strip=True)
        m = re.search(r'Format\s*:\s*([1-7])\s*[-–]?\s*(.*?)(?:\s{2,}|$)', page_text, re.I)
        if m:
            logger.debug("Format extracted via page-text fallback")
            return m.group(1), m.group(2).strip().rstrip("."), [
                {"num": m.group(1), "desc": m.group(2).strip().rstrip(".")}
            ]
        return None, "", []

    best = max(
        set(f["num"] for f in formats_list),
        key=lambda x: sum(1 for f in formats_list if f["num"] == x),
    )
    best_desc = next((f["desc"] for f in formats_list if f["num"] == best), "")
    return best, best_desc, formats_list


def _reload_session_cookies(session: requests.Session, cookies_file: str) -> bool:
    """Reload cookies from file into session. Returns True if file was readable."""
    try:
        import json as _json
        with open(cookies_file, encoding="utf-8") as f:
            cookies = _json.load(f)
        session.cookies.clear()
        for c in cookies:
            session.cookies.set(c["name"], c["value"],
                                domain=c.get("domain", ".tenup.fft.fr"))
        logger.info("Cookies rechargés depuis %s (%d cookies)", cookies_file, len(cookies))
        return True
    except Exception as e:
        logger.warning("Impossible de recharger %s : %s", cookies_file, e)
        return False


def _is_queueit(resp: requests.Response) -> bool:
    """Return True if the response is a queue-it waiting room page."""
    return "queue-it.net" in resp.url or "enqueuetoken" in resp.text[:500]


def enrich_tournament(
    tournament: dict,
    session: requests.Session,
    delay_s: float = 1.5,
    max_retries: int = 3,
    cookies_file: Optional[str] = None,
) -> dict:
    url = get_tournament_url(tournament)
    enriched = {"detail_url": url}
    tid = tournament.get("id", "?")
    name = tournament.get("libelle", "?")

    wait_poll_s = 15
    wait_max_s  = 600

    # Retry loop for network errors + queue-it recovery
    resp = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("[%s] %s → attempt %d/%d failed: %s", tid, name, attempt, max_retries, e)
            if attempt == max_retries:
                enriched["fetch_failed"] = True
                time.sleep(delay_s)
                tournament["enriched"] = enriched
                return tournament
            time.sleep(min(2 ** attempt, 30))
            continue

        # Detect queue-it redirect (cookie expired)
        if _is_queueit(resp):
            if not cookies_file:
                logger.warning("[%s] %s → queue-it détecté, pas de cookies_file pour recharger", tid, name)
                enriched["fetch_failed"] = True
                tournament["enriched"] = enriched
                return tournament

            mtime_before = os.path.getmtime(cookies_file) if os.path.exists(cookies_file) else 0
            waited = 0
            logger.warning(
                "[%s] ⚠️  Queue-it détecté — cookie expiré. Attente de TamperMonkey... (max %ds)",
                tid, wait_max_s,
            )
            while waited < wait_max_s:
                time.sleep(wait_poll_s)
                waited += wait_poll_s
                mtime_after = os.path.getmtime(cookies_file) if os.path.exists(cookies_file) else 0
                if mtime_after > mtime_before:
                    logger.info("[%s] ✅  cookies.json mis à jour — rechargement...", tid)
                    _reload_session_cookies(session, cookies_file)
                    break
                logger.info("[%s] ⏳  cookies.json inchangé (%ds / %ds)...", tid, waited, wait_max_s)
            else:
                logger.error("[%s] Timeout — abandon après %ds", tid, wait_max_s)
                enriched["fetch_failed"] = True
                tournament["enriched"] = enriched
                return tournament
            continue  # retry with fresh cookies

        break  # good response, exit retry loop

    # Detect login redirect
    if any(kw in resp.text[:2000].lower() for kw in ["connexion", "se connecter", "login"]):
        logger.warning("[%s] %s → redirected to login page, cookies may be expired", tid, name)
        tournament["enriched"] = enriched
        return tournament

    soup = BeautifulSoup(resp.text, "lxml")

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
        enriched["no_format_in_html"] = True  # don't retry — likely JS-rendered

    # Extract inscription status
    statut_data = _extract_statut_inscription(soup)
    if statut_data["statuts"]:
        enriched["statuts_inscription"] = statut_data["statuts"]
        codes = [v["statut"] for v in statut_data["statuts"].values()]
        logger.info("[%s] %s → statuts: %s", tid, name, codes)
    else:
        logger.debug("[%s] %s → aucun bloc epreuve-step-0 trouvé", tid, name)
    if statut_data["commentaire_club"]:
        enriched["commentaire_club"] = statut_data["commentaire_club"]
    enriched["statut_fetched_at"] = datetime.now(timezone.utc).isoformat()

    time.sleep(delay_s)
    tournament["enriched"] = enriched
    return tournament


def enrich_all(
    tournaments: list[dict],
    session: requests.Session,
    delay_s: float = 1.5,
    max_enrich: int = 0,
    max_rounds: int = 3,
    cookies_file: Optional[str] = None,
) -> list[dict]:
    """
    Enrich tournaments with detail page data.

    Round 1: all unenriched + those without format.
    Rounds 2-N: only those that had a network failure (fetch_failed flag).
    max_enrich=0 means no limit (applied to round 1 only).
    max_rounds: how many retry passes for network failures (default 3).
    """
    def _needs_enrich(t):
        e = t.get("enriched", {})
        if "enriched" not in t:                return True   # never processed
        if e.get("fetch_failed"):              return True   # network error → retry
        if e.get("no_format_in_html"):         return False  # JS-rendered, won't improve
        if "format" not in e:                  return True   # has enriched but no format yet
        if "statut_fetched_at" not in e:       return True   # statut not yet fetched
        return False                                         # fully enriched → skip

    def _failed(t):
        return t.get("enriched", {}).get("fetch_failed", False)

    for round_num in range(1, max_rounds + 1):
        if round_num == 1:
            to_enrich = [t for t in tournaments if _needs_enrich(t)]
            if max_enrich:
                to_enrich = to_enrich[:max_enrich]
        else:
            to_enrich = [t for t in tournaments if _failed(t)]

        if not to_enrich:
            if round_num == 1:
                logger.info("All tournaments already enriched.")
            break

        total = len(to_enrich)
        logger.info("Enrichment round %d/%d: %d tournament(s) (delay=%.1fs → ~%dm)",
                    round_num, max_rounds, total, delay_s, int(total * delay_s / 60))

        for i, t in enumerate(to_enrich, 1):
            # Clear failed flag before retry
            if t.get("enriched", {}).get("fetch_failed"):
                del t["enriched"]["fetch_failed"]
            logger.info("[%d/%d] %s", i, total, t.get("libelle", "?"))
            enrich_tournament(t, session, delay_s=delay_s, cookies_file=cookies_file)

        still_failed = [t for t in tournaments if _failed(t)]
        if not still_failed:
            break
        if round_num < max_rounds:
            logger.warning("%d tournament(s) still failed after round %d — retrying in 10s…",
                           len(still_failed), round_num)
            time.sleep(10)

    # Ensure every tournament has at least the URL
    for t in tournaments:
        if "enriched" not in t:
            t["enriched"] = {"detail_url": get_tournament_url(t)}

    failed_total = sum(1 for t in tournaments if _failed(t))
    if failed_total:
        logger.warning("%d tournament(s) still have no format after all rounds "
                       "(likely JS-rendered — cannot be fixed by retrying).", failed_total)

    return tournaments
