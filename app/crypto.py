"""Verschluesselung vertraulicher Felder at-rest (z. B. SMTP-Passwort in den
Firmenstammdaten). DSGVO: Zugangsdaten nicht in Klartext in der Datenbank.

Der Schluessel wird deterministisch aus settings.secret_key abgeleitet (SHA-256 ->
Fernet-Key).Rotation von SECRET_KEY macht bereits verschluesselte Werte unlesbar -
deshalb SECRET_KEY stabil halten. decrypt_secret() faellt auf den Rohwert zurueck,
damit vor der Einfuehrung gespeicherte Klartext-Passwoerter weiter funktionieren und
beim naechsten Speichern automatisch verschluesselt werden.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        # Nicht entschluesselbar -> wahrscheinlich legacy-Klartext.
        return token
