import React, { useEffect, useRef, useState, useCallback } from 'react'
import { getState, runOptimize, injectEvent, decidePlan, reseed } from './api'
import ErrorBoundary from './components/ErrorBoundary.jsx'
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
import Outcomes from './components/Outcomes.jsx'

export default function App() {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState(null)
  const [offline, setOffline] = useState(false)
  const timer = useRef(null)

  const refresh = useCallback(async () => {
    try {
      setState(await getState())
      setOffline(false)
    } catch {
      setOffline(true)          // keep showing the last good state
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const run = state?.runs?.[0]
  const running = run?.status === 'running'

  useEffect(() => {
    clearInterval(timer.current)
    timer.current = setInterval(refresh, running ? 700 : 2000)
    return () => clearInterval(timer.current)
  }, [running, refresh])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 6000)
    return () => clearTimeout(t)
  }, [toast])

  const act = async (fn) => {
    setBusy(true)
    try {
      const res = await fn()
      if (res && res.ok === false) setToast({ kind: 'err', text: res.error })
      else if (res && res.already_running) setToast({ kind: 'warn', text: 'A run is already in progress — watch the Agent activity panel.' })
      await refresh()
      return res
    } finally {
      setBusy(false)
    }
  }

  if (!state) {
    return (
      <div className="shell">
        <div className="trace-empty">
          {offline ? 'Cannot reach the dispatch service — retrying…' : 'Connecting to dispatch service…'}
        </div>
      </div>
    )
  }

  const plan = state.plans[0] || null
  const key = `${run?.id || 'none'}:${run?.steps?.length || 0}:${plan?.id || 'none'}`

  return (
    <div className="shell">
      <ErrorBoundary name="Control bar" resetKey={key}>
        <Header
          meta={state.meta} run={run} plan={plan} scenarios={state.scenarios}
          busy={busy} running={running} offline={offline} hasPlan={!!plan}
          onRun={() => act(runOptimize)}
          onEvent={(k) => act(() => injectEvent(k))}
          onReset={() => act(reseed)}
        />
      </ErrorBoundary>

      {toast && <div className={`toast ${toast.kind}`}>{toast.text}</div>}
      {run?.status === 'failed' && (
        <div className="toast err static">
          The last agent run failed — see Agent activity for the reason. Press Run agent to retry.
        </div>
      )}
      {run?.status === 'stalled' && (
        <div className="toast warn static">
          The last run stopped responding and was released. Press Run agent to start a fresh one.
        </div>
      )}

      <ErrorBoundary name="Key metrics" resetKey={key}><Kpis plan={plan} /></ErrorBoundary>

      <div className="grid main">
        <div className="stack">
          <ErrorBoundary name="Dispatch plan" resetKey={key}>
            <PlanBoard plan={plan} shipments={state.shipments}
                       onDecide={(id, action, note) => act(() => decidePlan(id, action, note))} />
          </ErrorBoundary>
          {plan?.diff?.length > 0 && (
            <ErrorBoundary name="What changed" resetKey={key}>
              <DiffPanel diff={plan.diff} version={plan.version} />
            </ErrorBoundary>
          )}
        </div>
        <div className="stack">
          <ErrorBoundary name="Agent activity" resetKey={key}><AgentPanel run={run} /></ErrorBoundary>
          <ErrorBoundary name="Disruption feed" resetKey={key}><Events events={state.events} /></ErrorBoundary>
          <ErrorBoundary name="Decision log" resetKey={key}>
            <Outcomes plans={state.plans} outcomes={state.outcomes} runs={state.runs} />
          </ErrorBoundary>
        </div>
      </div>

      <div className="stack mt">
        <ErrorBoundary name="Dock schedule" resetKey={key}>
          <Gantt plan={plan} teams={state.teams} meta={state.meta} />
        </ErrorBoundary>
        <ErrorBoundary name="Cargo routing" resetKey={key}>
          <FlowMap plan={plan} shipments={state.shipments} wagons={state.wagons} ships={state.ships} />
        </ErrorBoundary>
        <div className="grid tri">
          <ErrorBoundary name="Wagon fleet" resetKey={key}>
            <Fleet wagons={state.wagons} plan={plan} meta={state.meta} />
          </ErrorBoundary>
          <ErrorBoundary name="Vessel schedule" resetKey={key}>
            <Ships ships={state.ships} plan={plan} meta={state.meta} />
          </ErrorBoundary>
          <ErrorBoundary name="Dispatcher delivery" resetKey={key}>
            <EmailPanel email={state.emails[0]} settings={state.email_settings}
                        planId={plan?.id} onRefresh={refresh} />
          </ErrorBoundary>
        </div>
      </div>

      <div className="footer">
        Port Operations Dispatch Agent · <b>Gemini + Google ADK + Cloud Run + Firestore</b> · All Things Agentic Hackathon
      </div>
    </div>
  )
}
