import httpx
import pytest
from datetime import timedelta

from app.config import settings
from app.models import UpdateApplyStatus, UpdateState
from app.services import update_check
from app.times import utcnow
from tests._db import make_session


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._payload


def test_detects_newer_version(monkeypatch):
    monkeypatch.setattr(
        update_check.httpx,
        "get",
        lambda *a, **k: FakeResponse(
            {
                "version": "99.0.0",
                "changelog": "Testeintrag",
                "release_date": "2026-09-01",
                "image": "ghcr.io/weidlingersoft/ws-verlag",
                "image_digest": "sha256:aa",
            }
        ),
    )
    db = make_session()
    state = update_check.check_for_update(db)

    assert state.check_error == ""
    assert state.latest_version == "99.0.0"
    assert state.image_ref == "ghcr.io/weidlingersoft/ws-verlag"
    assert state.image_digest == "sha256:aa"


def test_ignores_same_or_older_version(monkeypatch):
    monkeypatch.setattr(
        update_check.httpx,
        "get",
        lambda *a, **k: FakeResponse(
            {
                "version": "0.0.1",
                "image": "ghcr.io/weidlingersoft/ws-verlag",
                "image_digest": "sha256:aa",
            }
        ),
    )
    db = make_session()
    state = update_check.check_for_update(db)

    assert state.check_error == ""
    assert state.latest_version == ""


def test_rejects_non_https_manifest_url(monkeypatch):
    monkeypatch.setattr(settings, "update_manifest_url", "http://example.com/version.json")
    db = make_session()
    state = update_check.check_for_update(db)

    assert "HTTPS" in state.check_error
    assert state.latest_version == ""


def test_handles_incomplete_manifest_gracefully(monkeypatch):
    monkeypatch.setattr(update_check.httpx, "get", lambda *a, **k: FakeResponse({"version": "9.9.9"}))
    db = make_session()
    state = update_check.check_for_update(db)

    assert "Manifest unvollstaendig" in state.check_error
    assert state.latest_version == ""


def test_clear_stale_apply_status_resets_old_request():
    """Ein 'laeuft'-Status aelter als das Wartungsfenster ist verwaist (verlorener Report
    oder zurueckgespielte alte DB) und muss auf none heilen, damit die UI freigibt."""
    db = make_session()
    state = update_check.get_or_create_update_state(db)
    state.apply_status = UpdateApplyStatus.WIRD_INSTALLIERT
    state.apply_requested_at = utcnow() - timedelta(hours=2)
    db.commit()

    healed = update_check.clear_stale_apply_status(db)
    assert healed.apply_status == UpdateApplyStatus.NONE
    assert healed.apply_requested_at is None


def test_clear_stale_apply_status_keeps_recent_request():
    """Ein frischer 'laeuft'-Status ist ein echter laufender Update -> nicht antasten."""
    db = make_session()
    state = update_check.get_or_create_update_state(db)
    state.apply_status = UpdateApplyStatus.ANGEFORDERT
    state.apply_requested_at = utcnow()
    db.commit()

    same = update_check.clear_stale_apply_status(db)
    assert same.apply_status == UpdateApplyStatus.ANGEFORDERT


def test_resets_apply_status_when_a_newer_version_appears_after_a_successful_install(monkeypatch):
    """Regression: nach einem erfolgreich installierten Update muss die Update-Seite
    fuer eine spaetere, neuere Version wieder den 'Ja, Update installieren'-Button
    zeigen (apply_status == none), statt dauerhaft bei 'erfolgreich' zu bleiben."""
    db = make_session()
    state = update_check.get_or_create_update_state(db)
    state.latest_version = "99.0.0"
    state.apply_status = UpdateApplyStatus.ERFOLGREICH
    db.commit()

    monkeypatch.setattr(
        update_check.httpx,
        "get",
        lambda *a, **k: FakeResponse(
            {
                "version": "99.0.1",
                "image": "ghcr.io/weidlingersoft/ws-verlag",
                "image_digest": "sha256:bb",
            }
        ),
    )
    state = update_check.check_for_update(db)

    assert state.latest_version == "99.0.1"
    assert state.apply_status == UpdateApplyStatus.NONE


def test_keeps_apply_status_when_latest_version_is_unchanged(monkeypatch):
    db = make_session()
    state = update_check.get_or_create_update_state(db)
    state.latest_version = "99.0.1"
    state.apply_status = UpdateApplyStatus.ERFOLGREICH
    db.commit()

    monkeypatch.setattr(
        update_check.httpx,
        "get",
        lambda *a, **k: FakeResponse(
            {
                "version": "99.0.1",
                "image": "ghcr.io/weidlingersoft/ws-verlag",
                "image_digest": "sha256:bb",
            }
        ),
    )
    state = update_check.check_for_update(db)

    assert state.apply_status == UpdateApplyStatus.ERFOLGREICH


def test_network_error_is_caught_not_raised(monkeypatch):
    def raise_error(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(update_check.httpx, "get", raise_error)
    db = make_session()
    state = update_check.check_for_update(db)

    assert "fehlgeschlagen" in state.check_error
