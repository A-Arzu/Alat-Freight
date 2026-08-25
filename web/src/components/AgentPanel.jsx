import React, { useEffect, useRef } from 'react'

const ICONS = { tool: '⚙', reason: '✳', validate: '✓', publish: '↗', event: '⚠', error: '✕' }

export default function AgentPanel({ run }) {
  const boxRef = useRef(null)
  const running = run?.status === 'running'
  const steps = run?.steps || []

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight
  }, [steps.length, running])

  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>Agent activity</h2>
        {run && (
          <span className="badge" style={{ textTransform: 'none' }}>
            {run.trigger === 'event' ? `disruption${run.scenario ? ` · ${run.scenario}` : ''}` : run.trigger}
          </span>
        )}
        <div className="spacer" />
        {run?.planner && <span className="section-note">{run.planner}</span>}
      </div>
      <div className="panel-bd">
        <div className="trace" ref={boxRef}>
          {!run && <div className="trace-empty">The agent’s reasoning and tool calls stream here during a run.</div>}
          {steps.map((s, i) => (
            <div key={i} className={`step ${s.kind}`} style={{ animationDelay: `${Math.min(i * 40, 300)}ms` }}>
              <div className="ic" aria-hidden="true">{ICONS[s.kind] || '·'}</div>
              <div>
                <div className="lbl">{s.label} <span className="ts">+{s.t}s</span></div>
                {s.detail && <div className="dtl">{s.detail}</div>}
              </div>
            </div>
          ))}
          {running && (
            <div className="running-row"><span className="spin" /> agent thinking…</div>
          )}
        </div>
      </div>
    </section>
  )
}
