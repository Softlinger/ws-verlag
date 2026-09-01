"""Erfassung von Zahlungen zu Rechnungen und Ableitung des Zahlungsstatus."""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceStatus, Payment
from app.services.tax import calculate_totals


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

    totals = calculate_totals(
        invoice.items,
        reverse_charge=invoice.reverse_charge,
        advertising_tax_applicable=invoice.advertising_tax_applicable,
        advertising_tax_rate=invoice.advertising_tax_rate,
    )
    paid_total = sum((p.amount for p in invoice.payments), Decimal("0.00"))
    if paid_total >= totals.gross_total:
        invoice.status = InvoiceStatus.BEZAHLT
    elif paid_total > 0:
        invoice.status = InvoiceStatus.TEILBEZAHLT
    else:
        invoice.status = InvoiceStatus.OFFEN

    return payment
