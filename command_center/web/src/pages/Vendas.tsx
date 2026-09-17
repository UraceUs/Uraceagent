/* Vendas: o fluxo do closer (dono, 17/09 — aprovado no canvas antes de virar código).
 *
 * Oportunidade não é cliente. Uma tela por oportunidade: ficha, ações, follow-ups, e a
 * conversa com a IA ali mesmo (ditando, se quiser). "Fechar venda" abre a folha que dispara
 * tudo de uma vez — cliente, QuickBooks, waiver, Asana, Kommo — e depois vira acompanhamento,
 * com botão manual por passo e tarefas personalizadas.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Scrim, Spinner, type Tone } from '../components/ui'
import { Icon } from '../components/Icon'
import { Mic, Ouvir, TextoComVoz } from '../components/Voz'
import { diaLocal, fmtDate, fmtDateTime, fmtTime, hojeLocal, money } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'
import { Bolha } from './AI'
import type { AiCommand } from '../api/types'

export interface Opp {
  id: number; name: string; email: string | null; phone: string | null
  pilot_name: string | null; pilot_age: number | null
  service: string | null; service_date: string | null; service_time: string | null; amount: number | null
  stage: string; source: string | null; closer_user_id: number | null; closer_name?: string | null
  client_id: number | null; crm_lead_id: number | null
  next_at: string | null; next_what: string | null; lost_reason: string | null; notes: string | null
  closing: Fechamento | null; calls?: number; updated_at: string; created_at: string
  client_name?: string | null; client_pilot?: string | null
}
interface Passo { passo: string; nome: string; ok: boolean | null; detalhe: string; client_id?: number; invoice?: string; envelope?: string; tarefa?: string }
interface Fechamento { em: string; por: string; na_tabela: boolean | null; aprovado?: boolean; motivo_preco?: string; passos: Passo[] }
interface Evento { id: number; kind: string; title: string | null; detail: unknown; at: string; actor: string | null; ok: number | null }
interface Coluna { etapa: string; nome: string; total: number; valor: number; oportunidades: Opp[] }
interface Board { colunas: Coluna[]; abertas: number; retornos_hoje: number; atrasados: number; so_minhas: boolean }
interface Detalhe { oportunidade: Opp; eventos: Evento[]; etapas: { codigo: string; nome: string }[]; resultados: { codigo: string; nome: string }[] }
interface Agenda { retornos: (Opp & { atrasado: boolean })[]; ligacoes_hoje: { at: string; title: string; name: string }[] }

const ETAPA_TOM: Record<string, Tone> = { NOVO: 'neutral', CONVERSA: 'info', PROPOSTA: 'warn', FECHAMENTO: 'accent', GANHO: 'ok', PERDIDO: 'crit' }
const ETAPA_PT: Record<string, string> = { NOVO: 'Novo', CONVERSA: 'Em conversa', PROPOSTA: 'Proposta', FECHAMENTO: 'Fechamento', GANHO: 'Ganho', PERDIDO: 'Perdido' }
const KIND_ICONE: Record<string, string> = { call: 'phone', email: 'mail', note: 'pencil', stage: 'target', waiver: 'doc', invoice: 'dollar', asana: 'list', kommo: 'chat', client: 'people', task: 'check', next: 'clock', ia: 'spark' }
const CANAL_ICONE = (s?: string | null) => { const t = (s || '').toLowerCase(); return t.includes('insta') ? 'instagram' : t.includes('face') || t.includes('messenger') ? 'facebook' : t.includes('whats') ? 'whatsapp' : t.includes('liga') || t.includes('call') ? 'phone' : t.includes('site') || t.includes('web') ? 'globe' : 'target' }
const nomeDo = (o: Opp) => o.pilot_name && o.pilot_name !== o.name ? `${o.name} · piloto ${o.pilot_name}` : o.name
const paraInput = (iso?: string | null) => (iso ? iso.slice(0, 16) : '')
const paraISO = (local: string) => (local ? new Date(local).toISOString() : '')

// ------------------------------------------------------------------ quadro
export function Oportunidades() {
  const { can, user } = useAuth()
  const nav = useNavigate()
  // vendas é área do operador: todos veem tudo, e quem quiser filtra as suas (dono, 17/09)
  const [soMinhas, setSoMinhas] = useState(false)
  const b = useGet<Board>(`/sales/board${soMinhas ? '?minhas=1' : ''}`, 30000)
  const [nova, setNova] = useState(false)
  const [busca, setBusca] = useState('')
  if (b.loading && !b.data) return <Loading rows={5} />
  if (b.error) return <ErrorState error={b.error} retry={b.reload} />
  const d = b.data!
  const filtra = (o: Opp) => !busca || `${o.name} ${o.pilot_name || ''} ${o.email || ''} ${o.phone || ''} ${o.service || ''}`.toLowerCase().includes(busca.toLowerCase())
  return <div className="stack">
    <PageHeader title="Oportunidades" eyebrow={`Vendas · ${user?.name?.split(' ')[0] || ''}`}
      help={<>Quem está perto de fechar. Oportunidade não é cliente: só vira card de cliente quando a venda fecha.</>}>
      <div className="row" style={{ gap: 8 }}>
        <input className="input" style={{ width: 220 }} placeholder="Buscar nome, telefone…" value={busca} onChange={e => setBusca(e.target.value)} />
        <Mic valor={busca} onTexto={setBusca} titulo="Ditar a busca" />
        <button className={`btn${soMinhas ? ' on' : ''}`} onClick={() => setSoMinhas(v => !v)} title={soMinhas ? 'Mostrando só as suas' : 'Mostrando as de todos'}>
          <Icon name="user" size={16} /> {soMinhas ? 'Só minhas' : 'Todas'}
        </button>
        <Link className="btn" to="/sales/agenda"><Icon name="cal" size={16} /> Agenda</Link>
        {can('OPERATOR') && <button className="btn primary" onClick={() => setNova(true)}><Icon name="plus" size={16} /> Nova oportunidade</button>}
      </div>
    </PageHeader>

    <div className="strip">
      <div className="it"><span className="lbl">Abertas</span><span className="val">{d.abertas}</span></div>
      <div className="it link" onClick={() => nav('/sales/agenda')}><span className="lbl">Retornos hoje</span><span className="val">{d.retornos_hoje}</span></div>
      <div className="it link" onClick={() => nav('/sales/agenda')}><span className="lbl">Atrasados</span><span className={`val ${d.atrasados ? 'crit' : ''}`}>{d.atrasados}</span></div>
      <div className="it"><span className="lbl">Em proposta</span><span className="val">{money(d.colunas.find(c => c.etapa === 'PROPOSTA')?.valor || 0)}</span></div>
      <div className="it"><span className="lbl">Em fechamento</span><span className="val">{money(d.colunas.find(c => c.etapa === 'FECHAMENTO')?.valor || 0)}</span></div>
    </div>

    <div className="board">
      {d.colunas.map(c => <div className={`col${c.etapa === 'FECHAMENTO' ? ' today' : ''}`} key={c.etapa}>
        <div className="ch"><span className="truncate">{c.nome}</span><span className="count">{c.total}{c.valor ? ` · ${money(c.valor)}` : ''}</span></div>
        <div className="cards">
          {c.oportunidades.filter(filtra).length === 0 && <div className="small muted" style={{ padding: 8 }}>vazia</div>}
          {c.oportunidades.filter(filtra).map(o => <button className={`tcard lead${o.next_at && o.next_at < new Date().toISOString() ? ' esperando' : ''}`} key={o.id} onClick={() => nav(`/sales/${o.id}`)}>
            <div className="row wrap" style={{ gap: 6 }}><b className="truncate">{o.name}</b>{!!o.amount && <span className="mono small">{money(o.amount)}</span>}</div>
            <div className="row wrap small muted" style={{ gap: 6 }}>
              <Icon name={CANAL_ICONE(o.source)} size={13} />{o.source || 'sem origem'}
              {!!o.calls && <span>· {o.calls} ligação(ões)</span>}
            </div>
            {o.service && <div className="small truncate">{o.service}{o.service_date ? ` · ${fmtDate(o.service_date)}` : ''}</div>}
            {o.next_at && <div className="small" style={{ color: o.next_at < new Date().toISOString() ? 'var(--crit)' : 'var(--warn)' }}>
              <Icon name="clock" size={12} /> {fmtDateTime(o.next_at)}{o.next_what ? ` · ${o.next_what}` : ''}</div>}
            {o.stage === 'GANHO' && o.client_id && <div className="small" style={{ color: 'var(--ok)' }}>virou cliente</div>}
            {o.stage === 'PERDIDO' && o.lost_reason && <div className="small muted truncate">motivo: {o.lost_reason}</div>}
          </button>)}
        </div>
      </div>)}
    </div>
    {nova && <NovaOportunidade onClose={() => setNova(false)} onCriada={id => { setNova(false); nav(`/sales/${id}`) }} />}
  </div>
}

function NovaOportunidade({ onClose, onCriada, lead }: { onClose: () => void; onCriada: (id: number) => void; lead?: number }) {
  const toast = useToast()
  const [f, setF] = useState({ name: '', phone: '', email: '', pilot_name: '', pilot_age: '', service: '', amount: '', source: 'Ligação', notes: '' })
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof f) => (v: string) => setF(x => ({ ...x, [k]: v }))
  async function criar() {
    if (!f.name.trim()) { toast('Diga o nome de quem você falou.', 'crit'); return }
    setBusy(true)
    try {
      const r = await api.post<{ id: number; ja_e_cliente?: { id: number; nome: string } }>('/sales', {
        name: f.name, phone: f.phone || undefined, email: f.email || undefined, pilot_name: f.pilot_name || undefined,
        pilot_age: f.pilot_age ? Number(f.pilot_age) : undefined, service: f.service || undefined,
        amount: f.amount ? Number(f.amount) : undefined, source: f.source, notes: f.notes || undefined, crm_lead_id: lead,
      })
      toast(r.ja_e_cliente ? `Criada. Atenção: ${r.ja_e_cliente.nome} já é cliente — no fechamento o painel liga no card dele.` : 'Oportunidade criada.', 'ok')
      onCriada(r.id)
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 640 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label="Fechar" title="Fechar (Esc)"><Icon name="x" size={16} /></button>
    <div><div className="small muted cond">Vendas</div><h2 className="h1" style={{ fontSize: 22 }}>Nova oportunidade</h2>
      <div className="small muted">Durante a ligação: só o nome é obrigatório, o resto entra depois. Todo campo aceita ditado.</div></div>
    <div className="grid g2">
      <div className="field"><label>Quem decide (responsável)</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.name} onChange={e => set('name')(e.target.value)} autoFocus /><Mic valor={f.name} onTexto={set('name')} /></div></div>
      <div className="field"><label>Telefone</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.phone} onChange={e => set('phone')(e.target.value)} placeholder="+1 407…" /><Mic valor={f.phone} onTexto={set('phone')} /></div></div>
      <div className="field"><label>E-mail</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.email} onChange={e => set('email')(e.target.value)} /><Mic valor={f.email} onTexto={t => set('email')(t.replace(/\s+/g, '').replace(/arroba/gi, '@'))} /></div></div>
      <div className="field"><label>Origem</label><select className="input" value={f.source} onChange={e => set('source')(e.target.value)}>{['Ligação', 'Instagram', 'Facebook', 'WhatsApp', 'Site', 'Indicação', 'Outra'].map(x => <option key={x}>{x}</option>)}</select></div>
      <div className="field"><label>Piloto (se for outra pessoa)</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.pilot_name} onChange={e => set('pilot_name')(e.target.value)} /><Mic valor={f.pilot_name} onTexto={set('pilot_name')} /></div></div>
      <div className="field"><label>Idade do piloto</label><input className="input" type="number" value={f.pilot_age} onChange={e => set('pilot_age')(e.target.value)} placeholder="decide a waiver" /></div>
      <div className="field"><label>Interesse (serviço)</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.service} onChange={e => set('service')(e.target.value)} /><Mic valor={f.service} onTexto={set('service')} /></div></div>
      <div className="field"><label>Valor estimado</label><input className="input" type="number" step="0.01" value={f.amount} onChange={e => set('amount')(e.target.value)} /></div>
    </div>
    <div className="field"><label>Anotação da conversa</label><TextoComVoz valor={f.notes} onChange={set('notes')} linhas={3} placeholder="O que ele falou… (dá para ditar)" /></div>
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" disabled={busy} onClick={criar}>{busy ? <Spinner /> : 'Criar oportunidade'}</button></div>
  </div></Scrim>
}

// ------------------------------------------------------------------ uma oportunidade
export function Oportunidade() {
  const { id } = useParams()
  const oid = Number(id)
  const toast = useToast()
  const perguntar = usePerguntar()
  const { can } = useAuth()
  const d = useGet<Detalhe>(`/sales/${oid}`, 20000)
  const [aba, setAba] = useState<'tudo' | 'call' | 'note'>('tudo')
  const [fechar, setFechar] = useState(false)
  const [ligar, setLigar] = useState(false)
  const [nota, setNota] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const o = d.data?.oportunidade

  async function acao(nome: string, fn: () => Promise<unknown>, msg: string) {
    setBusy(nome)
    try { await fn(); toast(msg, 'ok'); d.reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function anotar() {
    if (!nota.trim()) return
    await acao('nota', () => api.post(`/sales/${oid}/note`, { texto: nota }), 'Anotado.')
    setNota('')
  }
  async function marcarRetorno() {
    const q = await perguntar({ titulo: 'Agendar retorno', campo: 'Quando (AAAA-MM-DD HH:MM)', valor: paraInput(new Date(Date.now() + 864e5).toISOString()).replace('T', ' ') })
    if (typeof q !== 'string' || !q.trim()) return
    const iso = paraISO(q.trim().replace(' ', 'T'))
    if (!iso) { toast('Data não entendida.', 'crit'); return }
    await acao('ret', () => api.post(`/sales/${oid}/next`, { quando: iso, o_que: 'retorno' }), 'Retorno marcado.')
  }
  async function perdido() {
    const m = await perguntar({ titulo: 'Marcar como perdido', campo: 'Motivo (preço, distância, sem resposta…)', perigo: true, ok: 'Marcar perdido' })
    if (typeof m !== 'string' || !m.trim()) return
    await acao('perd', () => api.post(`/sales/${oid}/stage`, { etapa: 'PERDIDO', motivo: m }), 'Oportunidade fechada como perdida.')
  }

  if (d.loading && !d.data) return <Loading rows={6} />
  if (d.error) return <ErrorState error={d.error} retry={d.reload} />
  if (!o) return null
  const atrasado = !!o.next_at && o.next_at < new Date().toISOString()
  const evs = (d.data?.eventos || []).filter(e => aba === 'tudo' || e.kind === aba)
  const passos = o.closing?.passos || []
  return <div className="stack">
    <div className="row wrap" style={{ gap: 8 }}>
      <Link className="small" to="/sales">← Oportunidades</Link>
      <span className="grow" />
      {o.crm_lead_id && <Link className="btn sm" to={`/crm/chat?lead=${o.crm_lead_id}`}><Icon name="chat" size={15} /> Chat</Link>}
      {o.client_id && <Link className="btn sm" to={`/clients/${o.client_id}`}><Icon name="people" size={15} /> Card do cliente</Link>}
    </div>

    <div className="c360-h">
      <div className="who">
        <div className="row wrap" style={{ gap: 10 }}>
          <h1 className="h1" style={{ fontSize: 30 }}>{o.name}</h1>
          <Chip tone={ETAPA_TOM[o.stage]}>{ETAPA_PT[o.stage]}</Chip>
          {o.source && <Chip tone="neutral"><Icon name={CANAL_ICONE(o.source)} size={13} /> {o.source}</Chip>}
          {o.closer_name && <Chip tone="outline">closer: {o.closer_name.split(' ')[0]}</Chip>}
        </div>
        <div className="meta">
          {o.phone && <span><span className="k">tel</span><a href={`tel:${o.phone.replace(/[^\d+]/g, '')}`}>{o.phone}</a></span>}
          {o.email && <span><span className="k">e-mail</span><a href={`mailto:${o.email}`}>{o.email}</a></span>}
          {o.pilot_name && <span><span className="k">piloto</span><b>{o.pilot_name}{o.pilot_age ? `, ${o.pilot_age} anos` : ''}</b></span>}
          {o.service && <span><span className="k">interesse</span><b>{o.service}</b>{o.service_date ? ` · ${fmtDate(o.service_date)}${o.service_time ? ' ' + o.service_time : ''}` : ''}</span>}
          {o.amount !== null && <span><span className="k">valor</span><b>{money(o.amount)}</b></span>}
        </div>
      </div>
      <div className="c360-acts">
        {can('OPERATOR') && <button className="btn primary" onClick={() => setLigar(true)}><Icon name="phone" size={16} /> Registrar ligação</button>}
        {can('OPERATOR') && o.stage !== 'GANHO' && <button className="btn" onClick={() => setFechar(true)}><Icon name="check" size={16} /> Fechar venda</button>}
        {can('OPERATOR') && <button className="btn" disabled={busy === 'ret'} onClick={marcarRetorno}><Icon name="clock" size={16} /> Retorno</button>}
        {can('OPERATOR') && o.stage !== 'PERDIDO' && o.stage !== 'GANHO' && <button className="btn ghost sm" disabled={busy === 'perd'} onClick={perdido}>Perdido</button>}
      </div>
    </div>

    {atrasado && <Banner tone="crit"><b>Retorno atrasado:</b> {fmtDateTime(o.next_at)}{o.next_what ? ` — ${o.next_what}` : ''}. Ligue e registre, ou remarque.</Banner>}
    {!atrasado && o.next_at && <Banner tone="info"><b>Próximo passo:</b> {fmtDateTime(o.next_at)}{o.next_what ? ` — ${o.next_what}` : ''}</Banner>}
    {o.stage === 'GANHO' && <Banner tone="ok"><b>Venda fechada.</b> {passos.filter(p => p.ok).length} de {passos.length} passos concluídos{passos.some(p => p.ok === false) ? ` · falta: ${passos.filter(p => p.ok === false).map(p => p.nome).join(', ')}` : ''}. <button className="btn ghost sm" onClick={() => setFechar(true)}>ver acompanhamento</button></Banner>}

    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)', gap: 14 }}>
      <div className="stack">
        <div className="card">
          <div className="card-h"><h2 className="h2">Histórico</h2><div className="tabs" style={{ marginLeft: 'auto' }}>
            {([['tudo', 'Tudo'], ['call', 'Ligações'], ['note', 'Notas']] as const).map(([k, l]) => <button key={k} className={aba === k ? 'on' : ''} onClick={() => setAba(k)}>{l}</button>)}</div></div>
          <div className="card-b tight">
            {evs.length === 0 && <div style={{ padding: 16 }}><Empty title="Nada registrado ainda">Registre a ligação: resultado, o que ele falou e o próximo passo.</Empty></div>}
            {evs.map(e => <div className="fu" key={e.id} style={{ padding: '10px 16px', display: 'grid', gridTemplateColumns: '92px 20px minmax(0,1fr) auto', gap: '0 10px', borderTop: '1px solid var(--glass-line)' }}>
              <div className="mono small muted">{fmtDate(e.at)}<br />{fmtTime(e.at)}</div>
              <Icon name={KIND_ICONE[e.kind] || 'dot'} size={16} className={e.ok === 0 ? 'muted' : undefined} />
              <div style={{ minWidth: 0 }}><div style={{ fontWeight: 600 }}>{e.title}</div>
                {typeof e.detail === 'string' && e.detail && <div className="small muted" style={{ whiteSpace: 'pre-wrap' }}>{e.detail}</div>}
                {typeof e.detail === 'object' && e.detail !== null && <div className="small muted mono">{JSON.stringify(e.detail).slice(0, 180)}</div>}</div>
              <div>{e.actor === 'ia' ? <Chip tone="accent">IA</Chip> : e.ok === 0 ? <Chip tone="crit">não</Chip> : null}</div>
            </div>)}
          </div>
        </div>

        {can('OPERATOR') && <div className="card card-b stack">
          <label className="small muted">Anotação (interna)</label>
          <TextoComVoz valor={nota} onChange={setNota} linhas={2} placeholder="O que combinou, o que ele pediu… (Enter guarda)" onEnter={anotar} />
          <div className="row"><button className="btn sm" disabled={busy === 'nota' || !nota.trim()} onClick={anotar}>{busy === 'nota' ? <Spinner /> : 'Guardar anotação'}</button></div>
        </div>}
      </div>

      <div className="stack">
        <IAdaVenda o={o} onDone={() => d.reload()} />
        {o.notes && <div className="card card-b"><div className="h2" style={{ marginBottom: 6 }}>Anotações</div><div className="small ink2" style={{ whiteSpace: 'pre-wrap' }}>{o.notes}</div></div>}
        <div className="card card-b stack" style={{ gap: 6 }}>
          <div className="h2">O que já saiu</div>
          {passos.length === 0 && <div className="small muted">Nada enviado ainda. No fechamento, o painel faz tudo de uma vez.</div>}
          {passos.map(p => <div key={p.passo} className="row" style={{ gap: 8 }}>
            <Icon name={p.ok ? 'check' : p.ok === false ? 'x' : 'clock'} size={15} className={p.ok ? undefined : 'muted'} />
            <span className="small" style={{ color: p.ok === false ? 'var(--crit)' : undefined }}>{p.nome}</span>
            <span className="small muted truncate" style={{ marginLeft: 'auto', maxWidth: 160 }}>{p.detalhe}</span>
          </div>)}
        </div>
      </div>
    </div>

    {ligar && <RegistrarLigacao o={o} resultados={d.data!.resultados} onClose={() => setLigar(false)} onOk={() => { setLigar(false); d.reload() }} onFechar={() => { setLigar(false); setFechar(true) }} />}
    {fechar && <FecharVenda o={o} onClose={() => setFechar(false)} onOk={() => { d.reload() }} />}
  </div>
}

/** A IA dentro da venda: o closer fala (ou escreve) e ela age na oportunidade dele. */
function IAdaVenda({ o, onDone }: { o: Opp; onDone: () => void }) {
  const toast = useToast()
  const [texto, setTexto] = useState('')
  const [cid, setCid] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const c = useGet<AiCommand>(cid ? `/ai/commands/${cid}` : null, cid ? 2500 : undefined)
  const rodando = c.data?.status === 'QUEUED' || c.data?.status === 'RUNNING'
  useEffect(() => { if (c.data && !rodando) onDone() }, [c.data?.status]) // eslint-disable-line react-hooks/exhaustive-deps
  const contexto = `[oportunidade #${o.id} — ${o.name}${o.pilot_name ? ` (piloto ${o.pilot_name})` : ''}${o.service ? `, ${o.service}` : ''}${o.amount !== null ? `, ${money(o.amount)}` : ''}, etapa ${ETAPA_PT[o.stage]}]`
  async function mandar() {
    const t = texto.trim()
    if (!t || busy) return
    setBusy(true)
    try { const r = await api.post<{ id: number }>('/ai/commands', { text: `${contexto} ${t}` }); setCid(r.id); setTexto('') }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  const sugestoes = ['Registre que ele pediu para ligar amanhã às 10h', 'Marque retorno para sexta 9h', 'Envie a waiver para ele', 'Feche essa venda', 'Anote: mãe decide junto']
  return <div className="card card-b stack" style={{ gap: 8 }}>
    <div className="row" style={{ gap: 8 }}><span className="icbox red"><Icon name="spark" /></span>
      <div><div style={{ fontWeight: 600 }}>Falar com a IA</div><div className="xs muted">ela age nesta oportunidade: registrar, agendar, waiver, invoice, fechar</div></div></div>
    <TextoComVoz valor={texto} onChange={setTexto} linhas={2} placeholder="Fale ou escreva… (Enter envia)" onEnter={mandar} disabled={busy} />
    <div className="row wrap" style={{ gap: 6 }}>
      <button className="btn primary sm" disabled={busy || !texto.trim()} onClick={mandar}>{busy ? <Spinner /> : 'Pedir à IA'}</button>
      {c.data?.output && <Ouvir texto={c.data.output} titulo="Ouvir a resposta" />}
    </div>
    <div className="sug">{sugestoes.map(s => <button key={s} onClick={() => setTexto(s)}>{s}</button>)}</div>
    {cid && c.data && <div style={{ marginTop: 4 }}><Bolha c={c.data} onChange={() => { c.reload(); onDone() }} /></div>}
  </div>
}

function RegistrarLigacao({ o, resultados, onClose, onOk, onFechar }: { o: Opp; resultados: { codigo: string; nome: string }[]; onClose: () => void; onOk: () => void; onFechar: () => void }) {
  const toast = useToast()
  const [res, setRes] = useState('pensar')
  const [minutos, setMinutos] = useState('')
  const [texto, setTexto] = useState('')
  const [quando, setQuando] = useState('')
  const [oque, setOque] = useState('')
  const [busy, setBusy] = useState(false)
  async function salvar() {
    setBusy(true)
    try {
      await api.post(`/sales/${o.id}/call`, {
        resultado: res, minutos: minutos ? Number(minutos) : undefined, texto: texto || undefined,
        proximo_em: quando ? paraISO(quando) : undefined, proximo_que: oque || undefined,
      })
      toast('Ligação registrada.', 'ok')
      if (res === 'fechou') onFechar()
      else onOk()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label="Fechar"><Icon name="x" size={16} /></button>
    <div><div className="small muted cond">Ligação · {o.name}</div><h2 className="h1" style={{ fontSize: 22 }}>Como foi?</h2></div>
    <div className="row wrap" style={{ gap: 6 }}>{resultados.map(r => <button key={r.codigo} className={`btn sm${res === r.codigo ? ' on' : ''}`} onClick={() => setRes(r.codigo)}>{r.nome}</button>)}</div>
    <div className="grid g2">
      <div className="field"><label>Minutos</label><input className="input" type="number" value={minutos} onChange={e => setMinutos(e.target.value)} /></div>
      <div className="field"><label>Retorno (opcional)</label><input className="input" type="datetime-local" value={quando} onChange={e => setQuando(e.target.value)} /></div>
    </div>
    {quando && <div className="field"><label>O que fazer no retorno</label><div className="row" style={{ gap: 6 }}><input className="input" value={oque} onChange={e => setOque(e.target.value)} placeholder="confirmar sábado e fechar" /><Mic valor={oque} onTexto={setOque} /></div></div>}
    <div className="field"><label>O que ele falou</label><TextoComVoz valor={texto} onChange={setTexto} linhas={3} placeholder="Dite aqui em vez de digitar…" /></div>
    {res === 'fechou' && <Banner tone="info">Ao salvar, abre a tela de fechar a venda: um botão dispara cliente, QuickBooks, waiver, Asana e Kommo.</Banner>}
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onClose}>Cancelar</button>
      <button className="btn primary" disabled={busy} onClick={salvar}>{busy ? <Spinner /> : res === 'fechou' ? 'Registrar e fechar venda' : 'Registrar'}</button></div>
  </div></Scrim>
}

// ------------------------------------------------------------------ fechar venda (a tela única)
interface Extra { titulo: string; onde: 'painel' | 'asana'; quando: string; notas: string }

function FecharVenda({ o, onClose, onOk }: { o: Opp; onClose: () => void; onOk: () => void }) {
  const toast = useToast()
  const [f, setF] = useState({
    service: o.service || '', service_date: (o.service_date || '').slice(0, 10), service_time: o.service_time || '',
    amount: o.amount !== null ? String(o.amount) : '', preco_tabela: o.amount !== null ? String(o.amount) : '',
    pilot_name: o.pilot_name || '', pilot_age: o.pilot_age !== null ? String(o.pilot_age) : '',
    email: o.email || '', phone: o.phone || '', nota_cliente: '',
  })
  const [passos, setPassos] = useState<Record<string, boolean>>({ cliente: true, qbo: true, waiver: true, asana: true, kommo: !!o.crm_lead_id })
  const [extras, setExtras] = useState<Extra[]>([])
  const [busy, setBusy] = useState(false)
  const [feito, setFeito] = useState<Fechamento | null>(o.closing || null)
  const set = (k: keyof typeof f) => (v: string) => setF(x => ({ ...x, [k]: v }))
  const fora = f.amount && f.preco_tabela && Math.abs(Number(f.amount) - Number(f.preco_tabela)) > 0.009

  async function confirmar() {
    if (!f.service.trim() || !f.amount) { toast('Diga o serviço e o valor fechado.', 'crit'); return }
    setBusy(true)
    try {
      const r = await api.post<{ etapa: string; fechamento: Fechamento }>(`/sales/${o.id}/close`, {
        service: f.service, service_date: f.service_date || undefined, service_time: f.service_time || undefined,
        amount: Number(f.amount), preco_tabela: f.preco_tabela ? Number(f.preco_tabela) : undefined,
        pilot_name: f.pilot_name || undefined, pilot_age: f.pilot_age ? Number(f.pilot_age) : undefined,
        email: f.email || undefined, phone: f.phone || undefined, nota_cliente: f.nota_cliente || undefined,
        passos, extras: extras.filter(e => e.titulo.trim()).map(e => ({ titulo: e.titulo, onde: e.onde, quando: e.quando || undefined, notas: e.notas || undefined })),
      })
      setFeito(r.fechamento)
      const falhou = r.fechamento.passos.filter(p => p.ok === false)
      toast(falhou.length ? `Fechada, mas faltou: ${falhou.map(p => p.nome).join(', ')}` : 'Venda fechada e tudo disparado.', falhou.length ? undefined : 'ok')
      onOk()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  async function refazer(passo: string) {
    setBusy(true)
    try { await api.post(`/sales/${o.id}/step/${passo}`); toast('Feito.', 'ok'); onOk() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }

  const LINHAS: { k: string; nome: string; o_que: string; icone: string }[] = [
    { k: 'cliente', nome: 'Cria o card do cliente', o_que: 'Clientes · responsável, piloto, contato e a anotação', icone: 'people' },
    { k: 'qbo', nome: 'Cliente no QuickBooks e invoice enviada', o_que: fora ? 'valor fora da tabela: a invoice fica esperando o dono' : 'cria o cliente se faltar e manda a invoice do valor fechado', icone: 'dollar' },
    { k: 'waiver', nome: 'Envia a waiver', o_que: `DocuSign · modelo ${f.pilot_age && Number(f.pilot_age) < 18 ? 'parental (piloto menor)' : 'adulto'} · para ${f.email || 'sem e-mail'}`, icone: 'doc' },
    { k: 'asana', nome: 'Cria a tarefa no Asana', o_que: 'quadro U-RACE, com a data do serviço', icone: 'list' },
    { k: 'kommo', nome: 'Fecha no Kommo', o_que: o.crm_lead_id ? 'lead do chat → Closed won' : 'esta oportunidade não veio do chat', icone: 'chat' },
  ]
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 1080 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label="Fechar"><Icon name="x" size={16} /></button>
    <div className="row" style={{ gap: 12 }}>
      <span className="icbox red" style={{ width: 44, height: 44, borderRadius: 14 }}><Icon name="check" size={22} /></span>
      <div><div className="small muted cond">Fechar venda · {o.name}</div><h2 className="h1" style={{ fontSize: 24 }}>{feito ? 'Acompanhamento do fechamento' : 'Uma tela. Confirmou, o painel faz o resto.'}</h2></div>
    </div>

    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.1fr)', gap: 14 }}>
      <div className="stack">
        <div className="h2">O que foi vendido</div>
        <div className="field"><label>Serviço</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.service} onChange={e => set('service')(e.target.value)} /><Mic valor={f.service} onTexto={set('service')} /></div></div>
        <div className="grid g2">
          <div className="field"><label>Data</label><input className="input" type="date" value={f.service_date} onChange={e => set('service_date')(e.target.value)} /></div>
          <div className="field"><label>Hora</label><input className="input" type="time" value={f.service_time} onChange={e => set('service_time')(e.target.value)} /></div>
        </div>
        <div className="grid g2">
          <div className="field"><label>Valor fechado</label><input className="input" type="number" step="0.01" value={f.amount} onChange={e => set('amount')(e.target.value)} /></div>
          <div className="field"><label>Preço da tabela</label><input className="input" type="number" step="0.01" value={f.preco_tabela} onChange={e => set('preco_tabela')(e.target.value)} /></div>
        </div>
        {fora ? <Banner tone="warn">Valor fora da tabela: a venda fecha, o resto sai, e a <b>invoice fica esperando sua aprovação</b> (política do dono).</Banner> : null}
        <div className="grid g2">
          <div className="field"><label>Piloto</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.pilot_name} onChange={e => set('pilot_name')(e.target.value)} /><Mic valor={f.pilot_name} onTexto={set('pilot_name')} /></div></div>
          <div className="field"><label>Idade do piloto</label><input className="input" type="number" value={f.pilot_age} onChange={e => set('pilot_age')(e.target.value)} placeholder="decide a waiver" /></div>
        </div>
        <div className="grid g2">
          <div className="field"><label>E-mail (invoice e waiver)</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.email} onChange={e => set('email')(e.target.value)} /><Mic valor={f.email} onTexto={t => set('email')(t.replace(/\s+/g, '').replace(/arroba/gi, '@'))} /></div></div>
          <div className="field"><label>Telefone</label><input className="input" value={f.phone} onChange={e => set('phone')(e.target.value)} /></div>
        </div>
        <div className="field"><label>Anotação para o card do cliente</label><TextoComVoz valor={f.nota_cliente} onChange={set('nota_cliente')} linhas={2} placeholder="Primeira vez no kart, mãe vai junto…" /></div>
      </div>

      <div className="stack">
        <div className="h2">{feito ? 'Como foi cada passo' : 'O que acontece ao confirmar'}</div>
        <div className="card" style={{ padding: 0 }}>
          {LINHAS.map(l => {
            const p = feito?.passos.find(x => x.passo === l.k)
            return <div className="inset" key={l.k}><div className="it" style={{ padding: '10px 14px' }}>
              <span className={`icbox${p?.ok ? ' ok' : p?.ok === false ? ' crit' : ''}`}><Icon name={l.icone} /></span>
              <div style={{ minWidth: 0 }}><div className="t">{l.nome}</div><div className="s">{p ? p.detalhe : l.o_que}</div></div>
              <div className="r">
                {!feito && <button className={`sw${passos[l.k] ? '' : ' off'}`} aria-label={passos[l.k] ? 'Ligado' : 'Desligado'} onClick={() => setPassos(x => ({ ...x, [l.k]: !x[l.k] }))} />}
                {feito && (p?.ok ? <Chip tone="ok">feito</Chip> : p?.ok === false ? <button className="btn sm" disabled={busy} onClick={() => refazer(l.k)}>tentar de novo</button> : <Chip tone="neutral">—</Chip>)}
              </div>
            </div></div>
          })}
        </div>

        {!feito && <div className="card card-b stack" style={{ gap: 8 }}>
          <div className="row"><b className="small">Tarefa personalizada</b><span className="grow" /><button className="btn ghost sm" onClick={() => setExtras(x => [...x, { titulo: '', onde: 'painel', quando: '', notas: '' }])}><Icon name="plus" size={14} /> adicionar</button></div>
          {extras.length === 0 && <div className="xs muted">Algo diferente para este cliente (mandar um material, avisar o instrutor, cobrar o equipamento). Vai junto no Confirmar.</div>}
          {extras.map((e, i) => <div className="stack" key={i} style={{ gap: 6, borderTop: i ? '1px solid var(--glass-line)' : undefined, paddingTop: i ? 8 : 0 }}>
            <div className="row" style={{ gap: 6 }}>
              <input className="input" placeholder="O que fazer" value={e.titulo} onChange={ev => setExtras(x => x.map((y, j) => j === i ? { ...y, titulo: ev.target.value } : y))} />
              <Mic valor={e.titulo} onTexto={t => setExtras(x => x.map((y, j) => j === i ? { ...y, titulo: t } : y))} />
              <button className="btn ghost sm" onClick={() => setExtras(x => x.filter((_, j) => j !== i))} aria-label="Remover"><Icon name="x" size={14} /></button>
            </div>
            <div className="row" style={{ gap: 6 }}>
              <select className="input" style={{ width: 150 }} value={e.onde} onChange={ev => setExtras(x => x.map((y, j) => j === i ? { ...y, onde: ev.target.value as 'painel' | 'asana' } : y))}>
                <option value="painel">lembrete no painel</option><option value="asana">tarefa no Asana</option>
              </select>
              <input className="input" type="date" style={{ width: 170 }} value={e.quando} onChange={ev => setExtras(x => x.map((y, j) => j === i ? { ...y, quando: ev.target.value } : y))} />
            </div>
          </div>)}
        </div>}

        {feito && feito.passos.filter(p => p.passo.startsWith('extra:')).map(p => <div className="row small" key={p.passo} style={{ gap: 8 }}>
          <Icon name={p.ok ? 'check' : 'x'} size={14} /><span>{p.passo.replace('extra:', '')}</span><span className="muted">{p.detalhe}</span></div>)}

        {!feito ? <div className="row fecha-acao" style={{ gap: 8 }}>
          <button className="btn primary" style={{ flex: '1 1 auto', minHeight: 48 }} disabled={busy} onClick={confirmar}>{busy ? <Spinner /> : <><Icon name="check" size={16} /> Confirmar e fechar a venda</>}</button>
          <button className="btn" onClick={onClose}>Voltar</button>
        </div> : <div className="row" style={{ gap: 8 }}>
          <div className="small muted" style={{ flex: '1 1 auto' }}>Fechada {fmtDateTime(feito.em)} por {feito.por}{feito.motivo_preco ? ` · ${feito.motivo_preco}` : ''}</div>
          <button className="btn" onClick={onClose}>Fechar</button>
        </div>}
      </div>
    </div>
  </div></Scrim>
}

// ------------------------------------------------------------------ agenda de vendas
export function AgendaVendas() {
  const a = useGet<Agenda>('/sales/agenda', 30000)
  const nav = useNavigate()
  const hoje = hojeLocal()
  const por = useMemo(() => {
    const m = new Map<string, (Opp & { atrasado: boolean })[]>()
    for (const o of a.data?.retornos || []) {
      const d = diaLocal(o.next_at)
      m.set(d, [...(m.get(d) || []), o])
    }
    return [...m.entries()].sort()
  }, [a.data])
  if (a.loading && !a.data) return <Loading rows={5} />
  if (a.error) return <ErrorState error={a.error} retry={a.reload} />
  return <div className="stack">
    <PageHeader title="Agenda de vendas" eyebrow="Vendas" help={<>Os retornos que você marcou ao registrar cada ligação. Atrasado fica em vermelho e também aparece em Precisa de atenção.</>}>
      <Link className="btn" to="/sales"><Icon name="target" size={16} /> Oportunidades</Link>
    </PageHeader>
    {por.length === 0 && <Empty title="Nenhum retorno marcado">Ao registrar uma ligação, escolha o próximo passo e a data: ele aparece aqui.</Empty>}
    {por.map(([dia, lista]) => <div className="card" key={dia}>
      <div className="card-h"><h2 className="h2">{dia === hoje ? 'Hoje' : fmtDate(dia)}</h2><span className="count">{lista.length}</span></div>
      <div className="card-b tight">
        {lista.map(o => <div className="att" key={o.id} style={{ cursor: 'pointer' }} onClick={() => nav(`/sales/${o.id}`)}>
          <div className={`lv ${o.atrasado ? 'CRITICAL' : 'MEDIUM'}`} />
          <div className="grow">
            <div className="row wrap" style={{ gap: 8 }}><span className="mono small">{fmtTime(o.next_at)}</span><b>{nomeDo(o)}</b>
              <Chip tone={ETAPA_TOM[o.stage]}>{ETAPA_PT[o.stage]}</Chip>{o.atrasado && <Chip tone="crit">atrasado</Chip>}</div>
            <div className="small muted">{o.next_what || 'retorno'}{o.service ? ` · ${o.service}` : ''}{o.amount ? ` · ${money(o.amount)}` : ''}{o.phone ? ` · ${o.phone}` : ''}</div>
          </div>
          <div className="row" style={{ gap: 6 }}>{o.phone && <a className="btn sm" href={`tel:${o.phone.replace(/[^\d+]/g, '')}`} onClick={e => e.stopPropagation()}><Icon name="phone" size={14} /> ligar</a>}</div>
        </div>)}
      </div>
    </div>)}
    {!!a.data?.ligacoes_hoje.length && <div className="card"><div className="card-h"><h2 className="h2">Ligações de hoje</h2><span className="count">{a.data.ligacoes_hoje.length}</span></div>
      <div className="card-b tight">{a.data.ligacoes_hoje.map((l, i) => <div className="att" key={i}><div className="lv LOW" /><div className="grow">
        <div className="row" style={{ gap: 8 }}><span className="mono small">{fmtTime(l.at)}</span><b>{l.name}</b></div><div className="small muted">{l.title}</div></div></div>)}</div></div>}
  </div>
}

/** Botão "Passar para o closer" usado no chat do Kommo. */
export function PassarParaCloser({ leadId }: { leadId: number }) {
  const nav = useNavigate()
  const toast = useToast()
  const { can } = useAuth()
  const [busy, setBusy] = useState(false)
  const ref = useRef(false)
  if (!can('OPERATOR')) return null
  return <button className="btn sm" disabled={busy} title="Vira oportunidade na área de vendas" onClick={async () => {
    if (ref.current) return
    ref.current = true; setBusy(true)
    try { const r = await api.post<{ id: number; reaproveitada: boolean }>(`/sales/from-lead/${leadId}`); toast(r.reaproveitada ? 'Já existia: abrindo.' : 'Oportunidade criada.', 'ok'); nav(`/sales/${r.id}`) }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false); ref.current = false }
  }}>{busy ? <Spinner /> : <><Icon name="target" size={14} /> Passar para o closer</>}</button>
}
