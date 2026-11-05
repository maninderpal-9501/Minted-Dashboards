"""Minted pages server (Option A: this server is an MCP client of the Ekyam Dev MCP server).

Run locally:   uvicorn app.main:app --reload --port 8000
Docker:        docker compose up --build
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import config
from .mcp_client import ToolUnavailable, describe, mcp
from .routes_downloads import router as downloads_router
from .routes_excel import router as excel_router
from .routes_pages import router as pages_router
from .routes_status import router as status_router
from .warmup import run_warmup, start_scheduler

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("minted")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("MCP server: %s (auth: %s) · settings from: %s · sign-in: %s%s", config.MCP_URL, config.MCP_AUTH_MODE,
             config.SETTINGS_SOURCE, "on" if config.DEMO_KEY else "off",
             f" (MINTED_DEMO_KEY from {config.DEMO_KEY_SOURCE})" if config.DEMO_KEY else "")
    if config.ON_AZURE and config.DOTENV_FOUND:
        log.warning("A .env file was deployed with the code; it is ignored on Azure. Remove it (it may hold secrets).")
    sched = start_scheduler()
    warm = asyncio.create_task(run_warmup(reason="startup")) if config.WARMUP_ON_STARTUP else None
    yield
    if warm and not warm.done():
        warm.cancel()
    if sched:
        sched.shutdown(wait=False)
    await mcp.close()


app = FastAPI(title="Minted pages server", version="1.0", lifespan=lifespan,
              docs_url="/minted/api/docs", openapi_url="/minted/api/openapi.json")
app.include_router(pages_router)
app.include_router(excel_router)
app.include_router(downloads_router)
app.include_router(status_router)


@app.get("/healthz", tags=["health"])
def healthz():
    """Liveness: the web server is up (does not touch the MCP server). Used by Docker / Azure."""
    return {"ok": True, "sign_in_required": bool(config.DEMO_KEY), "sign_in_setting": config.SIGN_IN,
            "demo_key_from": config.DEMO_KEY_SOURCE, "mcp_url": config.MCP_URL, "mcp_auth": config.MCP_AUTH_MODE,
            "on_azure": config.ON_AZURE, "settings_from": config.SETTINGS_SOURCE,
            "dotenv_file_deployed": config.DOTENV_FOUND}


@app.get("/readyz", tags=["health"])
async def readyz():
    """Readiness: can we reach the MCP server, and does it expose every tool we need?"""
    try:
        names = set(await mcp.list_tools())
    except ToolUnavailable as e:
        return JSONResponse({"ok": False, "mcp_url": config.MCP_URL, "error": str(e)}, 503)
    except Exception as e:
        await mcp.reset()
        return JSONResponse({"ok": False, "mcp_url": config.MCP_URL, "error": describe(e)}, 503)
    missing = sorted(config.ALLOWED_TOOLS - names)
    return JSONResponse({"ok": not missing, "mcp_url": config.MCP_URL, "server": mcp.server_info,
                         "auth": config.MCP_AUTH_MODE, "missing_tools": missing}, 200 if not missing else 503)