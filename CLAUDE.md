# Notes pour Claude — TournoisTenUp

## GitHub PAT — synchronisation des favoris

Le token GitHub et le Gist ID sont stockés dans le fichier `.env` (gitignore, jamais committé).
Le fichier `.env` à la racine du projet contient les variables :
- `TENUP_GIST_TOKEN` — token GitHub avec scope gist uniquement
- `TENUP_GIST_ID` — ID du Gist privé des favoris partagés

`generate_html_v3.py` les lit automatiquement via `_load_gist_env()` au démarrage.
Si le fichier `.env` n'existe pas (nouvelle machine), le recréer depuis les notes sécurisées
du propriétaire du projet.

Le Gist des favoris est sur le compte GitHub ggman23 (Gist privé nommé "TournoisTenUp — favoris partagés").
