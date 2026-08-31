from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
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
