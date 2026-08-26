// The dashboard authenticates mutating calls with a UI token the server hands
// out in /api/state. That keeps the Cloud Scheduler token off the wire and,
// unlike a build-time constant, always matches whatever the service is running.
let uiToken = import.meta.env.VITE_RUN_TOKEN || 'demo-token'

async function post(path, body) {
  try {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'X-Run-Token': uiToken, 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    })
    let data = null
    try { data = await r.json() } catch { /* empty or non-JSON body */ }
    if (!r.ok) {
      return { ok: false, error: (data && (data.detail || data.error)) || `request failed (${r.status})` }
    }
    return { ok: true, ...(data || {}) }
  } catch {
    return { ok: false, error: 'cannot reach the dispatch service' }
  }
}

export async function getState() {
  const r = await fetch('/api/state')
  if (!r.ok) throw new Error('state fetch failed')
  const state = await r.json()
  if (state.ui_token) uiToken = state.ui_token
  return state
}

export const runOptimize = () => post('/optimize')
export const injectEvent = (scenario) => post('/events', { scenario })
export const decidePlan = (planId, action, note) =>
  post(`/api/plans/${planId}/${action}`, note ? { note } : {})
export const reseed = () => post('/api/seed')
export const setRecipient = (recipient) => post('/api/settings/email', { recipient })
export const sendPlanEmail = (planId, recipient) =>
  post(`/api/plans/${planId}/email`, recipient ? { recipient } : {})

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
