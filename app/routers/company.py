from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import BankAccount, Company, DocumentType, DunningLevelSetting, NumberRange, PaymentTerm, User
from app.templating import templates


router = APIRouter(prefix="/company", tags=["company"])

LOGO_UPLOAD_DIR = Path("app/static/uploads")
ALLOWED_LOGO_EXTENSIONS = {".jpg", ".jpeg"}


def get_or_create_company(db: Session) -> Company:
    company = db.query(Company).first()
    if company is None:
        company = Company(name="Meine Firma")
        db.add(company)
        db.commit()
        db.refresh(company)
    return company


def _ensure_number_ranges(db: Session) -> None:
    for doc_type in DocumentType:
        exists = db.query(NumberRange).filter(NumberRange.document_type == doc_type).first()
        if not exists:
            db.add(NumberRange(document_type=doc_type))
    db.commit()


def _ensure_dunning_levels(db: Session) -> None:
    for level in (1, 2, 3):
        exists = db.query(DunningLevelSetting).filter(DunningLevelSetting.level == level).first()
        if not exists:
            db.add(DunningLevelSetting(level=level, due_days=14 * level))
    db.commit()


@router.get("")
def company_settings(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    company = get_or_create_company(db)
    _ensure_number_ranges(db)
    _ensure_dunning_levels(db)
    return templates.TemplateResponse(
        request,
        "company/settings.html",
        {
            "company": company,
            "bank_accounts": db.query(BankAccount).filter(BankAccount.company_id == company.id).all(),
            "payment_terms": db.query(PaymentTerm).all(),
            "number_ranges": db.query(NumberRange).all(),
            "dunning_levels": db.query(DunningLevelSetting).order_by(DunningLevelSetting.level).all(),
        },
    )


@router.post("/update")
def update_company(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    name: str = Form(...),
    street: str = Form(""),
    postal_code: str = Form(""),
    city: str = Form(""),
    country: str = Form("Oesterreich"),
    uid_number: str = Form(""),
    firmenbuchnummer: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    website: str = Form(""),
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    smtp_username: str = Form(""),
    smtp_password: str = Form(""),
    smtp_encryption: str = Form("starttls"),
    smtp_from_address: str = Form(""),
    smtp_from_name: str = Form(""),
    advertising_tax_rate: Decimal = Form(Decimal("5.00")),
):
    company = get_or_create_company(db)
    company.name = name
    company.street = street
    company.postal_code = postal_code
    company.city = city
    company.country = country
    company.uid_number = uid_number
    company.firmenbuchnummer = firmenbuchnummer
    company.phone = phone
    company.email = email
    company.website = website
    company.smtp_host = smtp_host
    company.smtp_port = smtp_port
    company.smtp_username = smtp_username
    if smtp_password:
        company.smtp_password = smtp_password
    company.smtp_encryption = smtp_encryption if smtp_encryption in ("none", "starttls", "ssl") else "starttls"
    company.smtp_from_address = smtp_from_address
    company.smtp_from_name = smtp_from_name
    company.advertising_tax_rate = advertising_tax_rate
    db.commit()
    return RedirectResponse("/company", status_code=303)


@router.post("/logo")
def upload_logo(db: Session = Depends(get_db), user: User = Depends(require_admin), logo: UploadFile | None = None):
    company = get_or_create_company(db)
    if logo is not None and logo.filename:
        extension = Path(logo.filename).suffix.lower()
        if extension not in ALLOWED_LOGO_EXTENSIONS:
            return RedirectResponse("/company?error=logo_type", status_code=303)
        LOGO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target_path = LOGO_UPLOAD_DIR / f"company_logo{extension}"
        target_path.write_bytes(logo.file.read())
        company.logo_path = f"uploads/company_logo{extension}"
        db.commit()
    return RedirectResponse("/company", status_code=303)


@router.post("/bank-accounts/new")
def create_bank_account(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    label: str = Form(...),
    iban: str = Form(...),
    bic: str = Form(""),
    bank_name: str = Form(""),
    is_default: bool = Form(False),
):
    company = get_or_create_company(db)
    if is_default:
        db.query(BankAccount).filter(BankAccount.company_id == company.id).update({"is_default": False})
    db.add(
        BankAccount(
            company_id=company.id, label=label, iban=iban, bic=bic, bank_name=bank_name, is_default=is_default
        )
    )
    db.commit()
    return RedirectResponse("/company", status_code=303)


@router.post("/bank-accounts/{account_id}/delete")
def delete_bank_account(account_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    account = db.get(BankAccount, account_id)
    if account:
        db.delete(account)
        db.commit()
    return RedirectResponse("/company", status_code=303)


@router.post("/payment-terms/new")
def create_payment_term(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    name: str = Form(...),
    days_due: int = Form(14),
    description: str = Form(""),
    printed_text: str = Form("Zahlbar nach Erhalt, ohne Abzug."),
    is_default: bool = Form(False),
):
    if is_default:
        db.query(PaymentTerm).update({"is_default": False})
    db.add(
        PaymentTerm(
            name=name, days_due=days_due, description=description, printed_text=printed_text, is_default=is_default
        )
    )
    db.commit()
    return RedirectResponse("/company", status_code=303)


@router.post("/payment-terms/{term_id}/delete")
def delete_payment_term(term_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    term = db.get(PaymentTerm, term_id)
    if term:
        db.delete(term)
        db.commit()
    return RedirectResponse("/company", status_code=303)


@router.post("/number-ranges/{range_id}/update")
def update_number_range(
    range_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    prefix: str = Form(""),
    suffix: str = Form(""),
    start_number: int = Form(1),
    digits: int = Form(4),
):
    number_range = db.get(NumberRange, range_id)
    number_range.prefix = prefix
    number_range.suffix = suffix
    number_range.start_number = start_number
    number_range.digits = digits
    db.commit()
    return RedirectResponse("/company", status_code=303)


@router.post("/dunning-levels/{level_id}/update")
def update_dunning_level(
    level_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    due_days: int = Form(14),
    fee_amount: Decimal = Form(Decimal("0.00")),
    text_template: str = Form(...),
):
    setting = db.get(DunningLevelSetting, level_id)
    setting.due_days = due_days
    setting.fee_amount = fee_amount
    setting.text_template = text_template
    db.commit()
    return RedirectResponse("/company", status_code=303)
