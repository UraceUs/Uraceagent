import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '../api/client'
import type { Level, Policy } from '../api/types'

export type Tone = 'ok' | 'warn' | 'crit' | 'info' | 'neutral' | 'accent' | 'outline'

export function Chip({ tone = 'neutral', children, dot, glyph, title }: { tone?: Tone | 'run' | 'wait'; children: ReactNode; dot?: boolean; glyph?: string; title?: string }) {
  return <span className={`chip ${tone}`} title={title}>{glyph ? <span className="g" aria-hidden="true">{glyph}</span> : dot && <i />}{children}</span>
}

/** Linguagem de estado do Pit Wall: cor + glifo + texto, nunca só a cor.
 *  ✓ feito/ok · ◐ em andamento · ○ esperando · ▲ atenção · ✕ falhou/crítico · — desligado */
export type StatusKind = 'ok' | 'run' | 'wait' | 'warn' | 'crit' | 'off'
export const STATUS_GLYPH: Record<StatusKind, string> = { ok: '✓', run: '◐', wait: '○', warn: '▲', crit: '✕', off: '—' }
export function statusKind(s?: string | null): StatusKind {
  switch ((s || '').toUpperCase()) {
    case 'CONNECTED': case 'COMPLETED': case 'DONE': case 'APPROVED': case 'ACTIVE': case 'SAFE': case 'PAID': case 'OK': case 'CONFIRMED': return 'ok'
    case 'SYNCING': case 'RUNNING': case 'QUEUED': return 'run'
    case 'PROPOSED': case 'DELIVERED': case 'SENT': case 'PENDING': case 'NEW': case 'OPEN': case 'INVITED': case 'REQUIRES_APPROVAL': case 'REQUIRES_CONFIRMATION': case 'DRAFT': return 'wait'
    case 'DEGRADED': case 'AT_RISK': case 'OVERDUE': return 'warn'
    case 'ERROR': case 'FAILED': case 'REJECTED': case 'AUTORESPONDED': case 'DECLINED': case 'VOIDED': case 'BLOCKED': return 'crit'
    case 'DISCONNECTED': case 'INACTIVE': case 'CANCELLED': case 'SKIPPED': return 'off'
    default: return 'wait'
  }
}
const KIND_TONE: Record<StatusKind, Tone | 'run' | 'wait'> = { ok: 'ok', run: 'run', wait: 'wait', warn: 'warn', crit: 'crit', off: 'neutral' }
/** Nome em português de cada estado cru que a API devolve. O que não estiver aqui aparece como veio. */
export const STATUS_PT: Record<string, string> = {
  CONNECTED: 'ok', DEGRADED: 'degradado', ERROR: 'erro', DISCONNECTED: 'desligado', SYNCING: 'sincronizando',
  ACTIVE: 'ativo', INACTIVE: 'inativo', NEW: 'novo', PENDING: 'pendente', AT_RISK: 'em risco', COMPLETED: 'concluído',
  open: 'aberto', completed: 'concluído', paid: 'paga', overdue: 'vencida', sent: 'enviada', draft: 'rascunho',
  PROPOSED: 'esperando você', APPROVED: 'aprovada', RUNNING: 'executando', QUEUED: 'na fila', DONE: 'feita', FAILED: 'falhou', REJECTED: 'rejeitada', BLOCKED: 'bloqueada', SKIPPED: 'pulado',
}
export function Status({ s, label, kind }: { s?: string | null; label?: ReactNode; kind?: StatusKind }) {
  const k = kind || statusKind(s)
  return <Chip tone={KIND_TONE[k]} glyph={STATUS_GLYPH[k]}>{label ?? (STATUS_PT[s || ''] ?? STATUS_PT[(s || '').toUpperCase()] ?? (s || '').toLowerCase())}</Chip>
}
export const LEVEL_GLYPH: Record<Level, string> = { CRITICAL: '✕', HIGH: '▲', MEDIUM: '●', LOW: '○' }

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

export function Kpi({ label, value, tone, foot, onClick, lead, sm }: { label: string; value: ReactNode; tone?: 'crit' | 'warn' | 'ok'; foot?: ReactNode; onClick?: () => void; lead?: boolean; sm?: boolean }) {
  return <div className={`card kpi${onClick ? ' link' : ''}${lead ? ' lead' : ''}${sm ? ' sm' : ''}${lead && tone ? ' ' + tone : ''}`} onClick={onClick} role={onClick ? 'button' : undefined} tabIndex={onClick ? 0 : undefined}
    onKeyDown={e => { if (onClick && (e.key === 'Enter' || e.key === ' ')) onClick() }}>
    <div className="lbl">{label}</div>
    <div className={`val ${tone || ''}`}><Num v={value} /></div>
    {foot && <div className="foot">{foot}</div>}
  </div>
}

const BANNER_GLYPH = { crit: '✕', warn: '▲', ok: '✓', info: '●' } as const
export function Banner({ tone, children }: { tone: 'crit' | 'warn' | 'ok' | 'info'; children: ReactNode }) {
  return <div className={`banner ${tone}`} role={tone === 'crit' ? 'alert' : 'status'}><span className="bi" aria-hidden="true">{BANNER_GLYPH[tone]}</span><div className="grow">{children}</div></div>
}

/** Cabeçalho de página: título quieto, a ação principal à direita, e a explicação (nível 4) atrás do "?".
 *  A pessoa que já sabe não lê o mesmo parágrafo toda vez; quem não sabe clica. */
export function PageHeader({ title, help, children, eyebrow }: { title: ReactNode; help?: ReactNode; children?: ReactNode; eyebrow?: ReactNode }) {
  const [open, setOpen] = useState(false)
  return <div className="page-h">
    <div className="grow">{eyebrow && <div className="small muted cond">{eyebrow}</div>}
      <h1 className="h1">{title}{help && <button type="button" className={`help${open ? ' on' : ''}`} aria-label="O que é esta tela" aria-expanded={open} title="O que é esta tela" onClick={() => setOpen(o => !o)}>?</button>}</h1>
      {help && open && <div className="sub small">{help}</div>}</div>
    {children && <div className="row wrap">{children}</div>}
  </div>
}

/** Barra fina no topo enquanto algo roda em segundo plano (sincronia, triagem, geração). */
export function Progress({ on }: { on: boolean }) {
  return on ? <div className="progress" role="progressbar" aria-label="em andamento" /> : null
}

export function Ext({ href, children }: { href?: string | null; children: ReactNode }) {
  if (!href) return <span className="muted">{children}</span>
  return <a href={href} target="_blank" rel="noopener noreferrer">{children} ↗</a>
}


/** Nome legível de cada sistema, para o link ficar ao lado do SEU item — nunca solto no topo. */
export const SYS_NAME: Record<string, string> = { asana: 'Asana', docusign: 'DocuSign', gmail: 'Gmail', quickbooks: 'QuickBooks', qbo: 'QuickBooks', brain: 'Cérebro', kommo: 'Kommo' }
export function SysLink({ links, one }: { links?: { system: string; external_id: string; deep_link: string | null }[] | null; one?: boolean }) {
  const ls = (links || []).filter(l => l.deep_link)
  if (ls.length === 0) return null
  return <span className="syslinks">{(one ? ls.slice(0, 1) : ls).map(l => <a key={l.system + l.external_id} className={`syslink ${l.system}`} href={l.deep_link!} target="_blank" rel="noopener noreferrer" title={`Abrir no ${SYS_NAME[l.system] || l.system}`}>{SYS_NAME[l.system] || l.system} ↗</a>)}</span>
}

/** Fita de números de contexto (nível 2): nome à esquerda, valor à direita. */
export function Strip({ items }: { items: { label: string; value: ReactNode; tone?: 'crit' | 'warn' | 'ok'; onClick?: () => void; title?: string }[] }) {
  return <div className="strip">{items.map(i => <div key={i.label} className={`it${i.onClick ? ' link' : ''}`} onClick={i.onClick} role={i.onClick ? 'button' : undefined} tabIndex={i.onClick ? 0 : undefined} title={i.title}
    onKeyDown={e => { if (i.onClick && (e.key === 'Enter' || e.key === ' ')) i.onClick() }}><span className="lbl">{i.label}</span><span className={`val ${i.tone || ''}`}><Num v={i.value} /></span></div>)}</div>
}

/** Conta até o número em ~400 ms (ease-out). Só para inteiros; qualquer outra coisa passa direto. */
export function Num({ v }: { v: ReactNode }) {
  const alvo = typeof v === 'number' && Number.isInteger(v) ? v : null
  const [n, setN] = useState(alvo ?? 0)
  const raf = useRef(0)
  useEffect(() => {
    if (alvo === null) return
    const reduz = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduz || alvo === 0) { setN(alvo); return }
    const de = n, t0 = performance.now(), dur = 400
    const tick = (t: number) => { const k = Math.min(1, (t - t0) / dur); const e = 1 - Math.pow(1 - k, 3); setN(Math.round(de + (alvo - de) * e)); if (k < 1) raf.current = requestAnimationFrame(tick) }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [alvo]) // eslint-disable-line react-hooks/exhaustive-deps
  return <>{alvo === null ? v : n}</>
}
