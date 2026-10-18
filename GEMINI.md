# MELODI Treasury — Directives du Module Trésorerie & Caisses (`modules/melodi_treasury/`)

Le module `melodi_treasury` gère les comptes bancaires, les caisses physiques, les mouvements de flux financiers, les transferts de fonds et le rapprochement de trésorerie.

---

## 1. Modèles et Schéma de Données

- **`TreasuryAccountModel`** (`ml_trs_accounts`) : Comptes bancaires ou coffres de trésorerie (`account_id`, `name`, `type`: `'bank'` / `'cash'`, `currency`, `balance`).
- **`TreasuryTransactionModel`** (`ml_trs_transactions`) : Mouvements financiers entrants ou sortants (`transaction_id`, `account_id`, `amount`, `type`: `'in'` / `'out'` / `'transfer'`, `reference`, `date`, `status`).

---

## 2. Directives Métier

1. **Intégrité des Soldes** :
   Chaque transaction validée doit mettre à jour le solde du compte de trésorerie de manière atomique au sein de la transaction SQL (`AsyncSession`).
2. **Transferts Inter-Comptes** :
   Un transfert crée une opération double liée (débit sur le compte émetteur, crédit sur le compte récepteur) avec un identifiant de transfert commun.
3. **Synchronisation Comptable** :
   Les opérations de trésorerie validées génèrent les écritures correspondantes dans le journal de trésorerie (`BQ` / `CA`) du module `melodi_accounting`.
