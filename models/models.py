import enum
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, ForeignKey, text, Enum, Text, Boolean
from sqlalchemy.orm import relationship
from core.orm.model import BaseModel, Mapped, mapped_column
from modules.melodi_treasury.config import MelodiTreasuryTables


class JournalType(str, enum.Enum):
    CASH = "CASH"
    BANK = "BANK"
    MOBILE_MONEY = "MOBILE_MONEY"


class TransactionDirection(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"


class TransactionSource(str, enum.Enum):
    CUSTOMER_INVOICE = "CUSTOMER_INVOICE"
    VENDOR_BILL = "VENDOR_BILL"
    ASSET_MAINTENANCE = "ASSET_MAINTENANCE"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"


class TreasuryJournalModel(BaseModel):
    __tablename__ = MelodiTreasuryTables.JOURNALS

    journal_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    branch_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    journal_type: Mapped[JournalType] = mapped_column(Enum(JournalType), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="XAF")
    balance: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, default=Decimal("0.0000"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), default=datetime.utcnow)

    transactions: Mapped[list["TreasuryTransactionModel"]] = relationship(
        "TreasuryTransactionModel",
        back_populates="journal",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class TreasuryTransactionModel(BaseModel):
    __tablename__ = MelodiTreasuryTables.TRANSACTIONS

    transaction_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    journal_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey(f"{MelodiTreasuryTables.JOURNALS}.journal_id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    direction: Mapped[TransactionDirection] = mapped_column(Enum(TransactionDirection), nullable=False, index=True)
    source_type: Mapped[TransactionSource] = mapped_column(Enum(TransactionSource), nullable=False, index=True)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("1.0000"))
    description: Mapped[str] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), default=datetime.utcnow, index=True)

    journal: Mapped[TreasuryJournalModel] = relationship(
        "TreasuryJournalModel",
        back_populates="transactions",
        lazy="select"
    )
