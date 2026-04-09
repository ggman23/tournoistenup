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

---

## Sélectionné — à implémenter 🔵

### 1. Statut d'inscription (PRIORITÉ 1) — ✅ Implémenté le 09/04/2026

**Objectif :** Récupérer et afficher le statut actuel des inscriptions de chaque tournoi.

**Ce que TenUp affiche sur les pages de détail :**
- "Inscriptions ouvertes"
- "Inscriptions closes"
- "Liste d'attente"
- "Inscriptions ouvertes à partir du JJ/MM/AAAA"
- Parfois un commentaire libre du club

**Complexité anticipée :** Élevée — comme pour les formats F1-F7, cette information est
probablement dans une div spécifique qui peut être rendue côté serveur ou côté JS selon
les tournois. Certaines pages ont une structure différente. Risque de variabilité.

**Architecture proposée :**
- Ajout dans `enrich.py` : récupérer le statut lors de l'enrichissement existant
  (même requête HTTP, même session avec cookies → pas de coût supplémentaire)
- Stocker dans `enriched` :
  ```json
  "statut_inscription": "Liste d'attente",
  "statut_fetched_at": "2026-04-09T13:00:00"
  ```
- Affichage HTML : badge coloré dans une nouvelle colonne ou dans la colonne Épreuves
- Indicateur de fraîcheur : ⚠️ si `statut_fetched_at` > 24h
- Filtre : "Inscriptions ouvertes" / "Liste d'attente" / "Closes"
- Flag `statut_fetch_failed` si la page ne contient pas l'info (comme `no_format_in_html`)

**À investiguer avant de coder :**
- Inspecter 5-6 pages de tournois aux statuts différents pour identifier les sélecteurs CSS
- Vérifier si le statut est dans le HTML statique ou dans du JS
- Identifier si la structure varie selon le type de tournoi (TMC vs standard)

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

### 3. Calendrier visuel (PRIORITÉ 3)

**Objectif :** Vue calendrier mensuelle en complément du tableau, avec clic sur une date
pour voir la liste des tournois commençant ce jour-là.

**Décisions de design :**
- Afficher sur la **date de début** du tournoi (pas une barre sur toute la durée)
- Nombre de tournois par case (ex: badge `7`), couleur selon format majoritaire
- Clic sur la case → panneau latéral avec liste des tournois du jour
- Tournois longs (> 3 semaines) marqués avec une pastille "long"
- Navigation mois par mois
- Intégré dans le même fichier HTML (onglet ou bouton bascule tableau/calendrier)

**Complexité :** Moyenne — 100% JS/CSS dans `generate_html.py`, pas de nouveau backend.

---

## Proposé — pas encore retenu ⬜

| # | Fonctionnalité | Pourquoi pas encore |
|---|---|---|
| 4 | Détection conflits de dates avec favoris | Utile mais dépend du calendrier visuel |
| 5 | Export agenda ICS (favoris → Google Calendar) | Simple à faire, faible priorité |
| 6 | Dotation financière des tournois | Info peu disponible sur TenUp |
| 7 | Historique des éditions passées | Complexe, base de données nécessaire |
| 8 | Windows Task Scheduler / cron | À faire quand Telegram sera en place |
| 9 | Mise sur NAS | Quand l'accès au NAS sera disponible |
| 10 | Déduplication avant enrichissement | Gain de temps ~80% sur le batch — optimisation technique, pas une feature |
| 11 | Normalisation noms de clubs | Heuristique difficile à fiabiliser |
| 12 | Bouton "Actualiser statut" temps réel | Dépend de l'implémentation du statut d'inscription |

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

*Document créé le 09/04/2026 — mis à jour au fil des développements.*
