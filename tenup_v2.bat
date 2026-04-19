@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TenUp v2 — Scraper de tournois de tennis

:menu
cls
echo.
echo  =============================================================
echo    TENUP v2  —  Scraper de tournois de tennis
echo  =============================================================
echo.
echo  [1]  France entiere  (scraping seul, ~15 min)
echo       2700+ tournois, infos de base, tri par distance vol d'oiseau.
echo       Sans distances routieres — carte incomplete.
echo       Demande : ville de reference / dates
echo.
echo  [7]  France entiere + distances routieres  (recommande, ~25 min)
echo       Meme chose que [1] mais calcule aussi les distances routieres.
echo       Carte 100%% complete, isochrones 30/60 min utilisables.
echo       Demande : ville de reference / dates
echo.
echo  [2]  Scraper + Enrichir une ville  (formats + statuts)
echo       Scrape une zone reduite et visite chaque page de tournoi.
echo       Necessite cookies.json
echo       Demande : ville / rayon (suggestion 100 km) / dates
echo.
echo  [3]  Refresh statuts uniquement  (ouvert / liste d'attente...)
echo       Actualise les statuts sans re-scraper.
echo       A lancer une fois par jour pour une zone donnee.
echo       Necessite cookies.json
echo       Demande : ville / rayon (suggestion 100 km)
echo.
echo  [4]  Generer le HTML uniquement
echo       Regenere la page HTML depuis les donnees existantes.
echo       Aucune requete vers TenUp.
echo       Demande : ville / rayon
echo.
echo  [5]  Calculer les distances routieres uniquement
echo       A lancer apres [1] si vous avez oublie [7].
echo       Aucune requete vers TenUp.
echo       Demande : ville / rayon
echo.
echo  [6]  Tout pour une ville  (le plus complet)
echo       Scrape + Formats + Statuts + Distances routieres.
echo       Necessite cookies.json
echo       Demande : ville / rayon (suggestion 100 km) / dates
echo.
echo  [8]  Enrichir toute la France  (formats + statuts + commentaires)
echo       A lancer apres [7] pour completer les infos de tous les tournois.
echo       Jitter + pauses automatiques pour eviter le ban (~2h).
echo       Necessite cookies.json
echo       Demande : meme ville / meme rayon que lors du [7]
echo.
echo  [9]  France complete  [7] + [8]
echo       Scraping + distances routieres + formats nouveaux tournois.
echo       Lancez et revenez dans ~3h.
echo       Necessite cookies.json
echo       Demande : ville de reference / dates  (une seule fois)
echo.
echo  [10] Tout tout tout  [7] + [8] + [3]  — option nuit
echo       Comme [9] + refresh statuts de TOUS les tournois existants.
echo       Lancez avant de dormir, tout est pret le matin. (~3h30)
echo       Necessite cookies.json
echo       Demande : ville de reference / dates  (une seule fois)
echo.
echo  [0]  Quitter
echo.
echo  =============================================================
echo.
set "choix="
set /p choix=  Votre choix :

if "%choix%"=="1" goto france
if "%choix%"=="7" goto france_geo
if "%choix%"=="2" goto enrichir_ville
if "%choix%"=="3" goto statuts
if "%choix%"=="4" goto html
if "%choix%"=="5" goto geo
if "%choix%"=="6" goto tout_ville
if "%choix%"=="8" goto enrichir_france
if "%choix%"=="9" goto france_complete
if "%choix%"=="10" goto tout_tout_tout
if "%choix%"=="0" goto fin

echo.
echo  Choix invalide, veuillez ressaisir.
timeout /t 2 >nul
goto menu

:: ─────────────────────────────────────────────────────────────────────────────
:france
cls
echo.
echo  [1] France entiere  (scraping seul)
echo  ─────────────────────────────────────────────────────────────
echo.
echo  Rayon fixe : 1100 km — Force 200 pages pour couvrir toute la France.
echo  Distances routieres non calculees (carte incomplete).
echo  Lancez ensuite [5] ou utilisez [7] pour tout faire d'un coup.
echo.
python main_v2.py --km 1100 --force-pages 200 --cookies cookies.json --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:france_geo
cls
echo.
echo  [7] France entiere + distances routieres  (recommande)
echo  ─────────────────────────────────────────────────────────────
echo.
echo  Rayon fixe : 1100 km — Force 200 pages pour couvrir toute la France.
echo  Calcule ensuite les distances routieres pour tous les tournois.
echo  Carte 100%% complete avec isochrones 30/60 min.
echo  Duree totale : ~25 min. Lancez et faites autre chose.
echo.
python main_v2.py --km 1100 --force-pages 200 --enrich-geo --cookies cookies.json --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:enrichir_ville
cls
echo.
echo  [2] Scrape + Formats + Statuts  (zone locale)
echo  ─────────────────────────────────────────────────────────────
echo.
echo  Entrez la ville et le rayon souhaites.
echo  Exemple : Marseille, 100 km pour les vacances.
echo  Les formats deja connus (autres villes) ne seront pas re-telecharges.
echo.
python main_v2.py --enrich --km-default 100 --cookies cookies.json --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:statuts
cls
echo.
echo  [3] Refresh statuts  (zone locale)
echo  ─────────────────────────────────────────────────────────────
echo.
echo  Entrez la ville et le rayon dont vous voulez actualiser les statuts.
echo.
python main_v2.py --enrich-statut-only --km-default 100 --cookies cookies.json --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:html
cls
echo.
echo  [4] Generation HTML uniquement
echo  ─────────────────────────────────────────────────────────────
echo.
python main_v2.py --html-only --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:geo
cls
echo.
echo  [5] Calcul des distances routieres uniquement
echo  ─────────────────────────────────────────────────────────────
echo.
echo  A utiliser apres [1] si vous avez oublie de faire [7].
echo.
python main_v2.py --enrich-geo-only --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:tout_ville
cls
echo.
echo  [6] Tout pour une ville  (scrape + formats + statuts + distances)
echo  ─────────────────────────────────────────────────────────────
echo.
echo  Entrez la ville et le rayon souhaites.
echo  Les formats deja connus (autres villes) ne seront pas re-telecharges.
echo.
python main_v2.py --enrich --enrich-geo --km-default 100 --cookies cookies.json --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:tout_tout_tout
cls
echo.
echo  [10] Tout tout tout  —  option nuit
echo  ─────────────────────────────────────────────────────────────
echo.
echo  Etape 1/3 : Scraping 2700+ tournois + distances routieres (~25 min)
echo  Etape 2/3 : Enrichissement nouveaux tournois (~variable)
echo  Etape 3/3 : Refresh statuts de TOUS les tournois (~30 min)
echo  Duree totale : ~3h30. Lancez et allez dormir.
echo.
python main_v2.py --km 1100 --force-pages 200 --enrich-geo --cookies cookies.json --generator v3
if errorlevel 1 goto fin_action
echo.
echo  Etape 1/3 terminee. Enrichissement des nouveaux tournois...
echo.
python main_v2.py --enrich-only --no-prompt --km 1100 --cookies cookies.json --generator v3
if errorlevel 1 goto fin_action
echo.
echo  Etape 2/3 terminee. Refresh statuts de tous les tournois...
echo.
python main_v2.py --enrich-statut-only --no-prompt --km 1100 --cookies cookies.json --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:france_complete
cls
echo.
echo  [9] France complete  (scraping + distances + formats + statuts)
echo  ─────────────────────────────────────────────────────────────
echo.
echo  Etape 1/2 : Scraping 2700+ tournois + distances routieres (~25 min)
echo  Etape 2/2 : Enrichissement formats + statuts + commentaires (~2h)
echo  Duree totale : ~3h. Lancez et faites autre chose.
echo.
python main_v2.py --km 1100 --force-pages 200 --enrich-geo --cookies cookies.json --generator v3
if errorlevel 1 goto fin_action
echo.
echo  Etape 1/2 terminee. Lancement de l'enrichissement...
echo.
python main_v2.py --enrich-only --no-prompt --km 1100 --cookies cookies.json --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:enrichir_france
cls
echo.
echo  [8] Enrichir toute la France  (formats + statuts + commentaires)
echo  ─────────────────────────────────────────────────────────────
echo.
echo  Entrez la meme ville et le meme rayon que lors du [7] (ex: 1100 km).
echo  Visite chaque page de tournoi pour recuperer formats + statuts.
echo  Jitter anti-ban : delai aleatoire entre chaque requete.
echo  Pause de 20-45s toutes les 100 requetes.
echo  Sauvegarde automatique toutes les 50 requetes.
echo  Duree estimee : ~2h pour 2700 tournois.
echo.
python main_v2.py --enrich-only --km-default 1100 --cookies cookies.json --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:fin_action
echo.
echo  =============================================================
echo   Termine ! Appuyez sur une touche pour revenir au menu...
echo  =============================================================
pause >nul
goto menu

:: ─────────────────────────────────────────────────────────────────────────────
:fin
echo.
echo   Au revoir !
timeout /t 2 >nul
exit
