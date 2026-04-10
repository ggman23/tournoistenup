# Roadmap — TournoisTenUp

> Évolutions proposées, statut et ordre de priorité.

---

## Légende

| Icône | Statut |
|---|---|
| ✅ | Implémenté |
| 🔵 | Sélectionné — à implémenter |
| 💬 | Discuté — décision en attente |
| ⬜ | Proposé — pas encore retenu |

---

## Fonctionnalités implémentées ✅

| Fonctionnalité | Description |
|---|---|
| Scraping TenUp | Récupération des tournois par ville + rayon via AJAX Drupal |
| Enrichissement formats | Récupération du format F1-F7 sur chaque page de détail |
| Batch France entière | `run_batch.py` sur 8 villes, rapport combiné dédupliqué |
| Rapport HTML interactif | Bootstrap + DataTables, tri, pagination, export Excel/CSV |
| Filtre épreuves | Affiche uniquement SM (configurable dans config.json) |
| Filtre ligue / comités | 13 ligues métropolitaines, sélection multi-départements |
| Barre de recherche | Recherche plein texte dans nom, juge, ville, club |
| Distances routières | Géocodage batch (api-adresse.data.gouv.fr) + OSRM table |
| Filtres trajet | Trajet max (km) et trajet max (min) dans le rapport HTML |
| Cookie auto-refresh | TamperMonkey + cookie_server.py, polling mtime 15s |
| Détection nouveaux | Badge NEW, historique par ville, rapport horodaté |
| Favoris | Sauvegardés en localStorage dans le navigateur |
| Masquer Vert/Orange | Filtre tournois débutants par mot-clé dans le nom |
| Statut d'inscription | Badge par épreuve (Ouvert/Bientôt/Clôturé/etc.), filtre, fraîcheur 24h, commentaire club |
| Distintion inscrit/attente | Distingue "déjà inscrit en attente" vs "inscription → liste d'attente générale" |
| Filtres multi-sélection | Épreuve, Surface, Format, Statut passés en panneaux de chips (sélection multiple OR) |
| Filtrage lignes épreuves | Quand filtre Format actif, masque les lignes d'épreuves de format non sélectionné |
| Vues Calendrier + Gantt | Onglets Calendrier mensuel et Gantt respectant les filtres actifs |

---

## Sélectionné — à implémenter 🔵

### 1. Vue Carte (PRIORITÉ 1)

**Objectif :** Quatrième onglet "🗺️ Carte" à côté de Calendrier et Gantt, affichant les
tournois filtrés sur une carte interactive centrée sur la ville de référence (ex : Vaires-sur-Marne).

**Comportement attendu :**
- Carte interactive (Leaflet.js, tuiles OpenStreetMap — gratuit, sans clé API)
- Un marqueur par tournoi, coloré selon le format (F1 = rouge, F2 = orange…) ou le statut
- La carte respecte les filtres actifs (mêmes tournois que les autres vues)
- **Survol** d'un marqueur → bulle de prévisualisation : nom, dates, format, distance, statut
- **Clic sur la bulle** (ou sur le marqueur) → ouvre TenUp dans un nouvel onglet
- Re-rendu automatique quand les filtres changent (via `drawCallback` comme Calendrier/Gantt)
- La ville de référence est marquée d'un point distinct (étoile ou cercle plein)

**Données disponibles :**
- `geo_lat` / `geo_lng` stockés dans `enriched` (calculés par `enrich_geo.py`)
- Déjà exposés dans les attributs `data-*` du `<tr>` (`data-lat`, `data-lng` à ajouter)
- Les tournois sans coordonnées (non encore géocodés) sont ignorés silencieusement

**Architecture proposée :**
- Leaflet.js chargé depuis CDN (une balise `<script>` et `<link>` supplémentaires)
- Pas de backend : les coordonnées sont encodées dans les `data-*` du tableau HTML
- `renderMap()` analogue à `renderCalendar()` / `renderGantt()` — lit `getFilteredData()`
- Popup Leaflet avec le mini-résumé du tournoi et un bouton "Ouvrir TenUp"
- Ajout de `data-lat` / `data-lng` sur les `<tr>` dans `generate_html.py`

**Complexité :** Faible à moyenne — Leaflet est simple, les données sont déjà là.
Seul point délicat : gestion des marqueurs (recréer à chaque re-rendu sans fuite mémoire).

---

### 2. Notifications Telegram (PRIORITÉ 2)

**Objectif :** Recevoir un message Telegram automatiquement quand de nouveaux tournois
sont détectés dans la zone surveillée.

**Architecture proposée :**
- `notify_telegram.py` : ~30 lignes, appelle l'API Telegram Bot
- Déclenché à la fin de `main.py` si `new_tournaments` non vide
- Message formaté : nom, dates, ville, distance, format, lien TenUp
- Configuration dans `config.json` :
  ```json
  "telegram": {
    "bot_token": "XXXX:YYYY",
    "chat_id": "123456789"
  }
  ```
- Optionnel : résumé quotidien même sans nouveaux tournois ("Scan terminé, 0 nouveaux")

**Prérequis utilisateur :**
1. Créer un bot Telegram via @BotFather → obtenir `bot_token`
2. Obtenir son `chat_id` (envoyer un message au bot, récupérer l'ID via l'API)
3. Renseigner dans `config.json`

---

## Proposé — pas encore retenu ⬜

| # | Fonctionnalité | Pourquoi pas encore |
|---|---|---|
| 4 | Détection conflits de dates avec favoris | Utile mais calendrier maintenant dispo |
| 5 | Export agenda ICS (favoris → Google Calendar) | Simple à faire, faible priorité |
| 6 | Dotation financière des tournois | Info peu disponible sur TenUp |
| 7 | Historique des éditions passées | Complexe, base de données nécessaire |
| 8 | Windows Task Scheduler / cron | À faire quand Telegram sera en place |
| 9 | Mise sur NAS | Quand l'accès au NAS sera disponible |
| 10 | Déduplication avant enrichissement | Gain de temps ~80% sur le batch — optimisation technique |
| 11 | Normalisation noms de clubs | Heuristique difficile à fiabiliser |
| 12 | Bouton "Actualiser statut" temps réel | Peu utile : clic sur le lien TenUp est plus simple |

---

## Notes techniques transverses

### Ce qu'on sait sur les pages de détail TenUp

- Les pages de détail nécessitent le **cookie queue-it** pour retourner le HTML complet
  (sans cookie, les divs de format et probablement de statut sont absentes)
- Certaines pages sont rendues **côté JS** (flag `no_format_in_html`) → impossible à parser
  sans navigateur headless (Playwright/Selenium)
- La structure HTML varie selon le type de tournoi (TMC vs homologué vs championnat)
- L'enrichissement utilise la même session avec cookies → réutiliser cette requête pour
  extraire le statut ne coûte rien de plus

### Serveur de statut temps réel (volet 2 du statut)

Si on veut un bouton "Actualiser" dans le HTML, il faut un serveur local qui tourne pendant
la consultation. L'architecture serait identique à `cookie_server.py` :
- `status_server.py` sur `localhost:5058`
- Le HTML appelle `GET /status?id=206919` → le serveur fetch la page TenUp → retourne le statut
- Nécessite les cookies valides côté serveur → intégration avec `cookies.json`
- **Non prioritaire** : le volet 1 (statut horodaté) suffit pour l'usage actuel

---

*Document créé le 09/04/2026 — mis à jour le 10/04/2026.*
