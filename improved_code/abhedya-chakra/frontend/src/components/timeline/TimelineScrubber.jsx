import { useEffect, useRef, useState } from 'react'
import { ts } from '../../utils/format'

/** 15-day, minute-resolution playback over the traced transactions only. */
export default function TimelineScrubber({ timeline, cursor, onCursor }) {
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const raf = useRef()
  const buckets = timeline?.buckets || []
  const max = Math.max(1, ...buckets.map((b) => b.count))

  useEffect(() => {
    if (!playing || !timeline) return
    let last = performance.now()
    const step = (now) => {
      const dt = (now - last) / 1000; last = now
      const span = timeline.to - timeline.from
      const next = (cursor || timeline.from) + dt * (span / 24) * speed
      if (next >= timeline.to) { onCursor(timeline.to); setPlaying(false); return }
      onCursor(next)
      raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [playing, speed, cursor, timeline, onCursor])

  if (!timeline || !buckets.length) return null
  const frac = cursor ? (cursor - timeline.from) / Math.max(1, timeline.to - timeline.from) : 1

  const seek = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    const f = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width))
    onCursor(timeline.from + f * (timeline.to - timeline.from))
  }

  return (
    <div className="timeline">
      <div className="tl-head">
        <button className="btn" onClick={() => setPlaying((p) => !p)}>
          {playing ? '❙❙ Pause' : '▶ Play'}
        </button>
        <button className="btn ghost" onClick={() => { setPlaying(false); onCursor(timeline.from) }}>Reset</button>
        <select className="inp" style={{ width: 70 }} value={speed} aria-label="Playback speed"
                onChange={(e) => setSpeed(Number(e.target.value))}>
          {[0.5, 1, 2, 4].map((s) => <option key={s} value={s}>{s}×</option>)}
        </select>
        <span className="tiny">bucket {timeline.bucket_seconds}s</span>
        <span className="mono dim" style={{ marginLeft: 'auto', fontSize: 11 }}>
          {cursor ? ts(Math.round(cursor)) : 'full window'}
        </span>
        <button className="btn ghost" onClick={() => onCursor(null)}>Show all</button>
      </div>
      <div className="tl-track" onClick={seek} role="slider" tabIndex={0}
           aria-label="Transaction timeline" aria-valuemin={timeline.from}
           aria-valuemax={timeline.to} aria-valuenow={Math.round(cursor || timeline.to)}>
        {buckets.map((b, i) => {
          const past = cursor ? b.ts <= cursor : true
          return <div key={i} className={`b ${past ? 'on' : 'past'}`}
                      style={{ height: `${(b.count / max) * 100}%` }}
                      title={`${ts(b.ts)} · ${b.count} transactions`} />
        })}
        {cursor && <div className="tl-cursor" style={{ left: `${frac * 100}%` }} />}
      </div>
      <div className="tl-axis"><span>{ts(timeline.from)}</span><span>{ts(timeline.to)}</span></div>
    </div>
  )
}
