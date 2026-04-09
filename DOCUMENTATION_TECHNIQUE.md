# Documentation technique — TournoisTenUp

> Architecture, choix techniques, problèmes rencontrés et solutions.

---

## Vue d'ensemble

TournoisTenUp est un scraper Python qui récupère les tournois de tennis depuis `tenup.fft.fr`
(plateforme officielle de la Fédération Française de Tennis). Il contourne la salle d'attente
virtuelle queue-it, enrichit les données avec les formats de tournoi (F1-F7), et génère des
rapports HTML interactifs.

---

## Architecture générale

```
cities_france.json
       │
       ▼
  run_batch.py  ──────────────────────────────────────────────────────────┐
       │                                                                   │
       │  pour chaque ville                                               │
       ▼                                                                   │
   main.py                                                                │
   ├── scraper.py      → tenup.fft.fr (AJAX/Drupal)                      │
   ├── enrich.py       → pages de détail tournoi                         │
   ├── storage.py      → JSON par ville + historique                     │
   ├── notify.py       → affichage console + JSON nouveaux               │
   └── generate_html.py → rapport HTML par ville                         │
                                                                          │
       └──────── merge_and_generate() ──► tournaments_france_entiere.html ┘

Gestion des cookies :
  cookie_server.py  ◄──── tampermonkey_tenup.js (navigateur)
         │
         ▼ (écrit cookies.json toutes les 8 min)
  scraper.py / enrich.py  (relit cookies.json quand queue-it détecté)
```

---

## Fichier par fichier

### `scraper.py` — Le cœur du scraping

#### Pourquoi c'est complexe

TenUp n'a pas d'API publique. La recherche est un formulaire Drupal qui fonctionne en AJAX :
- Chaque page de résultats est obtenue par un POST avec des tokens Drupal (`form_build_id`, `form_token`)
- Ces tokens changent à chaque chargement de la page — **impossible de réutiliser le même token pour la page 2**
- La pagination est encodée dans le corps du formulaire, pas en query string

#### Solution : token frais à chaque page

```python
def _get_form_tokens(self):
    # GET la page de recherche pour extraire les tokens Drupal frais
    resp = self.session.get(self.search_url)
    # Extrait form_build_id et form_token du HTML
    # Puis construit le payload POST avec ces tokens
```

**Problème découvert :** Si on réutilise le même `form_build_id` pour plusieurs pages,
Drupal retourne toujours la page 0 (il mémorise l'état du formulaire côté serveur).
**Solution :** faire un GET de la page de recherche avant chaque POST pour avoir des tokens frais.

#### Détection et contournement de queue-it

Queue-it est une salle d'attente virtuelle qui intercepte les requêtes. Sans le cookie
de session queue-it, toutes les requêtes sont redirigées vers `tenup.queue-it.net`.

```python
if "queue-it.net" in resp.url:
    # Attend que TamperMonkey mette à jour cookies.json
    mtime_before = os.path.getmtime(self.cookies_file)
    while waited < 600:  # max 10 min
        time.sleep(15)
        if os.path.getmtime(self.cookies_file) > mtime_before:
            self._reload_cookies()
            break  # retente la requête
```

**Pourquoi surveiller le mtime du fichier :** C'est le moyen le plus simple de détecter
qu'un nouveau cookie a été reçu sans avoir à analyser le contenu du fichier en continu.

---

### `enrich.py` — Récupération des formats F1-F7 et statuts d'inscription

#### Pourquoi enrichir séparément

La liste de résultats de recherche ne contient pas le format du tournoi (F1 = homologué
national, F2 = régional, etc. — détermine le nombre de points ATP/WTA FFT attribués).
Cette information est seulement sur la page de détail de chaque tournoi.

#### Pourquoi les cookies sont aussi requis pour l'enrichissement

**Problème découvert :** On a d'abord pensé que les pages de détail étaient publiques.
Elles le sont partiellement : sans cookie queue-it, la page HTML est servie mais sans
les `<div class="epreuve-detail-format">` qui contiennent le format. TenUp sert deux
versions différentes du HTML selon que la session est authentifiée ou non.

**Solution :** L'enrichissement utilise la même session avec les mêmes cookies que le scraping.

#### Les trois états possibles après enrichissement

| Flag | Signification | Comportement |
|---|---|---|
| `format: "5"` | Enrichi avec succès | Ignoré aux prochains runs |
| `fetch_failed: True` | Erreur réseau ou timeout cookie | **Retenté** au prochain run |
| `no_format_in_html: True` | Page fetchée sans erreur, mais aucun div format trouvé | **Non retenté** (présumé JS-rendu) |

#### Matching format ↔ épreuve

Un tournoi peut avoir plusieurs épreuves (SM 13/14 ans, SM 11/12 ans, SD adulte…)
avec des formats différents. La page de détail structure les formats dans des divs HTML
liés aux épreuves. L'extraction se fait en deux passes :

1. **Par clé épreuve** (`SM_140` = Simple Messieurs + catégorie âge 140) : le plus fiable
2. **Positionnel** : si le nombre de divs format = nombre d'épreuves, on les associe par index
3. **Format unique** : si toutes les épreuves ont le même format, on l'applique à toutes

#### Statut d'inscription (`_extract_statut_inscription`)

La même page de détail contient aussi le statut des inscriptions pour chaque épreuve.
La structure HTML : `div.epreuve-step-0` (1 par épreuve), avec `div.epreuve-detail-info` contenant
le message (vide = ouvert). La présence de la classe CSS `title-closed` sur ce bloc indique
que l'inscription est bloquée, même sans message explicite.

**Statuts normalisés :** `ouvert`, `bientot`, `attente`, `cloture`, `hors_bornes`,
`impossible`, `deja_inscrit`, `ineligible`, `autre`

**Commande dédiée `--enrich-statut-only` :**
Re-fetcher les statuts sans re-fetcher les formats. Ignore automatiquement les tournois
dont la `dateFin` est passée (inutile de vérifier le statut d'un tournoi terminé).

```python
# Stocké dans enriched:
"statuts_inscription": {
    "SM_140": {"statut": "bientot", "message": "Les inscriptions débutent le 14/04/2026",
               "nature": "SM", "titre": "Simple Messieurs 13/14 ans"}
},
"commentaire_club": "Parking gratuit...",
"statut_fetched_at": "2026-04-09T13:00:00+00:00"
```

---

### `generate_html.py` — Le rapport interactif

#### Choix technique : fichier HTML auto-contenu

Le rapport est un seul fichier `.html` qui charge Bootstrap et DataTables depuis des CDN.
**Pourquoi ?** Pour pouvoir l'ouvrir directement en double-cliquant sans serveur web,
et l'envoyer par email ou partager facilement.

#### Filtres côté client (JavaScript pur)

Tous les filtres (distance, département, format, etc.) fonctionnent sans rechargement.
DataTables fournit le tri et la pagination. Un hook personnalisé `$.fn.dataTable.ext.search.push()`
intercepte chaque ligne avant affichage et applique les filtres custom.

```javascript
$.fn.dataTable.ext.search.push(function(settings, _data, index) {
    var $tr = $(node);
    // Lit les data-* sur le <tr> pour filtrer sans parser le HTML visible
    var dept = $tr.attr('data-dept');
    // ...
    return true; // afficher cette ligne
});
```

**Pourquoi stocker les données en `data-*` sur le `<tr>` :** Les colonnes HTML contiennent
du HTML mis en forme (badges, liens) — le filtrer par `.text()` est fragile. Les `data-*`
contiennent les valeurs brutes (distance en km, code département, format numérique…).

#### Filtre ligue → départements

La hiérarchie Ligue → Comités (départements) est codée en dur en JS :

```javascript
var LIGUES = {
    "Île-de-France": ["75","77","78","91","92","93","94","95"],
    // ...
};
```

Quand l'utilisateur choisit une ligue, les cases des départements correspondants
se cochent automatiquement. Le filtre réel est sur le code département extrait
du code postal (`cp[:2]` en Python → `data-dept` sur le `<tr>`).

**Cas Corse :** les CP corses commencent tous par "20" (2A = 20000-20199, 2B = 20200+).
On utilise `"20"` comme code département unifié au lieu de "2A"/"2B".

---

### `run_batch.py` — Le batch France entière

#### Pourquoi sous-processus et non import direct

Chaque ville est traitée par `subprocess.run(["python", "main.py", ...])`.

**Raison :** Main.py modifie `config` en mémoire. Si on l'importait et appelait `main()`
en boucle, les configs des villes se mélangeraient. Le sous-processus garantit un
environnement propre par ville.

#### Déduplication dans le rapport combiné

Un tournoi à Paris peut aussi apparaître dans le fichier Lyon (s'il est à 200 km des deux).
La déduplication garde l'entrée avec la **distance la plus courte** (= la ville de référence
la plus proche, donc la plus pertinente pour l'utilisateur).

```python
if _dist_km(t) < _dist_km(all_tournaments[tid]):
    all_tournaments[tid] = t  # remplace par la version la plus proche
```

#### Pourquoi l'enrichissement prend 15h et non 2h

Le batch traite chaque fichier ville séparément. Un tournoi à Paris (75) peut apparaître
dans les fichiers Paris ET Rennes ET Lille (s'il est dans leur rayon de 300 km).
**Il est enrichi 3 fois.** Avec 8 villes et des recouvrements importants, on enrichit
~5000 tournois au lieu de ~2600 uniques. Optimisation possible : dédupliquer
*avant* l'enrichissement, mais non implémentée.

---

### `cookie_server.py` + `tampermonkey_tenup.js` — La boucle de refresh

#### Le problème

Queue-it expire toutes les 10 minutes. Pour un run de 15h, il faut renouveler le cookie
~90 fois. Impossible manuellement.

#### La solution

```
[Navigateur ouvert sur tenup.fft.fr]
       │
       │  TamperMonkey (toutes les 8 min)
       │  1. Lit document.cookie
       │  2. POST vers localhost:5057
       ▼
[cookie_server.py]
       │  Fusionne avec cookies.json existant
       │  (préserve les cookies HttpOnly non lisibles en JS)
       ▼
[cookies.json mis à jour]
       │
       │  scraper.py / enrich.py détectent le changement (mtime)
       ▼
[Session rechargée, run reprend automatiquement]
```

**Pourquoi fusionner et ne pas remplacer :** `document.cookie` en JavaScript ne retourne
pas les cookies `HttpOnly` (flag de sécurité). Ces cookies peuvent être présents dans un
`cookies.json` importé manuellement. Si on remplaçait le fichier entier, on perdrait ces
cookies HttpOnly et la session pourrait être invalide.

---

### `storage.py` — Persistance et détection des nouveaux

#### Problème encodage Windows

**Erreur rencontrée :** `UnicodeDecodeError: 'cp1252' codec can't decode byte 0x8f`

Python sur Windows utilise `cp1252` par défaut pour `open()`. Les noms de villes français
(accents, caractères spéciaux) sont encodés en UTF-8 dans les JSON.

**Correction :** `open(path, encoding="utf-8")` dans toutes les fonctions de lecture/écriture.

#### Détection des nouveaux tournois

Le fichier `history_<ville>.json` contient `known_ids` : tous les IDs de tournois jamais vus.
À chaque run, on compare les IDs actuels à `known_ids` → les absents sont "nouveaux".
Les IDs des nouveaux sont aussi sauvés dans `last_new_ids` pour que `--html-only` puisse
afficher le badge NEW sans re-scraper.

---

### `enrich_geo.py` — Distances routières et temps de trajet

#### Pourquoi deux étapes séparées

Le calcul de distance routière nécessite les coordonnées GPS de chaque installation.
TenUp ne fournit pas ces coordonnées, il faut donc les géocoder depuis l'adresse.

**Étape 1 — Géocodage batch via `api-adresse.data.gouv.fr`**

L'API gouvernementale française permet d'envoyer toutes les adresses en une seule requête CSV.
368 adresses → 1 requête → ~3 secondes. Gratuit, sans clé API.

Stratégie d'adresse : on envoie `"VILLE CP"` (ex: `"US 95450"`) dans un seul champ.
Envoyer ville et CP séparément causait des échecs sur les communes courtes (US, If, Eu…)
car l'API ne trouvait pas "US" seul. "US 95450" est non-ambigu.

```python
data=[("columns", "adresse")]   # liste de tuples, PAS dict
# data={"columns": "adresse"}  # bug potentiel: requests encode mal les listes
```

Colonnes retournées par l'API : `latitude`, `longitude`, `result_score` (PAS `result_latitude`).

**Étape 2 — Distances OSRM via `router.project-osrm.org`**

OSRM fournit une API "table" qui calcule les distances depuis UN point source vers N destinations
en une seule requête. On envoie la ville de référence en index 0, puis tous les tournois.

```
GET /table/v1/driving/REF_LNG,REF_LAT;T1_LNG,T1_LAT;T2_LNG,T2_LAT;...
    ?sources=0&annotations=duration,distance
```

Résultat : `durations[0][j]` = durée de ref_city vers tournoi j (en secondes).
Batché par 90 pour respecter les limites du serveur public. ~29 requêtes pour 2600 tournois.

**Champs ajoutés dans `enriched` :**
- `geo_lat`, `geo_lng` : coordonnées de l'installation (géocodées)
- `road_km` : distance réelle par la route (km)
- `road_min` : temps de trajet estimé (minutes)

**Idempotent :** les champs déjà calculés sont ignorés. Utiliser `--reset-geo` pour recalculer.

---

### `reset_no_format.py` — Correction des faux positifs

#### Quand l'utiliser

Si l'enrichissement s'est lancé sans cookie valide (par exemple, cookies expirés avant de lancer),
les pages de tournoi sont fetched sans les divs de format → tout est marqué `no_format_in_html=True`.
Normalement ce flag signifie "page JS-rendue, ne pas retenter". Mais ici c'est un faux positif.

**Ce script retire ce flag** uniquement sur les tournois qui n'ont pas de format,
pour qu'ils soient retentés au prochain `--enrich-only` avec des cookies valides.

---

## Problèmes rencontrés et solutions

| Problème | Cause | Solution |
|---|---|---|
| Pagination retourne toujours page 0 | Drupal mémorise l'état du form_build_id | Refaire un GET pour avoir un token frais par page |
| Cookie expiré mid-scrape | Queue-it expire en 10 min | Polling du mtime de cookies.json + TamperMonkey toutes les 8 min |
| 0 format trouvé malgré cookie valide | TenUp sert une version sans divs de format si pas de cookie | Utiliser la même session avec cookies pour l'enrichissement |
| `ValueError: '903 m'` | Certains tournois proches ont la distance en mètres | Fonction `_parse_distance_km()` qui gère "km" et "m" |
| `UnicodeDecodeError cp1252` | Windows ouvre les JSON en cp1252 par défaut | Ajout de `encoding="utf-8"` partout |
| 15h au lieu de 2h pour l'enrichissement | Doublons inter-villes enrichis plusieurs fois | Connu, non optimisé — dédupliquer avant enrichissement serait la solution |
| 187 tournois `fetch_failed` après coupure réseau | Panne réseau en cours de run | Relancer `--enrich-only` → les `fetch_failed` sont automatiquement retentés |
| Mauvais `no_format_in_html` après run sans cookies | Enrichissement sans cookie → pas de divs | `reset_no_format.py` + re-run avec cookies |
| Géocodage : 0/368 réussis | Colonnes API mal nommées (`result_latitude` vs `latitude`) | Utiliser `latitude`/`longitude` (sans préfixe) |
| Géocodage : 0/368 réussis (bis) | `data={"columns": ["ville"]}` → requests encode la liste comme string | Utiliser `data=[("columns", "ville")]` (liste de tuples) |
| Communes courtes non géocodées (US, If…) | Ville seule trop ambiguë pour le géocodeur | Envoyer `"VILLE CP"` combiné dans un seul champ |

---

## Structure des données

### `tournaments_<ville>.json`

```json
{
  "fetched_at": "2026-04-09T14:30:00",
  "total": 368,
  "tournaments": [
    {
      "id": "206919",
      "libelle": "TMC TCBVY 13/14 ANS",
      "nomClub": "TC BRUNOY",
      "distanceEnMetres": "22,2 km",
      "_ref_city": "VAIRES SUR MARNE, 77360",
      "_is_new": false,
      "installation": { "ville": "BRUNOY", "codePostal": "91800", ... },
      "epreuves": [{ "natureEpreuve": {"code":"SM"}, "categorieAge": {"id":140}, ... }],
      "enriched": {
        "detail_url": "https://tenup.fft.fr/tournoi/206919",
        "format": "2",
        "format_desc": "Tournoi régional homologué",
        "formats_list": [{"num":"2","desc":"...","epreuve_key":"SM_140"}],
        "geo_lat": 48.6963,
        "geo_lng": 2.3897,
        "road_km": 28.5,
        "road_min": 34,
        "statuts_inscription": {
          "SM_140": {"statut": "ouvert", "message": "", "nature": "SM", "titre": "Simple Messieurs 13/14 ans"}
        },
        "commentaire_club": "Parking gratuit avec disque...",
        "statut_fetched_at": "2026-04-09T13:00:00+00:00"
      }
    }
  ]
}
```

### `history_<ville>.json`

```json
{
  "known_ids": ["206919", "194832", ...],
  "last_new_ids": ["208012", "208623"],
  "last_run": "2026-04-09T14:30:00",
  "last_total": 368
}
```

---

## Configuration (`config.json`)

```json
{
  "search": {
    "ville": { "label": "VAIRES SUR MARNE, 77360", "lat": 48.874, "lng": 2.638, "distance_km": 100 },
    "date_start": "01/04/26",
    "date_end": "31/12/26",
    "epreuves": ["SM"],          // Filtre HTML : affiche uniquement les épreuves SM
                                  // Mettre ["SM","SD"] pour voir aussi les dames
    "categories_age": [110, 120, 125, 130, 140, 145],  // IDs internes FFT
    "types": ["T"],              // "T" = tournoi, "C" = championnat
    "sort": "_DIST_"            // tri par distance
  },
  "scraper": {
    "results_per_page": 22,
    "delay_between_pages_s": 2   // délai poli entre requêtes
  }
}
```

**Note sur `epreuves` :** Ce champ contrôle l'affichage HTML seulement, pas le scraping.
Le scraper récupère tous les tournois dans le rayon demandé. Seules les lignes d'épreuves
correspondant aux codes dans cette liste sont affichées dans le rapport HTML.
Valeurs possibles : `SM` (Simple Messieurs), `SD` (Simple Dames), `DM` (Double Messieurs),
`DD` (Double Dames), `DX` (Double Mixte).
