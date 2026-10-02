import { useEffect, useMemo, useRef, useState } from 'react'

/**
 * Layered trace graph, drawn as plain SVG.
 *
 * Deliberately dependency-free: the workstation UI uses Cytoscape with dagre,
 * this demo places nodes itself in hop columns. It renders what the backend
 * returned and nothing else - no layout opinion changes which accounts or
 * edges exist, and no position here means anything analytically.
 *
 * Encoding (never colour alone):
 *   column  = hop distance from the victim
 *   shape   = layer family (victim diamond, L* circle, H* square)
 *   colour  = risk band from the backend
 *   size    = MRI
 *   dashed  = hub account, not expanded further
 */

const BAND_VAR = {
  LOW: 'var(--low)',
  MEDIUM: 'var(--medium)',
  HIGH: 'var(--high)',
  CRITICAL: 'var(--critical)',
}
const BAND_ORDER = { LOW: 0, MEDIUM: 1, HIGH: 2, CRITICAL: 3 }

const ROW_H = 30
const PAD = 40

export default function TraceGraph({ trace, selected, onSelect, exportUrl, onOpenAccount }) {
  const [hideUnlayered, setHideUnlayered] = useState(trace.nodes.length > 60)
  const [showLabels, setShowLabels] = useState(null)   // null = automatic
  const [minBand, setMinBand] = useState('LOW')
  const [colWidth, setColWidth] = useState(190)
  const [full, setFull] = useState(false)
  const [view, setView] = useState(null)
  const [drag, setDrag] = useState(null)
  const [hovered, setHovered] = useState(null)        // account under the cursor
  const [hoveredEdge, setHoveredEdge] = useState(null)
  const svgRef = useRef(null)
  const wrapRef = useRef(null)

  // Escape leaves full screen
  useEffect(() => {
    if (!full) return undefined
    const onKey = (ev) => { if (ev.key === 'Escape') setFull(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [full])

  /* ---------------------------------------------------------- layout */
  const { nodes, edges, width, height, hiddenCount, bandFiltered } = useMemo(() => {
    const floor = BAND_ORDER[minBand] ?? 0
    const keptBand = trace.nodes.filter(
      (n) => (BAND_ORDER[n.band] ?? 0) >= floor || n.layer === 'VICTIM')
    const visible = keptBand.filter((n) => !(hideUnlayered && /^H\d+$/.test(n.layer)))
    const hidden = keptBand.length - visible.length
    const filtered = trace.nodes.length - keptBand.length

    const byHop = new Map()
    visible.forEach((n) => {
      const h = n.hop_distance
      if (!byHop.has(h)) byHop.set(h, [])
      byHop.get(h).push(n)
    })

    const tallest = Math.max(1, ...[...byHop.values()].map((c) => c.length))
    const h = Math.max(380, tallest * ROW_H + PAD * 2)
    const hops = [...byHop.keys()].sort((a, b) => a - b)
    const w = Math.max(560, (hops.length - 1) * colWidth + PAD * 2 + 160)

    const pos = new Map()
    hops.forEach((hop, ci) => {
      const col = byHop.get(hop).slice().sort((a, b) => b.mri - a.mri)
      const span = (col.length - 1) * ROW_H
      col.forEach((n, ri) => {
        pos.set(n.account_id, {
          ...n,
          x: PAD + ci * colWidth,
          y: h / 2 - span / 2 + ri * ROW_H,
          r: 5 + (n.mri / 100) * 9,
        })
      })
    })

    const drawn = trace.edges
      .filter((ed) => pos.has(ed.from) && pos.has(ed.to))
      .map((ed) => ({ ...ed, a: pos.get(ed.from), b: pos.get(ed.to) }))

    return {
      nodes: [...pos.values()],
      edges: drawn,
      width: w,
      height: h,
      hiddenCount: hidden,
      bandFiltered: filtered,
    }
  }, [trace, hideUnlayered, minBand, colWidth])

  // a null camera means "fit"; it resets whenever the drawing changes shape
  useEffect(() => { setView(null) }, [width, height])
  const cam = view || { x: 0, y: 0, w: width, h: height }

  /* ------------------------------------------------------ interaction */
  const zoom = (factor, cx = cam.x + cam.w / 2, cy = cam.y + cam.h / 2) => {
    const w = Math.min(width * 4, Math.max(width / 8, cam.w * factor))
    const h = w * (height / width)
    setView({ x: cx - (cx - cam.x) * (w / cam.w), y: cy - (cy - cam.y) * (h / cam.h), w, h })
  }

  const onWheel = (ev) => {
    const r = svgRef.current.getBoundingClientRect()
    const cx = cam.x + ((ev.clientX - r.left) / r.width) * cam.w
    const cy = cam.y + ((ev.clientY - r.top) / r.height) * cam.h
    zoom(ev.deltaY > 0 ? 1.15 : 0.87, cx, cy)
  }

  const onDown = (ev) => setDrag({ px: ev.clientX, py: ev.clientY, vx: cam.x, vy: cam.y })
  const onMove = (ev) => {
    if (!drag) return
    const r = svgRef.current.getBoundingClientRect()
    setView({
      ...cam,
      x: drag.vx - ((ev.clientX - drag.px) / r.width) * cam.w,
      y: drag.vy - ((ev.clientY - drag.py) / r.height) * cam.h,
    })
  }
  const onUp = () => setDrag(null)

  /** Centre the camera on one account without changing the zoom. */
  const focusOn = (accountId) => {
    const n = nodes.find((x) => x.account_id === accountId)
    if (!n) return
    setView({ x: n.x - cam.w / 2, y: n.y - cam.h / 2, w: cam.w, h: cam.h })
  }

  const downloadSvg = () => {
    const clone = svgRef.current.cloneNode(true)
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    // inline the themed colours so the file stands on its own
    const style = getComputedStyle(document.documentElement)
    let out = new XMLSerializer().serializeToString(clone)
    out = out.replace(/var\(--([a-z0-9-]+)\)/g, (_, name) =>
      style.getPropertyValue(`--${name}`).trim() || '#888')
    const url = URL.createObjectURL(new Blob([out], { type: 'image/svg+xml' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${trace.trace_id || 'trace'}.svg`
    a.click()
    URL.revokeObjectURL(url)
  }

  const labelled = showLabels === null ? nodes.length <= 45 : showLabels
  const neighbours = new Set()
  if (selected) {
    edges.forEach((ed) => {
      if (ed.from === selected) neighbours.add(ed.to)
      if (ed.to === selected) neighbours.add(ed.from)
    })
  }

  /* ------------------------------------------------------------ paint */
  const shapeFor = (n) => {
    const colour = BAND_VAR[n.band] || 'var(--muted)'
    const on = !selected || n.account_id === selected || neighbours.has(n.account_id)
    const common = {
      fill: colour,
      fillOpacity: on ? 0.85 : 0.25,
      stroke: n.account_id === selected ? 'var(--accent)' : 'var(--border)',
      strokeWidth: n.account_id === selected ? 2.5 : 1,
      strokeDasharray: n.is_hub ? '3 2' : undefined,
    }
    if (n.layer === 'VICTIM') {
      const s = n.r * 1.3
      return <rect x={-s} y={-s} width={s * 2} height={s * 2} transform="rotate(45)" {...common} />
    }
    if (/^H\d+$/.test(n.layer)) {
      const s = n.r * 0.95
      return <rect x={-s} y={-s} width={s * 2} height={s * 2} {...common} />
    }
    return <circle r={n.r} {...common} />
  }

  const toolbar = (
    <div className="graph-toolbar">
      <button onClick={() => setView(null)} title="Fit the whole graph">Fit</button>
      <button onClick={() => zoom(0.8)} aria-label="Zoom in" title="Zoom in">+</button>
      <button onClick={() => zoom(1.25)} aria-label="Zoom out" title="Zoom out">−</button>
      <button onClick={() => focusOn(trace.victim_account)} title="Centre on the victim">
        Victim
      </button>
      {selected && (
        <button onClick={() => focusOn(selected)} title="Centre on the selected account">
          Selected
        </button>
      )}

      <span className="sep" />

      <label className="small chk" title="Draw or hide accounts with no distinctive shape">
        <input type="checkbox" checked={hideUnlayered}
               onChange={(ev) => setHideUnlayered(ev.target.checked)} />
        hide H*
      </label>
      <label className="small chk" title="Account numbers on the canvas">
        <input type="checkbox" checked={labelled}
               onChange={(ev) => setShowLabels(ev.target.checked)} />
        labels
      </label>

      <label className="small" title="Only draw accounts at or above this band">
        band ≥{' '}
        <select value={minBand} onChange={(ev) => setMinBand(ev.target.value)}>
          <option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option>
        </select>
      </label>

      <label className="small" title="Horizontal spacing between hop columns">
        spread{' '}
        <input type="range" min="110" max="320" step="10" value={colWidth}
               onChange={(ev) => setColWidth(Number(ev.target.value))} style={{ width: 80 }} />
      </label>

      <span className="sep" />

      <button onClick={downloadSvg} title="Save the drawing as an SVG file">SVG</button>
      {exportUrl && (
        <a className="btnlink" href={exportUrl} target="_blank" rel="noreferrer"
           title="Backend-generated PDF report of this trace">PDF</a>
      )}
      <button className="primary" onClick={() => setFull((f) => !f)}
              title={full ? 'Leave full screen (Esc)' : 'Open the graph full screen'}>
        {full ? 'Exit full screen' : 'Full screen'}
      </button>
    </div>
  )

  const canvas = (
    <svg
      ref={svgRef}
      viewBox={`${cam.x} ${cam.y} ${cam.w} ${cam.h}`}
      width="100%"
      height={full ? '100%' : 460}
      role="img"
      aria-label={`Trace graph: ${nodes.length} accounts, ${edges.length} transactions`}
      style={{
        border: '1px solid var(--border)',
        borderRadius: full ? 0 : 6,
        background: 'var(--surface-2)',
        cursor: drag ? 'grabbing' : 'grab',
        touchAction: 'none',
        flex: full ? 1 : undefined,
        minHeight: 0,
      }}
      onWheel={onWheel}
      onMouseDown={onDown}
      onMouseMove={onMove}
      onMouseUp={onUp}
      onMouseLeave={onUp}
      onDoubleClick={() => setView(null)}
    >
      <defs>
        <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5"
                orient="auto">
          <path d="M0,0 L8,4 L0,8 z" fill="var(--muted)" />
        </marker>
      </defs>

      {edges.map((ed) => {
        const litSel = selected && (ed.from === selected || ed.to === selected)
        const litHov = hovered && (ed.from === hovered || ed.to === hovered)
        const isHovEdge = hoveredEdge === ed.edge_id
        const lit = litSel || litHov || isHovEdge
        const mx = (ed.a.x + ed.b.x) / 2
        return (
          <path
            key={ed.edge_id}
            d={`M ${ed.a.x} ${ed.a.y} C ${mx} ${ed.a.y}, ${mx} ${ed.b.y}, ${ed.b.x - ed.b.r - 3} ${ed.b.y}`}
            fill="none"
            stroke={lit ? 'var(--accent)' : 'var(--border)'}
            strokeWidth={lit ? (isHovEdge ? 2.4 : 1.8) : 1}
            opacity={(selected || hovered) && !lit ? 0.18 : 0.9}
            markerEnd="url(#arrow)"
            onMouseEnter={() => setHoveredEdge(ed.edge_id)}
            onMouseLeave={() => setHoveredEdge(null)}
            style={{ cursor: 'crosshair' }}
          >
            <title>
              {`Rs ${Number(ed.amount).toLocaleString('en-IN')}\n${ed.from} to ${ed.to}` +
               `\nhop ${ed.hop} \u00b7 source_row_id ${ed.source_row_id}`}
            </title>
          </path>
        )
      })}

      {nodes.map((n) => (
        <g
          key={n.account_id}
          transform={`translate(${n.x} ${n.y})`}
          onClick={() => onSelect(n.account_id)}
          onMouseEnter={() => setHovered(n.account_id)}
          onMouseLeave={() => setHovered(null)}
          opacity={hovered && hovered !== n.account_id &&
                   !edges.some((e) => (e.from === hovered && e.to === n.account_id) ||
                                      (e.to === hovered && e.from === n.account_id))
            ? 0.35 : 1}
          style={{ cursor: 'pointer' }}
        >
          {shapeFor(n)}
          <title>
            {`${n.account_id}\n${n.layer} · hop ${n.hop_distance}\nMRI ${n.mri} ${n.band} · ${n.role}\n${n.layer_reason}`}
          </title>
          {(labelled || n.account_id === selected || n.band === 'HIGH' || n.band === 'CRITICAL') && (
            <text x={n.r + 5} y={3.5} fontSize="9.5" fill="var(--text-2)"
                  style={{ pointerEvents: 'none', fontFamily: 'ui-monospace, Menlo, monospace' }}>
              {n.account_id}
            </text>
          )}
        </g>
      ))}

      {[...new Set(nodes.map((n) => n.hop_distance))].sort((a, b) => a - b).map((hop) => {
        const any = nodes.find((n) => n.hop_distance === hop)
        return (
          <text key={hop} x={any.x} y={16} fontSize="10" textAnchor="middle" fill="var(--muted)"
                style={{ pointerEvents: 'none' }}>
            hop {hop}
          </text>
        )
      })}
    </svg>
  )

  const legend = (
    <div className="row small muted" style={{ marginTop: 8, gap: 14, flexWrap: 'wrap' }}>
      <span>◆ victim</span>
      <span>● layered (L1/L2/L3)</span>
      <span>■ unlayered (H*)</span>
      <span>dashed border = hub</span>
      <span>size = MRI</span>
      {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((b) => (
        <span key={b} style={{ color: BAND_VAR[b] }}>■ {b}</span>
      ))}
      <span style={{ marginLeft: 'auto' }}>
        {nodes.length} of {trace.nodes.length} accounts drawn · {edges.length} of{' '}
        {trace.edges.length} transactions · drag to pan, scroll to zoom, double-click to fit
      </span>
    </div>
  )

  const notes = (hiddenCount > 0 || bandFiltered > 0) && (
    <div className="disclaimer">
      {hiddenCount > 0 && `${hiddenCount} unlayered account(s) hidden from the canvas. `}
      {bandFiltered > 0 && `${bandFiltered} account(s) below ${minBand} filtered out. `}
      Everything hidden here is still in the result, the tables, the evidence and the PDF
      report — only the drawing is reduced.
    </div>
  )

  const selectedNode = selected ? nodes.find((n) => n.account_id === selected) : null

  return (
    <div
      ref={wrapRef}
      className={full ? 'graph-full' : ''}
      style={full ? undefined : { minWidth: 0 }}
    >
      {toolbar}
      {canvas}
      {legend}
      {notes}
      {full && selectedNode && (
        <div className="graph-float">
          <div className="mono" style={{ fontSize: 14 }}>{selectedNode.account_id}</div>
          <div className="small" style={{ margin: '4px 0' }}>
            {selectedNode.layer} · hop {selectedNode.hop_distance} · MRI {selectedNode.mri}{' '}
            {selectedNode.band} · {selectedNode.role}
          </div>
          <div className="small muted">{selectedNode.layer_reason}</div>
          {onOpenAccount && (
            <button style={{ marginTop: 8 }}
                    onClick={() => { setFull(false); onOpenAccount(selectedNode.account_id) }}>
              Open account
            </button>
          )}
        </div>
      )}
    </div>
  )
}
