/** Presentation-layer formatting only. No calculation ever happens here. */
export const inr = (v) => {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const neg = v < 0
  const [w, f] = Math.abs(v).toFixed(2).split('.')
  let head = w.slice(0, -3), tail = w.slice(-3), parts = []
  while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2) }
  if (head) parts.unshift(head)
  return `${neg ? '-' : ''}₹${[...parts, tail].filter(Boolean).join(',')}.${f}`
}
export const inrShort = (v) => {
  if (v === null || v === undefined) return '—'
  const a = Math.abs(v)
  if (a >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`
  if (a >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`
  if (a >= 1e3) return `₹${(v / 1e3).toFixed(1)} K`
  return `₹${v.toFixed(0)}`
}
export const n = (v) => (v === null || v === undefined ? '—' : v.toLocaleString('en-IN'))
export const pct = (v, d = 1) => (v === null || v === undefined ? '—' : `${v.toFixed(d)}%`)
export const ts = (epoch) => {
  if (!epoch) return '—'
  const d = new Date(epoch * 1000)
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
export const dur = (s) => {
  if (s === null || s === undefined) return 'not measurable'
  if (s < 60) return `${Math.round(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`
}
/** Band glyph so risk is never carried by colour alone (A11Y). */
export const bandGlyph = (b) => ({ LOW: '▁', MEDIUM: '▃', HIGH: '▆', CRITICAL: '█' }[b] || '·')
