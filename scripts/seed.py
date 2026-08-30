"""Legt bei Bedarf einen initialen Admin-Benutzer und Demo-Stammdaten an.

Aufruf: poetry run python scripts/seed.py
"""
import secrets
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password
from app.database import Base, SessionLocal, engine, ensure_new_columns
from app.models import (
    Article,
    BankAccount,
    Customer,
    DocumentType,
    DunningLevelSetting,
    NumberRange,
    Order,
    OrderItem,
    PaymentTerm,
    User,
    UserRole,
)
from app.routers.company import get_or_create_company


def main() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_new_columns()
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            generated_password = secrets.token_urlsafe(9)
            admin = User(
                username="admin",
                full_name="Administrator",
                password_hash=hash_password(generated_password),
                role=UserRole.ADMIN,
            )
            db.add(admin)
            db.commit()
            print("=" * 60)
            print(f"Admin-Benutzer angelegt: admin / {generated_password}")
            print("WICHTIG: Passwort nach dem ersten Login aendern!")
            print("=" * 60)
        else:
            print("Admin-Benutzer existiert bereits, ueberspringe.")

        company = get_or_create_company(db)
        if company.name == "Meine Firma":
            company.name = "WS-Verlag GmbH"
            company.street = "Musterstrasse 1"
            company.postal_code = "1010"
            company.city = "Wien"
            company.country = "Oesterreich"
            company.uid_number = "ATU00000000"
            db.commit()

        for doc_type in DocumentType:
            if not db.query(NumberRange).filter(NumberRange.document_type == doc_type).first():
                prefix_map = {
                    DocumentType.AUFTRAG: "A-",
                    DocumentType.RECHNUNG: "R-",
                    DocumentType.GUTSCHRIFT: "G-",
                }
                db.add(NumberRange(document_type=doc_type, prefix=prefix_map[doc_type], start_number=1, digits=5))
        db.commit()

        for level in (1, 2, 3):
            if not db.query(DunningLevelSetting).filter(DunningLevelSetting.level == level).first():
                db.add(DunningLevelSetting(level=level, due_days=14 * level, fee_amount=Decimal("0.00") if level == 1 else Decimal("10.00")))
        db.commit()

        if not db.query(BankAccount).filter(BankAccount.company_id == company.id).first():
            db.add(
                BankAccount(
                    company_id=company.id,
                    label="Hauptkonto",
                    iban="AT483200000012345864",
                    bic="RLNWATWW",
                    bank_name="Raiffeisenlandesbank",
                    is_default=True,
                )
            )
            db.commit()

        if not db.query(PaymentTerm).first():
            db.add(PaymentTerm(name="Sofort netto", days_due=0, is_default=False))
            db.add(PaymentTerm(name="14 Tage netto", days_due=14, is_default=True))
            db.add(PaymentTerm(name="30 Tage netto", days_due=30, is_default=False))
            db.commit()

        if not db.query(Article).first():
            default_term = db.query(PaymentTerm).filter(PaymentTerm.is_default.is_(True)).first()
            bank_account = db.query(BankAccount).filter(BankAccount.is_default.is_(True)).first()

            db.add(Article(name="Zeitschriften-Abo Jahresbezug", unit_price=Decimal("89.00"), vat_rate=10, unit="Abo"))
            db.add(Article(name="Inserat 1/1 Seite", unit_price=Decimal("450.00"), vat_rate=20, unit="Stk"))
            db.add(Article(name="Einzelausgabe", unit_price=Decimal("6.90"), vat_rate=10, unit="Stk"))
            db.commit()

            demo_customer_at = Customer(
                name="Mustermann Buchhandel GmbH",
                street="Hauptstrasse 5",
                postal_code="4020",
                city="Linz",
                country="Oesterreich",
                is_eu_country=False,
                email="office@mustermann-buchhandel.example",
                payment_term_id=default_term.id if default_term else None,
                bank_account_id=bank_account.id if bank_account else None,
            )
            demo_customer_eu = Customer(
                name="Musterfirma GmbH (DE)",
                street="Beispielweg 10",
                postal_code="80331",
                city="Muenchen",
                country="Deutschland",
                is_eu_country=True,
                uid_number="DE123456789",
                email="buchhaltung@musterfirma.example",
                payment_term_id=default_term.id if default_term else None,
            )
            db.add(demo_customer_at)
            db.add(demo_customer_eu)
            db.commit()

            order_number_range = db.query(NumberRange).filter(NumberRange.document_type == DocumentType.AUFTRAG).first()
            order_number_range.current_number += 1
            order = Order(
                number=f"{order_number_range.prefix}{str(order_number_range.current_number).zfill(order_number_range.digits)}",
                customer_id=demo_customer_at.id,
                order_date=date.today(),
                advertising_tax_applicable=True,
                note="Demo-Auftrag aus Seed-Skript",
            )
            db.add(order)
            db.flush()
            order.items.append(OrderItem(description="Inserat 1/1 Seite", quantity=Decimal("1"), unit_price=Decimal("450.00"), vat_rate=20))
            db.commit()

            print("Demo-Stammdaten (Kunden, Artikel, Auftrag) angelegt.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
