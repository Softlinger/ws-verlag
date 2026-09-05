from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    CreditNote,
    CreditNoteItem,
    Customer,
    Dunning,
    DunningLevelSetting,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Payment,
)
from app.services.dunning import next_dunning_level, render_dunning_text
from app.services.payments import recompute_invoice_status
from tests._db import make_session


def _invoice(db, net_each=Decimal("100.00"), count=1, vat=20):
    """Rechnung mit `count` Positionen a `net_each` netto; Brutto je Position = net*(1+vat)."""
    customer = Customer(name="Kunde A")
    db.add(customer)
    db.flush()
    invoice = Invoice(
        number="R-1",
        customer_id=customer.id,
        invoice_date=date(2026, 1, 1),
        due_date=date(2026, 1, 15),
    )
    db.add(invoice)
    db.flush()
    for _ in range(count):
        invoice.items.append(
            InvoiceItem(description="Pos", quantity=Decimal("1"), unit_price=net_each, vat_rate=vat)
        )
    db.flush()
    return invoice


def test_status_open_then_partial_then_full_payment():
    db = make_session()
    invoice = _invoice(db)  # Brutto 120.00

    recompute_invoice_status(db, invoice)
    assert invoice.status == InvoiceStatus.OFFEN

    db.add(Payment(invoice_id=invoice.id, amount=Decimal("50.00"), payment_date=date(2026, 1, 2)))
    db.flush()
    recompute_invoice_status(db, invoice)
    assert invoice.status == InvoiceStatus.TEILBEZAHLT

    db.add(Payment(invoice_id=invoice.id, amount=Decimal("70.00"), payment_date=date(2026, 1, 3)))
    db.flush()
    recompute_invoice_status(db, invoice)
    assert invoice.status == InvoiceStatus.BEZAHLT


def test_full_credit_note_settles_invoice_status():
    """Regression A4: eine Rechnung, die vollstaendig gutgeschrieben wurde, muss als
    ausgeglichen gelten und darf nicht mehr in offenen Posten/Mahnungen auftauchen."""
    db = make_session()
    invoice = _invoice(db)  # Brutto 120.00

    note = CreditNote(number="G-1", invoice_id=invoice.id, credit_note_date=date(2026, 1, 5))
    db.add(note)
    db.flush()
    note.items.append(
        CreditNoteItem(description="Storno", quantity=Decimal("1"), unit_price=Decimal("100.00"), vat_rate=20)
    )
    db.flush()

    recompute_invoice_status(db, invoice)
    assert invoice.status == InvoiceStatus.BEZAHLT


def test_dunning_unique_constraint_blocks_duplicate_level():
    db = make_session()
    invoice = _invoice(db)
    db.add(Dunning(invoice_id=invoice.id, level=1, due_date=date(2026, 1, 20), rendered_text="m1"))
    db.flush()
    assert next_dunning_level(invoice) == 2

    db.add(Dunning(invoice_id=invoice.id, level=1, due_date=date(2026, 1, 21), rendered_text="dup"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_render_dunning_text_ignores_unknown_placeholder():
    """Regression D4: ein unbekannter {platzhalter} im editierbaren Mahntext darf die
    Mahnungserstellung nicht mit KeyError (500) zum Absturz bringen."""
    db = make_session()
    invoice = _invoice(db)
    setting = DunningLevelSetting(
        level=1,
        due_days=14,
        fee_amount=Decimal("0.00"),
        text_template="Hallo {kunde}, Betrag {betrag}, Unbekanntes: {xyz}",
    )
    db.add(setting)
    db.flush()

    out = render_dunning_text(setting, invoice, Decimal("120.00"))
    assert "Hallo Kunde A" in out
    assert "120.00" in out
    # {xyz} laeuft ins Leere statt Exception.
    assert "Unbekanntes: " in out
