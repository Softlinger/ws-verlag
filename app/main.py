from datetime import date

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_login
from app.config import settings
from app.database import Base, engine, get_db
from app.models import Invoice, InvoiceStatus, User
from app.routers import articles, auth, company, credit_notes, customers, dunning, invoices, orders, users
from app.templating import templates

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def create_tables():
    """Erstellt fehlende Tabellen. Fuer Schemaaenderungen im Produktivbetrieb Alembic-Migrationen verwenden."""
    Base.metadata.create_all(bind=engine)


@app.middleware("http")
async def attach_current_user(request: Request, call_next):
    """Macht den eingeloggten Benutzer als request.state.user fuer Templates verfuegbar."""
    from app.auth import read_session_token
    from app.database import SessionLocal

    request.state.user = None
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        user_id = read_session_token(token)
        if user_id is not None:
            db = SessionLocal()
            try:
                user = db.get(User, user_id)
                if user and user.active:
                    request.state.user = user
            finally:
                db.close()
    return await call_next(request)

app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(articles.router)
app.include_router(orders.router)
app.include_router(invoices.router)
app.include_router(credit_notes.router)
app.include_router(dunning.router)
app.include_router(company.router)
app.include_router(users.router)


@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    open_invoices = db.query(Invoice).filter(Invoice.status != InvoiceStatus.BEZAHLT).count()
    overdue_invoices = (
        db.query(Invoice)
        .filter(Invoice.status != InvoiceStatus.BEZAHLT, Invoice.due_date < date.today())
        .count()
    )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"open_invoices": open_invoices, "overdue_invoices": overdue_invoices},
    )


@app.exception_handler(303)
def redirect_handler(request: Request, exc):
    return RedirectResponse(exc.headers.get("Location", "/login"), status_code=303)
