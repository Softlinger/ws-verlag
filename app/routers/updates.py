import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import settings
from app.database import get_db
from app.models import UpdateApplyStatus, User
from app.services.update_check import check_for_update, get_or_create_update_state
from app.templating import templates
from app.version import __version__

router = APIRouter(prefix="/updates", tags=["updates"])


@router.get("")
def update_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    state = get_or_create_update_state(db)
    return templates.TemplateResponse(
        request, "updates/status.html", {"state": state, "current_version": __version__}
    )


@router.post("/check")
def trigger_check(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    check_for_update(db)
    return RedirectResponse("/updates", status_code=303)


@router.post("/apply")
def apply_update(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Fordert die Installation an. Installiert wird NICHT vom App-Prozess selbst,
    sondern vom separaten Updater-Container, der dieses Signal ueber ein gemeinsames
    Docker-Volume liest und Docker-Operationen (Pull, Stop/Start, Backup, Rollback)
    ausserhalb des App-Containers durchfuehrt."""
    state = get_or_create_update_state(db)
    if not state.image_ref or not state.image_digest:
        return RedirectResponse("/updates", status_code=303)

    state.apply_status = UpdateApplyStatus.ANGEFORDERT
    state.apply_requested_at = datetime.utcnow()
    state.apply_requested_by_id = user.id
    state.apply_message = ""
    db.commit()

    signal_dir = Path(settings.update_signal_dir)
    try:
        signal_dir.mkdir(parents=True, exist_ok=True)
        request_payload = {
            "requested_at": state.apply_requested_at.isoformat(),
            "target_version": state.latest_version,
            "image": state.image_ref,
            "image_digest": state.image_digest,
        }
        (signal_dir / "update_request.json").write_text(json.dumps(request_payload, indent=2), encoding="utf-8")
    except OSError as exc:
        # Kein Docker-/NAS-Betrieb (z. B. lokale Entwicklung ohne gemountetes Signal-Verzeichnis).
        state.apply_status = UpdateApplyStatus.FEHLGESCHLAGEN
        state.apply_message = f"Update-Signal-Verzeichnis nicht schreibbar: {exc}"[:500]
        db.commit()

    return RedirectResponse("/updates", status_code=303)


@router.get("/status.json")
def status_json(db: Session = Depends(get_db)):
    """Unauthentifizierter, read-only Status-Endpunkt fuer den Updater-Container
    (kein Login-Cookie im Sidecar verfuegbar). Gibt bewusst keine sensiblen Daten preis."""
    state = get_or_create_update_state(db)
    return JSONResponse(
        {
            "current_version": __version__,
            "apply_status": state.apply_status.value,
            "target_version": state.latest_version,
        }
    )


@router.post("/report")
def report_result(payload: dict, db: Session = Depends(get_db)):
    """Vom Updater-Container aufgerufen, um das Ergebnis (Erfolg/Fehlschlag/Rollback)
    zurueckzumelden. Bewusst ohne Admin-Login (Updater-Container hat keine Session),
    daher nur lokal erreichbar halten (siehe docker-compose.yml: kein Port-Publish,
    nur internes Docker-Netzwerk)."""
    state = get_or_create_update_state(db)
    status_value = payload.get("status")
    if status_value in {s.value for s in UpdateApplyStatus}:
        state.apply_status = UpdateApplyStatus(status_value)
    state.apply_finished_at = datetime.utcnow()
    state.apply_message = str(payload.get("message", ""))[:1000]
    db.commit()
    return {"ok": True}
