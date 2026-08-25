"""Hard-constraint pre-filter. Deterministic by design: the LLM only ever
sees cargo-wagon pairings that are physically and legally possible. Every
exclusion carries a reason so the agent trace can show its work.
"""
from core.clock import add_min, later
from core.models import LOAD_MINUTES

# cargo type -> acceptable wagon types
TYPE_RULES = {
    "hazmat": ["closed"],            # plus certification check below
    "perishable": ["reefer"],
    "fragile": ["covered", "closed"],
    "machinery": ["open", "covered"],
    "standard": ["open", "covered", "closed"],
    "bulk": ["open"],
}


def wagon_options(shipment: dict, wagons: list[dict], ships_by_id: dict, now: str):
    """Return (options, excluded) for one shipment.

    An option: {wagon_id, wagon_type, available_from, capacity_slack_kg,
    reserved_match, usable}. usable == the wagon can still make this
    shipment's ship cutoff (cold-chain window included).
    """
    from agent.tools.schedule import shipment_floor  # local import, no cycle at module load

    options, excluded = [], []
    cutoff = ships_by_id[shipment["target_ship"]]["loading_cutoff"]
    duration = LOAD_MINUTES[shipment["cargo_type"]]
    earliest = shipment_floor(shipment, ships_by_id, now)

    for w in wagons:
        wid = w["id"]

        def out(reason):
            excluded.append({"wagon_id": wid, "reason": reason})

        if w["status"] == "out_of_service":
            out("out of service")
            continue
        if w["type"] not in TYPE_RULES[shipment["cargo_type"]]:
            out(f"{w['type']} wagon cannot carry {shipment['cargo_type']}")
            continue
        if shipment["cargo_type"] == "hazmat" and "hazmat" not in w.get("certifications", []):
            out("no hazmat certification")
            continue
        if shipment["weight_kg"] > w["capacity_kg"]:
            out(f"over capacity ({shipment['weight_kg']} > {w['capacity_kg']} kg)")
            continue
        reserved = w.get("reserved_for")
        if reserved and reserved != shipment["customer_id"]:
            out(f"reserved for {reserved}")
            continue

        available_from = now if w["status"] == "available" else w.get("available_at") or now
        start_floor = later(earliest, available_from)
        usable = add_min(start_floor, duration) <= cutoff
        options.append({
            "wagon_id": wid,
            "wagon_type": w["type"],
            "available_from": available_from,
            "capacity_slack_kg": w["capacity_kg"] - shipment["weight_kg"],
            "reserved_match": bool(reserved and reserved == shipment["customer_id"]),
            "usable": usable,
        })

    return options, excluded


def pairing_table(shipments: list[dict], wagons: list[dict], ships_by_id: dict, now: str):
    """Options for every shipment + total exclusion count (for the trace)."""
    table, total_excluded = {}, 0
    for s in shipments:
        opts, excl = wagon_options(s, wagons, ships_by_id, now)
        table[s["id"]] = opts
        total_excluded += len(excl)
    return table, total_excluded
