"""
QuickBooks conversion package.

The simulation keeps the company's full history from January 2022, but QuickBooks starts on
BOOKS_START (Nov 1, 2024), the way a real company converts from a legacy system:

  * opening journal entry at the cutoff (Oct 31, 2024) for every balance sheet account, with
    all prior profit and loss rolled into retained earnings
  * accounts receivable and payable are NOT in the journal entry as balances. They are loaded
    as the individual invoices and bills still open at the cutoff, so QuickBooks keeps
    customer and vendor detail. The journal entry puts the net AR/AP amount in 1999
    Conversion Clearing; loading the open invoices and bills brings 1999 back to zero.
  * legacy monthly P&L (Jan 2022 to Oct 2024) is kept as a separate history table for
    trend analysis and forecasting
  * every transaction dated on or after BOOKS_START is loaded as-is
"""
from collections import defaultdict
from datetime import timedelta

from . import config as C
from .ledger import ACCOUNTS

CLEARING = ("1999", "Conversion Clearing", "Other Current Asset", "OtherCurrentAssets", "BS")
AR, AP, RE = "1100", "2000", "3900"


def build_conversion(sim, booked):
    cutoff = C.BOOKS_START - timedelta(days=1)
    rev, spend = sim["rev"], sim["spend"]
    acct = {a[0]: a for a in ACCOUNTS}
    cust = {c["customer_id"]: c for c in rev.customers}
    vend = {v["vendor_id"]: v for v in spend.vendors.values()}
    date_of = {e["je_id"]: e["txn_date"] for e in booked.entries}

    # ---- trial balance at the cutoff
    bal = defaultdict(float)
    pl = defaultdict(float)
    for l in booked.lines:
        d = date_of[l["je_id"]]
        if d > cutoff:
            continue
        amt = l["debit"] - l["credit"]
        bal[l["account_number"]] += amt
        if acct[l["account_number"]][4] != "BS":
            pl[(f"{d:%Y-%m}", l["account_number"], l["class"] or "")] += amt
    re_roll = sum(v for k, v in bal.items() if acct[k][4] != "BS")
    tb = {}
    for k, v in bal.items():
        if acct[k][4] == "BS":
            tb[k] = tb.get(k, 0.0) + v
    tb[RE] = tb.get(RE, 0.0) + re_roll
    tb = {k: round(v, 2) for k, v in tb.items() if abs(v) >= 0.005}

    trial_balance = [{"account_number": k, "account_name": acct[k][1],
                      "debit": v if v > 0 else 0.0, "credit": -v if v < 0 else 0.0}
                     for k, v in sorted(tb.items())]

    # ---- open AR invoices and AP bills at the cutoff
    open_ar = []
    for inv in rev.invoices:
        if inv["invoice_date"] > cutoff:
            continue
        if inv["status"] == "uncollectible" and inv.get("voided_date") and \
                inv["voided_date"] <= cutoff:
            continue
        if inv.get("paid_date") and inv["paid_date"] <= cutoff:
            continue
        if inv["status"] in ("void", "draft"):
            continue
        open_ar.append({
            "invoice_id": inv["invoice_id"], "invoice_number": inv["invoice_number"],
            "customer_id": inv["customer_id"], "customer_name": cust[inv["customer_id"]]["name"],
            "invoice_date": inv["invoice_date"], "due_date": inv["due_date"],
            "open_amount": round(inv["total"], 2),
            "memo": "Opening balance - open at conversion (Oct 31, 2024)"})
    open_ap = []
    for b in spend.bills:
        if b["invoice_date"] > cutoff or b["status"] == "pending_approval":
            continue
        if b.get("paid_date") and b["paid_date"] <= cutoff:
            continue
        open_ap.append({
            "bill_id": b["bill_id"], "invoice_number": b["invoice_number"],
            "vendor_id": b["vendor_id"], "vendor_name": vend[b["vendor_id"]]["name"],
            "invoice_date": b["invoice_date"], "due_date": b["due_date"],
            "open_amount": round(b["amount"], 2),
            "memo": "Opening balance - open at conversion (Oct 31, 2024)"})

    ar_total = round(sum(i["open_amount"] for i in open_ar), 2)
    ap_total = round(sum(b["open_amount"] for b in open_ap), 2)

    # ---- opening journal entry: AR/AP replaced by the clearing account
    je = []
    for k, v in sorted(tb.items()):
        if k in (AR, AP):
            continue
        je.append({"line_no": len(je) + 1, "account_number": k, "account_name": acct[k][1],
                   "debit": v if v > 0 else 0.0, "credit": -v if v < 0 else 0.0,
                   "description": "Opening balance at conversion"})
    clearing = round(ar_total - ap_total, 2)
    je.append({"line_no": len(je) + 1, "account_number": CLEARING[0],
               "account_name": CLEARING[1],
               "debit": clearing if clearing > 0 else 0.0,
               "credit": -clearing if clearing < 0 else 0.0,
               "description": f"Net of open AR ${ar_total:,.2f} and open AP ${ap_total:,.2f}, "
                              "loaded as individual invoices and bills"})
    # rounding between the GL and the subledgers (the GL is the record; sub-cent drift
    # from daily revenue proration) goes to retained earnings
    diff = round(sum(l["debit"] - l["credit"] for l in je), 2)
    if diff:
        for l in je:
            if l["account_number"] == RE:
                net = l["debit"] - l["credit"] - diff
                l["debit"], l["credit"] = (net, 0.0) if net > 0 else (0.0, -net)

    legacy = [{"month": m, "account_number": a, "account_name": acct[a][1],
               "qbo_account_type": acct[a][2], "class": c,
               "net_debit": round(v, 2),
               "amount": round(-v if acct[a][2] in ("Income", "Other Income") else v, 2)}
              for (m, a, c), v in sorted(pl.items()) if abs(v) >= 0.005]

    checks = {
        "cutoff": cutoff,
        "gl_ar": round(tb.get(AR, 0.0), 2), "open_ar_invoices": ar_total,
        "gl_ap": round(-tb.get(AP, 0.0), 2), "open_ap_bills": ap_total,
        "rounding_to_retained_earnings": diff,
    }
    return {
        "opening_trial_balance": (trial_balance, ["account_number", "account_name", "debit",
                                                  "credit"]),
        "opening_journal_entry": (je, ["line_no", "account_number", "account_name", "debit",
                                       "credit", "description"]),
        "open_ar_at_conversion": (open_ar, ["invoice_id", "invoice_number", "customer_id",
                                            "customer_name", "invoice_date", "due_date",
                                            "open_amount", "memo"]),
        "open_ap_at_conversion": (open_ap, ["bill_id", "invoice_number", "vendor_id",
                                            "vendor_name", "invoice_date", "due_date",
                                            "open_amount", "memo"]),
        "legacy_pl_monthly": (legacy, ["month", "account_number", "account_name",
                                       "qbo_account_type", "class", "net_debit", "amount"]),
    }, checks
