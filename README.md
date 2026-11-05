# Minted pages server (FastAPI + uvicorn, Option A: MCP client)

Serves the seven Minted × DoorDash pages, Minted's Excel files and a warm-up/status page.
All data comes from the nine Minted tools (plus `cypher_chain`) on the **Ekyam Dev MCP server**;
this server is an MCP client, exactly like the claude.ai connector. No chat.

```
Browser ──► FastAPI (this project) ──MCP over HTTPS + OAuth token──► Ekyam Dev MCP server ──► Neo4j / Redis
```

## 1. Run locally (Python)

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                       # then edit .env
uvicorn app.main:app --reload --port 8000
```

Open, in this order:

| URL | What you should see |
|---|---|
| http://localhost:8000/readyz | `{"ok": true, "missing_tools": []}` — the MCP server is reachable and has every tool |
| http://localhost:8000/ | Control Tower (redirect), top bar says "Live from Ekyam" |
| http://localhost:8000/minted/status | Warm-up page → press **Run warm-up now** → "Ready for the demo" |
| http://localhost:8000/minted/api/docs | API docs (Swagger) |

Then `python tests/smoke.py` checks everything in one go (add `--key <MINTED_DEMO_KEY>` if you set one).

### Without access to the real MCP server yet

A fake MCP server with the same ten tools (answers are the tools' documented example outputs) and the
same OAuth client-credentials sign-in as Ekyam is included:

```bash
FAKE_CLIENT_ID=demo FAKE_CLIENT_SECRET=s3cret python tests/fake_mcp_server.py   # terminal 1, http://localhost:9000/mcp/
# .env:  EKYAM_MCP_URL=http://localhost:9000/mcp/  MCP_AUTH_MODE=oauth  MCP_OAUTH_CLIENT_ID=demo  MCP_OAUTH_CLIENT_SECRET=s3cret
uvicorn app.main:app --reload --port 8000                                         # terminal 2
```

### Getting the OAuth client for the real server

Create it once with the backend's admin API, **on the same host as `EKYAM_MCP_URL`**, and with the
least powerful role that can run tools (not `admin` if a lower role exists):

```bash
curl -X POST https://mcp-dev.ekyam.ai/admin/clients -H "Content-Type: application/json" \
  -H "x-admin-api-key: $ADMIN_KEY" -d '{"name": "minted-pages-server", "role": "<role>"}'
```

Put the returned id and secret in `.env` as `MCP_OAUTH_CLIENT_ID` / `MCP_OAUTH_CLIENT_SECRET`.
The server exchanges them for an access token, renews it before it expires, and retries once on a 401.

## 2. Run locally (Docker)

```bash
cp .env.example .env            # edit it
docker compose up --build       # http://localhost:8000
```

With the fake MCP server: set `EKYAM_MCP_URL=http://fake-mcp:9000/mcp/`, `MCP_AUTH_MODE=oauth`,
`MCP_OAUTH_CLIENT_ID=demo`, `MCP_OAUTH_CLIENT_SECRET=s3cret` in `.env`, then `docker compose --profile fake up --build`.

To recalculate Excel formulas on the server, build with LibreOffice (bigger image):
`docker build --build-arg WITH_LIBREOFFICE=1 -t minted-server .` (or set it in `docker-compose.yml`).
Without it the files are still correct: Excel recalculates the formulas when the file is opened.

## 3. Endpoints

| Method & path | Purpose |
|---|---|
| `GET /minted/<page>.html` | The seven pages: `control-tower`, `order-journey`, `mixed-orders`, `weekly-shipped`, `reorder-planner`, `billing-check`, `graph-census` |
| `POST /minted/api/tools/{tool}` | Body = tool input JSON → the tool's JSON (what the pages call). Only the ten allowed tools |
| `GET/POST /minted/api/excel/everyday` | DDED Everyday PO to Marathon (`minted_build_everyday_po`, default `{"include":"all_needed"}`) |
| `GET/POST /minted/api/excel/seasonal` | DDHOL Seasonal PO + Distribution tab (`minted_build_seasonal_po`, default `{"program":"Holiday"}`) |
| `GET/POST /minted/api/excel/tracker?rows=new` | PO Tracker rows (`minted_billing_report`); `rows=new\|all\|differs\|matches\|cancelled`; GET takes `?month=YYYY-MM` |
| `POST /minted/api/warmup?refresh=false` | Run the warm-up now (`refresh=true` recomputes, e.g. right after a data reload) |
| `GET /minted/api/status` · `GET /minted/status` | Last warm-up report (JSON · page) |
| `GET /healthz` | Liveness (web server up) |
| `GET /readyz` | Readiness (MCP reachable, every tool present) |

Excel responses carry an `X-Minted-Info` header with cards / print subtotal / packaging / total (or row count).
The POs are **drafts**: a person approves them before they go to Marathon.

Order Journey for one PO: `/minted/order-journey.html#POA000163948`.

## 4. Environment variables

| Variable | Default | Notes |
|---|---|---|
| `EKYAM_MCP_URL` | `https://mcp-dev.ekyam.ai/mcp` | Later: the backend's `/mcp-internal` URL |
| `MCP_AUTH_MODE` | `oauth` | `oauth` (Ekyam client credentials) · `api_key` · `entra` (Azure) · `none` |
| `MCP_OAUTH_CLIENT_ID` / `MCP_OAUTH_CLIENT_SECRET` | – | `oauth` mode: made with the backend's `/admin/clients` |
| `MCP_OAUTH_SCOPE` | `mcp.read` | Scope asked for with the token |
| `MCP_OAUTH_TOKEN_URL` | empty | Empty = discovered from `/.well-known/oauth-protected-resource` |
| `EKYAM_MCP_TOKEN` | – | Service token, `api_key` mode |
| `MCP_ENTRA_SCOPE` | – | `entra` mode, e.g. `api://ekyam-tools/.default` |
| `MCP_TIMEOUT_SECONDS` | `180` | Per tool call |
| `MINTED_PAGES_DIR` | `./pages` | The seven built HTML files |
| `MINTED_API_PATH` | `/minted/api/tools` | Written into each page's `minted-endpoint` meta tag |
| `MINTED_DEMO_KEY` | empty | Empty = open (local only). Set = open a page once with `?key=…` |
| `WARMUP_ENABLED` / `WARMUP_CRON` / `WARMUP_TZ` | `true` / `0 7 * * 1-5` / `Asia/Kolkata` | Scheduled warm-up |
| `WARMUP_ON_STARTUP` | `false` | Warm up as soon as the server starts |
| `WARMUP_CONCURRENCY` | `6` | Parallel tool calls during warm-up |
| `EXCEL_RECALC` | `true` | Uses LibreOffice when installed |
| `LOG_LEVEL` | `INFO` | |

## 5. How the MCP connection works

* One MCP session is opened on first use and shared by all requests (many calls run at once on it).
* The `Authorization` header is added to **every** HTTP request, so OAuth / Entra tokens renew by themselves.
* If the MCP server restarts, the session expires or a token is refused, the call fails fast and the
  next one reconnects (retried once). Pages show tool errors in place and retry once on 502.
* Tool errors come back as `{"success": false, "error": "..."}` with status 200; an unreachable MCP
  server is a 502 `MCP call failed: …` — read the message (401 = token, ConnectError = URL/network).

## 6. Updating the pages

`pages/` holds the built files from the plugin (`minted-pages/pages/dist/*.html`), **unchanged**.
The server fills in `<meta name="minted-endpoint">` while serving, which switches each page and the
left menu to server mode. To update: rebuild in the plugin (`build.py`), copy `dist/*.html` here.
`app/minted_xlsx.py` is the minted-excel skill's script; keep it in step with the pages' `minted-xlsx.js`.

## 7. Going to Azure (summary)

1. Backend: add `/mcp-internal` with service auth (see `backend_reference/mcp_internal.py`).
2. Entra ID: app registration for the backend (`api://ekyam-tools`) with app role `Tools.Read`.
3. Deploy this image to App Service or Container Apps, turn on **Managed Identity**, grant it `Tools.Read`.
4. Settings: `MCP_AUTH_MODE=entra`, `MCP_ENTRA_SCOPE=api://ekyam-tools/.default`, `EKYAM_MCP_URL=<backend>/mcp-internal`.
5. Replace `MINTED_DEMO_KEY` with real sign-in (App Service Easy Auth or Ekyam SSO; `app/signin.py` is the one place to change).
6. Keep one replica/worker for the scheduler, or set `WARMUP_ENABLED=false` on all but one.
