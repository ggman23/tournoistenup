@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TenUp — Scraper de tournois de tennis

:menu
cls
echo.
echo  =============================================================
echo    TENUP  —  Scraper de tournois de tennis
echo  =============================================================
echo.
echo  Que voulez-vous faire ?
echo.
echo  [1]  Scraping de base
echo       Recupere la liste des tournois depuis TenUp.
echo       Rapide, pas de risque de ban.
echo       Demande : ville / km / dates de debut et fin
echo.
echo  [2]  Scraping + Formats (F1-F7) + Statuts d'inscription
echo       Visite la page de chaque tournoi pour recuperer
echo       le format de jeu ET le statut (ouvert / liste d'attente...).
echo       Plus long. Necessite cookies.json
echo       Demande : ville / km / dates de debut et fin
echo.
echo  [3]  Statuts uniquement  (ouvert / liste d'attente / cloture)
echo       Rafraichit les statuts sans re-scraper les pages de base.
echo       A lancer une fois par jour.
echo       Necessite cookies.json
echo       Demande : ville / km
echo.
echo  [4]  Generer le HTML uniquement
echo       Regenere la page HTML depuis les donnees deja sauvegardees.
echo       Aucune requete vers TenUp.
echo       Demande : ville / km
echo.
echo  [5]  Calculer les distances routieres
echo       Calcule les distances de conduite depuis la ville de reference.
echo       Aucune requete vers TenUp.
echo       Demande : ville / km
echo.
echo  [6]  Tout recuperer  (le plus complet)
echo       Scraping + Formats + Statuts + Distances routieres.
echo       Necessite cookies.json
echo       Demande : ville / km / dates de debut et fin
echo.
echo  [0]  Quitter
echo.
echo  =============================================================
echo.
set "choix="
set /p choix=  Votre choix :

if "%choix%"=="1" goto scraping_base
if "%choix%"=="2" goto formats_statuts
if "%choix%"=="3" goto statuts
if "%choix%"=="4" goto html
if "%choix%"=="5" goto geo
if "%choix%"=="6" goto tout
if "%choix%"=="0" goto fin

echo.
echo  Choix invalide, veuillez ressaisir.
timeout /t 2 >nul
goto menu

:: ─────────────────────────────────────────────────────────────────────────────
:scraping_base
cls
echo.
echo  [1] Scraping de base
echo  ─────────────────────────────────────────────────────────────
echo.
python main.py --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:formats_statuts
cls
echo.
echo  [2] Scraping + Formats + Statuts
echo  ─────────────────────────────────────────────────────────────
echo.
python main.py --enrich --cookies cookies.json --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:statuts
cls
echo.
echo  [3] Refresh des statuts d'inscription
echo  ─────────────────────────────────────────────────────────────
echo.
python main.py --enrich-statut-only --cookies cookies.json --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:html
cls
echo.
echo  [4] Generation HTML uniquement
echo  ─────────────────────────────────────────────────────────────
echo.
python main.py --html-only --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:geo
cls
echo.
echo  [5] Calcul des distances routieres
echo  ─────────────────────────────────────────────────────────────
echo.
python main.py --enrich-geo-only --generator v3
goto fin_action

:: ─────────────────────────────────────────────────────────────────────────────
:tout
cls
echo.
echo  [6] Recuperation complete  (scraping + formats + statuts + distances)
echo  ─────────────────────────────────────────────────────────────
echo.
python main.py --enrich --enrich-geo --cookies cookies.json --generator v3
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
