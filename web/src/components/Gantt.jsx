import React from 'react'
import { dayMin, hhmm } from '../api'

const DAY_START = 6 * 60
const DAY_END = 20 * 60
const SPAN = DAY_END - DAY_START

const pct = (mins) => Math.max(0, Math.min(100, ((mins - DAY_START) / SPAN) * 100))
const winEnd = (window) => {
  const [, e] = window.split('-')
  const [h, m] = e.split(':').map(Number)
  return h * 60 + m
}

export default function Gantt({ plan, teams, meta }) {
  const nowMin = dayMin(meta.now)
  const nowVisible = nowMin > DAY_START && nowMin < DAY_END

  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>Dock schedule — load windows</h2>
        <div className="spacer" />
        <span className="section-note">port day 06:00 – 20:00</span>
      </div>
      <div className="gantt">
        <div className="g-axis">
          {Array.from({ length: 15 }, (_, i) => 6 + i).map((h) => (
            <span key={h} className="tick" style={{ left: `${pct(h * 60)}%` }}>
              {String(h).padStart(2, '0')}:00
            </span>
          ))}
        </div>
        {teams.map((t) => {
          const blocks = plan
            ? plan.assignments.filter((a) => a.team_id === t.id)
            : []
          const ghosts = plan
            ? (plan.diff || []).filter(
                (d) => d.before && d.before.team_id === t.id &&
                       ['moved', 'retimed', 'rebooked'].includes(d.kind))
            : []
          return (
            <div className="g-lane" key={t.id}>
              <div className="name">{t.name || t.id}<br />
                <span style={{ color: 'var(--faint)', fontSize: 10 }}>
                  {hhmm(t.shift_start)}–{hhmm(t.shift_end)}
                </span>
              </div>
              <div className="g-track">
                {ghosts.map((d, i) => {
                  const s = dayMin(d.before.load_start)
                  const e = winEnd(d.before.window)
                  return (
                    <div key={`g${i}`} className="g-ghost"
                         style={{ left: `${pct(s)}%`, width: `${pct(e) - pct(s)}%` }}
                         title={`${d.shipment_id} originally ${d.before.window} on ${d.before.wagon_id}`}>
                      {d.shipment_id}
                    </div>
                  )
                })}
                {blocks.map((a) => {
                  const s = dayMin(a.load_start)
                  const e = dayMin(a.load_end)
                  const cls = [
                    'g-block', `p${a.priority}`,
                    a.change === 'completed' ? 'done' : '',
                    ['moved', 'retimed', 'scheduled'].includes(a.change) ? 'moved-in' : '',
                  ].join(' ')
                  return (
                    <div key={a.shipment_id} className={cls}
                         style={{ left: `${pct(s)}%`, width: `${Math.max(pct(e) - pct(s), 2.4)}%` }}
                         title={`${a.shipment_id} · ${a.wagon_id} → ${a.target_ship} · ${hhmm(a.load_start)}–${hhmm(a.load_end)} · ${a.reason}`}>
                      {a.change === 'completed' ? '✓ ' : ''}{a.shipment_id}
                    </div>
                  )
                })}
                {nowVisible && (
                  <div className="g-now" data-t={hhmm(meta.now)} style={{ left: `${pct(nowMin)}%` }} />
                )}
              </div>
            </div>
          )
        })}
        <div className="g-legend">
          <span><i style={{ background: 'var(--p1)' }} /> P1 urgent</span>
          <span><i style={{ background: 'var(--p2)' }} /> P2 asap</span>
          <span><i style={{ background: 'var(--p3)' }} /> P3 today</span>
          <span><i style={{ border: '1.5px dashed var(--crit)', background: 'transparent' }} /> pre-disruption slot</span>
          <span><i style={{ background: 'var(--accent)', width: 3 }} /> port clock</span>
        </div>
      </div>
    </section>
  )
}
