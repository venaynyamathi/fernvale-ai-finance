"""Money movement: Stripe balance & payouts, and the bank accounts (operating + treasury)."""
from collections import defaultdict
from datetime import date, timedelta

from . import config as C
from .util import (add_business_days, is_business_day, month_end, months_between, money,
                   next_business_day, prev_business_day)


def build_stripe(payments, refunds, customers, rng, planted_dispute=None):
    cust = {c["customer_id"]: c for c in customers}
    txns = []
    for p in payments:
        if p["method"] != "card" or p["status"] != "succeeded":
            continue
        fee = money(p["amount"] * C.STRIPE_PCT + C.STRIPE_FIXED)
        txns.append({"balance_txn_id": f"txn_{len(txns) + 1:06d}", "type": "charge",
                     "source_id": p["payment_id"].replace("py_", "ch_"),
                     "invoice_id": p["invoice_id"], "customer_id": p["customer_id"],
                     "created": p["attempted_at"],
                     "available_on": add_business_days(p["attempted_at"], 2),
                     "amount": p["amount"], "fee": fee, "net": money(p["amount"] - fee),
                     "description": f"Charge for invoice {p['invoice_id']}"})
        p["stripe_charge_id"] = txns[-1]["source_id"]
    for r in refunds:
        txns.append({"balance_txn_id": f"txn_{len(txns) + 1:06d}", "type": "refund",
                     "source_id": r["refund_id"], "invoice_id": r["invoice_id"],
                     "customer_id": r["customer_id"], "created": r["refund_date"],
                     "available_on": r["refund_date"], "amount": -r["amount"], "fee": 0.0,
                     "net": -r["amount"], "description": "Refund - requested by customer"})
    if planted_dispute:
        d = planted_dispute
        txns.append({"balance_txn_id": f"txn_{len(txns) + 1:06d}", "type": "dispute",
                     "source_id": "dp_1Q8fernvale", "invoice_id": d["invoice_id"],
                     "customer_id": d["customer_id"], "created": d["date"],
                     "available_on": d["date"], "amount": -d["amount"], "fee": 15.0,
                     "net": money(-d["amount"] - 15.0),
                     "description": "Dispute withdrawal - reason: product_not_received"})
    txns.sort(key=lambda t: (t["created"], t["balance_txn_id"]))

    # daily automatic payouts of everything that has become available
    payouts = []
    pending = sorted(txns, key=lambda t: t["available_on"])
    i = 0
    d = min(t["available_on"] for t in txns)
    while d <= C.AS_OF:
        if is_business_day(d):
            batch = []
            while i < len(pending) and pending[i]["available_on"] <= d:
                batch.append(pending[i])
                i += 1
            if batch:
                amt = money(sum(t["net"] for t in batch))
                if amt > 0:
                    po = f"po_{len(payouts) + 1:05d}"
                    payouts.append({"payout_id": po, "created": d,
                                    "arrival_date": add_business_days(d, 1)
                                    if add_business_days(d, 1) <= C.AS_OF else None,
                                    "amount": amt, "status": "paid"
                                    if add_business_days(d, 1) <= C.AS_OF else "in_transit",
                                    "txn_count": len(batch)})
                    for t in batch:
                        t["payout_id"] = po
                else:  # negative day rolls into the next payout
                    i -= len(batch)
                    for t in batch:
                        t["available_on"] = next_business_day(d + timedelta(days=1))
                    pending[i:] = sorted(pending[i:], key=lambda t: t["available_on"])
        d += timedelta(days=1)
    for t in txns:
        t.setdefault("payout_id", None)
    return txns, payouts


class Bank:
    def __init__(self):
        self.accounts = [
            {"account_id": "BA-OPER", "name": "Operating Checking", "bank": C.BANK_NAME,
             "type": "checking", "last4": "4417"},
            {"account_id": "BA-TRES", "name": "Treasury Money Market", "bank": C.BANK_NAME,
             "type": "money_market", "last4": "9052"},
        ]
        self.txns = []

    def add(self, acct, d, amount, desc, counterparty, ref=None, kind=None):
        if d is None or d > C.AS_OF or abs(amount) < 0.005:
            return
        self.txns.append({"account_id": acct, "posted_date": d, "amount": money(amount),
                          "description": desc, "counterparty": counterparty,
                          "reference": ref, "txn_type": kind})

    def balance(self, acct, upto):
        return sum(t["amount"] for t in self.txns if t["account_id"] == acct
                   and t["posted_date"] <= upto)

    def finalize(self):
        self.txns.sort(key=lambda t: (t["posted_date"], t["account_id"], -t["amount"]))
        bal = defaultdict(float)
        for n, t in enumerate(self.txns, start=1):
            t["bank_txn_id"] = f"BTX-{n:06d}"
            bal[t["account_id"]] += t["amount"]
            t["running_balance"] = money(bal[t["account_id"]])


def build_bank(rev, cust_by_id, stripe_payouts, payroll_runs, payroll_items, bills, statements,
               vendors_by_id):
    bank = Bank()
    for f in C.FUNDING:
        bank.add("BA-OPER", f["date"], f["amount"], f"INCOMING WIRE {f['round'].upper()} "
                 f"PREFERRED STOCK FINANCING", f["lead"], kind="equity_financing")
    for p in stripe_payouts:
        bank.add("BA-OPER", p["arrival_date"], p["amount"], f"STRIPE TRANSFER ST-{p['payout_id']}",
                 "Stripe", p["payout_id"], "stripe_payout")
    for p in rev.payments:
        if p["method"] in ("ach", "wire") and p["status"] == "succeeded":
            c = cust_by_id[p["customer_id"]]
            label = "ACH CREDIT" if p["method"] == "ach" else "WIRE IN"
            bank.add("BA-OPER", p["attempted_at"], p["amount"],
                     f"{label} {c['name'].upper()[:28]}", c["name"], p["invoice_id"],
                     "customer_payment")
    items_by_run = defaultdict(list)
    for it in payroll_items:
        items_by_run[it["run_id"]].append(it)
    for r in payroll_runs:
        its = items_by_run[r["run_id"]]
        net = sum(i["net_pay"] for i in its)
        tax = sum(i["employee_taxes_withheld"] + i["employer_taxes"] for i in its)
        bank.add("BA-OPER", r["funding_debit_date"], -net, f"GUSTO NET {r['run_id']}", "Gusto",
                 r["run_id"], "payroll_net")
        bank.add("BA-OPER", r["funding_debit_date"], -tax, f"GUSTO TAX {r['run_id']}", "Gusto",
                 r["run_id"], "payroll_tax")
    for b in bills:
        if b["status"] == "paid":
            v = vendors_by_id[b["vendor_id"]]
            bank.add("BA-OPER", b["paid_date"], -b["amount"],
                     f"ACH DEBIT {v['name'].upper()[:30]}", v["name"], b["invoice_number"],
                     "bill_payment")
    for s in statements:
        if s["payment_date"]:
            bank.add("BA-OPER", s["payment_date"], -s["statement_total"],
                     f"RAMP CARD PAYMENT {s['statement_id']}", "Ramp", s["statement_id"],
                     "card_payment")

    # monthly bank fee, treasury sweep and interest
    for m in months_between(C.SIM_START, C.AS_OF):
        me = month_end(m)
        bank.add("BA-OPER", prev_business_day(me), -85.0, "ACCOUNT ANALYSIS FEE",
                 C.BANK_NAME, None, "bank_fee")
        tres = bank.balance("BA-TRES", me)
        if tres > 0:
            bank.add("BA-TRES", me, money(tres * C.TREASURY_YIELD / 12), "INTEREST PAID",
                     C.BANK_NAME, None, "interest")
        sweep_day = prev_business_day(me)
        oper = bank.balance("BA-OPER", sweep_day)
        if oper > C.OPERATING_CASH_TARGET + 750_000:
            amt = round((oper - C.OPERATING_CASH_TARGET) / 100_000) * 100_000
            bank.add("BA-OPER", sweep_day, -amt, "TRANSFER TO MMKT x9052", C.BANK_NAME, None,
                     "internal_transfer")
            bank.add("BA-TRES", sweep_day, amt, "TRANSFER FROM CHK x4417", C.BANK_NAME, None,
                     "internal_transfer")
        elif oper < C.OPERATING_CASH_TARGET - 750_000 and bank.balance("BA-TRES", sweep_day) > 0:
            amt = min(bank.balance("BA-TRES", sweep_day),
                      round((C.OPERATING_CASH_TARGET - oper) / 100_000 + 0.5) * 100_000)
            bank.add("BA-TRES", sweep_day, -amt, "TRANSFER TO CHK x4417", C.BANK_NAME, None,
                     "internal_transfer")
            bank.add("BA-OPER", sweep_day, amt, "TRANSFER FROM MMKT x9052", C.BANK_NAME, None,
                     "internal_transfer")
    bank.finalize()
    return bank
