"""
Generates a self-contained interactive HTML report from tournaments data.
Uses Bootstrap 5 + DataTables (CDN) for sorting, filtering, pagination.
"""

import json
import os
import html
from datetime import datetime


# Maps surface codes to readable labels + badge colors
SURFACE_COLORS = {
    "TB": ("Terre battue", "#c0392b"),
    "TA": ("Terre artificielle", "#e67e22"),
    "RES": ("Résine", "#2980b9"),
    "BP": ("Béton poreux", "#7f8c8d"),
    "DUR": ("Dur", "#7f8c8d"),
    "DUR-": ("Dur", "#7f8c8d"),
    "GAZON": ("Gazon", "#27ae60"),
    "B-PIL": ("Moquette", "#8e44ad"),
    "AUTRE": ("Autre", "#95a5a6"),
}

FORMAT_COLORS = {
    "1": "#c0392b",
    "2": "#e67e22",
    "3": "#f39c12",
    "4": "#27ae60",
    "5": "#2980b9",
    "6": "#8e44ad",
    "7": "#7f8c8d",
}


def _fmt_date(date_obj: dict | None, short: bool = False) -> str:
    if not date_obj:
        return ""
    raw = date_obj.get("date", "")
    try:
        d = datetime.fromisoformat(raw.split(".")[0])
        return d.strftime("%d/%m") if short else d.strftime("%d/%m/%Y")
    except Exception:
        return raw[:10] if raw else ""


def _surfaces(terrains: list) -> str:
    parts = []
    for t in terrains:
        code = t.get("code", "").upper().replace(" ", "")
        label, color = SURFACE_COLORS.get(code, (t.get("libelle", code), "#95a5a6"))
        parts.append(
            f'<span class="badge" style="background:{color};font-size:0.75em">{html.escape(label)}</span>'
        )
    return " ".join(parts)


def _epreuves_html(epreuves: list) -> str:
    lines = []
    for ep in epreuves:
        age = ep.get("categorieAge", {}).get("libelle", "")
        nature = ep.get("natureEpreuve", {}).get("libelle", "")
        bas = ep.get("classementBas", {}).get("libelle", "?").strip()
        haut = ep.get("classementHaut", {}).get("libelle", "?").strip()
        tarif = ep.get("tarifJeune", 0)
        lines.append(
            f'<div class="ep-line"><span class="ep-nature">{html.escape(nature)}</span> '
            f'<span class="ep-age">{html.escape(age)}</span> '
            f'<span class="ep-range">{html.escape(bas)} → {html.escape(haut)}</span> '
            f'<span class="ep-tarif">{tarif}€</span></div>'
        )
    return "\n".join(lines) if lines else '<span class="text-muted">—</span>'


def _tournament_to_row(t: dict) -> dict:
    """Extract all display fields from a tournament dict."""
    install = t.get("installation", {})
    juge = t.get("jugeArbitre", {})
    enriched = t.get("enriched", {})

    detail_url = enriched.get("detail_url", f"https://tenup.fft.fr/tournoi/{t.get('id', '')}")
    fmt = enriched.get("format", "")

    date_debut = _fmt_date(t.get("dateDebut"))
    date_fin = _fmt_date(t.get("dateFin"))
    dates = date_debut if date_debut == date_fin else f"{date_debut} → {date_fin}"

    ville = install.get("ville", "")
    cp = install.get("codePostal", "")
    adresse_parts = [
        install.get("adresse1", ""),
        install.get("adresse2", ""),
        f"{cp} {ville}".strip(),
    ]
    adresse = ", ".join(p for p in adresse_parts if p.strip())

    distance_raw = t.get("distanceEnMetres", "")

    nom_club = t.get("nomClub", "")
    tmc = t.get("tmc", False)
    libelle = t.get("libelle", "")

    cat = t.get("categorieTournoi", {}).get("libelle", "")

    inscription = "✅" if t.get("inscriptionEnLigne") else "❌"
    paiement = "✅" if t.get("paiementEnLigne") else "❌"

    surfaces = _surfaces(t.get("naturesTerrains", []))
    epreuves = _epreuves_html(t.get("epreuves", []))

    juge_nom = f"{juge.get('prenom', '')} {juge.get('nom', '')}".strip()
    telephone = install.get("telephone", "")
    email = t.get("courrielEngagement", "")

    ouverture = t.get("dateOuvertureInscriptionEnLigne", "")

    return {
        "id": t.get("id", ""),
        "detail_url": detail_url,
        "libelle": libelle,
        "nom_club": nom_club,
        "tmc": tmc,
        "cat": cat,
        "fmt": fmt,
        "dates": dates,
        "date_debut_sort": t.get("dateDebut", {}).get("date", ""),
        "ville": ville,
        "cp": cp,
        "adresse": adresse,
        "distance_raw": distance_raw,
        "surfaces": surfaces,
        "epreuves": epreuves,
        "inscription": inscription,
        "paiement": paiement,
        "juge_nom": juge_nom,
        "telephone": telephone,
        "email": email,
        "ouverture": ouverture,
        "is_new": t.get("_is_new", False),
    }


def generate_html(
    tournaments: list[dict],
    output_path: str,
    new_ids: set[str] | None = None,
    title: str = "Tournois TenUp",
    fetched_at: str = "",
):
    new_ids = new_ids or set()

    # Mark new ones
    for t in tournaments:
        tid = t.get("originalId") or t.get("id", "")
        t["_is_new"] = tid in new_ids

    rows = [_tournament_to_row(t) for t in tournaments]

    # Build table rows HTML
    tbody_lines = []
    for r in rows:
        new_badge = '<span class="badge bg-danger ms-1">NEW</span>' if r["is_new"] else ""
        tmc_badge = '<span class="badge bg-warning text-dark ms-1">TMC</span>' if r["tmc"] else ""

        fmt_badge = ""
        if r["fmt"]:
            fc = FORMAT_COLORS.get(r["fmt"], "#666")
            fmt_badge = f'<span class="badge" style="background:{fc}">F{r["fmt"]}</span>'

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

        tbody_lines.append(f"""
        <tr class="{'table-warning' if r['is_new'] else ''}">
          <td data-sort="{html.escape(r['date_debut_sort'])}">{html.escape(r['dates'])}</td>
          <td>{nom_link}</td>
          <td>{html.escape(r['cat'])}</td>
          <td class="text-center">{fmt_badge}</td>
          <td>{r['epreuves']}</td>
          <td>{r['surfaces']}</td>
          <td>{html.escape(r['ville'])} <small class="text-muted">{html.escape(r['cp'])}</small></td>
          <td data-sort="{r['distance_raw'].replace(',','.')}">{html.escape(r['distance_raw'])}</td>
          <td class="text-center">{r['inscription']}</td>
          <td class="text-center">{r['paiement']}</td>
          <td><small>{html.escape(r['juge_nom'])}<br>{tel_str}</small></td>
          <td><small>{email_link}</small></td>
          <td><small>{html.escape(r['ouverture'])}</small></td>
        </tr>""")

    tbody = "\n".join(tbody_lines)
    total = len(rows)
    new_count = sum(1 for r in rows if r["is_new"])
    fetched_str = fetched_at or datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

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
    body {{ font-size: 0.88rem; background: #f8f9fa; }}
    h1 {{ font-size: 1.4rem; }}
    .tournament-link {{ font-weight: 600; color: #0d6efd; text-decoration: none; }}
    .tournament-link:hover {{ text-decoration: underline; }}
    .ep-line {{ margin-bottom: 2px; white-space: nowrap; }}
    .ep-nature {{ color: #495057; font-weight: 600; }}
    .ep-age {{ color: #6c757d; }}
    .ep-range {{ color: #0d6efd; }}
    .ep-tarif {{ background: #e9ecef; border-radius: 3px; padding: 0 4px; font-weight: 600; }}
    .badge {{ font-size: 0.72em; }}
    table.dataTable td {{ vertical-align: middle; }}
    .stat-card {{ border-radius: 8px; padding: 12px 18px; color: white; display: inline-block; margin-right: 8px; margin-bottom: 8px; }}
    #filter-bar {{ background: white; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    .dt-buttons {{ margin-bottom: 8px; }}
  </style>
</head>
<body>
<div class="container-fluid py-3">
  <div class="d-flex align-items-center mb-3 gap-3 flex-wrap">
    <h1 class="mb-0">🎾 {html.escape(title)}</h1>
    <span class="stat-card" style="background:#0d6efd">{total} tournois</span>
    {'<span class="stat-card" style="background:#dc3545">' + str(new_count) + ' nouveaux</span>' if new_count else ''}
    <small class="text-muted ms-auto">Mis à jour : {html.escape(fetched_str)}</small>
  </div>

  <div id="filter-bar" class="row g-2 align-items-end">
    <div class="col-auto">
      <label class="form-label mb-1 fw-semibold">Afficher</label>
      <div class="form-check form-check-inline">
        <input class="form-check-input" type="checkbox" id="chk-new" onchange="filterNew()">
        <label class="form-check-label" for="chk-new">Nouveaux seulement</label>
      </div>
      <div class="form-check form-check-inline">
        <input class="form-check-input" type="checkbox" id="chk-tmc" onchange="filterTmc()">
        <label class="form-check-label" for="chk-tmc">TMC seulement</label>
      </div>
    </div>
    <div class="col-auto">
      <label class="form-label mb-1 fw-semibold">Distance max (km)</label>
      <input type="number" class="form-control form-control-sm" id="filter-distance" placeholder="ex: 50" style="width:100px" oninput="filterDistance()">
    </div>
    <div class="col-auto">
      <label class="form-label mb-1 fw-semibold">Surface</label>
      <select class="form-select form-select-sm" id="filter-surface" onchange="filterSurface()" style="width:160px">
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
      <label class="form-label mb-1 fw-semibold">Format (1-7)</label>
      <select class="form-select form-select-sm" id="filter-format" onchange="filterFormat()" style="width:120px">
        <option value="">Tous</option>
        <option>1</option><option>2</option><option>3</option>
        <option>4</option><option>5</option><option>6</option><option>7</option>
      </select>
    </div>
    <div class="col-auto ms-auto">
      <button class="btn btn-sm btn-outline-secondary" onclick="resetFilters()">Réinitialiser filtres</button>
    </div>
  </div>

  <div class="bg-white rounded shadow-sm p-3">
    <table id="tournaments-table" class="table table-hover table-striped" style="width:100%">
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
          <th>Inscription</th>
          <th>Paiement</th>
          <th>Juge / Tél</th>
          <th>Email</th>
          <th>Ouverture inscr.</th>
        </tr>
      </thead>
      <tbody>
        {tbody}
      </tbody>
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
var table;
$(document).ready(function() {{
  table = $('#tournaments-table').DataTable({{
    pageLength: 25,
    order: [[0, 'asc']],
    language: {{
      url: 'https://cdn.datatables.net/plug-ins/2.0.5/i18n/fr-FR.json'
    }},
    columnDefs: [
      {{ targets: [3, 8, 9], searchable: false }},
      {{ targets: 7, type: 'num' }},
    ],
    dom: '<"row"<"col-sm-6"B><"col-sm-6"f>>rtip',
    buttons: [
      {{ extend: 'excelHtml5', text: '📥 Excel', className: 'btn-sm btn-outline-success' }},
      {{ extend: 'csvHtml5',   text: '📄 CSV',   className: 'btn-sm btn-outline-secondary' }},
      {{ extend: 'print',      text: '🖨️ Print',  className: 'btn-sm btn-outline-secondary' }},
    ],
  }});
}});

$.fn.dataTable.ext.search.push(function(settings, data, dataIndex, row) {{
  return row._visible !== false;
}});

function applyCustomFilters() {{
  var showNew  = document.getElementById('chk-new').checked;
  var showTmc  = document.getElementById('chk-tmc').checked;
  var maxDist  = parseFloat(document.getElementById('filter-distance').value) || null;
  var surface  = document.getElementById('filter-surface').value.toLowerCase();
  var fmt      = document.getElementById('filter-format').value;

  table.rows().every(function() {{
    var node = this.node();
    var rowData = this.data();
    var visible = true;

    if (showNew  && !$(node).hasClass('table-warning')) visible = false;
    if (showTmc  && !$(node).find('td:nth-child(2) .badge.bg-warning').length) visible = false;
    if (maxDist) {{
      var distCell = $(node).find('td:nth-child(8)').text().replace(',', '.').trim();
      var km = parseFloat(distCell);
      if (!isNaN(km) && km > maxDist) visible = false;
    }}
    if (surface) {{
      var surfCell = $(node).find('td:nth-child(6)').text().toLowerCase();
      if (surfCell.indexOf(surface) === -1) visible = false;
    }}
    if (fmt) {{
      var fmtCell = $(node).find('td:nth-child(4)').text().trim();
      if (fmtCell !== 'F' + fmt) visible = false;
    }}

    node._visible = visible;
    $(node).toggle(visible);
  }});
  table.draw(false);
}}

function filterNew()      {{ applyCustomFilters(); }}
function filterTmc()      {{ applyCustomFilters(); }}
function filterDistance() {{ applyCustomFilters(); }}
function filterSurface()  {{ applyCustomFilters(); }}
function filterFormat()   {{ applyCustomFilters(); }}

function resetFilters() {{
  document.getElementById('chk-new').checked = false;
  document.getElementById('chk-tmc').checked = false;
  document.getElementById('filter-distance').value = '';
  document.getElementById('filter-surface').value = '';
  document.getElementById('filter-format').value = '';
  table.rows().every(function() {{
    this.node()._visible = true;
    $(this.node()).show();
  }});
  table.search('').draw();
}}
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"📊 Rapport HTML généré : {os.path.abspath(output_path)}")


def generate_from_file(
    data_file: str,
    output_path: str,
    new_ids: set[str] | None = None,
):
    """Convenience function: load tournaments.json and generate HTML."""
    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)

    tournaments = data.get("tournaments", [])
    fetched_at = data.get("fetched_at", "")

    generate_html(
        tournaments,
        output_path,
        new_ids=new_ids,
        fetched_at=fetched_at,
    )
