"""Spend side: vendor master, AP bills (bill-pay system) and corporate-card transactions."""
from collections import defaultdict
from datetime import date, timedelta

import numpy as np

from . import config as C
from .hr import active_on, headcount_by_dept
from .util import (add_months, add_business_days, month_end, months_between, money,
                   next_business_day, prev_business_day)

# category -> GL account name the accountant uses (see ledger.py chart of accounts)
VENDORS = [
    # name, category, default department, channel, terms days, accrue (bill arrives after month)
    ("Amazon Web Services", "Hosting", "COGS", "bill", 15, True),
    ("Datadog", "Hosting", "COGS", "card", 0, False),
    ("Twilio", "Hosting", "COGS", "card", 0, False),
    ("Sentry", "Software - R&D", "Engineering", "card", 0, False),
    ("GitHub", "Software - R&D", "Engineering", "card", 0, False),
    ("Atlassian", "Software - R&D", "Engineering", "card", 0, False),
    ("Figma", "Software - R&D", "Product", "card", 0, False),
    ("Google Workspace", "Software - G&A", "G&A", "card", 0, False),
    ("Slack", "Software - G&A", "G&A", "card", 0, False),
    ("Zoom", "Software - G&A", "G&A", "card", 0, False),
    ("Notion", "Software - G&A", "G&A", "card", 0, False),
    ("1Password", "Software - G&A", "G&A", "card", 0, False),
    ("Gusto", "Payroll Fees", "G&A", "card", 0, False),
    ("Salesforce", "Software - Sales", "Sales", "bill", 30, False),
    ("ZoomInfo", "Software - Sales", "Sales", "bill", 30, False),
    ("Gong", "Software - Sales", "Sales", "card", 0, False),
    ("HubSpot", "Software - Marketing", "Marketing", "card", 0, False),
    ("Google Ads", "Advertising", "Marketing", "card", 0, False),
    ("LinkedIn Ads", "Advertising", "Marketing", "card", 0, False),
    ("LinkedIn Recruiter", "Recruiting", "G&A", "card", 0, False),
    ("OpsForward Summit (fictional)", "Events", "Marketing", "bill", 30, False),
    ("Kaltwerk Dev Studio (fictional)", "Contractors - R&D", "Engineering", "bill", 30, False),
    ("Brightquarry Content Co. (fictional)", "Contractors - Marketing", "Marketing", "bill", 30, False),
    ("Harbor Point Properties LLC (fictional)", "Rent", "G&A", "bill", 0, False),
    ("Dovetail Interiors (fictional)", "Fixed Assets", "G&A", "bill", 30, False),
    ("Marlow & Pierce LLP (fictional)", "Legal", "G&A", "bill", 30, True),
    ("Brennan Ostrow CPAs (fictional)", "Accounting & Tax", "G&A", "bill", 30, False),
    ("Keystone Mutual Insurance (fictional)", "Insurance", "G&A", "bill", 30, False),
    ("Bluepine Health Plans (fictional)", "Benefits", "Allocated", "bill", 0, False),
    ("Talentridge Search Partners (fictional)", "Recruiting", "G&A", "bill", 30, False),
    ("Apple", "Computer Equipment", "Allocated", "card", 0, False),
    ("Delaware Division of Corporations", "Taxes & Licenses", "G&A", "card", 0, False),
    ("California Franchise Tax Board", "Taxes & Licenses", "G&A", "card", 0, False),
    ("United Airlines", "Travel", "Sales", "card", 0, False),
    ("Delta Air Lines", "Travel", "Sales", "card", 0, False),
    ("Marriott", "Travel", "Sales", "card", 0, False),
    ("Hilton", "Travel", "Sales", "card", 0, False),
    ("Uber", "Travel", "Sales", "card", 0, False),
    ("DoorDash", "Meals & Entertainment", "G&A", "card", 0, False),
    ("Local restaurants", "Meals & Entertainment", "Sales", "card", 0, False),
    ("Costco Business", "Office Expenses", "G&A", "card", 0, False),
    ("Amazon Business", "Office Expenses", "G&A", "card", 0, False),
]


class SpendSim:
    def __init__(self, rng, employees, mrr_by_month, new_hires_by_month):
        self.rng = rng
        self.employees = employees
        self.mrr = mrr_by_month                 # month start -> MRR at month end
        self.new_hires = new_hires_by_month     # month start -> list of employees hired
        self.vendors = {}
        for i, (name, cat, dept, ch, terms, accrue) in enumerate(VENDORS, start=1):
            self.vendors[name] = {"vendor_id": f"V{i:03d}", "name": name, "category": cat,
                                  "default_department": dept, "payment_channel": ch,
                                  "payment_terms_days": terms, "accrue_monthly": int(accrue)}
        self.bills = []
        self.card_txns = []
        self.statements = []
        self.cardholders = {}

    # ---------------------------------------------------------------- helpers
    def _noise(self, sd=0.05):
        return float(np.clip(self.rng.normal(1, sd), 0.75, 1.3))

    def _bill(self, vendor, inv_date, amount, svc_start, svc_end, memo, dept=None,
              inv_no=None, terms=None, status=None, paid_date=None):
        v = self.vendors[vendor]
        terms = v["payment_terms_days"] if terms is None else terms
        due = inv_date + timedelta(days=terms)
        if paid_date is None:
            paid_date = prev_business_day(due) if due >= inv_date + timedelta(days=3) \
                else next_business_day(inv_date)
            # a few bills get paid late
            if self.rng.random() < 0.08:
                paid_date = next_business_day(paid_date + timedelta(days=int(
                    self.rng.integers(5, 20))))
        if status is None:
            status = "paid" if paid_date <= C.AS_OF else "approved"
        if status != "paid":
            paid_date = None
        next_no = max((int(x["bill_id"][5:]) for x in self.bills), default=0) + 1
        b = {"bill_id": f"BILL-{next_no:05d}", "vendor_id": v["vendor_id"],
             "vendor_name": vendor,
             "invoice_number": inv_no or f"{vendor[:3].upper()}-{inv_date:%y%m}"
                                         f"{int(self.rng.integers(100, 999))}",
             "invoice_date": inv_date, "received_date": inv_date + timedelta(days=int(
                 self.rng.integers(0, 3))),
             "due_date": due, "service_period_start": svc_start, "service_period_end": svc_end,
             "amount": money(amount), "category": v["category"],
             "department": dept or v["default_department"], "status": status,
             "paid_date": paid_date, "memo": memo}
        self.bills.append(b)
        return b

    def _card(self, vendor, d, amount, memo, dept=None, holder=None):
        if d > C.AS_OF:
            return
        v = self.vendors[vendor]
        self.card_txns.append({
            "transaction_id": f"rtx_{len(self.card_txns) + 1:06d}", "transaction_date": d,
            "post_date": add_business_days(d, 1) if d < C.AS_OF else d,
            "merchant": vendor, "vendor_id": v["vendor_id"], "amount": money(amount),
            "category": v["category"], "department": dept or v["default_department"],
            "cardholder_employee_id": holder or self._holder(dept or v["default_department"], d),
            "memo": memo, "receipt_attached": int(self.rng.random() > 0.06),
        })

    def _holder(self, dept, d):
        cands = [e for e in self.employees if active_on(e, d) and (
            e["department"] == dept or dept in ("COGS", "Allocated"))]
        if dept in ("COGS", "G&A", "Allocated") or not cands:
            cands = [e for e in self.employees if active_on(e, d) and
                     e["department"] in ("G&A", "Engineering")] or self.employees[:1]
        return cands[int(self.rng.integers(0, len(cands)))]["employee_id"]

    # ---------------------------------------------------------------- generation
    def generate(self):
        rng = self.rng
        for m in months_between(C.SIM_START, C.AS_OF):
            me = month_end(m)
            hc = headcount_by_dept(self.employees, me)
            total = sum(hc.values())
            mrr = self.mrr.get(m, 0.0)
            post_b = m >= date(2026, 6, 1)
            post_a = m >= date(2024, 4, 1)

            # ---- hosting / COGS
            aws = (0.082 * mrr + 2500 + 4000 * post_a) * self._noise(0.04)
            if m == date(2026, 7, 1):
                aws += 46_250   # one-time data migration to the new region (a real spike)
            inv_d = add_business_days(add_months(m, 1), 1)
            self._bill("Amazon Web Services", inv_d, aws, m, me,
                       f"AWS usage {m:%B %Y}", inv_no=f"EUINUS{m:%y%m}{int(rng.integers(1000, 9999))}")
            dd = (0.011 * mrr + 600) * self._noise(0.06)
            if m == date(2026, 9, 1):
                dd *= 3.1       # log-ingestion overage after a noisy deploy (a real spike)
            self._card("Datadog", prev_business_day(me), dd, f"Datadog {m:%b %Y} usage")
            self._card("Twilio", m.replace(day=2), (0.004 * mrr + 120) * self._noise(0.1),
                       "Twilio messaging credits")

            # ---- R&D tools
            eng, prod = hc["Engineering"], hc["Product"]
            self._card("GitHub", m.replace(day=4), 21 * (eng + prod), "GitHub Team seats")
            self._card("Atlassian", m.replace(day=7), 16 * (eng + prod) + 40, "Jira & Confluence")
            self._card("Sentry", m.replace(day=11), 80 + 26 * eng, "Sentry Business")
            self._card("Figma", m.replace(day=14), 45 * max(1, prod) + 15 * eng // 4, "Figma seats")

            # ---- company-wide tools (true-ups when headcount grows)
            self._card("Google Workspace", m.replace(day=1), 18 * total, "Workspace Business")
            self._card("Slack", m.replace(day=3), 12.5 * total, "Slack Pro")
            self._card("Zoom", m.replace(day=9), 15.99 * max(3, total // 2), "Zoom licenses")
            self._card("Notion", m.replace(day=12), 10 * total, "Notion Plus")
            self._card("1Password", m.replace(day=16), 7.99 * total, "1Password Business")
            self._card("Gusto", m.replace(day=5), 80 + 12 * total, "Gusto Plus")

            # ---- sales tools
            if m.month == 9:     # Salesforce renews annually each September (prepaid)
                users = hc["Sales"] + hc["Customer Success"] + 2
                if post_b:
                    users += 6   # bought seats ahead of the hiring plan
                amt = 165 * 12 * users * (1.07 if m.year >= 2026 else 1.0)
                self._bill("Salesforce", m.replace(day=12), amt, m.replace(day=15),
                           add_months(m.replace(day=15), 12) - timedelta(days=1),
                           f"Salesforce Sales Cloud Enterprise - {users} users, 12 months")
            if m.month == 1 and m.year >= 2024:
                amt = {2024: 14_500, 2025: 19_800, 2026: 27_600}[m.year]
                self._bill("ZoomInfo", m.replace(day=8), amt, m, add_months(m, 12) - timedelta(1),
                           "ZoomInfo SalesOS annual subscription")
            aes = sum(1 for e in self.employees if e["is_quota_carrying"] and active_on(e, me))
            if aes:
                self._card("Gong", m.replace(day=18), 125 * aes, "Gong seats")

            # ---- outsourced engineering capacity
            if m >= date(2024, 6, 1):
                fee = 28_000 if m < date(2025, 1, 1) else (38_000 if m < date(2026, 7, 1) else 20_000)
                self._bill("Kaltwerk Dev Studio (fictional)", me, fee, m, me,
                           f"Dedicated dev team - {m:%B %Y}")

            # ---- marketing
            mkt = hc["Marketing"]
            if mkt:
                self._card("HubSpot", m.replace(day=6), 1200 if m < date(2025, 6, 1) else 3600,
                           "HubSpot Marketing Hub")
            season = {1: 0.85, 2: 0.9, 3: 1.05, 4: 1.0, 5: 1.0, 6: 1.05, 7: 0.85, 8: 0.85,
                      9: 1.1, 10: 1.15, 11: 1.1, 12: 0.8}[m.month]
            gads = (3000 + 5200 * mkt) * season * (1.55 if post_b else 1.0)
            if mkt or m >= date(2022, 6, 1):
                for wk, frac in enumerate((0.27, 0.25, 0.25, 0.23)):
                    self._card("Google Ads", m.replace(day=min(28, 7 * wk + 7)),
                               gads * frac * self._noise(0.08), "Google Ads billing threshold")
            if mkt:
                self._card("LinkedIn Ads", m.replace(day=20), gads * 0.55 * self._noise(0.1),
                           "LinkedIn Campaign Manager")
            if m.month in (3, 9) and m >= date(2024, 3, 1):
                amt = {2024: 18_000, 2025: 26_000, 2026: 42_000}[m.year] * (0.7 if m.month == 3 else 1)
                self._bill("OpsForward Summit (fictional)", m.replace(day=3), amt, m, me,
                           f"Booth sponsorship - OpsForward Summit {m:%b %Y}")
            if m >= date(2024, 6, 1):
                fee = 9_000 if m < date(2026, 1, 1) else 14_000
                self._bill("Brightquarry Content Co. (fictional)", me, fee, m, me,
                           f"Content retainer {m:%B %Y}")

            # ---- facilities
            rent = 9_500 if m < date(2024, 4, 1) else (18_000 if m < date(2026, 8, 1) else 41_000)
            self._bill("Harbor Point Properties LLC (fictional)", m, rent, m, me,
                       f"Office rent {m:%B %Y}", inv_no=f"HPP-{m:%Y%m}")
            if m == date(2026, 7, 1):
                self._bill("Harbor Point Properties LLC (fictional)", m.replace(day=10), 82_000,
                           None, None, "Security deposit - Suite 400 lease (refundable)",
                           inv_no="HPP-DEP-400")
            if m == date(2026, 8, 1):
                self._bill("Dovetail Interiors (fictional)", m.replace(day=14), 186_400, None,
                           None, "Office furniture & buildout - Suite 400", inv_no="DI-24117")

            # ---- professional services
            legal = 2_500 + 900 * (m.year - 2021) + float(rng.uniform(0, 3000))
            if m == date(2024, 3, 1):
                legal += 92_000     # Series A financing
            if m == date(2026, 5, 1):
                legal += 118_000    # Series B financing
            if m == date(2026, 9, 1):
                legal += 14_500     # new office lease review
            inv_d = add_months(m, 1).replace(day=int(rng.integers(6, 12)))
            self._bill("Marlow & Pierce LLP (fictional)", inv_d, legal, m, me,
                       f"Legal services {m:%B %Y}", inv_no=f"INV-{1500 + len(self.bills) % 997}")
            if m.month == 3 and m.year >= 2023:
                self._bill("Brennan Ostrow CPAs (fictional)", m.replace(day=20),
                           6_500 + 3_000 * (m.year - 2023), None, None,
                           f"{m.year - 1} federal & state tax returns")
            if m.year == 2026 and m.month in (4, 5, 6):
                self._bill("Brennan Ostrow CPAs (fictional)", m.replace(day=25), 16_000, None,
                           None, "FY2025 financial statement audit - progress billing")
            if m.month == 2:
                prem = {2022: 9_000, 2023: 15_000, 2024: 24_000, 2025: 38_000, 2026: 64_000}[m.year]
                self._bill("Keystone Mutual Insurance (fictional)", m.replace(day=1), prem,
                           m.replace(day=1), add_months(m, 12) - timedelta(days=1),
                           "D&O, E&O/Cyber and general liability annual premium")

            # ---- benefits (billed on the 1st for the month)
            hc_start = sum(headcount_by_dept(self.employees, m).values())
            self._bill("Bluepine Health Plans (fictional)", m, C.BENEFITS_PER_EMPLOYEE_MONTH *
                       hc_start * (1.06 if m.year >= 2026 else 1.0), m, me,
                       f"Medical/dental/vision premiums {m:%B %Y} ({hc_start} enrolled)",
                       dept="Allocated")

            # ---- recruiting
            if m >= date(2025, 1, 1):
                self._card("LinkedIn Recruiter", m.replace(day=21), 900 if not post_b else 2_700,
                           "LinkedIn Recruiter seats")
            for e in self.new_hires.get(m, []):
                self._card("Apple", e["hire_date"] - timedelta(days=5) if e["hire_date"].day > 6
                           else e["hire_date"], C.LAPTOP_COST * self._noise(0.05),
                           f"MacBook Pro for new hire {e['employee_id']}", dept=e["department"])
                if e["hire_date"] >= date(2026, 6, 1) and rng.random() < 0.45:
                    self._bill("Talentridge Search Partners (fictional)",
                               e["hire_date"] + timedelta(days=5),
                               e["annual_salary"] * C.RECRUITER_FEE_PCT, None, None,
                               f"Placement fee - {e['title']} ({e['employee_id']})",
                               dept=e["department"])

            # ---- taxes & licenses
            if m.month == 3:
                self._card("Delaware Division of Corporations", m.replace(day=1), 400 +
                           (2_100 if m.year >= 2025 else 0), "Delaware franchise tax & annual report")
            if m.month == 4:
                self._card("California Franchise Tax Board", m.replace(day=15), 800,
                           "CA minimum franchise tax")

            # ---- T&E and office
            sales = hc["Sales"] + hc["Customer Success"]
            n_trips = int(rng.poisson(0.55 * sales * season))
            for _ in range(n_trips):
                d = m.replace(day=int(rng.integers(1, me.day + 1)))
                air = str(rng.choice(["United Airlines", "Delta Air Lines"]))
                dept = "Sales" if rng.random() < 0.75 else "Customer Success"
                holder = self._holder(dept, d)
                self._card(air, d, rng.uniform(320, 890), "Customer visit", dept, holder)
                self._card(str(rng.choice(["Marriott", "Hilton"])), d + timedelta(days=2),
                           rng.uniform(380, 1100), "Hotel - customer visit", dept, holder)
                self._card("Uber", d + timedelta(days=1), rng.uniform(35, 140), "Ground transport",
                           dept, holder)
                if rng.random() < 0.6:
                    self._card("Local restaurants", d + timedelta(days=1), rng.uniform(90, 420),
                               "Customer dinner", dept, holder)
            for _ in range(int(rng.poisson(total / 6))):
                d = m.replace(day=int(rng.integers(1, me.day + 1)))
                self._card("DoorDash", d, rng.uniform(40, 380), "Team lunch")
            if total:
                self._card("Costco Business", m.replace(day=int(rng.integers(2, 26))),
                           25 * total * self._noise(0.15), "Office snacks & supplies")
                self._card("Amazon Business", m.replace(day=int(rng.integers(2, 26))),
                           12 * total * self._noise(0.3), "Office supplies & peripherals")

        self._statements()
        self.bills.sort(key=lambda b: (b["invoice_date"], b["bill_id"]))
        self.card_txns.sort(key=lambda t: (t["transaction_date"], t["transaction_id"]))

    def _statements(self):
        """Monthly card statements; the balance is paid by ACH on the 6th of the next month."""
        by_month = defaultdict(list)
        for t in self.card_txns:
            by_month[t["post_date"].replace(day=1)].append(t)
        for m in sorted(by_month):
            me = month_end(m)
            sid = f"STMT-{m:%Y%m}"
            total = money(sum(t["amount"] for t in by_month[m]))
            for t in by_month[m]:
                t["statement_id"] = sid
            pay = next_business_day(add_months(m, 1).replace(day=6))
            self.statements.append({
                "statement_id": sid, "period_start": m, "period_end": me,
                "statement_total": total, "payment_date": pay if pay <= C.AS_OF else None,
                "status": "paid" if pay <= C.AS_OF else ("open" if me <= C.AS_OF else "current"),
            })
