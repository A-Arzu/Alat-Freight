"""FastAPI service: agent endpoints + dashboard API + static frontend.

One container does everything on Cloud Run:
  POST /optimize                 morning batch plan   (Cloud Scheduler / dashboard)
  POST /events                   disruption -> incremental re-plan
  GET  /api/state                full snapshot for the dashboard (polled)
  GET  /api/runs/{id}            live step trace of one agent run
  POST /api/plans/{id}/approve | /override    human-in-the-loop
  POST /api/plans/{id}/email     (re)send a plan to a chosen recipient
  POST /api/settings/email       set the dispatcher recipient at runtime
  POST /api/seed                 reset the demo dataset
  /                              React dashboard (web/dist)

Auth: mutating endpoints need an X-Run-Token header. Two tokens are accepted -
RUN_TOKEN (kept secret, used by Cloud Scheduler) and a UI token derived from it,
which the dashboard reads from /api/state. The dashboard is public by design, so
the UI token is not a secret; deriving it keeps the Scheduler's token off the wire
while still letting the browser drive the demo.
"""
import hashlib
import os
import time
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.store import get_store
from data.seed import build_state
from agent import pipeline
from agent.tools import notify

RUN_TOKEN = os.environ.get("RUN_TOKEN", "demo-token")
UI_TOKEN = hashlib.sha256(f"{RUN_TOKEN}|dashboard".encode()).hexdigest()[:24]

# short-TTL snapshot cache: the dashboard polls every ~1-2s, and on Firestore
# each uncached poll costs ~45 document reads
_cache = {"t": 0.0, "data": None}
_CACHE_TTL = 1.2

# Guard rails on a public endpoint: stop a runaway loop or a scraper from
# burning Gemini quota, wiping the demo, or turning the mailer into a relay.
# Counted per caller so one visitor can never lock the presenter out.
_limits: dict[tuple[str, str], deque] = {}
_LIMITS = {"run": (60, 3600), "email": (25, 3600), "seed": (60, 3600)}


def _invalidate():
    _cache["t"] = 0.0


def _caller(request: Request | None) -> str:
    if request is None:
        return "unknown"
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit(bucket: str, request: Request | None = None):
    cap, window = _LIMITS[bucket]
    key = (bucket, _caller(request))
    now = time.time()
    stamps = _limits.setdefault(key, deque())
    while stamps and now - stamps[0] > window:
        stamps.popleft()
    if len(stamps) >= cap:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit reached ({cap} {bucket} requests/hour). Try again shortly.")
    stamps.append(now)
    if len(_limits) > 5000:               # bound the bookkeeping
        for k in [k for k, v in _limits.items() if not v][:2000]:
            _limits.pop(k, None)


@asynccontextmanager
async def lifespan(app):
    store = get_store()
    if not store.get("meta", "meta"):
        store.reset(build_state())
    yield


app = FastAPI(title="Port Operations Dispatch Agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


def _check(token: str | None):
    if token not in (RUN_TOKEN, UI_TOKEN):
        raise HTTPException(status_code=401, detail="bad or missing X-Run-Token")


@app.get("/healthz")       # note: Cloud Run's Google Frontend reserves /healthz;
def healthz():             # use /api/health when probing through the public URL
    return {"ok": True}


@app.get("/api/health")
def api_health():
    return {"ok": True}


@app.get("/api/state")
def api_state():
    if _cache["data"] is not None and time.time() - _cache["t"] < _CACHE_TTL:
        return _cache["data"]
    store = get_store()
    state = store.state()
    state["plans"].sort(key=lambda p: p["generated_at"], reverse=True)
    state["runs"].sort(key=lambda r: r["started_at"], reverse=True)
    state["events"].sort(key=lambda e: e["received_at"], reverse=True)
    state["emails"].sort(key=lambda e: e["created_at"], reverse=True)
    state["runs"] = state["runs"][:10]
    for run in state["runs"]:             # never let a dead run lock the UI
        if pipeline.is_stale(run):
            run["status"] = "stalled"
    meta = next((m for m in state["meta"] if m["id"] == "meta"), {})
    scenarios = next((m for m in state["meta"] if m["id"] == "scenarios"), {"items": []})
    state["meta"] = meta
    state["scenarios"] = scenarios["items"]
    state["ui_token"] = UI_TOKEN
    recipients = notify.resolve_recipients(meta)
    state["email_settings"] = {
        "recipient": ", ".join(recipients),
        "smtp_configured": notify.smtp_configured(),
        "source": ("dashboard" if meta.get("email_to")
                   else "env" if os.environ.get("EMAIL_TO") else "unset"),
    }
    _cache.update(t=time.time(), data=state)
    return state


@app.post("/optimize")
def optimize(request: Request, sync: bool = False,
             x_run_token: str | None = Header(default=None)):
    _check(x_run_token)
    _rate_limit("run", request)
    _invalidate()
    store = get_store()
    busy = pipeline.active_run(store)     # double-click is idempotent, not a race
    if busy:
        return {"run_id": busy["id"], "already_running": True}
    if sync:  # Cloud Scheduler path: block until the plan is published
        run_id = pipeline.run_now(store, trigger="schedule")
        run = store.get("runs", run_id)
        _invalidate()
        return {"run_id": run_id, "status": run["status"], "plan_id": run.get("plan_id")}
    return {"run_id": pipeline.start_run(store, trigger="manual")}


@app.post("/events")
def events(request: Request, payload: dict = Body(...), sync: bool = False,
           x_run_token: str | None = Header(default=None)):
    _check(x_run_token)
    scenario = payload.get("scenario")
    if not scenario:
        raise HTTPException(status_code=422, detail="body must include {'scenario': <key>}")
    _rate_limit("run", request)
    _invalidate()
    store = get_store()
    busy = pipeline.active_run(store)
    if busy:
        return {"run_id": busy["id"], "already_running": True}
    if sync:
        run_id = pipeline.run_now(store, trigger="event", scenario_key=scenario)
        run = store.get("runs", run_id)
        _invalidate()
        return {"run_id": run_id, "status": run["status"], "plan_id": run.get("plan_id")}
    return {"run_id": pipeline.start_run(store, trigger="event", scenario_key=scenario)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = get_store().get("runs", run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/api/settings/email")
def set_email_recipient(request: Request, payload: dict = Body(default={}),
                        x_run_token: str | None = Header(default=None)):
    """Choose who receives dispatch plans, from the dashboard, at runtime."""
    _check(x_run_token)
    _rate_limit("email", request)
    raw = str(payload.get("recipient", "")).strip()
    store = get_store()
    if not raw:
        store.update("meta", "meta", {"email_to": None})
        _invalidate()
        return {"ok": True, "recipient": "", "cleared": True}
    try:
        addresses = notify.parse_recipients(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    value = ", ".join(addresses)
    store.update("meta", "meta", {"email_to": value})
    _invalidate()
    return {"ok": True, "recipient": value,
            "smtp_configured": notify.smtp_configured()}


@app.post("/api/plans/{plan_id}/email")
def email_plan(plan_id: str, request: Request, payload: dict = Body(default={}),
               x_run_token: str | None = Header(default=None)):
    """(Re)send an existing plan - optionally to a one-off recipient."""
    _check(x_run_token)
    _rate_limit("email", request)
    store = get_store()
    plan = store.get("plans", plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    override = str(payload.get("recipient", "")).strip() or None
    if override:
        try:
            notify.parse_recipients(override)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    meta = store.get("meta", "meta") or {}
    record = notify.send_dispatch_email(plan, meta, store, recipient=override)
    _invalidate()
    return {"ok": True, "delivered": record["delivered"], "to": record["to"],
            "error": record.get("error"), "attachment": record.get("attachment")}


@app.post("/api/plans/{plan_id}/approve")
def approve(plan_id: str, payload: dict = Body(default={}),
            x_run_token: str | None = Header(default=None)):
    _check(x_run_token)
    return _decide(plan_id, "approved", payload.get("note", ""))


@app.post("/api/plans/{plan_id}/override")
def override(plan_id: str, payload: dict = Body(default={}),
             x_run_token: str | None = Header(default=None)):
    _check(x_run_token)
    return _decide(plan_id, "overridden", payload.get("note", ""))


def _decide(plan_id: str, action: str, note: str):
    store = get_store()
    plan = store.get("plans", plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    store.update("plans", plan_id, {"status": action})
    _invalidate()
    outcome = {"id": f"outcome-{plan_id}-{action}", "plan_id": plan_id,
               "action": action, "note": str(note)[:500],
               "at": pipeline._now_iso(),
               "planner": plan.get("planner"), "version": plan.get("version")}
    store.upsert("outcomes", outcome)
    return {"ok": True, "plan_id": plan_id, "status": action}


@app.post("/api/seed")
def seed(request: Request, x_run_token: str | None = Header(default=None)):
    """Reset the demo dataset. The chosen email recipient survives a reseed."""
    _check(x_run_token)
    _rate_limit("seed", request)
    store = get_store()
    keep = (store.get("meta", "meta") or {}).get("email_to")
    store.reset(build_state())
    if keep:
        store.update("meta", "meta", {"email_to": keep})
    _invalidate()
    return {"ok": True, "reseeded": True}


# static dashboard (built by `npm run build` in web/) -- mounted last so API wins
_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "web", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="dashboard")
