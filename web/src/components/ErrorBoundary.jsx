import React from 'react'

/** Keeps one misbehaving panel from taking the whole control tower down
 *  mid-demo. Each panel is wrapped separately, so the rest stays live. */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('[panel error]', this.props.name, error, info)
  }

  componentDidUpdate(prev) {
    // a fresh data poll should give the panel another chance
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  render() {
    if (this.state.error) {
      return (
        <section className="panel">
          <div className="panel-hd">
            <h2>{this.props.name || 'Panel'}</h2>
            <span className="badge overridden">recovering</span>
          </div>
          <div className="panel-bd">
            <div className="section-note">
              This panel hit unexpected data and will redraw on the next update.
            </div>
          </div>
        </section>
      )
    }
    return this.props.children
  }
}
