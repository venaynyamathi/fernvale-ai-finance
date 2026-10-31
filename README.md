# Fernvale Systems: an AI-native finance practice lab

A complete, fictional high-growth SaaS company built for practicing AI-native finance and accounting work: closing the books, reconciliations, revenue recognition, variance analysis, forecasting and board reporting, run by AI agents connected to **QuickBooks Online** and the company's operational systems through MCP.

The data is fake but not random. A rules-based simulation drives every number: sales capacity drives bookings, cohorts drive churn, headcount drives payroll and software spend, and usage drives hosting. The result has the trends, seasonality and one-off events of a real company, with a set of planted bookkeeping errors to find.

> Fernvale and every customer, employee, investor and service firm in this dataset are fictional.

## The company at a glance

| | Nov 2024 | Sep 2026 |
|---|---:|---:|
| ARR | ~$3.0M | ~$10.0M |
| Customers | ~90 | ~250 |
| Headcount | 32 | 74 |
| Funding to date | $19M | $51M |

Workflow automation software for operations teams, sold self-serve to SMB and through account executives to mid-market and enterprise. See **[docs/company_profile.md](docs/company_profile.md)** for the business, pricing, storylines and accounting policies.

## What's in the repo

```
generator/        the simulation (config.py holds every assumption)
validation/       tie-outs and SaaS metric checks -> validation/report.md
data/
  source_systems.sqlite   CRM, billing, Stripe, payroll, AP & cards, bank, FY2026 budget
  csv/                    the same tables as CSV
build/
  books_as_booked.sqlite  chart of accounts + general ledger to load into QuickBooks
docs/             company profile, data dictionary, roadmap
private/          answer key (generated locally, git-ignored)
```

**Two layers, like a real company:**

1. **Source systems** (`data/source_systems.sqlite`): the operational detail. Subscriptions and invoices, Stripe charges and payouts, payroll runs, vendor bills, card swipes, bank statements, CRM deals and the board budget. See **[docs/data_dictionary.md](docs/data_dictionary.md)**.
2. **The books** (`build/books_as_booked.sqlite` → QuickBooks Online): opening balances at Nov 1, 2024 and every transaction through Oct 31, 2026. Closed through **September 2026**. **October 2026 is open**, with no month-end entries yet, and contains planted errors. That's where the agents go to work.

## Rebuild from scratch

```bash
pip install -r requirements.txt
python -m generator.build       # regenerates data/, build/, private/ and docs/data_dictionary.md
python -m validation.checks     # writes validation/report.md
```

The build uses a fixed random seed, so the same inputs give identical output. Change an assumption in `generator/config.py` and the whole company regenerates consistently.

## What the validation proves

- The trial balance nets to zero, and the GL ties to the source systems at every month-end: cash to bank statements, AR to open invoices, AP to unpaid bills, card liability to card activity, Stripe clearing to unpaid-out charges.
- ARR, customer counts, net and gross retention are recomputed from billing events.
- Monthly P&L, gross margin and cash burn stay in believable ranges.

## Roadmap

1. ✅ Company design, simulation, source-system database, validation
2. ⬜ QuickBooks Online sandbox: clear Intuit's sample data, create the chart of accounts and classes, load customers, vendors and history
3. ⬜ MCP connections: QuickBooks plus a SQLite server for the source systems
4. ⬜ Agentic workflows: October close, deferred revenue roll-forward, bank/Stripe/AR/AP reconciliations, accruals and prepaids, flux and budget-vs-actual analysis, rolling forecast, board metrics pack

See [docs/roadmap.md](docs/roadmap.md).
