import { type ReactNode } from 'react'
import { ApiError } from '../api/client'
import type { Level, Policy } from '../api/types'

export type Tone = 'ok' | 'warn' | 'crit' | 'info' | 'neutral' | 'accent' | 'outline'

export function Chip({ tone = 'neutral', children, dot }: { tone?: Tone; children: ReactNode; dot?: boolean }) {
  return <span className={`chip ${tone}`}>{dot && <i />}{children}</span>
}

export function levelTone(l: Level): Tone {
  return l === 'CRITICAL' ? 'crit' : l === 'HIGH' ? 'warn' : l === 'MEDIUM' ? 'info' : 'neutral'
}
export function statusTone(s?: string | null): Tone {
  switch ((s || '').toUpperCase()) {
    case 'CONNECTED': case 'COMPLETED': case 'DONE': case 'APPROVED': case 'ACTIVE': case 'SAFE': return 'ok'
    case 'DEGRADED': case 'SYNCING': case 'RUNNING': case 'QUEUED': case 'PROPOSED': case 'DELIVERED': case 'SENT':
    case 'PENDING': case 'AT_RISK': case 'REQUIRES_APPROVAL': case 'REQUIRES_CONFIRMATION': case 'NEW': return 'warn'
    case 'ERROR': case 'FAILED': case 'REJECTED': case 'AUTORESPONDED': case 'DECLINED': case 'VOIDED': case 'BLOCKED': case 'OVERDUE': return 'crit'
    case 'DISCONNECTED': case 'INACTIVE': case 'CANCELLED': return 'neutral'
    default: return 'neutral'
  }
}
export const POLICY_LABEL: Record<Policy, string> = {
  SAFE: 'Automática', REQUIRES_CONFIRMATION: 'Confirmar', REQUIRES_APPROVAL: 'Aprovação', BLOCKED: 'Bloqueada',
}
export const WAIVER_LABEL: Record<string, string> = {
  completed: 'assinada', delivered: 'aberta, não assinada', sent: 'enviada, não aberta',
  autoresponded: 'e-mail devolveu', declined: 'recusada', voided: 'anulada',
}

export function Spinner() { return <span className="spin" aria-label="carregando" /> }

export function Loading({ rows = 4 }: { rows?: number }) {
  return <div className="stack" style={{ padding: 16 }} aria-busy="true">
    {Array.from({ length: rows }).map((_, i) => <div key={i} className="skel" style={{ width: `${90 - i * 12}%` }} />)}
  </div>
}

export function Empty({ title = 'Nada aqui', children }: { title?: string; children?: ReactNode }) {
  return <div className="state"><div className="t">{title}</div>{children && <p>{children}</p>}</div>
}

export function ErrorState({ error, retry }: { error: ApiError | Error; retry?: () => void }) {
  const e = error as ApiError
  const off = e instanceof ApiError && e.offline
  const forb = e instanceof ApiError && e.forbidden
  return <div className="state" role="alert">
    <div className="t">{off ? 'Sem conexão' : forb ? 'Sem permissão' : 'Não deu para carregar'}</div>
    <p>{off ? 'O servidor não respondeu. Verifique a rede e tente de novo.' : e.message}</p>
    {retry && !forb && <button className="btn sm" onClick={retry}>Tentar de novo</button>}
  </div>
}

export function Section({ title, count, right, children, tight }: { title: ReactNode; count?: number; right?: ReactNode; children: ReactNode; tight?: boolean }) {
  return <section className="card">
    <div className="card-h"><h2 className="h2">{title}{count !== undefined && <span className="count">{count}</span>}</h2><div className="grow" />{right}</div>
    <div className={`card-b${tight ? ' tight' : ''}`}>{children}</div>
  </section>
}

export function Kpi({ label, value, tone, foot, onClick }: { label: string; value: ReactNode; tone?: 'crit' | 'warn' | 'ok'; foot?: ReactNode; onClick?: () => void }) {
  return <div className={`card kpi${onClick ? ' link' : ''}`} onClick={onClick} role={onClick ? 'button' : undefined} tabIndex={onClick ? 0 : undefined}
    onKeyDown={e => { if (onClick && (e.key === 'Enter' || e.key === ' ')) onClick() }}>
    <div className="lbl">{label}</div>
    <div className={`val ${tone || ''}`}>{value}</div>
    {foot && <div className="foot">{foot}</div>}
  </div>
}

export function Banner({ tone, children }: { tone: 'crit' | 'warn' | 'ok' | 'info'; children: ReactNode }) {
  return <div className={`banner ${tone}`} role={tone === 'crit' ? 'alert' : 'status'}>{children}</div>
}

export function Ext({ href, children }: { href?: string | null; children: ReactNode }) {
  if (!href) return <span className="muted">{children}</span>
  return <a href={href} target="_blank" rel="noopener noreferrer">{children} ↗</a>
}
