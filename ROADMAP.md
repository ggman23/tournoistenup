# Roadmap — TournoisTenUp

> Évolutions proposées, statut et ordre de priorité.

---

## Légende

| Icône | Statut |
|---|---|
| ✅ | Implémenté |
| 🔵 | Sélectionné — à implémenter |
| 💬 | En attente de décision |
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
| Détection nouveaux | Badge NEW + _first_seen préservés via last_new_ids dans history.json |
| Vue Derniers | Tri par date d'ajout décroissante + colonne "Ajouté le" |
| Favoris | Sauvegardés en localStorage dans le navigateur |
| Masquer Vert/Orange | Filtre tournois débutants par mot-clé dans le nom |
| Statut d'inscription | Badge par épreuve (Ouvert/Bientôt/Clôturé/etc.), filtre multi-sélection, commentaire club |
| Filtres multi-sélection | Épreuve, Surface, Format, Statut en panneaux de chips |
| Filtrage lignes épreuves | Filtre Format masque les lignes d'épreuves non correspondantes |
| Vue Calendrier | Onglet calendrier mensuel respectant les filtres actifs |
| Vue Gantt | Diagramme de Gantt respectant les filtres actifs |
| Vue Carte | Onglet carte interactive Leaflet, marqueurs colorés par format |
| Isochrones routières | Zones 30 min / 60 min via API Valhalla (vraies routes) + fallback cercles |
| Vue Vacs | Calendrier vacances scolaires Zone C + jours fériés sur 13 mois |
| Export PDF enrichi | PDF paysage avec colonne épreuves en nested table |
| --generator v1/v2/v3 | Choix du thème visuel du rapport HTML |
| --refresh | Tout-en-un : fix-encoding + enrich + statuts |
| --enrich-statut-only | Rafraîchit uniquement les statuts d'inscription |
| Fix encodage UTF-8 | Correction des textes corrompus avec retry x5 |
| Filtre classement par épreuve | data-classements avec clé par épreuve — filtre ne check que les épreuves du filtre épreuve actif |
| Bouton "Tout vider" | resetFiltersAll() — vide tout sans défauts (vs Réinitialiser qui restore les défauts SM) |
| Compteur épreuves | En-tête HTML affiche nombre de tournois + nombre total d'épreuves |
| Architecture v2 | main_v2.py + tenup_v2.bat — cache global cross-fichiers, --km-default |
| --force-pages N | Scraping forcé sur N pages sans stop-sur-doublons — 2719 tournois France entière |
| Logs horodatés | Chaque run écrit logs/tenup_YYYYMMDD_HHhMMSS.log |
| Jitter anti-ban | Délai aléatoire 70-200% du délai de base + pause 20-45s toutes les 100 requêtes |
| Sauvegarde intermédiaire | save_callback dans enrich_all — sauvegarde JSON toutes les 50 requêtes |
| tenup_v2.bat options 7-10 | [7] France+geo / [8] Enrichir France / [9] France complète / [10] Tout tout tout nuit |
| Filtre only_ep_keys SM 11-14 | Génère un second HTML ne contenant que SM 11/12, 13/14 ans — `tournaments_*_sm.html` |
| Clustering carte | Plusieurs tournois en même ville → badge numéroté sur la carte, popup liste tous |
| Vue Planning | Calendrier mensuel avec notes d'absence en localStorage, cellules oranges, navigation mois |
| Filtre Absent 🚫 | Masque les tournois qui chevauchent les absences du Planning (`isTournamentBlocked`) |
| Vue Ratés | Liste des tournois bloqués par les absences, triés par distance depuis la ville de référence |
| Correction filtre date | `fStart` seul = tournois débutant exactement ce jour (pas de chevauchement) |
| Ville cliquable → Maps | Clic sur la ville dans le tableau → Google Maps itinéraire depuis la ville de référence |
| Rue de départ | Prompt `_prompt_rue()` mémorisé dans config — itinéraire depuis l'adresse exacte du joueur |
| Destination Maps texte | Adresse textuelle du club utilisée (plus fiable que lat/lng géocodé) |
| Fix locale git française | Détection des messages git FR/EN pour éviter faux "commit HTML échoué" |

---

## Sélectionné — à implémenter 🔵

### 1. Notifications Telegram (PRIORITÉ 1)

**Objectif :** Recevoir un message Telegram quand de nouveaux tournois sont détectés,
ou quand un tournoi passe de "Bientôt" à "Ouvert".

**Architecture proposée :**
- `notify_telegram.py` : ~30 lignes, appelle l'API Telegram Bot
- Déclenché à la fin de `main_v2.py` si `new_tournaments` non vide
- Déclenché par `enrich_statut_all` si un statut change vers "ouvert"
- Message formaté : nom, dates, ville, distance, format, lien TenUp
- Configuration dans `config.json` :
  ```json
  "telegram": { "bot_token": "XXXX:YYYY", "chat_id": "123456789" }
  ```

---

## En attente de décision 💬

| # | Fonctionnalité | Description |
|---|---|---|
| 1 | Export ICS favoris | Favoris → format iCalendar → import Google Calendar / Apple Calendar. |
| 2 | Export ICS absences | Planning → iCalendar → import Google Calendar (absences visibles depuis le téléphone). |
| 3 | Profils de filtres sauvegardés | Sauvegarder un jeu de filtres nommé (ex: "SM 13/14 Île-de-France") en localStorage — rappel en un clic. |
| 4 | Mode "Prochain week-end" | Bouton one-click qui filtre sur le prochain week-end avec des tournois disponibles. |
| 5 | Fenêtres disponibles | Depuis le Planning : identifier automatiquement les week-ends sans absence qui ont des tournois. |
| 6 | Estimation coût déplacement | Colonne calculée : distance × tarif/km configurable + frais d'inscription. |
| 7 | Notifications navigateur | Web Push API pour alertes statut (Bientôt→Ouvert) sans Telegram. |
| 8 | Comparaison côte-à-côte | Sélectionner 2-3 tournois → tableau comparatif (dates, format, distance, statut, commentaire club). |
| 9 | Fermeture imminente | Mettre en évidence les tournois dont la clôture d'inscription est dans les 48h. |
| 10 | Synchronisation Planning | Export/import JSON des absences pour partager entre appareils ou avec un partenaire de double. |
| 11 | Alertes Telegram changement statut | Notifier : Bientôt→Ouvert, Ouvert→Liste d'attente, Attente→Ouvert. Nécessite Telegram (#1). |
| 12 | Vue "Inscriptions disponibles" | Onglet dédié : uniquement les tournois avec statut Ouvert dans les catégories filtrées. |
| 13 | Annotations personnelles | Note libre par tournoi en localStorage. Visible dans tableau, exportable PDF. |
| 14 | Windows Task Scheduler | Tâche planifiée pour lancer [10] chaque semaine automatiquement (ex: vendredi 23h). |

---

## Proposé — pas encore retenu ⬜

| # | Fonctionnalité | Pourquoi pas encore |
|---|---|---|
| 1 | Filtre classement requis | Info déjà dans data-classements — filtre HTML faisable sans nouveau scraping |
| 2 | Vue "Mon planning" | Timeline des favoris — Gantt couvre partiellement |
| 3 | Historique des statuts | Tracker ouvert→attente→ouvert — nécessite stockage historique |
| 4 | Dotation financière | Info peu disponible sur TenUp |
| 5 | Historique des éditions passées | Complexe, base de données nécessaire |
| 6 | Mise sur NAS | Quand l'accès au NAS sera disponible |
| 7 | Déduplication avant enrichissement | Non prioritaire maintenant que option 8 existe |
| 8 | Normalisation noms de clubs | Heuristique difficile à fiabiliser |
| 9 | QR code dans PDF | Lien TenUp scannable depuis le PDF imprimé |
| 10 | Partage de favoris | Export/import JSON des favoris pour coordonner avec un partenaire |

---

## Notes techniques transverses

### Limite TenUp : stop-sur-doublons

Sans `--force-pages`, le scraper s'arrête à ~1828 tournois car TenUp retourne des doublons
à partir de la page ~61 avec un grand rayon. `--force-pages 200` balaie 200 pages quoi
qu'il arrive → ~2719 tournois France entière.

### Badges NEW

- Apparaissent uniquement au scraping détectant un vrai nouveau tournoi
- En `--html-only` : restaurés depuis `history["last_new_ids"]`
- En `--enrich-only`, `--enrich-statut-only`, etc. → `new_ids = set()` (aucun badge parasite)

### Fichiers HTML produits

- `tournaments_<ville>_<km>km.html` : rapport complet toutes épreuves
- `tournaments_<ville>_<km>km_sm.html` : rapport SM 11/12 + 13/14 ans uniquement

---

*Document créé le 09/04/2026 — mis à jour le 20/04/2026 (clustering carte, Planning, Absent, Ratés, Maps, rue départ, filtre date, only_ep_keys SM, locale git).*
