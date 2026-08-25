import React from 'react'
import { hhmm, dayMin } from '../api'

export default function Fleet({ wagons, plan, meta }) {
  const nowMin = dayMin(meta.now)
  const nextLoad = {}
  const loadingNow = new Set()
  if (plan) {
    for (const a of [...plan.assignments].sort((x, y) => x.load_start.localeCompare(y.load_start))) {
      const s = dayMin(a.load_start), e = dayMin(a.load_end)
      if (s <= nowMin && nowMin < e) loadingNow.add(a.wagon_id)
      if (s >= nowMin && !nextLoad[a.wagon_id]) nextLoad[a.wagon_id] = a
    }
  }

  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>Wagon fleet</h2>
        <div className="spacer" />
        <span className="section-note">
          {wagons.filter((w) => w.status === 'available').length}/{wagons.length} available
        </span>
      </div>
      <div className="panel-bd">
        <div className="wagon-grid">
          {[...wagons].sort((a, b) => a.id.localeCompare(b.id)).map((w) => {
            const status = w.status === 'available' && loadingNow.has(w.id) ? 'in_use' : w.status
            const nl = nextLoad[w.id]
            return (
              <div className="wcard" key={w.id}>
                <div className="top">
                  <span className="wid">{w.id}</span>
                  <span className="wtype">{w.type}{w.certifications?.length ? ` · ${w.certifications.join(',')}` : ''}</span>
                  <span className={`pill ${status}`}>{status.replace(/_/g, ' ')}</span>
                </div>
                <div className="note">
                  {(w.capacity_kg / 1000).toFixed(0)}t cap
                  {w.reserved_for ? ` · reserved ${w.reserved_for}` : ''}
                  {w.available_at && w.status !== 'available' ? ` · back ${hhmm(w.available_at)}` : ''}
                  {nl ? ` · next ${nl.shipment_id} @ ${hhmm(nl.load_start)}` : ''}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
