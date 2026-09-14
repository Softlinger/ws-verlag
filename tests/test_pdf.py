from datetime import date
from decimal import Decimal

from app.models import Company, Customer, Invoice, InvoiceItem
from app.services.pdf import render_invoice_pdf
from app.services.tax import calculate_totals
from tests._db import make_session


def test_render_invoice_pdf_produces_valid_pdf_bytes():
    db = make_session()
    company = Company(name="WS-Verlag GmbH", street="Musterstr. 1", postal_code="1010", city="Wien")
    db.add(company)
    customer = Customer(name="Muster GmbH", name2="Filiale Wien", street="Kundenweg 2", postal_code="1020", city="Wien")
    db.add(customer)
    db.flush()
    invoice = Invoice(
        number="R-00001",
        customer_id=customer.id,
        invoice_date=date(2026, 1, 10),
        due_date=date(2026, 1, 24),
    )
    db.add(invoice)
    db.flush()
    invoice.items.append(InvoiceItem(description="Anzeige", quantity=Decimal("1"), unit_price=Decimal("100.00"), vat_rate=20))
    db.commit()

    totals = calculate_totals(invoice.items, reverse_charge=False, advertising_tax_applicable=False)
    pdf_bytes = render_invoice_pdf(company=company, invoice=invoice, customer=customer, items=invoice.items, totals=totals)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500
