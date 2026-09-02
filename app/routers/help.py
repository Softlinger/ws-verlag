import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.auth import require_admin, require_login
from app.config import settings
from app.models import User, UserRole
from app.templating import templates

router = APIRouter(prefix="/help", tags=["help"])


def _list_backups() -> list[dict]:
    """Listet vorhandene Backup-Dateien aus dem (read-only) gemounteten Backup-Verzeichnis.
    Die Dateien werden vom separaten Updater-Container angelegt (siehe updater/updater.py) -
    die App selbst hat keinen Datenbankzugriff dafuer noetig."""
    backups_dir = Path(settings.backups_dir)
    if not backups_dir.is_dir():
        return []
    files = [p for p in backups_dir.iterdir() if p.is_file() and p.name.startswith("ws_verlag-")]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "name": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "modified": datetime.fromtimestamp(p.stat().st_mtime),
        }
        for p in files
    ]


def _read_restore_status() -> dict | None:
    """Liest das Ergebnis der letzten Wiederherstellung, das der Updater-Container ins
    gemeinsame Signal-Verzeichnis geschrieben hat (gleiches Muster wie die Backup-Anforderung,
    nur in umgekehrter Richtung - kein zusaetzlicher HTTP-Endpunkt noetig)."""
    status_file = Path(settings.update_signal_dir) / "restore_status.json"
    if not status_file.is_file():
        return None
    try:
        return json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


@router.get("")
def help_page(request: Request, user: User = Depends(require_login)):
    context = {}
    if user.role == UserRole.ADMIN:
        context["backups"] = _list_backups()
        context["backup_requested"] = request.query_params.get("backup_requested") == "1"
        context["restore_requested"] = request.query_params.get("restore_requested") == "1"
        context["restore_error"] = request.query_params.get("restore_error") == "1"
        context["restore_status"] = _read_restore_status()
    return templates.TemplateResponse(request, "help/page.html", context)


@router.post("/backups/run")
def trigger_backup(user: User = Depends(require_admin)):
    """Legt ein Signal fuer den Updater-Container an, der als einziger Container Zugriff auf
    MariaDB/Docker hat und die eigentliche Sicherung ausserhalb des App-Containers durchfuehrt
    (analog zum Update-Mechanismus in app/routers/updates.py)."""
    signal_dir = Path(settings.update_signal_dir)
    signal_dir.mkdir(parents=True, exist_ok=True)
    payload = {"requested_at": datetime.utcnow().isoformat(), "requested_by": user.username}
    (signal_dir / "backup_request.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return RedirectResponse("/help?backup_requested=1#sicherung", status_code=303)


@router.post("/backups/restore")
def trigger_restore(filename: str = Form(...), user: User = Depends(require_admin)):
    """Fordert die Wiederherstellung einer Sicherung an - ueberschreibt die aktuelle
    Datenbank, daher strikte Pruefung, dass die Datei tatsaechlich im Backup-Verzeichnis
    existiert (kein Path-Traversal ueber den POST-Parameter moeglich)."""
    safe_name = Path(filename).name
    backup_path = Path(settings.backups_dir) / safe_name
    if safe_name != filename or not safe_name.startswith("ws_verlag-") or not backup_path.is_file():
        return RedirectResponse("/help?restore_error=1#sicherung", status_code=303)

    signal_dir = Path(settings.update_signal_dir)
    signal_dir.mkdir(parents=True, exist_ok=True)
    payload = {"filename": safe_name, "requested_at": datetime.utcnow().isoformat(), "requested_by": user.username}
    (signal_dir / "restore_request.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return RedirectResponse("/help?restore_requested=1#sicherung", status_code=303)

