from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import Article, Customer, DocumentType, Invoice, Order, OrderItem, User
from app.routers.company import get_or_create_company
from app.services.mailer import send_document_mail
from app.services.numbering import generate_next_number
from app.services.pdf import render_order_pdf
from app.services.tax import calculate_totals
from app.templating import templates

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
def list_orders(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    orders = db.query(Order).order_by(Order.id.desc()).all()
    return templates.TemplateResponse(request, "orders/list.html", {"orders": orders})


@router.get("/new")
def new_order_form(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    return templates.TemplateResponse(
        request,
        "orders/form.html",
        {
            "order": None,
            "customers": db.query(Customer).filter(Customer.active.is_(True)).order_by(Customer.name).all(),
            "articles": db.query(Article).filter(Article.active.is_(True)).order_by(Article.name).all(),
        },
    )


@router.post("/new")
def create_order(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    customer_id: int = Form(...),
    order_date: date = Form(...),
    advertising_tax_applicable: bool = Form(False),
    note: str = Form(""),
    article_id: list[str] = Form(default=[]),
    description: list[str] = Form(default=[]),
    quantity: list[Decimal] = Form(default=[]),
    unit_price: list[Decimal] = Form(default=[]),
    vat_rate: list[int] = Form(default=[]),
):
    number = generate_next_number(db, DocumentType.AUFTRAG)
    order = Order(
        number=number,
        customer_id=customer_id,
        order_date=order_date,
        advertising_tax_applicable=advertising_tax_applicable,
        note=note,
    )
    db.add(order)
    db.flush()

    for idx, desc in enumerate(description):
        if not desc.strip():
            continue
        order.items.append(
            OrderItem(
                article_id=int(article_id[idx]) if idx < len(article_id) and article_id[idx] else None,
                description=desc,
                quantity=quantity[idx] if idx < len(quantity) else Decimal("1"),
                unit_price=unit_price[idx] if idx < len(unit_price) else Decimal("0.00"),
                vat_rate=vat_rate[idx] if idx < len(vat_rate) else 20,
            )
        )
    db.commit()
    return RedirectResponse(f"/orders/{order.id}", status_code=303)


@router.get("/{order_id}")
def view_order(
    order_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_login), error: str = ""
):
    order = db.get(Order, order_id)
    totals = calculate_totals(
        order.items,
        reverse_charge=order.customer.reverse_charge_applicable,
        advertising_tax_applicable=order.advertising_tax_applicable,
    )
    has_invoices = db.query(Invoice).filter(Invoice.order_id == order.id).count() > 0
    return templates.TemplateResponse(
        request, "orders/detail.html", {"order": order, "totals": totals, "has_invoices": has_invoices, "error": error}
    )


@router.get("/{order_id}/pdf")
def download_order_pdf(order_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    order = db.get(Order, order_id)
    company = get_or_create_company(db)
    totals = calculate_totals(
        order.items,
        reverse_charge=order.customer.reverse_charge_applicable,
        advertising_tax_applicable=order.advertising_tax_applicable,
    )
    pdf_bytes = render_order_pdf(company=company, order=order, customer=order.customer, items=order.items, totals=totals)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{order.number}.pdf"'},
    )


@router.post("/{order_id}/send")
def send_order_mail(order_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    order = db.get(Order, order_id)
    if not order.customer.email.strip():
        return RedirectResponse(f"/orders/{order.id}?error=no_email", status_code=303)

    company = get_or_create_company(db)
    totals = calculate_totals(
        order.items,
        reverse_charge=order.customer.reverse_charge_applicable,
        advertising_tax_applicable=order.advertising_tax_applicable,
    )
    pdf_bytes = render_order_pdf(company=company, order=order, customer=order.customer, items=order.items, totals=totals)
    send_document_mail(
        db,
        company=company,
        related_type="order",
        related_id=order.id,
        recipient=order.customer.email,
        subject=f"Auftragsbestätigung {order.number}",
        body=(
            f"Sehr geehrte/r {order.customer.name},\n\nanbei erhalten Sie die Auftragsbestätigung "
            f"{order.number}.\n\nMit freundlichen Grüßen\n{company.name}"
        ),
        pdf_bytes=pdf_bytes,
        pdf_filename=f"{order.number}.pdf",
    )
    db.commit()
    return RedirectResponse(f"/orders/{order.id}", status_code=303)


@router.get("/{order_id}/edit")
def edit_order_form(order_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    order = db.get(Order, order_id)
    return templates.TemplateResponse(
        request,
        "orders/form.html",
        {
            "order": order,
            "customers": db.query(Customer).filter(Customer.active.is_(True)).order_by(Customer.name).all(),
            "articles": db.query(Article).filter(Article.active.is_(True)).order_by(Article.name).all(),
        },
    )


@router.post("/{order_id}/edit")
def update_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    customer_id: int = Form(...),
    order_date: date = Form(...),
    advertising_tax_applicable: bool = Form(False),
    note: str = Form(""),
    article_id: list[str] = Form(default=[]),
    description: list[str] = Form(default=[]),
    quantity: list[Decimal] = Form(default=[]),
    unit_price: list[Decimal] = Form(default=[]),
    vat_rate: list[int] = Form(default=[]),
):
    order = db.get(Order, order_id)
    order.customer_id = customer_id
    order.order_date = order_date
    order.advertising_tax_applicable = advertising_tax_applicable
    order.note = note

    order.items.clear()
    db.flush()
    for idx, desc in enumerate(description):
        if not desc.strip():
            continue
        order.items.append(
            OrderItem(
                article_id=int(article_id[idx]) if idx < len(article_id) and article_id[idx] else None,
                description=desc,
                quantity=quantity[idx] if idx < len(quantity) else Decimal("1"),
                unit_price=unit_price[idx] if idx < len(unit_price) else Decimal("0.00"),
                vat_rate=vat_rate[idx] if idx < len(vat_rate) else 20,
            )
        )
    db.commit()
    return RedirectResponse(f"/orders/{order.id}", status_code=303)


@router.post("/{order_id}/delete")
def delete_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    order = db.get(Order, order_id)
    if db.query(Invoice).filter(Invoice.order_id == order.id).count() > 0:
        # Auftrag wurde bereits abgerechnet - Loeschen wuerde die Nachvollziehbarkeit der
        # Rechnung gefaehrden. Stattdessen muesste zuerst die Rechnung storniert werden.
        return RedirectResponse(f"/orders/{order.id}?error=has_invoices", status_code=303)
    db.delete(order)
    db.commit()
    return RedirectResponse("/orders", status_code=303)
