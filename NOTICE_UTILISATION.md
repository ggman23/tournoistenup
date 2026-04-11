# Notice d'utilisation — TournoisTenUp

> Guide pratique : quoi lancer, dans quel ordre, pour quel résultat.

---

## ⚠️ Règle importante pour l'assistant Claude

**Toujours donner les commandes complètes et exactes**, copiables telles quelles.
Ne jamais omettre un flag obligatoire comme `--cookies cookies.json`.
L'utilisateur n'est pas développeur — une commande incomplète est une commande fausse.

---

## Prérequis avant toute chose

1. **Python** installé (3.10+)
2. **Dépendances** : `pip install -r requirements.txt`
3. **Cookies valides** dans `cookies.json` (voir section Cookies ci-dessous)
4. Être dans le dossier du projet :
   ```
   cd C:\tournoistenupv2\tournoistenup
   ```

---

## Les cookies — point critique

TenUp utilise une salle d'attente virtuelle (queue-it) qui expire **toutes les 10 minutes**.
Sans cookie valide, le scraper est bloqué avec le message :
`Redirigé vers queue-it.net — cookie expiré`

### Option A — Export manuel (simple, mais cookie expire vite)

1. Ouvre Chrome/Firefox → va sur `https://tenup.fft.fr`
2. Attends que la page charge complètement (passe la salle d'attente si nécessaire)
3. Ouvre l'extension **Cookie-Editor** → Export → copie le JSON → colle dans `cookies.json`
4. **Lance ta commande dans les 5 minutes** qui suivent

### Option B — Refresh automatique (recommandé, obligatoire pour les runs longs)

Nécessite TamperMonkey installé dans le navigateur + le script `tampermonkey_tenup.js` actif.

**Terminal 1 (laisser ouvert pendant tout le run) :**
```
python cookie_server.py
```
Tu dois voir : `Cookie server démarré → http://localhost:5057/update_cookie`

**Navigateur :** Ouvre `https://tenup.fft.fr` et laisse l'onglet ouvert.
TamperMonkey envoie automatiquement les cookies toutes les 8 min.
Tu verras dans le terminal : `✅ 31 cookies mis à jour → cookies.json`

**Terminal 2 :** Lance ton run avec `--cookies cookies.json` (voir commandes ci-dessous).

---

## Générateurs HTML disponibles

Le flag `--generator` permet de choisir le style visuel du rapport HTML :

| Flag | Description |
|---|---|
| `--generator v1` | Style original Bootstrap (défaut) |
| `--generator v2` | Style épuré avec filtres avancés repliés |
| `--generator v3` | Panel de filtres sombre (dark theme) — **recommandé** |

**Ajouter `--generator v3` à toutes les commandes** pour obtenir le design moderne.

---

## CAS 1 — Scraper les tournois de ta ville (usage principal)

### Scraping complet + enrichissement des formats + HTML v3
```
python main.py --enrich --cookies cookies.json --generator v3
```
Le menu interactif te demande la ville, la distance et les dates. Appuie sur Entrée pour valider les valeurs par défaut.

### Scraping sans enrichissement (plus rapide, sans format F1-F7)
```
python main.py --cookies cookies.json --generator v3
```

### Refresh complet : fix encodage + formats manquants + statuts (sans re-scraper)
```
python main.py --refresh --cookies cookies.json --generator v3
```

### Mettre à jour uniquement les statuts d'inscription (sans re-scraper)
```
python main.py --enrich-statut-only --cookies cookies.json --generator v3 --no-prompt --city "VAIRES SUR MARNE, 77360" --km 100 --lat 48.874 --lng 2.638
```
Rafraîchit les statuts (Ouvert / Clôturé / Bientôt…). Ignore les tournois terminés.
Durée : ~1.5s × tournois à venir (ex: 80 tournois ≈ 2 minutes).

### Re-enrichir les formats sans re-scraper
```
python main.py --enrich-only --cookies cookies.json --generator v3 --no-prompt --city "VAIRES SUR MARNE, 77360" --km 100 --lat 48.874 --lng 2.638
```

### Ajouter les distances routières et temps de trajet (pas besoin de cookies)
```
python main.py --enrich-geo-only --generator v3 --no-prompt --city "VAIRES SUR MARNE, 77360" --km 100 --lat 48.874 --lng 2.638
```
Durée : ~45 secondes pour 368 tournois.

### Régénérer uniquement le fichier HTML (sans rien télécharger)
```
python main.py --html-only --generator v3 --no-prompt --city "VAIRES SUR MARNE, 77360" --km 100
```

---

## CAS 2 — Run France entière (toutes les villes de cities_france.json)

> **Temps estimé :** scraping ~30-60 min | enrichissement ~2-15h | distances ~3 min | statuts ~5-15 min

### Étape 1 — Scraper toutes les villes (cookies requis)
```
python run_batch.py --cookies cookies.json --date-start 01/04/26 --date-end 31/12/26
```

### Étape 2 — Enrichir (récupérer les formats)
```
python run_batch.py --enrich-only --cookies cookies.json
```
Les tournois déjà enrichis sont ignorés → peut être interrompu et relancé.

### Étape 3 — Distances routières (pas besoin de cookies)
```
python run_batch.py --enrich-geo-only
```

### Étape 4 — Juste régénérer les HTMLs sans rien télécharger
```
python run_batch.py --html-only
```

### Ou tout en une seule commande
```
python run_batch.py --cookies cookies.json --enrich --enrich-geo --date-start 01/04/26 --date-end 31/12/26
```

---

## CAS 3 — Reprendre après une coupure / erreur

Les tournois qui ont échoué sont marqués `fetch_failed=True` dans le JSON.
Ils sont automatiquement retentés au prochain run :
```
python main.py --enrich-only --cookies cookies.json --generator v3 --no-prompt --city "VAIRES SUR MARNE, 77360" --km 100 --lat 48.874 --lng 2.638
```

---

## CAS 4 — Corriger des mauvais flags

Parfois, si l'enrichissement s'est fait sans cookie valide, des tournois sont marqués
`no_format_in_html=True` à tort. Pour corriger :

```
python reset_no_format.py --dry-run
python reset_no_format.py
python main.py --enrich-only --cookies cookies.json --generator v3 --no-prompt --city "VAIRES SUR MARNE, 77360" --km 100 --lat 48.874 --lng 2.638
```

**Recalculer les distances routières depuis zéro :**
```
python main.py --enrich-geo-only --reset-geo --generator v3 --no-prompt --city "VAIRES SUR MARNE, 77360" --km 100 --lat 48.874 --lng 2.638
```

---

## CAS 5 — Vérifier l'état des données

```
python check_enrichment.py
```
Affiche par fichier : ok / fetch_failed / no_format / non traités.

---

## Fichiers produits

| Fichier | Contenu |
|---|---|
| `data/tournaments_<ville>_<km>km.json` | Données brutes + enrichies |
| `data/history_<ville>_<km>km.json` | IDs connus → détection des nouveaux |
| `data/tournaments_<ville>_<km>km.html` | Rapport HTML (v1 par défaut, v3 si --generator v3) |
| `data/tournaments_france_entiere.html` | Rapport combiné toutes villes (dédupliqué) |

---

## Filtres disponibles dans le rapport HTML

| Filtre | Ce qu'il fait |
|---|---|
| 🔍 Rechercher | Cherche dans nom, juge, ville, club |
| Ligue | Sélectionne une ligue → coche automatiquement ses départements |
| Comités | Panneau multi-sélection de départements |
| Épreuve | Panneau multi-sélection — ex : SM 11/12 ET SM 13/14 simultanément |
| Vol d'oiseau max (km) | Distance à vol d'oiseau depuis la ville de référence |
| 🚗 Trajet max (km) | Distance réelle par la route |
| 🕐 Trajet max (min) | Temps de trajet estimé en voiture |
| Surface | Panneau multi-sélection |
| Format | Panneau multi-sélection F1-F7 + "sans format" |
| Statut inscription | Panneau multi-sélection (Ouvert, Bientôt, Clôturé…) |
| Masquer terminés | Cochée par défaut — cache les tournois dont la date de fin est passée |
| Nouveaux | Affiche uniquement les tournois apparus au dernier scraping |
| TMC | Tournois "Match Compétition" internes |
| Inscr. en ligne | Seulement ceux avec inscription en ligne |
| Masquer Vert/Orange | Cache les tournois débutants |
| Mots à exclure | Ex : `hiver open` → cache tout tournoi contenant ces mots |
| Dates | Plage de dates de début/fin |
| ⭐ Favoris | Sauvegardés dans le navigateur (localStorage) |

---

## Vues du rapport HTML

| Vue | Description |
|---|---|
| 📋 Tableau | Vue par défaut — tableau trié/paginé avec tous les filtres |
| 📅 Calendrier | Vue mensuelle — nombre de tournois par jour |
| 📊 Gantt | Diagramme de Gantt — durée des tournois sur axe temporel |
| 🗺️ Carte | Carte interactive Leaflet — marqueurs colorés par format |
| 🏖️ Vacs | Calendrier vacances scolaires Zone C + jours fériés (13 mois) |
| 🆕 Derniers | Tableau trié par date d'ajout décroissante + colonne "Ajouté le" (JJ/MM HH:MM) |

Toutes les vues respectent les filtres actifs.

---

## Statuts d'inscription

| Statut | Signification |
|---|---|
| Ouvert | Inscriptions en cours |
| Bientôt | Date d'ouverture future affichée |
| Liste d'attente | Tournoi plein — inscription possible en liste d'attente |
| Inscrit (liste d'attente) | Déjà inscrit mais en attente de place |
| Clôturé | Inscriptions fermées |
| Déjà inscrit | Inscription confirmée |
| Non éligible | Catégorie d'âge ou classement hors bornes |

---

*Document créé le 09/04/2026 — mis à jour le 11/04/2026 (repo GitHub passé en privé).*
