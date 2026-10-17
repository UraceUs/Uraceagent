/* Site público, visto de dentro (#41): a agenda que o cliente usa na área do cliente.
 * Agendamentos: o que o cliente pediu (confirmar, recusar). Disponibilidade: a semana,
 * os horários, os bloqueios — quem mexe é o gerente; a operação vê. */
import { lazy, Suspense, useId, useState } from 'react'
import { NavLink, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Section } from '../components/ui'
import { usePerguntar } from '../components/Perguntar'
import { Picker } from '../components/Unir'
import { InserirNoTopo } from '../components/Inserir'
import { Cartao as CartaoD, CdItem, CdLista, type TomD } from '../components/Cartao'
import { ESTADO_PEDIDO, tomDoPedido } from '../components/pedidoSite'
import type { Client } from '../api/types'
import { Link } from 'react-router-dom'
import { useToast } from '../components/Toast'
import { fmtDate, fmtDateTime } from '../components/fmt'
import { tr } from '../i18n'

type Tom = 'warn' | 'info' | 'ok' | 'neutral' | 'accent' | 'crit'
interface Per { open: boolean; spots: number; reason: string | null; capacity: number; used: number }
interface Dia { date: string; weekday: number; any_open: boolean; periods: { manha: Per; tarde: Per; dia: { open: boolean } } }
interface Regra { weekday: number; dia: string; period: 'manha' | 'tarde'; open: boolean; capacity: number }
interface Bloqueio { id: number; date_from: string; date_to: string; period: string; reason: string | null; created_at: string; weekday: number | null }
interface Cfg { morning_start: string; morning_end: string; afternoon_start: string; afternoon_end: string; auto_confirm: number; horizon_days: number; min_notice_hours: number; auto_sell?: number }
interface Agenda { dias: Dia[]; semana: Regra[]; bloqueios: Bloqueio[]; config_completa: Cfg }
interface Servico { id: number; name: string; description: string | null; price: number; qbo_item_id: string | null; qbo_item_name: string | null
  invoice_text: string | null; active: number; sort: number; updated_at: string | null; deposit?: number | null; site_kart?: string | null
  kind?: 'session' | 'plan' | 'addon' | null; months?: number | null; sessions_month?: number | null
  site_title?: string | null; site_subtitle?: string | null; site_note?: string | null; own_kart?: number | null
  deposit_required?: number | boolean | null
  /** #314: a sessão extra do plano — valor (vazio: mensal ÷ sessões) e o item do QuickBooks */
  extra_price?: number | null; extra_item_id?: string | null; extra_item_name?: string | null
  /** #312: onde o serviço aparece hoje no site (a mesma regra que monta as páginas) */
  no_site?: NoSite }
/** #312: `servicos_site.onde_no_site` */
interface NoSite { onde: 'kart' | 'addon' | 'plano' | 'area' | 'repetido' | 'nenhum' | 'desativado'; pagina: string | null; chave: string | null; com: string[] }
/** #312: as páginas do site em que um serviço ou um cartão entra (`servicos_site.paginas_do_site`) */
interface PaginaSite { id: string; nome: string; caminho: string; cartoes: boolean }
interface ItemQbo { id: string; name: string; full_name: string | null; price: number | null }
interface Ag { id: number; date: string; period: string; status: string; notes: string | null; decision_note: string | null; created_at: string
  service_name: string | null; price: number | null; contrato: { usadas: number; sessoes_por_mes: number; acima: boolean } | null
  /** #314: do pacote do mês (sem custo) ou extra (cobrada pela invoice); null = avulsa */
  coverage?: 'plano' | 'extra' | null; list_price?: number | null; group_id?: number | null
  accepted_at?: string | null; charge_kind?: string | null; store_order_id?: number | null; invoice_doc?: string | null; invoice_link?: string | null; charge_error?: string | null; waiver_error?: string | null; reminder_error?: string | null
  origin?: string | null; utm?: string | null; card_note?: string | null; paid_at?: string | null
  cobranca?: { aceita: boolean; pagamento: 'contrato' | 'pago' | 'enviada' | 'erro' | 'pendente'; waiver: 'ok' | 'enviada' | 'erro' | 'pendente'; pronta: boolean } | null
  account_name: string; account_email: string; account_phone: string | null; driver: string | null; driver_birth: string | null; client_id: number | null
  asana_gid: string | null; asana_error: string | null }

const TIPO_SERVICO: Record<string, string> = { session: tr("Sessão avulsa"), plan: tr("Plano mensal (Academy, Boost)"), addon: tr("Add-on do dia de treino (Lead and Follow)") }
/** #313: o tom da pílula do cartão D (o accent dos chips vira o azul da informação) */
const tomD = (t: Tom): TomD => t === 'accent' ? 'info' : t
const PER: Record<string, string> = { manha: tr("Manhã"), tarde: tr("Tarde"), dia: tr("Dia todo") }
const ST: Record<string, [string, Tom]> = { pendente: [tr("esperando confirmação"), 'warn'], confirmada: ['confirmada', 'ok'], recusada: ['recusada', 'crit'], cancelada: ['cancelada', 'neutral'] }
const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
const DIAS = [tr("Seg"), tr("Ter"), tr("Qua"), tr("Qui"), tr("Sex"), tr("Sáb"), tr("Dom")]
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
      const r = await perguntar({ titulo: d === 'recusar' ? tr("Recusar o pedido?") : tr("Cancelar a sessão?"), texto: tr("O cliente vê a nota na área do cliente."),
        campo: tr("Nota para o cliente (opcional)"), ok: d === 'recusar' ? tr("Recusar") : tr("Cancelar sessão"), perigo: true })
      if (r === false || r === null || r === undefined) return
      nota = typeof r === 'string' ? r : null
    }
    try {
      const r = await api.post<{ status: string; cobranca: { charge_error: string | null; waiver_error: string | null } | null }>(`/site/agendamentos/${a.id}/${d}`, { nota })
      toast(d === 'confirmar' ? tr("Sessão confirmada.") : d === 'aceitar' ? (r.status === 'confirmada' ? tr("Aceita e já confirmada (contrato + waiver em dia).")
        : r.cobranca?.charge_error || r.cobranca?.waiver_error ? tr("Aceita, mas falta resolver: veja no agendamento.") : tr("Aceita: invoice e waiver enviadas. Confirma sozinha quando pagar e assinar.")) : tr("Feito."),
        r.cobranca?.charge_error || r.cobranca?.waiver_error ? 'warn' : 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  return <>
    <div className="seg" style={{ marginBottom: 12 }}>{([['pendente', tr("Esperando confirmação")], ['proximas', tr("Próximas")], ['todas', tr("Todas")]] as const).map(([k, r]) =>
      <button key={k} className={`btn sm${filtro === k ? '' : ' ghost'}`} onClick={() => setFiltro(k)}>{r}</button>)}</div>
    {l.error && <ErrorState error={l.error} retry={l.reload} />}
    {l.loading && !l.data && <Loading />}
    {l.data && (!l.data.agendamentos.length ? <Empty title={filtro === 'pendente' ? tr("Nenhum pedido esperando") : tr("Nada aqui")}>{tr("Os pedidos feitos na área do cliente aparecem aqui.")}</Empty>
      : <div className="cd-grade">{l.data.agendamentos.map(a => {
        const [rot, tom]: [string, Tom] = a.status === 'pendente' && a.accepted_at ? ['aceita · esperando pagamento e waiver', 'info'] : ST[a.status] || [a.status, 'neutral']
        const anos = idade(a.driver_birth)
        const quem = a.driver || a.account_name
        const pg = a.cobranca?.pagamento, wv = a.cobranca?.waiver
        const campanha = a.utm ? (() => { try { const u = JSON.parse(a.utm) as Record<string, string>; return [u.utm_source, u.utm_campaign].filter(Boolean).join(' / ') || Object.keys(u).join(', ') } catch { return '' } })() : ''
        return <CartaoD key={a.id} id={`ag-${a.id}`} nivel={2} estado={rot} tom={tomD(tom)} avatar={quem} nome={quem}
          sub={[anos != null ? tr("{0} anos", anos) : null,
            a.driver && a.driver !== a.account_name ? <>{tr("Responsável")}: <b>{a.account_name}</b></> : null,
            a.service_name ? `${a.service_name}${a.coverage ? '' : a.price != null ? ` · ${usd(a.price)}` : ''}` : null]}
          grande={`${semanaDe(a.date)} ${dbr(a.date)}`} detalhe={PER[a.period]}
          progresso={a.status === 'pendente' && a.cobranca ? { rotulo: tr("Pronto para confirmar"), total: 3,
            feito: [a.cobranca.aceita, pg === 'pago' || pg === 'contrato', wv === 'ok'].filter(Boolean).length } : null}
          acoes={a.status === 'pendente' ? <>
            <button className="btn danger" onClick={() => decidir(a, 'recusar')}>{tr("Recusar")}</button>
            {!a.accepted_at && <button className="btn primary" onClick={() => decidir(a, 'aceitar')}
              title={a.group_id ? tr("Aceita o pedido inteiro: uma invoice com as sessões extras e uma waiver") : tr("Cria e envia a invoice e a waiver; confirma sozinha quando pagar e assinar")}>{tr("Aceitar")}</button>}
            {can('MANAGER') && <button className="btn" onClick={() => decidir(a, 'confirmar')} title={tr("Confirmar sem esperar pagamento e waiver")}>{tr("Confirmar mesmo assim")}</button>}
          </> : a.status === 'confirmada' && a.date >= hojeFL() ? <button className="btn danger" onClick={() => decidir(a, 'cancelar')}>{tr("Cancelar")}</button> : null}>
          <CdLista>
            {a.cobranca && <CdItem tom={pg === 'pago' || pg === 'contrato' ? 'ok' : pg === 'erro' ? 'crit' : 'warn'}>
              {pg === 'contrato' ? tr("sessão do contrato") : a.charge_kind === 'stripe' ? tr("pago no site · pedido #{0}", a.store_order_id ?? '') : pg === 'pago' ? tr("pago {0}", a.invoice_doc || '') : pg === 'enviada' ? tr("invoice {0} enviada", a.invoice_doc || '') : pg === 'erro' ? tr("invoice não saiu") : tr("invoice: tentando")}</CdItem>}
            {a.cobranca && <CdItem tom={wv === 'ok' ? 'ok' : wv === 'erro' ? 'crit' : 'warn'}>
              {wv === 'ok' ? tr("waiver em dia") : wv === 'enviada' ? tr("waiver enviada") : wv === 'erro' ? tr("waiver não saiu") : tr("waiver: assina na área do cliente")}</CdItem>}
            {/* #314: a sessão do aluno recorrente — do plano (sem custo) ou extra (invoice); o contador é só da equipe */}
            {a.coverage ? <CdItem tom={a.coverage === 'extra' ? 'warn' : 'info'} valor={a.contrato ? tr("pacote: {0} de {1} no mês", a.contrato.usadas, a.contrato.sessoes_por_mes) : null}>
              {a.coverage === 'extra' ? tr("extra {0}", a.price != null ? usd(a.price) : tr("sem valor")) + (a.invoice_doc ? tr(" · invoice {0}", a.invoice_doc) : '') : tr("do plano")}
              {a.group_id ? <> · {tr("pedido de vários dias #{0}", a.group_id)}</> : null}</CdItem>
              : a.contrato && <CdItem tom={a.contrato.acima ? 'warn' : 'info'}>{a.contrato.acima
                ? tr("acima do contrato: {0} de {1} no mês", a.contrato.usadas, a.contrato.sessoes_por_mes)
                : tr("contrato: {0} de {1} no mês", a.contrato.usadas, a.contrato.sessoes_por_mes)}</CdItem>}
            <CdItem tom={a.client_id ? 'ok' : 'warn'} valor={a.client_id ? <Link to={`/clients/${a.client_id}`}>{tr("Client ID")} {a.client_id}</Link> : null}>
              {a.client_id ? tr("Card do cliente") : tr("driver ainda sem card")}</CdItem>
            <CdItem tom={a.asana_gid ? 'ok' : a.asana_error ? 'warn' : 'neutral'}
              valor={a.asana_gid ? <a href={`https://app.asana.com/0/1205450093098920/${a.asana_gid}/f`} target="_blank" rel="noreferrer">{tr("tarefa no Asana ↗")}</a> : null}>
              {a.asana_gid ? tr("Asana") : a.asana_error ? <span title={a.asana_error}>{tr("Asana: tenta de novo em até 15 min")}</span> : tr("indo para o Asana…")}</CdItem>
            <CdItem tom="info" glifo="@" valor={a.account_phone}><span className="cd-mono">{a.account_email}</span></CdItem>
            {a.notes && <CdItem tom="info" glifo="“">“{a.notes}”</CdItem>}
            {[a.charge_error, a.waiver_error, a.reminder_error].filter(Boolean).map(e => <CdItem key={e} tom="crit"><span className="cd-erro">{e}</span></CdItem>)}
            {(a.origin === 'site' || a.card_note || a.utm) && <CdItem tom="neutral" glifo="↗" valor={campanha ? tr("campanha: {0}", campanha) : null}>
              {a.origin === 'site' ? tr("pelo site") : tr("pela área do cliente")}{a.card_note && <> · {a.card_note}</>}</CdItem>}
          </CdLista>
        </CartaoD>
      })}</div>)}
  </>
}

interface Corrida { id: number; name: string; series: string | null; track: string | null; city: string | null; date_start: string; date_end: string }
const MESES = [tr("janeiro"), tr("fevereiro"), tr("março"), tr("abril"), tr("maio"), tr("junho"), tr("julho"), tr("agosto"), tr("setembro"), tr("outubro"), tr("novembro"), tr("dezembro")]
const DIAS_LONGOS = [tr("segunda"), tr("terça"), tr("quarta"), tr("quinta"), tr("sexta"), tr("sábado"), tr("domingo")]
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
    <div className="row"><button className="btn ghost sm" aria-label={tr("Mês anterior")} onClick={() => setMes(somaMes(mes, -1))}>‹</button>
      <h3 className="h3 grow" style={{ margin: 0, textAlign: 'center' }}>{MESES[m - 1][0].toUpperCase() + MESES[m - 1].slice(1)} {tr("de")} {a}</h3>
      <button className="btn ghost sm" aria-label={tr("Próximo mês")} onClick={() => setMes(somaMes(mes, 1))}>›</button></div>
    <div className="site-cal" role="grid" aria-label={tr("Agenda de {0}", MESES[m - 1])}>
      {DIAS.map((d, i) => <div key={d} className={`site-cal-s${i >= 5 ? ' fds' : ''}`} role="columnheader">{d}</div>)}
      {Array.from({ length: vazios }, (_, i) => <div key={`v${i}`} />)}
      {Array.from({ length: total }, (_, i) => {
        const iso = `${mes}-${String(i + 1).padStart(2, '0')}`, d = porData[iso], dsem = (vazios + i) % 7, cs = corridasDe(iso)
        return <div key={iso} role="gridcell" className={`site-cal-d${dsem >= 5 ? ' fds' : ''}${iso === hoje ? ' hoje' : ''}${cs.length ? ' corrida' : ''}`}
          title={[d ? tr('manhã: {0} · tarde: {1}', d.periods.manha.reason || tr('aberta'), d.periods.tarde.reason || tr('aberta')) : '', ...cs.map(c => `🏁 ${c.name}`)].filter(Boolean).join('\n')}>
          <b>{i + 1}</b>
          {d && <span className="site-cal-p"><span className={`site-p ${cor(d.periods.manha)}`}>{tr("M")}<span className="n"> {d.periods.manha.capacity ? `${d.periods.manha.used}/${d.periods.manha.capacity}` : ''}</span></span>
            <span className={`site-p ${cor(d.periods.tarde)}`}>{tr("T")}<span className="n"> {d.periods.tarde.capacity ? `${d.periods.tarde.used}/${d.periods.tarde.capacity}` : ''}</span></span></span>}
          {cs.map(c => <span key={c.id} className="site-cal-corrida">🏁 <span className="n">{c.series || c.name}</span></span>)}
        </div>
      })}
    </div>
    <p className="small muted" style={{ margin: 0 }}>{tr("M = manhã, T = tarde (marcadas/vagas). Verde aberto, laranja lotado, vermelho bloqueado, cinza fechado. Fim de semana em destaque; 🏁 = corrida do calendário de corridas.")}</p>
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
      toast(regras ? tr("Semana salva: o cliente já vê.") : tr("Regras salvas."), 'ok'); setRegras(null); setCfg(null); a.reload()
    } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function bloquear() {
    if (bl.modo === 'data' && !bl.date_from) { toast(tr("Diga a data."), 'warn'); return }
    const corpo = bl.modo === 'semana'
      ? { weekday: bl.weekday, date_from: bl.date_from || null, date_to: bl.date_to || null, period: bl.period, reason: bl.reason || null }
      : { date_from: bl.date_from, date_to: bl.date_to || null, period: bl.period, reason: bl.reason || null }
    try { await api.post('/site/agenda/bloqueios', corpo); toast(tr("Bloqueado."), 'ok')
      setBl({ ...bl, date_from: '', date_to: '', reason: '' }); a.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function desbloquear(b: Bloqueio) {
    try { await api.post(`/site/agenda/bloqueios/${b.id}/remover`); toast(tr("Desbloqueado."), 'ok'); a.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  if (a.error && !a.data) return <ErrorState error={a.error} retry={a.reload} />
  if (!a.data || !c) return <Loading />
  const nadaAberto = !a.data.semana.some(r => r.open)
  const descreve = (b: Bloqueio) => b.weekday != null
    ? <>{tr("toda")} <b>{DIAS_LONGOS[b.weekday]}</b>{b.date_to === '9999-12-31' ? tr(" · desde {0}", dbr(b.date_from)) : tr(" · {0} a {1}", dbr(b.date_from), dbr(b.date_to))}</>
    : <b>{dbr(b.date_from)}{b.date_to !== b.date_from ? tr(" a {0}", dbr(b.date_to)) : ''}</b>
  return <div className="stack" style={{ gap: 18 }}>
    {/* #312: o "Bloquear" fica no topo da tela (antes era a 3ª seção, depois do calendário e da semana) */}
    {gerente && <InserirNoTopo rotulo={tr("Bloquear datas")} titulo={tr("Novo bloqueio")}>
      <div className="stack" style={{ gap: 10 }}>
        <div className="seg" role="radiogroup" aria-label={tr("Tipo de bloqueio")}>{([['data', tr("Uma data ou período")], ['semana', tr("Toda semana")]] as const).map(([k, r]) =>
          <button key={k} type="button" role="radio" aria-checked={bl.modo === k} className={`btn sm${bl.modo === k ? '' : ' ghost'}`} onClick={() => setBl({ ...bl, modo: k })}>{r}</button>)}</div>
        <div className="row gap wrap" style={{ alignItems: 'flex-end' }}>
          {bl.modo === 'semana' && <label className="fld" style={{ margin: 0 }}><span>{tr("Dia da semana")}</span><select value={bl.weekday} onChange={e => setBl({ ...bl, weekday: Number(e.target.value) })}>
            {DIAS_LONGOS.map((d, i) => <option key={d} value={i}>{tr("toda")} {d}</option>)}</select></label>}
          <label className="fld" style={{ margin: 0 }}><span>{bl.modo === 'semana' ? tr("A partir de") : tr("De")}{bl.modo === 'semana' && <i> {tr("(opcional)")}</i>}</span><input type="date" value={bl.date_from} onChange={e => setBl({ ...bl, date_from: e.target.value })} /></label>
          <label className="fld" style={{ margin: 0 }}><span>{tr("Até")} <i>{tr("(opcional)")}</i></span><input type="date" value={bl.date_to} onChange={e => setBl({ ...bl, date_to: e.target.value })} /></label>
          <label className="fld" style={{ margin: 0 }}><span>{tr("O quê")}</span><select value={bl.period} onChange={e => setBl({ ...bl, period: e.target.value })}>
            <option value="dia">{tr("o dia todo")}</option><option value="manha">{tr("só a manhã")}</option><option value="tarde">{tr("só a tarde")}</option></select></label>
          <label className="fld grow" style={{ margin: 0, minWidth: 160 }}><span>{tr("Motivo")} <i>{tr("(só a equipe vê)")}</i></span><input value={bl.reason} onChange={e => setBl({ ...bl, reason: e.target.value })} placeholder={tr("corrida, manutenção, feriado")} /></label>
          <button className="btn" onClick={bloquear}>{tr("Bloquear")}</button>
        </div></div>
    </InserirNoTopo>}
    {nadaAberto && <div className="banner warn"><span className="bi">▲</span><div className="grow">{tr("A agenda está")} <b>{tr("fechada")}</b>{tr(": nenhum dia da semana aberto. Abra abaixo os dias e períodos em que o cliente pode marcar.")}</div></div>}
    <Section title={tr("Calendário do mês")}><Calendario mes={mes} setMes={setMes} dias={a.data.dias} corridas={a.data.corridas || []} /></Section>

    <Section title={tr("Semana, horários e regras")}>
      <div className="site-semana2" role="table" aria-label={tr("Vagas por dia da semana")}>
        <div className="site-semana2-rot" role="row" aria-hidden="true"><span /><span>{tr("Manhã")}</span><span>{tr("Tarde")}</span></div>
        {DIAS.map((nome, d) => <div key={d} className={`site-semana2-dia${d >= 5 ? ' fds' : ''}`} role="row">
          <b role="rowheader">{nome}</b>
          {(['manha', 'tarde'] as const).map(p => { const r = semana.find(x => x.weekday === d && x.period === p)!
            return <div key={p} className={`site-slot${r.open ? ' on' : ''}`} role="cell">
              <label className="row" style={{ gap: 6 }}><input type="checkbox" disabled={!gerente} checked={r.open} onChange={e => muda(d, p, { open: e.target.checked })} aria-label={tr("{0} {1} aberto", nome, PER[p])} />
                <span className="site-slot-rot">{PER[p]}</span></label>
              <input className="inp" type="number" min={1} max={50} disabled={!gerente || !r.open} value={r.capacity}
                onChange={e => muda(d, p, { capacity: Number(e.target.value) || 1 })} aria-label={tr("vagas {0} {1}", nome, PER[p])} />
              <span className="small muted">{tr("vagas")}</span></div> })}
        </div>)}
      </div>
      <div className="site-horarios">
        {([['morning_start', tr("Manhã começa")], ['morning_end', tr("Manhã termina")], ['afternoon_start', tr("Tarde começa")], ['afternoon_end', tr("Tarde termina")]] as const).map(([k, rot]) =>
          <label key={k} className="fld" style={{ margin: 0 }}><span>{rot}</span><input type="time" disabled={!gerente} value={c[k]} onChange={e => setCfg({ ...c, [k]: e.target.value })} /></label>)}
        <label className="fld" style={{ margin: 0 }}><span>{tr("Antecedência (horas)")}</span><input type="number" min={0} disabled={!gerente} value={c.min_notice_hours} onChange={e => setCfg({ ...c, min_notice_hours: Number(e.target.value) })} /></label>
        <label className="fld" style={{ margin: 0 }}><span>{tr("Mostra até (dias)")}</span><input type="number" min={1} disabled={!gerente} value={c.horizon_days} onChange={e => setCfg({ ...c, horizon_days: Number(e.target.value) })} /></label>
      </div>
      <label className="check" style={{ marginTop: 10 }}><input type="checkbox" disabled={!gerente} checked={!!c.auto_confirm} onChange={e => setCfg({ ...c, auto_confirm: e.target.checked ? 1 : 0 })} /> {tr("Confirmar sozinho")} <span className="small muted">{tr("(desligado: a equipe confirma cada pedido)")}</span></label>
      {/* #164: venda automática — o site vende sozinho (só o administrador liga ou desliga) */}
      <label className="check" style={{ marginTop: 6 }}><input type="checkbox" disabled={!admin || salvandoVenda} checked={!!c.auto_sell} onChange={async e => {
        const ligar = e.target.checked
        setSalvandoVenda(true)
        try { await api.patch('/site/agenda/config', { auto_sell: ligar }); toast(ligar ? tr("Venda automática ligada: o pedido do site é cobrado e a waiver sai na hora (cliente novo no Stripe; aluno recorrente: do plano ou extra por invoice).") : tr("Venda automática desligada: a equipe aceita cada pedido."), 'ok'); setCfg(null); a.reload() }
        catch (ex) { toast((ex as ApiError).message, 'crit') } finally { setSalvandoVenda(false) } }} /> {tr("Venda automática")} <span className="small muted">{tr("(ligada: cobra e manda a waiver na hora, sem esperar \"Aceitar\". Cliente novo paga no Stripe pelo carrinho do site (sem o Stripe, invoice do QuickBooks com o depósito); aluno recorrente da Academy: a sessão do plano sai sem custo e a extra vira invoice do QuickBooks, sem depósito;")} {admin ? tr("só o administrador liga ou desliga") : tr("só o administrador muda")})</span></label>
      {gerente && (regras || cfg) && <div style={{ marginTop: 10 }}><button className="btn primary" onClick={salvar}>{regras ? tr("Salvar a semana") : tr("Salvar regras")}</button></div>}
    </Section>

    <Section title={tr("Bloqueios")} count={a.data.bloqueios.length}>
      {!a.data.bloqueios.length ? <Empty title={tr("Nenhum bloqueio")} /> : <div className="tbl">{a.data.bloqueios.map(b => <div className="tr" key={b.id}>
        <div className="grow">{descreve(b)} · {PER[b.period]}{b.reason ? <span className="small muted"> · {b.reason}</span> : null}</div>
        {b.weekday != null && <Chip tone="info">{tr("recorrente")}</Chip>}
        {gerente && <button className="btn sm ghost" onClick={() => desbloquear(b)}>{tr("Desbloquear")}</button>}
      </div>)}</div>}
    </Section>
  </div>
}

interface Sugestao { client_id: number; name: string; pilot_name: string | null; email: string | null; phone: string | null; motivo: string }
interface ContaSite { id: number; email: string; name: string; phone: string | null; city: string | null; state: string | null; created_at: string
  client_id: number | null; client_name: string | null; client_pilot: string | null; linked_at: string | null; linked_by_name: string | null
  drivers: number; pilotos: string[]; sugestao: Sugestao | null; drivers_list: DriverConta[]; welcome_error?: string | null }
/** Driver da conta e o card dele (#65): cada driver tem o seu Client ID. */
interface DriverConta { id: number; name: string; birth_date: string | null; client_id: number | null; client_name: string | null; client_pilot: string | null
  sugestao: { client_id: number; name: string; pilot_name: string | null; motivo: string } | null }

/* #263: os karts que a página do Arrive and Drive vende. A chave é o nome do kart, o mesmo de
 * `command_center/vitrine/conteudo.py` (`KARTS`) e o mesmo que vai em `booking_services.site_kart`.
 * `test_servico_do_kart.py` tranca os dois lados juntos. */
// #279: o kart próprio é a 5ª opção (dono, 15/10)
const KARTS_DO_SITE = ['Baby Kart', '4-stroke', '2-stroke', 'Adult Shifter', 'Own kart']
// #297 (dono, 16/10): "se a gente quiser adicionar algum outro" — um kart novo é uma chave nova, escrita aqui
const NOVO_KART = '__novo__'
function opcoesDeKart(atual: string | null | undefined) {
  const extra = atual && !KARTS_DO_SITE.includes(atual) && atual !== NOVO_KART ? [atual] : []
  return [...KARTS_DO_SITE, ...extra]
}

interface ListaServicos { servicos: Servico[]; itens_qbo: ItemQbo[]; paginas: PaginaSite[]; chave_addon: string }
const chaveDe = (k: string | null | undefined) => (k || '').split(/\s+/).filter(Boolean).join(' ').toLowerCase()

/* #312: onde o serviço que já existe aparece hoje no site — a página (com o link) e de que jeito. */
function OndeNoSite({ n, paginas }: { n?: NoSite; paginas: PaginaSite[] }) {
  if (!n) return null
  const pg = paginas.find(p => p.id === n.pagina)
  // #312 (revisão): o link da página é um botão ao lado do chip (alvo de 40 px no celular), não um link de 17 px dentro dele
  const ver = pg ? <> <a className="btn sm ghost" href={pg.caminho} target="_blank" rel="noreferrer" aria-label={tr("Abrir {0} no site", pg.nome)}>{tr("Ver no site ↗")}</a></> : null
  if (n.onde === 'kart') return <><Chip tone="ok">{tr("no site:")} {pg?.nome} · {tr("kart {0}", n.chave || '')}</Chip>{ver}</>
  if (n.onde === 'addon') return <><Chip tone="ok">{tr("no site:")} {pg?.nome} · {tr("add-on na reserva")}</Chip>{ver}</>
  if (n.onde === 'plano') return <><Chip tone="ok">{tr("no site:")} {pg?.nome} · {tr("plano mensal")}</Chip>{ver}</>
  if (n.onde === 'area') return <Chip tone="info">{tr("só na área do cliente")}</Chip>
  if (n.onde === 'repetido') return <Chip tone="crit">{tr("fora do site: a chave {0} também está em {1} (um serviço ativo por chave)", n.chave || '', n.com.join(', '))}</Chip>
  if (n.onde === 'nenhum') return <Chip tone="warn">{tr("fora do site: só o add-on Lead and Follow entra na reserva")}</Chip>
  return <Chip tone="neutral">{tr("desativado")}</Chip>
}

/* #312 (dono, 16/10): "a gente escolhe em qual página que esse serviço vai estar". O primeiro passo é a página do
 * site; o segundo, quando a página tem dois jeitos, como ele entra nela. Cada jeito grava o que o site já lê:
 * - Arrive and Drive · kart: serviço de sessão com o "Kart do site" (`booking_services.site_kart`);
 * - Arrive and Drive · add-on do dia: serviço de tipo add-on com a chave do Lead and Follow;
 * - Academy · plano mensal: serviço de tipo plano (com plano ativo, a Academy mostra os planos, não os cartões);
 * - Academy, Pro Team, For Beginners · cartão de preço: um cartão da página (`site_offers`);
 * - Só na área do cliente: serviço de sessão sem kart.
 * Em cada página, o painel mostra o que já está nela hoje; o kart que já tem serviço ativo não se escolhe de novo
 * (dois serviços com o mesmo kart tiram o kart do site). */
type Como = 'kart' | 'addon' | 'plano' | 'cartao' | 'area'
const COMO_DA_PAGINA: Record<string, Como[]> = { 'arrive-and-drive': ['kart', 'addon'], academy: ['plano', 'cartao'], 'pro-team': ['cartao'], 'for-beginners': ['cartao'], area: ['area'] }
const NOME_COMO: Record<Como, string> = { kart: tr("Kart (reserva online)"), addon: tr("Add-on do dia (Lead and Follow)"), plano: tr("Plano mensal vendido pelo site"),
  cartao: tr("Cartão de preço"), area: tr("Sessão avulsa") }

function NovoServico({ dados, recarregar }: { dados: ListaServicos; recarregar: () => void }) {
  const toast = useToast()
  const id = useId()
  const { servicos, paginas, chave_addon } = dados
  // #317 (dono, 16/10): "o serviço que eu coloquei no checkout ia permitir que eu fizesse o checkout … sem o security
  // deposit". A sessão nova já nasce com o depósito obrigatório marcado: sem valor, não salva.
  const vazio = { name: '', description: '', price: '', qbo_item: '', months: '', sessions_month: '', site_kart: '', kart_novo: '', site_title: '', site_subtitle: '',
    deposit: '', deposit_required: true, extra_price: '', extra_item: '' }
  const [novo, setNovo] = useState(vazio)
  const [pagina, setPagina] = useState('')
  const [como, setComo] = useState<Como | ''>('')
  const c = useGet<{ cartoes: Cartao[]; paginas: Record<string, string>; preco_kart: number }>(pagina && paginas.find(p => p.id === pagina)?.cartoes ? '/site/cartoes' : null)
  const ativos = servicos.filter(s => s.active)
  const opcoes = [...paginas.map(p => ({ id: p.id, nome: p.nome })), { id: 'area', nome: tr("Só na área do cliente") }]
  const escolher = (pg: string) => { setPagina(pg); setComo(COMO_DA_PAGINA[pg][0]) }
  const kind = como === 'plano' ? 'plan' : como === 'addon' ? 'addon' : 'session'
  const sessao = kind === 'session'
  // o kart que já tem serviço ativo: mostra qual é e não deixa repetir
  const donoDoKart = (k: string) => ativos.filter(s => (s.kind ?? 'session') === 'session' && chaveDe(s.site_kart) === chaveDe(k))
  const karts = [...KARTS_DO_SITE, ...[...new Set(servicos.filter(s => (s.kind ?? 'session') === 'session' && s.site_kart && !KARTS_DO_SITE.includes(s.site_kart)).map(s => s.site_kart!))]]
  const addonHoje = ativos.filter(s => s.kind === 'addon' && chaveDe(s.site_kart) === chaveDe(chave_addon))
  const temPlano = ativos.some(s => s.kind === 'plan')
  // #312 (revisão, NO FAKE DATA): com plano ativo a Academy mostra os planos, não os cartões — eles não estão na página
  const cartoesDaPagina = (c.data?.cartoes || []).filter(x => x.page === pagina && x.active)
  const escondePlano = pagina === 'academy' && temPlano
  const rotuloCartao = (x: Cartao) => x.grp ? tr("cartão {0} · {1}", x.grp, x.title) : tr("cartão {0}", x.title)
  const hoje = pagina === 'arrive-and-drive'
    ? [...servicos.filter(s => s.no_site?.onde === 'kart').map(s => tr("kart {0} ({1})", s.no_site!.chave || '', s.name)),
      ...servicos.filter(s => s.no_site?.onde === 'addon').map(s => tr("add-on {0}", s.name))]
    : pagina === 'area' ? servicos.filter(s => s.no_site?.onde === 'area').map(s => s.name)
    : [...(pagina === 'academy' ? servicos.filter(s => s.no_site?.onde === 'plano').map(s => tr("plano {0}", s.name)) : []),
      ...(escondePlano ? [] : cartoesDaPagina.map(rotuloCartao))]
  const kartEscolhido = novo.site_kart === NOVO_KART ? novo.kart_novo.trim() : novo.site_kart
  const deposito = Number(novo.deposit.replace(/[$,\s]/g, ''))
  const pode = !!novo.name && !!novo.price && (!sessao || !novo.deposit_required || deposito > 0)
    && (como !== 'kart' || (!!kartEscolhido && !donoDoKart(kartEscolhido).length)) && (como !== 'addon' || !addonHoje.length)
  async function criar() {
    try {
      await api.post('/site/servicos', { name: novo.name, description: novo.description || null, price: novo.price, qbo_item: novo.qbo_item || null, kind,
        site_kart: como === 'kart' ? kartEscolhido : como === 'addon' ? chave_addon : null,
        site_title: como === 'kart' || como === 'addon' ? (novo.site_title || null) : null, site_subtitle: como === 'kart' ? (novo.site_subtitle || null) : null,
        months: kind === 'plan' ? (novo.months || '1') : null, sessions_month: kind === 'plan' ? (novo.sessions_month || null) : null,
        extra_price: kind === 'plan' ? (novo.extra_price || null) : null, extra_item: kind === 'plan' ? (novo.extra_item || null) : null,
        deposit: sessao ? (novo.deposit || null) : null, deposit_required: sessao && novo.deposit_required })
      toast(kind === 'plan' ? tr("Plano criado: já aparece na página da Academy.") : como === 'addon' ? tr("Add-on criado: já aparece na reserva do Arrive and Drive.")
        : como === 'kart' ? tr("Serviço criado: o kart já aparece no Arrive and Drive.") : tr("Serviço criado: o cliente já vê."), 'ok')
      setNovo(vazio); recarregar()
    } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  const pg = paginas.find(p => p.id === pagina)
  return <div className="stack" style={{ gap: 14 }}>
    <div className="ins-passo"><span id={`${id}-pg`} className="ins-passo-rot">{tr("Em qual página do site?")}</span>
      <div className="seg" role="radiogroup" aria-labelledby={`${id}-pg`}>{opcoes.map(o =>
        <button key={o.id} type="button" role="radio" aria-checked={pagina === o.id} className={`btn sm${pagina === o.id ? '' : ' ghost'}`} onClick={() => escolher(o.id)}>{o.nome}</button>)}</div></div>
    {pagina && COMO_DA_PAGINA[pagina].length > 1 && <div className="ins-passo"><span id={`${id}-como`} className="ins-passo-rot">{tr("Como ele entra na página?")}</span>
      <div className="seg" role="radiogroup" aria-labelledby={`${id}-como`}>{COMO_DA_PAGINA[pagina].map(k =>
        <button key={k} type="button" role="radio" aria-checked={como === k} className={`btn sm${como === k ? '' : ' ghost'}`} onClick={() => setComo(k)}>{NOME_COMO[k]}</button>)}</div></div>}
    {pagina && <div className="ins-onde">
      <p>{pg ? <>{tr("Hoje em")} <b>{pg.nome}</b>: </> : <>{tr("Hoje só na área do cliente:")} </>}
        {hoje.length ? hoje.join(' · ') : (pg?.cartoes && c.loading ? '…' : tr("nada ainda"))}
        {escondePlano && cartoesDaPagina.length > 0 && <span className="ins-escondido"> · {tr("escondidos pelo plano ativo: {0}", cartoesDaPagina.map(rotuloCartao).join(', '))}</span>}</p>
      {pg && <a className="btn sm ghost" href={pg.caminho} target="_blank" rel="noreferrer" aria-label={tr("Abrir {0} no site", pg.nome)}>{tr("Ver no site ↗")}</a>}
    </div>}
    {como === 'cartao' && <>
      {pagina === 'academy' && temPlano && <Banner tone="warn">{tr("Com plano ativo, a Academy mostra os planos no lugar dos cartões: este cartão só aparece quando nenhum plano estiver ativo.")}</Banner>}
      {c.data ? <FormCartao paginas={c.data.paginas} pagina={pagina} precoKart={c.data.preco_kart} onCriado={c.reload} />
        : c.error ? <ErrorState error={c.error} retry={c.reload} /> : <Loading />}</>}
    {como && como !== 'cartao' && <>
      {como === 'plano' && <p className="small muted" style={{ margin: 0 }}>{tr("Com plano ativo, a Academy mostra os planos do painel no lugar dos cartões.")}</p>}
      {como === 'addon' && addonHoje.length > 0 && <Banner tone="warn">{tr("A reserva já vende o add-on {0}. Dois tiram a caixa do site: desative aquele na lista antes de criar outro.", addonHoje.map(s => s.name).join(', '))}</Banner>}
      <div className="site-servico">
        <label className="fld"><span>{tr("Nome")}</span><input value={novo.name} onChange={x => setNovo({ ...novo, name: x.target.value })} placeholder={como === 'addon' ? 'Lead and Follow' : tr("Arrive and Drive")} /></label>
        <label className="fld"><span>{como === 'addon' ? tr("Texto da caixa na reserva") : tr("Descrição")} <i>{tr("opcional")}</i></span><input value={novo.description} onChange={x => setNovo({ ...novo, description: x.target.value })} /></label>
        <label className="fld"><span>{kind === 'plan' ? tr("Preço por mês (US$)") : tr("Preço (US$)")}</span><input inputMode="decimal" value={novo.price} onChange={x => setNovo({ ...novo, price: x.target.value })} placeholder="719.00" /></label>
        {kind === 'plan' && <>
          <label className="fld"><span>{tr("Meses do plano")}</span><input inputMode="numeric" value={novo.months} onChange={x => setNovo({ ...novo, months: x.target.value })} placeholder="3" /></label>
          <label className="fld"><span>{tr("Sessões por mês")}</span><input inputMode="numeric" value={novo.sessions_month} onChange={x => setNovo({ ...novo, sessions_month: x.target.value })} placeholder="4" /></label>
          <label className="fld"><span>{tr("Valor da sessão extra (US$)")} <i>{tr("vazio = mensal ÷ sessões")}</i></span><input inputMode="decimal" value={novo.extra_price} onChange={x => setNovo({ ...novo, extra_price: x.target.value })} /></label>
          <label className="fld"><span>{tr("Item da sessão extra")} <i>{tr("vazio = o \"Extra session\" do QuickBooks")}</i></span><input list="itens-qbo" value={novo.extra_item} placeholder={tr("escolha da lista")}
            onChange={x => setNovo({ ...novo, extra_item: x.target.value })} /></label></>}
        <label className="fld"><span>{tr("Item no QuickBooks")} <i>{tr("ou texto")}</i></span><input list="itens-qbo" value={novo.qbo_item} placeholder={tr("escolha ou escreva")}
          onChange={x => setNovo({ ...novo, qbo_item: x.target.value })} /></label>
        {sessao && <>
          <label className="fld"><span>{tr("Depósito por sessão (US$)")} <i>{novo.deposit_required ? tr("obrigatório") : tr("0 = sem")}</i></span>
            <input inputMode="decimal" value={novo.deposit} placeholder="400.00" onChange={x => setNovo({ ...novo, deposit: x.target.value })} /></label>
          <label className="check" style={{ minHeight: 40 }}><input type="checkbox" checked={novo.deposit_required}
            onChange={x => setNovo({ ...novo, deposit_required: x.target.checked })} /> {tr("Security deposit obrigatório")}</label></>}
        {como === 'kart' && <>
          <label className="fld"><span>{tr("Kart do site")} <i>{tr("Arrive and Drive")}</i></span>
            <select value={novo.site_kart} onChange={x => setNovo({ ...novo, site_kart: x.target.value })}>
              <option value="">{tr("escolha o kart")}</option>
              {karts.map(k => { const d = donoDoKart(k)
                return <option key={k} value={k} disabled={!!d.length}>{d.length ? tr("{0} · hoje: {1}", k, d.map(s => s.name).join(', ')) : k}</option> })}
              <option value={NOVO_KART}>{tr("Novo kart…")}</option></select></label>
          {novo.site_kart === NOVO_KART &&
            <label className="fld"><span>{tr("Nome do kart novo")}</span><input value={novo.kart_novo} placeholder="Rental 2-stroke Pro"
              onChange={x => setNovo({ ...novo, kart_novo: x.target.value })} /></label>}</>}
        {(como === 'kart' || como === 'addon') && <label className="fld"><span>{tr("Nome no site")}</span><input value={novo.site_title} onChange={x => setNovo({ ...novo, site_title: x.target.value })} /></label>}
        {como === 'kart' && <label className="fld"><span>{tr("Linha de baixo no site")} <i>{tr("ex.: Ages 7+")}</i></span><input value={novo.site_subtitle}
          onChange={x => setNovo({ ...novo, site_subtitle: x.target.value })} /></label>}
        <button className="btn sm primary" disabled={!pode} onClick={criar}>{tr("Criar")}</button>
      </div>
      {como === 'kart' && !!kartEscolhido && donoDoKart(kartEscolhido).length > 0 && <p className="small" style={{ margin: 0, color: 'var(--crit)' }}>{tr("Esse kart já tem serviço ativo.")}</p>}
      {como === 'kart' && <p className="small muted" style={{ margin: 0 }}>{tr("O kart que já tem serviço ativo fica bloqueado: dois serviços com o mesmo kart tiram o kart do site. Para trocar o serviço de um kart, desative o de hoje na lista.")}</p>}
      <p className="small muted" style={{ margin: 0 }}>{tr("Mudar o preço vale para os próximos agendamentos: quem já marcou fica com o valor do dia em que marcou. A lista mostra só os itens Academy e o Daily Using Own Kart do QuickBooks; o que não for item vira o texto da linha da invoice. O \"Kart do site\" é o que liga o serviço ao kart da página do Arrive and Drive: sem ele, aquele kart não aparece no site; desativar o serviço tira aquele kart da página.")} {tr("O nome no site, a linha de baixo e o aviso são o que o cartão do kart mostra; vazio volta ao texto de sempre. \"Novo kart…\" cria um kart a mais na página, com o preço e o depósito deste serviço.")}</p>
    </>}
  </div>
}

/* Serviços e preços (#50): o gerente muda o preço aqui, sem código. Quem já marcou fica
 * com o valor do dia; desativar tira da área do cliente sem apagar. */
function Servicos() {
  const { can } = useAuth()
  const gerente = can('MANAGER')
  const toast = useToast()
  const l = useGet<ListaServicos>('/site/servicos')
  type Edicao = Partial<Omit<Servico, 'own_kart'>> & { price_txt?: string; qbo_item?: string; deposit_txt?: string; months_txt?: string; sessions_txt?: string
    extra_txt?: string; extra_item?: string
    kart_novo?: string; own_kart?: boolean }
  const [edit, setEdit] = useState<Record<number, Edicao>>({})
  const itens = l.data?.itens_qbo || []
  async function salvar(sv: Servico, extra?: Partial<Servico>) {
    const e = edit[sv.id] || {}
    const corpo: Record<string, unknown> = { ...extra }
    if (e.name !== undefined) corpo.name = e.name
    if (e.description !== undefined) corpo.description = e.description || null
    if (e.price_txt !== undefined) corpo.price = e.price_txt
    if (e.qbo_item !== undefined) corpo.qbo_item = e.qbo_item || null
    if (e.deposit_txt !== undefined) corpo.deposit = e.deposit_txt || null
    if (e.deposit_required !== undefined) corpo.deposit_required = !!e.deposit_required     // #317
    if (e.site_kart !== undefined) corpo.site_kart = (e.site_kart === NOVO_KART ? e.kart_novo : e.site_kart) || null   // #263; #297: ou um kart novo
    if (e.site_title !== undefined) corpo.site_title = e.site_title || null       // #297: o cartão no site
    if (e.site_subtitle !== undefined) corpo.site_subtitle = e.site_subtitle || null
    if (e.site_note !== undefined) corpo.site_note = e.site_note || null
    if (e.own_kart !== undefined) corpo.own_kart = e.own_kart
    if (e.kind !== undefined) corpo.kind = e.kind
    if (e.months_txt !== undefined) corpo.months = e.months_txt || null
    if (e.sessions_txt !== undefined) corpo.sessions_month = e.sessions_txt || null
    if (e.extra_txt !== undefined) corpo.extra_price = e.extra_txt || null          // #314
    if (e.extra_item !== undefined) corpo.extra_item = e.extra_item || null
    try { await api.patch(`/site/servicos/${sv.id}`, corpo); toast(tr("Salvo. Vale para os próximos agendamentos."), 'ok')
      setEdit(x => { const y = { ...x }; delete y[sv.id]; return y }); l.reload() }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!l.data) return <Loading />
  const muda = (id: number, x: Edicao) => setEdit(e => ({ ...e, [id]: { ...e[id], ...x } }))
  /** #312 (revisão): os outros serviços ATIVOS do mesmo tipo com esta chave (a mesma regra do servidor e da página) */
  const outrosComChave = (sv: Servico, chave: string | null | undefined, kind: string) => chaveDe(chave) && (kind === 'session' || kind === 'addon')
    ? l.data!.servicos.filter(o => o.id !== sv.id && o.active && (o.kind ?? 'session') === kind && chaveDe(o.site_kart) === chaveDe(chave)) : []
  // dono, 01/10: o item é um texto — escolhe da lista ou escreve; sem o preço no rótulo
  const sugestoes = <datalist id="itens-qbo">{itens.map(i => <option key={i.id} value={i.name} />)}</datalist>
  return <div className="stack" style={{ gap: 18 }}>
    {/* #312 (dono, 16/10): "um botão de adicionar novo serviço e a gente escolhe em qual página que esse serviço vai
        estar, e aí abra essa seção". Fica no topo, antes da lista, que cresce. */}
    {gerente && <InserirNoTopo rotulo={tr("Adicionar serviço")} titulo={tr("Novo serviço")} primario inicial={!l.data.servicos.length}>
      <NovoServico dados={l.data} recarregar={l.reload} />
    </InserirNoTopo>}
    {!l.data.servicos.some(x => x.active) && <div className="banner warn"><span className="bi">▲</span><div className="grow">{tr("Nenhum serviço ativo: o cliente")} <b>{tr("não consegue marcar")}</b> {tr("até haver pelo menos um, com preço.")}</div></div>}
    {sugestoes}
    <Section title={tr("Serviços")} count={l.data.servicos.length}>
      {!l.data.servicos.length ? <Empty title={tr("Nenhum serviço ainda")}>{tr("Use \"Adicionar serviço\", em cima, para cadastrar o que o cliente pode marcar e o preço de cada um.")}</Empty>
        : <div className="cd-grade">{l.data.servicos.map(sv => {
          const e = edit[sv.id] || {}
          // #312 (revisão): reativar não pode deixar dois ativos com a mesma chave (o kart ou a caixa do add-on sairia do site)
          const conflito = sv.active ? [] : outrosComChave(sv, sv.site_kart, sv.kind ?? 'session')
          const n = sv.no_site?.onde
          const [rot, tom]: [string, TomD] = !sv.active || n === 'desativado' ? [tr("desativado"), 'neutral'] : n === 'kart' || n === 'addon' || n === 'plano' ? [tr("no site"), 'ok']
            : n === 'area' ? [tr("só na área do cliente"), 'info'] : n === 'repetido' ? [tr("fora do site"), 'crit'] : n === 'nenhum' ? [tr("fora do site"), 'warn'] : [tr("ativo"), 'ok']
          return <CartaoD key={sv.id} id={`servico-${sv.id}`} estado={rot} tom={tom} nome={sv.name}
            sub={[TIPO_SERVICO[sv.kind ?? 'session']]} grande={usd(sv.price)} detalhe={sv.kind === 'plan' ? tr("por mês") : null}
            acoes={gerente ? <>
              <button className="btn primary" disabled={!edit[sv.id]} onClick={() => salvar(sv)}>{tr("Salvar")}</button>
              <button className="btn" disabled={!!conflito.length} onClick={() => salvar(sv, { active: sv.active ? 0 : 1 })}>{sv.active ? tr("Desativar") : tr("Reativar")}</button></> : null}>
            <div className="cd-form"><div className="site-servico">
              <label className="fld"><span>{tr("Nome (o cliente lê, em inglês)")}</span><input value={e.name ?? sv.name} disabled={!gerente} onChange={x => muda(sv.id, { name: x.target.value })} /></label>
              <label className="fld"><span>{tr("Descrição")} <i>{tr("opcional")}</i></span><input value={e.description ?? sv.description ?? ''} disabled={!gerente} onChange={x => muda(sv.id, { description: x.target.value })} /></label>
              <label className="fld"><span>{tr("Tipo")}</span><select value={e.kind ?? sv.kind ?? 'session'} disabled={!gerente} onChange={x => muda(sv.id, { kind: x.target.value as 'session' | 'plan' | 'addon' })}>
                <option value="session">{tr("Sessão avulsa")}</option><option value="plan">{tr("Plano mensal (Academy, Boost)")}</option>
                <option value="addon">{tr("Add-on do dia de treino (Lead and Follow)")}</option></select></label>
              <label className="fld"><span>{(e.kind ?? sv.kind) === 'plan' ? tr("Preço por mês (US$)") : tr("Preço (US$)")}</span><input inputMode="decimal" value={e.price_txt ?? String(sv.price)} disabled={!gerente} onChange={x => muda(sv.id, { price_txt: x.target.value })} /></label>
              {(e.kind ?? sv.kind) === 'plan' && <>
                <label className="fld"><span>{tr("Meses do plano")}</span><input inputMode="numeric" value={e.months_txt ?? String(sv.months ?? 1)} disabled={!gerente} onChange={x => muda(sv.id, { months_txt: x.target.value })} /></label>
                <label className="fld"><span>{tr("Sessões por mês")}</span><input inputMode="numeric" value={e.sessions_txt ?? String(sv.sessions_month ?? '')} disabled={!gerente} onChange={x => muda(sv.id, { sessions_txt: x.target.value })} /></label>
                {/* #314: a sessão além do pacote do mês, para quem comprou este plano */}
                <label className="fld"><span>{tr("Valor da sessão extra (US$)")} <i>{tr("vazio = mensal ÷ sessões")}</i></span><input inputMode="decimal" value={e.extra_txt ?? (sv.extra_price != null ? String(sv.extra_price) : '')} disabled={!gerente}
                  placeholder={sv.sessions_month ? (Math.round(sv.price * 100 / sv.sessions_month) / 100).toFixed(2) : ''} onChange={x => muda(sv.id, { extra_txt: x.target.value })} /></label>
                <label className="fld"><span>{tr("Item da sessão extra")} <i>{tr("vazio = o \"Extra session\" do QuickBooks")}</i></span><input list="itens-qbo" value={e.extra_item ?? sv.extra_item_name ?? ''} disabled={!gerente}
                  onChange={x => muda(sv.id, { extra_item: x.target.value })} placeholder={tr("escolha da lista")} /></label></>}
              <label className="fld"><span>{tr("Item no QuickBooks")} <i>{tr("ou texto")}</i></span><input list="itens-qbo" value={e.qbo_item ?? sv.qbo_item_name ?? sv.invoice_text ?? ''} disabled={!gerente}
                onChange={x => muda(sv.id, { qbo_item: x.target.value })} placeholder={tr("escolha ou escreva")} /></label>
              <label className="fld"><span>{tr("Depósito por sessão (US$)")} <i>{tr("0 = sem")}</i></span><input inputMode="decimal" value={e.deposit_txt ?? String(sv.deposit ?? 0)} disabled={!gerente}
                onChange={x => muda(sv.id, { deposit_txt: x.target.value })} /></label>
              {(e.kind ?? sv.kind ?? 'session') === 'session' &&
                <label className="check" style={{ minHeight: 40 }}><input type="checkbox" checked={!!(e.deposit_required ?? sv.deposit_required)} disabled={!gerente}
                  onChange={x => muda(sv.id, { deposit_required: x.target.checked })} /> {tr("Security deposit obrigatório")}</label>}
              {(e.kind ?? sv.kind ?? 'session') === 'session' &&
                <label className="fld"><span>{tr("Kart do site")} <i>{tr("Arrive and Drive")}</i></span>
                  <select value={e.site_kart ?? sv.site_kart ?? ''} disabled={!gerente} onChange={x => muda(sv.id, { site_kart: x.target.value })}>
                    <option value="">{tr("não é do site")}</option>
                    {opcoesDeKart(sv.site_kart).map(k => { const d = sv.active ? outrosComChave(sv, k, 'session') : []
                      return <option key={k} value={k} disabled={!!d.length}>{d.length ? tr("{0} · hoje: {1}", k, d.map(o => o.name).join(', ')) : k}</option> })}
                    <option value={NOVO_KART}>{tr("Novo kart…")}</option></select></label>}
              {(e.site_kart ?? sv.site_kart) === NOVO_KART &&
                <label className="fld"><span>{tr("Nome do kart novo")}</span><input value={e.kart_novo ?? ''} disabled={!gerente} placeholder="Rental 2-stroke Pro"
                  onChange={x => muda(sv.id, { kart_novo: x.target.value })} /></label>}
              {/* #297: o cartão que o site mostra — vazio volta ao texto de sempre */}
              {(e.site_kart ?? sv.site_kart) && <>
                <label className="fld"><span>{tr("Nome no site")}</span><input value={e.site_title ?? sv.site_title ?? ''} disabled={!gerente}
                  placeholder={sv.name} onChange={x => muda(sv.id, { site_title: x.target.value })} /></label>
                {(e.kind ?? sv.kind ?? 'session') === 'session' && <>
                  <label className="fld"><span>{tr("Linha de baixo no site")} <i>{tr("ex.: Ages 7+")}</i></span><input value={e.site_subtitle ?? sv.site_subtitle ?? ''} disabled={!gerente}
                    onChange={x => muda(sv.id, { site_subtitle: x.target.value })} /></label>
                  <label className="fld"><span>{tr("Aviso no cartão")} <i>{tr("opcional")}</i></span><input value={e.site_note ?? sv.site_note ?? ''} disabled={!gerente}
                    onChange={x => muda(sv.id, { site_note: x.target.value })} /></label>
                  <label className="check" style={{ minHeight: 40 }}><input type="checkbox" checked={e.own_kart ?? !!sv.own_kart} disabled={!gerente}
                    onChange={x => muda(sv.id, { own_kart: x.target.checked })} /> {tr("O cliente traz o próprio kart")}</label></>}</>}
            </div></div>
            {gerente && conflito.length > 0 && <p className="cd-aviso warn">{tr("Para reativar, desative antes \"{0}\": ele já usa a chave {1}.", conflito.map(o => o.name).join(', '), sv.site_kart || '')}</p>}
            <div className="cd-aviso small muted"><OndeNoSite n={sv.no_site} paginas={l.data!.paginas} />
              {sv.kind === 'plan' && <> · <span>{tr("plano de")} {sv.months ?? 1} {(sv.months ?? 1) > 1 ? tr("meses") : tr("mês")}{sv.sessions_month ? tr(", {0} sessões/mês", sv.sessions_month) : ''}{tr(": a 1ª mensalidade sai na hora, as outras no dia 1")}</span></>}
              {sv.kind === 'plan' && <> · <span>{tr("sessão extra")} {sv.extra_price != null ? usd(sv.extra_price) : tr("= mensal ÷ sessões")}</span></>}
              {(sv.kind ?? 'session') === 'session' && (sv.deposit_required ? <> · <Chip tone="ok">{tr("depósito obrigatório")}</Chip></>
                : !(sv.deposit ?? 0) ? <> · <Chip tone="warn">{tr("sem security deposit")}</Chip></> : null)}
              {sv.qbo_item_id ? <> · <span>{tr("item do QuickBooks")}</span></> : sv.invoice_text ? <> · <span>{tr("texto personalizado na invoice")}</span></> : <> · <span>{tr("sem item: o site cobra pelo Stripe; a invoice da equipe pede a linha")}</span></>}</div>
          </CartaoD>
        })}</div>}
    </Section>
  </div>
}

/* Cartões das páginas (#297, parte 2). Dono, 16/10: "os serviços que estão lá em cada página, a gente consiga
 * alterar o valor, alterar o nome, alterar as coisas ali pelo Command Center". Os cartões de preço da Academy, do
 * Pro Team e do For Beginners: editar, criar, esconder (não apaga) e mudar a ordem. */
interface Cartao { id: number; page: string; grp: string | null; title: string; subtitle: string | null; body: string | null
  price: string | null; per: string | null; link: string | null; button: string | null; active: number; sort: number }
const CAMPOS_CARTAO: [keyof Cartao, string, string][] = [['grp', 'Grupo', 'opcional'], ['title', 'Título', ''], ['subtitle', 'Subtítulo', 'opcional'],
  ['price', 'Preço', 'texto do cartão'], ['per', 'Embaixo do preço', 'ex.: per month'], ['link', 'Link do botão', 'ex.: /contact/'], ['button', 'Texto do botão', 'ex.: Choose']]
function Cartoes() {
  const { can } = useAuth()
  const gerente = can('MANAGER')
  const toast = useToast()
  const l = useGet<{ cartoes: Cartao[]; paginas: Record<string, string>; preco_kart: number }>('/site/cartoes')
  const [edit, setEdit] = useState<Record<number, Partial<Cartao>>>({})
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!l.data) return <Loading />
  const { cartoes, paginas } = l.data
  const muda = (id: number, x: Partial<Cartao>) => setEdit(e => ({ ...e, [id]: { ...e[id], ...x } }))
  async function salvar(c: Cartao, extra?: Partial<Cartao>) {
    const corpo = { ...edit[c.id], ...extra }
    try { await api.patch(`/site/cartoes/${c.id}`, corpo); toast(tr("Salvo: a página do site já mostra."), 'ok')
      setEdit(x => { const y = { ...x }; delete y[c.id]; return y }); l.reload() }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  async function mover(c: Cartao, lista: Cartao[], passo: number) {
    const i = lista.indexOf(c), o = lista[i + passo]
    if (!o) return
    try { await api.patch(`/site/cartoes/${c.id}`, { sort: o.sort }); await api.patch(`/site/cartoes/${o.id}`, { sort: c.sort === o.sort ? c.sort + passo : c.sort }); l.reload() }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  return <div className="stack" style={{ gap: 18 }}>
    {/* #312: a inserção fica no topo, antes das três páginas de cartões */}
    {gerente && <InserirNoTopo rotulo={tr("Adicionar cartão")} titulo={tr("Novo cartão")} primario>
      <FormCartao paginas={paginas} precoKart={l.data.preco_kart} onCriado={l.reload} /></InserirNoTopo>}
    <p className="small muted" style={{ margin: 0 }}>{tr("No preço, {kart} vira o menor preço de kart do painel (hoje {0}); {academy} e {boost}, o plano do painel. Esconder tira da página sem apagar. Página sem cartão ativo volta ao texto de sempre.", `$${l.data.preco_kart}`)}</p>
    {Object.keys(paginas).map(pg => {
      const lista = cartoes.filter(c => c.page === pg)
      return <Section key={pg} title={NOMES_CARTAO[pg] || pg} count={lista.filter(c => c.active).length}
        right={<a className="btn sm ghost" href={paginas[pg]} target="_blank" rel="noreferrer">{tr("Ver no site ↗")}</a>}>
        <div className="cd-grade">{lista.map(c => {
          const e = edit[c.id] || {}
          return <CartaoD key={c.id} id={`cartao-${c.id}`} dados={{ 'data-cartao': c.id }} estado={c.active ? tr("na página") : tr("escondido")} tom={c.active ? 'ok' : 'neutral'}
            nome={c.title} sub={[c.grp, c.subtitle]} grande={c.price || null} detalhe={c.per}
            acoes={gerente ? <>
              <button className="btn primary" disabled={!edit[c.id]} onClick={() => salvar(c)}>{tr("Salvar")}</button>
              <button className="btn" onClick={() => salvar(c, { active: c.active ? 0 : 1 })}>{c.active ? tr("Esconder") : tr("Mostrar")}</button>
              <button className="btn" aria-label={tr("Subir")} disabled={lista.indexOf(c) === 0} onClick={() => mover(c, lista, -1)}>↑</button>
              <button className="btn" aria-label={tr("Descer")} disabled={lista.indexOf(c) === lista.length - 1} onClick={() => mover(c, lista, 1)}>↓</button></> : null}>
            <div className="cd-form"><div className="site-servico">
              {CAMPOS_CARTAO.map(([k, rot, dica]) => <label key={k} className="fld"><span>{tr(rot)} {dica && <i>{tr(dica)}</i>}</span>
                <input value={String(e[k] ?? c[k] ?? '')} disabled={!gerente} onChange={x => muda(c.id, { [k]: x.target.value })} /></label>)}
              <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Texto")}</span>
                <textarea rows={3} value={e.body ?? c.body ?? ''} disabled={!gerente} onChange={x => muda(c.id, { body: x.target.value })} /></label>
            </div></div>
          </CartaoD>
        })}</div>
      </Section>
    })}
  </div>
}

const NOMES_CARTAO: Record<string, string> = { academy: 'Academy', 'pro-team': 'Pro Team', 'for-beginners': 'For Beginners' }

/* #312: o formulário do cartão novo — o mesmo em Cartões das páginas e no "Adicionar serviço" (com a página já
 * escolhida, `pagina`). Cria do mesmo jeito de antes: POST /site/cartoes, e a página do site já mostra. */
function FormCartao({ paginas, pagina, precoKart, onCriado }: { paginas: Record<string, string>; pagina?: string; precoKart: number; onCriado: () => void }) {
  const toast = useToast()
  const [novo, setNovo] = useState<Partial<Cartao>>({ page: pagina || 'academy', title: '', price: '' })
  const corpo = { ...novo, page: pagina || novo.page }
  async function criar() {
    try { await api.post('/site/cartoes', corpo); toast(tr("Cartão criado: já aparece na página."), 'ok'); setNovo({ page: corpo.page, title: '', price: '' }); onCriado() }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  return <div className="stack" style={{ gap: 10 }}>
    <div className="site-servico">
      {!pagina && <label className="fld"><span>{tr("Página")}</span><select value={novo.page} onChange={x => setNovo({ ...novo, page: x.target.value })}>
        {Object.keys(paginas).map(pg => <option key={pg} value={pg}>{NOMES_CARTAO[pg] || pg}</option>)}</select></label>}
      {CAMPOS_CARTAO.map(([k, rot, dica]) => <label key={k} className="fld"><span>{tr(rot)} {dica && <i>{tr(dica)}</i>}</span>
        <input value={String(novo[k] ?? '')} onChange={x => setNovo({ ...novo, [k]: x.target.value })} /></label>)}
      <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Texto")}</span>
        <textarea rows={3} value={novo.body ?? ''} onChange={x => setNovo({ ...novo, body: x.target.value })} /></label>
      <button className="btn sm primary" disabled={!novo.title} onClick={criar}>{tr("Criar")}</button>
    </div>
    {pagina && <p className="small muted" style={{ margin: 0 }}>{tr("No preço, {kart} vira o menor preço de kart do painel (hoje {0}); {academy} e {boost}, o plano do painel. Esconder tira da página sem apagar. Página sem cartão ativo volta ao texto de sempre.", `$${precoKart}`)}</p>}
  </div>
}

/* Pedidos do site (#236, #245): carrinho e loja em todo estado do Stripe (pago, processando, falhou,
 * expirou, no checkout), cada um com o link da página do pedido para mandar ao cliente. */
interface PedidoLista { id: number; tipo: 'produto' | 'carrinho'; status: string; total: number; pago: number | null; criado_em: string
  pago_em: string | null; nome: string | null; email: string | null; telefone: string | null; resumo: string; opp_id: number | null
  atencao: string | null; aviso_em: string | null; aviso_para: string | null; aviso_erro: string | null; refeito_de: number | null; link: string; idioma?: 'en' | 'pt'; conta?: number | null
  sem_estoque?: boolean; estoque?: { linha: string; nota: string }[] }
const POR_PAGINA_PEDIDOS = 30

function Pedidos() {
  const toast = useToast()
  const perguntar = usePerguntar()
  const [resolvendo, setResolvendo] = useState(0)
  const [filtro, setFiltro] = useState('')
  const [offset, setOffset] = useState(0)
  const l = useGet<{ pedidos: PedidoLista[]; total: number }>(`/site/pedidos?limit=${POR_PAGINA_PEDIDOS}&offset=${offset}${filtro ? `&status=${filtro}` : ''}`, 30000)
  const copiar = (p: PedidoLista) => navigator.clipboard?.writeText(p.link).then(() => toast(tr("Link do pedido copiado: mande ao cliente."), 'ok'))
  // #309 (revisão): o "sem estoque" resolvido sai do pedido e do "Pagos sem estoque" do Painel do site
  async function resolvido(p: PedidoLista) {
    if (!await perguntar({ titulo: tr("O sem estoque do pedido #{0} está resolvido?", p.id), texto: tr("Use quando a peça foi separada, o cliente combinou outro prazo ou o valor foi devolvido pelo Stripe. A frase continua no pedido e na auditoria."), ok: tr("Resolvido") })) return
    setResolvendo(p.id)
    try { await api.post(`/site/pedidos/${p.id}/estoque-resolvido`); toast(tr("Resolvido: saiu do Painel do site."), 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setResolvendo(0) }
  }
  return <>
    <div className="seg" style={{ marginBottom: 12, flexWrap: 'wrap' }}>{([['', tr("Todos")], ['pago', tr("Pagos")], ['aguardando', tr("Processando")], ['falhou', tr("Não passou")], ['expirado', tr("Expirou")], ['aberto', tr("No checkout")]] as const).map(([k, r]) =>
      <button key={k || 'todos'} className={`btn sm${filtro === k ? '' : ' ghost'}`} onClick={() => { setFiltro(k); setOffset(0) }}>{r}</button>)}</div>
    {l.error && <ErrorState error={l.error} retry={l.reload} />}
    {l.loading && !l.data && <Loading />}
    {l.data && (!l.data.pedidos.length ? <Empty title={tr("Nenhum pedido aqui")}>{tr("Os pedidos do carrinho e da loja do site aparecem aqui, em todo estado do pagamento.")}</Empty>
      : <div className="cd-grade">{l.data.pedidos.map(p => <CartaoD key={p.id} id={`pedido-${p.id}`} nivel={2}
        estado={ESTADO_PEDIDO[p.status] || p.status} tom={tomDoPedido(p.status) as TomD} avatar={p.nome || p.email || '#'} nome={p.nome || p.email || tr("sem nome ainda")}
        sub={[p.resumo, <span key="contato" className="cd-mono">{[p.email, p.telefone].filter(Boolean).join(' · ')}</span>,
          p.refeito_de ? tr("refeito do pedido #{0}", p.refeito_de) : null, p.idioma === 'pt' ? tr("comprou em português") : null]}
        grande={usd(p.pago ?? p.total)} detalhe={`${tr("Pedido #{0}", p.id)} · ${fmtDateTime(p.criado_em)}`}
        acoes={<>
          {p.sem_estoque && <button className="btn primary" disabled={resolvendo === p.id} onClick={() => resolvido(p)}
            aria-label={tr("Resolvido: sem estoque do pedido #{0}", p.id)}>{tr("Resolvido")}</button>}
          <a className="btn" href={p.link} target="_blank" rel="noreferrer">{tr("Página do pedido ↗")}</a>
          <button className="btn" onClick={() => copiar(p)}>{tr("Copiar o link")}</button>
          {p.opp_id && <Link className="btn" to={`/sales/${p.opp_id}`}>{tr("Venda")}</Link>}</>}>
        {(p.status !== 'aberto' || p.atencao || (p.estoque || []).length > 0) && <CdLista>
          {p.status !== 'aberto' && (p.aviso_em ? <CdItem tom={p.aviso_para ? 'ok' : 'warn'}>{p.aviso_para ? tr("Avisado por e-mail ({0}) em {1}.", p.aviso_para, fmtDateTime(p.aviso_em)) : tr("Sem e-mail para avisar: ligue para o cliente.")}</CdItem>
            : p.aviso_erro ? <CdItem tom="crit"><span className="cd-erro">{tr("O aviso não saiu: {0}", p.aviso_erro)}</span></CdItem> : <CdItem tom="neutral" glifo="…">{tr("Aviso por e-mail: saindo.")}</CdItem>)}
          {p.atencao && <CdItem tom="crit"><span className="cd-erro"><b>{tr("Resolver:")}</b> {p.atencao}</span></CdItem>}
          {/* #309: o que a venda tirou do estoque, para separar exatamente aquilo (no kart usado e no motor, o serial) */}
          {(p.estoque || []).map((x, i) => <CdItem key={i} tom="info"><b>{tr("Estoque:")}</b> {x.linha ? `${x.linha}: ` : ''}{x.nota}</CdItem>)}
        </CdLista>}
      </CartaoD>)}</div>)}
    {l.data && l.data.total > POR_PAGINA_PEDIDOS && <div className="row" style={{ gap: 8, marginTop: 10 }}>
      <button className="btn sm ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - POR_PAGINA_PEDIDOS))}>{tr("Anteriores")}</button>
      <span className="small muted grow" style={{ textAlign: 'center' }}>{offset + 1}–{Math.min(offset + POR_PAGINA_PEDIDOS, l.data.total)} {tr("de")} {l.data.total}</span>
      <button className="btn sm ghost" disabled={offset + POR_PAGINA_PEDIDOS >= l.data.total} onClick={() => setOffset(offset + POR_PAGINA_PEDIDOS)}>{tr("Próximas")}</button></div>}
  </>
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
    if (!await perguntar({ titulo: tr("Ligar {0} a {1}?", c.email, nome), texto: tr("O cliente passa a ver na área do cliente o histórico de serviços deste card. Confira se é mesmo a mesma família."), ok: tr("Vincular") })) return
    try { await api.post(`/site/contas/${c.id}/vincular`, { client_id: clientId }); toast(tr("Vinculado."), 'ok'); l.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function criar(c: ContaSite) {
    if (!await perguntar({ titulo: tr("Criar o cliente {0}?", c.name), texto: tr("O card nasce com os dados da conta ({0}{1}) e já fica vinculado.", c.email, c.pilotos.length ? `, piloto ${c.pilotos[0]}` : ''), ok: tr("Criar cliente") })) return
    try { await api.post(`/site/contas/${c.id}/criar-cliente`); toast(tr("Cliente criado e vinculado."), 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function vincularDriver(p: DriverConta, clientId: number, nome: string) {
    if (!await perguntar({ titulo: tr("O card de {0} é {1} (Client ID {2})?", p.name, nome, clientId), texto: tr("Cada driver tem o seu card: as sessões, o contrato e o histórico dele ficam ali, separados dos irmãos."), ok: tr("Vincular") })) return
    try { await api.post(`/site/drivers/${p.id}/vincular`, { client_id: clientId }); toast(tr("Driver vinculado."), 'ok'); l.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function criarDriver(c: ContaSite, p: DriverConta) {
    if (!await perguntar({ titulo: tr("Criar o card de {0}?", p.name), texto: tr("Responsável {0} ({1}), piloto {2}. O card nasce já vinculado a este driver, com o seu Client ID.", c.name, c.email, p.name), ok: tr("Criar card") })) return
    try { const r = await api.post<{ client_id: number }>(`/site/drivers/${p.id}/criar-cliente`); toast(tr("Card criado: Client ID {0}.", r.client_id), 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function desvincularDriver(p: DriverConta) {
    if (!await perguntar({ titulo: tr("Desligar {0} do Client ID {1}?", p.name, p.client_id), texto: tr("O card não é apagado; só deixa de ser deste driver."), ok: tr("Desvincular"), perigo: true })) return
    try { await api.post(`/site/drivers/${p.id}/desvincular`); toast(tr("Driver desvinculado."), 'ok'); l.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function desvincular(c: ContaSite) {
    if (!await perguntar({ titulo: tr("Desligar {0} de {1}?", c.email, c.client_pilot || c.client_name), texto: tr("O cliente deixa de ver o histórico."), ok: tr("Desvincular"), perigo: true })) return
    try { await api.post(`/site/contas/${c.id}/desvincular`); toast(tr("Desvinculado."), 'ok'); l.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  return <>
    <div className="seg" style={{ marginBottom: 12 }}>{([['sem_vinculo', tr("Esperando vínculo")], ['vinculadas', tr("Vinculadas")], ['todas', tr("Todas")]] as const).map(([k, r]) =>
      <button key={k} className={`btn sm${filtro === k ? '' : ' ghost'}`} onClick={() => setFiltro(k)}>{r}</button>)}</div>
    {l.error && <ErrorState error={l.error} retry={l.reload} />}
    {l.loading && !l.data && <Loading />}
    {l.data && (!l.data.contas.length ? <Empty title={filtro === 'sem_vinculo' ? tr("Nenhuma conta esperando vínculo") : tr("Nada aqui")}>{tr("As contas criadas na área do cliente aparecem aqui.")}</Empty>
      : <div className="cd-grade">{l.data.contas.map(c => <CartaoD key={c.id} id={`conta-${c.id}`} nivel={2}
        estado={c.client_id ? tr("vinculada") : tr("sem vínculo")} tom={c.client_id ? 'ok' : 'warn'} avatar={c.name} avatarTom="azul" nome={c.name}
        sub={[<span key="email" className="cd-mono">{c.email}</span>, [c.phone, c.city ? `${c.city}${c.state ? `/${c.state}` : ''}` : null].filter(Boolean).join(' · ')]}
        acoes={c.client_id ? (can('MANAGER') ? <button className="btn" onClick={() => desvincular(c)}>{tr("Desvincular")}</button> : null) : <>
          {c.sugestao ? <button className="btn primary" onClick={() => vincular(c, c.sugestao!.client_id, c.sugestao!.pilot_name || c.sugestao!.name)}>{tr("Vincular a este")}</button>
            : <button className="btn primary" onClick={() => criar(c)}>{tr("Criar cliente")}</button>}
          {outro[c.id] && <button className="btn" onClick={() => vincular(c, outro[c.id]!.id, outro[c.id]!.pilot_name || outro[c.id]!.name)}>{tr("Vincular")}</button>}</>}>
        <CdLista>
          <CdItem tom={c.pilotos.length ? 'ok' : 'warn'} valor={c.pilotos.length ? c.pilotos.join(', ') : null}>{c.pilotos.length ? tr("Pilotos") : tr("Nenhum piloto ainda")}</CdItem>
          {c.welcome_error && <CdItem tom="crit"><span className="cd-erro">{tr("O e-mail de boas-vindas não saiu ({0}). O sistema manda de novo, sem a senha; se a pessoa não achar, ela pede uma nova em Forgot password.", c.welcome_error)}</span></CdItem>}
          {c.client_id ? <CdItem tom="ok" valor={c.linked_by_name ? tr("por {0}", c.linked_by_name) : null}>{tr("Cliente:")} <Link to={`/clients/${c.client_id}`}>{c.client_pilot || c.client_name}</Link></CdItem>
            : c.sugestao ? <CdItem tom="warn" glifo="✦">{tr("✦ Sugestão:")} <Link to={`/clients/${c.sugestao.client_id}`}><b>{c.sugestao.pilot_name || c.sugestao.name}</b></Link>
              {c.sugestao.pilot_name && c.sugestao.pilot_name !== c.sugestao.name ? tr(" (resp. {0})", c.sugestao.name) : ''} · {c.sugestao.motivo}</CdItem>
            : <CdItem tom="info">{tr("Nenhum cliente parecido no site interno (pelo e-mail, telefone, nome do responsável ou do piloto). Se é cliente novo, crie o card; se já existe, escolha abaixo.")}</CdItem>}
        </CdLista>
        {!c.client_id && <div className="cd-form"><Picker label={tr("Outro cliente")} value={outro[c.id] || null} onPick={x => setOutro(o => ({ ...o, [c.id]: x }))} /></div>}
        {c.client_id && c.drivers_list.length > 0 && <div className="cd-form">
          <h3 className="h3 cd-sec">{tr("Drivers · cada um com o seu card")}</h3>
          <ul className="cd-lista">{c.drivers_list.map(p => <li key={p.id} className="cd-li-forma">
            <i className={`cd-ic ${p.client_id ? 'ok' : p.sugestao ? 'warn' : 'neutral'}`} aria-hidden="true">{p.client_id ? '✓' : p.sugestao ? '✦' : '·'}</i>
            <span className="grow"><b>{p.name}</b>{p.birth_date ? tr(" · {0} anos", idade(p.birth_date)) : ''}
              {p.client_id ? <> · <Link to={`/clients/${p.client_id}`}>{tr("Client ID")} {p.client_id}</Link></>
                : p.sugestao ? <> {tr("· ✦ sugestão:")} <Link to={`/clients/${p.sugestao.client_id}`}>{p.sugestao.pilot_name || p.sugestao.name} {tr("(Client ID")} {p.sugestao.client_id})</Link> · {p.sugestao.motivo}</>
                : <span className="muted"> {tr("· sem card")}</span>}</span>
            {p.client_id ? can('MANAGER') && <button className="btn sm ghost" onClick={() => desvincularDriver(p)}>{tr("Desvincular")}</button>
              : <>{p.sugestao && <button className="btn sm primary" onClick={() => vincularDriver(p, p.sugestao!.client_id, p.sugestao!.pilot_name || p.sugestao!.name)}>{tr("Vincular a este")}</button>}
                {!p.sugestao && <button className="btn sm primary" onClick={() => criarDriver(c, p)}>{tr("Criar card")}</button>}
                <div className="cd-li-picker"><Picker label={tr("Outro card para {0}", p.name)} value={outro[-p.id] || null} onPick={x => setOutro(o => ({ ...o, [-p.id]: x }))} /></div>
                {outro[-p.id] && <button className="btn sm" onClick={() => vincularDriver(p, outro[-p.id]!.id, outro[-p.id]!.pilot_name || outro[-p.id]!.name)}>{tr("Vincular")}</button>}</>}
          </li>)}</ul>
        </div>}
      </CartaoD>)}</div>)}
  </>
}

/* Waiver assinada na área do cliente (#85), sem DocuSign. O texto vem dos dois modelos do
 * DocuSign, importados como estão (com o hash). Nasce desligada: quem liga é o ADMIN, depois do
 * sim do advogado. Desligar não apaga nada; o DocuSign segue como está. */
interface ModeloW { kind: 'adult' | 'parental'; templateId: string; name: string | null; pages: number | null; sha256: string | null; imported_at: string | null
  version: number | null }
interface Assinada { id: number; client_id: number | null; signer_name: string; signer_email: string; minor_name: string | null; template: string
  completed_at: string; expires_at: string; doc_sha256: string; voided_at: string | null; voided_by: string | null; void_reason: string | null }
/* #116: a conferência do aviso §744.301(3) no parental. O texto do aviso não está no sistema: é o que o advogado
 * aprovar, num arquivo no servidor. Sem ele, só informa; com ele, barra importar, ligar e assinar a parental. */
interface Conferencia { configured: boolean; ok: boolean | null; reason: string; notice_pt?: number | null; body_pt?: number | null }
interface Aviso744 extends Conferencia { path: string; approved_text: string | null; approved_sha256: string | null }
interface WN { ligada: boolean; modelos: ModeloW[]; assinadas: { itens: Assinada[]; total: number; limit: number; offset: number }; aviso_744: Aviso744 }
interface VersaoM { id: number; kind: 'adult' | 'parental'; sha256: string; name: string; pages: number | null; imported_at: string
  imported_by_name: string | null; current: boolean; number: number; signatures: number; notice_744: Conferencia | null }
interface Versoes { itens: VersaoM[]; total: number; limit: number; offset: number }
const POR_PAGINA = 25

function ChipDoAviso({ c }: { c: Conferencia | null }) {
  if (!c) return null
  if (!c.configured) return <Chip tone="neutral" glyph="○" title={c.reason}>{tr("aviso: esperando o advogado")}</Chip>
  return c.ok ? <Chip tone="ok" glyph="✓" title={c.reason}>{tr("aviso confere")}</Chip>
    : <Chip tone="crit" glyph="✕" title={c.reason}>{tr("aviso não confere")}</Chip>
}

function AvisoDoParental({ a }: { a: Aviso744 }) {
  return <Section title={tr("Aviso do §744.301(3) (parental)")} right={<ChipDoAviso c={a} />}>
    <div className="card card-b stack" style={{ gap: 10 }}>
      <p className="small" style={{ margin: 0 }}>{tr("Pelo menor, a waiver só vale com o aviso que a lei da Flórida pede, em maiúsculas e com letra maior que o resto. O sistema confere o modelo parental: o texto aprovado inteiro, em maiúsculas, com 5 pt a mais que o corpo.")}</p>
      <p className="small" style={{ margin: 0 }}><b>{a.reason}</b></p>
      {a.configured
        ? <p className="small muted" style={{ margin: 0 }}>{tr("Com o texto aprovado no servidor ({0}), o parental que não confere não é importado, a assinatura não liga e a parental não se assina online.", a.path)}</p>
        : <p className="small muted" style={{ margin: 0 }}>{tr("O texto do aviso não está no sistema: quando o advogado aprovar, ele vai para o arquivo {0} no servidor. Até lá a conferência só informa e nada é barrado.", a.path)}</p>}
      {a.approved_text && <details><summary className="small" style={{ cursor: 'pointer', minHeight: 40, display: 'flex', alignItems: 'center', gap: 6 }}>{tr("Texto aprovado")} <span className="mono muted">{a.approved_sha256?.slice(0, 12)}</span></summary>
        <p className="small" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: '8px 0 0' }}>{a.approved_text}</p></details>}
    </div>
  </Section>
}

/* #111: a trilha de eventos de uma waiver assinada aqui (append-only e encadeada por hash). O que veio antes
 * de assinar está também no certificado do PDF; o que veio depois (anulada, PDF baixado) fica só aqui. */
interface EventoW { id: number; at: string; event: string; phase: 'before' | 'signed' | 'after'; source: 'server' | 'client'
  ip: string | null; user_agent: string | null }
interface TrilhaW { eventos: EventoW[]; cadeia: { ok: boolean; total: number | null; first_bad_id: number | null } }

function rotuloDoEvento(ev: string) {
  const r: Record<string, string> = {
    invite_sent: tr("convite enviado por e-mail"), screen_opened: tr("abriu a tela de assinar"), pdf_delivered: tr("recebeu o PDF"),
    all_pages_viewed: tr("leu todas as páginas"), code_sent: tr("código enviado"), code_verified: tr("código confirmado"),
    reviewed: tr("revisou e confirmou"), signed: tr("assinou"), copy_emailed: tr("cópia por e-mail"), id_checked: tr("documento conferido no balcão"),
    voided: tr("anulada"), downloaded: tr("PDF baixado"), evidence_exported: tr("pacote de prova exportado") }
  return r[ev] || ev
}

function TrilhaDaWaiver({ wid }: { wid: number }) {
  const l = useGet<TrilhaW>(`/site/waiver-nativa/${wid}/eventos`)
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!l.data) return <Loading />
  const { eventos, cadeia } = l.data
  return <div className="stack" style={{ gap: 6, padding: '4px 0 10px' }}>
    <div className="small">{cadeia.ok ? <Chip tone="ok" glyph="✓">{tr("trilha íntegra · {0} eventos no total", cadeia.total ?? 0)}</Chip>
      : <Chip tone="crit" glyph="✕">{tr("trilha com linha mexida no evento #{0}", cadeia.first_bad_id ?? '?')}</Chip>}</div>
    {!eventos.length ? <p className="small muted" style={{ margin: 0 }}>{tr("Sem eventos: assinada antes da trilha.")}</p>
      : <ol className="small stack" style={{ margin: 0, paddingLeft: 18, gap: 4 }}>{eventos.map(e => <li key={e.id} style={{ overflowWrap: 'anywhere' }}>
        <b>{rotuloDoEvento(e.event)}</b> · {fmtDateTime(e.at)} · {e.source === 'client' ? tr("relatado pela tela") : tr("registrado pelo servidor")}
        {e.phase === 'after' && <> · <Chip tone="neutral">{tr("depois de assinar")}</Chip></>}
        <div className="muted">IP {e.ip || '—'} · {e.user_agent || '—'}</div></li>)}</ol>}
  </div>
}

/* #116: toda versão que já valeu fica guardada (append-only), com o PDF: reimportar não apaga a anterior. */
function VersoesDoModelo() {
  const [offset, setOffset] = useState(0)
  const l = useGet<Versoes>(`/site/waiver-nativa/versoes?limit=${POR_PAGINA}&offset=${offset}`)
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!l.data) return <Loading />
  const v = l.data
  return <Section title={tr("Versões dos modelos")} count={v.total}>
    {!v.itens.length ? <Empty title={tr("Nenhuma versão ainda")}>{tr("Cada importação do DocuSign com um texto novo vira uma versão. A anterior continua aqui.")}</Empty>
      : <div className="tbl">{v.itens.map(x => <div className="tr" key={x.id}>
        <span className="grow"><b>{x.kind === 'adult' ? tr("Adult") : tr("Parental (menor)")} · {tr("versão {0}", x.number)}</b> {x.current && <Chip tone="ok">{tr("atual")}</Chip>}
          <div className="small muted">{x.name} · {x.pages} {tr("pág. ·")} <span className="mono" title={x.sha256}>{x.sha256.slice(0, 12)}</span></div>
          <div className="small muted">{tr("importada em {0}", fmtDateTime(x.imported_at))}{x.imported_by_name ? tr(" por {0}", x.imported_by_name) : ''} · {tr("{0} assinatura(s)", x.signatures)}</div>
          {x.kind === 'parental' && <div className="small"><ChipDoAviso c={x.notice_744} /> <span className="muted">{tr("(na importação)")}</span></div>}</span>
        <a className="btn sm" href={`/ops/api/site/waiver-nativa/versoes/${x.id}/pdf`} target="_blank" rel="noreferrer">{tr("PDF")}</a>
      </div>)}</div>}
    {v.total > POR_PAGINA && <div className="row" style={{ gap: 8, marginTop: 10 }}>
      <button className="btn sm ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - POR_PAGINA))}>{tr("Anteriores")}</button>
      <span className="small muted grow" style={{ textAlign: 'center' }}>{offset + 1}–{Math.min(offset + POR_PAGINA, v.total)} {tr("de")} {v.total}</span>
      <button className="btn sm ghost" disabled={offset + POR_PAGINA >= v.total} onClick={() => setOffset(offset + POR_PAGINA)}>{tr("Próximas")}</button></div>}
    <p className="small muted" style={{ margin: '8px 0 0' }}>{tr("Nenhuma versão se apaga nem muda. Cada assinatura guarda o hash e a versão que valia.")}</p>
  </Section>
}

function WaiverNativa() {
  const { can } = useAuth()
  const admin = can('ADMIN')
  const toast = useToast()
  const perguntar = usePerguntar()
  const [offset, setOffset] = useState(0)
  const l = useGet<WN>(`/site/waiver-nativa?limit=${POR_PAGINA}&offset=${offset}`)
  const [indo, setIndo] = useState(false)
  const [trilha, setTrilha] = useState<number | null>(null)
  async function importar() {
    setIndo(true)
    try { await api.post('/site/waiver-nativa/importar', {}); toast(tr("Modelos importados do DocuSign (só leitura lá)."), 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  async function ligar(ligada: boolean) {
    if (ligada && !await perguntar({ titulo: tr("Ligar a assinatura na área do cliente?"), ok: tr("Ligar"),
      texto: tr("Os clientes passam a assinar a waiver pela área do cliente, sem DocuSign. Faça isso depois do sim do advogado. O DocuSign continua funcionando como hoje.") })) return
    try { await api.post('/site/waiver-nativa/ligar', { ligada }); toast(ligada ? tr("Ligada: o cliente já vê \"Sign now\".") : tr("Desligada. Nada assinado foi apagado."), 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  /* #109: assinada não vai para a lixeira; o gerente anula com motivo e ela continua aqui, no card e no backup */
  async function anular(w: Assinada) {
    const motivo = await perguntar({ titulo: tr("Anular a waiver de {0}?", w.minor_name || w.signer_name), perigo: true, ok: tr("Anular a waiver"),
      texto: tr("A waiver não é apagada nem muda: continua no card e no backup, marcada como anulada, e deixa de valer. O cliente pode assinar outra. Não se desfaz."),
      campo: tr("Motivo (pelo menos 10 letras)") }) as string | null
    if (motivo === null) return
    try { await api.post(`/waivers/${w.id}/void`, { reason: motivo }); toast(tr("Waiver anulada. Ela continua no card e no backup."), 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!l.data) return <Loading />
  const d = l.data, a = d.assinadas
  const prontos = d.modelos.every(m => m.sha256)
  return <div className="stack" style={{ gap: 18 }}>
    <Section title={tr("Assinatura na área do cliente")} right={d.ligada ? <Chip tone="ok">{tr("ligada")}</Chip> : <Chip tone="neutral">{tr("desligada")}</Chip>}>
      <div className="stack" style={{ gap: 10 }}>
        <p className="small" style={{ margin: 0 }}>{tr("O responsável assina pela área do cliente: lê o documento, marca as duas caixas, digita o nome e desenha a assinatura. Menor de 18 assina a parental; maior, a adult. Vale 1 ano. O PDF final é o original do DocuSign mais uma página de assinatura e certificado (data e hora da Flórida, IP, aparelho, hashes).")}</p>
        {!d.ligada && <p className="small muted" style={{ margin: 0 }}>{tr("Antes de ligar: o advogado confirma que a assinatura eletrônica com essa página de certificado vale para a waiver de menor na Flórida.")}</p>}
        {admin ? <div className="row wrap" style={{ gap: 8 }}>
          {d.ligada ? <button className="btn sm ghost" onClick={() => ligar(false)}>{tr("Desligar")}</button>
            : <button className="btn sm primary" disabled={!prontos} title={prontos ? undefined : tr("Importe os dois modelos primeiro")} onClick={() => ligar(true)}>{tr("Ligar")}</button>}
        </div> : <p className="small muted" style={{ margin: 0 }}>{tr("Só o ADMIN liga ou desliga.")}</p>}
      </div>
    </Section>
    <Section title={tr("Modelos (do DocuSign)")} count={d.modelos.length} right={admin ? <button className="btn sm" disabled={indo} onClick={importar}>{indo ? <span className="spin" /> : tr("Importar do DocuSign")}</button> : undefined}>
      <div className="tbl">{d.modelos.map(m => <div className="tr" key={m.kind}>
        <span className="grow"><b>{m.kind === 'adult' ? tr("Adult") : tr("Parental (menor)")}</b><div className="small muted">{m.name || tr("ainda não importado")}</div></span>
        <Chip tone={m.sha256 ? 'ok' : 'warn'}>{m.sha256 ? tr("importado") : tr("falta importar")}</Chip>
        <span className="small muted">{m.sha256 ? <>{m.version ? tr("versão {0}", m.version) + ' · ' : ''}{m.pages} {tr("pág. ·")} <span className="mono" title={m.sha256}>{m.sha256.slice(0, 12)}</span> · {fmtDateTime(m.imported_at)}</> : '—'}</span>
      </div>)}</div>
      <p className="small muted" style={{ margin: '8px 0 0' }}>{tr("Importar só LÊ os modelos no DocuSign. Se o texto mudar lá, importe de novo: as próximas assinaturas usam o novo, as já feitas ficam com o delas.")}</p>
    </Section>
    <AvisoDoParental a={d.aviso_744} />
    <VersoesDoModelo key={d.modelos.map(m => m.sha256 || '').join()} />
    <Section title={tr("Assinadas aqui")} count={a.total}>
      {!a.itens.length ? <Empty title={tr("Nenhuma ainda")}>{tr("Quando um cliente assinar pela área do cliente, ela aparece aqui e no card do cliente.")}</Empty>
        : <div className="cd-grade">{a.itens.map(w => <CartaoD key={w.id} id={`waiver-${w.id}`} className={trilha === w.id ? 'cd-largo' : undefined}
          estado={w.voided_at ? tr("anulada") : tr("assinada")} tom={w.voided_at ? 'crit' : 'ok'}
          avatar={w.minor_name || w.signer_name} nome={w.minor_name || w.signer_name}
          sub={[w.template === 'parental' ? tr("parental · por {0}", w.signer_name) : tr("adult")]}
          grande={fmtDate(w.completed_at)} detalhe={`${tr("assinada")} ${tr("· vale até")} ${fmtDate(w.expires_at)}`}
          acoes={<>
            {w.client_id && <Link className="btn" to={`/clients/${w.client_id}`}>{tr("Card")}</Link>}
            <a className="btn" href={`/ops/api/waivers/${w.id}/download`}>{tr("PDF")}</a>
            {/* #111: a trilha de eventos abre dentro do cartão, que ocupa a linha inteira */}
            <button className="btn" aria-expanded={trilha === w.id} onClick={() => setTrilha(trilha === w.id ? null : w.id)}>{tr("Trilha")}</button>
            {!w.voided_at && can('MANAGER') && <button className="btn danger" onClick={() => anular(w)}>{tr("Anular")}</button>}</>}>
          {(w.voided_at || !w.client_id) && <CdLista>
            {w.voided_at && <CdItem tom="crit">{tr("por {0} em {1}: {2}", w.voided_by || '—', fmtDate(w.voided_at), w.void_reason || '')}</CdItem>}
            {!w.client_id && <CdItem tom="warn">{tr("sem card")}</CdItem>}
          </CdLista>}
          {trilha === w.id && <div className="cd-form"><TrilhaDaWaiver wid={w.id} /></div>}
        </CartaoD>)}</div>}
      {a.total > POR_PAGINA && <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <button className="btn sm ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - POR_PAGINA))}>{tr("Anteriores")}</button>
        <span className="small muted grow" style={{ textAlign: 'center' }}>{offset + 1}–{Math.min(offset + POR_PAGINA, a.total)} {tr("de")} {a.total}</span>
        <button className="btn sm ghost" disabled={offset + POR_PAGINA >= a.total} onClick={() => setOffset(offset + POR_PAGINA)}>{tr("Próximas")}</button></div>}
    </Section>
  </div>
}

/* #298: os produtos da loja ficam em arquivo próprio (só carrega quem abre a aba). */
const ProdutosDaLoja = lazy(() => import('./LojaProdutos').then(m => ({ default: m.ProdutosDaLoja })))
const EditarProduto = lazy(() => import('./LojaProdutos').then(m => ({ default: m.EditarProduto })))
/* #300: o editor visual do site, também em arquivo próprio. */
/* #306: o painel do site (as métricas), a página de entrada da seção Site. */
const SitePainel = lazy(() => import('./SitePainel').then(m => ({ default: m.SitePainel })))
/* #317: o security deposit (devolver pelo Stripe e o valor cobrado), em arquivo próprio. */
const SiteDepositos = lazy(() => import('./SiteDepositos').then(m => ({ default: m.SiteDepositos })))
/* #309: o estoque do site (dropshipping ou em estoque, ligado ao estoque do box), em arquivo próprio. */
const EstoqueDoSite = lazy(() => import('./EstoqueDoSite').then(m => ({ default: m.EstoqueDoSite })))
const PaginasDoEditor = lazy(() => import('./EditorSite').then(m => ({ default: m.PaginasDoEditor })))
/* #315: a página em si abre no editor como o Canva, num arquivo só dele (a lista não carrega o editor). */
const EditorDePagina = lazy(() => import('./editor/Editor').then(m => ({ default: m.EditorDePagina })))
/* #172: o blog do site (o OPERATOR escreve, o ADMIN publica), em arquivo próprio. */
const ArtigosDoBlog = lazy(() => import('./BlogDoSite').then(m => ({ default: m.ArtigosDoBlog })))
const EditarArtigo = lazy(() => import('./BlogDoSite').then(m => ({ default: m.EditarArtigo })))

/* #306 (dono, 16/10): "uma sessão dedicada exclusiva somente para o site … uma seção com subseções de cada painel de lá".
 * Cada painel do site é uma subseção (no menu, em "Site", e aqui nas abas); o h1 é o nome da subseção (o título da aba). */
const SUBSECOES: { aba: string; to: string; rotulo: string; min?: 'MANAGER' }[] = [
  { aba: '', to: '/site', rotulo: tr("Painel do site") },
  { aba: 'pedidos', to: '/site/pedidos', rotulo: tr("Pedidos do site") },
  { aba: 'agendamentos', to: '/site/agendamentos', rotulo: tr("Agendamentos") },
  { aba: 'disponibilidade', to: '/site/disponibilidade', rotulo: tr("Disponibilidade") },
  { aba: 'servicos', to: '/site/servicos', rotulo: tr("Serviços e preços") },
  { aba: 'cartoes', to: '/site/cartoes', rotulo: tr("Cartões das páginas") },
  { aba: 'produtos', to: '/site/produtos', rotulo: tr("Produtos da loja") },
  { aba: 'estoque', to: '/site/estoque', rotulo: tr("Estoque do site") },        // #309
  { aba: 'editor', to: '/site/editor', rotulo: tr("Editor do site") },
  { aba: 'blog', to: '/site/blog', rotulo: tr("Blog") },                         // #172
  { aba: 'contas', to: '/site/contas', rotulo: tr("Contas de clientes") },
  { aba: 'waiver', to: '/site/waiver', rotulo: tr("Waiver"), min: 'MANAGER' },
  { aba: 'deposito', to: '/site/deposito', rotulo: tr("Security deposit") },      // #317
]

export function SitePublico() {
  const { aba, id } = useParams()
  const { can } = useAuth()
  const subs = SUBSECOES.filter(s => !s.min || can(s.min))
  const atual = subs.find(s => s.aba === (aba || '')) || subs[0]
  return <>
    <PageHeader eyebrow={tr("Site")} title={atual.rotulo} help={<>{tr("Tudo o que é do site público: os pedidos, os agendamentos, a agenda, os serviços e preços, os cartões, a loja e o estoque dela, o editor, as contas e a waiver. O cliente usa a área do cliente em")} <a href="/ops/portal" target="_blank" rel="noreferrer">{tr("/ops/portal")}</a>.</>}>
      <a className="btn ghost" href="/ops/portal" target="_blank" rel="noreferrer">{tr("Abrir a área do cliente ↗")}</a>
    </PageHeader>
    <nav className="tabs" aria-label={tr("Subseções do site")}>
      {subs.map(s => <NavLink key={s.to} to={s.to} end={!s.aba} className={({ isActive }) => isActive ? 'on' : ''}>{s.rotulo}</NavLink>)}
    </nav>
    {atual.aba === '' ? <Suspense fallback={<Loading />}><SitePainel /></Suspense>
      : atual.aba === 'deposito' ? <Suspense fallback={<Loading />}><SiteDepositos /></Suspense>
      : atual.aba === 'estoque' ? <Suspense fallback={<Loading />}><EstoqueDoSite key={id || ''} produto={id} /></Suspense>
      : atual.aba === 'editor' ? <Suspense fallback={<Loading />}>{id && /^\d+$/.test(id) ? <EditorDePagina key={id} id={Number(id)} /> : <PaginasDoEditor />}</Suspense>
      : atual.aba === 'blog' ? <Suspense fallback={<Loading />}>{id && /^\d+$/.test(id) ? <EditarArtigo key={id} id={Number(id)} /> : <ArtigosDoBlog />}</Suspense>
      : atual.aba === 'produtos' ? <Suspense fallback={<Loading />}>{id && /^\d+$/.test(id) ? <EditarProduto key={id} id={Number(id)} /> : <ProdutosDaLoja />}</Suspense>
      : atual.aba === 'disponibilidade' ? <Disponibilidade /> : atual.aba === 'servicos' ? <Servicos /> : atual.aba === 'cartoes' ? <Cartoes />
      : atual.aba === 'contas' ? <Contas /> : atual.aba === 'pedidos' ? <Pedidos /> : atual.aba === 'waiver' ? <WaiverNativa /> : <Agendamentos />}
  </>
}
