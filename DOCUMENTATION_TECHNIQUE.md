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
                    │  [10] Tout nuit     [2] Zone locale          │
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

Deux différences clés par rapport à v1 :

**1. Cache global d'enrichissement cross-fichiers**
```python
# main_v2.py : cherche dans TOUS les fichiers tournaments_*.json
all_files = sorted(glob.glob(os.path.join("data", "tournaments_*.json")))
```
Un tournoi enrichi lors d'un run Bordeaux 300km est réutilisé lors d'un run France 1100km
→ évite de re-visiter les pages déjà connues.

**2. --km-default**
```python
p.add_argument("--km-default", type=int, default=None)
# Suggère un rayon dans le prompt sans le forcer
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
        # GET la page de recherche pour des tokens frais
        form_build_id, form_token, ... = self._get_form_tokens()
        items, nb_results, _ = self._post_search(form_build_id, form_token, page, ...)
```

### Problème du stop-sur-doublons

Avec un grand rayon (1100km), TenUp retourne des doublons à partir de la page ~61.
L'ancienne logique s'arrêtait à ~1828 tournois.

**Solution : --force-pages N**
```python
# force_pages=200 : ignore new_on_page==0, balaie N pages quoi qu'il arrive
if not force_pages:
    if new_on_page == 0 or len(all_items) >= nb_results:
        break
page += 1
if effective_max and page >= effective_max:
    break
```
Résultat : ~2719 tournois France entière (proche des 2720 annoncés TenUp).

### Détection queue-it

```python
if "queue-it.net" in resp.url:
    # Attend que TamperMonkey mette à jour cookies.json (polling mtime)
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
    resp = session.get(url)         # 1 seule requête HTTP
    soup = BeautifulSoup(resp.text)

    fmt, fmt_desc, formats_list = _extract_formats(soup)      # formats F1-F7
    statut_data = _extract_statut_inscription(soup)            # statuts + commentaire
    enriched["statut_fetched_at"] = datetime.now(timezone.utc).isoformat()
```

### Jitter anti-ban (ajouté en v2)

```python
# Délai aléatoire entre 70% et 200% du délai de base
jitter = random.uniform(-0.3 * delay_s, 0.8 * delay_s)
time.sleep(max(0.5, delay_s + jitter))
```

### Pauses longues + sauvegarde intermédiaire (enrich_all)

```python
def enrich_all(..., save_every=50, save_callback=None, long_pause_every=100):
    for i, t in enumerate(to_enrich, 1):
        enrich_tournament(t, session, ...)

        if save_callback and i % save_every == 0:
            save_callback()  # sauvegarde JSON toutes les 50 requêtes

        if i % long_pause_every == 0 and i < total:
            pause = random.uniform(20, 45)
            time.sleep(pause)  # pause anti-ban 20-45s toutes les 100 requêtes
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

**Distinction `attente` vs `inscrit_attente` :**
- `attente` : le tournoi accepte des inscriptions en liste d'attente (cas général)
- `inscrit_attente` : le joueur est **déjà inscrit** et se retrouve en attente

---

## enrich_geo.py — Distances routières

### Étape 1 : Géocodage batch (api-adresse.data.gouv.fr)

1 seule requête CSV pour toutes les adresses. Gratuit, sans clé API.
Champ envoyé : `"VILLE CP"` combiné (ex: `"BRUNOY 91800"`) — évite les ambiguïtés
sur les communes courtes (US, If, Eu…).

### Étape 2 : OSRM table (router.project-osrm.org)

Calcule distance + temps depuis la ville de référence vers tous les tournois.
Batché par 90 pour respecter les limites du serveur public.

```
GET /table/v1/driving/REF_LNG,REF_LAT;T1_LNG,T1_LAT;...?sources=0&annotations=duration,distance
```

---

## generate_html_v3.py — Le rapport interactif

### Données stockées en data-* sur chaque TR

```html
<tr data-dist="22.2" data-dept="91" data-fmt="2,4"
    data-lat="48.6963" data-lng="2.3897"
    data-classements='[{"key":"SM_140","pair":"NC|15/5"}]' ...>
```

Le filtre JS lit ces attributs bruts plutôt que le HTML visible (plus fiable).

### Filtre classement par épreuve

```javascript
// Filtre classement : ne check QUE les épreuves du filtre épreuve actif
var classementsToCheck = (checkedEpreuves.length > 0)
    ? classementsEp.filter(item => checkedEpreuves.indexOf(item.key) !== -1)
    : classementsEp;
```

### Isochrones routières (Valhalla)

```javascript
fetch('https://valhalla1.openstreetmap.de/isochrone', {
    method: 'POST',
    body: JSON.stringify({
        locations: [{lon: _REF_LNG, lat: _REF_LAT}],
        costing: 'auto',          // calcul par route, pas à vol d'oiseau
        contours: [{time: 30}, {time: 60}],
        polygons: true
    })
})
// Fallback si API indisponible : cercles à 70km/h
```

Les formes irrégulières suivent le réseau routier réel.
La ville de référence est modifiable dans l'onglet Carte — les isochrones se recalculent.

### Compteur épreuves dans l'en-tête

```python
total_ep = sum(len(t.get("epreuves", [])) for t in tournaments)
# Affiché dans la stat-card aux côtés du nombre de tournois
```

---

## Logs horodatés (main_v2.py)

```python
def _setup_logging():
    os.makedirs("logs", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%Hh%M%S")
    log_file = os.path.join("logs", f"tenup_{stamp}.log")
    # Ajoute handlers console + fichier sur le root logger
    # Tous les modules (scraper, enrich, enrich_geo) écrivent dans ce fichier
```

Chaque lancement crée `logs/tenup_YYYYMMDD_HHhMMSS.log`.
Le dossier `logs/` est dans `.gitignore`.

---

## cookie_server.py + tampermonkey_tenup.js

```
[Navigateur sur tenup.fft.fr]
       │  TamperMonkey toutes les 8 min
       │  1. Lit document.cookie
       │  2. POST vers localhost:5057
       ▼
[cookie_server.py]
       │  Fusionne avec cookies.json existant
       │  (préserve les cookies HttpOnly non lisibles en JS)
       ▼
[cookies.json mis à jour → mtime change]
       │
       │  scraper.py / enrich.py détectent le changement (polling mtime)
       ▼
[Session rechargée, run reprend automatiquement]
```

---

## Structure des données

### tournaments_\<ville\>_\<km\>km.json

```json
{
  "fetched_at": "2026-04-19T20:00:00",
  "total": 2719,
  "tournaments": [{
    "id": "206919",
    "libelle": "TMC TCBVY 13/14 ANS",
    "distanceEnMetres": "22,2 km",
    "epreuves": [{"natureEpreuve": {"code": "SM"}, "categorieAge": {"id": 140}}],
    "enriched": {
      "format": "2",
      "formats_list": [{"num": "2", "epreuve_key": "SM_140"}],
      "geo_lat": 48.6963, "geo_lng": 2.3897,
      "road_km": 28.5, "road_min": 34,
      "statuts_inscription": {
        "SM_140": {"statut": "ouvert", "message": ""}
      },
      "commentaire_club": "Parking gratuit...",
      "statut_fetched_at": "2026-04-19T20:00:00+00:00"
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

---

*Document créé le 09/04/2026 — mis à jour le 19/04/2026 (v2, force-pages, jitter, sauvegarde intermédiaire, logs).*
