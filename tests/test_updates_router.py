from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import UpdateApplyStatus
from app.routers.updates import report_result
from app.services.update_check import get_or_create_update_state


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_successful_report_clears_the_now_outdated_update_card():
    """Regression: nach einem erfolgreich installierten Update lief die soeben
    installierte Version noch bis zur naechsten planmaessigen Pruefung (Standard:
    24h) als 'verfuegbares Update' weiter, statt sofort zu verschwinden."""
    db = make_session()
    state = get_or_create_update_state(db)
    state.latest_version = "0.3.1"
    state.changelog = "- Testeintrag"
    state.release_date = "2026-09-04"
    state.image_ref = "ghcr.io/softlinger/ws-verlag"
    state.image_digest = "sha256:aa"
    db.commit()

    report_result({"status": "erfolgreich", "message": "ok"}, db)

    assert state.apply_status == UpdateApplyStatus.ERFOLGREICH
    assert state.latest_version == ""
    assert state.changelog == ""
    assert state.release_date == ""
    assert state.image_ref == ""
    assert state.image_digest == ""


def test_failed_report_keeps_the_update_card_for_a_retry():
    db = make_session()
    state = get_or_create_update_state(db)
    state.latest_version = "0.3.1"
    state.image_ref = "ghcr.io/softlinger/ws-verlag"
    state.image_digest = "sha256:aa"
    db.commit()

    report_result({"status": "fehlgeschlagen", "message": "Pull fehlgeschlagen"}, db)

    assert state.apply_status == UpdateApplyStatus.FEHLGESCHLAGEN
    assert state.latest_version == "0.3.1"
    assert state.image_digest == "sha256:aa"
