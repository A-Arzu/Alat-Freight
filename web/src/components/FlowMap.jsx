import React from 'react'
import { hhmm } from '../api'

const W = 990
const COLS = { ship: 155, wagon: 495, vessel: 835 }
const NODE_W = 124
const NODE_H = 26
const ROW_H = 33
const Y0 = 46

function link(x1, y1, x2, y2) {
  const dx = 100
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
}

export default function FlowMap({ plan, shipments, wagons, ships }) {
  const sList = [...shipments].sort((a, b) => a.id.localeCompare(b.id))
  const wList = [...wagons].sort((a, b) => a.id.localeCompare(b.id))
  const vList = [...ships].sort((a, b) => a.id.localeCompare(b.id))

  const yOf = (list) => Object.fromEntries(list.map((x, i) => [x.id, Y0 + i * ROW_H]))
  const yS = yOf(sList)
  const yW = yOf(wList)
  const yV = yOf(vList)
  const yHold = Y0 + vList.length * ROW_H + 6
  const H = Math.max(sList.length, wList.length, vList.length + 1) * ROW_H + Y0 + 26

  const byId = (list) => Object.fromEntries(list.map((x) => [x.id, x]))
  const shipById = byId(sList)

  const links = []
  const hotWagons = new Set()
  if (plan) {
    for (const a of plan.assignments) {
      const fresh = ['moved', 'retimed', 'scheduled'].includes(a.change)
      if (fresh) hotWagons.add(a.wagon_id)
      const cls = `flink p${a.priority}${a.change === 'completed' ? ' done' : ''}${fresh ? ' fresh' : ''}`
      links.push({ d: link(COLS.ship + NODE_W / 2, yS[a.shipment_id], COLS.wagon - NODE_W / 2, yW[a.wagon_id]), cls, key: `sw-${a.shipment_id}` })
      links.push({ d: link(COLS.wagon + NODE_W / 2, yW[a.wagon_id], COLS.vessel - NODE_W / 2, yV[a.target_ship]), cls, key: `wv-${a.shipment_id}` })
    }
    for (const h of plan.holds || []) {
      if (h.rebook_ship && yV[h.rebook_ship] != null) {
        links.push({
          d: link(COLS.ship + NODE_W / 2, yS[h.shipment_id], COLS.vessel - NODE_W / 2, yV[h.rebook_ship]),
          cls: 'flink hold', key: `rb-${h.shipment_id}`,
        })
      } else if (yS[h.shipment_id] != null) {
        links.push({
          d: link(COLS.ship + NODE_W / 2, yS[h.shipment_id], COLS.vessel - NODE_W / 2, yHold),
          cls: 'flink hold', key: `hd-${h.shipment_id}`,
        })
      }
    }
    for (const d of plan.diff || []) {
      if (d.before && ['moved', 'rebooked'].includes(d.kind) && yW[d.before.wagon_id] != null) {
        links.push({
          d: link(COLS.ship + NODE_W / 2, yS[d.shipment_id], COLS.wagon - NODE_W / 2, yW[d.before.wagon_id]),
          cls: 'flink ghost', key: `gh-${d.shipment_id}`,
        })
      }
    }
  }

  const node = (x, y, id, sub, extraCls = '', outside = null) => (
    <g key={`${x}-${id}`}>
      <rect className={`fnode ${extraCls}`} x={x - NODE_W / 2} y={y - NODE_H / 2}
            width={NODE_W} height={NODE_H} rx="6" />
      <text className={`ftxt ${extraCls === 'dead' ? 'dead' : ''}`} x={x - NODE_W / 2 + 9}
            y={y + 4}>{id}</text>
      {sub && (
        <text className="ftxt sub" x={x + NODE_W / 2 - 9} y={y + 4}
              textAnchor="end">{sub}</text>
      )}
      {outside && (
        <text className="ftxt sub" x={x + NODE_W / 2 + 8} y={y + 4}>{outside}</text>
      )}
    </g>
  )

  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>Cargo routing — shipment → wagon → vessel</h2>
        <div className="spacer" />
        <span className="section-note">
          {plan ? `plan v${plan.version}` : 'waiting for first plan'} · animated = changed by the agent
        </span>
      </div>
      <div className="flow-wrap">
        <svg className="flow-svg" viewBox={`0 0 ${W} ${H}`} role="img"
             aria-label="Routing map from shipments through wagons to vessels">
          <text className="fcol" x={COLS.ship - NODE_W / 2} y="22">SHIPMENTS</text>
          <text className="fcol" x={COLS.wagon - NODE_W / 2} y="22">WAGONS</text>
          <text className="fcol" x={COLS.vessel - NODE_W / 2} y="22">VESSELS</text>

          {links.map((l) => <path key={l.key} className={l.cls} d={l.d} />)}

          {sList.map((s) => node(COLS.ship, yS[s.id], s.id, s.cargo_type))}
          {wList.map((w) => node(COLS.wagon, yW[w.id], w.id,
            w.status === 'out_of_service' ? 'OUT' : w.type,
            w.status === 'out_of_service' ? 'dead' : hotWagons.has(w.id) ? 'hot' : ''))}
          {vList.map((v) => node(COLS.vessel, yV[v.id], v.id, hhmm(v.loading_cutoff),
            '', v.destination))}
          {plan && plan.holds?.some((h) => !h.rebook_ship) &&
            node(COLS.vessel, yHold, 'YARD HOLD', '', 'dead', 'awaiting release')}
        </svg>
      </div>
    </section>
  )
}
