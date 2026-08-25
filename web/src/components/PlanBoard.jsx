import React from 'react'
import { hhmm } from '../api'

export default function PlanBoard({ plan, shipments, onDecide }) {
  const cargoOf = Object.fromEntries(shipments.map((s) => [s.id, s.cargo_type]))

  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>Dispatch plan</h2>
        {plan && <span className="badge v">v{plan.version}</span>}
        {plan && <span className={`badge ${plan.status}`}>{plan.status}</span>}
        <div className="spacer" />
        {plan && plan.status === 'pending' && (
          <>
            <button className="btn" style={{ padding: '6px 12px', fontSize: 12 }}
                    onClick={() => onDecide(plan.id, 'override')}>Override</button>
            <button className="btn primary" style={{ padding: '6px 14px', fontSize: 12 }}
                    onClick={() => onDecide(plan.id, 'approve')}>✓ Approve plan</button>
          </>
        )}
      </div>
      <div className="panel-bd">
        {!plan && (
          <div className="trace-empty">
            No plan yet. Press <b>Run agent</b> to generate today’s dispatch plan.
          </div>
        )}
        {plan && (
          <div className="plan-list">
            {[...plan.assignments]
              .sort((a, b) => a.load_start.localeCompare(b.load_start))
              .map((a, i) => {
                const cargo = cargoOf[a.shipment_id] || 'standard'
                const confCls = a.confidence >= 88 ? '' : a.confidence >= 74 ? 'mid' : 'low'
                return (
                  <div key={a.shipment_id}
                       className={`acard p${a.priority} ${a.change === 'completed' ? 'dim' : ''}`}
                       style={{ animationDelay: `${i * 35}ms` }}>
                    <div className="stripe" />
                    <div className="when">
                      <div className="t">{hhmm(a.load_start)}</div>
                      <div className="d">{a.duration_min} min</div>
                    </div>
                    <div className="mid">
                      <div className="row1">
                        <span className="sid">{a.shipment_id}</span>
                        <span className={`cargo ${cargo}`}>{cargo}</span>
                        <span className="route">
                          <b>{a.wagon_id}</b><span className="arr">▸</span>{a.team_id}
                          <span className="arr">▸</span><b>{a.target_ship}</b>
                        </span>
                        <span className={`chg ${a.change}`}>
                          {a.change === 'completed' ? '✓ loaded' : a.change}
                        </span>
                      </div>
                      <div className="reason" title={a.reason}>{a.reason}</div>
                    </div>
                    <div className="right">
                      <div className="conf">
                        <div className="bar"><div className={`fill ${confCls}`} style={{ width: `${a.confidence}%` }} /></div>
                        <span className="pct">{a.confidence}%</span>
                      </div>
                    </div>
                  </div>
                )
              })}
            {plan.holds.map((h) => (
              <div key={h.shipment_id} className={`hold-card ${h.change === 'rebooked' ? 'rebooked' : ''}`}>
                <div className="ico">{h.change === 'rebooked' ? '↻' : '⏸'}</div>
                <div className="t">
                  <b>{h.shipment_id}</b> — {h.action}
                  <div className="why">
                    {h.reason}
                    {h.retry_at ? ` · wagon window ${hhmm(h.retry_at)}` : ''}
                    {` · confidence ${h.confidence}%`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
