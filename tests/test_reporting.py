from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import CreditNote, CreditNoteItem, Customer, Invoice, InvoiceItem, Payment
from app.services.reporting import get_balance_list, get_vat_summary


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def make_customer(db, name="Kunde A", **kwargs):
    customer = Customer(name=name, **kwargs)
    db.add(customer)
    db.flush()
    return customer


def make_invoice(db, customer, *, invoice_date, items, reverse_charge=False, advertising_tax_applicable=False):
    invoice = Invoice(
        number=f"R-{customer.id}-{invoice_date.isoformat()}",
        customer_id=customer.id,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=14),
        reverse_charge=reverse_charge,
        advertising_tax_applicable=advertising_tax_applicable,
        advertising_tax_rate=Decimal("5.00"),
    )
    db.add(invoice)
    db.flush()
    for description, quantity, unit_price, vat_rate in items:
        invoice.items.append(
            InvoiceItem(description=description, quantity=quantity, unit_price=unit_price, vat_rate=vat_rate)
        )
    db.flush()
    return invoice


def test_balance_list_groups_by_customer_and_sums_totals():
    db = make_session()
    customer = make_customer(db)
    invoice = make_invoice(
        db, customer, invoice_date=date(2026, 1, 10), items=[("Position", Decimal("1"), Decimal("100.00"), 20)]
    )
    db.add(Payment(invoice_id=invoice.id, amount=Decimal("60.00"), payment_date=date(2026, 1, 15)))
    db.commit()

    saldenliste = get_balance_list(db, date(2026, 1, 1), date(2026, 1, 31))

    assert len(saldenliste.kunden) == 1
    kunde = saldenliste.kunden[0]
    assert kunde.customer.id == customer.id
    assert kunde.zeilen[0].gross_total == Decimal("120.00")
    assert kunde.zeilen[0].paid_total == Decimal("60.00")
    assert kunde.zeilen[0].open_amount == Decimal("60.00")
    assert saldenliste.gesamt_brutto == Decimal("120.00")
    assert saldenliste.gesamt_offen == Decimal("60.00")


def test_balance_list_credit_note_reduces_customer_balance():
    db = make_session()
    customer = make_customer(db)
    invoice = make_invoice(
        db, customer, invoice_date=date(2026, 1, 5), items=[("Position", Decimal("1"), Decimal("100.00"), 20)]
    )
    credit_note = CreditNote(number="G-1", invoice_id=invoice.id, credit_note_date=date(2026, 1, 20))
    db.add(credit_note)
    db.flush()
    credit_note.items.append(CreditNoteItem(description="Storno", quantity=Decimal("1"), unit_price=Decimal("100.00"), vat_rate=20))
    db.commit()

    saldenliste = get_balance_list(db, date(2026, 1, 1), date(2026, 1, 31))

    kunde = saldenliste.kunden[0]
    assert len(kunde.zeilen) == 2
    gutschrift = next(z for z in kunde.zeilen if z.kind == "gutschrift")
    assert gutschrift.gross_total == Decimal("-120.00")
    assert kunde.summe_brutto == Decimal("0.00")


def test_balance_list_excludes_invoices_outside_period():
    db = make_session()
    customer = make_customer(db)
    make_invoice(db, customer, invoice_date=date(2026, 2, 1), items=[("Position", Decimal("1"), Decimal("50.00"), 20)])
    db.commit()

    saldenliste = get_balance_list(db, date(2026, 1, 1), date(2026, 1, 31))

    assert saldenliste.kunden == []


def test_vat_summary_splits_net_and_vat_by_rate():
    db = make_session()
    customer = make_customer(db)
    make_invoice(
        db,
        customer,
        invoice_date=date(2026, 3, 5),
        items=[("A", Decimal("1"), Decimal("100.00"), 20), ("B", Decimal("1"), Decimal("100.00"), 10)],
    )
    db.commit()

    summary = get_vat_summary(db, date(2026, 3, 1), date(2026, 3, 31))

    assert summary.net_by_rate[20] == Decimal("100.00")
    assert summary.vat_by_rate[20] == Decimal("20.00")
    assert summary.net_by_rate[10] == Decimal("100.00")
    assert summary.vat_by_rate[10] == Decimal("10.00")
    assert summary.vat_total == Decimal("30.00")
    assert summary.net_total == Decimal("200.00")
    assert summary.gross_total == Decimal("230.00")


def test_vat_summary_reverse_charge_invoice_is_separated_from_rate_buckets():
    db = make_session()
    customer = make_customer(db)
    make_invoice(
        db,
        customer,
        invoice_date=date(2026, 3, 5),
        items=[("A", Decimal("1"), Decimal("100.00"), 20)],
        reverse_charge=True,
    )
    db.commit()

    summary = get_vat_summary(db, date(2026, 3, 1), date(2026, 3, 31))

    assert summary.reverse_charge_net == Decimal("100.00")
    assert summary.net_by_rate[20] == Decimal("0.00")
    assert summary.vat_by_rate[20] == Decimal("0.00")
    assert summary.vat_total == Decimal("0.00")
    assert summary.gross_total == Decimal("100.00")


def test_vat_summary_advertising_tax_is_summed_and_credit_note_reduces_period():
    db = make_session()
    customer = make_customer(db)
    invoice = make_invoice(
        db,
        customer,
        invoice_date=date(2026, 3, 5),
        items=[("A", Decimal("1"), Decimal("100.00"), 20)],
        advertising_tax_applicable=True,
    )
    credit_note = CreditNote(number="G-1", invoice_id=invoice.id, credit_note_date=date(2026, 3, 10))
    db.add(credit_note)
    db.flush()
    credit_note.items.append(CreditNoteItem(description="Storno", quantity=Decimal("1"), unit_price=Decimal("40.00"), vat_rate=20))
    db.commit()

    summary = get_vat_summary(db, date(2026, 3, 1), date(2026, 3, 31))

    # Rechnung: Netto 100 + 5% Werbesteuer (5.00) = 105, + 20% USt (21.00) = 126.00
    # Gutschrift: Netto 40, + 20% USt (8.00) = 48.00 (keine Werbesteuer auf Gutschriften)
    assert summary.advertising_tax_amount == Decimal("5.00")
    assert summary.net_by_rate[20] == Decimal("60.00")  # 100 - 40
    assert summary.vat_by_rate[20] == Decimal("13.00")  # 21.00 - 8.00
    assert summary.gross_total == Decimal("78.00")  # 126.00 - 48.00
