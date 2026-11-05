"""Downloads page: Minted's Excel files from buttons.

GET /minted/downloads   page with the Everyday PO, Seasonal PO and PO Tracker rows, each with its options.
The buttons call the Excel endpoints in routes_excel.py (POST /minted/api/excel/{kind}).
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .signin import is_signed_in

router = APIRouter()


@router.get("/minted/downloads", response_class=HTMLResponse, include_in_schema=False)
def downloads_page(request: Request):
    if not is_signed_in(request):
        return HTMLResponse("<p>Open a Minted page with <code>?key=&lt;demo key&gt;</code> first.</p>", 401)
    return HTMLResponse(PAGE, headers={"Cache-Control": "no-store"})


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Minted · Excel downloads</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Inter+Tight:wght@600;700&display=swap" rel="stylesheet">
<style>
:root{color-scheme:light;--bg:#f5f8fc;--card:#fff;--line:#e3e8f0;--line2:#eef2f7;--ink:#16202e;--ink2:#3b4656;--mut:#5d6878;
--blu:#2f6fed;--blu-bg:#eaf1fe;--navy:#111827;--grn:#127a57;--grn-bg:#e6f4ee;--amb:#a8580a;--amb-bg:#fdf1e3;--red:#c62828;--red-bg:#fdecec;
--display:"Inter Tight",Inter,system-ui,-apple-system,"Segoe UI",sans-serif;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
.top{display:flex;align-items:center;gap:12px;padding:12px 20px;background:var(--card);border-bottom:1px solid var(--line)}
.top .brand{font:700 15px var(--display);letter-spacing:.02em}.top .sep{width:1px;height:20px;background:var(--line)}
.top .ctx{color:var(--mut);font-size:13px}.top .ctx b{color:var(--ink);font-weight:600}
.top .links{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}
.eyebrow{color:var(--blu);font-size:11.5px;font-weight:600;letter-spacing:.06em;text-transform:uppercase}
h1{font:700 26px/1.2 var(--display);margin:4px 0 6px}.lede{color:var(--ink2);margin:0 0 20px;max-width:760px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;align-items:start}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;display:flex;flex-direction:column}
.card-h{padding:16px 18px 12px;border-bottom:1px solid var(--line2)}
.card-h .tag{display:inline-block;font:600 11px var(--mono);color:var(--blu);background:var(--blu-bg);border-radius:6px;padding:2px 7px;margin-bottom:8px}
.card-h h2{font:600 17px/1.3 var(--display);margin:0 0 4px}.card-h p{margin:0;color:var(--ink2);font-size:13px}
.card-b{padding:14px 18px;display:grid;gap:12px}
.card-f{padding:14px 18px 18px;border-top:1px solid var(--line2);display:grid;gap:10px;margin-top:auto}
label.fld{display:grid;gap:4px;font-size:12px;color:var(--mut);font-weight:500}
label.fld input,label.fld select{font:14px Inter,sans-serif;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 10px;background:#fff;width:100%}
label.fld input:focus,label.fld select:focus{outline:2px solid var(--blu-bg);border-color:var(--blu)}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;flex-wrap:wrap}
.seg button{border:0;background:#fff;color:var(--ink2);font:500 13px Inter,sans-serif;padding:7px 11px;cursor:pointer;border-right:1px solid var(--line)}
.seg button:last-child{border-right:0}.seg button.on{background:var(--navy);color:#fff}
.segwrap{display:grid;gap:4px}.segwrap .l{font-size:12px;color:var(--mut);font-weight:500}
.hint{font-size:12px;color:var(--mut);margin:0}
.btn{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:9px;padding:8px 13px;font:500 13px Inter,sans-serif;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:8px;justify-content:center}
.btn.pri{background:var(--navy);border-color:var(--navy);color:#fff;padding:11px 14px;font-size:14px;font-weight:600}
.btn.pri:hover{background:#1f2937}.btn:disabled{opacity:.6;cursor:wait}
.spin{width:14px;height:14px;border:2px solid rgba(255,255,255,.35);border-top-color:#fff;border-radius:50%;animation:s .8s linear infinite;display:none}
.busy .spin{display:inline-block}@keyframes s{to{transform:rotate(360deg)}}
.msg{border-radius:10px;padding:9px 12px;font-size:13px}.msg.ok{background:var(--grn-bg);color:var(--grn)}
.msg.err{background:var(--red-bg);color:var(--red)}.msg.note{background:var(--amb-bg);color:var(--amb)}
.res{display:none}.res.show{display:block}
.res dl{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;margin:6px 0 0}.res dt{color:inherit;opacity:.8}.res dd{margin:0;font-weight:600;font-variant-numeric:tabular-nums}
.foot{margin-top:22px;color:var(--mut);font-size:12.5px;max-width:860px}
@media (max-width:420px){.row2{grid-template-columns:1fr}.top .links{display:none}h1{font-size:22px}}
</style></head><body>
<div class="top"><span class="brand">EKYAM</span><span class="sep"></span>
<span class="ctx"><b>Minted</b> · DoorDash greeting cards</span>
<span class="links"><a class="btn" href="/minted/control-tower.html">Control Tower</a><a class="btn" href="/minted/status">Server status</a></span></div>
<main>
<div class="eyebrow">Downloads</div>
<h1>Minted Excel files</h1>
<p class="lede">Minted's own files, built from live Ekyam data in Minted's template layouts. Choose the options and press the button; the file downloads to your computer.</p>

<div class="grid">

<section class="card" data-kind="everyday">
 <div class="card-h"><span class="tag">DDEDmmddyy.xlsx</span><h2>Everyday PO to Marathon</h2>
 <p>Restocks single cards at CTL. Quantities come from the reorder plan, rounded up to 240-card c-boxes.</p></div>
 <div class="card-b">
  <div class="segwrap"><span class="l">Which cards</span><div class="seg" data-name="include">
   <button class="on" data-v="all_needed">Every card short of target</button><button data-v="order_now">Only run-out-soon cards</button></div></div>
  <div class="row2">
   <label class="fld">Weeks of cover<input type="number" name="target_weeks" value="12" min="4" max="26"></label>
   <label class="fld">Lead time (weeks)<input type="number" name="lead_time_weeks" value="6" min="1" max="12"></label>
  </div>
  <label class="fld">PO date<input type="date" name="po_date"></label>
  <label class="fld">Own quantities (optional)<input type="text" name="lines" placeholder="843740132460DD:240, MIN-QAN-NCG:480"></label>
  <p class="hint">Leave quantities empty to use the reorder plan.</p>
 </div>
 <div class="card-f"><button class="btn pri dl"><span class="spin"></span><span class="t">Download Everyday PO</span></button>
  <div class="msg note">Draft: a person checks and approves it before it goes to Marathon.</div>
  <div class="res msg"></div></div>
</section>

<section class="card" data-kind="seasonal">
 <div class="card-h"><span class="tag">DDHOLmmddyy.xlsx</span><h2>Seasonal PO + Distribution</h2>
 <p>Marathon prints and ships straight to each DoorDash location. Mixed orders are left out and listed.</p></div>
 <div class="card-b">
  <div class="row2">
   <label class="fld">Program<select name="program">
    <option value="Holiday" data-code="HOL">Holiday</option><option value="Mother's Day" data-code="MD">Mother's Day</option>
    <option value="Graduation" data-code="GR">Graduation</option><option value="" data-code="">Any seasonal</option></select></label>
   <label class="fld">Season code<input type="text" name="season_code" value="HOL" maxlength="6"></label>
  </div>
  <div class="row2">
   <label class="fld">Orders from<input type="date" name="date_from"></label>
   <label class="fld">Orders to<input type="date" name="date_to"></label>
  </div>
  <div class="row2">
   <label class="fld">PO date<input type="date" name="po_date"></label>
   <label class="fld">Deliver by<input type="date" name="delivery_date"></label>
  </div>
  <p class="hint">Empty dates use the tool's defaults: all orders, PO dated today, delivery by the earliest due date.</p>
 </div>
 <div class="card-f"><button class="btn pri dl"><span class="spin"></span><span class="t">Download Seasonal PO</span></button>
  <div class="msg note">Draft: a person checks and approves it before it goes to Marathon.</div>
  <div class="res msg"></div></div>
</section>

<section class="card" data-kind="tracker">
 <div class="card-h"><span class="tag">PO Tracker rows</span><h2>Billing rows for accounting</h2>
 <p>Rows for the PO Tracker tab of the BD Wholesale &amp; Accounting tracker, one per DoorDash PO placed in the month.</p></div>
 <div class="card-b">
  <label class="fld">Month<input type="month" name="month"></label>
  <p class="hint">Empty = the latest month with order detail.</p>
  <div class="segwrap"><span class="l">Rows</span><div class="seg" data-name="rows">
   <button class="on" data-v="new">To add</button><button data-v="differs">Differ</button><button data-v="all">All</button>
   <button data-v="matches">Match</button><button data-v="cancelled">Cancelled</button></div></div>
  <p class="hint">“To add” is what accounting pastes: POs not in the tracker yet.</p>
 </div>
 <div class="card-f"><button class="btn pri dl"><span class="spin"></span><span class="t">Download tracker rows</span></button>
  <div class="res msg"></div></div>
</section>

</div>
<p class="foot">Files are built on the server from the same Minted tools the pages use (minted_build_everyday_po, minted_build_seasonal_po, minted_billing_report), so the numbers agree with the Control Tower, Reorder Planner and Billing Check.</p>
</main>
<script>
var LABEL={cards:"Cards",subtotal:"Print subtotal",packaging:"Packaging",total:"Total",rows:"Rows"};
var MONEY={subtotal:1,packaging:1,total:1};
function money(v){return "$"+Number(v).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}

document.querySelectorAll(".seg").forEach(function(seg){
 seg.addEventListener("click",function(e){var b=e.target.closest("button");if(!b)return;
  seg.querySelectorAll("button").forEach(function(x){x.classList.toggle("on",x===b)})})});

var prog=document.querySelector('[data-kind="seasonal"] select[name="program"]');
prog.addEventListener("change",function(){var c=prog.selectedOptions[0].getAttribute("data-code");
 if(c)document.querySelector('[data-kind="seasonal"] input[name="season_code"]').value=c});

function collect(card){
 var body={},query="";
 card.querySelectorAll("input[name],select[name]").forEach(function(el){
  var v=el.value.trim();if(v==="")return;
  body[el.name]=el.type==="number"?Number(v):v});
 card.querySelectorAll(".seg").forEach(function(seg){
  var v=seg.querySelector("button.on").getAttribute("data-v"),n=seg.getAttribute("data-name");
  if(n==="rows")query="?rows="+encodeURIComponent(v);else body[n]=v});
 if(card.dataset.kind==="everyday"&&body.lines)delete body.include;
 if(card.dataset.kind==="seasonal"&&!("program" in body))body.program="";
 if(card.dataset.kind==="tracker")body.limit=1000;
 return {body:body,query:query};
}

function filename(res,fallback){
 var cd=res.headers.get("Content-Disposition")||"",m=cd.match(/filename\\*=UTF-8''([^;]+)/i)||cd.match(/filename="?([^";]+)"?/i);
 return m?decodeURIComponent(m[1]):fallback}

function show(box,cls,html){box.className="res msg show "+cls;box.innerHTML=html}

document.querySelectorAll(".card").forEach(function(card){
 var btn=card.querySelector(".dl"),box=card.querySelector(".res"),txt=btn.querySelector(".t"),label=txt.textContent;
 btn.addEventListener("click",function(){
  var req=collect(card);
  btn.disabled=true;btn.classList.add("busy");txt.textContent="Building the file…";box.className="res msg";
  fetch("/minted/api/excel/"+card.dataset.kind+req.query,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(req.body)})
  .then(function(res){
   if(res.status===401)throw new Error("You are not signed in. Open a Minted page with your key first.");
   if(!res.ok)return res.json().catch(function(){return{}}).then(function(j){throw new Error(j.error||j.detail||("The server answered "+res.status))});
   var info={};try{info=JSON.parse(res.headers.get("X-Minted-Info")||"{}")}catch(e){}
   var name=filename(res,card.dataset.kind+".xlsx");
   return res.blob().then(function(b){
    var a=document.createElement("a");a.href=URL.createObjectURL(b);a.download=name;document.body.appendChild(a);a.click();
    setTimeout(function(){URL.revokeObjectURL(a.href);a.remove()},1500);
    var rows=Object.keys(LABEL).filter(function(k){return k in info}).map(function(k){
     return "<dt>"+LABEL[k]+"</dt><dd>"+(MONEY[k]?money(info[k]):Number(info[k]).toLocaleString("en-US"))+"</dd>"}).join("");
    var empty=(info.cards===0||info.rows===0)?'<div style="margin-top:6px">The file has no lines: the tool found nothing for these options.</div>':"";
    show(box,(info.cards===0||info.rows===0)?"note":"ok","<b>Downloaded "+esc(name)+"</b>"+(rows?"<dl>"+rows+"</dl>":"")+empty);
   })})
  .catch(function(e){show(box,"err",esc(e.message||String(e)))})
  .then(function(){btn.disabled=false;btn.classList.remove("busy");txt.textContent=label});
 });
});
</script></body></html>"""
