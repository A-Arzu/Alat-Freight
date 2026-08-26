"""The agent's memory of human judgement.

Approvals and overrides accumulate in the outcomes collection every time a
dispatcher acts on a plan. This turns them into something the planner can read
back on its next run, so a pairing a human rejected does not get proposed again
with blind confidence.
"""


def dispatcher_history(state: dict, limit: int = 5) -> tuple[list[dict], str]:
    """Return (decisions, one_line_summary) newest first."""
    outcomes = sorted(state.get("outcomes", []) or [],
                      key=lambda o: o.get("at", ""), reverse=True)[:limit]
    plans_by_id = {p["id"]: p for p in (state.get("plans", []) or [])}

    decisions = []
    for o in outcomes:
        plan = plans_by_id.get(o.get("plan_id"), {})
        decisions.append({
            "action": o.get("action"),
            "note": (o.get("note") or "")[:300],
            "at": o.get("at"),
            "plan": o.get("plan_id"),
            "pairings": [{"shipment_id": a.get("shipment_id"), "wagon_id": a.get("wagon_id"),
                          "priority": a.get("priority")}
                         for a in (plan.get("assignments") or [])][:12],
        })

    if not decisions:
        return [], "no prior dispatcher decisions yet - planning from policy alone"

    approved = sum(1 for d in decisions if d["action"] == "approved")
    overrides = [d for d in decisions if d["action"] == "overridden"]
    summary = (f"{len(decisions)} prior decision(s): {approved} approved, "
               f"{len(overrides)} overridden")
    noted = next((d for d in overrides if d["note"]), None)
    if noted:
        summary += f' - last override: "{noted["note"][:90]}"'
    return decisions, summary
