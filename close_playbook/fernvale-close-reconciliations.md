---
name: fernvale-close-reconciliations
description: Balance sheet reconciliations for Fernvale's month-end close - bank, Stripe clearing, corporate card, accounts receivable and accounts payable - tying QuickBooks to the source systems and drafting correcting entries.
---

# Fernvale close: reconciliations

Each reconciliation follows the same shape. Get the GL balance from QuickBooks at month-end, get the independent balance from the source system, list and explain the differences, and draft entries for any that belong in the books. A difference that nets to zero across offsetting errors is still two errors; look at the detail, not just the totals.

Use `qbo_report` with `TrialBalance` or `GeneralLedger` (pass `{"account": "<qbo id>"}` from `qbo_chart_of_accounts`) for GL detail, `qbo_query` for documents, and `source_query` for source data. Run `source_tables` for table and column names.

## 1. Bank (1000 Operating Checking, 1010 Treasury Money Market)

1. **Get the two balances.** Bank balance: sum `bank_transactions.amount` by `account_id` through month-end, and confirm it against the last `running_balance`. GL balance: the trial balance.
2. **Match the month's activity.** Match bank lines to GL transactions by date (±3 days), amount and counterparty or reference. Payroll debits, Stripe payouts, customer ACH and wires, bill payments, card statement payments, transfers, interest and fees should each have a GL counterpart.
3. **Classify the unmatched items.**
   - **On the bank, not the books:** fees, interest, unexpected receipts or debits. These need entries.
   - **On the books, not the bank:** timing items (deposits in transit, outstanding payments). These need no entry, but confirm they clear early next month if the data shows it.
   - **On both, but with different amounts:** recording errors. Find the cause in the source system before drafting a fix.
4. **Deposits:** check that the payer and amount on the bank line agree with the customer and amount the payment was recorded against in QuickBooks.

## 2. Stripe clearing (1050)

1050 holds card receipts that Stripe hasn't paid out yet. At month-end it should equal charges, less refunds, disputes and fees, not yet in a payout.

1. **Compute the expected balance from Stripe.** Use `stripe_balance_transactions` (charges, refunds, disputes and their fees) and `stripe_payouts`. The expected balance is the net of balance transactions not yet included in a payout that arrived by month-end.
2. **Check each payout.** Every payout should appear in the bank and be recorded in QuickBooks at the same net amount, with gross and fees split correctly. Fees go to 5200 Merchant Processing Fees.
3. **Disputes and chargebacks** reduce payouts. Make sure each one is booked: the disputed amount to 6900 Bad Debt & Chargebacks, and the dispute fee to bank and service fees. Open disputes are a review item; note whether a response is due.
4. **Refunds** recorded in billing should appear in Stripe and in the GL.

## 3. Corporate card (2100)

1. **The liability** should equal card transactions posted to date, less statement payments made. Use `spend_card_transactions` and `spend_card_statements`.
2. **Coding:** confirm every card transaction in the month is in QuickBooks at the same amount. Spot-check its account and class against the vendor's category and the cardholder's department.
3. **Policy flags:** list transactions without receipts over $75, unusual merchants, personal-looking charges and split purchases. These go in the memo; they don't need entries unless the expense is misclassified.

## 4. Accounts receivable (1100)

1. **Tie AR to billing.** AR in QuickBooks should equal open invoices in billing at month-end. Use `billing_invoices` and payments by date.
2. **Customer-level detail:** run `AgedReceivableDetail` or `CustomerBalance` and compare it customer by customer with billing. Any customer with a **credit balance**, an unapplied payment, or a balance that differs from billing needs explaining. Check where the cash came from (`billing_payments`, `bank_transactions`), whose invoice it paid, and whether it was applied to the right customer and invoice.
3. **Aging and collectability:**
   - Summarize the aging buckets.
   - For every invoice 30+ days past due over $25,000, note the customer, the amount, the days past due, the customer's payment history and its subscription status.
   - Recommend a specific reserve or write-off where warranted, and explain the judgment. A reserve needs the reviewer's agreement.
4. **Write-offs and voids** in the month should match billing's `uncollectible` and voided invoices.

## 5. Accounts payable (2000) and unrecorded liabilities

1. **Tie AP to the AP system.** AP in QuickBooks should equal approved, unpaid bills in `spend_bills` (status not `pending_approval`) dated on or before month-end.
2. **Duplicates:** look for bills from the same vendor with the same or very similar amount within 30 days, or with very similar invoice numbers. Confirm each against the AP system before proposing a deletion. Deleting an unpaid duplicate is a `qbo_draft_change` with action `delete`.
3. **Search for unrecorded liabilities.**
   - **Bills not yet in the books:** bills in the AP system for goods or services received on or before month-end that aren't in QuickBooks. This includes bills awaiting approval and bills dated after month-end whose service period falls in the month.
   - **Expected costs with no invoice:** vendors with `accrue_monthly = 1`, and any vendor that bills monthly in arrears.
   - **Events that create costs:** hires, offsites, legal matters, financing work and similar.
   - **Booking:** draft a bill (`qbo_draft_bill`) when the invoice exists and is approved, or an accrual (`qbo_draft_journal_entry` with a reversing date) when it doesn't.
4. **Bill coding:** for bills in the month over $5,000, confirm the account and class fit the vendor and description. Any bill covering more than one month of service should go to prepaid; see `fernvale-close-entries`.

## Output per reconciliation

For each reconciliation, report:

| | |
|---|---|
| GL balance | |
| Source balance | |
| Difference | |
| Reconciling items | description, amount, evidence (table / record IDs), entry needed? |
| Draft IDs | |
| Conclusion | tied / tied after entries / open item |
