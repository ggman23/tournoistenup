"""
Generates a self-contained interactive HTML report from tournaments data.
Uses Bootstrap 5 + DataTables (CDN) for sorting, filtering, pagination.
"""

import json
import os
import html
from datetime import datetime, timezone, timedelta


SURFACE_COLORS = {
    "TB":    ("Terre battue",         "#c0392b"),
    "TA":    ("Terre artificielle",   "#e67e22"),
    "RES":   ("Résine",               "#2980b9"),
    "BP":    ("Béton poreux",         "#7f8c8d"),
    "DUR":   ("Dur",                  "#95a5a6"),
    "DUR-":  ("Dur",                  "#95a5a6"),
    "GAZON": ("Gazon",                "#27ae60"),
    "B-PIL": ("Moquette",             "#8e44ad"),
    "AUTRE": ("Autre",                "#bdc3c7"),
}

FORMAT_COLORS = {
    "1": "#c0392b", "2": "#e67e22", "3": "#f39c12",
    "4": "#27ae60", "5": "#2980b9", "6": "#8e44ad", "7": "#7f8c8d",
}

STATUT_CONFIG = {
    "ouvert":          ("#27ae60", "Ouvert"),
    "bientot":         ("#2980b9", "Bientôt"),
    "attente":         ("#e67e22", "Liste d'attente"),
    "inscrit_attente": ("#d35400", "Inscrit (liste d'attente)"),
    "cloture":         ("#c0392b", "Clôturé"),
    "hors_bornes":     ("#7f8c8d", "Hors bornes"),
    "impossible":      ("#95a5a6", "Hors ligne"),
    "deja_inscrit":    ("#1abc9c", "Déjà inscrit"),
    "ineligible":      ("#34495e", "Non éligible"),
    "autre":           ("#bdc3c7", "?"),
}


def _statut_badge_html(code: str, message: str = "") -> str:
    color, label = STATUT_CONFIG.get(code, ("#bdc3c7", code))
    tip = html.escape(message) if message else html.escape(label)
    return (
        f' <span class="badge statut-badge" data-statut="{html.escape(code)}" style="background:{color}" '
        f'title="{tip}" data-bs-toggle="tooltip">{html.escape(label)}</span>'
    )


# Age category IDs → short label for filter UI
AGE_LABELS = {
    110: "11 ans",   120: "11/12 ans", 125: "12 ans",
    130: "13 ans",   140: "13/14 ans", 145: "14 ans",
    160: "15/16 ans", 180: "17/18 ans", 200: "Adulte",
}


def _fmt_date(date_obj, short=False):
    if not date_obj:
        return ""
    raw = date_obj.get("date", "")
    try:
        d = datetime.fromisoformat(raw.split(".")[0])
        return d.strftime("%d/%m") if short else d.strftime("%d/%m/%Y")
    except Exception:
        return raw[:10] if raw else ""


def _surfaces(terrains):
    parts = []
    for t in terrains:
        code = t.get("code", "").upper().replace(" ", "")
        label, color = SURFACE_COLORS.get(code, (t.get("libelle", code), "#95a5a6"))
        parts.append(
            f'<span class="badge srf-badge" style="background:{color}">{html.escape(label)}</span>'
        )
    return " ".join(parts)


def _epreuves_html(epreuves, formats_list=None, statuts=None, only_natures=None):
    """
    Render one line per épreuve.  If formats_list is provided, attach a format badge.
    If statuts (dict from enriched["statuts_inscription"]) is provided, attach a statut badge.

    only_natures: if set (e.g. ["SM"]), only render épreuves whose natureEpreuve.code
                  is in the list. Others are silently skipped.

    Matching strategy (best-effort):
      1. By epreuve_key: match "NATURE_ageid" stored during enrichment.
      2. Positional: if lengths match, use index.
      3. Fallback: no badge.
    """
    # Build lookup: epreuve_key → format entry
    key_to_fmt = {}
    positional = []
    if formats_list:
        for f in formats_list:
            positional.append(f)
            k = f.get("epreuve_key")
            if k:
                key_to_fmt[k] = f

    lines = []
    for idx, ep in enumerate(epreuves):
        # Build epreuve_key from API data
        nat_code = ep.get("natureEpreuve", {}).get("code", "")

        # Skip épreuves not in the display filter (e.g. hide DD/DM when only SM wanted)
        if only_natures and nat_code and nat_code not in only_natures:
            continue

        age    = ep.get("categorieAge", {}).get("libelle", "")
        nature = ep.get("natureEpreuve", {}).get("libelle", "")
        bas    = ep.get("classementBas",  {}).get("libelle", "?").strip()
        haut   = ep.get("classementHaut", {}).get("libelle", "?").strip()
        tarif  = ep.get("tarifJeune", 0)
        age_id   = ep.get("categorieAge", {}).get("id", 0)
        # Abbreviations for print
        _NAT_ABBR = {"Simple Messieurs": "SM", "Simple Dames": "SD",
                     "Double Messieurs": "DM", "Double Dames": "DD", "Double Mixte": "DX"}
        abbr_nat = _NAT_ABBR.get(nature, nature)
        abbr_age = age.replace(" ans", "").replace(" Ans", "").strip()
        ep_key   = f"{nat_code}_{age_id}" if nat_code and age_id else ""

        fmt_entry = None
        if ep_key and ep_key in key_to_fmt:
            fmt_entry = key_to_fmt[ep_key]
        elif positional and len(positional) == len(epreuves):
            fmt_entry = positional[idx]
        elif positional:
            # Lengths differ: if all formats share the same number, apply to all epreuves.
            nums = {f.get("num") for f in positional}
            if len(nums) == 1:
                fmt_entry = positional[0]

        fmt_badge = ""
        if fmt_entry:
            fn  = fmt_entry.get("num", "")
            fd  = fmt_entry.get("desc", "")
            fc  = FORMAT_COLORS.get(fn, "#666")
            tip = f"Format {fn}"
            if fd:
                tip += f" — {fd}"
            fmt_badge = (
                f' <span class="badge fmt-ep-badge" style="background:{fc}" '
                f'title="{html.escape(tip)}" data-bs-toggle="tooltip">F{fn}</span>'
            )

        statut_badge = ""
        if statuts is not None:
            s_entry = statuts.get(ep_key) or statuts.get(nat_code)
            if s_entry:
                statut_badge = _statut_badge_html(s_entry["statut"], s_entry["message"])

        ep_fmt_num = fmt_entry.get("num", "") if fmt_entry else ""
        lines.append(
            f'<div class="ep-line" data-ep-key="{html.escape(ep_key)}" data-fmt="{html.escape(ep_fmt_num)}">'
            f'<span class="ep-nature" data-abbr="{html.escape(abbr_nat)}">{html.escape(nature)}</span> '
            f'<span class="ep-age" data-abbr="{html.escape(abbr_age)}">{html.escape(age)}</span> '
            f'<span class="ep-range">{html.escape(bas)} → {html.escape(haut)}</span> '
            f'<span class="ep-tarif">{tarif}€</span>'
            f'{fmt_badge}{statut_badge}'
            f'</div>'
        )
    return "\n".join(lines) if lines else '<span class="text-muted">—</span>'


def _epreuves_data(epreuves):
    """Return a JSON-safe list of (nature_code, age_id) pairs for JS filtering."""
    result = []
    for ep in epreuves:
        nature = ep.get("natureEpreuve", {}).get("code", "")
        age_id = ep.get("categorieAge", {}).get("id", 0)
        if nature and age_id:
            result.append(f"{nature}_{age_id}")
    return result


def _parse_distance_km(raw: str) -> float:
    """Parse '1,5 km' or '903 m' or '1.5 km' → float km."""
    raw = raw.replace("\xa0", "").replace(",", ".").strip()
    try:
        if raw.endswith(" m") or raw == "m":
            return float(raw.replace(" m", "").strip()) / 1000.0
        return float(raw.replace(" km", "").strip() or 0)
    except ValueError:
        return 0.0


def _tournament_to_row(t, only_natures=None):
    install  = t.get("installation", {})
    juge     = t.get("jugeArbitre", {})
    enriched = t.get("enriched", {})

    detail_url   = enriched.get("detail_url", f"https://tenup.fft.fr/tournoi/{t.get('id', '')}")
    fmt          = enriched.get("format", "")
    fmt_desc     = enriched.get("format_desc", "")
    formats_list = enriched.get("formats_list", [])
    # All distinct format numbers, ordered by first appearance
    seen_nums: list[str] = []
    for f in formats_list:
        n = f.get("num", "")
        if n and n not in seen_nums:
            seen_nums.append(n)
    if not seen_nums and fmt:
        seen_nums = [fmt]
    fmt_all = seen_nums          # e.g. ["5", "6"] when two epreuves have different formats

    date_debut = _fmt_date(t.get("dateDebut"))
    date_fin   = _fmt_date(t.get("dateFin"))
    dates      = date_debut if date_debut == date_fin else f"{date_debut} → {date_fin}"

    ville = install.get("ville", "")
    cp    = install.get("codePostal", "")
    dept  = cp[:2].upper() if cp else ""
    adresse_parts = [
        install.get("adresse1", ""),
        install.get("adresse2", ""),
        f"{cp} {ville}".strip(),
    ]
    adresse = ", ".join(p for p in adresse_parts if p.strip())

    statuts_inscription = enriched.get("statuts_inscription")
    commentaire_club    = enriched.get("commentaire_club", "")
    statut_fetched_at   = enriched.get("statut_fetched_at", "")

    # Unique statut codes across all épreuves, for JS filtering
    statuts_set: list[str] = []
    if statuts_inscription:
        seen_codes: set[str] = set()
        for v in statuts_inscription.values():
            c = v.get("statut", "")
            if c and c not in seen_codes:
                seen_codes.add(c)
                statuts_set.append(c)

    # Freshness: warn if statut_fetched_at is older than 24h
    statut_stale = False
    if statut_fetched_at:
        try:
            fetched_dt = datetime.fromisoformat(statut_fetched_at)
            if fetched_dt.tzinfo is None:
                fetched_dt = fetched_dt.replace(tzinfo=timezone.utc)
            statut_stale = (datetime.now(timezone.utc) - fetched_dt) > timedelta(hours=24)
        except Exception:
            pass

    ep_html = _epreuves_html(
        t.get("epreuves", []),
        enriched.get("formats_list"),
        statuts=statuts_inscription,
        only_natures=only_natures,
    )
    if commentaire_club:
        short = commentaire_club[:100] + ("…" if len(commentaire_club) > 100 else "")
        ep_html += (
            f'\n<div class="ep-comment text-muted fst-italic" style="font-size:.78em;margin-top:4px" '
            f'title="{html.escape(commentaire_club)}" data-bs-toggle="tooltip">'
            f'📋 {html.escape(short)}</div>'
        )
    if statut_stale:
        ep_html += (
            '\n<div class="text-warning" style="font-size:.75em;margin-top:2px">'
            '⚠️ Statut &gt; 24h</div>'
        )

    return {
        "id":           t.get("id", ""),
        "detail_url":   detail_url,
        "libelle":      t.get("libelle", ""),
        "nom_club":     t.get("nomClub", ""),
        "tmc":          t.get("tmc", False),
        "cat":          t.get("categorieTournoi", {}).get("libelle", ""),
        "fmt":          fmt,
        "fmt_all":      fmt_all,
        "fmt_desc":     fmt_desc,
        "fmt_sort":     int(fmt_all[0]) if fmt_all else 99,
        "dates":        dates,
        "date_debut_sort": t.get("dateDebut", {}).get("date", ""),
        "date_debut_iso": t.get("dateDebut", {}).get("date", "")[:10],
        "date_fin_iso":   t.get("dateFin",   {}).get("date", "")[:10],
        "ville":        ville,
        "cp":           cp,
        "dept":         dept,
        "adresse":      adresse,
        "distance_raw": t.get("distanceEnMetres", ""),
        "distance_km":  _parse_distance_km(t.get("distanceEnMetres", "")),
        "ref_city":     t.get("_ref_city", ""),
        "road_km":      enriched.get("road_km"),
        "road_min":     enriched.get("road_min"),
        "geo_lat":      enriched.get("geo_lat"),
        "geo_lng":      enriched.get("geo_lng"),
        "surfaces":     _surfaces(t.get("naturesTerrains", [])),
        "epreuves":     ep_html,
        "epreuves_keys": _epreuves_data(t.get("epreuves", [])),
        "statuts_set":  statuts_set,
        "inscription":  t.get("inscriptionEnLigne", False),
        "paiement":     t.get("paiementEnLigne", False),
        "juge_nom":     f"{juge.get('prenom', '')} {juge.get('nom', '')}".strip(),
        "telephone":    install.get("telephone", ""),
        "email":        t.get("courrielEngagement", ""),
        "ouverture":    t.get("dateOuvertureInscriptionEnLigne", ""),
        "is_new":       t.get("_is_new", False),
        "first_seen":   t.get("_first_seen", ""),
    }


def _collect_epreuve_options(rows):
    """Build sorted list of (key, label) for the épreuve filter dropdown."""
    seen = {}
    nature_labels = {"SM": "Simple Messieurs", "SD": "Simple Dames",
                     "DM": "Double Messieurs", "DD": "Double Dames", "DX": "Double Mixte"}
    for r in rows:
        for key in r["epreuves_keys"]:
            if key not in seen:
                parts = key.split("_")
                if len(parts) == 2:
                    nat, age_id = parts[0], int(parts[1])
                    nat_lbl = nature_labels.get(nat, nat)
                    age_lbl = AGE_LABELS.get(age_id, f"cat {age_id}")
                    seen[key] = f"{nat_lbl} {age_lbl}"
    # Sort: SM first, then SD, then others; within each by age
    def sort_key(item):
        k, lbl = item
        order = {"SM": 0, "SD": 1, "DM": 2, "DD": 3, "DX": 4}
        nat = k.split("_")[0]
        age = int(k.split("_")[1]) if k.split("_")[1].isdigit() else 999
        return (order.get(nat, 9), age)
    return sorted(seen.items(), key=sort_key)


def generate_html(
    tournaments: list,
    output_path: str,
    new_ids=None,
    title: str = "Tournois TenUp",
    fetched_at: str = "",
    only_natures: list = None,
    ref_lat: float = 0.0,
    ref_lng: float = 0.0,
    ref_city: str = "",
):
    new_ids = new_ids or set()
    for t in tournaments:
        tid = t.get("originalId") or t.get("id", "")
        t["_is_new"] = tid in new_ids

    rows = [_tournament_to_row(t, only_natures=only_natures) for t in tournaments]
    epreuve_options = _collect_epreuve_options(rows)

    tbody_lines = []
    for r in rows:
        new_badge = '<span class="badge bg-danger ms-1">NEW</span>' if r["is_new"] else ""
        tmc_badge = '<span class="badge bg-warning text-dark ms-1">TMC</span>' if r["tmc"] else ""

        # Build Format column: one badge per distinct format number
        fmt_parts = []
        for fn in r["fmt_all"]:
            fc  = FORMAT_COLORS.get(fn, "#666")
            tip = f"Format {fn}"
            if fn == r["fmt"] and r["fmt_desc"]:
                tip += f" — {r['fmt_desc']}"
            fmt_parts.append(
                f'<span class="badge fmt-badge" data-fmt="{fn}" style="background:{fc}" '
                f'title="{html.escape(tip)}" data-bs-toggle="tooltip">F{fn}</span>'
            )
        fmt_badge = " ".join(fmt_parts)

        nom_link = (
            f'<a href="{html.escape(r["detail_url"])}" target="_blank" '
            f'class="tournament-link">{html.escape(r["libelle"])}</a>'
            f'{new_badge}{tmc_badge}'
        )
        email_link = (
            f'<a href="mailto:{html.escape(r["email"])}">{html.escape(r["email"])}</a>'
            if r["email"] else "—"
        )
        tel_str = (
            f'<a href="tel:{r["telephone"]}">{html.escape(r["telephone"])}</a>'
            if r["telephone"] else "—"
        )
        insc  = "✅" if r["inscription"] else "❌"
        paiem = "✅" if r["paiement"]    else "❌"

        ep_keys_json   = json.dumps(r["epreuves_keys"])
        statuts_json   = json.dumps(r["statuts_set"])

        tid_esc  = html.escape(str(r['id']))
        has_fmt  = "true" if r["fmt_all"] else "false"
        tbody_lines.append(f"""
        <tr class="{'table-warning' if r['is_new'] else ''}"
            data-id="{tid_esc}"
            data-ep-keys='{ep_keys_json}'
            data-statuts='{statuts_json}'
            data-distance="{r['distance_km']}"
            data-fmt="{html.escape(','.join(r['fmt_all']))}"
            data-has-format="{has_fmt}"
            data-new="{str(r['is_new']).lower()}"
            data-tmc="{str(r['tmc']).lower()}"
            data-libelle="{html.escape(r['libelle'].lower())}"
            data-cat="{html.escape(r['cat'].lower())}"
            data-date-debut="{r['date_debut_iso']}"
            data-date-fin="{r['date_fin_iso']}"
            data-dept="{html.escape(r['dept'])}"
            data-road-km="{r['road_km'] if r['road_km'] is not None else ''}"
            data-road-min="{r['road_min'] if r['road_min'] is not None else ''}"
            data-lat="{r['geo_lat'] if r['geo_lat'] is not None else ''}"
            data-lng="{r['geo_lng'] if r['geo_lng'] is not None else ''}">
          <td data-sort="{html.escape(r['date_debut_sort'])}">{html.escape(r['dates'])}</td>
          <td class="col-first-seen">{html.escape(r.get('first_seen', ''))}</td>
          <td>{nom_link}</td>
          <td>{html.escape(r['cat'])}</td>
          <td data-sort="{r['fmt_sort']}">{fmt_badge}</td>
          <td>{r['epreuves']}</td>
          <td>{r['surfaces']}</td>
          <td>{html.escape(r['ville'])} <small class="text-muted">{html.escape(r['cp'])}</small></td>
          <td data-sort="{r['road_km'] if r['road_km'] is not None else r['distance_km']}">{html.escape(r['distance_raw'])}{f'<br><small class="text-muted">/ {html.escape(r["ref_city"])}</small>' if r.get("ref_city") else ""}{f'<br><small class="text-success">🚗 {r["road_km"]} km · {r["road_min"]} min</small>' if r.get("road_km") is not None else ""}</td>
          <td class="text-center">{insc}</td>
          <td class="text-center">{paiem}</td>
          <td><small>{html.escape(r['juge_nom'])}<br>{tel_str}</small></td>
          <td><small>{email_link}</small></td>
          <td><small>{html.escape(r['ouverture'])}</small></td>
          <td class="text-center"><button class="fav-btn" data-id="{tid_esc}" onclick="toggleFav(this)">&#9734;</button></td>
        </tr>""")

    tbody        = "\n".join(tbody_lines)
    total        = len(rows)
    new_count    = sum(1 for r in rows if r["is_new"])
    fetched_str  = fetched_at or datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    ep_options_html = '<option value="">Toutes les épreuves</option>\n'
    for key, lbl in epreuve_options:
        ep_options_html += f'<option value="{html.escape(key)}">{html.escape(lbl)}</option>\n'

    # Chips épreuves
    import re as _re
    ep_chips_html = ""
    for key, lbl in epreuve_options:
        short = lbl
        for full, abbr in [("Simple Messieurs","SM"),("Simple Dames","SD"),("Double Messieurs","DM"),("Double Dames","DD"),("Double Mixte","DX")]:
            if full in lbl:
                rest = lbl.replace(full,"").strip()
                rest = _re.sub(r'\bans\b','',rest).strip()
                short = f"{abbr} {rest}"
                break
        ep_chips_html += (
            f'<label class="dept-chip">'
            f'<input type="checkbox" class="ep-chk" value="{html.escape(key)}" onchange="onEpChange()"> '
            f'{html.escape(short)}</label>'
        )

    # Chips surface (déduplication par label pour éviter "Dur" en double)
    _seen_surf: set[str] = set()
    surf_chips_parts = []
    for _code, (label, _color) in SURFACE_COLORS.items():
        key = label.lower()
        if key not in _seen_surf:
            _seen_surf.add(key)
            surf_chips_parts.append(
                f'<label class="dept-chip">'
                f'<input type="checkbox" class="surf-chk" value="{key}" onchange="onSurfChange()"> '
                f'{label}</label>'
            )
    surf_chips_html = "".join(surf_chips_parts)

    # Chips format F1-F7
    fmt_chips_html = "".join(
        f'<label class="dept-chip">'
        f'<input type="checkbox" class="fmt-chk" value="{i}" onchange="onFmtChange()"> '
        f'<span style="background:{FORMAT_COLORS[str(i)]};color:white;border-radius:2px;padding:0 3px;font-size:.8em;margin-right:2px">F{i}</span>'
        f'</label>'
        for i in range(1, 8)
    )
    fmt_chips_html += (
        '<label class="dept-chip" style="margin-left:6px">'
        '<input type="checkbox" id="chk-no-fmt" onchange="onFmtChange()"> + sans format</label>'
    )

    # Chips statut
    statut_chips_html = "".join(
        f'<label class="dept-chip">'
        f'<input type="checkbox" class="statut-chk" value="{code}" onchange="onStatutChange()"> '
        f'<span style="background:{color};color:white;border-radius:2px;padding:0 3px;font-size:.8em;margin-right:2px">●</span>'
        f'{html.escape(label)}</label>'
        for code, (color, label) in STATUT_CONFIG.items()
        if code != "autre"
    )

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdn.datatables.net/2.0.5/css/dataTables.bootstrap5.min.css">
  <link rel="stylesheet" href="https://cdn.datatables.net/buttons/3.0.2/css/buttons.bootstrap5.min.css">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    body {{ font-size: 0.875rem; background:#f4f6f9; }}
    h1   {{ font-size: 1.35rem; }}
    .tournament-link {{ font-weight:600; color:#0d6efd; text-decoration:none; }}
    .tournament-link:hover {{ text-decoration:underline; }}
    .ep-line  {{ margin-bottom:3px; white-space:nowrap; line-height:1.4; }}
    .ep-nature {{ color:#495057; font-weight:600; }}
    .ep-age    {{ color:#6c757d; font-size:.85em; }}
    .ep-range  {{ color:#0d6efd; }}
    .ep-tarif  {{ background:#e9ecef; border-radius:3px; padding:0 5px; font-weight:600; font-size:.85em; }}
    .badge        {{ font-size:.72em; }}
    .fmt-badge    {{ font-size:.85em; padding:.35em .6em; }}
    .fmt-ep-badge    {{ font-size:.75em; padding:.2em .45em; vertical-align:middle; opacity:.9; }}
    .statut-badge    {{ font-size:.72em; padding:.2em .45em; vertical-align:middle; }}
    .srf-badge       {{ font-size:.75em; }}
    .ep-comment      {{ border-top:1px solid #eee; margin-top:4px; padding-top:2px; }}
    table.dataTable td {{ vertical-align:middle; }}
    /* ── Filter bar v2 ───────────────────────────────────────────────────── */
    #filter-bar {{
      background: linear-gradient(145deg, #ffffff 0%, #f8faff 100%);
      border-radius: 16px;
      padding: 18px 20px 14px;
      margin-bottom: 16px;
      box-shadow: 0 2px 16px rgba(13,110,253,.07), 0 1px 4px rgba(0,0,0,.04);
      border: 1px solid rgba(13,110,253,.1);
    }}
    #filter-search {{
      border-radius: 10px !important;
      border: 1.5px solid #dee2e6 !important;
      padding-left: 34px !important;
      height: 36px !important;
      font-size: .87em !important;
      transition: border-color .2s, box-shadow .2s !important;
      background: white !important;
    }}
    #filter-search:focus {{
      border-color: #0d6efd !important;
      box-shadow: 0 0 0 3px rgba(13,110,253,.12) !important;
    }}
    .toggle-pill {{
      display: inline-flex; align-items: center; gap: 5px;
      padding: 5px 12px; border-radius: 20px;
      cursor: pointer; font-size: .8em; font-weight: 500;
      border: 1.5px solid #dee2e6; background: white;
      transition: all .15s; user-select: none; white-space: nowrap;
      line-height: 1.3;
    }}
    .toggle-pill:hover {{ border-color: #adb5bd; background: #f8f9fa; }}
    .toggle-pill:has(input:checked) {{ background: #0d6efd; color: white; border-color: #0d6efd; }}
    .toggle-pill.pill-muted:has(input:checked)   {{ background: #6c757d; border-color: #6c757d; }}
    .toggle-pill.pill-danger:has(input:checked)  {{ background: #dc3545; border-color: #dc3545; }}
    .toggle-pill.pill-warning:has(input:checked) {{ background: #fd7e14; border-color: #fd7e14; color: white; }}
    .toggle-pill.pill-success:has(input:checked) {{ background: #198754; border-color: #198754; }}
    .toggle-pill.pill-gold:has(input:checked)    {{ background: #d97706; border-color: #d97706; }}
    .toggle-pill input {{ display: none; }}
    .filter-dropdown-btn {{
      border-radius: 10px !important; border: 1.5px solid #dee2e6 !important;
      font-size: .8em !important; font-weight: 500 !important;
      padding: 5px 11px !important; background: white !important;
      color: #495057 !important; transition: all .15s !important;
      white-space: nowrap;
    }}
    .filter-dropdown-btn:hover {{ border-color: #adb5bd !important; background: #f8f9fa !important; }}
    .filter-dropdown-btn.active-filter {{
      background: #e8f0fe !important; border-color: #0d6efd !important; color: #0d6efd !important;
    }}
    .filter-select-sm {{
      border-radius: 10px !important; border: 1.5px solid #dee2e6 !important;
      font-size: .8em !important; padding: 5px 28px 5px 10px !important;
      height: 32px !important; background: white !important; color: #495057 !important;
    }}
    .filter-select-sm:focus {{ border-color: #0d6efd !important; box-shadow: 0 0 0 3px rgba(13,110,253,.12) !important; }}
    .filter-divider {{ width:1px; height:22px; background:#e5e7eb; flex-shrink:0; }}
    .filter-section-lbl {{
      font-size: .68em; font-weight: 700; color: #9ca3af;
      text-transform: uppercase; letter-spacing: .06em; margin-bottom: 5px;
    }}
    #advanced-toggle {{
      cursor: pointer; font-size: .78em; color: #9ca3af;
      user-select: none; text-decoration: none; display: inline-flex;
      align-items: center; gap: 4px; border: none; background: none; padding: 0;
      transition: color .15s;
    }}
    #advanced-toggle:hover {{ color: #0d6efd; }}
    #advanced-filters {{
      border-top: 1px solid #e9ecef; margin-top: 12px; padding-top: 12px;
    }}
    .stat-card  {{ border-radius: 20px; padding: 6px 16px; color: white;
                   display: inline-block; font-weight: 600; font-size: .82em; }}
    .dt-buttons {{ margin-bottom: 8px; }}
    .fav-btn {{ background:none; border:none; cursor:pointer; font-size:1.15em;
               padding:0 3px; color:#ccc; line-height:1; transition:color .15s; }}
    .fav-btn.fav-active {{ color:#f39c12; }}
    .dept-group {{ display:flex; align-items:center; flex-wrap:wrap; gap:3px; font-size:.8em; }}
    .dept-ligue-btn {{ font-size:.72em; white-space:nowrap; user-select:none; }}
    .dept-ligue-btn:hover {{ opacity:.8; }}
    .dept-chips {{ display:inline-flex; flex-wrap:wrap; gap:2px; margin-left:4px; }}
    .dept-chip {{ display:inline-flex; align-items:center; gap:2px; padding:1px 5px;
                 border:1px solid #dee2e6; border-radius:3px; cursor:pointer;
                 background:#f8f9fa; white-space:nowrap; }}
    .dept-chip:has(input:checked) {{ background:#0d6efd; color:white; border-color:#0d6efd; }}
    .dept-chip input {{ display:none; }}
    .multi-panel {{ position:absolute; z-index:200; background:white; border:1px solid #dee2e6; border-radius:10px; padding:10px 12px; box-shadow:0 6px 20px rgba(0,0,0,.12); min-width:220px; max-width:420px; max-height:280px; overflow-y:auto; }}
    /* ── Vue onglets ──────────────────────────────────────────────────────── */
    .view-tab {{ transition:all .15s; }}
    /* ── Calendrier ──────────────────────────────────────────────────────── */
    .cal-grid {{ display:grid; grid-template-columns:repeat(7,1fr); gap:3px; }}
    .cal-dow  {{ text-align:center; font-weight:600; font-size:.78em; padding:5px 2px;
                background:#e9ecef; border-radius:4px; }}
    .cal-cell {{ min-height:78px; border:1px solid #dee2e6; border-radius:5px;
                padding:4px 5px; cursor:pointer; transition:background .12s; }}
    .cal-cell:hover:not(.cal-empty) {{ background:#f0f7ff; }}
    .cal-has-events {{ background:#f5faff; border-color:#bee3f8; }}
    .cal-today  {{ border:2px solid #e74c3c !important; }}
    .cal-empty  {{ border:none !important; background:transparent !important; cursor:default; }}
    .cal-day-num {{ font-size:.82em; font-weight:600; color:#6c757d; line-height:1.2; }}
    .cal-today .cal-day-num {{ color:#e74c3c; }}
    .cal-count  {{ font-weight:700; font-size:1.05em; color:#0d6efd; line-height:1.3; }}
    .cal-chip   {{ font-size:.67em; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
                  padding:1px 3px; border-radius:2px; margin-top:1px; }}
    .cal-chip-more {{ font-size:.67em; color:#6c757d; margin-top:1px; }}
    .cal-panel  {{ border:1px solid #dee2e6; border-radius:6px; padding:14px 16px;
                  background:#f8f9fa; margin-top:10px; }}
    /* ── Gantt ────────────────────────────────────────────────────────────── */
    .gantt-row   {{ display:flex; align-items:center; border-bottom:1px solid #f0f0f0; min-height:26px; }}
    .gantt-row:hover {{ background:#f8f9fa; }}
    .gantt-label {{ width:210px; min-width:210px; font-size:.75em; overflow:hidden;
                   text-overflow:ellipsis; white-space:nowrap; padding-right:8px;
                   color:#495057; text-align:right; }}
    .gantt-bar   {{ position:absolute; height:16px; top:3px; border-radius:3px;
                   cursor:pointer; opacity:.82; transition:opacity .12s; }}
    .gantt-bar:hover {{ opacity:1; box-shadow:0 2px 5px rgba(0,0,0,.2); }}
    .gantt-today {{ position:absolute; top:0; bottom:0; width:2px;
                   background:#e74c3c; opacity:.55; pointer-events:none; z-index:5; }}
    /* ── Carte ────────────────────────────────────────────────────────────── */
    #view-map-wrap {{ position:relative; }}
    #view-map {{ height:600px; border-radius:8px; overflow:hidden; }}
    #view-map-wrap.map-fs {{ position:fixed !important; top:0; left:0; right:0; bottom:0;
                             z-index:9999; background:#fff; padding:0; }}
    #view-map-wrap.map-fs #view-map {{ height:100vh !important; border-radius:0; }}
    #map-fs-btn {{ position:absolute; top:10px; right:10px; z-index:10000;
                  background:white; border:2px solid #aaa; border-radius:5px;
                  padding:4px 10px; font-size:.82em; cursor:pointer;
                  box-shadow:0 1px 4px rgba(0,0,0,.2); }}
    #map-fs-btn:hover {{ background:#f0f0f0; }}
    .map-popup-btn {{ display:block; margin-top:8px; padding:5px 12px;
                     background:#0d6efd !important; color:#fff !important;
                     border-radius:4px; text-decoration:none !important;
                     font-size:.82em; font-weight:600; text-align:center; }}
    .map-popup-btn:hover {{ background:#0b5ed7 !important; color:#fff !important; }}
    .leaflet-popup-content {{ min-width:210px; }}
    .map-ep-line {{ font-size:.78em; color:#495057; white-space:nowrap;
                   overflow:hidden; text-overflow:ellipsis; }}
    /* Marqueur ville de référence */
    .map-ref-marker {{ width:28px !important; height:28px !important;
                       background:#0d6efd; border:3px solid white; border-radius:50%;
                       box-shadow:0 0 0 2px #0d6efd, 0 2px 8px rgba(0,0,0,.5);
                       display:flex; align-items:center; justify-content:center;
                       color:white; font-size:15px; line-height:1; font-weight:bold; }}
    /* Impression compacte avec abréviations (SM, SD…) */
    @media print {{
      .ep-range, .ep-tarif {{ display:none !important; }}
      .statut-badge, .fmt-ep-badge, .ep-comment {{ display:none !important; }}
      .ep-line {{ margin-bottom:0 !important; line-height:1.3 !important; }}
      table.dataTable td {{ padding:2px 4px !important; }}
      /* Remplace le texte long par l'abréviation */
      .ep-nature {{ font-size:0 !important; color:transparent !important; }}
      .ep-nature::after {{ content:attr(data-abbr); font-size:7pt; color:#495057; font-weight:600; }}
      .ep-age {{ font-size:0 !important; color:transparent !important; }}
      .ep-age::after {{ content:" " attr(data-abbr); font-size:7pt; color:#6c757d; }}
      /* Masquer les colonnes moins utiles en impression */
      #t th:nth-child(9), #t td:nth-child(9),
      #t th:nth-child(10), #t td:nth-child(10),
      #t th:nth-child(12), #t td:nth-child(12),
      #t th:nth-child(13), #t td:nth-child(13),
      #t th:nth-child(14), #t td:nth-child(14) {{ display:none !important; }}
    }}
  </style>
</head>
<body>
<div class="container-fluid py-3">

  <!-- Header -->
  <div class="d-flex align-items-center mb-3 gap-3 flex-wrap">
    <h1 class="mb-0">🎾 {html.escape(title)}</h1>
    <span class="stat-card" style="background:#0d6efd">{total} tournois</span>
    {'<span class="stat-card" style="background:#dc3545">' + str(new_count) + ' nouveaux</span>' if new_count else ''}
    <small class="text-muted ms-auto">Mis à jour : {html.escape(fetched_str)}</small>
  </div>

  <!-- Filter bar v2 -->
  <div id="filter-bar">

    <!-- Ligne 1 : Recherche + Ligue + Comités + toggles rapides + reset -->
    <div class="d-flex gap-2 align-items-center mb-3 flex-wrap">

      <!-- Recherche -->
      <div style="position:relative; flex:1; min-width:200px; max-width:320px">
        <span style="position:absolute;left:10px;top:50%;transform:translateY(-50%);color:#9ca3af;pointer-events:none;font-size:.9em">🔍</span>
        <input type="search" class="form-control" id="filter-search"
               placeholder="Nom, juge, ville, club…"
               oninput="applySearch(this.value)">
      </div>

      <!-- Ligue -->
      <select class="form-select filter-select-sm" id="filter-ligue"
              style="min-width:155px;max-width:200px" onchange="onLigueChange()">
        <option value="">Toutes les ligues</option>
        <option>Auvergne-Rhône-Alpes</option>
        <option>Bourgogne-Franche-Comté</option>
        <option>Bretagne</option>
        <option>Centre-Val de Loire</option>
        <option>Corse</option>
        <option>Grand Est</option>
        <option>Hauts-de-France</option>
        <option>Île-de-France</option>
        <option>Normandie</option>
        <option>Nouvelle-Aquitaine</option>
        <option>Occitanie</option>
        <option>Pays de la Loire</option>
        <option>PACA</option>
      </select>

      <!-- Comités -->
      <div class="dropdown" style="position:relative">
        <button class="filter-dropdown-btn btn" id="dept-btn"
                data-bs-toggle="dropdown" data-bs-auto-close="outside"
                aria-expanded="false">
          📍 Comités ▾
        </button>
        <div class="dropdown-menu p-2" style="min-width:480px;max-height:320px;overflow-y:auto;border-radius:12px;box-shadow:0 6px 20px rgba(0,0,0,.12)">
          <div class="d-flex justify-content-between mb-1">
            <small class="text-muted fst-italic" style="font-size:.75em">Cliquez sur une ligue pour tout cocher</small>
            <button class="btn btn-xs btn-link p-0 text-danger" style="font-size:.75em" onclick="clearDepts()">Tout décocher</button>
          </div>
          <div id="dept-checkboxes">
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Auvergne-Rhône-Alpes')" style="cursor:pointer">Auvergne-Rhône-Alpes</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['01','03','15','26','38','42','43','63','69','73','74'])}</span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Bourgogne-Franche-Comté')" style="cursor:pointer">Bourgogne-Franche-Comté</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['21','25','39','58','70','71','89','90'])}</span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Bretagne')" style="cursor:pointer">Bretagne</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['22','29','35','56'])}</span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Centre-Val de Loire')" style="cursor:pointer">Centre-Val de Loire</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['18','28','36','37','41','45'])}</span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Corse')" style="cursor:pointer">Corse</span>
              <span class="dept-chips"><label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-20" value="20" onchange="onDeptChange()"> 20 (2A/2B)</label></span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Grand Est')" style="cursor:pointer">Grand Est</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['08','10','51','52','54','55','57','67','68','88'])}</span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Hauts-de-France')" style="cursor:pointer">Hauts-de-France</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['02','59','60','62','80'])}</span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Île-de-France')" style="cursor:pointer">Île-de-France</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['75','77','78','91','92','93','94','95'])}</span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Normandie')" style="cursor:pointer">Normandie</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['14','27','50','61','76'])}</span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Nouvelle-Aquitaine')" style="cursor:pointer">Nouvelle-Aquitaine</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['16','17','19','23','24','33','40','47','64','79','86','87'])}</span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Occitanie')" style="cursor:pointer">Occitanie</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['09','11','12','30','31','32','34','46','48','65','66','81','82'])}</span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('Pays de la Loire')" style="cursor:pointer">Pays de la Loire</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['44','49','53','72','85'])}</span></div>
            <div class="dept-group mb-1"><span class="badge bg-secondary dept-ligue-btn" onclick="selectLigueGroup('PACA')" style="cursor:pointer">PACA</span>
              <span class="dept-chips">{''.join(f'<label class="dept-chip"><input type="checkbox" class="dept-chk" id="dept-chk-{d}" value="{d}" onchange="onDeptChange()"> {d}</label>' for d in ['04','05','06','13','83','84'])}</span></div>
          </div>
        </div>
      </div>

      <div class="filter-divider d-none d-lg-block"></div>

      <!-- Toggles rapides -->
      <label class="toggle-pill pill-muted">
        <input type="checkbox" id="chk-hide-past" checked onchange="applyFilters()">
        Terminés masqués
      </label>
      <label class="toggle-pill pill-danger">
        <input type="checkbox" id="chk-new" onchange="applyFilters()">
        🆕 Nouveaux
      </label>
      <label class="toggle-pill pill-warning">
        <input type="checkbox" id="chk-tmc" onchange="applyFilters()">
        TMC
      </label>
      <label class="toggle-pill pill-success">
        <input type="checkbox" id="chk-insc" onchange="applyFilters()">
        Inscr. en ligne
      </label>
      <label class="toggle-pill pill-gold">
        <input type="checkbox" id="chk-fav" onchange="applyFilters()">
        ⭐ Favoris
      </label>

      <!-- Reset + compteur -->
      <div class="ms-auto d-flex align-items-center gap-2">
        <span id="filter-count" class="text-muted" style="font-size:.78em;white-space:nowrap"></span>
        <button class="btn" style="border-radius:10px;border:1.5px solid #dee2e6;font-size:.78em;padding:5px 11px;background:white;color:#6c757d;white-space:nowrap" onclick="resetFilters()">✕ Réinitialiser</button>
      </div>
    </div>

    <!-- Ligne 2 : Filtres contenu + bouton Avancé -->
    <div class="d-flex gap-2 align-items-center flex-wrap">

      <div style="position:relative">
        <button class="filter-dropdown-btn btn" id="btn-ep"
                onclick="toggleMultiPanel('panel-ep','btn-ep')">
          Épreuves ▾</button>
        <div id="panel-ep" class="multi-panel" style="display:none">{ep_chips_html}</div>
      </div>

      <div style="position:relative">
        <button class="filter-dropdown-btn btn" id="btn-surf"
                onclick="toggleMultiPanel('panel-surf','btn-surf')">
          Surface ▾</button>
        <div id="panel-surf" class="multi-panel" style="display:none">{surf_chips_html}</div>
      </div>

      <div style="position:relative">
        <button class="filter-dropdown-btn btn" id="btn-fmt"
                onclick="toggleMultiPanel('panel-fmt','btn-fmt')">
          Format ▾</button>
        <div id="panel-fmt" class="multi-panel" style="display:none">{fmt_chips_html}</div>
      </div>

      <div style="position:relative">
        <button class="filter-dropdown-btn btn" id="btn-statut"
                onclick="toggleMultiPanel('panel-statut','btn-statut')">
          Statut ▾</button>
        <div id="panel-statut" class="multi-panel" style="display:none">{statut_chips_html}</div>
      </div>

      <button id="advanced-toggle" onclick="toggleAdvanced()">
        <span id="adv-arrow">▸</span> Filtres avancés
      </button>
    </div>

    <!-- Filtres avancés (repliés par défaut) -->
    <div id="advanced-filters" style="display:none">
      <div class="d-flex gap-3 align-items-end flex-wrap pt-1">

        <div>
          <div class="filter-section-lbl">Distances</div>
          <div class="d-flex gap-2">
            <input type="number" class="form-control form-control-sm" id="filter-distance"
                   placeholder="🔭 vol max km" style="width:120px;border-radius:8px" oninput="applyFilters()">
            <input type="number" class="form-control form-control-sm" id="filter-road-km"
                   placeholder="🚗 trajet km" style="width:115px;border-radius:8px" oninput="applyFilters()">
            <input type="number" class="form-control form-control-sm" id="filter-road-min"
                   placeholder="🕐 trajet min" style="width:115px;border-radius:8px" oninput="applyFilters()">
          </div>
        </div>

        <div>
          <div class="filter-section-lbl">Plage de dates</div>
          <div class="d-flex gap-2 align-items-center">
            <input type="date" class="form-control form-control-sm" id="filter-date-start"
                   style="width:148px;border-radius:8px" onchange="applyFilters()">
            <span style="color:#9ca3af;font-size:.8em">au</span>
            <input type="date" class="form-control form-control-sm" id="filter-date-end"
                   style="width:148px;border-radius:8px" onchange="applyFilters()">
          </div>
        </div>

        <div>
          <div class="filter-section-lbl">Exclusions</div>
          <div class="d-flex gap-2 align-items-center flex-wrap">
            <input type="text" class="form-control form-control-sm" id="filter-exclude"
                   placeholder="mots à exclure (séparés par espace)"
                   style="min-width:220px;border-radius:8px" oninput="applyFilters()">
            <label class="toggle-pill pill-success" style="font-size:.76em">
              <input type="checkbox" id="chk-hide-vert" onchange="applyFilters()"> Masquer Vert
            </label>
            <label class="toggle-pill pill-warning" style="font-size:.76em">
              <input type="checkbox" id="chk-hide-orange" onchange="applyFilters()"> Masquer Orange
            </label>
          </div>
        </div>

      </div>
    </div>

  </div>

  <!-- Onglets de vue -->
  <div class="d-flex gap-2 mb-2 align-items-center">
    <button class="btn btn-sm btn-primary view-tab" id="tab-table"
            onclick="showView('table')">📋 Tableau</button>
    <button class="btn btn-sm btn-outline-secondary view-tab" id="tab-cal"
            onclick="showView('calendar')">📅 Calendrier</button>
    <button class="btn btn-sm btn-outline-secondary view-tab" id="tab-gantt"
            onclick="showView('gantt')">📊 Gantt</button>
    <button class="btn btn-sm btn-outline-secondary view-tab" id="tab-vacs"
            onclick="showView('vacs')">🏖️ Vacs</button>
    <button class="btn btn-sm btn-outline-secondary view-tab" id="tab-map"
            onclick="showView('map')">🗺️ Carte</button>
    <button class="btn btn-sm btn-outline-warning view-tab" id="tab-derniers"
            onclick="showView('derniers')">🆕 Derniers</button>
    <small class="text-muted ms-2" id="view-info"></small>
  </div>

  <!-- Vue Calendrier -->
  <div id="view-calendar" style="display:none" class="bg-white rounded shadow-sm p-3"></div>

  <!-- Vue Gantt -->
  <div id="view-gantt" style="display:none" class="bg-white rounded shadow-sm p-3" style="overflow-x:auto"></div>

  <!-- Vue Vacances -->
  <div id="view-vacs" style="display:none" class="bg-white rounded shadow-sm p-3">
    <div id="vacs-container" class="text-center text-muted py-4">
      <span class="spinner-border spinner-border-sm me-2"></span>Chargement des vacances Zone C…
    </div>
  </div>

  <!-- Vue Carte -->
  <div id="view-map-wrap" style="display:none">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
      <label class="fw-semibold small" style="color:#495057;margin:0">📍 Ville de référence ★ :</label>
      <input type="text" id="map-ref-input" placeholder="ex: Vaires-sur-Marne"
             style="border:1px solid #ced4da;border-radius:4px;padding:3px 8px;font-size:.85em;width:200px"
             value="{ref_city}"
             onkeydown="if(event.key==='Enter')geocodeRefCity()">
      <button onclick="geocodeRefCity()" class="btn btn-sm btn-outline-primary">Localiser ★</button>
      <small class="text-muted" id="map-ref-status"></small>
    </div>
    <button id="map-fs-btn" onclick="toggleMapFullscreen()">⛶ Plein écran</button>
    <div id="view-map"></div>
  </div>

  <!-- Table -->
  <div id="view-table" class="bg-white rounded shadow-sm p-3">
    <table id="t" class="table table-hover table-striped" style="width:100%">
      <thead class="table-dark">
        <tr>
          <th>Dates</th>
          <th class="col-first-seen">_first_seen</th>
          <th>Tournoi</th>
          <th>Catégorie</th>
          <th>Format</th>
          <th>Épreuves</th>
          <th>Surface</th>
          <th>Ville</th>
          <th>Distance</th>
          <th>Inscr.</th>
          <th>Paiem.</th>
          <th>Juge / Tél</th>
          <th>Email</th>
          <th>Ouv. inscr.</th>
          <th>⭐</th>
        </tr>
      </thead>
      <tbody>{tbody}</tbody>
    </table>
  </div>
</div>

<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.datatables.net/2.0.5/js/dataTables.min.js"></script>
<script src="https://cdn.datatables.net/2.0.5/js/dataTables.bootstrap5.min.js"></script>
<script src="https://cdn.datatables.net/buttons/3.0.2/js/dataTables.buttons.min.js"></script>
<script src="https://cdn.datatables.net/buttons/3.0.2/js/buttons.bootstrap5.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.2.7/pdfmake.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.2.7/vfs_fonts.js"></script>
<script src="https://cdn.datatables.net/buttons/3.0.2/js/buttons.html5.min.js"></script>
<script src="https://cdn.datatables.net/buttons/3.0.2/js/buttons.print.min.js"></script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var dt;
var currentView = 'table';
var _REF_LAT = {ref_lat or 0};
var _REF_LNG = {ref_lng or 0};
var _REF_CITY = {json.dumps(ref_city or "")};
var _mapObj = null;
var _mapMarkers = null;
var calYear, calMonth;

$(function() {{
  $('[data-bs-toggle="tooltip"]').each(function() {{
    new bootstrap.Tooltip(this);
  }});

  // ── Custom DataTables row filter ──────────────────────────────────────────
  $.fn.dataTable.ext.search.push(function(settings, _data, index) {{
    var node = settings.aoData[index] && settings.aoData[index].nTr;
    if (!node) return true;
    var $tr = $(node);

    var checkedEpreuves = $('.ep-chk:checked').map(function() {{ return $(this).val(); }}).get();
    var maxDist  = parseFloat($('#filter-distance').val()) || null;
    var onlyNew  = $('#chk-new').prop('checked');
    var onlyTmc  = $('#chk-tmc').prop('checked');
    var onlyInsc = $('#chk-insc').prop('checked');
    var onlyFav  = $('#chk-fav').prop('checked');

    // ── Filtre comités/départements ───────────────────────────────────────────
    var checkedDepts = $('.dept-chk:checked').map(function() {{ return $(this).val(); }}).get();
    if (checkedDepts.length > 0) {{
      var dept = $tr.attr('data-dept') || '';
      if (checkedDepts.indexOf(dept) === -1) return false;
    }}

    if (checkedEpreuves.length > 0) {{
      var keys = JSON.parse($tr.attr('data-ep-keys') || '[]');
      if (keys.length === 0) return false; // Épreuves non enrichies → on masque quand filtre actif
      if (!checkedEpreuves.some(function(e) {{ return keys.indexOf(e) !== -1; }})) return false;
    }}
    if (maxDist !== null && (parseFloat($tr.attr('data-distance')) || 0) > maxDist) return false;

    var maxRoadKm  = parseFloat($('#filter-road-km').val())  || null;
    var maxRoadMin = parseFloat($('#filter-road-min').val()) || null;
    if (maxRoadKm !== null) {{
      var roadKm = $tr.attr('data-road-km');
      if (!roadKm || parseFloat(roadKm) > maxRoadKm) return false;
    }}
    if (maxRoadMin !== null) {{
      var roadMin = $tr.attr('data-road-min');
      if (!roadMin || parseFloat(roadMin) > maxRoadMin) return false;
    }}

    var checkedSurfs = $('.surf-chk:checked').map(function() {{ return $(this).val(); }}).get();
    if (checkedSurfs.length > 0) {{
      var cellSurf = $tr.find('td:nth-child(6)').text().toLowerCase();
      if (!checkedSurfs.some(function(s) {{ return cellSurf.indexOf(s) !== -1; }})) return false;
    }}
    var checkedFmts = $('.fmt-chk:checked').map(function() {{ return $(this).val(); }}).get();
    var inclNoFmt = $('#chk-no-fmt').prop('checked');
    if (checkedFmts.length > 0 || inclNoFmt) {{
      var fmts      = ($tr.attr('data-fmt') || '').split(',').filter(Boolean);
      var hasFmt    = $tr.attr('data-has-format') === 'true';
      var hasMatch  = checkedFmts.some(function(f) {{ return fmts.indexOf(f) !== -1; }});
      if (!hasMatch && !(inclNoFmt && !hasFmt)) return false;
    }}
    // ── Masquer tournois terminés (date de fin dépassée) ─────────────────────
    if ($('#chk-hide-past').prop('checked')) {{
      var dateFin = $tr.attr('data-date-fin') || '';
      if (dateFin) {{
        var todayStr = (function() {{
          var d = new Date();
          return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
        }})();
        if (dateFin < todayStr) return false;
      }}
    }}

    var checkedStatuts = $('.statut-chk:checked').map(function() {{ return $(this).val(); }}).get();
    if (checkedStatuts.length > 0) {{
      var statuts = JSON.parse($tr.attr('data-statuts') || '[]');
      if (!checkedStatuts.some(function(s) {{ return statuts.indexOf(s) !== -1; }})) return false;
    }}

    if (onlyNew  && $tr.attr('data-new') !== 'true')  return false;
    if (onlyTmc  && $tr.attr('data-tmc') !== 'true')  return false;
    if (onlyInsc && $tr.find('td:nth-child(9)').text().trim() !== '✅') return false;
    if (onlyFav) {{
      var favs = JSON.parse(localStorage.getItem('tenup_favs') || '{{}}');
      if (!favs[$tr.attr('data-id')]) return false;
    }}

    // ── Masquer Vert / Orange (nom + catégorie uniquement) ────────────────
    var libelle = $tr.attr('data-libelle') || '';
    var cat     = $tr.attr('data-cat') || '';
    var nameCat = libelle + ' ' + cat;
    if ($('#chk-hide-vert').prop('checked')   && nameCat.indexOf('vert')   !== -1) return false;
    if ($('#chk-hide-orange').prop('checked') && nameCat.indexOf('orange') !== -1) return false;

    // ── Exclure mots personnalisés (nom + catégorie) ──────────────────────
    var excludeRaw = $('#filter-exclude').val().trim().toLowerCase();
    if (excludeRaw) {{
      var words = excludeRaw.split(/\\s+/).filter(Boolean);
      for (var wi = 0; wi < words.length; wi++) {{
        if (nameCat.indexOf(words[wi]) !== -1) return false;
      }}
    }}

    // ── Filtre plage de dates ─────────────────────────────────────────────
    var fStart = $('#filter-date-start').val();
    var fEnd   = $('#filter-date-end').val();
    if (fStart || fEnd) {{
      var tStart = $tr.attr('data-date-debut') || '';
      var tEnd   = $tr.attr('data-date-fin')   || '';
      if (fEnd   && tStart && tStart > fEnd)   return false;
      if (fStart && tEnd   && tEnd   < fStart) return false;
    }}

    return true;
  }});

// ── Export PDF : mise en forme personnalisée ─────────────────────────────────
function pdfCustomize(doc) {{
  // IMPORTANT : on fusionne (et non remplace) defaultStyle pour préserver la police pdfmake
  doc.defaultStyle = Object.assign(doc.defaultStyle || {{}}, {{ fontSize: 8 }});
  // Recherche robuste de la table (peut être doc.content[0] ou [1] selon DataTables)
  var tbl = null;
  for (var ci = 0; ci < doc.content.length; ci++) {{
    if (doc.content[ci] && doc.content[ci].table) {{ tbl = doc.content[ci]; break; }}
  }}
  if (!tbl) return;
  // 6 colonnes : Dates | Tournoi(fixe 35c) | Épreuves(nested) | Surface | Ville* | Distance
  // Épreuves = nested table 5 sous-colonnes : ep(38) | range(46) | tarif(17) | statut(22) | fmt(17)
  tbl.table.widths = [50, 155, 170, 50, '*', 90];
  var FC = {{'1':'#c0392b','2':'#e67e22','3':'#f39c12','4':'#27ae60','5':'#2980b9','6':'#8e44ad','7':'#7f8c8d'}};
  var SC = {{'TB':'#c0392b','TA':'#e67e22','R':'#2980b9','BP':'#7f8c8d','D':'#95a5a6','G':'#27ae60','M':'#8e44ad','?':'#bdc3c7'}};
  var SSCOLOR = {{'Ouv':'#27ae60','Bient':'#2980b9','Att':'#e67e22','Att+':'#d35400',
    'Clot':'#c0392b','HB':'#7f8c8d','HL':'#95a5a6','Inscr':'#1abc9c','Inelig':'#e74c3c','?':'#bdc3c7'}};
  tbl.table.body.forEach(function(row, ri) {{
    if (ri === 0) {{
      row.forEach(function(c) {{ if (c && typeof c === 'object') {{ c.fillColor = '#343a40'; c.color = '#fff'; }} }});
      return;
    }}
    // Épreuves (index 2) : nested table pipe-séparé "SM 13/14|NC-30|10€|HL|F2"
    var epRaw = typeof row[2] === 'string' ? row[2] : ((row[2] || {{}}).text || '');
    if (epRaw && epRaw.indexOf('|') !== -1) {{
      var epBody = [];
      epRaw.split('\\n').forEach(function(line) {{
        var p    = line.split('|');
        var ep   = p[0]||''; var rng = p[1]||''; var tar = p[2]||'';
        var ss   = p[3]||''; var fTk = p[4]||'';
        var fClr = (fTk && fTk.length > 1) ? (FC[fTk[1]]||'#333') : '#333';
        var sClr = SSCOLOR[ss] || '#333';
        epBody.push([
          {{ text: ep,  fontSize:8, noWrap:true }},
          {{ text: rng, fontSize:8, noWrap:true }},
          {{ text: tar, fontSize:8, noWrap:true }},
          {{ text: ss,  fontSize:8, color: ss  ? sClr : '#333', bold: !!ss,  noWrap:true }},
          {{ text: fTk, fontSize:8, color: fTk ? fClr : '#333', bold: !!fTk, noWrap:true }}
        ]);
      }});
      row[2] = {{ table: {{ widths:[38,46,17,22,17], body:epBody }}, layout: {{
        hLineWidth: function() {{ return 0; }},
        vLineWidth: function(i, node) {{ return (i > 0 && i < node.table.widths.length) ? 0.5 : 0; }},
        vLineColor: function() {{ return '#adb5bd'; }},
        paddingLeft:  function(i) {{ return i === 0 ? 0 : 3; }},
        paddingRight: function(i, node) {{ return i === node.table.widths.length-1 ? 0 : 3; }},
        paddingTop:    function() {{ return 1; }},
        paddingBottom: function() {{ return 1; }}
      }} }};
    }}
    // Surface (index 3) : abréviations colorées, pas de retour à la ligne
    var srfRaw = typeof row[3] === 'string' ? row[3] : ((row[3] || {{}}).text || '');
    if (srfRaw && srfRaw !== '\u2014') {{
      var srfContent = [];
      srfRaw.split('/').forEach(function(a, si) {{
        if (si > 0) srfContent.push({{ text: ' ' }});
        var abbr = a.trim();
        srfContent.push({{ text: abbr, color: SC[abbr] || '#666', bold: true }});
      }});
      row[3] = {{ text: srfContent, noWrap: true }};
    }}
    // Distance (index 5) : pas de retour à la ligne
    var distRaw = typeof row[5] === 'string' ? row[5] : ((row[5] || {{}}).text || '');
    if (distRaw && distRaw !== '\u2014') {{
      row[5] = {{ text: distRaw, noWrap: true }};
    }}
  }});
}}

  dt = $('#t').DataTable({{
    pageLength: 25,
    lengthMenu: [[25, 50, 100, -1], [25, 50, 100, "Tout"]],
    order: [[0, 'asc']],
    language: {{ url: 'https://cdn.datatables.net/plug-ins/2.0.5/i18n/fr-FR.json' }},
    columnDefs: [
      {{ targets: [3,4,6,9,10], searchable: false }},
      {{ targets: [4,8], type: 'num' }},
      {{ targets: [14], orderable: false, searchable: false }},
      {{ targets: ['.col-first-seen'], visible: false, searchable: false,
         render: function(data, type, row) {{
           if (type === 'display' && data) {{
             try {{
               var d = new Date(data);
               var day = String(d.getDate()).padStart(2,'0');
               var mon = String(d.getMonth()+1).padStart(2,'0');
               var h   = String(d.getHours()).padStart(2,'0');
               var m   = String(d.getMinutes()).padStart(2,'0');
               return '<span style="font-size:.78em;white-space:nowrap;line-height:1.5">'
                    + day+'/'+mon+'<br><span style="color:#6c757d">'+h+':'+m+'</span></span>';
             }} catch(e) {{ return data || '—'; }}
           }}
           return data;
         }}
      }},
    ],
    dom: '<"row"<"col-sm-6"B><"col-sm-6"l>>rtip',
    buttons: [
      {{ extend:'excelHtml5', text:'📥 Excel', className:'btn-sm btn-outline-success',
         exportOptions:{{ columns:':visible' }} }},
      {{ extend:'csvHtml5',   text:'📄 CSV',   className:'btn-sm btn-outline-secondary',
         exportOptions:{{ columns:':visible' }} }},
      {{ text:'🖨 Print', className:'btn-sm btn-outline-secondary',
         action: function() {{ window.print(); }} }},
      {{ extend:'pdfHtml5', text:'📑 PDF', className:'btn-sm btn-outline-danger',
         orientation:'landscape', pageSize:'A4',
         exportOptions:{{
           columns:[0,2,5,6,7,8],
           format:{{
             body: function(data, row, column, node) {{
               // Dates (col 0) : "27/04/2026 → 29/04/2026" → deux lignes, sans flèche
               if (column === 0) {{
                 var txt = $('<div>').html(data).text().replace(/\\s+/g,' ').trim();
                 var parts = txt.split(/\\s*[→>]\\s*/);
                 if (parts.length >= 2 && parts[0].trim() !== parts[1].trim()) {{
                   return parts[0].trim() + '\\n' + parts[1].trim();
                 }}
                 return parts[0].trim();
               }}
               // Tournoi (col 2) : tronqué à 35 caractères
               if (column === 2) {{
                 var txt = $('<div>').html(data).text().replace(/\\s+/g,' ').trim();
                 return txt.length > 35 ? txt.substring(0, 35) + '\u2026' : txt;
               }}
               // Épreuves (col 5) : pipe-séparé → "SM 13/14|NC-30|10€|HL|F2"
               // BUG FIX : on lit les filtres actifs (pas le css display) car DataTables
               // rend toutes les lignes visibles lors de l'export, même les pages 2+
               if (column === 5) {{
                 var SSHORT = {{'ouvert':'Ouv','bientot':'Bient','attente':'Att',
                   'inscrit_attente':'Att+','cloture':'Clot','hors_bornes':'HB',
                   'impossible':'HL','deja_inscrit':'Inscr','ineligible':'Inelig','autre':'?'}};
                 var checkedEps  = $('.ep-chk:checked').map(function()  {{ return $(this).val(); }}).get();
                 var checkedFmts = $('.fmt-chk:checked').map(function() {{ return $(this).val(); }}).get();
                 var lines = [];
                 $(node).find('.ep-line').each(function() {{
                   var epKey = $(this).attr('data-ep-key') || '';
                   var fmt   = $(this).attr('data-fmt')    || '';
                   if (checkedEps.length  > 0 && epKey && checkedEps.indexOf(epKey)   === -1) return;
                   if (checkedFmts.length > 0 && fmt   && checkedFmts.indexOf(fmt)    === -1) return;
                   var nat   = $(this).find('.ep-nature').attr('data-abbr') || $(this).find('.ep-nature').text().trim();
                   var age   = $(this).find('.ep-age').attr('data-abbr')    || $(this).find('.ep-age').text().trim();
                   var range = $(this).find('.ep-range').text().trim().replace(/\\s*\u2192\\s*/g, '-');
                   var tarif = $(this).find('.ep-tarif').text().trim();
                   var sc    = $(this).find('.statut-badge').attr('data-statut') || '';
                   var ss    = SSHORT[sc] || '';
                   if (nat) {{
                     var ep  = nat + (age ? ' '+age : '');
                     var rng = (range && range !== '?-?') ? range : '';
                     var tar = (tarif && tarif !== '0\u20ac')  ? tarif : '';
                     lines.push([ep, rng, tar, ss, fmt ? 'F'+fmt : ''].join('|'));
                   }}
                 }});
                 return lines.join('\\n') || '\u2014';
               }}
               // Surfaces (col 6) : abréviations colorées
               if (column === 6) {{
                 var SABBR = {{'terre battue':'TB','terre artificielle':'TA','résine':'R','béton poreux':'BP','dur':'D','gazon':'G','moquette':'M','autre':'?'}};
                 var abbrs = $(node).find('.srf-badge').map(function() {{
                   return SABBR[$(this).text().trim().toLowerCase()] || $(this).text().trim().substring(0,2).toUpperCase();
                 }}).get();
                 return abbrs.join('/') || '—';
               }}
               // Distance (col 8) : "27.1 km / 36 min" (route) ou "24.5 km" (vol d'oiseau)
               if (column === 8) {{
                 var $tr = $(node).closest('tr');
                 var rKm  = $tr.attr('data-road-km');
                 var rMin = $tr.attr('data-road-min');
                 if (rKm && rMin) return rKm + ' km / ' + rMin + ' min';
                 var dKm = $tr.attr('data-distance');
                 return dKm ? dKm + ' km' : '—';
               }}
               return $('<div>').html(data).text().replace(/\\s+/g,' ').trim();
             }}
           }}
         }},
         customize: pdfCustomize
      }},
    ],
    drawCallback: function() {{
      restoreFavs();
      applyEpLineFilter();
      var n = dt.page.info().recordsDisplay;
      $('#filter-count').text(n + ' affiché(s)');
      $('#view-info').text(n + ' tournois dans la vue');
      if (currentView === 'calendar') renderCalendar();
      if (currentView === 'gantt')    renderGantt();
      if (currentView === 'map')      renderMap();
    }}
  }});

  // Close multi-panels when clicking outside
  $(document).on('click.multiPanel', function(e) {{
    if (!$(e.target).closest('.multi-panel, [id^="btn-ep"], [id^="btn-surf"], [id^="btn-fmt"], [id^="btn-statut"]').length) {{
      $('.multi-panel').hide();
    }}
  }});
}});

function applyFilters() {{
  if (dt) dt.draw();
}}

// ── Recherche texte (toutes colonnes via DataTables) ─────────────────────────
function applySearch(val) {{
  if (dt) dt.search(val).draw();
}}

// ── Ligue → Comités ──────────────────────────────────────────────────────────
var LIGUES = {{
  "Auvergne-Rhône-Alpes":    ["01","03","15","26","38","42","43","63","69","73","74"],
  "Bourgogne-Franche-Comté": ["21","25","39","58","70","71","89","90"],
  "Bretagne":                ["22","29","35","56"],
  "Centre-Val de Loire":     ["18","28","36","37","41","45"],
  "Corse":                   ["20"],
  "Grand Est":               ["08","10","51","52","54","55","57","67","68","88"],
  "Hauts-de-France":         ["02","59","60","62","80"],
  "\u00cele-de-France":      ["75","77","78","91","92","93","94","95"],
  "Normandie":               ["14","27","50","61","76"],
  "Nouvelle-Aquitaine":      ["16","17","19","23","24","33","40","47","64","79","86","87"],
  "Occitanie":               ["09","11","12","30","31","32","34","46","48","65","66","81","82"],
  "Pays de la Loire":        ["44","49","53","72","85"],
  "PACA":                    ["04","05","06","13","83","84"]
}};

function onLigueChange() {{
  var ligue = $('#filter-ligue').val();
  $('.dept-chk').prop('checked', false);
  if (ligue && LIGUES[ligue]) {{
    LIGUES[ligue].forEach(function(d) {{
      $('#dept-chk-' + d).prop('checked', true);
    }});
  }}
  updateDeptBtn();
  applyFilters();
}}

function selectLigueGroup(ligue) {{
  if (LIGUES[ligue]) {{
    var allChecked = LIGUES[ligue].every(function(d) {{
      return $('#dept-chk-' + d).prop('checked');
    }});
    LIGUES[ligue].forEach(function(d) {{
      $('#dept-chk-' + d).prop('checked', !allChecked);
    }});
    updateDeptBtn();
    applyFilters();
  }}
}}

function onDeptChange() {{
  // Clear ligue select when manually picking depts
  $('#filter-ligue').val('');
  updateDeptBtn();
  applyFilters();
}}

function clearDepts() {{
  $('.dept-chk').prop('checked', false);
  $('#filter-ligue').val('');
  updateDeptBtn();
  applyFilters();
}}

function updateDeptBtn() {{
  var checked = $('.dept-chk:checked').map(function() {{ return $(this).val(); }}).get();
  var btn = $('#dept-btn');
  if (checked.length === 0) {{
    btn.text('Tous les comités').removeClass('btn-primary').addClass('btn-outline-secondary');
  }} else {{
    btn.text(checked.join(', ')).removeClass('btn-outline-secondary').addClass('btn-primary');
  }}
}}

function applyEpLineFilter() {{
  var checked     = $('.ep-chk:checked').map(function() {{ return $(this).val(); }}).get();
  var checkedFmts = $('.fmt-chk:checked').map(function() {{ return $(this).val(); }}).get();
  $('#ep-line-filter-style').remove();
  var css = '';
  if (checked.length > 0) {{
    var notSel = checked.map(function(k) {{ return ':not([data-ep-key="' + k + '"])'; }}).join('');
    css += '.ep-line' + notSel + ' {{ display:none !important; }}';
  }}
  if (checkedFmts.length > 0) {{
    // Hide ep-lines and FORMAT column badges that don't match selected formats
    var fmtNotSel = checkedFmts.map(function(f) {{ return ':not([data-fmt="' + f + '"])'; }}).join('');
    css += ' .ep-line:not([data-fmt=""])' + fmtNotSel + ' {{ display:none !important; }}';
    css += ' .fmt-badge' + fmtNotSel + ' {{ display:none !important; }}';
  }}
  if (css) {{ $('<style id="ep-line-filter-style">').text(css).appendTo('head'); }}
}}

// ── Favorites (stored in localStorage) ───────────────────────────────────────
function toggleFav(btn) {{
  var id   = btn.getAttribute('data-id');
  var favs = JSON.parse(localStorage.getItem('tenup_favs') || '{{}}');
  if (favs[id]) {{
    delete favs[id];
    btn.textContent = '\u2606';
    btn.classList.remove('fav-active');
  }} else {{
    favs[id] = true;
    btn.textContent = '\u2605';
    btn.classList.add('fav-active');
  }}
  localStorage.setItem('tenup_favs', JSON.stringify(favs));
  if ($('#chk-fav').prop('checked')) dt.draw();
}}

function toggleFavMap(btn) {{
  var id = btn.getAttribute('data-id');
  var favs = {{}};
  try {{ favs = JSON.parse(localStorage.getItem('tenup_favs') || '{{}}'); }} catch(e) {{}}
  if (favs[id]) {{
    delete favs[id];
    btn.textContent = '\u2606';
    btn.style.color = '#bbb';
  }} else {{
    favs[id] = true;
    btn.textContent = '\u2605';
    btn.style.color = '#f39c12';
  }}
  localStorage.setItem('tenup_favs', JSON.stringify(favs));
  // Sync bouton dans le tableau
  var $row = $('.fav-btn[data-id="' + id + '"]');
  if ($row.length) {{
    if (favs[id]) {{ $row.text('\u2605').addClass('fav-active'); }}
    else          {{ $row.text('\u2606').removeClass('fav-active'); }}
  }}
  if ($('#chk-fav').prop('checked')) dt.draw();
}}

function restoreFavs() {{
  var favs = JSON.parse(localStorage.getItem('tenup_favs') || '{{}}');
  $('.fav-btn').each(function() {{
    var id  = $(this).attr('data-id');
    var isFav = !!favs[id];
    $(this).text(isFav ? '\u2605' : '\u2606').toggleClass('fav-active', isFav);
  }});
}}

function resetFilters() {{
  $('#filter-distance, #filter-road-km, #filter-road-min, #filter-exclude').val('');
  $('#filter-date-start, #filter-date-end').val('');
  $('#filter-ligue').val('');
  $('.dept-chk').prop('checked', false);
  updateDeptBtn();
  $('#chk-new, #chk-tmc, #chk-insc, #chk-fav').prop('checked', false);
  $('#chk-hide-vert, #chk-hide-orange').prop('checked', false);
  $('#chk-hide-past').prop('checked', true);  // remet masquer-terminés coché par défaut
  $('#filter-search').val('');
  $('.ep-chk, .surf-chk, .fmt-chk, .statut-chk, #chk-no-fmt').prop('checked', false);
  $('#btn-ep').text('Épreuves ▾').removeClass('active-filter');
  $('#btn-surf').text('Surface ▾').removeClass('active-filter');
  $('#btn-fmt').text('Format ▾').removeClass('active-filter');
  $('#btn-statut').text('Statut ▾').removeClass('active-filter');
  applyEpLineFilter();
  if (dt) {{ dt.search('').draw(); }} else {{ applyFilters(); }}
}}

// ── Multi-select panels ───────────────────────────────────────────────────────
function toggleMultiPanel(panelId, btnId) {{
  var isOpen = $('#' + panelId).is(':visible');
  $('.multi-panel').hide();
  if (!isOpen) $('#' + panelId).show();
}}

function toggleAdvanced() {{
  var el = document.getElementById('advanced-filters');
  var arrow = document.getElementById('adv-arrow');
  var visible = el.style.display !== 'none';
  el.style.display = visible ? 'none' : 'block';
  arrow.textContent = visible ? '▸' : '▾';
}}

function updateMultiBtn(btnId, cls, allLabel) {{
  var n = $(cls + ':checked').length;
  var btn = $('#' + btnId);
  btn.text(n === 0 ? allLabel + ' ▾' : n + ' sél. ▾');
  btn.toggleClass('active-filter', n > 0);
}}

function onEpChange() {{
  updateMultiBtn('btn-ep', '.ep-chk', 'Épreuves');
  applyEpLineFilter();
  applyFilters();
}}

function onSurfChange() {{
  updateMultiBtn('btn-surf', '.surf-chk', 'Surface');
  applyFilters();
}}

function onFmtChange() {{
  updateMultiBtn('btn-fmt', '.fmt-chk', 'Format');
  applyEpLineFilter();
  applyFilters();
}}

function onStatutChange() {{
  updateMultiBtn('btn-statut', '.statut-chk', 'Statut');
  applyFilters();
}}

// ── Gestion des vues (Tableau / Calendrier / Gantt / Vacs / Carte) ──────────
function showView(view) {{
  // 'derniers' is a special sort on the table view
  var isDerniers = (view === 'derniers');
  var tableView = isDerniers ? 'table' : view;
  currentView = tableView;
  $('#view-table').toggle(tableView === 'table');
  $('#view-calendar').toggle(tableView === 'calendar');
  $('#view-gantt').toggle(tableView === 'gantt');
  $('#view-vacs').toggle(tableView === 'vacs');
  $('#view-map-wrap').toggle(tableView === 'map');
  $('.view-tab').removeClass('btn-primary btn-warning').addClass('btn-outline-secondary');
  var tabId = {{table:'tab-table', calendar:'tab-cal', gantt:'tab-gantt', vacs:'tab-vacs', map:'tab-map'}}[tableView] || 'tab-table';
  if (isDerniers) {{
    $('#tab-derniers').removeClass('btn-outline-secondary btn-outline-warning').addClass('btn-warning');
    dt.column('.col-first-seen').visible(true);
    $(dt.column('.col-first-seen').header()).text('Ajouté le');
    dt.order([[dt.column('.col-first-seen').index(), 'desc']]).draw();
  }} else {{
    dt.column('.col-first-seen').visible(false);
    $('#' + tabId).removeClass('btn-outline-secondary').addClass('btn-primary');
  }}
  if (tableView === 'calendar') {{ calYear = undefined; calMonth = undefined; renderCalendar(); }}
  if (tableView === 'gantt')    renderGantt();
  if (tableView === 'vacs')     renderVacs();
  if (tableView === 'map')      renderMap();
}}

// ── Extraction des données filtrées depuis DataTables ────────────────────────
function getFilteredData() {{
  var result = [];
  dt.rows({{ search: 'applied' }}).nodes().each(function(node) {{
    var $tr = $(node);
    var $link = $tr.find('a.tournament-link').first();
    result.push({{
      id:      $tr.attr('data-id') || '',
      nom:     $link.text().trim(),
      url:     $link.attr('href') || '',
      debut:   $tr.attr('data-date-debut') || '',
      fin:     $tr.attr('data-date-fin')   || '',
      fmt:     ($tr.attr('data-fmt') || '').split(',')[0] || '',
      fmtAll:  ($tr.attr('data-fmt') || '').split(',').filter(Boolean),
      ville:       $tr.find('td:eq(6)').contents().first().text().trim(),
      surfaceHtml: $tr.find('td:eq(5)').html() || '',
      statuts: $tr.attr('data-statuts') || '[]',
      epreuves: (function() {{
        var lines = [];
        var checkedEps  = $('.ep-chk:checked').map(function() {{ return $(this).val(); }}).get();
        var checkedFmts = $('.fmt-chk:checked').map(function() {{ return $(this).val(); }}).get();
        $tr.find('.ep-line').each(function() {{
          var epKey  = $(this).attr('data-ep-key') || '';
          var fmt    = $(this).attr('data-fmt')    || '';
          if (checkedEps.length  > 0 && epKey && checkedEps.indexOf(epKey)   === -1) return;
          if (checkedFmts.length > 0 && fmt   && checkedFmts.indexOf(fmt)    === -1) return;
          var nat    = $(this).find('.ep-nature').text().trim();
          var age    = $(this).find('.ep-age').text().trim();
          var statut = $(this).find('.statut-badge').attr('data-statut') || '';
          if (nat) lines.push({{ text: nat + (age ? ' ' + age : ''), fmt: fmt, statut: statut }});
        }});
        return lines;
      }})(),
      lat:     parseFloat($tr.attr('data-lat')) || 0,
      lng:     parseFloat($tr.attr('data-lng')) || 0,
      distKm:  parseFloat($tr.attr('data-distance')) || 0,
      roadKm:  $tr.attr('data-road-km') ? parseFloat($tr.attr('data-road-km')) : null,
      roadMin: $tr.attr('data-road-min') ? parseFloat($tr.attr('data-road-min')) : null,
    }});
  }});
  return result;
}}

var _FMT_COLORS = {{'1':'#c0392b','2':'#e67e22','3':'#f39c12','4':'#27ae60','5':'#2980b9','6':'#8e44ad','7':'#7f8c8d'}};
var _STATUT_CFG = {{'ouvert':['#27ae60','Ouvert'],'bientot':['#2980b9','Bientôt'],'attente':['#e67e22','Attente'],'inscrit_attente':['#d35400','Inscrit (attente)'],'cloture':['#c0392b','Clôturé'],'impossible':['#95a5a6','Hors ligne'],'hors_bornes':['#7f8c8d','Hors bornes'],'deja_inscrit':['#1abc9c','Déjà inscrit'],'ineligible':['#34495e','Non éligible'],'autre':['#bdc3c7','?']}};
var _MONTH_NAMES = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];
var _MONTH_SHORT = ['Jan','Fév','Mar','Avr','Mai','Juin','Juil','Août','Sep','Oct','Nov','Déc'];
var _DAY_NAMES   = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];

// ── Calendrier ────────────────────────────────────────────────────────────────
function renderCalendar() {{
  var data = getFilteredData();

  // Initialise le mois : 1er mois avec des tournois ≥ aujourd'hui, sinon mois courant
  if (calYear === undefined) {{
    var today = new Date();
    var todayYM = today.getFullYear() + '-' + String(today.getMonth()+1).padStart(2,'0');
    var earliest = null;
    data.forEach(function(t) {{
      var ym = t.debut.slice(0,7);
      if (ym >= todayYM && (!earliest || ym < earliest)) earliest = ym;
    }});
    var initYM = earliest || todayYM;
    calYear  = parseInt(initYM.slice(0,4));
    calMonth = parseInt(initYM.slice(5,7)) - 1;
  }}

  // Regroupement par date de début
  var byDate = {{}};
  data.forEach(function(t) {{
    if (!t.debut) return;
    if (!byDate[t.debut]) byDate[t.debut] = [];
    byDate[t.debut].push(t);
  }});

  var firstDay    = new Date(calYear, calMonth, 1);
  var daysInMonth = new Date(calYear, calMonth+1, 0).getDate();
  var startDow    = (firstDay.getDay() + 6) % 7; // Lundi = 0
  var now         = new Date();
  var todayStr    = now.getFullYear() + '-' + String(now.getMonth()+1).padStart(2,'0') + '-' + String(now.getDate()).padStart(2,'0');

  // Compte total du mois
  var monthTotal = 0;
  for (var d2 = 1; d2 <= daysInMonth; d2++) {{
    var ds2 = calYear + '-' + String(calMonth+1).padStart(2,'0') + '-' + String(d2).padStart(2,'0');
    monthTotal += (byDate[ds2] || []).length;
  }}

  var html = '<div class="d-flex align-items-center gap-3 mb-3">';
  html += '<button class="btn btn-sm btn-outline-secondary" onclick="calNav(-1)">‹ Préc</button>';
  html += '<h5 class="mb-0 fw-bold" style="min-width:220px;text-align:center">' + _MONTH_NAMES[calMonth] + ' ' + calYear + '</h5>';
  html += '<button class="btn btn-sm btn-outline-secondary" onclick="calNav(1)">Suiv ›</button>';
  html += '<small class="text-muted ms-3">' + monthTotal + ' tournoi(s) débutant ce mois · ' + data.length + ' au total</small>';
  html += '</div>';

  html += '<div class="cal-grid mb-2">';
  ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'].forEach(function(d3) {{
    html += '<div class="cal-dow">' + d3 + '</div>';
  }});
  for (var i = 0; i < startDow; i++) html += '<div class="cal-cell cal-empty"></div>';

  for (var d = 1; d <= daysInMonth; d++) {{
    var ds = calYear + '-' + String(calMonth+1).padStart(2,'0') + '-' + String(d).padStart(2,'0');
    var ts = byDate[ds] || [];
    var isToday = ds === todayStr;
    var cls = 'cal-cell' + (isToday ? ' cal-today' : '') + (ts.length ? ' cal-has-events' : '');
    html += '<div class="' + cls + '" onclick="showDayPanel(\\'' + ds + '\\')">';
    html += '<div class="cal-day-num">' + d + '</div>';
    if (ts.length) {{
      html += '<div class="cal-count">' + ts.length + ' 🎾</div>';
      ts.slice(0, 3).forEach(function(t) {{
        var color = _FMT_COLORS[t.fmt] || '#999';
        var nomCourt = t.nom.length > 20 ? t.nom.substring(0,19)+'…' : t.nom;
        html += '<div class="cal-chip" style="background:' + color + '22;border-left:3px solid ' + color + '">' + nomCourt + '</div>';
      }});
      if (ts.length > 3) html += '<div class="cal-chip-more">+' + (ts.length-3) + ' autres</div>';
    }}
    html += '</div>';
  }}
  html += '</div>';
  html += '<div id="cal-day-panel"></div>';
  $('#view-calendar').html(html);
}}

function calNav(dir) {{
  calMonth += dir;
  if (calMonth < 0)  {{ calMonth = 11; calYear--; }}
  if (calMonth > 11) {{ calMonth = 0;  calYear++; }}
  renderCalendar();
}}

function showDayPanel(dateStr) {{
  var data  = getFilteredData();
  var ts    = data.filter(function(t) {{ return t.debut === dateStr; }});
  var panel = $('#cal-day-panel');
  if (!ts.length) {{ panel.html('').hide(); return; }}

  var d = new Date(dateStr + 'T12:00:00');
  var title = _DAY_NAMES[d.getDay()] + ' ' + d.getDate() + ' ' + _MONTH_NAMES[d.getMonth()].toLowerCase() + ' ' + d.getFullYear();

  var html = '<div class="cal-panel">';
  html += '<div class="d-flex align-items-center mb-2 gap-2">';
  html += '<strong>' + title + '</strong>';
  html += '<span class="badge bg-primary">' + ts.length + ' tournoi(s)</span>';
  html += '<button class="btn btn-sm btn-close ms-auto" onclick="$(\\\'#cal-day-panel\\\').html(\\\'\\\')" ></button>';
  html += '</div><div class="row g-2">';
  ts.forEach(function(t) {{
    var color   = _FMT_COLORS[t.fmt] || '#aaa';
    var statuts = [];
    try {{ statuts = JSON.parse(t.statuts); }} catch(e) {{}}
    var statutsHtml = statuts.map(function(s) {{
      var cfg = _STATUT_CFG[s] || ['#bdc3c7', s];
      return '<span class="badge" style="background:' + cfg[0] + ';font-size:.68em">' + cfg[1] + '</span>';
    }}).join(' ');
    html += '<div class="col-xl-3 col-lg-4 col-md-6">';
    html += '<div class="border rounded p-2 h-100" style="border-left:4px solid ' + color + ' !important">';
    html += '<div><a href="' + t.url + '" target="_blank" class="fw-semibold text-decoration-none" style="font-size:.85em">' + t.nom.replace(/</g,'&lt;') + '</a></div>';
    html += '<div class="text-muted" style="font-size:.78em">' + t.ville + '</div>';
    if (t.fmt) html += '<span class="badge mt-1" style="background:' + color + ';font-size:.68em">F' + t.fmt + '</span> ';
    html += statutsHtml;
    html += '</div></div>';
  }});
  html += '</div></div>';
  panel.html(html);
}}

// ── Gantt ─────────────────────────────────────────────────────────────────────
function renderGantt() {{
  var data = getFilteredData().filter(function(t) {{ return t.debut && t.fin; }});
  data.sort(function(a,b) {{ return a.debut < b.debut ? -1 : a.debut > b.debut ? 1 : 0; }});

  if (!data.length) {{
    $('#view-gantt').html('<p class="text-muted p-3">Aucun tournoi dans la vue courante.</p>');
    return;
  }}

  var minDate = data[0].debut;
  var maxDate = data.reduce(function(m,t) {{ return t.fin > m ? t.fin : m; }}, data[0].fin);
  var minMs   = new Date(minDate + 'T00:00:00').getTime();
  var maxMs   = new Date(maxDate + 'T00:00:00').getTime();
  var spanMs  = maxMs - minMs || 86400000;

  // Aujourd'hui
  var now = new Date(); now.setHours(0,0,0,0);
  var todayPct = (now.getTime() - minMs) / spanMs * 100;

  var html = '<p class="text-muted mb-2" style="font-size:.82em">'
           + data.length + ' tournois — cliquer sur une barre pour ouvrir TenUp</p>';

  // Axe des mois
  html += '<div style="display:flex;margin-left:212px;margin-bottom:3px;position:relative;height:18px;overflow:hidden">';
  var cur = new Date(minDate + 'T00:00:00'); cur.setDate(1);
  while (cur.getTime() <= maxMs + 86400000*31) {{
    var pct = (cur.getTime() - minMs) / spanMs * 100;
    if (pct > 100) break;
    if (pct >= -5) {{
      html += '<div style="position:absolute;left:' + Math.max(0,pct).toFixed(1) + '%;font-size:.7em;color:#888;white-space:nowrap;border-left:1px solid #ddd;padding-left:3px">'
            + _MONTH_SHORT[cur.getMonth()] + ' ' + cur.getFullYear() + '</div>';
    }}
    cur.setMonth(cur.getMonth() + 1);
  }}
  html += '</div>';

  // Barres
  html += '<div style="max-height:520px;overflow-y:auto;position:relative">';
  // Ligne "aujourd'hui"
  if (todayPct >= 0 && todayPct <= 100) {{
    html += '<div class="gantt-today" style="left:calc(212px + ' + todayPct.toFixed(2) + '% * (100% - 212px) / 100)"></div>';
  }}
  data.forEach(function(t) {{
    var startMs = new Date(t.debut + 'T00:00:00').getTime();
    var endMs   = new Date(t.fin   + 'T00:00:00').getTime() + 86400000; // inclure dernier jour
    var left    = (startMs - minMs) / spanMs * 100;
    var width   = Math.max((endMs  - startMs) / spanMs * 100, 0.4);
    var color   = _FMT_COLORS[t.fmt] || '#aaa';
    var nbDays  = Math.round((endMs - startMs) / 86400000);
    var tip     = t.nom + '\\n' + t.debut + ' → ' + t.fin + ' (' + nbDays + ' j)\\n' + t.ville;
    html += '<div class="gantt-row">';
    html += '<div class="gantt-label" title="' + t.nom.replace(/"/g,'&quot;') + '">' + (t.nom.length>28 ? t.nom.substring(0,27)+'…' : t.nom) + '</div>';
    html += '<div style="flex:1;position:relative;height:22px">';
    html += '<div class="gantt-bar" style="left:' + left.toFixed(2) + '%;width:' + width.toFixed(2) + '%;background:' + color + ';min-width:4px" ';
    html += 'title="' + tip.replace(/"/g,'&quot;') + '" onclick="window.open(\\'' + t.url + '\\',\\'_blank\\')">';
    if (width > 6) {{
      html += '<span style="font-size:.62em;color:rgba(255,255,255,.9);padding:0 4px;line-height:16px;overflow:hidden;white-space:nowrap;display:block">' + t.ville + '</span>';
    }}
    html += '</div></div></div>';
  }});
  html += '</div>';
  $('#view-gantt').html(html);
}}

// ── Vacances Zone C + Jours fériés ───────────────────────────────────────────
var _vacsLoaded = false;
function renderVacs() {{
  if (_vacsLoaded) return;
  var today     = new Date();
  var todayStr  = today.toISOString().slice(0,10);
  var year      = today.getFullYear();
  var vacsUrl   = 'https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/'
    + 'fr-en-calendrier-scolaire/records?where='
    + encodeURIComponent('zones like "Zone C" and end_date > "' + todayStr + '"')
    + '&limit=40&order_by=start_date&timezone=Europe%2FParis';
  Promise.all([
    fetch(vacsUrl).then(function(r) {{ return r.json(); }}),
    fetch('https://calendrier.api.gouv.fr/jours-feries/metropole/' + year + '.json').then(function(r) {{ return r.json(); }}),
    fetch('https://calendrier.api.gouv.fr/jours-feries/metropole/' + (year+1) + '.json').then(function(r) {{ return r.json(); }})
  ]).then(function(res) {{
    var vacList = res[0].results || [];
    var feries  = Object.assign({{}}, res[1], res[2]);
    _vacsLoaded = true;
    // Build day sets
    var vacDays   = {{}};  // "YYYY-MM-DD" → label
    var ferieDays = {{}};  // "YYYY-MM-DD" → label
    vacList.forEach(function(v) {{
      var label = v.description || v.libelle || 'Vacances';
      var d = new Date(v.start_date); var end = new Date(v.end_date);
      while (d <= end) {{
        vacDays[d.toISOString().slice(0,10)] = label;
        d.setDate(d.getDate()+1);
      }}
    }});
    Object.keys(feries).forEach(function(k) {{ ferieDays[k] = feries[k]; }});
    // Render 13 months from today
    var MOIS = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];
    var html = '<div style="margin-bottom:10px;display:flex;gap:10px;flex-wrap:wrap;align-items:center">';
    html += '<span style="display:inline-block;width:14px;height:14px;background:#c8e6c9;border:1px solid #a5d6a7;border-radius:2px;vertical-align:middle"></span> Vacances scolaires Zone C&nbsp;&nbsp;';
    html += '<span style="display:inline-block;width:14px;height:14px;background:#ffcdd2;border:1px solid #ef9a9a;border-radius:2px;vertical-align:middle"></span> Jour férié&nbsp;&nbsp;';
    html += '<span style="display:inline-block;width:14px;height:14px;background:#bbdefb;border:1px solid #90caf9;border-radius:2px;vertical-align:middle"></span> Vacances + Férié';
    html += '</div>';
    // Upcoming vacations list
    html += '<div style="margin-bottom:12px;font-size:.85em">';
    html += '<strong>Prochaines vacances Zone C :</strong> ';
    var shown = 0;
    vacList.forEach(function(v) {{
      if (shown >= 8) return;
      var label = v.description || 'Vacances';
      var s = new Date(v.start_date); var e = new Date(v.end_date);
      var fmt = function(d) {{ return d.toLocaleDateString('fr-FR',{{day:'2-digit',month:'2-digit',year:'numeric'}}); }};
      html += '<span style="background:#e8f5e9;border:1px solid #a5d6a7;border-radius:4px;padding:2px 7px;margin:2px;display:inline-block">'
        + label + ' : ' + fmt(s) + ' → ' + fmt(e) + '</span>';
      shown++;
    }});
    html += '</div>';
    // Calendar grid (13 months)
    html += '<div style="display:flex;flex-wrap:wrap;gap:12px">';
    var cur = new Date(today.getFullYear(), today.getMonth(), 1);
    for (var mi = 0; mi < 13; mi++) {{
      var y = cur.getFullYear(); var m = cur.getMonth();
      var firstDow = (new Date(y, m, 1).getDay()+6)%7; // Mon=0
      var daysInM  = new Date(y, m+1, 0).getDate();
      html += '<div style="border:1px solid #dee2e6;border-radius:6px;overflow:hidden;min-width:196px;flex:0 0 auto">';
      html += '<div style="background:#343a40;color:#fff;text-align:center;padding:5px 10px;font-weight:600;font-size:.9em">' + MOIS[m] + ' ' + y + '</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(7,28px);background:#f8f9fa">';
      ['Lu','Ma','Me','Je','Ve','Sa','Di'].forEach(function(dn) {{
        html += '<div style="text-align:center;padding:3px 0;font-size:.7em;font-weight:600;color:#6c757d">' + dn + '</div>';
      }});
      html += '</div>';
      html += '<div style="display:grid;grid-template-columns:repeat(7,28px)">';
      for (var di = 0; di < firstDow; di++) html += '<div></div>';
      for (var d = 1; d <= daysInM; d++) {{
        var ds   = y + '-' + String(m+1).padStart(2,'0') + '-' + String(d).padStart(2,'0');
        var isV  = !!vacDays[ds]; var isF = !!ferieDays[ds];
        var isT  = (today.getFullYear()===y && today.getMonth()===m && today.getDate()===d);
        var dow  = (new Date(y,m,d).getDay()+6)%7; // 5=Sa, 6=Di
        var bg   = (isV && isF) ? '#bbdefb' : isV ? '#c8e6c9' : isF ? '#ffcdd2' : (dow >= 5 ? '#fafafa' : '#fff');
        var tc   = (dow >= 5 && !isV && !isF) ? '#aaa' : '#333';
        var tip  = (vacDays[ds]||'') + (isV&&isF?' + ':'') + (ferieDays[ds]||'');
        var bdr  = isT ? 'outline:2px solid #0d6efd;outline-offset:-2px;' : '';
        html += '<div title="' + tip.replace(/"/g,'&quot;') + '" style="text-align:center;line-height:24px;font-size:.78em;background:' + bg + ';color:' + tc + ';' + bdr + '">' + d + '</div>';
      }}
      html += '</div></div>';
      cur.setMonth(cur.getMonth()+1);
    }}
    html += '</div>';
    document.getElementById('vacs-container').innerHTML = html;
  }}).catch(function(e) {{
    document.getElementById('vacs-container').innerHTML =
      '<div class="alert alert-warning">Impossible de charger les vacances : ' + e.message + '</div>';
  }});
}}

// ── Carte (Leaflet) ───────────────────────────────────────────────────────────
function geocodeRefCity(nameOverride) {{
  var q = nameOverride || $('#map-ref-input').val().trim();
  if (!q) return;
  $('#map-ref-status').text('Recherche…');
  fetch('https://api-adresse.data.gouv.fr/search/?q=' + encodeURIComponent(q) + '&type=municipality&limit=1')
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      if (data.features && data.features.length > 0) {{
        var f = data.features[0];
        _REF_LNG  = f.geometry.coordinates[0];
        _REF_LAT  = f.geometry.coordinates[1];
        _REF_CITY = f.properties.label;
        $('#map-ref-input').val(_REF_CITY);
        $('#map-ref-status').text('✓ ' + _REF_CITY);
        renderMap();
      }} else {{
        $('#map-ref-status').text('⚠️ Ville non trouvée');
      }}
    }})
    .catch(function() {{ $('#map-ref-status').text('⚠️ Erreur réseau'); }});
}}

function toggleMapFullscreen() {{
  var $wrap = $('#view-map-wrap');
  var isFs  = $wrap.hasClass('map-fs');
  $wrap.toggleClass('map-fs', !isFs);
  $('#map-fs-btn').text(isFs ? '⛶ Plein écran' : '✕ Quitter');
  setTimeout(function() {{ if (_mapObj) _mapObj.invalidateSize(); }}, 100);
}}

function buildMapPopup(t) {{
  // Statuts : uniquement ceux des épreuves filtrées (pas toutes les épreuves du tournoi)
  var statutCodes = [];
  t.epreuves.forEach(function(e) {{
    if (e.statut && statutCodes.indexOf(e.statut) === -1) statutCodes.push(e.statut);
  }});
  var statutBadges = statutCodes.map(function(s) {{
    var cfg = _STATUT_CFG[s] || ['#bdc3c7','?'];
    return '<span style="background:' + cfg[0] + ';color:white;border-radius:3px;padding:1px 6px;font-size:.75em;margin-right:3px">' + cfg[1] + '</span>';
  }}).join('');
  var fmtBadges = t.fmtAll.map(function(f) {{
    return '<span style="background:' + (_FMT_COLORS[f]||'#666') + ';color:white;border-radius:3px;padding:1px 6px;font-size:.75em;margin-right:3px">F' + f + '</span>';
  }}).join('');
  var dist = '';
  if (t.roadKm !== null) {{
    dist = '<div style="font-size:.82em;color:#495057;margin-top:3px">🚗 ' + t.roadKm + ' km · ' + Math.round(t.roadMin) + ' min</div>';
  }} else if (t.distKm) {{
    dist = '<div style="font-size:.82em;color:#495057;margin-top:3px">📍 ' + t.distKm.toFixed(1) + ' km</div>';
  }}
  var dates = t.debut;
  if (t.fin && t.fin !== t.debut) dates += ' → ' + t.fin;
  var epHtml = t.epreuves && t.epreuves.length
    ? '<div style="margin-top:4px;border-top:1px solid #eee;padding-top:3px">' +
      t.epreuves.map(function(e) {{
        var color = e.fmt ? (_FMT_COLORS[e.fmt] || '#666') : '';
        var fmtTag = color ? ' <span style="background:' + color + ';color:#fff;border-radius:3px;padding:0 4px;font-size:.7em;vertical-align:middle">F' + e.fmt + '</span>' : '';
        return '<div class="map-ep-line">• ' + e.text + fmtTag + '</div>';
      }}).join('') +
      '</div>'
    : '';
  var surfHtml = t.surfaceHtml
    ? '<div style="margin-top:3px;font-size:.82em">' + t.surfaceHtml + '</div>'
    : '';
  // Bouton favori
  var favs = {{}};
  try {{ favs = JSON.parse(localStorage.getItem('tenup_favs') || '{{}}'); }} catch(ex) {{}}
  var isFav = !!favs[t.id];
  var favBtn = '<button class="map-fav-btn" data-id="' + t.id + '" onclick="toggleFavMap(this)" '
    + 'style="float:right;background:none;border:none;cursor:pointer;font-size:1.7em;padding:0 0 0 6px;line-height:1;color:' + (isFav ? '#f39c12' : '#bbb') + '">'
    + (isFav ? '\u2605' : '\u2606') + '</button>';
  return '<div style="min-width:220px;max-width:300px">' +
    '<div style="font-weight:700;margin-bottom:2px;font-size:.9em">' + favBtn + t.nom + '</div>' +
    '<div style="font-size:.8em;color:#6c757d;margin-bottom:3px">' + (t.ville || '') + ' — ' + dates + '</div>' +
    (fmtBadges ? '<div style="margin-bottom:3px">' + fmtBadges + '</div>' : '') +
    (statutBadges ? '<div style="margin-bottom:3px">' + statutBadges + '</div>' : '') +
    surfHtml + dist + epHtml +
    '<a href="' + t.url + '" target="_blank" class="map-popup-btn">🔗 Ouvrir TenUp</a>' +
    '</div>';
}}

function renderMap() {{
  // Collect tournaments that have coordinates
  var data = getFilteredData().filter(function(t) {{ return t.lat && t.lng; }});

  // Initialize map once
  if (!_mapObj) {{
    var initLat = (_REF_LAT !== 0) ? _REF_LAT : (data.length ? data[0].lat : 48.866);
    var initLng = (_REF_LNG !== 0) ? _REF_LNG : (data.length ? data[0].lng : 2.333);
    _mapObj = L.map('view-map').setView([initLat, initLng], 9);
    // Auto-géocode la ville de référence si les coords sont absentes mais le nom est connu
    if (!_REF_LAT && !_REF_LNG && _REF_CITY) {{ geocodeRefCity(_REF_CITY); }}
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
      attribution: '© <a href="https://www.openstreetmap.org">OpenStreetMap</a> contributors, © <a href="https://carto.com">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 19
    }}).addTo(_mapObj);
    _mapMarkers = L.layerGroup().addTo(_mapObj);
  }}

  _mapMarkers.clearLayers();

  // Reference city marker (SVG, auto-contenu, pas de CSS externe)
  if (_REF_LAT && _REF_LNG) {{
    var refSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36">'
      + '<circle cx="18" cy="18" r="15" fill="#0d6efd" stroke="#fff" stroke-width="3"/>'
      + '<text x="18" y="24" text-anchor="middle" fill="#fff" font-size="18" font-family="Arial,sans-serif">\u2605</text>'
      + '</svg>';
    var refIcon = L.divIcon({{ className: '', html: refSvg, iconSize: [36, 36], iconAnchor: [18, 18] }});
    L.marker([_REF_LAT, _REF_LNG], {{ icon: refIcon, zIndexOffset: 1000 }})
      .bindPopup('<b>\u2605 ' + (_REF_CITY || 'Ville de référence') + '</b><br><small style="color:#6c757d">Ville de référence</small>')
      .addTo(_mapMarkers);
  }}

  if (data.length === 0) return;

  // Tournament markers
  var bounds = [];
  var activeFmts = $('.fmt-chk:checked').map(function() {{ return $(this).val(); }}).get();
  data.forEach(function(t) {{
    // Use the first format that matches the active filter (not necessarily the primary format)
    var displayFmt = t.fmt;
    if (activeFmts.length > 0) {{
      for (var fi = 0; fi < t.fmtAll.length; fi++) {{
        if (activeFmts.indexOf(t.fmtAll[fi]) !== -1) {{ displayFmt = t.fmtAll[fi]; break; }}
      }}
    }}
    var color = _FMT_COLORS[displayFmt] || '#6c757d';
    var marker = L.circleMarker([t.lat, t.lng], {{
      radius: 8,
      color: '#fff',
      fillColor: color,
      fillOpacity: 0.85,
      weight: 1.5
    }});
    marker.bindPopup(buildMapPopup(t), {{ maxWidth: 300 }});
    marker.on('mouseover', function() {{ this.openPopup(); }});
    marker.addTo(_mapMarkers);
    bounds.push([t.lat, t.lng]);
  }});

  // Fit map to all markers (include ref city)
  if (_REF_LAT && _REF_LNG) bounds.push([_REF_LAT, _REF_LNG]);
  if (bounds.length > 0) {{
    _mapObj.fitBounds(bounds, {{ padding: [30, 30], maxZoom: 12 }});
  }}

  // Recalculate size (needed when div was hidden)
  setTimeout(function() {{ _mapObj.invalidateSize(); }}, 50);
}}
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Rapport HTML genere : {os.path.abspath(output_path)}")


def generate_from_file(data_file, output_path, new_ids=None, only_natures=None):
    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)
    generate_html(
        data.get("tournaments", []),
        output_path,
        new_ids=new_ids,
        fetched_at=data.get("fetched_at", ""),
        only_natures=only_natures,
        ref_lat=data.get("ref_lat", 0.0),
        ref_lng=data.get("ref_lng", 0.0),
        ref_city=data.get("ref_city", ""),
    )
