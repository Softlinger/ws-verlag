from dataclasses import dataclass
from decimal import Decimal

from app.services.tax import calculate_totals


@dataclass
class FakeItem:
    quantity: Decimal
    unit_price: Decimal
    vat_rate: int

    @property
    def net_total(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))


def test_normal_vat_20_percent():
    items = [FakeItem(Decimal("1"), Decimal("100.00"), 20)]
    totals = calculate_totals(items)
    assert totals.net_total == Decimal("100.00")
    assert totals.vat_total == Decimal("20.00")
    assert totals.gross_total == Decimal("120.00")


def test_reduced_vat_10_percent():
    items = [FakeItem(Decimal("2"), Decimal("50.00"), 10)]
    totals = calculate_totals(items)
    assert totals.net_total == Decimal("100.00")
    assert totals.vat_total == Decimal("10.00")
    assert totals.gross_total == Decimal("110.00")


def test_mixed_vat_rates():
    items = [FakeItem(Decimal("1"), Decimal("100.00"), 20), FakeItem(Decimal("1"), Decimal("100.00"), 10)]
    totals = calculate_totals(items)
    assert totals.net_total == Decimal("200.00")
    assert totals.vat_total == Decimal("30.00")
    assert totals.gross_total == Decimal("230.00")


def test_reverse_charge_no_vat():
    items = [FakeItem(Decimal("1"), Decimal("100.00"), 20)]
    totals = calculate_totals(items, reverse_charge=True)
    assert totals.net_total == Decimal("100.00")
    assert totals.vat_total == Decimal("0.00")
    assert totals.gross_total == Decimal("100.00")


def test_advertising_tax_increases_vat_base():
    # Netto 100 + 5% Werbesteuer (5.00) = Zwischensumme 105, + 20% USt (21.00) = 126.00
    items = [FakeItem(Decimal("1"), Decimal("100.00"), 20)]
    totals = calculate_totals(items, advertising_tax_applicable=True, advertising_tax_rate=Decimal("5.00"))
    assert totals.net_total == Decimal("100.00")
    assert totals.advertising_tax_amount == Decimal("5.00")
    assert totals.subtotal == Decimal("105.00")
    assert totals.vat_breakdown[20] == Decimal("21.00")
    assert totals.vat_total == Decimal("21.00")
    assert totals.gross_total == Decimal("126.00")


def test_advertising_tax_applies_without_vat_under_reverse_charge():
    items = [FakeItem(Decimal("1"), Decimal("100.00"), 20)]
    totals = calculate_totals(
        items, reverse_charge=True, advertising_tax_applicable=True, advertising_tax_rate=Decimal("5.00")
    )
    assert totals.advertising_tax_amount == Decimal("5.00")
    assert totals.vat_total == Decimal("0.00")
    assert totals.gross_total == Decimal("105.00")


def test_advertising_tax_distributed_proportionally_across_mixed_vat_rates():
    # Netto 100 (20%) + Netto 100 (10%) = 200, + 5% Werbesteuer (10.00) = Zwischensumme 210
    # Werbesteuer wird 50/50 verteilt: je 5.00 zusaetzliche Bemessungsgrundlage je Satz.
    items = [FakeItem(Decimal("1"), Decimal("100.00"), 20), FakeItem(Decimal("1"), Decimal("100.00"), 10)]
    totals = calculate_totals(items, advertising_tax_applicable=True, advertising_tax_rate=Decimal("5.00"))
    assert totals.subtotal == Decimal("210.00")
    assert totals.vat_breakdown[20] == Decimal("21.00")  # (100 + 5) * 20%
    assert totals.vat_breakdown[10] == Decimal("10.50")  # (100 + 5) * 10%
    assert totals.gross_total == Decimal("241.50")
