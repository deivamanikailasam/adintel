"""Launch the AdIntel MCP server over stdio with seeded demo data (for the SDK conformance test only)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
os.environ.setdefault("ADINTEL_LLM_PROVIDER", "mock")

from adintel.approvals.service import load_user
from adintel.mcp.server import main
from adintel.security.auth import issue_token
from adintel.seed.catalog import seed
from adintel.storage import get_database

db = get_database()
seed(db, with_kb=False)
os.environ["ADINTEL_MCP_TOKEN"] = issue_token(load_user(db, "brightwave", os.environ.get("DEMO_USER", "u_jordan")))
main()
