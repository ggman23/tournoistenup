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
| Rapport HTML interactif | Bootstrap + DataTables, tri, pagination, export Excel/CSV/PDF |
| Filtre épreuves | Multi-sélection par panneau de chips (SM, SD, DM, DD, DX) |
| Filtre ligue / comités | 13 ligues métropolitaines, sélection multi-départements |
| Barre de recherche | Recherche plein texte dans nom, juge, ville, club |
| Distances routières | Géocodage batch (api-adresse.data.gouv.fr) + OSRM table |
| Filtres trajet | Trajet max (km) et trajet max (min) dans le rapport HTML |
| Cookie auto-refresh | TamperMonkey + cookie_server.py, polling mtime 15s |
| Détection nouveaux | Badge NEW uniquement au scraping — plus de badges parasites en mode enrich/html-only |
| Vue Derniers | Tri par date d'ajout décroissante (`_first_seen` stamped au scraping) |
| Favoris | Sauvegardés en localStorage dans le navigateur |
| Masquer Vert/Orange | Filtre tournois débutants par mot-clé dans le nom |
| Statut d'inscription | Badge par épreuve (Ouvert/Bientôt/Clôturé/etc.), filtre multi-sélection, commentaire club |
| Distinction inscrit/attente | "Déjà inscrit en attente" vs "liste d'attente générale" |
| Filtres multi-sélection | Épreuve, Surface, Format, Statut en panneaux de chips (sélection multiple OR) |
| Filtrage lignes épreuves | Filtre Format masque les lignes d'épreuves non correspondantes |
| Vue Calendrier | Onglet calendrier mensuel respectant les filtres actifs |
| Vue Gantt | Diagramme de Gantt respectant les filtres actifs |
| Vue Carte | Onglet carte interactive Leaflet, marqueurs colorés par format, ville de référence ★ |
| Vue Vacs | Calendrier vacances scolaires Zone C + jours fériés sur 13 mois (APIs gouvernementales) |
| Export PDF enrichi | PDF paysage avec colonne épreuves en nested table (classement, tarif, statut, format) |
| --generator v1/v2/v3 | Choix du thème visuel du rapport HTML via flag en ligne de commande |
| UI v3 dark panel | Panel de filtres thème sombre (dark navy) avec tous les contrôles v1 conservés |
| --refresh | Tout-en-un : fix-encoding + enrich + statuts en une seule commande |
| --enrich-statut-only | Rafraîchit uniquement les statuts d'inscription, ignore les tournois terminés |
| Fix encodage UTF-8 | Correction des textes corrompus (double-encodage latin-1/UTF-8) avec retry x5 |

---

## Sélectionné — à implémenter 🔵

### 1. Notifications Telegram (PRIORITÉ 1)

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

**Prérequis utilisateur :**
1. Créer un bot Telegram via @BotFather → obtenir `bot_token`
2. Obtenir son `chat_id` (envoyer un message au bot, récupérer l'ID via l'API)
3. Renseigner dans `config.json`

---

## Proposé — pas encore retenu ⬜

| # | Fonctionnalité | Pourquoi pas encore |
|---|---|---|
| 1 | Export agenda ICS (favoris → Google Calendar) | Simple à faire, faible priorité |
| 2 | Dotation financière des tournois | Info peu disponible sur TenUp |
| 3 | Historique des éditions passées | Complexe, base de données nécessaire |
| 4 | Windows Task Scheduler / cron | À faire quand Telegram sera en place |
| 5 | Mise sur NAS | Quand l'accès au NAS sera disponible |
| 6 | Déduplication avant enrichissement | Gain de temps ~80% sur le batch — optimisation technique |
| 7 | Normalisation noms de clubs | Heuristique difficile à fiabiliser |
| 8 | Bouton "Actualiser statut" temps réel | Peu utile : clic sur le lien TenUp est plus simple |
| 9 | Détection conflits de dates avec favoris | Calendrier et vue Gantt couvrent ce besoin |

---

## Notes techniques transverses

### Ce qu'on sait sur les pages de détail TenUp

- Les pages de détail nécessitent le **cookie queue-it** pour retourner le HTML complet
  (sans cookie, les divs de format et de statut sont absentes)
- Certaines pages sont rendues **côté JS** (flag `no_format_in_html`) → impossible à parser
  sans navigateur headless
- La structure HTML varie selon le type de tournoi (TMC vs homologué vs championnat)

### Badges NEW — comportement correct depuis v3

- Les badges NEW n'apparaissent **que lors d'un scraping** qui détecte un vrai nouveau tournoi
- En mode `--html-only`, `--enrich-only`, `--enrich-statut-only`, `--enrich-geo-only`,
  `--fix-encoding`, `--refresh` → `new_ids = set()` → aucun badge parasite
- `_first_seen` est stamped sur chaque nouveau tournoi au moment du scraping et préservé lors des re-scrapes

---

*Document créé le 09/04/2026 — mis à jour le 11/04/2026.*
