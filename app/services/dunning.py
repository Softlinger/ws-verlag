from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import DunningLevelSetting, Invoice


def render_dunning_text(level_setting: DunningLevelSetting, invoice: Invoice, open_amount) -> str:
    return level_setting.text_template.format(
        kunde=invoice.customer.name,
        rechnungsnummer=invoice.number,
        rechnungsdatum=invoice.invoice_date.strftime("%d.%m.%Y"),
        betrag=f"{open_amount:.2f}",
        faelligkeitsdatum=(date.today() + timedelta(days=level_setting.due_days)).strftime("%d.%m.%Y"),
    )


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
