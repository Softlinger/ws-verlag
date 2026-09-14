from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import BankAccount, Customer, Invoice, Order, PaymentTerm, User
from app.routers.company import get_or_create_company
from app.services.pdf import render_address_label_pdf
from app.templating import templates

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
def list_customers(request: Request, q: str = "", db: Session = Depends(get_db), user: User = Depends(require_login)):
    query = db.query(Customer)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Customer.name.ilike(like),
                Customer.name2.ilike(like),
                Customer.street.ilike(like),
                Customer.city.ilike(like),
                Customer.postal_code.ilike(like),
                Customer.uid_number.ilike(like),
                Customer.email.ilike(like),
            )
        )
    customers = query.order_by(Customer.name).all()
    return templates.TemplateResponse(request, "customers/list.html", {"customers": customers, "q": q})


@router.get("/new")
def new_customer_form(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    return templates.TemplateResponse(
        request,
        "customers/form.html",
        {
            "customer": None,
            "payment_terms": db.query(PaymentTerm).all(),
            "bank_accounts": db.query(BankAccount).all(),
        },
    )


@router.post("/new")
def create_customer(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    name: str = Form(...),
    name2: str = Form(""),
    street: str = Form(""),
    street2: str = Form(""),
    postal_code: str = Form(""),
    city: str = Form(""),
    country: str = Form("Oesterreich"),
    is_eu_country: bool = Form(False),
    uid_number: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    contact_person: str = Form(""),
    payment_term_id: str = Form(""),
    bank_account_id: str = Form(""),
):
    customer = Customer(
        name=name,
        name2=name2,
        street=street,
        street2=street2,
        postal_code=postal_code,
        city=city,
        country=country,
        is_eu_country=is_eu_country,
        uid_number=uid_number,
        email=email,
        phone=phone,
        contact_person=contact_person,
        payment_term_id=int(payment_term_id) if payment_term_id else None,
        bank_account_id=int(bank_account_id) if bank_account_id else None,
    )
    db.add(customer)
    db.commit()
    return RedirectResponse("/customers", status_code=303)


@router.get("/{customer_id}/edit")
def edit_customer_form(
    customer_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)
):
    customer = db.get(Customer, customer_id)
    return templates.TemplateResponse(
        request,
        "customers/form.html",
        {
            "customer": customer,
            "payment_terms": db.query(PaymentTerm).all(),
            "bank_accounts": db.query(BankAccount).all(),
        },
    )


@router.post("/{customer_id}/edit")
def update_customer(
    customer_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    name: str = Form(...),
    name2: str = Form(""),
    street: str = Form(""),
    street2: str = Form(""),
    postal_code: str = Form(""),
    city: str = Form(""),
    country: str = Form("Oesterreich"),
    is_eu_country: bool = Form(False),
    uid_number: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    contact_person: str = Form(""),
    payment_term_id: str = Form(""),
    bank_account_id: str = Form(""),
    active: bool = Form(False),
):
    customer = db.get(Customer, customer_id)
    customer.name = name
    customer.name2 = name2
    customer.street = street
    customer.street2 = street2
    customer.postal_code = postal_code
    customer.city = city
    customer.country = country
    customer.is_eu_country = is_eu_country
    customer.uid_number = uid_number
    customer.email = email
    customer.phone = phone
    customer.contact_person = contact_person
    customer.payment_term_id = int(payment_term_id) if payment_term_id else None
    customer.bank_account_id = int(bank_account_id) if bank_account_id else None
    customer.active = active
    db.commit()
    return RedirectResponse("/customers", status_code=303)


@router.post("/{customer_id}/delete")
def delete_customer(customer_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)):
    customer = db.get(Customer, customer_id)
    if customer:
        # Referenziert? Auftraege/Rechnungen unterliegen der Aufbewahrungspflicht (Buchhaltung)
        # und duerfen nicht verwaist werden - dann nur Deaktivieren statt Loeschen anbieten.
        in_use = (
            db.query(Order).filter(Order.customer_id == customer_id).count()
            + db.query(Invoice).filter(Invoice.customer_id == customer_id).count()
        )
        if in_use:
            return RedirectResponse("/customers?error=customer_in_use", status_code=303)
        db.delete(customer)
        db.commit()
    return RedirectResponse("/customers", status_code=303)


@router.get("/{customer_id}/address-pdf")
def download_address_label_pdf(
    customer_id: int, db: Session = Depends(get_db), user: User = Depends(require_login)
):
    customer = db.get(Customer, customer_id)
    company = get_or_create_company(db)
    pdf_bytes = render_address_label_pdf(company=company, customer=customer)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="Adresse-{customer.id}.pdf"'},
    )
