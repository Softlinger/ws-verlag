"""Prueft das Auslieferungsverzeichnis auf der Website auf eine neuere Version.

Sicherheitsprinzipien:
- Nur HTTPS, nur die konfigurierte Domain (kein Redirect-Following auf andere Hosts).
- Es wird niemals automatisch installiert - lediglich der Status in der DB aktualisiert.
  Die tatsaechliche Installation erfordert eine explizite Bestaetigung durch einen Admin
  (siehe app/routers/updates.py) und wird von einem separaten, privilegierten Updater-
  Container ausgefuehrt, niemals vom Anwendungsprozess selbst.
"""
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
from packaging.version import InvalidVersion, Version
from sqlalchemy.orm import Session

from app.config import settings
from app.models import UpdateApplyStatus, UpdateState
from app.version import __version__ as current_version


def get_or_create_update_state(db: Session) -> UpdateState:
    state = db.query(UpdateState).first()
    if state is None:
        state = UpdateState()
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def is_check_due(state: UpdateState) -> bool:
    if not settings.update_check_enabled:
        return False
    if state.last_checked_at is None:
        return True
    return datetime.utcnow() - state.last_checked_at > timedelta(hours=settings.update_check_interval_hours)


def check_for_update(db: Session) -> UpdateState:
    """Fuehrt die Pruefung durch und persistiert das Ergebnis. Wirft keine Exceptions nach
    aussen - Netzwerkfehler werden im state.check_error vermerkt, damit ein einzelner
    fehlgeschlagener Check die App nie zum Absturz bringt."""
    state = get_or_create_update_state(db)
    parsed = urlparse(settings.update_manifest_url)

    if parsed.scheme != "https":
        state.check_error = "Update-Manifest-URL muss HTTPS verwenden - Pruefung uebersprungen."
        state.last_checked_at = datetime.utcnow()
        db.commit()
        return state

    try:
        response = httpx.get(settings.update_manifest_url, timeout=10, follow_redirects=False)
        response.raise_for_status()
        manifest = response.json()

        required_fields = {"version", "image", "image_digest"}
        if not required_fields.issubset(manifest.keys()):
            raise ValueError(f"Manifest unvollstaendig, erwartet Felder: {required_fields}")

        # Downgrades/gleiche Version werden ignoriert - Vergleich per SemVer, nicht per String.
        try:
            is_newer = Version(str(manifest["version"])) > Version(current_version)
        except InvalidVersion as exc:
            raise ValueError(f"Ungueltige Versionsnummer im Manifest: {exc}") from exc

        state.check_error = ""
        state.last_checked_at = datetime.utcnow()
        if is_newer:
            is_different_version = str(manifest["version"]) != state.latest_version
            state.latest_version = str(manifest["version"])
            state.changelog = str(manifest.get("changelog", ""))
            state.release_date = str(manifest.get("release_date", ""))
            state.image_ref = str(manifest["image"])
            state.image_digest = str(manifest["image_digest"])

            # Ein frueherer Installationsstatus (erfolgreich/fehlgeschlagen/zurueckgerollt)
            # bezieht sich auf eine andere Version - ohne Reset wuerde der "Ja, Update
            # installieren"-Button im Template dauerhaft verschwinden, sobald einmal ein
            # Update installiert wurde. Ein laufender Installationsvorgang (angefordert/
            # wird_installiert) wird nicht angetastet.
            if is_different_version and state.apply_status in (
                UpdateApplyStatus.ERFOLGREICH,
                UpdateApplyStatus.FEHLGESCHLAGEN,
                UpdateApplyStatus.ZURUECKGEROLLT,
            ):
                state.apply_status = UpdateApplyStatus.NONE
                state.apply_message = ""
                state.apply_requested_at = None
                state.apply_requested_by_id = None
                state.apply_finished_at = None
        else:
            state.latest_version = ""
            state.changelog = ""
            state.image_ref = ""
            state.image_digest = ""

    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        state.check_error = f"Update-Pruefung fehlgeschlagen: {exc}"[:500]
        state.last_checked_at = datetime.utcnow()

    db.commit()
    return state
