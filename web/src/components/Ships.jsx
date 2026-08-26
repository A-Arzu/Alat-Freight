import React from 'react'
import { hhmm, untilLabel } from '../api'

export default function Ships({ ships, plan, meta }) {
  const counts = {}
  const rebooks = {}
  if (plan) {
    for (const a of plan.assignments) counts[a.target_ship] = (counts[a.target_ship] || 0) + 1
    for (const h of plan.holds || []) if (h.rebook_ship) rebooks[h.rebook_ship] = (rebooks[h.rebook_ship] || 0) + 1
  }
  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>Vessel schedule</h2>
        <div className="spacer" />
        <span className="section-note">loading cutoffs vs port clock</span>
      </div>
      <div className="panel-bd">
        <div className="ship-list">
          {[...ships]
            .filter((v) => v && v.loading_cutoff)
            .sort((a, b) => a.loading_cutoff.localeCompare(b.loading_cutoff)).map((v) => {
            const now = meta?.now || ''
            const sameDay = !!now && v.loading_cutoff.slice(0, 10) === now.slice(0, 10)
            const label = untilLabel(v.loading_cutoff, now)
            return (
              <div className="scard" key={v.id}>
                <div>
                  <div className="nm">{v.id} <span>{v.name}</span></div>
                  <div className="dest">→ {v.destination} · departs {v.departs_at.slice(5, 10)} {hhmm(v.departs_at)}</div>
                </div>
                <div className={`cut ${sameDay ? 'hot' : ''}`}>
                  cutoff {sameDay ? '' : v.loading_cutoff.slice(5, 10) + ' '}{hhmm(v.loading_cutoff)}
                  <b>{label}</b>
                </div>
                <div className="loads">
                  {counts[v.id] || 0} load{(counts[v.id] || 0) === 1 ? '' : 's'} assigned
                  {rebooks[v.id] ? ` · +${rebooks[v.id]} rebooked inbound` : ''}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
