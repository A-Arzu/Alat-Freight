"""Plan-to-plan diff: what the disruption response actually changed."""
from core.clock import hhmm


def compute_diff(old_plan: dict, new_assignments: list[dict], new_holds: list[dict],
                 now: str) -> list[dict]:
    entries = []
    old_a = {a["shipment_id"]: a for a in old_plan.get("assignments", [])}
    old_h = {h["shipment_id"]: h for h in old_plan.get("holds", [])}

    for a in new_assignments:
        sid = a["shipment_id"]
        prev = old_a.get(sid)
        if prev is None:
            kind = "scheduled" if sid in old_h else "new"
            entries.append({"shipment_id": sid, "kind": kind, "before": None,
                            "after": _slot(a), "note": a.get("reason", "")})
            continue
        if prev["load_end"] <= now:
            entries.append({"shipment_id": sid, "kind": "completed", "before": _slot(prev),
                            "after": _slot(prev), "note": "loaded before the disruption"})
            continue
        moved = prev["wagon_id"] != a["wagon_id"]
        retimed = prev["load_start"] != a["load_start"] or prev["team_id"] != a["team_id"]
        if moved or retimed:
            kind = "moved" if moved else "retimed"
            entries.append({"shipment_id": sid, "kind": kind, "before": _slot(prev),
                            "after": _slot(a), "note": a.get("reason", "")})

    for h in new_holds:
        sid = h["shipment_id"]
        if sid in old_a:
            kind = "rebooked" if h.get("rebook_ship") else "held"
            entries.append({"shipment_id": sid, "kind": kind, "before": _slot(old_a[sid]),
                            "after": None, "note": f"{h['action']} - {h['reason']}"})
        elif sid not in old_h:
            entries.append({"shipment_id": sid, "kind": "held", "before": None,
                            "after": None, "note": f"{h['action']} - {h['reason']}"})

    order = {"moved": 0, "rebooked": 1, "retimed": 2, "scheduled": 3, "held": 4,
             "new": 5, "completed": 6}
    entries.sort(key=lambda e: order.get(e["kind"], 9))
    return entries


def _slot(a: dict) -> dict:
    return {"wagon_id": a["wagon_id"], "team_id": a["team_id"],
            "load_start": a["load_start"], "window": f"{hhmm(a['load_start'])}-{hhmm(a['load_end'])}"}
