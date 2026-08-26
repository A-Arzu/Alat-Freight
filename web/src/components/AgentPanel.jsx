import React, { useEffect, useRef, useState } from 'react'

const ICONS = { tool: '⚙', reason: '✳', validate: '✓', publish: '↗', event: '⚠', error: '✕' }

// The pipeline a judge should be able to narrate while watching it run.
const STAGES = [
  { key: 'triage', label: 'Triage', match: /breakdown|cutoff|outage|impact_analysis/i, eventOnly: true },
  { key: 'ingest', label: 'Ingest', match: /snapshot/i },
  { key: 'filter', label: 'Filter', match: /pairings|customs/i },
  { key: 'reason', label: 'Reason', match: /planner|gemini|priority ordering|recovery/i },
  { key: 'schedule', label: 'Schedule', match: /propose_schedule/i },
  { key: 'validate', label: 'Validate', match: /re-check|submit_plan/i },
  { key: 'publish', label: 'Publish', match: /published|notified/i },
]

function stageIndex(steps, isEvent) {
  const stages = STAGES.filter((s) => !s.eventOnly || isEvent)
  let reached = -1
  for (const step of steps) {
    const text = `${step.label} ${step.detail || ''}`
    stages.forEach((s, i) => { if (s.match.test(text) && i > reached) reached = i })
  }
  return { stages, reached }
}

export default function AgentPanel({ run }) {
  const boxRef = useRef(null)
  const [tick, setTick] = useState(0)
  const running = run?.status === 'running'
  const steps = run?.steps || []
  const isEvent = run?.trigger === 'event'

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight
  }, [steps.length, running])

  // smooth the timer between 700ms polls so it never looks frozen on camera
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => setTick((n) => n + 1), 500)
    return () => clearInterval(t)
  }, [running])

  const { stages, reached } = stageIndex(steps, isEvent)
  const base = run?.elapsed_s ?? 0
  const elapsed = running ? (base + tick * 0.5).toFixed(0) : base.toFixed(1)
  const last = steps[steps.length - 1]
  const waitingOnModel = running && last && /planner|gemini|reasoning/i.test(last.label)

  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>Agent activity</h2>
        {run && (
          <span className="badge" style={{ textTransform: 'none' }}>
            {isEvent ? `disruption${run.scenario ? ` · ${run.scenario}` : ''}` : run.trigger}
          </span>
        )}
        <div className="spacer" />
        {run && (
          <span className="run-timer" title="wall-clock time for this run">
            {running && <span className="spin sm" />}
            {elapsed}s
          </span>
        )}
      </div>

      {run && (
        <div className="stager">
          {stages.map((s, i) => (
            <div key={s.key}
                 className={`stage ${i < reached ? 'done' : ''} ${i === reached ? (running ? 'active' : 'done') : ''}`}>
              <span className="pip">{i < reached || (!running && i === reached) ? '✓' : i + 1}</span>
              {s.label}
            </div>
          ))}
        </div>
      )}

      <div className="panel-bd">
        <div className="trace" ref={boxRef}>
          {!run && (
            <div className="trace-empty">
              The agent’s reasoning and tool calls stream here.<br />
              Press <b>Run agent</b> to watch it plan the port’s day.
            </div>
          )}
          {steps.map((s, i) => (
            <div key={i} className={`step ${s.kind}`} style={{ animationDelay: `${Math.min(i * 40, 300)}ms` }}>
              <div className="ic" aria-hidden="true">{ICONS[s.kind] || '·'}</div>
              <div>
                <div className="lbl">{s.label} <span className="ts">+{s.t}s</span></div>
                {s.detail && (
                  <div className={`dtl ${s.label === 'Gemini reasoning' ? 'quote' : ''}`}>{s.detail}</div>
                )}
              </div>
            </div>
          ))}
          {running && (
            <div className="running-row">
              <span className="spin" />
              {waitingOnModel
                ? `Gemini is weighing trade-offs — scarcity, SLA tiers and ship cutoffs (${elapsed}s)`
                : `agent working… (${elapsed}s)`}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
