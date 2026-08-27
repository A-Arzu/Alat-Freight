# Devpost submission — copy/paste answers

Everything below is ready to paste into the Devpost form. All numbers are from **real runs on the
deployed Cloud Run service**, not estimates.

---

## Category

**Taskmaster**

## Project name

Port Operations Dispatch Agent

## Elevator pitch

An autonomous agent that plans a port's entire cargo-loading day in seconds — and re-plans it live
when a wagon breaks down, explaining every decision to the dispatcher who approves it.

## Hosted project URL

https://dispatch-agent-ygolewwlkq-uc.a.run.app

*(No login required. Press **Run agent**, then **Inject disruption → Wagon W003 breakdown**.)*

## Code repository

https://github.com/A-Arzu/Alat-Freight — public.

---

## Text description

### Features and functionality

Every morning a port dispatcher decides which waiting shipment loads onto which rail wagon, in what
order. They juggle eight kinds of constraints simultaneously: cargo-type rules (hazmat needs a
certified closed wagon, perishables need a reefer, fragile needs cover), weight and axle limits,
customer SLA tiers, cold-chain windows, wagon reservations and availability, dock-team capacity,
customs clearance, and hard ship loading cutoffs. Done by hand it takes about 45 minutes, and under
pressure the wrong wagon gets loaded first — premium cargo waits, perishables spoil, ships sail
without cargo that should have been aboard.

The Port Operations Dispatch Agent does the whole job autonomously:

1. **Ingests** the live port state from Firestore — shipment queue, wagon fleet, vessel schedule,
   dock-team calendars, port clock.
2. **Pre-filters every illegal option in deterministic code** before the model sees anything. In our
   dataset that removes 51 impossible cargo–wagon pairings, leaving 37 legal ones.
3. **Reasons with Gemini 3.5 Flash through Google ADK** over only the legal options — deciding
   priority order, wagon assignment and reuse across the day.
4. **Computes concrete times deterministically.** The model proposes an *order*; a gap-aware
   time-slot engine owns the clock, so Gemini can never invent a load window.
5. **Validates and self-corrects.** A plan can only be submitted through a tool that re-checks every
   hard constraint; violations bounce back to the agent to fix.
6. **Publishes and notifies** — a versioned plan to Firestore, plus a formatted HTML email with an
   Excel attachment to a dispatcher address chosen at runtime in the dashboard.
7. **Re-plans on disruption.** A wagon breakdown, an advanced ship cutoff or a dock-team outage
   triggers deterministic impact analysis; the agent re-plans only the affected shipments and
   publishes plan v2 with a full diff — moved, retimed, rebooked, already-completed.
8. **Keeps a human in command.** Every assignment carries a confidence score and a one-sentence
   justification; the dispatcher approves or overrides in one click, and those decisions accumulate
   in an outcomes log shown in the dashboard.

Measured on the deployed service: **11 loads planned in ~85 seconds** (vs a 45-minute manual
baseline) at **100% SLA compliance** and **100% peak dock utilisation**, with **0 hard-constraint
violations**. After the wagon-breakdown disruption the agent moved the affected perishable to the
only other reefer — still clearing its ship cutoff by 90 minutes — and rebooked the shipment it
could not save onto the next sailing, holding SLA at 91% instead of failing silently.

### Technologies used

- **Gemini 3.5 Flash** on **Vertex AI** — the reasoning core (soft trade-offs and recovery choices).
- **Google Agent Development Kit (ADK)** — `LlmAgent` with four function tools and a tool-gated
  submission path.
- **Cloud Run** — one container serving the FastAPI backend, the ADK agent and the React dashboard;
  scales to zero.
- **Firestore** — shipments, wagons, vessels, versioned plans, run traces, outcomes.
- **Cloud Scheduler** — fires the 06:00 Asia/Baku dispatch run automatically every day.
- **Secret Manager** — Gmail app password for dispatcher email.
- **Cloud Logging** — the agent's step-by-step reasoning trace.
- **Cloud Build / Artifact Registry** — container build and storage.
- Python 3.12, FastAPI, Pydantic, openpyxl, React 18 + Vite.

### Other data sources used

Synthetic port data only — no third-party datasets. `data/seed.py` generates a deliberately
adversarial scenario: a hazmat shipment with exactly one certified wagon, two perishables competing
for the only available reefer under cold-chain windows, a wagon reserved by standing agreement, a
customs-blocked shipment, an over-capacity heavyweight, and a second reefer in transit until 15:30
that becomes the recovery path when the first one fails. Everything is date-relative with a frozen
port clock, so runs are reproducible on any day.

### Findings and learnings

- **Pre-filtering is what makes an LLM trustworthy in operations.** By removing every illegal option
  in code before the model sees it — and re-validating afterwards — the failure mode shifts from
  "dangerous" to merely "suboptimal". That single decision is what makes us comfortable letting a
  model schedule hazardous cargo.
- **Give the model a calculator, not a calendar.** Letting Gemini choose the *order* while a
  deterministic engine computes the times eliminated an entire class of hallucination.
- **LLMs don't assume resource reuse.** Gemini's first cloud plan held three schedulable shipments
  citing "capacity limits" — it hadn't realised wagons can be reused after a turnaround. Adding an
  explicit *capacity facts* section to the prompt took it from 8 loads and 4 holds to a full
  11-load day, with the reuse reasoning appearing in its own explanations.
- **Model output is untrusted input all the way through.** A priority value outside 1–3 would have
  failed schema validation *after* planning succeeded — past the fallback safety net — turning a
  cosmetic model slip into a dead run. We coerce and clamp at the tool boundary.
- **Model output can be incomplete, not just wrong.** Nothing forced Gemini to account for every
  shipment, so one could silently vanish from the plan, the board and the email. The submission tool
  now rejects any plan leaving an in-scope shipment neither assigned nor explicitly held.
- **The dangerous bugs live in the gap between two implementations.** Our in-memory store's `update`
  no-ops on a missing key while Firestore's `set(merge=True)` *creates* the document — an unexpected
  id would have written a phantom record with no `id` field and crashed every later run. Local tests
  could never have caught it.
- **Test the UI against the deployed configuration, not just the API.** Our `curl` checks all passed
  while the dashboard's own buttons returned 401 in production: the frontend bundle had baked in a
  build-time token that no longer matched the deployed service. A client bundle cannot hold a
  deploy-time secret; the server now serves a derived token at runtime.
- **Design so the demo can never die.** When our first deployment pointed at a Gemini model ID that
  isn't publicly released, the deterministic fallback planner kept the service fully functional —
  honestly labelled in the UI — while we fixed the model.
- **Cloud Run has its own trivia.** Its frontend reserves `/healthz` and rejects body-less POSTs with
  411; background threads can be CPU-throttled after a response, so scheduled runs use a synchronous
  path.

---

## Testing instructions for judges

**Fastest path (no setup):** open the hosted URL, press **Run agent** (~85 s — the live trace shows
Gemini reasoning as it goes), then **Inject disruption → Wagon W003 breakdown** and watch plan v2
appear with a diff. Press **Approve plan** to see the human-in-the-loop decision recorded in the
Decision log. **Reset** restores the demo dataset at any time.

**Run locally:**

```bash
git clone https://github.com/A-Arzu/Alat-Freight.git && cd Alat-Freight
pip install fastapi "uvicorn[standard]" "pydantic>=2.7" openpyxl
cd web && npm install && npm run build && cd ..
uvicorn api.main:app --port 8000     # http://localhost:8000
```

Locally the deterministic fallback planner runs (labelled `PLANNER: FALLBACK`) so no Google
credentials are needed; set `PLANNER=gemini` with Vertex AI credentials for the real model.

**Deploy it yourself:** `bash deploy/deploy.sh YOUR_PROJECT_ID`, then
`bash deploy/verify.sh <URL> <TOKEN>` — the verify script proves end to end that Gemini, not the
fallback, produced the plan.

**Tests:** `python test_pipeline.py`, `test_scenarios.py`, `test_email.py`, `test_hardening.py`,
`test_adk_wiring.py`.

## Which Google SDK did you use?

**Agent Development Kit (ADK)** — plus the Google GenAI SDK underneath it for Vertex AI access.

## Additional Google AI models (bonus)

**Gemma** — an opt-in second-model audit (`ENABLE_GEMMA_AUDIT=true`). After Gemini produces a plan,
Gemma independently reviews the same shipments and flags any assignment it would have decided
differently; flagged assignments get their confidence lowered and Gemma's dissent attached to the
reason. It's advisory (it can never break a hard constraint) and degrades to a clean no-op if the
model isn't reachable — a genuine two-model verification pattern rather than a token integration.

## Which Google Cloud services did you use?

Cloud Run · Vertex AI · Firestore · Cloud Scheduler · Secret Manager · Cloud Logging ·
Cloud Build · Artifact Registry

## Disclosures

Built entirely new during the submission period; all commit history is public and within the window.
Third-party components are standard open-source libraries (FastAPI, Uvicorn, Pydantic, openpyxl,
React, Vite, google-adk, google-genai, google-cloud-firestore). No pre-existing project code was
reused. All data is synthetic.
