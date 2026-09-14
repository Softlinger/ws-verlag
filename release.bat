@echo off
rem ============================================================
rem  release.bat - Komplettes Release in einem Schritt.
rem    1) Version bumpen + git commit + Tag (via deploy/release.py)
rem    2) Docker-Image bauen und auf ghcr.io pushen (:VER + :latest)
rem    3) version.json schreiben und per FTPS auf den Update-Server laden
rem    4) version.json-Artefakt committen
rem    5) git push origin master --follow-tags
rem
rem  Aufruf:  release.bat                      (interaktiv nach Version + Changelog fragen)
rem  oder:    release.bat 0.4.6 "Neue Funktion X"   (nicht-interaktiv)
rem
rem  Voraussetzungen: Docker laeuft; einmalig 'docker login ghcr.io'
rem  (PAT mit write:packages); deploy\.env.deploy mit FTP-Zugang; sauberer Git-Baum.
rem ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PATH=%APPDATA%\Python\Python314\Scripts;%PATH%"

set "VER=%~1"
set "CHG=%~2"
if "%VER%"=="" set /p "VER=Neue Version (z.B. 0.4.6): "
if "%CHG%"=="" set /p "CHG=Changelog (eine Zeile): "

if "%VER%"=="" ( echo FEHLER: keine Version angegeben. & exit /b 1 )
if "%CHG%"=="" ( echo FEHLER: kein Changelog angegeben. & exit /b 1 )

echo.
echo === Preflight ===
docker info >nul 2>&1
if errorlevel 1 (
  echo FEHLER: Docker laeuft nicht. Bitte Docker Desktop starten.
  exit /b 1
)

rem release.py verlangt einen sauberen Baum (inkl. unversionierter Dateien).
set "DIRTY="
for /f "delims=" %%i in ('git status --porcelain') do set "DIRTY=1"
if defined DIRTY (
  echo FEHLER: Arbeitsbaum nicht sauber bzw. unversionierte Dateien vorhanden.
  echo         Bitte alles committen (auch diese .bat-Dateien), dann erneut starten.
  git status --short
  exit /b 1
)

echo Hinweis: ghcr-Push braucht einmalig 'docker login ghcr.io' (PAT write:packages).
echo.
echo === Release %VER%: Bump + Build + ghcr-Push + version.json + FTPS-Upload ===
poetry run python deploy/release.py %VER% --changelog "%CHG%"
if errorlevel 1 (
  echo FEHLER: release.py fehlgeschlagen (Build / ghcr-Push / FTP pruefen).
  exit /b 1
)

echo.
echo === version.json-Artefakt committen ===
git add deploy/release_upload/version.json
git commit -m "version.json fuer Release %VER% nachgetragen" >nul 2>&1
if errorlevel 1 echo (kein Artefakt zu committen)

echo.
echo === git push (master + Tags) ===
git push origin master --follow-tags
if errorlevel 1 (
  echo WARNUNG: git push fehlgeschlagen. Spaeter manuell: git push origin master --follow-tags
  exit /b 1
)

echo.
echo ============================================================
echo  Release %VER% fertig: ghcr + version.json-Upload + Git-Push.
echo  Instanzen holen sich das Update ueber /updates.
echo ============================================================
endlocal
