"""Local smoke test: full story arc without HTTP.
Run: python test_pipeline.py
"""
import os
import io
import sys

os.environ["TRACE_DELAY_MS"] = "0"
os.environ["PLANNER"] = "mock"
os.environ["STORE"] = "memory"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.store import get_store
from data.seed import build_state
from agent.pipeline import start_run, execute_run
import uuid
from datetime import datetime


def run_sync(store, trigger, scenario=None):
    rid = f"run-{uuid.uuid4().hex[:8]}"
    store.upsert("runs", {"id": rid, "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                          "finished_at": None, "status": "running", "trigger": trigger,
                          "scenario": scenario, "steps": [], "plan_id": None, "planner": None})
    execute_run(store, rid, trigger, scenario)
    return store.get("runs", rid)


def show_plan(plan):
    print(f"\n=== {plan['id']} ({plan['planner']}) status={plan['status']} ===")
    for a in sorted(plan["assignments"], key=lambda x: x["load_start"]):
        print(f"  P{a['priority']} {a['shipment_id']} -> {a['wagon_id']} {a['team_id']} "
              f"{a['load_start'][11:]}-{a['load_end'][11:]} ship={a['target_ship']} "
              f"conf={a['confidence']}% [{a['change']}]")
        print(f"      {a['reason']}")
    for h in plan["holds"]:
        print(f"  HOLD {h['shipment_id']}: {h['action']} ({h['reason']}) [{h.get('change')}]")
    print(f"  summary: {plan['summary']}")
    if plan["diff"]:
        print("  diff:")
        for d in plan["diff"]:
            print(f"    {d['kind']:>10} {d['shipment_id']}: "
                  f"{(d['before'] or {}).get('window', '-')} -> {(d['after'] or {}).get('window', '-')}  {d['note'][:80]}")


store = get_store()
store.reset(build_state())

print(">>> MORNING BATCH RUN")
run1 = run_sync(store, "manual")
print(f"run status: {run1['status']}")
for s in run1["steps"]:
    print(f"  [{s['kind']:>8}] {s['label']} -- {s['detail'][:110]}")
assert run1["status"] == "done", "morning run failed"
plan1 = store.get("plans", run1["plan_id"])
show_plan(plan1)

print("\n>>> DISRUPTION: W003 BREAKDOWN")
run2 = run_sync(store, "event", "wagon_breakdown")
print(f"run status: {run2['status']}")
for s in run2["steps"]:
    print(f"  [{s['kind']:>8}] {s['label']} -- {s['detail'][:110]}")
assert run2["status"] == "done", "event run failed"
plan2 = store.get("plans", run2["plan_id"])
show_plan(plan2)

# story assertions
a2 = {a["shipment_id"]: a for a in plan2["assignments"]}
h2 = {h["shipment_id"]: h for h in plan2["holds"]}
assert "S003" in a2 and a2["S003"]["wagon_id"] == "W006", "S003 should move to W006"
assert "S007" in h2 and h2["S007"].get("rebook_ship") == "SHIP-04", "S007 should rebook to SHIP-04"
assert any(a["change"] == "completed" for a in plan2["assignments"]), "some loads should be completed"
email = store.all("emails")
assert len(email) == 2, "two emails recorded"
print("\nALL STORY ASSERTIONS PASSED")
