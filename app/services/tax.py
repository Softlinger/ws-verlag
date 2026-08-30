from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, NamedTuple, Protocol


class HasNetTotal(Protocol):
    vat_rate: int

    @property
    def net_total(self) -> Decimal: ...


class TaxTotals(NamedTuple):
    net_total: Decimal
    vat_total: Decimal
    gross_total: Decimal
    vat_breakdown: dict[int | str, Decimal]  # Satz (10/20) oder "werbesteuer" -> Steuerbetrag


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_totals(
    items: Iterable[HasNetTotal],
    *,
    reverse_charge: bool = False,
    advertising_tax_applicable: bool = False,
    advertising_tax_rate: Decimal = Decimal("5.00"),
) -> TaxTotals:
    """Berechnet Netto-, USt- und Bruttosumme.

    Reverse-Charge (auslaendischer EU-Kunde mit UID): 0% USt, Steuerschuld geht auf den
    Leistungsempfaenger ueber - es wird keine USt ausgewiesen.
    Werbesteuer (5%) wird pauschal auf den Nettobetrag des gesamten Belegs aufgeschlagen,
    sofern zugeordnet, und getrennt von der USt ausgewiesen.
    """
    net_total = Decimal("0.00")
    vat_breakdown: dict[int | str, Decimal] = {}

    for item in items:
        item_net = item.net_total
        net_total += item_net
        if not reverse_charge:
            rate = item.vat_rate
            vat_amount = _round(item_net * Decimal(rate) / Decimal("100"))
            vat_breakdown[rate] = vat_breakdown.get(rate, Decimal("0.00")) + vat_amount

    net_total = _round(net_total)
    vat_total = _round(sum(vat_breakdown.values(), Decimal("0.00")))

    advertising_tax_amount = Decimal("0.00")
    if advertising_tax_applicable:
        advertising_tax_amount = _round(net_total * advertising_tax_rate / Decimal("100"))
        vat_breakdown["werbesteuer"] = advertising_tax_amount  # type: ignore[index]

    gross_total = _round(net_total + vat_total + advertising_tax_amount)

    return TaxTotals(
        net_total=net_total,
        vat_total=vat_total,
        gross_total=gross_total,
        vat_breakdown=vat_breakdown,
    )
