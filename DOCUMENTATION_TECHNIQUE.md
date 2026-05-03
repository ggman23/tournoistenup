# Documentation technique — TournoisTenUp

> Architecture, choix techniques, problèmes rencontrés et solutions.

---

## Vue d'ensemble

TournoisTenUp est un scraper Python qui récupère les tournois de tennis depuis `tenup.fft.fr`.
Il contourne la salle d'attente virtuelle queue-it, enrichit les données (formats F1-F7,
statuts d'inscription, distances routières) et génère des rapports HTML interactifs.

---

## Architecture générale

```
                    ┌─────────────────────────────────────────────┐
                    │           tenup_v2.bat (menu interactif)     │
                    │  [1] France seul    [7] France+geo           │
                    │  [8] Enrichir FR    [9] France complète      │
                    │  [10] Tout tout tout nuit [2] Zone locale    │
                    │  [3] Statuts        [4] HTML  [5] Geo        │
                    └──────────────────┬──────────────────────────┘
                                       │
                                       ▼
                                  main_v2.py
                    ┌──────────────────────────────────────────┐
                    │  scraper.py     → tenup.fft.fr (AJAX)    │
                    │  enrich.py      → pages détail tournoi   │
                    │  enrich_geo.py  → géocodage + OSRM       │
                    │  storage.py     → JSON + historique      │
                    │  generate_html_v3.py → rapport HTML      │
                    └──────────────────────────────────────────┘
                                       │
                              logs/tenup_*.log
                              data/tournaments_*.json
                              data/tournaments_*.html

Gestion des cookies :
  cookie_server.py  ◄──── tampermonkey_tenup.js (navigateur)
         │  écrit cookies.json toutes les 8 min
         ▼
  scraper.py / enrich.py  (relit cookies.json quand queue-it détecté)
```

---

## Architecture v1 vs v2

### v1 (main.py + tenup.bat)

Fichiers originaux. Toujours fonctionnels. Le cache d'enrichissement cherche dans
le fichier de la ville courante + `data/tournaments.json`.

### v2 (main_v2.py + tenup_v2.bat) — recommandé

**1. Cache global d'enrichissement cross-fichiers**
```python
all_files = sorted(glob.glob(os.path.join("data", "tournaments_*.json")))
```
Un tournoi enrichi lors d'un run Bordeaux 300km est réutilisé lors d'un run France 1100km.

**2. --km-default**
```python
p.add_argument("--km-default", type=int, default=None)
```

**Nouvelles options bat v2 :**
- `[7]` France entière + distances routières (~25 min)
- `[8]` Enrichir toute la France (~2h, jitter anti-ban)
- `[9]` France complète = [7]+[8] (~3h)
- `[10]` Tout tout tout = [7]+[8]+[3] (~3h30, option nuit)

---

## scraper.py — Le cœur du scraping

### Pourquoi c'est complexe

TenUp n'a pas d'API publique. La recherche est un formulaire Drupal fonctionnant en AJAX :
- Chaque page de résultats nécessite un POST avec des tokens Drupal frais (`form_build_id`, `form_token`)
- Ces tokens changent à chaque chargement — impossible de réutiliser le même pour la page 2
- La pagination est encodée dans le corps du formulaire, pas en query string

**Solution : token frais à chaque page**
```python
def fetch_all(self, max_pages=0, force_pages=0):
    while True:
        form_build_id, form_token, ... = self._get_form_tokens()
        items, nb_results, _ = self._post_search(form_build_id, form_token, page, ...)
```

### Problème du stop-sur-doublons

Avec un grand rayon (1100km), TenUp retourne des doublons à partir de la page ~61.

**Solution : --force-pages N**
```python
if not force_pages:
    if new_on_page == 0 or len(all_items) >= nb_results:
        break
```
Résultat : ~2719 tournois France entière.

### Détection queue-it

```python
if "queue-it.net" in resp.url:
    mtime_before = os.path.getmtime(self.cookies_file)
    while waited < 600:
        time.sleep(15)
        if os.path.getmtime(self.cookies_file) > mtime_before:
            self._reload_cookies()
            break
```

---

## enrich.py — Formats, statuts, commentaires

### Une seule visite par tournoi pour tout récupérer

```python
def enrich_tournament(tournament, session, delay_s=1.5, ...):
    resp = session.get(url)
    soup = BeautifulSoup(resp.text)
    fmt, fmt_desc, formats_list = _extract_formats(soup)
    statut_data = _extract_statut_inscription(soup)
    enriched["statut_fetched_at"] = datetime.now(timezone.utc).isoformat()
```

### Jitter anti-ban

```python
jitter = random.uniform(-0.3 * delay_s, 0.8 * delay_s)
time.sleep(max(0.5, delay_s + jitter))
```

### Pauses longues + sauvegarde intermédiaire

```python
def enrich_all(..., save_every=50, save_callback=None, long_pause_every=100):
    for i, t in enumerate(to_enrich, 1):
        enrich_tournament(t, session, ...)
        if save_callback and i % save_every == 0:
            save_callback()
        if i % long_pause_every == 0 and i < total:
            pause = random.uniform(20, 45)
            time.sleep(pause)
```

### Trois états possibles après enrichissement

| Flag | Signification | Comportement |
|---|---|---|
| `format: "5"` | Enrichi avec succès | Ignoré aux prochains runs |
| `fetch_failed: True` | Erreur réseau | Retenté automatiquement |
| `no_format_in_html: True` | Page fetchée sans div format | Non retenté (JS-rendu présumé) |

### Statuts d'inscription normalisés

`ouvert`, `bientot`, `attente`, `inscrit_attente`, `cloture`, `hors_bornes`,
`impossible`, `deja_inscrit`, `ineligible`, `autre`

---

## enrich_geo.py — Distances routières

### Étape 1 : Géocodage batch (api-adresse.data.gouv.fr)

1 seule requête CSV pour toutes les adresses. Gratuit, sans clé API.
Champ envoyé : `"VILLE CP"` combiné (ex: `"BRUNOY 91800"`) — évite les ambiguïtés.

### Étape 2 : OSRM table (router.project-osrm.org)

```
GET /table/v1/driving/REF_LNG,REF_LAT;T1_LNG,T1_LAT;...?sources=0&annotations=duration,distance
```
Batché par 90 pour respecter les limites du serveur public.

---

## generate_html_v3.py — Le rapport interactif

### Deux fichiers HTML produits

```python
generate_html(tournaments, html_file, ...)
generate_html(tournaments, html_file_sm, ..., sm_only=True)
```

`sm_only=True` filtre via `SM_TARGET_KEYS = frozenset({"SM_110","SM_120","SM_125","SM_130","SM_140","SM_145"})`.
Les tournois sans aucune épreuve SM cible sont entièrement exclus du second fichier.

### Données stockées en data-* sur chaque TR

```html
<tr data-dist="22.2" data-dept="91" data-fmt="2,4"
    data-lat="48.6963" data-lng="2.3897"
    data-classements='[{"key":"SM_140","pair":"NC|15/5"}]' ...>
```

### Filtre classement par épreuve

```javascript
var classementsToCheck = (checkedEpreuves.length > 0)
    ? classementsEp.filter(item => checkedEpreuves.indexOf(item.key) !== -1)
    : classementsEp;
```

### Filtre date — sémantique exacte

```javascript
if (fStart && !fEnd) {
    // Date seule : seulement les tournois qui débutent CE JOUR
    if (tStart && tStart !== fStart) return false;
} else {
    // Fenêtre [fStart, fEnd]
    if (fStart && tEnd2  && tEnd2  < fStart) return false;
    if (fEnd   && tStart && tStart > fEnd)   return false;
    if (fEnd   && tEnd2  && tEnd2  > fEnd)   return false;
}
```

### Ville cliquable → Google Maps

```python
_dest = urllib.parse.quote(r['adresse'], safe='')   # adresse texte du club
if ref_address:
    _orig = urllib.parse.quote(ref_address, safe='')
elif ref_lat and ref_lng:
    _orig = f"{ref_lat},{ref_lng}"
else:
    _orig = urllib.parse.quote(ref_city, safe='')
_maps_url = f"https://www.google.com/maps/dir/?api=1&origin={_orig}&destination={_dest}"
```

L'adresse du club (texte brut) est utilisée comme destination — plus fiable que les
coordonnées GPS géocodées qui peuvent pointer vers une rue approximative.

### Rue de départ (ref_address)

`main_v2.py` pose une troisième question au démarrage : `Rue de départ [...]`.
La réponse est mémorisée dans `config.json` sous `config["search"]["ville"]["rue"]`
et combinée avec la ville : `ref_address = f"{rue}, {ville}"`.

En mode `--html-only`, la rue est relue depuis config et sauvegardée dans le JSON
avant la génération, pour que `generate_from_file()` en dispose.

### Clustering carte

```javascript
var locGroups = {};
data.forEach(function(t) {
    var key = t.lat.toFixed(4) + ',' + t.lng.toFixed(4);
    if (!locGroups[key]) locGroups[key] = { lat: t.lat, lng: t.lng, list: [] };
    locGroups[key].list.push(t);
});
// N>1 → divIcon SVG avec badge numéroté, popup liste tous les tournois
```

### Isochrones routières (Valhalla)

```javascript
fetch('https://valhalla1.openstreetmap.de/isochrone', {
    method: 'POST',
    body: JSON.stringify({
        locations: [{lon: _REF_LNG, lat: _REF_LAT}],
        costing: 'auto',
        contours: [{time: 30}, {time: 60}],
        polygons: true
    })
})
// Fallback si API indisponible : cercles à 70km/h
```

### Vue Planning

Calendrier mensuel stockant les absences en `localStorage` sous la clé `tenup_planning`.
Format : `{ "2026-07-14": "Vacances", "2026-07-15": "Vacances" }`.

Clic sur un jour → prompt texte → sauvegarde. Clic sur un jour déjà noté → suppression.

### Filtre Absent (🚫) — isTournamentBlocked

```javascript
function isTournamentBlocked(debut, fin, planning) {
    var duration = Math.round((d2 - d1) / 86400000) + 1;
    if (duration <= 4)  return overlap >= 1;
    if (duration <= 14) return overlap / duration >= 0.4;
    return overlap / duration >= 0.6;
}
```

| Durée tournoi | Seuil de blocage |
|---|---|
| ≤ 4 jours | 1 jour d'absence suffit |
| 5–14 jours | ≥ 40 % des jours absents |
| > 14 jours | ≥ 60 % des jours absents |

### Vue Ratés

Liste les tournois bloqués par les absences du Planning, triés par distance routière
(`data-distance` sur chaque TR) depuis la ville de référence.

### Calendrier — overlay absences

```javascript
var planNote = _calPlanning[ds] || '';
var cls = 'cal-cell' + (planNote ? ' cal-absent' : '');
if (planNote) html += '<div class="plan-note-chip">🚫 ' + planNote.substring(0,15) + '</div>';
```

---

## Onglet Élite — generate_html_v3.py

### Fichiers source

Les données proviennent de trois fichiers CSV placés dans le même répertoire que le script :
`2014.csv`, `2015.csv`, `2016.csv` (catégories de joueurs Elite FFT).

Encodage `utf-8-sig` (UTF-8 avec BOM Windows), séparateur `;`.

### _TENNIS_RANK — correspondance classement → entier de tri

```python
_TENNIS_RANK = {
    "NC":0, "40/2":1, "40":2, "30/5":3, "30/4":4, "30/3":5, "30/2":6, "30/1":7, "30":8,
    "15/5":9, "15/4":10, "15/3":11, "15/2":12, "15/1":13, "15":14,
    "4/6":15, "3/6":16, "2/6":17, "1/6":18, "0":19, "-2/6":20, "-4/6":21, "-15":22, "-30":23
}
```

Utilisé pour le tri numérique correct des colonnes Classement et Meilleur classement.
Les valeurs manquantes ou inconnues reçoivent la valeur 99 → se retrouvent en bas du tableau.

### _read_elite_csv() — parsing défensif champ par champ

Chaque champ est lu avec une vérification de longueur individuelle :
```python
clas = row[6].strip() if len(row) > 6 else ""
```
Ce pattern évite un `IndexError` silencieux qui faisait tomber le nombre de joueurs de
2936 à 2612 (la garde initiale `len(row) < 12` laissait passer des lignes incomplètes
qui explosaient plus loin sur `row[12]`).

### DataTables — colonnes de rang cachées pour le tri

Les colonnes Classement et Meilleur utilisent une colonne cachée de rang numérique :
```javascript
{ data: 4, orderData: [9] },          // Classement (texte) trié par rang col 9
{ data: 5, orderData: [10] },         // Meilleur  (texte) trié par rang col 10
{ data: 9,  visible: false, type: 'num' },   // rang r_clas
{ data: 10, visible: false, type: 'num' }    // rang r_best
```
Le `type: 'num'` est obligatoire — sans lui DataTables trie en mode lexicographique
("9" > "13"), ce qui plaçait 30/1 avant 15 dans l'ordre descendant.

### Problème ext.search — conflit avec la table tournois

Le filtre global `$.fn.dataTable.ext.search` dédié aux tournois vérifiait l'attribut DOM
`data-ep-keys` (uniquement présent sur les lignes tournoi). Une fois les lignes de l'onglet
Élite rendues dans le DOM, ce filtre retournait `false` pour elles car elles n'ont pas cet
attribut — rendant la recherche irréversible (effacer du texte ne faisait pas réapparaître
les résultats).

**Correction :** ajout d'un `return true` précoce au début du filtre tournoi :
```javascript
var _tid = settings.nTable && settings.nTable.id;
if (_tid && (_tid.indexOf('dt-elite-') === 0 || _tid === 'dt-adv')) return true;
```

### Recherche nom dans l'onglet Élite

`column().search()` de DataTables 2.x filtre sur la valeur brute du champ `data`,
pas sur la valeur retournée par `render`. La recherche par nom utilise donc `ext.search`
avec une comparaison directe sur les champs prénom (index 1) et nom (index 2) :
```javascript
$.fn.dataTable.ext.search.push(function(settings, _d, _i, rowData) {
    var tid = settings.nTable.id;
    if (!tid || tid.indexOf('dt-elite-') !== 0) return true;
    var q = _eliteJoueurVal[tid];
    if (!q) return true;
    var name = ((rowData[1]||'') + ' ' + (rowData[2]||'')).toLowerCase();
    return name.indexOf(q) !== -1;
});
```

---

## Onglet Adversaires — generate_html_v3.py

### Structure de adv.csv

Fichier de 14 colonnes minimum (séparateur `;`, encodage `utf-8-sig`) :

| Index | Champ | Exemple |
|---|---|---|
| 0 | N° match | 127 |
| 1 | Date | 15/03/2024 |
| 2 | Prénom adversaire | Cyril |
| 3 | Nom adversaire | LARDE |
| 4 | ID CRM | 123456 |
| 5 | Année de naissance | 2011 |
| 6 | Âge | 13 |
| 7 | Classement jour J | 30/2 |
| 8 | Victoire/Défaite | Oui / Non |
| 9 | Club | TC Exemple |
| 10 | Classement du mois | 15/3 |
| 11 | Meilleur classement obtenu | 15/1 |
| 12 | Nom du tournoi | TMC TCBVY 13/14 |
| 13 | ID tournoi TenUp | 206919 |

`_read_adv_csv()` calcule trois colonnes de rang supplémentaires ajoutées en fin de liste :
`r_clas` (rang de col 7), `r_mois` (rang de col 10), `r_best` (rang de col 11).

### Coloration des lignes (victoire/défaite)

```javascript
createdRow: function(row, data) {
    if (data[8] === 'Oui') $(row).addClass('adv-win');
    else if (data[8] === 'Non') $(row).addClass('adv-loss');
}
```
CSS : `rgba(40,167,69,.12)` (vert doux) pour les victoires, `rgba(220,53,69,.10)` (rouge doux) pour les défaites.

### Liens Joueur et Tournoi

- **Joueur** → `https://tenup.fft.fr/palmares/{id_crm}` (palmarès FFT)
- **Tournoi** → `https://tenup.fft.fr/tournament/tableaux/{tournoi_id}` (tableaux du tournoi)

### renderAdvStats() — section statistiques

Calculée en JavaScript à l'initialisation de l'onglet depuis `_ADV` (données JSON injectées
dans le HTML au moment de la génération).

**Bilan global** (4 cartes) : total matchs, victoires, défaites, pourcentage victoires.

**Taux de victoire par classement jour J** : groupe par valeur de col 7 (classement au moment
du match), calcule V / Total / % pour chaque classe, trié par rang numérique.

**Taux de victoire par meilleur classement** : même structure, groupe par col 11 (meilleur
classement obtenu par l'adversaire depuis le début de sa carrière).

**Adversaires rencontrés plusieurs fois** :
```javascript
var byPlayer = {};
_ADV.forEach(function(r) {
    var key = r[4]; // id CRM — identifiant unique de l'adversaire
    if (!byPlayer[key]) byPlayer[key] = {
        prenom: r[2], nom: r[3], wins: 0, total: 0, bestRank: -1, bestClass: ''
    };
    byPlayer[key].total++;
    if (r[8] === 'Oui') byPlayer[key].wins++;
    var rb = typeof r[16] === 'number' ? r[16] : -1;
    if (rb > byPlayer[key].bestRank) {
        byPlayer[key].bestRank = rb;
        byPlayer[key].bestClass = r[11];
    }
});
```
Filtre `total >= 2`, trié par total décroissant.
La colonne "Meilleur Classement" affiche le meilleur classement jamais atteint par cet
adversaire (pas le classement du dernier match rencontré).

---

## GitHub Pages — déploiement automatique

Le fichier `.github/workflows/pages.yml` déploie automatiquement le contenu du dossier
`data/` (fichiers HTML générés) vers GitHub Pages à chaque push sur `main`.

L'URL résultante est accessible sans authentification depuis n'importe quel appareil
(téléphone, tablette) sans avoir le projet en local.

---

## Logs horodatés (main_v2.py)

```python
def _setup_logging():
    os.makedirs("logs", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%Hh%M%S")
    log_file = os.path.join("logs", f"tenup_{stamp}.log")
```

---

## cookie_server.py + tampermonkey_tenup.js

```
[Navigateur sur tenup.fft.fr]
       │  TamperMonkey toutes les 8 min
       ▼
[cookie_server.py]  →  cookies.json mis à jour (mtime change)
       │
       ▼
[scraper.py / enrich.py détectent le changement → session rechargée]
```

---

## Structure des données

### tournaments_\<ville\>_\<km\>km.json

```json
{
  "fetched_at": "2026-04-19T20:00:00",
  "ref_lat": 48.8733, "ref_lng": 2.6383,
  "ref_city": "Vaires-sur-Marne",
  "ref_address": "6 rue des Loriots, Vaires-sur-Marne",
  "total": 404,
  "tournaments": [{
    "id": "206919",
    "libelle": "TMC TCBVY 13/14 ANS",
    "adresse": "POLE TENNISTIQUE MAURICE MACHOEL, 6 RUE GUY RABOURDIN, 77500 CHELLES",
    "enriched": {
      "format": "2",
      "geo_lat": 48.6963, "geo_lng": 2.3897,
      "road_km": 28.5, "road_min": 34,
      "statuts_inscription": { "SM_140": {"statut": "ouvert"} }
    }
  }]
}
```

---

## Problèmes rencontrés et solutions

| Problème | Cause | Solution |
|---|---|---|
| Pagination retourne toujours page 0 | Drupal mémorise l'état du form_build_id | Refaire un GET pour token frais par page |
| Plafond à ~1828 tournois | Stop-sur-doublons avec grand rayon | `--force-pages 200` |
| Cookie expiré mid-scrape | Queue-it expire en 10 min | Polling mtime cookies.json + TamperMonkey 8 min |
| 0 format trouvé malgré cookie valide | TenUp sert HTML sans divs si pas de cookie | Même session avec cookies pour l'enrichissement |
| Ban temporaire WAF | Trop de requêtes régulières | Jitter 70-200% + pause 20-45s/100 requêtes |
| Perte des données si interruption | Sauvegarde seulement en fin de run | save_callback toutes les 50 requêtes |
| UnicodeDecodeError cp1252 | Windows ouvre JSON en cp1252 | encoding="utf-8" partout |
| Géocodage 0/368 réussis | Colonnes API mal nommées | Utiliser latitude/longitude (sans préfixe result_) |
| Communes courtes non géocodées | "US" trop ambigu | Envoyer "VILLE CP" combiné |
| Scraper redirigé vers mauvaise page | TenUp redirige vers dernière page visitée | Vérification URL après GET + re-fetch si nécessaire |
| UnboundLocalError sur `saved` | Variable non initialisée dans le flux scrape+enrich | `saved = {}` avant le bloc `args.enrich` |
| Faux "git commit HTML échoué" | Message git en français non reconnu | Détection FR+EN : "rien à valider" ou "nothing to commit" |
| Destination Maps imprécise | lat/lng géocodé ne correspond pas à l'adresse réelle | Utiliser `r['adresse']` texte brut comme destination |
| Origine Maps ignorait la rue | --html-only ne sauvegardait pas ref_address dans JSON | Écrire ref_address dans JSON avant generate_from_file() |
| Filtre 1J + date 25/04 montrait 29/04 | Logique chevauchement trop permissive | fStart seul → tStart !== fStart → return false |
| Élite : 2612 joueurs au lieu de 2936 | Garde `len(row) < 12` + accès `row[12]` sur ligne de 12 cols → IndexError silencieux | Garde `< 9` + lecture champ par champ avec `if len(row) > N` |
| Élite : 30/1 trié avant 15 | Colonnes de rang sans `type: 'num'` → tri lexicographique ("6" > "13") | Ajout `type: 'num'` sur les colonnes cachées de rang |
| Élite : "40/2" trié en tête | Classement absent de `_TENNIS_RANK` → valeur par défaut 99 | Ajout `"40/2": 1` dans le dictionnaire |
| Élite : recherche bloquée après 1 frappe | `ext.search` tournoi vérifiait `data-ep-keys` sur les lignes élite déjà rendues → `false` permanent | `return true` précoce pour `dt-elite-*` et `dt-adv` au début du filtre tournoi |
| Adversaires : "Dernier Class." affichait le 1er classement | Itération CSV décroissante par N° → la dernière valeur stockée était la plus ancienne | Remplacement par "Meilleur Classement" : on garde la valeur avec le rang r_best le plus élevé |

---

*Document créé le 09/04/2026 — mis à jour le 03/05/2026 (Onglet Élite, Onglet Adversaires, Stats, GitHub Pages, table problèmes complétée).*
