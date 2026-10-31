# Loading Fernvale into the QuickBooks sandbox

The loader (`qbo_loader/`) puts Fernvale's books into a QuickBooks Online **sandbox** company through the QuickBooks API. It uses only the Python standard library, so there's nothing to install beyond Python 3.10+. It refuses to run against anything but a sandbox.

## Before you start

1. Create an Intuit Developer app with the Accounting scope, and add the redirect URI `http://localhost:8765/callback` to its **Development** settings.
2. Copy `.env.example` to `.env` and fill in the Development **Client ID**, **Client Secret** and sandbox **Company ID**. `.env` is git-ignored.

## Run it

From the repo folder (PowerShell on Windows, Terminal on Mac):

```
python -m qbo_loader check     # sign in (opens your browser), fix settings, count sample data
python -m qbo_loader clean     # delete Intuit's sample transactions (asks you to type DELETE SAMPLE)
python -m qbo_loader setup     # 49 accounts, 8 classes, 3 items, ~320 customers, 42 vendors
python -m qbo_loader load      # opening balances + ~6,000 transactions, about 15 minutes
python -m qbo_loader verify    # QuickBooks trial balance vs the ledger on 4 dates
python -m qbo_loader close     # reminds you to set the closing date (Sep 30, 2026) in QuickBooks
```

Or run everything in order with `python -m qbo_loader all`.

The first command opens a browser window to sign in to QuickBooks. Choose the sandbox company. Windows may ask whether Python can use the network; allow it on private networks. Tokens are saved to `.qbo_tokens.json` (git-ignored) and refreshed automatically.

## What it does

| Step | Detail |
|---|---|
| check | Confirms four settings are on in QuickBooks (account numbers, class per line, custom transaction numbers, auto-apply credits off) and tells you where to change any that aren't. It only reads settings: the QuickBooks API replaces all settings at once, so writing one resets the others. |
| clean | Deletes the sample company's transactions and makes sample customers, vendors, products and unused accounts inactive. Anything tagged `FV:` is never touched. |
| setup | Reuses QuickBooks' own A/R, A/P and Retained Earnings accounts (renamed and numbered), creates everything else. |
| load | Opening journal entry at Oct 31, 2024, the 4 invoices and 3 bills open at that date, then every transaction from Nov 1, 2024 to Oct 31, 2026 as native QuickBooks records: invoices, payments, credit memos, refund receipts, bills, bill payments, expenses, deposits, transfers and journal entries. |
| verify | Pulls QuickBooks' trial balance at Dec 31, 2024, Dec 31, 2025, Sep 30, 2026 and Oct 31, 2026 and compares every Fernvale account to the ledger. Writes `.qbo/verify_report.md`. |
| close | Reminds you to set the closing date to Sep 30, 2026 in QuickBooks (Settings > Advanced > Accounting > Close the books), leaving October open. |

**Tagging:** every record the loader creates has a private note starting `FV:` followed by its ledger ID, so agents and people can trace any QuickBooks record back to the ledger and source systems.

## If something stops

- **Resuming:** the loader records the QuickBooks ID of everything it creates in `.qbo/state.json`. Rerunning `load` picks up where it stopped and never creates a record twice.
- **Errors:** if QuickBooks rejects a record, the loader stops and writes the details to `.qbo/load_errors.json`. The log is in `.qbo/loader.log`.
- **Fallbacks:** if QuickBooks refuses a deposit with a fee line, an expense or a transfer, the loader posts the same debits and credits as a journal entry. If it refuses the conversion item on account 1999, it uses subscription revenue plus a same-day reclass entry. Both are noted in the verify report.
- **Optional links:** linking a credit memo or write-off to its invoice is treated as optional. If it fails, the books are still correct and the invoice just shows as open.

## Accounting notes

- **Voided invoices** become credit memos dated the void date, linked to the original invoice with a $0 payment. A QuickBooks "void" would erase the invoice from its original month and change closed periods.
- **Stripe Clearing (1050)** is a bank-type account. Card payments are deposited there, and Stripe payouts are deposits from it into checking, net of fees.
- **Corporate card payments and payroll** are journal entries, as they would be with Ramp and Gusto syncing summaries.

## Tests (no QuickBooks needed)

```
python -m tests.test_plan            # every record posts exactly what the ledger says
python -m tests.test_loader_offline  # full run against a fake QuickBooks, including a resume
```
