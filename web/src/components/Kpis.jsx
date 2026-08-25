import React from 'react'

export default function Kpis({ plan }) {
  const s = plan?.summary || {}
  const done = plan ? plan.assignments.filter((a) => a.change === 'completed').length : 0
  const tiles = [
    {
      lbl: 'Planning time', color: 'var(--accent)',
      val: plan ? <>{s.planning_seconds}<small>s</small></> : '—',
      sub: plan ? `manual baseline ${s.manual_baseline_min} min` : 'run the agent',
    },
    {
      lbl: 'Loads planned', color: 'var(--cyan)',
      val: plan ? s.planned : '—',
      sub: done ? `${done} already loaded` : plan ? 'across 2 dock teams' : 'awaiting first run',
    },
    {
      lbl: 'SLA compliance', color: s.sla_met_pct >= 100 ? 'var(--ok)' : s.sla_met_pct >= 90 ? 'var(--warn)' : 'var(--crit)',
      val: plan ? <>{s.sla_met_pct}<small>%</small></> : '—',
      sub: s.rebooked ? `${s.rebooked} rebooked to next sailing` : 'no commitments missed',
    },
    {
      lbl: 'Peak dock utilization', color: 'var(--p3)',
      val: plan ? <>{s.peak_util_pct}<small>%</small></> : '—',
      sub: plan ? `avg ${s.util_pct}% over plan window` : '',
    },
    {
      lbl: 'On hold', color: 'var(--hold)',
      val: plan ? s.holds : '—',
      sub: plan ? 'customs / rebooking' : '',
    },
  ]
  return (
    <div className="kpis">
      {tiles.map((t) => (
        <div className="kpi" key={t.lbl} style={{ '--kpi-color': t.color }}>
          <div className="lbl">{t.lbl}</div>
          <div className="val">{t.val}</div>
          <div className="sub">{t.sub || ' '}</div>
        </div>
      ))}
    </div>
  )
}
