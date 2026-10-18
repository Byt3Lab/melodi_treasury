import uuid
from decimal import Decimal
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.melodi_treasury.models.models import (
    TreasuryJournalModel,
    TreasuryTransactionModel,
    JournalType,
    TransactionDirection,
    TransactionSource
)


class TreasuryService:
    @staticmethod
    async def create_journal(
        session: AsyncSession,
        branch_id: str,
        name: str,
        journal_type: JournalType,
        currency: str = "XAF",
        initial_balance: Decimal | float | str = Decimal("0.0000")
    ) -> TreasuryJournalModel:
        """
        Creates a new treasury journal. Enforces using the branch's local currency.
        """
        from base.models.branch_model import BranchModel
        
        # Récupérer la branche associée pour obtenir sa monnaie locale
        stmt = select(BranchModel).where(BranchModel.branch_id == branch_id)
        res = await session.execute(stmt)
        branch = res.scalar_one_or_none()
        
        if not branch:
            raise ValueError(f"La branche associée est introuvable : {branch_id}")
            
        # Forcer la monnaie locale de la branche (donc du pays associé)
        branch_currency = branch.currency_code or "XAF"
        
        journal_id = str(uuid.uuid4())
        balance_dec = Decimal(str(initial_balance))

        journal = TreasuryJournalModel(
            journal_id=journal_id,
            branch_id=branch_id,
            name=name,
            journal_type=journal_type,
            currency=branch_currency,
            balance=balance_dec,
            is_active=True
        )
        session.add(journal)
        await session.flush()
        return journal

    @staticmethod
    async def create_transaction(
        session: AsyncSession,
        journal_id: str,
        direction: TransactionDirection,
        source_type: TransactionSource,
        amount: Decimal | float | str,
        created_by_user_id: str,
        reference_id: str = None,
        description: str = None,
        exchange_rate: Decimal | float | str = Decimal("1.0000")
    ) -> TreasuryTransactionModel:
        """
        Records a treasury transaction and adjusts the journal balance.
        """
        amount_dec = Decimal(str(amount))
        rate_dec = Decimal(str(exchange_rate))

        if amount_dec <= Decimal("0.0000"):
            raise ValueError("Transaction amount must be strictly positive.")

        if rate_dec <= Decimal("0.0000"):
            raise ValueError("Exchange rate must be strictly positive.")

        # Fetch and lock the journal for update to prevent race conditions in concurrent transactions
        stmt = (
            select(TreasuryJournalModel)
            .where(TreasuryJournalModel.journal_id == journal_id)
            .with_for_update()
        )
        result = await session.execute(stmt)
        journal = result.scalar_one_or_none()

        if not journal:
            raise ValueError(f"Treasury journal not found: {journal_id}")

        if not journal.is_active:
            raise ValueError(f"Treasury journal is inactive: {journal.name}")

        exchanged_amount = amount_dec * rate_dec

        if direction == TransactionDirection.IN:
            new_balance = journal.balance + exchanged_amount
        elif direction == TransactionDirection.OUT:
            new_balance = journal.balance - exchanged_amount
            # Enforce non-negative restriction for cash journals
            if journal.journal_type == JournalType.CASH and new_balance < Decimal("0.0000"):
                raise ValueError(
                    f"Insufficient funds in cash journal {journal.name}. "
                    f"Attempted to withdraw {exchanged_amount} {journal.currency}, "
                    f"current balance: {journal.balance} {journal.currency}."
                )
        else:
            raise ValueError(f"Invalid transaction direction: {direction}")

        # Update the journal balance
        journal.balance = new_balance

        # Record the transaction entry
        transaction_id = str(uuid.uuid4())
        transaction = TreasuryTransactionModel(
            transaction_id=transaction_id,
            journal_id=journal_id,
            direction=direction,
            source_type=source_type,
            reference_id=reference_id,
            amount=amount_dec,
            exchange_rate=rate_dec,
            description=description,
            created_by_user_id=created_by_user_id
        )
        session.add(transaction)
        await session.flush()
        return transaction

    @staticmethod
    async def get_journals_by_branch(
        session: AsyncSession,
        branch_id: str,
        only_active: bool = False
    ) -> Sequence[TreasuryJournalModel]:
        """
        Retrieves all journals belonging to a specific branch.
        """
        stmt = select(TreasuryJournalModel).where(TreasuryJournalModel.branch_id == branch_id)
        if only_active:
            stmt = stmt.where(TreasuryJournalModel.is_active == True)
        
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_transactions_by_journal(
        session: AsyncSession,
        journal_id: str
    ) -> Sequence[TreasuryTransactionModel]:
        """
        Retrieves the ledger of transactions for a specific journal.
        """
        stmt = (
            select(TreasuryTransactionModel)
            .where(TreasuryTransactionModel.journal_id == journal_id)
            .order_by(TreasuryTransactionModel.created_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def transfer_funds(
        session: AsyncSession,
        source_journal_id: str,
        target_journal_id: str,
        amount: Decimal | float | str,
        created_by_user_id: str,
        description: str = None
    ) -> tuple[TreasuryTransactionModel, TreasuryTransactionModel]:
        """
        Transfers funds from a source journal to a target journal.
        Calculates conversion rate from DB if they use different currencies.
        """
        amount_dec = Decimal(str(amount))
        
        # Charger les deux journaux
        stmt_src = select(TreasuryJournalModel).where(TreasuryJournalModel.journal_id == source_journal_id)
        src_journal = (await session.execute(stmt_src)).scalar_one_or_none()
        
        stmt_tgt = select(TreasuryJournalModel).where(TreasuryJournalModel.journal_id == target_journal_id)
        tgt_journal = (await session.execute(stmt_tgt)).scalar_one_or_none()
        
        if not src_journal or not tgt_journal:
            raise ValueError("Source or target journal not found.")
            
        rate = Decimal("1.0000")
        if src_journal.currency != tgt_journal.currency:
            # Récupérer le taux de change de la base de données (de la devise source vers cible)
            from base.models import ExchangeRateModel
            stmt_rate = select(ExchangeRateModel).where(
                ExchangeRateModel.from_currency_code == src_journal.currency,
                ExchangeRateModel.to_currency_code == tgt_journal.currency
            )
            rate_obj = (await session.execute(stmt_rate)).scalar_one_or_none()
            if rate_obj:
                rate = Decimal(str(rate_obj.rate))
            else:
                # Essayer le taux inverse
                stmt_inv_rate = select(ExchangeRateModel).where(
                    ExchangeRateModel.from_currency_code == tgt_journal.currency,
                    ExchangeRateModel.to_currency_code == src_journal.currency
                )
                inv_rate_obj = (await session.execute(stmt_inv_rate)).scalar_one_or_none()
                if inv_rate_obj and inv_rate_obj.rate > 0:
                    rate = Decimal("1.0000") / Decimal(str(inv_rate_obj.rate))
                else:
                    raise ValueError(f"No exchange rate found in DB from {src_journal.currency} to {tgt_journal.currency}")
                    
        # Débiter le journal source
        tx_out = await TreasuryService.create_transaction(
            session=session,
            journal_id=source_journal_id,
            direction=TransactionDirection.OUT,
            source_type=TransactionSource.MANUAL_ADJUSTMENT,
            amount=amount_dec,
            created_by_user_id=created_by_user_id,
            description=description or f"Transfer to journal {tgt_journal.name}"
        )
        
        # Créditer le journal cible avec le montant converti
        tx_in = await TreasuryService.create_transaction(
            session=session,
            journal_id=target_journal_id,
            direction=TransactionDirection.IN,
            source_type=TransactionSource.MANUAL_ADJUSTMENT,
            amount=amount_dec * rate,
            created_by_user_id=created_by_user_id,
            description=description or f"Transfer from journal {src_journal.name}",
            exchange_rate=rate
        )
        
        return tx_out, tx_in
