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
        self.cookies_file = cookies_file   # kept for hot-reload on queue-it
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

    def _reload_cookies(self):
        """Reload cookies from file into session (called when queue-it is detected)."""
        if not self.cookies_file:
            return
        self.session.cookies.clear()
        self._load_cookies(self.cookies_file)
        logger.info("Cookies rechargés depuis %s", self.cookies_file)

    def _get_form_tokens(self) -> tuple[str, str, str, str]:
        """
        GET the search page to obtain a fresh Drupal form_build_id, form_token,
        theme_token and jquery_version_token.
        Returns (form_build_id, form_token, theme_token, jquery_version_token).

        If queue-it is detected (cookie expired), waits for cookies.json to be
        updated (by TamperMonkey / cookie_server.py) then retries automatically.
        Raises RuntimeError if tokens cannot be found after all retries.
        """
        import os as _os

        url = BASE_URL + SEARCH_PAGE
        wait_poll_s   = 15    # check cookies.json every 15 seconds
        wait_max_s    = 600   # give up after 10 minutes
        wait_total    = 0

        while True:
            logger.debug("Fetching form tokens from %s", url)
            resp = self.session.get(url, timeout=30)
            logger.info("GET %s → HTTP %d (final URL: %s)", url, resp.status_code, resp.url)
            resp.raise_for_status()

            # Detect queue-it redirect
            if "queue-it.net" in resp.url:
                if not self.cookies_file or wait_total >= wait_max_s:
                    raise RuntimeError(
                        "Redirigé vers queue-it.net — cookie expiré. "
                        "Lancez cookie_server.py + TamperMonkey pour renouveler les cookies."
                    )
                # Get mtime before waiting
                try:
                    mtime_before = _os.path.getmtime(self.cookies_file)
                except OSError:
                    mtime_before = 0

                logger.warning(
                    "⚠️  Queue-it détecté — cookie expiré. "
                    "Attente de la mise à jour de %s par TamperMonkey... "
                    "(max %ds, vérification toutes les %ds)",
                    self.cookies_file, wait_max_s - wait_total, wait_poll_s,
                )
                time.sleep(wait_poll_s)
                wait_total += wait_poll_s

                # Check if cookies.json was updated
                try:
                    mtime_after = _os.path.getmtime(self.cookies_file)
                except OSError:
                    mtime_after = mtime_before

                if mtime_after > mtime_before:
                    logger.info("✅  cookies.json mis à jour — rechargement et nouvelle tentative...")
                    self._reload_cookies()
                    wait_total = 0  # reset timeout after a successful cookie refresh
                else:
                    logger.info("⏳  cookies.json inchangé (%ds écoulés / %ds max)...",
                                wait_total, wait_max_s)
                continue   # retry the GET

            # Not queue-it — we have the real page
            break

        soup = BeautifulSoup(resp.text, "lxml")

        form_build_id = None
        form_token = None
        theme_token = None
        jquery_version_token = None

        # form_build_id is a hidden input inside the search form
        build_input = soup.find("input", {"name": "form_build_id"})
        if build_input:
            form_build_id = build_input.get("value")

        # form_token is also a hidden input
        token_input = soup.find("input", {"name": "form_token"})
        if token_input:
            form_token = token_input.get("value")

        # Extract theme_token and jquery_version_token from inline Drupal.settings JS
        scripts = soup.find_all("script")
        for script in scripts:
            text = script.string or ""
            if not form_build_id and "form_build_id" in text:
                m = re.search(r'"form_build_id"\s*:\s*"([^"]+)"', text)
                if m:
                    form_build_id = m.group(1)
            if not form_token and "form_token" in text:
                m = re.search(r'"form_token"\s*:\s*"([^"]+)"', text)
                if m:
                    form_token = m.group(1)
            if not theme_token and "theme_token" in text:
                m = re.search(r'"theme_token"\s*:\s*"([^"]+)"', text)
                if m:
                    theme_token = m.group(1)
            if not jquery_version_token and "jquery_version_token" in text:
                m = re.search(r'"jquery_version_token"\s*:\s*"([^"]+)"', text)
                if m:
                    jquery_version_token = m.group(1)

        if not form_build_id or not form_token:
            raise RuntimeError(
                "Could not extract form_build_id / form_token from the search page. "
                "The page structure may have changed, or you may need to provide valid cookies."
            )

        logger.debug(
            "form_build_id=%s  form_token=%s...  theme_token=%s  jq_token=%s",
            form_build_id, form_token[:10],
            theme_token[:10] if theme_token else None,
            jquery_version_token[:10] if jquery_version_token else None,
        )
        return form_build_id, form_token, theme_token or "", jquery_version_token or ""

    def _build_post_data(
        self,
        form_build_id: str,
        form_token: str,
        page: int = 0,
        theme_token: str = "",
        jquery_version_token: str = "",
    ) -> dict:
        """Build the POST payload matching the Drupal AJAX form submission.

        Page 0 (initial search): _triggering_element_name=submit_main
        Page 1+ (pagination):    _triggering_element_name=submit_page
        Both cases include page=N in the POST body (URL is always /system/ajax).
        """
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
            "sort": s.get("sort", "_DIST_"),
            "form_build_id": form_build_id,
            "form_token": form_token,
            "form_id": "recherche_tournois_form",
            "page": str(page),
        }

        if page == 0:
            data["_triggering_element_name"]  = "submit_main"
            data["_triggering_element_value"] = "Rechercher"
        else:
            data["_triggering_element_name"]  = "submit_page"
            data["_triggering_element_value"] = "Submit page"

        # Epreuves (SM, SD, DX, DM, DD)
        for epreuve in s.get("epreuves", []):
            data[f"epreuve[{epreuve}]"] = epreuve

        # Categories d'age
        for cat in s.get("categories_age", []):
            data[f"categorie_age[{cat}]"] = str(cat)

        # Types (T = tournoi, C = championnat)
        for t in s.get("types", []):
            data[f"type[{t}]"] = t

        # ajax_page_state — include tokens extracted from the page if available
        data["ajax_page_state[theme]"] = "met"
        data["ajax_page_state[jquery_version]"] = "2.2"
        if theme_token:
            data["ajax_page_state[theme_token]"] = theme_token
        if jquery_version_token:
            data["ajax_page_state[jquery_version_token]"] = jquery_version_token

        return data

    AJAX_HEADERS = {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    def _do_ajax(self, method: str, url: str, data=None) -> list:
        """Make one AJAX request (POST or GET) and return the parsed command list."""
        for attempt in range(1, self.scraper_cfg["max_retries"] + 1):
            try:
                if method == "POST":
                    resp = self.session.post(url, data=data, headers=self.AJAX_HEADERS, timeout=30)
                else:
                    resp = self.session.get(url, headers=self.AJAX_HEADERS, timeout=30)
                resp.raise_for_status()
                if not resp.content:
                    raise ValueError(f"Empty response body (HTTP {resp.status_code}) for {method} {url}")
                return resp.json()
            except Exception as e:
                logger.warning("Attempt %d/%d failed: %s", attempt, self.scraper_cfg["max_retries"], e)
                if attempt == self.scraper_cfg["max_retries"]:
                    raise
                time.sleep(2 ** attempt)

    def _post_search(
        self,
        form_build_id: str,
        form_token: str,
        page: int,
        theme_token: str = "",
        jquery_version_token: str = "",
    ) -> tuple:
        """Fetch one page of results; return (items, nb_results, new_form_build_id)."""
        url  = BASE_URL + AJAX_ENDPOINT  # never append ?page=N — browser doesn't
        data = self._build_post_data(form_build_id, form_token, page, theme_token, jquery_version_token)
        commands = self._do_ajax("POST", url, data=data)

        new_fbid = None
        for cmd in commands:
            if cmd.get("command") == "settings":
                s = cmd.get("settings") or {}
                logger.info("Page %d settings top-level keys: %s", page, list(s.keys()))
                # Log full content (truncated to 1000 chars) to find form_build_id location
                import json as _j
                logger.info("Page %d settings content: %s", page, _j.dumps(s)[:1000])
                # Common Drupal locations for updated form_build_id
                for form_name, fdata in (s.get("forms") or {}).items():
                    if isinstance(fdata, dict):
                        fbid = fdata.get("build_id") or fdata.get("form_build_id")
                        if fbid:
                            new_fbid = fbid
                            logger.info("Page %d: extracted new form_build_id from settings[forms][%s]",
                                        page, form_name)

        for cmd in commands:
            if cmd.get("command") == "recherche_tournois_update":
                results    = cmd.get("results", {})
                items      = results.get("items", [])
                nb_results = results.get("nb_results", 0)
                ids = [it.get("originalId") or it.get("id") for it in items[:3]]
                logger.info("Page %d: %d items (total: %d) — first IDs: %s",
                            page, len(items), nb_results, ids)
                return items, nb_results, new_fbid

        cmd_names = [c.get("command", "?") for c in commands]
        logger.warning("No recherche_tournois_update on page %d — got: %s", page, cmd_names)
        return [], 0, new_fbid

    def fetch_all(self, max_pages: int = 0) -> list[dict]:
        """
        Fetch all pages, deduplicate by originalId/id, and return a flat list.

        For each page we fetch a FRESH form_build_id/form_token by GETting the
        search page again.  The same form_build_id reused across pages always
        returns page 0 (Drupal uses the cached form state, which has page=0).
        A pristine token lets Drupal process the submission without a stale
        page position in the cached state, so ?page=N in the URL and page=N
        in the POST body can take effect via pager_find_page().

        max_pages: stop after this many pages (0 = no limit, useful for testing).
        """
        seen_ids: set[str] = set()
        all_items: list[dict] = []
        page = 0

        while True:
            logger.info("Fetching fresh tokens for page %d...", page)
            form_build_id, form_token, theme_token, jquery_version_token = self._get_form_tokens()
            time.sleep(1)

            items, nb_results, _ = self._post_search(
                form_build_id, form_token, page, theme_token, jquery_version_token
            )

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
            if max_pages and page >= max_pages:
                logger.info("Stopping after %d page(s) (--pages-max).", max_pages)
                break

            time.sleep(self.scraper_cfg["delay_between_pages_s"])

        logger.info("Fetched %d unique tournaments in total", len(all_items))
        return all_items
