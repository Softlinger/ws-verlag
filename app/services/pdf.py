from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

from app.models import Company

styles = getSampleStyleSheet()


def _company_header(company: Company) -> list:
    elements = [
        Paragraph(f"<b>{company.name}</b>", styles["Heading2"]),
        Paragraph(
            f"{company.street}, {company.postal_code} {company.city}, {company.country}",
            styles["Normal"],
        ),
    ]
    if company.uid_number:
        elements.append(Paragraph(f"UID: {company.uid_number}", styles["Normal"]))
    if company.phone or company.email:
        elements.append(Paragraph(f"{company.phone} | {company.email}", styles["Normal"]))
    elements.append(Spacer(1, 8 * mm))
    return elements


def render_invoice_pdf(*, company: Company, invoice, customer, items, totals) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = _company_header(company)

    title = "RECHNUNG"
    elements.append(Paragraph(f"<b>{title} {invoice.number}</b>", styles["Heading1"]))
    elements.append(Paragraph(f"Rechnungsdatum: {invoice.invoice_date.strftime('%d.%m.%Y')}", styles["Normal"]))
    elements.append(Paragraph(f"Faellig am: {invoice.due_date.strftime('%d.%m.%Y')}", styles["Normal"]))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(f"<b>{customer.name}</b>", styles["Normal"]))
    elements.append(Paragraph(f"{customer.street}, {customer.postal_code} {customer.city}", styles["Normal"]))
    if customer.uid_number:
        elements.append(Paragraph(f"UID: {customer.uid_number}", styles["Normal"]))
    elements.append(Spacer(1, 6 * mm))

    table_data = [["Bezeichnung", "Menge", "Einzelpreis", "USt%", "Gesamt"]]
    for item in items:
        table_data.append(
            [
                item.description,
                str(item.quantity),
                f"{item.unit_price:.2f}",
                "RC" if invoice.reverse_charge else f"{item.vat_rate}%",
                f"{item.net_total:.2f}",
            ]
        )
    table = Table(table_data, colWidths=[70 * mm, 20 * mm, 30 * mm, 20 * mm, 30 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f3e46")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))

    summary_rows = [["Nettosumme", f"{totals.net_total:.2f} EUR"]]
    if invoice.reverse_charge:
        summary_rows.append(["USt", "Reverse-Charge-Verfahren, Steuerschuld beim Leistungsempfaenger"])
    else:
        for rate, amount in totals.vat_breakdown.items():
            if rate == "werbesteuer":
                continue
            summary_rows.append([f"USt {rate}%", f"{amount:.2f} EUR"])
    if invoice.advertising_tax_applicable:
        werbesteuer = totals.vat_breakdown.get("werbesteuer", Decimal("0.00"))
        summary_rows.append([f"Werbesteuer {invoice.advertising_tax_rate}%", f"{werbesteuer:.2f} EUR"])
    summary_rows.append(["Gesamtbetrag", f"{totals.gross_total:.2f} EUR"])

    summary_table = Table(summary_rows, colWidths=[100 * mm, 50 * mm])
    summary_table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
    elements.append(summary_table)

    if invoice.reverse_charge:
        elements.append(Spacer(1, 6 * mm))
        elements.append(
            Paragraph(
                "Steuerfreie innergemeinschaftliche Leistung - Reverse-Charge-Verfahren gemaess Art. 196 MwStSystRL "
                "bzw. § 19 Abs. 1 UStG. Die Steuerschuld geht auf den Leistungsempfaenger ueber.",
                styles["Italic"],
            )
        )

    doc.build(elements)
    return buffer.getvalue()


def render_credit_note_pdf(*, company: Company, credit_note, customer, items, totals) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = _company_header(company)
    elements.append(Paragraph(f"<b>GUTSCHRIFT {credit_note.number}</b>", styles["Heading1"]))
    elements.append(
        Paragraph(f"Datum: {credit_note.credit_note_date.strftime('%d.%m.%Y')}", styles["Normal"])
    )
    elements.append(Paragraph(f"Bezug: Rechnung {credit_note.invoice.number}", styles["Normal"]))
    if credit_note.reason:
        elements.append(Paragraph(f"Grund: {credit_note.reason}", styles["Normal"]))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(f"<b>{customer.name}</b>", styles["Normal"]))
    elements.append(Paragraph(f"{customer.street}, {customer.postal_code} {customer.city}", styles["Normal"]))
    elements.append(Spacer(1, 6 * mm))

    table_data = [["Bezeichnung", "Menge", "Einzelpreis", "USt%", "Gesamt"]]
    for item in items:
        table_data.append(
            [item.description, str(item.quantity), f"{item.unit_price:.2f}", f"{item.vat_rate}%", f"{item.net_total:.2f}"]
        )
    table = Table(table_data, colWidths=[70 * mm, 20 * mm, 30 * mm, 20 * mm, 30 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f3e46")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(f"<b>Gesamtbetrag: {totals.gross_total:.2f} EUR</b>", styles["Normal"]))

    doc.build(elements)
    return buffer.getvalue()


def render_dunning_pdf(*, company: Company, dunning, invoice, customer) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = _company_header(company)
    elements.append(Paragraph(f"<b>{dunning.level}. MAHNUNG</b>", styles["Heading1"]))
    elements.append(Paragraph(f"Datum: {dunning.created_at.strftime('%d.%m.%Y')}", styles["Normal"]))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(f"<b>{customer.name}</b>", styles["Normal"]))
    elements.append(Paragraph(f"{customer.street}, {customer.postal_code} {customer.city}", styles["Normal"]))
    elements.append(Spacer(1, 6 * mm))
    for paragraph in dunning.rendered_text.split("\n"):
        elements.append(Paragraph(paragraph or "&nbsp;", styles["Normal"]))
    if dunning.fee_amount:
        elements.append(Spacer(1, 6 * mm))
        elements.append(Paragraph(f"Mahngebuehr: {dunning.fee_amount:.2f} EUR", styles["Normal"]))

    doc.build(elements)
    return buffer.getvalue()
