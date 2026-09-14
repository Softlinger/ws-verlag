from fastapi.testclient import TestClient

import tests._db as db_module
from app.auth import hash_password
from app.main import app
from app.models import Customer, Order, User, UserRole
from tests._db import make_session


def _login(client: TestClient) -> None:
    client.get("/login")
    csrf = client.cookies.get("ws_verlag_csrf")
    client.post("/login", data={"username": "admin", "password": "secret1234", "csrf_token": csrf})


def _seed_admin():
    db = make_session()
    db.add(
        User(
            username="admin",
            full_name="Admin",
            password_hash=hash_password("secret1234"),
            role=UserRole.ADMIN,
        )
    )
    db.commit()
    return db


def _current_session():
    # App und Test teilen sich TEST_DATABASE_URL; _db_module._last zeigt auf die
    # zuletzt von make_session() erzeugte (weiterhin lebendige) Session/Engine.
    return db_module._last[0]


def test_create_customer_persists_name2():
    db = _seed_admin()
    db.close()

    with TestClient(app) as client:
        _login(client)
        csrf = client.cookies.get("ws_verlag_csrf")
        resp = client.post(
            "/customers/new",
            data={"name": "Muster GmbH", "name2": "Filiale Wien", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    customer = _current_session().query(Customer).filter(Customer.name == "Muster GmbH").one()
    assert customer.name2 == "Filiale Wien"


def test_delete_customer_without_documents_succeeds():
    db = _seed_admin()
    customer = Customer(name="Loeschbar KG")
    db.add(customer)
    db.commit()
    customer_id = customer.id
    db.close()

    with TestClient(app) as client:
        _login(client)
        csrf = client.cookies.get("ws_verlag_csrf")
        resp = client.post(f"/customers/{customer_id}/delete", data={"csrf_token": csrf}, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/customers"

    assert _current_session().get(Customer, customer_id) is None


def test_delete_customer_with_order_is_blocked():
    db = _seed_admin()
    customer = Customer(name="Mit Auftrag AG")
    db.add(customer)
    db.commit()
    db.add(Order(number="A-00001", customer_id=customer.id))
    db.commit()
    customer_id = customer.id
    db.close()

    with TestClient(app) as client:
        _login(client)
        csrf = client.cookies.get("ws_verlag_csrf")
        resp = client.post(f"/customers/{customer_id}/delete", data={"csrf_token": csrf}, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/customers?error=customer_in_use"

    assert _current_session().get(Customer, customer_id) is not None


def test_address_pdf_returns_valid_pdf():
    db = _seed_admin()
    customer = Customer(name="Paketkunde GmbH", name2="Lager Nord", street="Lagerweg 3", postal_code="4020", city="Linz")
    db.add(customer)
    db.commit()
    customer_id = customer.id
    db.close()

    with TestClient(app) as client:
        _login(client)
        resp = client.get(f"/customers/{customer_id}/address-pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
