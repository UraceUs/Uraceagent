/* Vários dias num pedido do aluno recorrente (#314). Dono, 16/10: "para esses clientes, é interessante eles
 * terem a oportunidade de marcar mais de um dia, multi-seleção de dias. Então, se ele quiser marcar para
 * quartas, toda quarta. Ou quartas e sábado dessa semana, ou então sábado e domingo da outra, ele consegue
 * marcar isso tudo em um book."
 *
 * Tocar no dia marca ou desmarca. Atalhos: "Every Wed" (o resto do mês, as próximas 4 semanas ou até uma
 * data, dentro do que a agenda mostra), "This weekend", "Next weekend". Cada dia mostra só "Included in your
 * plan" ou "Extra session · $X", vindo do servidor (a cotação); o contador do pacote não aparece (dono,
 * 01/10). No máximo 12 dias por pedido; ou entra tudo, ou nada. Carregado só para quem tem plano. O dia que o plano
 * não cobre (o plano acaba antes daquele mês) tem "Book as a regular session": abre a marcação de um dia, avulsa. */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { dataLonga, faixa, PERIODOS } from './Agendar'
import { papi, PortalError, usd, type AgendaCfg, type CheckoutGrupo, type Cotacao, type Dia, type PlanoPiloto, type Servico, type Turno } from './api'

const MAX_DIAS = 12
const SEMANA = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const DIA_PY = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']           // `Dia.weekday` é o do Python (0 = segunda)
const TURNOS: Turno[] = ['manha', 'tarde', 'dia']
const mesDe = (iso: string) => iso.slice(0, 7)
const curta = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
const somaDias = (iso: string, n: number) => { const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() + n); return d.toLocaleDateString('en-CA') }
const fimDoMes = (iso: string) => { const [a, m] = iso.split('-').map(Number); return `${iso.slice(0, 7)}-${String(new Date(a, m, 0).getDate()).padStart(2, '0')}` }

/** O turno de um dia novo: o de costume, se abre; senão o único aberto; senão o primeiro aberto. */
function turnoPara(d: Dia, costume: Turno): Turno | null {
  const abertos = TURNOS.filter(t => d.periods[t].open)
  if (!abertos.length) return null
  if (abertos.includes(costume)) return costume
  const meios = abertos.filter(t => t !== 'dia')
  return meios.length === 1 ? meios[0] : abertos[0]
}

export function AgendarVarios({ piloto, plano, dias, cfg, servicos, servico, setServico, seletorPiloto, onMarcou, onAvulso }: {
  piloto: number; plano: PlanoPiloto; dias: Dia[]; cfg: AgendaCfg; servicos: Servico[]; servico: number | null
  setServico: (id: number) => void; seletorPiloto: ReactNode; onMarcou: () => void
  onAvulso: (date: string, period: Turno) => void
}) {
  const hoje = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' })
  const porData = useMemo(() => Object.fromEntries(dias.map(d => [d.date, d])), [dias])
  const meses = useMemo(() => [...new Set(dias.map(d => mesDe(d.date)))], [dias])
  const ultimo = dias.length ? dias[dias.length - 1].date : hoje
  const [mes, setMes] = useState(() => mesDe(dias.find(d => d.any_open)?.date || hoje))
  const [escolhidos, setEscolhidos] = useState<Record<string, Turno>>({})
  const [costume, setCostume] = useState<Turno>('manha')
  const [ate, setAte] = useState<'mes' | '4sem' | 'data'>('4sem')
  const [ateData, setAteData] = useState('')
  const [cot, setCot] = useState<{ chave: string; r: Cotacao | null; erro: string | null } | null>(null)
  const [refaz, setRefaz] = useState(0)
  const [erro, setErro] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  const [nota, setNota] = useState('')
  const [indo, setIndo] = useState(false)
  const nav = useNavigate()
  const pedido = useMemo(() => Object.entries(escolhidos).sort(([a], [b]) => a.localeCompare(b)).map(([date, period]) => ({ date, period })), [escolhidos])
  const chave = JSON.stringify([servico, piloto, pedido, refaz])

  // a cotação acompanha a escolha (o preço e o rótulo são do servidor); a resposta vale só para a escolha dela
  useEffect(() => {
    if (!pedido.length || !servico) return
    let vale = true
    const t = window.setTimeout(async () => {
      try {
        const r = await papi<Cotacao>('POST', '/bookings/quote', { service_id: servico, driver_id: piloto, slots: pedido })
        if (vale) setCot({ chave, r, erro: null })
      } catch (e) { if (vale) setCot({ chave, r: null, erro: (e as PortalError).message }) }
    }, 300)
    return () => { vale = false; window.clearTimeout(t) }
  }, [chave, pedido, servico, piloto])
  const atual = cot && cot.chave === chave ? cot : null
  const q = atual?.r || null
  const cotando = !!pedido.length && !!servico && !atual

  const grade = useMemo(() => {
    const [a, m] = mes.split('-').map(Number)
    const primeiro = new Date(a, m - 1, 1).getDay(), total = new Date(a, m, 0).getDate()
    return [...Array(primeiro).fill(null), ...Array.from({ length: total }, (_, i) => `${mes}-${String(i + 1).padStart(2, '0')}`)]
  }, [mes])

  /** `vazio`: o que dizer quando o atalho não acha nenhum dia aberto (senão o toque não faria nada, sem aviso). */
  function adicionar(isos: string[], vazio?: string) {
    setAviso(null)
    if (!isos.length) { if (vazio) setAviso(vazio); return }
    setEscolhidos(x => {
      const novo = { ...x }
      let cortou = false
      for (const iso of isos) {
        if (novo[iso]) continue
        const d = porData[iso], t = d && turnoPara(d, costume)
        if (!t) continue
        if (Object.keys(novo).length >= MAX_DIAS) { cortou = true; break }
        novo[iso] = t
      }
      if (cortou) setAviso(`Up to ${MAX_DIAS} days per booking. Book the rest in another one.`)
      return novo
    })
  }
  function alternar(iso: string) {
    if (escolhidos[iso]) { setEscolhidos(x => { const y = { ...x }; delete y[iso]; return y }); setAviso(null); return }
    adicionar([iso])
  }
  const limite = ate === 'mes' ? fimDoMes(hoje) : ate === '4sem' ? somaDias(hoje, 27) : (ateData || somaDias(hoje, 27))
  const diasDaSemana = useMemo(() => [...new Set(dias.filter(d => d.any_open).map(d => d.weekday))].sort(), [dias])
  const todaSemana = (wd: number) => adicionar(dias.filter(d => d.any_open && d.weekday === wd && d.date <= limite).map(d => d.date),
    ate === '4sem' ? 'No open days in the next 4 weeks.' : 'No open days left until then: try the next 4 weeks.')
  // o fim de semana desta semana (segunda a domingo) e o da próxima
  const sabado = (n: number) => { const d = new Date(hoje + 'T12:00:00'); const a = (d.getDay() + 6) % 7; return somaDias(hoje, 5 - a + 7 * n) }
  const fimDeSemana = (n: number) => adicionar([sabado(n), somaDias(sabado(n), 1)].filter(x => x >= hoje && porData[x]?.any_open),
    'No open days that weekend.')

  const cotado = (iso: string) => q?.slots.find(x => x.date === iso && x.period === escolhidos[iso])
  const prontos = !!q && !cotando && q.slots.length === pedido.length && q.slots.every(x => x.ok)
  const n = pedido.length

  async function marcar() {
    if (!q || !prontos || !servico) return
    setIndo(true); setErro(null)
    try {
      const r = await papi<{ group_id: number }>('POST', '/bookings/batch', { service_id: servico, driver_id: piloto, slots: pedido,
        quote: q.hash, notes: nota || null })
      onMarcou()
      nav(`/portal/sessions/group/${r.group_id}`)
    } catch (e) {
      setErro((e as PortalError).message)
      setRefaz(n => n + 1)                                   // cota de novo: a vaga ou o preço mudou
    } finally { setIndo(false) }
  }

  return <div className="stack" style={{ gap: 18 }}>
    <div><h1 className="h1">Book sessions</h1>
      <p className="muted" style={{ margin: '4px 0 0' }}>Pick one day or many. Sessions in your plan are included; an extra session is billed by invoice.</p>
      <p style={{ margin: '8px 0 0' }}><span className="chip info">{plano.plan || 'Monthly plan'}</span></p></div>
    {(erro || atual?.erro) && <div className="banner crit" role="alert"><span className="bi" aria-hidden="true">✕</span><div className="grow">{erro || atual?.erro}</div></div>}
    <div className="card card-b stack">
      {seletorPiloto}
      <fieldset className="portal-servicos"><legend className="small">Session type</legend>
        {servicos.map(x => <label key={x.id} className={`portal-servico${servico === x.id ? ' on' : ''}`}>
          <input type="radio" name="servico" checked={servico === x.id} onChange={() => setServico(x.id)} />
          <span className="grow"><b>{x.name}</b>{x.description && <span className="small muted"> · {x.description}</span>}</span></label>)}</fieldset>

      <section className="stack" style={{ gap: 10 }} aria-labelledby="v-rapido">
        <h2 className="h2" id="v-rapido">Quick picks</h2>
        <div className="row wrap" style={{ gap: 6 }} role="group" aria-label="Usual time">
          <span className="small muted" style={{ alignSelf: 'center' }}>Usual time</span>
          {TURNOS.map(t => <button key={t} type="button" className={`btn${costume === t ? ' primary' : ''}`} aria-pressed={costume === t}
            onClick={() => setCostume(t)}>{PERIODOS[t]}</button>)}</div>
        <label className="fld" style={{ margin: 0 }}><span>Repeat until</span>
          <select value={ate} onChange={e => setAte(e.target.value as typeof ate)}>
            <option value="mes">the end of this month</option><option value="4sem">the next 4 weeks</option><option value="data">a date…</option></select></label>
        {ate === 'data' && <label className="fld" style={{ margin: 0 }}><span>Until</span>
          <input type="date" min={hoje} max={ultimo} value={ateData} onChange={e => setAteData(e.target.value)} /></label>}
        <div className="portal-varios-atalhos">
          {diasDaSemana.map(wd => <button key={wd} type="button" className="btn" onClick={() => todaSemana(wd)}>Every {DIA_PY[wd]}</button>)}
          <button type="button" className="btn" onClick={() => fimDeSemana(0)}>This weekend</button>
          <button type="button" className="btn" onClick={() => fimDeSemana(1)}>Next weekend</button>
        </div>
      </section>

      <section className="stack" style={{ gap: 10 }} aria-labelledby="v-cal">
        <h2 className="h2" id="v-cal">Days</h2>
        <div className="row"><button className="btn ghost" aria-label="Previous month" disabled={meses.indexOf(mes) <= 0} onClick={() => setMes(meses[meses.indexOf(mes) - 1])}>‹</button>
          <b className="grow" style={{ textAlign: 'center' }}>{new Date(mes + '-15T12:00:00').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</b>
          <button className="btn ghost" aria-label="Next month" disabled={meses.indexOf(mes) >= meses.length - 1} onClick={() => setMes(meses[meses.indexOf(mes) + 1])}>›</button></div>
        <div className="portal-cal" role="group" aria-label="Pick the days">
          {SEMANA.map(s => <div key={s} className="portal-cal-s" aria-hidden="true">{s}</div>)}
          {grade.map((iso, i) => {
            if (!iso) return <div key={`v${i}`} />
            const aberto = !!porData[iso]?.any_open, on = !!escolhidos[iso]
            return <button key={iso} type="button" className={`portal-cal-d${aberto ? ' aberto' : ''}${on ? ' on' : ''}`} disabled={!aberto && !on}
              aria-pressed={on} aria-label={`${dataLonga(iso)}${on ? ', selected' : aberto ? ', available' : ', not available'}`}
              onClick={() => alternar(iso)}>{Number(iso.slice(8))}</button>
          })}
        </div>
        {aviso && <p className="small" role="status" style={{ margin: 0 }}>{aviso}</p>}
      </section>

      <section className="stack" style={{ gap: 10 }} aria-labelledby="v-lista">
        <h2 className="h2" id="v-lista">Your booking</h2>
        {!n ? <p className="small muted" style={{ margin: 0 }}>Tap the days in the calendar, or use a quick pick.</p>
          : <ul className="portal-varios-lista">{pedido.map(({ date, period }) => {
            const d = porData[date], c = cotado(date)
            return <li key={date} className={`portal-varios-dia${c && !c.ok ? ' ruim' : ''}`}>
              <div className="portal-varios-cab"><b>{curta(date)}</b>
                {c?.ok ? <span className={`chip ${c.coverage === 'extra' ? 'warn' : 'ok'}`}>{c.label}</span>
                  : !servico ? <span className="small muted">Pick the session type</span>
                  : !c && cotando ? <span className="small muted">checking…</span> : null}</div>
              <button type="button" className="btn ghost portal-varios-tirar" aria-label={`Remove ${dataLonga(date)}`} onClick={() => alternar(date)}>✕</button>
              <div className="portal-varios-turnos" role="group" aria-label={`Time on ${dataLonga(date)}`}>
                {TURNOS.filter(t => d?.periods[t].open || t === period).map(t =>
                  <button key={t} type="button" className={`btn${period === t ? ' primary' : ''}`} aria-pressed={period === t}
                    onClick={() => setEscolhidos(x => ({ ...x, [date]: t }))}>{PERIODOS[t]}<span className="small"> {faixa(cfg, t)}</span></button>)}</div>
              {c && !c.ok && <p className="small portal-varios-motivo">{c.message}</p>}
              {c?.reason === 'fora_do_plano' && <div className="portal-varios-avulso">
                <button type="button" className="btn" onClick={() => onAvulso(date, period)}>Book as a regular session</button></div>}
            </li>
          })}</ul>}
        {n > 0 && <div className="reserva-total" aria-live="polite">
          {q && !cotando ? <div className="soma"><span>{q.extras
            ? `${q.included} included · ${q.extras} extra${q.extras > 1 ? 's' : ''}`
            : `${q.included} included in your plan`}</span><span>{q.extras ? (q.extra_price_missing ? 'by invoice' : usd(q.extras_total)) : usd(0)}</span></div>
            : !servico ? <div className="small muted"><span>Pick the session type above to see what is included.</span></div>
            : <div className="small muted"><span>Checking your days…</span></div>}
          {q && q.extras > 0 && <div className="small muted"><span>The extra sessions come in one invoice by email.</span></div>}</div>}
        {n > 0 && <label className="fld"><span>Anything we should know? <i>optional</i></span><textarea value={nota} onChange={e => setNota(e.target.value)} maxLength={500} /></label>}
        <div><button className="btn primary" disabled={!prontos || indo} onClick={marcar}>{indo ? 'Booking…' : n ? `Book ${n} session${n > 1 ? 's' : ''}` : 'Book sessions'}</button></div>
      </section>
    </div>
    <p className="small muted" style={{ margin: 0 }}>See what you booked in <Link to="/portal/sessions">My sessions</Link>.</p>
  </div>
}

/* ------------------------------------------------------------ o pedido de vários dias */
/** As etapas do pedido: os dias (do plano ou extra) → pagar a invoice das extras (se houver) → waiver → confirmado. */
export function AcompanharGrupo() {
  const { gid } = useParams()
  const [c, setC] = useState<CheckoutGrupo | null>(null)
  const [cfg, setCfg] = useState<AgendaCfg | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const carregar = useCallback(async () => {
    try { setC(await papi<CheckoutGrupo>('GET', `/bookings/group/${gid}`)); setErro(null) }
    catch (e) { setErro((e as PortalError).message) }
  }, [gid])
  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { papi<{ config: AgendaCfg }>('GET', '/availability').then(a => setCfg(a.config)).catch(() => null) }, [])
  const preparando = !!c && (c.pagamento.estado === 'preparando' || c.waiver.estado === 'preparando')
  useEffect(() => {
    if (!c || c.confirmada || c.status === 'cancelada') return
    const t = window.setTimeout(carregar, preparando ? 4000 : 20000)
    return () => window.clearTimeout(t)
  }, [c, preparando, carregar])
  if (erro && !c) return <div className="stack"><h1 className="h1">Your booking</h1>
    <div className="banner crit" role="alert"><span className="bi" aria-hidden="true">✕</span><div className="grow">{erro}</div></div>
    <div><Link className="btn" to="/portal/sessions">My sessions</Link></div></div>
  if (!c) return <div className="state"><span className="spin" /></div>
  const pg = c.pagamento, w = c.waiver
  const pagoOk = pg.estado === 'pago' || pg.estado === 'contrato'
  const waiverOk = w.estado === 'ok'
  const ativas = c.sessions.filter(s => s.status === 'pendente' || s.status === 'confirmada')
  return <div className="stack" style={{ gap: 16 }}>
    <div><h1 className="h1">{c.confirmada ? "You're confirmed!" : c.status === 'cancelada' ? 'Your booking' : 'Almost there'}</h1>
      <p className="muted" style={{ margin: '6px 0 0' }}>{c.service}{c.driver ? ` · ${c.driver}` : ''} · {ativas.length} session{ativas.length === 1 ? '' : 's'}</p></div>
    <section className="card card-b stack" style={{ gap: 8 }} aria-labelledby="g-dias">
      <h2 className="h2" id="g-dias">Your days</h2>
      <ul className="portal-varios-lista">{c.sessions.map(s => <li key={s.id} className="portal-varios-dia">
        <div className="portal-varios-cab"><b>{dataLonga(s.date)}</b>
          {s.status === 'cancelada' || s.status === 'recusada' ? <span className="chip neutral">{s.status === 'cancelada' ? 'Cancelled' : 'Not available'}</span>
            : s.label && <span className={`chip ${s.coverage === 'extra' ? 'warn' : 'ok'}`}>{s.label}</span>}</div>
        <span className="small muted portal-varios-turnos">{PERIODOS[s.period]}{cfg ? ` · ${faixa(cfg, s.period)}` : ''}{s.status === 'confirmada' ? ' · Confirmed' : ''}</span>
      </li>)}</ul>
    </section>
    {c.status === 'cancelada' ? <div className="banner warn"><span className="bi" aria-hidden="true">▲</span><div className="grow">This booking was cancelled. <Link to="/portal/book">Book again</Link></div></div>
      : !c.aceita && !c.confirmada ? <div className="banner info" role="status"><span className="bi" aria-hidden="true">●</span><div className="grow">Request received. Our team confirms your sessions{c.extras ? ' and emails the invoice of the extra sessions' : ''}.</div></div>
      : <ol className="etapas" aria-label="Steps to confirm">
        <li className="etapa ok"><span className="marca" aria-hidden="true">✓</span><div className="corpo"><b>Spots reserved</b><span className="small muted">We are holding your days.</span></div></li>
        <li className={`etapa${pagoOk ? ' ok' : ' agora'}`}><span className="marca" aria-hidden="true">{pagoOk ? '✓' : '2'}</span><div className="corpo">
          <b>{pg.estado === 'contrato' ? 'Included in your plan' : pagoOk ? 'Paid' : 'Pay the invoice of the extra sessions'}</b>
          {pg.estado === 'pagar' && <>{pg.link ? <div><a className="btn primary" href={pg.link} target="_blank" rel="noopener noreferrer">Pay now{pg.total != null ? ` ${usd(pg.total)}` : ''}</a></div> : null}
            <span className="small muted">Invoice {pg.invoice}{pg.para ? `, also sent to ${pg.para}` : ''}. It updates here by itself after you pay.</span></>}
          {pg.estado === 'preparando' && <span className="small muted"><span className="spin" /> Preparing your invoice… it also goes to your email.</span>}
          {pg.estado === 'equipe' && <span className="small muted">Our team is finishing your invoice and will email it to you shortly. Your spots stay reserved.</span>}</div></li>
        <li className={`etapa${waiverOk ? ' ok' : pagoOk ? ' agora' : ''}`}><span className="marca" aria-hidden="true">{waiverOk ? '✓' : '3'}</span><div className="corpo">
          <b>{waiverOk ? 'Waiver signed' : 'Sign the waiver'}</b>
          {w.estado === 'assinar_aqui' && w.link && <div><Link className="btn primary" to={w.link}>Sign now</Link></div>}
          {w.estado === 'email' && <span className="small muted">Check your email from DocuSign{w.para ? ` (sent to ${w.para})` : ''} and sign it there.</span>}
          {w.estado === 'preparando' && <span className="small muted"><span className="spin" /> Sending the waiver…</span>}
          {w.estado === 'equipe' && <span className="small muted">Our team will email you the waiver shortly.</span>}</div></li>
        <li className={`etapa${c.confirmada ? ' ok' : ''}`}><span className="marca" aria-hidden="true">{c.confirmada ? '✓' : '4'}</span><div className="corpo">
          <b>{c.confirmada ? 'Confirmed' : 'Confirmed by itself'}</b>
          <span className="small muted">{c.confirmada ? 'See you at the track! Your URACE QR is on your Dashboard: show it at the shop.' : 'As soon as it is all done. We email you.'}</span></div></li>
      </ol>}
    <div className="row wrap etapas-fim" style={{ gap: 8 }}><Link className="btn" to="/portal/sessions">My sessions</Link><Link className="btn ghost" to="/portal/dashboard">Dashboard</Link></div>
  </div>
}
