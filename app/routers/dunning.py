from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import Dunning, Invoice, InvoiceStatus, MailStatus, User
from app.routers.company import get_or_create_company
from app.services.dunning import get_level_setting, next_dunning_level, render_dunning_text
from app.services.mailer import send_document_mail
from app.services.payments import open_amount as invoice_open_amount
from app.services.pdf import render_dunning_pdf
from app.templating import templates
from app.times import today_vienna

router = APIRouter(prefix="/dunning", tags=["dunning"])


@router.get("")
def list_open_invoices(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    today = today_vienna()
    invoices = (
        db.query(Invoice)
        .filter(Invoice.status != InvoiceStatus.BEZAHLT, Invoice.due_date < today)
        .order_by(Invoice.due_date)
        .all()
    )
    return templates.TemplateResponse(request, "dunning/list.html", {"invoices": invoices})


@router.post("/{invoice_id}/create")
def create_dunning(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    invoice = db.get(Invoice, invoice_id)

    # Bereits ausgeglichen (bezahlt oder vollstaendig gutgeschrieben)? Dann keine Mahnung.
    open_amt = invoice_open_amount(db, invoice)
    if open_amt <= Decimal("0.00"):
        return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)

    level = next_dunning_level(invoice)
    setting = get_level_setting(db, level)
    # Geforderter Betrag = offener Rechnungsrest + bereits aufgelaufene Mahngebuehren
    # fruherer Stufen (die sind ebenfalls geschuldet). Die Gebuehr DIESER Stufe kommt
    # erst mit naechsten Mahnungen dazu; als steuerpflichtige Position verbuchen waere
    # eine separate Steuer-Entscheidung und ist hier bewusst nicht eingerechnet.
    accrued_fees = sum((d.fee_amount for d in invoice.dunnings), Decimal("0.00"))
    demanded = open_amt + accrued_fees
    text = render_dunning_text(setting, invoice, demanded)
    dunning = Dunning(
        invoice_id=invoice.id,
        level=level,
        due_date=today_vienna() + timedelta(days=setting.due_days),
        fee_amount=setting.fee_amount,
        rendered_text=text,
        created_by_id=user.id,
    )
    db.add(dunning)
    try:
        db.commit()
    except IntegrityError:
        # Race zweier Sitzungen auf derselben Stufe -> Unique-Constraint greift, keine
        # Doppel-Mahnung. Transaktion verwerfen, ruhig auf der Rechnung bleiben.
        db.rollback()
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)


@router.get("/{dunning_id}/pdf")
def download_dunning_pdf(dunning_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    dunning = db.get(Dunning, dunning_id)
    company = get_or_create_company(db)
    pdf_bytes = render_dunning_pdf(company=company, dunning=dunning, invoice=dunning.invoice, customer=dunning.invoice.customer)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="Mahnung-{dunning.invoice.number}-{dunning.level}.pdf"'},
    )


@router.post("/{dunning_id}/send")
def send_dunning_mail(dunning_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    dunning = db.get(Dunning, dunning_id)
    if not dunning.invoice.customer.email.strip():
        return RedirectResponse(f"/invoices/{dunning.invoice.id}?error=no_email", status_code=303)

    company = get_or_create_company(db)
    pdf_bytes = render_dunning_pdf(company=company, dunning=dunning, invoice=dunning.invoice, customer=dunning.invoice.customer)
    mail_log = send_document_mail(
        db,
        company=company,
        related_type="dunning",
        related_id=dunning.id,
        recipient=dunning.invoice.customer.email,
        subject=f"{dunning.level}. Mahnung zu Rechnung {dunning.invoice.number}",
        body=dunning.rendered_text,
        pdf_bytes=pdf_bytes,
        pdf_filename=f"Mahnung-{dunning.invoice.number}-{dunning.level}.pdf",
    )
    db.commit()
    mail_status = "sent" if mail_log.status == MailStatus.GESENDET else "failed"
    return RedirectResponse(f"/invoices/{dunning.invoice.id}?mail={mail_status}", status_code=303)
