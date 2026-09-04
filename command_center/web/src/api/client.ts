/* Cliente HTTP do Command Center.
 * - cookies de sessão (HttpOnly) vão sozinhos; o CSRF vai no header X-CSRF
 *   copiado do cookie cc_csrf (legível) em toda requisição que não é GET.
 * - 401 => sessão caiu: avisa o AuthContext (que manda para /login).
 * - Nunca guarda token no JS. Nenhum segredo aqui.
 */
export const API = '/ops/api'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
  get unauthorized() { return this.status === 401 }
  get forbidden() { return this.status === 403 }
  get offline() { return this.status === 0 }
}

type Listener = () => void
const onUnauthorized = new Set<Listener>()
export function subscribeUnauthorized(fn: Listener) { onUnauthorized.add(fn); return () => { onUnauthorized.delete(fn) } }

function csrf(): string {
  const m = document.cookie.match(/(?:^|;\s*)cc_csrf=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

async function req<T>(method: string, path: string, body?: unknown, opts: { silent401?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') headers['X-CSRF'] = csrf()
  let res: Response
  try {
    res = await fetch(API + path, { method, headers, credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new ApiError(0, 'Sem conexão com o servidor.')
  }
  if (res.status === 401 && !opts.silent401) onUnauthorized.forEach(fn => fn())
  if (!res.ok) {
    let msg = res.statusText || `HTTP ${res.status}`
    try {
      const j = await res.json()
      if (typeof j?.detail === 'string') msg = j.detail
      else if (j?.detail?.[0]?.msg) msg = j.detail[0].msg
      else if (typeof j?.error === 'string') msg = j.error
    } catch { /* corpo não-JSON */ }
    throw new ApiError(res.status, msg)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string, opts?: { silent401?: boolean }) => req<T>('GET', path, undefined, opts),
  post: <T>(path: string, body?: unknown) => req<T>('POST', path, body ?? {}),
  put: <T>(path: string, body?: unknown) => req<T>('PUT', path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => req<T>('PATCH', path, body ?? {}),
}

export function qs(params: Record<string, string | number | boolean | null | undefined>) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? '?' + s : ''
}
