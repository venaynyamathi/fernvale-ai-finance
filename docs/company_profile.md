# Fernvale Systems, Inc.: company profile

*Fernvale and every customer, employee, investor, landlord and professional-service firm in this dataset are fictional. Well-known software vendors (AWS, Slack, Salesforce, etc.) appear only as expense payees.*

## The business

| | |
|---|---|
| Product | **Fernvale Flow**, a workflow automation platform for operations teams at logistics, manufacturing and field-service companies |
| Founded | January 2022, Oakland, CA |
| Fiscal year | Calendar year |
| Funding | Seed $5M (Jan 2022), Series A $14M (Mar 2024), Series B $32M (May 2026) |
| ARR | ~$3.0M (Nov 2024) → ~$10.0M (Sep 2026) → ~$11.0M (Oct 2026) |
| Customers | ~260 at Oct 2026: ~170 SMB, ~77 Mid-Market, ~15 Enterprise |
| Headcount | 32 (Nov 2024) → 52 (May 2026) → 74 (Oct 2026) |
| Gross margin | ~76–85%, rising with scale |
| Monthly net burn | ~$0.4–0.9M |

## How it sells and bills

| Segment | Plan | List price (per seat / month) | Typical deal | Billing | Collection |
|---|---|---|---|---|---|
| SMB | Starter | $45 → $50 (Jan 2026) | 10–45 seats | ~60% monthly, rest annual prepaid | Card via Stripe |
| Mid-Market | Growth | $60 → $67 | 30–115 seats, 0–10% discount, optional onboarding package | Annual upfront, Net 30 | ACH |
| Enterprise | Enterprise | $72 → $80 | 130–420 seats, 5–25% discount, required implementation, ~30% on 2-year terms (billed annually) | Annual upfront, Net 45 | Wire |

New Mid-Market and Enterprise logos are driven by sales capacity: each ramped account executive closes a set number of deals a month, so hiring sales reps shows up in bookings a few months later. SMB is self-serve and grows steadily. Bookings peak at quarter-ends and in December.

## What management would tell you (the business storylines)

These are real events in the data. A good variance or flux workflow should find and explain them.

1. **Price increase, January 1, 2026.** List prices went up ~11–12% for new business. Existing customers get a 7% uplift at renewal.
2. **The Series B came late.** The FY2026 budget assumed a March close and hiring from April. The round actually closed May 19, 2026, so the company ran close to a hiring freeze until then and hired hard from June to mid-September (52 → 74 people). Expect opex under budget in H1, then catching up, and bookings lagging plan.
3. **Largest customer churned.** Halvorsen Freight Group (410 Enterprise seats) did not renew on August 1, 2026 after consolidating onto an in-house tool. Gross and net revenue retention dip after that.
4. **AWS region migration, July 2026.** A one-time data migration drove a large hosting spike that month.
5. **Datadog overage, September 2026.** A noisy deploy tripled log-ingestion costs for one month.
6. **Outsourced engineering scaled back.** The dedicated dev studio retainer dropped from $38k to $20k a month in July 2026 as in-house engineers were hired.
7. **New office.** The company moved into a larger office in August 2026 (rent ~$18k → ~$41k a month). The budget assumed July.
8. **Recurring calendar effects.** Merit increases every January. Payroll taxes are front-loaded early in each year as wage bases reset. The annual bonus is accrued monthly and paid in March. Salesforce renews (prepaid) every September. ZoomInfo and insurance renew annually.

There are also bookkeeping errors and loose ends planted in the books. Those are deliberately not listed here; finding them is the point. The answer key is generated locally into `private/` and kept out of the repository.

## Systems landscape

| Function | System (simulated) | Where it lives |
|---|---|---|
| CRM | Salesforce-style | `data/source_systems.sqlite` → `crm_*` |
| Subscription billing | Stripe Billing-style | `billing_*` |
| Card payments | Stripe | `stripe_*` |
| HRIS / payroll | Gusto-style | `hr_*`, `payroll_*`, `sales_commissions` |
| AP and corporate cards | Ramp-style | `spend_*` |
| Bank | Pacific Crest Bank (fictional) | `bank_*` |
| Planning | Board budget spreadsheet | `plan_*` |
| General ledger | **QuickBooks Online** | loaded from `build/books_as_booked.sqlite` |

## Accounting policies used in the books

- **Revenue:** subscription revenue is recognized ratably, by day, over each invoice line's service period. Onboarding and implementation fees are recognized evenly over 2 and 3 months respectively. Invoices are booked to deferred revenue, and a month-end entry trues deferred revenue up to the waterfall.
- **Expenses:** accrual basis. Bills are recorded on invoice date. Recurring vendors whose invoice arrives after month-end (AWS, legal) are accrued at month-end and reversed the following month.
- **Prepaids:** annual software and insurance bills are capitalized to prepaid and amortized by day over the service period.
- **Commissions:** 10% of first-year subscription ACV, accrued in the month the deal closes and paid the following month. They are expensed as incurred, not capitalized under ASC 340-40. Changing that policy is a good exercise.
- **Bonus:** 8% target for non-sales staff, accrued monthly, paid in March.
- **Fixed assets:** furniture and leasehold improvements depreciated straight-line. Laptops are expensed.
- **Departments:** every P&L line carries a QuickBooks class. Support salaries are classified in cost of revenue.
- **Not modeled (yet):** sales tax, ASC 842 lease accounting, stock-based compensation, income taxes.
