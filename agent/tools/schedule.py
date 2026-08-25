"""Time-slot engine. Given an ORDERED list of (shipment -> wagon) picks, it
computes concrete dock-team assignments and load windows deterministically:
earliest-feasible gap placement per team, wagon turnaround respected. The
planner (LLM or heuristic) decides order and pairing; this engine owns the
clock, so the model can never invent times.
"""
from core.clock import parse, iso, later, diff_min
from datetime import timedelta
from core.models import LOAD_MINUTES, WAGON_TURNAROUND_MIN


def shipment_floor(shipment: dict, ships_by_id: dict, now: str) -> str:
    """Earliest allowed load start: port clock, plus cold-chain window for
    perishables (reefer cargo loads close to its ship cutoff)."""
    floor = now
    cold = shipment.get("cold_chain_min")
    if cold:
        cutoff = ships_by_id[shipment["target_ship"]]["loading_cutoff"]
        floor = later(floor, iso(parse(cutoff) - timedelta(minutes=cold)))
    return floor


def _free(busy: list[tuple], start, end) -> bool:
    return all(end <= s or start >= e for s, e in busy)


def _earliest_fit(team_busy, wagon_busy, floor, duration_min, shift_end):
    """Earliest start >= floor where both team and wagon are free."""
    dur = timedelta(minutes=duration_min)
    points = {floor}
    points.update(e for _, e in team_busy if e >= floor)
    points.update(e for _, e in wagon_busy if e >= floor)
    for p in sorted(points):
        end = p + dur
        if end > shift_end:
            continue
        if _free(team_busy, p, end) and _free(wagon_busy, p, end):
            return p, end
    return None, None


def build_schedule(ordered: list[dict], shipments_by_id: dict, wagons_by_id: dict,
                   ships_by_id: dict, teams: list[dict], now: str,
                   fixed_slots: list[dict] | None = None):
    """ordered: [{shipment_id, wagon_id}] in load-priority order.
    fixed_slots: existing assignments to plan around (incremental re-plan).

    Returns (slots, violations)."""
    team_busy = {t["id"]: [] for t in teams}
    team_shift = {t["id"]: (parse(later(now, t["shift_start"])), parse(t["shift_end"]))
                  for t in teams}
    wagon_busy: dict[str, list] = {}
    pad = timedelta(minutes=WAGON_TURNAROUND_MIN)

    def block(tid, wid, start_dt, end_dt):
        team_busy[tid].append((start_dt, end_dt))
        wagon_busy.setdefault(wid, []).append((start_dt - pad, end_dt + pad))

    for f in fixed_slots or []:
        if f["team_id"] in team_busy:
            block(f["team_id"], f["wagon_id"], parse(f["load_start"]), parse(f["load_end"]))

    slots, violations = [], []
    for item in ordered:
        sid, wid = item["shipment_id"], item["wagon_id"]
        s, w = shipments_by_id[sid], wagons_by_id[wid]
        duration = LOAD_MINUTES[s["cargo_type"]]
        cutoff = ships_by_id[s["target_ship"]]["loading_cutoff"]

        floor = shipment_floor(s, ships_by_id, now)
        if w["status"] != "available" and w.get("available_at"):
            floor = later(floor, w["available_at"])
        floor_dt = parse(floor)

        best = None  # (start, end, tid)
        for tid, busy in team_busy.items():
            shift_start, shift_end = team_shift[tid]
            start, end = _earliest_fit(busy, wagon_busy.get(wid, []),
                                       max(floor_dt, shift_start), duration, shift_end)
            if start and (best is None or start < best[0]):
                best = (start, end, tid)

        if best is None:
            violations.append({"shipment_id": sid, "type": "no_capacity",
                               "detail": "no dock team + wagon window fits inside shift hours"})
            continue

        start_dt, end_dt, tid = best
        block(tid, wid, start_dt, end_dt)
        slack = diff_min(cutoff, iso(end_dt))
        if slack < 0:
            violations.append({"shipment_id": sid, "type": "cutoff_miss",
                               "detail": f"load ends {-slack} min after {s['target_ship']} cutoff"})

        slots.append({
            "shipment_id": sid, "wagon_id": wid, "team_id": tid,
            "load_start": iso(start_dt), "load_end": iso(end_dt),
            "duration_min": duration, "cutoff_slack_min": slack,
        })

    return slots, violations
