"""Launcher for Claude's config: python <repo>/fernvale_mcp/run.py (works from any folder)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fernvale_mcp.server import main  # noqa: E402

main()
