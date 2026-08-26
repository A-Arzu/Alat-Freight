import React from 'react'

/** Plan lineage + the dispatcher's decisions. This is the audit trail behind
 *  the "tracks outcomes" claim: every version, who planned it, what the human
 *  did with it. */
export default function Outcomes({ plans, outcomes, runs }) {
  const history = [...(plans || [])].sort((a, b) => b.version - a.version)
  const decisions = [...(outcomes || [])].sort((a, b) => (b.at || '').localeCompare(a.at || ''))
  const done = (runs || []).filter((r) => r.status === 'done')

  const confidences = history.flatMap((p) => (p.assignments || []).map((a) => a.confidence))
  const avgConf = confidences.length
    ? Math.round(confidences.reduce((s, c) => s + c, 0) / confidences.length) : null
  const times = done.map((r) => r.elapsed_s).filter((n) => typeof n === 'number' && n > 0)
  const avgTime = times.length ? (times.reduce((s, t) => s + t, 0) / times.length).toFixed(1) : null
  const approved = decisions.filter((d) => d.action === 'approved').length
  const overridden = decisions.filter((d) => d.action === 'overridden').length
  const baseline = (history[0]?.summary?.manual_baseline_min ?? 45) * 60
  const saved = avgTime ? Math.round(baseline / Number(avgTime)) : null

  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>Decision log</h2>
        <div className="spacer" />
        <span className="section-note">
          {history.length ? `${history.length} plan version${history.length === 1 ? '' : 's'} today` : 'no runs yet'}
        </span>
      </div>
      <div className="panel-bd">
        {!history.length && (
          <div className="section-note">
            Every plan version and every approve/override lands here — the record the agent learns from.
          </div>
        )}

        {history.length > 0 && (
          <>
            <div className="score-row">
              <div className="score"><b>{avgConf ?? '—'}%</b><span>avg confidence</span></div>
              <div className="score"><b>{avgTime ?? '—'}s</b><span>avg plan time</span></div>
              <div className="score"><b>{saved ? `${saved}×` : '—'}</b><span>vs manual</span></div>
              <div className="score"><b>{approved}/{approved + overridden || 0}</b><span>approved</span></div>
            </div>

            <div className="lineage">
              {history.map((p) => {
                const decided = decisions.find((d) => d.plan_id === p.id)
                const gemini = /gemini|adk/i.test(p.planner || '')
                return (
                  <div className="lin" key={p.id}>
                    <span className="v">v{p.version}</span>
                    <div className="linmid">
                      <div className="lintop">
                        <span className={`badge ${p.status}`}>{p.status}</span>
                        <span className="lintrig">
                          {p.trigger?.startsWith('event') ? `disruption · ${p.trigger.split(':')[1]}` : p.trigger}
                        </span>
                      </div>
                      <div className="linsub">
                        {p.summary?.planned ?? 0} loads · {p.summary?.holds ?? 0} holds ·
                        SLA {p.summary?.sla_met_pct ?? '—'}% · {p.summary?.planning_seconds ?? '—'}s
                        {decided && ` · ${decided.action} ${decided.at?.slice(11, 16) || ''}`}
                      </div>
                      {decided?.note && (
                        <div className="linnote" title="the agent reads this on its next run">
                          “{decided.note}”
                        </div>
                      )}
                    </div>
                    <span className={`planner-tag ${gemini ? 'ai' : ''}`}>
                      {gemini ? 'Gemini' : 'fallback'}
                    </span>
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>
    </section>
  )
}
