from itsdangerous import BadSignature, URLSafeTimedSerializer
from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(settings.secret_key, salt="ws-verlag-session")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_session_token(user: "User") -> str:
    return serializer.dumps({"uid": user.id, "pv": user.password_version})


def read_session_token(token: str) -> dict | None:
    try:
        return serializer.loads(token, max_age=settings.session_max_age_seconds)
    except BadSignature:
        return None


def resolve_user_from_token(token: str | None, db: Session) -> "User | None":
    """Einzigelle Session-Auflösung (Middleware + get_current_user teilen sie).

    Prüft Signatur/Ablauf, dass der Benutzer existiert UND aktiv ist, und dass der im
    Cookie eingebaute password_version-Wert noch mit dem Benutzer übereinstimmt - so
    widerruft ein Passwortwechsel/Deaktivieren bestehende Sessions sofort, obwohl der
    Cookie noch nicht abgelaufen ist.
    """
    if not token:
        return None
    payload = read_session_token(token)
    if payload is None:
        return None
    user = db.get(User, payload.get("uid"))
    if user is None or not user.active:
        return None
    if int(payload.get("pv", 0)) != int(user.password_version):
        return None
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return resolve_user_from_token(request.cookies.get(settings.session_cookie_name), db)


def require_login(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def require_admin(user: User = Depends(require_login)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur fuer Administratoren.")
    return user
