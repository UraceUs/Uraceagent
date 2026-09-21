/* Abas por sistema: o que cada um mostra por dentro, com dado espelhado das
 * fontes reais e link "abrir na fonte". Asana e DocuSign não permitem ser
 * embutidos em iframe (X-Frame-Options), então a visão é reconstruída aqui
 * a partir do espelho — e cada item leva para o original com um clique. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useGet } from '../api/hooks'
import type { Client, Email, GmailLabel, GmailMessage, Integration, Invoice, QboSummary, Task, Waiver } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Dots, Empty, ErrorState, Loading, PageHeader, Progress, Scrim, Section, Spinner, Status, SysLink, WAIVER_LABEL } from '../components/ui'
import { daysUntil, fmtDate, fmtDateTime, money, safeJson } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'
import { Mic, TextoComVoz } from '../components/Voz'

const ORDEM_SECOES = ['TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY', 'RACES', 'Finished Services']
const ASANA_PROJ = 'https://app.asana.com/0/1205450093098920/board'

/* Estado de aba na URL. Lê a URL AO VIVO na hora de escrever, não o valor do closure:
   um clique que troca caixa + filtro + thread chama três setters seguidos, e partindo
   do valor antigo cada um sobrescrevia o anterior — "clico em support@ e não acontece
   nada". Com BrowserRouter o replaceState é síncrono, então o segundo setter já vê o
   que o primeiro gravou. E quem muda várias chaves de uma vez usa `useTabs().setMany`,
   que grava tudo numa navegação só. */
function useTab<T extends string>(key: string, def: T): [T, (t: T) => void] {
  const [sp, setSp] = useSearchParams()
  const v = (sp.get(key) as T) || def
  return [v, (t: T) => { const n = new URLSearchParams(window.location.search); n.set(key, t); setSp(n, { replace: true }) }]
}

function useTabs() {
  const [, setSp] = useSearchParams()
  return {
    setMany: (mudancas: Record<string, string>) => {
      const n = new URLSearchParams(window.location.search)
      for (const [k, v] of Object.entries(mudancas)) { if (v) n.set(k, v); else n.delete(k) }
      setSp(n, { replace: true })
    },
  }
}

/** No celular o mês de 7 colunas não cabe de pé: a Lista abre por padrão e o
 *  calendário fica a um toque. Quem escolher a aba manda — a escolha vai para a URL. */
const telaPequena = () => typeof window !== 'undefined' && window.matchMedia('(max-width:700px)').matches

function SubTabs<T extends string>({ tabs, value, onChange }: { tabs: [T, string][]; value: T; onChange: (t: T) => void }) {
  return <div className="tabs">{tabs.map(([k, l]) => <button key={k} className={value === k ? 'on' : ''} onClick={() => onChange(k)}>{l}</button>)}</div>
}

function IntHeader({ system, title, desc, openHref, openLabel }: { system: string; title: string; desc: string; openHref: string; openLabel: string }) {
  const ints = useGet<Integration[]>('/integrations', 120000)
  const st = ints.data?.find(x => x.system === system)
  return <PageHeader title={<>{title} {st && <Status s={st.status} />}</>} help={desc}>
    <a className="btn" href={openHref} target="_blank" rel="noopener noreferrer">{openLabel} ↗</a>
  </PageHeader>
}

// ------------------------------------------------------------------ Asana
function taskTone(t: Task) {
  if (t.status === 'completed') return 'done'
  if ((t.section || '').toUpperCase() === 'RACES') return 'race'
  const d = daysUntil(t.due_on); return d !== null && d < 0 ? 'late' : ''
}
function TaskLink({ t }: { t: Task }) {
  return <SysLink links={t.links} one />
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

/** Ordem do quadro e da lista (dono, 16/09): o que ainda não foi concluído vem primeiro; dentro
 *  de cada grupo, a data mais recente no topo; sem data vai para o fim. O calendário não usa. */
function ordenar(ts: Task[]) {
  return [...ts].sort((a, b) => ((a.status === 'completed' ? 1 : 0) - (b.status === 'completed' ? 1 : 0)) || (b.due_on || '').localeCompare(a.due_on || ''))
}

function Quadro({ tasks, onOpen }: { tasks: Task[]; onOpen: (t: Task) => void }) {
  const cols = useMemo(() => { const mp = new Map<string, Task[]>(); for (const t of tasks) { const k = t.section || '—'; mp.set(k, [...(mp.get(k) || []), t]) }
    return [...mp.entries()].sort((a, b) => { const ia = ORDEM_SECOES.indexOf(a[0]), ib = ORDEM_SECOES.indexOf(b[0]); return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) }) }, [tasks])
  if (cols.length === 0) return <div className="card"><Empty title="Quadro vazio">Nenhuma tarefa espelhada. Sincronize no Dashboard.</Empty></div>
  const hojeSec = ORDEM_SECOES[(new Date().getDay() + 6) % 7 - 1] || ''   // seg → nada; ter…dom → coluna do dia
  return <div className="board">{cols.map(([sec, ts]) => <div className={`col${sec === hojeSec ? ' today' : ''}${sec === 'Finished Services' ? ' hist' : ''}`} key={sec}><div className="ch">{sec === hojeSec ? '● ' : ''}{sec}<span className="count">{ts.length}</span></div><div className="cards">
    {ts.map(t => { const d = daysUntil(t.due_on); return <div key={t.id} className={`tcard${t.status === 'completed' ? ' done' : ''}`} onClick={() => onOpen(t)} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') onOpen(t) }}>
      {t.client_name && <div className="who">{t.client_name}</div>}
      <div className="t">{t.title}</div>
      <div className="m">{t.due_on && <span className={`mono${t.status !== 'completed' && d !== null && d < 0 ? ' warn' : ''}`}>{d === 0 ? 'HOJE' : d === 1 ? 'amanhã' : fmtDate(t.due_on)}</span>}{t.subtasks_total ? <span className="row" style={{ gap: 6 }}><Dots done={t.subtasks_done ?? 0} total={t.subtasks_total} tone={t.status === 'completed' ? 'ok' : 'accent'} /><span className="mono">{t.subtasks_done ?? '?'}/{t.subtasks_total}</span></span> : null}{t.waiver_id ? <span className="ok" title="waiver assinada anexada">✓ waiver</span> : null}</div>
    </div> })}</div></div>)}</div>
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
  const { can } = useAuth()
  const det = useGet<TaskDetail>(`/tasks/${t.id}/detail`)
  const fields = (det.data?.task?.campos as Record<string, string> | undefined) || (safeJson(t.fields) as Record<string, string> | null)
  const subs = det.data?.task?.subtarefas_lista || []
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 860 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label="Fechar">✕</button>
    <div><div className="small muted cond">{t.project} · {t.section}</div><h2 className="h1" style={{ fontSize: 22 }}>{t.title}</h2></div>
    <div className="grid g2">
      <dl className="dl"><dt>Vence</dt><dd className="mono">{fmtDate(t.due_on)}</dd><dt>Status</dt><dd><Status s={t.status} /></dd>
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
        <Section title={<>Subtarefas <Dots done={subs.filter(s => s.concluida).length} total={subs.length} /></>} count={subs.length} tight>{subs.length === 0 ? <Empty>Nenhuma.</Empty> : <div>{subs.map(s => <div key={s.gid} className="att"><div className={`lv ${s.concluida ? 'LOW' : 'MEDIUM'}`} /><div className="grow" style={{ textDecoration: s.concluida ? 'line-through' : undefined, color: s.concluida ? 'var(--muted)' : undefined }}>{s.concluida ? '✓ ' : '○ '}{s.nome}{s.vence_em && <span className="small muted mono"> · {fmtDate(s.vence_em)}</span>}</div></div>)}</div>}</Section>
        <Section title="Anexos" count={det.data.attachments?.length} tight>{!det.data.attachments?.length ? <Empty>Nenhum.</Empty> : <div>{det.data.attachments.map(a => <div key={a.gid} className="att"><div className="lv LOW" /><div className="grow">{a.download ? <a href={a.download} target="_blank" rel="noopener noreferrer">{a.nome} ↗</a> : a.nome}<div className="small muted">{a.origem} · {fmtDateTime(a.quando)}</div></div></div>)}</div>}</Section>
      </div>
      <Section title="Comentários" count={det.data.comments?.length} tight>{!det.data.comments?.length ? <Empty>Nenhum comentário.</Empty> : <div>{det.data.comments.map((c, i) => <div key={i} className="att"><div className="lv LOW" /><div className="grow"><div className="small muted"><b>{c.quem || '?'}</b> · {fmtDateTime(c.quando)}</div><div style={{ whiteSpace: 'pre-wrap' }}>{c.texto}</div></div></div>)}</div>}</Section>
    </>}
    {can('OPERATOR') && <InstruirTarefa t={t} onClose={onClose} />}
    <div className="row"><TaskLink t={t} /></div>
  </div></Scrim>
}

/** Caixa da IA dentro da tarefa (dono, 16/09): a instrução vai com o gid, o título, o cliente,
 *  as subtarefas e a descrição desta tarefa, e a IA age nela — e só nela. */
function InstruirTarefa({ t, onClose }: { t: Task; onClose: () => void }) {
  const toast = useToast()
  const nav = useNavigate()
  const [text, setText] = useState('')
  const [remember, setRemember] = useState(false)
  const [busy, setBusy] = useState(false)
  async function send() {
    if (!text.trim()) return
    setBusy(true)
    try {
      const r = await api.post<{ command_id: number; remembered: boolean }>(`/tasks/${t.id}/instruct`, { text, remember })
      toast(r.remembered ? 'Instrução enviada à IA e guardada na memória dela.' : 'Instrução enviada à IA.', 'ok'); onClose(); nav(`/ai/${r.command_id}`)
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <Section title="✦ IA nesta tarefa" tight>
    <TextoComVoz valor={text} onChange={setText} linhas={3} placeholder={`Diga (ou dite) à IA o que fazer com esta tarefa. Ex.: "confirme o piloto, feche a subtarefa da waiver e comente que a invoice foi paga".`} />
    <div className="row wrap"><label className="check"><input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} /> guardar na memória da IA {t.client_id ? '(deste cliente)' : '(tarefas)'}</label><span className="grow" /><button className="btn primary sm" disabled={busy || !text.trim()} onClick={send}>{busy ? <span className="spin" /> : '✦ Enviar à IA'}</button></div>
  </Section>
}

function NovaTarefa({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const [f, setF] = useState({ pilot_name: '', responsible: '', email: '', phone: '', dob: '', height: '', weight: '', waist: '', experience: '', product: 'Urace Daily', category: '2 stroke', package_n: 1, package_total: 4, days: 1, due_on: '', extra_notes: '' })
  const [busy, setBusy] = useState(false)
  const set = (k: string, v: string | number) => setF({ ...f, [k]: v })
  const idade = f.dob ? Math.floor((Date.now() - new Date(f.dob + 'T12:00:00Z').getTime()) / (365.25 * 86400000)) : null
  const menor = idade !== null && idade < 18
  const faltam = [!f.pilot_name.trim() && 'piloto', !f.email.includes('@') && 'e-mail', !f.phone.trim() && 'telefone', !f.due_on && 'data', (menor || idade === null) && !f.responsible.trim() && (menor ? 'responsável (piloto menor)' : 'nascimento ou responsável')].filter(Boolean) as string[]
  async function save() {
    setBusy(true)
    try { const r = await api.post<{ id: number; link: string; section: string }>('/tasks', f); toast(`Tarefa criada na coluna ${r.section}.`, 'ok'); onDone(); onClose(); if (r.link) window.open(r.link, '_blank', 'noopener') }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 720 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose}>✕</button>
    <div><h2 className="h1" style={{ fontSize: 22 }}>Nova tarefa de serviço</h2><div className="small muted">Cria no Asana a partir do modelo oficial (com as subtarefas), na coluna do dia da data. A IA é avisada e prepara waiver e invoice.</div></div>
    <div className="grid g2">
      <div className="field"><label>Piloto *</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.pilot_name} onChange={e => set('pilot_name', e.target.value)} /><Mic valor={f.pilot_name} onTexto={t => set('pilot_name', t)} /></div></div>
      <div className="field"><label>Responsável {menor ? '* (piloto menor: quem assina e paga)' : '(quem paga/assina)'}</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.responsible} onChange={e => set('responsible', e.target.value)} placeholder={menor ? 'obrigatório' : 'se adulto e vazio, o próprio piloto'} /><Mic valor={f.responsible} onTexto={t => set('responsible', t)} /></div></div>
      <div className="field"><label>E-mail do responsável *</label><div className="row" style={{ gap: 6 }}><input className="input" type="email" value={f.email} onChange={e => set('email', e.target.value)} /><Mic valor={f.email} onTexto={t => set('email', t.replace(/\s+/g, '').replace(/arroba/gi, '@'))} /></div></div>
      <div className="field"><label>Telefone *</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.phone} onChange={e => set('phone', e.target.value)} /><Mic valor={f.phone} onTexto={t => set('phone', t)} /></div></div>
      <div className="field"><label>Nascimento do piloto {idade !== null && <span className="muted">({idade} anos{menor ? ', menor' : ''})</span>}</label><input className="input" type="date" value={f.dob} onChange={e => set('dob', e.target.value)} /></div>
      <div className="field"><label>Data do serviço *</label><input className="input" type="date" value={f.due_on} onChange={e => set('due_on', e.target.value)} /></div>
      <div className="field"><label>Produto *</label><select className="input" value={f.product} onChange={e => set('product', e.target.value)}>
        <option value="Urace Daily">Urace Daily (treino: Practice / Professional Coaching)</option><option value="Lead and Follow">Lead and Follow (coach na pista, $769 fechado antes)</option><option value="Academy">Academy (mensal, 4 sessões)</option><option value="Corrida">Corrida (Race / Trackside Support)</option><option value="Arrive and Drive">Arrive and Drive</option><option value="Summer Camp">Summer Camp</option><option value="Test Drive">Test Drive</option></select>
        <span className="small muted">{f.product === 'Corrida' ? 'preço: Rate Card, aba Racing team' : 'preço: Rate Card, aba Academy'}</span></div>
      <div className="field"><label>Categoria (como na Rate Card)</label><select className="input" value={f.category} onChange={e => set('category', e.target.value)}>
        <option value="Using Own Kart">Using Own Kart (4+ anos)</option><option value="Baby Kart">Baby Kart (4 a 7 anos)</option><option value="4 stroke">4 stroke kart (7+)</option><option value="2 stroke">2 stroke kart (7+)</option><option value="Adult Shifter">Adult Shifter rental (14+, com experiência)</option><option value="F4">F4</option></select></div>
      {f.product === 'Academy' ? <div className="field"><label>Sessão do mês</label><select className="input" value={f.package_n} onChange={e => set('package_n', Number(e.target.value))}>{[1, 2, 3, 4].map(n => <option key={n} value={n}>{n}/4</option>)}</select></div>
        : <div className="field"><label>Dias</label><input className="input" type="number" min={1} max={10} value={f.days} onChange={e => set('days', Number(e.target.value))} /></div>}
      <div className="field"><label>Altura</label><input className="input" value={f.height} onChange={e => set('height', e.target.value)} placeholder="ex.: 1,60 m" /></div>
      <div className="field"><label>Peso</label><input className="input" value={f.weight} onChange={e => set('weight', e.target.value)} placeholder="ex.: 52 kg" /></div>
      <div className="field"><label>Cintura</label><input className="input" value={f.waist} onChange={e => set('waist', e.target.value)} placeholder="para o macacão" /></div>
      <div className="field"><label>Experiência</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.experience} onChange={e => set('experience', e.target.value)} placeholder="ex.: 2 anos de kart, nunca pilotou" /><Mic valor={f.experience} onTexto={t => set('experience', t)} /></div></div>
    </div>
    <div className="field"><label>Observações</label><TextoComVoz valor={f.extra_notes} onChange={t => set('extra_notes', t)} linhas={2} placeholder="altura, peso, experiência, pedidos especiais (dá para ditar)" /></div>
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onClose}>Cancelar</button><span className="small muted">{faltam.length > 0 && `falta: ${faltam.join(', ')}`}</span><button className="btn primary" disabled={busy || faltam.length > 0} onClick={save}>{busy ? <Spinner /> : 'Criar no Asana'}</button></div>
  </div></Scrim>
}

export function AsanaPage() {
  const { can } = useAuth()
  const [nova, setNova] = useState(false)
  const [tab, setTab] = useTab<'cal' | 'board' | 'list'>('v', telaPequena() ? 'list' : 'cal')
  const [status, setStatus] = useTab<'all' | 'open' | 'completed'>('s', 'open')     // dono, 16/09: o quadro abre só com o que falta fazer
  const { data, error, loading, reload } = useGet<Task[]>('/tasks?status=all', 120000)
  const [open, setOpen] = useState<Task | null>(null)
  const tasks = ordenar((data || []).filter(t => status === 'all' || t.status === status))
  return <>
    <IntHeader system="asana" title="Asana" desc="Quadro U-RACE: TUESDAY a SUNDAY é a agenda, RACES são corridas, Finished Services é o histórico." openHref={ASANA_PROJ} openLabel="Abrir no Asana" />
    <div className="row wrap"><SubTabs tabs={[['cal', 'Calendário'], ['board', 'Quadro'], ['list', 'Lista']]} value={tab} onChange={setTab} /><div className="grow" />
      {can('OPERATOR') && <button className="btn primary" onClick={() => setNova(true)}>+ Nova tarefa</button>}
      <select className="input" style={{ width: 160 }} value={status} onChange={e => setStatus(e.target.value as 'all')} aria-label="Quais tarefas"><option value="open">Só abertas</option><option value="all">Abertas e concluídas</option><option value="completed">Só concluídas</option></select><button className="btn" onClick={reload} aria-label="Atualizar">↻</button></div>
    {nova && <NovaTarefa onClose={() => setNova(false)} onDone={reload} />}
    {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading rows={6} /> : <>
      {tab === 'cal' && <Calendario tasks={tasks} onOpen={setOpen} />}
      {tab === 'board' && <Quadro tasks={tasks} onOpen={setOpen} />}
      {tab === 'list' && <Section title="Tarefas" count={tasks.length} tight>{tasks.length === 0 ? <Empty>Nada com esse filtro.</Empty> :
        <div className="tbl-wrap"><table className="tbl rsp"><thead><tr><th>Data</th><th>Tarefa</th><th>Coluna</th><th>Cliente</th><th>Responsável</th><th>Subtarefas</th><th>Status</th><th></th></tr></thead><tbody>
          {tasks.map(t => <tr key={t.id} className="click" onClick={() => setOpen(t)}><td className="mono nowrap" data-l="Data">{fmtDate(t.due_on)}</td><td className="first">{t.title}</td><td data-l="Coluna">{t.section}</td><td data-l="Cliente">{t.client_name || <span className="muted">—</span>}</td><td className="small" data-l="Quem">{t.assignee}</td><td className="mono" data-l="Subtarefas">{t.subtasks_total ? `${t.subtasks_done ?? '?'}/${t.subtasks_total}` : '—'}</td><td data-l="Status"><Status s={t.status} /></td><td onClick={e => e.stopPropagation()}><TaskLink t={t} /></td></tr>)}
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
function EnviarWaiver({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const perguntar = usePerguntar()
  const toast = useToast()
  const [f, setF] = useState({ template: 'parental', signer_name: '', signer_email: '', service: '' })
  const [busy, setBusy] = useState(false)
  async function send() {
    if (!await perguntar({ titulo: 'Enviar a waiver agora?', texto: `Modelo ${f.template} para ${f.signer_name} <${f.signer_email}>.`, ok: 'Enviar' })) return
    setBusy(true)
    try { await api.post('/waivers/send', f); toast('Waiver enviada pelo DocuSign.', 'ok'); onDone(); onClose() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose}>✕</button>
    <div><h2 className="h1" style={{ fontSize: 22 }}>Enviar waiver</h2><div className="small muted">Parental quando o piloto é menor: quem assina é o responsável. O DocuSign recusa se já houver waiver válida ou envelope aberto para o e-mail.</div></div>
    <div className="grid g2">
      <div className="field"><label>Modelo</label><select className="input" value={f.template} onChange={e => setF({ ...f, template: e.target.value })}><option value="parental">Parental (piloto menor)</option><option value="adult">Adult</option></select></div>
      <div className="field"><label>Serviço (opcional)</label><input className="input" value={f.service} onChange={e => setF({ ...f, service: e.target.value })} /></div>
      <div className="field"><label>Nome de quem assina *</label><input className="input" value={f.signer_name} onChange={e => setF({ ...f, signer_name: e.target.value })} /></div>
      <div className="field"><label>E-mail de quem assina *</label><input className="input" type="email" value={f.signer_email} onChange={e => setF({ ...f, signer_email: e.target.value })} /></div>
    </div>
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={busy || !f.signer_name.trim() || !f.signer_email.includes('@')} onClick={send}>{busy ? <Spinner /> : 'Enviar agora'}</button></div>
  </div></Scrim>
}

interface ModeloDetalhe {
  connected: boolean; reason?: string; templateId?: string; nome?: string | null; descricao?: string | null; alterado_em?: string | null
  documentos?: { documentId: string; nome: string | null; paginas?: string | number | null }[]
  papeis?: { papel: string | null; campos: number; ancoras: string[] }[]; uso_pela_IA?: string | null
}
/** Modelo do DocuSign por inteiro (dono, 16/09): ver o PDF, renomear, trocar o PDF. A troca
 *  guarda o PDF antigo no servidor antes; os campos de assinatura ficam presos ao documento. */
function ModeloModal({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const perguntar = usePerguntar()
  const det = useGet<ModeloDetalhe>(`/docusign/templates/${id}`)
  const [nome, setNome] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const nomeAtual = nome ?? (det.data?.nome || '')
  async function renomear() {
    setBusy('nome')
    try { await api.patch(`/docusign/templates/${id}`, { name: nomeAtual }); toast('Modelo renomeado no DocuSign.', 'ok'); setNome(null); det.reload(); onChanged() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function substituir(did: string, file: File) {
    const vazio = !det.data?.documentos?.length
    const ok = await perguntar(vazio ? { titulo: 'Adicionar este PDF ao modelo?', ok: 'Adicionar', texto: `"${file.name}" vira o documento do modelo "${det.data?.nome || id}".\n\nO modelo continua sem papéis e sem campos de assinatura: isso se coloca no DocuSign, depois.` }
      : { titulo: 'Trocar o PDF deste modelo?', perigo: true, ok: 'Trocar',
      texto: `"${file.name}" vai substituir o documento ${did} do modelo "${det.data?.nome || id}" no DocuSign.\n\nO PDF atual fica guardado no servidor antes da troca. Os campos de assinatura continuam presos ao documento: se o leiaute mudou, confira no DocuSign onde eles caíram antes de enviar a próxima waiver.` })
    if (!ok) return
    setBusy(did)
    try {
      const fd = new FormData(); fd.append('file', file)
      const csrf = document.cookie.match(/(?:^|;\s*)cc_csrf=([^;]+)/)?.[1] || ''
      const res = await fetch(`/ops/api/docusign/templates/${id}/documents/${did}`, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-CSRF': decodeURIComponent(csrf) } })
      if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(j.detail || `HTTP ${res.status}`) }
      const j = await res.json(); toast(j.novo ? 'PDF adicionado ao modelo. Agora coloque os campos de assinatura no DocuSign.' : `PDF trocado. O antigo ficou guardado como ${j.backup}.`, 'ok'); det.reload(); onChanged()
    } catch (e) { toast((e as Error).message, 'crit') } finally { setBusy(null) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 720 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label="Fechar">✕</button>
    <div><div className="small muted cond">DocuSign · modelo</div><h2 className="h1" style={{ fontSize: 22 }}>{det.data?.nome || <span className="muted">(sem nome)</span>}</h2><div className="small muted mono">{id}</div></div>
    {det.loading && !det.data && <Loading rows={3} />}
    {det.error && <ErrorState error={det.error} retry={det.reload} />}
    {det.data && !det.data.connected && <Banner tone="warn">DocuSign não conectado: {det.data.reason}</Banner>}
    {det.data?.connected && <>
      {det.data.uso_pela_IA && <Banner tone="info">Este modelo é um dos dois que a automação usa: {det.data.uso_pela_IA}</Banner>}
      {can('MANAGER') && <Section title="Nome" tight><div className="row wrap"><input className="input grow" value={nomeAtual} onChange={e => setNome(e.target.value)} maxLength={120} /><button className="btn primary sm" disabled={busy === 'nome' || nomeAtual.trim().length < 2 || nomeAtual === (det.data.nome || '')} onClick={renomear}>{busy === 'nome' ? <Spinner /> : 'Salvar nome'}</button></div></Section>}
      {!det.data.documentos?.length && !det.data.papeis?.length && <Banner tone="warn">Modelo <b>vazio</b>: sem PDF, sem papel, sem campo de assinatura. Não serve para enviar nada. Ou você o apaga no DocuSign, ou sobe um PDF aqui e coloca os campos lá.</Banner>}
      <Section title="Documentos" count={det.data.documentos?.length} right={!det.data.documentos?.length && can('MANAGER') ? <label className="btn sm" style={{ cursor: busy ? 'default' : 'pointer' }}>{busy === '1' ? <Spinner /> : 'Adicionar PDF…'}<input type="file" accept="application/pdf,.pdf" style={{ display: 'none' }} disabled={!!busy} onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) substituir('1', f) }} /></label> : undefined} tight>{!det.data.documentos?.length ? <Empty>O modelo não tem documento.</Empty> : <div>{det.data.documentos.map(d => <div key={d.documentId} className="att"><div className="lv LOW" /><div className="grow">{d.nome || `documento ${d.documentId}`}<div className="small muted">id {d.documentId}{d.paginas ? ` · ${d.paginas} pág.` : ''}</div></div>
        <a className="btn sm" href={`/ops/api/docusign/templates/${id}/documents/${d.documentId}`} target="_blank" rel="noopener noreferrer">Ver PDF ↗</a>
        {can('MANAGER') && <label className="btn sm" style={{ cursor: busy ? 'default' : 'pointer' }}>{busy === d.documentId ? <Spinner /> : 'Substituir PDF…'}<input type="file" accept="application/pdf,.pdf" style={{ display: 'none' }} disabled={!!busy} onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) substituir(d.documentId, f) }} /></label>}
      </div>)}</div>}</Section>
      <Section title="Papéis e campos de assinatura" count={det.data.papeis?.length} tight>{!det.data.papeis?.length ? <Empty>Sem papéis.</Empty> : <div>{det.data.papeis.map((p, i) => <div key={i} className="att"><div className="lv LOW" /><div className="grow">{p.papel || '?'}<div className="small muted">{p.campos} campo(s){p.ancoras.length ? ` · âncoras: ${p.ancoras.join(', ')}` : ' · por posição na página'}</div></div></div>)}</div>}</Section>
      <div className="small muted">Alterado em {fmtDateTime(det.data.alterado_em)}. Trocar o PDF mantém o documento e seus campos; se o leiaute mudou, confira no DocuSign.</div>
    </>}
  </div></Scrim>
}

export function DocuSignPage() {
  const nav = useNavigate()
  const { can } = useAuth()
  const perguntar = usePerguntar()
  const toast = useToast()
  const [enviar, setEnviar] = useState(false)
  const [tab, setTab] = useTab<'env' | 'signed' | 'int' | 'tpl' | 'lixo'>('v', 'env')
  const [modelo, setModelo] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [st, setSt] = useTab<string>('s', 'all')
  const env = useGet<Waiver[]>(tab === 'lixo' ? '/waivers?hidden=1' : '/waivers', 120000)
  const tpl = useGet<{ connected: boolean; reason?: string; templates: Template[] | Record<string, unknown> }>(tab === 'tpl' ? '/docusign/templates' : null)
  const [busy, setBusy] = useState<number | null>(null)
  // Documento interno = envelope que o support@ assina (carta de emprego, invite letter…): aba própria, fora das waivers (dono, 16/09)
  const interno = (w: Waiver) => !!w.internal
  const bate = (w: Waiver) => { const s = q.trim().toLowerCase(); return !s || [w.signer_name, w.signer_email, w.client_pilot, w.client_name, w.minor_name, w.subject].some(v => (v || '').toLowerCase().includes(s)) }
  const rows = (env.data || []).filter(w => tab === 'signed' ? (w.status === 'completed' && (w.template === 'parental' || w.template === 'adult') && !interno(w))
    : tab === 'int' ? interno(w) : tab === 'lixo' ? (st === 'all' || w.status === st) : (!interno(w) && (st === 'all' || w.status === st))).filter(bate)
  const nInt = (env.data || []).filter(interno).length
  const counts = (env.data || []).filter(w => tab === 'lixo' || !interno(w)).reduce<Record<string, number>>((a, w) => { a[w.status || '?'] = (a[w.status || '?'] || 0) + 1; return a }, {})
  const tplList: Template[] = Array.isArray(tpl.data?.templates) ? tpl.data!.templates as Template[] : ((tpl.data?.templates as Record<string, unknown>)?.templates as Template[]) || []
  async function act(w: Waiver, kind: 'trash' | 'restore' | 'resend', body?: unknown) {
    setBusy(w.id)
    try { const r = await api.post<{ note?: string; voided?: boolean; email_corrigido?: string }>(`/waivers/${w.id}/${kind}`, body || {})
      toast(kind === 'trash' ? (r.voided ? 'Envelope anulado no DocuSign e removido do painel.' : r.note || 'Removido do painel.') : kind === 'restore' ? 'Restaurado.' : r.email_corrigido ? `E-mail corrigido para ${r.email_corrigido} e reenviado.` : 'Reenviado ao signatário.', 'ok'); env.reload() }
    catch (ex) { toast((ex as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function trash(w: Waiver) {
    const aberto = ['sent', 'delivered', 'autoresponded'].includes(w.status || '')
    const msg = aberto ? `Anular o envelope de ${w.signer_name} no DocuSign e tirar do painel?\n\nO signatário não consegue mais assinar. Motivo (opcional):` : `Tirar a waiver de ${w.signer_name} do painel?\n\nEnvelope assinado é registro legal e continua no DocuSign. Motivo (opcional):`
    const reason = await perguntar({ titulo: 'Mandar para a lixeira?', texto: msg, campo: 'Motivo (opcional)', ok: 'Confirmar', perigo: true }) as string | null; if (reason === null) return
    act(w, 'trash', { reason })
  }
  async function resend(w: Waiver) {
    const novo = await perguntar({ titulo: `Reenviar a waiver para ${w.signer_name}`, texto: 'Confira o e-mail do signatário e corrija se estava errado.', campo: 'E-mail', valor: w.signer_email || '', ok: 'Reenviar' }) as string | null
    if (novo === null) return
    act(w, 'resend', { email: novo.trim().toLowerCase() !== (w.signer_email || '').toLowerCase() ? novo.trim() : undefined })
  }
  return <>
    <IntHeader system="docusign" title="DocuSign" desc="Waivers de produção. Entregue não é assinada; devolvida é e-mail errado. Cada envelope ligado ao piloto." openHref="https://app.docusign.com/home" openLabel="Abrir no DocuSign" />
    <div className="row wrap"><SubTabs tabs={[['env', 'Envelopes'], ['signed', `Assinadas (${(env.data || []).filter(w => w.status === 'completed' && (w.template === 'parental' || w.template === 'adult') && !interno(w)).length})`], ['int', `Internos (${nInt})`], ['tpl', 'Modelos'], ['lixo', 'Lixeira']]} value={tab} onChange={setTab} /><div className="grow" />
      {can('OPERATOR') && <button className="btn primary" onClick={() => setEnviar(true)}>+ Enviar waiver</button>}
      {tab !== 'tpl' && <input className="input" style={{ width: 200 }} placeholder="Buscar…" title="signatário, e-mail, piloto, responsável, menor ou assunto" value={q} onChange={e => setQ(e.target.value)} aria-label="Buscar nas waivers" />}
      {tab !== 'tpl' && tab !== 'signed' && tab !== 'int' && <select className="input" style={{ width: 220 }} value={st} onChange={e => setSt(e.target.value)}><option value="all">Todos ({Object.values(counts).reduce((a, n) => a + n, 0)})</option>{Object.entries(counts).map(([k, n]) => <option key={k} value={k}>{WAIVER_LABEL[k] || k} ({n})</option>)}</select>}
      <button className="btn" onClick={() => { env.reload(); tpl.reload() }}>↻</button></div>
    {enviar && <EnviarWaiver onClose={() => setEnviar(false)} onDone={env.reload} />}
    {tab !== 'tpl' && <Section title={tab === 'lixo' ? 'Na lixeira do painel' : tab === 'signed' ? 'Waivers assinadas (parental e adult)' : tab === 'int' ? 'Documentos internos (o support@ assina; não são waiver de cliente)' : 'Envelopes'} count={rows.length} tight>
      {env.error && !env.data ? <ErrorState error={env.error} retry={env.reload} /> : env.loading && !env.data ? <Loading /> : rows.length === 0 ? <Empty>{tab === 'lixo' ? 'Nada na lixeira.' : q ? 'Nada bate com a busca.' : tab === 'int' ? 'Nenhum documento interno espelhado. A próxima sincronia do DocuSign marca os envelopes que o support@ assina.' : 'Nenhum envelope espelhado com esse filtro.'}</Empty> :
        <div className="tbl-wrap"><table className="tbl rsp"><thead><tr><th>Signatário</th><th>{tab === 'int' ? 'Documento' : 'Cliente / piloto'}</th><th>Modelo</th><th>Status</th><th>Enviada</th><th>Assinada</th><th>Expira</th><th></th></tr></thead><tbody>
          {rows.map(w => { const aberto = ['sent', 'delivered', 'autoresponded'].includes(w.status || ''); return <tr key={w.id}>
            <td className="first">{w.signer_name}<div className="small muted">{w.signer_email}</div>{w.minor_name && <div className="small">menor: <b>{w.minor_name}</b></div>}{tab !== 'int' && w.subject && <div className="small muted" title={w.subject}>{w.subject.slice(0, 60)}</div>}</td>
            <td data-l={tab === 'int' ? 'Documento' : 'Piloto'}>{tab === 'int' ? <span title={w.subject || ''}>{w.subject || <span className="muted">sem assunto</span>}</span> : w.client_id ? <><a onClick={() => nav(`/clients/${w.client_id}`)} style={{ cursor: 'pointer' }}>{w.client_pilot || w.client_name}</a>{w.client_pilot && <div className="small muted">{w.client_name}</div>}{w.link_reason && <div className="small muted" title={w.link_reason}>{w.link_by === 'human' ? 'vínculo à mão' : 'vínculo automático'}</div>}</> : <><span className="muted">não vinculado</span>{can('OPERATOR') && <LinkClient w={w} onDone={env.reload} />}</>}</td>
            <td data-l="Modelo">{w.template}</td>
            <td data-l="Status"><Status s={w.status} label={WAIVER_LABEL[w.status || ''] || w.status} /></td>
            <td data-l="Enviada" className="mono">{fmtDate(w.sent_at)}</td><td data-l="Assinada" className="mono">{fmtDate(w.completed_at)}</td><td data-l="Expira" className="mono">{fmtDate(w.expires_at)}</td>
            <td className="nowrap" data-l="Ações">
              {w.status === 'completed' && <a className={tab === 'signed' ? 'btn sm' : 'ic'} href={`/ops/api/waivers/${w.id}/download`} title="Baixar PDF assinado" aria-label="Baixar">⬇{tab === 'signed' ? ' PDF' : ''}</a>}
              {tab === 'signed' && w.client_id && <button className="btn sm" onClick={() => nav(`/clients?open=${w.client_id}`)} title="Abrir o card do cliente">→ cliente</button>}
              {aberto && can('OPERATOR') && tab !== 'lixo' && <button className="ic" disabled={busy === w.id} title={w.status === 'autoresponded' ? 'Corrigir e-mail e reenviar' : 'Reenviar'} aria-label="Reenviar" onClick={() => resend(w)}>↻</button>}
              {tab !== 'lixo' && can('OPERATOR') && <button className="ic danger" disabled={busy === w.id} title={aberto ? 'Anular no DocuSign e tirar do painel' : 'Tirar do painel (assinada fica no DocuSign)'} aria-label="Lixeira" onClick={() => trash(w)}>🗑</button>}
              {tab === 'lixo' && can('OPERATOR') && <button className="btn sm" disabled={busy === w.id} onClick={() => act(w, 'restore')}>Restaurar</button>}
              <SysLink links={w.links} one />
            </td></tr> })}
        </tbody></table></div>}</Section>}
    {tab === 'tpl' && <Section title="Modelos da conta" count={tplList.length}>
      {tpl.loading && !tpl.data ? <Loading /> : tpl.error ? <ErrorState error={tpl.error} retry={tpl.reload} /> : tpl.data && !tpl.data.connected ? <Banner tone="warn">DocuSign não conectado neste servidor: {tpl.data.reason}</Banner> :
        tplList.length === 0 ? <Empty>A conta não devolveu modelos.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Modelo</th><th>ID</th><th>Papéis</th></tr></thead><tbody>
          {tplList.map((t, i) => { const id = String(t.templateId || t.id || ''); return <tr key={i} className="click" onClick={() => id && setModelo(id)}><td>{t.nome || t.name || <span className="muted">(sem nome — clique para nomear)</span>}{!(t.papeis || t.roles || []).length && <span className="small muted"> · vazio</span>}</td><td className="mono small">{id}</td><td className="small">{(t.papeis || t.roles || []).join(', ')}</td></tr> })}
        </tbody></table></div>}
      <div className="small muted" style={{ marginTop: 10 }}>Clique no modelo para ver o PDF, renomear ou trocar o PDF. Envio de waiver pela IA passa por aprovação (política). Só os dois modelos de PARAMETROS servem para a automação.</div>
    </Section>}
    {modelo && <ModeloModal id={modelo} onClose={() => setModelo(null)} onChanged={tpl.reload} />}
  </>
}

// ------------------------------------------------------------------ Gmail
type Box = 'urace' | 'support'
const SYS_LABELS = new Set(['INBOX', 'UNREAD', 'STARRED', 'IMPORTANT', 'SENT', 'DRAFT', 'SPAM', 'TRASH', 'CHAT'])
const userLabelsOf = (e: Email) => (JSON.parse(e.labels || '[]') as string[]).filter(l => l && !SYS_LABELS.has(l.toUpperCase()) && !l.startsWith('CATEGORY_'))

/** Busca por digitação entre os marcadores reais da caixa (decisão do dono, 09/09). Enter ou clique adiciona. */
export function LabelPicker({ labels, exclude, onPick, placeholder = 'Adicionar marcador… (digite para buscar)' }: { labels: GmailLabel[]; exclude?: string[]; onPick: (name: string) => void; placeholder?: string }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [ix, setIx] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  const ex = new Set((exclude || []).map(x => x.toLowerCase()))
  const norm = (t: string) => t.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  const qn = norm(q.trim())
  const hits = labels.filter(l => !ex.has(l.name.toLowerCase())).filter(l => !qn || norm(l.name).includes(qn))
    .sort((a, b) => (norm(a.name).startsWith(qn) ? 0 : 1) - (norm(b.name).startsWith(qn) ? 0 : 1) || a.name.localeCompare(b.name)).slice(0, 12)
  useEffect(() => { setIx(0) }, [q])
  useEffect(() => {
    const h = (ev: MouseEvent) => { if (box.current && !box.current.contains(ev.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [])
  function pick(name: string) { onPick(name); setQ(''); setOpen(false) }
  return <div className="lpick" ref={box}>
    <input className="input" value={q} placeholder={placeholder} aria-label="Buscar marcador" onFocus={() => setOpen(true)} onChange={ev => { setQ(ev.target.value); setOpen(true) }}
      onKeyDown={ev => { if (ev.key === 'ArrowDown') { ev.preventDefault(); setIx(i => Math.min(i + 1, hits.length - 1)) } else if (ev.key === 'ArrowUp') { ev.preventDefault(); setIx(i => Math.max(i - 1, 0)) } else if (ev.key === 'Enter') { ev.preventDefault(); if (hits[ix]) pick(hits[ix].name) } else if (ev.key === 'Escape') setOpen(false) }} />
    {open && <div className="lpick-menu" role="listbox">
      {hits.length === 0 ? <div className="small muted" style={{ padding: '6px 10px' }}>Nenhum marcador com “{q}”. A IA não cria marcador; crie no Gmail.</div>
        : hits.map((l, i) => <div key={l.name} role="option" aria-selected={i === ix} className={`opt${i === ix ? ' on' : ''}`} onMouseEnter={() => setIx(i)} onMouseDown={ev => { ev.preventDefault(); pick(l.name) }}>
          <span className="truncate">{l.name}</span>{l.inbox_count ? <span className="c mono">{l.inbox_count}</span> : null}</div>)}
    </div>}
  </div>
}

/** O corpo como o Gmail mostra: HTML com imagens, num iframe sem script (sandbox + CSP própria no servidor). */
function CorpoHtml({ eid, m }: { eid: number; m: GmailMessage }) {
  const [alt, setAlt] = useState(false)
  const [h, setH] = useState(320)
  if (!m.tem_html || alt) return <><pre>{m.corpo || m.snippet}</pre>{m.tem_html && <a className="small" style={{ cursor: 'pointer' }} onClick={() => setAlt(false)}>ver como no Gmail</a>}</>
  return <>
    <iframe className="mail-frame" title={m.assunto || 'mensagem'} src={`/ops/api/emails/${eid}/html/${m.message_id}`} sandbox="" referrerPolicy="no-referrer" style={{ height: h }}
      onLoad={ev => { try { const d = (ev.target as HTMLIFrameElement).contentDocument; if (d) setH(Math.min(1800, Math.max(160, d.documentElement.scrollHeight + 24))) } catch { /* sandbox opaco: fica na altura padrão */ } }} />
    <a className="small" style={{ cursor: 'pointer' }} onClick={() => setAlt(true)}>ver só o texto</a>
  </>
}

export function GmailPage() {
  const nav = useNavigate()
  const { can } = useAuth()
  const perguntar = usePerguntar()
  const toast = useToast()
  const [box] = useTab<Box>('v', 'urace')
  const [sel, setSel] = useTab<string>('l', 'INBOX')          // INBOX | SEM_SUGESTAO | <marcador>
  const [openId, setOpenId] = useTab<string>('o', '')
  const { setMany } = useTabs()
  const labels = useGet<{ connected: boolean; reason?: string; labels: GmailLabel[] }>(`/gmail/labels?mailbox=${box}`, 120000)
  const emails = useGet<Email[]>(`/emails?mailbox=${box}`, 60000)
  const thread = useGet<{ connected: boolean; reason?: string; messages: GmailMessage[] }>(openId ? `/emails/${openId}/thread` : null)
  const [busy, setBusy] = useState<number | null>(null)
  const [classifying, setClassifying] = useState(false)
  const [triaging, setTriaging] = useState(false)
  const triage = useGet<{ running: boolean; rule?: { enabled: number; schedule: string | null; last_run_at: string | null; last_result: string | null } | null }>('/gmail/triage', 60000)
  const inbox = (emails.data || []).filter(e => e.is_inbox !== 0)
  const rows = sel === 'INBOX' ? inbox : sel === 'SEM_SUGESTAO' ? inbox.filter(e => !e.suggested_label) : inbox.filter(e => (JSON.parse(e.labels || '[]') as string[]).includes(sel) || e.suggested_label === sel)
  const cur = (emails.data || []).find(e => String(e.id) === openId) || null
  const userLabels = (labels.data?.labels || []).filter(l => l.type !== 'system')

  async function move(e: Email, label: string) {
    if (!label) return
    if (!await perguntar({ titulo: `Mover para "${label}"?`, texto: 'Aplica o marcador e tira da caixa de entrada.', ok: 'Mover' })) return
    setBusy(e.id)
    try { await api.post(`/emails/${e.id}/move`, { label }); toast(`Movido para ${label}.`, 'ok'); if (String(e.id) === openId) setOpenId(''); emails.reload(); labels.reload() }
    catch (ex) { toast((ex as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function addLabel(e: Email, label: string) {
    setBusy(e.id)
    try { await api.post(`/emails/${e.id}/labels`, { add: [label] }); toast(`Marcador ${label} adicionado. Clique nele para mover.`, 'ok'); emails.reload(); labels.reload() }
    catch (ex) { toast((ex as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function triageNow() {
    setTriaging(true)
    try {
      const r = await api.post<{ started: boolean }>('/gmail/triage', { mailbox: box })
      toast(r.started ? 'A IA está lendo a inbox: aplica os marcadores e move para o principal. Leva alguns minutos.' : 'Já há uma triagem rodando.')
      for (let i = 0; i < 150; i++) {
        await new Promise(res => setTimeout(res, 4000))
        const st = await api.get<{ running: boolean; result: { lidos?: number; movidos?: number; ficaram?: number; precisa_humano?: number; erros?: string[] } | null }>('/gmail/triage')
        if (!st.running) { const r2 = st.result || {}; const err = (r2.erros || []).length; toast(`IA leu ${r2.lidos ?? 0}: moveu ${r2.movidos ?? 0}, ${r2.ficaram ?? 0} ficaram na inbox, ${r2.precisa_humano ?? 0} pedem resposta${err ? `; ${err} erro(s): ${r2.erros![0]}` : ''}.`, err ? 'crit' : 'ok'); break }
      }
      emails.reload(); labels.reload(); triage.reload()
    } catch (ex) { toast((ex as ApiError).message, 'crit') } finally { setTriaging(false) }
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
  const horarios = (() => { try { return (JSON.parse(triage.data?.rule?.schedule || '[]') as string[]).join(', ') } catch { return '' } })()
  const ultimaTriagem = (() => { try { const r = JSON.parse(triage.data?.rule?.last_result || 'null'); return r ? `última: ${r.horario || ''} → ${r.movidos ?? 0} movidos, ${r.ficaram ?? 0} ficaram` : 'ainda não rodou' } catch { return '' } })()
  return <>
    <IntHeader system="gmail" title="Gmail" desc={`A IA lê a inbox ${horarios ? `às ${horarios}` : '3× ao dia'}, marca e move para o principal. Aqui fica o que ela não decidiu. Clicar num marcador move.`} openHref={`https://mail.google.com/mail/u/${box === 'urace' ? 0 : 1}/`} openLabel="Abrir o Gmail" />
    <div className="row wrap"><SubTabs tabs={[['urace', 'urace@'], ['support', 'support@']]} value={box} onChange={b => setMany({ v: b, l: 'INBOX', o: '' })} /><div className="grow" />
      <span className="small muted" title={ultimaTriagem}>{triage.data?.rule && !triage.data.rule.enabled ? 'triagem automática desligada (Automação)' : ultimaTriagem}</span>
      {can('OPERATOR') && <button className="btn primary" disabled={triaging || triage.data?.running || inbox.length === 0} onClick={triageNow} title="A IA lê cada thread da inbox, aplica os marcadores e move para o principal — agora, sem esperar o horário">{triaging || triage.data?.running ? <Spinner /> : '✦'} Triar com a IA agora</button>}
      {can('OPERATOR') && <button className="btn quiet" disabled={classifying || semSug === 0} onClick={classify} title="Só sugere o marcador (não move) para as threads ainda sem sugestão">{classifying ? <Spinner /> : ''} só sugerir{semSug > 0 && ` (${semSug})`}</button>}
      <button className="btn" onClick={() => { emails.reload(); labels.reload() }} aria-label="Atualizar">↻</button></div>
    <Progress on={triaging || classifying || !!triage.data?.running} />
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
              {!!e.handled && (e.handled_by === 'auto' || e.handled_by === 'ia') && <Chip tone="ok" >✓ IA: {e.handled_reason}</Chip>}
              {userLabelsOf(e).slice(0, 3).map(l => <button key={l} className="lchip" disabled={busy === e.id || !can('OPERATOR')} title={`Mover para ${l}`} onClick={() => move(e, l)}>{l} →</button>)}
              {e.suggested_label ? <><Chip tone={e.suggested_by === 'ia' ? 'info' : 'neutral'}>{e.suggested_by === 'ia' ? '✦ ' : ''}{e.suggested_label}</Chip>
                {can('OPERATOR') && <button className="btn sm primary" disabled={busy === e.id} onClick={() => move(e, e.suggested_label!)}>{busy === e.id ? <Spinner /> : 'Mover'}</button>}</>
                : <span className="small muted">sem sugestão</span>}
            </span>
          </div>)}
      </div>
      <div className="read">
        {!cur ? <Empty title="Selecione uma thread">O corpo abre aqui, ao vivo do Gmail.</Empty> : <>
          <div className="toolbar">
            <div className="row wrap" style={{ gap: 6 }} aria-label="Marcadores da thread">
              {userLabelsOf(cur).map(l => <button key={l} className={`lchip${cur.is_inbox === 0 ? ' here' : ''}`} disabled={busy === cur.id || !can('OPERATOR')} title={cur.is_inbox === 0 ? `Já está em ${l}` : `Mover para ${l} (aplica e tira da inbox)`} onClick={() => cur.is_inbox !== 0 && move(cur, l)}>{l}{cur.is_inbox !== 0 && ' →'}</button>)}
              {cur.suggested_label && !userLabelsOf(cur).includes(cur.suggested_label) && can('OPERATOR') && <button className="lchip sug" disabled={busy === cur.id} title={`Sugestão da IA: mover para ${cur.suggested_label}`} onClick={() => move(cur, cur.suggested_label!)}>✦ {cur.suggested_label} →</button>}
              {userLabelsOf(cur).length === 0 && !cur.suggested_label && <span className="small muted">sem marcador</span>}
            </div>
            {can('OPERATOR') && <div style={{ minWidth: 260, flex: '1 1 260px' }}><LabelPicker labels={userLabels} exclude={userLabelsOf(cur)} onPick={l => addLabel(cur, l)} /></div>}
            {can('OPERATOR') && <button className="btn sm" title={cur.handled_reason || ''} onClick={async () => { await api.patch(`/emails/${cur.id}`, { handled: !cur.handled }); emails.reload() }}>{cur.handled ? (cur.handled_by === 'auto' || cur.handled_by === 'ia' ? '✓ tratado pela IA' : '✓ tratado') : 'marcar tratado'}</button>}
            <span className="grow" />
            {cur.client_id && <a onClick={() => nav(`/clients/${cur.client_id}`)} style={{ cursor: 'pointer' }} className="small">cliente: {cur.client_name}</a>}
            <SysLink links={cur.links} one />
          </div>
          <div><div className="h1" style={{ fontSize: 20 }}>{cur.subject || '(sem assunto)'}</div>
            <div className="small muted">{cur.sender} · {fmtDateTime(cur.last_at)}{cur.suggested_label && <> · sugestão: <b>{cur.suggested_label}</b>{cur.suggested_reason && <> ({cur.suggested_reason})</>}</>}</div></div>
          {thread.loading && !thread.data ? <Loading rows={5} /> : thread.error ? <ErrorState error={thread.error} retry={thread.reload} /> : thread.data && !thread.data.connected ? <Banner tone="warn">Não deu para ler o corpo: {thread.data.reason}</Banner> :
            (thread.data?.messages || []).map(m => <div className="msg-b" key={m.message_id}>
              <div className="hd"><b>{m.de}</b><span>para {m.para}</span><span className="mono">{m.data}</span></div>
              <CorpoHtml eid={cur.id} m={m} />
              {m.anexos && m.anexos.length > 0 && <div className="small muted" style={{ marginTop: 6 }}>Anexos: {m.anexos.map(a => a.nome).join(', ')}</div>}
            </div>)}
        </>}
      </div>
    </div>
  </>
}

// ------------------------------------------------------------- QuickBooks
const ABERTA = (i: Invoice) => ['open', 'sent', 'overdue'].includes(i.status || '') && (i.balance || 0) > 0
const CAD_PT: Record<string, string> = { daily: 'diário', weekly: 'semanal', custom: 'personalizado' }
export function cadenciaTexto(i: Invoice) { return i.reminder_cadence === 'custom' ? `a cada ${i.reminder_every_days} d` : CAD_PT[i.reminder_cadence || ''] || '' }

/** Estado do lembrete de uma invoice, com o toggle (dono, 16/09). */
export function LembreteChip({ i, onChange }: { i: Invoice; onChange: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  if (!i.reminder_id) return <span className="muted small">—</span>
  const on = !!i.reminder_enabled
  async function toggle() {
    setBusy(true)
    try { await api.patch(`/invoice-reminders/${i.reminder_id}`, { enabled: !on }); toast(on ? 'Lembrete desligado.' : 'Lembrete ligado. Vai no próximo dia útil da rotina (09:00).', 'ok'); onChange() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <span className="row" style={{ gap: 6 }}>
    <Status kind={on ? 'ok' : 'off'} label={on ? `${cadenciaTexto(i)} · próx. ${fmtDate(i.reminder_next_on)}` : `desligado · ${cadenciaTexto(i)}`} />
    {i.reminder_sent_count ? <span className="small muted mono" title={i.reminder_last_sent_at ? `último ${fmtDateTime(i.reminder_last_sent_at)}` : ''}>{i.reminder_sent_count}×</span> : null}
    {i.reminder_note && <span className="small muted" title={i.reminder_note}>▲</span>}
    {can('MANAGER') && <button className={`btn sm${on ? '' : ' quiet'}`} disabled={busy} onClick={e => { e.stopPropagation(); toggle() }} title={on ? 'Desligar o lembrete' : 'Ligar o lembrete'} aria-pressed={on}>{busy ? <Spinner /> : on ? 'ligado' : 'ligar'}</button>}
  </span>
}

/** Configurar lembretes das invoices escolhidas: diário, semanal ou a cada N dias; ligado/desligado; enviar agora. */
export function LembreteModal({ invoices, onClose, onDone }: { invoices: Invoice[]; onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const perguntar = usePerguntar()
  const base = invoices.find(i => i.reminder_id)
  const [cad, setCad] = useState<'daily' | 'weekly' | 'custom'>(base?.reminder_cadence || 'weekly')
  const [every, setEvery] = useState<number>(base?.reminder_every_days || 3)
  const [on, setOn] = useState<boolean>(base ? !!base.reminder_enabled : true)
  const [busy, setBusy] = useState<'save' | 'now' | null>(null)
  const abertas = invoices.filter(ABERTA)
  const total = abertas.reduce((s, i) => s + (i.balance || 0), 0)
  async function salvar() {
    setBusy('save')
    try { await api.put('/invoice-reminders', { invoice_ids: abertas.map(i => i.id), cadence: cad, every_days: cad === 'custom' ? every : undefined, enabled: on }); toast(on ? `Lembrete ${cad === 'custom' ? `a cada ${every} dias` : CAD_PT[cad]} ligado em ${abertas.length} invoice(s). Sai às 09:00 de cada dia devido.` : 'Lembrete guardado desligado.', 'ok'); onDone(); onClose() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function agora() {
    if (!await perguntar({ titulo: `Enviar o lembrete agora para ${abertas.length} invoice(s)?`, texto: `Reenvia cada invoice por e-mail pelo QuickBooks, para o e-mail de cobrança dela. Total em aberto: ${money(total)}.\n\nIsso sai da empresa agora.`, ok: 'Enviar agora ↗', perigo: true })) return
    setBusy('now')
    try { const r = await api.post<{ enviados: number; detalhe: { invoice_id: number; ok: boolean; motivo?: string; aplicado?: boolean }[] }>('/invoice-reminders/send-now', { invoice_ids: abertas.map(i => i.id) }); const falhas = r.detalhe.filter(d => !d.ok); const sim = r.detalhe.some(d => d.ok && !d.aplicado); toast(`${r.enviados} lembrete(s) enviado(s)${sim ? ' — em simulação (APLICAR=0), nada saiu de verdade' : ''}${falhas.length ? `; ${falhas.length} não: ${falhas[0].motivo}` : ''}.`, falhas.length ? 'crit' : 'ok'); onDone() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label="Fechar">✕</button>
    <div><div className="small muted cond">QuickBooks · lembretes</div><h2 className="h1" style={{ fontSize: 22 }}>Lembrete de {abertas.length} invoice(s) em aberto</h2>
      <div className="small ink2">{abertas.map(i => `${i.doc_number || '#' + i.id}${i.pilot_name || i.client_name ? ` (${i.pilot_name || i.client_name})` : ''}`).join(' · ')} — {money(total)} em aberto.{invoices.length > abertas.length && <> <b>{invoices.length - abertas.length}</b> ficaram de fora por já estarem pagas.</>}</div></div>
    <div className="field"><label>Com que frequência</label>
      <div className="row wrap" style={{ gap: 8 }}>
        {(['daily', 'weekly', 'custom'] as const).map(c => <button key={c} className={`btn sm${cad === c ? ' on' : ''}`} onClick={() => setCad(c)} aria-pressed={cad === c}>{c === 'daily' ? 'Diário' : c === 'weekly' ? 'Semanal' : 'A cada N dias'}</button>)}
        {cad === 'custom' && <span className="row" style={{ gap: 6 }}><input className="input" type="number" min={1} max={90} value={every} onChange={e => setEvery(Math.max(1, Math.min(90, Number(e.target.value) || 1)))} style={{ width: 80 }} aria-label="Dias" /> <span className="small muted">dias</span></span>}
      </div></div>
    <label className="check"><input type="checkbox" checked={on} onChange={e => setOn(e.target.checked)} /> lembrete ligado {on ? '— começa hoje, às 09:00 (ou amanhã, se já passou)' : '— fica guardado, não envia'}</label>
    <div className="small muted">Cada envio é o reenvio da invoice pelo QuickBooks, para o e-mail de cobrança. Invoice paga desliga o lembrete sozinha. Tudo fica na auditoria.</div>
    <div className="row wrap" style={{ justifyContent: 'flex-end' }}><button className="btn quiet" disabled={!!busy || abertas.length === 0} onClick={agora} title="Manda o lembrete agora, sem esperar as 09:00">{busy === 'now' ? <Spinner /> : 'Enviar agora ↗'}</button><button className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={!!busy || abertas.length === 0} onClick={salvar}>{busy === 'save' ? <Spinner /> : 'Salvar'}</button></div>
  </div></Scrim>
}

export function QuickBooksPage() {
  const { can } = useAuth()
  const [sp] = useSearchParams()
  const ints = useGet<Integration[]>('/integrations', 60000)
  const i = ints.data?.find(x => x.system === 'quickbooks')
  const connected = i?.status === 'CONNECTED'
  const sum = useGet<QboSummary>(can('MANAGER') ? '/qbo/summary' : null, 120000)
  const inv = useGet<Invoice[]>(can('MANAGER') && connected ? '/invoices' : null, 120000)
  const [st, setSt] = useTab<string>('s', 'all')
  const [q, setQ] = useTab<string>('q', '')
  const [vmin, setVmin] = useTab<string>('min', '')
  const [vmax, setVmax] = useTab<string>('max', '')
  const [de, setDe] = useTab<string>('de', '')
  const [ate, setAte] = useTab<string>('ate', '')
  const [campo, setCampo] = useTab<'due_on' | 'issued_on'>('d', 'due_on')
  const [sel, setSel] = useState<number[]>([])
  const [lemb, setLemb] = useState(false)
  const norm = (s: string) => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  const qn = norm(q.trim())
  // Filtros (dono, 16/09): valor, período (por vencimento ou emissão), cliente, número e palavras da invoice (memo).
  const rows = (inv.data || []).filter(x => (st === 'all' || (st === 'aberto' ? ABERTA(x) : st === 'lembrete' ? !!x.reminder_enabled : x.status === st))
    && (!qn || [x.doc_number, x.client_name, x.pilot_name, x.memo, x.customer_email].some(v => norm(v || '').includes(qn)))
    && (!vmin || (x.amount || 0) >= Number(vmin)) && (!vmax || (x.amount || 0) <= Number(vmax))
    && (!de || (x[campo] || '') >= de) && (!ate || (x[campo] || '') <= ate))
  const somaAberto = rows.reduce((s, x) => s + (x.balance || 0), 0)
  const filtrando = !!(qn || vmin || vmax || de || ate || st !== 'all')
  const limpar = () => { setQ(''); setVmin(''); setVmax(''); setDe(''); setAte(''); setSt('all') }
  const abertasNaTela = rows.filter(ABERTA)
  const selecionadas = rows.filter(x => sel.includes(x.id))
  const toggleSel = (id: number) => setSel(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])
  const det = safeJson(i?.detail) as { nota?: string; realm_id?: string; empresa?: string } | null
  return <>
    <IntHeader system="quickbooks" title="QuickBooks" desc="Invoices e pagamentos da URACE US INC. A IA prepara; enviar pede aprovação. Nunca apaga." openHref="https://qbo.intuit.com/" openLabel="Abrir o QuickBooks" />
    {sp.get('connected') && <Banner tone="ok">QuickBooks conectado. Rode “Sincronizar agora” no Dashboard para trazer as invoices.</Banner>}
    {sp.get('erro') && <Banner tone="crit">A Intuit devolveu erro no consentimento: {sp.get('erro')}</Banner>}
    {!connected && <div className="card card-b stack">
      <div className="h2">Conectar</div>
      <div className="small ink2">Três passos, todos no <code>docs/adminai/quickbooks-conexao.md</code>: (1) chaves de produção do app na Intuit com a redirect URI <span className="mono">https://urace-bridge.duckdns.org/ops/api/qbo/callback</span>; (2) as chaves no servidor; (3) o botão abaixo, que abre a tela de autorização da Intuit e volta para cá.</div>
      {i?.last_error && <Banner tone="warn">Último erro: {i.last_error}</Banner>}
      <div className="row">{can('ADMIN') ? <a className="btn primary" href="/ops/api/qbo/connect">Conectar QuickBooks</a> : <span className="muted small">Só o administrador conecta.</span>}<span className="small muted">{det?.nota}</span></div>
    </div>}
    {!can('MANAGER') && <Banner tone="info">Valores financeiros são visíveis para gerentes e administradores.</Banner>}
    {can('MANAGER') && sum.data && <div className="grid g3">
      <div className="card kpi"><div className="lbl">Em aberto</div><div className="val">{connected ? money(sum.data.open.total) : '—'}</div><div className="foot">{connected ? `${sum.data.open.count} invoice(s)` : 'conecte para ver'}</div></div>
      <div className="card kpi"><div className="lbl">Vencidas</div><div className={`val${sum.data.overdue.count ? ' crit' : ''}`}>{connected ? money(sum.data.overdue.total) : '—'}</div><div className="foot">{connected ? `${sum.data.overdue.count} invoice(s)` : 'conecte para ver'}</div></div>
      <div className="card kpi"><div className="lbl">Emitidas e pagas (30 d)</div><div className="val ok">{connected ? money(sum.data.paid_30d.total) : '—'}</div><div className="foot">{connected ? `${sum.data.paid_30d.count} invoice(s)` : 'conecte para ver'}</div></div>
    </div>}
    {can('MANAGER') && connected && !!sum.data?.top_debtors.length && <Section title="Maiores saldos em aberto" tight>
      <table className="tbl"><tbody>{sum.data.top_debtors.map(d => <tr key={d.id} className="click" onClick={() => window.location.assign(`/ops/clients?open=${d.id}`)}><td>{d.pilot_name || d.name}{d.pilot_name && <div className="small muted">{d.name}</div>}</td><td className="mono">{d.n} invoice(s)</td><td className="mono right">{money(d.balance)}</td></tr>)}</tbody></table>
      <div className="small muted" style={{ padding: '8px 14px' }}>Saldo em aberto não é inadimplência: existe parcelamento. Cobrança é por lote (decisão de 31/08).</div>
    </Section>}
    {can('MANAGER') && connected && <>
      <div className="card card-b stack" style={{ gap: 8 }}>
        <div className="row wrap toolbar-page">
          <input className="input" style={{ maxWidth: 300 }} placeholder="Nº, cliente, piloto, e-mail ou palavra da invoice" value={q} onChange={e => setQ(e.target.value)} aria-label="Buscar invoice" />
          <select className="input" style={{ width: 170 }} value={st} onChange={e => setSt(e.target.value)} aria-label="Status"><option value="all">Todas</option><option value="aberto">Com saldo</option><option value="overdue">Vencidas</option><option value="open">Em aberto</option><option value="sent">Enviadas</option><option value="paid">Pagas</option><option value="lembrete">Com lembrete ligado</option></select>
          <span className="row" style={{ gap: 6 }}><span className="small muted">valor</span><input className="input" type="number" style={{ width: 96 }} placeholder="de" value={vmin} onChange={e => setVmin(e.target.value)} aria-label="Valor mínimo" /><input className="input" type="number" style={{ width: 96 }} placeholder="até" value={vmax} onChange={e => setVmax(e.target.value)} aria-label="Valor máximo" /></span>
          <span className="row" style={{ gap: 6 }}><select className="input" style={{ width: 120 }} value={campo} onChange={e => setCampo(e.target.value as 'due_on')} aria-label="Data por"><option value="due_on">vence</option><option value="issued_on">emitida</option></select><input className="input" type="date" style={{ width: 150 }} value={de} onChange={e => setDe(e.target.value)} aria-label="De" /><input className="input" type="date" style={{ width: 150 }} value={ate} onChange={e => setAte(e.target.value)} aria-label="Até" /></span>
          {filtrando && <button className="btn quiet sm" onClick={limpar}>limpar</button>}
        </div>
        <div className="row wrap small muted"><span><b className="ink2">{rows.length}</b> invoice(s){filtrando ? ' no filtro' : ''} · <b className="ink2">{money(somaAberto)}</b> em aberto</span><span className="grow" />
          {abertasNaTela.length > 0 && <><button className="btn sm" onClick={() => setSel(s => s.length === abertasNaTela.length ? [] : abertasNaTela.map(x => x.id))}>{sel.length === abertasNaTela.length ? 'desmarcar todas' : `marcar as ${abertasNaTela.length} com saldo`}</button>
          <button className="btn primary sm" disabled={selecionadas.length === 0} onClick={() => setLemb(true)}>⏰ Lembretes{selecionadas.length ? ` (${selecionadas.length})` : ''}</button></>}</div>
      </div>
      <Section title="Invoices" count={rows.length} tight>
      {inv.error && !inv.data ? <ErrorState error={inv.error} retry={inv.reload} /> : inv.loading && !inv.data ? <Loading /> : rows.length === 0 ? <Empty>{filtrando ? 'Nada bate com o filtro.' : 'Nenhuma invoice espelhada. Sincronize no Dashboard.'}</Empty> :
        <div className="tbl-wrap"><table className="tbl rsp"><thead><tr><th></th><th>Nº</th><th>Cliente</th><th className="hide-md">Emitida</th><th>Vence</th><th>Valor</th><th>Saldo</th><th>Status</th><th>Lembrete</th><th></th></tr></thead><tbody>
          {rows.map(x => <tr key={x.id} className={sel.includes(x.id) ? 'on' : ''}><td>{ABERTA(x) && <input type="checkbox" checked={sel.includes(x.id)} onChange={() => toggleSel(x.id)} aria-label={`Selecionar ${x.doc_number}`} />}</td><td className="mono first" data-l="Nº">{x.doc_number}{x.memo && <div className="small muted truncate" style={{ maxWidth: 220 }} title={x.memo}>{x.memo}</div>}</td><td data-l="Cliente">{x.client_id ? <a href={`/ops/clients?open=${x.client_id}`}>{x.pilot_name || x.client_name}</a> : <span className="muted">não vinculado</span>}</td><td className="mono hide-md" data-l="Emitida">{fmtDate(x.issued_on)}</td><td className="mono" data-l="Vence">{fmtDate(x.due_on)}</td><td className="mono" data-l="Valor">{money(x.amount)}</td><td className="mono" data-l="Saldo">{money(x.balance)}</td><td data-l="Status"><Status s={x.status} /></td><td data-l="Lembrete"><LembreteChip i={x} onChange={inv.reload} /></td><td><SysLink links={x.links} one /></td></tr>)}
        </tbody></table></div>}
      </Section>
      {lemb && <LembreteModal invoices={selecionadas} onClose={() => setLemb(false)} onDone={() => { inv.reload(); setSel([]) }} />}
    </>}
  </>
}
