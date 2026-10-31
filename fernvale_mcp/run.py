"""Launcher for Claude's config: python <repo>/fernvale_mcp/run.py (works from any folder).

Writes a startup record and any crash to .qbo/mcp_server.log, so a server that shows as
"disconnected" in Claude can be diagnosed.
"""
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / ".qbo" / "mcp_server.log"
sys.path.insert(0, str(ROOT))


def note(msg):
    try:
        LOG.parent.mkdir(exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
    except OSError:
        pass


note(f"starting: python {sys.version.split()[0]} at {sys.executable}")
try:
    import importlib.metadata as md
    try:
        note(f"mcp package version {md.version('mcp')}")
    except md.PackageNotFoundError:
        note("mcp package NOT installed for this Python. Run: "
             f'"{sys.executable}" -m pip install mcp')
    from fernvale_mcp.server import main
    note("server loaded, waiting for Claude")
    main()
    note("server stopped normally")
except Exception:
    note("CRASHED:\n" + traceback.format_exc())
    raise
