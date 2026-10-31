"""Offline tests for the Fernvale MCP server:  python -m tests.test_mcp_server"""
import asyncio
import sys
import tempfile
from pathlib import Path

from qbo_loader import client, steps
from tests.fake_qbo import FakeQBO


def tools_against_fake():
    tmp = Path(tempfile.mkdtemp())
    client.WORK = steps.WORK = tmp
    steps.STATE = tmp / "state.json"
    steps.BATCH_GAP = 0
    q = FakeQBO()
    steps.setup(q)
    steps.load(q, limit=50)
    from fernvale_mcp import server as S
    S._qbo, S.DRAFTS = q, tmp / "drafts"

    coa = S.qbo_chart_of_accounts()
    assert "6600\tLegal Fees" in coa, coa[:300]
    assert "bank_transactions" in S.source_tables()
    out = S.source_query("SELECT COUNT(*) AS n FROM billing_invoices")
    assert out.splitlines()[1].isdigit()
    for bad in ("DELETE FROM bank_transactions", "SELECT 1; DROP TABLE x"):
        try:
            S.source_query(bad)
            raise AssertionError("write query allowed")
        except ValueError:
            pass
    try:
        S.source_query("SELECT * FROM private_answers")
        raise AssertionError("unknown table should fail")
    except Exception:
        pass
    assert "2024-10" in S.legacy_pl_history("2024-10", "2024-10")

    # closed period is refused; open period drafts and posts
    try:
        S.qbo_draft_journal_entry("2026-09-30", "test", [{"account": "6600", "debit": 1},
                                                         {"account": "2200", "credit": 1}])
        raise AssertionError("closed period allowed")
    except ValueError:
        pass
    try:
        S.qbo_draft_journal_entry("2026-10-31", "unbalanced", [{"account": "6600", "debit": 2},
                                                               {"account": "2200", "credit": 1}])
        raise AssertionError("unbalanced allowed")
    except ValueError:
        pass
    txt = S.qbo_draft_journal_entry(
        "2026-10-31", "Accrue October legal", [
            {"account": "6600", "debit": 20000, "class": "G&A", "description": "Oct legal"},
            {"account": "2200", "credit": 20000}], reversing_date="2026-11-01")
    did = txt.split()[1]
    before = len(q.db["JournalEntry"])
    assert "Not posted" in txt and len(q.db["JournalEntry"]) == before
    print(S.qbo_list_drafts())
    S.qbo_post_draft(did)
    assert len(q.db["JournalEntry"]) == before + 1
    try:
        S.qbo_post_draft(did)
        raise AssertionError("posted twice")
    except ValueError:
        pass
    S.qbo_discard_draft(did + "R")

    bill = S.qbo_draft_bill("V001", "2026-10-14", "2026-11-13", "TEST-1",
                            [{"account": "6700", "amount": 28400, "class": "Sales"}])
    bid = bill.split()[1]
    S.qbo_post_draft(bid)
    new_bill = [b for b in q.db["Bill"].values() if b.get("DocNumber") == "TEST-1"][0]
    ch = S.qbo_draft_change("delete", "Bill", new_bill["Id"], "duplicate test")
    S.qbo_post_draft(ch.split()[1])
    assert new_bill["Id"] not in q.db["Bill"]
    print("tool tests passed")


async def protocol():
    """Start the real server over stdio and list its tools, as Claude would."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable,
                                   args=[str(Path("fernvale_mcp/run.py").resolve())])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            names = sorted(t.name for t in tools)
            print(f"{len(names)} tools over stdio: {', '.join(names)}")
            res = await s.call_tool("source_query", {"sql": "SELECT COUNT(*) n FROM hr_employees"})
            print("source_query over stdio ->", res.content[0].text.replace("\n", " | "))


if __name__ == "__main__":
    tools_against_fake()
    asyncio.run(protocol())
