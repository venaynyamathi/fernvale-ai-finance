"""Date and naming helpers shared by the generator."""
import calendar
from datetime import date, timedelta

import numpy as np


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def months_between(start: date, end: date):
    """Yield the first day of each month from start's month through end's month."""
    cur = month_start(start)
    while cur <= end:
        yield cur
        cur = add_months(cur, 1)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5


def next_business_day(d: date) -> date:
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def prev_business_day(d: date) -> date:
    while not is_business_day(d):
        d -= timedelta(days=1)
    return d


def add_business_days(d: date, n: int) -> date:
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining:
        d += timedelta(days=step)
        if is_business_day(d):
            remaining -= 1
    return d


def days_inclusive(a: date, b: date) -> int:
    return (b - a).days + 1


def overlap_days(a1: date, a2: date, b1: date, b2: date) -> int:
    lo, hi = max(a1, b1), min(a2, b2)
    return max(0, (hi - lo).days + 1)


def money(x: float) -> float:
    return float(round(x + 0.0, 2))


# ---------------------------------------------------------------------------
# Fictional names
# ---------------------------------------------------------------------------
_PREFIX = ["Alder", "Basalt", "Bluestem", "Brackenridge", "Cedarline", "Cinder", "Clearwater",
           "Copperfield", "Corrigan", "Driftwood", "Elmstead", "Fallowmere", "Flint", "Foxglove",
           "Granite", "Greywater", "Halden", "Harrowgate", "Hollis", "Ironleaf", "Juniper",
           "Kestrel", "Larkspur", "Lowell", "Maplecrest", "Marrow", "Millrace", "Northgate",
           "Oakhurst", "Osprey", "Palisade", "Pinecroft", "Quarry", "Redfern", "Ridgeway",
           "Rookwood", "Saltmarsh", "Sawtooth", "Silverbell", "Stonebridge", "Sumner",
           "Tamarack", "Thornbury", "Timberline", "Upland", "Vantor", "Wexley", "Whitlock",
           "Willowbend", "Yarrow", "Ambrose", "Belmar", "Calder", "Dunmore", "Eastwick",
           "Fenwick", "Garland", "Hartwell", "Kingsley", "Lockhart", "Merriam", "Norcross",
           "Pemberton", "Radcliffe", "Sheffield", "Talbot", "Underhill", "Westbrook"]
_INDUSTRY_NOUNS = {
    "Logistics": ["Freight", "Logistics", "Transport", "Haulage", "Shipping", "Cartage"],
    "Manufacturing": ["Manufacturing", "Fabrication", "Industries", "Components", "Machining",
                      "Plastics"],
    "Field Services": ["Field Services", "Mechanical", "Electric", "HVAC", "Plumbing",
                       "Facility Services"],
    "Distribution": ["Supply", "Distribution", "Wholesale", "Trading"],
    "Construction": ["Builders", "Construction", "Contracting", "Concrete"],
    "Utilities": ["Energy Services", "Water Works", "Power Systems"],
}
_SUFFIX = ["Co.", "Inc.", "LLC", "Group", "Partners", "Corp.", "Holdings", ""]

FIRST_NAMES = ["Aaron", "Abigail", "Adrian", "Aisha", "Alejandro", "Alicia", "Amara", "Andre",
               "Anika", "Ben", "Bianca", "Caleb", "Camila", "Carmen", "Chloe", "Daniel", "Daria",
               "David", "Devon", "Diego", "Elena", "Eli", "Emeka", "Emily", "Ethan", "Fatima",
               "Gabriel", "Grace", "Hana", "Hector", "Imani", "Isaac", "Jasmine", "Javier",
               "Jenna", "Jonah", "Julia", "Kai", "Kenji", "Laila", "Leo", "Lucia", "Malik",
               "Maya", "Mei", "Miguel", "Nadia", "Naomi", "Nikhil", "Noah", "Olivia", "Omar",
               "Priya", "Quinn", "Rafael", "Riya", "Rosa", "Ryan", "Samir", "Sara", "Sofia",
               "Tariq", "Theo", "Uma", "Victor", "Wei", "Yara", "Zoe", "Marcus", "Hannah",
               "Owen", "Leah", "Felix", "Iris", "Rohan", "Talia", "Simone", "Arjun", "Elise"]
LAST_NAMES = ["Abbott", "Agarwal", "Alvarez", "Baker", "Banerjee", "Bennett", "Castillo", "Chen",
              "Cohen", "Delgado", "Dubois", "Edwards", "Farouk", "Fischer", "Garcia", "Gupta",
              "Hale", "Hansen", "Hughes", "Ibarra", "Iyer", "Jensen", "Kapoor", "Kim", "Kowalski",
              "Larsen", "Lee", "Lindqvist", "Lopez", "Mahoney", "Mensah", "Moreau", "Nakamura",
              "Novak", "Okafor", "Olsen", "Ortiz", "Park", "Patel", "Petrov", "Quintero", "Reyes",
              "Rossi", "Sato", "Schmidt", "Shah", "Silva", "Sokolov", "Tanaka", "Thompson",
              "Turner", "Vargas", "Walsh", "Weber", "Whitaker", "Xu", "Yilmaz", "Zhang", "Murphy",
              "Owens", "Brennan", "Calloway", "Duarte", "Ellison", "Fontaine", "Greer"]


class NameFactory:
    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.used = set()

    def company(self, reserved=()):
        self.used.update(reserved)
        for _ in range(10_000):
            industry = str(self.rng.choice(list(_INDUSTRY_NOUNS)))
            noun = str(self.rng.choice(_INDUSTRY_NOUNS[industry]))
            pre = str(self.rng.choice(_PREFIX))
            suf = str(self.rng.choice(_SUFFIX))
            name = f"{pre} {noun} {suf}".strip()
            if name not in self.used:
                self.used.add(name)
                return name, industry
        raise RuntimeError("ran out of company names")

    def person(self):
        for _ in range(10_000):
            n = f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(LAST_NAMES)}"
            if n not in self.used:
                self.used.add(n)
                return n
        raise RuntimeError("ran out of person names")
