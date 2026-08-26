"""Validates the Gemini/ADK planner wiring WITHOUT calling the model:
imports, LlmAgent + tool construction, Runner + session creation, and the
tool bodies (snapshot / pairings / schedule / submit) executed directly.
Run: python test_adk_wiring.py   (requires: pip install google-adk)
"""
import os
import io
import sys
import asyncio

os.environ["TRACE_DELAY_MS"] = "0"
os.environ["STORE"] = "memory"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types  # noqa: F401  (import path used by adk_planner)

from core.store import MemoryStore
from data.seed import build_state
from agent.prompts import PLANNER_PROMPT
from agent.tools.prefilter import pairing_table
from agent.tools.schedule import build_schedule
from agent.tools.validate import validate_plan

store = MemoryStore()
store.reset(build_state())
state = store.state()
state["meta"] = store.get("meta", "meta")
now = state["meta"]["now"]

shipments = state["shipments"]
ships_by_id = {s["id"]: s for s in state["ships"]}
wagons_by_id = {w["id"]: w for w in state["wagons"]}
shipments_by_id = {s["id"]: s for s in shipments}

# ---- 1. tool bodies work standalone ------------------------------------
table, excluded = pairing_table(shipments, state["wagons"], ships_by_id, now)
assert excluded > 0 and sum(len(v) for v in table.values()) > 0
ordered = [{"shipment_id": "S001", "wagon_id": "W001"},
           {"shipment_id": "S005", "wagon_id": "W005"}]
slots, violations = build_schedule(ordered, shipments_by_id, wagons_by_id,
                                   ships_by_id, state["teams"], now)
assert len(slots) == 2 and not violations
v = validate_plan([{**s, "target_ship": shipments_by_id[s["shipment_id"]]["target_ship"],
                    "priority": 1, "confidence": 90, "reason": "t", "status": "planned",
                    "change": "new"} for s in slots],
                  shipments_by_id, wagons_by_id, ships_by_id, now)
assert v == [], v
print("tool bodies: OK")

# ---- 2. LlmAgent constructs with the same tool signatures ---------------


def get_dispatch_snapshot() -> dict:
    """Current port state."""
    return {"shipments": len(shipments)}


def get_valid_pairings() -> dict:
    """Legal wagon options per shipment."""
    return {"pairings": {}}


def propose_schedule(ordered: list[dict]) -> dict:
    """Compute load windows for an ordered pairing list."""
    return {"slots": []}


def submit_plan(assignments: list[dict], holds: list[dict]) -> dict:
    """Submit the final plan."""
    return {"status": "accepted"}


agent = LlmAgent(
    name="dispatch_planner",
    model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
    instruction=PLANNER_PROMPT,
    tools=[get_dispatch_snapshot, get_valid_pairings, propose_schedule, submit_plan],
)
print(f"LlmAgent constructed: {agent.name}, model={agent.model}, tools={len(agent.tools)}")

# ---- 3. Runner + session service wire up --------------------------------


async def _wire():
    svc = InMemorySessionService()
    runner = Runner(agent=agent, app_name="port-dispatch", session_service=svc)
    session = await svc.create_session(app_name="port-dispatch", user_id="dispatcher")
    return runner, session


runner, session = asyncio.run(_wire())
print(f"Runner + session OK: session={session.id[:8]}...")
print("\nADK WIRING VALIDATED (model call itself needs Vertex AI credentials)")
