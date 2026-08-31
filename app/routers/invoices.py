from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import (
    Article,
    BankAccount,
    Customer,
    DocumentType,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    Order,
    PaymentTerm,
    User,
)
from app.routers.company import get_or_create_company
from app.services.mailer import send_document_mail
from app.services.numbering import generate_next_number
from app.services.pdf import render_invoice_pdf
from app.services.tax import calculate_totals
from app.templating import templates

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _build_totals(invoice: Invoice):
    return calculate_totals(
        invoice.items,
        reverse_charge=invoice.reverse_charge,
        advertising_tax_applicable=invoice.advertising_tax_applicable,
        advertising_tax_rate=invoice.advertising_tax_rate,
    )


@router.get("")
def list_invoices(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
    totals_by_id = {inv.id: _build_totals(inv) for inv in invoices}
    return templates.TemplateResponse(
        request, "invoices/list.html", {"invoices": invoices, "totals_by_id": totals_by_id}
    )


@router.get("/new")
def new_invoice_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    order_id: int | None = None,
):
    order = db.get(Order, order_id) if order_id else None
    return templates.TemplateResponse(
        request,
        "invoices/form.html",
        {
            "order": order,
            "customers": db.query(Customer).filter(Customer.active.is_(True)).order_by(Customer.name).all(),
            "articles": db.query(Article).filter(Article.active.is_(True)).order_by(Article.name).all(),
            "bank_accounts": db.query(BankAccount).all(),
        },
    )


@router.post("/new")
def create_invoice(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    customer_id: int = Form(...),
    order_id: str = Form(""),
    invoice_date: date = Form(...),
    advertising_tax_applicable: bool = Form(False),
    bank_account_id: str = Form(""),
    article_id: list[str] = Form(default=[]),
    description: list[str] = Form(default=[]),
    quantity: list[Decimal] = Form(default=[]),
    unit_price: list[Decimal] = Form(default=[]),
    vat_rate: list[int] = Form(default=[]),
):
    customer = db.get(Customer, customer_id)
    company = get_or_create_company(db)

    payment_term_days = customer.payment_term.days_due if customer.payment_term else 14
    number = generate_next_number(db, DocumentType.RECHNUNG)
    invoice = Invoice(
        number=number,
        order_id=int(order_id) if order_id else None,
        customer_id=customer_id,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=payment_term_days),
        reverse_charge=customer.reverse_charge_applicable,
        advertising_tax_applicable=advertising_tax_applicable,
        advertising_tax_rate=company.advertising_tax_rate,
        bank_account_id=int(bank_account_id) if bank_account_id else customer.bank_account_id,
    )
    db.add(invoice)
    db.flush()

    for idx, desc in enumerate(description):
        if not desc.strip():
            continue
        invoice.items.append(
            InvoiceItem(
                article_id=int(article_id[idx]) if idx < len(article_id) and article_id[idx] else None,
                description=desc,
                quantity=quantity[idx] if idx < len(quantity) else Decimal("1"),
                unit_price=unit_price[idx] if idx < len(unit_price) else Decimal("0.00"),
                vat_rate=vat_rate[idx] if idx < len(vat_rate) else 20,
            )
        )
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)


@router.get("/{invoice_id}")
def view_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    invoice = db.get(Invoice, invoice_id)
    totals = _build_totals(invoice)
    paid_total = sum((p.amount for p in invoice.payments), Decimal("0.00"))
    return templates.TemplateResponse(
        request,
        "invoices/detail.html",
        {"invoice": invoice, "totals": totals, "paid_total": paid_total, "open_amount": totals.gross_total - paid_total},
    )


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    invoice = db.get(Invoice, invoice_id)
    company = get_or_create_company(db)
    totals = _build_totals(invoice)
    pdf_bytes = render_invoice_pdf(
        company=company, invoice=invoice, customer=invoice.customer, items=invoice.items, totals=totals
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.number}.pdf"'},
    )


@router.post("/{invoice_id}/send")
def send_invoice_mail(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice.customer.email.strip():
        return RedirectResponse(f"/invoices/{invoice.id}?error=no_email", status_code=303)

    company = get_or_create_company(db)
    totals = _build_totals(invoice)
    pdf_bytes = render_invoice_pdf(
        company=company, invoice=invoice, customer=invoice.customer, items=invoice.items, totals=totals
    )
    send_document_mail(
        db,
        company=company,
        related_type="invoice",
        related_id=invoice.id,
        recipient=invoice.customer.email,
        subject=f"Rechnung {invoice.number}",
        body=f"Sehr geehrte/r {invoice.customer.name},\n\nanbei erhalten Sie Rechnung {invoice.number}.\n\nMit freundlichen Gruessen\n{company.name}",
        pdf_bytes=pdf_bytes,
        pdf_filename=f"{invoice.number}.pdf",
    )
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)


@router.post("/{invoice_id}/payments")
def add_payment(
    invoice_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    amount: Decimal = Form(...),
    payment_date: date = Form(...),
    method: str = Form("Ueberweisung"),
    note: str = Form(""),
):
    from app.models import Payment

    invoice = db.get(Invoice, invoice_id)
    db.add(
        Payment(
            invoice_id=invoice.id, amount=amount, payment_date=payment_date, method=method, note=note, created_by_id=user.id
        )
    )
    db.flush()

    totals = _build_totals(invoice)
    paid_total = sum((p.amount for p in invoice.payments), Decimal("0.00"))
    if paid_total >= totals.gross_total:
        invoice.status = InvoiceStatus.BEZAHLT
    elif paid_total > 0:
        invoice.status = InvoiceStatus.TEILBEZAHLT
    else:
        invoice.status = InvoiceStatus.OFFEN

    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)
