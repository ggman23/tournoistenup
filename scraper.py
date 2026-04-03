"""
Scraper for tenup.fft.fr tournament search.

Flow:
1. GET /recherche/tournois to get session cookies + Drupal form tokens
2. POST /system/ajax with search criteria (paginated)
3. Parse recherche_tournois_update command from the JSON response
"""

import json
import re
import time
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://tenup.fft.fr"
SEARCH_PAGE = "/recherche/tournois"
AJAX_ENDPOINT = "/system/ajax"


class TenupScraper:
    def __init__(self, config: dict, cookies_file: Optional[str] = None):
        self.config = config
        self.search_cfg = config["search"]
        self.scraper_cfg = config["scraper"]
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.scraper_cfg["user_agent"],
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_URL,
            "Referer": BASE_URL + SEARCH_PAGE,
        })
        if cookies_file:
            self._load_cookies(cookies_file)

    def _load_cookies(self, cookies_file: str):
        """Load cookies from a JSON file (list of cookie dicts with name/value/domain...)."""
        try:
            with open(cookies_file) as f:
                cookies = json.load(f)
            for cookie in cookies:
                self.session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain", ".tenup.fft.fr"),
                )
            logger.info("Loaded %d cookies from %s", len(cookies), cookies_file)
        except Exception as e:
            logger.warning("Could not load cookies from %s: %s", cookies_file, e)

    def _get_form_tokens(self) -> tuple[str, str]:
        """
        GET the search page to obtain a fresh Drupal form_build_id and form_token.
        Returns (form_build_id, form_token).
        Raises RuntimeError if tokens cannot be found.
        """
        url = BASE_URL + SEARCH_PAGE
        logger.debug("Fetching form tokens from %s", url)
        resp = self.session.get(url, timeout=30)
        logger.info("GET %s → HTTP %d (final URL: %s)", url, resp.status_code, resp.url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")

        form_build_id = None
        form_token = None

        # form_build_id is a hidden input inside the search form
        build_input = soup.find("input", {"name": "form_build_id"})
        if build_input:
            form_build_id = build_input.get("value")

        # form_token is also a hidden input
        token_input = soup.find("input", {"name": "form_token"})
        if token_input:
            form_token = token_input.get("value")

        # Fallback: search in inline JS for Drupal.settings
        if not form_build_id or not form_token:
            scripts = soup.find_all("script")
            for script in scripts:
                text = script.string or ""
                if "form_build_id" in text:
                    m = re.search(r'"form_build_id"\s*:\s*"([^"]+)"', text)
                    if m:
                        form_build_id = m.group(1)
                if "form_token" in text:
                    m = re.search(r'"form_token"\s*:\s*"([^"]+)"', text)
                    if m:
                        form_token = m.group(1)

        if not form_build_id or not form_token:
            raise RuntimeError(
                "Could not extract form_build_id / form_token from the search page. "
                "The page structure may have changed, or you may need to provide valid cookies."
            )

        logger.debug("form_build_id=%s  form_token=%s...", form_build_id, form_token[:10])
        return form_build_id, form_token

    def _build_post_data(
        self, form_build_id: str, form_token: str, page: int = 0
    ) -> dict:
        """Build the POST payload matching the Drupal AJAX form submission."""
        s = self.search_cfg
        ville = s["ville"]

        data = {
            "recherche_type": "ville",
            "ville[autocomplete][country]": ville["country"],
            "ville[autocomplete][textfield]": "",
            "ville[autocomplete][value_container][value_field]": ville["value"],
            "ville[autocomplete][value_container][label_field]": ville["label"],
            "ville[autocomplete][value_container][lat_field]": str(ville["lat"]),
            "ville[autocomplete][value_container][lng_field]": str(ville["lng"]),
            "ville[distance][value_field]": str(ville["distance_km"]),
            "club[autocomplete][textfield]": "",
            "club[autocomplete][value_container][value_field]": "",
            "club[autocomplete][value_container][label_field]": "",
            "filter_mine": "",
            "pratique": s["pratique"],
            "date[start]": s["date_start"],
            "date[end]": s["date_end"],
            "tournois_interne": str(s.get("tournois_interne", 0)),
            "inscription_ligne": str(s.get("inscription_ligne", 0)),
            "paiement_ligne": str(s.get("paiement_ligne", 0)),
            "page": str(page),
            "sort": s.get("sort", "_DIST_"),
            "form_build_id": form_build_id,
            "form_token": form_token,
            "form_id": "recherche_tournois_form",
            "_triggering_element_name": "submit_main",
            "_triggering_element_value": "Rechercher",
        }

        # Epreuves (SM, SD, DX, DM, DD)
        for epreuve in s.get("epreuves", []):
            data[f"epreuve[{epreuve}]"] = epreuve

        # Categories d'age
        for cat in s.get("categories_age", []):
            data[f"categorie_age[{cat}]"] = str(cat)

        # Types (T = tournoi, C = championnat)
        for t in s.get("types", []):
            data[f"type[{t}]"] = t

        # Minimal ajax_page_state (required by Drupal)
        data["ajax_page_state[theme]"] = "met"
        data["ajax_page_state[jquery_version]"] = "2.2"

        return data

    def _post_search(self, form_build_id: str, form_token: str, page: int) -> tuple:
        """
        Fetch one page of results.

        Page 0: POST to /system/ajax with the full form payload — this establishes
                the search state in the Drupal session.
        Page N>0: GET /system/ajax?page=N — the server uses the session-stored search
                  state, matching the <a href="/system/ajax?page=1"> links in the HTML.
        """
        if page == 0:
            url  = BASE_URL + AJAX_ENDPOINT
            data = self._build_post_data(form_build_id, form_token, page)
            for attempt in range(1, self.scraper_cfg["max_retries"] + 1):
                try:
                    resp = self.session.post(url, data=data, timeout=30)
                    resp.raise_for_status()
                    commands = resp.json()
                    break
                except requests.RequestException as e:
                    logger.warning("Attempt %d/%d failed: %s", attempt, self.scraper_cfg["max_retries"], e)
                    if attempt == self.scraper_cfg["max_retries"]:
                        raise
                    time.sleep(2 ** attempt)
        else:
            url = BASE_URL + AJAX_ENDPOINT + f"?page={page}"
            for attempt in range(1, self.scraper_cfg["max_retries"] + 1):
                try:
                    resp = self.session.get(url, timeout=30)
                    resp.raise_for_status()
                    commands = resp.json()
                    break
                except requests.RequestException as e:
                    logger.warning("Attempt %d/%d failed: %s", attempt, self.scraper_cfg["max_retries"], e)
                    if attempt == self.scraper_cfg["max_retries"]:
                        raise
                    time.sleep(2 ** attempt)

        # Find the recherche_tournois_update command in the response
        for cmd in commands:
            if cmd.get("command") == "recherche_tournois_update":
                results    = cmd.get("results", {})
                items      = results.get("items", [])
                nb_results = results.get("nb_results", 0)
                logger.info("Page %d: %d items (total: %d)", page, len(items), nb_results)
                return items, nb_results

        # Log all returned commands to help diagnose unexpected responses
        cmd_names = [c.get("command", "?") for c in commands]
        logger.warning("No recherche_tournois_update on page %d — got: %s", page, cmd_names)
        return [], 0

    def fetch_all(self) -> list[dict]:
        """
        Fetch all pages, deduplicate by originalId/id, and return a flat list.
        Tokens are fetched once — re-GETting the page would reset the Drupal
        session and break pagination. Page number goes in the URL (?page=N).
        """
        # Single GET to obtain session cookies + form tokens
        logger.info("Fetching tokens...")
        form_build_id, form_token = self._get_form_tokens()
        time.sleep(1)

        seen_ids: set[str] = set()
        all_items: list[dict] = []
        page = 0

        while True:
            items, nb_results = self._post_search(form_build_id, form_token, page)

            if not items:
                break

            new_on_page = 0
            for item in items:
                tid = item.get("originalId") or item.get("id", "")
                if tid and tid not in seen_ids:
                    seen_ids.add(tid)
                    all_items.append(item)
                    new_on_page += 1

            logger.info(
                "Page %d: %d items (%d new, %d total unique / %d announced)",
                page, len(items), new_on_page, len(all_items), nb_results,
            )

            if new_on_page == 0 or len(all_items) >= nb_results:
                break

            page += 1
            time.sleep(self.scraper_cfg["delay_between_pages_s"])

        logger.info("Fetched %d unique tournaments in total", len(all_items))
        return all_items
