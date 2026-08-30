from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import DocumentType, NumberRange
from app.services.numbering import generate_next_number


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_generates_sequential_numbers_with_prefix_and_padding():
    db = make_session()
    db.add(NumberRange(document_type=DocumentType.RECHNUNG, prefix="R-", start_number=1, digits=4))
    db.commit()

    assert generate_next_number(db, DocumentType.RECHNUNG) == "R-0001"
    assert generate_next_number(db, DocumentType.RECHNUNG) == "R-0002"
    assert generate_next_number(db, DocumentType.RECHNUNG) == "R-0003"


def test_respects_custom_start_number():
    db = make_session()
    db.add(NumberRange(document_type=DocumentType.AUFTRAG, prefix="A-", start_number=1000, digits=4))
    db.commit()

    assert generate_next_number(db, DocumentType.AUFTRAG) == "A-1000"
    assert generate_next_number(db, DocumentType.AUFTRAG) == "A-1001"


def test_creates_range_on_demand_when_missing():
    db = make_session()
    number = generate_next_number(db, DocumentType.GUTSCHRIFT)
    assert number == "0001"


def test_applies_suffix():
    db = make_session()
    db.add(NumberRange(document_type=DocumentType.RECHNUNG, prefix="", suffix="/2026", start_number=1, digits=3))
    db.commit()
    assert generate_next_number(db, DocumentType.RECHNUNG) == "001/2026"
