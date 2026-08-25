import React from 'react'

export default function DiffPanel({ diff, version }) {
  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>What changed — v{version - 1} → v{version}</h2>
        <div className="spacer" />
        <span className="section-note">{diff.filter((d) => d.kind !== 'completed').length} changes</span>
      </div>
      <div className="panel-bd">
        <div className="diff-list">
          {diff.map((d, i) => (
            <div key={i} className={`dline ${d.kind}`}>
              <span className="k">{d.kind}</span>
              <span className="s">{d.shipment_id}</span>
              <span className="w">
                {d.before && <><b>{d.before.wagon_id}</b> {d.before.window}</>}
                {d.before && d.after && d.kind !== 'completed' && ' → '}
                {d.after && d.kind !== 'completed' && <><b>{d.after.wagon_id}</b> {d.after.window}</>}
                {!d.after && d.kind !== 'completed' && d.note && <> — {d.note}</>}
                {d.kind === 'completed' && ' loaded before the disruption'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
