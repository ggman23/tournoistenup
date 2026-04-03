"""
Generates a self-contained interactive HTML report from tournaments data.
Uses Bootstrap 5 + DataTables (CDN) for sorting, filtering, pagination.
"""

import json
import os
import html
from datetime import datetime


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

# Age category IDs → short label for filter UI
AGE_LABELS = {
    110: "9/10 ans", 120: "11/12 ans", 125: "12/13 ans",
    130: "12/13 ans", 140: "13/14 ans", 145: "14/15 ans",
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


def _epreuves_html(epreuves):
    lines = []
    for ep in epreuves:
        age    = ep.get("categorieAge", {}).get("libelle", "")
        nature = ep.get("natureEpreuve", {}).get("libelle", "")
        bas    = ep.get("classementBas",  {}).get("libelle", "?").strip()
        haut   = ep.get("classementHaut", {}).get("libelle", "?").strip()
        tarif  = ep.get("tarifJeune", 0)
        lines.append(
            f'<div class="ep-line">'
            f'<span class="ep-nature">{html.escape(nature)}</span> '
            f'<span class="ep-age">{html.escape(age)}</span> '
            f'<span class="ep-range">{html.escape(bas)} → {html.escape(haut)}</span> '
            f'<span class="ep-tarif">{tarif}€</span>'
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


def _tournament_to_row(t):
    install  = t.get("installation", {})
    juge     = t.get("jugeArbitre", {})
    enriched = t.get("enriched", {})

    detail_url = enriched.get("detail_url", f"https://tenup.fft.fr/tournoi/{t.get('id', '')}")
    fmt        = enriched.get("format", "")

    date_debut = _fmt_date(t.get("dateDebut"))
    date_fin   = _fmt_date(t.get("dateFin"))
    dates      = date_debut if date_debut == date_fin else f"{date_debut} → {date_fin}"

    ville = install.get("ville", "")
    cp    = install.get("codePostal", "")
    adresse_parts = [
        install.get("adresse1", ""),
        install.get("adresse2", ""),
        f"{cp} {ville}".strip(),
    ]
    adresse = ", ".join(p for p in adresse_parts if p.strip())

    return {
        "id":           t.get("id", ""),
        "detail_url":   detail_url,
        "libelle":      t.get("libelle", ""),
        "nom_club":     t.get("nomClub", ""),
        "tmc":          t.get("tmc", False),
        "cat":          t.get("categorieTournoi", {}).get("libelle", ""),
        "fmt":          fmt,
        "fmt_sort":     int(fmt) if fmt else 99,
        "dates":        dates,
        "date_debut_sort": t.get("dateDebut", {}).get("date", ""),
        "ville":        ville,
        "cp":           cp,
        "adresse":      adresse,
        "distance_raw": t.get("distanceEnMetres", ""),
        "distance_km":  float(
            t.get("distanceEnMetres", "0 km")
            .replace(",", ".").replace(" km", "").replace("\xa0", "").strip() or 0
        ),
        "surfaces":     _surfaces(t.get("naturesTerrains", [])),
        "epreuves":     _epreuves_html(t.get("epreuves", [])),
        "epreuves_keys": _epreuves_data(t.get("epreuves", [])),
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
):
    new_ids = new_ids or set()
    for t in tournaments:
        tid = t.get("originalId") or t.get("id", "")
        t["_is_new"] = tid in new_ids

    rows = [_tournament_to_row(t) for t in tournaments]
    epreuve_options = _collect_epreuve_options(rows)

    tbody_lines = []
    for r in rows:
        new_badge = '<span class="badge bg-danger ms-1">NEW</span>' if r["is_new"] else ""
        tmc_badge = '<span class="badge bg-warning text-dark ms-1">TMC</span>' if r["tmc"] else ""

        fmt_badge = ""
        if r["fmt"]:
            fc = FORMAT_COLORS.get(r["fmt"], "#666")
            fmt_badge = (
                f'<span class="badge fmt-badge" style="background:{fc}" '
                f'title="Format {r["fmt"]} — coefficient de points">'
                f'F{r["fmt"]}</span>'
            )

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

        ep_keys_json = json.dumps(r["epreuves_keys"])

        tbody_lines.append(f"""
        <tr class="{'table-warning' if r['is_new'] else ''}"
            data-ep-keys='{ep_keys_json}'
            data-distance="{r['distance_km']}"
            data-fmt="{html.escape(r['fmt'])}"
            data-new="{str(r['is_new']).lower()}"
            data-tmc="{str(r['tmc']).lower()}">
          <td data-sort="{html.escape(r['date_debut_sort'])}">{html.escape(r['dates'])}</td>
          <td>{nom_link}</td>
          <td>{html.escape(r['cat'])}</td>
          <td data-sort="{r['fmt_sort']}">{fmt_badge}</td>
          <td>{r['epreuves']}</td>
          <td>{r['surfaces']}</td>
          <td>{html.escape(r['ville'])} <small class="text-muted">{html.escape(r['cp'])}</small></td>
          <td data-sort="{r['distance_km']}">{html.escape(r['distance_raw'])}</td>
          <td class="text-center">{insc}</td>
          <td class="text-center">{paiem}</td>
          <td><small>{html.escape(r['juge_nom'])}<br>{tel_str}</small></td>
          <td><small>{email_link}</small></td>
          <td><small>{html.escape(r['ouverture'])}</small></td>
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
    .badge     {{ font-size:.72em; }}
    .fmt-badge {{ font-size:.85em; padding:.35em .6em; }}
    .srf-badge {{ font-size:.75em; }}
    table.dataTable td {{ vertical-align:middle; }}
    #filter-bar {{ background:white; border-radius:8px; padding:14px 18px; margin-bottom:14px;
                   box-shadow:0 1px 4px rgba(0,0,0,.08); }}
    .stat-card  {{ border-radius:8px; padding:8px 16px; color:white;
                   display:inline-block; margin-right:8px; margin-bottom:6px; font-weight:600; }}
    .dt-buttons {{ margin-bottom:8px; }}
    tr.hidden-row {{ display:none !important; }}
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
    <div class="row g-2 align-items-end">

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Épreuve</label>
        <select class="form-select form-select-sm" id="filter-epreuve"
                style="min-width:220px" onchange="applyFilters()">
          {ep_options_html}
        </select>
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">Distance max (km)</label>
        <input type="number" class="form-control form-control-sm" id="filter-distance"
               placeholder="ex: 50" style="width:110px" oninput="applyFilters()">
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
      </div>

      <div class="col-auto">
        <label class="form-label mb-1 fw-semibold small">&nbsp;</label><br>
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
      </div>

      <div class="col-auto ms-auto align-self-end">
        <button class="btn btn-sm btn-outline-secondary" onclick="resetFilters()">
          ✕ Réinitialiser
        </button>
        <span id="filter-count" class="ms-2 text-muted small"></span>
      </div>
    </div>
  </div>

  <!-- Table -->
  <div class="bg-white rounded shadow-sm p-3">
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

$(function() {{
  dt = $('#t').DataTable({{
    pageLength: 25,
    order: [[0, 'asc']],
    language: {{ url: 'https://cdn.datatables.net/plug-ins/2.0.5/i18n/fr-FR.json' }},
    columnDefs: [
      {{ targets: [2,3,5,8,9], searchable: false }},
      {{ targets: [3,7], type: 'num' }},
    ],
    dom: '<"row"<"col-sm-6"B><"col-sm-6"f>>rtip',
    buttons: [
      {{ extend:'excelHtml5', text:'📥 Excel', className:'btn-sm btn-outline-success',
         exportOptions:{{ columns:':visible' }} }},
      {{ extend:'csvHtml5',   text:'📄 CSV',   className:'btn-sm btn-outline-secondary',
         exportOptions:{{ columns:':visible' }} }},
      {{ extend:'print',      text:'🖨 Print',  className:'btn-sm btn-outline-secondary' }},
    ],
  }});

  // Hide rows via class instead of DataTables draw (keeps sorting)
  applyFilters();
}});

function applyFilters() {{
  var epKey   = $('#filter-epreuve').val();
  var maxDist = parseFloat($('#filter-distance').val()) || null;
  var surface = $('#filter-surface').val().toLowerCase();
  var fmt     = $('#filter-format').val();
  var onlyNew  = $('#chk-new').prop('checked');
  var onlyTmc  = $('#chk-tmc').prop('checked');
  var onlyInsc = $('#chk-insc').prop('checked');

  var visible = 0;

  $('#t tbody tr').each(function() {{
    var $tr = $(this);
    var show = true;

    if (epKey) {{
      var keys = JSON.parse($tr.attr('data-ep-keys') || '[]');
      if (keys.indexOf(epKey) === -1) show = false;
    }}
    if (maxDist !== null) {{
      var d = parseFloat($tr.attr('data-distance')) || 0;
      if (d > maxDist) show = false;
    }}
    if (surface) {{
      var srfText = $tr.find('td:nth-child(6)').text().toLowerCase();
      if (srfText.indexOf(surface) === -1) show = false;
    }}
    if (fmt) {{
      if ($tr.attr('data-fmt') !== fmt) show = false;
    }}
    if (onlyNew  && $tr.attr('data-new')  !== 'true') show = false;
    if (onlyTmc  && $tr.attr('data-tmc')  !== 'true') show = false;
    if (onlyInsc) {{
      var inscCell = $tr.find('td:nth-child(9)').text().trim();
      if (inscCell !== '✅') show = false;
    }}

    $tr.toggleClass('hidden-row', !show);
    if (show) visible++;
  }});

  $('#filter-count').text(visible + ' affiché(s)');
}}

function resetFilters() {{
  $('#filter-epreuve').val('');
  $('#filter-distance').val('');
  $('#filter-surface').val('');
  $('#filter-format').val('');
  $('#chk-new, #chk-tmc, #chk-insc').prop('checked', false);
  applyFilters();
}}
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"📊 Rapport HTML généré : {os.path.abspath(output_path)}")


def generate_from_file(data_file, output_path, new_ids=None):
    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)
    generate_html(
        data.get("tournaments", []),
        output_path,
        new_ids=new_ids,
        fetched_at=data.get("fetched_at", ""),
    )
