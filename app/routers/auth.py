import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    create_session_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models import User
from app.services.update_check import check_for_update, get_or_create_update_state, is_check_due
from app.templating import templates

router = APIRouter(tags=["auth"])

# Einfacher In-Memory-Brute-Force-Schutz pro (IP, Benutzername): max. LOGIN_MAX_ATTEMPTS
# Fehlversuche im rollierenden LOGIN_LOCKOUT_SECONDS-Fenster. Bewusst prozesslokal und
# flüchtig - reicht für den einzelnen LAN-Server; ein Neustart setzt ihn zurück.
_LOGIN_FAILS: dict[tuple[str, str], deque[float]] = defaultdict(deque)
LOGIN_MAX_ATTEMPTS = 8
LOGIN_LOCKOUT_SECONDS = 300
# Feste Dummy-Hash, um bei unbekanntem Benutzer dieselbe bcrypt-Kostenzeit zu
# verbrauchen (verhindert User-Enumeration über Antwortzeit).
_DUMMY_HASH = hash_password("ws-verlag-timing-equalizer")


def _is_rate_limited(key: tuple[str, str]) -> bool:
    now = time.monotonic()
    fails = _LOGIN_FAILS[key]
    while fails and now - fails[0] > LOGIN_LOCKOUT_SECONDS:
        fails.popleft()
    return len(fails) >= LOGIN_MAX_ATTEMPTS


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/login")
def login_form(request: Request, user: User | None = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    key = (_client_ip(request), username)
    if _is_rate_limited(key):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Zu viele Fehlversuche. Bitte einige Minuten warten."},
            status_code=429,
        )

    user = db.query(User).filter(User.username == username).one_or_none()
    # Immer genau einmal bcrypt verify() laufen lassen (auch bei fehlendem Benutzer),
    # damit aus der Antwortzeit nicht hervorgeht, ob der Benutzername existiert.
    stored_hash = user.password_hash if user is not None else _DUMMY_HASH
    password_ok = verify_password(password, stored_hash)
    if user is None or not user.active or not password_ok:
        _LOGIN_FAILS[key].append(time.monotonic())
        return templates.TemplateResponse(
            request, "login.html", {"error": "Benutzername oder Passwort falsch."}, status_code=401
        )

    _LOGIN_FAILS.pop(key, None)
    if user.role.value == "admin":
        state = get_or_create_update_state(db)
        if is_check_due(state):
            check_for_update(db)

    token = create_session_token(user)
    response = RedirectResponse("/", status_code=303)
    # Session-Cookie ueber HTTPS senden -> nur dann 'secure'; hinter einem TLS-Proxy
    # erkennt request.url.scheme/X-Forwarded-Proto https. Auf reinem LAN-HTTP bleibt
    # es ohne secure, sonst koennte sich niemand einloggen (Browser verwirft Cookie).
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip() or request.url.scheme
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=(proto == "https"),
        path="/",
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    # Attribute muessen zum Setzen passen, sonst loeschen manche Browser das Cookie nicht.
    response.delete_cookie(settings.session_cookie_name, path="/", samesite="lax")
    return response
