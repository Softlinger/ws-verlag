"""Anzeigeformat fuer Geldbetraege (oesterreichisch): Tausenderpunkt, Dezimalkomma.

Nur fuer Druck/Anzeige - CSV-Exporte bleiben bewusst maschinenlesbar (1234.56)."""


def format_amount(amount) -> str:
    """1234.5 -> '1.234,50'."""
    return f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
