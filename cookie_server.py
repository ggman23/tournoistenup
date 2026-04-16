#!/usr/bin/env python3
"""
Serveur local pour recevoir les cookies depuis TamperMonkey.
TamperMonkey POST les cookies toutes les 8 minutes → sauvegarde dans cookies.json.

Usage (dans un terminal séparé) :
    python cookie_server.py

Laissez ce serveur tourner pendant tout le run_batch.py.
"""

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

COOKIE_FILE = "cookies.json"
PORT        = 5057
DOMAIN      = ".tenup.fft.fr"


def parse_cookie_string(raw: str) -> list[dict]:
    """Parse 'name=value; name2=value2' → list of cookie dicts."""
    cookies = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        value = value.strip()
        if name:
            cookies.append({
                "name":     name,
                "value":    value,
                "domain":   DOMAIN,
                "path":     "/",
                "secure":   True,
                "httpOnly": False,
            })
    return cookies


class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        """Preflight CORS — nécessaire pour certains navigateurs."""
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path != "/update_cookie":
            self.send_response(404)
            self.end_headers()
            return

        length  = int(self.headers.get("Content-Length", 0))
        body    = self.rfile.read(length).decode("utf-8", errors="replace").strip()

        if not body:
            self.send_response(400)
            self._cors()
            self.end_headers()
            self.wfile.write(b"Empty body")
            return

        cookies = parse_cookie_string(body)

        if not cookies:
            self.send_response(400)
            self._cors()
            self.end_headers()
            self.wfile.write(b"No cookies parsed")
            return

        # Merge avec l'ancien fichier pour ne pas perdre les cookies HttpOnly
        # (qui ne sont pas envoyés par document.cookie mais peuvent être dans
        # un fichier existant)
        existing: list[dict] = []
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        # Index par nom des cookies existants → pour récupérer le bon domaine
        # (Cookie-Editor exporte les vrais domaines : .fft.fr, tenup.fft.fr…)
        existing_by_name = {c["name"]: c for c in existing}

        # Corriger le domaine des cookies TamperMonkey :
        # TamperMonkey ne connaît pas le domaine d'origine → on réutilise celui
        # présent dans le fichier existant s'il y en a un, sinon on garde
        # le domaine par défaut (.tenup.fft.fr).
        for c in cookies:
            if c["name"] in existing_by_name:
                orig_domain = existing_by_name[c["name"]].get("domain", DOMAIN)
                c["domain"] = orig_domain

        # Index par nom des nouveaux cookies
        new_by_name = {c["name"]: c for c in cookies}
        # Garder les anciens non-présents dans les nouveaux (HttpOnly, etc.)
        merged = [c for c in existing if c["name"] not in new_by_name]
        merged += cookies

        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)

        logger.info("✅  %d cookies mis à jour → %s  (%d total dans le fichier)",
                    len(cookies), COOKIE_FILE, len(merged))

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt, *args):
        pass   # Silence le log HTTP brut


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), Handler)
    abs_path = os.path.abspath(COOKIE_FILE)
    logger.info("🚀  Cookie server démarré  →  http://localhost:%d/update_cookie", PORT)
    logger.info("    Fichier cookie : %s", abs_path)
    logger.info("    Ctrl+C pour arrêter")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Arrêt.")
