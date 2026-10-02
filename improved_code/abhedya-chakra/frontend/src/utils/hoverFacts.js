/**
 * What the graph says when you hover.
 *
 * Kept as pure functions, separate from the Cytoscape component, for two
 * reasons: the wording is a contract (OBSERVED vs ASSESSED must stay separate
 * even in a tooltip), and a pure function can be tested without a browser,
 * which this sandbox does not have.
 *
 * Nothing here computes anything. Every value is read from the node or edge
 * data the backend sent.
 */
import { inr, n, ts } from './format'

const LAYER_MEANING = {
  VICTIM: 'the account the money left',
  L1: 'first collection point',
  L2: 'dispersal',
  L3: 'exit edge of the trace',
}

export const layerMeaning = (layer) =>
  LAYER_MEANING[layer] || 'no distinctive shape measured at this hop'

/** Rows for the hover card over a node. Order matters: observed, then assessed. */
export function nodeHoverFacts(d = {}) {
  const rows = [
    { k: 'layer', v: `${d.layer ?? '—'} · ${layerMeaning(d.layer)}`, group: 'observed' },
    { k: 'hop', v: d.hop == null ? '—' : `${d.hop} from the victim`, group: 'observed' },
    { k: 'degree', v: `${n(d.in_degree ?? 0)} in · ${n(d.out_degree ?? 0)} out`, group: 'observed' },
    { k: 'traced value', v: inr(d.attributed ?? 0), group: 'observed' },
  ]
  if (d.hub) {
    rows.push({
      k: 'hub',
      v: 'not expanded — infrastructure, not a finding',
      group: 'observed',
    })
  }
  rows.push({ k: 'index', v: `${d.mri ?? '—'} ${d.band ?? ''}`.trim(), group: 'assessed' })
  if (d.role) rows.push({ k: 'role', v: d.role, group: 'assessed' })
  return rows
}

/** Rows for the hover card over an edge. An edge is always a real row in the CSV. */
export function edgeHoverFacts(d = {}) {
  return [
    { k: 'amount', v: inr(d.amount ?? 0), group: 'observed' },
    { k: 'from', v: d.source ?? d.from ?? '—', group: 'observed' },
    { k: 'to', v: d.target ?? d.to ?? '—', group: 'observed' },
    { k: 'when', v: ts(d.ts), group: 'observed' },
    { k: 'hop', v: d.hop == null ? '—' : String(d.hop), group: 'observed' },
    { k: 'source_row_id', v: d.row == null ? '—' : String(d.row), group: 'provenance' },
  ]
}

/**
 * Keep the card inside the canvas. A tooltip that falls off the right edge of
 * a 1280-wide screen is a tooltip nobody can read.
 */
export function clampCard(x, y, box, card = { w: 260, h: 190 }) {
  const pad = 10
  const left = x + card.w + pad > box.w ? Math.max(pad, x - card.w - 14) : x + 14
  const top = Math.min(Math.max(pad, y - 12), Math.max(pad, box.h - card.h - pad))
  return { left, top }
}
