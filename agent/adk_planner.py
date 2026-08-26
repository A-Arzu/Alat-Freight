"""Gemini planner on Google ADK.

The LlmAgent decides ordering, pairing, priorities, confidence and reasons;
the function tools own all facts and all arithmetic (Firestore snapshot,
hard-constraint filter, time-slot engine, validation). The model can only
submit a plan through submit_plan, which re-times and re-validates it - an
illegal plan bounces back with violations for the agent to correct.

Requires: pip install google-adk, plus Vertex AI env on Cloud Run:
  GOOGLE_GENAI_USE_VERTEXAI=TRUE  GOOGLE_CLOUD_PROJECT=...  GOOGLE_CLOUD_LOCATION=...
Raises PlannerUnavailable on any setup/runtime failure so the pipeline can
fall back to the deterministic planner instead of dying mid-demo.
"""
import asyncio
import json
import os

from agent.prompts import PLANNER_PROMPT
from agent.tools.prefilter import pairing_table
from agent.tools.schedule import build_schedule
from agent.tools.validate import validate_plan
from core.models import LOAD_MINUTES


class PlannerUnavailable(Exception):
    pass


def plan(scope: list[dict], state: dict, trace, fixed_slots: list[dict] | None = None) -> dict:
    try:
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types
    except ImportError as exc:
        raise PlannerUnavailable(f"google-adk not installed: {exc}")

    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    shipments_by_id = {s["id"]: s for s in scope}
    all_shipments_by_id = {s["id"]: s for s in state["shipments"]}
    wagons_by_id = {w["id"]: w for w in state["wagons"]}
    ships_by_id = {s["id"]: s for s in state["ships"]}
    customers = {c["id"]: c for c in state["customers"]}
    teams = state["teams"]
    now = state["meta"]["now"]
    result = {"submitted": None, "last_slots": []}

    # ---- tools (closures over the planning context) ----------------------

    def get_dispatch_snapshot() -> dict:
        """Current port state: waiting shipments in scope, wagon fleet, ship
        schedule with loading cutoffs, dock teams and the port clock."""
        snap = {
            "port_clock": now,
            "shipments": [{
                "id": s["id"], "cargo_type": s["cargo_type"], "weight_kg": s["weight_kg"],
                "customer": s["customer_id"],
                "sla_tier": customers[s["customer_id"]]["sla_tier"],
                "target_ship": s["target_ship"],
                "ship_cutoff": ships_by_id[s["target_ship"]]["loading_cutoff"],
                "arrived_at": s.get("arrived_at"),
                "customs_cleared": s.get("customs_cleared", True),
                "cold_chain_min": s.get("cold_chain_min"),
            } for s in scope],
            "wagons": [{k: w.get(k) for k in
                        ("id", "type", "capacity_kg", "certifications", "status",
                         "available_at", "reserved_for")} for w in state["wagons"]],
            "ships": state["ships"],
            "teams": teams,
        }
        trace("tool", "get_dispatch_snapshot",
              f"{len(scope)} shipments in scope - {len(state['wagons'])} wagons - "
              f"{len(state['ships'])} ships - {len(teams)} dock teams")
        return snap

    def get_valid_pairings() -> dict:
        """Legal wagon options per shipment after hard-constraint filtering
        (cargo type rules, certifications, capacity, reservations, cutoff
        feasibility). Only options with usable=true can be assigned."""
        table, excluded = pairing_table(
            [s for s in scope if s.get("customs_cleared", True)],
            state["wagons"], ships_by_id, now)
        legal = sum(len(v) for v in table.values())
        trace("tool", "get_valid_pairings",
              f"Removed {excluded} illegal pairings - {legal} legal options remain")
        return {"pairings": table, "excluded_count": excluded}

    def propose_schedule(ordered: list[dict]) -> dict:
        """Compute concrete load windows for an ordered pairing list.
        ordered: [{"shipment_id": "S001", "wagon_id": "W001"}, ...] in load-priority
        order. Returns slots with load_start/load_end/team and any violations."""
        slots, violations = build_schedule(ordered, all_shipments_by_id, wagons_by_id,
                                           ships_by_id, teams, now, fixed_slots)
        result["last_slots"] = slots
        trace("tool", "propose_schedule",
              f"Placed {len(slots)} loads - "
              + (f"{len(violations)} violation(s)" if violations else "no conflicts"))
        return {"slots": slots, "violations": violations}

    def submit_plan(assignments: list[dict], holds: list[dict]) -> dict:
        """Submit the final plan. assignments: [{shipment_id, wagon_id, priority,
        confidence, reason}]. holds: [{shipment_id, action, reason, rebook_ship?}].
        Times come from the schedule engine, never from you. Returns
        {status:"accepted"} or {status:"rejected", violations:[...]} to fix."""
        ordered = [{"shipment_id": a["shipment_id"], "wagon_id": a["wagon_id"]}
                   for a in assignments]
        slots, sched_violations = build_schedule(ordered, all_shipments_by_id, wagons_by_id,
                                                 ships_by_id, teams, now, fixed_slots)
        slot_by_sid = {x["shipment_id"]: x for x in slots}
        full = []
        for a in assignments:
            slot = slot_by_sid.get(a["shipment_id"])
            if not slot:
                continue
            s = all_shipments_by_id[a["shipment_id"]]
            full.append({
                "shipment_id": a["shipment_id"], "wagon_id": a["wagon_id"],
                "team_id": slot["team_id"], "load_start": slot["load_start"],
                "load_end": slot["load_end"], "duration_min": slot["duration_min"],
                "target_ship": s["target_ship"],
                "priority": int(a.get("priority", 2)),
                "confidence": int(a.get("confidence", 75)),
                "reason": str(a.get("reason", ""))[:300],
                "status": "planned", "change": "new",
            })
        violations = [f"{v['shipment_id']}: {v['detail']}" for v in sched_violations]
        violations += validate_plan(full, all_shipments_by_id, wagons_by_id, ships_by_id, now)
        if violations:
            trace("validate", "submit_plan rejected", "; ".join(violations[:4]))
            return {"status": "rejected", "violations": violations}
        clean_holds = [{
            "shipment_id": h["shipment_id"], "action": str(h.get("action", "Hold")),
            "reason": str(h.get("reason", "")), "rebook_ship": h.get("rebook_ship"),
            "retry_at": h.get("retry_at"),
            "confidence": int(h.get("confidence", 80)),
            "change": "rebooked" if h.get("rebook_ship") else "held",
        } for h in holds or []]
        result["submitted"] = {"assignments": full, "holds": clean_holds,
                               "planner": f"{model_name} via Google ADK"}
        trace("validate", "submit_plan accepted",
              f"{len(full)} assignments, {len(clean_holds)} holds - 0 violations")
        return {"status": "accepted"}

    # ---- run the agent ---------------------------------------------------

    agent = LlmAgent(
        name="dispatch_planner",
        model=model_name,
        instruction=PLANNER_PROMPT,
        tools=[get_dispatch_snapshot, get_valid_pairings, propose_schedule, submit_plan],
    )

    async def _run():
        session_service = InMemorySessionService()
        runner = Runner(agent=agent, app_name="port-dispatch", session_service=session_service)
        session = await session_service.create_session(app_name="port-dispatch",
                                                       user_id="dispatcher")
        msg = types.Content(role="user", parts=[types.Part(
            text="Build the dispatch plan for the current port state now.")])
        async for event in runner.run_async(user_id="dispatcher",
                                            session_id=session.id, new_message=msg):
            if getattr(event, "content", None) and event.content.parts:
                for part in event.content.parts:
                    text = getattr(part, "text", None)
                    if text and text.strip():
                        trace("reason", "Gemini reasoning", text.strip()[:400])

    try:
        asyncio.run(asyncio.wait_for(_run(), timeout=float(os.environ.get("PLANNER_TIMEOUT_S", "150"))))
    except Exception as exc:
        raise PlannerUnavailable(f"agent run failed: {exc}")

    if not result["submitted"]:
        raise PlannerUnavailable("agent finished without submitting a plan")
    return result["submitted"]
