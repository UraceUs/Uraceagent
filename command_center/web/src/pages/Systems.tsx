/* Abas por sistema: o que cada um mostra por dentro, com dado espelhado das
 * fontes reais e link "abrir na fonte". Asana e DocuSign não permitem ser
 * embutidos em iframe (X-Frame-Options), então a visão é reconstruída aqui
 * a partir do espelho — e cada item leva para o original com um clique. */
import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useGet } from '../api/hooks'
import type { Email, Integration, Task, Waiver } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Ext, Loading, Section, WAIVER_LABEL, statusTone } from '../components/ui'
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

function TaskModal({ t, onClose }: { t: Task; onClose: () => void }) {
  const nav = useNavigate()
  const fields = safeJson(t.fields) as Record<string, string> | null
  return <div className="modal-scrim" onMouseDown={onClose}><div className="modal" style={{ maxWidth: 640 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label="Fechar">✕</button>
    <div><div className="small muted cond">{t.project} · {t.section}</div><h2 className="h1" style={{ fontSize: 22 }}>{t.title}</h2></div>
    <dl className="dl"><dt>Vence</dt><dd className="mono">{fmtDate(t.due_on)}</dd><dt>Status</dt><dd><Chip tone={statusTone(t.status === 'open' ? 'PENDING' : 'COMPLETED')}>{t.status}</Chip></dd>
      <dt>Responsável</dt><dd>{t.assignee || '—'}</dd><dt>Subtarefas</dt><dd className="mono">{t.subtasks_total ? `${t.subtasks_done ?? '?'}/${t.subtasks_total}` : '—'}</dd>
      <dt>Cliente</dt><dd>{t.client_id ? <a onClick={() => { onClose(); nav(`/clients/${t.client_id}`) }} style={{ cursor: 'pointer' }}>{t.client_name || 'abrir'}</a> : <span className="muted">não vinculado</span>}</dd>
      {fields && Object.entries(fields).map(([k, v]) => <><dt key={k + 'k'}>{k}</dt><dd key={k + 'v'}>{v}</dd></>)}
      <dt>Espelhado</dt><dd className="mono small">{fmtDateTime(t.synced_at)}</dd></dl>
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
export function DocuSignPage() {
  const nav = useNavigate()
  const [tab, setTab] = useTab<'env' | 'tpl'>('v', 'env')
  const [st, setSt] = useTab<string>('s', 'all')
  const env = useGet<Waiver[]>('/waivers', 120000)
  const tpl = useGet<{ connected: boolean; reason?: string; templates: Template[] | Record<string, unknown> }>(tab === 'tpl' ? '/docusign/templates' : null)
  const rows = (env.data || []).filter(w => st === 'all' || w.status === st)
  const counts = (env.data || []).reduce<Record<string, number>>((a, w) => { a[w.status || '?'] = (a[w.status || '?'] || 0) + 1; return a }, {})
  const tplList: Template[] = Array.isArray(tpl.data?.templates) ? tpl.data!.templates as Template[] : ((tpl.data?.templates as Record<string, unknown>)?.templates as Template[]) || []
  return <>
    <IntHeader system="docusign" title="DocuSign" desc="Envelopes de waiver da conta de produção (na4). Delivered não é assinada; autoresponded é e-mail devolvido." openHref="https://app.docusign.com/home" openLabel="Abrir no DocuSign" />
    <div className="row wrap"><SubTabs tabs={[['env', 'Envelopes'], ['tpl', 'Modelos']]} value={tab} onChange={setTab} /><div className="grow" />
      {tab === 'env' && <select className="input" style={{ width: 220 }} value={st} onChange={e => setSt(e.target.value)}><option value="all">Todos ({env.data?.length ?? 0})</option>{Object.entries(counts).map(([k, n]) => <option key={k} value={k}>{WAIVER_LABEL[k] || k} ({n})</option>)}</select>}
      <button className="btn" onClick={() => { env.reload(); tpl.reload() }}>↻</button></div>
    {tab === 'env' && <Section title="Envelopes" count={rows.length} tight>
      {env.error && !env.data ? <ErrorState error={env.error} retry={env.reload} /> : env.loading && !env.data ? <Loading /> : rows.length === 0 ? <Empty>Nenhum envelope espelhado com esse filtro.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Signatário</th><th>Cliente</th><th>Modelo</th><th>Status</th><th>Enviada</th><th>Assinada</th><th>Expira</th><th></th></tr></thead><tbody>
          {rows.map(w => <tr key={w.id} className={w.client_id ? 'click' : ''} onClick={() => w.client_id && nav(`/clients/${w.client_id}`)}>
            <td>{w.signer_name}<div className="small muted">{w.signer_email}</div></td><td>{w.client_name || <span className="muted">não vinculado</span>}</td><td>{w.template}</td>
            <td><Chip tone={statusTone(w.status)}>{WAIVER_LABEL[w.status || ''] || w.status}</Chip></td>
            <td className="mono">{fmtDate(w.sent_at)}</td><td className="mono">{fmtDate(w.completed_at)}</td><td className="mono">{fmtDate(w.expires_at)}</td>
            <td onClick={e => e.stopPropagation()}>{w.links?.map(l => <Ext key={l.external_id} href={l.deep_link}>abrir</Ext>)}</td></tr>)}
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
export function GmailPage() {
  const nav = useNavigate()
  const { can } = useAuth()
  const toast = useToast()
  const [box, setBox] = useTab<'all' | 'urace' | 'support'>('v', 'all')
  const [f, setF] = useTab<'all' | 'open' | 'client'>('f', 'all')
  const { data, error, loading, reload } = useGet<Email[]>('/emails' + qs({ mailbox: box === 'all' ? undefined : box }), 120000)
  const rows = (data || []).filter(e => f === 'all' || (f === 'open' && !e.handled) || (f === 'client' && e.client_id))
  async function toggle(e: Email) {
    try { await api.patch(`/emails/${e.id}`, { handled: !e.handled }); toast(e.handled ? 'Marcado como não tratado.' : 'Marcado como tratado.', 'ok'); reload() } catch (ex) { toast((ex as ApiError).message, 'crit') }
  }
  return <>
    <IntHeader system="gmail" title="Gmail" desc="Threads das caixas urace@ e support@ classificadas pela triagem. Marcar “tratado” é só aqui, no espelho; a IA nunca envia e-mail." openHref="https://mail.google.com/" openLabel="Abrir o Gmail" />
    <div className="row wrap"><SubTabs tabs={[['all', 'Todas as caixas'], ['urace', 'urace@'], ['support', 'support@']]} value={box} onChange={setBox} /><div className="grow" />
      <select className="input" style={{ width: 200 }} value={f} onChange={e => setF(e.target.value as 'all')}><option value="all">Todas</option><option value="open">Sem tratamento</option><option value="client">De cliente conhecido</option></select><button className="btn" onClick={reload}>↻</button></div>
    <Section title="Threads" count={rows.length} tight>
      {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> : rows.length === 0 ? <Empty>Nenhuma thread com esse filtro.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Quando</th><th>Caixa</th><th>Assunto</th><th>De</th><th>Cliente</th><th>Prioridade</th><th>Intenção</th><th>Tratado</th><th></th></tr></thead><tbody>
          {rows.map(e => <tr key={e.id}>
            <td className="mono nowrap">{fmtDateTime(e.last_at)}</td><td>{e.mailbox}@</td><td className="truncate" style={{ maxWidth: 320 }}>{e.subject}</td><td className="small truncate" style={{ maxWidth: 200 }}>{e.sender}</td>
            <td>{e.client_id ? <a onClick={() => nav(`/clients/${e.client_id}`)} style={{ cursor: 'pointer' }}>{e.client_name}</a> : <span className="muted">—</span>}</td>
            <td>{e.priority && <Chip tone={e.priority === 'CRITICAL' ? 'crit' : e.priority === 'HIGH' ? 'warn' : 'neutral'}>{e.priority}</Chip>}</td><td className="small">{e.intent}</td>
            <td>{can('OPERATOR') ? <button className={`btn sm${e.handled ? ' ghost' : ''}`} onClick={() => toggle(e)}>{e.handled ? '✓ tratado' : 'marcar tratado'}</button> : (e.handled ? '✓' : 'não')}</td>
            <td>{e.links?.map(l => <Ext key={l.external_id} href={l.deep_link}>Gmail</Ext>)}</td></tr>)}
        </tbody></table></div>}
    </Section>
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
