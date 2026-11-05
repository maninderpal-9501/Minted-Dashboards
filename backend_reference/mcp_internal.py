"""FOR THE EKYAM BACKEND REPO (not used by this project at runtime).

Adds a second MCP endpoint, /mcp-internal, for the Minted pages server:
  * same tool runner as /mcp, so results and the 24-hour cache are identical to Claude's
  * its own auth (service token), so the claude.ai connector on /mcp is untouched
  * only the ten tools the pages use

Adapt the three marked places to how your backend builds its MCP server.

Settings on the backend
  TOOLS_AUTH_MODE    api_key (local/dev) | entra (Azure)
  TOOLS_API_KEYS     comma-separated keys accepted in api_key mode (leave EMPTY in production)
  ENTRA_TENANT_ID    your tenant id (entra mode)
  TOOLS_API_AUDIENCE api://ekyam-tools  (the app registration's Application ID URI)
  TOOLS_REQUIRED_ROLE Tools.Read        (app role assigned to the pages server's Managed Identity)

pip install pyjwt[crypto]
"""
import os

import jwt
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

INTERNAL_PREFIX = "/mcp-internal"
MODE = os.environ.get("TOOLS_AUTH_MODE", "entra")
API_KEYS = {k.strip() for k in os.environ.get("TOOLS_API_KEYS", "").split(",") if k.strip()}
TENANT = os.environ.get("ENTRA_TENANT_ID", "")
AUDIENCE = os.environ.get("TOOLS_API_AUDIENCE", "api://ekyam-tools")
ROLE = os.environ.get("TOOLS_REQUIRED_ROLE", "Tools.Read")

MINTED_PAGE_TOOLS = {
    "minted_weekly_shipped_by_card", "minted_reorder_plan", "minted_build_everyday_po",
    "minted_build_seasonal_po", "minted_order_check", "minted_order_trace",
    "minted_delivery_status", "minted_billing_report", "minted_cards_by_location", "cypher_chain",
}

_jwks = PyJWKClient(f"https://login.microsoftonline.com/{TENANT}/discovery/v2.0/keys") if TENANT else None


def verify_service_token(token: str) -> str | None:
    """Return the caller id, or None if the token is not acceptable."""
    if not token:
        return None
    if MODE == "api_key" and token in API_KEYS:
        return "api-key"
    if _jwks is None:
        return None
    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=AUDIENCE,
                            issuer=f"https://login.microsoftonline.com/{TENANT}/v2.0")
    except jwt.PyJWTError:
        return None
    if ROLE not in claims.get("roles", []):
        return None
    return claims.get("oid") or claims.get("sub")


class InternalMCPAuth(BaseHTTPMiddleware):
    """Protects only /mcp-internal; /mcp keeps whatever auth the claude.ai connector uses today."""

    async def dispatch(self, request, call_next):
        if request.url.path.startswith(INTERNAL_PREFIX):
            token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            caller = verify_service_token(token)
            if not caller:
                return JSONResponse({"error": "unauthorized"}, status_code=401,
                                    headers={"WWW-Authenticate": 'Bearer realm="mcp-internal"'})
            request.state.service_caller = caller
        return await call_next(request)


# ---------------------------------------------------------------------------------------------
# Wiring — ADAPT to your backend. Typical shapes:
#
# (1) Build a second MCP server object that registers ONLY the Minted page tools but calls the
#     SAME runner your /mcp server uses:
#
#       internal = build_mcp_server(tool_filter=lambda name: name in MINTED_PAGE_TOOLS)   # <-- your factory
#
#     If your server lists tools dynamically from the custom-tool registry, filter that list and
#     reject call_tool for any other name.
#
# (2) Mount it beside the existing one, with its own session manager:
#
#       from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
#       internal_manager = StreamableHTTPSessionManager(app=internal)
#       async def internal_handler(scope, receive, send):
#           await internal_manager.handle_request(scope, receive, send)
#       app.router.routes.append(Mount(INTERNAL_PREFIX, app=internal_handler))     # <-- your Starlette/FastAPI app
#       # and run `async with internal_manager.run():` inside the app lifespan, like the /mcp manager
#
#     With FastMCP:  internal = FastMCP("ekyam-internal"); register the same tool functions;
#                    app.mount(INTERNAL_PREFIX, internal.streamable_http_app())
#
# (3) Add the middleware once:
#
#       app.add_middleware(InternalMCPAuth)                                        # <-- your app
#
# Log request.state.service_caller with each tool call for auditing.
# ---------------------------------------------------------------------------------------------
