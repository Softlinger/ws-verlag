from datetime import date
from decimal import Decimal

from app.models import Customer, Dunning, Invoice, InvoiceItem
from app.services.reporting import get_balance_list, get_vat_summary
from tests._db import make_session

PERIOD = (date(2020, 1, 1), date(2030, 12, 31))


def _invoice_with_fee(db, fee):
    customer = Customer(name="Kunde A")
    db.add(customer)
    db.flush()
    invoice = Invoice(
        number="R-1", customer_id=customer.id,
        invoice_date=date(2026, 1, 1), due_date=date(2026, 1, 15),
    )
    db.add(invoice)
    db.flush()
    invoice.items.append(InvoiceItem(description="Pos", quantity=Decimal("1"), unit_price=Decimal("100.00"), vat_rate=20))
    db.add(Dunning(invoice_id=invoice.id, level=1, due_date=date(2026, 1, 20),
                   fee_amount=fee, rendered_text="m"))
    db.commit()
    return invoice


def test_saldenliste_bucht_mahngebuehr_als_eigene_position():
    db = make_session()
    invoice = _invoice_with_fee(db, Decimal("10.00"))

    saldenliste = get_balance_list(db, *PERIOD)
    kunde = saldenliste.kunden[0]
    fee_zeilen = [z for z in kunde.zeilen if z.kind == "mahngebuehr"]

    assert len(fee_zeilen) == 1
    assert fee_zeilen[0].gross_total == Decimal("10.00")
    assert fee_zeilen[0].open_amount == Decimal("10.00")
    # Kunde schuldet Rechnung (120 offen) + Mahngebuehr (10) = 130 offen.
    assert kunde.summe_offen == Decimal("130.00")
    assert saldenliste.gesamt_brutto == Decimal("130.00")


def test_mahngebuehren_sind_umsatzsteuerfrei_in_uva():
    db = make_session()
    _invoice_with_fee(db, Decimal("10.00"))

    summary = get_vat_summary(db, *PERIOD)
    # USt bleibt reine Rechnung (20% von 100 = 20), unabhaengig von der Gebuehr.
    assert summary.vat_total == Decimal("20.00")
    assert summary.gross_total == Decimal("120.00")  # Gebuehr NICHT in UVA enthalten
