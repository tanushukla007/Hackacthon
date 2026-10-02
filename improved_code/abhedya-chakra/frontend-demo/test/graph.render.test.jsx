import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import fs from 'fs'
import TraceGraph from '../src/components/TraceGraph.jsx'

// Render the graph without a browser and assert what it drew.
//
//   curl -s -X POST localhost:8000/api/trace -H 'content-type: application/json' \
//        -d '{"victim_account":"327091122305"}' > test/fixtures/trace.json
//
// The fixture is committed so the test runs without a backend (and survives a
// sandbox recycle, which /tmp does not).
//   npx esbuild test/graph.render.test.jsx --bundle --platform=node --format=cjs \
//       --jsx=automatic --outfile=/tmp/t.cjs && node /tmp/t.cjs
// Bundled to CJS (react-dom/server needs it), so no import.meta here.
const FIXTURE = ['test/fixtures/trace.json', 'frontend-demo/test/fixtures/trace.json']
  .find((p) => fs.existsSync(p))
const trace = JSON.parse(fs.readFileSync(process.env.TRACE_JSON || FIXTURE, 'utf8')).data

function check(name, cond, extra='') {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name} ${extra}`)
  if (!cond) process.exitCode = 1
}

// default render: >60 nodes so H* hidden
const html = renderToStaticMarkup(React.createElement(TraceGraph, { trace, selected: null, onSelect: () => {} }))

const circles = (html.match(/<circle/g) || []).length
const rects   = (html.match(/<rect/g) || []).length
const paths   = (html.match(/<path /g) || []).length
const texts   = (html.match(/<text/g) || []).length
const layered = trace.nodes.filter(n => !/^H\d+$/.test(n.layer))
const hiddenN = trace.nodes.length - layered.length

check('renders an svg', html.includes('<svg'))
check('has a viewBox', /viewBox="0 0 \d+/.test(html), html.match(/viewBox="[^"]+"/)[0])
check('one shape per visible node', circles + rects === layered.length,
      `circles=${circles} + rects=${rects} = ${circles+rects}, expected ${layered.length}`)
check('edges drawn as curves', paths >= 1, `paths=${paths}`)
check('hop column headings present', html.includes('hop 0') && html.includes('hop 1'))
check('honest hidden-count note',
      html.includes(`${hiddenN} unlayered account(s)`) && html.includes('hidden from the canvas'),
      `hidden=${hiddenN}`)
check('hidden nodes are stated as still present in the result',
      html.includes('still in the result'))
check('legend states the encodings', html.includes('size = MRI') && html.includes('dashed border = hub'))
check('bands named, not colour only', ['LOW','MEDIUM','HIGH','CRITICAL'].every(b => html.includes(b)))
check('no NaN in geometry', !/NaN/.test(html))
check('accessible label', /aria-label="Trace graph: \d+ accounts, \d+ transactions"/.test(html),
      (html.match(/aria-label="Trace graph[^"]*"/)||[''])[0])

// selected node render
const sel = '545470146222'
const html2 = renderToStaticMarkup(React.createElement(TraceGraph, { trace, selected: sel, onSelect: () => {} }))
check('selection highlights with accent stroke', html2.includes('var(--accent)'))
check('selected account is labelled', html2.includes(sel))

// every H* drawn when the toggle is off: force it by passing a small trace
const small = { ...trace, nodes: trace.nodes.slice(0, 50), edges: trace.edges.slice(0, 40) }
const html3 = renderToStaticMarkup(React.createElement(TraceGraph, { trace: small, selected: null, onSelect: () => {} }))
check('small trace draws every node incl. H*', ((html3.match(/<circle/g)||[]).length + (html3.match(/<rect/g)||[]).length) === small.nodes.length,
      `${(html3.match(/<circle/g)||[]).length + (html3.match(/<rect/g)||[]).length} vs ${small.nodes.length}`)
check('small trace has no hidden note', !html3.includes('hidden from the canvas'))
check('no NaN with every node drawn', !/NaN/.test(html3))

console.log(`\nnodes drawn: ${layered.length}/${trace.nodes.length}, hidden: ${hiddenN}, texts: ${texts}`)
