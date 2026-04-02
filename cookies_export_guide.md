# Export des cookies depuis votre navigateur

Si vous êtes connecté sur tenup.fft.fr, vous pouvez exporter vos cookies
pour que le scraper accède aux résultats en tant qu'utilisateur authentifié.

## Méthode recommandée : Extension "EditThisCookie" ou "Cookie-Editor"

1. Installez [Cookie-Editor](https://cookie-editor.com/) sur Chrome/Firefox
2. Connectez-vous sur https://tenup.fft.fr
3. Ouvrez Cookie-Editor
4. Cliquez **Export** → **Export as JSON**
5. Sauvegardez le fichier sous `cookies.json` dans ce dossier

## Format attendu (JSON)

```json
[
  {
    "name": "SESS...",
    "value": "abc123...",
    "domain": ".tenup.fft.fr",
    "path": "/",
    "httpOnly": true,
    "secure": true
  },
  ...
]
```

## Utilisation

```bash
python main.py --cookies cookies.json
```

Ou définissez la variable d'environnement :

```bash
export TENUP_COOKIES_FILE=cookies.json
python main.py
```

## Notes

- Les cookies de session expirent (généralement après quelques heures/jours)
- Sans cookies, le scraper fonctionne quand même mais sans le filtre `filter_mine`
- La plupart des tournois publics sont accessibles sans authentification
