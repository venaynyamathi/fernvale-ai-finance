"""Revenue side: CRM (opportunities), billing (customers, subscriptions, invoices, payments)."""
from collections import defaultdict
from datetime import date, timedelta

import numpy as np

from . import config as C
from .hr import active_on, ramped_aes
from .util import (NameFactory, add_months, days_inclusive, month_end, months_between, money)

LOST_REASONS = ["Chose competitor", "No budget", "No decision / stalled", "Built in-house",
                "Timing - revisit next year", "Missing integration"]
CHURN_REASONS = ["Budget cuts", "Switched to competitor", "Company acquired", "Low adoption",
                 "Consolidated tooling", "Business closed"]


def list_price(plan, d):
    p = C.PLANS[plan]
    return p["list_price_2026"] if d >= C.PRICE_INCREASE_DATE else p["list_price"]


class RevenueSim:
    def __init__(self, rng: np.random.Generator, names: NameFactory, employees):
        self.rng = rng
        self.names = names
        self.employees = employees
        self.customers = []
        self.subs = []
        self.events = []
        self.invoices = []      # header dicts with "lines"
        self.payments = []      # payment attempts (card and bank)
        self.refunds = []
        self.crm_accounts = []
        self.opps = []
        self.commissions = []
        self._cust_by_name = {}

    # ------------------------------------------------------------------ helpers
    def _ae_owner(self, d):
        aes = [e for e in self.employees if e["is_quota_carrying"] and active_on(e, d)]
        if not aes:
            return "E0006"  # Head of Sales sold everything early on
        return str(self.rng.choice([e["employee_id"] for e in aes]))

    def _new_customer(self, segment, d, name=None, industry=None):
        if name is None:
            name, industry = self.names.company()
        cid = f"C{len(self.customers) + 1:05d}"
        employees_band = {"SMB": (20, 200), "Mid-Market": (200, 1500),
                          "Enterprise": (1500, 15000)}[segment]
        cust = {
            "customer_id": cid, "name": name, "segment": segment, "industry": industry,
            "created_at": d, "payment_method": C.SEGMENTS[segment]["payment_method"],
            "billing_email": f"ap@{name.split()[0].lower()}{cid[-3:]}.example",
            "state": str(self.rng.choice(["CA", "TX", "IL", "OH", "GA", "WA", "NY", "PA",
                                          "NC", "AZ", "CO", "MI", "TN", "MO", "MN"])),
            "employee_count": int(self.rng.integers(*employees_band)),
            "stripe_customer_id": f"cus_{self.rng.integers(10**13, 10**14):x}",
        }
        self.customers.append(cust)
        self.crm_accounts.append({
            "account_id": f"001{cid[1:]}A", "name": name, "industry": industry,
            "segment": segment, "employee_count": cust["employee_count"],
            "billing_customer_id": cid, "account_owner_id": None, "type": "Customer",
            "created_date": d,
        })
        return cust

    def _invoice(self, cust, sub_id, inv_date, lines, kind):
        seg = C.SEGMENTS[cust["segment"]]
        inv = {
            "invoice_id": f"in_{len(self.invoices) + 1:06d}", "customer_id": cust["customer_id"],
            "subscription_id": sub_id, "invoice_date": inv_date,
            "due_date": inv_date + timedelta(days=seg["terms_days"]),
            "collection_method": "charge_automatically" if cust["payment_method"] == "card"
            else "send_invoice",
            "kind": kind, "lines": lines, "total": money(sum(l["amount"] for l in lines)),
            "status": "open", "amount_paid": 0.0, "amount_written_off": 0.0,
            "paid_date": None, "voided_date": None,
        }
        self.invoices.append(inv)
        return inv

    def _event(self, sub, d, etype, seats_before, seats_after, price_before, price_after,
               reason=None):
        self.events.append({
            "event_id": f"evt_{len(self.events) + 1:06d}", "subscription_id": sub["subscription_id"],
            "customer_id": sub["customer_id"], "event_date": d, "event_type": etype,
            "seats_before": seats_before, "seats_after": seats_after,
            "unit_price_before": price_before, "unit_price_after": price_after,
            "mrr_before": money(seats_before * price_before),
            "mrr_after": money(seats_after * price_after), "reason": reason,
        })

    # ------------------------------------------------------------------ collections
    def _collect(self, inv, cust, monthly=False):
        """Simulate how and when the invoice gets paid. Returns False if it never gets paid."""
        rng = self.rng
        if inv["total"] <= 0:
            inv["status"] = "paid"
            return True
        if cust["payment_method"] == "card":
            fail_p = 0.05 if monthly else 0.03
            attempt_dates = [inv["invoice_date"], inv["invoice_date"] + timedelta(days=3),
                             inv["invoice_date"] + timedelta(days=7)]
            for i, d in enumerate(attempt_dates):
                if d > C.AS_OF:
                    return True  # still open at the as-of date
                ok = rng.random() > (fail_p if i == 0 else (0.4 if i == 1 else 0.5))
                self.payments.append({
                    "payment_id": f"py_{len(self.payments) + 1:06d}",
                    "invoice_id": inv["invoice_id"], "customer_id": cust["customer_id"],
                    "attempted_at": d, "amount": inv["total"], "method": "card",
                    "status": "succeeded" if ok else "failed",
                    "failure_reason": None if ok else str(rng.choice(
                        ["card_declined", "insufficient_funds", "expired_card"])),
                })
                if ok:
                    inv["status"], inv["amount_paid"], inv["paid_date"] = "paid", inv["total"], d
                    return True
            inv["status"] = "uncollectible"
            inv["voided_date"] = attempt_dates[-1] + timedelta(days=7)
            return False

        # ACH / wire customers
        seg = cust["segment"]
        if seg == "Mid-Market" and rng.random() < 0.012:
            inv["status"] = "uncollectible"
            inv["voided_date"] = inv["due_date"] + timedelta(days=120)
            if inv["voided_date"] > C.AS_OF:
                inv["status"], inv["voided_date"] = "open", None
            return False
        bucket_p = [0.30, 0.40, 0.25, 0.05] if seg == "Mid-Market" else [0.10, 0.45, 0.35, 0.10]
        bucket = rng.choice(4, p=bucket_p)
        delay = int({0: rng.integers(-12, 0), 1: rng.integers(0, 6), 2: rng.integers(6, 31),
                     3: rng.integers(31, 76)}[bucket])
        pay_date = max(inv["invoice_date"] + timedelta(days=3), inv["due_date"] + timedelta(days=delay))
        if pay_date > C.AS_OF:
            return True
        amount = inv["total"]
        fee = 0.0
        if cust["payment_method"] == "wire" and rng.random() < 0.25:
            fee = float(rng.choice([15.0, 20.0, 25.0, 30.0]))   # intermediary bank fee deducted
        self.payments.append({
            "payment_id": f"py_{len(self.payments) + 1:06d}", "invoice_id": inv["invoice_id"],
            "customer_id": cust["customer_id"], "attempted_at": pay_date,
            "amount": money(amount - fee), "method": cust["payment_method"],
            "status": "succeeded", "failure_reason": None,
        })
        inv["status"], inv["amount_paid"], inv["paid_date"] = "paid", money(amount - fee), pay_date
        inv["amount_written_off"] = fee
        return True

    # ------------------------------------------------------------------ deals
    def _new_deal(self, segment, close_date, forced=None):
        rng = self.rng
        seg = C.SEGMENTS[segment]
        plan = seg["plan"]
        if forced:
            cust = self._new_customer(segment, close_date, forced["name"], "Logistics")
            seats, disc = forced["seats"], forced["discount"]
            start = forced["start"]
        else:
            cust = self._new_customer(segment, close_date)
            seats = int(rng.integers(*seg["seats"]))
            disc = float(rng.uniform(*seg["discount"])) if seg["discount"][1] > 0 else 0.0
            disc = round(disc * 20) / 20
            if segment == "Enterprise":
                start = add_months(close_date.replace(day=1), 1) if close_date.day > 18 \
                    else close_date + timedelta(days=14)
            elif segment == "Mid-Market":
                start = close_date + timedelta(days=int(rng.integers(0, 10)))
            else:
                start = close_date
        price = money(list_price(plan, close_date) * (1 - disc))
        if segment == "SMB":
            interval = "month" if rng.random() < seg["monthly_billing_share"] else "year"
        else:
            interval = "year"
        term = 1 if interval == "month" else (
            24 if segment == "Enterprise" and rng.random() < seg.get("multi_year_share", 0)
            and not forced else 12)
        sub = {
            "subscription_id": f"sub_{len(self.subs) + 1:05d}", "customer_id": cust["customer_id"],
            "plan": plan, "segment": segment, "billing_interval": interval,
            "start_date": start, "term_months": term, "seats": seats, "unit_price": price,
            "discount_pct": disc, "status": "active", "canceled_at": None,
            "cancel_reason": None, "current_term_start": start,
            "current_term_end": add_months(start, term) - timedelta(days=1),
        }
        self.subs.append(sub)
        self._event(sub, start, "new", 0, seats, 0.0, price)
        acv = money(seats * price * 12)
        services = 0.0
        svc = seg["services"]
        if svc and rng.random() < svc["attach_rate"]:
            services = float(round(rng.uniform(*svc["fee"]) / 500) * 500)
        owner = None
        if segment != "SMB":
            owner = self._ae_owner(close_date)
            self.crm_accounts[-1]["account_owner_id"] = owner
            created = close_date - timedelta(days=int(rng.integers(35, 75) if segment ==
                                                      "Mid-Market" else rng.integers(70, 160)))
            oid = self._opp(cust["name"], self.crm_accounts[-1]["account_id"], "New Business",
                            "Closed Won", acv, created, close_date, owner, seats, start, term,
                            services, sub["subscription_id"])
            self.commissions.append({"opp_id": oid, "employee_id": owner,
                                     "close_date": close_date,
                                     "pay_month": add_months(close_date.replace(day=1), 1),
                                     "amount": money(acv * C.COMMISSION_RATE)})
            # the deals we lost while winning this one
            win_rate = 0.24 if segment == "Mid-Market" else 0.2
            for _ in range(int(rng.poisson((1 - win_rate) / win_rate))):
                self._lost_opp(segment, close_date + timedelta(days=int(rng.integers(-25, 25))))
        sub["services_amount"] = services
        return cust, sub

    def _opp(self, acct_name, acct_id, otype, stage, amount, created, close, owner, seats,
             start, term, services, sub_id, lost_reason=None):
        oid = f"006{len(self.opps) + 1:06d}"
        prob = {"Closed Won": 100, "Closed Lost": 0}.get(stage, None)
        self.opps.append({
            "opportunity_id": oid, "account_id": acct_id,
            "name": f"{acct_name} - {otype} {close:%Y}", "type": otype, "stage": stage,
            "amount": amount, "services_amount": services, "probability": prob,
            "created_date": created, "close_date": close, "owner_id": owner,
            "contract_seats": seats, "contract_start_date": start, "term_months": term,
            "billing_subscription_id": sub_id, "lost_reason": lost_reason,
            "forecast_category": "Closed" if stage == "Closed Won" else (
                "Omitted" if stage == "Closed Lost" else None),
        })
        return oid

    def _lost_opp(self, segment, close):
        if close > C.AS_OF:
            return
        rng = self.rng
        name, industry = self.names.company()
        acct_id = f"001P{len(self.crm_accounts):05d}"
        self.crm_accounts.append({
            "account_id": acct_id, "name": name, "industry": industry, "segment": segment,
            "employee_count": int(rng.integers(200, 1500) if segment == "Mid-Market"
                                  else rng.integers(1500, 12000)),
            "billing_customer_id": None, "account_owner_id": self._ae_owner(close),
            "type": "Prospect", "created_date": close - timedelta(days=120),
        })
        seg = C.SEGMENTS[segment]
        seats = int(rng.integers(*seg["seats"]))
        acv = money(seats * list_price(seg["plan"], close) * 12 * 0.9)
        self._opp(name, acct_id, "New Business", "Closed Lost", acv,
                  close - timedelta(days=int(rng.integers(30, 140))), close,
                  self.crm_accounts[-1]["account_owner_id"], seats, None, 12, 0.0, None,
                  lost_reason=str(rng.choice(LOST_REASONS)))

    # ------------------------------------------------------------------ main loop
    def generate_new_business(self):
        rng = self.rng
        for m in months_between(C.SIM_START, C.AS_OF):
            t = (m.year - C.SIM_START.year) * 12 + m.month - C.SIM_START.month
            season = C.BOOKING_SEASONALITY[m.month]
            ramped = ramped_aes(self.employees, m)
            price_drag = 0.93 if m >= C.PRICE_INCREASE_DATE else 1.0
            lam = {
                "SMB": C.SEGMENTS["SMB"]["new_logos_base"] * np.exp(
                    C.SEGMENTS["SMB"]["new_logo_growth"] * t) * season ** 0.5 * price_drag,
                "Mid-Market": C.SEGMENTS["Mid-Market"]["per_ramped_ae"] * ramped * season,
                "Enterprise": C.SEGMENTS["Enterprise"]["per_ramped_ae"] * ramped * season
                * float(np.clip((t - 14) / 30, 0, 1)),  # enterprise motion starts in year 2, matures by year 4
            }
            for seg, l in lam.items():
                for _ in range(int(rng.poisson(l))):
                    day = int(rng.integers(1, 29))
                    # sales-assisted deals cluster toward month end
                    if seg != "SMB" and rng.random() < 0.45:
                        day = int(rng.integers(20, month_end(m).day + 1))
                    close = m.replace(day=day)
                    if close > C.AS_OF:
                        continue
                    self._new_deal(seg, close)
            if m.year == C.BIG_LOGO["start"].year and m.month == 7:
                self._new_deal("Enterprise", date(2023, 7, 27), forced=C.BIG_LOGO)

    def simulate_subscriptions(self):
        for sub in list(self.subs):
            cust = next(c for c in self.customers if c["customer_id"] == sub["customer_id"])
            if sub["billing_interval"] == "month":
                self._run_monthly(sub, cust)
            else:
                self._run_annual(sub, cust)

    def _run_monthly(self, sub, cust):
        rng = self.rng
        seg = C.SEGMENTS[sub["segment"]]
        ps = sub["start_date"]
        n = 0
        while ps <= C.AS_OF:
            if ps >= date(2026, 3, 1) and sub["unit_price"] < list_price(sub["plan"], ps) \
                    and n > 0 and sub.get("_repriced") is None:
                old = sub["unit_price"]
                sub["unit_price"] = money(old * (1 + C.RENEWAL_UPLIFT_AFTER_INCREASE))
                sub["_repriced"] = True
                self._event(sub, ps, "price_change", sub["seats"], sub["seats"], old,
                            sub["unit_price"], "2026 price increase")
            pe = add_months(ps, 1) - timedelta(days=1)
            line = {"description": f"{sub['plan']} plan - {sub['seats']} seats (monthly)",
                    "line_type": "subscription", "quantity": sub["seats"],
                    "unit_price": sub["unit_price"],
                    "amount": money(sub["seats"] * sub["unit_price"]),
                    "service_start": ps, "service_end": pe}
            inv = self._invoice(cust, sub["subscription_id"], ps, [line],
                                "subscription_create" if n == 0 else "subscription_cycle")
            sub["current_term_start"], sub["current_term_end"] = ps, pe
            if not self._collect(inv, cust, monthly=True):
                self._cancel(sub, inv["voided_date"] or ps, "Payment failed (involuntary)",
                             involuntary=True)
                return
            # churn decision at end of the period
            age = n + 1
            p = seg["monthly_logo_churn"] * (1.6 if age <= 6 else 1.0)
            if date(2026, 3, 1) <= ps <= date(2026, 5, 31):
                p *= 1.35  # some SMB customers leave after the price increase
            nxt = add_months(ps, 1)
            if rng.random() < p and nxt <= C.AS_OF:
                self._cancel(sub, pe, str(rng.choice(CHURN_REASONS)))
                return
            if rng.random() < 0.07 and nxt <= C.AS_OF:
                before = sub["seats"]
                delta = int(rng.integers(1, 6)) * (1 if rng.random() < 0.72 else -1)
                sub["seats"] = max(5, before + delta)
                if sub["seats"] != before:
                    self._event(sub, nxt, "expansion" if sub["seats"] > before else "contraction",
                                before, sub["seats"], sub["unit_price"], sub["unit_price"])
            ps = nxt
            n += 1

    def _run_annual(self, sub, cust):
        rng = self.rng
        seg = C.SEGMENTS[sub["segment"]]
        forced = cust["name"] == C.BIG_LOGO["name"]
        first = True
        while sub["current_term_start"] <= C.AS_OF:
            ts, te = sub["current_term_start"], sub["current_term_end"]
            # one invoice per billed year within the term
            for yr in range(sub["term_months"] // 12):
                bs = add_months(ts, 12 * yr)
                if bs > C.AS_OF:
                    break
                be = add_months(bs, 12) - timedelta(days=1)
                lines = [{"description": f"{sub['plan']} plan - {sub['seats']} seats, "
                                         f"{bs:%b %d, %Y} - {be:%b %d, %Y}",
                          "line_type": "subscription", "quantity": sub["seats"],
                          "unit_price": money(sub["unit_price"] * 12),
                          "amount": money(sub["seats"] * sub["unit_price"] * 12),
                          "service_start": bs, "service_end": be}]
                if first and yr == 0 and sub.get("services_amount"):
                    months = seg["services"]["months"]
                    lines.append({"description": "Implementation & onboarding services "
                                                 "(fixed fee)",
                                  "line_type": "services", "quantity": 1,
                                  "unit_price": sub["services_amount"],
                                  "amount": sub["services_amount"], "service_start": bs,
                                  "service_end": add_months(bs, months) - timedelta(days=1)})
                inv_date = bs if sub["segment"] != "Enterprise" else bs - timedelta(days=int(
                    rng.integers(0, 10)))
                inv = self._invoice(cust, sub["subscription_id"], max(inv_date, bs - timedelta(
                    days=10)), lines, "subscription_create" if first and yr == 0 else
                    "subscription_cycle")
                ok = self._collect(inv, cust)
                if not ok:
                    self._cancel(sub, te, "Non-payment", involuntary=True)
                    return
                # SMB annual prepaid customers occasionally cancel within 30 days and get refunded
                if sub["segment"] == "SMB" and first and rng.random() < 0.03 \
                        and inv["paid_date"] and inv["paid_date"] + timedelta(days=20) <= C.AS_OF:
                    rd = inv["paid_date"] + timedelta(days=int(rng.integers(5, 25)))
                    self.refunds.append({"refund_id": f"re_{len(self.refunds) + 1:05d}",
                                         "invoice_id": inv["invoice_id"],
                                         "customer_id": cust["customer_id"],
                                         "refund_date": rd, "amount": inv["total"],
                                         "reason": "requested_by_customer"})
                    inv["status"] = "refunded"
                    inv["refunded_date"] = rd
                    self._cancel(sub, rd, "Refunded within 30 days")
                    return
            # mid-term upsell (co-termed, prorated)
            up_p = seg.get("midterm_upsell_prob", 0.12 if sub["segment"] == "Mid-Market" else 0)
            ud = add_months(ts, 6)
            if up_p and rng.random() < up_p and ud <= C.AS_OF and not forced:
                add = max(5, int(sub["seats"] * rng.uniform(0.1, 0.3)))
                # prorate to the end of the current billed year
                year_end = add_months(ts, 12) - timedelta(days=1)
                frac = days_inclusive(ud, year_end) / days_inclusive(ts, year_end)
                amt = money(add * sub["unit_price"] * 12 * frac)
                before = sub["seats"]
                sub["seats"] += add
                self._event(sub, ud, "expansion", before, sub["seats"], sub["unit_price"],
                            sub["unit_price"], "Mid-term seat add")
                inv = self._invoice(cust, sub["subscription_id"], ud, [{
                    "description": f"Add {add} seats (prorated {ud:%b %d, %Y} - "
                                   f"{year_end:%b %d, %Y})",
                    "line_type": "proration", "quantity": add, "unit_price": money(amt / add),
                    "amount": amt, "service_start": ud, "service_end": year_end}],
                    "subscription_update")
                self._collect(inv, cust)
                owner = self._ae_owner(ud)
                acct = next(a for a in self.crm_accounts if a["billing_customer_id"] ==
                            cust["customer_id"])
                acv = money(add * sub["unit_price"] * 12)
                oid = self._opp(cust["name"], acct["account_id"], "Expansion", "Closed Won", acv,
                                ud - timedelta(days=40), ud - timedelta(days=int(rng.integers(1, 10))),
                                owner, add, ud, 12, 0.0, sub["subscription_id"])
                self.commissions.append({"opp_id": oid, "employee_id": owner, "close_date": ud,
                                         "pay_month": add_months(ud.replace(day=1), 1),
                                         "amount": money(acv * C.COMMISSION_RATE)})

            # renewal decision at term end
            renew_date = te + timedelta(days=1)
            if renew_date > C.AS_OF:
                return
            churn = (forced and renew_date >= C.BIG_LOGO["churn_at"]) or (
                not forced and rng.random() < seg["annual_renewal_churn"])
            acct = next((a for a in self.crm_accounts if a["billing_customer_id"] ==
                         cust["customer_id"]), None)
            if churn:
                reason = "Consolidated tooling" if forced else str(rng.choice(CHURN_REASONS))
                if sub["segment"] != "SMB":
                    self._opp(cust["name"], acct["account_id"], "Renewal", "Closed Lost",
                              money(sub["seats"] * sub["unit_price"] * 12),
                              te - timedelta(days=90), te - timedelta(days=int(rng.integers(5, 30))),
                              acct["account_owner_id"], sub["seats"], renew_date, 12, 0.0,
                              sub["subscription_id"], lost_reason=reason)
                self._cancel(sub, te, reason)
                return
            before_s, before_p = sub["seats"], sub["unit_price"]
            mu, sd = seg["expansion_at_renewal"]
            growth = float(np.clip(rng.normal(mu, sd), -0.3, 0.8))
            if forced:
                growth = 0.0
            sub["seats"] = max(5, int(round(before_s * (1 + growth))))
            if renew_date >= C.PRICE_INCREASE_DATE:
                uplift = C.RENEWAL_UPLIFT_AFTER_INCREASE
            else:
                uplift = float(rng.choice([0.0, 0.0, 0.02, 0.03, 0.05]))
            sub["unit_price"] = money(before_p * (1 + uplift))
            sub["term_months"] = 24 if sub["segment"] == "Enterprise" and not forced and \
                rng.random() < seg.get("multi_year_share", 0) * 0.6 else 12
            sub["current_term_start"] = renew_date
            sub["current_term_end"] = add_months(renew_date, sub["term_months"]) - timedelta(days=1)
            etype = "renewal_expansion" if sub["seats"] > before_s else (
                "renewal_contraction" if sub["seats"] < before_s else "renewal_flat")
            self._event(sub, renew_date, etype, before_s, sub["seats"], before_p,
                        sub["unit_price"])
            if sub["segment"] != "SMB" and acct:
                self._opp(cust["name"], acct["account_id"], "Renewal", "Closed Won",
                          money(sub["seats"] * sub["unit_price"] * 12), te - timedelta(days=90),
                          te - timedelta(days=int(rng.integers(3, 25))), acct["account_owner_id"],
                          sub["seats"], renew_date, sub["term_months"], 0.0,
                          sub["subscription_id"])
            first = False

    def _cancel(self, sub, d, reason, involuntary=False):
        sub["status"] = "canceled"
        sub["canceled_at"] = d
        sub["cancel_reason"] = reason
        self._event(sub, d + timedelta(days=1), "churn", sub["seats"], 0, sub["unit_price"],
                    0.0, reason)

    # ------------------------------------------------------------------ open pipeline
    def build_open_pipeline(self):
        """Open opportunities at the as-of date, closing over the next ~5 months."""
        rng = self.rng
        stages = [("Discovery", 10), ("Solution Validation", 25), ("Proposal", 50),
                  ("Negotiation", 75), ("Contracting", 90)]
        future = [add_months(C.AS_OF.replace(day=1), k) for k in range(1, 6)]
        ramped = ramped_aes(self.employees, C.AS_OF) * 1.15  # the surge hires keep ramping
        for k, m in enumerate(future):
            season = C.BOOKING_SEASONALITY[m.month]
            for seg in ("Mid-Market", "Enterprise"):
                rate = C.SEGMENTS[seg]["per_ramped_ae"]
                expected_wins = rate * ramped * season
                win_rate = 0.24 if seg == "Mid-Market" else 0.2
                n_open = int(rng.poisson(expected_wins / win_rate * (1.0 - 0.12 * k)))
                for _ in range(n_open):
                    close = m.replace(day=int(rng.integers(1, month_end(m).day + 1)))
                    # nearer-term deals sit in later stages
                    stage_idx = int(np.clip(rng.normal(3.2 - 0.8 * k, 1.0), 0, 4))
                    stage, prob = stages[stage_idx]
                    name, industry = self.names.company()
                    acct_id = f"001P{len(self.crm_accounts):05d}"
                    owner = self._ae_owner(C.AS_OF)
                    self.crm_accounts.append({
                        "account_id": acct_id, "name": name, "industry": industry,
                        "segment": seg, "employee_count": int(rng.integers(200, 1500) if seg ==
                                                              "Mid-Market" else rng.integers(1500, 12000)),
                        "billing_customer_id": None, "account_owner_id": owner,
                        "type": "Prospect", "created_date": C.AS_OF - timedelta(days=60),
                    })
                    s = C.SEGMENTS[seg]
                    seats = int(rng.integers(*s["seats"]))
                    disc = float(rng.uniform(*s["discount"]))
                    acv = money(seats * list_price(s["plan"], close) * (1 - disc) * 12)
                    svc = s["services"]
                    services = float(round(rng.uniform(*svc["fee"]) / 500) * 500) \
                        if svc and rng.random() < svc["attach_rate"] else 0.0
                    oid = self._opp(name, acct_id, "New Business", stage, acv,
                                    C.AS_OF - timedelta(days=int(rng.integers(10, 120))), close,
                                    owner, seats, None, 12, services, None)
                    o = self.opps[-1]
                    o["probability"] = prob
                    o["forecast_category"] = "Commit" if prob >= 75 else (
                        "Best Case" if prob >= 50 else "Pipeline")
        # upcoming renewals for active annual subscriptions
        for sub in self.subs:
            if sub["status"] != "active" or sub["billing_interval"] != "year" \
                    or sub["segment"] == "SMB":
                continue
            renew = sub["current_term_end"] + timedelta(days=1)
            if C.AS_OF < renew <= add_months(C.AS_OF, 5):
                acct = next(a for a in self.crm_accounts
                            if a["billing_customer_id"] == sub["customer_id"])
                cust = next(c for c in self.customers if c["customer_id"] == sub["customer_id"])
                stage, prob = ("Negotiation", 75) if renew <= add_months(C.AS_OF, 2) else (
                    "Proposal", 50)
                self._opp(cust["name"], acct["account_id"], "Renewal", stage,
                          money(sub["seats"] * sub["unit_price"] * 12 * 1.05),
                          sub["current_term_end"] - timedelta(days=100),
                          sub["current_term_end"] - timedelta(days=5), acct["account_owner_id"],
                          sub["seats"], renew, 12, 0.0, sub["subscription_id"])
                self.opps[-1]["probability"] = prob
                self.opps[-1]["forecast_category"] = "Commit" if prob >= 75 else "Best Case"

    def finalize(self):
        """Number invoices chronologically, the way a billing system would."""
        self.invoices.sort(key=lambda i: (i["invoice_date"], i["invoice_id"]))
        for n, inv in enumerate(self.invoices, start=10001):
            inv["invoice_number"] = f"FV-{n}"
        self.opps.sort(key=lambda o: (o["close_date"], o["opportunity_id"]))
