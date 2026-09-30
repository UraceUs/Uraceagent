/* Site público, visto de dentro (#41): a agenda que o cliente usa na área do cliente.
 * Agendamentos: o que o cliente pediu (confirmar, recusar). Disponibilidade: a semana,
 * os horários, os bloqueios — quem mexe é o gerente; a operação vê. */
import { useMemo, useState } from 'react'
import { NavLink, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Chip, Empty, ErrorState, Loading, PageHeader, Section } from '../components/ui'
import { usePerguntar } from '../components/Perguntar'
import { Picker } from '../components/Unir'
import type { Client } from '../api/types'
import { Link } from 'react-router-dom'
import { useToast } from '../components/Toast'

type Tom = 'warn' | 'info' | 'ok' | 'neutral' | 'accent' | 'crit'
interface Per { open: boolean; spots: number; reason: string | null; capacity: number; used: number }
interface Dia { date: string; weekday: number; any_open: boolean; periods: { manha: Per; tarde: Per; dia: { open: boolean } } }
interface Regra { weekday: number; dia: string; period: 'manha' | 'tarde'; open: boolean; capacity: number }
interface Bloqueio { id: number; date_from: string; date_to: string; period: string; reason: string | null; created_at: string }
interface Cfg { morning_start: string; morning_end: string; afternoon_start: string; afternoon_end: string; auto_confirm: number; horizon_days: number; min_notice_hours: number }
interface Agenda { dias: Dia[]; semana: Regra[]; bloqueios: Bloqueio[]; config_completa: Cfg }
interface Ag { id: number; date: string; period: string; status: string; notes: string | null; decision_note: string | null; created_at: string
  account_name: string; account_email: string; account_phone: string | null; driver: string | null; driver_birth: string | null; client_id: number | null }

const PER: Record<string, string> = { manha: 'Manhã', tarde: 'Tarde', dia: 'Dia todo' }
const ST: Record<string, [string, Tom]> = { pendente: ['esperando confirmação', 'warn'], confirmada: ['confirmada', 'ok'], recusada: ['recusada', 'crit'], cancelada: ['cancelada', 'neutral'] }
const DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
const dbr = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`
const semanaDe = (iso: string) => DIAS[(new Date(iso + 'T12:00:00').getDay() + 6) % 7]
const hojeFL = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
const idade = (iso: string | null) => { if (!iso) return null; const n = new Date(iso + 'T12:00:00'), h = new Date(); return h.getFullYear() - n.getFullYear() - (h < new Date(h.getFullYear(), n.getMonth(), n.getDate()) ? 1 : 0) }

function Agendamentos() {
  const toast = useToast()
  const perguntar = usePerguntar()
  const [filtro, setFiltro] = useState<'pendente' | 'proximas' | 'todas'>('pendente')
  const q = filtro === 'pendente' ? '?status=pendente' : filtro === 'proximas' ? `?de=${hojeFL()}` : ''
  const l = useGet<{ agendamentos: Ag[] }>(`/site/agendamentos${q}`, 30000)
  async function decidir(a: Ag, d: 'confirmar' | 'recusar' | 'cancelar') {
    let nota: string | null = null
    if (d !== 'confirmar') {
      const r = await perguntar({ titulo: d === 'recusar' ? 'Recusar o pedido?' : 'Cancelar a sessão?', texto: 'O cliente vê a nota na área do cliente.',
        campo: 'Nota para o cliente (opcional)', ok: d === 'recusar' ? 'Recusar' : 'Cancelar sessão', perigo: true })
      if (r === false || r === null || r === undefined) return
      nota = typeof r === 'string' ? r : null
    }
    try { await api.post(`/site/agendamentos/${a.id}/${d}`, { nota }); toast(d === 'confirmar' ? 'Sessão confirmada.' : 'Feito.', 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  return <>
    <div className="seg" style={{ marginBottom: 12 }}>{([['pendente', 'Esperando confirmação'], ['proximas', 'Próximas'], ['todas', 'Todas']] as const).map(([k, r]) =>
      <button key={k} className={`btn sm${filtro === k ? '' : ' ghost'}`} onClick={() => setFiltro(k)}>{r}</button>)}</div>
    {l.error && <ErrorState error={l.error} retry={l.reload} />}
    {l.loading && !l.data && <Loading />}
    {l.data && (!l.data.agendamentos.length ? <Empty title={filtro === 'pendente' ? 'Nenhum pedido esperando' : 'Nada aqui'}>Os pedidos feitos na área do cliente aparecem aqui.</Empty>
      : <div className="card"><div className="tbl">{l.data.agendamentos.map(a => {
        const [rot, tom] = ST[a.status] || [a.status, 'neutral']
        const anos = idade(a.driver_birth)
        return <div className="tr" key={a.id}>
          <div className="grow" style={{ minWidth: 0 }}>
            <b>{semanaDe(a.date)} {dbr(a.date)} · {PER[a.period]}</b>
            <div className="small">{a.driver || a.account_name}{anos != null ? ` (${anos} anos)` : ''}{a.driver && a.driver !== a.account_name ? ` · responsável ${a.account_name}` : ''}</div>
            <div className="small muted" style={{ overflowWrap: 'anywhere' }}>{a.account_email}{a.account_phone ? ` · ${a.account_phone}` : ''}{a.client_id ? '' : ' · conta ainda sem vínculo'}</div>
            {a.notes && <div className="small">“{a.notes}”</div>}
          </div>
          <Chip tone={tom}>{rot}</Chip>
          {a.status === 'pendente' && <><button className="btn sm primary" onClick={() => decidir(a, 'confirmar')}>Confirmar</button>
            <button className="btn sm ghost" onClick={() => decidir(a, 'recusar')}>Recusar</button></>}
          {a.status === 'confirmada' && a.date >= hojeFL() && <button className="btn sm ghost" onClick={() => decidir(a, 'cancelar')}>Cancelar</button>}
        </div>
      })}</div></div>)}
  </>
}

function Mes({ dias }: { dias: Dia[] }) {
  const cor = (p: Per) => p.open ? 'ok' : p.reason === 'lotado' ? 'warn' : p.reason?.startsWith('bloqueado') ? 'crit' : 'neutral'
  return <div className="site-mes">{dias.map(d => <div key={d.date} className="site-dia" title={`${d.periods.manha.reason || 'manhã aberta'} · ${d.periods.tarde.reason || 'tarde aberta'}`}>
    <span className="small muted">{semanaDe(d.date)}</span><b>{dbr(d.date)}</b>
    <span className={`site-p ${cor(d.periods.manha)}`}>M {d.periods.manha.capacity ? `${d.periods.manha.used}/${d.periods.manha.capacity}` : '—'}</span>
    <span className={`site-p ${cor(d.periods.tarde)}`}>T {d.periods.tarde.capacity ? `${d.periods.tarde.used}/${d.periods.tarde.capacity}` : '—'}</span>
  </div>)}</div>
}

function Disponibilidade() {
  const { can } = useAuth()
  const gerente = can('MANAGER')
  const toast = useToast()
  const a = useGet<Agenda>('/site/agenda')
  const [regras, setRegras] = useState<Regra[] | null>(null)
  const [cfg, setCfg] = useState<Cfg | null>(null)
  const [bl, setBl] = useState({ date_from: '', date_to: '', period: 'dia', reason: '' })
  const semana = regras || a.data?.semana || []
  const c = cfg || a.data?.config_completa
  const muda = (d: number, p: string, x: Partial<Regra>) => setRegras(semana.map(r => r.weekday === d && r.period === p ? { ...r, ...x } : r))
  const proximos = useMemo(() => (a.data?.dias || []).slice(0, 35), [a.data])

  async function salvarSemana() {
    try { await api.put('/site/agenda/semana', semana.map(({ weekday, period, open, capacity }) => ({ weekday, period, open, capacity })))
      toast('Semana salva: o cliente já vê.', 'ok'); setRegras(null); a.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function salvarCfg() {
    if (!c) return
    try { await api.patch('/site/agenda/config', { ...c, auto_confirm: !!c.auto_confirm }); toast('Regras salvas.', 'ok'); setCfg(null); a.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function bloquear() {
    if (!bl.date_from) { toast('Diga a data.', 'warn'); return }
    try { await api.post('/site/agenda/bloqueios', { ...bl, date_to: bl.date_to || null, reason: bl.reason || null }); toast('Bloqueado.', 'ok')
      setBl({ date_from: '', date_to: '', period: 'dia', reason: '' }); a.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function desbloquear(b: Bloqueio) {
    try { await api.post(`/site/agenda/bloqueios/${b.id}/remover`); toast('Desbloqueado.', 'ok'); a.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  if (a.error && !a.data) return <ErrorState error={a.error} retry={a.reload} />
  if (!a.data || !c) return <Loading />
  const nadaAberto = !a.data.semana.some(r => r.open)
  return <div className="stack" style={{ gap: 18 }}>
    {nadaAberto && <div className="banner warn"><span className="bi">▲</span><div className="grow">A agenda está <b>fechada</b>: nenhum dia da semana aberto. Abra abaixo os dias e períodos em que o cliente pode marcar.</div></div>}
    <Section title="Próximos dias" count={proximos.length}><Mes dias={proximos} />
      <p className="small muted" style={{ margin: '8px 0 0' }}>M = manhã, T = tarde (marcadas/vagas). Verde aberto, laranja lotado, vermelho bloqueado, cinza fechado.</p></Section>

    <Section title="A semana">
      <div className="site-semana"><span /><b className="small muted">Manhã</b><b className="small muted">Tarde</b>
        {DIAS.map((nome, d) => [<b key={`n${d}`}>{nome}</b>,
        ...(['manha', 'tarde'] as const).map(p => { const r = semana.find(x => x.weekday === d && x.period === p)!
          return <label key={`${d}${p}`} className="row" style={{ gap: 6 }}>
            <input type="checkbox" disabled={!gerente} checked={r.open} onChange={e => muda(d, p, { open: e.target.checked })} aria-label={`${nome} ${PER[p]} aberto`} />
            <input className="inp" style={{ width: 70 }} type="number" min={1} max={50} disabled={!gerente || !r.open} value={r.capacity}
              onChange={e => muda(d, p, { capacity: Number(e.target.value) || 1 })} aria-label={`vagas ${nome} ${PER[p]}`} />
            <span className="small muted">vagas</span></label> })])}
      </div>
      {gerente && regras && <div style={{ marginTop: 10 }}><button className="btn primary" onClick={salvarSemana}>Salvar a semana</button></div>}
    </Section>

    <Section title="Horários e regras">
      <div className="row gap wrap" style={{ alignItems: 'flex-end' }}>
        {([['morning_start', 'Manhã começa'], ['morning_end', 'Manhã termina'], ['afternoon_start', 'Tarde começa'], ['afternoon_end', 'Tarde termina']] as const).map(([k, rot]) =>
          <label key={k} className="fld" style={{ margin: 0 }}><span>{rot}</span><input type="time" disabled={!gerente} value={c[k]} onChange={e => setCfg({ ...c, [k]: e.target.value })} /></label>)}
        <label className="fld" style={{ margin: 0, width: 150 }}><span>Antecedência (horas)</span><input type="number" min={0} disabled={!gerente} value={c.min_notice_hours} onChange={e => setCfg({ ...c, min_notice_hours: Number(e.target.value) })} /></label>
        <label className="fld" style={{ margin: 0, width: 150 }}><span>Mostra até (dias)</span><input type="number" min={1} disabled={!gerente} value={c.horizon_days} onChange={e => setCfg({ ...c, horizon_days: Number(e.target.value) })} /></label>
      </div>
      <label className="check" style={{ marginTop: 10 }}><input type="checkbox" disabled={!gerente} checked={!!c.auto_confirm} onChange={e => setCfg({ ...c, auto_confirm: e.target.checked ? 1 : 0 })} /> Confirmar sozinho <span className="small muted">(desligado: a equipe confirma cada pedido)</span></label>
      {gerente && cfg && <div style={{ marginTop: 10 }}><button className="btn primary" onClick={salvarCfg}>Salvar regras</button></div>}
    </Section>

    <Section title="Bloqueios" count={a.data.bloqueios.length}>
      {gerente && <div className="row gap wrap" style={{ alignItems: 'flex-end', marginBottom: 10 }}>
        <label className="fld" style={{ margin: 0 }}><span>De</span><input type="date" value={bl.date_from} onChange={e => setBl({ ...bl, date_from: e.target.value })} /></label>
        <label className="fld" style={{ margin: 0 }}><span>Até <i>(opcional)</i></span><input type="date" value={bl.date_to} onChange={e => setBl({ ...bl, date_to: e.target.value })} /></label>
        <label className="fld" style={{ margin: 0 }}><span>O quê</span><select value={bl.period} onChange={e => setBl({ ...bl, period: e.target.value })}>
          <option value="dia">o dia todo</option><option value="manha">só a manhã</option><option value="tarde">só a tarde</option></select></label>
        <label className="fld grow" style={{ margin: 0, minWidth: 160 }}><span>Motivo <i>(só a equipe vê)</i></span><input value={bl.reason} onChange={e => setBl({ ...bl, reason: e.target.value })} placeholder="corrida, manutenção, feriado" /></label>
        <button className="btn" onClick={bloquear}>Bloquear</button>
      </div>}
      {!a.data.bloqueios.length ? <Empty title="Nenhum bloqueio" /> : <div className="tbl">{a.data.bloqueios.map(b => <div className="tr" key={b.id}>
        <div className="grow"><b>{dbr(b.date_from)}{b.date_to !== b.date_from ? ` a ${dbr(b.date_to)}` : ''}</b> · {PER[b.period]}{b.reason ? <span className="small muted"> · {b.reason}</span> : null}</div>
        {gerente && <button className="btn sm ghost" onClick={() => desbloquear(b)}>Desbloquear</button>}
      </div>)}</div>}
    </Section>
  </div>
}

interface Sugestao { client_id: number; name: string; pilot_name: string | null; email: string | null; phone: string | null; motivo: string }
interface ContaSite { id: number; email: string; name: string; phone: string | null; city: string | null; state: string | null; created_at: string
  client_id: number | null; client_name: string | null; client_pilot: string | null; linked_at: string | null; linked_by_name: string | null
  drivers: number; pilotos: string[]; sugestao: Sugestao | null }

/* Contas de clientes (#42): o sistema sugere o cliente interno; uma pessoa confirma. O vínculo
 * abre para o cliente o histórico daquele card — por isso nunca é automático. */
function Contas() {
  const { can } = useAuth()
  const toast = useToast()
  const perguntar = usePerguntar()
  const [filtro, setFiltro] = useState<'sem_vinculo' | 'vinculadas' | 'todas'>('sem_vinculo')
  const l = useGet<{ contas: ContaSite[] }>(`/site/contas?filtro=${filtro}`, 30000)
  const [outro, setOutro] = useState<Record<number, Client | null>>({})
  async function vincular(c: ContaSite, clientId: number, nome: string) {
    if (!await perguntar({ titulo: `Ligar ${c.email} a ${nome}?`, texto: 'O cliente passa a ver na área do cliente o histórico de serviços deste card. Confira se é mesmo a mesma família.', ok: 'Vincular' })) return
    try { await api.post(`/site/contas/${c.id}/vincular`, { client_id: clientId }); toast('Vinculado.', 'ok'); l.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function desvincular(c: ContaSite) {
    if (!await perguntar({ titulo: `Desligar ${c.email} de ${c.client_pilot || c.client_name}?`, texto: 'O cliente deixa de ver o histórico.', ok: 'Desvincular', perigo: true })) return
    try { await api.post(`/site/contas/${c.id}/desvincular`); toast('Desvinculado.', 'ok'); l.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  return <>
    <div className="seg" style={{ marginBottom: 12 }}>{([['sem_vinculo', 'Esperando vínculo'], ['vinculadas', 'Vinculadas'], ['todas', 'Todas']] as const).map(([k, r]) =>
      <button key={k} className={`btn sm${filtro === k ? '' : ' ghost'}`} onClick={() => setFiltro(k)}>{r}</button>)}</div>
    {l.error && <ErrorState error={l.error} retry={l.reload} />}
    {l.loading && !l.data && <Loading />}
    {l.data && (!l.data.contas.length ? <Empty title={filtro === 'sem_vinculo' ? 'Nenhuma conta esperando vínculo' : 'Nada aqui'}>As contas criadas na área do cliente aparecem aqui.</Empty>
      : <div className="stack" style={{ gap: 10 }}>{l.data.contas.map(c => <div className="card card-b stack" key={c.id} style={{ gap: 8 }}>
        <div className="row wrap"><div className="grow" style={{ minWidth: 0 }}><b>{c.name}</b>
          <div className="small muted" style={{ overflowWrap: 'anywhere' }}>{c.email}{c.phone ? ` · ${c.phone}` : ''}{c.city ? ` · ${c.city}${c.state ? `/${c.state}` : ''}` : ''}</div>
          <div className="small">{c.pilotos.length ? `Pilotos: ${c.pilotos.join(', ')}` : 'Nenhum piloto ainda'}</div></div>
          {c.client_id ? <Chip tone="ok">vinculada</Chip> : <Chip tone="warn">sem vínculo</Chip>}</div>
        {c.client_id ? <div className="row wrap"><span className="small grow">Cliente: <Link to={`/clients/${c.client_id}`}>{c.client_pilot || c.client_name}</Link>{c.linked_by_name ? ` · por ${c.linked_by_name}` : ''}</span>
          {can('MANAGER') && <button className="btn sm ghost" onClick={() => desvincular(c)}>Desvincular</button>}</div>
          : <>
            {c.sugestao ? <div className="row wrap" style={{ gap: 8 }}><span className="small grow">✦ Sugestão: <Link to={`/clients/${c.sugestao.client_id}`}><b>{c.sugestao.pilot_name || c.sugestao.name}</b></Link>
              {c.sugestao.pilot_name && c.sugestao.pilot_name !== c.sugestao.name ? ` (resp. ${c.sugestao.name})` : ''} · {c.sugestao.motivo}</span>
              <button className="btn sm primary" onClick={() => vincular(c, c.sugestao!.client_id, c.sugestao!.pilot_name || c.sugestao!.name)}>Vincular a este</button></div>
              : <span className="small muted">Nenhum cliente parecido no site interno. Escolha abaixo, ou deixe para quando o cliente entrar pelo Asana.</span>}
            <div className="row wrap" style={{ alignItems: 'flex-end', gap: 8 }}><div className="grow" style={{ minWidth: 220 }}>
              <Picker label="Outro cliente" value={outro[c.id] || null} onPick={x => setOutro(o => ({ ...o, [c.id]: x }))} /></div>
              {outro[c.id] && <button className="btn sm" onClick={() => vincular(c, outro[c.id]!.id, outro[c.id]!.pilot_name || outro[c.id]!.name)}>Vincular</button>}</div>
          </>}
      </div>)}</div>)}
  </>
}

export function SitePublico() {
  const { aba } = useParams()
  return <>
    <PageHeader title="Site público" help={<>O que o cliente usa na área do cliente (hoje em <a href="/ops/portal" target="_blank" rel="noreferrer">/ops/portal</a>, depois no urace.us): os pedidos de sessão e a agenda que você abre e fecha.</>}>
      <a className="btn ghost" href="/ops/portal" target="_blank" rel="noreferrer">Abrir a área do cliente ↗</a>
    </PageHeader>
    <div className="tabs">
      <NavLink to="/site" end className={({ isActive }) => isActive ? 'on' : ''}>Agendamentos</NavLink>
      <NavLink to="/site/disponibilidade" className={({ isActive }) => isActive ? 'on' : ''}>Disponibilidade</NavLink>
      <NavLink to="/site/contas" className={({ isActive }) => isActive ? 'on' : ''}>Contas de clientes</NavLink>
    </div>
    {aba === 'disponibilidade' ? <Disponibilidade /> : aba === 'contas' ? <Contas /> : <Agendamentos />}
  </>
}
