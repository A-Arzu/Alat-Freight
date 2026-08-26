"""Regression tests for defects found by the demo-readiness audit.
Run: python test_hardening.py
"""
import io
import os
import sys
import uuid
from datetime import datetime, timedelta

os.environ["TRACE_DELAY_MS"] = "0"
os.environ["PLANNER"] = "mock"
os.environ["STORE"] = "memory"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pydantic
from core.store import MemoryStore
from core.models import Assignment
from data.seed import build_state
from agent import pipeline


def run_sync(store, trigger, scenario=None):
    rid = f"run-{uuid.uuid4().hex[:8]}"
    store.upsert("runs", {"id": rid, "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                          "finished_at": None, "status": "running", "trigger": trigger,
                          "scenario": scenario, "steps": [], "plan_id": None, "planner": None})
    pipeline.execute_run(store, rid, trigger, scenario)
    return store.get("runs", rid)


# ---- 1. a stalled run must never lock the dashboard --------------------
fresh = {"id": "r1", "status": "running",
         "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
dead = {"id": "r2", "status": "running",
        "started_at": (datetime.now() - timedelta(minutes=pipeline.STALE_RUN_MIN + 2))
        .strftime("%Y-%m-%dT%H:%M:%S")}
assert pipeline.is_stale(fresh) is False
assert pipeline.is_stale(dead) is True
assert pipeline.is_stale({"id": "r3", "status": "running", "started_at": "garbage"}) is True
assert pipeline.is_stale({"id": "r4", "status": "done", "started_at": "garbage"}) is False

s = MemoryStore()
s.reset(build_state())
s.upsert("runs", dead)
assert pipeline.active_run(s) is None, "a stalled run must not count as active"
s.upsert("runs", fresh)
assert pipeline.active_run(s)["id"] == "r1"
print("stalled-run detection: OK")

# ---- 2. re-running after a disruption keeps the rebooked shipment ------
store = MemoryStore()
store.reset(build_state())
run_sync(store, "manual")
r2 = run_sync(store, "event", "wagon_breakdown")
v2 = store.get("plans", r2["plan_id"])
holds_v2 = {h["shipment_id"] for h in v2["holds"]}
assert "S007" in holds_v2, "the disruption should rebook S007"
sla_v2 = v2["summary"]["sla_met_pct"]
assert sla_v2 < 100, f"SLA should reflect the rebooking, got {sla_v2}"

r3 = run_sync(store, "manual")          # a plain re-run, as in a demo retake
v3 = store.get("plans", r3["plan_id"])
holds_v3 = {h["shipment_id"] for h in v3["holds"]}
assigned_v3 = {a["shipment_id"] for a in v3["assignments"]}
assert "S007" in holds_v3 or "S007" in assigned_v3, \
    "S007 vanished on re-run - it must stay visible as a hold"
assert v3["summary"]["sla_met_pct"] <= sla_v2, \
    f"SLA silently inflated back to {v3['summary']['sla_met_pct']}% after a re-run"
print(f"re-run keeps rebooked cargo: OK (S007 held, SLA {v3['summary']['sla_met_pct']}%)")

# ---- 3. plan ids never collide ----------------------------------------
ids = [p["id"] for p in store.all("plans")]
assert len(ids) == len(set(ids)), f"duplicate plan ids: {ids}"
assert len(ids) == 3, ids
print(f"unique plan versions: OK ({', '.join(sorted(ids))})")

# ---- 4. update() on a missing id is a no-op (store parity) -------------
before = len(store.all("shipments"))
store.update("shipments", "S999-does-not-exist", {"status": "hold"})
assert len(store.all("shipments")) == before, \
    "update() must not create a phantom document (FirestoreStore mirrors this)"
assert all("id" in x for x in store.all("shipments")), "every doc must keep its id"
print("no phantom documents on update(): OK")

# ---- 5. why the model's numbers get clamped ---------------------------
try:
    Assignment(shipment_id="S1", wagon_id="W1", team_id="T1",
               load_start="2026-08-26T09:00", duration_min=45,
               load_end="2026-08-26T09:45", target_ship="SHIP-01",
               priority=5, confidence=75, reason="x")
    raise AssertionError("priority 5 should be rejected by the schema")
except pydantic.ValidationError:
    pass                                  # hence the clamp in adk_planner.submit_plan
print("plan schema rejects out-of-range priority: OK (clamped upstream)")

# ---- 6. the agent's memory of human judgement --------------------------
from agent.tools.memory import dispatcher_history

empty, summary = dispatcher_history({"outcomes": [], "plans": []})
assert empty == [] and "no prior dispatcher decisions" in summary

plan_id = store.all("plans")[0]["id"]
store.upsert("outcomes", {"id": "o1", "plan_id": plan_id, "action": "approved",
                          "note": "", "at": "2026-08-26T08:00:00"})
store.upsert("outcomes", {"id": "o2", "plan_id": plan_id, "action": "overridden",
                          "note": "Keep W005 free for the 14:00 crane inspection",
                          "at": "2026-08-26T09:30:00"})
decisions, summary = dispatcher_history(store.state())
assert len(decisions) == 2, decisions
assert decisions[0]["action"] == "overridden", "newest decision must come first"
assert decisions[0]["pairings"], "the agent must see which pairings were judged"
assert "1 approved, 1 overridden" in summary, summary
assert "crane inspection" in summary, "the human's reason must reach the agent"
print(f"dispatcher memory: OK ({summary[:70]}…)")

print("\nALL HARDENING TESTS PASSED")
