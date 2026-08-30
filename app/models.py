import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SACHBEARBEITER = "sachbearbeiter"


class DocumentType(str, enum.Enum):
    AUFTRAG = "auftrag"
    RECHNUNG = "rechnung"
    GUTSCHRIFT = "gutschrift"


class InvoiceStatus(str, enum.Enum):
    OFFEN = "offen"
    TEILBEZAHLT = "teilbezahlt"
    BEZAHLT = "bezahlt"


class VatRate(int, enum.Enum):
    REDUZIERT = 10
    NORMAL = 20


class MailStatus(str, enum.Enum):
    GESENDET = "gesendet"
    FEHLGESCHLAGEN = "fehlgeschlagen"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.SACHBEARBEITER)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Company(Base):
    """Firmenstammdaten - einzige Zeile (Singleton)."""

    __tablename__ = "company"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    street: Mapped[str] = mapped_column(String(255), default="")
    postal_code: Mapped[str] = mapped_column(String(20), default="")
    city: Mapped[str] = mapped_column(String(128), default="")
    country: Mapped[str] = mapped_column(String(64), default="Oesterreich")
    uid_number: Mapped[str] = mapped_column(String(32), default="")
    firmenbuchnummer: Mapped[str] = mapped_column(String(32), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    website: Mapped[str] = mapped_column(String(128), default="")

    smtp_host: Mapped[str] = mapped_column(String(255), default="")
    smtp_port: Mapped[int] = mapped_column(default=587)
    smtp_username: Mapped[str] = mapped_column(String(255), default="")
    smtp_password: Mapped[str] = mapped_column(String(255), default="")
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    smtp_from_address: Mapped[str] = mapped_column(String(255), default="")
    smtp_from_name: Mapped[str] = mapped_column(String(255), default="")

    advertising_tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("5.00"))

    bank_accounts: Mapped[list["BankAccount"]] = relationship(back_populates="company")


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))
    label: Mapped[str] = mapped_column(String(128))
    iban: Mapped[str] = mapped_column(String(34))
    bic: Mapped[str] = mapped_column(String(11), default="")
    bank_name: Mapped[str] = mapped_column(String(128), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    company: Mapped["Company"] = relationship(back_populates="bank_accounts")


class PaymentTerm(Base):
    __tablename__ = "payment_terms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    days_due: Mapped[int] = mapped_column(default=14)
    description: Mapped[str] = mapped_column(String(255), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class NumberRange(Base):
    """Nummernkreis je Belegtyp: fortlaufend, mit Praefix/Suffix und Startnummer."""

    __tablename__ = "number_ranges"
    __table_args__ = (UniqueConstraint("document_type", name="uq_number_range_doctype"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType))
    prefix: Mapped[str] = mapped_column(String(20), default="")
    suffix: Mapped[str] = mapped_column(String(20), default="")
    start_number: Mapped[int] = mapped_column(default=1)
    current_number: Mapped[int] = mapped_column(default=0)
    digits: Mapped[int] = mapped_column(default=4)


class DunningLevelSetting(Base):
    """Konfiguration je Mahnstufe (1-3): Frist, Gebuehr, editierbarer Text."""

    __tablename__ = "dunning_level_settings"
    __table_args__ = (UniqueConstraint("level", name="uq_dunning_level"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[int] = mapped_column()  # 1, 2 oder 3
    due_days: Mapped[int] = mapped_column(default=14)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    text_template: Mapped[str] = mapped_column(
        Text,
        default=(
            "Sehr geehrte/r {kunde},\n\n"
            "trotz Fristablauf konnten wir zu Rechnung {rechnungsnummer} vom {rechnungsdatum} "
            "ueber {betrag} EUR bislang keinen Zahlungseingang feststellen.\n"
            "Wir bitten um Ausgleich bis {faelligkeitsdatum}.\n\n"
            "Mit freundlichen Gruessen"
        ),
    )


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    street: Mapped[str] = mapped_column(String(255), default="")
    postal_code: Mapped[str] = mapped_column(String(20), default="")
    city: Mapped[str] = mapped_column(String(128), default="")
    country: Mapped[str] = mapped_column(String(64), default="Oesterreich")
    is_eu_country: Mapped[bool] = mapped_column(Boolean, default=False)
    uid_number: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    contact_person: Mapped[str] = mapped_column(String(128), default="")

    payment_term_id: Mapped[int | None] = mapped_column(ForeignKey("payment_terms.id"), nullable=True)
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    payment_term: Mapped["PaymentTerm | None"] = relationship()
    bank_account: Mapped["BankAccount | None"] = relationship()

    @property
    def reverse_charge_applicable(self) -> bool:
        """Reverse-Charge gilt fuer auslaendische (EU) Kunden mit gueltiger UID."""
        return self.is_eu_country and bool(self.uid_number.strip())


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(500), default="")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    vat_rate: Mapped[int] = mapped_column(default=20)  # 10 oder 20
    unit: Mapped[str] = mapped_column(String(32), default="Stk")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(64), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    order_date: Mapped[date] = mapped_column(Date, default=date.today)
    advertising_tax_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer: Mapped["Customer"] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    vat_rate: Mapped[int] = mapped_column(default=20)

    order: Mapped["Order"] = relationship(back_populates="items")

    @property
    def net_total(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(64), unique=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    invoice_date: Mapped[date] = mapped_column(Date, default=date.today)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.OFFEN)
    reverse_charge: Mapped[bool] = mapped_column(Boolean, default=False)
    advertising_tax_applicable: Mapped[bool] = mapped_column(Boolean, default=False)
    advertising_tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("5.00"))
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer: Mapped["Customer"] = relationship()
    order: Mapped["Order | None"] = relationship()
    bank_account: Mapped["BankAccount | None"] = relationship()
    items: Mapped[list["InvoiceItem"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    dunnings: Mapped[list["Dunning"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    vat_rate: Mapped[int] = mapped_column(default=20)

    invoice: Mapped["Invoice"] = relationship(back_populates="items")

    @property
    def net_total(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))


class CreditNote(Base):
    """Gutschrift: eigener Belegtyp mit eigenem Nummernkreis, referenziert die Original-Rechnung."""

    __tablename__ = "credit_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(64), unique=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    credit_note_date: Mapped[date] = mapped_column(Date, default=date.today)
    reason: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    invoice: Mapped["Invoice"] = relationship()
    items: Mapped[list["CreditNoteItem"]] = relationship(back_populates="credit_note", cascade="all, delete-orphan")


class CreditNoteItem(Base):
    __tablename__ = "credit_note_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    credit_note_id: Mapped[int] = mapped_column(ForeignKey("credit_notes.id"))
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    vat_rate: Mapped[int] = mapped_column(default=20)

    credit_note: Mapped["CreditNote"] = relationship(back_populates="items")

    @property
    def net_total(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    payment_date: Mapped[date] = mapped_column(Date, default=date.today)
    method: Mapped[str] = mapped_column(String(64), default="Ueberweisung")
    note: Mapped[str] = mapped_column(String(255), default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    invoice: Mapped["Invoice"] = relationship(back_populates="payments")


class Dunning(Base):
    """Ausgestellte Mahnung zu einer Rechnung, Stufe 1-3, manuell ausgeloest."""

    __tablename__ = "dunnings"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    level: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_date: Mapped[date] = mapped_column(Date)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    rendered_text: Mapped[str] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    invoice: Mapped["Invoice"] = relationship(back_populates="dunnings")


class MailLog(Base):
    """Protokoll versendeter Belege per E-Mail (SMTP)."""

    __tablename__ = "mail_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    related_type: Mapped[str] = mapped_column(String(32))  # invoice | credit_note | dunning
    related_id: Mapped[int] = mapped_column()
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    status: Mapped[MailStatus] = mapped_column(Enum(MailStatus))
    error_message: Mapped[str] = mapped_column(String(500), default="")
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
