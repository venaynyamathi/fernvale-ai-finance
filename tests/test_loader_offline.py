"""
End-to-end loader test against the fake QuickBooks API:  python -m tests.test_loader_offline
Runs check -> clean -> setup -> load (interrupted halfway, then resumed) -> verify.
"""
import tempfile
from pathlib import Path

from qbo_loader import client, steps
from tests.fake_qbo import FakeQBO


def main():
    for strict in (False, True):
        run(strict)


def run(strict):
    print(f"--- fake QuickBooks, strict={strict}")
    tmp = Path(tempfile.mkdtemp())
    client.WORK = steps.WORK = tmp
    steps.STATE = tmp / "state.json"
    steps.BATCH_GAP = 0

    q = FakeQBO(strict=strict)
    assert steps.check(q), "settings should pass"
    steps.clean(q, assume_yes=True)
    assert not q.db["Invoice"], "sample invoice should be deleted"
    steps.setup(q)
    steps.setup(q)                       # running twice must be harmless
    steps.load(q, limit=2500)            # simulate stopping partway
    steps.load(q)                        # resume
    steps.load(q)                        # nothing left to do
    ok = steps.verify(q)
    st = steps.load_state()
    print((tmp / "verify_report.md").read_text()[:600])
    assert ok, "verify failed"
    n_docs = sum(len(q.db[e]) for e in ("Invoice", "Payment", "CreditMemo", "RefundReceipt",
                                        "Bill", "BillPayment", "Purchase", "Deposit",
                                        "Transfer", "JournalEntry"))
    loaded = sum(1 for d in st["docs"].values() if "id" in d)
    if strict:
        assert st["open_item_fallback"], "expected the opening-balance item fallback"
    assert n_docs == loaded, f"{n_docs} records in fake QuickBooks vs {loaded} in state"
    print(f"offline loader test passed: {loaded} transactions, "
          f"{len(st['customers'])} customers, {len(st['vendors'])} vendors, "
          f"{len(st['warnings'])} warnings")


if __name__ == "__main__":
    main()
