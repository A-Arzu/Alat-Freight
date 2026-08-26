import React, { useEffect, useState } from 'react'
import { setRecipient, sendPlanEmail } from '../api'

export default function EmailPanel({ email, settings, planId, onRefresh }) {
  const saved = settings?.recipient || ''
  const smtpReady = !!settings?.smtp_configured
  const [value, setValue] = useState(saved)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState(null)   // {kind: ok|warn|err, text}
  const [open, setOpen] = useState(true)

  // adopt server-side changes unless the operator is mid-edit
  useEffect(() => { if (!dirty) setValue(saved) }, [saved, dirty])

  const run = async (fn) => {
    setBusy(true)
    try {
      const res = await fn()
      if (!res.ok) setStatus({ kind: 'err', text: res.error })
      return res
    } finally {
      setBusy(false)
      onRefresh && onRefresh()
    }
  }

  const save = async () => {
    const res = await run(() => setRecipient(value.trim()))
    if (res.ok) {
      setDirty(false)
      setStatus(res.recipient
        ? { kind: smtpReady ? 'ok' : 'warn', text: `Saved. Dispatch plans go to ${res.recipient}.` }
        : { kind: 'warn', text: 'Recipient cleared. Plans will render here only.' })
    }
  }

  const sendNow = async () => {
    const target = value.trim()
    if (target && target !== saved) {
      const s = await run(() => setRecipient(target))
      if (!s.ok) return
      setDirty(false)
    }
    const res = await run(() => sendPlanEmail(planId, target))
    if (!res.ok) return
    setStatus(res.delivered
      ? { kind: 'ok', text: `Sent to ${res.to}. First message can land in spam — mark it "not spam".` }
      : { kind: 'warn', text: `Not delivered: ${res.error}. The plan is rendered below.` })
  }

  const badge = !email ? null
    : email.delivered ? { cls: 'approved', text: 'email sent' }
    : email.error && email.error !== 'SMTP not configured' && email.error !== 'no recipient set'
      ? { cls: 'overridden', text: 'send failed' }
      : { cls: 'pending', text: 'rendered' }

  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>Dispatcher delivery</h2>
        {badge && <span className={`badge ${badge.cls}`}>{badge.text}</span>}
        <div className="spacer" />
        {email && (
          <button className="btn ghost" style={{ padding: '4px 10px', fontSize: 11.5 }}
                  onClick={() => setOpen(!open)}>{open ? 'Collapse' : 'Expand'}</button>
        )}
      </div>
      <div className="panel-bd">
        <div className="mail-to">
          <label htmlFor="mail-to-input">Send plans to</label>
          <div className="mail-row">
            <input id="mail-to-input" type="email" inputMode="email" autoComplete="email"
                   className="mail-input" placeholder="dispatcher@example.com"
                   value={value} disabled={busy}
                   onChange={(e) => { setValue(e.target.value); setDirty(true); setStatus(null) }}
                   onKeyDown={(e) => { if (e.key === 'Enter' && !busy) save() }} />
            <button className="btn" style={{ padding: '7px 12px', fontSize: 12 }}
                    onClick={save} disabled={busy || !dirty}>Save</button>
            <button className="btn primary" style={{ padding: '7px 12px', fontSize: 12 }}
                    onClick={sendNow} disabled={busy || !planId || !value.trim()}
                    title={planId ? 'Email the current plan now' : 'Run the agent first'}>
              {busy ? 'Working…' : 'Send now'}
            </button>
          </div>
          {status && <div className={`mail-status ${status.kind}`}>{status.text}</div>}
          {!status && !smtpReady && (
            <div className="mail-status warn">
              SMTP not configured — plans render here instead of sending.
              Enable Gmail delivery with <code>deploy/email_setup.sh</code>.
            </div>
          )}
          {!status && smtpReady && !saved && (
            <div className="mail-status warn">No recipient set yet — enter one to receive plans.</div>
          )}
        </div>

        {!email && <div className="section-note">The formatted plan email (+ XLSX) appears here after a run.</div>}
        {email && (
          <>
            <div className="email-meta">
              <div className="subj">{email.subject}</div>
              <div className="to">to: {email.to}</div>
            </div>
            {open && (
              <div className="email-frame" dangerouslySetInnerHTML={{ __html: email.html }} />
            )}
            {email.attachment && <div className="attach">📎 {email.attachment}</div>}
          </>
        )}
      </div>
    </section>
  )
}
