"""All settings come from environment variables (or a .env file next to the project)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# --- Ekyam Dev MCP server -------------------------------------------------------------
MCP_URL = os.environ.get("EKYAM_MCP_URL", "https://mcp-dev.ekyam.ai/mcp")
MCP_AUTH_MODE = os.environ.get("MCP_AUTH_MODE", "oauth").strip().lower()  # none | api_key | oauth | entra
MCP_TOKEN = os.environ.get("EKYAM_MCP_TOKEN", "")                          # api_key mode
MCP_ENTRA_SCOPE = os.environ.get("MCP_ENTRA_SCOPE", "")                    # entra mode, e.g. api://ekyam-tools/.default
# oauth mode (OAuth client credentials: a client_id/secret made with the backend's /admin/clients)
MCP_OAUTH_CLIENT_ID = os.environ.get("MCP_OAUTH_CLIENT_ID", "")
MCP_OAUTH_CLIENT_SECRET = os.environ.get("MCP_OAUTH_CLIENT_SECRET", "")
MCP_OAUTH_SCOPE = os.environ.get("MCP_OAUTH_SCOPE", "mcp.read")
MCP_OAUTH_TOKEN_URL = os.environ.get("MCP_OAUTH_TOKEN_URL", "")  # empty = discover from the MCP server
MCP_TIMEOUT = float(os.environ.get("MCP_TIMEOUT_SECONDS", "180"))

# --- Pages ------------------------------------------------------------------------------
PAGES_DIR = Path(os.environ.get("MINTED_PAGES_DIR", ROOT / "pages"))
API_PATH = os.environ.get("MINTED_API_PATH", "/minted/api/tools")

# --- Simple sign-in for local testing (replace with SSO later) ---------------------------
DEMO_KEY = os.environ.get("MINTED_DEMO_KEY", "")

# --- Warm-up -----------------------------------------------------------------------------
WARMUP_ENABLED = _bool("WARMUP_ENABLED", True)
WARMUP_CRON = os.environ.get("WARMUP_CRON", "0 7 * * 1-5")       # minute hour day month weekday
WARMUP_TZ = os.environ.get("WARMUP_TZ", "Asia/Kolkata")
WARMUP_ON_STARTUP = _bool("WARMUP_ON_STARTUP", False)
WARMUP_CONCURRENCY = int(os.environ.get("WARMUP_CONCURRENCY", "6"))

# --- Excel -------------------------------------------------------------------------------
EXCEL_RECALC = _bool("EXCEL_RECALC", True)   # uses LibreOffice when it is installed

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# The only tools the server will run (the pages, Excel and warm-up use exactly these).
ALLOWED_TOOLS = frozenset({
    "minted_weekly_shipped_by_card", "minted_reorder_plan", "minted_build_everyday_po",
    "minted_build_seasonal_po", "minted_order_check", "minted_order_trace",
    "minted_delivery_status", "minted_billing_report", "minted_cards_by_location",
    "cypher_chain",
})
