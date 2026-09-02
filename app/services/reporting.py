"""Aggregationslogik fuer die Buchhaltungs-Berichte (Saldenliste, USt.-Voranmeldung).

Baut auf calculate_totals() aus app/services/tax.py auf - siehe dort fuer die
Berechnungsreihenfolge (Werbesteuer erhoeht die USt.-Bemessungsgrundlage, Reverse-Charge
fuehrt zu 0% USt.). Gutschriften mindern die jeweilige Periode (Saldenliste: negativer
Betrag je Kunde; USt.-Auswertung: Subtraktion von Netto/USt./Werbesteuer der Periode).
"""
import csv
import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import CreditNote, Customer, Invoice
from app.services.tax import calculate_totals


@dataclass
class BelegZeile:
    kind: str  # "rechnung" | "gutschrift"
    number: str
    beleg_date: date
    status: str | None
    gross_total: Decimal
    paid_total: Decimal
    open_amount: Decimal


@dataclass
class KundenSaldo:
    customer: Customer
    zeilen: list[BelegZeile]
    summe_brutto: Decimal
    summe_bezahlt: Decimal
    summe_offen: Decimal


@dataclass
class Saldenliste:
    date_from: date
    date_to: date
    kunden: list[KundenSaldo]
    gesamt_brutto: Decimal
    gesamt_bezahlt: Decimal
    gesamt_offen: Decimal


def get_balance_list(db: Session, date_from: date, date_to: date) -> Saldenliste:
    invoices = (
        db.query(Invoice)
        .filter(Invoice.invoice_date >= date_from, Invoice.invoice_date <= date_to)
        .all()
    )
    credit_notes = (
        db.query(CreditNote)
        .join(Invoice, CreditNote.invoice_id == Invoice.id)
        .filter(CreditNote.credit_note_date >= date_from, CreditNote.credit_note_date <= date_to)
        .all()
    )

    zeilen_by_customer: dict[int, list[BelegZeile]] = {}
    customers_by_id: dict[int, Customer] = {}

    for invoice in invoices:
        totals = calculate_totals(
            invoice.items,
            reverse_charge=invoice.reverse_charge,
            advertising_tax_applicable=invoice.advertising_tax_applicable,
            advertising_tax_rate=invoice.advertising_tax_rate,
        )
        paid_total = sum((p.amount for p in invoice.payments), Decimal("0.00"))
        zeilen_by_customer.setdefault(invoice.customer_id, []).append(
            BelegZeile(
                kind="rechnung",
                number=invoice.number,
                beleg_date=invoice.invoice_date,
                status=invoice.status.value,
                gross_total=totals.gross_total,
                paid_total=paid_total,
                open_amount=totals.gross_total - paid_total,
            )
        )
        customers_by_id[invoice.customer_id] = invoice.customer

    for credit_note in credit_notes:
        invoice = credit_note.invoice
        totals = calculate_totals(credit_note.items)
        zeilen_by_customer.setdefault(invoice.customer_id, []).append(
            BelegZeile(
                kind="gutschrift",
                number=credit_note.number,
                beleg_date=credit_note.credit_note_date,
                status=None,
                gross_total=-totals.gross_total,
                paid_total=Decimal("0.00"),
                open_amount=-totals.gross_total,
            )
        )
        customers_by_id.setdefault(invoice.customer_id, invoice.customer)

    kunden: list[KundenSaldo] = []
    gesamt_brutto = Decimal("0.00")
    gesamt_bezahlt = Decimal("0.00")
    gesamt_offen = Decimal("0.00")

    for customer_id in sorted(zeilen_by_customer, key=lambda cid: customers_by_id[cid].name):
        zeilen = sorted(zeilen_by_customer[customer_id], key=lambda z: z.beleg_date)
        summe_brutto = sum((z.gross_total for z in zeilen), Decimal("0.00"))
        summe_bezahlt = sum((z.paid_total for z in zeilen), Decimal("0.00"))
        summe_offen = sum((z.open_amount for z in zeilen), Decimal("0.00"))
        kunden.append(
            KundenSaldo(
                customer=customers_by_id[customer_id],
                zeilen=zeilen,
                summe_brutto=summe_brutto,
                summe_bezahlt=summe_bezahlt,
                summe_offen=summe_offen,
            )
        )
        gesamt_brutto += summe_brutto
        gesamt_bezahlt += summe_bezahlt
        gesamt_offen += summe_offen

    return Saldenliste(
        date_from=date_from,
        date_to=date_to,
        kunden=kunden,
        gesamt_brutto=gesamt_brutto,
        gesamt_bezahlt=gesamt_bezahlt,
        gesamt_offen=gesamt_offen,
    )


def balance_list_to_csv(saldenliste: Saldenliste) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Kunde", "Belegart", "Nummer", "Datum", "Status", "Betrag", "Bezahlt", "Offen"])
    for kunde in saldenliste.kunden:
        for zeile in kunde.zeilen:
            writer.writerow(
                [
                    kunde.customer.name,
                    "Rechnung" if zeile.kind == "rechnung" else "Gutschrift",
                    zeile.number,
                    zeile.beleg_date.strftime("%d.%m.%Y"),
                    zeile.status or "",
                    f"{zeile.gross_total:.2f}",
                    f"{zeile.paid_total:.2f}",
                    f"{zeile.open_amount:.2f}",
                ]
            )
        writer.writerow(
            [kunde.customer.name, "Summe", "", "", "", f"{kunde.summe_brutto:.2f}", f"{kunde.summe_bezahlt:.2f}", f"{kunde.summe_offen:.2f}"]
        )
    writer.writerow(
        ["Gesamt", "", "", "", "", f"{saldenliste.gesamt_brutto:.2f}", f"{saldenliste.gesamt_bezahlt:.2f}", f"{saldenliste.gesamt_offen:.2f}"]
    )
    return buffer.getvalue()


@dataclass
class VatSummary:
    date_from: date
    date_to: date
    net_by_rate: dict[int, Decimal] = field(default_factory=lambda: {10: Decimal("0.00"), 20: Decimal("0.00")})
    vat_by_rate: dict[int, Decimal] = field(default_factory=lambda: {10: Decimal("0.00"), 20: Decimal("0.00")})
    reverse_charge_net: Decimal = Decimal("0.00")
    advertising_tax_amount: Decimal = Decimal("0.00")
    net_total: Decimal = Decimal("0.00")
    vat_total: Decimal = Decimal("0.00")
    gross_total: Decimal = Decimal("0.00")


def _apply_beleg_to_vat_summary(summary: VatSummary, *, items, reverse_charge: bool, totals, sign: int) -> None:
    if reverse_charge:
        summary.reverse_charge_net += sign * totals.net_total
    else:
        for item in items:
            summary.net_by_rate[item.vat_rate] = summary.net_by_rate.get(item.vat_rate, Decimal("0.00")) + sign * item.net_total
        for rate, amount in totals.vat_breakdown.items():
            summary.vat_by_rate[rate] = summary.vat_by_rate.get(rate, Decimal("0.00")) + sign * amount
    summary.advertising_tax_amount += sign * totals.advertising_tax_amount
    summary.net_total += sign * totals.net_total
    summary.gross_total += sign * totals.gross_total


def get_vat_summary(db: Session, date_from: date, date_to: date) -> VatSummary:
    summary = VatSummary(date_from=date_from, date_to=date_to)

    invoices = (
        db.query(Invoice)
        .filter(Invoice.invoice_date >= date_from, Invoice.invoice_date <= date_to)
        .all()
    )
    for invoice in invoices:
        totals = calculate_totals(
            invoice.items,
            reverse_charge=invoice.reverse_charge,
            advertising_tax_applicable=invoice.advertising_tax_applicable,
            advertising_tax_rate=invoice.advertising_tax_rate,
        )
        _apply_beleg_to_vat_summary(summary, items=invoice.items, reverse_charge=invoice.reverse_charge, totals=totals, sign=1)

    credit_notes = (
        db.query(CreditNote)
        .join(Invoice, CreditNote.invoice_id == Invoice.id)
        .filter(CreditNote.credit_note_date >= date_from, CreditNote.credit_note_date <= date_to)
        .all()
    )
    for credit_note in credit_notes:
        invoice = credit_note.invoice
        totals = calculate_totals(credit_note.items, reverse_charge=invoice.reverse_charge)
        _apply_beleg_to_vat_summary(summary, items=credit_note.items, reverse_charge=invoice.reverse_charge, totals=totals, sign=-1)

    summary.vat_total = sum(summary.vat_by_rate.values(), Decimal("0.00"))
    return summary


def vat_summary_to_csv(summary: VatSummary) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Bezeichnung", "Netto", "USt.-Betrag"])
    for rate in sorted(summary.net_by_rate):
        writer.writerow([f"{rate}% USt.", f"{summary.net_by_rate[rate]:.2f}", f"{summary.vat_by_rate.get(rate, Decimal('0.00')):.2f}"])
    writer.writerow(["Reverse-Charge (0% USt.)", f"{summary.reverse_charge_net:.2f}", "0.00"])
    writer.writerow(["Werbesteuer", f"{summary.advertising_tax_amount:.2f}", ""])
    writer.writerow(["Gesamt Netto", f"{summary.net_total:.2f}", ""])
    writer.writerow(["Gesamt USt.", "", f"{summary.vat_total:.2f}"])
    writer.writerow(["Gesamt Brutto", f"{summary.gross_total:.2f}", ""])
    return buffer.getvalue()
