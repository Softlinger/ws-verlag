"""PDF-Erzeugung fuer Auftrag/Rechnung/Gutschrift nach der 1:1-Layoutvorgabe aus
Belegdefiniation.txt (Koordinaten anhand von vorlage-belege.pdf verifiziert - alle
Positionsangaben sind mm vom LINKEN und OBEREN Blattrand, A4 hochkant).

Mahnungen (render_dunning_pdf) folgen einem eigenen, einfacheren Layout und sind
bewusst NICHT Teil dieser 1:1-Vorlage (siehe Rueckfrage vom 2026-08-30).
"""
import html
import re
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.models import Company

styles = getSampleStyleSheet()

PAGE_W, PAGE_H = A4  # A4 hochkant: 210 x 297 mm

# --- Layout-Konstanten (mm vom linken/oberen Blattrand) ---------------------------
PRINT_LEFT = 23
PRINT_RIGHT = 187  # 210 - 23, symmetrischer Rand
ITEMS_LINE_RIGHT_X = PRINT_RIGHT + 10  # Trennlinien der Positionstabelle: 1cm ueber den Druckrand hinaus verlaengert

LOGO_X, LOGO_Y_TOP, LOGO_W, LOGO_H = 110, 35, 90, 50

ADDR_X, ADDR_Y_TOP, ADDR_SIZE = 23, 58, 14
ADDR_LEADING = 5.6

DATE_X, DATE_Y_TOP, DATE_SIZE = 160, 128, 12

TITLE_X, TITLE_Y_TOP, TITLE_SIZE = 23, 145, 16  # 1cm nach oben (vorher 155) - Unwucht durch Leerraum vermindern

ITEMS_QTY_X = 23
ITEMS_QTY_COL_WIDTH = 12  # mm reservierte Breite fuer die (fettgedruckte, 16pt) Mengenangabe, bis zu 4-stellig
ITEMS_QTY_DESC_GAP = 5  # mm Abstand zwischen Mengenspalte und Beschreibung
ITEMS_DESC_X = ITEMS_QTY_X + ITEMS_QTY_COL_WIDTH + ITEMS_QTY_DESC_GAP  # 40
ITEMS_DESC_RIGHT_X = 185  # Bezeichnung-Spalte: 3cm nach rechts erweitert (vorher 155)
ITEMS_PRICE_RIGHT_X = 190  # Preisspalte: 1cm nach links korrigiert (vorher 200)
ITEMS_DESC_GAP = 5  # mm Sicherheitsabstand zwischen umgebrochenem Positionstext und der Preisspalte.
ITEMS_DESC_MAX_WIDTH = (ITEMS_DESC_RIGHT_X - ITEMS_DESC_X - ITEMS_DESC_GAP) * mm
ITEMS_Y_TOP, ITEMS_SIZE, ITEMS_LEADING = 165, 16, 6.3  # 1cm nach oben (vorher 175)

ITEM_DESCRIPTION_STYLE = ParagraphStyle(
    "ItemDescription",
    fontName="Helvetica",
    fontSize=ITEMS_SIZE,
    leading=ITEMS_LEADING * mm,
)

# Erlaubte Steuerzeichen fuer Positionstexte (siehe Hinweistext im Formular):
#   \n            Zeilenumbruch
#   **text**      fett
#   _text_        kursiv
#   [size=N]text[/size]   Schriftgroesse N (Punkt) fuer diesen Textteil
_BOLD_MARKUP_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
_ITALIC_MARKUP_RE = re.compile(r"_(.+?)_", re.S)
_SIZE_MARKUP_RE = re.compile(r"\[size=(\d+(?:\.\d+)?)\](.+?)\[/size\]", re.S)


def _format_item_description(text: str) -> str:
    """Wandelt die Steuerzeichen eines Positionstexts in reportlab-Paragraph-Markup um.
    Der Text wird zuerst XML-escaped, damit vom Benutzer eingegebene < > & keine
    ungueltigen/unerwuenschten Tags erzeugen koennen."""
    escaped = html.escape(_safe_text(str(text)), quote=False)
    escaped = escaped.replace("\n", "<br/>")
    escaped = _BOLD_MARKUP_RE.sub(r"<b>\1</b>", escaped)
    escaped = _ITALIC_MARKUP_RE.sub(r"<i>\1</i>", escaped)
    escaped = _SIZE_MARKUP_RE.sub(r'<font size="\1">\2</font>', escaped)
    return escaped

TAX_SIZE, TAX_LEADING = 14, 5.6

RC_TEXT_Y_TOP, RC_TEXT_SIZE = 243, 14
RC_TEXT_LEADING = 5.5  # mm Zeilenabstand innerhalb des Reverse-Charge-Texts (siehe _draw_reverse_charge_text)
# Der Reverse-Charge-Text hat 2 Zeilen (bei RC_TEXT_Y_TOP und +1*LEADING); +1 weitere Leerzeile
# vor den Zahlungsbedingungen ergibt +3*LEADING ab RC_TEXT_Y_TOP.
TERMS_Y_TOP, TERMS_SIZE = RC_TEXT_Y_TOP + 3 * RC_TEXT_LEADING, 14
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
    y_top = ITEMS_Y_TOP

    for item in items:
        y = _y(y_top)

        c.setFont("Helvetica-Bold", ITEMS_SIZE)
        c.drawString(ITEMS_QTY_X * mm, y, f"{item.quantity:.0f}")
        c.drawRightString(ITEMS_PRICE_RIGHT_X * mm, y, f"€ {item.unit_price:.2f}")

        paragraph = Paragraph(_format_item_description(item.description), ITEM_DESCRIPTION_STYLE)
        _, height = paragraph.wrap(ITEMS_DESC_MAX_WIDTH, PAGE_H)
        # reportlab setzt die Baseline der ersten Zeile bei (Hoehe - Schriftgroesse)
        # unterhalb der Boxoberkante an - so landet sie auf derselben Zeile wie
        # Menge/Preis, unabhaengig davon, wie viele Zeilen der Text danach umbricht.
        bottom_y = y - height + ITEM_DESCRIPTION_STYLE.fontSize
        paragraph.drawOn(c, ITEMS_DESC_X * mm, bottom_y)

        n_lines = max(1, round(height / ITEM_DESCRIPTION_STYLE.leading))
        y_top += ITEMS_LEADING * n_lines
        y_top += ITEMS_LEADING * 0.3  # kleiner Abstand zwischen Positionen

    return y_top


def _draw_reverse_charge_text(c: canvas.Canvas) -> None:
    c.setFont("Helvetica", RC_TEXT_SIZE)
    lines = [
        "Ausländische Dienstleistung daher MwSt. frei.",
        "Die Leistung unterliegt dem Reverse-Charge-System gem. § 19 Abs. 1 USTG 1994",
    ]
    y_top = RC_TEXT_Y_TOP
    for line in lines:
        c.drawCentredString(PAGE_W / 2, _y(y_top), line)
        y_top += RC_TEXT_LEADING


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
    # Ist keine Steuer faellig (weder Werbesteuer noch MwSt., z. B. reines Reverse-Charge
    # ohne Werbesteuer), wird zwischen Positionen und Gesamtbetrag nur EIN Strich gezogen
    # statt zwei direkt aufeinanderfolgenden Strichen ohne Inhalt dazwischen.
    has_tax_lines = advertising_tax_applicable or (not reverse_charge and bool(totals.vat_breakdown))

    if has_tax_lines:
        y = _y(y_top)
        c.line(PRINT_LEFT * mm, y + 2 * mm, ITEMS_LINE_RIGHT_X * mm, y + 2 * mm)
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
    else:
        y_top += TAX_LEADING * 0.8

    y = _y(y_top)
    c.line(PRINT_LEFT * mm, y + 2 * mm, ITEMS_LINE_RIGHT_X * mm, y + 2 * mm)
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


def _report_table_style(n_numeric_cols: int) -> TableStyle:
    """Tabellenstil mit rechtsbuendigen letzten `n_numeric_cols` Spalten (Betraege)."""
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e0e0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (-n_numeric_cols, 0), (-1, -1), "RIGHT"),
        ]
    )


def _report_header(company: Company, title: str, date_from, date_to) -> list:
    return [
        Paragraph(f"<b>{company.name}</b>", styles["Heading2"]),
        Paragraph(f"<b>{title}</b>", styles["Heading1"]),
        Paragraph(f"Zeitraum: {date_from.strftime('%d.%m.%Y')} - {date_to.strftime('%d.%m.%Y')}", styles["Normal"]),
        Spacer(1, 6 * mm),
    ]


def render_balance_list_pdf(*, company: Company, saldenliste) -> bytes:
    """Saldenliste als PDF (Tabellenlayout, siehe app/services/reporting.py:Saldenliste)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = _report_header(company, "Saldenliste", saldenliste.date_from, saldenliste.date_to)

    for kunde in saldenliste.kunden:
        elements.append(Paragraph(f"<b>{kunde.customer.name}</b>", styles["Heading3"]))
        data = [["Belegart", "Nummer", "Datum", "Betrag", "Bezahlt", "Offen"]]
        for zeile in kunde.zeilen:
            data.append(
                [
                    "Rechnung" if zeile.kind == "rechnung" else "Gutschrift",
                    zeile.number,
                    zeile.beleg_date.strftime("%d.%m.%Y"),
                    f"{zeile.gross_total:.2f}",
                    f"{zeile.paid_total:.2f}",
                    f"{zeile.open_amount:.2f}",
                ]
            )
        data.append(["Summe", "", "", f"{kunde.summe_brutto:.2f}", f"{kunde.summe_bezahlt:.2f}", f"{kunde.summe_offen:.2f}"])
        table = Table(data, colWidths=[28 * mm, 28 * mm, 24 * mm, 28 * mm, 28 * mm, 28 * mm])
        table.setStyle(_report_table_style(3))
        elements.append(table)
        elements.append(Spacer(1, 5 * mm))

    elements.append(Spacer(1, 3 * mm))
    elements.append(
        Paragraph(
            f"<b>Gesamt: {saldenliste.gesamt_brutto:.2f} EUR, bezahlt {saldenliste.gesamt_bezahlt:.2f} EUR, "
            f"offen {saldenliste.gesamt_offen:.2f} EUR</b>",
            styles["Normal"],
        )
    )
    doc.build(elements)
    return buffer.getvalue()


def render_vat_summary_pdf(*, company: Company, summary) -> bytes:
    """USt.-Voranmeldungs-Auswertung als PDF (siehe app/services/reporting.py:VatSummary)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = _report_header(company, "USt.-Voranmeldung (interne Aufstellung)", summary.date_from, summary.date_to)

    data = [["Bezeichnung", "Netto", "USt.-Betrag"]]
    for rate in sorted(summary.net_by_rate):
        data.append([f"{rate}% USt.", f"{summary.net_by_rate[rate]:.2f}", f"{summary.vat_by_rate.get(rate, Decimal('0.00')):.2f}"])
    data.append(["Reverse-Charge (0% USt.)", f"{summary.reverse_charge_net:.2f}", "0.00"])
    data.append(["Werbesteuer", f"{summary.advertising_tax_amount:.2f}", ""])
    data.append(["Gesamt Netto", f"{summary.net_total:.2f}", ""])
    data.append(["Gesamt USt.", "", f"{summary.vat_total:.2f}"])
    data.append(["Gesamt Brutto", f"{summary.gross_total:.2f}", ""])

    table = Table(data, colWidths=[70 * mm, 40 * mm, 40 * mm])
    table.setStyle(_report_table_style(2))
    elements.append(table)
    doc.build(elements)
    return buffer.getvalue()
