"""Run orchestrator: one code path for both agent modes.

  /optimize  -> full-day batch plan (everything not yet loaded)
  /events    -> disruption response (re-plan only the affected subset)

Each run writes a live step trace to the store (the dashboard polls it), picks
the planner (Gemini via ADK, or the deterministic fallback), validates, then
publishes the plan + email. A Gemini failure downgrades to the fallback
planner mid-run instead of failing the demo.
"""
import os
import threading
import time
import uuid
from datetime import datetime

from core import kpis
from core.diff import compute_diff
from core.models import DispatchPlan
from agent import mock_planner
from agent.tools.impact import apply_event, affected_assignments, EVENT_LIBRARY
from agent.tools.notify import send_dispatch_email
from agent.tools.validate import validate_plan


def _now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _create_run(store, trigger: str, scenario_key: str | None) -> str:
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    run = {"id": run_id, "started_at": _now_iso(), "finished_at": None,
           "status": "running", "trigger": trigger, "scenario": scenario_key,
           "steps": [], "plan_id": None, "planner": None}
    store.upsert("runs", run)
    return run_id


def start_run(store, trigger: str, scenario_key: str | None = None) -> str:
    """Background run: returns immediately; the dashboard polls the trace."""
    run_id = _create_run(store, trigger, scenario_key)
    t = threading.Thread(target=execute_run, args=(store, run_id, trigger, scenario_key),
                         daemon=True)
    t.start()
    return run_id


def run_now(store, trigger: str, scenario_key: str | None = None) -> str:
    """Synchronous run: blocks until done. Used by Cloud Scheduler (sync=true),
    where a background thread could be CPU-throttled after the response."""
    run_id = _create_run(store, trigger, scenario_key)
    execute_run(store, run_id, trigger, scenario_key)
    return run_id


def execute_run(store, run_id: str, trigger: str, scenario_key: str | None = None):
    delay = int(os.environ.get("TRACE_DELAY_MS", "300")) / 1000
    t0 = time.time()

    def emit(kind: str, label: str, detail: str = ""):
        run = store.get("runs", run_id)
        steps = run.get("steps", [])
        steps.append({"t": round(time.time() - t0, 1), "kind": kind,
                      "label": label, "detail": detail})
        store.update("runs", run_id, {"steps": steps})
        if delay:
            time.sleep(delay)

    try:
        _execute(store, run_id, trigger, scenario_key, emit, t0)
    except Exception as exc:
        emit("error", "Run failed", str(exc)[:400])
        store.update("runs", run_id, {"status": "failed", "finished_at": _now_iso()})


def _latest_plan(store):
    plans = store.all("plans")
    if not plans:
        return None
    plans.sort(key=lambda p: p["generated_at"])
    return plans[-1]


def _execute(store, run_id, trigger, scenario_key, emit, t0):
    meta = store.get("meta", "meta")
    old_plan = _latest_plan(store)

    completed, kept, event_note = [], [], None
    scope_ids = None

    # ---- disruption handling --------------------------------------------
    if scenario_key:
        scenarios = store.get("meta", "scenarios")["items"]
        scenario = next((x for x in scenarios if x["key"] == scenario_key), None)
        if scenario is None:
            raise ValueError(f"unknown scenario {scenario_key}")
        if old_plan is None:
            raise ValueError("no active plan to disrupt - run the morning optimization first")

        new_now = max(meta["now"], scenario["advance_clock_to"])
        store.update("meta", "meta", {"now": new_now})
        meta["now"] = new_now

        event = {"id": f"event-{uuid.uuid4().hex[:6]}", "received_at": _now_iso(),
                 "port_time": new_now, **scenario["event"], "label": scenario["label"],
                 "resolved_by_plan": None}
        note = apply_event(scenario["event"], store, new_now)
        event_note = note
        store.upsert("events", event)
        emit("event", EVENT_LIBRARY[scenario["event"]["type"]]["label"], note)

        scope_ids = affected_assignments(scenario["event"], old_plan,
                                         {s["id"]: s for s in store.all("ships")}, new_now)
        for a in old_plan["assignments"]:
            sid = a["shipment_id"]
            if a["load_end"] <= new_now:
                completed.append({**a, "status": "completed", "change": "completed"})
            elif sid not in scope_ids:
                kept.append({**a, "change": "unchanged"})
        emit("tool", "impact_analysis",
             f"{len(scope_ids)} assignment(s) affected ({', '.join(scope_ids) or 'none'}) - "
             f"{len(completed)} already loaded - {len(kept)} untouched")
        store.update("runs", run_id, {"event_id": event["id"]})
    elif old_plan:
        # batch re-run: keep what is already loaded, re-plan the rest
        for a in old_plan["assignments"]:
            if a["load_end"] <= meta["now"]:
                completed.append({**a, "status": "completed", "change": "completed"})

    # ---- scope -----------------------------------------------------------
    shipments = store.all("shipments")
    done_ids = {a["shipment_id"] for a in completed}
    kept_ids = {a["shipment_id"] for a in kept}
    if scope_ids is not None:
        scope = [s for s in shipments if s["id"] in scope_ids]
    else:
        scope = [s for s in shipments
                 if s["id"] not in done_ids and s.get("status") != "rebooked"]

    state = store.state()
    state["meta"] = meta
    emit("tool", "get_snapshot",
         f"Port clock {meta['now'][11:]} - {len(scope)} shipment(s) in scope - "
         f"{sum(1 for w in state['wagons'] if w['status'] == 'available')} wagons available")

    # ---- plan ------------------------------------------------------------
    mode = os.environ.get("PLANNER", "auto").lower()
    use_gemini = mode == "gemini" or (
        mode == "auto" and (os.environ.get("GOOGLE_CLOUD_PROJECT")
                            or os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")))
    fresh = None
    if use_gemini:
        try:
            from agent import adk_planner
            emit("reason", "Planner", f"Gemini ({os.environ.get('GEMINI_MODEL', 'gemini-3.5-flash')}) "
                                      "via Google ADK engaged")
            fresh = adk_planner.plan(scope, state, emit, fixed_slots=kept)
        except Exception as exc:
            emit("error", "Gemini unavailable - deterministic fallback",
                 str(exc)[:300])
    if fresh is None:
        fresh = mock_planner.plan(scope, state, emit, fixed_slots=kept)
    store.update("runs", run_id, {"planner": fresh["planner"]})

    # ---- validate (fresh, future-dated assignments only) -----------------
    shipments_by_id = {s["id"]: s for s in shipments}
    wagons_by_id = {w["id"]: w for w in store.all("wagons")}
    ships_by_id = {s["id"]: s for s in store.all("ships")}
    future = [a for a in fresh["assignments"] if a["load_start"] >= meta["now"]]
    violations = validate_plan(future, shipments_by_id, wagons_by_id, ships_by_id, meta["now"])
    if violations:
        raise RuntimeError("validator rejected plan: " + "; ".join(violations[:5]))
    emit("validate", "Hard-constraint re-check", "0 violations - plan is legal")

    # ---- assemble + diff -------------------------------------------------
    version = (old_plan["version"] + 1) if old_plan else 1
    plan_id = f"plan-{meta['plan_date']}-v{version}"
    all_assignments = completed + kept + fresh["assignments"]

    carry_holds = []
    if old_plan and scope_ids is not None:
        fresh_hold_ids = {h["shipment_id"] for h in fresh["holds"]}
        carry_holds = [h for h in old_plan.get("holds", [])
                       if h["shipment_id"] not in fresh_hold_ids
                       and h["shipment_id"] not in {a["shipment_id"] for a in all_assignments}]
    all_holds = carry_holds + fresh["holds"]

    diff = []
    if old_plan:
        diff = compute_diff(old_plan, all_assignments, all_holds, meta["now"])
        kind_by_sid = {d["shipment_id"]: d["kind"] for d in diff}
        for a in all_assignments:
            if a["change"] not in ("completed", "unchanged"):
                a["change"] = kind_by_sid.get(a["shipment_id"], "unchanged")
        changed = [d for d in diff if d["kind"] not in ("completed",)]
        if scenario_key:
            emit("reason", "Recovery summary",
                 "; ".join(f"{d['shipment_id']} {d['kind']}" for d in changed) or "no changes needed")

    summary = kpis.summarize(all_assignments, all_holds, store.all("teams"),
                             time.time() - t0, meta.get("manual_baseline_min", 45),
                             shipments_by_id)

    plan = DispatchPlan(
        id=plan_id, version=version,
        parent_id=old_plan["id"] if old_plan else None,
        plan_date=meta["plan_date"], generated_at=_now_iso(),
        trigger=trigger if not scenario_key else f"event:{scenario_key}",
        planner=fresh["planner"], assignments=all_assignments, holds=all_holds,
        summary=summary, diff=diff, status="pending",
    ).model_dump()

    if old_plan:
        store.update("plans", old_plan["id"], {"status": "superseded"})
    store.upsert("plans", plan)
    store.update("meta", "meta", {"active_plan_id": plan_id})

    # ---- shipment status chips ------------------------------------------
    for a in all_assignments:
        store.update("shipments", a["shipment_id"],
                     {"status": a["status"] if a["change"] == "completed" else "planned"})
    for h in all_holds:
        store.update("shipments", h["shipment_id"],
                     {"status": "rebooked" if h.get("rebook_ship") else "hold"})

    emit("publish", f"Plan v{version} published",
         f"{summary['planned']} loads - {summary['holds']} holds - "
         f"SLA {summary['sla_met_pct']}% - planned in {summary['planning_seconds']}s")

    email = send_dispatch_email(plan, meta, store)
    emit("publish", "Dispatcher notified",
         ("Email sent to " + email["to"]) if email["delivered"]
         else "Email rendered + XLSX attached (SMTP not configured - preview in dashboard)")

    if scenario_key:
        events = store.all("events")
        if events:
            events.sort(key=lambda e: e["received_at"])
            store.update("events", events[-1]["id"], {"resolved_by_plan": plan_id})

    store.update("runs", run_id, {"status": "done", "finished_at": _now_iso(),
                                  "plan_id": plan_id})
