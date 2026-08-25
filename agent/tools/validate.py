"""Final-plan validator. Re-checks every hard constraint on whatever the
planner produced — defense in depth, so nothing illegal can ever be
published, whichever brain produced the plan.
"""
from core.clock import parse
from core.models import LOAD_MINUTES, WAGON_TURNAROUND_MIN
from agent.tools.prefilter import wagon_options
from agent.tools.schedule import shipment_floor


def validate_plan(assignments: list[dict], shipments_by_id: dict, wagons_by_id: dict,
                  ships_by_id: dict, now: str) -> list[str]:
    violations = []
    by_team, by_wagon = {}, {}

    for a in assignments:
        sid = a["shipment_id"]
        s = shipments_by_id.get(sid)
        if not s:
            violations.append(f"{sid}: unknown shipment")
            continue

        opts, _ = wagon_options(s, list(wagons_by_id.values()), ships_by_id, now)
        if a["wagon_id"] not in {o["wagon_id"] for o in opts}:
            violations.append(f"{sid}: wagon {a['wagon_id']} is not a legal pairing")

        expected = LOAD_MINUTES[s["cargo_type"]]
        if a["duration_min"] != expected:
            violations.append(f"{sid}: duration {a['duration_min']} != required {expected} min")

        cutoff = ships_by_id[s["target_ship"]]["loading_cutoff"]
        if a["load_end"] > cutoff:
            violations.append(f"{sid}: load ends {a['load_end']} after {s['target_ship']} cutoff {cutoff}")

        floor = shipment_floor(s, ships_by_id, now)
        if a["load_start"] < floor:
            violations.append(f"{sid}: starts before earliest allowed load {floor} (cold chain / port clock)")

        by_team.setdefault(a["team_id"], []).append(a)
        by_wagon.setdefault(a["wagon_id"], []).append(a)

    for tid, items in by_team.items():
        items.sort(key=lambda x: x["load_start"])
        for prev, nxt in zip(items, items[1:]):
            if parse(nxt["load_start"]) < parse(prev["load_end"]):
                violations.append(f"{tid}: overlapping loads {prev['shipment_id']} / {nxt['shipment_id']}")

    for wid, items in by_wagon.items():
        items.sort(key=lambda x: x["load_start"])
        for prev, nxt in zip(items, items[1:]):
            gap = (parse(nxt["load_start"]) - parse(prev["load_end"])).total_seconds() / 60
            if gap < WAGON_TURNAROUND_MIN:
                violations.append(
                    f"{wid}: reuse gap {int(gap)} min < {WAGON_TURNAROUND_MIN} min turnaround")

    return violations
