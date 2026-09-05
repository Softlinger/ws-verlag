"""CSRF-Schutz (Double-Submit-Cookie, serverseitig verifiziert).

Prinzip: Die App setzt einen per itsdangerous signierten Token in ein Cookie
(same-site-lax, httponly). Jedes POST-Formular bettet denselben Token als
verstecktes Feld ein. Der Server verlangt auf unsicheren Methoden, dass Feldwert und
Cookie uebereinstimmen UND das Cookie eine gueltige Signatur tragt. Ein Cross-Site-
Angreifer kann das Cookie des Opfers nicht auslesen und damit weder Feldwert noch
gueltige Signatur mitliefern. Ergaenzt die bestehende SameSite=Lax-Verteidigung um
einen bewussten (nicht nur beilaeufigen) Schutz.

Anwendung: `require_csrf` als Router-Dependency anhaengen; `{{ csrf_field(request) }}`
in jedes POST-Formular. Server-zu-Server-POSTs (Updater-Report) sind ausgenommen, die
sind ueber X-Updater-Token gesichert.
"""
from itsdangerous import BadSignature, URLSafeSerializer
from fastapi import HTTPException, Request, status

from app.config import settings

_serializer = URLSafeSerializer(settings.secret_key, salt="ws-verlag-csrf")
COOKIE_NAME = "ws_verlag_csrf"

# POST-Endpunkte, die NICHT vom Browser-Formular kommen und stattdessen anderweitig
# gesichert sind (Updater-Report via X-Updater-Token).
_SERVER_TO_SERVER_PATHS = {"/updates/report"}


def create_token() -> str:
    # Stabiler, vorzeichenrichtiger Marker; die Signatur (Secret) macht ihn fälschungssicher.
    return _serializer.dumps("csrf")


def validate_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        return _serializer.loads(token) == "csrf"
    except BadSignature:
        return False


async def require_csrf(request: Request) -> None:
    """FastAPI-Dependency: erzwingt CSRF auf unsicheren Methoden.

    Liest request.form() - Starlette cacht den Body, nachgelagerte `Form(...)`-
    Parameter funktionieren dadurch weiterhin.
    """
    if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return
    if request.url.path in _SERVER_TO_SERVER_PATHS:
        return

    cookie_token = request.cookies.get(COOKIE_NAME)
    if not validate_token(cookie_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF-Token fehlt/abgelaufen.")
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 - kein Formular-Body -> kein gueltiger Submit
        form = {}
    if form.get("csrf_token") != cookie_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF-Token stimmt nicht ueberein.")
