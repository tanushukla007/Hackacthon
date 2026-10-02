import React from 'react'

/** A crash in one panel must not take the workstation down mid-investigation. */
export default class ErrorBoundary extends React.Component {
  constructor(p) { super(p); this.state = { err: null } }
  static getDerivedStateFromError(err) { return { err } }
  componentDidCatch(err, info) { console.error('[abhedya] panel crashed', err, info) }
  render() {
    if (!this.state.err) return this.props.children
    return (
      <div className="state">
        <div className="big">This panel failed to render.</div>
        <div className="code">{String(this.state.err.message || this.state.err)}</div>
        <div className="dim" style={{ marginTop: 6 }}>
          The rest of the console is unaffected. No investigative data was altered.
        </div>
        <div style={{ marginTop: 11 }}>
          <button className="btn" onClick={() => this.setState({ err: null })}>Reset panel</button>
        </div>
      </div>
    )
  }
}
