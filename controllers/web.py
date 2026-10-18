import json
from decimal import Decimal
from sqlalchemy import select
from core.routing import Request, Response
from core.page_builder import Page, Component
from base.components import admin_layout
from modules.melodi_treasury.models.models import (
    TreasuryJournalModel,
    TreasuryTransactionModel,
    JournalType,
    TransactionDirection,
    TransactionSource
)
from modules.melodi_treasury.services.services import TreasuryService


class TreasuryWebController:

    @classmethod
    def get_user_payload(cls, request: Request) -> dict:
        """
        Safely retrieves the user payload from the session.
        """
        user_raw = request.get_session("user_payload")
        if not user_raw:
            return {}
        try:
            return json.loads(user_raw) if isinstance(user_raw, str) else user_raw
        except Exception:
            return {}

    @classmethod
    async def admin_journals(cls, request: Request, response: Response):
        """
        Lists all treasury journals for the active branch.
        """
        user_payload = cls.get_user_payload(request)
        active_branch_id = user_payload.get("active_branch")

        if not active_branch_id:
            return response.redirect("/admin?error=Aucune+agence+active")

        async with request.module.app.db.get_session() as session:
            journals = await TreasuryService.get_journals_by_branch(
                session=session,
                branch_id=active_branch_id,
                only_active=False
            )

        content = Component(
            module_name="melodi_treasury",
            name="admin_journals",
            context={
                "journals": journals,
                "JournalType": JournalType
            }
        )
        page = Page("Journaux de Trésorerie", admin_layout(content))
        return await response.render_page(page)

    @classmethod
    async def admin_create_journal(cls, request: Request, response: Response):
        """
        Creates a new treasury journal (GET/POST).
        """
        user_payload = cls.get_user_payload(request)
        active_branch_id = user_payload.get("active_branch")

        if not active_branch_id:
            return response.redirect("/admin/melodi_treasury/journals?error=Aucune+agence+active")

        from base.models.branch_model import BranchModel

        async with request.module.app.db.get_session() as session:
            branch = await session.get(BranchModel, active_branch_id)
            branch_currency = branch.currency_code if branch else "XAF"

        if request.method == "POST":
            form = request.form

            name = form.get("name")
            j_type_str = form.get("journal_type")
            initial_balance = form.get("initial_balance", "0.0000")

            if not name or not j_type_str:
                return response.redirect("/admin/melodi_treasury/journals/create?error=Veuillez+remplir+tous+les+champs+obligatoires")

            try:
                async with request.module.app.db.get_session() as session:
                    await TreasuryService.create_journal(
                        session=session,
                        branch_id=active_branch_id,
                        name=name,
                        journal_type=JournalType(j_type_str),
                        currency=branch_currency,
                        initial_balance=initial_balance
                    )
                    await session.commit()
                return response.redirect("/admin/melodi_treasury/journals")
            except Exception as e:
                return response.redirect(f"/admin/melodi_treasury/journals/create?error={str(e)}")

        content = Component(
            module_name="melodi_treasury",
            name="admin_create_journal",
            context={
                "JournalType": JournalType,
                "branch_currency": branch_currency
            }
        )
        page = Page("Créer un Journal", admin_layout(content))
        return await response.render_page(page)

    @classmethod
    async def admin_transactions(cls, request: Request, response: Response):
        """
        Lists treasury transactions.
        """
        user_payload = cls.get_user_payload(request)
        active_branch_id = user_payload.get("active_branch")
        journal_filter = request.query.get("journal_id", "")
        start_date_str = request.query.get("start_date", "")
        end_date_str = request.query.get("end_date", "")

        if not active_branch_id:
            return response.redirect("/admin?error=Aucune+agence+active")

        async with request.module.app.db.get_session() as session:
            # Get journals for filter dropdown
            journals = await TreasuryService.get_journals_by_branch(
                session=session,
                branch_id=active_branch_id
            )

            # Query transactions
            from sqlalchemy.orm import joinedload
            stmt = select(TreasuryTransactionModel).join(TreasuryJournalModel)
            stmt = stmt.where(TreasuryJournalModel.branch_id == active_branch_id)
            stmt = stmt.options(joinedload(TreasuryTransactionModel.journal))

            if journal_filter:
                stmt = stmt.where(TreasuryTransactionModel.journal_id == journal_filter)

            from datetime import datetime, time
            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                    stmt = stmt.where(TreasuryTransactionModel.created_at >= start_date)
                except ValueError:
                    pass
            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
                    end_date = datetime.combine(end_date.date(), time(23, 59, 59))
                    stmt = stmt.where(TreasuryTransactionModel.created_at <= end_date)
                except ValueError:
                    pass

            stmt = stmt.order_by(TreasuryTransactionModel.created_at.desc())
            res = await session.execute(stmt)
            transactions = res.scalars().all()

        content = Component(
            module_name="melodi_treasury",
            name="admin_transactions",
            context={
                "transactions": transactions,
                "journals": journals,
                "journal_filter": journal_filter,
                "TransactionDirection": TransactionDirection,
                "TransactionSource": TransactionSource
            }
        )
        page = Page("Transactions de Trésorerie", admin_layout(content))
        return await response.render_page(page)

    @classmethod
    async def admin_create_transaction(cls, request: Request, response: Response):
        """
        Records a manual transaction adjustment (GET/POST).
        """
        user_payload = cls.get_user_payload(request)
        active_branch_id = user_payload.get("active_branch")
        user_id = user_payload.get("user_id")

        if not active_branch_id:
            return response.redirect("/admin/melodi_treasury/transactions?error=Aucune+agence+active")

        if request.method == "POST":
            form = request.form

            journal_id = form.get("journal_id")
            direction_str = form.get("direction")
            amount = form.get("amount")
            exchange_rate = "1.0000"
            description = form.get("description")

            if not journal_id or not direction_str or not amount:
                return response.redirect("/admin/melodi_treasury/transactions/create?error=Veuillez+remplir+tous+les+champs+obligatoires")

            try:
                async with request.module.app.db.get_session() as session:
                    await TreasuryService.create_transaction(
                        session=session,
                        journal_id=journal_id,
                        direction=TransactionDirection(direction_str),
                        source_type=TransactionSource.MANUAL_ADJUSTMENT,
                        amount=amount,
                        created_by_user_id=user_id,
                        exchange_rate=exchange_rate,
                        description=description
                    )
                    await session.commit()
                return response.redirect("/admin/melodi_treasury/transactions")
            except Exception as e:
                return response.redirect(f"/admin/melodi_treasury/transactions/create?error={str(e)}")

        journal_id = request.query.get("journal_id")
        if not journal_id:
            return response.redirect("/admin/melodi_treasury/transactions?error=Veuillez+sélectionner+un+journal")

        async with request.module.app.db.get_session() as session:
            stmt = select(TreasuryJournalModel).where(
                TreasuryJournalModel.journal_id == journal_id,
                TreasuryJournalModel.branch_id == active_branch_id
            )
            res = await session.execute(stmt)
            journal = res.scalar_one_or_none()

            if not journal:
                return response.redirect("/admin/melodi_treasury/transactions?error=Journal+introuvable")

        content = Component(
            module_name="melodi_treasury",
            name="admin_create_transaction",
            context={
                "journal": journal,
                "TransactionDirection": TransactionDirection
            }
        )
        page = Page("Nouvel Ajustement", admin_layout(content))
        return await response.render_page(page)

    @classmethod
    async def admin_dashboard(cls, request: Request, response: Response):
        """
        Main Admin Dashboard page for MELODI Treasury (/admin/melodi_treasury).
        Provides an overview of cash journals, total balances, inflow/outflow metrics, and recent transactions.
        """
        user_payload = cls.get_user_payload(request)
        active_branch_id = user_payload.get("active_branch")

        if not active_branch_id:
            return response.redirect("/admin?error=Aucune+agence+active")

        async with request.module.app.db.get_session() as session:
            # 1. Fetch all journals for active branch
            journals = await TreasuryService.get_journals_by_branch(
                session=session,
                branch_id=active_branch_id,
                only_active=False
            )

            total_balance = sum((j.balance for j in journals if j.is_active), Decimal("0.0000"))
            cash_journals_count = sum(1 for j in journals if j.journal_type == JournalType.CASH and j.is_active)
            bank_journals_count = sum(1 for j in journals if j.journal_type == JournalType.BANK and j.is_active)
            mobile_journals_count = sum(1 for j in journals if j.journal_type == JournalType.MOBILE_MONEY and j.is_active)

            # 2. Fetch transactions for active branch
            from sqlalchemy.orm import joinedload
            stmt_tx = select(TreasuryTransactionModel).join(TreasuryJournalModel)
            stmt_tx = stmt_tx.where(TreasuryJournalModel.branch_id == active_branch_id)
            stmt_tx = stmt_tx.options(joinedload(TreasuryTransactionModel.journal))
            stmt_tx = stmt_tx.order_by(TreasuryTransactionModel.created_at.desc())

            res_tx = await session.execute(stmt_tx)
            all_transactions = list(res_tx.scalars().all())

            total_inflow = sum((tx.amount for tx in all_transactions if tx.direction == TransactionDirection.IN), Decimal("0.0000"))
            total_outflow = sum((tx.amount for tx in all_transactions if tx.direction == TransactionDirection.OUT), Decimal("0.0000"))
            net_cash_flow = total_inflow - total_outflow

            recent_transactions = all_transactions[:5]

            stats = {
                "total_journals": len(journals),
                "active_journals": sum(1 for j in journals if j.is_active),
                "total_balance": total_balance,
                "total_inflow": total_inflow,
                "total_outflow": total_outflow,
                "net_cash_flow": net_cash_flow,
                "cash_count": cash_journals_count,
                "bank_count": bank_journals_count,
                "mobile_count": mobile_journals_count,
                "total_tx_count": len(all_transactions)
            }

        content = Component(
            module_name="melodi_treasury",
            name="admin_dashboard",
            context={
                "stats": stats,
                "journals": journals,
                "recent_transactions": recent_transactions,
                "JournalType": JournalType,
                "TransactionDirection": TransactionDirection,
                "TransactionSource": TransactionSource
            }
        )
        page = Page("Tableau de bord Trésorerie", admin_layout(content))
        return await response.render_page(page)
