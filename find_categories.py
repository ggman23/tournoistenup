#!/usr/bin/env python3
"""
Utility: fetch the TenUp search page and list all categorie_age checkbox values.
Run with: python find_categories.py --cookies cookies.json
"""
import argparse, json, re, sys
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://tenup.fft.fr"
SEARCH_PAGE = "/recherche/tournois"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cookies", required=True)
    args = p.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    with open(args.cookies) as f:
        for c in json.load(f):
            session.cookies.set(c["name"], c["value"], domain=c.get("domain", ".tenup.fft.fr"))

    resp = session.get(BASE_URL + SEARCH_PAGE, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    print("\n=== Catégories d'âge trouvées ===")
    found = []
    for inp in soup.find_all("input", {"type": "checkbox"}):
        name = inp.get("name", "")
        m = re.match(r"categorie_age\[(\d+)\]", name)
        if not m:
            continue
        cid = m.group(1)
        # Find the label next to this checkbox
        label = ""
        parent = inp.parent
        for _ in range(3):
            lbl = parent.find("label")
            if lbl:
                label = lbl.get_text(strip=True)
                break
            parent = parent.parent
        found.append((int(cid), label or "?"))
        print(f"  {cid}: {label}")

    if not found:
        print("Aucune case cochée trouvée — la page est peut-être rendue par JS.")
        print("Essaye d'inspecter le réseau sur tenup.fft.fr et regarde les valeurs")
        print("categorie_age[XXX] dans la requête POST /system/ajax")

if __name__ == "__main__":
    main()
