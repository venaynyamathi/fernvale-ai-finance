"""People: the employee roster (HRIS) and payroll runs (Gusto-style payroll system)."""
from collections import defaultdict
from datetime import date, timedelta

import numpy as np

from . import config as C
from .util import (NameFactory, add_months, months_between, month_end, prev_business_day,
                   add_business_days, money)

TITLES = {
    "Engineering": [("Software Engineer", 0.55), ("Senior Software Engineer", 0.3),
                    ("Staff Engineer", 0.1), ("Engineering Manager", 0.05)],
    "Product": [("Product Manager", 0.6), ("Product Designer", 0.4)],
    "Sales": [("Account Executive", 0.62), ("Sales Development Rep", 0.28),
              ("Sales Engineer", 0.10)],
    "Marketing": [("Demand Generation Manager", 0.4), ("Product Marketing Manager", 0.35),
                  ("Content Marketing Manager", 0.25)],
    "Customer Success": [("Customer Success Manager", 0.85), ("Onboarding Specialist", 0.15)],
    "Support": [("Support Engineer", 0.8), ("Support Lead", 0.2)],
    "G&A": [("Finance Manager", 0.25), ("People Operations Manager", 0.25),
            ("Recruiter", 0.3), ("Office & IT Manager", 0.2)],
}

FOUNDERS = [
    ("Chief Executive Officer", "G&A", 185_000),
    ("Chief Technology Officer", "Engineering", 185_000),
    ("Head of Product", "Product", 170_000),
    ("Founding Engineer", "Engineering", 160_000),
    ("Founding Engineer", "Engineering", 155_000),
    ("Head of Sales", "Sales", 150_000),
]

# One-off leadership hires layered on top of the generic hiring plan
LEADERSHIP_HIRES = [
    (date(2024, 5, 13), "VP Marketing", "Marketing", 215_000),
    (date(2025, 2, 10), "Controller", "G&A", 195_000),
    (date(2026, 6, 8), "VP Engineering", "Engineering", 265_000),
    (date(2026, 7, 13), "VP Sales", "Sales", 240_000),
]


def _target(d: date):
    pts = C.HEADCOUNT_TARGETS
    if d <= pts[0][0]:
        return dict(pts[0][1])
    for (d0, t0), (d1, t1) in zip(pts, pts[1:]):
        if d0 <= d <= d1:
            w = (d - d0).days / (d1 - d0).days
            return {k: t0[k] + w * (t1[k] - t0[k]) for k in t0}
    return dict(pts[-1][1])


def build_roster(rng: np.random.Generator, names: NameFactory):
    employees = []
    comp = []

    def hire(dept, title, hire_date, salary, quota=False):
        eid = f"E{len(employees) + 1:04d}"
        employees.append({
            "employee_id": eid, "full_name": names.person(), "department": dept,
            "title": title, "hire_date": hire_date, "termination_date": None,
            "termination_reason": None, "annual_salary": salary,
            "is_quota_carrying": int(quota), "location": str(rng.choice(
                ["Oakland, CA", "Oakland, CA", "Remote - CA", "Remote - NY", "Remote - TX",
                 "Remote - WA", "Remote - CO"])),
            "employment_type": "Full-time",
        })
        comp.append({"employee_id": eid, "effective_date": hire_date, "annual_salary": salary,
                     "reason": "Hire"})
        return eid

    for i, (title, dept, sal) in enumerate(FOUNDERS):
        hire(dept, title, C.COMPANY["founded"] + timedelta(days=0 if i < 3 else 14 * i), sal)
    lead_queue = list(LEADERSHIP_HIRES)
    attrition_rng = np.random.default_rng(C.SEED + 1)   # separate stream for departures

    for m in months_between(C.SIM_START, C.AS_OF):
        # leadership hires scheduled this month
        for item in [x for x in lead_queue if x[0].year == m.year and x[0].month == m.month]:
            d, title, dept, sal = item
            hire(dept, title, d, sal)
            lead_queue.remove(item)

        active = [e for e in employees if e["hire_date"] <= month_end(m)
                  and (e["termination_date"] is None or e["termination_date"] > m)]
        # attrition (founders and leadership hires excluded)
        for e in active:
            if e["employee_id"] <= "E0006" or e["title"].startswith(("VP", "Controller")):
                continue
            if e["hire_date"] > add_months(m, -4):
                continue
            if attrition_rng.random() < C.ANNUAL_ATTRITION / 12:
                e["termination_date"] = m + timedelta(days=int(attrition_rng.integers(3, 27)))
                e["termination_reason"] = str(attrition_rng.choice(
                    ["Voluntary - new opportunity", "Voluntary - relocation",
                     "Voluntary - career change", "Involuntary - performance"],
                    p=[0.55, 0.15, 0.1, 0.2]))

        target = _target(month_end(m))
        counts = defaultdict(int)
        for e in employees:
            if e["hire_date"] <= month_end(m) and (e["termination_date"] is None
                                                  or e["termination_date"] > month_end(m)):
                counts[e["department"]] += 1
        for dept in C.DEPARTMENTS:
            need = int(np.floor(target[dept] + 0.35)) - counts[dept]
            for _ in range(max(0, need)):
                titles, probs = zip(*TITLES[dept])
                title = str(rng.choice(titles, p=probs))
                lo, hi = C.SALARY_BANDS[dept]
                sal = round(float(rng.uniform(lo, hi)) / 500) * 500
                if "Senior" in title or "Staff" in title or "Manager" in title:
                    sal = min(hi * 1.1, sal * 1.08)
                hd = m + timedelta(days=int(rng.integers(0, 26)))
                if hd > C.AS_OF:
                    continue
                hire(dept, title, hd, round(sal / 500) * 500,
                     quota=(title == "Account Executive"))

    # January merit increases
    for e in employees:
        for year in range(2023, C.AS_OF.year + 1):
            eff = date(year, 1, 1)
            if e["hire_date"] < date(year - 1, 10, 1) and (
                    e["termination_date"] is None or e["termination_date"] > eff):
                prev = [c for c in comp if c["employee_id"] == e["employee_id"]][-1]
                new = round(prev["annual_salary"] * (1 + C.MERIT_INCREASE
                                                     + float(rng.normal(0, 0.01))) / 500) * 500
                comp.append({"employee_id": e["employee_id"], "effective_date": eff,
                             "annual_salary": new, "reason": "Annual merit"})
        e["annual_salary"] = [c for c in comp if c["employee_id"] == e["employee_id"]][-1][
            "annual_salary"]
    return employees, comp


def salary_on(comp_by_emp, eid, d):
    sal = None
    for c in comp_by_emp[eid]:
        if c["effective_date"] <= d:
            sal = c["annual_salary"]
    return sal


def active_on(e, d):
    return e["hire_date"] <= d and (e["termination_date"] is None or e["termination_date"] > d)


def headcount_by_dept(employees, d):
    out = defaultdict(int)
    for e in employees:
        if active_on(e, d):
            out[e["department"]] += 1
    return out


def ramped_aes(employees, d):
    """Account executives weighted by ramp: 0 for first 2 months, 0.5 for months 3-4."""
    total = 0.0
    for e in employees:
        if e["is_quota_carrying"] and active_on(e, d):
            tenure = (d - e["hire_date"]).days / 30.4
            total += 0 if tenure < 2 else (0.5 if tenure < 4 else 1.0)
    # founders/heads of sales close deals in the early years
    if d < date(2024, 1, 1):
        total += 0.5
    return total


def run_payroll(employees, comp, commissions, rng):
    """Semi-monthly payroll. commissions: list of {employee_id, pay_month(date), amount, opp_id}."""
    comp_by_emp = defaultdict(list)
    for c in comp:
        comp_by_emp[c["employee_id"]].append(c)
    for v in comp_by_emp.values():
        v.sort(key=lambda c: c["effective_date"])

    comm_by_month = defaultdict(list)
    for c in commissions:
        comm_by_month[(c["pay_month"].year, c["pay_month"].month)].append(c)

    runs, items = [], []
    ytd_wages = defaultdict(float)   # (eid, year) -> wages
    for m in months_between(C.SIM_START, C.AS_OF):
        for half in (1, 2):
            p_start = m if half == 1 else m.replace(day=16)
            p_end = m.replace(day=15) if half == 1 else month_end(m)
            if p_start > C.AS_OF:
                continue
            pay_date = prev_business_day(p_end)
            run_id = f"PR-{p_end:%Y%m}-{half}"
            runs.append({"run_id": run_id, "pay_period_start": p_start, "pay_period_end": p_end,
                         "pay_date": pay_date,
                         "funding_debit_date": add_business_days(pay_date, -2),
                         "run_type": "Regular", "status": "Paid"})
            period_days = (p_end - p_start).days + 1
            month_comms = comm_by_month[(m.year, m.month)] if half == 1 else []
            comm_by_emp = defaultdict(float)
            for c in month_comms:
                comm_by_emp[c["employee_id"]] += c["amount"]
            for e in employees:
                s = max(p_start, e["hire_date"])
                t_end = e["termination_date"] - timedelta(days=1) if e["termination_date"] else p_end
                f = min(p_end, t_end)
                days = (f - s).days + 1
                commission = comm_by_emp.get(e["employee_id"], 0.0)
                bonus = 0.0
                if m.month == 3 and half == 1 and e["department"] != "Sales" \
                        and active_on(e, pay_date) and m.year >= 2023:
                    py = m.year - 1
                    start = max(e["hire_date"], date(py, 1, 1))
                    frac = max(0, (date(py, 12, 31) - start).days + 1) / 365
                    sal = salary_on(comp_by_emp, e["employee_id"], date(py, 12, 31)) or 0
                    perf = float(np.clip(rng.normal(1.0, 0.15), 0.6, 1.4))
                    bonus = money(sal * C.BONUS_TARGET_PCT * frac * perf
                                  * (0.6 if py == 2022 else 1.0))
                if days <= 0 and commission == 0 and bonus == 0:
                    continue
                sal = salary_on(comp_by_emp, e["employee_id"], max(s, p_start)) or 0
                base = money(sal / 24 * max(0, days) / period_days) if days > 0 else 0.0
                gross = money(base + commission + bonus)
                if gross <= 0:
                    continue
                yk = (e["employee_id"], p_end.year)
                prior = ytd_wages[yk]
                ss_base = C.SS_WAGE_BASE[p_end.year]
                ss_wages = max(0.0, min(gross, ss_base - prior))
                ui_wages = max(0.0, min(gross, C.FUTA_SUTA_BASE - prior))
                employer_tax = money(ss_wages * 0.062 + gross * 0.0145 + ui_wages * C.FUTA_SUTA_RATE)
                withheld = money(ss_wages * 0.062 + gross * 0.0145 + gross * 0.215)
                ytd_wages[yk] = prior + gross
                items.append({
                    "run_id": run_id, "employee_id": e["employee_id"],
                    "department": e["department"], "base_pay": base,
                    "commission_pay": money(commission), "bonus_pay": bonus,
                    "gross_pay": gross, "employee_taxes_withheld": withheld,
                    "net_pay": money(gross - withheld), "employer_taxes": employer_tax,
                })
    return runs, items
