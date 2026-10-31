"""
Offline model of how QuickBooks posts each transaction type to the general ledger.
Used by the tests and the fake QuickBooks client; never needed for a real load.

Works on unresolved payloads (with "@acct:4000"-style references) and returns a list of
(account_number, debit, credit).
"""
from .plan import ITEMS

AR, AP = "1100", "2000"


def _acct(r):
    return r["value"].split(":", 1)[1]


def posting(entity, p, item_accounts=None):
    item_accounts = item_accounts or {k: v[1] for k, v in ITEMS.items()}

    def _item_acct(r):
        return item_accounts[r["value"].split(":", 1)[1]]

    out = []

    def dr(a, x):
        if round(x, 2):
            out.append((a, round(x, 2), 0.0) if x > 0 else (a, 0.0, round(-x, 2)))

    def cr(a, x):
        dr(a, -x)

    if entity == "Invoice":
        for l in p["Line"]:
            cr(_item_acct(l["SalesItemLineDetail"]["ItemRef"]), l["Amount"])
        dr(AR, sum(l["Amount"] for l in p["Line"]))
    elif entity == "CreditMemo":
        for l in p["Line"]:
            dr(_item_acct(l["SalesItemLineDetail"]["ItemRef"]), l["Amount"])
        cr(AR, sum(l["Amount"] for l in p["Line"]))
    elif entity == "RefundReceipt":
        for l in p["Line"]:
            dr(_item_acct(l["SalesItemLineDetail"]["ItemRef"]), l["Amount"])
        cr(_acct(p["DepositToAccountRef"]), sum(l["Amount"] for l in p["Line"]))
    elif entity == "Payment":
        if p["TotalAmt"]:
            dr(_acct(p["DepositToAccountRef"]), p["TotalAmt"])
            cr(AR, p["TotalAmt"])
    elif entity in ("Bill", "Purchase"):
        for l in p["Line"]:
            dr(_acct(l["AccountBasedExpenseLineDetail"]["AccountRef"]), l["Amount"])
        total = sum(l["Amount"] for l in p["Line"])
        cr(AP if entity == "Bill" else _acct(p["AccountRef"]), total)
    elif entity == "BillPayment":
        dr(AP, p["TotalAmt"])
        cr(_acct(p["CheckPayment"]["BankAccountRef"]), p["TotalAmt"])
    elif entity == "Deposit":
        for l in p["Line"]:
            cr(_acct(l["DepositLineDetail"]["AccountRef"]), l["Amount"])
        dr(_acct(p["DepositToAccountRef"]), sum(l["Amount"] for l in p["Line"]))
    elif entity == "Transfer":
        dr(_acct(p["ToAccountRef"]), p["Amount"])
        cr(_acct(p["FromAccountRef"]), p["Amount"])
    elif entity == "JournalEntry":
        for l in p["Line"]:
            det = l["JournalEntryLineDetail"]
            (dr if det["PostingType"] == "Debit" else cr)(_acct(det["AccountRef"]), l["Amount"])
    else:
        raise ValueError(entity)
    return out


def net(lines):
    tot = {}
    for a, d, c in lines:
        tot[a] = round(tot.get(a, 0.0) + d - c, 2)
    return {a: v for a, v in tot.items() if v}
