import asyncio
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_login, resolve_user_from_token
from app.config import settings
from app.csrf import require_csrf
from app.database import Base, SessionLocal, engine, ensure_new_columns, ensure_new_constraints, get_db
from app.models import Invoice, InvoiceStatus, UpdateApplyStatus, UpdateState, User
from app.routers import (
    account,
    accounting,
    articles,
    auth,
    company,
    credit_notes,
    customers,
    dunning,
    help,
    invoices,
    mail_log,
    orders,
    reports,
    updates,
    users,
)
from app.services.update_check import check_for_update
from app.templating import templates
from app.version import __version__

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


DEFAULT_SECRET_KEY = "change-me-in-production-please"
# Pfade, die auch während eines Updates erreichbar bleiben MUESSEN (sonst kann der
# Updater sein Ergebnis nicht zurückmelden und die Health-Prüfung würde fehlschlagen).
_MAINTENANCE_ALLOWLIST = (
    "/healthz",
    "/login",
    "/logout",
    "/static",
    "/updates",  # Admin-Update-Seite + status.json/report/check
)


@app.on_event("startup")
def create_tables():
    """Erstellt fehlende Tabellen. Fuer Schemaaenderungen im Produktivbetrieb Alembic-Migrationen verwenden."""
    if settings.secret_key == DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY ist nicht gesetzt (steht auf dem Default-Wert). Session-Cookies "
            "waeren faelschbar. SECRET_KEY in .env setzen (z. B. "
            "`python -c \"import secrets; print(secrets.token_urlsafe(32))\"`)."
        )
    Base.metadata.create_all(bind=engine)
    ensure_new_columns()
    ensure_new_constraints()


def _update_in_progress(db: Session) -> bool:
    """True, solange ein Update laeuft (und nicht ein altes, nie abgeschlossenes Signal
    das Tor blockiert). Fuehrt dazu, dass die App normalen Benutzerzugriff ablehnt,
    damit niemand waehrend Backup/Container-Tausch auf App oder DB schreibt."""
    state = db.query(UpdateState).order_by(UpdateState.id).first()
    if state is None or state.apply_status not in (
        UpdateApplyStatus.ANGEFORDERT,
        UpdateApplyStatus.WIRD_INSTALLIERT,
    ):
        return False
    requested_at = state.apply_requested_at
    if requested_at is None:
        return False
    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - requested_at < timedelta(seconds=settings.update_maintenance_timeout_seconds)


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
async def maintenance_and_user_middleware(request: Request, call_next):
    """Waehrend eines laufenden Updates normalen Zugriff blockieren (503) und den
    eingeloggten Benutzer als request.state.user fuer Templates bereitstellen.

    Ein Update tauscht den App-Container aus, aber MariaDB laeuft weiter - ohne dieses
    Gate koennten Benutzer waehrend Backup/Tausch weiter auf App UND DB schreiben
    (inkonsistentes Backup, Schreiben ins laufende Upgrade). Erlaubt bleiben nur die
    Pfade in _MAINTENANCE_ALLOWLIST (Health-Check, Login/Logout, statische Dateien und
    /updates inkl. status.json/report/check, damit der Updater abschliessen kann).
    """
    request.state.user = None
    db = SessionLocal()
    try:
        token = request.cookies.get(settings.session_cookie_name)
        request.state.user = resolve_user_from_token(token, db)

        path = request.url.path
        in_maintenance = path.startswith(_MAINTENANCE_ALLOWLIST)
        if not in_maintenance and _update_in_progress(db):
            return HTMLResponse(
                "<h1>Wartungsmodus</h1><p>Die Anwendung fuehrt gerade ein Update aus "
                "und ist gleich wieder erreichbar. Bitte kurz warten.</p>",
                status_code=503,
                headers={"Retry-After": "60"},
            )
    finally:
        db.close()

    # CSRF-Token bereitstellen: vorhandenes, gueltiges Cookie verwenden oder neu
    # erzeugen und (zusammen mit einem evtl. Session-Cookie) auf die Response setzen.
    from app.csrf import COOKIE_NAME as CSRF_COOKIE, create_token, validate_token

    fresh_csrf = None
    existing = request.cookies.get(CSRF_COOKIE)
    if validate_token(existing):
        request.state.csrf_token = existing
    else:
        fresh_csrf = create_token()
        request.state.csrf_token = fresh_csrf

    response = await call_next(request)
    if fresh_csrf is not None:
        response.set_cookie(
            CSRF_COOKIE,
            fresh_csrf,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=settings.session_max_age_seconds,
        )
    return response

app.include_router(auth.router, dependencies=[Depends(require_csrf)])
app.include_router(accounting.router, dependencies=[Depends(require_csrf)])
app.include_router(customers.router, dependencies=[Depends(require_csrf)])
app.include_router(articles.router, dependencies=[Depends(require_csrf)])
app.include_router(orders.router, dependencies=[Depends(require_csrf)])
app.include_router(invoices.router, dependencies=[Depends(require_csrf)])
app.include_router(credit_notes.router, dependencies=[Depends(require_csrf)])
app.include_router(dunning.router, dependencies=[Depends(require_csrf)])
app.include_router(reports.router, dependencies=[Depends(require_csrf)])
app.include_router(company.router, dependencies=[Depends(require_csrf)])
app.include_router(users.router, dependencies=[Depends(require_csrf)])
app.include_router(updates.router, dependencies=[Depends(require_csrf)])
app.include_router(help.router, dependencies=[Depends(require_csrf)])
app.include_router(account.router, dependencies=[Depends(require_csrf)])
app.include_router(mail_log.router, dependencies=[Depends(require_csrf)])


@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_login)):
    from app.services.update_check import get_or_create_update_state
    from app.times import today_vienna

    today = today_vienna()
    open_invoices = db.query(Invoice).filter(Invoice.status != InvoiceStatus.BEZAHLT).count()
    overdue_invoices = (
        db.query(Invoice)
        .filter(Invoice.status != InvoiceStatus.BEZAHLT, Invoice.due_date < today)
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
