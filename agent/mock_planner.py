"""Deterministic heuristic planner.

Runs the same tools as the Gemini/ADK planner (pre-filter -> ordering ->
time-slot engine -> holds) with a transparent scoring policy instead of LLM
reasoning. Used for local development, and as the automatic fallback if the
model is unreachable mid-demo — the show must go on.
"""
from core.clock import hhmm, later, add_min
from core.models import SLA_RANK, LOAD_MINUTES
from agent.tools.prefilter import pairing_table
from agent.tools.schedule import build_schedule, shipment_floor

PLANNER_NAME = "deterministic heuristic (local fallback)"


def _pick_wagon(options):
    usable = [o for o in options if o["usable"]]
    if not usable:
        return None
    usable.sort(key=lambda o: (not o["reserved_match"], o["capacity_slack_kg"], o["available_from"]))
    return usable[0]


def _next_sailing(shipment, ships, current_ship):
    """Next ship to the same destination with a later cutoff."""
    dest = current_ship["destination"]
    later_ships = [s for s in ships
                   if s["destination"] == dest and s["loading_cutoff"] > current_ship["loading_cutoff"]]
    later_ships.sort(key=lambda s: s["loading_cutoff"])
    return later_ships[0] if later_ships else None


def plan(scope: list[dict], state: dict, trace, fixed_slots: list[dict] | None = None) -> dict:
    shipments_by_id = {s["id"]: s for s in state["shipments"]}
    wagons_by_id = {w["id"]: w for w in state["wagons"]}
    ships_by_id = {s["id"]: s for s in state["ships"]}
    customers = {c["id"]: c for c in state["customers"]}
    teams = state["teams"]
    now = state["meta"]["now"]
    plan_date = state["meta"]["plan_date"]

    holds = []
    plannable = []
    for s in scope:
        if not s.get("customs_cleared", True):
            holds.append({"shipment_id": s["id"], "action": "Hold in yard until customs release",
                          "reason": "customs clearance pending", "confidence": 85, "change": "held"})
        else:
            plannable.append(s)
    if holds:
        trace("reason", "Customs screen",
              f"{len(holds)} shipment(s) held pending clearance: "
              + ", ".join(h["shipment_id"] for h in holds))

    table, excluded_count = pairing_table(plannable, state["wagons"], ships_by_id, now)
    legal = sum(len(v) for v in table.values())
    trace("tool", "get_valid_pairings",
          f"Removed {excluded_count} illegal pairings (type, certification, capacity, "
          f"reservations, availability) - {legal} legal options remain")

    features = {}
    for s in plannable:
        opts = table[s["id"]]
        usable = [o for o in opts if o["usable"]]
        cutoff = ships_by_id[s["target_ship"]]["loading_cutoff"]
        features[s["id"]] = {
            "usable": len(usable),
            "sla": SLA_RANK.get(customers[s["customer_id"]]["sla_tier"], 2),
            "cutoff": cutoff,
            "cutoff_today": cutoff[:10] == plan_date,
            "arrived": s.get("arrived_at", now),
        }

    ordered_ships = sorted(
        plannable,
        key=lambda s: (features[s["id"]]["usable"], features[s["id"]]["sla"],
                       features[s["id"]]["cutoff"], features[s["id"]]["arrived"]))

    ordered, unschedulable = [], []
    for s in ordered_ships:
        pick = _pick_wagon(table[s["id"]])
        if pick is None:
            unschedulable.append(s)
        else:
            ordered.append({"shipment_id": s["id"], "wagon_id": pick["wagon_id"]})

    trace("reason", "Priority ordering",
          "Scarcity -> SLA tier -> ship cutoff -> dwell time: "
          + " > ".join(o["shipment_id"] for o in ordered[:8])
          + (" ..." if len(ordered) > 8 else ""))

    slots, violations = build_schedule(ordered, shipments_by_id, wagons_by_id,
                                       ships_by_id, teams, now, fixed_slots)
    trace("tool", "propose_schedule",
          f"Placed {len(slots)} loads across {len(teams)} dock teams"
          + (f" - {len(violations)} violation(s) to resolve" if violations else " - no conflicts"))

    # anything the engine could not place inside constraints becomes a hold
    placed = {x["shipment_id"] for x in slots}
    for v in violations:
        sid = v["shipment_id"]
        if sid in placed:
            slots = [x for x in slots if x["shipment_id"] != sid]
            placed.discard(sid)
        unschedulable.append(shipments_by_id[sid])

    assignments = []
    for slot in slots:
        s = shipments_by_id[slot["shipment_id"]]
        f = features[s["id"]]
        opts = table[s["id"]]
        pick = next(o for o in opts if o["wagon_id"] == slot["wagon_id"])

        priority = 1 if (f["usable"] <= 1 or (f["sla"] == 0 and f["cutoff_today"])) \
            else 2 if (f["cutoff_today"] or f["sla"] <= 1) else 3
        slack = slot["cutoff_slack_min"]
        confidence = 97 - 5 * max(0, f["usable"] - 1) - (6 if slack < 60 else 3 if slack < 120 else 0)
        confidence = max(62, min(98, confidence))

        parts = []
        if f["usable"] <= 1:
            parts.append(f"only viable wagon is {slot['wagon_id']} ({pick['wagon_type']})")
        elif pick["reserved_match"]:
            parts.append(f"standing-agreement wagon {slot['wagon_id']}")
        else:
            parts.append(f"{slot['wagon_id']} best fit ({pick['capacity_slack_kg']} kg spare)")
        if f["sla"] == 0:
            parts.append("premium SLA")
        if s.get("cold_chain_min"):
            floor = shipment_floor(s, ships_by_id, now)
            parts.append(f"cold-chain window opens {hhmm(floor)}")
        parts.append(f"clears {s['target_ship']} cutoff by {slack} min"
                     if slack < 180 else f"{s['target_ship']} cutoff comfortable")
        reason = "; ".join(parts)
        reason = reason[0].upper() + reason[1:]

        assignments.append({
            "shipment_id": s["id"], "wagon_id": slot["wagon_id"], "team_id": slot["team_id"],
            "load_start": slot["load_start"], "load_end": slot["load_end"],
            "duration_min": slot["duration_min"], "target_ship": s["target_ship"],
            "priority": priority, "confidence": confidence, "reason": reason,
            "status": "planned", "change": "new",
        })

    for s in unschedulable:
        current_ship = ships_by_id[s["target_ship"]]
        nxt = _next_sailing(s, state["ships"], current_ship)
        if nxt:
            opts = [o for o in table.get(s["id"], [])
                    if add_min(later(o["available_from"], now), LOAD_MINUTES[s["cargo_type"]])
                    <= nxt["loading_cutoff"]]
            retry = min((o["available_from"] for o in opts), default=None)
            holds.append({
                "shipment_id": s["id"],
                "action": f"Rebook onto {nxt['id']} ({nxt['name']}, {nxt['destination']}, "
                          f"departs {nxt['departs_at'][5:10]} {hhmm(nxt['departs_at'])})",
                "reason": f"no wagon can make {current_ship['id']} cutoff {hhmm(current_ship['loading_cutoff'])}",
                "retry_at": retry, "rebook_ship": nxt["id"], "confidence": 88,
                "change": "rebooked",
            })
        else:
            holds.append({"shipment_id": s["id"], "action": "Hold - notify customer",
                          "reason": "no feasible wagon or sailing", "confidence": 70,
                          "change": "held"})
    if unschedulable:
        trace("reason", "Recovery decisions",
              "; ".join(f"{h['shipment_id']}: {h['action']}" for h in holds
                        if h.get("change") == "rebooked"))

    return {"assignments": assignments, "holds": holds, "planner": PLANNER_NAME}
