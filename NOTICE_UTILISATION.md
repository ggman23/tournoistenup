# Notice d'utilisation — TournoisTenUp

> Guide pratique : quoi lancer, dans quel ordre, pour quel résultat.

---

## Prérequis avant toute chose

1. **Python** installé (3.10+)
2. **Dépendances** : `pip install -r requirements.txt`
3. **Cookies valides** dans `cookies.json` (voir section Cookies ci-dessous)
4. Être dans le dossier du projet : `cd C:\tournoistenupv2\tournoistenup`

---

## Les cookies — point critique

TenUp utilise une salle d'attente virtuelle (queue-it) qui expire **toutes les 10 minutes**.
Sans cookie valide, le scraper ne peut pas accéder aux données.

### Option A — Export manuel (simple, mais cookie expire vite)

1. Ouvre Chrome/Firefox → va sur `https://tenup.fft.fr`
2. Attends que la page charge complètement (passe la salle d'attente si nécessaire)
3. Ouvre l'extension **Cookie-Editor** → Export → copie le JSON → colle dans `cookies.json`
4. **Lance ta commande dans les 5 minutes** qui suivent

### Option B — Refresh automatique (recommandé pour les runs longs)

Nécessite TamperMonkey installé dans le navigateur + le script `tampermonkey_tenup.js` actif.

**Terminal 1 (laisser ouvert pendant tout le run) :**
```
python cookie_server.py
```
Tu dois voir : `Cookie server démarré → http://localhost:5057/update_cookie`

**Navigateur :** Ouvre `https://tenup.fft.fr` — TamperMonkey envoie automatiquement les cookies toutes les 8 min et recharge la page. Tu verras dans le terminal : `✅ 12 cookies mis à jour → cookies.json`

**Terminal 2 :** Lance ton run normalement avec `--cookies cookies.json`

---

## CAS 1 — Scraper une seule ville

### Récupérer les tournois + formats en une fois
```
python main.py --no-prompt --city "VAIRES SUR MARNE, 77360" --km 100 --lat 48.874 --lng 2.638 --cookies cookies.json
```

### Seulement re-enrichir (récupérer les formats manquants) sans re-scraper
```
python main.py --enrich-only --no-prompt --city "VAIRES SUR MARNE, 77360" --km 100 --lat 48.874 --lng 2.638 --cookies cookies.json
```

### Seulement régénérer le fichier HTML (sans rien télécharger)
```
python main.py --html-only --no-prompt --city "VAIRES SUR MARNE, 77360" --km 100
```

### Mode interactif (avec prompts pour choisir la ville, distance, dates)
```
python main.py --cookies cookies.json
```

---

## CAS 2 — Run France entière (toutes les villes de cities_france.json)

> **Temps estimé :** scraping ~30-60 min | enrichissement ~2-15h selon les doublons

### Étape 1 — Scraper toutes les villes (cookies requis)
```
python run_batch.py --cookies cookies.json --date-start 01/04/26 --date-end 31/12/26
```
Crée un fichier `data/tournaments_<ville>.json` pour chaque ville.

### Étape 2 — Enrichir (récupérer les formats)
```
python run_batch.py --enrich-only --cookies cookies.json
```
Lit les fichiers JSON existants, va chercher le format (F1-F7) sur chaque page de tournoi.
**Les tournois déjà enrichis sont ignorés** → peut être interrompu et relancé.

### Étape 3 — (Auto) Génération du rapport combiné
Le rapport `data/tournaments_france_entiere.html` est généré automatiquement à la fin.

### Ou tout en une seule commande (si les cookies restent valides assez longtemps)
```
python run_batch.py --cookies cookies.json --enrich --date-start 01/04/26 --date-end 31/12/26
```

### Juste régénérer les HTMLs sans rien télécharger
```
python run_batch.py --html-only
```

---

## CAS 3 — Reprendre après une coupure / erreur

Les tournois qui ont échoué sont marqués `fetch_failed=True` dans le JSON.
**Ils sont automatiquement retentés** au prochain run `--enrich-only`.
Il suffit de relancer :
```
python run_batch.py --enrich-only --cookies cookies.json
```

---

## CAS 4 — Ajouter une nouvelle ville personnalisée

Exemple : Monc-en-Belin (non présente dans cities_france.json) :
```
python main.py --no-prompt --city "MONCE EN BELIN, 72230" --km 150 --lat 47.8 --lng 0.08 --cookies cookies.json
```
Crée `data/tournaments_monce_en_belin_72230_150km.json` et son HTML.
Elle sera **automatiquement incluse** dans le rapport France entière lors du prochain `--html-only`.

---

## CAS 5 — Vérifier l'état des données

### Voir combien de tournois ont été enrichis / ont échoué
```
python check_enrichment.py
```
Affiche par fichier : ok / fetch_failed / no_format / non traités.

### Voir l'état des derniers nouveaux tournois
```
python check_new.py data/tournaments_vaires_sur_marne_77360_100km.json
```

---

## CAS 6 — Corriger des mauvais flags

Parfois, si l'enrichissement s'est fait sans cookie valide, des tournois sont marqués `no_format_in_html=True` à tort (la page existait mais sans les divs de format car pas de cookie).

**Réinitialiser ces flags puis re-enrichir :**
```
python reset_no_format.py --dry-run   ← aperçu sans modifier
python reset_no_format.py             ← applique la correction
python run_batch.py --enrich-only --cookies cookies.json
```

---

## Fichiers produits

| Fichier | Contenu |
|---|---|
| `data/tournaments_<ville>_<km>km.json` | Données brutes + enrichies d'une ville |
| `data/history_<ville>_<km>km.json` | IDs connus → détection des nouveaux tournois |
| `data/tournaments_<ville>_<km>km.html` | Rapport HTML d'une ville |
| `data/tournaments_france_entiere.html` | Rapport combiné toutes villes (dédupliqué) |
| `data/france_entiere_<date>.html` | Idem, horodaté (archivé) |
| `data/tournois_<date>.html` | Rapport ville horodaté |
| `data/nouveaux_<date>.html` | Rapport des nouveaux tournois uniquement |

---

## Filtres disponibles dans le rapport HTML

| Filtre | Ce qu'il fait |
|---|---|
| 🔍 Rechercher | Cherche dans nom, juge, ville, club |
| Ligue | Sélectionne une ligue → coche automatiquement ses départements |
| Comités | Sélection multiple de départements (77, 93, 95… simultanément) |
| Épreuve | Filtre par type + catégorie d'âge (SM 13/14 ans, etc.) |
| Distance max | N'affiche que les tournois à moins de X km |
| Format | F1 à F7 (coefficient de points) |
| Surface | Terre battue, Résine, Béton poreux… |
| Nouveaux | Affiche uniquement les tournois apparus au dernier run |
| TMC | Tournois "Match Compétition" internes |
| Inscr. en ligne | Seulement ceux avec inscription en ligne |
| Masquer Vert/Orange | Cache les tournois débutants |
| Mots à exclure | Ex : `hiver open` → cache tout tournoi contenant ces mots |
| Dates | Plage de dates de début/fin |
| ⭐ Favoris | Sauvegardés dans le navigateur (localStorage) |

---

## Commandes utilitaires rapides

```bash
# Test rapide (2 pages seulement, sans sauvegarder)
python main.py --dry-run --pages-max 2 --cookies cookies.json

# Ne traiter qu'une ville du batch
python run_batch.py --city-filter "bordeaux" --enrich-only --cookies cookies.json

# Réinitialiser l'historique (tous les tournois redeviennent "nouveaux")
python main.py --reset --city "PARIS, 75001" --km 300

# Voir les coordonnées d'une ville (pour --lat --lng)
python -c "
import requests
r = requests.get('https://geo.api.gouv.fr/communes?nom=Vaires-sur-Marne&fields=nom,codesPostaux,centre&boost=population&limit=3')
for c in r.json(): print(c['nom'], c.get('codesPostaux'), c.get('centre',{}).get('coordinates'))
"
```

---

## Coordonnées des villes du batch (cities_france.json)

| Ville | lat | lng | rayon |
|---|---|---|---|
| PARIS, 75001 | 48.8566 | 2.3522 | 300 km |
| RENNES, 35000 | 48.1173 | -1.6778 | 300 km |
| LILLE, 59000 | 50.6292 | 3.0573 | 300 km |
| STRASBOURG, 67000 | 48.5734 | 7.7521 | 300 km |
| LYON, 69001 | 45.7640 | 4.8357 | 300 km |
| BORDEAUX, 33000 | 44.8378 | -0.5792 | 300 km |
| TOULOUSE, 31000 | 43.6047 | 1.4442 | 300 km |
| AJACCIO, 20000 | 41.9192 | 8.7386 | 300 km |
