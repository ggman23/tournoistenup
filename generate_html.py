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
    "ouvert":       ("#27ae60", "Ouvert"),
    "bientot":      ("#2980b9", "Bientôt"),
    "attente":      ("#e67e22", "Liste d'attente"),
    "cloture":      ("#c0392b", "Clôturé"),
    "hors_bornes":  ("#7f8c8d", "Hors bornes"),
    "impossible":   ("#95a5a6", "Hors ligne"),
    "deja_inscrit": ("#1abc9c", "Déjà inscrit"),
    "ineligible":   ("#34495e", "Non éligible"),
    "autre":        ("#bdc3c7", "?"),
}


def _statut_badge_html(code: str, message: str = "") -> str:
    color, label = STATUT_CONFIG.get(code, ("#bdc3c7", code))
    tip = html.escape(message) if message else html.escape(label)
    return (
        f' <span class="badge statut-badge" style="background:{color}" '
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

        lines.append(
            f'<div class="ep-line" data-ep-key="{html.escape(ep_key)}">'
            f'<span class="ep-nature">{html.escape(nature)}</span> '
            f'<span class="ep-age">{html.escape(age)}</span> '
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
                f'<span class="badge fmt-badge" style="background:{fc}" '
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
            data-road-min="{r['road_min'] if r['road_min'] is not None else ''}">
          <td data-sort="{html.escape(r['date_debut_sort'])}">{html.escape(r['dates'])}</td>
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

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdn.datatables.net/2.0.5/css/dataTables.bootstrap5.min.css">
  <link rel="stylesheet" href="https://cdn.datatables.net/buttons/3.0.2/css/buttons.bootstrap5.min.css">
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
    #filter-bar {{ background:white; border-radius:8px; padding:14px 18px; margin-bottom:14px;
                   box-shadow:0 1px 4px rgba(0,0,0,.08); }}
    .stat-card  {{ border-radius:8px; padding:8px 16px; color:white;
                   display:inline-block; margin-right:8px; margin-bottom:6px; font-weight:600; }}
    .dt-buttons {{ margin-bottom:8px; }}
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

  <!-- Filter bar -->
  <div id="filter-bar">

    <!-- Ligne 0 : Recherche + Ligue + Comités -->
    <div class="row g-2 align-items-end mb-2 pb-2 border-bottom">

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">🔍 Rechercher</label>
        <input type="search" class="form-control form-control-sm" id="filter-search"
               placeholder="Nom, juge, ville, club…" style="min-width:240px"
               oninput="applySearch(this.value)">
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Ligue</label>
        <select class="form-select form-select-sm" id="filter-ligue"
                style="min-width:210px" onchange="onLigueChange()">
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
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Comités (depts)</label><br>
        <div class="dropdown">
          <button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button"
                  id="dept-btn" data-bs-toggle="dropdown" data-bs-auto-close="outside"
                  aria-expanded="false">
            Tous les comités
          </button>
          <div class="dropdown-menu p-2" style="min-width:480px;max-height:320px;overflow-y:auto">
            <div class="d-flex justify-content-between mb-1">
              <small class="text-muted fst-italic">Cliquez sur une ligue pour tout cocher</small>
              <button class="btn btn-xs btn-link p-0 text-danger" onclick="clearDepts()">Tout décocher</button>
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
      </div>

    </div>

    <div class="row g-2 align-items-end">

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Épreuve</label>
        <select class="form-select form-select-sm" id="filter-epreuve"
                style="min-width:220px" onchange="applyFilters()">
          {ep_options_html}
        </select>
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Vol d'oiseau max (km)</label>
        <input type="number" class="form-control form-control-sm" id="filter-distance"
               placeholder="ex: 50" style="width:110px" oninput="applyFilters()">
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">🚗 Trajet max (km)</label>
        <input type="number" class="form-control form-control-sm" id="filter-road-km"
               placeholder="ex: 60" style="width:110px" oninput="applyFilters()">
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">🕐 Trajet max (min)</label>
        <input type="number" class="form-control form-control-sm" id="filter-road-min"
               placeholder="ex: 45" style="width:110px" oninput="applyFilters()">
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Surface</label>
        <select class="form-select form-select-sm" id="filter-surface"
                style="min-width:150px" onchange="applyFilters()">
          <option value="">Toutes</option>
          <option>Résine</option>
          <option>Terre battue</option>
          <option>Terre artificielle</option>
          <option>Béton poreux</option>
          <option>Gazon</option>
          <option>Moquette</option>
        </select>
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Format</label>
        <select class="form-select form-select-sm" id="filter-format"
                style="width:110px" onchange="applyFilters()">
          <option value="">Tous</option>
          <option value="1">F1</option><option value="2">F2</option>
          <option value="3">F3</option><option value="4">F4</option>
          <option value="5">F5</option><option value="6">F6</option>
          <option value="7">F7</option>
        </select>
        <div class="form-check mt-1">
          <input class="form-check-input" type="checkbox" id="chk-no-fmt" onchange="applyFilters()">
          <label class="form-check-label small" for="chk-no-fmt">+ sans format</label>
        </div>
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Statut inscription</label>
        <select class="form-select form-select-sm" id="filter-statut"
                style="min-width:175px" onchange="applyFilters()">
          <option value="">Tous statuts</option>
          <option value="ouvert">✅ Ouvert</option>
          <option value="bientot">🔵 Bientôt</option>
          <option value="attente">🟠 Liste d'attente</option>
          <option value="cloture">🔴 Clôturé</option>
          <option value="impossible">⬜ Hors ligne</option>
          <option value="hors_bornes">⬜ Hors bornes</option>
          <option value="deja_inscrit">🟢 Déjà inscrit</option>
          <option value="ineligible">⬛ Non éligible</option>
        </select>
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">&nbsp;</label><br>
        <div class="form-check form-check-inline">
          <input class="form-check-input" type="checkbox" id="chk-hide-past" checked onchange="applyFilters()">
          <label class="form-check-label small fw-semibold" for="chk-hide-past" style="color:#6c757d">Masquer terminés</label>
        </div>
        <div class="form-check form-check-inline">
          <input class="form-check-input" type="checkbox" id="chk-new" onchange="applyFilters()">
          <label class="form-check-label small" for="chk-new">Nouveaux</label>
        </div>
        <div class="form-check form-check-inline">
          <input class="form-check-input" type="checkbox" id="chk-tmc" onchange="applyFilters()">
          <label class="form-check-label small" for="chk-tmc">TMC</label>
        </div>
        <div class="form-check form-check-inline">
          <input class="form-check-input" type="checkbox" id="chk-insc" onchange="applyFilters()">
          <label class="form-check-label small" for="chk-insc">Inscr. en ligne</label>
        </div>
        <div class="form-check form-check-inline">
          <input class="form-check-input" type="checkbox" id="chk-fav" onchange="applyFilters()">
          <label class="form-check-label small" for="chk-fav">⭐ Favoris</label>
        </div>
      </div>

      <div class="col-auto ms-auto align-self-end">
        <button class="btn btn-sm btn-outline-secondary" onclick="resetFilters()">
          ✕ Réinitialiser
        </button>
        <span id="filter-count" class="ms-2 text-muted small"></span>
      </div>
    </div>

    <!-- Ligne 2 : masquer mots-clés + plage de dates -->
    <div class="row g-2 align-items-end mt-2 pt-2 border-top">

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Masquer tournois contenant</label><br>
        <div class="form-check form-check-inline">
          <input class="form-check-input" type="checkbox" id="chk-hide-vert" onchange="applyFilters()">
          <label class="form-check-label small fw-bold" for="chk-hide-vert" style="color:#198754">Vert</label>
        </div>
        <div class="form-check form-check-inline">
          <input class="form-check-input" type="checkbox" id="chk-hide-orange" onchange="applyFilters()">
          <label class="form-check-label small fw-bold" for="chk-hide-orange" style="color:#fd7e14">Orange</label>
        </div>
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Mots à exclure (séparés par espace)</label>
        <input type="text" class="form-control form-control-sm" id="filter-exclude"
               placeholder="ex: hiver open fédéral" style="min-width:260px" oninput="applyFilters()">
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Dates du</label>
        <input type="date" class="form-control form-control-sm" id="filter-date-start"
               style="width:150px" onchange="applyFilters()">
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">au</label>
        <input type="date" class="form-control form-control-sm" id="filter-date-end"
               style="width:150px" onchange="applyFilters()">
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
    <small class="text-muted ms-2" id="view-info"></small>
  </div>

  <!-- Vue Calendrier -->
  <div id="view-calendar" style="display:none" class="bg-white rounded shadow-sm p-3"></div>

  <!-- Vue Gantt -->
  <div id="view-gantt" style="display:none" class="bg-white rounded shadow-sm p-3" style="overflow-x:auto"></div>

  <!-- Table -->
  <div id="view-table" class="bg-white rounded shadow-sm p-3">
    <table id="t" class="table table-hover table-striped" style="width:100%">
      <thead class="table-dark">
        <tr>
          <th>Dates</th>
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
<script src="https://cdn.datatables.net/buttons/3.0.2/js/buttons.html5.min.js"></script>
<script src="https://cdn.datatables.net/buttons/3.0.2/js/buttons.print.min.js"></script>
<script>
var dt;
var currentView = 'table';
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

    var epKey    = $('#filter-epreuve').val();
    var maxDist  = parseFloat($('#filter-distance').val()) || null;
    var surface  = $('#filter-surface').val().toLowerCase();
    var fmt      = $('#filter-format').val();
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

    if (epKey) {{
      var keys = JSON.parse($tr.attr('data-ep-keys') || '[]');
      if (keys.indexOf(epKey) === -1) return false;
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

    if (surface && $tr.find('td:nth-child(6)').text().toLowerCase().indexOf(surface) === -1) return false;
    if (fmt) {{
      var fmts      = ($tr.attr('data-fmt') || '').split(',');
      var hasFmt    = $tr.attr('data-has-format') === 'true';
      var inclNoFmt = $('#chk-no-fmt').prop('checked');
      if (fmts.indexOf(fmt) === -1 && !(inclNoFmt && !hasFmt)) return false;
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

    var filterStatut = $('#filter-statut').val();
    if (filterStatut) {{
      var statuts = JSON.parse($tr.attr('data-statuts') || '[]');
      if (statuts.indexOf(filterStatut) === -1) return false;
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

  dt = $('#t').DataTable({{
    pageLength: 25,
    lengthMenu: [[25, 50, 100, -1], [25, 50, 100, "Tout"]],
    order: [[0, 'asc']],
    language: {{ url: 'https://cdn.datatables.net/plug-ins/2.0.5/i18n/fr-FR.json' }},
    columnDefs: [
      {{ targets: [2,3,5,8,9], searchable: false }},
      {{ targets: [3,7], type: 'num' }},
      {{ targets: [-1], orderable: false, searchable: false }},
    ],
    dom: '<"row"<"col-sm-6"B><"col-sm-6"l>>rtip',
    buttons: [
      {{ extend:'excelHtml5', text:'📥 Excel', className:'btn-sm btn-outline-success',
         exportOptions:{{ columns:':visible' }} }},
      {{ extend:'csvHtml5',   text:'📄 CSV',   className:'btn-sm btn-outline-secondary',
         exportOptions:{{ columns:':visible' }} }},
      {{ extend:'print',      text:'🖨 Print',  className:'btn-sm btn-outline-secondary' }},
    ],
    drawCallback: function() {{
      restoreFavs();
      applyEpLineFilter();
      var n = dt.page.info().recordsDisplay;
      $('#filter-count').text(n + ' affiché(s)');
      $('#view-info').text(n + ' tournois dans la vue');
      if (currentView === 'calendar') renderCalendar();
      if (currentView === 'gantt')    renderGantt();
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
  var epKey = $('#filter-epreuve').val();
  $('#ep-line-filter-style').remove();
  if (epKey) {{
    $('<style id="ep-line-filter-style">')
      .text('.ep-line:not([data-ep-key="' + epKey + '"]) {{ display:none !important; }}')
      .appendTo('head');
  }}
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

function restoreFavs() {{
  var favs = JSON.parse(localStorage.getItem('tenup_favs') || '{{}}');
  $('.fav-btn').each(function() {{
    var id  = $(this).attr('data-id');
    var isFav = !!favs[id];
    $(this).text(isFav ? '\u2605' : '\u2606').toggleClass('fav-active', isFav);
  }});
}}

function resetFilters() {{
  $('#filter-epreuve, #filter-surface, #filter-format, #filter-statut').val('');
  $('#filter-distance, #filter-road-km, #filter-road-min, #filter-exclude').val('');
  $('#filter-date-start, #filter-date-end').val('');
  $('#filter-ligue').val('');
  $('.dept-chk').prop('checked', false);
  updateDeptBtn();
  $('#chk-new, #chk-tmc, #chk-insc, #chk-fav, #chk-no-fmt').prop('checked', false);
  $('#chk-hide-vert, #chk-hide-orange').prop('checked', false);
  $('#chk-hide-past').prop('checked', true);  // remet masquer-terminés coché par défaut
  $('#filter-search').val('');
  if (dt) {{ dt.search('').draw(); }} else {{ applyFilters(); }}
}}

// ── Gestion des vues (Tableau / Calendrier / Gantt) ──────────────────────────
function showView(view) {{
  currentView = view;
  $('#view-table').toggle(view === 'table');
  $('#view-calendar').toggle(view === 'calendar');
  $('#view-gantt').toggle(view === 'gantt');
  $('.view-tab').removeClass('btn-primary').addClass('btn-outline-secondary');
  var tabId = view === 'table' ? 'tab-table' : view === 'calendar' ? 'tab-cal' : 'tab-gantt';
  $('#' + tabId).removeClass('btn-outline-secondary').addClass('btn-primary');
  if (view === 'calendar') {{ calYear = undefined; calMonth = undefined; renderCalendar(); }}
  if (view === 'gantt')    renderGantt();
}}

// ── Extraction des données filtrées depuis DataTables ────────────────────────
function getFilteredData() {{
  var result = [];
  dt.rows({{ search: 'applied' }}).nodes().each(function(node) {{
    var $tr = $(node);
    var $link = $tr.find('a.tournament-link').first();
    result.push({{
      id:    $tr.attr('data-id') || '',
      nom:   $link.text().trim(),
      url:   $link.attr('href') || '',
      debut: $tr.attr('data-date-debut') || '',
      fin:   $tr.attr('data-date-fin')   || '',
      fmt:   ($tr.attr('data-fmt') || '').split(',')[0] || '',
      ville: $tr.find('td:eq(6)').contents().first().text().trim(),
      statuts: $tr.attr('data-statuts') || '[]',
    }});
  }});
  return result;
}}

var _FMT_COLORS = {{'1':'#c0392b','2':'#e67e22','3':'#f39c12','4':'#27ae60','5':'#2980b9','6':'#8e44ad','7':'#7f8c8d'}};
var _STATUT_CFG = {{'ouvert':['#27ae60','Ouvert'],'bientot':['#2980b9','Bientôt'],'attente':['#e67e22','Attente'],'cloture':['#c0392b','Clôturé'],'impossible':['#95a5a6','Hors ligne'],'hors_bornes':['#7f8c8d','Hors bornes'],'deja_inscrit':['#1abc9c','Déjà inscrit'],'ineligible':['#34495e','Non éligible'],'autre':['#bdc3c7','?']}};
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
    )
