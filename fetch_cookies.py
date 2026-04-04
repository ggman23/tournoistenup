#!/usr/bin/env python3
"""
Opens a real browser, navigates to tenup.fft.fr, and saves the session
cookies to cookies.json — no manual copy-paste needed.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    python fetch_cookies.py              # saves to cookies.json
    python fetch_cookies.py --out my_cookies.json
    python fetch_cookies.py --reuse      # reuse existing profile (stay logged in)
"""

import argparse
import json
import os
import sys
import time

TARGET_URL     = "https://tenup.fft.fr/recherche-tournois"
QUEUE_DOMAIN   = "queue-it.net"
PROFILE_DIR    = ".browser_profile"   # persists login between runs with --reuse


def wait_for_page(page, timeout: int):
    """Wait until we're on tenup.fft.fr (past queue-it) and the page is idle."""
    print("⏳  En attente du chargement de tenup.fft.fr…")
    deadline = time.time() + timeout
    while time.time() < deadline:
        url = page.url
        if "tenup.fft.fr" in url and QUEUE_DOMAIN not in url:
            # Wait for network idle to ensure all session cookies are set
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            return True
        time.sleep(1)
    return False


def run(out_file: str, reuse_profile: bool, timeout: int, headless: bool):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌  Playwright non installé.")
        print("    Installez-le avec :")
        print("      pip install playwright")
        print("      playwright install chromium")
        sys.exit(1)

    with sync_playwright() as pw:
        launch_args = dict(
            headless=headless,
            args=["--start-maximized"],
        )
        if reuse_profile:
            os.makedirs(PROFILE_DIR, exist_ok=True)
            ctx = pw.chromium.launch_persistent_context(
                PROFILE_DIR,
                **launch_args,
                no_viewport=True,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        else:
            browser = pw.chromium.launch(**launch_args)
            ctx     = browser.new_context(no_viewport=True)
            page    = ctx.new_page()

        print(f"🌐  Ouverture de {TARGET_URL}")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60_000)

        # Check if we hit queue-it
        if QUEUE_DOMAIN in page.url:
            print()
            print("⚠️   File d'attente queue-it détectée.")
            print("    Attendez que la page tenup.fft.fr s'affiche normalement.")
            print(f"    Timeout: {timeout}s")
            print()

        ok = wait_for_page(page, timeout)
        if not ok:
            print(f"❌  Page tenup.fft.fr non atteinte après {timeout}s (URL: {page.url})")
            ctx.close()
            sys.exit(1)

        print(f"✅  Page chargée : {page.url}")

        # Give an extra moment for any deferred cookies (SSO, analytics)
        time.sleep(2)

        raw_cookies = ctx.cookies()
        ctx.close()

    if not raw_cookies:
        print("❌  Aucun cookie récupéré.")
        sys.exit(1)

    # Format compatible with Requests (and our scraper)
    cookies_out = [
        {
            "name":     c["name"],
            "value":    c["value"],
            "domain":   c.get("domain", ""),
            "path":     c.get("path", "/"),
            "secure":   c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
        }
        for c in raw_cookies
    ]

    with open(out_file, "w") as f:
        json.dump(cookies_out, f, indent=2, ensure_ascii=False)

    print(f"💾  {len(cookies_out)} cookies sauvegardés dans {out_file}")
    print()
    print("Vous pouvez maintenant lancer l'extraction :")
    print(f"  python main.py --enrich")
    print(f"  python run_batch.py --enrich --date-start 01/04/26 --date-end 01/09/26")


def parse_args():
    p = argparse.ArgumentParser(description="Exporte les cookies tenup.fft.fr vers un fichier JSON")
    p.add_argument("--out", default="cookies.json", metavar="FILE",
                   help="Fichier de sortie (défaut: cookies.json)")
    p.add_argument("--reuse", action="store_true",
                   help=f"Réutiliser le profil persistant dans ./{PROFILE_DIR}/ "
                        f"(conserve la session entre les runs)")
    p.add_argument("--timeout", type=int, default=120,
                   help="Secondes à attendre que tenup.fft.fr charge (défaut: 120)")
    p.add_argument("--headless", action="store_true",
                   help="Mode sans fenêtre (déconseillé si queue-it est actif)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        out_file       = args.out,
        reuse_profile  = args.reuse,
        timeout        = args.timeout,
        headless       = args.headless,
    )
