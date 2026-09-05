from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DocumentType, NumberRange


def generate_next_number(db: Session, document_type: DocumentType) -> str:
    """Erzeugt die naechste fortlaufende Belegnummer fuer den gegebenen Belegtyp.

    Race-sicher innerhalb einer DB-Transaktion durch SELECT ... FOR UPDATE auf der
    NumberRange-Zeile (MariaDB/MySQL; SQLite wird nicht mehr unterstuetzt). Der
    Zaehler-Bump liegt in derselben Transaktion wie der Beleg-INSERT: schlaegt der
    INSERT fehl, rollt der Bump mit zurueck (Nummer wird wiederverwendet, keine
    Luecke - wie fuer fortlaufende Nummernkreise gefordert).
    """
    range_row = db.execute(
        select(NumberRange).where(NumberRange.document_type == document_type).with_for_update()
    ).scalar_one_or_none()

    if range_row is None:
        range_row = NumberRange(document_type=document_type, current_number=0)
        db.add(range_row)
        db.flush()

    if range_row.current_number < range_row.start_number - 1:
        range_row.current_number = range_row.start_number - 1

    range_row.current_number += 1
    number_part = str(range_row.current_number).zfill(range_row.digits)
    db.flush()
    return f"{range_row.prefix}{number_part}{range_row.suffix}"
