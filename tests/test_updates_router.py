from types import SimpleNamespace

from app.models import UpdateApplyStatus
from app.routers.updates import report_result
from app.services.update_check import get_or_create_update_state
from tests._db import make_session


def _req():
    # report_result prueft den Header nur, wenn settings.updater_token gesetzt ist
    # (in Tests leer -> uebersprungen). Ein leeres headers-Dict genuegt.
    return SimpleNamespace(headers={})


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

    report_result(_req(), {"status": "erfolgreich", "message": "ok"}, db)

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

    report_result(_req(), {"status": "fehlgeschlagen", "message": "Pull fehlgeschlagen"}, db)

    assert state.apply_status == UpdateApplyStatus.FEHLGESCHLAGEN
    assert state.latest_version == "0.3.1"
    assert state.image_digest == "sha256:aa"
