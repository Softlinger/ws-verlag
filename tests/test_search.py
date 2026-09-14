from fastapi.testclient import TestClient

from app.auth import hash_password
from app.main import app
from app.models import Customer, Invoice, InvoiceItem, User, UserRole
from decimal import Decimal
from datetime import date
from tests._db import make_session


def _login(client):
    client.get("/login")
    tok = client.cookies.get("ws_verlag_csrf")
    client.post("/login", data={"username": "admin", "password": "secret1234", "csrf_token": tok})


def test_customers_list_search_filters():
    db = make_session()
    db.add(User(username="admin", full_name="A", password_hash=hash_password("secret1234"), role=UserRole.ADMIN))
    db.add_all([Customer(name="Alpha Handel"), Customer(name="Beta Verlag")])
    db.commit()
    db.close()

    with TestClient(app) as client:
        _login(client)
        hit = client.get("/customers", params={"q": "Alpha"}).text
        assert "Alpha Handel" in hit
        assert "Beta Verlag" not in hit
        # Treffer-Partial (case-insensitiv)
        assert "Alpha Handel" in client.get("/customers", params={"q": "alpha han"}).text
        # leere Suche -> alle
        alle = client.get("/customers").text
        assert "Alpha Handel" in alle and "Beta Verlag" in alle
        # Suchfeld ist im Template eingebunden
        assert 'name="q"' in alle


def test_invoices_list_search_by_customer_name():
    db = make_session()
    db.add(User(username="admin", full_name="A", password_hash=hash_password("secret1234"), role=UserRole.ADMIN))
    c1 = Customer(name="Gamma Druck")
    db.add(c1)
    db.flush()
    inv = Invoice(number="R-5", customer_id=c1.id, invoice_date=date(2026, 1, 1), due_date=date(2026, 1, 15))
    inv.items.append(InvoiceItem(description="x", quantity=Decimal("1"), unit_price=Decimal("100.00"), vat_rate=20))
    db.add(inv)
    db.commit()
    db.close()

    with TestClient(app) as client:
        _login(client)
        assert "R-5" in client.get("/invoices", params={"q": "Gamma"}).text
        assert "R-5" not in client.get("/invoices", params={"q": "unbekannt"}).text
