from fastapi.testclient import TestClient

from app.auth import hash_password
from app.main import app
from app.models import User, UserRole
from tests._db import make_session


def test_company_page_has_floating_home_button():
    # Admin in der geteilten Test-DB anlegen (Firmenseite ist admin-only).
    db = make_session()  # legt das Schema an
    db.add(
        User(
            username="admin",
            full_name="Admin",
            password_hash=hash_password("secret1234"),
            role=UserRole.ADMIN,
        )
    )
    db.commit()
    db.close()

    with TestClient(app) as client:
        client.get("/login")
        csrf = client.cookies.get("ws_verlag_csrf")
        client.post("/login", data={"username": "admin", "password": "secret1234", "csrf_token": csrf})

        page = client.get("/company")
        assert page.status_code == 200
        # Schwebender Start-Button vorhanden und zeigt auf die Startseite.
        assert "floating-home" in page.text
        assert 'href="/"' in page.text
