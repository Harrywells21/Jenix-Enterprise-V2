# JENIX Enterprise — Architecture

Internal reference document. Reflects the real, live-verified state of the codebase as of
2026-09-24. Every claim below is sourced directly from the actual source files (`server/main.py`,
`server/db.py`, `server/routes/*.py`, `master/master_server.py`, `server/ws/handler.py`) — nothing
in this document is inferred or assumed beyond what those files show.

## 1. System overview

JENIX Enterprise is a Linux/cross-platform IT fleet management and security platform with three
tiers:

- **Agent** — a Python process (`agent/`) installed on each managed machine. Connects outward to
  its assigned Floor server over a persistent WebSocket, reports metrics, and executes signed
  commands.
- **Floor server** — a FastAPI application (`server/`) that owns a SQLite database, authenticates
  users, terminates agent WebSocket connections, and exposes a REST API. Each floor is an
  independent deployment (its own DB, its own systemd service, its own venv). This installation
  runs two floors: Floor 1 (`~/Desktop/jenix/`, port 8000, git-tracked) and Floor 2
  (`~/Desktop/sales/jenix/`, port 8001, no git).
- **Master** — a separate FastAPI application (`master/`) that has no database of its own. It is a
  pure aggregation/control-plane layer: it logs into each configured floor's REST API with cached
  admin credentials, fans requests out to every floor in parallel, and merges the results into a
  single fleet-wide view. Port 9000.

A buyer receiving the full source gets all three tiers; Master is optional (a single floor can run
standalone) but is what turns N independent floors into one fleet.

## 2. Floor server (`server/`)

### 2.1 Application wiring (`main.py`)

- FastAPI app, version `2.0.0`, lifespan-managed startup: `init_db()` → start the offline
  watchdog background task → `init_scheduler()` → start the cleanup job (every 6h) → start the
  backup scheduler (every 24h).
- **Every REST router is mounted under a single global prefix: `/api`**
  (`app.include_router(router, prefix="/api")` in a loop over all 16 routers). This means every
  route path documented below is reached as `/api/<router-prefix>/<path>` — e.g. login is
  `POST /api/auth/login`, not `/auth/login`. This was confirmed live during the tests/ workstream:
  the un-prefixed path returns 405, the `/api`-prefixed path is the real one.
- A global `security_middleware` HTTP middleware runs on every request: applies an IP-based API
  rate limit (`rate_limit_api`, `security.py`) before the request reaches any route, and attaches
  `SECURITY_HEADERS` to every response.
- CORS is currently wide open (`allow_origins=["*"]`, all methods, all headers, credentials
  allowed) — acceptable for a single-tenant on-prem deployment, worth flagging to a buyer who
  plans to expose this beyond a private network.
- Two native WebSocket endpoints: `ws://.../ws/agent/{token}` (agent connections) and
  `ws://.../ws/dashboard` (dashboard live updates, token passed as a query param).
- Static/installer routes: `GET /install` and `GET /install/windows` serve the real
  `install_jenix.sh` / `install_jenix.ps1` scripts from the repo root (both were previously dead
  links — fixed and now live). `GET /agent-binary/{os_name}` serves a pre-built agent binary for
  `linux` / `macos` / `windows` from `releases/`. `/dashboard` and `/dashboard/{full_path}` serve
  the built React SPA (`static/index.html`); a catch-all SPA fallback route serves the same file
  for any unrecognized path, explicitly excluding `api/`, `static/`, `ws/`, and a few reserved
  exact paths so a typo'd API call still 404s instead of silently returning HTML.
- `GET /` serves a small self-contained marketing/landing page (inline HTML, not the SPA).
- `GET /health` returns `{status, app, version, time}` for uptime/monitoring checks.

### 2.2 Data model (`db.py`)

SQLite by default (`DATABASE_URL` env-overridable), WAL journal mode, `check_same_thread=False`.
Schema evolution is handled by an additive, idempotent `_migrate_schema()` run on every `init_db()`
call (checks `PRAGMA table_info` and `ALTER TABLE ... ADD COLUMN` for anything missing) rather than
a formal migrations tool — appropriate for a single-tenant SQLite deployment, worth noting for a
buyer used to Alembic-style migrations.

Tables (all SQLAlchemy declarative models):

| Table | Purpose |
|---|---|
| `users` | Login accounts. `role` is a free-text column with three conventions used in code: `admin` / `operator` / `viewer`. |
| `machines` | One row per enrolled agent. Tracks status (`online`/`offline`/`warning`/`pending`/`reassigning`/`reassigned`), a per-machine `action_passphrase_hash` gating destructive actions, version/upgrade state, checkpoint state, optional `site_id` grouping, and the last computed risk score. |
| `sites` | Simple named grouping for machines (no enforced FK from `machines.site_id` — matches the same loose-reference convention as `redirect_target_url`). |
| `metrics` | Time-series CPU/RAM/disk/network samples per machine, written on every `metrics` WebSocket message. |
| `commands` | Dispatched command log (`scan`/`boost`/`clean`/`fix`/`rollback`/etc.), with `output` populated as results stream back over the agent WebSocket. |
| `snapshots` | Filesystem snapshot IDs reported by an agent before a destructive action, for rollback. |
| `audit_logs` | Append-only action log. Every insert triggers a SQLAlchemy `after_insert` event that computes a SHA-256 `content_hash` over the row's fields (`compute_audit_hash`) and writes it back — this is the tamper-evidence mechanism the audit PDF report's integrity section is built on. |
| `schedules` | Recurring scan schedules per machine (`daily`/`weekly`, target hour). |
| `reports` | Generated PDF/report metadata; `report_type` distinguishes `single`-machine from `fleet`-wide, `machine_ids` is a comma-separated list for fleet reports. |
| `cve_scans` / `cve_findings` | CVE scan runs and their individual findings (package, version, CVE ID, severity). |
| `alerts` | Threshold-triggered alerts (cpu/ram/disk/offline/port), with a status workflow (`open` → `investigating`/`acknowledged`/`resolved`/`snoozed`) and optional assignment to a user. |
| `license` | A single perpetual/expiring license record (key, company name, max nodes). |
| `blacklisted_tokens` | Logged-out JWTs, checked on every authenticated request via `get_current_user`. |

A one-time, idempotent `backfill_audit_hashes()` runs on `init_db()` to compute `content_hash` for
any `audit_logs` rows that predate the column, so upgrading an existing install doesn't leave old
rows unverifiable.

`_seed_admin()` creates a default `admin@jenix.io` / `admin123` (env-overridable) admin user on
first run if the `users` table is empty.

### 2.3 Authentication (`auth.py` + `routes/auth.py`)

- Password hashing via `passlib`'s `CryptContext(schemes=["bcrypt"])`. The same pattern is
  duplicated in `db.py` (`hash_passphrase`/`verify_passphrase`) for the separate per-machine
  action-passphrase feature — two independent bcrypt contexts, not shared state.
- Access tokens are standard PyJWT bearer tokens (`HS256`, configurable secret/algorithm/expiry via
  env vars, default 24h expiry), carrying `sub` (user id) and `role`.
- A second, distinct token type exists purely for dashboard WebSocket auth
  (`create_ws_token`/`decode_ws_token`): 45-second expiry, tagged `purpose=ws_dashboard`, and
  explicitly rejected by `decode_ws_token` if that purpose tag doesn't match — so a leaked
  ws-token (e.g. via browser console or URL) can't be replayed against a normal REST endpoint.
- `get_current_user` checks the blacklist first, then decodes the token, then confirms the user
  still exists and `is_active` — so login itself already rejects deactivated users
  (`authenticate_user` checks `is_active`), and a still-valid token for a user deactivated
  mid-session is rejected on the very next request.
- Role enforcement is two flat dependency functions: `require_admin` (role must be exactly
  `admin`) and `require_operator` (role must be `admin` or `operator`) — there's no hierarchical
  permission system beyond these three fixed roles.
- Rate limiting on login specifically (`rate_limit_login`, keyed by client IP + username, separate
  from the global per-IP `rate_limit_api` middleware) — a 429 with a 1-minute retry hint.

Routes (all under `/api/auth`): `POST /login`, `POST /logout` (blacklists the token), `GET /me`,
`POST /ws-token`, `POST /change-password`, `GET /users` (admin-only), `POST /users` (admin-only),
`PATCH /users/{id}/deactivate` (admin-only), `PATCH /users/{id}/role` (admin-only).

### 2.4 WebSocket layer (`ws/handler.py`)

Two long-lived in-memory registries, module-level, not persisted: `_agents: Dict[token, WebSocket]`
and `_dashboards: list[WebSocket]`. This means agent/dashboard connection state does **not**
survive a server restart — an agent must reconnect, which it does automatically since it holds a
persistent outbound connection.

- **Agent connection** (`agent_endpoint`): on connect, looks up the machine by its enrollment
  token. A `pending` machine either gets redirected (if `redirect_target_url` is set — the
  cross-floor reassignment flow, see §3) or is disconnected with a specific close code. Otherwise
  status flips to `online` and `last_seen` updates. The main loop dispatches on message `type`:
  `metrics` (writes a `Metric` row, evaluates CPU/RAM/disk thresholds with a cooldown check
  (`should_create_alert`) before creating an `Alert`, and fires an async notification for
  high-severity ones), `command_result` / `cmd_output` (updates the matching `Command` row),
  `snapshot` (records a `Snapshot`), `checkpoint_status` (updates the machine's checkpoint fields),
  and `ping`/`pong` keepalive. On disconnect, status flips to `offline` — unless the disconnect was
  itself caused by a reassignment in progress, in which case status becomes `reassigned` instead
  and no offline alert fires (checked via a `StaleDataError`/`ObjectDeletedError`-safe query, since
  a reassigned machine's row may already be gone).
- **Dashboard connection** (`dashboard_endpoint`): requires a valid `ws_dashboard`-purpose token
  (see §2.3); otherwise just registers/deregisters itself in `_dashboards` and is a pure
  receive-only sink for the server's own broadcasts.
- **`_broadcast_dashboards`**: fire-and-forget push to every connected dashboard; connections that
  raise on send are pruned from the list on the same pass.
- **`offline_watchdog`**: background task, polls every 30s for any `online` machine whose
  `last_seen` is >35s stale, flips it to `offline`, raises an alert (cooldown-gated) and
  broadcasts the status change. This is what catches an agent that dropped without a clean
  WebSocket close.

### 2.5 REST route inventory

All paths below omit the `/api` prefix (see §2.1) for brevity — prepend `/api` to every path.

| Router (file) | Routes |
|---|---|
| `routes/auth.py` | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/ws-token`, `POST /auth/change-password`, `GET/POST /auth/users`, `PATCH /auth/users/{id}/deactivate`, `PATCH /auth/users/{id}/role` |
| `routes/agents.py` | `POST /agents/register`, `GET /agents`, `GET /agents/pending`, `GET /agents/install-command`, `POST /agents/{id}/approve`, `POST /agents/{id}/reject`, `GET/DELETE /agents/{id}`, `GET /agents/{id}/snapshots`, `POST/DELETE /agents/{id}/passphrase`, `GET /agents/{id}/passphrase-status`, `GET /agents/{id}/logs` |
| `routes/commands.py` | `POST /commands/{machine_id}/command`, `GET /commands/{machine_id}/command/{cmd_id}`, `GET /commands/{machine_id}/commands`, `GET /commands/history/all` |
| `routes/metrics.py` | `GET /metrics/{machine_id}/metrics`, `GET /metrics/{machine_id}/metrics/latest`, `GET /metrics/{machine_id}/alerts`, `PATCH /metrics/{machine_id}/alerts/{alert_id}/read` |
| `routes/reports.py` | `POST /reports/fleet`, `POST /reports/audit`, `GET /reports/audit/csv`, `GET /reports/{machine_id}/alerts/csv`, `POST /reports/{machine_id}`, `GET /reports`, `GET /reports/{id}/download`, `DELETE /reports/{id}` |
| `routes/audit.py` | `GET /audit/logs`, `GET /audit/logs/verify/{id}`, `GET /audit/logs/export` |
| `routes/audit_trail_report.py` | `POST /audit`, `GET /audit/csv` *(note: shares the `audit` path segment with `routes/audit.py` under a different router prefix — see the route-shadowing history in §5)* |
| `routes/schedules.py` | `GET/POST /schedules`, `DELETE /schedules/{id}`, `PATCH /schedules/{id}/toggle` |
| `routes/license.py` | `GET/DELETE /license`, `POST /license/activate`, `POST /license/generate` |
| `routes/analytics.py` | `GET /analytics/fleet`, `GET /analytics/fleet/compliance-score`, `GET /analytics/machine/{id}/score`, `GET /analytics/alerts/all`, `PATCH /analytics/alerts/{id}/status`, `PATCH /analytics/alerts/{id}/assign`, `POST /analytics/alerts/mark-all-read`, `GET /analytics/savings` |
| `routes/fleet.py` | `POST /fleet/command`, `GET /fleet/status` |
| `routes/cve.py` | `POST /cve/scan/{machine_id}`, `GET /cve/results/{machine_id}`, `GET /cve/summary`, `GET /cve/export/excel` |
| `routes/notify_settings.py` | `POST/GET /notify_settings/notifications`, `POST /notify_settings/notifications/test` |
| `routes/whitelabel.py` | `GET/POST /whitelabel`, `GET /whitelabel/public`, `POST /whitelabel/reset` |
| `routes/uptime.py` | `GET /uptime/{machine_id}`, `GET /uptime/fleet/summary` |
| `routes/backup.py` | `POST /backup/create`, `GET /backup/list`, `POST /backup/restore/{filename}` |
| `routes/sites.py` | `GET/POST /sites`, `DELETE /sites/{id}` |

## 3. Master control plane (`master/master_server.py`)

Master holds no business data. It:

1. Reads floor **topology** (name + URL only) from `floors.json`, and floor **credentials**
   separately from `floors_secrets.json`, which is Fernet-encrypted at rest (key in
   `floors_secrets.key`, both gitignored). The code's own header comment flags the known
   limitation directly: *"floors.json stores admin passwords in plaintext. For a real 40-floor
   deployment, replace with per-floor read-only/operator service accounts or API keys rather than
   full admin credentials."* — the encryption-at-rest split (secrets file separate from topology
   file) is already a mitigation of the original plaintext-everywhere design.
2. Logs into each floor's real `/api/auth/login` on demand, caches the returned bearer token
   per-floor-URL, and transparently refreshes it once on a 401 before retrying (`floor_request`).
   No changes are required on a floor server for Master to manage it — Master is a pure client of
   the same REST API a human admin would use.
3. Has its own **separate session-cookie auth** for the humans using the Master dashboard itself
   (`jenix_session` cookie, `require_session` middleware, 12h expiry, credentials in
   `admin_auth.json`) — this is distinct from, and layered on top of, the per-floor JWT
   credentials Master uses internally to talk to each floor.
4. **Aggregation pattern**: nearly every Master route either (a) fans a `GET` out to all floors in
   parallel with `asyncio.gather` and merges/sorts the combined list (audit logs, command history,
   schedules, sites, backups, reports — each tagged with `floor_idx`/`floor_name` on the way in),
   or (b) proxies a single floor-scoped action straight through (`/api/floors/{idx}/...` routes for
   approve/reject/command/reports/etc.), or (c) pushes a `POST` to every floor and reports
   per-floor success/failure (whitelabel, notification settings — since those are meant to be
   fleet-consistent settings).
5. **Fleet-wide commands never fan out per-machine over HTTP.** `POST /api/fleet/command` and
   `POST /api/fleet/checkpoint-start` accept an optional `targets` list
   (`[{floor_idx, machine_ids}]`) and delegate the actual per-machine targeting to each floor's own
   existing `fleet_command` route (a single `Machine.id.in_(...)` DB query per floor), explicitly
   to avoid a file-descriptor-exhaustion pattern the code comments say was seen earlier in the
   project when this was done per-machine from Master.
6. **Signed command dispatch** for the small set of destructive/topology-changing commands
   (`reassign_server`, `apply_upgrade`, `checkpoint_start`/`_restore`/`_discard`/`_list`): Master
   signs a payload with an Ed25519 private key (`topology_private.key`) and the agent
   independently verifies both the signature and that any target URL is in its own baked-in
   trusted floor list before acting — so, per the code's own doc comment, "a compromised master
   can only ever move nodes between already-known floors, never to an arbitrary server."
7. **Agent auto-upgrade** is a simple stage-then-register-then-signed-dispatch flow: a binary is
   copied to `master/upgrade_staging/<version>/<os>/`, registered via `POST /api/upgrades` (records
   version/filename/sha256 in `upgrades.json`), then `POST /api/floors/{idx}/machines/{id}/approve-upgrade`
   signs and dispatches an `apply_upgrade` command pointing the agent at
   `GET /agent-upgrade-binary/{version}/{os}` to download it.
8. Serves the built Master React SPA (`master/static/`) with its own catch-all route, excluding
   `api/`, `static/`, `agent-upgrade-binary/`, `login`, `logout`.
9. `ws_relay` (imported, not shown in this document — not yet inspected in full) relays each
   floor's dashboard WebSocket stream into a single `/ws/master-dashboard` endpoint for the Master
   UI's live updates; that endpoint checks the same `jenix_session` cookie manually, since
   Starlette's HTTP middleware does not run for WebSocket scope.

## 4. Agent (`agent/`)

Files present: `jenix_agent.py`, `agent.py`, `jenix_gui_agent.py`, `collector.py`, `executor.py`,
`snapshot.py`, `checkpoint.py`, `topology_auth.py`, `fleet_auth.py`, plus three
`_*_baked.py` files (`_topology_floors_baked.py`, `_topology_key_baked.py`, `_fleet_key_baked.py`)
whose naming strongly implies compile-time-embedded trust material (the baked-in floor list and
public key referenced in §3's signature-verification description) — **not yet inspected in full**;
this section is structural only and should be expanded once those files are reviewed in a later
session.

## 5. Known issues found and fixed this project (for buyer changelog / due diligence)

- **Route-shadowing bugs** (FastAPI matches routes in declaration order — a literal path segment
  declared after a parameterized path sharing the same prefix gets shadowed). Two real instances
  found and fixed: the fleet report route and the audit report route were both being shadowed by
  an earlier `{machine_id}`-typed route, causing a 422 instead of reaching the intended handler.
  Both fixed by reordering declarations; both committed and live-verified via authenticated calls.
- **Two files answering different things under the word "audit"**: `routes/audit.py` (audit-log
  listing, verification, CSV export) and `routes/audit_trail_report.py` (the audit *PDF report*
  workstream, machine-scoped as of the Sept 24 patch) are separate routers, both mounted under
  `/api`, both using the `audit` path segment for different purposes. Functionally this works
  because their full paths differ, but the naming overlap is a real source of confusion for future
  maintenance and is worth flagging to a buyer's engineering team.
- **`requirements.txt` audit**: of the original 51 runtime packages, 6 were confirmed via live grep
  against `server/`, `master/`, `agent/` to have zero real usage (`python-jose` — the actual JWT
  library in use is `PyJWT`, not `jose`; `pypdf`; `aiofiles`; `Deprecated`; `slowapi`; `pillow`) and
  were dropped, leaving 45. `uvicorn` and `bcrypt` show zero *direct* `import` hits but are
  confirmed real dependencies (uvicorn is the systemd `ExecStart` entrypoint; bcrypt is passlib's
  configured hashing backend).

## 6. Known limitations disclosed for the sale (not fixed, by design or by explicit timeline decision)

- **Floor 2 sync gap**: Floor 2's `/audit` route is confirmed (live recon) to still be the old
  unscoped signature with no `machine_ids` payload support; Floor 2 has no git; Floor 2's Linux
  agent binaries and installer architecture differ from Floor 1's; Floor 1's sudoers `NOPASSWD`
  entries have no Floor 2 equivalent. Master's own 501-safeguard in `floor_generate_audit_report`
  already protects against this mismatch (it refuses to pass off an unscoped report as
  machine-scoped) rather than silently returning wrong data.
- **CVE and Users management are not built on the Master side** (Floor-level equivalents exist and
  are fully functional; Master has no proxy routes for them). Explicitly deprioritized as
  non-blocking for the sale.
- **Floor-service-restart is not built at all**, by original design — a genuine security-model
  change that was never implemented, not a partial feature.
- **`floors.json`/credential model** is admin-credential-based per floor rather than scoped service
  accounts, as flagged directly in the code's own header comment (§3).
- **CORS is fully open** (`allow_origins=["*"]`) in `server/main.py` — fine for a private-network,
  single-tenant deployment; worth tightening if the buyer plans external exposure.
- **Agent registry/dashboard registry are in-memory, not persisted** — a Floor server restart
  clears WebSocket connection state (agents reconnect automatically; this is expected behavior, not
  a data-loss risk, but worth noting for anyone tuning restart/deploy procedures).
