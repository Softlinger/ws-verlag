from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import Customer, Invoice, InvoiceStatus, User
from app.routers.invoices import _build_totals
from app.services.payments import record_payment
from app.templating import templates

router = APIRouter(prefix="/accounting", tags=["accounting"])


@router.get("/open-items")
def list_open_items(request: Request, q: str = "", db: Session = Depends(get_db), user: User = Depends(require_login)):
    query = db.query(Invoice).filter(Invoice.status != InvoiceStatus.BEZAHLT)
    if q:
        like = f"%{q}%"
        query = query.join(Customer).filter(or_(Invoice.number.ilike(like), Customer.name.ilike(like)))
    invoices = query.order_by(Invoice.due_date).all()
    today = date.today()
    rows = []
    for invoice in invoices:
        totals = _build_totals(invoice)
        paid_total = sum((p.amount for p in invoice.payments), Decimal("0.00"))
        rows.append(
            {
                "invoice": invoice,
                "gross_total": totals.gross_total,
                "paid_total": paid_total,
                "open_amount": totals.gross_total - paid_total,
                "overdue": invoice.due_date < today,
            }
        )
    return templates.TemplateResponse(request, "accounting/open_items.html", {"rows": rows, "today": today, "q": q})


@router.post("/open-items/{invoice_id}/confirm-payment")
def confirm_payment(
    invoice_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    amount: Decimal = Form(...),
    payment_date: date = Form(...),
    method: str = Form("Ueberweisung"),
    note: str = Form(""),
):
    invoice = db.get(Invoice, invoice_id)
    record_payment(
        db, invoice, amount=amount, payment_date=payment_date, method=method, note=note, created_by_id=user.id
    )
    db.commit()
    return RedirectResponse("/accounting/open-items", status_code=303)
