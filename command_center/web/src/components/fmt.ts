const TZ = 'America/New_York'   // Orlando

export function fmtDate(iso?: string | null) {
  if (!iso) return '—'
  const d = iso.length <= 10 ? new Date(iso + 'T12:00:00Z') : new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: iso.length <= 10 ? 'UTC' : TZ })
}
export function fmtDateTime(iso?: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: TZ })
}
export function ago(iso?: string | null) {
  if (!iso) return 'nunca'
  const d = new Date(iso); if (isNaN(d.getTime())) return iso
  const s = Math.max(0, (Date.now() - d.getTime()) / 1000)
  if (s < 60) return 'agora'
  if (s < 3600) return `${Math.floor(s / 60)} min`
  if (s < 86400) return `${Math.floor(s / 3600)} h`
  return `${Math.floor(s / 86400)} d`
}
export function daysUntil(iso?: string | null) {
  if (!iso) return null
  const d = new Date(iso.slice(0, 10) + 'T12:00:00Z')
  const today = new Date(); today.setUTCHours(12, 0, 0, 0)
  return Math.round((d.getTime() - today.getTime()) / 86400000)
}
export function money(v?: number | null) {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}
export function initials(name?: string | null) {
  return (name || '?').split(/\s+/).slice(0, 2).map(p => p[0]?.toUpperCase() || '').join('')
}
export function safeJson(s?: string | null): unknown {
  if (!s) return null
  try { return JSON.parse(s) } catch { return s }
}
