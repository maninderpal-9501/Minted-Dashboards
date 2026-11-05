"""All settings come from environment variables (or a .env file next to the project)."""
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# Where settings come from:
#   on a laptop  -> the .env file (plus any environment variables)
#   on Azure     -> ONLY Azure's environment variables. A .env file that was deployed with the
#                   code is ignored, so an old value in it (e.g. MINTED_DEMO_KEY) cannot sneak in.
#   USE_DOTENV=true forces reading .env anywhere; USE_DOTENV=false never reads it.
ON_AZURE = any(os.environ.get(v) for v in ("WEBSITE_SITE_NAME", "WEBSITE_INSTANCE_ID", "CONTAINER_APP_NAME"))
_use = os.environ.get("USE_DOTENV", "").strip().lower()
USE_DOTENV = _use in ("1", "true", "yes", "on") if _use else not ON_AZURE
DOTENV_FOUND = (ROOT / ".env").exists()
_DOTENV_VALUES = dotenv_values(ROOT / ".env") if DOTENV_FOUND else {}
if USE_DOTENV:
    load_dotenv(ROOT / ".env")
SETTINGS_SOURCE = ".env + environment" if USE_DOTENV and DOTENV_FOUND else "environment only"


def _env(name: str, default: str = "") -> str:
    """Read a setting, ignoring stray spaces and surrounding quotes.
    (Azure App Settings keep quotes literally: a value typed as "" is two quote characters, not empty.)"""
    v = os.environ.get(name, default)
    v = (v or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].strip()
    return v


def _bool(name: str, default: bool) -> bool:
    return _env(name, str(default)).lower() in ("1", "true", "yes", "on")


# --- Ekyam Dev MCP server -------------------------------------------------------------
MCP_URL = _env("EKYAM_MCP_URL", "https://mcp-dev.ekyam.ai/mcp")
MCP_AUTH_MODE = _env("MCP_AUTH_MODE", "oauth").lower()  # none | api_key | oauth | entra
MCP_TOKEN = _env("EKYAM_MCP_TOKEN", "")                          # api_key mode
MCP_ENTRA_SCOPE = _env("MCP_ENTRA_SCOPE", "")                    # entra mode, e.g. api://ekyam-tools/.default
# oauth mode (OAuth client credentials: a client_id/secret made with the backend's /admin/clients)
MCP_OAUTH_CLIENT_ID = _env("MCP_OAUTH_CLIENT_ID", "")
MCP_OAUTH_CLIENT_SECRET = _env("MCP_OAUTH_CLIENT_SECRET", "")
MCP_OAUTH_SCOPE = _env("MCP_OAUTH_SCOPE", "mcp.read")
MCP_OAUTH_TOKEN_URL = _env("MCP_OAUTH_TOKEN_URL", "")  # empty = discover from the MCP server
MCP_TIMEOUT = float(_env("MCP_TIMEOUT_SECONDS", "180"))

# --- Pages ------------------------------------------------------------------------------
PAGES_DIR = Path(_env("MINTED_PAGES_DIR") or ROOT / "pages")
API_PATH = _env("MINTED_API_PATH", "/minted/api/tools")

# --- Simple sign-in for local testing (replace with SSO later) ---------------------------
# MINTED_SIGN_IN=off  -> never ask for a key, whatever MINTED_DEMO_KEY says (the sure switch)
# MINTED_SIGN_IN=on   -> ask for MINTED_DEMO_KEY (it must be set)
# not set / auto      -> ask only when MINTED_DEMO_KEY has a value
SIGN_IN = _env("MINTED_SIGN_IN", "auto").lower()
_raw_key = _env("MINTED_DEMO_KEY", "")
DEMO_KEY = "" if SIGN_IN in ("off", "false", "0", "no") else _raw_key
if "MINTED_DEMO_KEY" not in os.environ:
    DEMO_KEY_SOURCE = "not set"
elif USE_DOTENV and DOTENV_FOUND and os.environ.get("MINTED_DEMO_KEY") == _DOTENV_VALUES.get("MINTED_DEMO_KEY"):
    DEMO_KEY_SOURCE = ".env file"
else:
    DEMO_KEY_SOURCE = "server environment (Azure settings, Docker, or shell)"

# --- Warm-up -----------------------------------------------------------------------------
WARMUP_ENABLED = _bool("WARMUP_ENABLED", True)
WARMUP_CRON = _env("WARMUP_CRON", "0 7 * * 1-5")       # minute hour day month weekday
WARMUP_TZ = _env("WARMUP_TZ", "Asia/Kolkata")
WARMUP_ON_STARTUP = _bool("WARMUP_ON_STARTUP", False)
WARMUP_CONCURRENCY = int(_env("WARMUP_CONCURRENCY", "6"))

# --- Excel -------------------------------------------------------------------------------
EXCEL_RECALC = _bool("EXCEL_RECALC", True)   # uses LibreOffice when it is installed

LOG_LEVEL = _env("LOG_LEVEL", "INFO")

# The only tools the server will run (the pages, Excel and warm-up use exactly these).
ALLOWED_TOOLS = frozenset({
    "minted_weekly_shipped_by_card", "minted_reorder_plan", "minted_build_everyday_po",
    "minted_build_seasonal_po", "minted_order_check", "minted_order_trace",
    "minted_delivery_status", "minted_billing_report", "minted_cards_by_location",
    "cypher_chain",
})