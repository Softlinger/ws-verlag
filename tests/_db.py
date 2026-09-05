"""MariaDB-Testdatenbank-Helper.

Stellt make_session() bereit und ersetzt das fruehere `sqlite:///:memory:`. Alle Tests
teilen sich eine Test-DB (TEST_DATABASE_URL); make_session() setzt das Schema pro Aufruf
zurueck. Wichtig: die jeweils VORHERIGE Session wird geschlossen, bevor dropped/angelegt
wird - sonst wartet das DDL (drop_all) auf einem Meta-Lock der noch offenen Transaktion
des vorherigen Tests und die Suite haengt. Ist keine erreichbare MariaDB konfiguriert,
werden abhaengige Tests sauber skipped statt rot.
"""
import os

import pytest
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.database import Base

_TEST_URL = os.environ["TEST_DATABASE_URL"]
_engine = None
_last: tuple | None = None  # (session, engine) des zuletzt ausgegebenen make_session()
_db_ready = False


def _server_url() -> URL:
    """TEST_DATABASE_URL ohne Datenbankanteil - fuer CREATE DATABASE IF NOT EXISTS."""
    url = make_url(_TEST_URL)
    if not url.database:
        raise RuntimeError("TEST_DATABASE_URL muss einen Datenbanknamen enthalten")
    return URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        query=url.query,
    )


def _ensure_database():
    global _db_ready
    if _db_ready:
        return
    db_name = make_url(_TEST_URL).database
    srv = create_engine(_server_url(), poolclass=NullPool, future=True)
    try:
        with srv.begin() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4"))
        _db_ready = True
    except Exception as exc:
        pytest.skip(
            "MariaDB-Testinstanz nicht erreichbar "
            f"(TEST_DATABASE_URL={_TEST_URL!r}): {exc}. "
            "z. B. `docker run -d -p 3307:3306 -e MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1 "
            "mariadb:11` starten oder TEST_DATABASE_URL setzen."
        )
    finally:
        srv.dispose()


def make_session():
    global _engine, _last
    _ensure_database()

    # Vorgaenger-Session schliessen, damit ihr Lock das folgende DDL nicht blockiert.
    if _last is not None:
        prev_session, prev_engine = _last
        prev_session.close()
        if prev_engine is not _engine:
            prev_engine.dispose()
        _last = None

    if _engine is None:
        _engine = create_engine(_TEST_URL, poolclass=NullPool, future=True)

    # Schema zuruecksetzen (frischer Stand je Test wie frueher bei :memory:).
    with _engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    with _engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))

    session = sessionmaker(bind=_engine)()
    _last = (session, _engine)
    return session


def final_teardown() -> None:
    """Von conftest am Suite-Ende aufgerufen: letzte Session + Engine freigeben."""
    global _engine, _last
    if _last is not None:
        _last[0].close()
        _last = None
    if _engine is not None:
        _engine.dispose()
        _engine = None
