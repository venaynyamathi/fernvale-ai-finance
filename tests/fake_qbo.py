"""
A small in-memory stand-in for the QuickBooks API, enough to run the whole loader offline:
setup -> load -> verify. It enforces references (every Id must exist), applies payments to
invoices, and builds a trial balance report the way QuickBooks does (prior-year P&L in
retained earnings).
"""
import copy
import re
from collections import defaultdict

from qbo_loader.client import QBOError
from qbo_loader.plan import ITEMS
from qbo_loader.simulate import posting

PL_TYPES = {"Income", "Other Income", "Expense", "Other Expense", "Cost of Goods Sold"}
TXN = {"Invoice", "Payment", "CreditMemo", "RefundReceipt", "Bill", "BillPayment", "Purchase",
       "Deposit", "Transfer", "JournalEntry", "SalesReceipt", "Estimate", "VendorCredit",
       "PurchaseOrder", "TimeActivity"}
REF_KEYS = {"AccountRef": "Account", "DepositToAccountRef": "Account", "BankAccountRef": "Account",
            "FromAccountRef": "Account", "ToAccountRef": "Account", "IncomeAccountRef": "Account",
            "ItemRef": "Item", "ClassRef": "Class", "CustomerRef": "Customer",
            "VendorRef": "Vendor"}


class FakeQBO:
    realm = "fake-realm"
    tokens = {"access_token": "x"}

    def __init__(self, strict=False):
        self.strict = strict      # refuse negative deposit lines and balance-sheet items
        self.db = defaultdict(dict)
        self.next_id = 1000
        self.prefs = {"SyncToken": "0",
                      "AccountingInfoPrefs": {"UseAccountNumbers": True,
                                              "ClassTrackingPerTxnLine": True},
                      "SalesFormsPrefs": {"CustomTxnNumbers": True, "AutoApplyCredit": False,
                                          "AutoApplyPayments": True}}
        # Intuit-style sample company
        for name, typ, sub in [("Accounts Receivable (A/R)", "Accounts Receivable", "AccountsReceivable"),
                               ("Accounts Payable (A/P)", "Accounts Payable", "AccountsPayable"),
                               ("Retained Earnings", "Equity", "RetainedEarnings"),
                               ("Opening Balance Equity", "Equity", "OpeningBalanceEquity"),
                               ("Insurance", "Expense", "Insurance"),
                               ("Travel", "Expense", "Travel"),
                               ("Checking", "Bank", "Checking"),
                               ("Services", "Income", "ServiceFeeIncome")]:
            self._add("Account", {"Name": name, "AccountType": typ, "AccountSubType": sub,
                                  "Active": True, "CurrentBalance": 0})
        bank = self._find("Account", "Checking")
        inc = self._find("Account", "Services")
        c = self._add("Customer", {"DisplayName": "Amy's Bird Sanctuary", "Active": True})
        it = self._add("Item", {"Name": "Gardening", "Type": "Service", "Active": True,
                                "IncomeAccountRef": {"value": inc["Id"]}})
        self._add("Invoice", {"TxnDate": "2026-08-01", "CustomerRef": {"value": c["Id"]},
                              "Line": [{"Amount": 100, "DetailType": "SalesItemLineDetail",
                                        "SalesItemLineDetail": {"ItemRef": {"value": it["Id"]}}}]})
        self.sample_bank = bank["Id"]

    # ----------------------------------------------------------------- storage
    def _add(self, entity, obj):
        self.next_id += 1
        obj = copy.deepcopy(obj)
        obj["Id"], obj["SyncToken"] = str(self.next_id), "0"
        self.db[entity][obj["Id"]] = obj
        return obj

    def _find(self, entity, name):
        return next(o for o in self.db[entity].values()
                    if o.get("Name") == name or o.get("DisplayName") == name)

    def _check_refs(self, entity, x, path=""):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in REF_KEYS and isinstance(v, dict):
                    if v.get("value") not in self.db[REF_KEYS[k]]:
                        raise QBOError(f"{entity}: invalid {k} {v}", 400)
                elif k == "EntityRef" and isinstance(v, dict):
                    t = v.get("type") or ("Vendor" if v.get("value") in self.db["Vendor"]
                                          else "Customer")
                    if v.get("value") not in self.db[t] and \
                            v.get("value") not in self.db["Customer"]:
                        raise QBOError(f"{entity}: invalid EntityRef {v}", 400)
                elif k == "LinkedTxn":
                    for lt in v:
                        if lt["TxnId"] not in self.db[lt["TxnType"]]:
                            raise QBOError(f"{entity}: linked {lt} not found", 400)
                else:
                    self._check_refs(entity, v, path + "." + k)
        elif isinstance(x, list):
            for v in x:
                self._check_refs(entity, v, path)

    def _create(self, entity, p):
        self._check_refs(entity, p)
        if entity in TXN and "@" in str(p):
            raise QBOError(f"{entity}: unresolved reference in payload", 400)
        if self.strict and entity == "Deposit" and any(l["Amount"] < 0 for l in p["Line"]):
            raise QBOError("Deposit lines can't be negative", 400)
        if self.strict and entity == "Item":
            acct = self.db["Account"][p["IncomeAccountRef"]["value"]]
            if acct["AccountType"] not in ("Income", "Other Income"):
                raise QBOError("Item income account must be an income account", 400)
        if entity == "Account":
            if any(o["Name"] == p["Name"] for o in self.db["Account"].values()):
                raise QBOError("Duplicate Name Exists Error", 400)
        if entity in ("Customer", "Vendor"):
            names = {o.get("DisplayName") for e in ("Customer", "Vendor")
                     for o in self.db[e].values()}
            if p["DisplayName"] in names:
                raise QBOError("Duplicate Name Exists Error", 400)
        if entity == "Payment":
            applied = sum(l["Amount"] for l in p.get("Line", [])
                          if l["LinkedTxn"][0]["TxnType"] == "Invoice")
            credits = sum(l["Amount"] for l in p.get("Line", [])
                          if l["LinkedTxn"][0]["TxnType"] != "Invoice")
            if round(applied - credits, 2) > round(p["TotalAmt"], 2) + 0.001:
                raise QBOError("Payment lines exceed total", 400)
        if entity == "JournalEntry":
            dr = sum(l["Amount"] for l in p["Line"]
                     if l["JournalEntryLineDetail"]["PostingType"] == "Debit")
            cr = sum(l["Amount"] for l in p["Line"]
                     if l["JournalEntryLineDetail"]["PostingType"] == "Credit")
            if round(dr - cr, 2):
                raise QBOError("Journal entry does not balance", 400)
            for l in p["Line"]:
                det = l["JournalEntryLineDetail"]
                acct = self.db["Account"][det["AccountRef"]["value"]]
                if acct["AccountType"] in ("Accounts Receivable", "Accounts Payable") and \
                        "Entity" not in det:
                    raise QBOError("AR/AP line needs a customer or vendor", 400)
        if "ClassRef" in str(p) and not self.prefs["AccountingInfoPrefs"]["ClassTrackingPerTxnLine"]:
            raise QBOError("Class tracking is not enabled", 400)
        return self._add(entity, p)

    def _update(self, entity, p):
        cur = self.db[entity][p["Id"]]
        cur.update({k: v for k, v in p.items() if k not in ("sparse", "SyncToken")})
        cur["SyncToken"] = str(int(cur["SyncToken"]) + 1)
        return cur

    # ----------------------------------------------------------------- API surface
    def request(self, method, path, body=None, params=None):
        if path.startswith("companyinfo"):
            return {"CompanyInfo": {"CompanyName": "Sandbox Company_US_1"}}
        if path == "preferences":
            if method == "POST":
                for k, v in body.items():
                    if isinstance(v, dict):
                        self.prefs.setdefault(k, {}).update(v)
            return {"Preferences": self.prefs}
        if path == "batch":
            return self.batch_raw(body)
        raise NotImplementedError(path)

    def query(self, sql):
        m = re.match(r"SELECT \* FROM (\w+)(.*)", sql)
        entity, where = m.group(1), m.group(2)
        rows = list(self.db[entity].values())
        if "Active = true" in where:
            rows = [r for r in rows if r.get("Active", True)]
        return copy.deepcopy(rows)

    def create(self, entity, payload):
        return copy.deepcopy(self._create(entity, payload))

    def update(self, entity, payload):
        return copy.deepcopy(self._update(entity, payload))

    def batch(self, items):
        assert len(items) <= 30, "batch too large"
        out = {}
        for b, op, entity, p in items:
            try:
                if op == "create":
                    out[b] = (copy.deepcopy(self._create(entity, p)), None)
                elif op == "update":
                    out[b] = (copy.deepcopy(self._update(entity, p)), None)
                elif op == "delete":
                    self.db[entity].pop(p["Id"])
                    out[b] = ({"Id": p["Id"], "status": "Deleted"}, None)
            except QBOError as e:
                out[b] = (None, {"Error": [{"code": "400", "Message": str(e)}]})
        return out

    # ----------------------------------------------------------------- reporting
    def _unresolve(self, entity, p):
        acct_num = {i: a.get("AcctNum") for i, a in self.db["Account"].items()}
        item_key = {i: next(k for k, v in ITEMS.items() if v[0] == it["Name"])
                    for i, it in self.db["Item"].items() if it.get("Description", "").startswith("FV:")}

        def walk(x, parent=None):
            if isinstance(x, dict):
                out = {}
                for k, v in x.items():
                    if k in ("AccountRef", "DepositToAccountRef", "BankAccountRef",
                             "FromAccountRef", "ToAccountRef") and isinstance(v, dict):
                        out[k] = {"value": f"@acct:{acct_num[v['value']] or 'X' + v['value']}"}
                    elif k == "ItemRef":
                        out[k] = {"value": f"@item:{item_key.get(v['value'], 'SAMPLE')}"}
                    else:
                        out[k] = walk(v, k)
                return out
            if isinstance(x, list):
                return [walk(v) for v in x]
            return x
        return walk(p)

    def report(self, name, params):
        assert name == "TrialBalance"
        start, end = params["start_date"], params["end_date"]
        num_to_id = {a.get("AcctNum"): i for i, a in self.db["Account"].items() if a.get("AcctNum")}
        re_id = next(i for i, a in self.db["Account"].items()
                     if a.get("AccountSubType") == "RetainedEarnings")
        bal = defaultdict(float)
        for entity in TXN:
            for t in self.db[entity].values():
                if t["TxnDate"] > end or entity not in (
                        "Invoice", "Payment", "CreditMemo", "RefundReceipt", "Bill", "BillPayment",
                        "Purchase", "Deposit", "Transfer", "JournalEntry"):
                    continue
                if not str(t.get("PrivateNote", "")).startswith("FV:"):
                    continue   # (sample transactions were deleted in the test anyway)
                acct_num = {i: a.get("AcctNum") for i, a in self.db["Account"].items()}
                item_accts = {next(k for k, v in ITEMS.items() if v[0] == it["Name"]):
                              acct_num[it["IncomeAccountRef"]["value"]]
                              for it in self.db["Item"].values()
                              if it.get("Description", "").startswith("FV:")}
                for a, d, c in posting(entity, self._unresolve(entity, t), item_accts):
                    aid = num_to_id[a]
                    acct = self.db["Account"][aid]
                    if acct["AccountType"] in PL_TYPES and t["TxnDate"] < start:
                        aid = re_id
                    bal[aid] += d - c
        rows = []
        for aid, v in bal.items():
            if abs(v) < 0.005:
                continue
            rows.append({"ColData": [{"value": self.db["Account"][aid]["Name"], "id": aid},
                                     {"value": f"{v:.2f}" if v > 0 else ""},
                                     {"value": f"{-v:.2f}" if v < 0 else ""}]})
        return {"Rows": {"Row": rows + [{"type": "Section", "Summary": {}}]}}
