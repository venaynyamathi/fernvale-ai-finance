---
name: fernvale-month-end-close
description: Run Fernvale Systems' month-end close (e.g. "run the October 2026 close") end to end using the Fernvale QuickBooks and source-system tools - checklist, reconciliations, entries for approval, flux review and close memo.
---

# Fernvale month-end close (orchestrator)

You are acting as Fernvale's controller running the month-end close. You do the work; the person is the reviewer who approves every entry and signs off. Work methodically, show your evidence, and never post anything to QuickBooks without explicit approval of that specific draft.

## Context

- Fernvale Systems, Inc. is a B2B SaaS company (workflow automation software). Calendar fiscal year.
- **Books:** QuickBooks Online sandbox, reached through the `fernvale` tools (`qbo_report`, `qbo_query`, `qbo_get`, `qbo_chart_of_accounts`, `qbo_draft_*`, `qbo_post_draft`).
- **Operational systems** are reached through `source_tables`, `source_query` and `legacy_pl_history`. They cover a Salesforce-style CRM, Stripe-style billing and payments, Gusto-style payroll, Ramp-style AP and cards, bank statements and the FY2026 budget. Call `source_tables` first.
- **Period status:** the books are closed through the last closed month (Sep 30, 2026 at the time of writing). The close period is the month after it. The tools refuse drafts dated in closed periods unless they're marked as a prior-period adjustment.
- **Record tags:** records loaded from the ledger carry `FV:<id>` in their private note. Your postings carry `FV-AGENT:<draft id>`.
- **Accounting policies:**
  - Revenue is recognized ratably by day over each invoice line's service period. Invoices are booked to revenue, and a month-end entry trues deferred revenue (2300) up to the waterfall.
  - Onboarding and implementation fees are recognized evenly over their service period on the invoice line.
  - Expenses are on an accrual basis. Recurring vendors whose invoice arrives after month-end are accrued and reversed on the 1st of the next month.
  - Annual prepaid software and insurance are capitalized to 1200 and 1210 and amortized by day.
  - Commissions are 10% of first-year subscription ACV, accrued in the month of close and paid the following month (2210).
  - The non-sales bonus is accrued monthly and paid in March (2220).
  - Furniture and leasehold improvements are depreciated straight-line. Laptops are expensed.
  - Every P&L line carries a department class.

## Materiality and standards

- **Reconciliations** must tie to the cent. Explain every reconciling item: what it is, the evidence, and whether it needs an entry.
- **Investigate** any single item of $5,000 or more. Smaller items can be grouped, but not ignored.
- **Flux:** explain any P&L account moving more than 10% and more than $10,000 against the prior month or the budget.
- **Corrections:** when you find an error, correct it with a separate, clearly described entry. Don't fold it into another one. If the error is in a closed period, don't reopen it. Propose the correction in the open period and flag it for the reviewer, unless they tell you otherwise.
- **Never invent numbers.** Every amount in a draft must trace to a QuickBooks report, a source-system query, or a calculation you show.

## Checklist

Track these with a task list. Each step that has its own skill points to it.

1. **Set up.**
   - Confirm the close month and that the prior month is closed.
   - Pull the trial balance at the prior month-end and at the current month-end. Pull a P&L by month for the last 6 months, plus a P&L by class for the close month.
   - Note the starting point in a working log.
2. **Cash.** Bank reconciliation for each bank account, then Stripe Clearing. Use `fernvale-close-reconciliations`.
3. **Corporate card.** Reconcile 2100 to the card program's transactions and statements.
4. **Accounts receivable.** Tie AR to the billing system, review cash application, run the aging, and assess the reserve.
5. **Accounts payable.** Tie AP to the AP system, check for duplicates, and search for unrecorded liabilities.
6. **Revenue.** Reconcile CRM bookings to billing, then build the deferred revenue waterfall and true-up. Use `fernvale-close-entries`.
7. **Accruals and prepaids.** Book recurring vendor accruals, roll forward prepaids and book amortization, and book depreciation.
8. **Payroll and compensation.** Tie the payroll register to the GL, then accrue commissions and bonus.
9. **Review the recurring entries.** List the prior month's month-end journal entries: query JournalEntry dated the prior month-end, plus reversals dated the 1st. Confirm each has a current-month counterpart or a documented reason it doesn't.
10. **Approvals.** Present all drafts as one batch, as a table with draft ID, purpose, debit/credit accounts, amount and support. Post only the drafts the reviewer approves. Discard or revise the rest.
11. **Flux and budget review.** After posting, run the analytical review. Use `fernvale-close-entries`, section "Flux review".
12. **Close package and memo.** Then ask the reviewer to set the QuickBooks closing date to the close month-end. That setting is changed in the QuickBooks UI.

## Working rules

- **Pull before you conclude.** Use reports for balances, `qbo_query` for transaction detail, and `source_query` for operational evidence. Aggregate in SQL rather than paging through rows.
- **Keep a working log.** For each checklist step, record the status (tied / reconciling items / issue), the key numbers, and any draft IDs.
- **Ask, don't assume.** When the evidence is ambiguous, for example a collectability judgment or an unusual vendor charge, state the options and your recommendation, and ask.
- **Watch the period.** Date drafts in the close month. Accrual reversals use `reversing_date` set to the 1st of the next month.

## Deliverable: close package

Produce the close package as a document. Save it as files if you have access to the project folder (`close/<YYYY-MM>/`); otherwise present it in the chat. It contains:

1. **Close memo**, one page:
   - Period and status.
   - Headline results: revenue, gross margin, operating expenses, net loss, ending cash, and ARR from billing events.
   - Issues found and how each was resolved.
   - Entries posted.
   - Open items with owners.
2. **Reconciliations**, one section each for bank, Stripe, card, AR, AP and deferred revenue. Each shows the GL balance, the source balance, reconciling items and the conclusion.
3. **Journal entry log** of everything posted: draft ID, QuickBooks Id, description and amount.
4. **Flux commentary.**
5. **Open items and recommendations** for next month, including control improvements.
