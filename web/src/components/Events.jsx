import React from 'react'
import { hhmm } from '../api'

export default function Events({ events }) {
  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>Disruption feed</h2>
        <div className="spacer" />
        <span className="section-note">{events.length ? `${events.length} today` : 'steady state'}</span>
      </div>
      <div className="panel-bd">
        {events.length === 0 && (
          <div className="section-note">No disruptions. Inject one to watch the agent re-plan live.</div>
        )}
        <div className="event-list">
          {events.map((e) => (
            <div className="ecard" key={e.id}>
              <div style={{ fontSize: 16 }}>⚠</div>
              <div className="t">
                <b>{e.label}</b>
                {e.resolved_by_plan
                  ? <span className="res">resolved → {e.resolved_by_plan}</span>
                  : <span style={{ color: 'var(--warn)', fontSize: 11 }}>re-planning…</span>}
              </div>
              <div className="when">port {e.port_time ? hhmm(e.port_time) : e.received_at.slice(11, 16)}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
