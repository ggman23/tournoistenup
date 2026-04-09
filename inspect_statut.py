"""
Inspection du HTML des pages de détail TenUp pour identifier
où se trouvent les messages de statut d'inscription.

Usage:
    python inspect_statut.py --cookies cookies.json
"""
import argparse
import json
import re
import sys
import requests
from bs4 import BeautifulSoup

URLS = [
    ("197251", "Inscriptions pas encore ouvertes (date future)"),
    ("201198", "Inscriptions clôturées"),
    ("201815", "Inscriptions ouvertes (pas de message)"),
    ("206133", "Tournoi terminé"),
    ("179474", "Inscription en ligne non disponible"),
    ("204739", "Classement hors bornes"),
    ("208068", "Déjà inscrit"),
    ("195216", "Mauvais genre / âge"),
]

BASE = "https://tenup.fft.fr/tournoi/{}"

CANDIDATE_SELECTORS = [
    # Sélecteurs CSS à tester — on cherche lequel contient les messages
    "div.epreuve-detail-inscription",
    "div.inscription-status",
    "div.statut-inscription",
    "div.epreuve-statut",
    "div.alert",
    "div.message",
    "div.epreuve-detail",
    "div.epreuve-inscription",
    "p.statut",
    "span.statut",
    "div[class*='statut']",
    "div[class*='inscription']",
    "div[class*='message']",
    "div[class*='alert']",
    "button[class*='inscri']",
    "a[class*='inscri']",
]

# Mots-clés qui signalent un message de statut
KEYWORDS = [
    "inscri", "clôtur", "clotur", "attente", "ouvert",
    "terminé", "classement", "bornes", "déjà", "deja",
    "possible", "autoris", "âge", "age", "dames", "début",
    "débute", "liste", "complet", "fermé", "ferme",
]


def load_cookies(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {c["name"]: c["value"] for c in data}


def fetch(url: str, session: requests.Session) -> str | None:
    try:
        r = session.get(url, timeout=20)
        if r.status_code == 200:
            return r.text
        print(f"  HTTP {r.status_code}")
        return None
    except Exception as e:
        print(f"  Erreur réseau : {e}")
        return None


def find_status_elements(soup: BeautifulSoup) -> list[dict]:
    """Cherche tous les éléments contenant un mot-clé de statut."""
    results = []
    for tag in soup.find_all(True):
        text = tag.get_text(" ", strip=True)
        if len(text) < 5 or len(text) > 500:
            continue
        text_lower = text.lower()
        if any(kw in text_lower for kw in KEYWORDS):
            # Ignore les menus, headers, footers
            if any(p in (tag.get("class") or []) for p in ["nav", "menu", "footer", "header"]):
                continue
            classes = " ".join(tag.get("class") or [])
            results.append({
                "tag": tag.name,
                "classes": classes,
                "text": text[:200],
            })
    # Déduplique par texte
    seen = set()
    unique = []
    for r in results:
        if r["text"] not in seen:
            seen.add(r["text"])
            unique.append(r)
    return unique[:15]


def inspect_url(tid: str, label: str, session: requests.Session):
    url = BASE.format(tid)
    print(f"\n{'='*70}")
    print(f"[{tid}] {label}")
    print(f"URL: {url}")
    print('='*70)

    html = fetch(url, session)
    if not html:
        print("  ÉCHEC — pas de réponse")
        return

    soup = BeautifulSoup(html, "html.parser")

    # 1) Teste les sélecteurs candidats
    print("\n--- Sélecteurs candidats avec contenu ---")
    found_any = False
    for sel in CANDIDATE_SELECTORS:
        try:
            elems = soup.select(sel)
        except Exception:
            continue
        for el in elems:
            txt = el.get_text(" ", strip=True)
            if txt and len(txt) > 3:
                print(f"  [{sel}] → \"{txt[:150]}\"")
                found_any = True
    if not found_any:
        print("  (aucun sélecteur candidat ne correspond)")

    # 2) Recherche par mots-clés
    print("\n--- Éléments contenant des mots-clés de statut ---")
    matches = find_status_elements(soup)
    if matches:
        for m in matches:
            print(f"  <{m['tag']} class=\"{m['classes']}\">")
            print(f"    → \"{m['text']}\"")
    else:
        print("  (aucun élément trouvé avec les mots-clés)")

    # 3) Cherche tous les div/p qui contiennent "inscri" dans leur classe
    print("\n--- Divs/spans dont la classe contient 'inscri' ou 'statut' ---")
    pattern = re.compile(r"inscri|statut|epreuve", re.I)
    for tag in soup.find_all(["div", "span", "p", "button", "a"]):
        classes = " ".join(tag.get("class") or [])
        if pattern.search(classes):
            txt = tag.get_text(" ", strip=True)[:150]
            print(f"  <{tag.name} class=\"{classes}\"> → \"{txt}\"")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cookies", default="cookies.json")
    p.add_argument("--id", default=None,
                   help="Inspecter seulement ce tournoi ID (ex: 197251)")
    args = p.parse_args()

    cookies = load_cookies(args.cookies)
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    urls = URLS if not args.id else [(args.id, "Inspection manuelle")]

    for tid, label in urls:
        inspect_url(tid, label, session)

    print(f"\n{'='*70}")
    print("Inspection terminée.")


if __name__ == "__main__":
    main()
