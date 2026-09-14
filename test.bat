@echo off
rem ============================================================
rem  test.bat - Komplette Testsuite ueber Docker ausfuehren.
rem  Baut den "test"-Stage und laeuft pytest gegen eine eigene
rem  Wegwerf-MariaDB (db-test). Kein manuelles DB-Setnoetig.
rem  Aufruf: test.bat
rem ============================================================
setlocal
cd /d "%~dp0"

docker info >nul 2>&1
if errorlevel 1 (
  echo FEHLER: Docker laeuft nicht. Bitte Docker Desktop starten.
  exit /b 1
)

echo === Test-Image bauen ===
docker compose --profile test build test
if errorlevel 1 (
  echo FEHLER: Test-Build fehlgeschlagen.
  goto :cleanup_fail
)

echo === Suite ausfuehren ===
docker compose --profile test run --rm test
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (
  echo.
  echo ALLE TESTS BESTANDEN.
) else (
  echo.
  echo TESTS FEHLGESCHLAGEN (Exit %RC%).
)

:cleanup
docker rm -f ws-verlag-dbtest >nul 2>&1
exit /b %RC%

:cleanup_fail
docker rm -f ws-verlag-dbtest >nul 2>&1
exit /b 1
