from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import CreditNote, CreditNoteItem, DocumentType, Invoice, User
from app.routers.company import get_or_create_company
from app.services.mailer import send_document_mail
from app.services.numbering import generate_next_number
from app.services.pdf import render_credit_note_pdf
from app.services.tax import calculate_totals
from app.templating import templates

router = APIRouter(prefix="/credit-notes", tags=["credit_notes"])


@router.get("")
def list_credit_notes(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    credit_notes = db.query(CreditNote).order_by(CreditNote.id.desc()).all()
    return templates.TemplateResponse(request, "credit_notes/list.html", {"credit_notes": credit_notes})


@router.get("/new")
def new_credit_note_form(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_login), invoice_id: int | None = None
):
    invoice = db.get(Invoice, invoice_id) if invoice_id else None
    invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
    return templates.TemplateResponse(
        request, "credit_notes/form.html", {"invoice": invoice, "invoices": invoices}
    )


@router.post("/new")
def create_credit_note(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    invoice_id: int = Form(...),
    credit_note_date: date = Form(...),
    reason: str = Form(""),
    description: list[str] = Form(default=[]),
    quantity: list[Decimal] = Form(default=[]),
    unit_price: list[Decimal] = Form(default=[]),
    vat_rate: list[int] = Form(default=[]),
):
    number = generate_next_number(db, DocumentType.GUTSCHRIFT)
    credit_note = CreditNote(number=number, invoice_id=invoice_id, credit_note_date=credit_note_date, reason=reason)
    db.add(credit_note)
    db.flush()

    for idx, desc in enumerate(description):
        if not desc.strip():
            continue
        credit_note.items.append(
            CreditNoteItem(
                description=desc,
                quantity=quantity[idx] if idx < len(quantity) else Decimal("1"),
                unit_price=unit_price[idx] if idx < len(unit_price) else Decimal("0.00"),
                vat_rate=vat_rate[idx] if idx < len(vat_rate) else 20,
            )
        )
    db.commit()
    return RedirectResponse(f"/credit-notes/{credit_note.id}", status_code=303)


@router.get("/{credit_note_id}")
def view_credit_note(
    credit_note_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)
):
    credit_note = db.get(CreditNote, credit_note_id)
    totals = calculate_totals(credit_note.items)
    return templates.TemplateResponse(request, "credit_notes/detail.html", {"credit_note": credit_note, "totals": totals})


@router.get("/{credit_note_id}/pdf")
def download_credit_note_pdf(credit_note_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    credit_note = db.get(CreditNote, credit_note_id)
    company = get_or_create_company(db)
    totals = calculate_totals(credit_note.items)
    pdf_bytes = render_credit_note_pdf(
        company=company, credit_note=credit_note, customer=credit_note.invoice.customer, items=credit_note.items, totals=totals
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{credit_note.number}.pdf"'},
    )


@router.post("/{credit_note_id}/send")
def send_credit_note_mail(credit_note_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    credit_note = db.get(CreditNote, credit_note_id)
    company = get_or_create_company(db)
    totals = calculate_totals(credit_note.items)
    pdf_bytes = render_credit_note_pdf(
        company=company, credit_note=credit_note, customer=credit_note.invoice.customer, items=credit_note.items, totals=totals
    )
    send_document_mail(
        db,
        company=company,
        related_type="credit_note",
        related_id=credit_note.id,
        recipient=credit_note.invoice.customer.email,
        subject=f"Gutschrift {credit_note.number}",
        body=f"Sehr geehrte/r {credit_note.invoice.customer.name},\n\nanbei erhalten Sie Gutschrift {credit_note.number}.\n\nMit freundlichen Gruessen\n{company.name}",
        pdf_bytes=pdf_bytes,
        pdf_filename=f"{credit_note.number}.pdf",
    )
    db.commit()
    return RedirectResponse(f"/credit-notes/{credit_note.id}", status_code=303)
