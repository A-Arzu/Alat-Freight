"""CI smoke check: assert a served /api/state snapshot reflects a completed
morning plan plus a disruption re-plan. Kept as a file (not inline in the CI
YAML) so indentation can't break it. Usage: python ci_smoke_check.py state.json
"""
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    state = json.load(f)

plans = state.get("plans", [])
assert plans, "no plans in state"
plan = plans[0]
assert plan["version"] == 2, f"expected v2 after disruption, got v{plan['version']}"
assert plan["assignments"], "plan has no assignments"
changed = [d for d in plan.get("diff", []) if d["kind"] != "completed"]
assert changed, "disruption produced no diff entries"
assert plan["summary"]["sla_met_pct"] <= 100, "impossible SLA"

print(f"API smoke OK: {plan['id']} - {len(plan['assignments'])} loads, "
      f"{len(changed)} diff change(s), SLA {plan['summary']['sla_met_pct']}%")
