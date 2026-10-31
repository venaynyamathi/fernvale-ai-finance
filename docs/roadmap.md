# Roadmap

## 1. Data ✅

Simulation, source-system database, ledger, budget and validation are done. Rebuild with `python -m generator.build`.

## 2. QuickBooks Online sandbox

- [ ] Create an Intuit Developer account and an app with the `com.intuit.quickbooks.accounting` scope. Connect the sandbox company and keep the credentials in a local `.env` (git-ignored).
- [ ] Neutralize Intuit's sample company: make sample accounts, customers, vendors and items inactive.
- [ ] Create the 49 accounts and 8 classes (`build/qbo_load/01_chart_of_accounts.csv`, `02_classes.csv`).
- [ ] Create customers and vendors, plus service items for subscription and services revenue and a "Conversion" item mapped to 1999 Conversion Clearing.
- [ ] Post the opening journal entry dated Oct 31, 2024 (`04_opening_journal_entry`).
- [ ] Load the open invoices and bills at the cutoff (`05`, `06`) against 1999. Confirm 1999 is zero.
- [ ] Load every transaction from Nov 1, 2024 in date order (`gl_entries_to_load`): invoices, payments, bills, bill payments, card activity, deposits, transfers and journal entries.
- [ ] Tag every loaded record (for example `FV:` in the memo or private note) so agents can filter out sandbox noise.
- [ ] Verify: QuickBooks trial balance at Sep 30 and Oct 31, 2026 matches the as-booked ledger.
- [ ] Set a closing date of Sep 30, 2026.

## 3. MCP connections

- [ ] QuickBooks Online MCP server (Intuit's sandbox server or a community server with draft-and-confirm writes)
- [ ] SQLite MCP server pointed at `data/source_systems.sqlite`
- [ ] Rule for honest testing: agents get QuickBooks plus the source database, never `private/` or the generator code.

## 4. Workflows to build

| Workflow | Inputs | Output |
|---|---|---|
| October close checklist & orchestration | everything | close status, JEs proposed for approval |
| Deferred revenue waterfall & roll-forward | billing invoice lines | DR schedule, true-up JE |
| Bank reconciliation | bank_transactions vs QBO | rec + reconciling items |
| Stripe reconciliation | stripe_* vs QBO clearing | payout-level tie-out |
| AR aging & cash application review | billing vs QBO AR | aging, reserve proposal |
| AP review & unrecorded liabilities | spend_bills vs QBO AP | duplicates, accruals |
| Accruals & prepaid amortization | bills with service periods | JEs |
| Payroll & commission accruals | payroll, sales_commissions | JEs |
| Flux analysis | QBO P&L by month | commentary on material moves |
| Budget vs actual | plan_budget_fy2026 vs QBO | variance report with drivers |
| SaaS metrics pack | billing events, CRM | ARR bridge, NRR/GRR, CAC payback, burn multiple |
| Rolling forecast | all of the above | 18-month forecast and cash runway |

## 5. Portfolio

- [ ] Before making the repo public: confirm `private/` was never committed and no secrets are in history.
- [ ] Showcase page with the company, workflows and sample outputs; short screen recordings of agent runs.
