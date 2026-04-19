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
| 1 | Changement de ville de référence dans HTML | Saisir une ville → géocodage Nominatim (1 appel) → recalcul vol d'oiseau Haversine en JS → distance routière approx ×1.3 → re-tri tableau. Utile pour les vacances (Saint-Jean-de-Monts…). |
| 2 | Alertes Telegram changement de statut | Notifier quand : Bientôt→Ouvert, Ouvert→Liste d'attente, Attente→Ouvert (place libérée). Nécessite Telegram (#1). |
| 3 | Vue "Inscriptions disponibles" | Onglet dédié : uniquement les tournois avec statut Ouvert dans les catégories filtrées. Vue rapide "où peut-on encore s'inscrire ?". |
| 4 | Annotations personnelles | Note libre par tournoi en localStorage ("Covoiturage avec Martin"). Visible dans tableau, exportable PDF. |
| 5 | Windows Task Scheduler | Configurer une tâche planifiée pour lancer [10] chaque semaine automatiquement (ex: vendredi 23h). |
| 6 | Export ICS favoris | Favoris → format iCalendar → import Google Calendar / Apple Calendar. |
| 7 | Partage de favoris | Export/import JSON des favoris pour coordonner avec un autre parent ou partenaire de double. |

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

---

*Document créé le 09/04/2026 — mis à jour le 19/04/2026 (v2, force-pages, jitter, options 7-10, nouvelles propositions).*
