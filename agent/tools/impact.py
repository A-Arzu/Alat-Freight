"""Disruption impact analysis. Deterministic set logic: which assignments of
the active plan does this event touch, and what does it free up. The agent
re-plans only the affected subset.
"""

EVENT_LIBRARY = {
    "wagon_breakdown": {
        "label": "Wagon breakdown",
        "describe": lambda p: f"Wagon {p['wagon_id']} failed axle inspection and is out of service",
    },
    "ship_advanced": {
        "label": "Ship cutoff advanced",
        "describe": lambda p: f"{p['ship_id']} loading cutoff moved earlier to {p['new_cutoff'][11:]}",
    },
    "team_outage": {
        "label": "Dock team outage",
        "describe": lambda p: f"{p['team_id']} unavailable from {p['from'][11:]} (crane fault)",
    },
}


def apply_event(event: dict, store, now: str):
    """Mutate world state per the event. Returns human description."""
    p = event["payload"]
    etype = event["type"]
    if etype == "wagon_breakdown":
        store.update("wagons", p["wagon_id"], {"status": "out_of_service", "available_at": None})
    elif etype == "ship_advanced":
        store.update("ships", p["ship_id"], {"loading_cutoff": p["new_cutoff"]})
    elif etype == "team_outage":
        store.update("teams", p["team_id"], {"shift_end": p["from"]})
    return EVENT_LIBRARY[etype]["describe"](p)


def affected_assignments(event: dict, plan: dict, ships_by_id: dict, now: str) -> list[str]:
    """Shipment ids from the active plan that must be re-planned.
    Already-completed loads (before the port clock 'now') are never affected."""
    p = event["payload"]
    etype = event["type"]
    hit = []
    for a in plan.get("assignments", []):
        if a["load_end"] <= now:      # already done, history
            continue
        if etype == "wagon_breakdown" and a["wagon_id"] == p["wagon_id"]:
            hit.append(a["shipment_id"])
        elif etype == "ship_advanced" and a["target_ship"] == p["ship_id"] \
                and a["load_end"] > p["new_cutoff"]:
            hit.append(a["shipment_id"])
        elif etype == "team_outage" and a["team_id"] == p["team_id"] \
                and a["load_end"] > p["from"]:
            hit.append(a["shipment_id"])
    return hit
