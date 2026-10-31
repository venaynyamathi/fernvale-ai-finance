"""Offline tests for the QuickBooks load plan:  python -m tests.test_plan"""
import json
import sqlite3
from collections import defaultdict

from qbo_loader.plan import BOOKS, Planner
from qbo_loader.simulate import net, posting


def main():
    p = Planner()
    ops = p.build()
    fails = []

    # 1. every record posts exactly what the ledger says, account by account
    for o in ops:
        got = net(posting(o["entity"], o["payload"]))
        want = net(o["expect"])
        if got != want:
            fails.append(f"{o['key']} {o['entity']}: posts {got}, ledger {want}")

    # 2. dependencies come first; keys unique
    seen = set()
    for o in ops:
        assert o["key"] not in seen, f"duplicate key {o['key']}"
        for d in o["deps"]:
            if d not in seen:
                fails.append(f"{o['key']} placed before its dependency {d}")
        seen.add(o["key"])

    # 3. every reference points at something the loader will create
    accts, classes = set(p.accounts), set(p.classes)
    custs = {c["id"] for c in p.customers()}
    vends = {v["id"] for v in p.vendors()}
    keys = {o["key"] for o in ops}

    def walk(x, k):
        if isinstance(x, dict):
            for v in x.values():
                walk(v, k)
        elif isinstance(x, list):
            for v in x:
                walk(v, k)
        elif isinstance(x, str) and x.startswith("@"):
            kind, val = x[1:].split(":", 1)
            ok = {"acct": val in accts, "class": val in classes, "cust": val in custs,
                  "vend": val in vends, "item": val in ("SUB", "SVC", "OPEN"),
                  "doc": val in keys}[kind]
            if not ok:
                fails.append(f"{k}: unresolvable reference {x}")

    for o in ops:
        walk(o["payload"], o["key"])

    # 4. QuickBooks field limits
    for o in ops:
        dn = o["payload"].get("DocNumber")
        if dn and len(dn) > 21:
            fails.append(f"{o['key']}: DocNumber too long ({dn})")
        for l in o["payload"].get("Line", []):
            if l.get("Amount", 0) < 0 and o["entity"] != "Deposit":
                fails.append(f"{o['key']}: negative line amount")

    # 5. replaying the whole plan reproduces the ledger at every month-end
    b = sqlite3.connect(BOOKS)
    stmt = dict(b.execute("SELECT account_number, statement FROM accounts"))
    replay = defaultdict(float)
    by_month = defaultdict(lambda: defaultdict(float))
    for o in ops:
        m = o["payload"]["TxnDate"][:7]
        for a, d, c in posting(o["entity"], o["payload"]):
            by_month[m][a] += d - c
    months = sorted(by_month)
    worst = 0.0
    for m in months:
        for a, v in by_month[m].items():
            replay[a] += v
        if m < "2024-10":      # open invoices/bills keep their original (earlier) dates
            continue
        end = f"{m}-31"
        full = dict(b.execute("""SELECT l.account_number, SUM(l.debit - l.credit) FROM gl_lines l
                                 JOIN gl_entries e USING (je_id) WHERE e.txn_date <= ?
                                 AND (e.txn_date >= '2024-11-01' OR l.account_number IN
                                 (SELECT account_number FROM accounts WHERE statement = 'BS'))
                                 GROUP BY 1""", (end,)))
        pre_pl = b.execute("""SELECT COALESCE(SUM(l.debit - l.credit), 0) FROM gl_lines l
                              JOIN gl_entries e USING (je_id) JOIN accounts a USING (account_number)
                              WHERE e.txn_date < '2024-11-01' AND a.statement != 'BS'""").fetchone()[0]
        full["3900"] = full.get("3900", 0.0) + pre_pl
        for a in set(full) | set(replay):
            diff = abs(round(replay.get(a, 0.0) - full.get(a, 0.0), 2))
            if a == "1999":
                diff = abs(round(replay.get(a, 0.0), 2))
            worst = max(worst, diff)
            if diff > 0.01 and len(fails) < 40:
                fails.append(f"{m} {a}: replay {replay.get(a, 0):,.2f} vs ledger "
                             f"{full.get(a, 0):,.2f}")

    print(f"{len(ops)} operations planned; max month-end difference {worst:,.2f}")
    if fails:
        print(f"{len(fails)} problems:")
        for f in fails[:40]:
            print("  " + f)
        raise SystemExit(1)
    print("all plan tests passed")


if __name__ == "__main__":
    main()
