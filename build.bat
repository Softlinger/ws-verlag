@echo off
rem ============================================================
rem  build.bat - App-Image lokal kompilieren/pruefen (OHNE Push).
rem  Baut das Server-Image (Stage "runtime") als ws-verlag-app:local.
rem  Aufruf: build.bat
rem ============================================================
setlocal
cd /d "%~dp0"

docker info >nul 2>&1
if errorlevel 1 (
  echo FEHLER: Docker laeuft nicht. Bitte Docker Desktop starten.
  exit /b 1
)

echo === Docker-Build: runtime-Image (lokal, ohne Push) ===
docker build -t ws-verlag-app:local --target runtime .
if errorlevel 1 (
  echo FEHLER: Build fehlgeschlagen.
  exit /b 1
)
echo.
echo OK - Image 'ws-verlag-app:local' gebaut.
endlocal
