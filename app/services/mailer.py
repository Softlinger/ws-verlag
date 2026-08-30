import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.models import Company, MailLog, MailStatus


def send_document_mail(
    db: Session,
    *,
    company: Company,
    related_type: str,
    related_id: int,
    recipient: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> MailLog:
    """Versendet ein PDF-Dokument per SMTP und protokolliert das Ergebnis in mail_log."""
    status = MailStatus.GESENDET
    error_message = ""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{company.smtp_from_name} <{company.smtp_from_address}>" if company.smtp_from_name else company.smtp_from_address
    msg["To"] = recipient
    msg.set_content(body)
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=pdf_filename)

    try:
        if not company.smtp_host:
            raise RuntimeError("Kein SMTP-Server in den Firmenstammdaten konfiguriert.")
        with smtplib.SMTP(company.smtp_host, company.smtp_port, timeout=15) as server:
            if company.smtp_use_tls:
                server.starttls()
            if company.smtp_username:
                server.login(company.smtp_username, company.smtp_password)
            server.send_message(msg)
    except Exception as exc:  # noqa: BLE001 - Fehler wird protokolliert, nicht verschluckt
        status = MailStatus.FEHLGESCHLAGEN
        error_message = str(exc)[:500]

    log_entry = MailLog(
        related_type=related_type,
        related_id=related_id,
        recipient=recipient,
        subject=subject,
        status=status,
        error_message=error_message,
    )
    db.add(log_entry)
    db.flush()
    return log_entry
