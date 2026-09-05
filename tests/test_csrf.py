"""CSRF: Kern (signieren/validieren) + End-to-End-Ueberpruefung der Verdrahtung
(Middleware setzt Cookie, Form enthält Feld, require_csrf weist POST ohne Feld ab).

Der TestClient loest den App-Startup aus (create_all auf der Test-MariaDB, durch
conftest mit gesetztem SECRET_KEY + deaktiviertem Update-Check)."""
from fastapi.testclient import TestClient

from app.csrf import create_token, validate_token
from app.main import app


def test_token_roundtrip():
    token = create_token()
    assert validate_token(token)
    assert not validate_token(None)
    assert not validate_token("")
    assert not validate_token(token + "x")  # manipuliert -> Signatur fehlerhaft


def test_post_without_csrf_is_rejected():
    with TestClient(app) as client:
        # Kein CSRF-Cookie/Feld -> require_csrf blockiert die Anmeldung.
        resp = client.post("/login", data={"username": "admin", "password": "x"})
        assert resp.status_code == 403


def test_login_form_sets_csrf_cookie_and_field():
    with TestClient(app) as client:
        get = client.get("/login")
        assert get.status_code == 200
        cookie = client.cookies.get("ws_verlag_csrf")
        assert cookie and validate_token(cookie)
        # Das gerenderte Formular enthaelt denselben Token als verstecktes Feld.
        assert f'name="csrf_token" value="{cookie}"' in get.text

        # Gueltiges CSRF-Feld, aber falsches Passwort -> 401 (CSRF hat gegriffen).
        bad = client.post(
            "/login", data={"username": "admin", "password": "wrong", "csrf_token": cookie}
        )
        assert bad.status_code == 401

        # Cookie present, Feld weggelassen -> erneut 403.
        missing = client.post("/login", data={"username": "admin", "password": "wrong"})
        assert missing.status_code == 403
