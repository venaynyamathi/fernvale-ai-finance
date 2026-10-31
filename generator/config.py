"""
Company design for Fernvale Systems, Inc. — a fictional high-growth B2B SaaS company.

Everything the simulation does is driven by the assumptions in this file. Change a
number here, rerun `python -m generator.build`, and the whole company regenerates.
All names of the company, its customers, landlord and professional-service firms are
invented. Well-known software vendors (AWS, Slack, etc.) appear only as expense payees.
"""
from datetime import date

SEED = 20261030

COMPANY = {
    "name": "Fernvale Systems, Inc.",
    "short_name": "Fernvale",
    "product": "Fernvale Flow",
    "description": "Workflow automation platform for operations teams at logistics, "
                   "manufacturing and field-service companies.",
    "domain": "fernvale.example",
    "hq": "Oakland, CA",
    "fiscal_year_end": "December 31",
    "founded": date(2022, 1, 3),
}

# Simulation window. The source systems hold the full company history; the books
# (QuickBooks) start from opening balances at BOOKS_START.
SIM_START = date(2022, 1, 1)
BOOKS_START = date(2024, 11, 1)     # first month loaded into QuickBooks
LAST_CLOSED = date(2026, 9, 30)     # last month that is fully closed in the books
AS_OF = date(2026, 10, 31)          # data runs through this date; October is the open month

# ---------------------------------------------------------------------------
# Funding history (cash in to the operating account)
# ---------------------------------------------------------------------------
FUNDING = [
    {"date": date(2022, 1, 6), "round": "Seed", "amount": 5_000_000,
     "lead": "Tallgrass Ventures (fictional)"},
    {"date": date(2024, 3, 8), "round": "Series A", "amount": 14_000_000,
     "lead": "Ninebark Capital (fictional)"},
    {"date": date(2026, 5, 19), "round": "Series B", "amount": 32_000_000,
     "lead": "Corvid Partners (fictional)"},
]

# ---------------------------------------------------------------------------
# Pricing and segments
# ---------------------------------------------------------------------------
PRICE_INCREASE_DATE = date(2026, 1, 1)   # list prices rise ~11-12% for new business
PLANS = {
    #            list $/seat/month  before / after price increase
    "Starter":    {"segment": "SMB", "list_price": 45.0, "list_price_2026": 50.0},
    "Growth":     {"segment": "Mid-Market", "list_price": 60.0, "list_price_2026": 67.0},
    "Enterprise": {"segment": "Enterprise", "list_price": 72.0, "list_price_2026": 80.0},
}
RENEWAL_UPLIFT_AFTER_INCREASE = 0.07     # existing customers get a smaller uplift at renewal

SEGMENTS = {
    "SMB": {
        "plan": "Starter",
        "seats": (10, 45),
        "monthly_billing_share": 0.62,       # rest prepay annually by card
        "payment_method": "card",
        "monthly_logo_churn": 0.021,          # month-to-month customers
        "annual_renewal_churn": 0.16,
        "expansion_at_renewal": (0.08, 0.10),  # mean, sd of seat growth
        "discount": (0.0, 0.0),
        "terms_days": 0,
        "new_logos_base": 1.0,               # self-serve sign-ups per month at SIM_START
        "new_logo_growth": 0.045,             # monthly growth in self-serve sign-up rate
        "services": None,
    },
    "Mid-Market": {
        "plan": "Growth",
        "seats": (30, 115),
        "monthly_billing_share": 0.0,
        "payment_method": "ach",
        "annual_renewal_churn": 0.09,
        "expansion_at_renewal": (0.13, 0.12),
        "discount": (0.0, 0.10),
        "terms_days": 30,
        "per_ramped_ae": 0.48,               # new logos per fully ramped AE per month
        "services": {"attach_rate": 0.4, "fee": (8_000, 15_000), "months": 2},
    },
    "Enterprise": {
        "plan": "Enterprise",
        "seats": (130, 420),
        "monthly_billing_share": 0.0,
        "payment_method": "wire",
        "annual_renewal_churn": 0.05,
        "expansion_at_renewal": (0.17, 0.14),
        "discount": (0.05, 0.25),
        "terms_days": 45,
        "per_ramped_ae": 0.14,
        "multi_year_share": 0.3,             # 2-year terms, billed annually
        "midterm_upsell_prob": 0.3,
        "services": {"attach_rate": 1.0, "fee": (25_000, 60_000), "months": 3},
    },
}

# Bookings seasonality: quarter-end months and December are heavier.
BOOKING_SEASONALITY = {1: 0.75, 2: 0.85, 3: 1.2, 4: 0.85, 5: 0.95, 6: 1.2,
                       7: 0.8, 8: 0.85, 9: 1.2, 10: 0.95, 11: 1.0, 12: 1.4}

# Named storyline customers (forced events)
BIG_LOGO = {
    "name": "Halvorsen Freight Group",
    "segment": "Enterprise",
    "start": date(2023, 8, 1),
    "seats": 410,
    "discount": 0.12,
    "churn_at": date(2026, 8, 1),     # does not renew: consolidated onto an in-house tool
}

# ---------------------------------------------------------------------------
# Headcount plan (target headcount by department at points in time; linear between)
# ---------------------------------------------------------------------------
DEPARTMENTS = ["Engineering", "Product", "Sales", "Marketing", "Customer Success",
               "Support", "G&A"]
HEADCOUNT_TARGETS = [
    (date(2022, 1, 1),  {"Engineering": 3, "Product": 1, "Sales": 1, "Marketing": 0,
                         "Customer Success": 0, "Support": 0, "G&A": 1}),
    (date(2023, 6, 1),  {"Engineering": 6, "Product": 1, "Sales": 3, "Marketing": 1,
                         "Customer Success": 1, "Support": 1, "G&A": 1}),
    (date(2024, 4, 1),  {"Engineering": 8, "Product": 2, "Sales": 4, "Marketing": 2,
                         "Customer Success": 2, "Support": 2, "G&A": 2}),
    (date(2024, 11, 1), {"Engineering": 12, "Product": 2, "Sales": 6, "Marketing": 3,
                         "Customer Success": 3, "Support": 3, "G&A": 3}),
    (date(2025, 12, 1), {"Engineering": 16, "Product": 3, "Sales": 9, "Marketing": 4,
                         "Customer Success": 5, "Support": 4, "G&A": 5}),
    # near hiring freeze while the Series B is being raised
    (date(2026, 5, 20), {"Engineering": 17, "Product": 4, "Sales": 10, "Marketing": 5,
                         "Customer Success": 5, "Support": 4, "G&A": 5}),
    # post-Series-B hiring surge
    (date(2026, 9, 15), {"Engineering": 25, "Product": 6, "Sales": 17, "Marketing": 7,
                         "Customer Success": 7, "Support": 5, "G&A": 7}),
]
ANNUAL_ATTRITION = 0.16

SALARY_BANDS = {   # annual base salary range by department
    "Engineering": (150_000, 230_000),
    "Product": (155_000, 215_000),
    "Sales": (95_000, 165_000),
    "Marketing": (110_000, 175_000),
    "Customer Success": (90_000, 140_000),
    "Support": (70_000, 100_000),
    "G&A": (95_000, 210_000),
}
MERIT_INCREASE = 0.04             # applied each January
BONUS_TARGET_PCT = 0.08           # non-sales staff; accrued monthly, paid in March
COMMISSION_RATE = 0.10            # of first-year subscription ACV, paid month after close
BENEFITS_PER_EMPLOYEE_MONTH = 1_050
RECRUITER_FEE_PCT = 0.20          # agency fee on salary, used on ~45% of hires after Series B
LAPTOP_COST = 2_400

SS_WAGE_BASE = {2022: 147_000, 2023: 160_200, 2024: 168_600, 2025: 176_100, 2026: 184_500}
FUTA_SUTA_BASE = 9_500            # combined unemployment wage base (simplified)
FUTA_SUTA_RATE = 0.042

# ---------------------------------------------------------------------------
# Banking
# ---------------------------------------------------------------------------
BANK_NAME = "Pacific Crest Bank (fictional)"
TREASURY_YIELD = 0.041            # annual yield on the money-market sweep account
OPERATING_CASH_TARGET = 2_500_000 # excess swept to treasury monthly

STRIPE_PCT = 0.029
STRIPE_FIXED = 0.30
