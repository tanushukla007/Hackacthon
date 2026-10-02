import { useEffect, useMemo, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import { useTheme } from '../../theme'
import { clampCard, edgeHoverFacts, nodeHoverFacts } from '../../utils/hoverFacts'

cytoscape.use(dagre)

/* Cytoscape cannot read CSS variables, so the palette is resolved from the
   document at build time and the graph is rebuilt when the theme changes. */
const cssVar = (name, fallback) => {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}
const palette = () => ({
  LOW: cssVar('--moss', '#6f9475'),
  MEDIUM: cssVar('--ochre', '#c8a24a'),
  HIGH: cssVar('--oxide', '#cc7a3b'),
  CRITICAL: cssVar('--rust', '#b84141'),
  other: cssVar('--slate-blue', '#5d7f9e'),
  halo: cssVar('--node-halo', '#0b0c0f'),
  label: cssVar('--node-label', '#b2b0a9'),
  edge: cssVar('--edge-line', '#39404d'),
  arrow: cssVar('--edge-arrow', '#4a5260'),
  hub: cssVar('--hub-ring', '#e4e1d9'),
  accent: cssVar('--brass', '#c8a24a'),
})
/* Shape carries the layer so meaning never depends on colour alone (A11Y §33). */
const LAYER_SHAPE = {
  VICTIM: 'diamond', L1: 'round-rectangle', L2: 'rectangle', L3: 'hexagon',
}

export default function NetworkGraph({ trace, selected, onSelect, timeCursor }) {
  /* The canvas palette is resolved from CSS variables, so the graph has to be
     rebuilt when the sheet changes. */
  const { theme } = useTheme()
  const box = useRef(null)
  const cy = useRef(null)
  /* Dense fans are unreadable at 150+ nodes. The filter hides UNLAYERED nodes
     from the CANVAS only - the result itself is untouched and the count of what
     is hidden is always stated. */
  const [layeredOnly, setLayeredOnly] = useState(trace ? trace.nodes.length > 60 : false)
  const [hover, setHover] = useState(null)
  const shown = useMemo(() => {
    if (!trace) return null
    const nodes = layeredOnly
      ? trace.nodes.filter((n) => !/^H\d+$/.test(n.layer))
      : trace.nodes
    const keep = new Set(nodes.map((n) => n.account_id))
    return {
      ...trace,
      nodes,
      edges: trace.edges.filter((e) => keep.has(e.from) && keep.has(e.to)),
    }
  }, [trace, layeredOnly])
  const hidden = trace ? trace.nodes.length - (shown?.nodes.length || 0) : 0

  /* Build once per trace. Selection and time filtering never trigger a relayout (§29). */
  useEffect(() => {
    const C = palette()
    if (!box.current || !shown) return
    const trace = shown
    const elements = [
      ...trace.nodes.map((n) => ({
        data: {
          id: n.account_id, label: n.account_id.slice(-6), band: n.band, layer: n.layer,
          mri: n.mri, hub: n.is_hub ? 1 : 0, hop: n.hop_distance,
          role: n.role, attributed: n.attributed_value,
          in_degree: n.in_degree, out_degree: n.out_degree,
        },
      })),
      ...trace.edges.map((e) => ({
        data: {
          id: `e${e.edge_id}`, source: e.from, target: e.to,
          amount: e.amount, ts: e.ts_epoch, row: e.source_row_id, hop: e.hop,
          w: Math.max(1, Math.min(7, Math.log10(Math.max(e.amount, 10)) * 1.5)),
        },
      })),
    ]
    const inst = cytoscape({
      container: box.current,
      elements,
      wheelSensitivity: 0.2,
      pixelRatio: 1,
      textureOnViewport: trace.nodes.length > 250,
      hideEdgesOnViewport: trace.nodes.length > 400,
      style: [
        {
          selector: 'node',
          style: {
            'background-color': (el) => C[el.data('band')] || C.other,
            'background-opacity': 0.82,
            shape: (el) => LAYER_SHAPE[el.data('layer')] || 'ellipse',
            width: (el) => 16 + Math.min(el.data('mri'), 100) / 6,
            height: (el) => 16 + Math.min(el.data('mri'), 100) / 6,
            'border-width': 1,
            'border-color': C.halo,
            label: 'data(label)',
            'font-family': 'ui-monospace, Menlo, Consolas, monospace',
            'font-size': 8,
            color: C.label,
            'text-valign': 'bottom',
            'text-margin-y': 3,
            'min-zoomed-font-size': 7,
          },
        },
        { selector: 'node[hub = 1]', style: { 'border-width': 2, 'border-color': C.hub, 'border-style': 'dashed' } },
        { selector: 'node:selected', style: { 'border-width': 2, 'border-color': C.accent, 'border-style': 'solid' } },
        {
          selector: 'edge',
          style: {
            width: 'data(w)',
            'line-color': C.edge,
            'target-arrow-color': C.arrow,
            'target-arrow-shape': 'triangle',
            'arrow-scale': 0.6,
            'curve-style': 'bezier',
            opacity: 0.75,
          },
        },
        { selector: 'edge.dim', style: { opacity: 0.08 } },
        { selector: 'node.dim', style: { 'background-opacity': 0.15, 'text-opacity': 0.2 } },
        { selector: 'edge.hot', style: { 'line-color': C.accent, 'target-arrow-color': C.accent, opacity: 1 } },
        /* Hover: emphasis only. No size change, no relayout, no animation (29, 34.2). */
        { selector: 'node.hov', style: { 'border-width': 3, 'border-color': C.accent, 'text-opacity': 1 } },
        { selector: 'edge.hov-edge', style: { 'line-color': C.accent, 'target-arrow-color': C.accent, opacity: 1 } },
      ],
      layout: layoutFor(trace.nodes.length),
    })
    inst.on('tap', 'node', (ev) => onSelect?.(ev.target.id()))
    inst.on('tap', (ev) => { if (ev.target === inst) onSelect?.(null) })

    /* Hover reads out what is already on the element. It never selects, never
       re-runs a layout, and never fetches - hovering a 500-node graph has to
       stay free. The same facts are available by clicking, so nothing is
       hover-only (33). */
    const container = inst.container()
    const show = (el, kind) => {
      const p = el.renderedPosition ? el.renderedPosition() : { x: 0, y: 0 }
      setHover({ kind, id: el.id(), data: el.data(), x: p.x, y: p.y })
    }
    inst.on('mouseover', 'node', (ev) => {
      ev.target.addClass('hov')
      ev.target.connectedEdges().addClass('hov-edge')
      if (container) container.style.cursor = 'pointer'
      show(ev.target, 'node')
    })
    inst.on('mouseout', 'node', (ev) => {
      ev.target.removeClass('hov')
      ev.target.connectedEdges().removeClass('hov-edge')
      if (container) container.style.cursor = ''
      setHover(null)
    })
    inst.on('mouseover', 'edge', (ev) => {
      ev.target.addClass('hov-edge')
      const mid = ev.renderedPosition || { x: 0, y: 0 }
      setHover({ kind: 'edge', id: ev.target.id(), data: ev.target.data(),
                 x: mid.x, y: mid.y })
    })
    inst.on('mouseout', 'edge', (ev) => {
      ev.target.removeClass('hov-edge')
      setHover(null)
    })
    inst.on('pan zoom', () => setHover(null))
    cy.current = inst
    return () => { inst.destroy(); cy.current = null }
  }, [shown, onSelect, theme])

  /* Selection highlight: pure class toggling, no layout work. */
  useEffect(() => {
    const inst = cy.current
    if (!inst) return
    inst.elements().removeClass('hot')
    inst.nodes().unselect()
    if (selected && inst.getElementById(selected).length) {
      const node = inst.getElementById(selected)
      node.select()
      node.connectedEdges().addClass('hot')
    }
  }, [selected, shown])

  /* Time scrubbing dims edges after the cursor. Still no relayout. */
  useEffect(() => {
    const inst = cy.current
    if (!inst) return
    if (!timeCursor) { inst.edges().removeClass('dim'); return }
    inst.batch(() => {
      inst.edges().forEach((e) => {
        if (e.data('ts') > timeCursor) e.addClass('dim'); else e.removeClass('dim')
      })
    })
  }, [timeCursor, shown])

  return (
    <div className="canvas-wrap">
      <div className="canvas" ref={box} />
      <div className="canvas-tools">
        <button className="btn ghost" onClick={() => cy.current?.fit(undefined, 40)}>Fit</button>
        <button className="btn ghost" onClick={() => cy.current?.layout(layoutFor(shown?.nodes.length || 0)).run()}>
          Re-layout
        </button>
        <button className={`btn ghost ${layeredOnly ? 'on' : ''}`}
                onClick={() => setLayeredOnly((v) => !v)}
                title="Hide accounts with no measured collection, dispersal or exit shape">
          {layeredOnly ? 'Layered only' : 'All nodes'}
        </button>
      </div>
      {trace?.truncated && (
        <div className="trunc-banner">
          <b>Result truncated · {trace.truncation_reason}.</b>{' '}
          {trace.truncation_reason === 'HUB_GUARD'
            ? `Expansion stopped at a hub account (degree ≥ ${trace.hub_threshold_degree}). Hubs are infrastructure, not findings.`
            : `Caps: ${trace.caps.max_nodes} nodes / ${trace.caps.max_edges} edges. Narrow the window or reduce hops to see the rest.`}
        </div>
      )}
      {hover && (() => {
        const b = box.current?.getBoundingClientRect?.() || { width: 900, height: 600 }
        const { left, top } = clampCard(hover.x, hover.y, { w: b.width, h: b.height })
        const facts = hover.kind === 'node'
          ? nodeHoverFacts(hover.data)
          : edgeHoverFacts(hover.data)
        return (
          <div className="hovercard" style={{ left, top }} role="tooltip" aria-hidden="true">
            <div className="hc-head mono">
              {hover.kind === 'node' ? hover.id : `row ${hover.data.row}`}
            </div>
            <table>
              <tbody>
                {facts.map((f) => (
                  <tr key={f.k} className={`g-${f.group}`}>
                    <td className="k">{f.k}</td>
                    <td className="v mono">{f.v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="hc-foot">
              {hover.kind === 'node'
                ? 'index and role are assessments · click to open the inspector'
                : 'one transaction, cited by source_row_id'}
            </div>
          </div>
        )
      })()}
      <div className="canvas-overlay">
        {['VICTIM', 'L1', 'L2', 'L3'].map((l) => (
          <div className="lg" key={l}>
            <span className="sw" style={{
              borderColor: 'var(--faint)',
              transform: l === 'VICTIM' ? 'rotate(45deg)' : 'none',
              borderRadius: l === 'L1' ? 3 : 0,
            }} />
            <span className="mono">{l}</span>
            <span className="dim">{l === 'VICTIM' ? 'seed' : l === 'L1' ? 'collection' : l === 'L2' ? 'dispersal' : 'exit'}</span>
          </div>
        ))}
        <div className="lg" style={{ marginTop: 4 }}>
          <span className="sw" style={{ borderColor: 'var(--hub-ring)', borderStyle: 'dashed' }} />
          <span className="dim">hub · not expanded</span>
        </div>
        <div className="dim" style={{ marginTop: 4 }}>size = MRI · colour = band · shape = layer</div>
        {hidden > 0 && (
          <div className="dim" style={{ marginTop: 3 }}>
            {hidden} unlayered account(s) hidden from the canvas — still in the result and the ledger
          </div>
        )}
      </div>
    </div>
  )
}

/* Layout is chosen by size, runs once, and is never re-run on selection (§29). */
function layoutFor(nodeCount) {
  if (nodeCount > 400) {
    return { name: 'breadthfirst', directed: true, spacingFactor: 0.9, animate: false, padding: 24 }
  }
  return {
    name: 'dagre', rankDir: 'LR', nodeSep: 12, rankSep: 150, edgeSep: 6, ranker: 'tight-tree',
    animate: false, padding: 24, fit: true, spacingFactor: 1,
  }
}
