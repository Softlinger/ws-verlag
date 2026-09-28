"""Setzt das Passwort eines Benutzers zurueck (Notfall, z. B. Admin-Passwort vergessen).

Aufruf im laufenden App-Container (interaktiv, Passwort wird verdeckt abgefragt):
    docker exec -it ws-verlag-app python scripts/reset_password.py admin

Aktiviert den Benutzer wieder und entwertet alle bestehenden Sessions
(password_version wird erhoeht) - wie beim Passwortwechsel in der Benutzerverwaltung.
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password
from app.database import SessionLocal
from app.models import User

MIN_LENGTH = 8  # wie in app/routers/users.py


def main() -> int:
    if len(sys.argv) != 2:
        print("Aufruf: python scripts/reset_password.py <benutzername>")
        return 2
    username = sys.argv[1]

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).one_or_none()
        if user is None:
            print(f"Benutzer '{username}' existiert nicht.")
            return 1

        password = getpass.getpass("Neues Passwort: ")
        if len(password) < MIN_LENGTH:
            print(f"Passwort zu kurz (mindestens {MIN_LENGTH} Zeichen).")
            return 1
        if getpass.getpass("Passwort wiederholen: ") != password:
            print("Passwoerter stimmen nicht ueberein.")
            return 1

        user.password_hash = hash_password(password)
        user.active = True
        user.password_version = (user.password_version or 0) + 1
        db.commit()
        print(f"Passwort fuer '{username}' wurde gesetzt.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
