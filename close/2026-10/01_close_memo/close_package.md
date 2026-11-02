# Fernvale Systems — October 2026 Close Package

Nov 1, 2026 · Vinny (reviewer) · Prepared by Claude (close agent)

> Exported from the Claude Doc "Fernvale Systems — October 2026 Close Package". Workpaper references point to files in this folder.

## Close memo

October 2026 is closed, and QuickBooks is locked through October 31, 2026. Every balance sheet account ties to its source system after 21 entries posted on November 1. Net loss was $595.8k on $967.7k of revenue, and ending ARR was $11.00M.

**Period status.** September 2026 was the last closed month. All October entries are dated in October, and the accrual reversals are dated November 1. Three corrections fix errors from closed months. They're booked in October and flagged; no prior period was reopened.

### Headline results

| Metric | Oct 2026 reported | Oct 2026 excl. prior-period corrections | Sep 2026 | Oct budget |
| --- | --- | --- | --- | --- |
| Revenue | $967,700 | $967,700 | $818,024 | $958,215 |
| Gross margin | 77.6% | 84.2% | 78.5% | 84.0% |
| Operating expenses | $1,460,343 | $1,597,241 | $1,709,176 | $1,611,742 |
| Net loss | ($595,755) | ($668,408) | ($949,074) | ($693,755) |
| Ending cash (1000 + 1010 + 1050) | $34,725,310 | | $35,771,365 | |
| Ending ARR | $11,003,295 | | $10,007,448 | $11,388,586 |
| Net new ARR | $995,846 | | $596,074 | $620,000 |

Reported results are the headline for the board. The excluded column is supplementary only. It removes three items:

- the June AWS reclass ($63,677 moved into hosting cost),
- the Salesforce prepaid correction ($64,823 removed from software expense),
- the FV-11156 deferred revenue fix ($8,397 removed from bad debt).

It also removes $568 of sandbox demo inventory. Gross margin counts Support pay in cost of revenue.

Cash fell $1.05M in October, which is about 33 months of runway at that rate. The October outflow included the $67.8k annual Salesforce renewal.

ARR is $385k below plan even though October's net new ARR beat plan by $376k. The gap carries over from earlier months.

October ARR movements:

- $920k gross new ARR from 18 new logos. Yarrow Distribution ($362k) and Talbot Electric ($219k) account for most of it.
- $179k of expansion.
- $103k of churn and contraction.

From the September base, that's a monthly gross revenue retention of 99.0% and net revenue retention of 100.8%.

### Issues found and resolved

1. **Unrecorded Stripe chargeback, $10,726.44.** Payout `po_00688` netted out a $10,711.44 dispute and a $15 fee, but the deposit was booked gross. Booked to bad debt and bank fees, which ties the bank.
2. **Payment applied to the wrong customer, $44,788.32.** Sawtooth Plumbing Holdings' ACH for FV-12064 had been recorded to Sawtooth Wholesale Co. Re-pointed and applied, which clears a false credit and an open invoice.
3. **Duplicate vendor bill, $23,531.81.** Marlow & Pierce INV-1817 was entered twice, once as "INV1817". The unpaid duplicate is deleted, which ties AP.
4. **Deferred revenue left on a written-off invoice, $8,397.37 (prior period).** FV-11156 was written off in April. The full $71,280 went to bad debt, but its unearned portion stayed in 2300. Corrected in October.
5. **Annual Salesforce renewal expensed, $64,823.36 (prior period).** The $67,795 renewal for 9/15/26–9/14/27 was expensed in September. Moved to prepaid and amortized from October.
6. **AWS bill miscoded, $63,677.46 (prior period).** The June AWS bill, booked in July, went to software expense under Marketing instead of hosting cost. Reclassed this year to date.
7. **Revenue true-up, $410,820.34.** October billings exceeded revenue earned. Deferred revenue was trued up to the billing waterfall of $5,093,961.43.

### Reviewer decisions (agreed November 1)

- **Garland Water Works, $321,200, 50 days past due.** No reserve this month. Collections and the account owner will escalate this week, and the reserve will be revisited at the November close.
- **Norcross renewal under-billed by 40 seats, $29,582 a year.** No entry. Billing will confirm the order form and issue an add-on invoice.
- **Marlow & Pierce October accrual.** $13,100 at the July–September run-rate stands.
- **Board headline.** October is reported as reported, with prior-period corrections included.

### Entries posted

There are 21 postings: 13 journal entries, 4 accruals each with a November 1 reversal, one payment fix and one bill deletion. The journal entry log below lists them.

October's P&L was reduced by these items:

- the revenue true-up, $410.8k,
- the $142.4k of accruals,
- commissions of $61.2k,
- bonus of $69.4k,
- amortization and depreciation of $16.6k.

### Open items

The last section lists open items with owners. The most urgent is collecting Garland's $321k. The QuickBooks closing date was set to October 31, 2026 on November 1.

## Reconciliations

All seven accounts tie to the cent after the posted entries. Balances are as of October 31, 2026, after close. The summary of every balance sheet account is in `02_reconciliations/00_reconciliation_summary.xlsx`.

| Account | GL balance | Source balance | Difference | Conclusion | Workpaper |
| -------------- | -------------- | ---------------- | ---------- | ---------- | ---------------------- |
| 1000 Operating Checking | $2,547,011.53 | $2,547,011.53 bank | $0.00 | Tied after entries | `1000_1010_bank_reconciliation.xlsx` |
| 1010 Treasury Money Market | $32,170,561.74 | $32,170,561.74 bank | $0.00 | Tied | `1000_1010_bank_reconciliation.xlsx` |
| 1050 Stripe Clearing | $7,737.15 | $7,737.15 Stripe | $0.00 | Tied | `1050_stripe_clearing.xlsx` |
| 2100 Ramp Corporate Card | $190,752.80 | $190,752.80 Ramp | $0.00 | Tied | `2100_corporate_card.xlsx` |
| 1100 Accounts Receivable | $2,273,263.08 | $2,273,263.08 billing | $0.00 | Tied after entries | `1100_accounts_receivable.xlsx` |
| 2000 Accounts Payable | $43,531.81 | $43,531.81 AP system | $0.00 | Tied after entries | `2000_accounts_payable.xlsx` |
| 2300 Deferred Revenue | $5,093,961.43 | $5,093,961.43 waterfall | $0.00 | Tied after entries | `2300_deferred_revenue_waterfall.xlsx` |

### Bank: 1000 Operating Checking and 1010 Treasury Money Market

All 42 October lines on the operating account matched a GL entry by date, amount and counterparty. There are no deposits in transit and no outstanding payments.

The one difference was payout `po_00688` on October 19. The bank received $450.68. The GL had recorded $11,177.12, because the $10,711.44 dispute and $15 fee were never booked. Entry D1031-B7B9 (QBO 6139) books them.

All seven customer ACH payers agree to the QuickBooks customer except Sawtooth, which is fixed by D1031-446A. Payroll debits agree to Gusto runs PR-202610-1 and PR-202610-2.

Treasury had two lines: $113,627.86 of interest and a $1.2M transfer to operating. Both are in the GL.

### Stripe clearing: 1050

The balance is $6,487.15 of charges in payout `po_00698`, created October 30 and not yet arrived, plus a $1,250.00 charge from October 30 that isn't yet in a payout.

Nineteen October payouts arrived. Each matches the bank at its net amount, with gross charges and fees split to 5200. The only dispute was `dp_1Q8fernvale`, $10,711.44, reason product_not_received. It's now booked to 6900.

Three card payments failed, totaling $4,409.30: FV-12115, FV-12166 and FV-12173. Billing retried and collected all three in October, and none produced a Stripe charge. There were no refunds in October.

### Corporate card: 2100

| Component | Amount |
| --- | --- |
| October statement STMT-202610, open, due early November | $180,915.52 |
| October-dated charges posting to the November statement | $9,837.28 |
| GL balance | $190,752.80 |

The September statement, $169,481.34, was paid October 6 and cleared the prior balance. Every October card charge is in QuickBooks at its card amount, and the account and class agree to the Ramp category and department.

Five charges over $75 have no receipt, totaling $2,196.31:

- Amazon Business, $1,025.16
- 1Password, $591.26
- a customer dinner, $367.08
- two Uber rides, $212.81

These are policy follow-ups, not entries. Advertising was $107,660.46 across five Google and LinkedIn charges, all with receipts.

### Accounts receivable: 1100

AR ties to the 19 open billing invoices in total and customer by customer. Before the fix, the totals hid two offsetting errors: Sawtooth Wholesale showed a $44,788.32 credit, and Sawtooth Plumbing showed the same invoice still open.

| Aging bucket | Amount | Invoices |
| --- | --- | --- |
| Current | $1,873,391.68 | 16 |
| 1–30 days past due | $78,671.40 | 2 |
| 31–60 days past due | $321,200.00 | 1 |
| Over 60 days | $0.00 | 0 |

One invoice is 30 or more days past due and over $25,000: Garland Water Works, FV-11858, $321,200. It's 50 days past due. It's the first invoice on a new 325-seat Enterprise subscription that started August 1, with no payment ever attempted, and the subscription is active. Per the reviewer, there's no reserve this month.

There were no write-offs or voids in October.

### Accounts payable: 2000

AP holds two bills, which match the approved, unpaid bills in Ramp:

- Marlow & Pierce INV-1817, $23,531.81
- Kaltwerk KAL-2610590, $20,000.00

The duplicate Marlow & Pierce bill (QBO 5975) is deleted.

The search for unrecorded liabilities turned up four items, all accrued as of October 31 and reversing November 1:

- Talentridge placement fee, $28,400. The offer was accepted 10/12 and the bill is pending approval.
- AWS October usage, $86,900.
- Marlow & Pierce October legal, $13,100.
- Brightquarry October content retainer, $14,000. This vendor bills at month-end and no October invoice had arrived.

### Deferred revenue: 2300

| Roll-forward | Amount |
| --- | --- |
| Opening balance, 9/30 | $4,691,538.46 |
| Correction: FV-11156 written off with deferred revenue left in 2300 | ($8,397.37) |
| October billings | $1,378,520.73 |
| Revenue recognized | ($967,700.39) |
| Closing balance, 10/31 | $5,093,961.43 |

The closing balance equals the waterfall: subscription $4,956,688.38 and services $137,273.05. The waterfall excludes voided, refunded and uncollectible invoices.

Subscription revenue of $889,703.77 is 1.6% above average October MRR of $875,448, which is consistent with mid-month new logos billed from their start dates. Services revenue of $77,996.62 traces to ten implementation lines; Garland, Talbot Electric and Redfern account for 66% of it.

## Journal entry log

Twenty-one postings went to QuickBooks on November 1, 2026, all approved by the reviewer. Entries marked ⚑ correct closed periods and are booked in October. Lines and calculations are in `03_journal_entries/je_support.xlsx`.

| Draft ID | QBO Id | Date | Description | Debit / credit | Amount |
| ------------ | ------ | ------------ | ------------------------------ | -------------- | ------------ |
| D1031-B7B9 | 6139 | 2026-10-19 | Stripe dispute dp_1Q8fernvale withdrawn from payout po_00688 | 6900 + 6850 / 1000 | $10,726.44 |
| D1031-446A | 6037 | 2026-10-21 | Re-point Sawtooth ACH to Sawtooth Plumbing Holdings, apply to FV-12064 | Payment update | $44,788.32 |
| D1031-907D | 5975 | 2026-10-13 | Delete duplicate Marlow & Pierce bill INV1817 | Bill deleted | $23,531.81 |
| D1031-71D6 ⚑ | 6140 | 2026-10-31 | Remove unearned balance of written-off FV-11156 | 2300 / 6900 | $8,397.37 |
| D1031-E141 | 6141 | 2026-10-31 | Deferred revenue true-up to waterfall | 4000 + 4100 / 2300 | $410,820.34 |
| D1031-124A | 6142 | 2026-10-31 | Accrue AWS October usage | 5000 / 2200 | $86,900.00 |
| D1031-124AR | 6143 | 2026-11-01 | Reverse AWS accrual | 2200 / 5000 | $86,900.00 |
| D1031-376E | 6144 | 2026-10-31 | Accrue Marlow & Pierce October legal | 6600 / 2200 | $13,100.00 |
| D1031-376ER | 6145 | 2026-11-01 | Reverse Marlow & Pierce accrual | 2200 / 6600 | $13,100.00 |
| D1031-07AB | 6146 | 2026-10-31 | Accrue Brightquarry October content retainer | 6100 / 2200 | $14,000.00 |
| D1031-07ABR | 6147 | 2026-11-01 | Reverse Brightquarry accrual | 2200 / 6100 | $14,000.00 |
| D1031-8FD2 | 6148 | 2026-10-31 | Accrue Talentridge placement fee TAL-2610992 | 6700 / 2200 | $28,400.00 |
| D1031-8FD2R | 6149 | 2026-11-01 | Reverse Talentridge accrual | 2200 / 6700 | $28,400.00 |
| D1031-BF83 ⚑ | 6150 | 2026-10-31 | Salesforce renewal: move unexpired 9/30 portion to prepaid | 1200 / 6200 | $64,823.36 |
| D1031-27E0 | 6151 | 2026-10-31 | Amortize Salesforce prepaid (31/365) | 6200 / 1200 | $5,757.95 |
| D1031-1F6D | 6152 | 2026-10-31 | Amortize ZoomInfo prepaid (31/365) | 6200 / 1200 | $2,344.11 |
| D1031-8450 | 6153 | 2026-10-31 | Amortize Keystone prepaid insurance (31/365) | 6620 / 1210 | $5,435.62 |
| D1031-2864 | 6154 | 2026-10-31 | Depreciation: $186,400 over 60 months | 6950 / 1550 | $3,106.67 |
| D1031-A52D | 6155 | 2026-10-31 | Accrue commissions on 8 October deals (10% of first-year ACV) | 6030 / 2210 | $61,229.94 |
| D1031-9BF6 | 6156 | 2026-10-31 | Accrue non-sales bonus (8% of base, monthly) | 6040 + 5100 / 2220 | $69,410.00 |
| D1031-CF36 ⚑ | 6157 | 2026-10-31 | Reclass June AWS bill from software (Marketing) to hosting | 5000 / 6200 | $63,677.46 |

Prepaids roll forward to QuickBooks within rounding. 1200 Prepaid Software is $63,677.98: Salesforce $59,065.41 plus ZoomInfo $4,612.60, a 3¢ day-count rounding difference. 1210 Prepaid Insurance is $16,131.48 against a schedule of $16,131.51.

Every September recurring entry has an October counterpart. Salesforce amortization now runs on the September 2026 renewal, because the prior contract ended September 14.

## Flux and budget commentary

October's net loss beat budget by $98k on a reported basis. Excluding the prior-period corrections, the beat is $25k. The full variance table is in `04_variance_analysis/flux_and_budget_variance.xlsx`.

The drivers:

- services revenue, $43k over budget,
- salaries, $70k under budget from lower headcount cost,
- advertising, $53k over budget,
- underlying software spend, $4k over budget.

Flagged lines moved more than 10% and more than $10,000 against September or the budget.

| Account | Oct actual | vs Sep | vs budget | Driver |
| ---------------------- | ------------ | ---------------- | ---------------- | ---------------------------------------- |
| 4000 Subscription revenue | $889,704 | +$98,540 (+12.5%) | ($33,512) (−3.6%) | Average MRR rose to $875k from 18 new logos: Yarrow from 10/17 at $30.2k MRR, Talbot Electric from 10/1 at $18.2k MRR, plus 11 expansion renewals. Below budget because ending ARR trails plan by $385k. |
| 4100 Professional services | $77,997 | +$51,136 | +$42,997 | Ten implementation lines are earning at once. Garland ($18.9k, ends 10/31), Talbot Electric ($17.7k) and Redfern ($14.6k) are 66%. The budget assumes a flat $35k a month. |
| 5000 Hosting & infrastructure | $159,643 | +$43,019 | +$68,207 | Includes the $63,677 June AWS reclass (⚑). Excluding it, $95,965, or 10.8% of subscription revenue against a 9.2% plan ratio and $4.5k over budget. October includes the $86,900 AWS accrual, the September AWS bill $4,333 below its accrual, and $13,398 of Twilio and Datadog on the card. |
| 6000 Salaries & wages | $1,033,750 | +$11,168 (+1.1%) | ($70,107) (−6.4%) | Not flagged. 74 employees against a plan of 74. Headcount is on plan, so the gap is pay levels or hire timing in the plan build. The plan's salary assumptions aren't in the plan data and still need explaining. There were no new hires in October. |
| 6030 Sales commissions | $61,230 | ($3,818) | ($22,470) (−26.8%) | Commissionable October bookings were $612k of first-year ACV across 8 deals, against roughly $837k implied by the budget. Renewals carry no commission. |
| 6200 Software & subscriptions | ($109,214) | ($191,602) | ($124,718) | Negative because of two prior-period corrections (⚑): the Salesforce prepaid ($64,823) and the AWS reclass out of Marketing ($63,677). Underlying $19,287 (card tools $11,185 plus amortization $8,102), $3.8k over budget. September included the full $67,795 Salesforce renewal. |
| 6300 Advertising & marketing programs | $107,660 | +$3,243 (+3.1%) | +$52,529 (+95.3%) | Google Ads $72,527 and LinkedIn Ads $35,133, all on the card and coded to Marketing. Spend has run at about twice plan since September. Worth confirming the paid budget with Marketing. |
| 6310 Events & sponsorships | $0 | ($42,000) | $0 | September had the OpsForward Summit booth. None in October, in line with budget. |
| 6600 Legal fees | $13,132 | ($10,181) (−43.7%) | +$6,632 | October is the $13,100 run-rate accrual, plus $32 over the September accrual once the actual bill arrived. September's $23.3k reflected higher activity. |
| 6700 Recruiting | $31,100 | +$100 | +$8,454 | Not flagged against budget. The $28,400 Talentridge fee for a Senior AE starting 11/2, plus LinkedIn Recruiter. 60% below the July–September average, which carried the August agency placements. |
| 7000 Interest income | $113,628 | ($4,380) (−3.7%) | +$878 | Not flagged. Slightly lower monthly yield. Within budget. |

All other lines are within threshold.

Two lines deserve a note even though they're under it. Bad debt of $2,314 is the $10,711 chargeback net of the $8,397 FV-11156 correction. Computer equipment was zero against a $4,800 budget, because there were no October hires.

The $568 "Inventory Shrinkage (deleted)" line in cost of revenue is QuickBooks sandbox demo data, not Fernvale activity.

**Opex by function, October reported.** The figures excluding prior-period corrections are in parentheses.

- R&D: $671,156
- S&M: $576,010 ($704,510)
- G&A: $213,178 ($221,575)

The Sales and Marketing classes carry the Salesforce and AWS corrections, so S&M looks about $128k lighter than it is.

**Balance sheet movements.** Most of the month-over-month change is explained above.

- Deferred revenue rose $402k: billings exceeded revenue.
- AR rose $758k: October annual invoices to Yarrow ($397k) and Norcross ($218k), with Garland's $321k still uncollected.
- Treasury fell $1.09M: a $1.2M transfer to operating, less $114k of interest.
- Accrued expenses rose to $142,400, accrued commissions to $61,230 and accrued bonus to $567,257.
- Prepaid software rose $56.7k from the Salesforce correction, net of amortization.

## Open items and recommendations

These items carry into November. The QuickBooks closing date was set to October 31, 2026 on November 1.

| Item | Owner | Due |
| --- | --- | --- |
| Collect Garland Water Works FV-11858, $321,200, 50 days past due; revisit reserve at November close | Collections + account owner | Escalate this week |
| Confirm Norcross order form (335 vs 295 seats) and issue 40-seat add-on invoice, $29,582/yr | Billing + Sales ops | November |
| Approve Talentridge bill BILL-00327 in Ramp so it replaces the accrual | Hiring manager (Sales) | November |
| Collect receipts for five card charges over $75, $2,196 | Cardholders E0072, E0050, E0020, E0060, E0018 | November |
| Delete QuickBooks sandbox demo records: Oct 5 inventory adjustments ($567.50), "Checking" (−$76.90), two sales-tax payables ($76.90) | Controller | Before November close |
| Explain $70k salary gap to plan with headcount on plan | FP&A | November flux |
| Confirm the paid marketing budget, with ads running about twice plan | Marketing | November |
| Pursue Stripe dispute dp_1Q8fernvale, $10,711.44, product_not_received | Billing / CS | Per Stripe deadline |

**Control recommendations**

1. **Stripe payout posting.** Post each payout from Stripe's balance transactions, so disputes and their fees are booked automatically instead of grossing up the deposit.
2. **Cash application.** Match ACH receipts on invoice number, not customer name. Two customers share "Sawtooth" in their names.
3. **AP duplicate check.** Turn on QuickBooks duplicate-bill warnings, and normalize invoice numbers so "INV-1817" and "INV1817" match, before entry.
4. **Prepaid review.** Flag any bill over $5,000 with a service period longer than 31 days for prepaid treatment before posting. The Salesforce renewal would have been caught.
5. **Bill coding by vendor.** Lock Amazon Web Services' default to 5000 Hosting / Cost of Revenue. The June bill went to Software / Marketing.
6. **Write-off procedure.** Clear the invoice's unearned deferred revenue when writing it off, so only the earned portion hits bad debt.
7. **New-customer collections.** Start dunning on first invoices of large new logos at 15 days past due. Garland went 50 days with no payment attempt.
