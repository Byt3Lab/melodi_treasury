from core import get_prefix_table
from core.db.base_module_tables import BaseModuleTables

MODULE_NAME = "melodi_treasury"
PREFIX_TABLE = get_prefix_table(MODULE_NAME)


class MelodiTreasuryTables(BaseModuleTables):
    JOURNALS = f"{PREFIX_TABLE}journals"
    TRANSACTIONS = f"{PREFIX_TABLE}transactions"
