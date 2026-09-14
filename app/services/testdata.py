"""Entfernt Testdaten vor dem Produktivstart: alle Auftraege, Rechnungen und
Gutschriften samt Positionen, Zahlungen, Mahnungen und zugehoerigem Mail-Protokoll.
Artikel, Kunden und Firmenstammdaten bleiben unberuehrt (siehe app/routers/help.py).
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import CreditNote, CreditNoteItem, Dunning, Invoice, InvoiceItem, MailLog, Order, OrderItem, Payment


@dataclass
class PurgeCounts:
    orders: int
    invoices: int
    credit_notes: int


def count_test_documents(db: Session) -> PurgeCounts:
    return PurgeCounts(
        orders=db.query(Order).count(),
        invoices=db.query(Invoice).count(),
        credit_notes=db.query(CreditNote).count(),
    )


def purge_test_documents(db: Session) -> PurgeCounts:
    """Loescht unwiderruflich alle Auftraege/Rechnungen/Gutschriften. Reihenfolge
    beachtet die Fremdschluessel - Kinder vor Eltern, Rechnungen vor Auftraegen (auf
    die sie per order_id verweisen). Bulk-DELETE statt ORM-Cascades, da Query.delete()
    die in den Relationships hinterlegten cascade="all, delete-orphan" nicht ausloest."""
    counts = count_test_documents(db)

    db.query(MailLog).filter(MailLog.related_type.in_(["order", "invoice", "credit_note", "dunning"])).delete(
        synchronize_session=False
    )
    db.query(Dunning).delete(synchronize_session=False)
    db.query(Payment).delete(synchronize_session=False)
    db.query(CreditNoteItem).delete(synchronize_session=False)
    db.query(CreditNote).delete(synchronize_session=False)
    db.query(InvoiceItem).delete(synchronize_session=False)
    db.query(Invoice).delete(synchronize_session=False)
    db.query(OrderItem).delete(synchronize_session=False)
    db.query(Order).delete(synchronize_session=False)
    db.commit()
    return counts
