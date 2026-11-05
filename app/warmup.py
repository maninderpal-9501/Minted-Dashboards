"""Warm-up (the minted-warm-up skill as a server job).

Runs every Minted tool once with the exact inputs the seven pages use, so the tools' 24-hour
caches are warm and pages load instantly, then cross-checks the numbers between tools.
Checks compare relationships, not fixed numbers, because the numbers change after each data reload.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone

from . import config
from .mcp_client import ToolUnavailable, describe, payload, tool_json

log = logging.getLogger("minted.warmup")

CENSUS = {  # the Graph Census page's four fixed queries (sent as-is, so they hit the same cache)
    "totals": ("How many Minted records and links are in the graph",
               "MATCH (n:Minted) WITH count(n) AS nodes MATCH (:Minted)-[r]->(:Minted) RETURN nodes, count(r) AS rels LIMIT 1"),
    "kinds": ("How many Minted records of each kind are in the graph",
              "MATCH (n:Minted) UNWIND labels(n) AS l WITH l WHERE l <> 'Minted' RETURN l AS label, count(*) AS nodes ORDER BY nodes DESC LIMIT 50"),
    "links": ("How many links connect Minted records, counted by link and record kind",
              "MATCH (a:Minted)-[r]->(b:Minted) WITH type(r) AS rel, [x IN labels(a) WHERE x <> 'Minted'][0] AS from_label, "
              "[x IN labels(b) WHERE x <> 'Minted'][0] AS to_label RETURN rel, from_label, to_label, count(*) AS links ORDER BY links DESC LIMIT 100"),
    "iso": ("Count relationships between Minted nodes and nodes outside the Minted slice (isolation check)",
            "MATCH (a:Minted)-[r]-(b) WHERE NOT b:Minted RETURN count(r) AS links, count(DISTINCT a) AS minted_nodes_touching LIMIT 1"),
}

# (key, tool, inputs, used by) — inputs must match the pages exactly, or the page misses the cache
CALLS = [
    ("weekly_all", "minted_weekly_shipped_by_card", {}, "Control Tower, Weekly Shipped"),
    ("weekly_12", "minted_weekly_shipped_by_card", {"weeks": 12}, "Control Tower, Weekly Shipped"),
    ("reorder", "minted_reorder_plan", {"target_weeks": 12, "lead_time_weeks": 6}, "Control Tower, Reorder Planner"),
    ("reorder_w", "minted_reorder_plan", {"weeks": 12, "target_weeks": 12, "lead_time_weeks": 6}, "Reorder Planner"),
    ("orders_mixed", "minted_order_check", {"show": "mixed"}, "Control Tower"),
    ("orders_mixed50", "minted_order_check", {"show": "mixed", "limit": 50}, "Mixed-Order Alert"),
    ("orders_mixed1", "minted_order_check", {"show": "mixed", "limit": 1}, "Order Journey"),
    ("orders_seasonal1", "minted_order_check", {"show": "seasonal", "limit": 1}, "Order Journey"),
    ("delivery200", "minted_delivery_status", {"limit": 200}, "Control Tower"),
    ("delivery1", "minted_delivery_status", {"limit": 1}, "Order Journey"),
    ("billing", "minted_billing_report", {"limit": 1000}, "Control Tower, Billing Check"),
    ("billing_new1", "minted_billing_report", {"rows": "new", "limit": 1}, "Order Journey"),
    ("billing_page", "minted_billing_report", {"rows": "all", "offset": 470, "limit": 80}, "Billing Check"),
    ("locations", "minted_cards_by_location", {"weeks": 12, "top_n": 15}, "Weekly Shipped"),
    ("locations_card", "minted_cards_by_location", {"card": "843740116316DD", "weeks": 12, "top_n": 15}, "Weekly Shipped"),
    ("seasonal_po", "minted_build_seasonal_po", {"program": "Holiday", "po_date": "2025-10-23"}, "Control Tower"),
    ("trace_1", "minted_order_trace", {"po_number": "POA000163948"}, "Order Journey"),
    ("trace_2", "minted_order_trace", {"po_number": "POA000087985"}, "Order Journey"),
] + [(f"census_{k}", "cypher_chain", {"user_input": ask, "cypher": cy}, "Graph Census") for k, (ask, cy) in CENSUS.items()]

STATE: dict = {"running": False, "report": None}
_lock = asyncio.Lock()


async def _one(sem: asyncio.Semaphore, key: str, tool: str, args: dict, used_by: str, refresh: bool) -> dict:
    inputs = dict(args, refresh=True) if refresh and tool != "cypher_chain" and tool != "minted_order_trace" else args
    async with sem:
        t = time.time()
        try:
            data = payload(await tool_json(tool, inputs))
            ok, err = bool(data.get("success", True)), data.get("error")
        except ToolUnavailable as e:
            data, ok, err = {}, False, str(e)
        except Exception as e:  # never let one tool break the report
            data, ok, err = {}, False, describe(e)
    return {"key": key, "tool": tool, "inputs": args, "used_by": used_by, "ok": ok, "error": err,
            "seconds": round(time.time() - t, 1), "cached": data.get("cached"), "_data": data}


def _num(d: dict, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d if isinstance(d, (int, float)) else None


def _check(name: str, ok: bool | None, detail: str) -> dict:
    return {"check": name, "status": "skipped" if ok is None else ("ok" if ok else "mismatch"), "detail": detail}


def cross_checks(r: dict) -> list[dict]:
    """r maps call key -> tool data."""
    out = []

    w = _num(r.get("weekly_12", {}), "summary", "units_shipped")
    loc = r.get("locations", {}).get("summary", {}) if isinstance(r.get("locations"), dict) else {}
    l_all, l_with, l_without = _num(loc, "cards_shipped"), _num(loc, "cards_with_location"), _num(loc, "cards_without_location")
    out.append(_check("Weekly total = location tool total (12 weeks, all cards)",
                      None if w is None or l_all is None else w == l_all, f"weekly {w}, locations {l_all}"))
    out.append(_check("Location total = with location + without (sheet weeks)",
                      None if None in (l_all, l_with, l_without) else l_all == l_with + l_without,
                      f"{l_all} = {l_with} + {l_without}"))

    b = r.get("billing", {}).get("summary", {}) if isinstance(r.get("billing"), dict) else {}
    parts = [_num(b, k) for k in ("in_tracker_matching", "in_tracker_different", "not_in_tracker")]
    orders, cancelled = _num(b, "orders"), _num(b, "cancelled") or 0
    month = (r.get("billing", {}).get("period") or {}).get("month") if isinstance(r.get("billing"), dict) else None
    if None in parts or orders is None:
        out.append(_check("Billing: matches + to add + differs (+ cancelled) = POs", None, "billing summary missing"))
    else:
        s = sum(parts)
        out.append(_check(f"Billing {month or ''}: matches + to add + differs (+ cancelled) = POs".replace("  ", " "),
                          s == orders or s + cancelled == orders,
                          f"{parts[0]} + {parts[1]} + {parts[2]} (+ {cancelled} cancelled) vs {orders} POs"))

    sp = r.get("seasonal_po", {}).get("summary", {}) if isinstance(r.get("seasonal_po"), dict) else {}
    scope, on_po, excl = _num(sp, "orders_in_scope"), _num(sp, "orders_on_po"), _num(sp, "excluded_mixed")
    out.append(_check("Seasonal PO: on PO + excluded mixed = orders in scope",
                      None if None in (scope, on_po, excl) else on_po + excl == scope, f"{on_po} + {excl} = {scope}"))

    for k, po in (("trace_1", "POA000163948"), ("trace_2", "POA000087985")):
        d = r.get(k)
        out.append(_check(f"Trace {po} resolves", None if d is None else bool(d) and d.get("success", True) is not False,
                          "found" if d and d.get("success", True) is not False else (d or {}).get("error", "no answer")))

    iso = r.get("census_iso", {})
    rows = iso.get("results") if isinstance(iso, dict) else None
    links = _num(rows[0], "links") if rows else None
    out.append(_check("Isolation: no links from Minted to other data", None if links is None else links == 0,
                      f"{links} links"))
    return out


async def run_warmup(refresh: bool = False, reason: str = "manual") -> dict:
    if _lock.locked():
        return {"busy": True, **(STATE["report"] or {})}
    async with _lock:
        STATE["running"] = True
        started = time.time()
        try:
            sem = asyncio.Semaphore(config.WARMUP_CONCURRENCY)
            results = list(await asyncio.gather(*(_one(sem, *c, refresh) for c in CALLS)))
            # the Billing Check page also asks for the latest month by name: warm that key too
            month = (results[[c[0] for c in CALLS].index("billing")]["_data"].get("period") or {}).get("month")
            if month:
                results.append(await _one(sem, "billing_month", "minted_billing_report",
                                          {"month": month, "limit": 1000}, "Billing Check", refresh))
            data = {x["key"]: x["_data"] for x in results}
            checks = cross_checks(data)
            failed = [x for x in results if not x["ok"]]
            mism = [c for c in checks if c["status"] == "mismatch"]
            if not failed and not mism:
                verdict = "Ready for the demo"
            else:
                bits = []
                if failed:
                    bits.append(f"{len(failed)} tool call(s) failed ({', '.join(sorted({x['tool'] for x in failed}))}): "
                                "check the tool is enabled on the Ekyam Dev MCP server and the token is valid")
                if mism:
                    bits.append(f"{len(mism)} check(s) disagree: " + "; ".join(c["check"] for c in mism))
                verdict = " · ".join(bits)
            report = {
                "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "reason": reason, "refresh": refresh, "seconds": round(time.time() - started, 1),
                "ready": not failed and not mism, "verdict": verdict,
                "tools": [{k: v for k, v in x.items() if k != "_data"} for x in results],
                "checks": checks,
            }
            STATE["report"] = report
            log.info("warm-up (%s): %s in %.1fs", reason, verdict, report["seconds"])
            return report
        finally:
            STATE["running"] = False


def start_scheduler():
    """Runs the warm-up on WARMUP_CRON. Returns the scheduler (or None when disabled)."""
    if not config.WARMUP_ENABLED:
        return None
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = AsyncIOScheduler(timezone=config.WARMUP_TZ)
    sched.add_job(run_warmup, CronTrigger.from_crontab(config.WARMUP_CRON, timezone=config.WARMUP_TZ),
                  kwargs={"reason": "schedule"}, id="minted-warmup", max_instances=1, coalesce=True)
    sched.start()
    log.info("warm-up scheduled: '%s' (%s)", config.WARMUP_CRON, config.WARMUP_TZ)
    return sched
