# QuickBooks load verification

Run 2026-10-31 15:32. Compares QuickBooks' trial balance with the Fernvale ledger (build/books_as_booked.sqlite).

## Trial balance at 2024-12-31: PASS

All 38 Fernvale accounts match to the cent.

## Trial balance at 2025-12-31: PASS

All 44 Fernvale accounts match to the cent.

## Trial balance at 2026-09-30: PASS

All 49 Fernvale accounts match to the cent.

## Trial balance at 2026-10-31: PASS

All 49 Fernvale accounts match to the cent.

## Non-Fernvale accounts with balances (left over from sample data)

| Account | Balance |
|---|---:|
| Arizona Dept. of Revenue Payable | 38.40 |
| Board of Equalization Payable | 38.50 |
| Checking | -76.90 |
| Inventory Shrinkage (deleted) | 567.50 |
| Opening Balance Equity | -567.50 |

The non-Fernvale balances are crumbs from Intuit's sample company (sales tax payments and an inventory adjustment that QuickBooks keeps after the transactions are deleted). They net to zero and sit outside the Fernvale chart of accounts.
