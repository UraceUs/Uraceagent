/* Agendar sessão (#41): o cliente vê o mês com o que está aberto e marca para um piloto
 * da conta. Quem decide o que abre é a equipe, no site interno (Site público › Agenda). */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { papi, PortalError, usd, type Account, type AgendaCfg, type Booking, type Dia, type Servico } from './api'

const PERIODO: Record<string, string> = { manha: 'Morning', tarde: 'Afternoon', dia: 'Full day' }
const STATUS: Record<string, [string, string]> = { pendente: ['Waiting for confirmation', 'warn'], confirmada: ['Confirmed', 'ok'],
  recusada: ['Not available', 'crit'], cancelada: ['Cancelled', 'neutral'] }
const SEMANA = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function horaUS(h: string) {
  const [hh, mm] = h.split(':').map(Number)
  return `${((hh + 11) % 12) + 1}${mm ? `:${String(mm).padStart(2, '0')}` : ''} ${hh < 12 ? 'AM' : 'PM'}`
}
const faixa = (cfg: AgendaCfg, p: string) => p === 'manha' ? `${horaUS(cfg.morning_start)} – ${horaUS(cfg.morning_end)}`
  : p === 'tarde' ? `${horaUS(cfg.afternoon_start)} – ${horaUS(cfg.afternoon_end)}` : `${horaUS(cfg.morning_start)} – ${horaUS(cfg.afternoon_end)}`
const dataLonga = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
const mesDe = (iso: string) => iso.slice(0, 7)

export function MinhasSessoes({ sessoes, cfg, onCancelar }: { sessoes: Booking[]; cfg: AgendaCfg | null; onCancelar: (id: number) => void }) {
  if (!sessoes.length) return <p className="muted small" style={{ margin: 0 }}>No sessions yet.</p>
  return <div className="stack" style={{ gap: 8 }}>{sessoes.map(s => {
    const [rot, tom] = STATUS[s.status] || [s.status, 'neutral']
    const ativa = s.status === 'pendente' || s.status === 'confirmada'
    return <div className="card card-b row wrap portal-sessao" key={s.id}>
      <div className="grow"><b>{dataLonga(s.date)}</b>
        <div className="small muted">{PERIODO[s.period]}{cfg ? ` · ${faixa(cfg, s.period)}` : ''}{s.driver ? ` · ${s.driver}` : ''}</div>
        {s.service && <div className="small">{s.service}{s.price != null ? ` · ${usd(s.price)}` : ''}</div>}
        {s.decision_note && <div className="small">{s.decision_note}</div>}</div>
      <span className={`chip ${tom}`}>{rot}</span>
      {ativa && <button className="btn ghost sm" onClick={() => onCancelar(s.id)}>Cancel</button>}
    </div>
  })}</div>
}

export function Agendar({ conta }: { conta: Account }) {
  const hoje = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' })     // AAAA-MM-DD na Flórida
  const [dias, setDias] = useState<Dia[] | null>(null)
  const [cfg, setCfg] = useState<AgendaCfg | null>(null)
  const [servicos, setServicos] = useState<Servico[]>([])
  const [servico, setServico] = useState<number | null>(null)
  const [mes, setMes] = useState(mesDe(hoje))
  const [dia, setDia] = useState<string | null>(null)
  const [periodo, setPeriodo] = useState<'manha' | 'tarde' | 'dia' | null>(null)
  const [piloto, setPiloto] = useState<number | ''>(conta.drivers[0]?.id ?? '')
  const [nota, setNota] = useState('')
  const [sessoes, setSessoes] = useState<Booking[]>([])
  const [erro, setErro] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)

  const carregar = useCallback(async () => {
    try {
      const d = await papi<{ config: AgendaCfg; dias: Dia[]; services: Servico[] }>('GET', '/availability')
      setDias(d.dias); setCfg(d.config); setServicos(d.services)
      setServico(s => d.services.some(x => x.id === s) ? s : d.services.length === 1 ? d.services[0].id : null)
      // abre no primeiro mês que tem dia aberto: no dia 30, o mês corrente pode não ter mais nada
      const primeiro = d.dias.find(x => x.any_open)
      setMes(m => (d.dias.some(x => x.any_open && mesDe(x.date) === m) || !primeiro) ? m : mesDe(primeiro.date))
      setSessoes((await papi<{ bookings: Booking[] }>('GET', '/bookings')).bookings)
    } catch (e) { setErro((e as PortalError).message) }
  }, [])
  useEffect(() => { carregar() }, [carregar])

  const porData = useMemo(() => Object.fromEntries((dias || []).map(d => [d.date, d])), [dias])
  const meses = useMemo(() => [...new Set((dias || []).map(d => mesDe(d.date)))], [dias])
  const grade = useMemo(() => {
    const [a, m] = mes.split('-').map(Number)
    const primeiro = new Date(a, m - 1, 1).getDay(), total = new Date(a, m, 0).getDate()
    return [...Array(primeiro).fill(null), ...Array.from({ length: total }, (_, i) => `${mes}-${String(i + 1).padStart(2, '0')}`)]
  }, [mes])
  const escolhido = dia ? porData[dia] : null
  const temAlgo = (dias || []).some(d => d.any_open) && servicos.length > 0
  const escolhidoServico = servicos.find(x => x.id === servico)

  async function marcar() {
    if (!dia || !periodo || !servico) return
    setIndo(true); setErro(null); setOk(null)
    try {
      const r = await papi<{ bookings: Booking[] }>('POST', '/bookings', { date: dia, period: periodo, service_id: servico, driver_id: piloto || null, notes: nota || null })
      setSessoes(r.bookings); setOk(cfg?.auto_confirm ? 'Your session is confirmed. See you at the track!' : 'Request sent! We will confirm your session soon.')
      setDia(null); setPeriodo(null); setNota(''); carregar()
    } catch (e) { setErro((e as PortalError).message); carregar() } finally { setIndo(false) }
  }
  async function cancelar(id: number) {
    if (!window.confirm('Cancel this session?')) return
    try { setSessoes((await papi<{ bookings: Booking[] }>('POST', `/bookings/${id}/cancel`)).bookings); carregar() }
    catch (e) { setErro((e as PortalError).message) }
  }

  return <section className="stack" aria-labelledby="agendar-h">
    <h2 className="h2" id="agendar-h">Book a session</h2>
    {erro && <div className="banner crit" role="alert"><span className="bi">✕</span><div className="grow">{erro}</div></div>}
    {ok && <div className="banner ok" role="status"><span className="bi">✓</span><div className="grow">{ok}</div></div>}
    {!conta.drivers.length ? <p className="muted">Add a driver first, then pick a date.</p>
      : dias === null ? <div className="state"><span className="spin" /></div>
      : !temAlgo ? <p className="muted">No dates open for booking right now. Please check back soon or contact us.</p>
      : <div className="card card-b stack">
        <fieldset className="portal-servicos"><legend className="small">Session type</legend>
          {servicos.map(x => <label key={x.id} className={`portal-servico${servico === x.id ? ' on' : ''}`}>
            <input type="radio" name="servico" checked={servico === x.id} onChange={() => setServico(x.id)} />
            <span className="grow"><b>{x.name}</b>{x.description && <span className="small muted"> · {x.description}</span>}</span>
            <b>{usd(x.price)}</b></label>)}</fieldset>
        <div className="row"><button className="btn ghost sm" aria-label="Previous month" disabled={meses.indexOf(mes) <= 0} onClick={() => setMes(meses[meses.indexOf(mes) - 1])}>‹</button>
          <b className="grow" style={{ textAlign: 'center' }}>{new Date(mes + '-15T12:00:00').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</b>
          <button className="btn ghost sm" aria-label="Next month" disabled={meses.indexOf(mes) >= meses.length - 1} onClick={() => setMes(meses[meses.indexOf(mes) + 1])}>›</button></div>
        <div className="portal-cal" role="grid">
          {SEMANA.map(s => <div key={s} className="portal-cal-s" role="columnheader">{s}</div>)}
          {grade.map((iso, i) => {
            if (!iso) return <div key={`v${i}`} />
            const d = porData[iso], aberto = !!d?.any_open
            return <button key={iso} role="gridcell" className={`portal-cal-d${aberto ? ' aberto' : ''}${dia === iso ? ' on' : ''}`} disabled={!aberto}
              aria-label={`${dataLonga(iso)}${aberto ? ', available' : ', not available'}`} onClick={() => { setDia(iso); setPeriodo(null) }}>{Number(iso.slice(8))}</button>
          })}
        </div>
        {escolhido && cfg && <div className="stack" style={{ gap: 10 }}>
          <b>{dataLonga(escolhido.date)}</b>
          <div className="portal-periodos">{(['manha', 'tarde', 'dia'] as const).filter(p => escolhido.periods[p].open).map(p =>
            <button key={p} className={`btn${periodo === p ? ' primary' : ''}`} onClick={() => setPeriodo(p)} aria-pressed={periodo === p}>
              <span>{PERIODO[p]}</span><span className="small">{faixa(cfg, p)}</span></button>)}</div>
          <label className="fld"><span>Driver</span>
            <select value={piloto} onChange={e => setPiloto(e.target.value ? Number(e.target.value) : '')}>
              {conta.drivers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          <label className="fld"><span>Anything we should know? <i>optional</i></span><textarea value={nota} onChange={e => setNota(e.target.value)} maxLength={500} /></label>
          {escolhidoServico && <p className="small" style={{ margin: 0 }}>{escolhidoServico.name} · <b>{usd(escolhidoServico.price)}</b> per driver</p>}
          <div><button className="btn primary" disabled={!periodo || !servico || indo} onClick={marcar}>{indo ? 'Booking…' : cfg.auto_confirm ? 'Book session' : 'Request session'}</button></div>
        </div>}
      </div>}
    <h2 className="h2">Your sessions</h2>
    <MinhasSessoes sessoes={sessoes} cfg={cfg} onCancelar={cancelar} />
  </section>
}
