import React, { useState } from 'react'

export default function EmailPanel({ email }) {
  const [open, setOpen] = useState(true)
  return (
    <section className="panel">
      <div className="panel-hd">
        <h2>Dispatcher delivery</h2>
        {email && (
          <span className={`badge ${email.delivered ? 'approved' : 'pending'}`}>
            {email.delivered ? 'email sent' : 'rendered'}
          </span>
        )}
        <div className="spacer" />
        {email && (
          <button className="btn ghost" style={{ padding: '4px 10px', fontSize: 11.5 }}
                  onClick={() => setOpen(!open)}>{open ? 'Collapse' : 'Expand'}</button>
        )}
      </div>
      <div className="panel-bd">
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
