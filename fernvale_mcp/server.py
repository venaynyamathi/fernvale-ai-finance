"""
Fernvale MCP server: gives Claude the company's QuickBooks sandbox and its source systems.

Tools
  QuickBooks (read)      qbo_report, qbo_query, qbo_get, qbo_chart_of_accounts
  QuickBooks (write)     qbo_draft_journal_entry, qbo_draft_bill, qbo_draft_change,
                         qbo_list_drafts, qbo_discard_draft, qbo_post_draft
  Source systems (read)  source_tables, source_query, legacy_pl_history

Guardrails
  * Sandbox only (the QuickBooks client refuses anything else).
  * Nothing is written to QuickBooks except through qbo_post_draft, and only for a draft the
    person has approved. Drafts dated on or before the closing date are refused unless the
    draft was explicitly marked as a prior-period adjustment.
  * Source data is opened read-only. There is no tool that can read private/ (the answer key)
    or the generator code.
"""
import json
import re
import secrets
import sqlite3
import time
from pathlib import Path

try:                                    # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:                     # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
try:
    from mcp.types import ToolAnnotations
except ImportError:                     # very old SDKs
    ToolAnnotations = None

from qbo_loader.client import QBO, QBOError, WORK

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = ROOT / "data" / "source_systems.sqlite"
BOOKS_DB = ROOT / "build" / "books_as_booked.sqlite"
DRAFTS = WORK / "drafts"
CLOSED_THROUGH = "2026-09-30"
AGENT_TAG = "FV-AGENT:"
MAX_CHARS = 60_000            # keep tool results a manageable size

INSTRUCTIONS = f"""\
Fernvale Systems, Inc. is a fictional B2B SaaS company (workflow automation software, ~$11M ARR).
Its books are in a QuickBooks Online sandbox, closed through {CLOSED_THROUGH}; October 2026 is
the open month and has had no month-end entries yet. The operational systems (CRM, Stripe-style
billing and payments, Gusto-style payroll, Ramp-style AP and cards, bank statements, FY2026
budget) are in a read-only database: start with source_tables.

Records loaded from the ledger carry a private note starting 'FV:' plus a ledger ID; records
you post carry 'FV-AGENT:'. Account numbers: 1000s assets, 2000s liabilities, 3000s equity, 4000s
revenue, 5000s cost of revenue, 6000s operating expenses, 7000 other income. Classes are
departments. Customer and vendor IDs in the source data (C00123, V012) appear in QuickBooks
notes as FV:C00123.

To change the books: create a draft (qbo_draft_*), show it to the person, and call
qbo_post_draft only after they approve that specific draft.
"""

mcp = _Server(name="fernvale", instructions=INSTRUCTIONS)
_qbo = None


def qbo():
    global _qbo
    if _qbo is None:
        _qbo = QBO()
        if not _qbo.tokens:
            raise QBOError("Not signed in to QuickBooks. In PowerShell, from the repo folder, run: "
                           "python -m qbo_loader signin")
    return _qbo


def _ann(read_only, destructive=False):
    if ToolAnnotations is None:
        return None
    return ToolAnnotations(readOnlyHint=read_only, destructiveHint=destructive,
                           openWorldHint=False)


def _trim(text):
    if len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS] + f"\n... (truncated at {MAX_CHARS:,} characters; narrow the request)"


def _tsv(header, rows):
    def cell(v):
        return "" if v is None else str(v).replace("\t", " ").replace("\n", " ")
    return "\n".join(["\t".join(header)] + ["\t".join(cell(v) for v in r) for r in rows])


# ============================================================== QuickBooks: read
def _flatten_report(rep):
    cols = [c.get("ColTitle") or c.get("ColType") or f"col{i}"
            for i, c in enumerate(rep.get("Columns", {}).get("Column", []))]
    out = []

    def walk(node, path):
        for r in node.get("Row", []):
            title = None
            if r.get("Header", {}).get("ColData"):
                title = r["Header"]["ColData"][0].get("value")
            sub = path + [title] if title else path
            if "ColData" in r:
                vals = [c.get("value", "") for c in r["ColData"]]
                out.append([" > ".join(path), "row"] + vals)
            if "Rows" in r:
                walk(r["Rows"], sub)
            if r.get("Summary", {}).get("ColData"):
                vals = [c.get("value", "") for c in r["Summary"]["ColData"]]
                out.append([" > ".join(sub), "total"] + vals)
    walk(rep.get("Rows", {}), [])
    head = rep.get("Header", {})
    meta = (f"# {head.get('ReportName', '')} {head.get('StartPeriod', '')} to "
            f"{head.get('EndPeriod', '')} ({head.get('ReportBasis', '')})")
    return meta + "\n" + _tsv(["section", "kind"] + cols, out)


@mcp.tool(annotations=_ann(True))
def qbo_report(report: str, start_date: str = "", end_date: str = "",
               options: dict | None = None) -> str:
    """Run a QuickBooks report and return it as a tab-separated table.

    report: TrialBalance, ProfitAndLoss, ProfitAndLossDetail, BalanceSheet, GeneralLedger,
      CashFlow, AgedReceivables, AgedReceivableDetail, AgedPayables, AgedPayableDetail,
      CustomerBalance, VendorBalance, TransactionList, AccountList.
    start_date / end_date: YYYY-MM-DD.
    options: extra QuickBooks report parameters, e.g. {"summarize_column_by": "Month"},
      {"summarize_column_by": "Classes"}, {"accounting_method": "Cash"},
      {"account": "<QuickBooks account Id>"}, {"report_date": "2026-10-31"} for aging.
    """
    params = {"accounting_method": "Accrual"}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    params.update({k: str(v) for k, v in (options or {}).items()})
    return _trim(_flatten_report(qbo().report(report, params)))


@mcp.tool(annotations=_ann(True))
def qbo_query(sql: str, max_rows: int = 500) -> str:
    """Run a read-only QuickBooks query (their SQL dialect) and return JSON records.

    Examples:
      SELECT * FROM Invoice WHERE TxnDate >= '2026-10-01'
      SELECT * FROM Bill WHERE VendorRef = '58' ORDERBY TxnDate DESC
      SELECT * FROM Payment WHERE TxnDate >= '2026-10-01'
      SELECT * FROM Account WHERE AccountType = 'Bank'
    Entities: Invoice, Payment, CreditMemo, RefundReceipt, Bill, BillPayment, Purchase,
    Deposit, Transfer, JournalEntry, Customer, Vendor, Account, Class, Item.
    No LIKE on notes; filter by date, customer/vendor ref, amount or Id instead.
    """
    s = sql.strip().rstrip(";")
    if not re.match(r"(?is)^select\s", s) or ";" in s:
        raise ValueError("Only a single SELECT query is allowed.")
    rows = qbo().query(s)
    rows = rows[:max(1, min(max_rows, 2000))]
    for r in rows:
        r.pop("MetaData", None)
        r.pop("domain", None)
        r.pop("sparse", None)
    return _trim(json.dumps({"count": len(rows), "records": rows}, default=str))


@mcp.tool(annotations=_ann(True))
def qbo_get(entity: str, id: str) -> str:
    """Fetch one QuickBooks record by entity name and Id (e.g. "Invoice", "1234")."""
    res = qbo().request("GET", f"{entity.lower()}/{id}")
    return json.dumps(res.get(entity, res), default=str)


@mcp.tool(annotations=_ann(True))
def qbo_chart_of_accounts(include_inactive: bool = False) -> str:
    """The chart of accounts: number, name, type, subtype, balance and QuickBooks Id."""
    where = "" if include_inactive else " WHERE Active = true"
    rows = qbo().query(f"SELECT * FROM Account{where}")
    rows.sort(key=lambda a: (a.get("AcctNum") or "zzzz", a["Name"]))
    return _tsv(["acct_num", "name", "type", "subtype", "balance", "active", "qbo_id"],
                [[a.get("AcctNum"), a.get("FullyQualifiedName", a["Name"]), a["AccountType"],
                  a.get("AccountSubType"), a.get("CurrentBalance"), a.get("Active"), a["Id"]]
                 for a in rows])


# ============================================================== QuickBooks: drafts
def _refs():
    q = qbo()
    accts = {a["AcctNum"]: a for a in q.query("SELECT * FROM Account WHERE Active = true")
             if a.get("AcctNum")}
    classes = {c["Name"]: c["Id"] for c in q.query("SELECT * FROM Class")}
    return accts, classes


def _entity_ref(kind, key):
    """Find a customer/vendor by display name or by source ID (C00123 / V012)."""
    q = qbo()
    rows = q.query(f"SELECT * FROM {kind} WHERE Active IN (true, false)")
    for r in rows:
        if r.get("DisplayName") == key or (r.get("Notes") or "").startswith(f"FV:{key}"):
            return r["Id"], r["DisplayName"]
    raise ValueError(f"No {kind.lower()} named or tagged '{key}'")


def _save_draft(d):
    DRAFTS.mkdir(parents=True, exist_ok=True)
    (DRAFTS / f"{d['draft_id']}.json").write_text(json.dumps(d, indent=1))
    return d


def _new_id():
    return f"D{time.strftime('%m%d')}-{secrets.token_hex(2).upper()}"


def _period_check(txn_date, prior_period_adjustment):
    if txn_date <= CLOSED_THROUGH and not prior_period_adjustment:
        raise ValueError(f"{txn_date} is in a closed period (closed through {CLOSED_THROUGH}). "
                         "Date it in the open period, or set prior_period_adjustment=true if "
                         "the person has agreed to change closed books.")


def _preview_lines(lines):
    return _tsv(["account", "debit", "credit", "class", "name", "description"],
                [[l["account"], f"{l['debit']:,.2f}" if l["debit"] else "",
                  f"{l['credit']:,.2f}" if l["credit"] else "", l.get("class") or "",
                  l.get("name") or "", l.get("description") or ""] for l in lines])


@mcp.tool(annotations=_ann(False))
def qbo_draft_journal_entry(txn_date: str, memo: str, lines: list[dict],
                            doc_number: str = "", reversing_date: str = "",
                            prior_period_adjustment: bool = False) -> str:
    """Draft a journal entry (nothing is posted). Returns a draft ID and a preview.

    lines: [{"account": "6600", "debit": 20000, "class": "G&A", "description": "..."},
            {"account": "2200", "credit": 20000}]
      account: account number. class: department name (Engineering, Product, Sales,
      Marketing, Customer Success, Support, G&A, Cost of Revenue). Lines on 1100 Accounts
      Receivable need "customer" (name or source ID); lines on 2000 Accounts Payable need
      "vendor". Optional "customer"/"vendor" on other lines too.
    reversing_date: if set, a matching reversing entry is drafted for that date as well
      (typical for accruals).
    """
    _period_check(txn_date, prior_period_adjustment)
    accts, classes = _refs()
    clean, dr, cr = [], 0.0, 0.0
    for l in lines:
        a = str(l["account"]).strip()
        if a not in accts:
            raise ValueError(f"Unknown account number {a}")
        d, c = round(float(l.get("debit") or 0), 2), round(float(l.get("credit") or 0), 2)
        if (d > 0) == (c > 0) or d < 0 or c < 0:
            raise ValueError(f"Each line needs a positive debit or credit (account {a})")
        if l.get("class") and l["class"] not in classes:
            raise ValueError(f"Unknown class {l['class']}")
        entity = None
        if a == "1100" or l.get("customer"):
            if not l.get("customer"):
                raise ValueError("Lines on 1100 need a customer")
            entity = ("Customer",) + _entity_ref("Customer", l["customer"])
        elif a == "2000" or l.get("vendor"):
            if not l.get("vendor"):
                raise ValueError("Lines on 2000 need a vendor")
            entity = ("Vendor",) + _entity_ref("Vendor", l["vendor"])
        clean.append({"account": a, "account_id": accts[a]["Id"],
                      "account_name": accts[a]["Name"], "debit": d, "credit": c,
                      "class": l.get("class"), "class_id": classes.get(l.get("class")),
                      "entity": entity, "name": entity[2] if entity else None,
                      "description": l.get("description", "")})
        dr, cr = dr + d, cr + c
    if round(dr - cr, 2):
        raise ValueError(f"Entry doesn't balance: debits {dr:,.2f}, credits {cr:,.2f}")
    did = _new_id()
    drafts = [{"draft_id": did, "kind": "JournalEntry", "txn_date": txn_date, "memo": memo,
               "doc_number": doc_number or did, "lines": clean, "status": "draft",
               "prior_period_adjustment": prior_period_adjustment}]
    if reversing_date:
        _period_check(reversing_date, prior_period_adjustment)
        rev = [dict(l, debit=l["credit"], credit=l["debit"]) for l in clean]
        drafts.append({"draft_id": did + "R", "kind": "JournalEntry", "txn_date": reversing_date,
                       "memo": f"Reverse {did}: {memo}", "doc_number": did + "R", "lines": rev,
                       "status": "draft", "prior_period_adjustment": prior_period_adjustment})
    for d in drafts:
        _save_draft(d)
    out = [f"Draft {d['draft_id']} - journal entry {d['txn_date']}: {d['memo']}\n"
           f"{_preview_lines(d['lines'])}" for d in drafts]
    return "\n\n".join(out) + f"\n\nTotal {dr:,.2f}. Not posted. Post with qbo_post_draft " \
                              "after the person approves."


@mcp.tool(annotations=_ann(False))
def qbo_draft_bill(vendor: str, txn_date: str, due_date: str, vendor_invoice_number: str,
                   lines: list[dict], memo: str = "",
                   prior_period_adjustment: bool = False) -> str:
    """Draft a vendor bill (nothing is posted).

    vendor: display name or source ID (V012).
    lines: [{"account": "6700", "amount": 28400, "class": "Sales", "description": "..."}]
    """
    _period_check(txn_date, prior_period_adjustment)
    accts, classes = _refs()
    vid, vname = _entity_ref("Vendor", vendor)
    clean = []
    for l in lines:
        a = str(l["account"])
        if a not in accts:
            raise ValueError(f"Unknown account number {a}")
        if l.get("class") and l["class"] not in classes:
            raise ValueError(f"Unknown class {l['class']}")
        clean.append({"account": a, "account_id": accts[a]["Id"], "debit": round(float(l["amount"]), 2),
                      "credit": 0.0, "class": l.get("class"), "class_id": classes.get(l.get("class")),
                      "description": l.get("description", "")})
    total = round(sum(l["debit"] for l in clean), 2)
    d = _save_draft({"draft_id": _new_id(), "kind": "Bill", "vendor_id": vid, "vendor": vname,
                     "txn_date": txn_date, "due_date": due_date, "doc_number": vendor_invoice_number,
                     "memo": memo, "lines": clean, "status": "draft",
                     "prior_period_adjustment": prior_period_adjustment})
    return (f"Draft {d['draft_id']} - bill from {vname}, {txn_date}, invoice "
            f"{vendor_invoice_number}, total {total:,.2f}\n"
            f"{_preview_lines(clean + [{'account': '2000', 'debit': 0, 'credit': total, 'name': vname}])}"
            "\n\nNot posted. Post with qbo_post_draft after the person approves.")


@mcp.tool(annotations=_ann(False, destructive=True))
def qbo_draft_change(action: str, entity: str, id: str, reason: str,
                     changes: dict | None = None, prior_period_adjustment: bool = False) -> str:
    """Draft a change to an existing QuickBooks record (nothing happens until posted).

    action: "delete", "void" (Invoice, Payment, Bill payment and a few others), or "update"
      (sparse update: pass only the fields to change in `changes`, e.g.
      {"CustomerRef": {"value": "123"}, "Line": [...]}).
    Use for fixing errors found in review, e.g. deleting a duplicate bill or re-pointing a
    payment to the right customer and invoice. Records dated in a closed period are refused
    unless prior_period_adjustment=true (only when the person has agreed to change closed books).
    """
    action = action.lower()
    if action not in ("delete", "void", "update"):
        raise ValueError("action must be delete, void or update")
    cur = qbo().request("GET", f"{entity.lower()}/{id}")[entity]
    _period_check(cur.get("TxnDate", "9999-12-31"), prior_period_adjustment)
    d = _save_draft({"draft_id": _new_id(), "kind": "Change", "action": action, "entity": entity,
                     "id": id, "reason": reason, "changes": changes or {}, "status": "draft",
                     "prior_period_adjustment": prior_period_adjustment,
                     "txn_date": cur.get("TxnDate"),
                     "before": {k: cur.get(k) for k in ("TxnDate", "TotalAmt", "DocNumber",
                                                         "CustomerRef", "VendorRef", "PrivateNote")}})
    return (f"Draft {d['draft_id']} - {action} {entity} {id} ({reason}).\nCurrent record: "
            f"{json.dumps(d['before'], default=str)}\nChanges: {json.dumps(changes or {})}\n\n"
            "Not applied. Apply with qbo_post_draft after the person approves.")


@mcp.tool(annotations=_ann(True))
def qbo_list_drafts(status: str = "draft") -> str:
    """List drafts (status: draft, posted, discarded or all)."""
    if not DRAFTS.exists():
        return "No drafts."
    rows = []
    for f in sorted(DRAFTS.glob("*.json")):
        d = json.loads(f.read_text())
        if status != "all" and d["status"] != status:
            continue
        total = sum(l.get("debit", 0) for l in d.get("lines", []))
        desc = d.get("memo") or d.get("reason") or ""
        rows.append([d["draft_id"], d["status"], d["kind"], d.get("action", ""),
                     d.get("txn_date", ""), f"{total:,.2f}" if total else "", desc,
                     d.get("qbo_id", "")])
    return _tsv(["draft_id", "status", "kind", "action", "date", "amount", "description",
                 "qbo_id"], rows) if rows else "No matching drafts."


@mcp.tool(annotations=_ann(False))
def qbo_discard_draft(draft_id: str) -> str:
    """Discard a draft that should not be posted."""
    f = DRAFTS / f"{draft_id}.json"
    d = json.loads(f.read_text())
    if d["status"] != "draft":
        raise ValueError(f"Draft is already {d['status']}")
    d["status"] = "discarded"
    _save_draft(d)
    return f"Discarded {draft_id}."


@mcp.tool(annotations=_ann(False, destructive=True))
def qbo_post_draft(draft_id: str) -> str:
    """Post an approved draft to QuickBooks. Only call this after the person has explicitly
    approved this specific draft in the conversation."""
    f = DRAFTS / f"{draft_id}.json"
    if not f.exists():
        raise ValueError(f"No draft {draft_id}")
    d = json.loads(f.read_text())
    if d["status"] != "draft":
        raise ValueError(f"Draft {draft_id} is already {d['status']}")
    _period_check(d.get("txn_date") or "9999-12-31", d.get("prior_period_adjustment", False))
    q = qbo()
    note = f"{AGENT_TAG}{draft_id} | {d.get('memo') or d.get('reason') or ''}"[:4000]
    if d["kind"] == "JournalEntry":
        lines = []
        for l in d["lines"]:
            det = {"PostingType": "Debit" if l["debit"] else "Credit",
                   "AccountRef": {"value": l["account_id"]}}
            if l.get("class_id"):
                det["ClassRef"] = {"value": l["class_id"]}
            if l.get("entity"):
                det["Entity"] = {"Type": l["entity"][0], "EntityRef": {"value": l["entity"][1]}}
            lines.append({"DetailType": "JournalEntryLineDetail",
                          "Amount": l["debit"] or l["credit"],
                          "Description": l.get("description", "")[:4000],
                          "JournalEntryLineDetail": det})
        obj = q.create("JournalEntry", {"TxnDate": d["txn_date"], "DocNumber": d["doc_number"][:21],
                                        "PrivateNote": note, "Line": lines})
    elif d["kind"] == "Bill":
        lines = []
        for l in d["lines"]:
            det = {"AccountRef": {"value": l["account_id"]}}
            if l.get("class_id"):
                det["ClassRef"] = {"value": l["class_id"]}
            lines.append({"DetailType": "AccountBasedExpenseLineDetail", "Amount": l["debit"],
                          "Description": l.get("description", "")[:4000],
                          "AccountBasedExpenseLineDetail": det})
        obj = q.create("Bill", {"VendorRef": {"value": d["vendor_id"]}, "TxnDate": d["txn_date"],
                                "DueDate": d["due_date"], "DocNumber": d["doc_number"][:21],
                                "PrivateNote": note, "Line": lines})
    else:
        cur = q.request("GET", f"{d['entity'].lower()}/{d['id']}")[d["entity"]]
        base = {"Id": cur["Id"], "SyncToken": cur["SyncToken"]}
        if d["action"] == "delete":
            obj = q.request("POST", d["entity"].lower(), base,
                            params={"operation": "delete"}).get(d["entity"], base)
        elif d["action"] == "void":
            obj = q.request("POST", d["entity"].lower(), base,
                            params={"operation": "void"}).get(d["entity"], base)
        else:
            body = dict(base, sparse=True, **d["changes"])
            prev = cur.get("PrivateNote") or ""
            body.setdefault("PrivateNote", f"{prev} | {note}"[:4000])
            obj = q.update(d["entity"], body)
    d.update(status="posted", qbo_id=obj.get("Id"), posted_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    _save_draft(d)
    return f"Posted {draft_id} to QuickBooks (Id {obj.get('Id')})."


# ============================================================== source systems
def _src():
    return sqlite3.connect(f"file:{SOURCE_DB.as_posix()}?mode=ro", uri=True)


@mcp.tool(annotations=_ann(True))
def source_tables() -> str:
    """List the source-system tables (CRM, billing, Stripe, payroll, spend, bank, plan) with
    what each holds, row counts and columns. Start here before writing source_query SQL."""
    from generator.docs import GROUPS
    con = _src()
    out = []
    for title, tables in GROUPS:
        out.append(f"## {title}")
        for name, desc in tables.items():
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({name})")]
            n = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            out.append(f"{name} ({n:,} rows): {desc}\n  columns: {', '.join(cols)}")
    return "\n".join(out)


@mcp.tool(annotations=_ann(True))
def source_query(sql: str, max_rows: int = 500) -> str:
    """Run a read-only SQLite query against the source systems and return a tab-separated
    table. Dates are ISO text (YYYY-MM-DD). Example:
      SELECT posted_date, amount, description FROM bank_transactions
      WHERE account_id = 'BA-OPER' AND posted_date BETWEEN '2026-10-01' AND '2026-10-31'
    """
    s = sql.strip().rstrip(";")
    if not re.match(r"(?is)^(select|with)\s", s) or ";" in s:
        raise ValueError("Only a single SELECT (or WITH ... SELECT) query is allowed.")
    con = _src()
    cur = con.execute(s)
    rows = cur.fetchmany(max(1, min(max_rows, 5000)))
    more = cur.fetchone() is not None
    text = _tsv([c[0] for c in cur.description], rows)
    if more:
        text += f"\n... more rows not shown (limit {max_rows}); aggregate or filter."
    return _trim(text)


@mcp.tool(annotations=_ann(True))
def legacy_pl_history(start_month: str = "2022-01", end_month: str = "2024-10") -> str:
    """Monthly P&L by account and class from before QuickBooks (Jan 2022 to Oct 2024), from the
    legacy system. amount is in the account's natural sign (revenue positive)."""
    con = sqlite3.connect(f"file:{BOOKS_DB.as_posix()}?mode=ro", uri=True)
    rows = con.execute("""SELECT month, account_number, account_name, class, amount
                          FROM legacy_pl_monthly WHERE month BETWEEN ? AND ?
                          ORDER BY month, account_number, class""",
                       (start_month, end_month)).fetchall()
    return _trim(_tsv(["month", "account", "name", "class", "amount"], rows))


def main():
    mcp.run()


if __name__ == "__main__":
    main()
