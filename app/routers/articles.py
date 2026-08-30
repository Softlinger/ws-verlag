from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import Article, User
from app.templating import templates

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("")
def list_articles(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    articles = db.query(Article).order_by(Article.name).all()
    return templates.TemplateResponse(request, "articles/list.html", {"articles": articles})


@router.get("/new")
def new_article_form(request: Request, user: User = Depends(require_login)):
    return templates.TemplateResponse(request, "articles/form.html", {"article": None})


@router.post("/new")
def create_article(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    name: str = Form(...),
    description: str = Form(""),
    unit_price: Decimal = Form(...),
    vat_rate: int = Form(20),
    unit: str = Form("Stk"),
):
    article = Article(name=name, description=description, unit_price=unit_price, vat_rate=vat_rate, unit=unit)
    db.add(article)
    db.commit()
    return RedirectResponse("/articles", status_code=303)


@router.get("/{article_id}/edit")
def edit_article_form(article_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    article = db.get(Article, article_id)
    return templates.TemplateResponse(request, "articles/form.html", {"article": article})


@router.post("/{article_id}/edit")
def update_article(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
    name: str = Form(...),
    description: str = Form(""),
    unit_price: Decimal = Form(...),
    vat_rate: int = Form(20),
    unit: str = Form("Stk"),
    active: bool = Form(False),
):
    article = db.get(Article, article_id)
    article.name = name
    article.description = description
    article.unit_price = unit_price
    article.vat_rate = vat_rate
    article.unit = unit
    article.active = active
    db.commit()
    return RedirectResponse("/articles", status_code=303)
