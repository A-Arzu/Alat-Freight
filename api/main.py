"""FastAPI service: agent endpoints + dashboard API + static frontend.

One container does everything on Cloud Run:
  POST /optimize            morning batch plan   (Cloud Scheduler / dashboard)
  POST /events              disruption -> incremental re-plan
  GET  /api/state           full snapshot for the dashboard (polled)
  GET  /api/runs/{id}       live step trace of one agent run
  POST /api/plans/{id}/approve | /override      human-in-the-loop
  POST /api/seed            reset the demo dataset
  /                         React dashboard (web/dist)
"""
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.store import get_store
from data.seed import build_state
from agent import pipeline

RUN_TOKEN = os.environ.get("RUN_TOKEN", "demo-token")

# short-TTL snapshot cache: the dashboard polls every ~1-2s, and on Firestore
# each uncached poll costs ~45 document reads
_cache = {"t": 0.0, "data": None}
_CACHE_TTL = 1.2


def _invalidate():
    _cache["t"] = 0.0


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
    if token != RUN_TOKEN:
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
    meta = next((m for m in state["meta"] if m["id"] == "meta"), {})
    scenarios = next((m for m in state["meta"] if m["id"] == "scenarios"), {"items": []})
    state["meta"] = meta
    state["scenarios"] = scenarios["items"]
    _cache.update(t=time.time(), data=state)
    return state


@app.post("/optimize")
def optimize(sync: bool = False, x_run_token: str | None = Header(default=None)):
    _check(x_run_token)
    _invalidate()
    store = get_store()
    if sync:  # Cloud Scheduler path: block until the plan is published
        run_id = pipeline.run_now(store, trigger="schedule")
        run = store.get("runs", run_id)
        _invalidate()
        return {"run_id": run_id, "status": run["status"], "plan_id": run.get("plan_id")}
    return {"run_id": pipeline.start_run(store, trigger="manual")}


@app.post("/events")
def events(payload: dict = Body(...), sync: bool = False,
           x_run_token: str | None = Header(default=None)):
    _check(x_run_token)
    scenario = payload.get("scenario")
    if not scenario:
        raise HTTPException(status_code=422, detail="body must include {'scenario': <key>}")
    _invalidate()
    store = get_store()
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


@app.post("/api/plans/{plan_id}/approve")
def approve(plan_id: str, payload: dict = Body(default={})):
    return _decide(plan_id, "approved", payload.get("note", ""))


@app.post("/api/plans/{plan_id}/override")
def override(plan_id: str, payload: dict = Body(default={})):
    return _decide(plan_id, "overridden", payload.get("note", ""))


def _decide(plan_id: str, action: str, note: str):
    store = get_store()
    plan = store.get("plans", plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    store.update("plans", plan_id, {"status": action})
    _invalidate()
    outcome = {"id": f"outcome-{plan_id}-{action}", "plan_id": plan_id,
               "action": action, "note": note,
               "at": pipeline._now_iso(),
               "planner": plan.get("planner"), "version": plan.get("version")}
    store.upsert("outcomes", outcome)
    return {"ok": True, "plan_id": plan_id, "status": action}


@app.post("/api/seed")
def seed(x_run_token: str | None = Header(default=None)):
    _check(x_run_token)
    get_store().reset(build_state())
    _invalidate()
    return {"ok": True, "reseeded": True}


# static dashboard (built by `npm run build` in web/) -- mounted last so API wins
_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "web", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="dashboard")
