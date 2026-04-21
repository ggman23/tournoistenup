# Notice d'utilisation — TournoisTenUp

> Guide pratique : quoi lancer, dans quel ordre, pour quel résultat.

---

## Règle importante pour l'assistant Claude

**Toujours donner les commandes complètes et exactes**, copiables telles quelles.
Ne jamais omettre un flag obligatoire comme `--cookies cookies.json`.
L'utilisateur n'est pas développeur — une commande incomplète est une commande fausse.

---

## Prérequis avant toute chose

1. **Python** installé (3.10+)
2. **Dépendances** : `pip install -r requirements.txt`
3. **Cookies valides** dans `cookies.json` (voir section Cookies ci-dessous)
4. Être dans le dossier du projet

---

## Les cookies — point critique

TenUp utilise une salle d'attente virtuelle (queue-it) qui expire **toutes les 10 minutes**.
Sans cookie valide : `Redirigé vers queue-it.net — cookie expiré`

### Option A — Export manuel (simple, cookie expire vite)

1. Chrome → `https://tenup.fft.fr/recherche/tournois` (page recherche, pas l'accueil)
2. Attends que la page charge complètement
3. Extension **Cookie-Editor** → Export → colle dans `cookies.json`
4. Lance la commande dans les 5 minutes qui suivent

### Option B — Refresh automatique (obligatoire pour runs longs)

**Terminal 1 (laisser ouvert pendant tout le run) :**
```
python cookie_server.py
```
Doit afficher : `Cookie server démarré → http://localhost:5057/update_cookie`

**Navigateur :** Ouvre `https://tenup.fft.fr` et laisse l'onglet ouvert.
TamperMonkey envoie les cookies toutes les 8 min automatiquement.

**Terminal 2 :** Lance ton run normalement avec `--cookies cookies.json`.

---

## L'outil principal : tenup_v2.bat

Double-clique sur `tenup_v2.bat`. Menu interactif avec toutes les options.
Un fichier de log horodaté est créé automatiquement dans `logs/` à chaque lancement.

### Menu complet

| Option | Nom | Ce que ça fait | Durée | Cookies |
|--------|-----|----------------|-------|---------|
| **[10]** | Tout tout tout — option nuit | [7]+[8]+[3] : scraping + geo + formats + statuts | ~3h30 | Oui |
| [9] | France complète | [7]+[8] : scraping + geo + formats nouveaux | ~3h | Oui |
| [8] | Enrichir toute la France | Formats + statuts + commentaires pour tous les tournois | ~2h | Oui |
| [7] | France entière + distances | 2700+ tournois scraping + distances routières | ~25 min | Oui |
| [6] | Tout pour une ville | Scraping + formats + statuts + distances (zone locale) | variable | Oui |
| [5] | Distances routières seules | Après un [1] ou [7] oublié | ~10 min | Non |
| [4] | Générer HTML uniquement | Régénère HTML depuis données existantes | <1 min | Non |
| [3] | Refresh statuts | Actualise ouvert/attente/clôturé pour tous les tournois | ~30 min | Oui |
| [2] | Scraper + Enrichir une ville | Scraping zone + formats + statuts locaux | variable | Oui |
| [1] | France entière (scraping seul) | 2700+ tournois sans formats ni distances | ~15 min | Oui |

### Questions posées au démarrage

Lors d'un run qui nécessite une ville de référence, le script pose **trois questions** :

1. **Ville** (ex: `Vaires-sur-Marne`) — mémorisée dans `config.json`
2. **Rayon en km** (ex: `1100`) — mémorisé dans `config.json`
3. **Rue de départ** (ex: `6 rue des Loriots`) — mémorisée dans `config.json`

La rue de départ est utilisée pour construire les liens Google Maps dans le rapport HTML.
Elle est pré-remplie à la valeur précédente — appuie sur Entrée pour la conserver.

### Workflow recommandé

**Première fois :**
```
Lancer [9] ou [10]  →  ~3h  →  tous les tournois France avec formats + distances
```

**Chaque semaine (vendredi soir) :**
```
Lancer [10]  →  ~3h30  →  nouveaux tournois + statuts à jour
```

**Vacances dans une autre ville (ex: Saint-Jean-de-Monts) :**
```
Lancer [2]  →  entrer "Saint-Jean-de-Monts" + "150 km"  →  tournois locaux enrichis
```

**Juste vérifier les statuts ce matin :**
```
Lancer [3]  →  ~30 min  →  statuts à jour
```

### Note importante sur [8] et [10]

Lors du lancement de [8] ou [10], le script demande la **même ville et le même rayon**
que lors du [7] précédent. Par exemple : `Vaires-sur-Marne` puis `1100` km.
Les tournois déjà enrichis sont automatiquement sautés — seuls les nouveaux sont traités.

---

## Lire les logs après un run

Chaque lancement crée un fichier dans le dossier `logs/` :
```
logs/tenup_20260419_21h30.log
```
Ouvre-le avec le Bloc-notes ou VS Code pour relire toutes les pages scrapées,
les tournois enrichis, les éventuelles erreurs.

---

## Générateurs HTML

| Flag | Description |
|---|---|
| `--generator v1` | Style Bootstrap original |
| `--generator v2` | Style épuré, filtres repliés |
| `--generator v3` | Panel de filtres sombre — **recommandé**, utilisé par tenup_v2.bat |

### Fichiers produits

Chaque run produit **deux fichiers HTML** :
- `tournaments_<ville>_<km>km.html` — rapport complet toutes épreuves
- `tournaments_<ville>_<km>km_sm.html` — rapport SM 11/12 + 13/14 ans uniquement

---

## Commandes directes (sans bat)

### Scraping + enrichissement zone locale
```
python main_v2.py --enrich --cookies cookies.json --generator v3
```

### France entière force-pages
```
python main_v2.py --km 1100 --force-pages 200 --enrich-geo --cookies cookies.json --generator v3
```

### Enrichir sans re-scraper
```
python main_v2.py --enrich-only --cookies cookies.json --generator v3
```

### Refresh statuts uniquement
```
python main_v2.py --enrich-statut-only --cookies cookies.json --generator v3
```

### Distances routières uniquement
```
python main_v2.py --enrich-geo-only --generator v3
```

### Régénérer HTML sans téléchargement
```
python main_v2.py --html-only --generator v3
```

---

## Filtres disponibles dans le rapport HTML

| Filtre | Ce qu'il fait |
|---|---|
| Rechercher | Cherche dans nom, juge, ville, club |
| Ligue | Sélectionne une ligue → coche automatiquement ses départements |
| Comités | Panneau multi-sélection de départements |
| Épreuve | Panneau multi-sélection — ex : SM 11/12 ET SM 13/14 simultanément |
| Vol d'oiseau max (km) | Distance à vol d'oiseau depuis la ville de référence |
| Trajet max (km) | Distance réelle par la route |
| Trajet max (min) | Temps de trajet estimé en voiture |
| Surface | Panneau multi-sélection |
| Format | Panneau multi-sélection F1-F7 + "sans format" |
| Statut inscription | Panneau multi-sélection (Ouvert, Bientôt, Clôturé…) |
| Masquer terminés | Cochée par défaut — cache les tournois dont la date de fin est passée |
| Nouveaux | Affiche uniquement les tournois apparus au dernier scraping |
| TMC | Tournois "Match Compétition" internes |
| Inscr. en ligne | Seulement ceux avec inscription en ligne |
| Masquer Vert/Orange | Cache les tournois débutants |
| Mots à exclure | Ex : `hiver open` → cache les tournois contenant ces mots |
| Dates | Plage de dates de début/fin |
| 🚫 Absent | Cache les tournois qui chevauchent tes absences du Planning |
| Favoris | Sauvegardés dans le navigateur (localStorage) |

### Filtre date — comportement précis

- **"DATES DU 25/04"** (date de début seule, sans date de fin) : affiche uniquement les tournois
  qui **débutent exactement** le 25/04. Les tournois en cours ce jour mais commencés avant sont cachés.
- **"DATES DU 25/04 AU 27/04"** (fenêtre) : affiche les tournois dont les dates chevauchent
  la fenêtre — un tournoi 24→26/04 reste visible car il se déroule pendant la fenêtre.

### Boutons de réinitialisation

| Bouton | Effet |
|--------|-------|
| ↺ Réinitialiser | Restaure les filtres par défaut (SM sélectionné, masquer vert/orange actif) |
| ✕ Tout vider | Efface absolument tout — ardoise vierge |

---

## Vues du rapport HTML

| Vue | Description |
|---|---|
| Tableau | Vue par défaut — tableau trié/paginé |
| Calendrier | Vue mensuelle — nombre de tournois par jour. Les jours avec absences Planning apparaissent en orange. |
| Gantt | Diagramme de Gantt — durée des tournois sur axe temporel |
| Carte | Carte interactive — marqueurs colorés par format, isochrones 30/60 min routières. Plusieurs tournois en même ville → badge numéroté, popup liste tous. |
| Vacs | Calendrier vacances scolaires Zone C + jours fériés (13 mois) |
| Derniers | Tableau trié par date d'ajout décroissante + colonne "Ajouté le" |
| 🗓️ Planning | Calendrier mensuel d'absences — clic sur un jour pour noter une absence (stockée en localStorage) |
| ❌ Ratés | Liste des tournois bloqués par les absences du Planning, triés par distance depuis la ville de référence |

**Dans l'onglet Carte :** tu peux changer la ville de référence — les isochrones 30/60 min
se recalculent automatiquement en temps réel via l'API Valhalla (vraies routes).

### Vue Planning — utilisation

1. Clique sur l'onglet **🗓️ Planning**
2. Clique sur un jour pour saisir une note (ex: "Vacances Bretagne" ou "Mariage")
3. Le jour s'affiche en orange dans le Planning et dans le Calendrier
4. Coche le filtre **🚫 Absent** dans les filtres → les tournois qui chevauchent tes absences disparaissent
5. Va dans **❌ Ratés** pour voir la liste complète des tournois manqués, triés du plus proche au plus loin

### Logique "tournoi bloqué"

Le filtre Absent utilise ces règles selon la durée du tournoi :
- Tournoi ≤ 4 jours : bloqué si **au moins 1 jour d'absence** chevauche
- Tournoi 5-14 jours : bloqué si **40 %** des jours ou plus sont absents
- Tournoi > 14 jours : bloqué si **60 %** des jours ou plus sont absents

### Ville cliquable → Google Maps

Dans le tableau, le nom de la ville est un lien cliquable. Il ouvre Google Maps avec :
- **Origine** : ta rue de départ (saisie au démarrage du script)
- **Destination** : l'adresse textuelle complète du club (plus fiable que les coordonnées GPS)

---

## Statuts d'inscription

| Statut | Signification |
|---|---|
| Ouvert | Inscriptions en cours |
| Bientôt | Date d'ouverture future affichée |
| Liste d'attente | Tournoi plein — inscription possible en liste d'attente |
| Inscrit (attente) | Déjà inscrit mais en attente de place |
| Clôturé | Inscriptions fermées |
| Déjà inscrit | Inscription confirmée |
| Non éligible | Catégorie d'âge ou classement hors bornes |

---

## Reprendre après une coupure / erreur

Les tournois qui ont échoué sont marqués `fetch_failed=True` dans le JSON
et automatiquement retentés au prochain run :
```
python main_v2.py --enrich-only --cookies cookies.json --generator v3
```

## Corriger des faux "no_format_in_html"

Si l'enrichissement s'est fait sans cookie valide, utiliser :
```
python reset_no_format.py --dry-run
python reset_no_format.py
python main_v2.py --enrich-only --cookies cookies.json --generator v3
```

## Recalculer les distances routières depuis zéro

```
python main_v2.py --enrich-geo-only --reset-geo --generator v3
```

---

## Fichiers produits

| Fichier | Contenu |
|---|---|
| `data/tournaments_<ville>_<km>km.json` | Données brutes + enrichies |
| `data/tournaments_<ville>_<km>km_sm.html` | Rapport HTML SM 11/12 + 13/14 ans uniquement |
| `data/history_<ville>_<km>km.json` | IDs connus → détection des nouveaux |
| `data/tournaments_<ville>_<km>km.html` | Rapport HTML interactif complet |
| `logs/tenup_YYYYMMDD_HHhMMSS.log` | Log complet de chaque run |

---

*Document créé le 09/04/2026 — mis à jour le 20/04/2026 (rue de départ, ville cliquable Maps, Planning, Absent, Ratés, clustering carte, filtre date, HTML SM, vues).*
