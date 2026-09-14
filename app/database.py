import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings

# Nur MariaDB/MySQL (siehe app/config.py - SQLite wird nicht mehr unterstuetzt).
# pool_pre_ping haendelt vom Server geschlossene Verbindungen; pool_recycle holt
# Verbindungen regelmaessig zurueck, bevor MariaDBs wait_timeout sie beendet.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Additive Mini-Migration fuer bereits bestehende Datenbanken: Base.metadata.create_all()
# legt fehlende TABELLEN an, aendert aber niemals bestehende Tabellen. Neue Spalten an
# bereits vorhandenen Tabellen muessen deshalb hier nachgezogen werden, damit produktive
# Installationen (mit echten Kundendaten) nicht auf ein manuelles Alembic-Setup angewiesen
# sind. Nur additiv (ADD COLUMN) - fuer Umbenennungen/Loeschungen ist Alembic vorgesehen.
_NEW_COLUMNS: list[tuple[str, str, str]] = [
    ("customers", "street2", "VARCHAR(255) DEFAULT ''"),
    ("company", "logo_path", "VARCHAR(255) DEFAULT ''"),
    ("payment_terms", "printed_text", "VARCHAR(255) DEFAULT 'Zahlbar nach Erhalt, ohne Abzug.'"),
    ("company", "smtp_encryption", "VARCHAR(16) DEFAULT 'starttls'"),
    ("users", "password_version", "INTEGER NOT NULL DEFAULT 0"),
    ("customers", "name2", "VARCHAR(255) DEFAULT ''"),
]


def ensure_new_columns() -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl_type in _NEW_COLUMNS:
            if table not in inspector.get_table_names():
                continue  # Tabelle wird ohnehin frisch per create_all() mit der Spalte angelegt.
            existing_columns = {col["name"] for col in inspector.get_columns(table)}
            if column in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


# Einmalige Constraint-Nachziehen auf BESTEHENDEN Tabellen: create_all()/ADD COLUMN
# erzeugt KEINE neuen Unique-Constraints auf bereits existierenden Tabellen. Neue
# hier eintragen (idempotent; scheitert tolerant, falls Daten dagegen sprechen).
_NEW_UNIQUE_CONSTRAINTS: list[tuple[str, str, tuple[str, ...]]] = [
    ("dunnings", "uq_dunning_invoice_level", ("invoice_id", "level")),
]


def ensure_new_constraints() -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    for table, name, columns in _NEW_UNIQUE_CONSTRAINTS:
        if table not in tables:
            continue  # frisch per create_all() mit Constraint angelegt.
        existing = {c.get("name") for c in inspector.get_unique_constraints(table)}
        if name in existing:
            continue
        cols = ", ".join(columns)
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE ({cols})"))
        except Exception as exc:  # noqa: BLE001 - Bestandsdaten mit Duplikaten o. a.
            logging.getLogger(__name__).warning(
                "Konnte Unique-Constraint %s auf %s nicht nachziehen (evtl. Duplikate "
                "in Bestandsdaten, manuell bereinigen): %s",
                name,
                table,
                exc,
            )
