# October 2026 close — scored against the answer key

Scored 2026-11-01. The answer key was regenerated with `python -m generator.build` in a scratch worktree at commit `cb487b4`. Its `data/source_systems.sqlite` and `build/books_as_booked.sqlite` were byte-identical to the repo's (SHA-1 `b5eca76a…` and `64defdb2…`), so the key matches the books that were closed. The key itself (`private/`) stays git-ignored.

## Result

**All 8 planted issues found and fixed. The post-close balance sheet matches the expected books to the cent except 2200 and 2300. Every difference is an estimate or a convention the key and the playbook handle differently. None is a missed error.**

| | Score |
| --- | --- |
| Planted issues found | 8 / 8 |
| Planted issues fixed as the key prescribes | 8 / 8 |
| Expected month-end entries matched exactly | 7 / 10 |
| Expected entries differing by estimate or convention | 3 / 10 (AWS accrual, Marlow accrual, deferred revenue true-up) |
| Entries the run booked that the key doesn't have | 2 (Brightquarry accrual, FV-11156 correction), both supported |
| Balance sheet accounts matching expected books exactly | All except 2200 and 2300 |

## Planted issues

| ID | Issue | Found by | Run's fix | Verdict |
| --- | --- | --- | --- | --- |
| E1 | June AWS bill ($63,677.46) coded to 6200 Software / Marketing | Review of hosting vs AWS bills (6200 in July had an AWS bill) | D1031-CF36: reclass to 5000 / Cost of Revenue, booked in October | ✅ Found and fixed |
| E2 | Salesforce annual renewal ($67,795.20) expensed in September | Prepaid roll-forward: renewal had a 12-month service period | D1031-BF83 moved $64,823.36 unexpired at 9/30 to 1200, leaving the 9/15–9/30 portion ($2,971.84) as September expense. D1031-27E0 amortized October. 1200 at 10/31 = $63,677.98, same as the key | ✅ Found and fixed |
| E3 | Duplicate Marlow & Pierce bill INV1817 ($23,531.81) | AP tie-out to Ramp + duplicate check | D1031-907D deleted the unpaid duplicate | ✅ Found and fixed |
| E4 | Stripe payout po_00688 recorded gross of a $10,711.44 dispute + $15 fee | Bank rec (book cash over bank by $10,726.44) and Stripe payout check | D1031-B7B9: 6900 + 6850 / 1000. Dispute response logged as an open item | ✅ Found and fixed |
| E5 | $44,788.32 ACH from Sawtooth Plumbing applied to Sawtooth Wholesale | AR by customer (credit balance) + bank payer check | D1031-446A re-pointed and applied to FV-12064 | ✅ Found and fixed |
| S1 | Garland Water Works FV-11858, $321,200, past due | AR aging, 30+ days over $25k | Raised with reserve options; reviewer chose collections escalation, no reserve in October | ✅ Found; judgment per reviewer |
| S2 | Norcross: CRM 335 seats vs billing 295 | CRM-to-billing bookings check | Quantified $29,582.40 ARR under-billed; billing to confirm order form and re-bill | ✅ Found |
| S3 | Talentridge $28,400 bill pending approval, not in books | Unrecorded-liability search of Ramp | D1031-8FD2 accrued it (reverses 11/1) | ✅ Found and fixed |

## Month-end entries vs the key

| Key ref | Key amount | Run | Run amount | Match |
| --- | ---: | --- | ---: | --- |
| COMM-202610 | 61,229.94 | D1031-A52D | 61,229.94 | ✅ Exact |
| BONUS-202610 | 69,410.00 | D1031-9BF6 | 69,410.00 | ✅ Exact |
| DEPR-202610 | 3,106.67 | D1031-2864 | 3,106.67 | ✅ Exact |
| AMORT-BILL-00249-202610 (ZoomInfo) | 2,344.11 | D1031-1F6D | 2,344.11 | ✅ Exact |
| AMORT-BILL-00260-202610 (Keystone) | 5,435.62 | D1031-8450 | 5,435.62 | ✅ Exact |
| AMORT-BILL-00313-202610 (Salesforce) | 5,757.95 | D1031-27E0 | 5,757.95 | ✅ Exact |
| ACCR-TALENT-202610 | 28,400.00 | D1031-8FD2 | 28,400.00 | ✅ Exact |
| ACCR-AMAZON-202610 | 80,600.00 | D1031-124A | 86,900.00 | ≈ Estimate (+6,300) |
| ACCR-MARLOW-202610 | 20,000.00 | D1031-376E | 13,100.00 | ≈ Estimate (−6,900) |
| DEFREV-202610 | 404,766.43 | D1031-E141 | 410,820.34 | ≈ Convention (+6,053.91, see FV-11156) |
| — | — | D1031-07AB Brightquarry | 14,000.00 | ➕ Not in key (see below) |
| — | — | D1031-71D6 FV-11156 | 8,397.37 | ➕ Not in key (see below) |

## Every balance sheet difference, explained

| Account | Expected | Run | Run − expected | Cause |
| --- | ---: | ---: | ---: | --- |
| 2200 Accrued Expenses | (129,000.00) | (142,400.00) | (13,400.00) | Brightquarry +14,000; AWS estimate +6,300; Marlow estimate −6,900 |
| 2300 Deferred Revenue | (5,096,304.89) | (5,093,961.43) | 2,343.46 | FV-11156 unearned at 10/31 ($71,280 × 12/365) |

P&L differences (year to date) are the other side of the same items:
- 4000 is $6,053.91 lower: FV-11156 true-up.
- 6900 is $8,397.37 lower: FV-11156 correction.
- 6100 is $14,000 higher: Brightquarry.
- 5000 is $6,300 higher: AWS estimate.
- 6600 is $6,900 lower: Marlow estimate.

October *reported* net loss also differs from the key's October. The key restates the original months, while the run booked the three prior-period corrections in October, as the playbook requires ("don't reopen it"). Year to date, only the items above differ.

## Where the key and the run disagree

1. **FV-11156: deferred revenue on a written-off invoice ($8,397.37 at 9/30).** The key's expected books write off the full $71,280 to bad debt and keep the unearned part in 2300. The playbook's waterfall rule says "exclude invoices voided or written off on or before month-end", so the run corrected it. The two documents conflict. The run follows the playbook, and the playbook's treatment is the better accounting: unearned revenue on a cancelled, uncollectible contract isn't a liability to deliver. **Recommendation: change the generator's write-off entry to debit 2300 for the unearned portion and 6900 only for the earned part, or add FV-11156 as a planted issue.**
2. **Brightquarry October retainer ($14,000).** The simulation bills it on 10/31 for October service, but the bill's received date falls after the 10/31 data cut, so it isn't in Ramp. The key's open-month accrual covers only `accrue_monthly` vendors, so the expected books miss October content cost. The budget also carries it ($14,000, Marketing). **Recommendation: flag Brightquarry `accrue_monthly`, or extend the generator's open-month accrual to any recurring month-end biller.**
3. **Accrual estimates (AWS +$6,300, Marlow −$6,900).** The key uses the prior invoice × 1.04 (AWS) and × 0.85 (Marlow). The run scaled AWS with subscription revenue, as the playbook suggests, and used a three-month average for legal. Both are defensible, and the net difference is $600. **Recommendation: score accrual estimates within a tolerance (say ±15%), or state the method in the playbook.**

## What the run could do better (playbook refinements)

- **Name the counterparty on disputes.** The key names the disputing customer (Thornbury Fabrication Partners). The run cited customer C00044 and invoice in_000551 but never looked up the name, which the dispute response needs.
- **Keep one figure per metric.** The first approval message said subscription revenue was within 0.3% of average MRR; the reconciled figure is 1.6%. The close package has the right number. Add a rule to recompute sanity-check metrics after posting, not before.
- **Say how corrections are presented.** Add to the playbook that prior-period corrections in the open month should come with a reported vs adjusted view. The run did this, at the reviewer's prompting on the headline.

## Reproduce

```bash
git worktree add --detach /tmp/regen cb487b4
cd /tmp/regen && python -m generator.build      # writes private/ (git-ignored)
```
Then compare `private/books_expected.sqlite` to `close/2026-10/05_trial_balances/trial_balance_2026-10-31_post_close.csv`.
