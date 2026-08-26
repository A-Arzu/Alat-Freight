# 4-minute demo video — shot list

Target: **3:50**. Hard cap 4:00. Public on YouTube, uploaded by **Aug 30** (processing takes hours).

## Before you hit record

```bash
# no cold starts on camera
gcloud run services update dispatch-agent --region us-central1 --min-instances 1
# clean demo state (grab the token from the deploy output)
curl -sS -X POST "$URL/api/seed" -H "X-Run-Token: $TOKEN" -d ''
```

- Set the dispatcher email in the dashboard (**Send plans to** → your inbox → **Save**) and send one
  test plan so the first message is out of spam.
- Browser at 1440×900, zoom 100%, bookmarks bar hidden, no notifications.
- Tabs open in this order: **1** dashboard · **2** your inbox · **3** Cloud Run console ·
  **4** Firestore console · **5** Cloud Scheduler console.
- Record in short clips — one per section — so you can redo a single take.
- The Gemini run takes **~85 s**. Do **not** film it in real time: start it, cut, and rejoin when the
  plan lands, or speed that section up 4–6×. The stage stepper (Ingest → Filter → Reason → Schedule
  → Validate → Publish) with its live timer makes the sped-up section read clearly.

---

## 0:00–0:15 — Hook (dashboard already open, plan visible)

> "A port dispatcher spends about 45 minutes every morning deciding which cargo loads onto which
> rail wagon. This agent does it in under two minutes — and when a wagon breaks down mid-shift, it
> re-plans the day by itself."

**On screen:** the control tower with a completed plan. Cursor drifts across the KPI strip.
**On-screen text:** `45 min → 85 s · 100% SLA · 0 constraint violations`

## 0:15–0:40 — The problem

> "Eight constraint families collide here: hazmat needs a certified wagon, perishables need a reefer
> inside a cold-chain window, premium customers have contractual SLAs, and ships have hard loading
> cutoffs. Miss one and cargo spoils or a ship sails without it."

**On screen:** scroll the wagon fleet and vessel schedule; hover a cutoff countdown. Overlay the
eight constraint names as fast text.

## 0:40–1:35 — The agent plans the day

Click **Run agent**. Cut/speed through the run, then land on the finished plan.

> "It ingests the port state, then removes every physically illegal pairing in code — 51 of them
> here — before Gemini sees anything. Gemini then reasons only over legal options: priority order,
> which wagon, and how to reuse wagons across the day. It proposes an order; a deterministic engine
> computes the actual times, so the model can never invent a load window."

**Zoom on one assignment's reasoning line:**
`S001 → W001 · Only hazmat-certified wagon; premium SLA; clears SHIP-01 cutoff by 645 min`

> "Every assignment carries a confidence score and a reason a dispatcher can argue with."

Cut to **tab 2 (inbox)**: the formatted plan email with the Excel attachment.

## 1:35–2:35 — The disruption (the peak — give it room)

Click **Inject disruption → Wagon W003 breakdown**.

> "It's 09:30. The reefer wagon carrying two perishable shipments fails inspection."

Point at the trace: `impact_analysis — 2 assignments affected, 4 already loaded, 5 untouched`.

> "It doesn't re-plan the day — it re-plans only what broke. Four loads already went out; five are
> untouched."

Land on the diff panel:

> "S003 moves to the port's only other reefer and still clears its ship cutoff by 90 minutes. S007
> can't be saved, so the agent rebooks it onto the next Baku sailing rather than letting it rot on
> the dock — and says so."

**On screen:** the Gantt's dashed ghost slots showing where cargo *was*; the routing map re-drawing.
Then click **Approve plan** → the Decision log records it.

## 2:35–3:25 — Proof it runs on Google Cloud

**Tab 3 — Cloud Run:** the `dispatch-agent` service, region, and the invocations graph.

> "The agent runs on Cloud Run — one container, scales to zero."

**Tab 4 — Firestore:** open `dispatch_plans`, show `plan-…-v1` and `-v2` documents side by side.

> "Every plan version is persisted in Firestore, with the diff and the reasoning."

**Tab 5 — Cloud Scheduler:** the `daily-dispatch` job, `0 6 * * *`, last run succeeded.

> "And it doesn't wait to be asked — Cloud Scheduler triggers the 06:00 plan every morning. This one
> ran on its own today."

**Cloud Logging (worth 8 s — this is the strongest proof):** open Logs Explorer with

```
jsonPayload.component="dispatch-agent"
```

> "And the agent's reasoning isn't just in the UI — every step is structured server-side logging."

Split-screen this against the dashboard's Agent Activity panel showing the same steps. Start the run
*before* cutting to Logs Explorer; ingest lags a few seconds, so don't film a live tail.

## 3:25–3:50 — Impact and architecture

> "Deterministic code owns the hard constraints, Gemini owns the judgment calls, and a human owns
> the final approval. Forty-five minutes of manual planning becomes eighty-five seconds, at a
> hundred percent SLA compliance — and when the day goes wrong, the agent is the first to know."

**On screen:** `docs/architecture.png` full-frame for the last 8–10 seconds.

---

## Must appear on camera (submission requirements)

- [ ] The agent visibly working (run + disruption re-plan)
- [ ] Google Cloud proof — Cloud Run **and** Firestore (Scheduler and Logging are bonus)
- [ ] The `.run.app` URL legible in the address bar at least once
- [ ] Under 4:00, English, public on YouTube

## If something goes wrong mid-take

- Button does nothing → check the toast; the service shows the real error now.
- Plan looks wrong → **Reset**, then re-run; the dataset is deterministic.
- Run seems stuck → runs release automatically after 6 minutes, and **Reset** is never disabled.
