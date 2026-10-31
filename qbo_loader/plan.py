"""
Turns the ledger in build/books_as_booked.sqlite into an ordered list of QuickBooks
operations. Pure Python, no network: this is the part that can be tested offline.

Each operation is a dict:
    key      unique id of the record we create (used for resuming and linking)
    entity   QuickBooks entity name (Invoice, Payment, Bill, JournalEntry, ...)
    payload  the JSON body, with symbolic references that the loader resolves at load time:
               "@acct:4000"  "@class:Sales"  "@cust:C00100"  "@vend:V008"  "@item:SUB"
               "@doc:<key>"  (the QuickBooks Id of a record created earlier)
    deps     keys this operation needs to exist first
    optional True when a failure should be logged but not stop the load (linking only)
    expect   the debit/credit lines the record should post, for offline testing
"""
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "build" / "books_as_booked.sqlite"
SOURCE = ROOT / "data" / "source_systems.sqlite"

TAG = "FV:"            # every record we create carries this at the start of its PrivateNote
ITEMS = {              # item key -> (QuickBooks name, income account)
    "SUB": ("Fernvale Flow Subscription", "4000"),
    "SVC": ("Fernvale Professional Services", "4100"),
    "OPEN": ("Conversion - Opening Balance", "1999"),
}
INCOME_ITEM = {"4000": "SUB", "4100": "SVC"}
BANK_ACCOUNTS = {"1000", "1010", "1050"}


def ref(kind, key):
    return {"value": f"@{kind}:{key}"}


def r2(x):
    return round(float(x) + 1e-9, 2)


def note(key, ref_text, memo):
    text = f"{TAG}{key} {ref_text or ''} | {memo or ''}".strip()
    return text[:4000]


class Planner:
    def __init__(self, books=BOOKS, source=SOURCE):
        self.b = sqlite3.connect(books)
        self.s = sqlite3.connect(source)
        self.accounts = {r[0]: {"number": r[0], "name": r[1], "type": r[2], "subtype": r[3]}
                         for r in self.b.execute("SELECT account_number, name, qbo_account_type, "
                                                 "qbo_account_subtype FROM accounts")}
        self.classes = [r[0] for r in self.b.execute("SELECT class FROM classes")]
        self.inv_num = dict(self.s.execute("SELECT invoice_id, invoice_number FROM billing_invoices"))
        self.inv_cust = dict(self.s.execute("SELECT invoice_number, customer_id FROM billing_invoices"))
        self.pay_inv = {pid: self.inv_num[iid] for pid, iid in
                        self.s.execute("SELECT payment_id, invoice_id FROM billing_payments")}
        self.bill_info = {r[0]: {"vendor_id": r[1], "invoice_number": r[2], "due_date": r[3]}
                          for r in self.s.execute("SELECT bill_id, vendor_id, invoice_number, "
                                                  "due_date FROM spend_bills")}
        self.ops = []
        self.doc_alias = {}       # "INV:FV-10001" / "BILL:BILL-00012" -> op key

    # ------------------------------------------------------------------ lists
    def customers(self):
        ids = {r[0] for r in self.b.execute(
            "SELECT DISTINCT customer_id FROM gl_lines_to_load WHERE customer_id IS NOT NULL")}
        ids |= {r[0] for r in self.b.execute("SELECT customer_id FROM open_ar_at_conversion")}
        rows = self.s.execute("SELECT customer_id, name, billing_email, state, segment, "
                              "payment_method FROM billing_customers").fetchall()
        return [{"id": r[0], "name": r[1], "email": r[2], "state": r[3], "segment": r[4],
                 "payment_method": r[5]} for r in rows if r[0] in ids]

    def vendors(self):
        ids = {r[0] for r in self.b.execute(
            "SELECT DISTINCT vendor_id FROM gl_lines_to_load WHERE vendor_id IS NOT NULL")}
        ids |= {r[0] for r in self.b.execute("SELECT vendor_id FROM open_ap_at_conversion")}
        rows = self.s.execute("SELECT vendor_id, name, category, payment_terms_days "
                              "FROM spend_vendors").fetchall()
        return [{"id": r[0], "name": r[1], "category": r[2], "terms": r[3]}
                for r in rows if r[0] in ids]

    # ------------------------------------------------------------------ helpers
    def add(self, key, entity, payload, deps=(), optional=False, expect=None, alias=None,
            fallback=None):
        self.ops.append({"key": key, "entity": entity, "payload": payload, "deps": list(deps),
                         "optional": optional, "expect": expect or [], "fallback": fallback})
        if alias:
            self.doc_alias[alias] = key

    def je_lines(self, lines, desc_default=""):
        out = []
        for l in lines:
            amt = l["debit"] or l["credit"]
            det = {"PostingType": "Debit" if l["debit"] else "Credit",
                   "AccountRef": ref("acct", l["account_number"])}
            if l["class"]:
                det["ClassRef"] = ref("class", l["class"])
            acct = l["account_number"]
            if acct == "1100" or (l["customer_id"] and not l["vendor_id"] and acct != "2000"):
                det["Entity"] = {"Type": "Customer", "EntityRef": ref("cust", l["customer_id"])}
            elif l["vendor_id"]:
                det["Entity"] = {"Type": "Vendor", "EntityRef": ref("vend", l["vendor_id"])}
            out.append({"DetailType": "JournalEntryLineDetail", "Amount": r2(amt),
                        "Description": (l["description"] or desc_default)[:4000],
                        "JournalEntryLineDetail": det})
        return out

    @staticmethod
    def expect_of(lines):
        return [(l["account_number"], r2(l["debit"]), r2(l["credit"])) for l in lines]

    # ------------------------------------------------------------------ conversion
    def plan_conversion(self):
        je = [dict(zip(["account_number", "debit", "credit", "description"], r)) for r in
              self.b.execute("SELECT account_number, debit, credit, description "
                             "FROM opening_journal_entry ORDER BY line_no")]
        for l in je:
            l.update({"class": None, "customer_id": None, "vendor_id": None})
        self.add("OPENING-JE", "JournalEntry", {
            "TxnDate": "2024-10-31", "DocNumber": "OPENING-2024",
            "PrivateNote": note("OPENING-JE", "Opening balances", "Conversion to QuickBooks at "
                                "Oct 31, 2024. Prior P&L rolled into retained earnings."),
            "Line": self.je_lines(je)}, expect=self.expect_of(je))
        for num, cust, d, due, amt in self.b.execute(
                "SELECT invoice_number, customer_id, invoice_date, due_date, open_amount "
                "FROM open_ar_at_conversion"):
            key = f"OPENAR:{num}"
            self.add(key, "Invoice", {
                "TxnDate": d, "DueDate": due, "DocNumber": num, "CustomerRef": ref("cust", cust),
                "PrivateNote": note(key, num, "Open invoice at conversion (Oct 31, 2024)"),
                "Line": [{"DetailType": "SalesItemLineDetail", "Amount": r2(amt),
                          "Description": f"Opening balance - invoice {num} open at conversion",
                          "SalesItemLineDetail": {"ItemRef": ref("item", "OPEN"),
                                                  "Qty": 1, "UnitPrice": r2(amt),
                                                  "TaxCodeRef": {"value": "NON"}}}]},
                expect=[("1100", r2(amt), 0.0), ("1999", 0.0, r2(amt))], alias=f"INV:{num}")
        for bill_id, num, vend, d, due, amt in self.b.execute(
                "SELECT bill_id, invoice_number, vendor_id, invoice_date, due_date, open_amount "
                "FROM open_ap_at_conversion"):
            key = f"OPENAP:{bill_id}"
            self.add(key, "Bill", {
                "TxnDate": d, "DueDate": due, "DocNumber": num[:21],
                "VendorRef": ref("vend", vend),
                "PrivateNote": note(key, bill_id, "Open bill at conversion (Oct 31, 2024)"),
                "Line": [{"DetailType": "AccountBasedExpenseLineDetail", "Amount": r2(amt),
                          "Description": f"Opening balance - bill {num} open at conversion",
                          "AccountBasedExpenseLineDetail": {"AccountRef": ref("acct", "1999")}}]},
                expect=[("1999", r2(amt), 0.0), ("2000", 0.0, r2(amt))], alias=f"BILL:{bill_id}")

    # ------------------------------------------------------------------ transactions
    def plan_transactions(self):
        lines = defaultdict(list)
        cols = ["je_id", "line_no", "account_number", "debit", "credit", "class", "customer_id",
                "vendor_id", "description"]
        for r in self.b.execute(f"SELECT {', '.join(cols)} FROM gl_lines_to_load "
                                "ORDER BY je_id, line_no"):
            lines[r[0]].append(dict(zip(cols, r)))
        entries = self.b.execute("SELECT je_id, txn_date, doc_type, source_ref, memo "
                                 "FROM gl_entries_to_load").fetchall()
        for je_id, d, doc, src, memo in entries:
            ls = lines[je_id]
            handler = {
                "Invoice": self._invoice, "Invoice Void": self._void, "Payment": self._payment,
                "Refund Receipt": self._refund, "Bill": self._bill,
                "Bill Payment": self._bill_payment, "Expense": self._expense,
                "Deposit": self._deposit, "Transfer": self._transfer,
            }.get(doc, self._journal)
            handler(je_id, d, src, memo, ls)

    def _base(self, je_id, d, src, memo):
        return {"TxnDate": d, "PrivateNote": note(je_id, src, memo)}

    def _invoice(self, je_id, d, src, memo, ls):
        ar = [l for l in ls if l["account_number"] == "1100"]
        cust = ar[0]["customer_id"]
        p = self._base(je_id, d, src, memo)
        p.update({"DocNumber": src[:21], "CustomerRef": ref("cust", cust), "Line": []})
        for l in ls:
            if l["account_number"] == "1100":
                continue
            amt = r2(l["credit"] - l["debit"])
            det = {"ItemRef": ref("item", INCOME_ITEM[l["account_number"]]), "Qty": 1,
                   "UnitPrice": amt, "TaxCodeRef": {"value": "NON"}}
            if l["class"]:
                det["ClassRef"] = ref("class", l["class"])
            p["Line"].append({"DetailType": "SalesItemLineDetail", "Amount": amt,
                              "Description": (l["description"] or "")[:4000],
                              "SalesItemLineDetail": det})
        self.add(je_id, "Invoice", p, expect=self.expect_of(ls), alias=f"INV:{src}")

    def _void(self, je_id, d, src, memo, ls):
        """Our ledger reverses the invoice on the void date. A QuickBooks void would erase it
        from its original month, so use a credit memo dated the void date, then link it to
        the invoice with a $0 payment so the invoice shows as closed."""
        ar = [l for l in ls if l["account_number"] == "1100"][0]
        cust, amt = ar["customer_id"], r2(ar["credit"])
        p = self._base(je_id, d, src, memo)
        p.update({"DocNumber": f"CM-{src}"[:21], "CustomerRef": ref("cust", cust),
                  "Line": [{"DetailType": "SalesItemLineDetail", "Amount": amt,
                            "Description": f"Void invoice {src}: {memo}"[:4000],
                            "SalesItemLineDetail": {"ItemRef": ref("item", "SUB"), "Qty": 1,
                                                    "UnitPrice": amt,
                                                    "TaxCodeRef": {"value": "NON"}}}]})
        self.add(je_id, "CreditMemo", p, expect=self.expect_of(ls))
        self._link_zero_payment(je_id, d, cust, src, amt, "CreditMemo")

    def _link_zero_payment(self, je_id, d, cust, inv_num, amt, other_type):
        inv_key = self.doc_alias.get(f"INV:{inv_num}")
        if not inv_key:
            return
        key = f"LINK:{je_id}"
        self.add(key, "Payment", {
            "TxnDate": d, "CustomerRef": ref("cust", cust), "TotalAmt": 0,
            "PrivateNote": note(key, inv_num, f"Applies {other_type} to invoice {inv_num}"),
            "Line": [{"Amount": amt, "LinkedTxn": [{"TxnId": f"@doc:{inv_key}",
                                                    "TxnType": "Invoice"}]},
                     {"Amount": amt, "LinkedTxn": [{"TxnId": f"@doc:{je_id}",
                                                    "TxnType": other_type}]}]},
            deps=[inv_key, je_id], optional=True)

    def _payment(self, je_id, d, src, memo, ls):
        ar = [l for l in ls if l["account_number"] == "1100"][0]
        dep = [l for l in ls if l["account_number"] != "1100"][0]
        cust, amt = ar["customer_id"], r2(ar["credit"])
        p = self._base(je_id, d, src, memo)
        p.update({"CustomerRef": ref("cust", cust), "TotalAmt": amt,
                  "DepositToAccountRef": ref("acct", dep["account_number"]),
                  "PaymentRefNum": src[:21]})
        inv = self.pay_inv.get(src)
        inv_key = self.doc_alias.get(f"INV:{inv}") if inv else None
        deps = []
        # Applied only when the payment is booked to the invoice's own customer. A payment
        # booked to a different customer stays as that customer's unapplied credit.
        if inv_key and self.inv_cust.get(inv) == cust:
            p["Line"] = [{"Amount": amt, "LinkedTxn": [{"TxnId": f"@doc:{inv_key}",
                                                        "TxnType": "Invoice"}]}]
            deps = [inv_key]
        self.add(je_id, "Payment", p, deps=deps, expect=self.expect_of(ls))

    def _refund(self, je_id, d, src, memo, ls):
        rev = [l for l in ls if l["account_number"] == "4000"][0]
        bank = [l for l in ls if l["account_number"] != "4000"][0]
        amt = r2(rev["debit"])
        p = self._base(je_id, d, src, memo)
        p.update({"DocNumber": src[:21], "CustomerRef": ref("cust", rev["customer_id"]),
                  "DepositToAccountRef": ref("acct", bank["account_number"]),
                  "Line": [{"DetailType": "SalesItemLineDetail", "Amount": amt,
                            "Description": memo[:4000],
                            "SalesItemLineDetail": {"ItemRef": ref("item", "SUB"), "Qty": 1,
                                                    "UnitPrice": amt,
                                                    "TaxCodeRef": {"value": "NON"}}}]})
        self.add(je_id, "RefundReceipt", p, expect=self.expect_of(ls))

    def _bill(self, je_id, d, src, memo, ls):
        ap = [l for l in ls if l["account_number"] == "2000"][0]
        bill_id = src.replace("-DUP", "")
        info = self.bill_info.get(bill_id, {})
        p = self._base(je_id, d, src, memo)
        docnum = memo.split()[-1] if memo else src
        p.update({"VendorRef": ref("vend", ap["vendor_id"]), "DocNumber": docnum[:21],
                  "Line": [self._expense_line(l) for l in ls if l["account_number"] != "2000"]})
        if info.get("due_date"):
            p["DueDate"] = info["due_date"]
        self.add(je_id, "Bill", p, expect=self.expect_of(ls), alias=f"BILL:{src}")

    def _expense_line(self, l):
        det = {"AccountRef": ref("acct", l["account_number"])}
        if l["class"]:
            det["ClassRef"] = ref("class", l["class"])
        return {"DetailType": "AccountBasedExpenseLineDetail", "Amount": r2(l["debit"]),
                "Description": (l["description"] or "")[:4000],
                "AccountBasedExpenseLineDetail": det}

    def _bill_payment(self, je_id, d, src, memo, ls):
        ap = [l for l in ls if l["account_number"] == "2000"][0]
        bank = [l for l in ls if l["account_number"] != "2000"][0]
        amt = r2(ap["debit"])
        bill_key = self.doc_alias.get(f"BILL:{src}")
        p = self._base(je_id, d, src, memo)
        p.update({"VendorRef": ref("vend", ap["vendor_id"]), "PayType": "Check",
                  "TotalAmt": amt,
                  "CheckPayment": {"BankAccountRef": ref("acct", bank["account_number"])},
                  "Line": [{"Amount": amt, "LinkedTxn": [{"TxnId": f"@doc:{bill_key}",
                                                          "TxnType": "Bill"}]}]})
        if not bill_key:
            raise ValueError(f"{je_id}: bill payment for unknown bill {src}")
        self.add(je_id, "BillPayment", p, deps=[bill_key], expect=self.expect_of(ls))

    def _expense(self, je_id, d, src, memo, ls):
        credit = [l for l in ls if l["credit"]]
        debits = [l for l in ls if l["debit"]]
        if len(credit) != 1:
            return self._journal(je_id, d, src, memo, ls)
        c = credit[0]
        ptype = "CreditCard" if self.accounts[c["account_number"]]["type"] == "Credit Card" \
            else "Cash"
        p = self._base(je_id, d, src, memo)
        p.update({"PaymentType": ptype, "AccountRef": ref("acct", c["account_number"]),
                  "DocNumber": src[:21], "Line": [self._expense_line(l) for l in debits]})
        vend = next((l["vendor_id"] for l in ls if l["vendor_id"]), None)
        if vend:
            p["EntityRef"] = {"value": f"@vend:{vend}", "type": "Vendor"}
        self.add(je_id, "Purchase", p, expect=self.expect_of(ls),
                 fallback=self._je_payload(je_id, d, src, memo, ls))

    def _deposit(self, je_id, d, src, memo, ls):
        bank_dr = [l for l in ls if l["debit"] and l["account_number"] in BANK_ACCOUNTS
                   and self.accounts[l["account_number"]]["type"] == "Bank"]
        if len(bank_dr) != 1:
            return self._journal(je_id, d, src, memo, ls)
        to = bank_dr[0]
        p = self._base(je_id, d, src, memo)
        p.update({"DepositToAccountRef": ref("acct", to["account_number"]), "Line": []})
        for l in ls:
            if l is to:
                continue
            amt = r2(l["credit"] - l["debit"])   # fees come through as negative lines
            det = {"AccountRef": ref("acct", l["account_number"])}
            if l["class"]:
                det["ClassRef"] = ref("class", l["class"])
            p["Line"].append({"DetailType": "DepositLineDetail", "Amount": amt,
                              "Description": (l["description"] or memo or "")[:4000],
                              "DepositLineDetail": det})
        self.add(je_id, "Deposit", p, expect=self.expect_of(ls),
                 fallback=self._je_payload(je_id, d, src, memo, ls))

    def _transfer(self, je_id, d, src, memo, ls):
        if len(ls) != 2:
            return self._journal(je_id, d, src, memo, ls)
        dr = [l for l in ls if l["debit"]][0]
        cr = [l for l in ls if l["credit"]][0]
        p = self._base(je_id, d, src, memo)
        p.update({"FromAccountRef": ref("acct", cr["account_number"]),
                  "ToAccountRef": ref("acct", dr["account_number"]), "Amount": r2(dr["debit"])})
        self.add(je_id, "Transfer", p, expect=self.expect_of(ls),
                 fallback=self._je_payload(je_id, d, src, memo, ls))

    def _je_payload(self, je_id, d, src, memo, ls):
        p = self._base(je_id, d, src, memo)
        p.update({"DocNumber": je_id, "Line": self.je_lines(ls, memo or "")})
        return p

    def _journal(self, je_id, d, src, memo, ls):
        self.add(je_id, "JournalEntry", self._je_payload(je_id, d, src, memo, ls),
                 expect=self.expect_of(ls))
        # A write-off journal entry against a customer invoice: link it to the invoice
        ar = [l for l in ls if l["account_number"] == "1100" and l["credit"]]
        if ar and src and src.startswith("FV-"):
            self._link_zero_payment(je_id, d, ar[0]["customer_id"], src, r2(ar[0]["credit"]),
                                    "JournalEntry")

    # ------------------------------------------------------------------ main
    def build(self):
        self.ops, self.doc_alias = [], {}
        # pre-register invoice and bill keys so a payment dated the same day as its invoice
        # (but planned first) still links to it
        for je_id, doc, src in self.b.execute(
                "SELECT je_id, doc_type, source_ref FROM gl_entries_to_load "
                "WHERE doc_type IN ('Invoice', 'Bill')"):
            self.doc_alias[("INV:" if doc == "Invoice" else "BILL:") + src] = je_id
        self.plan_conversion()
        self.plan_transactions()
        return self._order(self.ops)

    @staticmethod
    def _order(ops):
        """Keep date order, but make sure every operation comes after its dependencies."""
        by_key = {o["key"]: o for o in ops}
        done, out = set(), []

        def place(o, stack=()):
            if o["key"] in done:
                return
            if o["key"] in stack:
                raise ValueError(f"circular dependency at {o['key']}")
            for d in o["deps"]:
                if d not in by_key:
                    raise ValueError(f"{o['key']} depends on unknown {d}")
                place(by_key[d], stack + (o["key"],))
            done.add(o["key"])
            out.append(o)

        for o in ops:
            place(o)
        return out
