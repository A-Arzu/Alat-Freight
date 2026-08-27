"""The demo "story dataset". Deterministic and date-relative: everything is
seeded against today's date with a frozen port clock (meta.now = 06:30), so
the plan is reproducible whenever you run it.

The data is engineered so the day tells a story:
  - S001 hazmat has exactly one certified wagon and a premium SLA.
  - S007 (perishable, SHIP-02 cutoff 14:00) and S003 (perishable, SHIP-01
    cutoff 18:00) both depend on reefer wagon W003; W006 (the only other
    reefer) is in transit until 15:30.
  - Injecting the W003 breakdown at port clock 09:30 forces the agent to
    save S003 via W006 and rebook S007 onto the next Baku sailing.
  - S012 is not customs cleared -> held in v1.
"""
from datetime import date, timedelta


def _d(day_offset: int, hhmm: str) -> str:
    d = date.today() + timedelta(days=day_offset)
    return f"{d.isoformat()}T{hhmm}"


def build_state() -> dict:
    T = _d  # alias

    customers = [
        {"id": "CUST-A", "name": "TransCaspian Chem", "sla_tier": "premium"},
        {"id": "CUST-B", "name": "Karvan Machinery", "sla_tier": "standard"},
        {"id": "CUST-C", "name": "AgroFresh Export", "sla_tier": "premium"},
        {"id": "CUST-D", "name": "SpotFreight Ltd", "sla_tier": "spot"},
        {"id": "CUST-E", "name": "Silk Road Textiles", "sla_tier": "contract"},
        {"id": "CUST-F", "name": "Absheron Commodities", "sla_tier": "standard"},
    ]

    ships = [
        {"id": "SHIP-01", "name": "MV Anadolu", "destination": "Istanbul",
         "departs_at": T(1, "14:00"), "loading_cutoff": T(0, "18:00")},
        {"id": "SHIP-02", "name": "MV Khazar", "destination": "Baku",
         "departs_at": T(0, "16:00"), "loading_cutoff": T(0, "14:00")},
        {"id": "SHIP-03", "name": "MV Rioni", "destination": "Tbilisi",
         "departs_at": T(3, "08:00"), "loading_cutoff": T(1, "18:00")},
        {"id": "SHIP-04", "name": "MV Absheron", "destination": "Baku",
         "departs_at": T(2, "10:00"), "loading_cutoff": T(2, "08:00")},
    ]

    wagons = [
        {"id": "W001", "type": "closed", "capacity_kg": 25000, "certifications": ["hazmat"],
         "status": "available", "available_at": None},
        {"id": "W002", "type": "open", "capacity_kg": 30000, "certifications": [],
         "status": "available", "available_at": None},
        {"id": "W003", "type": "reefer", "capacity_kg": 22000, "certifications": ["cold-chain"],
         "status": "available", "available_at": None},
        {"id": "W004", "type": "open", "capacity_kg": 30000, "certifications": [],
         "status": "maintenance", "available_at": T(0, "14:00")},
        {"id": "W005", "type": "covered", "capacity_kg": 24000, "certifications": [],
         "status": "available", "available_at": None},
        {"id": "W006", "type": "reefer", "capacity_kg": 22000, "certifications": ["cold-chain"],
         "status": "in_transit", "available_at": T(0, "15:30")},
        {"id": "W007", "type": "open", "capacity_kg": 28000, "certifications": [],
         "status": "available", "available_at": None},
        {"id": "W008", "type": "covered", "capacity_kg": 24000, "certifications": [],
         "status": "available", "available_at": None, "reserved_for": "CUST-E"},
    ]

    teams = [
        {"id": "T1", "name": "Dock Team 1", "shift_start": T(0, "06:00"), "shift_end": T(0, "20:00")},
        {"id": "T2", "name": "Dock Team 2", "shift_start": T(0, "08:00"), "shift_end": T(0, "20:00")},
    ]

    def ship_def(sid, cargo, kg, cust, ship, arrived, cleared=True, cold=None, note=""):
        s = {"id": sid, "cargo_type": cargo, "weight_kg": kg, "customer_id": cust,
             "target_ship": ship, "arrived_at": arrived, "customs_cleared": cleared,
             "note": note}
        if cold:
            s["cold_chain_min"] = cold
        return s

    shipments = [
        ship_def("S001", "hazmat", 18000, "CUST-A", "SHIP-01", T(-1, "22:15"),
                 note="Class 8 corrosives, placarded"),
        ship_def("S002", "machinery", 21000, "CUST-B", "SHIP-03", T(-1, "16:40"),
                 note="CNC mill, crated"),
        ship_def("S003", "perishable", 15000, "CUST-C", "SHIP-01", T(0, "04:10"),
                 cold=240, note="Chilled produce, reefer at 4C"),
        ship_def("S004", "standard", 12000, "CUST-D", "SHIP-03", T(-2, "11:30"),
                 note="Palletized retail goods"),
        ship_def("S005", "fragile", 9000, "CUST-B", "SHIP-01", T(-1, "09:20"),
                 note="Glass panels"),
        ship_def("S006", "bulk", 26000, "CUST-F", "SHIP-03", T(-1, "14:05"),
                 note="Bagged grain"),
        ship_def("S007", "perishable", 14000, "CUST-C", "SHIP-02", T(0, "03:45"),
                 cold=240, note="Dairy, reefer at 2C"),
        ship_def("S008", "standard", 11000, "CUST-D", "SHIP-03", T(-2, "18:50"),
                 note="Household appliances"),
        ship_def("S009", "machinery", 19000, "CUST-B", "SHIP-03", T(-1, "20:10"),
                 note="Pump skids"),
        ship_def("S010", "standard", 28000, "CUST-F", "SHIP-03", T(-3, "07:00"),
                 note="Steel coils - heavy"),
        ship_def("S011", "standard", 10000, "CUST-E", "SHIP-03", T(-1, "12:30"),
                 note="Textile bales, standing agreement"),
        ship_def("S012", "standard", 13000, "CUST-D", "SHIP-03", T(0, "05:20"),
                 cleared=False, note="Customs docs pending"),
    ]

    meta = [{
        "id": "meta",
        "now": T(0, "06:30"),          # frozen port clock
        "plan_date": date.today().isoformat(),
        "port_name": "Port Operations Dispatch Agent",
        "manual_baseline_min": 45,
    }]

    scenarios = [{
        "id": "scenarios",
        "items": [
            {"key": "wagon_breakdown", "label": "Wagon W003 breakdown",
             "detail": "Reefer W003 fails axle inspection mid-morning",
             "event": {"type": "wagon_breakdown", "payload": {"wagon_id": "W003"}},
             "advance_clock_to": T(0, "09:30")},
            {"key": "ship_advanced", "label": "SHIP-01 cutoff moved to 14:30",
             "detail": "MV Anadolu berth window shortened by port authority",
             "event": {"type": "ship_advanced",
                       "payload": {"ship_id": "SHIP-01", "new_cutoff": T(0, "14:30")}},
             "advance_clock_to": T(0, "09:30")},
            {"key": "team_outage", "label": "Dock Team 2 crane fault",
             "detail": "T2 gantry crane down from 09:30, out for the day",
             "event": {"type": "team_outage",
                       "payload": {"team_id": "T2", "from": T(0, "09:30")}},
             "advance_clock_to": T(0, "09:30")},
        ],
    }]

    return {
        "customers": customers, "ships": ships, "wagons": wagons, "teams": teams,
        "shipments": shipments, "meta": meta + scenarios,
        "plans": [], "runs": [], "events": [], "outcomes": [], "emails": [],
    }
