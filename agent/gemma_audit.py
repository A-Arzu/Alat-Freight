"""Second-model plan audit with Gemma.

A dispatch plan is safety-relevant, so we don't trust a single model's judgement
blindly. After Gemini produces a plan, Gemma (a second, independent Google model)
reviews the same shipments and the proposed assignments and flags any it would
have decided differently. It is ADVISORY ONLY — Gemma cannot move cargo or break
a hard constraint (those are already enforced in code); it can only lower the
confidence on a flagged assignment and attach its dissent to the reason. Agreement
is a signal too: assignments both models back read as higher-trust.

Opt-in via ENABLE_GEMMA_AUDIT=true so it can never destabilise the main demo, and
it degrades to a clean no-op if the model is unreachable — same philosophy as the
Gemini→deterministic fallback.
"""
import json
import os

AUDIT_PROMPT = """You are a second, independent reviewer auditing a rail-port dispatch plan that another
AI produced. Hard constraints (cargo/wagon compatibility, certifications, capacity, ship cutoffs)
are already guaranteed by code — do NOT re-check those. Judge only the SOFT choices: is each
shipment's priority and wagon sensible given SLA tier, deadline urgency, cargo scarcity and dwell?

For each assignment you would have decided differently, return an object:
  {"shipment_id": "...", "concern": "<one terse sentence>"}
Return STRICT JSON: {"flags": [ ... ]}. If the plan looks sound, return {"flags": []}.
Be sparing — flag only genuine disagreements, not stylistic nits."""


def _model_name() -> str:
    return os.environ.get("GEMMA_MODEL", "gemma-3-27b-it")


def _client(genai):
    """Prefer the Gemini API for Gemma (it serves the gemma-* models directly);
    fall back to whatever the ambient config is (e.g. Vertex) otherwise. A
    dedicated GEMMA_API_KEY lets the auditor use the Gemini API even when the
    primary planner runs on Vertex."""
    api_key = os.environ.get("GEMMA_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key, vertexai=False)
    return genai.Client()


def enabled() -> bool:
    return os.environ.get("ENABLE_GEMMA_AUDIT", "").lower() in ("1", "true", "yes")


def _payload(plan: dict, scope: list[dict], customers: dict, ships_by_id: dict) -> str:
    shipments = {s["id"]: s for s in scope}
    lines = []
    for a in plan["assignments"]:
        s = shipments.get(a["shipment_id"])
        if not s:
            continue
        tier = customers.get(s["customer_id"], {}).get("sla_tier", "standard")
        cutoff = ships_by_id.get(a["target_ship"], {}).get("loading_cutoff", "?")
        lines.append({
            "shipment_id": a["shipment_id"], "cargo": s["cargo_type"], "sla_tier": tier,
            "wagon": a["wagon_id"], "priority": a["priority"],
            "load": a["load_start"][11:], "ship": a["target_ship"], "ship_cutoff": cutoff,
        })
    return json.dumps({"assignments": lines,
                       "holds": [h["shipment_id"] for h in plan.get("holds", [])]}, default=str)


def audit(plan: dict, scope: list[dict], state: dict, emit) -> dict:
    """Annotate `plan` in place with Gemma's dissent. Returns a small summary."""
    if not enabled():
        return {"ran": False, "reason": "disabled"}
    try:
        from google import genai
    except ImportError:
        emit("reason", "Gemma audit skipped", "google-genai not installed")
        return {"ran": False, "reason": "sdk missing"}

    customers = {c["id"]: c for c in state.get("customers", [])}
    ships_by_id = {s["id"]: s for s in state.get("ships", [])}
    model = _model_name()
    try:
        client = _client(genai)
        resp = client.models.generate_content(
            model=model,
            contents=f"{AUDIT_PROMPT}\n\nPLAN:\n{_payload(plan, scope, customers, ships_by_id)}",
        )
        flags = _parse_flags(getattr(resp, "text", "") or "")
    except Exception as exc:                 # unreachable model must never fail a run
        emit("reason", "Gemma audit unavailable", f"{type(exc).__name__}: {exc}"[:160])
        return {"ran": False, "reason": "call failed"}

    by_id = {f["shipment_id"]: f["concern"] for f in flags
             if isinstance(f, dict) and f.get("shipment_id")}
    flagged = 0
    for a in plan["assignments"]:
        concern = by_id.get(a["shipment_id"])
        if concern:
            a["confidence"] = max(40, int(a.get("confidence", 75)) - 20)
            a["reason"] = f"{a['reason']} | Gemma flags: {concern[:120]}"
            a["gemma"] = "flagged"
            flagged += 1
        else:
            a["gemma"] = "concurred"

    total = len(plan["assignments"])
    if flagged:
        emit("reason", "Gemma cross-check",
             f"Second model ({model}) reviewed {total} assignments and flagged {flagged} "
             f"for lower confidence: {', '.join(sorted(by_id))}")
    else:
        emit("validate", "Gemma cross-check",
             f"Second model ({model}) concurred with all {total} assignments")
    return {"ran": True, "model": model, "flagged": flagged, "total": total,
            "shipment_ids": sorted(by_id)}


def _parse_flags(text: str) -> list:
    """Pull the flags array out of a model response that may be fenced or chatty."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    try:
        data = json.loads(text)
        flags = data.get("flags", []) if isinstance(data, dict) else []
        return flags if isinstance(flags, list) else []
    except (json.JSONDecodeError, AttributeError):
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return (json.loads(text[start:end + 1]).get("flags", []) or [])
            except json.JSONDecodeError:
                return []
        return []
