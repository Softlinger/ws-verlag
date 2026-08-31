from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import CreditNote, Dunning, Invoice, MailLog, Order, User
from app.templating import templates

router = APIRouter(prefix="/mail-log", tags=["mail_log"])

_LABELS = {
    "order": "Auftrag",
    "invoice": "Rechnung",
    "credit_note": "Gutschrift",
    "dunning": "Mahnung",
}

_RESEND_URL = {
    "order": "/orders/{id}/send",
    "invoice": "/invoices/{id}/send",
    "credit_note": "/credit-notes/{id}/send",
    "dunning": "/dunning/{id}/send",
}


def _detail_url(db: Session, related_type: str, related_id: int) -> str | None:
    if related_type == "order" and db.get(Order, related_id):
        return f"/orders/{related_id}"
    if related_type == "invoice" and db.get(Invoice, related_id):
        return f"/invoices/{related_id}"
    if related_type == "credit_note" and db.get(CreditNote, related_id):
        return f"/credit-notes/{related_id}"
    if related_type == "dunning":
        dunning = db.get(Dunning, related_id)
        if dunning:
            return f"/invoices/{dunning.invoice_id}"
    return None


@router.get("")
def list_mail_log(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    entries = db.query(MailLog).order_by(MailLog.sent_at.desc()).all()
    rows = []
    for entry in entries:
        rows.append(
            {
                "entry": entry,
                "type_label": _LABELS.get(entry.related_type, entry.related_type),
                "detail_url": _detail_url(db, entry.related_type, entry.related_id),
                "resend_url": _RESEND_URL.get(entry.related_type, "").format(id=entry.related_id)
                if entry.related_type in _RESEND_URL
                else None,
            }
        )
    return templates.TemplateResponse(request, "mail_log/list.html", {"rows": rows})
