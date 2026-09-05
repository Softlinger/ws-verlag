"""Erfassung von Zahlungen/Gutschriften und Ableitung des Zahlungsstatus einer Rechnung.

Die Status-Ableitung ist zentral in recompute_invoice_status() gekapselt, damit sie
nicht nur nach Zahlungen, sondern auch nach Rechnungs-Edits und Gutschriften
konsistent nachgefuehrt wird (frueher: nur in record_payment -> veraltete Salden,
Mahnungen trotz Ausgleich).
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CreditNote, Invoice, InvoiceStatus, Payment
from app.services.tax import calculate_totals


def _invoice_totals(invoice: Invoice):
    return calculate_totals(
        invoice.items,
        reverse_charge=invoice.reverse_charge,
        advertising_tax_applicable=invoice.advertising_tax_applicable,
        advertising_tax_rate=invoice.advertising_tax_rate,
    )


def credited_total(db: Session, invoice: Invoice) -> Decimal:
    """Summe der Brutto-Gutschriften, die auf diese Rechnung laufen. Nutzt dieselbe
    Steuerbasis wie die Ursprungsrechnung (Reverse-Charge + Werbeabgabe), damit eine
    Gutschrift auch die anteilige Werbeabgabe korrekt umkehrt (M3)."""
    notes = db.query(CreditNote).filter(CreditNote.invoice_id == invoice.id).all()
    total = Decimal("0.00")
    for note in notes:
        totals = calculate_totals(
            note.items,
            reverse_charge=invoice.reverse_charge,
            advertising_tax_applicable=invoice.advertising_tax_applicable,
            advertising_tax_rate=invoice.advertising_tax_rate,
        )
        total += totals.gross_total
    return total


def open_amount(db: Session, invoice: Invoice) -> Decimal:
    """Rechnerischer offener Betrag der Rechnung selbst = Brutto - gezahlt -
    gutgeschrieben (nie < 0). OHNE Mahngebuehren - das ist die Basis fuer
    Gutschriften-Cap und Zahlungsvergleich."""
    gross = _invoice_totals(invoice).gross_total
    paid = sum((p.amount for p in invoice.payments), Decimal("0.00"))
    credited = credited_total(db, invoice)
    return max(Decimal("0.00"), gross - paid - credited)


def accrued_dunning_fees(invoice: Invoice) -> Decimal:
    """Summe der Gebuehren aller zu dieser Rechnung gestellten Mahnungen.
    Mahngebuehren sind Kostenersatz und damit UMSATSTEUERFREI - sie laufen niemals in
    calculate_totals/USt-Basis/UVA, sondern nur als offene Forderung mit."""
    return sum((d.fee_amount for d in invoice.dunnings), Decimal("0.00"))


def total_open(db: Session, invoice: Invoice) -> Decimal:
    """Vollstaendig offene Forderung an den Kunden = Rechnungsrest + Mahngebuehren."""
    return open_amount(db, invoice) + accrued_dunning_fees(invoice)


def recompute_invoice_status(db: Session, invoice: Invoice) -> InvoiceStatus:
    """Leitet den Zahlungsstatus aus Brutto, gezahlt und gutgeschrieben ab.

    Sperret die Rechnungszeile (FOR UPDATE), damit zwei gleichzeitige Sitzungen den
    Status nicht auf Basis veralteter Salden berechnen (Lost-Update).
    """
    db.execute(select(Invoice).where(Invoice.id == invoice.id).with_for_update())
    db.expire(invoice)  # nach dem Lock frische Zeilenversion (inkl. Zahlungen) sehen.

    gross = _invoice_totals(invoice).gross_total
    paid = sum((p.amount for p in invoice.payments), Decimal("0.00"))
    credited = credited_total(db, invoice)
    settled = paid + credited

    if settled >= gross:
        invoice.status = InvoiceStatus.BEZAHLT
    elif settled > 0:
        invoice.status = InvoiceStatus.TEILBEZAHLT
    else:
        invoice.status = InvoiceStatus.OFFEN
    return invoice.status


def record_payment(
    db: Session,
    invoice: Invoice,
    *,
    amount: Decimal,
    payment_date: date,
    method: str,
    note: str,
    created_by_id: int,
) -> Payment:
    payment = Payment(
        invoice_id=invoice.id,
        amount=amount,
        payment_date=payment_date,
        method=method,
        note=note,
        created_by_id=created_by_id,
    )
    db.add(payment)
    db.flush()
    recompute_invoice_status(db, invoice)
    return payment
