/* Cliente HTTP da área do cliente (#40). Separado do cliente da equipe (api/client.ts):
 * outra base (/ops/api/portal), outro cookie de CSRF (cp_csrf). Sessão em cookie HttpOnly. */
const BASE = '/ops/api/portal'

export class PortalError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

function csrf() {
  const m = document.cookie.match(/(?:^|;\s*)cp_csrf=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

export async function papi<T>(method: 'GET' | 'POST' | 'PATCH', path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') headers['X-CSRF'] = csrf()
  let res: Response
  try {
    res = await fetch(BASE + path, { method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body) })
  } catch { throw new PortalError(0, 'No connection. Check your internet and try again.') }
  if (!res.ok) {
    let msg = `Something went wrong (${res.status}).`
    try {
      const j = await res.json()
      if (typeof j?.detail === 'string') msg = j.detail
      else if (Array.isArray(j?.detail) && j.detail[0]?.msg) msg = String(j.detail[0].msg)
    } catch { /* corpo não-JSON */ }
    throw new PortalError(res.status, msg)
  }
  return res.json() as Promise<T>
}

export interface Driver { id: number; name: string; birth_date: string | null; is_self: boolean; email: string | null; phone: string | null
  measures: Record<string, number | string>; measures_updated_at: string | null; notes: string | null; age: number | null }
export interface Account { id: number; email: string; name: string; birth_date: string; phone: string | null
  address_line1: string | null; address_line2: string | null; city: string | null; state: string | null; zip: string | null
  linked: boolean; drivers: Driver[] }

export interface Periodo { open: boolean; spots: number }
export interface Dia { date: string; weekday: number; any_open: boolean; periods: { manha: Periodo; tarde: Periodo; dia: Periodo } }
export interface AgendaCfg { morning_start: string; morning_end: string; afternoon_start: string; afternoon_end: string
  horizon_days: number; min_notice_hours: number; auto_confirm: number }
export interface Servico { id: number; name: string; description: string | null; price: number }
export interface Booking { id: number; date: string; period: 'manha' | 'tarde' | 'dia'; status: 'pendente' | 'confirmada' | 'recusada' | 'cancelada'
  notes: string | null; decision_note: string | null; driver: string | null; created_at: string; service: string | null; price: number | null }

export const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
