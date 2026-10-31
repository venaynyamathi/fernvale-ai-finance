"""
FY2026 board-approved budget, built the way a finance team would have built it in
December 2025: run-rates from 2025 actuals plus explicit plan assumptions. The plan assumed
the Series B would close in March 2026 and hiring would start in April; in reality it closed
in May, which (along with other real events) creates explainable variances.
"""
from collections import defaultdict
from datetime import date

from . import config as C
from .hr import active_on
from .util import add_months, month_end, money

PLAN_ASSUMPTIONS = {
    "built_on": date(2025, 12, 12),
    "approved_by_board": date(2025, 12, 18),
    "series_b_close_assumed": date(2026, 3, 31),
    "december_2025_net_new_arr_forecast": 400_000,
    "net_new_arr_by_quarter": {1: 380_000, 2: 420_000, 3: 560_000, 4: 620_000},  # per month
    "gross_to_net_new_bookings": 1.35,
    "services_revenue_monthly": 35_000,
    "hosting_pct_of_subscription": 0.092,
    "hosting_fixed_monthly": 6_500,
    "payroll_tax_rate_by_quarter": {1: 0.095, 2: 0.078, 3: 0.068, 4: 0.058},
    "benefits_per_head_month": 1_113,
    "agency_recruiting_share_of_hires": 0.30,
    "new_office_move_in": date(2026, 7, 1),
    "new_office_rent": 40_000,
    "headcount_plan_end": {   # plan headcount by department for Sep 2026 onward
        "Engineering": 24, "Product": 6, "Sales": 16, "Marketing": 7,
        "Customer Success": 7, "Support": 5, "G&A": 7},
}


def build_budget(employees, ledger_lines, entries, mrr_by_month):
    """Amounts are positive in each account's natural direction (revenue and expense alike)."""
    A = PLAN_ASSUMPTIONS
    je_date = {e["je_id"]: e["txn_date"] for e in entries}

    # 2025 actuals (Jan-Nov, what was known in December) by account x class per month
    act = defaultdict(float)
    for l in ledger_lines:
        d = je_date[l["je_id"]]
        if date(2025, 1, 1) <= d <= date(2025, 11, 30):
            act[(l["account_number"], l["class"])] += l["debit"] - l["credit"]
    avg25 = {k: v / 11 for k, v in act.items()}
    acct_total = defaultdict(float)
    for (a, c), v in avg25.items():
        acct_total[a] += v

    def mix(acct):
        tot = acct_total.get(acct, 0)
        parts = {c: v for (a, c), v in avg25.items() if a == acct and abs(v) > 0.01}
        if not parts or abs(tot) < 0.01:
            return {"G&A": 1.0}
        return {c: v / tot for c, v in parts.items()}

    nov_sub = -sum(v for (a, c), v in act.items() if a == "4000") / 11   # 2025 average
    # use the November exit rate rather than the 2025 average as the starting point
    months = [date(2026, m, 1) for m in range(1, 13)]

    # ---------------- headcount plan
    dec = date(2025, 12, 1)
    start_hc = defaultdict(int)
    avg_sal = defaultdict(list)
    for e in employees:
        if active_on(e, dec):
            start_hc[e["department"]] += 1
            avg_sal[e["department"]].append(e["annual_salary"])
    avg_sal = {d: sum(v) / len(v) * (1 + C.MERIT_INCREASE) for d, v in avg_sal.items()}
    hc_plan = {}
    for m in months:
        hc_plan[m] = {}
        for d in C.DEPARTMENTS:
            s, t = start_hc[d], A["headcount_plan_end"][d]
            if m.month <= 3:
                hc = s + (1 if m.month >= 2 and d in ("Engineering", "Sales") else 0)
            elif m.month <= 9:
                hc = s + (t - s) * (m.month - 3) / 6
            else:
                hc = t + (m.month - 9) * (1 if d in ("Engineering", "Sales") else 0)
            hc_plan[m][d] = round(hc)

    rows = []

    def add(m, acct, klass, amt, driver):
        if abs(amt) >= 0.5:
            rows.append({"month": m, "account_number": acct, "class": klass,
                         "amount": money(amt), "driver": driver})

    # ---------------- revenue (ARR plan -> recognized revenue)
    arr = mrr_by_month[date(2025, 11, 1)] * 12 + A["december_2025_net_new_arr_forecast"]
    arr_rows = []
    for m in months:
        q = (m.month - 1) // 3 + 1
        net_new = A["net_new_arr_by_quarter"][q]
        start_arr, arr = arr, arr + net_new
        arr_rows.append({"month": m, "plan_ending_arr": money(arr), "plan_net_new_arr": net_new})
        sub_rev = (start_arr + arr) / 2 / 12
        add(m, "4000", None, sub_rev, "Average plan ARR / 12")
        add(m, "4100", None, A["services_revenue_monthly"], "Implementation services plan")
        add(m, "6030", "Sales", net_new * A["gross_to_net_new_bookings"] * C.COMMISSION_RATE,
            "10% of planned gross new ACV")
        add(m, "5000", "Cost of Revenue", sub_rev * A["hosting_pct_of_subscription"]
            + A["hosting_fixed_monthly"], "9.2% of subscription revenue + fixed")
        add(m, "5200", "Cost of Revenue", acct_total.get("5200", 0) * sub_rev / nov_sub,
            "Card fees scale with revenue")
        add(m, "6900", "G&A", sub_rev * 0.003, "0.3% of revenue")

        # ---------------- people costs
        hires = 0
        for d in C.DEPARTMENTS:
            hc = hc_plan[m][d]
            prior = hc_plan[add_months(m, -1)][d] if m.month > 1 else start_hc[d]
            hires += max(0, hc - prior)
            sal = hc * avg_sal.get(d, 120_000) / 12
            add(m, "5100" if d == "Support" else "6000", d, sal, "Plan headcount x avg salary")
            add(m, "5110" if d == "Support" else "6010", d,
                sal * A["payroll_tax_rate_by_quarter"][q], "Employer tax rate by quarter")
            add(m, "5110" if d == "Support" else "6020", d, hc * A["benefits_per_head_month"],
                "Benefits per head")
            if d != "Sales":
                add(m, "5100" if d == "Support" else "6040", d, sal * C.BONUS_TARGET_PCT,
                    "8% bonus target accrual")
        avg_all = sum(avg_sal.values()) / len(avg_sal)
        add(m, "6700", "G&A", 1_500 + hires * A["agency_recruiting_share_of_hires"] * avg_all
            * C.RECRUITER_FEE_PCT, "Agency fee on 30% of planned hires")
        add(m, "6710", "G&A", hires * C.LAPTOP_COST, "Laptop per planned hire")
        total_hc = sum(hc_plan[m].values())
        growth_hc = total_hc / sum(start_hc.values())

        # ---------------- operating expenses from 2025 run-rate + plan items
        def runrate(acct, factor, note):
            for klass, share in mix(acct).items():
                add(m, acct, klass, acct_total.get(acct, 0) * factor * share, note)

        runrate("6200", 1.0 + 0.6 * (growth_hc - 1) + 0.15, "2025 run-rate scaled by headcount")
        ads = 1.25 if m < A["series_b_close_assumed"] else 1.7
        runrate("6300", ads, "2025 run-rate; step-up after Series B")
        add(m, "6310", "Marketing", {3: 30_000, 9: 45_000}.get(m.month, 0), "Two conferences")
        add(m, "6100", "Engineering", 38_000 if m.month <= 6 else 25_000, "Dev agency")
        add(m, "6100", "Marketing", 14_000, "Content retainer")
        runrate("6400", 1.0 + 0.8 * (growth_hc - 1), "Travel scales with GTM headcount")
        runrate("6410", growth_hc, "Meals scale with headcount")
        runrate("6720", growth_hc, "Office scales with headcount")
        runrate("6850", 1.2, "2025 run-rate + 20%")
        rent = 18_000 if m < A["new_office_move_in"] else A["new_office_rent"]
        add(m, "6500", "G&A", rent, "Lease; new office from July")
        legal = 6_500 + (100_000 if m == date(2026, 3, 1) else 0)
        add(m, "6600", "G&A", legal, "Retainer run-rate + Series B financing in March")
        acct_fee = {3: 9_500, 4: 15_000, 5: 15_000, 6: 15_000}.get(m.month, 0)
        add(m, "6610", "G&A", acct_fee, "Tax returns (Mar) + FY25 audit (Apr-Jun)")
        add(m, "6620", "G&A", 55_000 / 12, "2026 insurance premium amortized")
        add(m, "6800", "G&A", {3: 2_500, 4: 800}.get(m.month, 0), "DE franchise + CA min tax")
        add(m, "6950", "G&A", 2_500 if m >= date(2026, 8, 1) else 0,
            "Buildout $150k over 5 years")
        cash = 5_500_000 if m < A["series_b_close_assumed"] else 33_000_000
        add(m, "7000", None, cash * C.TREASURY_YIELD / 12, "Yield on planned cash balance")

    headcount_rows = [{"month": m, "department": d, "planned_headcount": hc}
                      for m in months for d, hc in hc_plan[m].items()]
    return rows, headcount_rows, arr_rows
