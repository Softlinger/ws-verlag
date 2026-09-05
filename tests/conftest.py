"""Shared pytest setup.

Die Unit-Tests laufen gegen eine echte MariaDB (kein SQLite mehr). Diese Datei muss
die Umgebungsvariablen setzen, BEVOR irgendein Testmodul app.config/app.database
importiert - die Konfiguration verlangt zwingend eine MariaDB-DATABASE_URL und würde
sonst (oder wegen eines evtl. in .env hinterlegten SQLite-Werts) beim Import abbrechen.
"""
import os

# Vor jeder App-Import-Zeile ausführen: process-env schlägt in pydantic-settings immer
# .env, d. h. ein dort evtl. stehender SQLite-Wert wird überschrieben.
os.environ.setdefault(
    "TEST_DATABASE_URL",
    "mysql+pymysql://root@127.0.0.1:3306/ws_verlag_test",
)
os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])

# Nicht-Default-Secret, damit der SECRET_KEY-Start-Guard bei einem TestClient-Lauf
# (loest App-Startup aus) nicht abbricht; und kein Hintergrund-Update-Check, der im
# Test gegen das echte Internet gehen wuerde.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-default")
os.environ.setdefault("UPDATE_CHECK_ENABLED", "false")


import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_database():
    """Legt die Testschema vor irgendwelchen Tests an - auch vor Tests, die den
    App-Startup (TestClient) nutzen und deren globaler Engine direkt gegen
    DATABASE_URL verbindet, bevor ein make_session()-Test die DB erzeugen wuerde."""
    from tests._db import _ensure_database

    _ensure_database()


def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001
    # Am Suite-Ende die letzte Test-Session/Engine freigeben (Sessions werden sonst
    # nie geschlossen und koennten Meta-Locks halten).
    try:
        from tests._db import final_teardown

        final_teardown()
    except Exception:  # pragma: no cover - Aufräumen ist Best-Effort
        pass
