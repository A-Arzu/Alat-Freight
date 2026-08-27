"""Gemma second-model audit: parsing, annotation, gating, and graceful failure.
The Gemma model itself is mocked, so this needs no credentials.
Run: python test_gemma.py
"""
import io
import os
import sys
import uuid
from datetime import datetime

os.environ["TRACE_DELAY_MS"] = "0"
os.environ["PLANNER"] = "mock"
os.environ["STORE"] = "memory"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from agent import gemma_audit
from core.store import MemoryStore
from data.seed import build_state
from agent.pipeline import execute_run

STEPS = []


def emit(kind, label, detail=""):
    STEPS.append((kind, label, detail))


# ---- 1. flag parsing tolerates fences and chatter ----------------------
assert gemma_audit._parse_flags('{"flags": []}') == []
assert gemma_audit._parse_flags('{"flags": [{"shipment_id":"S002","concern":"x"}]}')[0]["shipment_id"] == "S002"
assert gemma_audit._parse_flags('```json\n{"flags": [{"shipment_id":"S002","concern":"y"}]}\n```')[0]["shipment_id"] == "S002"
assert gemma_audit._parse_flags('Sure! Here it is:\n{"flags": [{"shipment_id":"S004","concern":"z"}]}\nHope that helps') \
    [0]["shipment_id"] == "S004"
assert gemma_audit._parse_flags('not json at all') == []
assert gemma_audit._parse_flags('') == []
print("flag parsing: OK (json / fenced / chatty / garbage all handled)")

# ---- 2. disabled by default -------------------------------------------
os.environ.pop("ENABLE_GEMMA_AUDIT", None)
assert gemma_audit.enabled() is False
r = gemma_audit.audit({"assignments": []}, [], {}, emit)
assert r == {"ran": False, "reason": "disabled"}
print("off by default: OK")

# ---- build a real plan to audit ---------------------------------------
store = MemoryStore()
store.reset(build_state())
rid = f"run-{uuid.uuid4().hex[:6]}"
store.upsert("runs", {"id": rid, "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                      "finished_at": None, "status": "running", "trigger": "manual",
                      "scenario": None, "steps": [], "plan_id": None, "planner": None})
execute_run(store, rid, "manual")
plan = store.get("plans", store.get("runs", rid)["plan_id"])
scope = store.all("shipments")
state = store.state()

# ---- 3. enabled + a Gemma that flags one assignment -------------------
os.environ["ENABLE_GEMMA_AUDIT"] = "true"
target = plan["assignments"][2]["shipment_id"]
before_conf = plan["assignments"][2]["confidence"]


class FakeResp:
    def __init__(self, text): self.text = text


class FakeModels:
    def __init__(self, text): self._text = text
    def generate_content(self, model, contents):
        FakeClient.seen_model = model
        return FakeResp(self._text)


class FakeClient:
    seen_model = None
    _text = ''
    def __init__(self, *a, **k): self.models = FakeModels(FakeClient._text)


import agent.gemma_audit as ga
from google import genai

FakeClient._text = '{"flags": [{"shipment_id": "%s", "concern": "spot cargo should not hold a premium wagon"}]}' % target
STEPS.clear()
orig = genai.Client
genai.Client = FakeClient
try:
    res = ga.audit(plan, scope, state, emit)
finally:
    genai.Client = orig

assert res["ran"] is True and res["flagged"] == 1, res
flagged = next(a for a in plan["assignments"] if a["shipment_id"] == target)
assert flagged["gemma"] == "flagged"
assert flagged["confidence"] == max(40, before_conf - 20), (flagged["confidence"], before_conf)
assert "Gemma flags:" in flagged["reason"]
assert all(a["gemma"] in ("flagged", "concurred") for a in plan["assignments"])
assert "gemma-3" in (FakeClient.seen_model or ""), FakeClient.seen_model
assert any(l == "Gemma cross-check" for _, l, _ in STEPS), STEPS
print(f"flag path: OK ({target} confidence {before_conf}→{flagged['confidence']}, model={FakeClient.seen_model})")

# ---- 4. a Gemma that concurs on everything ----------------------------
store.reset(build_state())
store.upsert("runs", {"id": rid, "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                      "finished_at": None, "status": "running", "trigger": "manual",
                      "scenario": None, "steps": [], "plan_id": None, "planner": None})
execute_run(store, rid, "manual")
plan2 = store.get("plans", store.get("runs", rid)["plan_id"])
FakeClient._text = '{"flags": []}'
genai.Client = FakeClient
try:
    res2 = ga.audit(plan2, store.all("shipments"), store.state(), emit)
finally:
    genai.Client = orig
assert res2["flagged"] == 0 and res2["ran"] is True
assert all(a["gemma"] == "concurred" for a in plan2["assignments"])
print(f"concur path: OK (all {res2['total']} assignments concurred)")

# ---- 5. an unreachable Gemma must not break the run -------------------
class ExplodingClient:
    def __init__(self, *a, **k): raise OSError("model gemma-3-27b-it not found in project")

genai.Client = ExplodingClient
try:
    res3 = ga.audit(plan2, store.all("shipments"), store.state(), emit)
finally:
    genai.Client = orig
assert res3["ran"] is False and res3["reason"] == "call failed", res3
print("unreachable model: OK (contained, run survives)")

os.environ.pop("ENABLE_GEMMA_AUDIT", None)
print("\nALL GEMMA TESTS PASSED")
