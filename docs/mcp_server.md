# Fernvale MCP server

`fernvale_mcp/` connects Claude to Fernvale's QuickBooks sandbox and its source systems through the Model Context Protocol. It reuses the QuickBooks sign-in the loader already set up (`.env` and `.qbo_tokens.json`).

## Tools

| Group | Tool | What it does |
|---|---|---|
| QuickBooks, read | `qbo_report` | Any QuickBooks report (trial balance, P&L, balance sheet, general ledger, AR/AP aging, cash flow), optionally by month or class, as a table |
| | `qbo_query` | Read-only QuickBooks query, e.g. all October invoices |
| | `qbo_get` | One record by type and Id |
| | `qbo_chart_of_accounts` | Accounts with numbers, types and balances |
| QuickBooks, write | `qbo_draft_journal_entry` | Drafts a balanced entry, optionally with its reversal (accruals) |
| | `qbo_draft_bill` | Drafts a vendor bill |
| | `qbo_draft_change` | Drafts a delete, void or update of an existing record (e.g. a duplicate bill) |
| | `qbo_list_drafts`, `qbo_discard_draft` | Review and discard drafts |
| | `qbo_post_draft` | Posts an approved draft |
| Source systems | `source_tables` | What's in the CRM, billing, Stripe, payroll, spend, bank and budget tables |
| | `source_query` | Read-only SQL against them |
| | `legacy_pl_history` | Monthly P&L from before QuickBooks (2022 to Oct 2024) |

## Guardrails

- **Draft, then confirm:** nothing changes in QuickBooks until `qbo_post_draft` runs for a draft the person approved. Claude's app also asks before each tool call that can write.
- **Closed periods are protected:** drafts dated on or before Sep 30, 2026 are refused unless explicitly marked as a prior-period adjustment.
- **Audit trail:** every record Claude posts carries `FV-AGENT:<draft id>` in its private note. Drafts are kept in `.qbo/drafts/`.
- **Honest tests:** source data opens read-only, and no tool can read `private/` (the answer key) or the generator.
- **Sandbox only:** the QuickBooks client refuses production companies.

## Setup (Windows)

1. `pip install mcp`
2. In the Claude desktop app, go to **Settings → Developer → Edit Config**. That opens `claude_desktop_config.json`. Add the `fernvale` entry, using your own path:

```json
{
  "mcpServers": {
    "fernvale": {
      "command": "python",
      "args": ["C:\\Users\\<you>\\Documents\\GitHub\\demo-company\\fernvale_mcp\\run.py"]
    }
  }
}
```

   If the file already has an `"mcpServers"` section, add `"fernvale": {...}` inside it.

3. Fully quit the Claude desktop app (from the system tray too) and reopen it. The Fernvale tools appear under the tools/connectors menu.

If the server doesn't start, try the full path to Python instead of `python`. Running `where python` in PowerShell shows it. Note that JSON needs double backslashes.

## Tests

```
python -m tests.test_mcp_server   # tools against a fake QuickBooks, plus a real stdio session
```
