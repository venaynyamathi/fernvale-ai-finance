"""The loader's steps: check, clean, setup, load, verify, close."""
import json
import sqlite3
import time
from collections import defaultdict
from datetime import date

from .client import WORK, QBOError, log
from .plan import BOOKS, ITEMS, TAG, Planner, ref

STATE = WORK / "state.json"
BOOKS_START = "2024-11-01"
LAST_CLOSED = "2026-09-30"
VERIFY_DATES = ["2024-12-31", "2025-12-31", "2026-09-30", "2026-10-31"]
SAMPLE_TXN_TYPES = ["Deposit", "Payment", "BillPayment", "RefundReceipt", "SalesReceipt",
                    "CreditMemo", "Invoice", "Estimate", "VendorCredit", "Bill", "Purchase",
                    "PurchaseOrder", "Transfer", "JournalEntry", "TimeActivity"]
SYSTEM_SUBTYPES = {"AccountsReceivable", "AccountsPayable", "UndepositedFunds",
                   "RetainedEarnings", "OpeningBalanceEquity"}
BATCH_SIZE = 30
BATCH_GAP = 1.6          # seconds between batch calls (QuickBooks allows ~40 a minute)


# ---------------------------------------------------------------------- state
def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"accounts": {}, "classes": {}, "items": {}, "customers": {}, "vendors": {},
            "docs": {}, "warnings": [], "open_item_fallback": False}


def save_state(st):
    WORK.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(STATE)


def resolve(x, st, key):
    maps = {"acct": st["accounts"], "class": st["classes"], "item": st["items"],
            "cust": st["customers"], "vend": st["vendors"]}
    if isinstance(x, dict):
        return {k: resolve(v, st, key) for k, v in x.items()}
    if isinstance(x, list):
        return [resolve(v, st, key) for v in x]
    if isinstance(x, str) and x.startswith("@"):
        kind, val = x[1:].split(":", 1)
        if kind == "doc":
            d = st["docs"].get(val)
            if not d or "id" not in d:
                raise KeyError(f"{key}: needs {val}, which hasn't been created")
            return d["id"]
        if val not in maps[kind]:
            raise KeyError(f"{key}: no QuickBooks record for {kind} {val} (run setup first)")
        return maps[kind][val]
    return x


def fault_text(fault):
    if not fault:
        return ""
    errs = fault.get("Error", [])
    return "; ".join(f"{e.get('code')}: {e.get('Message')} - {e.get('Detail')}" for e in errs) \
        or json.dumps(fault)


# ---------------------------------------------------------------------- check
def check(q):
    info = q.request("GET", f"companyinfo/{q.realm}")["CompanyInfo"]
    log(f"Connected to '{info.get('CompanyName')}' (realm {q.realm}).")
    prefs = q.request("GET", "preferences")["Preferences"]
    acc, sales = prefs.get("AccountingInfoPrefs", {}), prefs.get("SalesFormsPrefs", {})
    # Read-only on purpose: QuickBooks treats a settings update as a full replace, so
    # writing even one setting resets the others. People change these in the UI.
    acc, sales = prefs.get("AccountingInfoPrefs", {}), prefs.get("SalesFormsPrefs", {})
    problems = []
    if not acc.get("UseAccountNumbers"):
        problems.append("Settings > Account and settings > Advanced > Chart of accounts: "
                        "turn ON 'Enable account numbers'")
    if not acc.get("ClassTrackingPerTxnLine"):
        problems.append("Settings > Account and settings > Advanced > Categories: turn ON "
                        "'Track classes' and choose 'One to each row in transaction'")
    if not sales.get("CustomTxnNumbers"):
        problems.append("Settings > Account and settings > Sales > Sales form content: turn ON "
                        "'Custom transaction numbers'")
    if sales.get("AutoApplyCredit"):
        problems.append("Settings > Account and settings > Advanced > Automation: turn OFF "
                        "'Automatically apply credits'")
    counts = {}
    for t in SAMPLE_TXN_TYPES:
        try:
            rows = q.query(f"SELECT * FROM {t}")
        except QBOError:
            continue
        n = sum(1 for r in rows if not (r.get("PrivateNote") or "").startswith(TAG))
        if n:
            counts[t] = n
    log("Sample (non-Fernvale) transactions in the company: " +
        (", ".join(f"{k} {v}" for k, v in counts.items()) or "none"))
    st = load_state()
    log(f"Fernvale records already loaded: {len(st['docs'])} transactions, "
        f"{len(st['accounts'])} accounts, {len(st['customers'])} customers")
    if problems:
        log("ACTION NEEDED in QuickBooks before loading:\n  - " + "\n  - ".join(problems))
        return False
    log("Settings OK.")
    return True


# ---------------------------------------------------------------------- clean
def clean(q, assume_yes=False):
    remaining = 0
    for t in SAMPLE_TXN_TYPES:
        try:
            remaining += sum(1 for r in q.query(f"SELECT * FROM {t}")
                             if not (r.get("PrivateNote") or "").startswith(TAG))
        except QBOError:
            pass
    if not remaining:
        log("Clean: no sample transactions left, skipping.")
        return
    if not assume_yes:
        print("\nThis permanently deletes Intuit's SAMPLE transactions from the sandbox company\n"
              "and makes the sample customers, vendors, products and unused accounts inactive.\n"
              "Fernvale records (tagged FV:) are never touched.")
        if input("Type DELETE SAMPLE to continue: ").strip() != "DELETE SAMPLE":
            log("Clean skipped.")
            return
    for t in SAMPLE_TXN_TYPES:
        try:
            rows = q.query(f"SELECT * FROM {t}")
        except QBOError as e:
            log(f"  {t}: can't query ({e.status}), skipping")
            continue
        rows = [r for r in rows if not (r.get("PrivateNote") or "").startswith(TAG)]
        if not rows:
            continue
        failed = 0
        for i in range(0, len(rows), BATCH_SIZE):
            chunk = rows[i:i + BATCH_SIZE]
            res = q.batch([(str(n), "delete", t, {"Id": r["Id"], "SyncToken": r["SyncToken"]})
                           for n, r in enumerate(chunk)])
            failed += sum(1 for _, f in res.values() if f)
            time.sleep(BATCH_GAP)
        log(f"  {t}: deleted {len(rows) - failed} sample records" +
            (f", {failed} could not be deleted" if failed else ""))
    for t, tagfield in (("Customer", "Notes"), ("Vendor", "Notes"), ("Item", "Description")):
        rows = [r for r in q.query(f"SELECT * FROM {t} WHERE Active = true")
                if not (r.get(tagfield) or "").startswith(TAG)]
        failed = 0
        for i in range(0, len(rows), BATCH_SIZE):
            chunk = rows[i:i + BATCH_SIZE]
            items = []
            for n, r in enumerate(chunk):
                body = {"Id": r["Id"], "SyncToken": r["SyncToken"], "sparse": True,
                        "Active": False}
                if t == "Item":
                    body["Name"] = r["Name"]
                items.append((str(n), "update", t, body))
            res = q.batch(items)
            failed += sum(1 for _, f in res.values() if f)
            time.sleep(BATCH_GAP)
        log(f"  {t}: made {len(rows) - failed} sample records inactive" +
            (f" ({failed} refused; harmless)" if failed else ""))
    st = load_state()
    ours = set(st["accounts"].values())
    rows = [r for r in q.query("SELECT * FROM Account WHERE Active = true")
            if r["Id"] not in ours and r.get("AccountSubType") not in SYSTEM_SUBTYPES
            and not (r.get("Description") or "").startswith(TAG)
            and abs(float(r.get("CurrentBalance", 0) or 0)) < 0.005]
    done = 0
    for r in rows:
        try:
            q.update("Account", {"Id": r["Id"], "SyncToken": r["SyncToken"], "sparse": True,
                                 "Name": r["Name"], "Active": False})
            done += 1
        except QBOError:
            pass
    log(f"  Account: made {done} unused sample accounts inactive")


# ---------------------------------------------------------------------- setup
def _create_account(q, body, a):
    """Create an account, retrying the ways QuickBooks most often objects."""
    attempts = [dict(body)]
    no_sub = {k: v for k, v in body.items() if k != "AccountSubType"}
    attempts.append(no_sub)
    errors = []
    for b in attempts:
        try:
            return q.create("Account", b)
        except QBOError as e:
            errors.append(str(e))
            log(f"  account {a['number']}: QuickBooks said: {str(e)[:400]}")
    # A same-named account may exist that our first search didn't return (or QuickBooks
    # reserves the name). Find it and take it over.
    for x in q.query("SELECT * FROM Account WHERE Active IN (true, false)"):
        if x["Name"].lower() == body["Name"].lower() or x.get("AcctNum") == body["AcctNum"]:
            try:
                return q.update("Account", {"Id": x["Id"], "SyncToken": x["SyncToken"],
                                            "sparse": True, "Active": True,
                                            "Name": body["Name"], "AcctNum": body["AcctNum"],
                                            "Description": body["Description"]})
            except QBOError as e:
                errors.append(str(e))
    # last resort: a distinct name
    try:
        return q.create("Account", dict(no_sub, Name=f"{body['Name']} (FV)"))
    except QBOError as e:
        errors.append(str(e))
    raise QBOError(f"Could not create account {a['number']} {a['name']}:\n  " +
                   "\n  ".join(errors))


def setup(q):
    st = load_state()
    p = Planner()
    con = sqlite3.connect(BOOKS)
    ours = [dict(zip(["number", "name", "type", "subtype"], r)) for r in con.execute(
        "SELECT account_number, name, qbo_account_type, qbo_account_subtype FROM accounts "
        "ORDER BY account_number")]

    # accounts
    existing = q.query("SELECT * FROM Account WHERE Active IN (true, false)")
    taken = set(st["accounts"].values())
    special = {"1100": lambda a: a["AccountType"] == "Accounts Receivable",
               "2000": lambda a: a["AccountType"] == "Accounts Payable",
               "3900": lambda a: a.get("AccountSubType") == "RetainedEarnings"}
    for a in ours:
        if a["number"] in st["accounts"]:
            continue
        match = None
        if a["number"] in special:
            match = next((x for x in existing if special[a["number"]](x)
                          and x["Id"] not in taken), None)
        if not match:
            same = next((x for x in existing if x["Name"] == a["name"] and x["Id"] not in taken),
                        None)
            if same and same["AccountType"] == a["type"] and \
                    same.get("AccountSubType") not in SYSTEM_SUBTYPES:
                match = same
            elif same:
                q.update("Account", {"Id": same["Id"], "SyncToken": same["SyncToken"],
                                     "sparse": True, "Name": f"{same['Name']} (sample)"})
        if match:
            body = {"Id": match["Id"], "SyncToken": match["SyncToken"], "sparse": True,
                    "Name": a["name"], "AcctNum": a["number"], "Active": True,
                    "Description": f"{TAG} Fernvale account {a['number']}"}
            obj = q.update("Account", body)
            log(f"  account {a['number']} {a['name']}: using existing QuickBooks account")
        else:
            body = {"Name": a["name"], "AcctNum": a["number"], "AccountType": a["type"],
                    "AccountSubType": a["subtype"],
                    "Description": f"{TAG} Fernvale account {a['number']}"}
            obj = _create_account(q, body, a)
            log(f"  account {a['number']} {a['name']}: created")
        st["accounts"][a["number"]] = obj["Id"]
        taken.add(obj["Id"])
        save_state(st)

    # classes
    existing = {c["Name"]: c for c in q.query("SELECT * FROM Class WHERE Active IN (true, false)")}
    for c in p.classes:
        if c in st["classes"]:
            continue
        obj = existing.get(c) or q.create("Class", {"Name": c})
        st["classes"][c] = obj["Id"]
    save_state(st)
    log(f"  {len(st['classes'])} classes ready")

    # items
    existing = {i["Name"]: i for i in q.query("SELECT * FROM Item WHERE Active IN (true, false)")}
    for k, (name, acct) in ITEMS.items():
        if k in st["items"]:
            continue
        body = {"Name": name, "Type": "Service", "Taxable": False,
                "IncomeAccountRef": {"value": st["accounts"][acct]},
                "Description": f"{TAG} Fernvale item {k}"}
        if name in existing:
            ex = existing[name]
            obj = q.update("Item", {"Id": ex["Id"], "SyncToken": ex["SyncToken"], "sparse": True,
                                    "Active": True, **body})
        else:
            try:
                obj = q.create("Item", body)
            except QBOError as e:
                if k != "OPEN":
                    raise
                # QuickBooks may refuse an item that posts to a balance sheet account. Fall back
                # to subscription revenue plus a reclass entry on the same date.
                log(f"  item {name}: QuickBooks refused account 1999 ({e.status}); using "
                    "4000 plus a reclass journal entry instead")
                body["IncomeAccountRef"] = {"value": st["accounts"]["4000"]}
                obj = q.create("Item", body)
                st["open_item_fallback"] = True
        st["items"][k] = obj["Id"]
    save_state(st)
    log(f"  {len(st['items'])} items ready")

    # customers and vendors
    for entity, rows, key in (("Customer", p.customers(), "customers"),
                              ("Vendor", p.vendors(), "vendors")):
        existing = {r["DisplayName"]: r for r in
                    q.query(f"SELECT * FROM {entity} WHERE Active IN (true, false)")}
        todo = []
        for r in rows:
            if r["id"] in st[key]:
                continue
            ex = existing.get(r["name"])
            if ex:
                if not ex.get("Active", True):
                    q.update(entity, {"Id": ex["Id"], "SyncToken": ex["SyncToken"],
                                      "sparse": True, "Active": True})
                st[key][r["id"]] = ex["Id"]
                continue
            body = {"DisplayName": r["name"], "CompanyName": r["name"],
                    "Notes": f"{TAG}{r['id']}"}
            if entity == "Customer":
                body["Notes"] += f" segment={r['segment']} pays_by={r['payment_method']}"
                if r.get("email"):
                    body["PrimaryEmailAddr"] = {"Address": r["email"]}
                if r.get("state"):
                    body["BillAddr"] = {"CountrySubDivisionCode": r["state"], "Country": "US"}
            todo.append((r["id"], body))
        for i in range(0, len(todo), BATCH_SIZE):
            chunk = todo[i:i + BATCH_SIZE]
            res = q.batch([(rid, "create", entity, body) for rid, body in chunk])
            for rid, (obj, fault) in res.items():
                if fault:
                    raise QBOError(f"Creating {entity} {rid} failed: {fault_text(fault)}")
                st[key][rid] = obj["Id"]
            save_state(st)
            time.sleep(BATCH_GAP)
        log(f"  {len(st[key])} {key} ready")
    log("Setup complete.")


# ---------------------------------------------------------------------- load
def load(q, limit=None):
    st = load_state()
    ops = Planner().build()
    if st.get("open_item_fallback"):
        total = round(sum(o["payload"]["Line"][0]["Amount"] for o in ops
                          if o["key"].startswith("OPENAR:")), 2)
        last = max(i for i, o in enumerate(ops) if o["key"].startswith("OPENAR:"))
        ops.insert(last + 1, {
            "key": "OPENAR-RECLASS", "entity": "JournalEntry", "deps": [], "optional": False,
            "fallback": None,
            "expect": [], "payload": {
                "TxnDate": "2024-10-31", "DocNumber": "OPENING-AR-RCL",
                "PrivateNote": f"{TAG}OPENAR-RECLASS | Move opening invoices to conversion clearing",
                "Line": [
                    {"DetailType": "JournalEntryLineDetail", "Amount": total,
                     "JournalEntryLineDetail": {"PostingType": "Debit",
                                                "AccountRef": ref("acct", "4000")}},
                    {"DetailType": "JournalEntryLineDetail", "Amount": total,
                     "JournalEntryLineDetail": {"PostingType": "Credit",
                                                "AccountRef": ref("acct", "1999")}}]}})
    todo = [o for o in ops if o["key"] not in st["docs"]]
    if limit:
        todo = todo[:limit]
    log(f"Loading {len(todo)} transactions ({len(st['docs'])} of {len(ops)} already done).")
    batch, in_batch, sent, started = [], set(), 0, time.time()
    progress = {"last": 0}

    def flush():
        nonlocal batch, in_batch, sent
        if not batch:
            return
        res = q.batch([(o["key"], "create", o["entity"], body) for o, body in batch])
        errors, retry = [], []
        for o, _ in batch:
            obj, fault = res.get(o["key"], (None, {"Error": [{"Message": "no response"}]}))
            if obj and not fault:
                st["docs"][o["key"]] = {"id": obj["Id"], "entity": o["entity"]}
            elif o.get("fallback") and not o.get("_fell_back"):
                # e.g. QuickBooks refuses a deposit with a fee line: post the same debits and
                # credits as a journal entry instead
                retry.append(o)
                pref = st.setdefault("use_journal_for", [])
                if o["entity"] not in pref:
                    pref.append(o["entity"])
                    st["warnings"].append(
                        f"QuickBooks refused a {o['entity']} ({fault_text(fault)}). "
                        f"{o['entity']} records from {o['key']} on are loaded as journal "
                        "entries with the same debits and credits.")
                    log(f"  {o['entity']} refused ({fault_text(fault)}); loading these as "
                        "journal entries instead")
            elif o["optional"]:
                st["docs"][o["key"]] = {"skipped": True, "entity": o["entity"]}
                st["warnings"].append(f"{o['key']}: {fault_text(fault)}")
                log(f"  warning (not fatal) {o['key']}: {fault_text(fault)}")
            else:
                errors.append({"key": o["key"], "entity": o["entity"],
                               "error": fault_text(fault), "payload": o["payload"]})
        save_state(st)
        sent += len(batch)
        batch, in_batch = [], set()
        if errors:
            (WORK / "load_errors.json").write_text(json.dumps(errors, indent=1))
            for e in errors[:5]:
                log(f"  ERROR {e['key']} ({e['entity']}): {e['error']}")
            raise SystemExit(f"Stopped: {len(errors)} records failed. Details in "
                             ".qbo/load_errors.json. Fix and rerun 'load'; finished records "
                             "are skipped.")
        if sent - progress["last"] >= 300:
            progress["last"] = sent
            mins = (time.time() - started) / 60
            log(f"  {sent}/{len(todo)} loaded, {mins:.1f} min so far")
        time.sleep(BATCH_GAP)
        for o in retry:
            je = dict(o, entity="JournalEntry", payload=o["fallback"], _fell_back=True)
            batch.append((je, resolve(je["payload"], st, je["key"])))
            in_batch.add(je["key"])

    for o in todo:
        if o.get("fallback") and o["entity"] in st.get("use_journal_for", []):
            o = dict(o, entity="JournalEntry", payload=o["fallback"], _fell_back=True)
        if any(d in in_batch for d in o["deps"]) or len(batch) >= BATCH_SIZE:
            flush()
        try:
            body = resolve(o["payload"], st, o["key"])
        except KeyError as e:
            if o["optional"]:
                st["docs"][o["key"]] = {"skipped": True, "entity": o["entity"]}
                st["warnings"].append(str(e))
                continue
            flush()
            body = resolve(o["payload"], st, o["key"])
        batch.append((o, body))
        in_batch.add(o["key"])
    flush()
    flush()          # journal-entry retries queued by the last batch
    skipped = sum(1 for d in st["docs"].values() if d.get("skipped"))
    log(f"Load complete: {len(st['docs']) - skipped} transactions in QuickBooks"
        + (f", {skipped} optional links skipped (see warnings)" if skipped else "") + ".")


# ---------------------------------------------------------------------- verify
def expected_tb(d):
    """What QuickBooks' trial balance (Jan 1 to d) should show, by our account number."""
    con = sqlite3.connect(BOOKS)
    stmt = dict(con.execute("SELECT account_number, statement FROM accounts"))
    y0 = max(f"{d[:4]}-01-01", BOOKS_START)
    out = defaultdict(float)
    for a, v in con.execute("""SELECT l.account_number, SUM(l.debit - l.credit) FROM gl_lines l
                               JOIN gl_entries e USING (je_id) WHERE e.txn_date <= ?
                               GROUP BY 1""", (d,)):
        if stmt[a] == "BS":
            out[a] += v
    for a, v, early in con.execute("""SELECT l.account_number, SUM(l.debit - l.credit),
                                      e.txn_date < ? FROM gl_lines l JOIN gl_entries e
                                      USING (je_id) JOIN accounts a USING (account_number)
                                      WHERE a.statement != 'BS' AND e.txn_date <= ?
                                      GROUP BY 1, 3""", (y0, d)):
        if early:
            out["3900"] += v          # prior years sit in retained earnings
        else:
            out[a] += v
    out["1999"] += 0.0
    return {a: round(v, 2) for a, v in out.items()}


def parse_tb(report):
    rows = {}

    def walk(node):
        for r in node.get("Row", []) if isinstance(node, dict) else []:
            if "Rows" in r:
                walk(r["Rows"])
            cols = r.get("ColData")
            if cols and r.get("type") != "Section" and cols[0].get("id"):
                num = lambda s: float(s.replace(",", "")) if s not in ("", None) else 0.0
                rows[cols[0]["id"]] = (cols[0].get("value"),
                                       round(num(cols[1].get("value")) -
                                             num(cols[2].get("value")), 2))
    walk(report.get("Rows", {}))
    return rows


def verify(q):
    st = load_state()
    by_id = {v: k for k, v in st["accounts"].items()}
    con = sqlite3.connect(BOOKS)
    names = dict(con.execute("SELECT account_number, name FROM accounts"))
    lines = ["# QuickBooks load verification", "",
             f"Run {time.strftime('%Y-%m-%d %H:%M')}. Compares QuickBooks' trial balance with "
             "the Fernvale ledger (build/books_as_booked.sqlite).", ""]
    all_ok, other = True, {}
    for d in VERIFY_DATES:
        rep = q.report("TrialBalance", {"start_date": f"{d[:4]}-01-01", "end_date": d,
                                        "accounting_method": "Accrual"})
        got_raw = parse_tb(rep)
        got = defaultdict(float)
        for qid, (name, v) in got_raw.items():
            if qid in by_id:
                got[by_id[qid]] += v
            elif abs(v) >= 0.01:
                other[name] = v
        want = expected_tb(d)
        bad = [(a, want.get(a, 0.0), round(got.get(a, 0.0), 2))
               for a in sorted(set(want) | set(got))
               if abs(want.get(a, 0.0) - got.get(a, 0.0)) >= 0.01]
        ok = not bad
        all_ok &= ok
        lines += [f"## Trial balance at {d}: {'PASS' if ok else 'DIFFERENCES'}", ""]
        if bad:
            lines += ["| Account | Ledger | QuickBooks | Difference |", "|---|---:|---:|---:|"]
            for a, w, g in bad:
                lines.append(f"| {a} {names.get(a, '')} | {w:,.2f} | {g:,.2f} | {g - w:,.2f} |")
        else:
            lines.append(f"All {len(want)} Fernvale accounts match to the cent.")
        lines.append("")
    if other:
        lines += ["## Non-Fernvale accounts with balances (left over from sample data)", "",
                  "| Account | Balance |", "|---|---:|"] + \
                 [f"| {n} | {v:,.2f} |" for n, v in sorted(other.items())] + [""]
    if st["warnings"]:
        lines += ["## Warnings", ""] + [f"- {w}" for w in st["warnings"]] + [""]
    (WORK / "verify_report.md").write_text("\n".join(lines), encoding="utf-8")
    log(("VERIFIED: QuickBooks matches the ledger on every date." if all_ok else
         "Differences found.") + " Report: .qbo/verify_report.md")
    return all_ok


# ---------------------------------------------------------------------- close
def close(q):
    """Setting the closing date through the API rewrites all company settings, so this is a
    one-minute manual step."""
    log("Last step, in QuickBooks: Settings > Account and settings > Advanced > Accounting > "
        f"Close the books: turn it on, closing date {LAST_CLOSED}, then Save. October 2026 "
        "stays open for the close.")
