"""Minted's Excel files, built on the server (same layouts as the pages' Download Excel buttons).

POST /minted/api/excel/everyday   body: minted_build_everyday_po input  (default {"include": "all_needed"})
POST /minted/api/excel/seasonal   body: minted_build_seasonal_po input  (default {"program": "Holiday"})
POST /minted/api/excel/tracker    body: minted_billing_report input     (default {"limit": 1000})
                                  ?rows=new|all|differs|matches|cancelled   (default new)
GET  the same URLs downloads with the defaults (handy from a browser); tracker also takes ?month=YYYY-MM

The files are drafts: the Everyday and Seasonal POs are approved by a person before they go to Marathon.
"""
import asyncio
import json
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from . import config
from . import minted_xlsx as mx
from .mcp_client import ToolUnavailable, payload, tool_json
from .signin import current_user

router = APIRouter(prefix="/minted/api/excel")

KINDS = {
    "everyday": ("minted_build_everyday_po", {"include": "all_needed"}),
    "seasonal": ("minted_build_seasonal_po", {"program": "Holiday"}),
    "tracker": ("minted_billing_report", {"limit": 1000}),
}
ROWS = {"new", "all", "differs", "matches", "cancelled"}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _build(kind: str, p: dict, rows: str, folder: Path) -> tuple[Path, dict]:
    if kind == "everyday":
        wb, name, info = mx.everyday(p)
    elif kind == "seasonal":
        wb, name, info = mx.seasonal(p)
    else:
        wb, name, info = mx.tracker(p, rows)
    path = folder / name
    wb.save(path)
    info["recalculated"] = mx.recalc(str(path)) if config.EXCEL_RECALC else False
    return path, info


async def _excel(kind: str, args: dict, rows: str, background: BackgroundTasks):
    if kind not in KINDS:
        raise HTTPException(404, "kind must be everyday, seasonal or tracker")
    if rows not in ROWS:
        raise HTTPException(400, "rows must be new, all, differs, matches or cancelled")
    tool, defaults = KINDS[kind]
    try:
        data = payload(await tool_json(tool, {**defaults, **args}))
    except ToolUnavailable as e:
        return JSONResponse({"success": False, "error": f"MCP call failed: {e}"}, 502)
    if not data.get("success", True):
        return JSONResponse({"success": False, "error": data.get("error", "The tool did not succeed.")}, 422)

    tmp = tempfile.TemporaryDirectory()
    background.add_task(tmp.cleanup)  # delete the file after it has been sent
    # openpyxl and LibreOffice are blocking: run them off the event loop
    path, info = await asyncio.to_thread(_build, kind, data, rows, Path(tmp.name))
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(path.name)}",
        "X-Minted-Info": json.dumps({k: v for k, v in info.items() if k != "file"}),
        "Cache-Control": "no-store",
    }
    return FileResponse(path, media_type=XLSX, headers=headers)


@router.post("/{kind}")
async def excel_post(kind: str, request: Request, background: BackgroundTasks,
                     rows: str = "new", user: str = Depends(current_user)):
    try:
        args = await request.json()
    except Exception:
        args = {}
    if not isinstance(args, dict):
        raise HTTPException(400, "Body must be a JSON object")
    return await _excel(kind, args, rows, background)


@router.get("/{kind}")
async def excel_get(kind: str, background: BackgroundTasks, rows: str = "new", month: str = "",
                    user: str = Depends(current_user)):
    args = {"month": month} if (kind == "tracker" and month) else {}
    return await _excel(kind, args, rows, background)
