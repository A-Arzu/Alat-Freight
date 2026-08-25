"""Plan-level KPIs shown in the dashboard and email summary."""
from core.clock import parse


def summarize(assignments: list[dict], holds: list[dict], teams: list[dict],
              planning_seconds: float, manual_baseline_min: int,
              shipments_by_id: dict | None = None) -> dict:
    planned = len(assignments)
    rebooked = sum(1 for h in holds if h.get("change") == "rebooked" or h.get("rebook_ship"))
    # SLA denominator: everything that had a sailing commitment today
    sla_total = planned + rebooked
    sla_met_pct = round(100 * planned / sla_total) if sla_total else 100

    util_pct = peak_util_pct = 0
    if assignments:
        starts = [parse(a["load_start"]) for a in assignments]
        ends = [parse(a["load_end"]) for a in assignments]
        window_start, window_end = min(starts), max(ends)
        window_min = max(1, (window_end - window_start).total_seconds() / 60)
        busy = sum(a["duration_min"] for a in assignments)
        util_pct = round(100 * busy / (len(teams) * window_min))

        # busiest 60-minute slice across all teams
        peak = 0
        cursor = window_start
        from datetime import timedelta
        while cursor < window_end:
            slice_end = cursor + timedelta(minutes=60)
            overlap = 0
            for a in assignments:
                s, e = parse(a["load_start"]), parse(a["load_end"])
                lo, hi = max(s, cursor), min(e, slice_end)
                overlap += max(0, (hi - lo).total_seconds() / 60)
            peak = max(peak, overlap / (len(teams) * 60))
            cursor = slice_end
        peak_util_pct = round(100 * peak)

    avg_dwell_h = 0
    if assignments and shipments_by_id:
        total = 0
        for a in assignments:
            s = shipments_by_id.get(a["shipment_id"])
            if s and s.get("arrived_at"):
                total += max(0, (parse(a["load_start"]) - parse(s["arrived_at"])).total_seconds() / 3600)
        avg_dwell_h = round(total / planned, 1)

    return {
        "planned": planned,
        "holds": len(holds),
        "rebooked": rebooked,
        "sla_met_pct": sla_met_pct,
        "util_pct": util_pct,
        "peak_util_pct": peak_util_pct,
        "avg_dwell_h": avg_dwell_h,
        "planning_seconds": round(planning_seconds, 1),
        "manual_baseline_min": manual_baseline_min,
    }
