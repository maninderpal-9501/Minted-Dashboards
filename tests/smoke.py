"""Smoke test against a running server.

    python tests/smoke.py                       # http://localhost:8000
    python tests/smoke.py http://localhost:8000 --key <MINTED_DEMO_KEY>
"""
import sys
import time

import httpx

BASE = next((a for a in sys.argv[1:] if a.startswith("http")), "http://localhost:8000").rstrip("/")
KEY = sys.argv[sys.argv.index("--key") + 1] if "--key" in sys.argv else ""
PAGES = ["control-tower", "order-journey", "mixed-orders", "weekly-shipped",
         "reorder-planner", "billing-check", "graph-census"]
failures = 0


def check(name, ok, detail=""):
    global failures
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


with httpx.Client(base_url=BASE, timeout=200, follow_redirects=True) as c:
    if KEY:
        c.get(f"/minted/control-tower.html?key={KEY}")

    r = c.get("/healthz"); check("healthz", r.status_code == 200)
    r = c.get("/readyz"); check("readyz (MCP reachable, all tools present)", r.status_code == 200, r.text[:200])

    for p in PAGES:
        r = c.get(f"/minted/{p}.html")
        check(f"page {p}", r.status_code == 200 and 'name="minted-endpoint" content="/' in r.text)

    t = time.time()
    r = c.post("/minted/api/tools/minted_reorder_plan", json={"target_weeks": 12, "lead_time_weeks": 6})
    check("tool minted_reorder_plan", r.status_code == 200 and r.json().get("success", True) is not False,
          f"{time.time() - t:.1f}s")
    r = c.post("/minted/api/tools/not_a_minted_tool", json={})
    check("unknown tool refused", r.status_code == 403)

    for kind in ("everyday", "seasonal", "tracker"):
        r = c.get(f"/minted/api/excel/{kind}")
        check(f"excel {kind}", r.status_code == 200 and r.content[:2] == b"PK",
              r.headers.get("content-disposition", r.text[:120]))

    r = c.post("/minted/api/warmup")
    rep = r.json() if r.status_code == 200 else {}
    check("warm-up", rep.get("ready") is True, rep.get("verdict", r.text[:200]))

print("\nAll good." if not failures else f"\n{failures} check(s) failed.")
sys.exit(1 if failures else 0)
