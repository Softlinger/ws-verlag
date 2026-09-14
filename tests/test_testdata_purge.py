from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

import tests._db as db_module
from app.auth import hash_password
from app.main import app
from app.models import (
    Article,
    CreditNote,
    CreditNoteItem,
    Customer,
    Dunning,
    Invoice,
    InvoiceItem,
    MailLog,
    MailStatus,
    Order,
    OrderItem,
    Payment,
    User,
    UserRole,
)
from tests._db import make_session


def _current_session():
    return db_module._last[0]


def _login(client: TestClient, username: str, password: str = "secret1234") -> None:
    client.get("/login")
    csrf = client.cookies.get("ws_verlag_csrf")
    client.post("/login", data={"username": username, "password": password, "csrf_token": csrf})


def _seed_full_dataset():
    db = make_session()
    db.add(User(username="admin", full_name="Admin", password_hash=hash_password("secret1234"), role=UserRole.ADMIN))
    db.add(
        User(
            username="worker",
            full_name="Sachbearbeiter",
            password_hash=hash_password("secret1234"),
            role=UserRole.SACHBEARBEITER,
        )
    )
    customer = Customer(name="Kunde A")
    article = Article(name="Anzeige", unit_price=Decimal("100.00"), vat_rate=20)
    db.add(customer)
    db.add(article)
    db.commit()
    customer_id, article_id = customer.id, article.id

    order = Order(number="A-00001", customer_id=customer.id)
    db.add(order)
    db.commit()
    order.items.append(OrderItem(description="Position", quantity=Decimal("1"), unit_price=Decimal("100.00"), vat_rate=20))
    db.commit()

    invoice = Invoice(
        number="R-00001",
        customer_id=customer.id,
        order_id=order.id,
        invoice_date=date(2026, 1, 10),
        due_date=date(2026, 1, 10) + timedelta(days=14),
    )
    db.add(invoice)
    db.commit()
    invoice.items.append(InvoiceItem(description="Position", quantity=Decimal("1"), unit_price=Decimal("100.00"), vat_rate=20))
    db.add(Payment(invoice_id=invoice.id, amount=Decimal("50.00"), payment_date=date(2026, 1, 12)))
    db.add(
        Dunning(
            invoice_id=invoice.id,
            level=1,
            due_date=date(2026, 2, 1),
            rendered_text="Mahntext",
        )
    )
    db.commit()

    credit_note = CreditNote(number="G-00001", invoice_id=invoice.id, credit_note_date=date(2026, 1, 20))
    db.add(credit_note)
    db.commit()
    credit_note.items.append(
        CreditNoteItem(description="Gutschrift-Position", quantity=Decimal("1"), unit_price=Decimal("10.00"), vat_rate=20)
    )
    db.add(
        MailLog(
            related_type="invoice",
            related_id=invoice.id,
            recipient="kunde@example.com",
            subject="Rechnung R-00001",
            status=MailStatus.GESENDET,
        )
    )
    db.commit()
    db.close()
    return customer_id, article_id


def test_non_admin_cannot_purge():
    _seed_full_dataset()
    with TestClient(app) as client:
        _login(client, "worker")
        csrf = client.cookies.get("ws_verlag_csrf")
        resp = client.post(
            "/help/testdata/purge",
            data={"confirm": "true", "confirm_text": "LÖSCHEN", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 403

    db = _current_session()
    assert db.query(Invoice).count() == 1


def test_purge_without_full_confirmation_changes_nothing():
    _seed_full_dataset()
    with TestClient(app) as client:
        _login(client, "admin")
        csrf = client.cookies.get("ws_verlag_csrf")
        # Checkbox fehlt.
        resp = client.post(
            "/help/testdata/purge",
            data={"confirm_text": "LÖSCHEN", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/help?purge_error=1#testdaten"

        # Bestaetigungswort falsch.
        resp2 = client.post(
            "/help/testdata/purge",
            data={"confirm": "true", "confirm_text": "loeschen", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp2.status_code == 303
        assert resp2.headers["location"] == "/help?purge_error=1#testdaten"

    db = _current_session()
    assert db.query(Order).count() == 1
    assert db.query(Invoice).count() == 1
    assert db.query(CreditNote).count() == 1


def test_purge_removes_documents_but_keeps_master_data():
    customer_id, article_id = _seed_full_dataset()
    with TestClient(app) as client:
        _login(client, "admin")
        csrf = client.cookies.get("ws_verlag_csrf")
        resp = client.post(
            "/help/testdata/purge",
            data={"confirm": "true", "confirm_text": "LÖSCHEN", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/help?purge_done=1#testdaten"

    db = _current_session()
    assert db.query(Order).count() == 0
    assert db.query(OrderItem).count() == 0
    assert db.query(Invoice).count() == 0
    assert db.query(InvoiceItem).count() == 0
    assert db.query(CreditNote).count() == 0
    assert db.query(CreditNoteItem).count() == 0
    assert db.query(Payment).count() == 0
    assert db.query(Dunning).count() == 0
    assert db.query(MailLog).count() == 0

    # Stammdaten unberuehrt.
    assert db.get(Customer, customer_id) is not None
    assert db.get(Article, article_id) is not None
