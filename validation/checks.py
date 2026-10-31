"""
Sanity checks and headline metrics:  python -m validation.checks

Ties the ledger back to the source systems (bank, billing, AP, card), recomputes SaaS metrics
from the billing events, and writes validation/report.md.
"""
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "source_systems.sqlite"
BOOKED = ROOT / "build" / "books_as_booked.sqlite"
EXPECTED = ROOT / "private" / "books_expected.sqlite"


def month_ends(start, end):
    out = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        nm = date(y + (m == 12), m % 12 + 1, 1)
        out.append(nm - timedelta(days=1))
        y, m = nm.year, nm.month
    return out


def q(con, sql, *args):
    return con.execute(sql, args).fetchall()


def gl_balance(con, acct, d):
    r = q(con, """SELECT COALESCE(SUM(l.debit - l.credit), 0) FROM gl_lines l
                  JOIN gl_entries e USING (je_id) WHERE l.account_number = ? AND e.txn_date <= ?""",
          acct, d.isoformat())
    return round(r[0][0], 2)


def pl_by_month(con, start, end):
    rows = q(con, """SELECT substr(e.txn_date, 1, 7) AS ym, a.qbo_account_type, l.account_number,
                            SUM(l.debit - l.credit)
                     FROM gl_lines l JOIN gl_entries e USING (je_id)
                     JOIN accounts a ON a.account_number = l.account_number
                     WHERE a.statement = 'PL' AND e.txn_date BETWEEN ? AND ?
                     GROUP BY 1, 2, 3""", start.isoformat(), end.isoformat())
    out = defaultdict(lambda: defaultdict(float))
    for ym, typ, acct, amt in rows:
        out[ym][acct] += amt
        out[ym]["_" + typ] += amt
    return out


def main():
    src = sqlite3.connect(SRC)
    exp = sqlite3.connect(EXPECTED)
    bkd = sqlite3.connect(BOOKED)
    lines = []
    ok = True

    def check(name, passed, detail=""):
        nonlocal ok
        ok &= passed
        lines.append(f"| {'PASS' if passed else 'FAIL'} | {name} | {detail} |")

    as_of = date(2026, 10, 31)
    mes = month_ends(date(2024, 10, 1), as_of)

    # ---------------------------------------------------------------- tie-outs (expected)
    lines += ["## Tie-outs (correct books vs source systems)", "",
              "| Result | Check | Detail |", "|---|---|---|"]
    keys = {"spend_bills": "bill_id", "billing_invoices": "invoice_id",
            "billing_payments": "payment_id", "billing_customers": "customer_id",
            "billing_subscriptions": "subscription_id", "bank_transactions": "bank_txn_id",
            "spend_card_transactions": "transaction_id", "crm_opportunities": "opportunity_id",
            "crm_accounts": "account_id", "hr_employees": "employee_id",
            "stripe_payouts": "payout_id"}
    dupes = {t: q(src, f"SELECT COUNT(*) - COUNT(DISTINCT {k}) FROM {t}")[0][0]
             for t, k in keys.items()}
    check("Record IDs are unique in every source table", not any(dupes.values()),
          ", ".join(f"{t}: {n}" for t, n in dupes.items() if n) or "no duplicates")
    for name, con in (("expected", exp), ("as-booked", bkd)):
        tb = q(con, "SELECT ROUND(SUM(debit) - SUM(credit), 2) FROM gl_lines")[0][0]
        check(f"Trial balance nets to zero ({name})", abs(tb) < 0.01, f"{tb:,.2f}")

    worst = 0
    for d in mes:
        for acct, bank in (("1000", "BA-OPER"), ("1010", "BA-TRES")):
            b = q(src, "SELECT COALESCE(SUM(amount),0) FROM bank_transactions WHERE account_id=? "
                       "AND posted_date <= ?", bank, d.isoformat())[0][0]
            worst = max(worst, abs(gl_balance(exp, acct, d) - b))
    check("GL cash = bank statements at every month-end", worst < 0.01, f"max diff {worst:,.2f}")

    worst = 0
    for d in mes:
        ds = d.isoformat()
        open_ar = q(src, """SELECT COALESCE(SUM(total - CASE WHEN paid_date <= ? THEN amount_paid
                                                         + amount_written_off ELSE 0 END), 0)
                            FROM billing_invoices WHERE invoice_date <= ?
                            AND NOT (status IN ('uncollectible') AND voided_date <= ?)""",
                    ds, ds, ds)[0][0]
        # refunded invoices were paid by card, so they are not in AR
        worst = max(worst, abs(gl_balance(exp, "1100", d) - open_ar))
    check("GL accounts receivable = open invoices in billing", worst < 1.0,
          f"max diff {worst:,.2f}")

    worst = 0
    for d in mes:
        ds = d.isoformat()
        open_ap = q(src, """SELECT COALESCE(SUM(amount), 0) FROM spend_bills
                            WHERE invoice_date <= ? AND status != 'pending_approval'
                            AND (paid_date IS NULL OR paid_date > ?)""", ds, ds)[0][0]
        worst = max(worst, abs(-gl_balance(exp, "2000", d) - open_ap))
    check("GL accounts payable = unpaid bills in AP system", worst < 0.01, f"max diff {worst:,.2f}")

    worst = 0
    for d in mes:
        ds = d.isoformat()
        card = q(src, """SELECT COALESCE((SELECT SUM(amount) FROM spend_card_transactions
                                          WHERE transaction_date <= ?), 0)
                         - COALESCE((SELECT SUM(statement_total) FROM spend_card_statements
                                     WHERE payment_date <= ?), 0)""", ds, ds)[0][0]
        worst = max(worst, abs(-gl_balance(exp, "2100", d) - card))
    check("GL card liability = card activity less statement payments", worst < 0.01,
          f"max diff {worst:,.2f}")

    worst = 0
    for d in mes:
        ds = d.isoformat()
        stripe = q(src, """SELECT COALESCE(SUM(t.amount - CASE WHEN t.type='dispute' THEN 15 ELSE 0 END), 0)
                           FROM stripe_balance_transactions t
                           LEFT JOIN stripe_payouts p USING (payout_id)
                           WHERE t.created <= ? AND (p.arrival_date IS NULL OR p.arrival_date > ?)""",
                   ds, ds)[0][0]
        worst = max(worst, abs(gl_balance(exp, "1050", d) - stripe))
    check("Stripe clearing = charges not yet paid out", worst < 0.01, f"max diff {worst:,.2f}")

    # ---------------------------------------------------------------- planted-difference sanity
    # written to private/ because it reveals where the planted issues are
    diff = ["# As-booked vs correct books at Oct 31, 2026", "",
            "| Account | Correct | As booked | Difference |", "|---|---:|---:|---:|"]
    for acct, name in q(exp, "SELECT account_number, name FROM accounts ORDER BY 1"):
        a, b = gl_balance(exp, acct, as_of), gl_balance(bkd, acct, as_of)
        if abs(a - b) > 0.5:
            diff.append(f"| {acct} {name} | {a:,.0f} | {b:,.0f} | {b - a:,.0f} |")
    (ROOT / "private" / "booked_vs_correct.md").write_text("\n".join(diff) + "\n")

    # ---------------------------------------------------------------- SaaS metrics
    ev = q(src, "SELECT subscription_id, customer_id, event_date, mrr_after FROM "
                "billing_subscription_events ORDER BY event_date, event_id")
    seg = dict(q(src, "SELECT customer_id, segment FROM billing_customers"))
    def mrr_at(d):
        cur = {}
        for sid, cid, ed, mrr in ev:
            if ed <= d.isoformat():
                cur[(sid, cid)] = mrr
        by_cust = defaultdict(float)
        for (sid, cid), v in cur.items():
            by_cust[cid] += v
        return {c: v for c, v in by_cust.items() if v > 0.005}
    snap = {d: mrr_at(d) for d in month_ends(date(2023, 10, 1), as_of)}

    # ---------------------------------------------------------------- QuickBooks conversion
    lines += ["", "## QuickBooks conversion package (opening balances at Oct 31, 2024)", "",
              "| Result | Check | Detail |", "|---|---|---|"]
    cut = "2024-10-31"
    oje = q(bkd, "SELECT account_number, debit - credit FROM opening_journal_entry")
    net = round(sum(v for _, v in oje), 2)
    check("Opening journal entry balances", abs(net) < 0.01, f"{net:,.2f}")
    ar_open = q(bkd, "SELECT ROUND(SUM(open_amount), 2) FROM open_ar_at_conversion")[0][0] or 0
    ap_open = q(bkd, "SELECT ROUND(SUM(open_amount), 2) FROM open_ap_at_conversion")[0][0] or 0
    gl_ar = gl_balance(bkd, "1100", date(2024, 10, 31))
    gl_ap = -gl_balance(bkd, "2000", date(2024, 10, 31))
    check("Open invoices at conversion = GL accounts receivable", abs(ar_open - gl_ar) < 0.01,
          f"{ar_open:,.2f} vs {gl_ar:,.2f}")
    check("Open bills at conversion = GL accounts payable", abs(ap_open - gl_ap) < 0.01,
          f"{ap_open:,.2f} vs {gl_ap:,.2f}")
    # Replay what QuickBooks will hold: opening JE + open AR/AP + every entry from Nov 1, 2024
    stmt = dict(q(bkd, "SELECT account_number, statement FROM accounts"))
    worst_acct, worst = None, 0.0
    for d in ("2025-12-31", "2026-09-30", "2026-10-31"):
        replay = defaultdict(float)
        for a, v in oje:
            replay[a] += v
        replay["1100"] += ar_open
        replay["1999"] -= ar_open
        replay["2000"] -= ap_open
        replay["1999"] += ap_open
        for a, v in q(bkd, """SELECT account_number, SUM(debit - credit) FROM gl_lines_to_load l
                              JOIN gl_entries e USING (je_id) WHERE e.txn_date <= ?
                              GROUP BY 1""", d):
            replay[a] += v
        full = dict(q(bkd, """SELECT account_number, SUM(debit - credit) FROM gl_lines l
                              JOIN gl_entries e USING (je_id) WHERE e.txn_date <= ? GROUP BY 1""",
                      d))
        # in the full history, prior-year P&L sits in the P&L accounts; in QuickBooks it is
        # in retained earnings as of the cutoff
        full_bs = defaultdict(float)
        for a, v in full.items():
            if stmt[a] == "BS":
                full_bs[a] += v
        pre = q(bkd, """SELECT SUM(l.debit - l.credit) FROM gl_lines l JOIN gl_entries e
                        USING (je_id) JOIN accounts a USING (account_number)
                        WHERE e.txn_date <= ? AND a.statement != 'BS'""", cut)[0][0]
        full_bs["3900"] += pre
        post_pl = dict(q(bkd, """SELECT l.account_number, SUM(l.debit - l.credit)
                                 FROM gl_lines l JOIN gl_entries e USING (je_id)
                                 JOIN accounts a USING (account_number)
                                 WHERE e.txn_date > ? AND e.txn_date <= ? AND a.statement != 'BS'
                                 GROUP BY 1""", cut, d))
        for a in set(replay) | set(full_bs) | set(post_pl):
            target = full_bs.get(a, 0.0) + post_pl.get(a, 0.0)
            diff = abs(replay.get(a, 0.0) - target)
            if diff > worst:
                worst, worst_acct = diff, f"{a} at {d}"
    check("Replayed QuickBooks load = full-history ledger (every account, 3 dates)",
          worst < 0.01, f"max diff {worst:,.2f}" + (f" ({worst_acct})" if worst >= 0.01 else ""))
    clr = round(sum(v for a, v in oje if a == "1999") - ar_open + ap_open, 2)
    check("Conversion clearing account nets to zero after loading open AR/AP", abs(clr) < 0.01,
          f"{clr:,.2f}")

    lines += ["", "## SaaS metrics (from billing events)", "",
              "| Month | ARR | Customers | SMB / MM / Ent | Net new ARR | NRR (TTM) | GRR (TTM) |",
              "|---|---:|---:|---|---:|---:|---:|"]
    keys = sorted(snap)
    for i, d in enumerate(keys):
        if d < date(2024, 10, 1):
            continue
        cur = snap[d]
        arr = sum(cur.values()) * 12
        prev = snap[keys[i - 1]]
        nn = (sum(cur.values()) - sum(prev.values())) * 12
        yago = snap.get(keys[i - 12]) if i >= 12 else None
        nrr = grr = None
        if yago:
            base = sum(yago.values())
            kept = sum(cur.get(c, 0) for c in yago)
            nrr = kept / base
            grr = sum(min(cur.get(c, 0), v) for c, v in yago.items()) / base
        counts = defaultdict(int)
        for c in cur:
            counts[seg[c]] += 1
        lines.append(f"| {d:%b %Y} | ${arr / 1e6:,.2f}M | {len(cur)} | "
                     f"{counts['SMB']} / {counts['Mid-Market']} / {counts['Enterprise']} | "
                     f"${nn / 1e3:,.0f}k | {nrr:.0%} | {grr:.0%} |" if nrr else
                     f"| {d:%b %Y} | ${arr / 1e6:,.2f}M | {len(cur)} | "
                     f"{counts['SMB']} / {counts['Mid-Market']} / {counts['Enterprise']} | "
                     f"${nn / 1e3:,.0f}k | | |")

    arr_end = sum(snap[keys[-1]].values()) * 12
    arr_yago = sum(snap[keys[-13]].values()) * 12
    check("ARR at Oct 2026 in the $8-12M range", 8e6 <= arr_end <= 12e6, f"${arr_end / 1e6:.2f}M")
    growth = arr_end / arr_yago - 1
    check("YoY ARR growth between 50% and 110%", 0.5 <= growth <= 1.1, f"{growth:.0%}")

    # ---------------------------------------------------------------- P&L by quarter (correct)
    pl = pl_by_month(exp, date(2024, 11, 1), as_of)
    lines += ["", "## P&L by month (correct books, $000s)", "",
              "| Month | Revenue | Gross margin | Opex | Net income | Op. cash burn |",
              "|---|---:|---:|---:|---:|---:|"]
    gm_list, burns = [], []
    for d in mes[1:]:
        ym = f"{d:%Y-%m}"
        p = pl[ym]
        revn = -p["_Income"]
        cogs = p["_Cost of Goods Sold"]
        opex = p["_Expense"]
        ni = -(p["_Income"] + p["_Cost of Goods Sold"] + p["_Expense"] + p["_Other Income"])
        prev = d.replace(day=1) - timedelta(days=1)
        cash = sum(gl_balance(exp, a, d) for a in ("1000", "1010"))
        cash_prev = sum(gl_balance(exp, a, prev) for a in ("1000", "1010"))
        fund = q(exp, """SELECT COALESCE(SUM(l.credit),0) FROM gl_lines l JOIN gl_entries e
                         USING (je_id) WHERE l.account_number LIKE '30%' AND
                         e.txn_date BETWEEN ? AND ?""", d.replace(day=1).isoformat(),
                 d.isoformat())[0][0]
        burn = cash_prev - (cash - fund)
        gm = (revn - cogs) / revn
        gm_list.append(gm)
        burns.append(burn)
        lines.append(f"| {d:%b %Y} | {revn / 1e3:,.0f} | {gm:.0%} | {opex / 1e3:,.0f} | "
                     f"{ni / 1e3:,.0f} | {burn / 1e3:,.0f} |")
    check("Gross margin between 70% and 85% every month", all(0.7 <= g <= 0.85 for g in gm_list),
          f"range {min(gm_list):.0%} to {max(gm_list):.0%}")
    min_cash = min(sum(gl_balance(exp, a, d) for a in ("1000", "1010")) for d in mes)
    check("Cash never below $1M", min_cash > 1e6, f"low point ${min_cash / 1e6:.1f}M")

    report = ["# Validation report", "",
              f"Overall: **{'all checks passed' if ok else 'some checks failed'}**", ""] + lines
    (ROOT / "validation" / "report.md").write_text("\n".join(report) + "\n")
    print("\n".join(report))
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
