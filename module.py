from core.module import ApplicationModule, Permission
from modules.melodi_treasury.services.services import TreasuryService
from modules.melodi_treasury.controllers.web import TreasuryWebController


class TreasuryModule(ApplicationModule):
    def _get_permissions(self):
        return [
            Permission(self, "treasury:read", "Consulter les journaux et transactions de trésorerie"),
            Permission(self, "treasury:write", "Gérer les opérations de trésorerie (Créer des journaux, ajuster des soldes)")
        ]

    async def run_dev_migrations(self):
        """
        Gère les migrations de développement : création des tables SQLAlchemy.
        """
        from modules.melodi_treasury.models.models import TreasuryJournalModel, TreasuryTransactionModel
        await self.app.db.create_all([TreasuryJournalModel, TreasuryTransactionModel])

    async def load(self):
        """
        Initialisation du module de trésorerie.
        """
        self.permissions = self._get_permissions()

        # Migrations de BDD en mode debug
        if self.app.server.app.debug:
            await self.run_dev_migrations()

        # Enregistrement des routes d'administration
        self.admin_router.add_route("", TreasuryWebController.admin_dashboard, methods=["GET"])
        self.admin_router.add_route("/", TreasuryWebController.admin_dashboard, methods=["GET"])

        self.admin_router.add_route("/journals", TreasuryWebController.admin_journals, methods=["GET"])
        self.admin_router.add_route("/journals/create", TreasuryWebController.admin_create_journal, methods=["GET", "POST"])
        self.admin_router.add_route("/transactions", TreasuryWebController.admin_transactions, methods=["GET"])
        self.admin_router.add_route("/transactions/create", TreasuryWebController.admin_create_transaction, methods=["GET", "POST"])

        # Enregistrement des actions inter-modules
        self._register_actions()

        # Enregistrement de la navigation
        self.register_navigation(
            id="treasury_root",
            label="Trésorerie",
            icon="name=account_balance_wallet&fill=white",
            url="/admin/melodi_treasury",
            priority=75,
            children=[
                {"label": "Tableau de Bord", "icon": "name=dashboard&fill=white", "url": "/admin/melodi_treasury"},
                {"label": "Journaux de caisse", "icon": "name=wallet&fill=white", "url": "/admin/melodi_treasury/journals"},
                {"label": "Transactions", "icon": "name=swap_horiz&fill=white", "url": "/admin/melodi_treasury/transactions"}
            ]
        )

    def _register_actions(self):
        """
        Enregistre les actions que ce module expose aux autres modules de l'application.
        """
        self.add_action("create_journal", self.action_create_journal)
        self.add_action("create_transaction", self.action_create_transaction)

    # --- Handlers d'actions inter-modules ---

    async def action_create_journal(self, payload: dict) -> dict:
        """
        Action inter-module permettant de créer un nouveau compte ou caisse de trésorerie.
        """
        async with self.app.db.get_session() as session:
            try:
                journal = await TreasuryService.create_journal(
                    session=session,
                    branch_id=payload.get("branch_id"),
                    name=payload.get("name"),
                    journal_type=payload.get("journal_type"),
                    currency=payload.get("currency", "XAF"),
                    initial_balance=payload.get("initial_balance", "0.0000")
                )
                await session.commit()
                return {
                    "status": "success",
                    "journal_id": journal.journal_id,
                    "name": journal.name,
                    "balance": str(journal.balance)
                }
            except Exception as e:
                await session.rollback()
                return {"status": "error", "message": str(e)}

    async def action_create_transaction(self, payload: dict) -> dict:
        """
        Action inter-module permettant de générer un flux de trésorerie de manière sécurisée.
        """
        async with self.app.db.get_session() as session:
            try:
                tx = await TreasuryService.create_transaction(
                    session=session,
                    journal_id=payload.get("journal_id"),
                    direction=payload.get("direction"),
                    source_type=payload.get("source_type"),
                    amount=payload.get("amount"),
                    created_by_user_id=payload.get("created_by_user_id"),
                    reference_id=payload.get("reference_id"),
                    description=payload.get("description"),
                    exchange_rate=payload.get("exchange_rate", "1.0000")
                )
                await session.commit()
                return {
                    "status": "success",
                    "transaction_id": tx.transaction_id,
                    "journal_id": tx.journal_id,
                    "direction": tx.direction.value,
                    "amount": str(tx.amount),
                    "balance": str(tx.journal.balance)
                }
            except Exception as e:
                await session.rollback()
                return {"status": "error", "message": str(e)}


module = TreasuryModule(
    name="melodi_treasury",
    router_name="melodi_treasury"
)
