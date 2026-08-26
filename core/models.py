"""Domain schema. Entities live in the store as plain dicts (JSON-friendly);
Pydantic models validate the one thing that must never be malformed: the
dispatch plan the agent submits.
"""
from typing import Optional
from pydantic import BaseModel, Field

CARGO_TYPES = ["hazmat", "perishable", "fragile", "machinery", "standard", "bulk"]
WAGON_TYPES = ["open", "covered", "closed", "reefer"]

# minutes to load one wagon, by cargo type
LOAD_MINUTES = {
    "hazmat": 45,
    "perishable": 60,
    "fragile": 50,
    "machinery": 50,
    "standard": 40,
    "bulk": 75,
}

SLA_RANK = {"premium": 0, "contract": 1, "standard": 2, "spot": 3}
WAGON_TURNAROUND_MIN = 20  # shunt + inspection between loads on the same wagon


class Assignment(BaseModel):
    shipment_id: str
    wagon_id: str
    team_id: str
    load_start: str            # ISO "YYYY-MM-DDTHH:MM"
    duration_min: int = Field(gt=0)
    load_end: str
    target_ship: str
    priority: int = Field(ge=1, le=3)   # 1 urgent, 2 asap, 3 today
    confidence: int = Field(ge=0, le=100)
    reason: str
    status: str = "planned"    # planned | completed | at_risk
    change: str = "new"        # new | unchanged | moved | retimed | completed


class Hold(BaseModel):
    shipment_id: str
    action: str                # what the dispatcher should do
    reason: str
    retry_at: Optional[str] = None
    rebook_ship: Optional[str] = None
    confidence: int = Field(ge=0, le=100, default=80)
    change: str = "new"        # new | held | rebooked


class DispatchPlan(BaseModel):
    id: str
    version: int = 1
    parent_id: Optional[str] = None
    plan_date: str
    generated_at: str
    trigger: str               # schedule | manual | event:<type>
    planner: str               # e.g. "gemini-3.5-flash via Google ADK" | "deterministic heuristic"
    assignments: list[Assignment]
    holds: list[Hold] = []
    summary: dict = {}
    diff: list[dict] = []      # v2+: [{shipment_id, kind, before, after, note}]
    status: str = "pending"    # pending | approved | overridden
