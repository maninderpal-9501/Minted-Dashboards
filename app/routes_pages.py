"""The seven Minted pages and the endpoint they call for data.

GET  /minted/<page>.html        page, with <meta name="minted-endpoint"> filled in (switches it to server mode)
POST /minted/api/tools/<tool>   body = tool input JSON  ->  the tool's JSON, exactly as the MCP server returns it
"""
import logging
import time
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import config
from .mcp_client import ToolUnavailable, tool_json
from .signin import COOKIE, current_user, is_signed_in

log = logging.getLogger("minted.pages")
router = APIRouter()

PAGES = ["control-tower", "order-journey", "mixed-orders", "weekly-shipped",
         "reorder-planner", "billing-check", "graph-census"]
EMPTY_META = '<meta name="minted-endpoint" content="">'


@lru_cache(maxsize=None)
def _page_html(name: str, mtime: float) -> str:  # mtime in the key: a copied-in page is picked up without restart
    html = (config.PAGES_DIR / f"{name}.html").read_text(encoding="utf-8")
    if EMPTY_META not in html:
        raise RuntimeError(f"{name}.html has no empty minted-endpoint meta tag; copy the built file from dist/")
    html = html.replace(EMPTY_META, f'<meta name="minted-endpoint" content="{config.API_PATH}">', 1)
    return html.replace("</body>", SERVER_MENU + "</body>", 1) if "</body>" in html else html + SERVER_MENU


# Server-only additions to the pages' left menu: links to the Downloads and Status pages.
# Added while serving, so the built page files stay exactly as the plugin made them.
SERVER_MENU = """<script>
(function () {
  var LINKS = [
    { href: "/minted/downloads", title: "Excel downloads", icon: "M12 4v11M7 10l5 5 5-5M5 20h14" },
    { href: "/minted/status", title: "Server status", icon: "M3 12h4l3-8 4 16 3-8h4" }
  ];
  function svg(d) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' + d + '"/></svg>'; }
  function add() {
    var side = document.querySelector(".mn-side");
    if (!side || side.querySelector(".mn-server")) return !!side;
    var box = document.createElement("div"); box.className = "mn-server";
    box.innerHTML = '<div class="mn-grp">Server</div>' + LINKS.map(function (l) {
      return '<a class="mn-a" href="' + l.href + '" title="' + l.title + '">' + svg(l.icon) + '<span class="mn-lab">' + l.title + "</span></a>";
    }).join("");
    side.insertBefore(box, side.querySelector(".mn-foot"));
    return true;
  }
  function start() {
    if (add()) return;
    var tries = 0, t = setInterval(function () { if (add() || ++tries > 40) clearInterval(t); }, 50);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
</script>
"""


@router.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/minted/control-tower.html")


@router.get("/minted/", include_in_schema=False)
def minted_root():
    return RedirectResponse("/minted/control-tower.html")


@router.get("/minted/{name}.html", response_class=HTMLResponse, include_in_schema=False)
def page(name: str, request: Request, key: str = ""):
    if name not in PAGES:
        raise HTTPException(404, "No such page")
    if config.DEMO_KEY and key:
        if key != config.DEMO_KEY:
            return HTMLResponse("<p>Wrong key.</p>", 401)
        resp = RedirectResponse(f"/minted/{name}.html")
        resp.set_cookie(COOKIE, config.DEMO_KEY, httponly=True, samesite="lax", max_age=7 * 86400)
        return resp
    if not is_signed_in(request):
        return HTMLResponse("<p>Open this link with <code>?key=&lt;demo key&gt;</code> to sign in.</p>", 401)
    path = config.PAGES_DIR / f"{name}.html"
    return HTMLResponse(_page_html(name, path.stat().st_mtime), headers={"Cache-Control": "no-store"})


@router.post(config.API_PATH + "/{tool}")
async def call_tool(tool: str, request: Request, user: str = Depends(current_user)):
    if tool not in config.ALLOWED_TOOLS:
        raise HTTPException(403, f"Tool {tool} is not allowed")
    try:
        args = await request.json()
    except Exception:
        args = {}
    if not isinstance(args, dict):
        raise HTTPException(400, "Body must be a JSON object")

    t = time.time()
    try:
        data = await tool_json(tool, args)
    except ToolUnavailable as e:
        log.error("tool=%s user=%s unavailable: %s", tool, user, e)
        return JSONResponse({"success": False, "error": f"MCP call failed: {e}"}, 502)
    log.info("tool=%s user=%s ok=%s %.1fs", tool, user, data.get("success", True), time.time() - t)
    return data  # tool errors come back as {"success": false, ...} with 200, which the pages show in place