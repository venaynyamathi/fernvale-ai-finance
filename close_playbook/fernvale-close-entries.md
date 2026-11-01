---
name: fernvale-close-entries
description: Month-end entries and review for Fernvale's close - deferred revenue waterfall and true-up, CRM-to-billing bookings check, accruals, prepaids, depreciation, commissions, bonus, and the flux and budget-vs-actual review.
---

# Fernvale close: entries and analytical review

Every entry here is a draft for the reviewer. Each one needs a calculation the reviewer can follow, and every input must come from a query or report you show. Date entries on the last day of the close month; accruals reverse on the 1st of the next month.

## 1. Revenue

### Bookings: CRM to billing

1. Take the Closed Won opportunities with a close date in the month (`crm_opportunities`).
2. Each should have a billing subscription (`billing_subscription_id`). Compare contract seats, term, start date and amount with the subscription (`billing_subscriptions`, `billing_subscription_events`) and its first invoice.
3. Report any mismatch, including seats, price, discount, missing subscriptions, and billing that started without a closed deal. Quantify the revenue and billing impact. A mismatch usually means re-billing or correcting the CRM; recommend which. Don't book revenue for it.

### Deferred revenue waterfall and true-up (2300)

1. **Build the waterfall** from `billing_invoice_lines` joined to `billing_invoices`.
   - **Include** lines on invoices dated on or before month-end.
   - **Exclude** invoices voided or written off on or before month-end.
   - **Unearned portion** of each line at month-end: amount × days of the service period after month-end ÷ total days in the period, both counted inclusively.
2. **Split** the unearned total into subscription (with proration lines) and services. Services link to 4100 and everything else to 4000.
3. **Compare** with the 2300 balance in QuickBooks. Draft the true-up between 2300 and 4000/4100. Show the waterfall totals, the GL balance, the difference by revenue account, and a roll-forward: opening balance + billings − revenue recognized = closing balance.
4. **Sanity check:** recognized revenue for the month should be close to MRR from billing events (`billing_subscription_events`, latest `mrr_after` per subscription) plus services revenue. Explain any large gap.

## 2. Accruals

1. **Find the reversals.** List last month's accruals and their reversals on the 1st of this month: query JournalEntry dated the prior month-end and the 1st.
2. **Accrue this month's costs.** For each vendor in `spend_vendors` with `accrue_monthly = 1`, and any other vendor whose invoice for this month hasn't arrived:
   - Estimate the month's cost from the trend in recent invoices (`spend_bills`), adjusted for known drivers. Hosting tends to scale with revenue; legal fees with activity.
   - If an invoice dated after month-end covers this month, use its actual amount.
   - Draft with `reversing_date` set to the 1st of the next month.
3. **Other accruals:** anything the unrecorded-liabilities search found that isn't a bill yet.

## 3. Prepaids (1200 Prepaid Software, 1210 Prepaid Insurance)

1. **Build the schedule.** Find every bill or card charge with a service period longer than one month (`spend_bills.service_period_start`/`service_period_end`). Each one's balance at month-end is amount × remaining days ÷ total days.
2. **Roll forward each account:** opening balance + new prepaids − amortization = closing balance. Compare with QuickBooks.
3. **Book this month's amortization** for each item: amount × days of service in the month ÷ total days. Charge it to the account and class the expense belongs to.
4. **If the roll-forward doesn't tie,** find the cause, such as a multi-month charge expensed directly or amortization missed, and correct it by moving the unexpired portion to prepaid or booking the missing amortization. If the original posting is in a closed period, book the correction in the open month and flag it.

## 4. Fixed assets and depreciation (1500, 1550, 6950)

1. **Book this month's depreciation** consistent with the established monthly entry: same method and life, recomputed if assets changed. Find the prior entry with `qbo_query` on JournalEntry, or the GL detail for 6950.
2. **Check additions** in the month: any bill coded to 1500. Confirm they're capital in nature and that depreciation starts in the right month.

## 5. Payroll and compensation

1. **Payroll register to GL.** For each payroll run paid in the month (`payroll_runs`, `payroll_items`):
   - Gross pay by department should match salary and wage expense by class. Support's pay goes to 5100/5110.
   - Employer taxes should match payroll tax expense.
   - The cash funded should match the bank debits.
   - Check that no one is paid after their `termination_date`, and that new hires appear from their `hire_date`.
2. **Commissions (2210):**
   - Accrued commissions at month-end should equal commissions earned on deals closed in the month and paid next month (`sales_commissions`, `pay_month`).
   - Commissions paid this month should have cleared last month's accrual.
   - Draft the accrual between 6030 and 2210 (class Sales).
3. **Bonus (2220):** accrue this month's share of the annual bonus for non-sales staff, at the target percentage of base salary for active employees. Follow the established monthly entry and recompute it for current headcount and salaries (`hr_employees`). The class follows each employee's department; Support goes to 5100.
4. **Benefits:** confirm the month's benefits bill is booked and roughly matches headcount × the per-employee cost.

## 6. Flux review

Run this after the entries are posted.

1. **Pull the P&L** by month for the close month and the prior 3 months, plus the close month by class. Pull the budget for the month from `plan_budget_fy2026` (amounts are in each account's natural sign).
2. **Flag** any account or department moving more than 10% and more than $10,000 against the prior month, the 3-month average, or the budget.
3. **Explain each flag with evidence:** the transactions behind it (`qbo_report` with `ProfitAndLossDetail` or `GeneralLedger`) and the operational driver (headcount, ARR, vendor invoices, one-off events).
   - "Timing" or "one-off" is only an explanation if you can name the transaction.
   - An explanation that would require an expense to sit in an odd account or department is a coding question. Raise it, and propose a reclass if it's wrong.
4. **Balance sheet flux:** explain large month-over-month moves in every balance sheet account. The reconciliations cover most of them.
5. **Key metrics** for the memo:
   - Revenue.
   - Gross margin %, with support in cost of revenue.
   - Opex by function (R&D, S&M, G&A, from the class mapping in `ref_departments`).
   - Net loss and ending cash.
   - Ending ARR and net new ARR from billing events, with NRR and GRR if you can compute them.
   - Burn and runway at the current burn.
6. **Budget variance table** by P&L line with a short driver note for each material variance. The budget assumptions are in `plan_assumptions`.
