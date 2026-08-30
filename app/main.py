import asyncio
from datetime import date

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_login
from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import Invoice, InvoiceStatus, User
from app.routers import articles, auth, company, credit_notes, customers, dunning, help, invoices, orders, updates, users
from app.services.update_check import check_for_update
from app.templating import templates
from app.version import __version__

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def create_tables():
    """Erstellt fehlende Tabellen. Fuer Schemaaenderungen im Produktivbetrieb Alembic-Migrationen verwenden."""
    Base.metadata.create_all(bind=engine)


@app.on_event("startup")
async def start_background_update_check():
    """Prueft periodisch (Standard: alle 24h) die Website auf eine neue Version.

    Rein informativ - installiert wird dadurch nichts. Siehe app/services/update_check.py.
    """
    if not settings.update_check_enabled:
        return

    async def loop() -> None:
        while True:
            db = SessionLocal()
            try:
                check_for_update(db)
            finally:
                db.close()
            await asyncio.sleep(settings.update_check_interval_hours * 3600)

    asyncio.create_task(loop())


@app.get("/healthz")
def healthz():
    """Unauthentifizierter Health-Check fuer den Updater-Container nach einem Update."""
    return {"status": "ok", "version": __version__}


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
app.include_router(updates.router)
app.include_router(help.router)


@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    from app.services.update_check import get_or_create_update_state

    open_invoices = db.query(Invoice).filter(Invoice.status != InvoiceStatus.BEZAHLT).count()
    overdue_invoices = (
        db.query(Invoice)
        .filter(Invoice.status != InvoiceStatus.BEZAHLT, Invoice.due_date < date.today())
        .count()
    )
    update_state = get_or_create_update_state(db) if user.role.value == "admin" else None
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"open_invoices": open_invoices, "overdue_invoices": overdue_invoices, "update_state": update_state},
    )


@app.exception_handler(303)
def redirect_handler(request: Request, exc):
    return RedirectResponse(exc.headers.get("Location", "/login"), status_code=303)
