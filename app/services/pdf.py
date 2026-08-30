"""PDF-Erzeugung fuer Auftrag/Rechnung/Gutschrift nach der 1:1-Layoutvorgabe aus
Belegdefiniation.txt (Koordinaten anhand von vorlage-belege.pdf verifiziert - alle
Positionsangaben sind mm vom LINKEN und OBEREN Blattrand, A4 hochkant).

Mahnungen (render_dunning_pdf) folgen einem eigenen, einfacheren Layout und sind
bewusst NICHT Teil dieser 1:1-Vorlage (siehe Rueckfrage vom 2026-08-30).
"""
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from app.models import Company

styles = getSampleStyleSheet()

PAGE_W, PAGE_H = A4  # A4 hochkant: 210 x 297 mm

# --- Layout-Konstanten (mm vom linken/oberen Blattrand) ---------------------------
PRINT_LEFT = 23
PRINT_RIGHT = 187  # 210 - 23, symmetrischer Rand

LOGO_X, LOGO_Y_TOP, LOGO_W, LOGO_H = 110, 35, 90, 50

ADDR_X, ADDR_Y_TOP, ADDR_SIZE = 23, 58, 14
ADDR_LEADING = 5.6

DATE_X, DATE_Y_TOP, DATE_SIZE = 160, 128, 12

TITLE_X, TITLE_Y_TOP, TITLE_SIZE = 23, 155, 16

ITEMS_QTY_X = 23
ITEMS_DESC_X = 46
ITEMS_PRICE_RIGHT_X = 160
ITEMS_Y_TOP, ITEMS_SIZE, ITEMS_LEADING = 175, 16, 6.3

TAX_SIZE, TAX_LEADING = 14, 5.6

RC_TEXT_Y_TOP, RC_TEXT_SIZE = 243, 14
TERMS_Y_TOP, TERMS_SIZE = 253, 14
BANK_Y_TOP, BANK_SIZE, BANK_LEADING = 273, 10, 4.2


_TYPOGRAPHIC_REPLACEMENTS = {
    "–": "-",  # Halbgeviertstrich (en dash)
    "—": "-",  # Geviertstrich (em dash)
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
}


def _safe_text(text: str) -> str:
    """Ersetzt typografische Sonderzeichen, die von den Standard-Helvetica-Schriften
    von reportlab nicht zuverlaessig dargestellt werden (z. B. Gedankenstrich), durch
    ASCII-Entsprechungen. Umlaute/ß bleiben unveraendert (werden korrekt dargestellt)."""
    for search, replacement in _TYPOGRAPHIC_REPLACEMENTS.items():
        text = text.replace(search, replacement)
    return text


def _y(top_mm: float) -> float:
    """Wandelt eine mm-Angabe vom oberen Blattrand in eine reportlab-Y-Koordinate
    (Ursprung unten links) um."""
    return (PAGE_H / mm - top_mm) * mm


def _draw_logo(c: canvas.Canvas, company: Company) -> None:
    if not company.logo_path:
        return
    logo_file = Path("app/static") / company.logo_path
    if not logo_file.exists():
        return
    c.drawImage(
        str(logo_file),
        LOGO_X * mm,
        _y(LOGO_Y_TOP + LOGO_H),
        width=LOGO_W * mm,
        height=LOGO_H * mm,
        preserveAspectRatio=True,
        mask="auto",
    )


def _draw_customer_address(c: canvas.Canvas, customer) -> None:
    c.setFont("Helvetica-Bold", ADDR_SIZE)
    lines = [customer.name, customer.street]
    if getattr(customer, "street2", ""):
        lines.append(customer.street2)
    lines.append(f"{customer.postal_code} {customer.city}".strip())
    if customer.country:
        lines.append(customer.country)
    if customer.uid_number:
        lines.append("")
        lines.append(f"UID: {customer.uid_number}")

    y = _y(ADDR_Y_TOP)
    for line in lines:
        if line:
            c.drawString(ADDR_X * mm, y, _safe_text(line))
        y -= ADDR_LEADING * mm


def _draw_date(c: canvas.Canvas, beleg_date: date) -> None:
    c.setFont("Helvetica", DATE_SIZE)
    c.drawString(DATE_X * mm, _y(DATE_Y_TOP), beleg_date.strftime("%d.%m.%Y"))


def _draw_title(c: canvas.Canvas, title: str) -> None:
    c.setFont("Helvetica-Bold", TITLE_SIZE)
    c.drawString(TITLE_X * mm, _y(TITLE_Y_TOP), _safe_text(title))


def _draw_items(c: canvas.Canvas, items, *, reverse_charge: bool) -> float:
    """Zeichnet die Positionen und gibt die naechste freie Y-Position (mm vom oberen
    Rand) zurueck, an der die Trennlinie/Steuerzeilen weitergehen."""
    c.setFont("Helvetica-Bold", ITEMS_SIZE)
    y_top = ITEMS_Y_TOP
    y = _y(y_top)

    for item in items:
        description_lines = str(item.description).split("\n")
        c.drawString(ITEMS_QTY_X * mm, y, str(item.quantity))
        c.drawString(ITEMS_DESC_X * mm, y, _safe_text(description_lines[0]))
        c.drawRightString(ITEMS_PRICE_RIGHT_X * mm, y, f"€ {item.unit_price:.2f}")
        y_top += ITEMS_LEADING
        y = _y(y_top)
        for extra_line in description_lines[1:]:
            c.drawString(ITEMS_DESC_X * mm, y, _safe_text(extra_line))
            y_top += ITEMS_LEADING
            y = _y(y_top)
        y_top += ITEMS_LEADING * 0.3  # kleiner Abstand zwischen Positionen
        y = _y(y_top)

    return y_top


def _draw_reverse_charge_text(c: canvas.Canvas) -> None:
    c.setFont("Helvetica-Bold", RC_TEXT_SIZE)
    lines = [
        "Ausländische Dienstleistung daher MwSt. frei.",
        "Die Leistung unterliegt dem Reverse-Charge-System gem. § 19 Abs. 1 USTG 1994",
    ]
    y_top = RC_TEXT_Y_TOP
    for line in lines:
        c.drawCentredString(PAGE_W / 2, _y(y_top), line)
        y_top += 5.5


def _draw_payment_terms(c: canvas.Canvas, text: str) -> None:
    if not text:
        return
    c.setFont("Helvetica-Bold", TERMS_SIZE)
    c.drawCentredString(PAGE_W / 2, _y(TERMS_Y_TOP), _safe_text(text))


def _draw_bank_info(c: canvas.Canvas, *, bank_account, company: Company) -> None:
    c.setFont("Helvetica", BANK_SIZE)
    y_top = BANK_Y_TOP
    if bank_account is not None:
        c.drawString(PRINT_LEFT * mm, _y(y_top), _safe_text(bank_account.bank_name))
        y_top += BANK_LEADING
        c.drawString(
            PRINT_LEFT * mm,
            _y(y_top),
            _safe_text(f"IBAN: {bank_account.iban}    BIC: {bank_account.bic}"),
        )
    if company.uid_number:
        c.drawRightString(PRINT_RIGHT * mm, _y(BANK_Y_TOP), company.uid_number)


def _render_beleg_pdf(
    *,
    company: Company,
    title: str,
    beleg_date: date,
    customer,
    items,
    totals,
    reverse_charge: bool,
    advertising_tax_applicable: bool,
    advertising_tax_rate: Decimal,
    payment_terms_text: str,
    bank_account,
) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    _draw_logo(c, company)
    _draw_customer_address(c, customer)
    _draw_date(c, beleg_date)
    _draw_title(c, title)

    next_y_top = _draw_items(c, items, reverse_charge=reverse_charge)
    _draw_tax_block(
        c,
        y_top=next_y_top,
        totals=totals,
        reverse_charge=reverse_charge,
        advertising_tax_applicable=advertising_tax_applicable,
        advertising_tax_rate=advertising_tax_rate,
    )

    if reverse_charge:
        _draw_reverse_charge_text(c)
    _draw_payment_terms(c, payment_terms_text)
    _draw_bank_info(c, bank_account=bank_account, company=company)

    c.showPage()
    c.save()
    return buffer.getvalue()


def _draw_tax_block(
    c: canvas.Canvas, *, y_top: float, totals, reverse_charge: bool, advertising_tax_applicable: bool, advertising_tax_rate: Decimal
) -> None:
    y = _y(y_top)
    c.line(PRINT_LEFT * mm, y + 2 * mm, PRINT_RIGHT * mm, y + 2 * mm)
    y_top += TAX_LEADING * 0.8

    c.setFont("Helvetica", TAX_SIZE)
    if advertising_tax_applicable:
        y = _y(y_top)
        c.drawString(ITEMS_DESC_X * mm, y, f"+{advertising_tax_rate}% Werbesteuer")
        c.drawRightString(ITEMS_PRICE_RIGHT_X * mm, y, f"€ {totals.advertising_tax_amount:.2f}")
        y_top += TAX_LEADING

    if not reverse_charge:
        for rate, amount in totals.vat_breakdown.items():
            y = _y(y_top)
            c.drawString(ITEMS_DESC_X * mm, y, f"+{rate}% MwSt.")
            c.drawRightString(ITEMS_PRICE_RIGHT_X * mm, y, f"€ {amount:.2f}")
            y_top += TAX_LEADING

    y = _y(y_top)
    c.line(PRINT_LEFT * mm, y + 2 * mm, PRINT_RIGHT * mm, y + 2 * mm)
    y_top += TAX_LEADING

    c.setFont("Helvetica-Bold", 16)
    y = _y(y_top)
    c.drawString(ITEMS_DESC_X * mm, y, "Gesamtbetrag")
    c.drawRightString(ITEMS_PRICE_RIGHT_X * mm, y, f"€ {totals.gross_total:.2f}")


def render_invoice_pdf(*, company: Company, invoice, customer, items, totals) -> bytes:
    return _render_beleg_pdf(
        company=company,
        title=f"Rechnung Nr. {invoice.number}",
        beleg_date=invoice.invoice_date,
        customer=customer,
        items=items,
        totals=totals,
        reverse_charge=invoice.reverse_charge,
        advertising_tax_applicable=invoice.advertising_tax_applicable,
        advertising_tax_rate=invoice.advertising_tax_rate,
        payment_terms_text=customer.payment_term.printed_text if customer.payment_term else "",
        bank_account=invoice.bank_account,
    )


def render_order_pdf(*, company: Company, order, customer, items, totals) -> bytes:
    return _render_beleg_pdf(
        company=company,
        title=f"Auftragsbestätigung Nr. {order.number}",
        beleg_date=order.order_date,
        customer=customer,
        items=items,
        totals=totals,
        reverse_charge=customer.reverse_charge_applicable,
        advertising_tax_applicable=order.advertising_tax_applicable,
        advertising_tax_rate=company.advertising_tax_rate,
        payment_terms_text=customer.payment_term.printed_text if customer.payment_term else "",
        bank_account=customer.bank_account,
    )


def render_credit_note_pdf(*, company: Company, credit_note, customer, items, totals) -> bytes:
    return _render_beleg_pdf(
        company=company,
        title=f"Gutschrift Nr. {credit_note.number}",
        beleg_date=credit_note.credit_note_date,
        customer=customer,
        items=items,
        totals=totals,
        reverse_charge=customer.reverse_charge_applicable,
        advertising_tax_applicable=False,
        advertising_tax_rate=company.advertising_tax_rate,
        payment_terms_text="",
        bank_account=credit_note.invoice.bank_account if credit_note.invoice else customer.bank_account,
    )


def render_dunning_pdf(*, company: Company, dunning, invoice, customer) -> bytes:
    """Eigenes, einfacheres Layout fuer Mahnungen (bewusst nicht Teil der 1:1-Vorlage)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = [
        Paragraph(f"<b>{company.name}</b>", styles["Heading2"]),
        Paragraph(
            f"{company.street}, {company.postal_code} {company.city}, {company.country}",
            styles["Normal"],
        ),
    ]
    if company.uid_number:
        elements.append(Paragraph(f"UID: {company.uid_number}", styles["Normal"]))
    elements.append(Spacer(1, 8 * mm))
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
