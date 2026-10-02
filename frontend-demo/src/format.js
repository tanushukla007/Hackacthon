/** Display helpers. Formatting only - no derived analytics. */

export const nf = new Intl.NumberFormat('en-IN')

export function num(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return nf.format(v)
}

/** Indian short scale, used only for display next to the exact value. */
export function inr(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`
  if (a >= 1e3) return `₹${(v / 1e3).toFixed(1)} K`
  return `₹${v.toFixed(2)}`
}

export function inrExact(v) {
  if (v === null || v === undefined) return '—'
  return `₹${nf.format(Number(v).toFixed(2))}`
}

export function ms(v) {
  if (v === null || v === undefined) return '—'
  return `${Number(v).toFixed(v < 10 ? 2 : 0)} ms`
}

export function dt(v) {
  if (!v) return '—'
  const d = typeof v === 'number' ? new Date(v * 1000) : new Date(v)
  if (Number.isNaN(d.getTime())) return String(v)
  return d.toISOString().slice(0, 19).replace('T', ' ')
}

export function dur(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const m = Math.floor(seconds / 60)
  return `${m}m ${Math.round(seconds - m * 60)}s`
}
