"""
Formats and outputs new tournament notifications.
Extend this module to add email, Telegram, etc.
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _format_date(date_obj: dict | None) -> str:
    if not date_obj:
        return "?"
    raw = date_obj.get("date", "")
    try:
        return datetime.fromisoformat(raw.split(".")[0]).strftime("%d/%m/%Y")
    except Exception:
        return raw[:10] if raw else "?"


def format_tournament(t: dict) -> str:
    """Single-tournament human-readable summary."""
    name = t.get("libelle", "?")
    club = t.get("nomClub", "?")
    city = t.get("installation", {}).get("ville", "?")
    cp = t.get("installation", {}).get("codePostal", "?")
    date_debut = _format_date(t.get("dateDebut"))
    date_fin = _format_date(t.get("dateFin"))
    distance = t.get("distanceEnMetres", "?")
    inscription = "Oui" if t.get("inscriptionEnLigne") else "Non"
    paiement = "Oui" if t.get("paiementEnLigne") else "Non"
    tmc = " [TMC]" if t.get("tmc") else ""
    cat = t.get("categorieTournoi", {}).get("libelle", "")

    epreuves_parts = []
    for ep in t.get("epreuves", []):
        age = ep.get("categorieAge", {}).get("libelle", "")
        nature = ep.get("natureEpreuve", {}).get("libelle", "")
        bas = ep.get("classementBas", {}).get("libelle", "?").strip()
        haut = ep.get("classementHaut", {}).get("libelle", "?").strip()
        tarif = ep.get("tarifJeune", 0)
        epreuves_parts.append(f"  - {nature} {age} [{bas} → {haut}] {tarif}€")

    epreuves_str = "\n".join(epreuves_parts) if epreuves_parts else "  (aucune)"

    return (
        f"🎾 {name}{tmc}\n"
        f"   Club    : {club}\n"
        f"   Lieu    : {city} ({cp})\n"
        f"   Dates   : {date_debut} → {date_fin}\n"
        f"   Distance: {distance}\n"
        f"   Catégorie: {cat}\n"
        f"   Inscription en ligne: {inscription} | Paiement en ligne: {paiement}\n"
        f"   Épreuves:\n{epreuves_str}"
    )


def notify(
    new_tournaments: list[dict],
    output_file: str,
    print_to_console: bool = True,
):
    if not new_tournaments:
        msg = "Aucun nouveau tournoi depuis la dernière vérification."
        if print_to_console:
            print(msg)
        logger.info(msg)
        return

    header = f"\n{'='*60}\n{len(new_tournaments)} NOUVEAU(X) TOURNOI(S) DÉTECTÉ(S)\n{'='*60}\n"
    lines = [header]
    for t in new_tournaments:
        lines.append(format_tournament(t))
        lines.append("")

    text = "\n".join(lines)

    if print_to_console:
        print(text)

    # Save new tournaments to file
    import os
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "detected_at": datetime.utcnow().isoformat() + "Z",
                "count": len(new_tournaments),
                "tournaments": new_tournaments,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    logger.info("New tournaments saved to %s", output_file)
