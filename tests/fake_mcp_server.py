"""A stand-in for the Ekyam Dev MCP server, for testing this project without the real one.

It speaks real MCP (streamable HTTP) and exposes the same ten tool names, answering with each
tool's documented example output (tests/fixtures/tool_examples.json). Numbers are examples, not live data.

    python tests/fake_mcp_server.py                 # http://localhost:9000/mcp/  (no auth)
    FAKE_MCP_TOKEN=dev123 python tests/fake_mcp_server.py   # requires "Authorization: Bearer dev123"
    FAKE_CLIENT_ID=demo FAKE_CLIENT_SECRET=s3cret python tests/fake_mcp_server.py   # OAuth client credentials

Point the app at it with EKYAM_MCP_URL=http://localhost:9000/mcp/ (and MCP_AUTH_MODE / EKYAM_MCP_TOKEN to match).
"""
import base64
import contextlib
import secrets
import time
import copy
import json
import os
from pathlib import Path

import mcp.types as types
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

EXAMPLES = json.loads((Path(__file__).parent / "fixtures" / "tool_examples.json").read_text())
TOKEN = os.environ.get("FAKE_MCP_TOKEN", "")
# OAuth client credentials like the real Ekyam server (client made with /admin/clients)
CLIENT_ID = os.environ.get("FAKE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("FAKE_CLIENT_SECRET", "")
TOKEN_TTL = int(os.environ.get("FAKE_TOKEN_TTL", "3600"))
ISSUED: dict[str, float] = {}

CENSUS_ROWS = {
    "MATCH (n:Minted) WITH count(n)": [{"nodes": 48210, "rels": 131877}],
    "UNWIND labels(n)": [{"label": "SalesOrder", "nodes": 5041}, {"label": "Card", "nodes": 29}],
    "type(r) AS rel": [{"rel": "HAS_LINE", "from_label": "SalesOrder", "to_label": "OrderLine", "links": 9120}],
    "NOT b:Minted": [{"links": 0, "minted_nodes_touching": 0}],
}

server = Server("fake-ekyam-dev")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    tools = [types.Tool(name=n, description=f"(fake) {n}", inputSchema=v["params"]) for n, v in EXAMPLES.items()]
    tools.append(types.Tool(name="cypher_chain", description="(fake) run Cypher",
                            inputSchema={"type": "object", "properties": {"user_input": {"type": "string"},
                                                                          "cypher": {"type": "string"}}}))
    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "cypher_chain":
        cy = arguments.get("cypher", "")
        rows = next((r for k, r in CENSUS_ROWS.items() if k in cy), [])
        out = {"success": True, "results": rows}
    elif name in EXAMPLES:
        out = copy.deepcopy(EXAMPLES[name]["example"])
        if name == "minted_cards_by_location" and not arguments.get("card"):  # all cards: match the weekly total
            out["summary"].update(cards_shipped=9463, cards_with_location=8808, cards_without_location=655)
        if "cached" in out:
            out["cached"] = not arguments.get("refresh", False)
    else:
        raise ValueError(f"Unknown tool {name}")
    return [types.TextContent(type="text", text=json.dumps(out))]


manager = StreamableHTTPSessionManager(app=server)


async def handle(scope, receive, send):
    await manager.handle_request(scope, receive, send)


class BearerCheck(BaseHTTPMiddleware):
    """Accepts FAKE_MCP_TOKEN or an unexpired token from /token, on /mcp only."""
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/mcp") and (TOKEN or CLIENT_ID):
            tok = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            ok = (TOKEN and tok == TOKEN) or ISSUED.get(tok, 0) > time.time()
            if not ok:
                return JSONResponse({"error": "invalid_token"}, status_code=401,
                                    headers={"WWW-Authenticate": 'Bearer realm="FAKE"'})
        return await call_next(request)


async def protected_resource(request):
    base = f"{request.url.scheme}://{request.url.netloc}"
    return JSONResponse({"resource": base + "/mcp", "authorization_servers": [base],
                         "scopes_supported": ["mcp.read", "mcp.write"]})


async def auth_server(request):
    base = f"{request.url.scheme}://{request.url.netloc}"
    return JSONResponse({"issuer": base, "token_endpoint": base + "/token",
                         "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"]})


async def token(request):
    form = await request.form()
    cid, secret = form.get("client_id"), form.get("client_secret")
    if not cid and request.headers.get("authorization", "").startswith("Basic "):
        cid, _, secret = base64.b64decode(request.headers["authorization"][6:]).decode().partition(":")
    if form.get("grant_type") != "client_credentials" or not CLIENT_ID or (cid, secret) != (CLIENT_ID, CLIENT_SECRET):
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    tok = secrets.token_urlsafe(24)
    ISSUED[tok] = time.time() + TOKEN_TTL
    return JSONResponse({"access_token": tok, "token_type": "Bearer", "expires_in": TOKEN_TTL,
                         "scope": form.get("scope", "")})


@contextlib.asynccontextmanager
async def lifespan(app):
    async with manager.run():
        yield


app = Starlette(routes=[
    Route("/.well-known/oauth-protected-resource", protected_resource),
    Route("/.well-known/oauth-authorization-server", auth_server),
    Route("/token", token, methods=["POST"]),
    Mount("/mcp", app=handle),
], lifespan=lifespan)
app.add_middleware(BearerCheck)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "9000")))
