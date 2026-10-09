/* Site público, visto de dentro (#41): a agenda que o cliente usa na área do cliente.
 * Agendamentos: o que o cliente pediu (confirmar, recusar). Disponibilidade: a semana,
 * os horários, os bloqueios — quem mexe é o gerente; a operação vê. */
import { useState } from 'react'
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
import { fmtDate, fmtDateTime } from '../components/fmt'

type Tom = 'warn' | 'info' | 'ok' | 'neutral' | 'accent' | 'crit'
interface Per { open: boolean; spots: number; reason: string | null; capacity: number; used: number }
interface Dia { date: string; weekday: number; any_open: boolean; periods: { manha: Per; tarde: Per; dia: { open: boolean } } }
interface Regra { weekday: number; dia: string; period: 'manha' | 'tarde'; open: boolean; capacity: number }
interface Bloqueio { id: number; date_from: string; date_to: string; period: string; reason: string | null; created_at: string; weekday: number | null }
interface Cfg { morning_start: string; morning_end: string; afternoon_start: string; afternoon_end: string; auto_confirm: number; horizon_days: number; min_notice_hours: number; auto_sell?: number }
interface Agenda { dias: Dia[]; semana: Regra[]; bloqueios: Bloqueio[]; config_completa: Cfg }
interface Servico { id: number; name: string; description: string | null; price: number; qbo_item_id: string | null; qbo_item_name: string | null
  invoice_text: string | null; active: number; sort: number; updated_at: string | null; deposit?: number | null
  kind?: 'session' | 'plan' | null; months?: number | null; sessions_month?: number | null }
interface ItemQbo { id: string; name: string; full_name: string | null; price: number | null }
interface Ag { id: number; date: string; period: string; status: string; notes: string | null; decision_note: string | null; created_at: string
  service_name: string | null; price: number | null; contrato: { usadas: number; sessoes_por_mes: number; acima: boolean } | null
  accepted_at?: string | null; invoice_doc?: string | null; invoice_link?: string | null; charge_error?: string | null; waiver_error?: string | null; reminder_error?: string | null
  origin?: string | null; utm?: string | null; card_note?: string | null; paid_at?: string | null
  cobranca?: { aceita: boolean; pagamento: 'contrato' | 'pago' | 'enviada' | 'erro' | 'pendente'; waiver: 'ok' | 'enviada' | 'erro' | 'pendente'; pronta: boolean } | null
  account_name: string; account_email: string; account_phone: string | null; driver: string | null; driver_birth: string | null; client_id: number | null
  asana_gid: string | null; asana_error: string | null }

const PER: Record<string, string> = { manha: 'Manhã', tarde: 'Tarde', dia: 'Dia todo' }
const ST: Record<string, [string, Tom]> = { pendente: ['esperando confirmação', 'warn'], confirmada: ['confirmada', 'ok'], recusada: ['recusada', 'crit'], cancelada: ['cancelada', 'neutral'] }
const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
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
  const { can } = useAuth()
  async function decidir(a: Ag, d: 'aceitar' | 'confirmar' | 'recusar' | 'cancelar') {
    let nota: string | null = null
    if (d === 'recusar' || d === 'cancelar') {
      const r = await perguntar({ titulo: d === 'recusar' ? 'Recusar o pedido?' : 'Cancelar a sessão?', texto: 'O cliente vê a nota na área do cliente.',
        campo: 'Nota para o cliente (opcional)', ok: d === 'recusar' ? 'Recusar' : 'Cancelar sessão', perigo: true })
      if (r === false || r === null || r === undefined) return
      nota = typeof r === 'string' ? r : null
    }
    try {
      const r = await api.post<{ status: string; cobranca: { charge_error: string | null; waiver_error: string | null } | null }>(`/site/agendamentos/${a.id}/${d}`, { nota })
      toast(d === 'confirmar' ? 'Sessão confirmada.' : d === 'aceitar' ? (r.status === 'confirmada' ? 'Aceita e já confirmada (contrato + waiver em dia).'
        : r.cobranca?.charge_error || r.cobranca?.waiver_error ? 'Aceita, mas falta resolver: veja no agendamento.' : 'Aceita: invoice e waiver enviadas. Confirma sozinha quando pagar e assinar.') : 'Feito.',
        r.cobranca?.charge_error || r.cobranca?.waiver_error ? 'warn' : 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  return <>
    <div className="seg" style={{ marginBottom: 12 }}>{([['pendente', 'Esperando confirmação'], ['proximas', 'Próximas'], ['todas', 'Todas']] as const).map(([k, r]) =>
      <button key={k} className={`btn sm${filtro === k ? '' : ' ghost'}`} onClick={() => setFiltro(k)}>{r}</button>)}</div>
    {l.error && <ErrorState error={l.error} retry={l.reload} />}
    {l.loading && !l.data && <Loading />}
    {l.data && (!l.data.agendamentos.length ? <Empty title={filtro === 'pendente' ? 'Nenhum pedido esperando' : 'Nada aqui'}>Os pedidos feitos na área do cliente aparecem aqui.</Empty>
      : <div className="card"><div className="tbl">{l.data.agendamentos.map(a => {
        const [rot, tom]: [string, Tom] = a.status === 'pendente' && a.accepted_at ? ['aceita · esperando pagamento e waiver', 'info'] : ST[a.status] || [a.status, 'neutral']
        const anos = idade(a.driver_birth)
        return <div className="tr" key={a.id}>
          <div className="grow" style={{ minWidth: 0 }}>
            <b>{semanaDe(a.date)} {dbr(a.date)} · {PER[a.period]}</b>
            <div className="small">{a.driver || a.account_name}{anos != null ? ` (${anos} anos)` : ''}{a.driver && a.driver !== a.account_name ? ` · responsável ${a.account_name}` : ''}</div>
            <div className="small muted" style={{ overflowWrap: 'anywhere' }}>{a.account_email}{a.account_phone ? ` · ${a.account_phone}` : ''}{a.client_id ? '' : ' · driver ainda sem card'}</div>
            <div className="small">{a.client_id && <><Link to={`/clients/${a.client_id}`}>Client ID {a.client_id}</Link> · </>}
              {a.asana_gid ? <a href={`https://app.asana.com/0/1205450093098920/${a.asana_gid}/f`} target="_blank" rel="noreferrer">tarefa no Asana ↗</a>
                : a.asana_error ? <span title={a.asana_error}>Asana: tenta de novo em até 15 min</span> : <span className="muted">indo para o Asana…</span>}</div>
            {a.service_name && <div className="small">{a.service_name}{a.price != null ? ` · ${usd(a.price)}` : ''}</div>}
            {a.contrato && <div className="small"><Chip tone={a.contrato.acima ? 'warn' : 'info'}>{a.contrato.acima
              ? `acima do contrato: ${a.contrato.usadas} de ${a.contrato.sessoes_por_mes} no mês`
              : `contrato: ${a.contrato.usadas} de ${a.contrato.sessoes_por_mes} no mês`}</Chip></div>}
            {a.notes && <div className="small">“{a.notes}”</div>}
            {a.cobranca && <div className="row wrap small" style={{ gap: 6 }}>
              <Chip tone={a.cobranca.pagamento === 'pago' || a.cobranca.pagamento === 'contrato' ? 'ok' : a.cobranca.pagamento === 'erro' ? 'crit' : 'warn'}>
                {a.cobranca.pagamento === 'contrato' ? 'sessão do contrato' : a.cobranca.pagamento === 'pago' ? `pago ${a.invoice_doc || ''}` : a.cobranca.pagamento === 'enviada' ? `invoice ${a.invoice_doc || ''} enviada` : a.cobranca.pagamento === 'erro' ? 'invoice não saiu' : 'invoice: tentando'}</Chip>
              <Chip tone={a.cobranca.waiver === 'ok' ? 'ok' : a.cobranca.waiver === 'erro' ? 'crit' : 'warn'}>
                {a.cobranca.waiver === 'ok' ? 'waiver em dia' : a.cobranca.waiver === 'enviada' ? 'waiver enviada' : a.cobranca.waiver === 'erro' ? 'waiver não saiu' : 'waiver: assina na área do cliente'}</Chip></div>}
            {[a.charge_error, a.waiver_error, a.reminder_error].filter(Boolean).map(e => <div key={e} className="small" style={{ color: 'var(--crit)' }}>{e}</div>)}
            {(a.origin === 'site' || a.card_note || a.utm) && <div className="small muted">{a.origin === 'site' ? 'pelo site' : 'pela área do cliente'}
              {a.utm && (() => { try { const u = JSON.parse(a.utm) as Record<string, string>; return ` · campanha: ${[u.utm_source, u.utm_campaign].filter(Boolean).join(' / ') || Object.keys(u).join(', ')}` } catch { return '' } })()}
              {a.card_note && <> · {a.card_note}</>}</div>}
          </div>
          <Chip tone={tom}>{rot}</Chip>
          {a.status === 'pendente' && <>{!a.accepted_at && <button className="btn sm primary" onClick={() => decidir(a, 'aceitar')}
            title="Cria e envia a invoice e a waiver; confirma sozinha quando pagar e assinar">Aceitar</button>}
            {can('MANAGER') && <button className="btn sm ghost" onClick={() => decidir(a, 'confirmar')} title="Confirmar sem esperar pagamento e waiver">Confirmar mesmo assim</button>}
            <button className="btn sm ghost" onClick={() => decidir(a, 'recusar')}>Recusar</button></>}
          {a.status === 'confirmada' && a.date >= hojeFL() && <button className="btn sm ghost" onClick={() => decidir(a, 'cancelar')}>Cancelar</button>}
        </div>
      })}</div></div>)}
  </>
}

interface Corrida { id: number; name: string; series: string | null; track: string | null; city: string | null; date_start: string; date_end: string }
const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
const DIAS_LONGOS = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']
const ultimoDia = (mes: string) => { const [a, m] = mes.split('-').map(Number); return `${mes}-${String(new Date(a, m, 0).getDate()).padStart(2, '0')}` }
const somaMes = (mes: string, n: number) => { const [a, m] = mes.split('-').map(Number); const d = new Date(a, m - 1 + n, 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` }

/* Calendário do mês (#52): dono, 01/10 — "um calendário por mês, que mostre os finais de
 * semana e os dias que a gente vai ter corridas". Semana começa na segunda. */
function Calendario({ mes, setMes, dias, corridas }: { mes: string; setMes: (m: string) => void; dias: Dia[]; corridas: Corrida[] }) {
  const porData = Object.fromEntries(dias.map(d => [d.date, d]))
  const [a, m] = mes.split('-').map(Number)
  const vazios = (new Date(a, m - 1, 1).getDay() + 6) % 7
  const total = new Date(a, m, 0).getDate()
  const hoje = hojeFL()
  const cor = (p: Per) => p.open ? 'ok' : p.reason === 'lotado' ? 'warn' : p.reason?.startsWith('bloqueado') ? 'crit' : 'neutral'
  const corridasDe = (iso: string) => corridas.filter(c => c.date_start <= iso && iso <= c.date_end)
  return <div className="stack" style={{ gap: 10 }}>
    <div className="row"><button className="btn ghost sm" aria-label="Mês anterior" onClick={() => setMes(somaMes(mes, -1))}>‹</button>
      <h3 className="h3 grow" style={{ margin: 0, textAlign: 'center' }}>{MESES[m - 1][0].toUpperCase() + MESES[m - 1].slice(1)} de {a}</h3>
      <button className="btn ghost sm" aria-label="Próximo mês" onClick={() => setMes(somaMes(mes, 1))}>›</button></div>
    <div className="site-cal" role="grid" aria-label={`Agenda de ${MESES[m - 1]}`}>
      {DIAS.map((d, i) => <div key={d} className={`site-cal-s${i >= 5 ? ' fds' : ''}`} role="columnheader">{d}</div>)}
      {Array.from({ length: vazios }, (_, i) => <div key={`v${i}`} />)}
      {Array.from({ length: total }, (_, i) => {
        const iso = `${mes}-${String(i + 1).padStart(2, '0')}`, d = porData[iso], dsem = (vazios + i) % 7, cs = corridasDe(iso)
        return <div key={iso} role="gridcell" className={`site-cal-d${dsem >= 5 ? ' fds' : ''}${iso === hoje ? ' hoje' : ''}${cs.length ? ' corrida' : ''}`}
          title={[d ? `manhã: ${d.periods.manha.reason || 'aberta'} · tarde: ${d.periods.tarde.reason || 'aberta'}` : '', ...cs.map(c => `🏁 ${c.name}`)].filter(Boolean).join('\n')}>
          <b>{i + 1}</b>
          {d && <span className="site-cal-p"><span className={`site-p ${cor(d.periods.manha)}`}>M<span className="n"> {d.periods.manha.capacity ? `${d.periods.manha.used}/${d.periods.manha.capacity}` : ''}</span></span>
            <span className={`site-p ${cor(d.periods.tarde)}`}>T<span className="n"> {d.periods.tarde.capacity ? `${d.periods.tarde.used}/${d.periods.tarde.capacity}` : ''}</span></span></span>}
          {cs.map(c => <span key={c.id} className="site-cal-corrida">🏁 <span className="n">{c.series || c.name}</span></span>)}
        </div>
      })}
    </div>
    <p className="small muted" style={{ margin: 0 }}>M = manhã, T = tarde (marcadas/vagas). Verde aberto, laranja lotado, vermelho bloqueado, cinza fechado. Fim de semana em destaque; 🏁 = corrida do calendário de corridas.</p>
    {corridas.length > 0 && <ul className="small site-cal-lista">{corridas.map(c => <li key={c.id}>🏁 <b>{dbr(c.date_start)}{c.date_end !== c.date_start ? `–${dbr(c.date_end)}` : ''}</b> {c.name}{c.track ? ` · ${c.track}` : ''}</li>)}</ul>}
  </div>
}

function Disponibilidade() {
  const { can, livre } = useAuth()
  const gerente = can('MANAGER')
  const admin = livre || can('ADMIN')
  const [salvandoVenda, setSalvandoVenda] = useState(false)
  const toast = useToast()
  const [mes, setMes] = useState(hojeFL().slice(0, 7))
  const a = useGet<Agenda & { corridas: Corrida[] }>(`/site/agenda?de=${mes}-01&ate=${ultimoDia(mes)}`)
  const [regras, setRegras] = useState<Regra[] | null>(null)
  const [cfg, setCfg] = useState<Cfg | null>(null)
  const [bl, setBl] = useState({ modo: 'data' as 'data' | 'semana', weekday: 0, date_from: '', date_to: '', period: 'dia', reason: '' })
  const semana = regras || a.data?.semana || []
  const c = cfg || a.data?.config_completa
  const muda = (d: number, p: string, x: Partial<Regra>) => setRegras(semana.map(r => r.weekday === d && r.period === p ? { ...r, ...x } : r))

  async function salvar() {
    try {
      if (regras) await api.put('/site/agenda/semana', semana.map(({ weekday, period, open, capacity }) => ({ weekday, period, open, capacity })))
      if (cfg && c) { const { auto_sell: _vendaAutomatica, ...regrasDaAgenda } = c; void _vendaAutomatica     // a venda automática tem o próprio botão (só ADMIN)
        await api.patch('/site/agenda/config', { ...regrasDaAgenda, auto_confirm: !!c.auto_confirm }) }
      toast(regras ? 'Semana salva: o cliente já vê.' : 'Regras salvas.', 'ok'); setRegras(null); setCfg(null); a.reload()
    } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function bloquear() {
    if (bl.modo === 'data' && !bl.date_from) { toast('Diga a data.', 'warn'); return }
    const corpo = bl.modo === 'semana'
      ? { weekday: bl.weekday, date_from: bl.date_from || null, date_to: bl.date_to || null, period: bl.period, reason: bl.reason || null }
      : { date_from: bl.date_from, date_to: bl.date_to || null, period: bl.period, reason: bl.reason || null }
    try { await api.post('/site/agenda/bloqueios', corpo); toast('Bloqueado.', 'ok')
      setBl({ ...bl, date_from: '', date_to: '', reason: '' }); a.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function desbloquear(b: Bloqueio) {
    try { await api.post(`/site/agenda/bloqueios/${b.id}/remover`); toast('Desbloqueado.', 'ok'); a.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  if (a.error && !a.data) return <ErrorState error={a.error} retry={a.reload} />
  if (!a.data || !c) return <Loading />
  const nadaAberto = !a.data.semana.some(r => r.open)
  const descreve = (b: Bloqueio) => b.weekday != null
    ? <>toda <b>{DIAS_LONGOS[b.weekday]}</b>{b.date_to === '9999-12-31' ? ` · desde ${dbr(b.date_from)}` : ` · ${dbr(b.date_from)} a ${dbr(b.date_to)}`}</>
    : <b>{dbr(b.date_from)}{b.date_to !== b.date_from ? ` a ${dbr(b.date_to)}` : ''}</b>
  return <div className="stack" style={{ gap: 18 }}>
    {nadaAberto && <div className="banner warn"><span className="bi">▲</span><div className="grow">A agenda está <b>fechada</b>: nenhum dia da semana aberto. Abra abaixo os dias e períodos em que o cliente pode marcar.</div></div>}
    <Section title="Calendário do mês"><Calendario mes={mes} setMes={setMes} dias={a.data.dias} corridas={a.data.corridas || []} /></Section>

    <Section title="Semana, horários e regras">
      <div className="site-semana2" role="table" aria-label="Vagas por dia da semana">
        <div className="site-semana2-rot" role="row" aria-hidden="true"><span /><span>Manhã</span><span>Tarde</span></div>
        {DIAS.map((nome, d) => <div key={d} className={`site-semana2-dia${d >= 5 ? ' fds' : ''}`} role="row">
          <b role="rowheader">{nome}</b>
          {(['manha', 'tarde'] as const).map(p => { const r = semana.find(x => x.weekday === d && x.period === p)!
            return <div key={p} className={`site-slot${r.open ? ' on' : ''}`} role="cell">
              <label className="row" style={{ gap: 6 }}><input type="checkbox" disabled={!gerente} checked={r.open} onChange={e => muda(d, p, { open: e.target.checked })} aria-label={`${nome} ${PER[p]} aberto`} />
                <span className="site-slot-rot">{PER[p]}</span></label>
              <input className="inp" type="number" min={1} max={50} disabled={!gerente || !r.open} value={r.capacity}
                onChange={e => muda(d, p, { capacity: Number(e.target.value) || 1 })} aria-label={`vagas ${nome} ${PER[p]}`} />
              <span className="small muted">vagas</span></div> })}
        </div>)}
      </div>
      <div className="site-horarios">
        {([['morning_start', 'Manhã começa'], ['morning_end', 'Manhã termina'], ['afternoon_start', 'Tarde começa'], ['afternoon_end', 'Tarde termina']] as const).map(([k, rot]) =>
          <label key={k} className="fld" style={{ margin: 0 }}><span>{rot}</span><input type="time" disabled={!gerente} value={c[k]} onChange={e => setCfg({ ...c, [k]: e.target.value })} /></label>)}
        <label className="fld" style={{ margin: 0 }}><span>Antecedência (horas)</span><input type="number" min={0} disabled={!gerente} value={c.min_notice_hours} onChange={e => setCfg({ ...c, min_notice_hours: Number(e.target.value) })} /></label>
        <label className="fld" style={{ margin: 0 }}><span>Mostra até (dias)</span><input type="number" min={1} disabled={!gerente} value={c.horizon_days} onChange={e => setCfg({ ...c, horizon_days: Number(e.target.value) })} /></label>
      </div>
      <label className="check" style={{ marginTop: 10 }}><input type="checkbox" disabled={!gerente} checked={!!c.auto_confirm} onChange={e => setCfg({ ...c, auto_confirm: e.target.checked ? 1 : 0 })} /> Confirmar sozinho <span className="small muted">(desligado: a equipe confirma cada pedido)</span></label>
      {/* #164: venda automática — o site vende sozinho (só o administrador liga ou desliga) */}
      <label className="check" style={{ marginTop: 6 }}><input type="checkbox" disabled={!admin || salvandoVenda} checked={!!c.auto_sell} onChange={async e => {
        const ligar = e.target.checked
        setSalvandoVenda(true)
        try { await api.patch('/site/agenda/config', { auto_sell: ligar }); toast(ligar ? 'Venda automática ligada: o pedido do site vira invoice + depósito + waiver na hora.' : 'Venda automática desligada: a equipe aceita cada pedido.', 'ok'); setCfg(null); a.reload() }
        catch (ex) { toast((ex as ApiError).message, 'crit') } finally { setSalvandoVenda(false) } }} /> Venda automática <span className="small muted">(ligada: o pedido do site vira invoice do QuickBooks com o depósito e a waiver na hora, sem esperar "Aceitar"; {admin ? 'só o administrador liga ou desliga' : 'só o administrador muda'})</span></label>
      {gerente && (regras || cfg) && <div style={{ marginTop: 10 }}><button className="btn primary" onClick={salvar}>{regras ? 'Salvar a semana' : 'Salvar regras'}</button></div>}
    </Section>

    <Section title="Bloqueios" count={a.data.bloqueios.length}>
      {gerente && <div className="stack" style={{ gap: 10, marginBottom: 10 }}>
        <div className="seg" role="radiogroup" aria-label="Tipo de bloqueio">{([['data', 'Uma data ou período'], ['semana', 'Toda semana']] as const).map(([k, r]) =>
          <button key={k} type="button" role="radio" aria-checked={bl.modo === k} className={`btn sm${bl.modo === k ? '' : ' ghost'}`} onClick={() => setBl({ ...bl, modo: k })}>{r}</button>)}</div>
        <div className="row gap wrap" style={{ alignItems: 'flex-end' }}>
          {bl.modo === 'semana' && <label className="fld" style={{ margin: 0 }}><span>Dia da semana</span><select value={bl.weekday} onChange={e => setBl({ ...bl, weekday: Number(e.target.value) })}>
            {DIAS_LONGOS.map((d, i) => <option key={d} value={i}>toda {d}</option>)}</select></label>}
          <label className="fld" style={{ margin: 0 }}><span>{bl.modo === 'semana' ? 'A partir de' : 'De'}{bl.modo === 'semana' && <i> (opcional)</i>}</span><input type="date" value={bl.date_from} onChange={e => setBl({ ...bl, date_from: e.target.value })} /></label>
          <label className="fld" style={{ margin: 0 }}><span>Até <i>(opcional)</i></span><input type="date" value={bl.date_to} onChange={e => setBl({ ...bl, date_to: e.target.value })} /></label>
          <label className="fld" style={{ margin: 0 }}><span>O quê</span><select value={bl.period} onChange={e => setBl({ ...bl, period: e.target.value })}>
            <option value="dia">o dia todo</option><option value="manha">só a manhã</option><option value="tarde">só a tarde</option></select></label>
          <label className="fld grow" style={{ margin: 0, minWidth: 160 }}><span>Motivo <i>(só a equipe vê)</i></span><input value={bl.reason} onChange={e => setBl({ ...bl, reason: e.target.value })} placeholder="corrida, manutenção, feriado" /></label>
          <button className="btn" onClick={bloquear}>Bloquear</button>
        </div></div>}
      {!a.data.bloqueios.length ? <Empty title="Nenhum bloqueio" /> : <div className="tbl">{a.data.bloqueios.map(b => <div className="tr" key={b.id}>
        <div className="grow">{descreve(b)} · {PER[b.period]}{b.reason ? <span className="small muted"> · {b.reason}</span> : null}</div>
        {b.weekday != null && <Chip tone="info">recorrente</Chip>}
        {gerente && <button className="btn sm ghost" onClick={() => desbloquear(b)}>Desbloquear</button>}
      </div>)}</div>}
    </Section>
  </div>
}

interface Sugestao { client_id: number; name: string; pilot_name: string | null; email: string | null; phone: string | null; motivo: string }
interface ContaSite { id: number; email: string; name: string; phone: string | null; city: string | null; state: string | null; created_at: string
  client_id: number | null; client_name: string | null; client_pilot: string | null; linked_at: string | null; linked_by_name: string | null
  drivers: number; pilotos: string[]; sugestao: Sugestao | null; drivers_list: DriverConta[] }
/** Driver da conta e o card dele (#65): cada driver tem o seu Client ID. */
interface DriverConta { id: number; name: string; birth_date: string | null; client_id: number | null; client_name: string | null; client_pilot: string | null
  sugestao: { client_id: number; name: string; pilot_name: string | null; motivo: string } | null }

/* Serviços e preços (#50): o gerente muda o preço aqui, sem código. Quem já marcou fica
 * com o valor do dia; desativar tira da área do cliente sem apagar. */
function Servicos() {
  const { can } = useAuth()
  const gerente = can('MANAGER')
  const toast = useToast()
  const l = useGet<{ servicos: Servico[]; itens_qbo: ItemQbo[] }>('/site/servicos')
  const [novo, setNovo] = useState({ name: '', description: '', price: '', qbo_item: '', kind: 'session', months: '', sessions_month: '' })
  type Edicao = Partial<Servico> & { price_txt?: string; qbo_item?: string; deposit_txt?: string; months_txt?: string; sessions_txt?: string }
  const [edit, setEdit] = useState<Record<number, Edicao>>({})
  const itens = l.data?.itens_qbo || []
  async function criar() {
    try { await api.post('/site/servicos', { ...novo, description: novo.description || null, qbo_item: novo.qbo_item || null,
      months: novo.kind === 'plan' ? (novo.months || '1') : null, sessions_month: novo.kind === 'plan' ? (novo.sessions_month || null) : null })
      toast(novo.kind === 'plan' ? 'Plano criado: já aparece na página da Academy.' : 'Serviço criado: o cliente já vê.', 'ok')
      setNovo({ name: '', description: '', price: '', qbo_item: '', kind: 'session', months: '', sessions_month: '' }); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function salvar(sv: Servico, extra?: Partial<Servico>) {
    const e = edit[sv.id] || {}
    const corpo: Record<string, unknown> = { ...extra }
    if (e.name !== undefined) corpo.name = e.name
    if (e.description !== undefined) corpo.description = e.description || null
    if (e.price_txt !== undefined) corpo.price = e.price_txt
    if (e.qbo_item !== undefined) corpo.qbo_item = e.qbo_item || null
    if (e.deposit_txt !== undefined) corpo.deposit = e.deposit_txt || null
    if (e.kind !== undefined) corpo.kind = e.kind
    if (e.months_txt !== undefined) corpo.months = e.months_txt || null
    if (e.sessions_txt !== undefined) corpo.sessions_month = e.sessions_txt || null
    try { await api.patch(`/site/servicos/${sv.id}`, corpo); toast('Salvo. Vale para os próximos agendamentos.', 'ok')
      setEdit(x => { const y = { ...x }; delete y[sv.id]; return y }); l.reload() }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!l.data) return <Loading />
  const muda = (id: number, x: Edicao) => setEdit(e => ({ ...e, [id]: { ...e[id], ...x } }))
  // dono, 01/10: o item é um texto — escolhe da lista ou escreve; sem o preço no rótulo
  const sugestoes = <datalist id="itens-qbo">{itens.map(i => <option key={i.id} value={i.name} />)}</datalist>
  return <div className="stack" style={{ gap: 18 }}>
    {!l.data.servicos.some(x => x.active) && <div className="banner warn"><span className="bi">▲</span><div className="grow">Nenhum serviço ativo: o cliente <b>não consegue marcar</b> até haver pelo menos um, com preço.</div></div>}
    {sugestoes}
    <Section title="Serviços" count={l.data.servicos.length}>
      {!l.data.servicos.length ? <Empty title="Nenhum serviço ainda">Cadastre abaixo o que o cliente pode marcar e o preço de cada um.</Empty>
        : <div className="stack" style={{ gap: 10 }}>{l.data.servicos.map(sv => {
          const e = edit[sv.id] || {}
          return <div key={sv.id} className="card card-b">
            <div className="site-servico">
              <label className="fld"><span>Nome (o cliente lê, em inglês)</span><input value={e.name ?? sv.name} disabled={!gerente} onChange={x => muda(sv.id, { name: x.target.value })} /></label>
              <label className="fld"><span>Descrição <i>opcional</i></span><input value={e.description ?? sv.description ?? ''} disabled={!gerente} onChange={x => muda(sv.id, { description: x.target.value })} /></label>
              <label className="fld"><span>Tipo</span><select value={e.kind ?? sv.kind ?? 'session'} disabled={!gerente} onChange={x => muda(sv.id, { kind: x.target.value as 'session' | 'plan' })}>
                <option value="session">Sessão avulsa</option><option value="plan">Plano mensal (Academy, Boost)</option></select></label>
              <label className="fld"><span>{(e.kind ?? sv.kind) === 'plan' ? 'Preço por mês (US$)' : 'Preço (US$)'}</span><input inputMode="decimal" value={e.price_txt ?? String(sv.price)} disabled={!gerente} onChange={x => muda(sv.id, { price_txt: x.target.value })} /></label>
              {(e.kind ?? sv.kind) === 'plan' && <>
                <label className="fld"><span>Meses do plano</span><input inputMode="numeric" value={e.months_txt ?? String(sv.months ?? 1)} disabled={!gerente} onChange={x => muda(sv.id, { months_txt: x.target.value })} /></label>
                <label className="fld"><span>Sessões por mês</span><input inputMode="numeric" value={e.sessions_txt ?? String(sv.sessions_month ?? '')} disabled={!gerente} onChange={x => muda(sv.id, { sessions_txt: x.target.value })} /></label></>}
              <label className="fld"><span>Item no QuickBooks <i>ou texto</i></span><input list="itens-qbo" value={e.qbo_item ?? sv.qbo_item_name ?? sv.invoice_text ?? ''} disabled={!gerente}
                onChange={x => muda(sv.id, { qbo_item: x.target.value })} placeholder="escolha ou escreva" /></label>
              <label className="fld"><span>Depósito por sessão (US$) <i>0 = sem</i></span><input inputMode="decimal" value={e.deposit_txt ?? String(sv.deposit ?? 0)} disabled={!gerente}
                onChange={x => muda(sv.id, { deposit_txt: x.target.value })} /></label>
              {gerente && <div className="row" style={{ gap: 6 }}>
                <button className="btn sm primary" disabled={!edit[sv.id]} onClick={() => salvar(sv)}>Salvar</button>
                <button className="btn sm ghost" onClick={() => salvar(sv, { active: sv.active ? 0 : 1 })}>{sv.active ? 'Desativar' : 'Reativar'}</button></div>}
            </div>
            <div className="small muted" style={{ marginTop: 6 }}>{sv.active ? <Chip tone="ok">{sv.kind === 'plan' ? 'na página da Academy' : 'na área do cliente'}</Chip> : <Chip tone="neutral">desativado</Chip>}
              {sv.kind === 'plan' && <> · <span>plano de {sv.months ?? 1} {(sv.months ?? 1) > 1 ? 'meses' : 'mês'}{sv.sessions_month ? `, ${sv.sessions_month} sessões/mês` : ''}: a 1ª mensalidade sai na hora, as outras no dia 1</span></>}
              {sv.qbo_item_id ? <> · <span>item do QuickBooks</span></> : sv.invoice_text ? <> · <span>texto personalizado na invoice</span></> : <> · <span>sem item: escolha um ou escreva o texto da invoice</span></>}</div>
          </div>
        })}</div>}
    </Section>
    {gerente && <Section title="Novo serviço">
      <div className="card card-b"><div className="site-servico">
        <label className="fld"><span>Nome</span><input value={novo.name} onChange={x => setNovo({ ...novo, name: x.target.value })} placeholder="Arrive and Drive" /></label>
        <label className="fld"><span>Descrição <i>opcional</i></span><input value={novo.description} onChange={x => setNovo({ ...novo, description: x.target.value })} /></label>
        <label className="fld"><span>Tipo</span><select value={novo.kind} onChange={x => setNovo({ ...novo, kind: x.target.value })}>
          <option value="session">Sessão avulsa</option><option value="plan">Plano mensal (Academy, Boost)</option></select></label>
        <label className="fld"><span>{novo.kind === 'plan' ? 'Preço por mês (US$)' : 'Preço (US$)'}</span><input inputMode="decimal" value={novo.price} onChange={x => setNovo({ ...novo, price: x.target.value })} placeholder="719.00" /></label>
        {novo.kind === 'plan' && <>
          <label className="fld"><span>Meses do plano</span><input inputMode="numeric" value={novo.months} onChange={x => setNovo({ ...novo, months: x.target.value })} placeholder="3" /></label>
          <label className="fld"><span>Sessões por mês</span><input inputMode="numeric" value={novo.sessions_month} onChange={x => setNovo({ ...novo, sessions_month: x.target.value })} placeholder="4" /></label></>}
        <label className="fld"><span>Item no QuickBooks <i>ou texto</i></span><input list="itens-qbo" value={novo.qbo_item} placeholder="escolha ou escreva"
          onChange={x => setNovo({ ...novo, qbo_item: x.target.value })} /></label>
        <button className="btn sm primary" disabled={!novo.name || !novo.price} onClick={criar}>Criar</button>
      </div></div>
      <p className="small muted" style={{ margin: '8px 0 0' }}>Mudar o preço vale para os próximos agendamentos: quem já marcou fica com o valor do dia em que marcou. A lista mostra só os itens Academy e o Daily Using Own Kart do QuickBooks; o que não for item vira o texto da linha da invoice.</p>
    </Section>}
  </div>
}

/* Contas de clientes (#42, #52): o sistema sugere o cliente interno; uma pessoa confirma. O
 * vínculo abre para o cliente o histórico daquele card — por isso nunca é automático. Quem
 * não está na base ganha o botão "Criar cliente": o card nasce com os dados da conta. */
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
  async function criar(c: ContaSite) {
    if (!await perguntar({ titulo: `Criar o cliente ${c.name}?`, texto: `O card nasce com os dados da conta (${c.email}${c.pilotos.length ? `, piloto ${c.pilotos[0]}` : ''}) e já fica vinculado.`, ok: 'Criar cliente' })) return
    try { await api.post(`/site/contas/${c.id}/criar-cliente`); toast('Cliente criado e vinculado.', 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function vincularDriver(p: DriverConta, clientId: number, nome: string) {
    if (!await perguntar({ titulo: `O card de ${p.name} é ${nome} (Client ID ${clientId})?`, texto: 'Cada driver tem o seu card: as sessões, o contrato e o histórico dele ficam ali, separados dos irmãos.', ok: 'Vincular' })) return
    try { await api.post(`/site/drivers/${p.id}/vincular`, { client_id: clientId }); toast('Driver vinculado.', 'ok'); l.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function criarDriver(c: ContaSite, p: DriverConta) {
    if (!await perguntar({ titulo: `Criar o card de ${p.name}?`, texto: `Responsável ${c.name} (${c.email}), piloto ${p.name}. O card nasce já vinculado a este driver, com o seu Client ID.`, ok: 'Criar card' })) return
    try { const r = await api.post<{ client_id: number }>(`/site/drivers/${p.id}/criar-cliente`); toast(`Card criado: Client ID ${r.client_id}.`, 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function desvincularDriver(p: DriverConta) {
    if (!await perguntar({ titulo: `Desligar ${p.name} do Client ID ${p.client_id}?`, texto: 'O card não é apagado; só deixa de ser deste driver.', ok: 'Desvincular', perigo: true })) return
    try { await api.post(`/site/drivers/${p.id}/desvincular`); toast('Driver desvinculado.', 'ok'); l.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
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
              : <div className="row wrap" style={{ gap: 8 }}><span className="small muted grow">Nenhum cliente parecido no site interno (pelo e-mail, telefone, nome do responsável ou do piloto). Se é cliente novo, crie o card; se já existe, escolha abaixo.</span>
                <button className="btn sm primary" onClick={() => criar(c)}>Criar cliente</button></div>}
            <div className="row wrap" style={{ alignItems: 'flex-end', gap: 8 }}><div className="grow" style={{ minWidth: 220 }}>
              <Picker label="Outro cliente" value={outro[c.id] || null} onPick={x => setOutro(o => ({ ...o, [c.id]: x }))} /></div>
              {outro[c.id] && <button className="btn sm" onClick={() => vincular(c, outro[c.id]!.id, outro[c.id]!.pilot_name || outro[c.id]!.name)}>Vincular</button>}</div>
          </>}
        {c.client_id && c.drivers_list.length > 0 && <div className="stack" style={{ gap: 6 }}>
          <h3 className="h3" style={{ fontSize: 14 }}>Drivers · cada um com o seu card</h3>
          {c.drivers_list.map(p => <div key={p.id} className="row wrap" style={{ gap: 8, padding: '6px 0', borderTop: '1px solid var(--glass-line)' }}>
            <span className="grow small" style={{ minWidth: 0 }}><b>{p.name}</b>{p.birth_date ? ` · ${idade(p.birth_date)} anos` : ''}
              {p.client_id ? <> · <Link to={`/clients/${p.client_id}`}>Client ID {p.client_id}</Link></>
                : p.sugestao ? <> · ✦ sugestão: <Link to={`/clients/${p.sugestao.client_id}`}>{p.sugestao.pilot_name || p.sugestao.name} (Client ID {p.sugestao.client_id})</Link> · {p.sugestao.motivo}</>
                : <span className="muted"> · sem card</span>}</span>
            {p.client_id ? can('MANAGER') && <button className="btn sm ghost" onClick={() => desvincularDriver(p)}>Desvincular</button>
              : <>{p.sugestao && <button className="btn sm primary" onClick={() => vincularDriver(p, p.sugestao!.client_id, p.sugestao!.pilot_name || p.sugestao!.name)}>Vincular a este</button>}
                {!p.sugestao && <button className="btn sm primary" onClick={() => criarDriver(c, p)}>Criar card</button>}
                <div style={{ minWidth: 200 }}><Picker label={`Outro card para ${p.name}`} value={outro[-p.id] || null} onPick={x => setOutro(o => ({ ...o, [-p.id]: x }))} /></div>
                {outro[-p.id] && <button className="btn sm" onClick={() => vincularDriver(p, outro[-p.id]!.id, outro[-p.id]!.pilot_name || outro[-p.id]!.name)}>Vincular</button>}</>}
          </div>)}
        </div>}
      </div>)}</div>)}
  </>
}

/* Waiver assinada na área do cliente (#85), sem DocuSign. O texto vem dos dois modelos do
 * DocuSign, importados como estão (com o hash). Nasce desligada: quem liga é o ADMIN, depois do
 * sim do advogado. Desligar não apaga nada; o DocuSign segue como está. */
interface ModeloW { kind: 'adult' | 'parental'; templateId: string; name: string | null; pages: number | null; sha256: string | null; imported_at: string | null }
interface Assinada { id: number; client_id: number | null; signer_name: string; signer_email: string; minor_name: string | null; template: string
  completed_at: string; expires_at: string; doc_sha256: string }
interface WN { ligada: boolean; modelos: ModeloW[]; assinadas: { itens: Assinada[]; total: number; limit: number; offset: number } }
const POR_PAGINA = 25

function WaiverNativa() {
  const { can } = useAuth()
  const admin = can('ADMIN')
  const toast = useToast()
  const perguntar = usePerguntar()
  const [offset, setOffset] = useState(0)
  const l = useGet<WN>(`/site/waiver-nativa?limit=${POR_PAGINA}&offset=${offset}`)
  const [indo, setIndo] = useState(false)
  async function importar() {
    setIndo(true)
    try { await api.post('/site/waiver-nativa/importar', {}); toast('Modelos importados do DocuSign (só leitura lá).', 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  async function ligar(ligada: boolean) {
    if (ligada && !await perguntar({ titulo: 'Ligar a assinatura na área do cliente?', ok: 'Ligar',
      texto: 'Os clientes passam a assinar a waiver pela área do cliente, sem DocuSign. Faça isso depois do sim do advogado. O DocuSign continua funcionando como hoje.' })) return
    try { await api.post('/site/waiver-nativa/ligar', { ligada }); toast(ligada ? 'Ligada: o cliente já vê "Sign now".' : 'Desligada. Nada assinado foi apagado.', 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!l.data) return <Loading />
  const d = l.data, a = d.assinadas
  const prontos = d.modelos.every(m => m.sha256)
  return <div className="stack" style={{ gap: 18 }}>
    <Section title="Assinatura na área do cliente" right={d.ligada ? <Chip tone="ok">ligada</Chip> : <Chip tone="neutral">desligada</Chip>}>
      <div className="card card-b stack" style={{ gap: 10 }}>
        <p className="small" style={{ margin: 0 }}>O responsável assina pela área do cliente: lê o documento, marca as duas caixas, digita o nome e desenha a assinatura. Menor de 18 assina a parental; maior, a adult. Vale 1 ano. O PDF final é o original do DocuSign mais uma página de assinatura e certificado (data e hora da Flórida, IP, aparelho, hashes).</p>
        {!d.ligada && <p className="small muted" style={{ margin: 0 }}>Antes de ligar: o advogado confirma que a assinatura eletrônica com essa página de certificado vale para a waiver de menor na Flórida.</p>}
        {admin ? <div className="row wrap" style={{ gap: 8 }}>
          {d.ligada ? <button className="btn sm ghost" onClick={() => ligar(false)}>Desligar</button>
            : <button className="btn sm primary" disabled={!prontos} title={prontos ? undefined : 'Importe os dois modelos primeiro'} onClick={() => ligar(true)}>Ligar</button>}
        </div> : <p className="small muted" style={{ margin: 0 }}>Só o ADMIN liga ou desliga.</p>}
      </div>
    </Section>
    <Section title="Modelos (do DocuSign)" count={d.modelos.length} right={admin ? <button className="btn sm" disabled={indo} onClick={importar}>{indo ? <span className="spin" /> : 'Importar do DocuSign'}</button> : undefined}>
      <div className="card"><div className="tbl">{d.modelos.map(m => <div className="tr" key={m.kind}>
        <span className="grow"><b>{m.kind === 'adult' ? 'Adult' : 'Parental (menor)'}</b><div className="small muted">{m.name || 'ainda não importado'}</div></span>
        <span className="small muted">{m.sha256 ? <>{m.pages} pág. · <span className="mono" title={m.sha256}>{m.sha256.slice(0, 12)}</span> · {fmtDateTime(m.imported_at)}</> : '—'}</span>
      </div>)}</div></div>
      <p className="small muted" style={{ margin: '8px 0 0' }}>Importar só LÊ os modelos no DocuSign. Se o texto mudar lá, importe de novo: as próximas assinaturas usam o novo, as já feitas ficam com o delas.</p>
    </Section>
    <Section title="Assinadas aqui" count={a.total}>
      {!a.itens.length ? <Empty title="Nenhuma ainda">Quando um cliente assinar pela área do cliente, ela aparece aqui e no card do cliente.</Empty>
        : <div className="card"><div className="tbl">{a.itens.map(w => <div className="tr" key={w.id}>
          <span className="mono small" style={{ width: 92 }}>{fmtDate(w.completed_at)}</span>
          <span className="grow">{w.minor_name || w.signer_name}<div className="small muted">{w.template === 'parental' ? `parental · por ${w.signer_name}` : 'adult'} · vale até {fmtDate(w.expires_at)}</div></span>
          {w.client_id ? <Link className="btn sm ghost" to={`/clients/${w.client_id}`}>Card</Link> : <span className="small muted">sem card</span>}
          <a className="btn sm" href={`/ops/api/waivers/${w.id}/download`}>PDF</a>
        </div>)}</div></div>}
      {a.total > POR_PAGINA && <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button className="btn sm ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - POR_PAGINA))}>Anteriores</button>
        <span className="small muted grow" style={{ textAlign: 'center' }}>{offset + 1}–{Math.min(offset + POR_PAGINA, a.total)} de {a.total}</span>
        <button className="btn sm ghost" disabled={offset + POR_PAGINA >= a.total} onClick={() => setOffset(offset + POR_PAGINA)}>Próximas</button></div>}
    </Section>
  </div>
}

export function SitePublico() {
  const { aba } = useParams()
  const { can } = useAuth()
  return <>
    <PageHeader title="Site público" help={<>O que o cliente usa na área do cliente (hoje em <a href="/ops/portal" target="_blank" rel="noreferrer">/ops/portal</a>, depois no urace.us): os pedidos de sessão e a agenda que você abre e fecha.</>}>
      <a className="btn ghost" href="/ops/portal" target="_blank" rel="noreferrer">Abrir a área do cliente ↗</a>
    </PageHeader>
    <div className="tabs">
      <NavLink to="/site" end className={({ isActive }) => isActive ? 'on' : ''}>Agendamentos</NavLink>
      <NavLink to="/site/disponibilidade" className={({ isActive }) => isActive ? 'on' : ''}>Disponibilidade</NavLink>
      <NavLink to="/site/servicos" className={({ isActive }) => isActive ? 'on' : ''}>Serviços e preços</NavLink>
      <NavLink to="/site/contas" className={({ isActive }) => isActive ? 'on' : ''}>Contas de clientes</NavLink>
      {can('MANAGER') && <NavLink to="/site/waiver" className={({ isActive }) => isActive ? 'on' : ''}>Waiver</NavLink>}
    </div>
    {aba === 'disponibilidade' ? <Disponibilidade /> : aba === 'servicos' ? <Servicos /> : aba === 'contas' ? <Contas />
      : aba === 'waiver' && can('MANAGER') ? <WaiverNativa /> : <Agendamentos />}
  </>
}
