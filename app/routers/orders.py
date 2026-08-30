from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import Article, Customer, DocumentType, Order, OrderItem, User
from app.services.numbering import generate_next_number
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
def view_order(order_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    order = db.get(Order, order_id)
    return templates.TemplateResponse(request, "orders/detail.html", {"order": order})
