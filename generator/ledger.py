"""
Accounting layer: chart of accounts and the general ledger derived from the source systems.

Two versions are produced:
  * expected  – the books as a careful accountant would keep them, every month closed
                properly, including October 2026. This is the answer key.
  * as_booked – what is (or will be) in QuickBooks: identical through September 2026 except
                for a few planted historical errors; October 2026 contains only day-to-day
                transactions plus planted errors, with no month-end close entries yet.
"""
from collections import defaultdict
from datetime import date, timedelta

import numpy as np

from . import config as C
from .hr import headcount_by_dept
from .util import (add_months, days_inclusive, month_end, months_between, money,
                   overlap_days)

# number, name, QuickBooks AccountType, AccountSubType, statement
ACCOUNTS = [
    ("1000", "Operating Checking", "Bank", "Checking", "BS"),
    ("1010", "Treasury Money Market", "Bank", "MoneyMarket", "BS"),
    ("1050", "Stripe Clearing", "Other Current Asset", "UndepositedFunds", "BS"),
    ("1100", "Accounts Receivable", "Accounts Receivable", "AccountsReceivable", "BS"),
    ("1200", "Prepaid Software", "Other Current Asset", "PrepaidExpenses", "BS"),
    ("1210", "Prepaid Insurance", "Other Current Asset", "PrepaidExpenses", "BS"),
    ("1300", "Security Deposits", "Other Asset", "SecurityDeposits", "BS"),
    ("1500", "Furniture & Leasehold Improvements", "Fixed Asset", "FurnitureAndFixtures", "BS"),
    ("1550", "Accumulated Depreciation", "Fixed Asset", "AccumulatedDepreciation", "BS"),
    ("2000", "Accounts Payable", "Accounts Payable", "AccountsPayable", "BS"),
    ("2100", "Ramp Corporate Card", "Credit Card", "CreditCard", "BS"),
    ("2200", "Accrued Expenses", "Other Current Liability", "OtherCurrentLiabilities", "BS"),
    ("2210", "Accrued Commissions", "Other Current Liability", "PayrollClearing", "BS"),
    ("2220", "Accrued Bonus", "Other Current Liability", "PayrollClearing", "BS"),
    ("2300", "Deferred Revenue", "Other Current Liability", "OtherCurrentLiabilities", "BS"),
    ("3010", "Preferred Stock - Seed", "Equity", "PreferredStock", "BS"),
    ("3020", "Preferred Stock - Series A", "Equity", "PreferredStock", "BS"),
    ("3030", "Preferred Stock - Series B", "Equity", "PreferredStock", "BS"),
    ("3900", "Retained Earnings", "Equity", "RetainedEarnings", "BS"),
    ("4000", "Subscription Revenue", "Income", "ServiceFeeIncome", "PL"),
    ("4100", "Professional Services Revenue", "Income", "ServiceFeeIncome", "PL"),
    ("5000", "Hosting & Infrastructure", "Cost of Goods Sold", "OtherCostsOfServiceCos", "PL"),
    ("5100", "COGS - Support Salaries", "Cost of Goods Sold", "CostOfLaborCos", "PL"),
    ("5110", "COGS - Support Taxes & Benefits", "Cost of Goods Sold", "CostOfLaborCos", "PL"),
    ("5200", "Merchant Processing Fees", "Cost of Goods Sold", "OtherCostsOfServiceCos", "PL"),
    ("6000", "Salaries & Wages", "Expense", "PayrollExpenses", "PL"),
    ("6010", "Payroll Taxes", "Expense", "PayrollExpenses", "PL"),
    ("6020", "Employee Benefits", "Expense", "PayrollExpenses", "PL"),
    ("6030", "Sales Commissions", "Expense", "PayrollExpenses", "PL"),
    ("6040", "Bonuses", "Expense", "PayrollExpenses", "PL"),
    ("6100", "Contractors", "Expense", "OtherMiscellaneousServiceCost", "PL"),
    ("6200", "Software & Subscriptions", "Expense", "OfficeGeneralAdministrativeExpenses", "PL"),
    ("6300", "Advertising & Marketing Programs", "Expense", "AdvertisingPromotional", "PL"),
    ("6310", "Events & Sponsorships", "Expense", "AdvertisingPromotional", "PL"),
    ("6400", "Travel", "Expense", "Travel", "PL"),
    ("6410", "Meals & Entertainment", "Expense", "EntertainmentMeals", "PL"),
    ("6500", "Rent & Facilities", "Expense", "RentOrLeaseOfBuildings", "PL"),
    ("6600", "Legal Fees", "Expense", "LegalProfessionalFees", "PL"),
    ("6610", "Accounting & Tax Fees", "Expense", "LegalProfessionalFees", "PL"),
    ("6620", "Insurance", "Expense", "Insurance", "PL"),
    ("6700", "Recruiting", "Expense", "OtherMiscellaneousServiceCost", "PL"),
    ("6710", "Computer Equipment", "Expense", "SuppliesMaterials", "PL"),
    ("6720", "Office Expenses", "Expense", "OfficeGeneralAdministrativeExpenses", "PL"),
    ("6800", "Taxes & Licenses", "Expense", "TaxesPaid", "PL"),
    ("6850", "Bank & Service Fees", "Expense", "BankCharges", "PL"),
    ("6900", "Bad Debt & Chargebacks", "Expense", "BadDebts", "PL"),
    ("6950", "Depreciation", "Expense", "OtherMiscellaneousServiceCost", "PL"),
    ("7000", "Interest Income", "Other Income", "InterestEarned", "PL"),
]
ACCT_NAME = {a[0]: a[1] for a in ACCOUNTS}
CLASSES = ["Engineering", "Product", "Sales", "Marketing", "Customer Success", "Support",
           "G&A", "Cost of Revenue"]

CATEGORY_ACCOUNT = {
    "Hosting": "5000", "Software - R&D": "6200", "Software - G&A": "6200",
    "Software - Sales": "6200", "Software - Marketing": "6200", "Payroll Fees": "6850",
    "Advertising": "6300", "Events": "6310", "Contractors - Marketing": "6100",
    "Contractors - R&D": "6100", "Recruiting": "6700", "Rent": "6500", "Legal": "6600",
    "Accounting & Tax": "6610", "Insurance": "6620", "Benefits": "6020",
    "Computer Equipment": "6710", "Taxes & Licenses": "6800", "Travel": "6400",
    "Meals & Entertainment": "6410", "Office Expenses": "6720", "Fixed Assets": "1500",
}
PREPAID_VENDORS = {"Salesforce": "1200", "ZoomInfo": "1200",
                   "Keystone Mutual Insurance (fictional)": "1210"}
FUNDING_ACCOUNT = {"Seed": "3010", "Series A": "3020", "Series B": "3030"}
DEPRECIATION_MONTHS = 60


def cls(dept):
    return {"COGS": "Cost of Revenue", "Allocated": "G&A"}.get(dept, dept)


def payroll_acct(dept, kind):
    if dept == "Support":
        return "5110" if kind in ("tax", "benefits") else "5100"
    return {"salary": "6000", "tax": "6010", "benefits": "6020", "commission": "6030",
            "bonus": "6040"}[kind]


class Ledger:
    def __init__(self):
        self.entries = []
        self.lines = []

    def je(self, d, doc_type, ref, memo, lines, kind="transaction", period=None):
        """lines: (account, debit, credit, class, customer_id, vendor_id, description)"""
        lines = [l for l in lines if abs(l[1]) > 0.004 or abs(l[2]) > 0.004]
        if not lines:
            return None
        dr = round(sum(l[1] for l in lines), 2)
        cr = round(sum(l[2] for l in lines), 2)
        if abs(dr - cr) > 0.011:
            raise ValueError(f"unbalanced entry {doc_type} {ref}: {dr} vs {cr}")
        if abs(dr - cr) > 0:  # absorb pennies from rounding into the last line
            l = list(lines[-1])
            if l[1]:
                l[1] = money(l[1] - (dr - cr))
            else:
                l[2] = money(l[2] + (dr - cr))
            lines[-1] = tuple(l)
        jid = f"JE{len(self.entries) + 1:06d}"
        self.entries.append({"je_id": jid, "txn_date": d, "period": f"{(period or d):%Y-%m}",
                             "doc_type": doc_type, "source_ref": ref, "memo": memo,
                             "entry_kind": kind})
        for n, (acct, dbt, crd, klass, cust, vend, desc) in enumerate(lines, start=1):
            self.lines.append({"je_id": jid, "line_no": n, "account_number": acct,
                               "account_name": ACCT_NAME[acct], "debit": money(dbt),
                               "credit": money(crd), "class": klass, "customer_id": cust,
                               "vendor_id": vend, "description": desc})
        return jid


def L(acct, amount, klass=None, cust=None, vend=None, desc=None):
    """Signed helper: positive amount = debit, negative = credit."""
    amount = money(amount)
    return (acct, amount if amount > 0 else 0.0, -amount if amount < 0 else 0.0, klass, cust,
            vend, desc)


# ---------------------------------------------------------------------------
def deferred_balance(invoice_lines, inv_by_id, as_of):
    """Unearned revenue at as_of, split into (subscription, services)."""
    sub = svc = 0.0
    for ln in invoice_lines:
        inv = inv_by_id[ln["invoice_id"]]
        if inv["invoice_date"] > as_of:
            continue
        removed = inv.get("voided_date") if inv["status"] == "uncollectible" and \
            inv["customer_payment_method"] == "card" else None
        if inv["status"] == "refunded":
            removed = inv.get("refunded_date")
        if removed and removed <= as_of:
            continue
        total_days = days_inclusive(ln["service_start"], ln["service_end"])
        remaining = overlap_days(ln["service_start"], ln["service_end"],
                                 as_of + timedelta(days=1), date(2100, 1, 1))
        amt = ln["amount"] * remaining / total_days
        if ln["line_type"] == "services":
            svc += amt
        else:
            sub += amt
    return money(sub), money(svc)


def build_ledgers(sim):
    expected = Ledger()
    booked = Ledger()
    errors = []
    rng = np.random.default_rng(C.SEED + 7)
    rev, spend = sim["rev"], sim["spend"]
    cust_by_id = {c["customer_id"]: c for c in rev.customers}
    vend_by_name = spend.vendors
    vend_by_id = {v["vendor_id"]: v for v in spend.vendors.values()}
    open_month = C.LAST_CLOSED + timedelta(days=1)
    planted = sim["planted"]

    def both(*args, **kw):
        expected.je(*args, **kw)
        booked.je(*args, **kw)

    def closed(d):
        return d <= C.LAST_CLOSED

    # flatten invoice lines
    inv_lines = []
    for inv in rev.invoices:
        inv["customer_payment_method"] = cust_by_id[inv["customer_id"]]["payment_method"]
        for n, ln in enumerate(inv["lines"], start=1):
            inv_lines.append({**ln, "invoice_id": inv["invoice_id"], "line_no": n})
    inv_by_id = {i["invoice_id"]: i for i in rev.invoices}

    # ------------------------------------------------------------------ equity
    for f in C.FUNDING:
        both(f["date"], "Deposit", f["round"], f"{f['round']} preferred stock financing - "
             f"{f['lead']}", [L("1000", f["amount"]), L(FUNDING_ACCOUNT[f["round"]], -f["amount"])])

    # ------------------------------------------------------------------ invoices & AR
    for inv in rev.invoices:
        lines = [L("1100", inv["total"], cust=inv["customer_id"])]
        for ln in inv["lines"]:
            acct = "4100" if ln["line_type"] == "services" else "4000"
            lines.append(L(acct, -ln["amount"], cust=inv["customer_id"], desc=ln["description"]))
        both(inv["invoice_date"], "Invoice", inv["invoice_number"], f"Invoice {inv['invoice_number']}",
             lines)
        if inv["status"] == "uncollectible" and inv["voided_date"]:
            if inv["customer_payment_method"] == "card":
                both(inv["voided_date"], "Invoice Void", inv["invoice_number"],
                     "Void - card payment failed after retries; subscription canceled",
                     [L("4000", inv["total"], cust=inv["customer_id"]),
                      L("1100", -inv["total"], cust=inv["customer_id"])])
            else:
                both(inv["voided_date"], "Journal Entry", inv["invoice_number"],
                     "Write off uncollectible invoice (120+ days past due)",
                     [L("6900", inv["total"], "G&A"),
                      L("1100", -inv["total"], cust=inv["customer_id"])])

    misapplied_done = False
    for p in rev.payments:
        if p["status"] != "succeeded":
            continue
        inv = inv_by_id[p["invoice_id"]]
        deposit = "1050" if p["method"] == "card" else "1000"
        lines = [L(deposit, p["amount"]), L("1100", -p["amount"], cust=p["customer_id"])]
        expected.je(p["attempted_at"], "Payment", p["payment_id"],
                    f"Payment for {inv['invoice_number']}", lines)
        # planted: an October ACH payment is applied to the wrong customer in QuickBooks
        if not misapplied_done and p["method"] == "ach" and p["attempted_at"] >= date(2026, 10, 12) \
                and 15_000 < p["amount"] < 80_000:
            others = [c for c in rev.customers if c["segment"] == "Mid-Market"
                      and c["customer_id"] != p["customer_id"]
                      and cust_by_id[p["customer_id"]]["name"].split()[0][:3] == c["name"].split()[0][:3]]
            if not others:
                others = [c for c in rev.customers if c["segment"] == "Mid-Market"
                          and c["customer_id"] != p["customer_id"]
                          and c["name"][0] == cust_by_id[p["customer_id"]]["name"][0]]
            if not others:
                others = [c for c in rev.customers if c["segment"] == "Mid-Market"
                          and c["customer_id"] != p["customer_id"]]
            wrong = others[0]
            booked.je(p["attempted_at"], "Payment", p["payment_id"],
                      f"Payment for {inv['invoice_number']}",
                      [L("1000", p["amount"]), L("1100", -p["amount"], cust=wrong["customer_id"])])
            errors.append({
                "id": "E5", "period": "2026-10", "area": "Accounts receivable / cash application",
                "title": "Customer payment applied to the wrong customer",
                "detail": f"ACH of ${p['amount']:,.2f} received {p['attempted_at']} from "
                          f"{cust_by_id[p['customer_id']]['name']} for invoice "
                          f"{inv['invoice_number']} was recorded against "
                          f"{wrong['name']} as an unapplied credit. The real customer's "
                          f"invoice still shows open; the other customer shows a credit.",
                "how_found": "AR aging shows a credit balance on a customer with nothing to pay; "
                             "bank deposit name doesn't match the customer on the payment.",
                "fix": "Delete/re-enter the payment under the correct customer and apply it to "
                       f"{inv['invoice_number']}.",
                "amount": p["amount"]})
            misapplied_done = True
        else:
            booked.je(p["attempted_at"], "Payment", p["payment_id"],
                      f"Payment for {inv['invoice_number']}", lines)
        if inv.get("amount_written_off"):
            both(p["attempted_at"], "Journal Entry", inv["invoice_number"],
                 "Short payment - intermediary wire fee deducted by customer's bank",
                 [L("6850", inv["amount_written_off"], "G&A"),
                  L("1100", -inv["amount_written_off"], cust=p["customer_id"])])

    for r in rev.refunds:
        both(r["refund_date"], "Refund Receipt", r["refund_id"],
             "Refund - customer canceled within 30 days",
             [L("4000", r["amount"], cust=r["customer_id"]), L("1050", -r["amount"])])

    # ------------------------------------------------------------------ Stripe payouts
    txn_by_payout = defaultdict(list)
    for t in sim["stripe_txns"]:
        if t["payout_id"]:
            txn_by_payout[t["payout_id"]].append(t)
    dispute = planted["dispute"]
    expected.je(dispute["date"], "Journal Entry", "dp_1Q8fernvale",
                f"Stripe dispute (chargeback) - {dispute['customer']}",
                [L("6900", dispute["amount"], "G&A", cust=dispute["customer_id"]),
                 L("6850", 15.0, "G&A"), L("1050", -(dispute["amount"] + 15.0))])
    for po in sim["payouts"]:
        if not po["arrival_date"]:
            continue
        txns = txn_by_payout[po["payout_id"]]
        fees = money(sum(t["fee"] for t in txns if t["type"] == "charge"))
        lines = [L("1000", po["amount"]), L("5200", fees, "Cost of Revenue"),
                 L("1050", -(po["amount"] + fees))]
        expected.je(po["arrival_date"], "Deposit", po["payout_id"], "Stripe payout", lines)
        if any(t["type"] == "dispute" for t in txns):
            gross = money(po["amount"] + dispute["amount"] + 15.0)
            booked.je(po["arrival_date"], "Deposit", po["payout_id"], "Stripe payout",
                      [L("1000", gross), L("5200", fees, "Cost of Revenue"),
                       L("1050", -(gross + fees))])
            errors.append({
                "id": "E4", "period": "2026-10", "area": "Cash / Stripe reconciliation",
                "title": "Stripe payout recorded without the chargeback deducted",
                "detail": f"Payout {po['payout_id']} arrived {po['arrival_date']} for "
                          f"${po['amount']:,.2f}, but was recorded at ${gross:,.2f}. A "
                          f"${dispute['amount']:,.2f} dispute by {dispute['customer']} plus "
                          f"the $15 dispute fee was netted out by Stripe and never booked.",
                "how_found": "Bank reconciliation: book cash exceeds the bank statement by "
                             f"${dispute['amount'] + 15:,.2f}; Stripe balance report shows a dispute.",
                "fix": "Reduce the deposit to the actual payout and book the chargeback "
                       "(bad debt/chargebacks) and $15 dispute fee; open the dispute response "
                       "in Stripe.", "amount": money(dispute["amount"] + 15)})
        else:
            booked.je(po["arrival_date"], "Deposit", po["payout_id"], "Stripe payout", lines)

    # ------------------------------------------------------------------ payroll
    items_by_run = defaultdict(list)
    for it in sim["payroll_items"]:
        items_by_run[it["run_id"]].append(it)
    bonus_paid = defaultdict(float)
    for r in sim["payroll_runs"]:
        its = items_by_run[r["run_id"]]
        by_dept = defaultdict(lambda: defaultdict(float))
        for it in its:
            d = by_dept[it["department"]]
            d["salary"] += it["base_pay"]
            d["commission"] += it["commission_pay"]
            d["bonus"] += it["bonus_pay"]
            d["tax"] += it["employer_taxes"]
        lines = []
        for dept, d in sorted(by_dept.items()):
            lines.append(L(payroll_acct(dept, "salary"), d["salary"], dept,
                           desc="Regular wages"))
            lines.append(L("2210", d["commission"], dept, desc="Commissions paid (accrued)"))
            lines.append(L("2220", d["bonus"], dept, desc="Annual bonus paid (accrued)"))
            lines.append(L(payroll_acct(dept, "tax"), d["tax"], dept, desc="Employer taxes"))
            bonus_paid[r["pay_date"].year - 1] += d["bonus"]
        net = sum(i["net_pay"] for i in its)
        tax = sum(i["employee_taxes_withheld"] + i["employer_taxes"] for i in its)
        lines += [L("1000", -net, desc="Net pay (Gusto)"),
                  L("1000", -tax, desc="Tax remittance (Gusto)")]
        both(r["funding_debit_date"], "Journal Entry", r["run_id"],
             f"Payroll {r['pay_period_start']:%b %d} - {r['pay_period_end']:%b %d, %Y}", lines)

    # ------------------------------------------------------------------ AP bills
    dup_done = False
    for b in spend.bills:
        if b["status"] == "pending_approval":
            continue
        v = vend_by_id[b["vendor_id"]]
        vendor = b["vendor_name"]
        months = 0
        if b["service_period_start"] and b["service_period_end"]:
            months = days_inclusive(b["service_period_start"], b["service_period_end"]) / 30.4
        if vendor in PREPAID_VENDORS and months > 2:
            acct, klass = PREPAID_VENDORS[vendor], None
        elif "Security deposit" in b["memo"]:
            acct, klass = "1300", None
        else:
            acct = CATEGORY_ACCOUNT[b["category"]]
            klass = cls(b["department"])
        if b["category"] == "Benefits":
            hc = headcount_by_dept(sim["employees"], b["invoice_date"])
            tot = sum(hc.values())
            exp_lines = []
            alloc = 0.0
            depts = [dp for dp in C.DEPARTMENTS if hc[dp]]
            for i, dp in enumerate(depts):
                amt = money(b["amount"] * hc[dp] / tot) if i < len(depts) - 1 else money(
                    b["amount"] - alloc)
                alloc += amt
                exp_lines.append(L(payroll_acct(dp, "benefits"), amt, dp, vend=b["vendor_id"],
                                   desc=b["memo"]))
        else:
            exp_lines = [L(acct, b["amount"], klass, vend=b["vendor_id"], desc=b["memo"])]
        lines = exp_lines + [L("2000", -b["amount"], vend=b["vendor_id"])]
        expected.je(b["invoice_date"], "Bill", b["bill_id"], f"{vendor} {b['invoice_number']}",
                    lines)

        # --- planted historical and open-month errors on the as-booked side
        if vendor == "Salesforce" and b["invoice_date"].year == 2026:
            booked.je(b["invoice_date"], "Bill", b["bill_id"], f"{vendor} {b['invoice_number']}",
                      [L("6200", b["amount"], "Sales", vend=b["vendor_id"], desc=b["memo"]),
                       L("2000", -b["amount"], vend=b["vendor_id"])])
            errors.append({
                "id": "E2", "period": "2026-09", "area": "Prepaids",
                "title": "Annual Salesforce renewal expensed instead of prepaid",
                "detail": f"Bill {b['invoice_number']} (${b['amount']:,.2f}, 12-month term "
                          f"{b['service_period_start']} to {b['service_period_end']}) was "
                          "posted straight to Software & Subscriptions in September 2026.",
                "how_found": "September software expense spikes vs trend and budget; the prepaid "
                             "software balance drops to almost zero after the 2025 renewal "
                             "finishes amortizing.",
                "fix": "Reclass to Prepaid Software and book amortization for Sep 15-30 "
                       "(and Oct going forward).", "amount": b["amount"]})
        elif vendor == "Amazon Web Services" and b["service_period_start"] == date(2026, 6, 1):
            booked.je(b["invoice_date"], "Bill", b["bill_id"], f"{vendor} {b['invoice_number']}",
                      [L("6200", b["amount"], "Marketing", vend=b["vendor_id"], desc=b["memo"]),
                       L("2000", -b["amount"], vend=b["vendor_id"])])
            errors.append({
                "id": "E1", "period": "2026-07", "area": "Expense coding",
                "title": "AWS invoice coded to Marketing software instead of hosting",
                "detail": f"AWS bill {b['invoice_number']} for June usage (${b['amount']:,.2f}, "
                          f"dated {b['invoice_date']}) was posted to Software & Subscriptions, "
                          "class Marketing. The June accrual reversal still hit Hosting, so "
                          "July hosting looks abnormally low and Marketing software abnormally "
                          "high.",
                "how_found": "Flux review: July gross margin jumps, Marketing over budget on "
                             "software, hosting under budget despite the migration.",
                "fix": "Reclass to 5000 Hosting & Infrastructure, class Cost of Revenue.",
                "amount": b["amount"]})
        else:
            booked.je(b["invoice_date"], "Bill", b["bill_id"], f"{vendor} {b['invoice_number']}",
                      lines)
            if not dup_done and vendor.startswith("Marlow") and b["invoice_date"] >= open_month:
                dup_inv = b["invoice_number"].replace("INV-", "INV")
                booked.je(b["invoice_date"] + timedelta(days=2), "Bill", b["bill_id"] + "-DUP",
                          f"{vendor} {dup_inv}", lines)
                errors.append({
                    "id": "E3", "period": "2026-10", "area": "Accounts payable",
                    "title": "Duplicate legal bill",
                    "detail": f"Marlow & Pierce invoice {b['invoice_number']} "
                              f"(${b['amount']:,.2f}) was entered twice; the second copy uses "
                              f"invoice number {dup_inv} and is dated two days later.",
                    "how_found": "Duplicate check on vendor + amount within a short window; the "
                                 "AP system (source) shows one bill.",
                    "fix": "Delete the duplicate bill before it is paid.", "amount": b["amount"]})
                dup_done = True
        if b["status"] == "paid":
            both(b["paid_date"], "Bill Payment", b["bill_id"], f"Payment - {vendor}",
                 [L("2000", b["amount"], vend=b["vendor_id"]), L("1000", -b["amount"])])

    # ------------------------------------------------------------------ card
    for t in spend.card_txns:
        acct = CATEGORY_ACCOUNT[t["category"]]
        both(t["transaction_date"], "Expense", t["transaction_id"], t["merchant"],
             [L(acct, t["amount"], cls(t["department"]), vend=t["vendor_id"], desc=t["memo"]),
              L("2100", -t["amount"], vend=t["vendor_id"])])
    for s in spend.statements:
        if s["payment_date"]:
            both(s["payment_date"], "Credit Card Payment", s["statement_id"],
                 "Ramp statement payment", [L("2100", s["statement_total"]),
                                            L("1000", -s["statement_total"])])

    # ------------------------------------------------------------------ bank-only items
    for t in sim["bank"].txns:
        k = t["txn_type"]
        if k == "bank_fee":
            both(t["posted_date"], "Expense", t["bank_txn_id"], "Bank account analysis fee",
                 [L("6850", 85.0, "G&A"), L("1000", -85.0)])
        elif k == "interest":
            both(t["posted_date"], "Deposit", t["bank_txn_id"], "Money market interest",
                 [L("1010", t["amount"]), L("7000", -t["amount"])])
        elif k == "internal_transfer" and t["account_id"] == "BA-OPER":
            amt = -t["amount"]   # positive = moved out of operating
            both(t["posted_date"], "Transfer", t["bank_txn_id"], t["description"],
                 [L("1010", amt), L("1000", -amt)])

    # ------------------------------------------------------------------ month-end close
    comm_by_month = defaultdict(lambda: defaultdict(float))
    for c in rev.commissions:
        comm_by_month[c["close_date"].replace(day=1)]["total"] += c["amount"]

    prev_def = (0.0, 0.0)
    bonus_accrued = defaultdict(float)
    accrual_bills = {}
    for b in spend.bills:
        if vend_by_name.get(b["vendor_name"], {}).get("accrue_monthly") and b["service_period_start"]:
            accrual_bills[(b["vendor_name"], b["service_period_start"])] = b
    fixed_assets = [b for b in spend.bills if CATEGORY_ACCOUNT.get(b["category"]) == "1500"]
    prepaid_bills = [b for b in spend.bills if b["vendor_name"] in PREPAID_VENDORS
                     and b["service_period_start"] and days_inclusive(
                         b["service_period_start"], b["service_period_end"]) > 60]

    for m in months_between(C.SIM_START, C.AS_OF):
        me = month_end(m)
        targets = [expected] if not closed(me) else [expected, booked]

        def close_je(ref, memo, lines, d=me):
            for t in targets:
                t.je(d, "Journal Entry", ref, memo, lines, kind="month_end", period=me)

        # deferred revenue true-up
        sub_def, svc_def = deferred_balance(inv_lines, inv_by_id, me)
        d_sub, d_svc = sub_def - prev_def[0], svc_def - prev_def[1]
        prev_def = (sub_def, svc_def)
        close_je(f"DEFREV-{me:%Y%m}", f"Deferred revenue true-up to waterfall {me:%b %Y}",
                 [L("4000", d_sub, desc="Subscription deferral"),
                  L("4100", d_svc, desc="Services deferral"),
                  L("2300", -(d_sub + d_svc))])

        # vendor accruals (bill arrives next month) - auto-reversing on the 1st
        for (vname, svc_start), b in accrual_bills.items():
            if svc_start != m:
                continue
            est = round(b["amount"] * float(rng.normal(1.0, 0.04)) / 100) * 100
            acct = CATEGORY_ACCOUNT[b["category"]]
            klass = cls(b["department"])
            if b["invoice_date"] <= me:
                continue
            close_je(f"ACCR-{vname[:6].upper()}-{me:%Y%m}", f"Accrue {vname} {m:%B %Y}",
                     [L(acct, est, klass, vend=b["vendor_id"]), L("2200", -est)])
            rev_d = me + timedelta(days=1)
            for t in targets:
                t.je(rev_d, "Journal Entry", f"ACCR-{vname[:6].upper()}-{me:%Y%m}-R",
                     f"Reverse accrual {vname} {m:%B %Y}",
                     [L("2200", est), L(acct, -est, klass, vend=b["vendor_id"])],
                     kind="month_end")
        # in the open month the expected books still need accruals for bills not yet received
        if not closed(me):
            for vname in [v for v, x in vend_by_name.items() if x["accrue_monthly"]]:
                if (vname, m) in accrual_bills:
                    continue
                prior = accrual_bills.get((vname, add_months(m, -1)))
                if not prior:
                    continue
                est = round(prior["amount"] * (1.04 if vname.startswith("Amazon") else 0.85)
                            / 100) * 100
                expected.je(me, "Journal Entry", f"ACCR-{vname[:6].upper()}-{me:%Y%m}",
                            f"Accrue {vname} {m:%B %Y} (estimate - invoice not yet received)",
                            [L(CATEGORY_ACCOUNT[prior["category"]], est, cls(prior["department"]),
                               vend=prior["vendor_id"]), L("2200", -est)], kind="month_end",
                            period=me)
            # unapproved recruiter bill sitting in the AP inbox belongs in October expense
            ub = planted.get("unrecorded_bill")
            if ub:
                b = next(x for x in spend.bills if x["bill_id"] == ub["bill_id"])
                expected.je(me, "Journal Entry", f"ACCR-TALENT-{me:%Y%m}",
                            "Accrue unapproved Talentridge placement invoice",
                            [L("6700", b["amount"], cls(b["department"]), vend=b["vendor_id"]),
                             L("2200", -b["amount"])], kind="month_end", period=me)

        # prepaid amortization
        for b in prepaid_bills:
            days = overlap_days(b["service_period_start"], b["service_period_end"], m, me)
            if not days:
                continue
            amt = money(b["amount"] * days / days_inclusive(b["service_period_start"],
                                                           b["service_period_end"]))
            acct = PREPAID_VENDORS[b["vendor_name"]]
            exp = "6620" if acct == "1210" else "6200"
            klass = "G&A" if acct == "1210" else "Sales"
            lines = [L(exp, amt, klass, vend=b["vendor_id"]), L(acct, -amt)]
            ref = f"AMORT-{b['bill_id']}-{me:%Y%m}"
            memo = f"Amortize {b['vendor_name']} prepaid {m:%b %Y}"
            if b["vendor_name"] == "Salesforce" and b["invoice_date"].year == 2026:
                expected.je(me, "Journal Entry", ref, memo, lines, kind="month_end", period=me)
            else:
                close_je(ref, memo, lines)

        # depreciation (straight line, starts the month after the asset is placed in service)
        dep = 0.0
        for b in fixed_assets:
            in_service = add_months(b["invoice_date"].replace(day=1), 1)
            if in_service <= m < add_months(in_service, DEPRECIATION_MONTHS):
                dep += b["amount"] / DEPRECIATION_MONTHS
        if dep:
            close_je(f"DEPR-{me:%Y%m}", f"Depreciation {m:%b %Y}",
                     [L("6950", dep, "G&A"), L("1550", -dep)])

        # commissions earned this month (paid next month)
        comm = comm_by_month[m]["total"]
        if comm:
            close_je(f"COMM-{me:%Y%m}", f"Accrue commissions on {m:%b %Y} bookings",
                     [L("6030", comm, "Sales"), L("2210", -comm)])

        # bonus accrual (non-sales) and March true-up for the prior year's payout
        acc_lines = []
        total_acc = 0.0
        for dept in C.DEPARTMENTS:
            if dept == "Sales":
                continue
            base = sum(e["annual_salary"] for e in sim["employees"]
                       if e["department"] == dept and e["hire_date"] <= me and
                       (e["termination_date"] is None or e["termination_date"] > me))
            amt = money(base * C.BONUS_TARGET_PCT / 12 * (0.6 if m.year == 2022 else 1.0))
            if amt:
                acc_lines.append(L(payroll_acct(dept, "bonus"), amt, dept))
                total_acc += amt
        if m.year < C.AS_OF.year or m.month <= C.AS_OF.month:
            bonus_accrued[m.year] += total_acc
            close_je(f"BONUS-{me:%Y%m}", f"Accrue annual bonus {m:%b %Y}",
                     acc_lines + [L("2220", -total_acc)])
        if m.month == 3 and m.year >= 2023:
            diff = money(bonus_accrued[m.year - 1] - bonus_paid[m.year - 1])
            if abs(diff) > 1:
                close_je(f"BONUS-TU-{m.year - 1}", f"True-up {m.year - 1} bonus accrual to payout",
                         [L("2220", diff), L("6040", -diff, "G&A")])
            bonus_accrued[m.year - 1] = 0.0

    return expected, booked, errors
