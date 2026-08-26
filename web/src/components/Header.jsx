import React, { useEffect, useRef, useState } from 'react'
import { hhmm } from '../api'

export default function Header({ meta, run, plan, scenarios, busy, running, offline,
                                 hasPlan, onRun, onEvent, onReset }) {
  const [open, setOpen] = useState(false)
  const ddRef = useRef(null)

  useEffect(() => {
    const close = (e) => { if (ddRef.current && !ddRef.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const plannerShort = run?.planner
    ? (run.planner.toLowerCase().includes('gemini') || run.planner.toLowerCase().includes('adk')
        ? 'GEMINI · ADK' : 'FALLBACK')
    : null

  return (
    <header className="hdr">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">⚓</div>
        <div>
          <h1>{meta.port_name || 'Port Terminal'}</h1>
          <div className="sub">AI Dispatch Control Tower</div>
        </div>
      </div>
      <div className="hdr-chips">
        <span className="chip">
          <span className={`dot ${offline ? 'off' : running ? 'busy' : 'live'}`} />
          {offline ? 'RECONNECTING' : running ? 'AGENT RUNNING' : 'SYSTEM LIVE'}
        </span>
        <span className="chip">PORT CLOCK <b>{hhmm(meta?.now)}</b></span>
        <span className="chip">PLAN <b>{plan ? `v${plan.version}` : '—'}</b></span>
        {plannerShort && <span className="chip">PLANNER <b>{plannerShort}</b></span>}
      </div>
      <div className="hdr-actions">
        {/* Reset stays available even mid-run: it is the escape hatch */}
        <button className="btn ghost" onClick={onReset} disabled={busy} title="Reseed the demo dataset">
          Reset
        </button>
        <div className="dd" ref={ddRef}>
          <button className="btn danger" disabled={busy || running || !hasPlan}
                  title={hasPlan ? 'Simulate an operational disruption' : 'Run the agent first'}
                  onClick={() => setOpen(!open)}>
            <span className="ico">⚠</span> Inject disruption
          </button>
          {open && (
            <div className="dd-menu">
              {scenarios.map((s) => (
                <button key={s.key} className="dd-item"
                        onClick={() => { setOpen(false); onEvent(s.key) }}>
                  <b>{s.label}</b>
                  <span>{s.detail}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button className={`btn primary ${!hasPlan && !running && !busy ? 'attention' : ''}`}
                onClick={onRun} disabled={busy || running}>
          <span className="ico">▶</span> {running ? 'Agent running…' : 'Run agent'}
        </button>
      </div>
    </header>
  )
}
