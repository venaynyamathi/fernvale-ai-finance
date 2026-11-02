# October 2026 close — Fernvale Systems

**Status:** closed. QuickBooks closing date set to 2026-10-31 on 2026-11-01.
**Prepared by:** Claude (close agent), running the [close playbook](../../close_playbook/). **Reviewed and approved by:** Vinny.

October net loss was $595,755 (reported) on $967,700 of revenue. Ending ARR was $11.00M, up $995,846 in the month. Every balance sheet account ties to its source system after 21 postings on 2026-11-01. Three of those postings correct errors from closed periods; they're booked in October and flagged ⚑.

## What's here

| Folder / file | What it supports |
| --- | --- |
| [`01_close_memo/close_package.md`](01_close_memo/close_package.md) (also `.pdf`, `.docx`) | Close memo, reconciliation summaries, journal entry log, flux commentary, open items and control recommendations |
| [`02_reconciliations/00_reconciliation_summary.xlsx`](02_reconciliations/00_reconciliation_summary.xlsx) | Every balance sheet account: GL vs source, difference, status, workpaper |
| `02_reconciliations/1000_1010_bank_reconciliation.xlsx` | Operating and treasury bank recs; all 44 October bank lines matched to the GL by reference; customer payer check |
| `02_reconciliations/1050_stripe_clearing.xlsx` | Payout-by-payout check of Stripe vs bank vs GL; balance in transit; the unbooked dispute |
| `02_reconciliations/2100_corporate_card.xlsx` | Card liability vs Ramp; all 66 October charges vs GL; receipts missing over $75 |
| `02_reconciliations/1100_accounts_receivable.xlsx` | AR vs billing in total and by customer; aging; collectability; the Sawtooth cash application fix |
| `02_reconciliations/2000_accounts_payable.xlsx` | AP vs Ramp; duplicate bill; unrecorded-liability search; bill coding over $5k |
| `02_reconciliations/2300_deferred_revenue_waterfall.xlsx` | Line-level waterfall at 9/30 and 10/31 (formulas), true-up, roll-forward, MRR and services checks, CRM-to-billing bookings check |
| [`03_journal_entries/je_log.csv`](03_journal_entries/je_log.csv) | One row per posting: draft ID, QuickBooks Id, date, category, memo, amount, support |
| `03_journal_entries/je_support.xlsx` | Every line posted, plus support tabs: accruals, prepaid schedule, depreciation, commissions, bonus, payroll tie-out, prior-period corrections, chargeback |
| `04_variance_analysis/flux_and_budget_variance.xlsx` | P&L Jul–Oct vs budget with flag formulas and drivers; reported vs adjusted; opex by function; ARR, retention, burn and runway; balance sheet flux |
| `05_trial_balances/` | Trial balances at 9/30, 10/31 pre-close and 10/31 post-close (CSV), and a tie-out of the rebuilt post-close TB to QuickBooks |
| [`inputs/posted_entries.json`](inputs/posted_entries.json) | The 21 approved postings, line by line, with reviewer decisions |
| `inputs/qbo_trial_balance_2026-10-31_post_close.csv` | QuickBooks trial balance pulled after posting |
| [`scripts/build_workpapers.py`](scripts/build_workpapers.py) | Regenerates every workbook and CSV from the inputs |

## Entries posted (summary)

| Category | Postings | Amount |
| --- | --- | --- |
| Reconciliation corrections (chargeback, cash application, duplicate bill) | 3 | $10,726 / $44,788 / $23,532 |
| Revenue: deferred revenue true-up | 1 | $410,820 |
| Accruals (AWS, legal, content retainer, recruiting) with 11/1 reversals | 8 | $142,400 accrued |
| Prepaid amortization and depreciation | 4 | $16,644 |
| Commissions and bonus | 2 | $130,640 |
| ⚑ Prior-period corrections (FV-11156 deferred revenue, Salesforce prepaid, June AWS coding) | 3 | $8,397 / $64,823 / $63,677 |

## How the workpapers were built

The QuickBooks ledger for October was loaded from `build/books_as_booked.sqlite`. The script starts from that ledger, adds the 21 postings in `inputs/posted_entries.json`, and rebuilds the post-close trial balance. That trial balance ties to the QuickBooks pull to the cent (see `05_trial_balances/trial_balance_tieout_to_quickbooks.xlsx`). The only QuickBooks rows that don't come from Fernvale are sandbox demo records, listed as an open item.

Source-side balances come from `data/source_systems.sqlite`. The script stops with an error if any reconciliation fails to tie.

```bash
python close/2026-10/scripts/build_workpapers.py
```

## Open items carried to November

1. Collect Garland Water Works FV-11858, $321,200, 50 days past due. No reserve in October; revisit at the November close.
2. Billing to confirm the Norcross order form (335 vs 295 seats) and invoice the 40-seat difference, $29,582/yr.
3. Approve Talentridge BILL-00327 in Ramp so it replaces the accrual.
4. Collect receipts for five card charges over $75 ($2,196).
5. Delete QuickBooks sandbox demo records: the Oct 5 inventory adjustments ($567.50), "Checking" (−$76.90) and two sales-tax payables.
6. Explain the $70k salaries gap to plan with headcount on plan.
7. Confirm the paid marketing budget; ads ran about twice plan.
8. Respond to Stripe dispute dp_1Q8fernvale ($10,711.44).
