# Submission image gallery

Captured live from the deployed Cloud Run service — every image shows the real
`gemini-3.5-flash via Google ADK` planner. Upload to the Devpost **Image gallery**
in this order (the first image is the cover). Suggested captions included.

| # | File | Caption for Devpost |
|---|------|---------------------|
| 1 | `01-dispatch-plan.png` | **The control tower** — Gemini plans 11 loads at 100% SLA in ~90s, a reason and confidence on every assignment, with the agent's tool calls and reasoning streaming live. |
| 2 | `04-disruption-diff.png` | **Live disruption recovery** — when reefer W003 breaks down mid-shift, the agent re-plans only what's affected: S003 moved to the other reefer, S007 rebooked to the next sailing, 4 loads already completed. |
| 3 | `05-dock-gantt.png` | **Dock schedule** — two dock-team lanes with the 09:30 port-clock line; dashed "pre-disruption" ghosts show exactly what the agent re-routed after the breakdown. |
| 4 | `02-agent-reasoning.png` | **Real agentic reasoning** — the ingest → filter → reason → schedule → validate → publish pipeline, with Gemini's own trade-off explanation (scarce reefer reused across two shipments instead of waiting for the late one). |
| 5 | `03-routing-map.png` | **Cargo routing** — shipment → wagon → vessel, priority-coloured; the customs-blocked S012 is held in the yard. |
| 6 | `07-replan-board.png` | **Plan v2 after recovery** — the updated board: completed loads marked, the moved and rebooked shipments highlighted. |
| 7 | `06-decision-log.png` | **Decision log** — every plan version, the human's approve/override, and the running scorecard (avg confidence, plan time, speed-up vs manual). |

Notes:
- All are PNG, well under Devpost's 5 MB limit; the cover (`01`) is a clean 3:2.
- Planning time varies run to run (~60–95 s of real Gemini reasoning) — the numbers are live, not staged.
- Regenerate any time from the deployed service with the capture scripts (see the repo's demo notes); nothing here is hand-edited.
