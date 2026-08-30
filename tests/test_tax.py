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


def test_advertising_tax_applied_on_net_total():
    items = [FakeItem(Decimal("1"), Decimal("100.00"), 20)]
    totals = calculate_totals(items, advertising_tax_applicable=True, advertising_tax_rate=Decimal("5.00"))
    assert totals.net_total == Decimal("100.00")
    assert totals.vat_total == Decimal("20.00")
    assert totals.vat_breakdown["werbesteuer"] == Decimal("5.00")
    assert totals.gross_total == Decimal("125.00")


def test_advertising_tax_ignored_with_reverse_charge_vat_but_still_applied():
    items = [FakeItem(Decimal("1"), Decimal("100.00"), 20)]
    totals = calculate_totals(
        items, reverse_charge=True, advertising_tax_applicable=True, advertising_tax_rate=Decimal("5.00")
    )
    assert totals.vat_total == Decimal("0.00")
    assert totals.vat_breakdown["werbesteuer"] == Decimal("5.00")
    assert totals.gross_total == Decimal("105.00")
