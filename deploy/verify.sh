#!/usr/bin/env bash
# End-to-end verification of a deployed service. Proves the full story on
# the cloud: seed -> morning plan (Gemini via ADK) -> disruption -> plan v2.
#
#   bash deploy/verify.sh https://dispatch-agent-xxxx.run.app RUN_TOKEN
set -euo pipefail

URL="${1:?usage: bash deploy/verify.sh SERVICE_URL RUN_TOKEN}"
TOKEN="${2:?usage: bash deploy/verify.sh SERVICE_URL RUN_TOKEN}"
URL="${URL%/}"

say() { echo; echo "---- $* ----"; }

py() { python3 -c "$1" 2>/dev/null || python -c "$1"; }

# NOTE: /healthz is reserved by Cloud Run's Google Frontend -> probe the API
# instead; bodyless POSTs need -d '' or the frontend rejects them with 411.
say "health"
curl -sSf -o /dev/null "${URL}/api/state" && echo "ok"

say "seed demo data"
curl -sSf -X POST "${URL}/api/seed" -H "X-Run-Token: ${TOKEN}" -d '' && echo

say "morning optimization (sync - waits for the plan)"
curl -sSf --max-time 280 -X POST "${URL}/optimize?sync=true" -H "X-Run-Token: ${TOKEN}" -d '' && echo

say "plan v1"
STATE="$(curl -sSf "${URL}/api/state")"
echo "$STATE" | py "
import sys, json
s = json.load(sys.stdin)
p = s['plans'][0]
print('plan:', p['id'], '| planner:', p['planner'])
print('assignments:', len(p['assignments']), '| holds:', len(p['holds']),
      '| SLA:', p['summary']['sla_met_pct'], '%')
assert p['assignments'], 'no assignments!'
"

say "disruption: wagon W003 breakdown (sync)"
curl -sSf --max-time 280 -X POST "${URL}/events?sync=true" -H "X-Run-Token: ${TOKEN}" \
  -H "Content-Type: application/json" -d '{"scenario": "wagon_breakdown"}' && echo

say "plan v2 diff"
STATE="$(curl -sSf "${URL}/api/state")"
echo "$STATE" | py "
import sys, json
s = json.load(sys.stdin)
p = s['plans'][0]
print('plan:', p['id'], '| planner:', p['planner'])
for d in p['diff']:
    if d['kind'] != 'completed':
        print(' ', d['kind'], d['shipment_id'],
              (d.get('before') or {}).get('window','-'), '->',
              (d.get('after') or {}).get('window','-'))
assert p['version'] >= 2, 'no v2 plan!'
changed = [d for d in p['diff'] if d['kind'] not in ('completed',)]
assert changed, 'no changes in diff!'
print('planner check:', 'GEMINI OK' if 'adk' in p['planner'].lower() or 'gemini' in p['planner'].lower()
      else 'WARNING: fallback planner ran - check Vertex AI access / Cloud Run logs')
"

say "reseed for a clean demo"
curl -sSf -X POST "${URL}/api/seed" -H "X-Run-Token: ${TOKEN}" -d '' && echo

echo
echo "VERIFIED. Video proof points:"
echo "  - dashboard:      ${URL}"
echo "  - Cloud Run:      console.cloud.google.com/run  (service + invocations graph)"
echo "  - Firestore:      console.cloud.google.com/firestore  (dispatch_plans, dispatch_runs)"
echo "  - Cloud Logging:  the agent's step trace"
echo "  - Scheduler:      console.cloud.google.com/cloudscheduler  (daily-dispatch job)"
