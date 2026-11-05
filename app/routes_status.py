"""Warm-up and status.

POST /minted/api/warmup?refresh=false   run the warm-up now (refresh=true recomputes, e.g. right after a data reload)
GET  /minted/api/status                 last warm-up report as JSON
GET  /minted/status                     the same as a page
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from . import config
from .signin import current_user, is_signed_in
from .warmup import STATE, run_warmup

router = APIRouter()


@router.post("/minted/api/warmup")
async def warmup_now(refresh: bool = False, user: str = Depends(current_user)):
    return await run_warmup(refresh=refresh, reason=f"manual ({user})")


@router.get("/minted/api/status")
def status_json(user: str = Depends(current_user)):
    return {"running": STATE["running"], "schedule": config.WARMUP_CRON if config.WARMUP_ENABLED else None,
            "timezone": config.WARMUP_TZ, "report": STATE["report"]}


@router.get("/minted/status", response_class=HTMLResponse, include_in_schema=False)
def status_page(request: Request):
    if not is_signed_in(request):
        return HTMLResponse("<p>Open a Minted page with <code>?key=&lt;demo key&gt;</code> first.</p>", 401)
    return HTMLResponse(STATUS_HTML, headers={"Cache-Control": "no-store"})


STATUS_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Minted · Server status</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Inter+Tight:wght@600;700&display=swap" rel="stylesheet">
<style>
:root{color-scheme:light;--bg:#f5f8fc;--card:#fff;--line:#e3e8f0;--line2:#eef2f7;--ink:#16202e;--ink2:#3b4656;--mut:#5d6878;
--blu:#2f6fed;--blu-bg:#eaf1fe;--navy:#111827;--grn:#127a57;--grn-bg:#e6f4ee;--amb:#a8580a;--amb-bg:#fdf1e3;--red:#c62828;--red-bg:#fdecec;
--display:"Inter Tight",Inter,system-ui,sans-serif;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}.eyebrow{color:var(--blu);font-size:11.5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase}
h1{font:700 24px/1.2 var(--display);margin:4px 0 6px}.lede{color:var(--ink2);margin:0 0 18px}
.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:16px}
.btn{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:7px 12px;font:500 13px Inter,sans-serif;cursor:pointer}
.btn.pri{background:var(--navy);border-color:var(--navy);color:#fff}.btn:disabled{opacity:.5;cursor:wait}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:16px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}.kpi .l{color:var(--mut);font-size:12px}
.kpi .v{font:700 22px/1.3 var(--display)}.kpi .v.sm{font-size:15px;font-weight:600}.good{color:var(--grn)}.warn{color:var(--amb)}.bad{color:var(--red)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:16px}.card-h{padding:12px 16px;border-bottom:1px solid var(--line2)}
.card-h h2{font:600 15px var(--display);margin:0}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:7px 12px;border-bottom:1px solid var(--line2);vertical-align:top}th{color:var(--mut);font-weight:500;white-space:nowrap}
.num{text-align:right;font-variant-numeric:tabular-nums}.mono{font-family:var(--mono);font-size:12px}
.pill{display:inline-block;border-radius:99px;padding:1px 9px;font-size:12px;font-weight:500;white-space:nowrap}
.p-grn{background:var(--grn-bg);color:var(--grn)}.p-red{background:var(--red-bg);color:var(--red)}.p-amb{background:var(--amb-bg);color:var(--amb)}.p-gry{background:var(--line2);color:var(--mut)}
.msg{border-radius:10px;padding:10px 14px;margin-bottom:16px}.msg.ok{background:var(--grn-bg);color:var(--grn)}.msg.err{background:var(--red-bg);color:var(--red)}.msg.info{background:var(--blu-bg);color:var(--ink2)}
a{color:var(--blu)}
</style></head><body><main>
<div class="eyebrow">Minted · DoorDash greeting cards</div><h1>Server status</h1>
<p class="lede">Warm-up of every Minted tool with the pages' exact inputs, and cross-checks between tools. Replaces the “warm the Minted caches” chore before a demo.</p>
<div class="bar"><button class="btn pri" id="run">Run warm-up now</button><button class="btn" id="refresh">Recompute (after a data reload)</button>
<a class="btn" href="/minted/control-tower.html" style="text-decoration:none">Open Control Tower</a></div>
<div id="verdict" class="msg info">Loading…</div><div class="kpis" id="kpis"></div>
<div class="card"><div class="card-h"><h2>Cross-checks</h2></div><div class="scroll"><table id="checks"></table></div></div>
<div class="card"><div class="card-h"><h2>Tool calls</h2></div><div class="scroll"><table id="tools"></table></div></div>
</main><script>
var $=function(i){return document.getElementById(i)};
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function pill(ok,yes,no){return '<span class="pill '+(ok?'p-grn':'p-red')+'">'+(ok?yes:no)+'</span>'}
function show(s){var r=s.report;
 if(!r){$("verdict").className="msg info";$("verdict").textContent=s.running?"Warm-up is running…":"No warm-up has run yet. Press “Run warm-up now”.";$("kpis").innerHTML="";$("checks").innerHTML="";$("tools").innerHTML="";return}
 $("verdict").className="msg "+(r.ready?"ok":"err");$("verdict").textContent=(s.running?"Running again… · ":"")+r.verdict;
 var ok=r.tools.filter(function(t){return t.ok}).length,cached=r.tools.filter(function(t){return t.cached===true}).length,mm=r.checks.filter(function(c){return c.status==="mismatch"}).length;
 $("kpis").innerHTML=[["Tool calls OK",ok+" / "+r.tools.length,ok===r.tools.length?"good":"bad"],["Served from cache",cached,""],["Checks disagreeing",mm,mm?"bad":"good"],
  ["Took",r.seconds+" s",""],["Last run",new Date(r.finished_at).toLocaleString(),"sm"],["Schedule",s.schedule?s.schedule+" ("+s.timezone+")":"off","sm"]]
  .map(function(k){return '<div class="kpi"><div class="l">'+k[0]+'</div><div class="v '+k[2]+'">'+esc(k[1])+'</div></div>'}).join("");
 $("checks").innerHTML="<tr><th>Check</th><th>Result</th><th>Detail</th></tr>"+r.checks.map(function(c){
  var p=c.status==="ok"?'<span class="pill p-grn">OK</span>':c.status==="mismatch"?'<span class="pill p-red">Disagrees</span>':'<span class="pill p-gry">Skipped</span>';
  return "<tr><td>"+esc(c.check)+"</td><td>"+p+"</td><td>"+esc(c.detail)+"</td></tr>"}).join("");
 $("tools").innerHTML="<tr><th>Tool</th><th>Inputs</th><th>Used by</th><th>Result</th><th class=num>Seconds</th><th>Cached</th><th>Error</th></tr>"+r.tools.map(function(t){
  return '<tr><td class="mono">'+esc(t.tool)+'</td><td class="mono">'+esc(JSON.stringify(t.inputs).slice(0,90))+"</td><td>"+esc(t.used_by)+"</td><td>"+pill(t.ok,"OK","Failed")+
  '</td><td class="num">'+t.seconds+"</td><td>"+(t.cached===true?"yes":t.cached===false?"no":"–")+"</td><td>"+esc(t.error||"")+"</td></tr>"}).join("")}
function load(){return fetch("/minted/api/status").then(function(r){return r.json()}).then(show).catch(function(e){$("verdict").className="msg err";$("verdict").textContent="Could not load status: "+e})}
function run(refresh){$("run").disabled=$("refresh").disabled=true;$("verdict").className="msg info";$("verdict").textContent="Warm-up running… (a cold cache can take a minute)";
 fetch("/minted/api/warmup?refresh="+refresh,{method:"POST"}).then(function(r){return r.json()}).then(function(){return load()})
 .catch(function(e){$("verdict").className="msg err";$("verdict").textContent="Warm-up failed: "+e}).then(function(){$("run").disabled=$("refresh").disabled=false})}
$("run").onclick=function(){run(false)};$("refresh").onclick=function(){if(confirm("Recompute every tool, ignoring the cache?"))run(true)};
load();
</script></body></html>"""
