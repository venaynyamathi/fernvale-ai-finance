"""Runs the business simulation and returns every source-system table as a list of dicts."""
from collections import defaultdict
from datetime import date, timedelta

import numpy as np

from . import config as C
from .bank import build_bank, build_stripe
from .hr import build_roster, run_payroll
from .revenue import RevenueSim
from .spend import SpendSim
from .util import NameFactory, month_end, months_between, money


def mrr_series(events):
    ev = sorted(events, key=lambda e: (e["event_date"], e["event_id"]))
    out, cur, i = {}, {}, 0
    for m in months_between(C.SIM_START, C.AS_OF):
        me = month_end(m)
        while i < len(ev) and ev[i]["event_date"] <= me:
            cur[ev[i]["subscription_id"]] = ev[i]["mrr_after"]
            i += 1
        out[m] = sum(cur.values())
    return out


def simulate():
    rng = np.random.default_rng(C.SEED)
    names = NameFactory(rng)
    names.used.add(C.BIG_LOGO["name"])

    employees, comp = build_roster(rng, names)

    rev = RevenueSim(rng, names, employees)
    rev.generate_new_business()
    rev.simulate_subscriptions()
    rev.build_open_pipeline()
    rev.finalize()
    planted = plant_revenue_side(rev, rng)

    runs, items = run_payroll(employees, comp, rev.commissions, rng)

    mrr = mrr_series(rev.events)
    hires = defaultdict(list)
    for e in employees:
        hires[e["hire_date"].replace(day=1)].append(e)
    spend = SpendSim(rng, employees, mrr, hires)
    spend.generate()
    # bills that have not reached the AP inbox by the as-of date do not exist yet
    spend.bills = [b for b in spend.bills if b["received_date"] <= C.AS_OF]
    planted.update(plant_spend_side(spend))

    cust_by_id = {c["customer_id"]: c for c in rev.customers}
    stripe_txns, payouts = build_stripe(rev.payments, rev.refunds, rev.customers, rng,
                                        planted_dispute=planted["dispute"])
    vendors_by_id = {v["vendor_id"]: v for v in spend.vendors.values()}
    bank = build_bank(rev, cust_by_id, payouts, runs, items, spend.bills, spend.statements,
                      vendors_by_id)
    return {
        "employees": employees, "comp": comp, "rev": rev, "payroll_runs": runs,
        "payroll_items": items, "spend": spend, "stripe_txns": stripe_txns,
        "payouts": payouts, "bank": bank, "mrr": mrr, "planted": planted,
    }


def plant_revenue_side(rev, rng):
    """Realistic source-system issues that the finance workflows should surface."""
    planted = {}
    inv_by_id = {i["invoice_id"]: i for i in rev.invoices}
    cust_by_id = {c["customer_id"]: c for c in rev.customers}

    # 1) A large enterprise invoice from summer 2026 that has not been paid (collections risk)
    cands = [i for i in rev.invoices if cust_by_id[i["customer_id"]]["segment"] == "Enterprise"
             and date(2026, 6, 1) <= i["invoice_date"] <= date(2026, 8, 15)
             and i["total"] > 50_000 and i["status"] == "paid"]
    cands.sort(key=lambda i: -i["total"])
    if cands:
        inv = cands[0]
        rev.payments = [p for p in rev.payments if p["invoice_id"] != inv["invoice_id"]]
        inv.update(status="open", amount_paid=0.0, paid_date=None, amount_written_off=0.0)
        planted["overdue_invoice"] = {"invoice_id": inv["invoice_id"],
                                      "invoice_number": inv["invoice_number"],
                                      "customer": cust_by_id[inv["customer_id"]]["name"],
                                      "amount": inv["total"], "due_date": inv["due_date"]}

    # 2) A card customer disputes an annual charge in October 2026
    cands = [p for p in rev.payments if p["method"] == "card" and p["status"] == "succeeded"
             and date(2026, 8, 1) <= p["attempted_at"] <= date(2026, 9, 30)
             and 4_000 < p["amount"] < 20_000]
    p = cands[int(rng.integers(0, len(cands)))]
    planted["dispute"] = {"invoice_id": p["invoice_id"], "customer_id": p["customer_id"],
                          "amount": p["amount"], "date": date(2026, 10, 14),
                          "customer": cust_by_id[p["customer_id"]]["name"]}

    # 3) CRM says one more seat block than billing invoiced on a recent enterprise renewal
    cands = [o for o in rev.opps if o["type"] in ("Renewal", "New Business")
             and o["stage"] == "Closed Won" and o["billing_subscription_id"]
             and date(2026, 8, 15) <= o["close_date"] <= date(2026, 10, 25)
             and o["amount"] > 60_000]
    if cands:
        o = cands[-1]
        unit = o["amount"] / 12 / o["contract_seats"]
        o["contract_seats"] += 40
        o["amount"] = money(o["contract_seats"] * unit * 12)
        planted["crm_billing_mismatch"] = {"opportunity_id": o["opportunity_id"],
                                           "subscription_id": o["billing_subscription_id"],
                                           "crm_seats": o["contract_seats"],
                                           "billing_seats": o["contract_seats"] - 40}
    return planted


def plant_spend_side(spend):
    planted = {}
    # A recruiter invoice sitting in the AP inbox awaiting approval (not yet in the books)
    tal = [b for b in spend.bills if b["vendor_name"].startswith("Talentridge")
           and b["invoice_date"] >= date(2026, 10, 1)]
    if not tal:
        # Hiring wound down in mid-September, so create the placement fee for an offer
        # accepted in October (fee is due on acceptance; the hire starts in November).
        tal = [spend._bill("Talentridge Search Partners (fictional)", date(2026, 10, 14),
                           0.20 * 142_000, date(2026, 10, 14), date(2026, 10, 14),
                           "Placement fee - Senior Account Executive (offer accepted "
                           "2026-10-12, start date 2026-11-02)", dept="Sales",
                           status="pending_approval")]
    if tal:
        b = tal[-1]
        b.update(status="pending_approval", paid_date=None)
        planted["unrecorded_bill"] = {"bill_id": b["bill_id"], "vendor": b["vendor_name"],
                                      "amount": b["amount"], "invoice_date": b["invoice_date"]}
    return planted
