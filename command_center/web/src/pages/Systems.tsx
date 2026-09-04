/* Abas por sistema: o que cada um mostra por dentro, com dado espelhado das
 * fontes reais e link "abrir na fonte". Asana e DocuSign não permitem ser
 * embutidos em iframe (X-Frame-Options), então a visão é reconstruída aqui
 * a partir do espelho — e cada item leva para o original com um clique. */
import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useGet } from '../api/hooks'
import type { Client, Email, GmailLabel, GmailMessage, Integration, Task, Waiver } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Ext, Loading, Section, Spinner, WAIVER_LABEL, statusTone } from '../components/ui'
import { daysUntil, fmtDate, fmtDateTime, safeJson } from '../components/fmt'
import { useToast } from '../components/Toast'

const ORDEM_SECOES = ['TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY', 'RACES', 'Finished Services']
const ASANA_PROJ = 'https://app.asana.com/0/1205450093098920/board'

function useTab<T extends string>(key: string, def: T): [T, (t: T) => void] {
  const [sp, setSp] = useSearchParams()
  const v = (sp.get(key) as T) || def
  return [v, (t: T) => { const n = new URLSearchParams(sp); n.set(key, t); setSp(n, { replace: true }) }]
}

function SubTabs<T extends string>({ tabs, value, onChange }: { tabs: [T, string][]; value: T; onChange: (t: T) => void }) {
  return <div className="tabs">{tabs.map(([k, l]) => <button key={k} className={value === k ? 'on' : ''} onClick={() => onChange(k)}>{l}</button>)}</div>
}

function IntHeader({ system, title, desc, openHref, openLabel }: { system: string; title: string; desc: string; openHref: string; openLabel: string }) {
  const { data } = useGet<Integration[]>('/integrations', 60000)
  const i = data?.find(x => x.system === system)
  return <div className="page-h"><div><div className="row wrap"><h1 className="h1">{title}</h1>{i && <Chip tone={statusTone(i.status)} dot>{i.status}</Chip>}</div><div className="sub small">{desc}</div></div>
    <a className="btn" href={openHref} target="_blank" rel="noopener noreferrer">{openLabel} ↗</a></div>
}

// ------------------------------------------------------------------ Asana
function taskTone(t: Task) {
  if (t.status === 'completed') return 'done'
  if ((t.section || '').toUpperCase() === 'RACES') return 'race'
  const d = daysUntil(t.due_on); return d !== null && d < 0 ? 'late' : ''
}
function TaskLink({ t }: { t: Task }) {
  const l = t.links?.find(x => x.system === 'asana')?.deep_link
  return l ? <Ext href={l}>Asana</Ext> : null
}

function Calendario({ tasks, onOpen }: { tasks: Task[]; onOpen: (t: Task) => void }) {
  const [sp, setSp] = useSearchParams()
  const hoje = new Date()
  const ym = sp.get('m') || `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, '0')}`
  const [y, m] = ym.split('-').map(Number)
  const first = new Date(y, m - 1, 1); const start = new Date(first); start.setDate(1 - ((first.getDay() + 6) % 7))   // semana começa segunda
  const days = Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d })
  const byDay = useMemo(() => { const mp = new Map<string, Task[]>(); for (const t of tasks) if (t.due_on) mp.set(t.due_on, [...(mp.get(t.due_on) || []), t]); return mp }, [tasks])
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  const go = (delta: number) => { const d = new Date(y, m - 1 + delta, 1); const n = new URLSearchParams(sp); n.set('m', `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`); setSp(n, { replace: true }) }
  const todayIso = iso(hoje)
  return <div className="card"><div className="card-h"><button className="btn sm" onClick={() => go(-1)}>‹</button><h2 className="h1" style={{ fontSize: 20 }}>{first.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })}</h2><button className="btn sm" onClick={() => go(1)}>›</button><div className="grow" /><button className="btn ghost sm" onClick={() => { const n = new URLSearchParams(sp); n.delete('m'); setSp(n, { replace: true }) }}>hoje</button></div>
    <div className="cal">{['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'].map(d => <div key={d} className="dow">{d}</div>)}
      {days.map(d => { const k = iso(d); const ts = byDay.get(k) || []; return <div key={k} className={`day${d.getMonth() !== m - 1 ? ' out' : ''}${k === todayIso ? ' today' : ''}`}>
        <span className="n">{d.getDate()}</span>
        {ts.slice(0, 4).map(t => <div key={t.id} className={`ev ${taskTone(t)}`} title={`${t.title}${t.client_name ? ' · ' + t.client_name : ''}`} onClick={() => onOpen(t)}>{t.title}</div>)}
        {ts.length > 4 && <span className="more">+{ts.length - 4}</span>}
      </div> })}</div></div>
}

function Quadro({ tasks, onOpen }: { tasks: Task[]; onOpen: (t: Task) => void }) {
  const cols = useMemo(() => { const mp = new Map<string, Task[]>(); for (const t of tasks) { const k = t.section || '—'; mp.set(k, [...(mp.get(k) || []), t]) }
    return [...mp.entries()].sort((a, b) => { const ia = ORDEM_SECOES.indexOf(a[0]), ib = ORDEM_SECOES.indexOf(b[0]); return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) }) }, [tasks])
  if (cols.length === 0) return <div className="card"><Empty title="Quadro vazio">Nenhuma tarefa espelhada. Sincronize no Dashboard.</Empty></div>
  return <div className="board">{cols.map(([sec, ts]) => <div className="col" key={sec}><div className="ch">{sec}<span className="count">{ts.length}</span></div><div className="cards">
    {ts.map(t => <div key={t.id} className={`tcard${t.status === 'completed' ? ' done' : ''}`} onClick={() => onOpen(t)}>
      <div className="t">{t.title}</div>
      <div className="m">{t.due_on && <span className="mono">{fmtDate(t.due_on)}</span>}{t.client_name && <span>{t.client_name}</span>}{t.subtasks_total ? <span>{t.subtasks_done ?? '?'}/{t.subtasks_total}</span> : null}</div>
    </div>)}</div></div>)}</div>
}

interface TaskDetail {
  connected: boolean; reason?: string; gid?: string
  task?: { notas?: string | null; link?: string | null; campos?: Record<string, string> | null; responsavel?: string | null; secao?: string | null
    criada_em?: string; modificada_em?: string; subtarefas_lista?: { gid: string; nome: string; concluida: boolean; vence_em: string | null }[] }
  comments?: { quando: string; quem: string | null; texto: string | null }[]
  attachments?: { gid: string; nome: string | null; origem: string | null; quando: string | null; download: string | null }[]
}
function TaskModal({ t, onClose }: { t: Task; onClose: () => void }) {
  const nav = useNavigate()
  const det = useGet<TaskDetail>(`/tasks/${t.id}/detail`)
  const fields = (det.data?.task?.campos as Record<string, string> | undefined) || (safeJson(t.fields) as Record<string, string> | null)
  const subs = det.data?.task?.subtarefas_lista || []
  return <div className="modal-scrim" onMouseDown={onClose}><div className="modal" style={{ maxWidth: 860 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label="Fechar">✕</button>
    <div><div className="small muted cond">{t.project} · {t.section}</div><h2 className="h1" style={{ fontSize: 22 }}>{t.title}</h2></div>
    <div className="grid g2">
      <dl className="dl"><dt>Vence</dt><dd className="mono">{fmtDate(t.due_on)}</dd><dt>Status</dt><dd><Chip tone={statusTone(t.status === 'open' ? 'PENDING' : 'COMPLETED')}>{t.status}</Chip></dd>
        <dt>Responsável</dt><dd>{t.assignee || '—'}</dd>
        <dt>Cliente</dt><dd>{t.client_id ? <a onClick={() => { onClose(); nav(`/clients?open=${t.client_id}`) }} style={{ cursor: 'pointer' }}>{t.client_name || 'abrir'}</a> : <span className="muted">não vinculado</span>}</dd></dl>
      <dl className="dl">{fields && Object.entries(fields).map(([k, v]) => <><dt key={k + 'k'}>{k}</dt><dd key={k + 'v'}>{v}</dd></>)}
        <dt>Espelhado</dt><dd className="mono small">{fmtDateTime(t.synced_at)}</dd></dl>
    </div>
    {det.loading && !det.data && <Loading rows={4} />}
    {det.error && <ErrorState error={det.error} retry={det.reload} />}
    {det.data && !det.data.connected && <Banner tone="warn">Sem Asana ao vivo agora: {det.data.reason}. Mostrando só o espelho.</Banner>}
    {det.data?.connected && <>
      <Section title="Descrição">{det.data.task?.notas ? <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--font)', margin: 0, fontSize: 13.5 }}>{det.data.task.notas}</pre> : <span className="muted small">sem descrição</span>}</Section>
      <div className="grid g2">
        <Section title="Subtarefas" count={subs.length} tight>{subs.length === 0 ? <Empty>Nenhuma.</Empty> : <div>{subs.map(s => <div key={s.gid} className="att"><div className={`lv ${s.concluida ? 'LOW' : 'MEDIUM'}`} /><div className="grow" style={{ textDecoration: s.concluida ? 'line-through' : undefined, color: s.concluida ? 'var(--muted)' : undefined }}>{s.concluida ? '✓ ' : '○ '}{s.nome}{s.vence_em && <span className="small muted mono"> · {fmtDate(s.vence_em)}</span>}</div></div>)}</div>}</Section>
        <Section title="Anexos" count={det.data.attachments?.length} tight>{!det.data.attachments?.length ? <Empty>Nenhum.</Empty> : <div>{det.data.attachments.map(a => <div key={a.gid} className="att"><div className="lv LOW" /><div className="grow">{a.download ? <a href={a.download} target="_blank" rel="noopener noreferrer">{a.nome} ↗</a> : a.nome}<div className="small muted">{a.origem} · {fmtDateTime(a.quando)}</div></div></div>)}</div>}</Section>
      </div>
      <Section title="Comentários" count={det.data.comments?.length} tight>{!det.data.comments?.length ? <Empty>Nenhum comentário.</Empty> : <div>{det.data.comments.map((c, i) => <div key={i} className="att"><div className="lv LOW" /><div className="grow"><div className="small muted"><b>{c.quem || '?'}</b> · {fmtDateTime(c.quando)}</div><div style={{ whiteSpace: 'pre-wrap' }}>{c.texto}</div></div></div>)}</div>}</Section>
    </>}
    <div className="row"><TaskLink t={t} /></div>
  </div></div>
}

export function AsanaPage() {
  const [tab, setTab] = useTab<'cal' | 'board' | 'list'>('v', 'cal')
  const [status, setStatus] = useTab<'all' | 'open' | 'completed'>('s', 'all')
  const { data, error, loading, reload } = useGet<Task[]>('/tasks?status=all', 120000)
  const [open, setOpen] = useState<Task | null>(null)
  const tasks = (data || []).filter(t => status === 'all' || t.status === status)
  return <>
    <IntHeader system="asana" title="Asana" desc="Quadro U-RACE espelhado: TUESDAY a SUNDAY é a agenda, RACES são corridas, Finished Services é o histórico. “Matt tasks” não é espelhada (decisão do dono)." openHref={ASANA_PROJ} openLabel="Abrir no Asana" />
    <div className="row wrap"><SubTabs tabs={[['cal', 'Calendário'], ['board', 'Quadro'], ['list', 'Lista']]} value={tab} onChange={setTab} /><div className="grow" />
      <select className="input" style={{ width: 160 }} value={status} onChange={e => setStatus(e.target.value as 'all')}><option value="all">Abertas e concluídas</option><option value="open">Só abertas</option><option value="completed">Só concluídas</option></select><button className="btn" onClick={reload}>↻</button></div>
    {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading rows={6} /> : <>
      {tab === 'cal' && <Calendario tasks={tasks} onOpen={setOpen} />}
      {tab === 'board' && <Quadro tasks={tasks} onOpen={setOpen} />}
      {tab === 'list' && <Section title="Tarefas" count={tasks.length} tight>{tasks.length === 0 ? <Empty>Nada com esse filtro.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Data</th><th>Tarefa</th><th>Coluna</th><th>Cliente</th><th>Responsável</th><th>Subtarefas</th><th>Status</th><th></th></tr></thead><tbody>
          {tasks.map(t => <tr key={t.id} className="click" onClick={() => setOpen(t)}><td className="mono nowrap">{fmtDate(t.due_on)}</td><td>{t.title}</td><td>{t.section}</td><td>{t.client_name || <span className="muted">—</span>}</td><td className="small">{t.assignee}</td><td className="mono">{t.subtasks_total ? `${t.subtasks_done ?? '?'}/${t.subtasks_total}` : '—'}</td><td><Chip tone={statusTone(t.status === 'open' ? 'PENDING' : 'COMPLETED')}>{t.status}</Chip></td><td onClick={e => e.stopPropagation()}><TaskLink t={t} /></td></tr>)}
        </tbody></table></div>}</Section>}
    </>}
    {open && <TaskModal t={open} onClose={() => setOpen(null)} />}
  </>
}

// --------------------------------------------------------------- DocuSign
interface Template { templateId?: string; id?: string; nome?: string; name?: string; papeis?: string[]; roles?: string[] }
function LinkClient({ w, onDone }: { w: Waiver; onDone: () => void }) {
  const toast = useToast()
  const [q, setQ] = useState('')
  const clients = useGet<Client[]>(q.length >= 2 ? '/clients' + qs({ q }) : null)
  return <div className="row wrap" onClick={e => e.stopPropagation()}>
    <input className="input" style={{ width: 200 }} placeholder="vincular a… (piloto/nome)" value={q} onChange={e => setQ(e.target.value)} />
    {(clients.data || []).slice(0, 5).map(c => <button key={c.id} className="btn sm" onClick={async () => { try { await api.post(`/waivers/${w.id}/link`, { client_id: c.id }); toast('Vinculado.', 'ok'); setQ(''); onDone() } catch (ex) { toast((ex as ApiError).message, 'crit') } }}>{c.pilot_name || c.name}</button>)}
  </div>
}
export function DocuSignPage() {
  const nav = useNavigate()
  const { can } = useAuth()
  const toast = useToast()
  const [tab, setTab] = useTab<'env' | 'signed' | 'tpl' | 'lixo'>('v', 'env')
  const [st, setSt] = useTab<string>('s', 'all')
  const env = useGet<Waiver[]>(tab === 'lixo' ? '/waivers?hidden=1' : '/waivers', 120000)
  const tpl = useGet<{ connected: boolean; reason?: string; templates: Template[] | Record<string, unknown> }>(tab === 'tpl' ? '/docusign/templates' : null)
  const [busy, setBusy] = useState<number | null>(null)
  const rows = (env.data || []).filter(w => tab === 'signed' ? (w.status === 'completed' && (w.template === 'parental' || w.template === 'adult')) : (st === 'all' || w.status === st))
  const counts = (env.data || []).reduce<Record<string, number>>((a, w) => { a[w.status || '?'] = (a[w.status || '?'] || 0) + 1; return a }, {})
  const tplList: Template[] = Array.isArray(tpl.data?.templates) ? tpl.data!.templates as Template[] : ((tpl.data?.templates as Record<string, unknown>)?.templates as Template[]) || []
  async function act(w: Waiver, kind: 'trash' | 'restore' | 'resend', body?: unknown) {
    setBusy(w.id)
    try { const r = await api.post<{ note?: string; voided?: boolean; email_corrigido?: string }>(`/waivers/${w.id}/${kind}`, body || {})
      toast(kind === 'trash' ? (r.voided ? 'Envelope anulado no DocuSign e removido do painel.' : r.note || 'Removido do painel.') : kind === 'restore' ? 'Restaurado.' : r.email_corrigido ? `E-mail corrigido para ${r.email_corrigido} e reenviado.` : 'Reenviado ao signatário.', 'ok'); env.reload() }
    catch (ex) { toast((ex as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  function trash(w: Waiver) {
    const aberto = ['sent', 'delivered', 'autoresponded'].includes(w.status || '')
    const msg = aberto ? `Anular o envelope de ${w.signer_name} no DocuSign e tirar do painel?\n\nO signatário não consegue mais assinar. Motivo (opcional):` : `Tirar a waiver de ${w.signer_name} do painel?\n\nEnvelope assinado é registro legal e continua no DocuSign. Motivo (opcional):`
    const reason = window.prompt(msg); if (reason === null) return
    act(w, 'trash', { reason })
  }
  function resend(w: Waiver) {
    const novo = window.prompt(`Reenviar a waiver para ${w.signer_name}.\n\nE-mail do signatário (edite se estava errado):`, w.signer_email || '')
    if (novo === null) return
    act(w, 'resend', { email: novo.trim().toLowerCase() !== (w.signer_email || '').toLowerCase() ? novo.trim() : undefined })
  }
  return <>
    <IntHeader system="docusign" title="DocuSign" desc="Envelopes de waiver da conta de produção (na4). Delivered não é assinada; autoresponded é e-mail devolvido. Cada envelope é ligado ao cliente/piloto pelo e-mail, pelo nome do menor ou pelo signatário." openHref="https://app.docusign.com/home" openLabel="Abrir no DocuSign" />
    <div className="row wrap"><SubTabs tabs={[['env', 'Envelopes'], ['signed', `Assinadas (${(env.data || []).filter(w => w.status === 'completed' && (w.template === 'parental' || w.template === 'adult')).length})`], ['tpl', 'Modelos'], ['lixo', 'Lixeira']]} value={tab} onChange={setTab} /><div className="grow" />
      {tab !== 'tpl' && tab !== 'signed' && <select className="input" style={{ width: 220 }} value={st} onChange={e => setSt(e.target.value)}><option value="all">Todos ({env.data?.length ?? 0})</option>{Object.entries(counts).map(([k, n]) => <option key={k} value={k}>{WAIVER_LABEL[k] || k} ({n})</option>)}</select>}
      <button className="btn" onClick={() => { env.reload(); tpl.reload() }}>↻</button></div>
    {tab !== 'tpl' && <Section title={tab === 'lixo' ? 'Na lixeira do painel' : tab === 'signed' ? 'Waivers assinadas (parental e adult)' : 'Envelopes'} count={rows.length} tight>
      {env.error && !env.data ? <ErrorState error={env.error} retry={env.reload} /> : env.loading && !env.data ? <Loading /> : rows.length === 0 ? <Empty>{tab === 'lixo' ? 'Nada na lixeira.' : 'Nenhum envelope espelhado com esse filtro.'}</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Signatário</th><th>Cliente / piloto</th><th>Modelo</th><th>Status</th><th>Enviada</th><th>Assinada</th><th>Expira</th><th></th></tr></thead><tbody>
          {rows.map(w => { const aberto = ['sent', 'delivered', 'autoresponded'].includes(w.status || ''); return <tr key={w.id}>
            <td>{w.signer_name}<div className="small muted">{w.signer_email}</div>{w.minor_name && <div className="small">menor: <b>{w.minor_name}</b></div>}</td>
            <td>{w.client_id ? <><a onClick={() => nav(`/clients/${w.client_id}`)} style={{ cursor: 'pointer' }}>{w.client_pilot || w.client_name}</a>{w.client_pilot && <div className="small muted">{w.client_name}</div>}{w.link_reason && <div className="small muted" title={w.link_reason}>{w.link_by === 'human' ? 'à mão' : 'auto'}: {w.link_reason.slice(0, 48)}</div>}</> : <><span className="muted">não vinculado</span>{can('OPERATOR') && <LinkClient w={w} onDone={env.reload} />}</>}</td>
            <td>{w.template}</td>
            <td><Chip tone={statusTone(w.status)}>{WAIVER_LABEL[w.status || ''] || w.status}</Chip></td>
            <td className="mono">{fmtDate(w.sent_at)}</td><td className="mono">{fmtDate(w.completed_at)}</td><td className="mono">{fmtDate(w.expires_at)}</td>
            <td className="nowrap">
              {w.status === 'completed' && <a className={tab === 'signed' ? 'btn sm' : 'ic'} href={`/ops/api/waivers/${w.id}/download`} title="Baixar PDF assinado" aria-label="Baixar">⬇{tab === 'signed' ? ' PDF' : ''}</a>}
              {tab === 'signed' && w.client_id && <button className="btn sm" onClick={() => nav(`/clients?open=${w.client_id}`)} title="Abrir o card do cliente">→ cliente</button>}
              {aberto && can('OPERATOR') && tab !== 'lixo' && <button className="ic" disabled={busy === w.id} title={w.status === 'autoresponded' ? 'Corrigir e-mail e reenviar' : 'Reenviar'} aria-label="Reenviar" onClick={() => resend(w)}>↻</button>}
              {tab !== 'lixo' && can('OPERATOR') && <button className="ic danger" disabled={busy === w.id} title={aberto ? 'Anular no DocuSign e tirar do painel' : 'Tirar do painel (assinada fica no DocuSign)'} aria-label="Lixeira" onClick={() => trash(w)}>🗑</button>}
              {tab === 'lixo' && can('OPERATOR') && <button className="btn sm" disabled={busy === w.id} onClick={() => act(w, 'restore')}>Restaurar</button>}
              {w.links?.map(l => <Ext key={l.external_id} href={l.deep_link}>abrir</Ext>)}
            </td></tr> })}
        </tbody></table></div>}</Section>}
    {tab === 'tpl' && <Section title="Modelos da conta" count={tplList.length}>
      {tpl.loading && !tpl.data ? <Loading /> : tpl.error ? <ErrorState error={tpl.error} retry={tpl.reload} /> : tpl.data && !tpl.data.connected ? <Banner tone="warn">DocuSign não conectado neste servidor: {tpl.data.reason}</Banner> :
        tplList.length === 0 ? <Empty>A conta não devolveu modelos.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Modelo</th><th>ID</th><th>Papéis</th></tr></thead><tbody>
          {tplList.map((t, i) => <tr key={i}><td>{t.nome || t.name}</td><td className="mono small">{t.templateId || t.id}</td><td className="small">{(t.papeis || t.roles || []).join(', ')}</td></tr>)}
        </tbody></table></div>}
      <div className="small muted" style={{ marginTop: 10 }}>Envio de waiver pela IA passa por aprovação (política). Só os dois modelos de PARAMETROS servem para a automação.</div>
    </Section>}
  </>
}

// ------------------------------------------------------------------ Gmail
type Box = 'urace' | 'support'
export function GmailPage() {
  const nav = useNavigate()
  const { can } = useAuth()
  const toast = useToast()
  const [box, setBox] = useTab<Box>('v', 'urace')
  const [sel, setSel] = useTab<string>('l', 'INBOX')          // INBOX | SEM_SUGESTAO | <marcador>
  const [openId, setOpenId] = useTab<string>('o', '')
  const labels = useGet<{ connected: boolean; reason?: string; labels: GmailLabel[] }>(`/gmail/labels?mailbox=${box}`, 120000)
  const emails = useGet<Email[]>(`/emails?mailbox=${box}`, 60000)
  const thread = useGet<{ connected: boolean; reason?: string; messages: GmailMessage[] }>(openId ? `/emails/${openId}/thread` : null)
  const [busy, setBusy] = useState<number | null>(null)
  const [classifying, setClassifying] = useState(false)
  const [moveTo, setMoveTo] = useState('')
  const inbox = (emails.data || []).filter(e => e.is_inbox !== 0)
  const rows = sel === 'INBOX' ? inbox : sel === 'SEM_SUGESTAO' ? inbox.filter(e => !e.suggested_label) : inbox.filter(e => (JSON.parse(e.labels || '[]') as string[]).includes(sel) || e.suggested_label === sel)
  const cur = (emails.data || []).find(e => String(e.id) === openId) || null
  const userLabels = (labels.data?.labels || []).filter(l => l.type !== 'system')

  async function move(e: Email, label: string) {
    if (!label) return
    if (!window.confirm(`Mover para "${label}"?\n\nAplica o marcador e tira da caixa de entrada.`)) return
    setBusy(e.id)
    try { await api.post(`/emails/${e.id}/move`, { label }); toast(`Movido para ${label}.`, 'ok'); if (String(e.id) === openId) setOpenId(''); emails.reload(); labels.reload() }
    catch (ex) { toast((ex as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function classify() {
    setClassifying(true)
    try {
      const r = await api.post<{ started: boolean }>('/gmail/classify', { mailbox: box })
      toast(r.started ? 'A IA está classificando. Leva de 1 a 3 minutos.' : 'Já há uma classificação rodando.')
      for (let i = 0; i < 120; i++) {
        await new Promise(res => setTimeout(res, 4000))
        const st = await api.get<{ running: boolean; result: { classificados?: number; sem_marcador?: number; erro?: string | null } | null }>('/gmail/classify')
        if (!st.running) { const r2 = st.result || {}; toast(r2.erro ? `Classificação falhou: ${r2.erro}` : `IA classificou ${r2.classificados ?? 0}; ${r2.sem_marcador ?? 0} sem marcador claro.`, r2.erro ? 'crit' : 'ok'); break }
      }
      emails.reload()
    } catch (ex) { toast((ex as ApiError).message, 'crit') } finally { setClassifying(false) }
  }
  const semSug = inbox.filter(e => !e.suggested_label).length
  return <>
    <IntHeader system="gmail" title="Gmail" desc="Caixa de entrada por dentro. A IA sugere o marcador de cada thread; o botão “Mover” aplica o marcador e tira da inbox (decisão de 04/09). A IA nunca envia e-mail." openHref={`https://mail.google.com/mail/u/${box === 'urace' ? 0 : 1}/`} openLabel="Abrir o Gmail" />
    <div className="row wrap"><SubTabs tabs={[['urace', 'urace@'], ['support', 'support@']]} value={box} onChange={b => { setBox(b); setSel('INBOX'); setOpenId('') }} /><div className="grow" />
      {can('OPERATOR') && <button className="btn primary" disabled={classifying || semSug === 0} onClick={classify} title="Manda para o agente as threads ainda sem sugestão">{classifying ? <Spinner /> : '✦'} Classificar com a IA{semSug > 0 && ` (${semSug})`}</button>}
      <button className="btn" onClick={() => { emails.reload(); labels.reload() }}>↻</button></div>
    {labels.data && !labels.data.connected && <Banner tone="warn">Gmail não conectado neste servidor: {labels.data.reason}. A lista abaixo é só o espelho.</Banner>}
    <div className="mail">
      <div className="labels">
        <div className={`lb${sel === 'INBOX' ? ' on' : ''}`} onClick={() => setSel('INBOX')}>Caixa de entrada<span className="c">{inbox.length}</span></div>
        <div className={`lb${sel === 'SEM_SUGESTAO' ? ' on' : ''}`} onClick={() => setSel('SEM_SUGESTAO')}>Sem sugestão<span className="c">{semSug}</span></div>
        <div className="grp">Marcadores</div>
        {labels.loading && !labels.data && <Loading rows={6} />}
        {userLabels.map(l => <div key={l.name} className={`lb${sel === l.name ? ' on' : ''}`} onClick={() => setSel(l.name)} title={l.name}><span className="truncate">{l.name}</span><span className="c">{(l.inbox_count || 0) + inbox.filter(e => e.suggested_label === l.name && !(JSON.parse(e.labels || '[]') as string[]).includes(l.name)).length || ''}</span></div>)}
      </div>
      <div className="list">
        {emails.error && !emails.data ? <ErrorState error={emails.error} retry={emails.reload} /> : emails.loading && !emails.data ? <Loading rows={8} /> : rows.length === 0 ? <Empty title="Vazio">{sel === 'INBOX' ? 'Nenhuma thread na inbox espelhada. Sincronize no Dashboard.' : 'Nada aqui.'}</Empty> :
          rows.map(e => <div key={e.id} className={`item${String(e.id) === openId ? ' on' : ''}`} onClick={() => setOpenId(String(e.id))}>
            <span className="from">{(e.sender || '').replace(/<.*>/, '').trim() || e.sender}</span><span className="when">{fmtDateTime(e.last_at)}</span>
            <span className="subj">{e.subject || '(sem assunto)'}{e.messages && e.messages > 1 ? <span className="muted"> ({e.messages})</span> : null}</span>
            <span className="snip">{e.snippet}</span>
            <span className="sug" onClick={ev => ev.stopPropagation()}>
              {e.client_id && <Chip tone="accent">{e.client_name}</Chip>}
              {e.suggested_label ? <><Chip tone={e.suggested_by === 'ia' ? 'info' : 'neutral'}>{e.suggested_by === 'ia' ? '✦ ' : ''}{e.suggested_label}</Chip>
                {can('OPERATOR') && <button className="btn sm primary" disabled={busy === e.id} onClick={() => move(e, e.suggested_label!)}>{busy === e.id ? <Spinner /> : 'Mover'}</button>}</>
                : <span className="small muted">sem sugestão</span>}
            </span>
          </div>)}
      </div>
      <div className="read">
        {!cur ? <Empty title="Selecione uma thread">O corpo abre aqui, ao vivo do Gmail.</Empty> : <>
          <div className="toolbar">
            <select className="input" style={{ width: 240 }} value={moveTo || cur.suggested_label || ''} onChange={ev => setMoveTo(ev.target.value)} aria-label="Marcador de destino"><option value="">Marcador…</option>{userLabels.map(l => <option key={l.name} value={l.name}>{l.name}</option>)}</select>
            {can('OPERATOR') && <button className="btn primary sm" disabled={busy === cur.id || !(moveTo || cur.suggested_label)} onClick={() => move(cur, moveTo || cur.suggested_label!)}>Mover para o marcador</button>}
            {can('OPERATOR') && <button className="btn sm" onClick={async () => { await api.patch(`/emails/${cur.id}`, { handled: !cur.handled }); emails.reload() }}>{cur.handled ? '✓ tratado' : 'marcar tratado'}</button>}
            <span className="grow" />
            {cur.client_id && <a onClick={() => nav(`/clients/${cur.client_id}`)} style={{ cursor: 'pointer' }} className="small">cliente: {cur.client_name}</a>}
            {cur.links?.map(l => <Ext key={l.external_id} href={l.deep_link}>Gmail</Ext>)}
          </div>
          <div><div className="h1" style={{ fontSize: 20 }}>{cur.subject || '(sem assunto)'}</div>
            <div className="small muted">{cur.sender} · {fmtDateTime(cur.last_at)}{cur.suggested_label && <> · sugestão: <b>{cur.suggested_label}</b>{cur.suggested_reason && <> ({cur.suggested_reason})</>}</>}</div></div>
          {thread.loading && !thread.data ? <Loading rows={5} /> : thread.error ? <ErrorState error={thread.error} retry={thread.reload} /> : thread.data && !thread.data.connected ? <Banner tone="warn">Não deu para ler o corpo: {thread.data.reason}</Banner> :
            (thread.data?.messages || []).map(m => <div className="msg-b" key={m.message_id}>
              <div className="hd"><b>{m.de}</b><span>para {m.para}</span><span className="mono">{m.data}</span></div>
              <pre>{m.corpo || m.snippet}</pre>
              {m.anexos && m.anexos.length > 0 && <div className="small muted" style={{ marginTop: 6 }}>Anexos: {m.anexos.map(a => a.nome).join(', ')}</div>}
            </div>)}
        </>}
      </div>
    </div>
  </>
}

// ------------------------------------------------------------- QuickBooks
export function QuickBooksPage() {
  const { data } = useGet<Integration[]>('/integrations', 60000)
  const i = data?.find(x => x.system === 'quickbooks')
  const det = safeJson(i?.detail) as { nota?: string } | null
  return <>
    <IntHeader system="quickbooks" title="QuickBooks" desc="Faturamento, clientes e pagamentos. Em stand-by por decisão do dono até a Intuit liberar a produção do app (P-11)." openHref="https://qbo.intuit.com/" openLabel="Abrir o QuickBooks" />
    <Banner tone="info"><b>Nada é inventado aqui.</b> Enquanto a integração não está conectada, esta aba mostra só o estado real. {det?.nota && <>Nota do servidor: {det.nota}.</>}</Banner>
    <div className="grid g3">
      <div className="card kpi"><div className="lbl">Invoices em aberto</div><div className="val">—</div><div className="foot">aparece quando conectar</div></div>
      <div className="card kpi"><div className="lbl">Recebido no mês</div><div className="val">—</div><div className="foot">aparece quando conectar</div></div>
      <div className="card kpi"><div className="lbl">Clientes no QBO</div><div className="val">—</div><div className="foot">aparece quando conectar</div></div>
    </div>
    <Section title="O que entra quando conectar">
      <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
        <li><b>Invoices</b> por cliente, com saldo, vencimento e status, também no card do cliente (histórico de pagamento).</li>
        <li><b>Envio de invoice pela IA só depois de aprovação humana</b> no Command Center (decisão de 04/09).</li>
        <li><b>Recebimentos</b> e vencidas há mais de 30 dias em “Precisa de atenção”.</li>
      </ul>
    </Section>
  </>
}
