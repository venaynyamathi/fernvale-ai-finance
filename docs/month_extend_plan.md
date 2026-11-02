# Plan: generate one more month at a time

Goal: run `python -m generator.extend --month 2026-11` (then 2026-12, 2027-01, …) to add one month of Fernvale activity, with a fresh set of planted errors, without changing anything already generated, loaded into QuickBooks or closed.

Written 2026-11-01 after the October 2026 close (see `close/2026-10/`). Build it in stages and commit after each one.

## Why the current generator can't just be extended

`generator/build.py` simulates the whole company from 2022 in one random sequence (`np.random.default_rng(C.SEED)` in `generator/source.py`), area by area across the full timeline. In a scratch test, setting `AS_OF = 2026-11-30` produced a November, but it also changed October and earlier history:

| Table | Rows through 10/31 that changed |
| --- | --- |
| bank_transactions, billing_invoices, billing_payments, spend_card_transactions, stripe_payouts, crm_opportunities, billing_subscription_events | most of them |
| payroll_runs, hr_employees | none |

The planted errors also repeated the same recipes (E1–E5, S1–S3) with new amounts.

QuickBooks is loaded through October and October is closed with 21 posted entries. **History through 2026-10-31 must never change.**

## Hard requirements

1. After extending to November, every source table and `build/books_as_booked.sqlite` must be **byte-identical for all rows dated on or before 2026-10-31**. Add a test that proves it.
2. Each month is reproducible: its seed is derived from `C.SEED` and the month (for example `hash((SEED, "2026-11"))`), so re-running `extend --month 2026-11` gives the same output.
3. Planted errors rotate. Draw 5–6 per month from a library and don't repeat an error type in consecutive months.
4. Each month's answer key is written to `private/<YYYY-MM>/` (git-ignored, like `private/` today): `ANSWER_KEY.md`, `planted_issues.json` and the expected month-end entries.
5. `company_info.last_closed_month` and `data_as_of` advance by one month.

## Stages

### Stage 1: extend step for the source systems (2–3 h)

`generator/extend.py`, run as `python -m generator.extend --month YYYY-MM`:

1. Read `data/source_systems.sqlite`. Refuse to run unless `--month` is the month after `data_as_of`.
2. Rebuild the simulation state at the prior month-end from the tables rather than re-simulating:
   - customers and subscriptions (plan, seats, unit price, discount, term, renewal date, status),
   - the open CRM pipeline,
   - employees, salaries and the hiring plan,
   - open invoices and failed-payment retries,
   - vendor schedules and the recurring bills that arrive after month-end (e.g. Brightquarry's month-end retainer),
   - Stripe balance not yet paid out,
   - bank balances.
3. Simulate the new month with the month's own RNG, reusing the existing simulation code where possible (`revenue.py`, `spend.py`, `hr.py`, `bank.py`). The month's activity should cover:
   - bookings, renewals, expansions and churn,
   - invoices, payments, refunds and disputes,
   - two payroll runs plus commissions paid,
   - bills and card spend,
   - Stripe payouts,
   - the bank statement.
4. Append the new rows only, including rows dated in the prior month that arrive late, such as a bill received in November but dated 10/31. Never update or delete existing rows.
5. **Test** in `tests/test_extend.py`:
   - run extend on a copy of the database,
   - assert every table is unchanged for rows dated ≤ prior month-end,
   - assert the new month's bank running balance ties,
   - assert re-running produces identical output.

### Stage 2: new month in the as-booked ledger (~1 h)

Add the month's day-to-day transactions to `build/books_as_booked.sqlite` (`gl_entries`/`gl_lines`) using the same mapping `ledger.py` applies today, with no month-end entries. Keep the trial balance balancing. Extend `validation/checks.py` to tie the new month to the source systems, the same way October ties.

### Stage 3: rotating error library and answer key (1–2 h)

`generator/errors.py`: each error is a small class that picks a target from the month's data, mutates the as-booked side (or the source side for review items), and describes itself for the answer key. Start with 8–10 types:

| Area | Error |
| --- | --- |
| Payroll | Terminated employee paid in a run after their termination date |
| Revenue | Mid-term seat upgrade billed without proration |
| Revenue | Renewal billed at the pre-2026 list price |
| AR / cash | Refund recorded twice |
| Cash | Transfer from treasury booked as revenue |
| Fixed assets | Capital purchase expensed |
| AP | Bill posted to the wrong department class |
| Cards | Personal charge on the corporate card coded as travel |
| Accruals | Recurring vendor bill dated in the month but received after month-end |
| Tax | State payroll tax deposit missing from the GL |

The **expected books** for the month start from the books as they actually stand after the prior close (use `close/<prior month>/inputs/posted_entries.json`), not from a regenerated ideal. The October scorecard showed why: the key re-graded October conventions.

Fix these two issues from `close/2026-10/SCORECARD.md`:
- **Write-offs.** Debit 2300 for the unearned portion, and charge 6900 only for the earned part. This matches the playbook's waterfall rule.
- **Open-month accruals.** Cover recurring month-end billers, not only `accrue_monthly` vendors.

### Stage 4: add the month to QuickBooks (1–2 h)

Add `python -m qbo_loader month --month YYYY-MM` to `qbo_loader/`:
- it creates only the new month's records,
- it skips anything already present (match on the `FV:<id>` private note),
- it never edits records dated in closed periods,
- it writes a load report.

Verify the QuickBooks trial balance against the extended ledger plus the prior closes' posted entries.

### Later

- FY2027 budget (`plan_budget_fy2027`, headcount and ARR plan) before the January 2027 close.
- Score each close against `private/<YYYY-MM>/` and commit `close/<YYYY-MM>/SCORECARD.md`.

## Usage notes

Pro plan: start each stage in a fresh chat pointed at this file. A long conversation costs much more per step. Commit after each stage so hitting a usage limit loses nothing.
