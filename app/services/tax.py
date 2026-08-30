from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, NamedTuple, Protocol


class HasNetTotal(Protocol):
    vat_rate: int

    @property
    def net_total(self) -> Decimal: ...


class TaxTotals(NamedTuple):
    net_total: Decimal
    advertising_tax_amount: Decimal
    subtotal: Decimal  # Netto + Werbesteuer, Bemessungsgrundlage fuer die USt.
    vat_total: Decimal
    gross_total: Decimal
    vat_breakdown: dict[int, Decimal]  # USt.-Satz -> Steuerbetrag


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_totals(
    items: Iterable[HasNetTotal],
    *,
    reverse_charge: bool = False,
    advertising_tax_applicable: bool = False,
    advertising_tax_rate: Decimal = Decimal("5.00"),
) -> TaxTotals:
    """Berechnet Netto-, Werbesteuer-, USt- und Bruttosumme.

    Berechnungsreihenfolge (fachlich vorgegeben):
        Nettobetrag + 5% Werbesteuer = Zwischensumme
        Zwischensumme + USt (10%/20%) = Gesamtbetrag

    Die Werbesteuer erhoeht also die Bemessungsgrundlage der USt., statt nur auf den
    Nettobetrag oben aufgeschlagen zu werden. Bei mehreren USt.-Saetzen auf einem Beleg
    wird die Werbesteuer proportional zum Nettoanteil jedes Satzes verteilt, damit die
    Summe der satzweisen Berechnung exakt der pauschalen Berechnung entspricht.

    Reverse-Charge (auslaendischer EU-Kunde mit UID): 0% USt, Steuerschuld geht auf den
    Leistungsempfaenger ueber - es wird keine USt ausgewiesen, die Werbesteuer bleibt
    davon unberuehrt.
    """
    net_by_rate: dict[int, Decimal] = {}
    net_total = Decimal("0.00")

    for item in items:
        item_net = item.net_total
        net_total += item_net
        net_by_rate[item.vat_rate] = net_by_rate.get(item.vat_rate, Decimal("0.00")) + item_net

    net_total = _round(net_total)

    advertising_tax_amount = Decimal("0.00")
    if advertising_tax_applicable:
        advertising_tax_amount = _round(net_total * advertising_tax_rate / Decimal("100"))

    subtotal = _round(net_total + advertising_tax_amount)

    vat_breakdown: dict[int, Decimal] = {}
    if not reverse_charge:
        for rate, rate_net in net_by_rate.items():
            # Anteiliger Werbesteuer-Anteil dieses USt.-Satzes an der Bemessungsgrundlage.
            share = (rate_net / net_total) if net_total else Decimal("0")
            rate_base = _round(rate_net + advertising_tax_amount * share)
            vat_breakdown[rate] = _round(rate_base * Decimal(rate) / Decimal("100"))

    vat_total = _round(sum(vat_breakdown.values(), Decimal("0.00")))
    gross_total = _round(subtotal + vat_total)

    return TaxTotals(
        net_total=net_total,
        advertising_tax_amount=advertising_tax_amount,
        subtotal=subtotal,
        vat_total=vat_total,
        gross_total=gross_total,
        vat_breakdown=vat_breakdown,
    )
