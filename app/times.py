"""Zeit-/Datums-Helfer in der massgeblichen Betriebszeitzone.

Der Server/Container laeuft moeglicherweise in UTC; fachlich ("Welcher Monat ist
aktuell?", "Ist diese Rechnung ueberfaellig?") zaehlt aber die oesterreichische
Ortszeit. Deshalb stets Europe/Vienna verwenden, damit Monatserste- und
Tagesrand-Faelle (00:00-02:00 Wiener Zeit) nicht im falschen Monat/Tag landen.
"""
from datetime import date, datetime, timezone, tzinfo
from zoneinfo import ZoneInfo

VIENNA: tzinfo = ZoneInfo("Europe/Vienna")


def now_vienna() -> datetime:
    return datetime.now(timezone.utc).astimezone(VIENNA)


def today_vienna() -> date:
    return now_vienna().date()


def utcnow() -> datetime:
    """Naive UTC-Jetzt - Ersatz für das deprecated datetime.utcnow().

    Bleibt bewusst *naive*, weil die DateTime-Spalten der DB naive UTC speichern;
    so bleiben Vergleiche (z. B. Wartungsfenster-Frist) konsistent.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
