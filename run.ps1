# Startet die WS-Verlag Verwaltung lokal (Windows PowerShell).
$env:Path += ";$env:APPDATA\Python\Python314\Scripts"
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
