const TOKEN = import.meta.env.VITE_RUN_TOKEN || 'demo-token'

export async function getState() {
  const r = await fetch('/api/state')
  if (!r.ok) throw new Error('state fetch failed')
  return r.json()
}

export async function runOptimize() {
  const r = await fetch('/optimize', { method: 'POST', headers: { 'X-Run-Token': TOKEN } })
  return r.json()
}

export async function injectEvent(scenario) {
  const r = await fetch('/events', {
    method: 'POST',
    headers: { 'X-Run-Token': TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario }),
  })
  return r.json()
}

export async function decidePlan(planId, action) {
  const r = await fetch(`/api/plans/${planId}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  return r.json()
}

export async function reseed() {
  const r = await fetch('/api/seed', { method: 'POST', headers: { 'X-Run-Token': TOKEN } })
  return r.json()
}

// ---- time helpers (naive ISO "YYYY-MM-DDTHH:MM") ----
export const hhmm = (s) => (s ? s.slice(11, 16) : '--:--')
export const dayMin = (s) => {
  if (!s) return 0
  return parseInt(s.slice(11, 13), 10) * 60 + parseInt(s.slice(14, 16), 10)
}
export function untilLabel(target, now) {
  if (!target || !now) return ''
  const sameDay = target.slice(0, 10) === now.slice(0, 10)
  const dayDiff = Math.round(
    (new Date(target.slice(0, 10)) - new Date(now.slice(0, 10))) / 86400000
  )
  let mins = dayMin(target) - dayMin(now) + dayDiff * 1440
  if (mins < 0) return 'passed'
  const h = Math.floor(mins / 60), m = mins % 60
  if (!sameDay && h >= 24) return `in ${Math.floor(h / 24)}d ${h % 24}h`
  return h > 0 ? `in ${h}h ${String(m).padStart(2, '0')}m` : `in ${m}m`
}
