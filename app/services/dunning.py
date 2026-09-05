from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import DunningLevelSetting, Invoice
from app.times import today_vienna


class _SafeDict(dict):
    """Gibt fuer unbekannte Platzhalter leer zurueck statt KeyError -> ein von Admins
    frei editierbarer Mahntext mit Tippfehler-{platzhalter} laess eine 500, sonst crasht
    das Erstellen/Versenden der Mahnung."""

    def __missing__(self, key):  # noqa: ANN001
        return ""


def render_dunning_text(level_setting: DunningLevelSetting, invoice: Invoice, open_amount) -> str:
    ctx = _SafeDict(
        kunde=invoice.customer.name,
        rechnungsnummer=invoice.number,
        rechnungsdatum=invoice.invoice_date.strftime("%d.%m.%Y"),
        betrag=f"{open_amount:.2f}",
        mahnstufe=str(level_setting.level),
        gebuehr=f"{level_setting.fee_amount:.2f}",
        faelligkeitsdatum=(today_vienna() + timedelta(days=level_setting.due_days)).strftime("%d.%m.%Y"),
    )
    # str.format_map mit _SafeDict statt .format(): unbekannte Schlussel -> leer.
    return level_setting.text_template.format_map(ctx)


def next_dunning_level(invoice: Invoice) -> int:
    """Naechste Mahnstufe (1-3) basierend auf bereits ausgestellten Mahnungen zur Rechnung."""
    existing_levels = {d.level for d in invoice.dunnings}
    for level in (1, 2, 3):
        if level not in existing_levels:
            return level
    return 3


def get_level_setting(db: Session, level: int) -> DunningLevelSetting:
    setting = db.query(DunningLevelSetting).filter(DunningLevelSetting.level == level).one_or_none()
    if setting is None:
        setting = DunningLevelSetting(level=level)
        db.add(setting)
        db.flush()
    return setting
