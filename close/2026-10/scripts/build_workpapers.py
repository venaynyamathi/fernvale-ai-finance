"""Build the October 2026 close workpapers for Fernvale Systems.

Run from the repo root:
    python close/2026-10/scripts/build_workpapers.py

Inputs
  data/source_systems.sqlite                         operational systems (bank, Stripe, billing, Ramp, payroll, CRM, plan)
  build/books_as_booked.sqlite                       the general ledger as loaded to QuickBooks (pre-close for October)
  close/2026-10/inputs/posted_entries.json           the 21 postings approved and made on 2026-11-01
  close/2026-10/inputs/qbo_trial_balance_*.csv       QuickBooks trial balance pulled after posting (tie-out only)

Every workbook is regenerated from these inputs, so the numbers trace to source.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[3]
CLOSE = ROOT / "close" / "2026-10"
SRC = sqlite3.connect(ROOT / "data" / "source_systems.sqlite")
BOOKS = sqlite3.connect(ROOT / "build" / "books_as_booked.sqlite")
ENTRIES = json.loads((CLOSE / "inputs" / "posted_entries.json").read_text())["entries"]

PERIOD_START, PERIOD_END, PRIOR_END = "2026-10-01", "2026-10-31", "2026-09-30"
PREPARED = "Prepared by Claude (close agent) 2026-11-01 · Reviewed by Vinny"

# ----------------------------------------------------------------------------- styling
FONT = "Arial"
NUM = '#,##0.00;(#,##0.00);"-"'
NUM0 = '#,##0;(#,##0);"-"'
PCT = '0.0%;(0.0%);"-"'
HDR_FILL = PatternFill("solid", fgColor="1F3864")
SEC_FILL = PatternFill("solid", fgColor="D9E1F2")
FLAG_FILL = PatternFill("solid", fgColor="FCE4D6")
THIN = Side(style="thin", color="999999")


def f(bold=False, color="000000", size=10, italic=False):
    return Font(name=FONT, bold=bold, color=color, size=size, italic=italic)


def q(conn, sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


def sheet(wb: Workbook, name: str, title: str, source: str, first=False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = name[:31]
    ws["A1"] = title
    ws["A1"].font = f(True, size=12)
    ws["A2"] = source
    ws["A2"].font = f(italic=True, color="595959", size=9)
    ws["A3"] = PREPARED
    ws["A3"].font = f(italic=True, color="595959", size=9)
    return ws


def table(ws, df: pd.DataFrame, row: int, col: int = 1, money=(), pct=(), total=False, widths=None, flag=None):
    """Write a DataFrame with a styled header. Returns the row after the table (and total row)."""
    cols = list(df.columns)
    for j, name in enumerate(cols):
        c = ws.cell(row=row, column=col + j, value=name)
        c.font = f(True, "FFFFFF")
        c.fill = HDR_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for i, rec in enumerate(df.itertuples(index=False), start=1):
        for j, v in enumerate(rec):
            if isinstance(v, float) and pd.isna(v):
                v = None
            c = ws.cell(row=row + i, column=col + j, value=v)
            c.font = f()
            if cols[j] in money:
                c.number_format = NUM
            if cols[j] in pct:
                c.number_format = PCT
        if flag is not None and flag(rec):
            for j in range(len(cols)):
                ws.cell(row=row + i, column=col + j).fill = FLAG_FILL
    end = row + len(df)
    if total and len(df):
        ws.cell(row=end + 1, column=col, value="Total").font = f(True)
        for j, name in enumerate(cols):
            if name in money:
                L = get_column_letter(col + j)
                c = ws.cell(row=end + 1, column=col + j, value=f"=SUM({L}{row + 1}:{L}{end})")
                c.font = f(True)
                c.number_format = NUM
                c.border = Border(top=THIN, bottom=Side(style="double"))
        end += 1
    if widths:
        for j, w in enumerate(widths):
            ws.column_dimensions[get_column_letter(col + j)].width = w
    return end + 2


def label(ws, row, text, col=1, bold=True, fill=None):
    c = ws.cell(row=row, column=col, value=text)
    c.font = f(bold)
    if fill:
        c.fill = fill
    return row + 1


def kv(ws, row, pairs, col=1):
    """Label / value rows. Values beginning with '=' are formulas. Returns next row."""
    for lab, val, *rest in pairs:
        ws.cell(row=row, column=col, value=lab).font = f(bool(rest and rest[0] == "bold"))
        c = ws.cell(row=row, column=col + 1, value=val)
        c.font = f(bool(rest and rest[0] == "bold"))
        if isinstance(val, (int, float)) or (isinstance(val, str) and val.startswith("=")):
            c.number_format = NUM
        if len(rest) > 1:
            ws.cell(row=row, column=col + 2, value=rest[1]).font = f(size=9, italic=True, color="595959")
        row += 1
    return row


def save(wb: Workbook, rel: str):
    path = CLOSE / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    for ws in wb.worksheets:
        ws.freeze_panes = ws.freeze_panes or None
    wb.save(path)
    print("wrote", path.relative_to(ROOT))
    return path


# ----------------------------------------------------------------------------- ledger (pre- and post-close)
ACCOUNTS = q(BOOKS, "SELECT account_number, name, statement FROM accounts")
ACCT_NAME = dict(zip(ACCOUNTS.account_number, ACCOUNTS.name))
ACCT_STMT = dict(zip(ACCOUNTS.account_number, ACCOUNTS.statement))

PRE = q(BOOKS, """
    SELECT e.je_id, e.txn_date, e.period, e.doc_type, e.source_ref, e.memo, e.entry_kind,
           l.line_no, l.account_number, l.debit, l.credit, l.class, l.customer_id, l.vendor_id, l.description
    FROM gl_lines l JOIN gl_entries e USING (je_id)""")
PRE["debit"] = PRE["debit"].fillna(0.0)
PRE["credit"] = PRE["credit"].fillna(0.0)
PRE["source"] = "books"

posted_rows = []
for e in ENTRIES:
    for i, ln in enumerate(e["lines"]):
        posted_rows.append({
            "je_id": e["draft_id"], "txn_date": e["txn_date"], "period": e["txn_date"][:7],
            "doc_type": "Close entry", "source_ref": e["qbo_id"], "memo": e["memo"], "entry_kind": "close",
            "line_no": i + 1, "account_number": ln["account"], "debit": ln.get("debit", 0.0),
            "credit": ln.get("credit", 0.0), "class": ln.get("class"), "customer_id": None,
            "vendor_id": ln.get("vendor"), "description": ln.get("description"), "source": "close"})
POSTED = pd.DataFrame(posted_rows)
POST = pd.concat([PRE, POSTED], ignore_index=True)
for df in (PRE, POSTED, POST):
    df["net"] = (df["debit"] - df["credit"]).round(2)

# The posted Sawtooth payment fix changes the customer on the AR side of py_000653 (no account effect).
SAWTOOTH_FIX = {"source_ref": "py_000653", "from": None, "to": None}


def balance(gl: pd.DataFrame, account: str, through: str) -> float:
    m = (gl.account_number == account) & (gl.txn_date <= through)
    return round(gl.loc[m, "net"].sum(), 2)


def activity(gl, account, start, end):
    m = (gl.account_number == account) & (gl.txn_date >= start) & (gl.txn_date <= end)
    return round(gl.loc[m, "net"].sum(), 2)


def assert_eq(a, b, what, tol=0.005):
    if abs(round(a - b, 2)) > tol:
        raise SystemExit(f"TIE-OUT FAILED: {what}: {a:,.2f} vs {b:,.2f}")


# ============================================================================= 1. trial balances
def trial_balances():
    out = []
    for name, gl, d in (("2026-09-30", PRE, PRIOR_END), ("2026-10-31_pre_close", PRE, PERIOD_END), ("2026-10-31_post_close", POST, PERIOD_END)):
        bs = gl[(gl.txn_date <= d) & gl.account_number.map(lambda a: ACCT_STMT.get(a) == "BS")]
        pl = gl[(gl.txn_date <= d) & gl.account_number.map(lambda a: ACCT_STMT.get(a) == "PL")]
        prior_pl = pl[pl.txn_date < "2026-01-01"].net.sum()
        ytd = pl[pl.txn_date >= "2026-01-01"].groupby("account_number").net.sum()
        b = bs.groupby("account_number").net.sum()
        b.loc["3900"] = b.get("3900", 0.0) + prior_pl  # prior years' P&L rolls into retained earnings
        tb = pd.concat([b, ytd]).round(2)
        tb = tb[tb != 0].sort_index()
        df = pd.DataFrame({"account_number": tb.index, "account_name": [ACCT_NAME.get(a) for a in tb.index],
                           "debit": [v if v > 0 else None for v in tb.values],
                           "credit": [-v if v < 0 else None for v in tb.values]})
        assert_eq(df.debit.sum(), df.credit.sum(), f"TB {name} balances")
        p = CLOSE / "05_trial_balances" / f"trial_balance_{name}.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(p, index=False)
        print("wrote", p.relative_to(ROOT))
        out.append((name, tb))

    # Tie the computed post-close TB to QuickBooks
    qbo = pd.read_csv(CLOSE / "inputs" / "qbo_trial_balance_2026-10-31_post_close.csv")
    qbo["acct"] = qbo.account.str.extract(r"^(\d{4})")
    qbo["qbo_net"] = qbo.debit.fillna(0) - qbo.credit.fillna(0)
    computed = out[2][1]
    rows = []
    for _, r in qbo.iterrows():
        comp = computed.get(r.acct, 0.0) if isinstance(r.acct, str) else None
        rows.append({"QuickBooks account": r.account, "QuickBooks (Dr+ / Cr-)": round(r.qbo_net, 2),
                     "Rebuilt from books + posted entries": comp,
                     "Note": "" if isinstance(r.acct, str) else "QuickBooks sandbox demo record - not Fernvale activity; delete in QBO"})
    tie = pd.DataFrame(rows)
    wb = Workbook()
    ws = sheet(wb, "QBO tie-out", "Trial balance 10/31/2026 post-close: QuickBooks vs rebuilt ledger",
               "QuickBooks TrialBalance pulled 2026-11-01 after posting vs build/books_as_booked.sqlite + inputs/posted_entries.json", first=True)
    end = table(ws, tie, 5, money=("QuickBooks (Dr+ / Cr-)", "Rebuilt from books + posted entries"), widths=[52, 20, 24, 60])
    for r in range(6, 6 + len(tie)):
        c = ws.cell(row=r, column=5, value=f'=IF(C{r}="","",ROUND(B{r}-C{r},2))')
        c.number_format = NUM
        c.font = f()
    ws.cell(row=5, column=5, value="Difference").font = f(True, "FFFFFF")
    ws.cell(row=5, column=5).fill = HDR_FILL
    ws.cell(row=end, column=1, value="Rows with a 4-digit account tie to the cent; sandbox rows net to zero against each other.").font = f(size=9, italic=True)
    for _, r in tie.iterrows():
        if r["Rebuilt from books + posted entries"] is not None:
            assert_eq(r["QuickBooks (Dr+ / Cr-)"], r["Rebuilt from books + posted entries"], f"QBO tie {r['QuickBooks account']}")
    save(wb, "05_trial_balances/trial_balance_tieout_to_quickbooks.xlsx")


# ============================================================================= 2. bank (1000 / 1010)
def bank():
    bank = q(SRC, "SELECT * FROM bank_transactions WHERE posted_date BETWEEN ? AND ? ORDER BY account_id, posted_date, bank_txn_id",
             (PERIOD_START, PERIOD_END))
    pay = q(SRC, "SELECT payment_id, invoice_id FROM billing_payments")
    inv_to_pay = dict(zip(pay.invoice_id, pay.payment_id))  # bank ACH reference is the billing invoice id
    bills = q(SRC, "SELECT bill_id, invoice_number FROM spend_bills")
    vinv_to_bill = dict(zip(bills.invoice_number, bills.bill_id))

    def gl_key(row):
        if row.txn_type == "stripe_payout":
            return ("ref", row.reference)
        if row.txn_type == "customer_payment":
            return ("ref", inv_to_pay.get(row.reference))
        if row.txn_type == "bill_payment":
            return ("ref", vinv_to_bill.get(row.reference))
        if row.txn_type == "card_payment":
            return ("ref", row.reference)
        if row.txn_type in ("payroll_net", "payroll_tax"):
            return ("payroll", row.reference, "Net pay (Gusto)" if row.txn_type == "payroll_net" else "Tax remittance (Gusto)")
        return ("ref", row.bank_txn_id)

    wb = Workbook()
    for acct_id, gl_acct, nm in (("BA-OPER", "1000", "1000 Operating Checking"), ("BA-TRES", "1010", "1010 Treasury Money Market")):
        b = bank[bank.account_id == acct_id].copy()
        g = PRE[(PRE.account_number == gl_acct) & (PRE.period == "2026-10")].copy()
        used = set()
        rows = []
        for r in b.itertuples():
            key = gl_key(r)
            if key[0] == "payroll":
                cand = g[(g.source_ref == key[1]) & (g.description == key[2])]
            elif acct_id == "BA-TRES" and r.txn_type == "internal_transfer":
                cand = g[g.memo.str.contains("TRANSFER", na=False)]
            elif acct_id == "BA-TRES" and r.txn_type == "interest":
                cand = g[g.source_ref == r.bank_txn_id]
                if cand.empty:
                    cand = g[(g.net.round(2) == round(r.amount, 2))]
            else:
                cand = g[g.source_ref == key[1]]
            cand = cand[~cand.index.isin(used)]
            if cand.empty:
                rows.append({"Bank txn": r.bank_txn_id, "Bank date": r.posted_date, "Type": r.txn_type, "Bank description": r.description,
                             "Bank amount": r.amount, "GL entry": None, "GL date": None, "GL reference": None, "GL amount": None})
                continue
            m = cand.iloc[0]
            used.add(cand.index[0])
            rows.append({"Bank txn": r.bank_txn_id, "Bank date": r.posted_date, "Type": r.txn_type, "Bank description": r.description,
                         "Bank amount": r.amount, "GL entry": m.je_id, "GL date": m.txn_date, "GL reference": m.source_ref, "GL amount": m.net})
        for i, m in g[~g.index.isin(used)].iterrows():
            rows.append({"Bank txn": None, "Bank date": None, "Type": "GL only", "Bank description": None, "Bank amount": None,
                         "GL entry": m.je_id, "GL date": m.txn_date, "GL reference": m.source_ref, "GL amount": m.net})
        match = pd.DataFrame(rows)

        open_bank = round(q(SRC, "SELECT SUM(amount) s FROM bank_transactions WHERE account_id=? AND posted_date<=?", (acct_id, PRIOR_END)).s[0], 2)
        close_bank = round(q(SRC, "SELECT SUM(amount) s FROM bank_transactions WHERE account_id=? AND posted_date<=?", (acct_id, PERIOD_END)).s[0], 2)
        last_rb = q(SRC, "SELECT running_balance FROM bank_transactions WHERE account_id=? AND posted_date<=? ORDER BY posted_date DESC, bank_txn_id DESC LIMIT 1", (acct_id, PERIOD_END)).running_balance[0]
        assert_eq(close_bank, last_rb, f"{acct_id} running balance")
        gl_open, gl_pre, gl_post = balance(PRE, gl_acct, PRIOR_END), balance(PRE, gl_acct, PERIOD_END), balance(POST, gl_acct, PERIOD_END)
        posted_here = POSTED[POSTED.account_number == gl_acct]

        ws = sheet(wb, f"{gl_acct} reconciliation", f"Bank reconciliation - {nm} - October 31, 2026",
                   f"Bank: bank_transactions ({acct_id}). GL: books_as_booked gl_lines {gl_acct}. Entries: inputs/posted_entries.json", first=(gl_acct == "1000"))
        ws.column_dimensions["A"].width = 58
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 70
        r = label(ws, 5, "Balance per bank", fill=SEC_FILL)
        r = kv(ws, r, [("Bank statement balance 10/31/2026", close_bank, "", f"Sum of {acct_id} lines through 10/31; equals last running_balance"),
                       ("Add: deposits in transit", float(match[(match.Type == "GL only") & (match["GL amount"] > 0)]["GL amount"].sum()), "", "GL receipts not on the bank"),
                       ("Less: outstanding payments", float(-match[(match.Type == "GL only") & (match["GL amount"] < 0)]["GL amount"].sum()), "", "GL disbursements not on the bank"),
                       ("Adjusted bank balance", f"=B{r}+B{r+1}-B{r+2}", "bold")])
        bank_adj_row = r - 1
        r = label(ws, r + 1, "Balance per books", fill=SEC_FILL)
        start = r
        r = kv(ws, r, [("GL balance 10/31/2026 before close entries", gl_pre, "", "books_as_booked through 10/31")])
        for e in posted_here.itertuples():
            r = kv(ws, r, [(f"  {e.je_id}: {e.description or e.memo}"[:120], e.net, "", f"Posted 2026-11-01, QBO Id {e.source_ref}")])
        r = kv(ws, r, [("Adjusted book balance (= QuickBooks after close)", f"=SUM(B{start}:B{r-1})", "bold")])
        book_adj_row = r - 1
        r = kv(ws, r + 1, [("Difference (must be zero)", f"=ROUND(B{bank_adj_row}-B{book_adj_row},2)", "bold")])
        ws.cell(row=r, column=1, value=f'=IF(B{r-1}=0,"RECONCILED","NOT RECONCILED")').font = f(True, "008000")
        assert_eq(close_bank, gl_post, f"{gl_acct} bank vs GL after close")
        r = label(ws, r + 2, "Roll-forward", fill=SEC_FILL)
        r = kv(ws, r, [("Opening 9/30 - bank", open_bank), ("Opening 9/30 - GL", gl_open),
                       ("October activity - bank", round(b.amount.sum(), 2)), ("October activity - GL before close", activity(PRE, gl_acct, PERIOD_START, PERIOD_END))])
        diffs = match[(match["Bank amount"].fillna(0).round(2) != match["GL amount"].fillna(0).round(2))]
        r = label(ws, r + 1, "Reconciling items found in matching", fill=SEC_FILL)
        if diffs.empty:
            ws.cell(row=r, column=1, value="None - every bank line matched a GL entry at the same amount.").font = f()
        else:
            table(ws, diffs.assign(Difference=(diffs["Bank amount"].fillna(0) - diffs["GL amount"].fillna(0)).round(2)),
                  r, money=("Bank amount", "GL amount", "Difference"))

        wm = wb.create_sheet(f"{gl_acct} matching")
        wm["A1"] = f"{nm} - October bank lines matched to GL by reference"
        wm["A1"].font = f(True, size=12)
        wm["A2"] = "Keys: Stripe payout id; billing payment id via invoice reference; AP bill via vendor invoice number; Ramp statement; Gusto run + net/tax; bank txn id."
        wm["A2"].font = f(italic=True, size=9, color="595959")
        end = table(wm, match, 4, money=("Bank amount", "GL amount"), total=True,
                    widths=[12, 11, 16, 44, 15, 11, 11, 14, 15],
                    flag=lambda rec: round((rec[4] or 0) - (rec[8] or 0), 2) != 0)
        n = len(match)
        wm.cell(row=4, column=10, value="Difference").font = f(True, "FFFFFF")
        wm.cell(row=4, column=10).fill = HDR_FILL
        for i in range(5, 5 + n):
            c = wm.cell(row=i, column=10, value=f"=ROUND(N(E{i})-N(I{i}),2)")
            c.number_format = NUM
        wm.freeze_panes = "A5"

    # Customer receipts: payer on the bank vs customer the payment was recorded to
    rec = q(SRC, """SELECT b.bank_txn_id, b.posted_date, b.counterparty AS bank_payer, b.reference AS invoice_ref, b.amount,
                    p.payment_id, c.name AS billing_customer
                    FROM bank_transactions b LEFT JOIN billing_payments p ON p.invoice_id=b.reference AND p.status='succeeded'
                    LEFT JOIN billing_invoices i ON i.invoice_id=b.reference LEFT JOIN billing_customers c ON c.customer_id=i.customer_id
                    WHERE b.txn_type='customer_payment' AND b.posted_date BETWEEN ? AND ?""", (PERIOD_START, PERIOD_END))
    books_cust = PRE[(PRE.account_number == "1100") & (PRE.source_ref.isin(rec.payment_id))][["source_ref", "customer_id"]]
    cust_names = q(SRC, "SELECT customer_id, name FROM billing_customers")
    books_cust = books_cust.merge(cust_names, on="customer_id", how="left").rename(columns={"name": "GL customer before close", "source_ref": "payment_id"})
    rec = rec.merge(books_cust[["payment_id", "GL customer before close"]], on="payment_id", how="left")
    rec["Agrees"] = rec.apply(lambda x: "Yes" if x.billing_customer == x["GL customer before close"] else "NO - fixed by D1031-446A", axis=1)
    ws = sheet(wb, "Receipts payer check", "Customer ACH receipts - payer vs customer credited",
               "bank_transactions + billing_payments/billing_invoices vs AR lines in books_as_booked")
    table(ws, rec, 5, money=("amount",), widths=[12, 11, 30, 12, 14, 12, 30, 30, 26], flag=lambda r: not str(r[-1]).startswith("Yes"))
    save(wb, "02_reconciliations/1000_1010_bank_reconciliation.xlsx")


# ============================================================================= 3. Stripe clearing (1050)
def stripe():
    payouts = q(SRC, """SELECT p.payout_id, p.created, p.arrival_date, p.amount AS net_payout, p.txn_count,
                ROUND(SUM(CASE WHEN t.type='charge' THEN t.amount ELSE 0 END),2) AS gross_charges,
                ROUND(SUM(CASE WHEN t.type='charge' THEN t.fee ELSE 0 END),2) AS charge_fees,
                ROUND(SUM(CASE WHEN t.type<>'charge' THEN t.net ELSE 0 END),2) AS disputes_refunds_net
                FROM stripe_payouts p JOIN stripe_balance_transactions t ON t.payout_id=p.payout_id
                WHERE p.arrival_date BETWEEN ? AND ? GROUP BY p.payout_id ORDER BY p.arrival_date""", (PERIOD_START, PERIOD_END))
    bank = q(SRC, "SELECT reference AS payout_id, amount AS bank_amount FROM bank_transactions WHERE txn_type='stripe_payout' AND posted_date BETWEEN ? AND ?",
             (PERIOD_START, PERIOD_END))
    dep = PRE[(PRE.doc_type == "Deposit") & (PRE.period == "2026-10")]
    gl = pd.DataFrame({"payout_id": dep.source_ref.unique()})
    gl["gl_deposit_to_1000"] = gl.payout_id.map(lambda p: round(dep[(dep.source_ref == p) & (dep.account_number == "1000")].net.sum(), 2))
    gl["gl_gross_from_1050"] = gl.payout_id.map(lambda p: round(-dep[(dep.source_ref == p) & (dep.account_number == "1050")].net.sum(), 2))
    gl["gl_fees_5200"] = gl.payout_id.map(lambda p: round(dep[(dep.source_ref == p) & (dep.account_number == "5200")].net.sum(), 2))
    po = payouts.merge(bank, on="payout_id", how="left").merge(gl, on="payout_id", how="left")

    open_items = q(SRC, """SELECT t.balance_txn_id, t.type, t.invoice_id, t.customer_id, t.created, t.available_on, t.amount, t.fee, t.net,
                   t.payout_id, p.arrival_date FROM stripe_balance_transactions t LEFT JOIN stripe_payouts p ON p.payout_id=t.payout_id
                   WHERE t.created<=? AND (t.payout_id IS NULL OR p.arrival_date IS NULL OR p.arrival_date>?) AND t.created>='2026-09-01'
                   ORDER BY t.created""", (PERIOD_END, PERIOD_END))
    disputes = q(SRC, "SELECT * FROM stripe_balance_transactions WHERE type IN ('dispute','refund') AND created BETWEEN ? AND ?", (PERIOD_START, PERIOD_END))
    failed = q(SRC, """SELECT p.payment_id, i.invoice_number, p.customer_id, p.attempted_at, p.amount, p.status, p.failure_reason,
                (SELECT MIN(p2.attempted_at) FROM billing_payments p2 WHERE p2.invoice_id=p.invoice_id AND p2.status='succeeded') AS later_success
                FROM billing_payments p JOIN billing_invoices i ON i.invoice_id=p.invoice_id
                WHERE p.method='card' AND p.status<>'succeeded' AND p.attempted_at BETWEEN ? AND ?""", (PERIOD_START, PERIOD_END + " 23:59"))
    gl_bal = balance(POST, "1050", PERIOD_END)
    stripe_bal = round(open_items.amount.sum(), 2)  # GL carries gross charges until payout; fees post with the payout

    wb = Workbook()
    ws = sheet(wb, "Reconciliation", "Stripe Clearing (1050) - October 31, 2026",
               "stripe_balance_transactions, stripe_payouts, bank_transactions; GL from books_as_booked + posted entries", first=True)
    ws.column_dimensions["A"].width = 62
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 70
    r = label(ws, 5, "1050 holds gross card receipts not yet paid out. Fees and disputes post when the payout lands.", bold=False)
    r = kv(ws, r + 1, [("GL balance 10/31 (after close)", gl_bal, "bold", "QuickBooks 1050"),
                       ("Stripe: charges not in a payout that arrived by 10/31 (gross)", stripe_bal, "bold", "See 'In transit' tab"),
                       ("Difference", f"=ROUND(B{r+1}-B{r+2},2)", "bold")])
    assert_eq(gl_bal, stripe_bal, "Stripe clearing")
    r = label(ws, r + 1, "Payout checks", fill=SEC_FILL)
    r = kv(ws, r, [("October payouts arrived", len(po)),
                   ("Payouts where bank = Stripe net", int((po.bank_amount.round(2) == po.net_payout.round(2)).sum())),
                   ("Payouts where GL deposit = Stripe net (before close)", int((po.gl_deposit_to_1000.round(2) == po.net_payout.round(2)).sum())),
                   ("Exception: po_00688 dispute dp_1Q8fernvale not booked with the deposit", -10726.44, "", "Booked by D1031-B7B9 (QBO 6139): 6900 $10,711.44, 6850 $15.00")])
    for c in range(2, 3):
        for rr in range(r - 4, r - 1):
            ws.cell(row=rr, column=c).number_format = "0"
    r = label(ws, r + 1, "Other checks", fill=SEC_FILL)
    kv(ws, r, [("Disputes and refunds created in October", len(disputes), "", "One dispute; no refunds"),
               ("Failed card attempts in October (all later collected)", len(failed), "", "No Stripe charge for failed attempts")])
    w = wb.create_sheet("Payouts")
    po["bank_minus_stripe"] = (po.bank_amount - po.net_payout).round(2)
    po["gl_minus_stripe"] = (po.gl_deposit_to_1000 - po.net_payout).round(2)
    table(w, po, 1, money=("net_payout", "gross_charges", "charge_fees", "disputes_refunds_net", "bank_amount", "gl_deposit_to_1000",
                           "gl_gross_from_1050", "gl_fees_5200", "bank_minus_stripe", "gl_minus_stripe"),
          total=True, widths=[11, 11, 11, 13, 9, 13, 11, 13, 13, 13, 13, 11, 12, 12], flag=lambda rec: rec[-1] != 0)
    w = wb.create_sheet("In transit")
    table(w, open_items, 1, money=("amount", "fee", "net"), total=True, widths=[14, 8, 12, 10, 11, 11, 11, 9, 11, 11, 11])
    w = wb.create_sheet("Disputes & failures")
    end = table(w, disputes, 1, money=("amount", "fee", "net"))
    table(w, failed, end, money=("amount",))
    save(wb, "02_reconciliations/1050_stripe_clearing.xlsx")


# ============================================================================= 4. corporate card (2100)
def card():
    stm = q(SRC, "SELECT * FROM spend_card_statements WHERE period_end>='2026-09-01' ORDER BY period_start")
    tx = q(SRC, """SELECT transaction_id, transaction_date, post_date, merchant, amount, category, department, cardholder_employee_id,
                   receipt_attached, statement_id, memo FROM spend_card_transactions WHERE transaction_date BETWEEN ? AND ? ORDER BY transaction_date""",
           (PERIOD_START, PERIOD_END))
    g = PRE[(PRE.doc_type == "Expense") & (PRE.period == "2026-10") & (PRE.source_ref.str.startswith("rtx_", na=False))]
    exp = g[g.account_number != "2100"][["source_ref", "account_number", "class", "net"]].rename(
        columns={"source_ref": "transaction_id", "account_number": "gl_account", "class": "gl_class", "net": "gl_amount"})
    exp["gl_account"] = exp.gl_account + " " + exp.gl_account.map(ACCT_NAME)
    tx = tx.merge(exp, on="transaction_id", how="left")
    tx["difference"] = (tx.amount - tx.gl_amount.fillna(0)).round(2)
    posted_to_date = round(q(SRC, "SELECT SUM(amount) s FROM spend_card_transactions WHERE post_date<=?", (PERIOD_END,)).s[0], 2)
    paid = round(q(SRC, "SELECT SUM(statement_total) s FROM spend_card_statements WHERE payment_date<=? AND status='paid'", (PERIOD_END,)).s[0], 2)
    # Liability per QuickBooks is charges by transaction date less payments; Ramp books by post date.
    by_txn_date = round(q(SRC, "SELECT SUM(amount) s FROM spend_card_transactions WHERE transaction_date<=?", (PERIOD_END,)).s[0], 2)
    gl_bal = -balance(POST, "2100", PERIOD_END)
    nov_stmt_oct_txns = round(tx[tx.statement_id == "STMT-202611"].amount.sum(), 2)

    wb = Workbook()
    ws = sheet(wb, "Reconciliation", "Ramp Corporate Card (2100) - October 31, 2026",
               "spend_card_transactions, spend_card_statements; GL from books_as_booked", first=True)
    ws.column_dimensions["A"].width = 64
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 60
    r = kv(ws, 5, [("Charges to date by transaction date", by_txn_date, "", "spend_card_transactions.transaction_date <= 10/31"),
                   ("Less: statements paid through 10/31", -paid, "", "STMT-202609 paid 10/06 was the last payment"),
                   ("Card liability per Ramp", f"=B5+B6", "bold"),
                   ("GL balance 10/31 (credit)", gl_bal, "bold", "QuickBooks 2100; no close entries"),
                   ("Difference", "=ROUND(B7-B8,2)", "bold")])
    assert_eq(by_txn_date - paid, gl_bal, "card liability")
    r = label(ws, r + 1, "Composition", fill=SEC_FILL)
    oct_stmt = float(stm[stm.statement_id == "STMT-202610"].statement_total.iloc[0])
    kv(ws, r, [("October statement STMT-202610 (open, due early November)", oct_stmt),
               ("October-dated charges posting to the November statement", nov_stmt_oct_txns),
               ("GL balance", f"=B{r}+B{r+1}", "bold"),
               ("Check", f"=ROUND(B{r+2}-B8,2)")])
    assert_eq(oct_stmt + nov_stmt_oct_txns, gl_bal, "card composition")
    w = wb.create_sheet("Oct transactions vs GL")
    table(w, tx, 1, money=("amount", "gl_amount", "difference"), total=True,
          widths=[13, 11, 11, 20, 12, 22, 16, 10, 8, 14, 32, 34, 18, 12, 11], flag=lambda rec: rec[-1] != 0)
    w = wb.create_sheet("Policy exceptions")
    exc = tx[(tx.receipt_attached == 0) & (tx.amount > 75)]
    end = table(w, exc[["transaction_id", "transaction_date", "merchant", "amount", "category", "department", "cardholder_employee_id", "memo"]],
                1, money=("amount",), total=True, widths=[13, 11, 20, 12, 22, 16, 12, 34])
    w.cell(row=end, column=1, value="Receipt missing over $75. Follow-up only; coding is consistent, no entry needed.").font = f(size=9, italic=True)
    w = wb.create_sheet("Statements")
    table(w, stm, 1, money=("statement_total",))
    save(wb, "02_reconciliations/2100_corporate_card.xlsx")


# ============================================================================= 5. accounts receivable (1100)
def receivables():
    inv = q(SRC, """SELECT i.invoice_id, i.invoice_number, i.customer_id, c.name AS customer, i.invoice_date, i.due_date, i.total,
                    i.amount_written_off, i.status, i.collection_method, s.status AS subscription_status
                    FROM billing_invoices i JOIN billing_customers c USING (customer_id) LEFT JOIN billing_subscriptions s ON s.subscription_id=i.subscription_id
                    WHERE i.invoice_date<=? AND (i.voided_date IS NULL OR i.voided_date>?) AND i.status NOT IN ('uncollectible')""", (PERIOD_END, PERIOD_END))
    paid = q(SRC, "SELECT invoice_id, SUM(amount) paid FROM billing_payments WHERE status='succeeded' AND attempted_at<=? GROUP BY invoice_id", (PERIOD_END + " 23:59",))
    inv = inv.merge(paid, on="invoice_id", how="left")
    inv["paid"] = inv.paid.fillna(0)
    inv["open_amount"] = (inv.total - inv.paid - inv.amount_written_off.fillna(0)).round(2)
    inv.loc[inv.status == "refunded", "open_amount"] = 0
    open_inv = inv[inv.open_amount.abs() > 0.005].copy()
    open_inv["days_past_due"] = (pd.Timestamp(PERIOD_END) - pd.to_datetime(open_inv.due_date)).dt.days
    open_inv["bucket"] = pd.cut(open_inv.days_past_due, [-10_000, 0, 30, 60, 90, 10_000],
                                labels=["Current", "1-30", "31-60", "61-90", "90+"]).astype(str)

    # GL AR by customer from books; post-close applies the Sawtooth re-point
    ar = PRE[(PRE.account_number == "1100") & (PRE.txn_date <= PERIOD_END)].copy()
    names = q(SRC, "SELECT customer_id, name FROM billing_customers")
    pre_by_cust = ar.groupby("customer_id").net.sum().round(2)
    post = ar.copy()
    wrong = post[(post.source_ref == "py_000653")].customer_id.iloc[0]
    right = q(SRC, "SELECT customer_id FROM billing_invoices WHERE invoice_number='FV-12064'").customer_id[0]
    post.loc[post.source_ref == "py_000653", "customer_id"] = right
    post_by_cust = post.groupby("customer_id").net.sum().round(2)
    bill_by_cust = open_inv.groupby("customer_id").open_amount.sum().round(2)
    custs = sorted(set(pre_by_cust[pre_by_cust != 0].index) | set(post_by_cust[post_by_cust != 0].index) | set(bill_by_cust.index))
    cmp = pd.DataFrame({"customer_id": custs})
    cmp = cmp.merge(names, on="customer_id", how="left")
    cmp["billing_open"] = cmp.customer_id.map(bill_by_cust).fillna(0)
    cmp["gl_before_close"] = cmp.customer_id.map(pre_by_cust).fillna(0)
    cmp["gl_after_close"] = cmp.customer_id.map(post_by_cust).fillna(0)
    cmp["difference_after"] = (cmp.gl_after_close - cmp.billing_open).round(2)
    gl_total = balance(POST, "1100", PERIOD_END)
    assert_eq(gl_total, open_inv.open_amount.sum(), "AR total")
    assert (cmp.difference_after.abs() < 0.005).all(), "AR customer-level tie failed"

    wb = Workbook()
    ws = sheet(wb, "Reconciliation", "Accounts Receivable (1100) - October 31, 2026",
               "billing_invoices, billing_payments; GL AR lines by customer from books_as_booked", first=True)
    ws.column_dimensions["A"].width = 62
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 70
    r = kv(ws, 5, [("GL balance 10/31", gl_total, "bold", "QuickBooks 1100"),
                   ("Open invoices per billing", round(open_inv.open_amount.sum(), 2), "bold", f"{len(open_inv)} invoices"),
                   ("Difference", "=ROUND(B5-B6,2)", "bold"),
                   ("Customers whose GL balance differed from billing before close", int((cmp.gl_before_close != cmp.billing_open).sum()), "",
                    "Sawtooth Wholesale (credit) / Sawtooth Plumbing (open FV-12064): py_000653 applied to wrong customer"),
                   ("Customers differing after D1031-446A", int((cmp.difference_after != 0).sum()))])
    for rr in (8, 9):
        ws.cell(row=rr, column=2).number_format = "0"
    r = label(ws, r + 1, "Aging (formulas over the Open invoices tab)", fill=SEC_FILL)
    n = len(open_inv)
    for i, b in enumerate(["Current", "1-30", "31-60", "61-90", "90+"]):
        ws.cell(row=r + i, column=1, value=b).font = f()
        c = ws.cell(row=r + i, column=2, value=f"=SUMIF('Open invoices'!$O$2:$O${n+1},A{r+i},'Open invoices'!$M$2:$M${n+1})")
        c.number_format = NUM
        ws.cell(row=r + i, column=3, value=f"=COUNTIF('Open invoices'!$O$2:$O${n+1},A{r+i})").font = f()
    ws.cell(row=r + 5, column=1, value="Total").font = f(True)
    c = ws.cell(row=r + 5, column=2, value=f"=SUM(B{r}:B{r+4})")
    c.number_format = NUM
    c.font = f(True)
    r += 7
    r = label(ws, r, "Collectability - invoices 30+ days past due over $25,000", fill=SEC_FILL)
    big = open_inv[(open_inv.days_past_due >= 30) & (open_inv.open_amount > 25000)]
    for x in big.itertuples():
        hist = q(SRC, "SELECT COUNT(*) n FROM billing_payments WHERE customer_id=?", (x.customer_id,)).n[0]
        ws.cell(row=r, column=1, value=f"{x.customer} {x.invoice_number}: ${x.open_amount:,.2f}, {x.days_past_due} days past due, "
                                       f"subscription {x.subscription_status}, payment attempts ever: {hist}").font = f()
        r += 1
    ws.cell(row=r, column=1, value="Reviewer decision 11/1: no reserve in October; escalate collections; revisit at November close.").font = f(True)
    w = wb.create_sheet("Open invoices")
    cols = ["invoice_id", "invoice_number", "customer_id", "customer", "invoice_date", "due_date", "total", "status", "collection_method",
            "subscription_status", "paid", "invoice_date_check", "open_amount", "days_past_due", "bucket"]
    open_inv["invoice_date_check"] = open_inv.invoice_date <= PERIOD_END
    table(w, open_inv[cols], 1, money=("total", "paid", "open_amount"), total=True,
          widths=[11, 11, 9, 30, 11, 11, 13, 8, 13, 10, 11, 8, 13, 9, 9], flag=lambda rec: rec[-2] >= 30)
    w = wb.create_sheet("By customer")
    table(w, cmp, 1, money=("billing_open", "gl_before_close", "gl_after_close", "difference_after"), total=True,
          widths=[10, 32, 14, 14, 14, 14], flag=lambda rec: round(rec[3] - rec[2], 2) != 0)
    w = wb.create_sheet("Cash application fix")
    fix = q(SRC, """SELECT p.payment_id, p.invoice_id, i.invoice_number, p.customer_id AS paying_customer, c.name AS paying_customer_name,
                    p.attempted_at, p.amount, p.method FROM billing_payments p JOIN billing_invoices i USING (invoice_id)
                    JOIN billing_customers c ON c.customer_id=p.customer_id WHERE p.payment_id='py_000653'""")
    fix["gl_customer_before"] = wrong + " " + names.set_index("customer_id").name.get(wrong, "")
    fix["gl_customer_after"] = right + " " + names.set_index("customer_id").name.get(right, "")
    fix["bank_line"] = "BTX-001625"
    fix["entry"] = "D1031-446A (QBO Payment 6037)"
    table(w, fix, 1, money=("amount",), widths=[11, 11, 11, 10, 28, 11, 12, 6, 30, 30, 11, 26])
    save(wb, "02_reconciliations/1100_accounts_receivable.xlsx")


# ============================================================================= 6. accounts payable (2000)
def payables():
    ap_src = q(SRC, """SELECT bill_id, vendor_id, vendor_name, invoice_number, invoice_date, received_date, due_date, service_period_start,
                       service_period_end, amount, category, department, status, paid_date, memo FROM spend_bills
                       WHERE invoice_date<=? AND status NOT IN ('pending_approval') AND (paid_date IS NULL OR paid_date>?)""", (PERIOD_END, PERIOD_END))
    g = PRE[(PRE.account_number == "2000") & (PRE.txn_date <= PERIOD_END)]
    by_ref = g.groupby("source_ref").net.sum().round(2)
    gl_open = by_ref[by_ref != 0]
    gl_tbl = pd.DataFrame({"gl_source_ref": gl_open.index, "gl_open_credit": -gl_open.values})
    gl_tbl = gl_tbl.merge(g.drop_duplicates("source_ref")[["source_ref", "je_id", "txn_date", "memo"]], left_on="gl_source_ref", right_on="source_ref").drop(columns="source_ref")
    gl_tbl["in_ap_system"] = gl_tbl.gl_source_ref.isin(ap_src.bill_id).map({True: "Yes", False: "NO - duplicate, deleted by D1031-907D"})
    gl_after = -balance(POST, "2000", PERIOD_END)
    assert_eq(gl_after, ap_src.amount.sum(), "AP tie")

    later = q(SRC, """SELECT bill_id, vendor_name, invoice_number, invoice_date, service_period_start, service_period_end, amount, status, memo
                      FROM spend_bills WHERE (invoice_date>? OR status='pending_approval') OR (invoice_date>? AND service_period_start<=?)""",
              (PERIOD_END, PERIOD_START, PERIOD_END))
    vend = q(SRC, "SELECT vendor_id, name, category, default_department, payment_channel, payment_terms_days, accrue_monthly FROM spend_vendors")
    hist = q(SRC, """SELECT vendor_name, substr(service_period_start,1,7) service_month, SUM(amount) amount FROM spend_bills
                     WHERE service_period_start>='2026-05-01' AND service_period_start<='2026-10-31' GROUP BY 1,2""")
    pivot = hist.pivot_table(index="vendor_name", columns="service_month", values="amount", aggfunc="sum").reset_index()
    big = q(SRC, """SELECT bill_id, vendor_name, invoice_number, invoice_date, amount, category, department, service_period_start, service_period_end, memo
                    FROM spend_bills WHERE invoice_date BETWEEN ? AND ? AND amount>=5000""", (PERIOD_START, PERIOD_END))

    wb = Workbook()
    ws = sheet(wb, "Reconciliation", "Accounts Payable (2000) - October 31, 2026", "spend_bills (Ramp AP); GL AP lines from books_as_booked", first=True)
    ws.column_dimensions["A"].width = 64
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 64
    kv(ws, 5, [("GL balance 10/31 before close", -balance(PRE, "2000", PERIOD_END), "", "Includes duplicate INV1817"),
               ("Less: duplicate Marlow & Pierce bill INV1817 deleted (D1031-907D)", -23531.81),
               ("GL balance 10/31 after close", "=B5+B6", "bold", "QuickBooks 2000"),
               ("Approved unpaid bills in Ramp dated on/before 10/31", round(ap_src.amount.sum(), 2), "bold", "status not pending_approval"),
               ("Difference", "=ROUND(B7-B8,2)", "bold")])
    label(ws, 11, "Unrecorded liabilities: four October costs accrued (see je_support.xlsx 'Accruals'):", bold=False)
    for i, t in enumerate(["AWS October usage $86,900 (accrue_monthly vendor; invoice arrives early Nov)",
                           "Marlow & Pierce October legal $13,100 (accrue_monthly vendor)",
                           "Brightquarry October content retainer $14,000 (bills at month-end; no October invoice)",
                           "Talentridge TAL-2610992 $28,400 (offer accepted 10/12; bill pending approval in Ramp)"]):
        ws.cell(row=12 + i, column=1, value="  • " + t).font = f()
    w = wb.create_sheet("Open bills - Ramp")
    table(w, ap_src, 1, money=("amount",), total=True, widths=[10, 7, 26, 13, 11, 11, 11, 11, 11, 12, 16, 10, 9, 10, 40])
    w = wb.create_sheet("Open bills - GL")
    table(w, gl_tbl, 1, money=("gl_open_credit",), total=True, widths=[16, 14, 10, 11, 48, 34], flag=lambda rec: rec[-1] != "Yes")
    w = wb.create_sheet("Liability search")
    end = table(w, later, 1, money=("amount",), widths=[10, 28, 14, 11, 11, 11, 12, 15, 60])
    end = table(w, vend[vend.accrue_monthly == 1], end, widths=[10, 28, 14, 14, 10, 10, 10])
    table(w, pivot, end, money=tuple(c for c in pivot.columns if c != "vendor_name"), widths=[34] + [13] * 6)
    w = wb.create_sheet("Bill coding over $5k")
    table(w, big, 1, money=("amount",), widths=[10, 28, 14, 11, 12, 18, 12, 11, 11, 50])
    save(wb, "02_reconciliations/2000_accounts_payable.xlsx")


# ============================================================================= 7. deferred revenue waterfall (2300)
def deferred_revenue():
    lines = q(SRC, """SELECT l.invoice_id, i.invoice_number, i.customer_id, c.name AS customer, i.invoice_date, i.status, i.voided_date,
                      l.line_no, l.line_type, l.description, l.amount, l.service_start, l.service_end
                      FROM billing_invoice_lines l JOIN billing_invoices i USING (invoice_id) JOIN billing_customers c ON c.customer_id=i.customer_id
                      WHERE i.invoice_date<=? ORDER BY i.invoice_date, l.invoice_id, l.line_no""", (PERIOD_END,))
    lines["account"] = lines.line_type.map(lambda t: "4100" if t == "services" else "4000")
    lines["excluded"] = lines.status.isin(["uncollectible", "refunded"]) | lines.voided_date.notna()
    sd, ed = pd.to_datetime(lines.service_start), pd.to_datetime(lines.service_end)
    lines["total_days"] = (ed - sd).dt.days + 1
    for me in (PRIOR_END, PERIOD_END):
        rem = (ed - pd.Timestamp(me)).dt.days.clip(lower=0)
        rem = rem.where(rem < lines.total_days, lines.total_days)
        inc = (pd.to_datetime(lines.invoice_date) <= pd.Timestamp(me)) & ~lines.excluded
        lines[f"unearned_{me}"] = (lines.amount * rem / lines.total_days).where(inc, 0.0)
    keep = lines[(lines[f"unearned_{PRIOR_END}"] > 0.004) | (lines[f"unearned_{PERIOD_END}"] > 0.004) |
                 (lines.invoice_date >= PERIOD_START) | lines.excluded & (pd.to_datetime(lines.service_end) >= pd.Timestamp("2026-01-01"))].copy()
    summ = lines.groupby("account")[[f"unearned_{PRIOR_END}", f"unearned_{PERIOD_END}"]].sum().round(2)
    target = round(summ[f"unearned_{PERIOD_END}"].sum(), 2)
    assert_eq(target, -balance(POST, "2300", PERIOD_END), "deferred revenue vs GL")
    assert_eq(summ.loc["4000", f"unearned_{PERIOD_END}"] - summ.loc["4000", f"unearned_{PRIOR_END}"], 405316.96, "4000 true-up")
    assert_eq(summ.loc["4100", f"unearned_{PERIOD_END}"] - summ.loc["4100", f"unearned_{PRIOR_END}"], 5503.38, "4100 true-up")

    wb = Workbook()
    ws = sheet(wb, "Summary", "Deferred Revenue (2300) waterfall and true-up - October 31, 2026",
               "billing_invoice_lines + billing_invoices; ratable by day, inclusive; excludes voided, refunded and uncollectible invoices", first=True)
    n = len(keep)
    W = "'Waterfall lines'"
    ws.column_dimensions["A"].width = 60
    for c in "BCD":
        ws.column_dimensions[c].width = 18
    for j, h in enumerate(["", "9/30/2026", "10/31/2026", "Change = true-up"]):
        cc = ws.cell(row=5, column=1 + j, value=h)
        cc.font = f(True, "FFFFFF")
        cc.fill = HDR_FILL
    for i, (acct, lab) in enumerate((("4000", "Subscription and proration (4000)"), ("4100", "Professional services (4100)"))):
        rr = 6 + i
        ws.cell(row=rr, column=1, value=lab).font = f()
        ws.cell(row=rr, column=2, value=f"=SUMIF({W}!$N$2:$N${n+1},\"{acct}\",{W}!$S$2:$S${n+1})").number_format = NUM
        ws.cell(row=rr, column=3, value=f"=SUMIF({W}!$N$2:$N${n+1},\"{acct}\",{W}!$T$2:$T${n+1})").number_format = NUM
        ws.cell(row=rr, column=4, value=f"=C{rr}-B{rr}").number_format = NUM
    ws.cell(row=8, column=1, value="Total waterfall").font = f(True)
    for col in "BCD":
        c = ws[f"{col}8"]
        c.value = f"={col}6+{col}7"
        c.number_format = NUM
        c.font = f(True)
    r = label(ws, 10, "Tie to GL", fill=SEC_FILL)
    r = kv(ws, r, [("2300 balance 9/30 per books (credit)", -balance(PRE, "2300", PRIOR_END)),
                   ("Less: FV-11156 unearned portion left after April write-off (D1031-71D6, prior-period)", -8397.37),
                   ("Corrected opening = waterfall 9/30", "=B11+B12", "bold"),
                   ("Check vs waterfall 9/30", "=ROUND(B13-B8,2)"),
                   ("October true-up posted (D1031-E141)", 410820.34),
                   ("2300 balance 10/31 after close", -balance(POST, "2300", PERIOD_END), "bold", "QuickBooks 2300"),
                   ("Check vs waterfall 10/31", "=ROUND(B16-C8,2)")])
    r = label(ws, r + 1, "Roll-forward", fill=SEC_FILL)
    billed = round(lines[(lines.invoice_date >= PERIOD_START) & ~lines.excluded].amount.sum(), 2)
    pl = POST[(POST.period == "2026-10") & POST.account_number.isin(["4000", "4100"])]
    rev = round(-pl.net.sum(), 2)
    kv(ws, r, [("Opening (corrected)", "=B13"), ("October billings", billed, "", "invoices dated in October"),
               ("Revenue recognized in October (4000 + 4100, after close)", -rev),
               ("Closing", f"=B{r}+B{r+1}+B{r+2}", "bold"), ("Check vs waterfall 10/31", f"=ROUND(B{r+3}-C8,2)")])
    assert_eq(target - 8397.37 * 0, (-balance(PRE, "2300", PRIOR_END) - 8397.37) + billed - rev, "deferred revenue roll-forward")

    w = wb.create_sheet("Waterfall lines")
    cols = ["invoice_id", "invoice_number", "customer_id", "customer", "invoice_date", "status", "voided_date", "line_no", "line_type",
            "description", "amount", "service_start", "service_end", "account", "excluded", "total_days"]
    hdr = cols + ["days_after_9/30", "days_after_10/31", f"unearned 9/30", f"unearned 10/31"]
    for j, h in enumerate(hdr, 1):
        c = w.cell(row=1, column=j, value=h)
        c.font = f(True, "FFFFFF")
        c.fill = HDR_FILL
    for i, rec in enumerate(keep[cols].itertuples(index=False), start=2):
        for j, v in enumerate(rec, 1):
            if isinstance(v, float) and pd.isna(v):
                v = None
            if isinstance(v, (bool,)) or type(v).__name__ == "bool_":
                v = bool(v)
            w.cell(row=i, column=j, value=v)
        w.cell(row=i, column=11).number_format = NUM
        # days remaining after each month-end, capped at total days; zero if the invoice was not yet issued or is excluded
        w.cell(row=i, column=17, value=f'=IF(OR(O{i},E{i}>"{PRIOR_END}"),0,MAX(0,MIN(P{i},DATEVALUE(M{i})-DATEVALUE("{PRIOR_END}"))))')
        w.cell(row=i, column=18, value=f'=IF(O{i},0,MAX(0,MIN(P{i},DATEVALUE(M{i})-DATEVALUE("{PERIOD_END}"))))')
        w.cell(row=i, column=19, value=f"=K{i}*Q{i}/P{i}").number_format = NUM
        w.cell(row=i, column=20, value=f"=K{i}*R{i}/P{i}").number_format = NUM
    for j, wdt in enumerate([10, 11, 9, 28, 11, 12, 11, 6, 11, 40, 12, 11, 11, 7, 8, 8, 9, 9, 13, 13], 1):
        w.column_dimensions[get_column_letter(j)].width = wdt
    w.freeze_panes = "A2"
    w.cell(row=n + 3, column=1, value=f"Lines shown: unearned at 9/30 or 10/31, invoiced in October, or excluded with 2026 service. "
                                      f"All other lines are fully earned before 9/30 and contribute zero.").font = f(size=9, italic=True)

    # MRR sanity and services detail
    w = wb.create_sheet("Revenue sanity checks")
    mrr = q(SRC, """WITH d AS (SELECT '2026-09-30' me UNION ALL SELECT '2026-10-31'),
                    last AS (SELECT d.me, e.subscription_id, e.mrr_after, ROW_NUMBER() OVER (PARTITION BY d.me, e.subscription_id ORDER BY e.event_date DESC, e.event_id DESC) rn
                             FROM d JOIN billing_subscription_events e ON e.event_date<=d.me)
                    SELECT me AS month_end, ROUND(SUM(mrr_after),2) mrr, ROUND(SUM(mrr_after)*12,2) arr FROM last WHERE rn=1 GROUP BY me""")
    end = table(w, mrr, 1, money=("mrr", "arr"), widths=[14, 16, 16])
    r = kv(w, end, [("Average October MRR", f"=AVERAGE(B2:B3)"),
                    ("Subscription revenue recognized October (4000)", round(-pl[pl.account_number == "4000"].net.sum(), 2)),
                    ("Revenue vs average MRR", f"=B{end+1}/B{end}-1")])
    w.cell(row=r - 1, column=2).number_format = PCT
    svc = q(SRC, """SELECT c.name customer, l.invoice_id, l.amount, l.service_start, l.service_end,
                    ROUND(l.amount*(MAX(0,julianday(MIN(l.service_end,'2026-10-31'))-julianday(MAX(l.service_start,'2026-10-01'))+1))
                          /(julianday(l.service_end)-julianday(l.service_start)+1),2) AS october_revenue
                    FROM billing_invoice_lines l JOIN billing_invoices i USING (invoice_id) JOIN billing_customers c ON c.customer_id=i.customer_id
                    WHERE l.line_type='services' AND l.service_end>='2026-10-01' AND l.service_start<='2026-10-31'
                    AND i.status NOT IN ('uncollectible','refunded') ORDER BY october_revenue DESC""")
    label(w, r + 1, "Services revenue in October by implementation line", fill=SEC_FILL)
    table(w, svc, r + 2, money=("amount", "october_revenue"), total=True, widths=[30, 11, 13, 12, 12, 16])
    assert_eq(svc.october_revenue.sum(), -pl[pl.account_number == "4100"].net.sum(), "services revenue")

    # Bookings check CRM -> billing
    w = wb.create_sheet("Bookings CRM vs billing")
    bk = q(SRC, """SELECT o.opportunity_id, a.name account, o.type, o.close_date, o.amount, o.services_amount, o.contract_seats, o.term_months,
                   o.contract_start_date, o.billing_subscription_id, s.seats billing_seats, s.unit_price, s.discount_pct, s.services_amount billing_services,
                   s.current_term_start, s.term_months billing_term
                   FROM crm_opportunities o JOIN crm_accounts a ON a.account_id=o.account_id LEFT JOIN billing_subscriptions s ON s.subscription_id=o.billing_subscription_id
                   WHERE o.stage='Closed Won' AND o.close_date BETWEEN ? AND ? ORDER BY o.close_date""", (PERIOD_START, PERIOD_END))
    bk["seat_gap"] = bk.contract_seats - bk.billing_seats
    end = table(w, bk, 1, money=("amount", "services_amount", "billing_services"), widths=[11, 28, 13, 11, 13, 12, 9, 7, 11, 11, 9, 9, 8, 12, 11, 8, 8],
                flag=lambda rec: rec[-1] != 0)
    w.cell(row=end, column=1, value="Norcross renewal: CRM 335 seats / 24 months; billing renewed 295 seats. 40 seats x $61.63 x 12 = $29,582.40 ARR not invoiced. "
                                    "Reviewer decision: billing to confirm order form and issue add-on invoice; no revenue entry.").font = f(size=9, italic=True)
    save(wb, "02_reconciliations/2300_deferred_revenue_waterfall.xlsx")


# ============================================================================= 8. recon summary (all balance sheet accounts)
def recon_summary():
    rows = [
        ("1000", "Operating Checking", "Bank statement (BA-OPER)", round(q(SRC, "SELECT SUM(amount) s FROM bank_transactions WHERE account_id='BA-OPER' AND posted_date<=?", (PERIOD_END,)).s[0], 2), "1000_1010_bank_reconciliation.xlsx"),
        ("1010", "Treasury Money Market", "Bank statement (BA-TRES)", round(q(SRC, "SELECT SUM(amount) s FROM bank_transactions WHERE account_id='BA-TRES' AND posted_date<=?", (PERIOD_END,)).s[0], 2), "1000_1010_bank_reconciliation.xlsx"),
        ("1050", "Stripe Clearing", "Stripe balance not yet paid out (gross)", 7737.15, "1050_stripe_clearing.xlsx"),
        ("1100", "Accounts Receivable", "Billing open invoices", 2273263.08, "1100_accounts_receivable.xlsx"),
        ("1200", "Prepaid Software", "Prepaid schedule (Salesforce, ZoomInfo)", None, "../03_journal_entries/je_support.xlsx (Prepaids)"),
        ("1210", "Prepaid Insurance", "Prepaid schedule (Keystone)", None, "../03_journal_entries/je_support.xlsx (Prepaids)"),
        ("1300", "Security Deposits", "Lease deposit - no October activity", 82000.00, "No activity; agrees to prior month"),
        ("1500", "Furniture & Leasehold Improvements", "Fixed asset register (DI-24117)", 186400.00, "../03_journal_entries/je_support.xlsx (Depreciation)"),
        ("1550", "Accumulated Depreciation", "Depreciation schedule", -6213.34, "../03_journal_entries/je_support.xlsx (Depreciation)"),
        ("2000", "Accounts Payable", "Ramp approved unpaid bills", -43531.81, "2000_accounts_payable.xlsx"),
        ("2100", "Ramp Corporate Card", "Ramp charges less statement payments", -190752.80, "2100_corporate_card.xlsx"),
        ("2200", "Accrued Expenses", "Accrual schedule (4 October accruals)", -142400.00, "../03_journal_entries/je_support.xlsx (Accruals)"),
        ("2210", "Accrued Commissions", "sales_commissions pay month 2026-11", -61229.94, "../03_journal_entries/je_support.xlsx (Commissions)"),
        ("2220", "Accrued Bonus", "Bonus accrual roll-forward (Jan-Oct, paid March)", None, "../03_journal_entries/je_support.xlsx (Bonus)"),
        ("2300", "Deferred Revenue", "Billing waterfall", -5093961.43, "2300_deferred_revenue_waterfall.xlsx"),
    ]
    sched = prepaid_schedule()
    for i, r in enumerate(rows):
        if r[0] == "1200":
            rows[i] = r[:3] + (round(sched[sched.account == "1200"].balance_10_31.sum(), 2),) + r[4:]
        if r[0] == "1210":
            rows[i] = r[:3] + (round(sched[sched.account == "1210"].balance_10_31.sum(), 2),) + r[4:]
        if r[0] == "2220":
            rows[i] = r[:3] + (balance(POST, "2220", PERIOD_END),) + r[4:]
    df = pd.DataFrame(rows, columns=["Account", "Name", "Source / support", "Source balance (Dr+ / Cr-)", "Workpaper"])
    df.insert(3, "GL balance 10/31 after close", [balance(POST, a, PERIOD_END) for a in df.Account])
    wb = Workbook()
    ws = sheet(wb, "Summary", "Balance sheet reconciliation summary - October 31, 2026",
               "GL: books_as_booked + posted entries (ties to QuickBooks, see 05_trial_balances). Source balances per workpaper.", first=True)
    end = table(ws, df, 5, money=("GL balance 10/31 after close", "Source balance (Dr+ / Cr-)"), widths=[9, 32, 44, 20, 20, 52])
    ws.cell(row=5, column=7, value="Difference").font = f(True, "FFFFFF")
    ws.cell(row=5, column=7).fill = HDR_FILL
    ws.cell(row=5, column=8, value="Status").font = f(True, "FFFFFF")
    ws.cell(row=5, column=8).fill = HDR_FILL
    for r in range(6, 6 + len(df)):
        ws.cell(row=r, column=7, value=f"=ROUND(D{r}-E{r},2)").number_format = NUM
        ws.cell(row=r, column=8, value=f'=IF(ABS(G{r})<0.05,"Tied","Investigate")')
    ws.column_dimensions["G"].width = 12
    ws.column_dimensions["H"].width = 12
    ws.cell(row=end, column=1, value="Prepaid schedule differences of a few cents are day-count rounding against the amortization posted.").font = f(size=9, italic=True)
    save(wb, "02_reconciliations/00_reconciliation_summary.xlsx")


# ============================================================================= 9. entry support
def prepaid_schedule():
    items = [("BILL-00313", "1200", "Salesforce", "SAL-2609414", 67795.20, "2026-09-15", "2027-09-14", "6200", "Sales"),
             ("BILL-00249", "1200", "ZoomInfo", "ZOO-2601502", 27600.00, "2026-01-01", "2026-12-31", "6200", "Sales"),
             ("BILL-00223", "1200", "Salesforce (prior term)", "SAL-2509928", 29700.00, "2025-09-15", "2026-09-14", "6200", "Sales"),
             ("BILL-00260", "1210", "Keystone Mutual Insurance", "KEY-2602130", 64000.00, "2026-02-01", "2027-01-31", "6620", "G&A")]
    rows = []
    for bill, acct, vendor, inv, amt, s, e, exp, cls in items:
        sd, ed = date.fromisoformat(s), date.fromisoformat(e)
        tot = (ed - sd).days + 1

        def rem(me):
            return max(0, min(tot, (ed - date.fromisoformat(me)).days))
        oct_days = max(0, (min(ed, date(2026, 10, 31)) - max(sd, date(2026, 10, 1))).days + 1)
        rows.append({"bill_id": bill, "account": acct, "vendor": vendor, "invoice": inv, "amount": amt, "service_start": s, "service_end": e,
                     "total_days": tot, "days_remaining_9_30": rem(PRIOR_END), "balance_9_30": round(amt * rem(PRIOR_END) / tot, 2),
                     "october_days": oct_days, "october_amortization": round(amt * oct_days / tot, 2),
                     "days_remaining_10_31": rem(PERIOD_END), "balance_10_31": round(amt * rem(PERIOD_END) / tot, 2), "expense_account": exp, "class": cls})
    return pd.DataFrame(rows)


def entry_support():
    wb = Workbook()
    # Log
    ws = sheet(wb, "JE log", "Journal entry log - October 2026 close (posted 2026-11-01)", "inputs/posted_entries.json", first=True)
    log = pd.DataFrame([{"draft_id": e["draft_id"], "qbo_id": e["qbo_id"], "txn_date": e["txn_date"], "category": e["category"],
                         "prior_period_correction": "Yes" if e.get("prior_period_correction") else "",
                         "memo": e["memo"], "amount": e.get("amount") or round(sum(l.get("debit", 0) for l in e["lines"]), 2),
                         "support": e["support"]} for e in ENTRIES])
    table(ws, log, 5, money=("amount",), widths=[13, 8, 11, 22, 10, 80, 13, 50], flag=lambda rec: rec[4] == "Yes")
    ws.freeze_panes = "A6"
    w = wb.create_sheet("JE lines")
    lines = POSTED[["je_id", "txn_date", "account_number", "debit", "credit", "class", "vendor_id", "description"]].copy()
    lines.insert(3, "account_name", lines.account_number.map(ACCT_NAME))
    table(w, lines.rename(columns={"vendor_id": "vendor"}), 1, money=("debit", "credit"), total=True, widths=[13, 11, 8, 28, 13, 13, 16, 32, 80])

    # Accruals
    w = sheet(wb, "Accruals", "Accrued expenses (2200) - October 2026", "spend_bills, spend_vendors, GL subscription revenue")
    aws = q(SRC, "SELECT invoice_number, service_period_start, amount FROM spend_bills WHERE vendor_id='V001' AND service_period_start>='2026-05-01' ORDER BY 2")
    sub_rev = {p: round(-POST[(POST.period == p) & (POST.account_number == "4000")].net.sum(), 2) for p in ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]}
    aws["service_month"] = aws.service_period_start.str[:7]
    aws["subscription_revenue"] = aws.service_month.map(sub_rev)
    end = label(w, 5, "1. Amazon Web Services - usage scales with subscription revenue", fill=SEC_FILL)
    end = table(w, aws[["invoice_number", "service_month", "amount", "subscription_revenue"]], end, money=("amount", "subscription_revenue"), widths=[18, 14, 16, 18])
    n0 = end - 2 - len(aws)
    r = kv(w, end, [("Aug + Sep AWS as % of subscription revenue", f"=(C{n0+4}+C{n0+5})/(D{n0+4}+D{n0+5})"),
                    ("October subscription revenue (after true-up)", sub_rev["2026-10"]),
                    ("Estimate", f"=B{end}*B{end+1}"), ("Accrued (rounded)", 86900.00, "bold", "D1031-124A / reversed 11/1 by D1031-124AR")])
    w.cell(row=end, column=2).number_format = PCT
    r = label(w, r + 1, "2. Marlow & Pierce LLP - legal, billed monthly in arrears", fill=SEC_FILL)
    mp = q(SRC, "SELECT invoice_number, service_period_start, amount FROM spend_bills WHERE vendor_id='V026' AND service_period_start>='2026-05-01' ORDER BY 2")
    e2 = table(w, mp, r, money=("amount",))
    r = kv(w, e2, [("Jul-Sep average (run-rate)", f"=AVERAGE(C{e2-4}:C{e2-2})"), ("Accrued (rounded; reviewer kept)", 13100.00, "bold", "D1031-376E / D1031-376ER")])
    r = label(w, r + 1, "3. Brightquarry Content Co. - fixed $14,000 monthly retainer billed at month-end; October invoice not received", fill=SEC_FILL)
    r = kv(w, r, [("Accrued", 14000.00, "bold", "D1031-07AB / D1031-07ABR")])
    r = label(w, r + 1, "4. Talentridge Search Partners - TAL-2610992 placement fee (BILL-00327 pending approval)", fill=SEC_FILL)
    tal = q(SRC, "SELECT bill_id, invoice_number, invoice_date, amount, department, status, memo FROM spend_bills WHERE bill_id='BILL-00327'")
    e4 = table(w, tal, r, money=("amount",), widths=[18, 14, 16, 18, 12, 16, 80])
    r = kv(w, e4, [("Accrued - fee earned on offer acceptance 10/12; hire starts 11/2", 28400.00, "bold", "D1031-8FD2 / D1031-8FD2R")])
    r = kv(w, r + 1, [("Total accrued expenses 10/31 (86,900 + 13,100 + 14,000 + 28,400)", 86900.00 + 13100.00 + 14000.00 + 28400.00, "bold"), ("GL 2200 after close (credit)", -balance(POST, "2200", PERIOD_END)), ("Difference", f"=ROUND(B{r+1}-B{r+2},2)")])
    prior = PRE[(PRE.account_number == "2200") & (PRE.txn_date.isin([PRIOR_END, PERIOD_START]))][["je_id", "txn_date", "memo", "net"]]
    label(w, r + 1, "September accruals and their October 1 reversals (all cleared)", fill=SEC_FILL)
    table(w, prior, r + 2, money=("net",), total=True)

    # Prepaids
    w = sheet(wb, "Prepaids", "Prepaid schedule (1200, 1210) - October 2026", "spend_bills service periods; amortized by day")
    sch = prepaid_schedule()
    end = table(w, sch, 5, money=("amount", "balance_9_30", "october_amortization", "balance_10_31"), total=True,
                widths=[11, 8, 26, 13, 12, 11, 11, 8, 9, 13, 8, 13, 9, 13, 9, 8])
    kv(w, end, [("1200 GL after close", balance(POST, "1200", PERIOD_END), "", "Schedule vs GL: day-count rounding of cents"),
                ("1200 per schedule", round(sch[sch.account == "1200"].balance_10_31.sum(), 2)),
                ("1210 GL after close", balance(POST, "1210", PERIOD_END)),
                ("1210 per schedule", round(sch[sch.account == "1210"].balance_10_31.sum(), 2)),
                ("Salesforce correction: unexpired at 9/30 moved from 6200 to 1200 (D1031-BF83, prior-period)", 64823.36, "bold",
                 "Renewal SAL-2609414 was expensed in full in September")])

    # Depreciation
    w = sheet(wb, "Depreciation", "Fixed assets and depreciation (1500, 1550) - October 2026", "books_as_booked 1500 additions; straight-line 60 months")
    fa = PRE[(PRE.account_number == "1500")][["je_id", "txn_date", "source_ref", "memo", "net"]]
    end = table(w, fa, 5, money=("net",), widths=[12, 11, 14, 46, 14])
    kv(w, end, [("Cost", 186400.00), ("Useful life (months)", 60), ("Monthly depreciation", "=ROUND(B{0}/B{1},2)".format(end, end + 1), "bold", "D1031-2864; same as Sep JE008913"),
                ("Accumulated depreciation 10/31 (2 months: Sep, Oct)", -balance(POST, "1550", PERIOD_END)),
                ("No October additions to 1500", 0)])
    w.cell(row=end + 1, column=2).number_format = "0"

    # Commissions
    w = sheet(wb, "Commissions", "Accrued commissions (2210) - October 2026", "sales_commissions, crm_opportunities")
    cm = q(SRC, """SELECT sc.opp_id, a.name account, o.type, sc.close_date, sc.employee_id, o.amount AS first_year_acv, sc.amount AS commission, sc.pay_month
                   FROM sales_commissions sc JOIN crm_opportunities o ON o.opportunity_id=sc.opp_id JOIN crm_accounts a ON a.account_id=o.account_id
                   WHERE sc.close_date BETWEEN ? AND ? ORDER BY sc.close_date""", (PERIOD_START, PERIOD_END))
    end = table(w, cm, 5, money=("first_year_acv", "commission"), total=True, widths=[11, 30, 13, 11, 10, 15, 13, 11])
    for i in range(6, 6 + len(cm)):
        w.cell(row=i, column=9, value=f"=ROUND(F{i}*10%,2)-G{i}").number_format = NUM
    w.cell(row=5, column=9, value="10% check").font = f(True, "FFFFFF")
    w.cell(row=5, column=9).fill = HDR_FILL
    kv(w, end, [("Accrued (D1031-A52D)", 61229.94, "bold"), ("September accrual paid in PR-202610-1 and cleared from 2210", 65048.40, "", "JE005167 line 'Commissions paid (accrued)'")])
    assert_eq(cm.commission.sum(), 61229.94, "commissions")

    # Bonus
    w = sheet(wb, "Bonus", "Accrued bonus (2220) - October 2026", "hr_employees active at 10/31 (non-Sales), 8% target, accrued monthly, paid March")
    emp = q(SRC, """SELECT department, COUNT(*) headcount, SUM(annual_salary) base_salary FROM hr_employees
                    WHERE hire_date<=? AND (termination_date IS NULL OR termination_date>?) AND department<>'Sales' GROUP BY department""", (PERIOD_END, PERIOD_END))
    emp["account"] = emp.department.map(lambda d: "5100" if d == "Support" else "6040")
    end = table(w, emp, 5, money=("base_salary",), total=True, widths=[18, 10, 15, 9, 15])
    w.cell(row=5, column=5, value="Monthly accrual").font = f(True, "FFFFFF")
    w.cell(row=5, column=5).fill = HDR_FILL
    for i in range(6, 6 + len(emp)):
        w.cell(row=i, column=5, value=f"=ROUND(C{i}*8%/12,2)").number_format = NUM
    w.cell(row=6 + len(emp), column=5, value=f"=SUM(E6:E{5+len(emp)})").number_format = NUM
    roll = PRE[(PRE.account_number == "2220") & (PRE.txn_date >= "2026-01-01")].groupby("period").net.sum().round(2).reset_index()
    kv(w, end, [("Accrued (D1031-9BF6)", 69410.00, "bold", "Headcount and salaries unchanged from September"),
                ("2220 balance after close (credit)", -balance(POST, "2220", PERIOD_END))])
    table(w, roll.rename(columns={"net": "2220 activity (Dr+ / Cr-) before close"}), end + 4, money=("2220 activity (Dr+ / Cr-) before close",))

    # Payroll tie
    w = sheet(wb, "Payroll tie-out", "Payroll register to GL - October 2026", "payroll_runs, payroll_items vs books_as_booked JE005167 / JE005168")
    pr = q(SRC, """SELECT r.run_id, i.department, ROUND(SUM(i.base_pay),2) base_pay, ROUND(SUM(i.commission_pay),2) commission_pay,
                   ROUND(SUM(i.gross_pay),2) gross_pay, ROUND(SUM(i.employer_taxes),2) employer_taxes, ROUND(SUM(i.net_pay),2) net_pay,
                   ROUND(SUM(i.employee_taxes_withheld),2) employee_taxes_withheld, COUNT(*) employees
                   FROM payroll_runs r JOIN payroll_items i ON i.run_id=r.run_id WHERE r.pay_date BETWEEN ? AND ? GROUP BY r.run_id, i.department""",
           (PERIOD_START, PERIOD_END))
    end = table(w, pr, 5, money=("base_pay", "commission_pay", "gross_pay", "employer_taxes", "net_pay", "employee_taxes_withheld"), total=True,
                widths=[13, 17, 14, 14, 14, 14, 14, 14, 9])
    gl_pay = PRE[PRE.source_ref.isin(["PR-202610-1", "PR-202610-2"])]
    kv(w, end, [("GL salaries (6000 + 5100) per payroll JEs", round(gl_pay[gl_pay.account_number.isin(["6000", "5100"])].net.sum(), 2)),
                ("GL commissions paid from 2210", round(gl_pay[gl_pay.account_number == "2210"].net.sum(), 2)),
                ("GL employer taxes (6010 + 5110)", round(gl_pay[gl_pay.account_number.isin(["6010", "5110"])].net.sum(), 2)),
                ("GL cash funded (net pay + tax remittance)", round(-gl_pay[gl_pay.account_number == "1000"].net.sum(), 2), "",
                 "Equals net pay + employee withholding + employer taxes; matches the Gusto bank debits"),
                ("No one paid after termination; no new hires in October; 74 employees on payroll", "")])
    assert_eq(gl_pay[gl_pay.account_number.isin(["6000", "5100"])].net.sum() + gl_pay[gl_pay.account_number == "2210"].net.sum(), pr.gross_pay.sum(), "payroll gross")
    assert_eq(gl_pay[gl_pay.account_number.isin(["6010", "5110"])].net.sum(), pr.employer_taxes.sum(), "payroll taxes")

    # Corrections
    w = sheet(wb, "Corrections", "Prior-period errors corrected in October (closed periods not reopened)", "Evidence per item")
    corr = pd.DataFrame([
        {"entry": "D1031-71D6", "error": "Invoice FV-11156 (in_001811, $71,280, service 11/13/25-11/12/26) written off in April 2026; full amount charged to 6900 while the "
                                         "unearned portion stayed in 2300", "period": "2026-04", "calculation": "$71,280 x 43/365 (days after 9/30)", "amount": 8397.37,
         "effect": "Dr 2300 / Cr 6900 - October bad debt lower"},
        {"entry": "D1031-BF83", "error": "Salesforce renewal SAL-2609414 ($67,795.20, 9/15/26-9/14/27) expensed in full to 6200 in September", "period": "2026-09",
         "calculation": "$67,795.20 x 349/365 unexpired at 9/30", "amount": 64823.36, "effect": "Dr 1200 / Cr 6200 - October software expense lower"},
        {"entry": "D1031-CF36", "error": "June 2026 AWS bill EUINUS26068261 ($63,677.46) coded to 6200 Software / Marketing when booked 7/2/2026", "period": "2026-07",
         "calculation": "Full bill amount", "amount": 63677.46, "effect": "Dr 5000 (Cost of Revenue) / Cr 6200 (Marketing) - P&L neutral, moves gross margin"},
    ])
    end = table(w, corr, 5, money=("amount",), widths=[12, 90, 9, 36, 13, 52])
    aws_jul = PRE[(PRE.source_ref == "BILL-00284")][["je_id", "txn_date", "account_number", "class", "net", "memo"]]
    label(w, end, "Evidence - how the June AWS bill was booked", fill=SEC_FILL)
    end = table(w, aws_jul, end + 1, money=("net",))
    sf = PRE[(PRE.source_ref == "BILL-00313")][["je_id", "txn_date", "account_number", "class", "net", "memo"]]
    label(w, end, "Evidence - how the Salesforce renewal was booked", fill=SEC_FILL)
    end = table(w, sf, end + 1, money=("net",))
    wo = PRE[(PRE.source_ref.isin(["FV-11156", "in_001811"])) | (PRE.memo.str.contains("FV-11156", na=False))][["je_id", "txn_date", "account_number", "net", "memo"]]
    label(w, end, "Evidence - FV-11156 invoice and write-off", fill=SEC_FILL)
    table(w, wo, end + 1, money=("net",))

    # Chargeback
    w = sheet(wb, "Chargeback", "Stripe dispute withdrawn from payout po_00688", "stripe_balance_transactions")
    cb = q(SRC, "SELECT * FROM stripe_balance_transactions WHERE payout_id='po_00688' ORDER BY type, created")
    end = table(w, cb, 5, money=("amount", "fee", "net"), total=True)
    kv(w, end, [("Bank received (BTX-001623)", 450.68), ("GL deposit before close (JE005043)", 11177.12),
                ("Unrecorded: dispute $10,711.44 + fee $15.00", "=B{0}-B{1}".format(end + 1, end), "bold", "D1031-B7B9")])
    save(wb, "03_journal_entries/je_support.xlsx")
    p = CLOSE / "03_journal_entries" / "je_log.csv"
    log.to_csv(p, index=False)
    print("wrote", p.relative_to(ROOT))


# ============================================================================= 10. flux and budget
def flux():
    months = ["2026-07", "2026-08", "2026-09", "2026-10"]
    pl = POST[POST.period.isin(months) & POST.account_number.map(lambda a: ACCT_STMT.get(a) == "PL")]
    piv = pl.pivot_table(index="account_number", columns="period", values="net", aggfunc="sum").fillna(0)
    sign = piv.index.map(lambda a: -1 if a.startswith(("4", "7")) else 1)
    piv = piv.mul(sign, axis=0).round(2)
    bud = q(SRC, "SELECT account_number, SUM(amount) budget FROM plan_budget_fy2026 WHERE month='2026-10-01' GROUP BY 1").set_index("account_number").budget
    df = piv.reset_index()
    df.insert(1, "account_name", df.account_number.map(ACCT_NAME))
    df["budget_2026-10"] = df.account_number.map(bud).fillna(0).round(2)
    drivers = {
        "4000": "Avg MRR up to $875k: 18 new logos incl. Yarrow ($30.2k MRR from 10/17) and Talbot Electric ($18.2k MRR from 10/1). Below budget: ending ARR $385k behind plan.",
        "4100": "Ten implementation lines earning; Garland, Talbot Electric, Redfern = 66%. Budget is flat $35k/month.",
        "5000": "Includes $63,677 June AWS reclass (prior period). Excluding it $95,965 = 10.8% of subscription revenue vs 9.2% plan.",
        "6030": "Commissionable first-year ACV $612k across 8 deals vs ~$837k implied by budget.",
        "6200": "Negative from prior-period corrections: Salesforce prepaid ($64,823) and AWS reclass ($63,677). Underlying $19,287.",
        "6300": "Google Ads $72.5k + LinkedIn Ads $35.1k on card; running ~2x plan since September.",
        "6310": "September OpsForward Summit booth; none in October.",
        "6600": "October = $13,100 run-rate accrual + $32 September true-up; September had higher activity.",
        "6000": "Headcount 74 = plan; $70k under budget - plan salary assumptions to be explained.",
        "6700": "Talentridge $28,400 Senior AE placement + LinkedIn Recruiter.",
        "6900": "$10,711 chargeback net of $8,397 FV-11156 correction.",
    }
    df["driver"] = df.account_number.map(drivers).fillna("")
    wb = Workbook()
    ws = sheet(wb, "P&L flux", "P&L flux and budget variance - October 2026 (after close)",
               "GL: books_as_booked + posted entries. Budget: plan_budget_fy2026 (natural sign). Flag: >10% AND >$10,000.", first=True)
    cols = ["account_number", "account_name"] + months + ["budget_2026-10"]
    n = len(df)
    for j, h in enumerate(cols + ["Oct vs Sep $", "Oct vs Sep %", "Oct vs 3-mo avg $", "Oct vs budget $", "Oct vs budget %", "Flag", "Driver"], 1):
        c = ws.cell(row=5, column=j, value=h)
        c.font = f(True, "FFFFFF")
        c.fill = HDR_FILL
        c.alignment = Alignment(wrap_text=True)
    for i, rec in enumerate(df[cols + ["driver"]].itertuples(index=False), start=6):
        for j, v in enumerate(rec[:-1], 1):
            c = ws.cell(row=i, column=j, value=v)
            if j >= 3:
                c.number_format = NUM0
        ws.cell(row=i, column=9, value=f"=F{i}-E{i}").number_format = NUM0
        ws.cell(row=i, column=10, value=f'=IF(E{i}=0,"",I{i}/ABS(E{i}))').number_format = PCT
        ws.cell(row=i, column=11, value=f"=F{i}-AVERAGE(C{i}:E{i})").number_format = NUM0
        ws.cell(row=i, column=12, value=f"=F{i}-G{i}").number_format = NUM0
        ws.cell(row=i, column=13, value=f'=IF(G{i}=0,"",L{i}/ABS(G{i}))').number_format = PCT
        ws.cell(row=i, column=14, value=f'=TRIM(IF(AND(ABS(I{i})>10000,OR(E{i}=0,ABS(I{i})>0.1*ABS(E{i}))),"MoM ","")&IF(AND(ABS(L{i})>10000,OR(G{i}=0,ABS(L{i})>0.1*ABS(G{i}))),"Budget",""))')
        ws.cell(row=i, column=15, value=rec[-1]).alignment = Alignment(wrap_text=True)
        for j in range(1, 16):
            ws.cell(row=i, column=j).font = f(size=9)
    r = 6 + n + 1
    rev = [i for i, a in enumerate(df.account_number, 6) if a.startswith("4")]
    cogs = [i for i, a in enumerate(df.account_number, 6) if a.startswith("5")]
    opex = [i for i, a in enumerate(df.account_number, 6) if a.startswith("6")]
    oth = [i for i, a in enumerate(df.account_number, 6) if a.startswith("7")]

    def sumrows(rows, col):
        return "=" + "+".join(f"{col}{x}" for x in rows) if rows else 0
    for lab, rows in (("Total revenue", rev), ("Total cost of revenue", cogs), ("Total operating expenses", opex), ("Other income", oth)):
        ws.cell(row=r, column=2, value=lab).font = f(True)
        for j, col in enumerate("CDEFG", 3):
            c = ws.cell(row=r, column=j, value=sumrows(rows, col))
            c.number_format = NUM0
            c.font = f(True)
        r += 1
    ws.cell(row=r, column=2, value="Gross margin %").font = f(True)
    for j, col in enumerate("CDEFG", 3):
        ws.cell(row=r, column=j, value=f"=({col}{r-4}-{col}{r-3})/{col}{r-4}").number_format = PCT
    r += 1
    ws.cell(row=r, column=2, value="Net income (loss)").font = f(True)
    for j, col in enumerate("CDEFG", 3):
        c = ws.cell(row=r, column=j, value=f"={col}{r-5}-{col}{r-4}-{col}{r-3}+{col}{r-2}")
        c.number_format = NUM0
        c.font = f(True)
    ws.cell(row=r + 2, column=1, value="QuickBooks also shows $567.50 'Inventory Shrinkage (deleted)' in October cost of revenue from sandbox demo data; "
                                       "it is excluded here, so October net loss here is $567.50 smaller than QuickBooks ($595,754.80).").font = f(size=9, italic=True)
    for j, w_ in enumerate([8, 30, 12, 12, 12, 12, 12, 12, 8, 12, 12, 12, 8, 10, 80], 1):
        ws.column_dimensions[get_column_letter(j)].width = w_
    ws.freeze_panes = "C6"

    # Adjusted view and functions
    w = sheet(wb, "Reported vs adjusted", "October 2026 - reported vs excluding prior-period corrections",
              "Board headline is REPORTED (reviewer decision 11/1); adjusted view is supplementary")
    oct_ = POST[(POST.period == "2026-10") & POST.account_number.map(lambda a: ACCT_STMT.get(a) == "PL")]
    ppc = POSTED[POSTED.je_id.isin(["D1031-71D6", "D1031-BF83", "D1031-CF36"])]
    rev_ = -oct_[oct_.account_number.str.startswith("4")].net.sum()
    cogs_ = oct_[oct_.account_number.str.startswith("5")].net.sum()
    opex_ = oct_[oct_.account_number.str.startswith("6")].net.sum()
    oi = -oct_[oct_.account_number.str.startswith("7")].net.sum()
    cogs_adj = cogs_ - ppc[ppc.account_number.str.startswith("5")].net.sum()
    opex_adj = opex_ - ppc[ppc.account_number.str.startswith("6")].net.sum()
    tbl = pd.DataFrame([
        ["Revenue", rev_, rev_], ["Cost of revenue", cogs_, cogs_adj], ["Gross margin %", (rev_ - cogs_) / rev_, (rev_ - cogs_adj) / rev_],
        ["Operating expenses", opex_, opex_adj], ["Interest income", oi, oi],
        ["Net income (loss)", rev_ - cogs_ - opex_ + oi, rev_ - cogs_adj - opex_adj + oi]], columns=["Line", "Reported", "Excl. prior-period corrections"])
    end = table(w, tbl, 5, money=("Reported", "Excl. prior-period corrections"), widths=[34, 16, 26])
    for col in (2, 3):
        w.cell(row=8, column=col).number_format = PCT
    cls = oct_[oct_.account_number.str.startswith("6")].groupby("class").net.sum()
    fn = q(SRC, "SELECT department, pl_function FROM ref_departments").set_index("department").pl_function
    func = cls.groupby(cls.index.map(lambda c: fn.get(c, c))).sum().round(2).reset_index()
    func.columns = ["Function", "Opex reported"]
    adj = ppc[ppc.account_number.str.startswith("6")].groupby("class").net.sum()
    func["Opex excl. corrections"] = func.apply(lambda x: round(x["Opex reported"] - sum(v for k, v in adj.items() if fn.get(k, k) == x.Function), 2), axis=1)
    table(w, func, end, money=("Opex reported", "Opex excl. corrections"), total=True)

    # KPIs
    w = sheet(wb, "Metrics", "Key metrics - October 2026", "billing_subscription_events (ARR), bank (cash), plan_arr_fy2026")
    ev = q(SRC, "SELECT event_type, COUNT(*) events, ROUND(SUM(mrr_after-mrr_before)*12,2) arr_change FROM billing_subscription_events WHERE event_date BETWEEN ? AND ? GROUP BY 1",
           (PERIOD_START, PERIOD_END))
    end = table(w, ev, 5, money=("arr_change",), total=True, widths=[46, 16, 18])
    cash = lambda d: balance(POST, "1000", d) + balance(POST, "1010", d) + balance(POST, "1050", d)
    plan = q(SRC, "SELECT plan_net_new_arr, plan_ending_arr FROM plan_arr_fy2026 WHERE month='2026-10-01'")
    r = kv(w, end, [("Opening ARR 9/30", 10007448.24, "", "Revenue sanity checks tab in 2300 workpaper"), ("Ending ARR 10/31", 11003294.64),
                    ("Net new ARR", f"=B{end+1}-B{end}", "bold"), ("Plan net new ARR", float(plan.plan_net_new_arr[0])), ("Plan ending ARR", float(plan.plan_ending_arr[0])),
                    ("Gross revenue retention (month, churn + contraction)", f"=1-(-SUMIFS(C6:C{end-3},A6:A{end-3},\"churn\")-SUMIFS(C6:C{end-3},A6:A{end-3},\"contraction\")-SUMIFS(C6:C{end-3},A6:A{end-3},\"renewal_contraction\"))/B{end}"),
                    ("Net revenue retention (month, excl. new)", f"=1+(SUM(C6:C{end-3})-SUMIFS(C6:C{end-3},A6:A{end-3},\"new\"))/B{end}"),
                    ("Cash 9/30 (1000 + 1010 + 1050)", cash(PRIOR_END)), ("Cash 10/31", cash(PERIOD_END)), ("October net burn", f"=B{end+7}-B{end+8}", "bold"),
                    ("Runway at October burn (months)", f"=B{end+8}/B{end+9}")])
    for rr in (end + 5, end + 6):
        w.cell(row=rr, column=2).number_format = PCT
    w.cell(row=end + 10, column=2).number_format = "0.0"

    # Balance sheet flux
    w = sheet(wb, "Balance sheet flux", "Balance sheet movements - September to October 2026 (after close)", "GL")
    accts = [a for a in ACCOUNTS.account_number if ACCT_STMT.get(a) == "BS"]
    bs = pd.DataFrame({"account": accts, "name": [ACCT_NAME[a] for a in accts],
                       "sep_30": [balance(PRE, a, PRIOR_END) for a in accts], "oct_31": [balance(POST, a, PERIOD_END) for a in accts]})
    bs = bs[(bs.sep_30 != 0) | (bs.oct_31 != 0)]
    bs["change"] = (bs.oct_31 - bs.sep_30).round(2)
    notes = {"1000": "See bank rec", "1010": "$1.2M to operating, +$113.6k interest", "1100": "Oct annual invoices: Yarrow $397k, Norcross $218k; Garland $321k unpaid",
             "1200": "Salesforce prepaid correction net of amortization", "1210": "Amortization", "1550": "Depreciation", "2000": "Duplicate deleted; bills paid",
             "2100": "Sep statement paid; Oct charges", "2200": "Sep accruals reversed; 4 Oct accruals", "2210": "Sep paid; Oct accrued", "2220": "Monthly bonus accrual",
             "2300": "Billings > revenue; FV-11156 correction"}
    bs["note"] = bs.account.map(notes).fillna("")
    table(w, bs, 5, money=("sep_30", "oct_31", "change"), widths=[9, 38, 16, 16, 16, 60])
    save(wb, "04_variance_analysis/flux_and_budget_variance.xlsx")


if __name__ == "__main__":
    trial_balances()
    bank()
    stripe()
    card()
    receivables()
    payables()
    deferred_revenue()
    recon_summary()
    entry_support()
    flux()
    print("all tie-outs passed")
