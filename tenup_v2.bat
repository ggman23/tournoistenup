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
echo  [1]  Scraper toute la France  (infos de base)
echo       Recupere les 2700+ tournois sur tout le territoire.
echo       Force 200 pages pour ne rater aucun tournoi (~30 min).
echo       Demande : ville de reference / dates
echo       Rayon fixe : 1100 km
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
echo  [5]  Calculer les distances routieres
echo       Calcule les distances de conduite depuis la ville choisie.
echo       Aucune requete vers TenUp.
echo       Demande : ville / rayon
echo.
echo  [6]  Tout pour une ville  (le plus complet)
echo       Scrape + Formats + Statuts + Distances routieres.
echo       Necessite cookies.json
echo       Demande : ville / rayon (suggestion 100 km) / dates
echo.
echo  [0]  Quitter
echo.
echo  =============================================================
echo.
set "choix="
set /p choix=  Votre choix :

if "%choix%"=="1" goto france
if "%choix%"=="2" goto enrichir_ville
if "%choix%"=="3" goto statuts
if "%choix%"=="4" goto html
if "%choix%"=="5" goto geo
if "%choix%"=="6" goto tout_ville
if "%choix%"=="0" goto fin

echo.
echo  Choix invalide, veuillez ressaisir.
timeout /t 2 >nul
goto menu

:: ─────────────────────────────────────────────────────────────────────────────
:france
cls
echo.
echo  [1] Scrape toute la France  (1100 km fixe)
echo  ─────────────────────────────────────────────────────────────
echo.
echo  Rayon fixe : 1100 km (toute la France metropolitaine + Corse)
echo  Force 200 pages pour ignorer le stop sur doublons de TenUp.
echo  Seules la ville de reference et les dates seront demandees.
echo.
python main_v2.py --km 1100 --force-pages 200 --cookies cookies.json --generator v3
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
echo  [5] Calcul des distances routieres
echo  ─────────────────────────────────────────────────────────────
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
