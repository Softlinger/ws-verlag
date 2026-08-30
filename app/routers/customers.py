from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import BankAccount, Customer, PaymentTerm, User
from app.templating import templates

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
def list_customers(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    customers = db.query(Customer).order_by(Customer.name).all()
    return templates.TemplateResponse(request, "customers/list.html", {"customers": customers})


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
