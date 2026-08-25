"""All three disruption scenarios end-to-end. Run: python test_scenarios.py"""
import os
import io
import sys

os.environ["TRACE_DELAY_MS"] = "0"
os.environ["PLANNER"] = "mock"
os.environ["STORE"] = "memory"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import uuid
from datetime import datetime
from core.store import MemoryStore
from data.seed import build_state
from agent.pipeline import execute_run


def run_sync(store, trigger, scenario=None):
    rid = f"run-{uuid.uuid4().hex[:8]}"
    store.upsert("runs", {"id": rid, "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                          "finished_at": None, "status": "running", "trigger": trigger,
                          "scenario": scenario, "steps": [], "plan_id": None, "planner": None})
    execute_run(store, rid, trigger, scenario)
    return store.get("runs", rid)


for key in ["wagon_breakdown", "ship_advanced", "team_outage"]:
    store = MemoryStore()
    store.reset(build_state())
    r1 = run_sync(store, "manual")
    assert r1["status"] == "done", f"{key}: batch run failed"
    r2 = run_sync(store, "event", key)
    assert r2["status"] == "done", f"{key}: event run failed: {r2['steps'][-1]}"
    plan = store.get("plans", r2["plan_id"])
    changed = [d for d in plan["diff"] if d["kind"] not in ("completed",)]
    print(f"\n### {key}: v{plan['version']} ok - {len(changed)} change(s), "
          f"SLA {plan['summary']['sla_met_pct']}%")
    for d in changed:
        print(f"   {d['kind']:>10} {d['shipment_id']}: "
              f"{(d['before'] or {}).get('window', '-')} -> {(d['after'] or {}).get('window', '-')}")
    assert changed, f"{key}: expected at least one change"

print("\nALL SCENARIOS PASS")
