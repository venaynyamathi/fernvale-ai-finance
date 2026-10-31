# Roadmap

## 1. Data ✅

Simulation, source-system database, ledger, budget and validation are done. Rebuild with `python -m generator.build`.

## 2. QuickBooks Online sandbox ✅

Loaded Oct 31, 2026 with `python -m qbo_loader all`: sample data cleaned, 49 accounts, 8 classes, 3 items, 320 customers, 42 vendors, the opening balances and 5,990 transactions as native QuickBooks records (invoices, payments, credit memos, refund receipts, bills, bill payments, expenses, deposits, transfers, journal entries). No record needed a fallback. Trial balance matches the ledger to the cent at Dec 31, 2024, Dec 31, 2025, Sep 30, 2026 and Oct 31, 2026. See [qbo_load_verification.md](qbo_load_verification.md).

- [ ] Set the closing date to Sep 30, 2026 in QuickBooks (manual; the API would reset other settings).

## 3. MCP connections

- [x] Fernvale MCP server (`fernvale_mcp/`): QuickBooks reports and queries, draft-then-confirm writes with closed-period protection, read-only source systems, no access to `private/` or the generator. See [mcp_server.md](mcp_server.md).
- [ ] Add it to the Claude desktop app and test live

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
