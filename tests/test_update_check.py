import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.models import UpdateState
from app.services import update_check


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


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


def test_network_error_is_caught_not_raised(monkeypatch):
    def raise_error(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(update_check.httpx, "get", raise_error)
    db = make_session()
    state = update_check.check_for_update(db)

    assert "fehlgeschlagen" in state.check_error
