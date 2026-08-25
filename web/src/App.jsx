import React, { useEffect, useRef, useState, useCallback } from 'react'
import { getState, runOptimize, injectEvent, decidePlan, reseed } from './api'
import Header from './components/Header.jsx'
import Kpis from './components/Kpis.jsx'
import PlanBoard from './components/PlanBoard.jsx'
import AgentPanel from './components/AgentPanel.jsx'
import DiffPanel from './components/DiffPanel.jsx'
import Gantt from './components/Gantt.jsx'
import FlowMap from './components/FlowMap.jsx'
import Fleet from './components/Fleet.jsx'
import Ships from './components/Ships.jsx'
import Events from './components/Events.jsx'
import EmailPanel from './components/EmailPanel.jsx'

export default function App() {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const timer = useRef(null)

  const refresh = useCallback(async () => {
    try { setState(await getState()) } catch { /* server restarting; keep last state */ }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const running = state?.runs?.[0]?.status === 'running'
  useEffect(() => {
    clearInterval(timer.current)
    timer.current = setInterval(refresh, running ? 700 : 2000)
    return () => clearInterval(timer.current)
  }, [running, refresh])

  const act = async (fn) => { setBusy(true); try { await fn(); await refresh() } finally { setBusy(false) } }

  if (!state) {
    return <div className="shell"><div className="trace-empty">Connecting to dispatch service…</div></div>
  }

  const plan = state.plans[0] || null
  const run = state.runs[0] || null

  return (
    <div className="shell">
      <Header
        meta={state.meta} run={run} plan={plan} scenarios={state.scenarios}
        busy={busy || running} hasPlan={!!plan}
        onRun={() => act(runOptimize)}
        onEvent={(key) => act(() => injectEvent(key))}
        onReset={() => act(reseed)}
      />
      <Kpis plan={plan} />
      <div className="grid main">
        <div className="stack">
          <PlanBoard plan={plan} shipments={state.shipments}
                     onDecide={(id, action) => act(() => decidePlan(id, action))} />
          {plan?.diff?.length > 0 && <DiffPanel diff={plan.diff} version={plan.version} />}
        </div>
        <div className="stack">
          <AgentPanel run={run} />
          <Events events={state.events} />
        </div>
      </div>
      <div className="stack mt">
        <Gantt plan={plan} teams={state.teams} meta={state.meta} />
        <FlowMap plan={plan} shipments={state.shipments} wagons={state.wagons} ships={state.ships} />
        <div className="grid tri">
          <Fleet wagons={state.wagons} plan={plan} meta={state.meta} />
          <Ships ships={state.ships} plan={plan} meta={state.meta} />
          <EmailPanel email={state.emails[0]} />
        </div>
      </div>
      <div className="footer">
        Port Operations Dispatch Agent · <b>Gemini + Google ADK + Cloud Run + Firestore</b> · All Things Agentic Hackathon
      </div>
    </div>
  )
}
