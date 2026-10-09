/* Reserva do site (#164): a jornada inteira numa tela, com a identidade do urace.us.
 *
 * Dono, 08/10: "a pessoa vai marcar o horário, o dia e o valor ... Na mesma tela, pode ir abrindo
 * sessões para ela conseguir finalizar ... ou ela loga ou ela cria a conta dela ... daí ela vai para a
 * etapa de compra ... e dali ela recebe a confirmação". As etapas nunca se pulam: 1 sessão → 2 conta →
 * 3 piloto → 4 revisar e pagar. Cada etapa só abre quando a anterior está pronta, e a escolha do site
 * (kart, dia, turno e de onde veio a pessoa) atravessa o login sem se perder. */
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { bloqueioDoPiloto, dataLonga, escolhaDoSite, faixa, PERIODOS } from './Agendar'
import { papi, PortalError, usd, type Account, type AgendaCfg, type Checkout, type Servico, type CheckoutPlano, type Plano } from './api'
import { Aviso, Campo, Endereco, FormPiloto } from './Portal'

interface DiaPublico { date: string; manha: { open: boolean; spots: number }; tarde: { open: boolean; spots: number } }
type Turno = 'manha' | 'tarde'
const CAMPANHA = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'gclid', 'fbclid', 'ref']
const GUARDA = 'urace.reserva'

/** A escolha e a campanha ficam na aba: criar a conta ou entrar não pode apagar o que a pessoa escolheu. */
function lerGuardado(): Record<string, string> {
  try { return JSON.parse(sessionStorage.getItem(GUARDA) || '{}') } catch { return {} }
}
function guardar(x: Record<string, string>) {
  try { sessionStorage.setItem(GUARDA, JSON.stringify(x)) } catch { /* navegador sem armazenamento: vale só nesta tela */ }
}

export function Reservar({ conta, onConta }: { conta: Account | null; onConta: (a: Account | null) => void }) {
  const [q] = useSearchParams()
  const nav = useNavigate()
  const inicial = useMemo(() => {
    const g = lerGuardado()
    const site = escolhaDoSite(q)
    const utm = Object.fromEntries(CAMPANHA.map(k => [k, q.get(k) || g[k] || '']).filter(([, v]) => v))
    const t = site.periodo || g.turno
    return { dia: site.dia || g.dia || null, turno: (t === 'manha' || t === 'tarde' ? t : null) as Turno | null,
      kart: site.kart || g.kart || null, servico: Number(q.get('service') || g.servico) || null,
      plano: Number(q.get('plan') || g.plano) || null, utm }                   // #169: plano mensal (Academy, Boost)
  }, [q])
  const [planos, setPlanos] = useState<Plano[] | null>(null)
  const [planoOk, setPlanoOk] = useState(false)
  const [servicos, setServicos] = useState<Servico[] | null>(null)
  const [autoSell, setAutoSell] = useState(false)
  const [dias, setDias] = useState<DiaPublico[] | null>(null)
  const [cfg, setCfg] = useState<AgendaCfg | null>(null)
  const [servico, setServico] = useState<number | null>(inicial.servico)
  const [dia, setDia] = useState<string | null>(inicial.dia)
  const [turno, setTurno] = useState<Turno | null>(inicial.turno)
  const [sessaoOk, setSessaoOk] = useState(false)
  const [piloto, setPiloto] = useState<number | null>(null)
  const [novoPiloto, setNovoPiloto] = useState(false)
  const [nota, setNota] = useState(inicial.kart ? `Kart: ${inicial.kart}` : '')
  const [aceite, setAceite] = useState(false)
  const [maisDias, setMaisDias] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)

  useEffect(() => {
    if (!inicial.plano) return
    fetch('/ops/api/vitrine/planos', { credentials: 'omit' }).then(r => r.json())
      .then((x: { plans: Plano[]; auto_sell: boolean }) => { setPlanos(x.plans); setAutoSell(x.auto_sell) })
      .catch(() => setErro('We could not load the plans. Please refresh the page.'))
  }, [inicial])
  useEffect(() => {
    if (inicial.plano) return
    Promise.all([fetch('/ops/api/vitrine/servicos', { credentials: 'omit' }).then(r => r.json()),
      fetch('/ops/api/vitrine/agenda', { credentials: 'omit' }).then(r => r.json())])
      .then(([s, a]: [{ services: Servico[]; auto_sell: boolean }, { config: AgendaCfg; dias: DiaPublico[] }]) => {
        setServicos(s.services); setAutoSell(s.auto_sell); setCfg(a.config); setDias(a.dias)
        // o kart escolhido no site escolhe o serviço com esse nome, quando há um só
        const doKart = inicial.kart ? s.services.filter(x => x.name.toLowerCase().includes(inicial.kart!.toLowerCase())) : []
        setServico(v => s.services.some(x => x.id === v) ? v : doKart.length === 1 ? doKart[0].id : s.services.length === 1 ? s.services[0].id : null)
        setDia(d => d && a.dias.some(x => x.date === d && (x.manha.open || x.tarde.open)) ? d : null)
      })
      .catch(() => setErro('We could not load the calendar. Please refresh the page.'))
  }, [inicial])

  // guarda a escolha e a campanha a cada mudança (sobrevive ao login)
  useEffect(() => {
    guardar({ ...(dia ? { dia } : {}), ...(turno ? { turno } : {}), ...(inicial.kart ? { kart: inicial.kart } : {}),
      ...(servico ? { servico: String(servico) } : {}), ...(inicial.plano ? { plano: String(inicial.plano) } : {}), ...inicial.utm })
  }, [dia, turno, servico, inicial])

  const abertos = useMemo(() => (dias || []).filter(d => d.manha.open || d.tarde.open), [dias])
  const escolhidoDia = abertos.find(d => d.date === dia) || null
  const s = servicos?.find(x => x.id === servico) || null
  const deposito = s?.deposit || 0
  const plano = inicial.plano ? planos?.find(x => x.id === inicial.plano) || null : null
  const sessaoPronta = plano ? true : !!(s && escolhidoDia && turno && escolhidoDia[turno].open)
  const passo1 = plano ? planoOk : sessaoPronta && sessaoOk
  const passo2 = passo1 && !!conta
  const livres = (conta?.drivers || []).filter(p => !bloqueioDoPiloto(p))
  const pilotoId = piloto ?? (livres.length === 1 ? livres[0].id : null)     // um piloto só: já vem escolhido
  const p = conta?.drivers.find(x => x.id === pilotoId) || null
  const passo3 = passo2 && !!p && !bloqueioDoPiloto(p) && !(conta?.missing.length)

  async function reservar() {
    if (!passo3) return
    setIndo(true); setErro(null)
    if (plano) {
      try {
        const r = await papi<{ id: number; auto_sell: boolean }>('POST', '/plans', { service_id: plano.id, driver_id: pilotoId, origin: 'site',
          utm: Object.keys(inicial.utm).length ? inicial.utm : null })
        try { sessionStorage.removeItem(GUARDA) } catch { /* nada guardado */ }
        nav(`/portal/plans/${r.id}`, { replace: true })
      } catch (e) { setErro((e as PortalError).message) } finally { setIndo(false) }
      return
    }
    if (!s || !dia || !turno) { setIndo(false); return }
    try {
      const r = await papi<{ id: number; auto_sell: boolean }>('POST', '/bookings', { date: dia, period: turno, service_id: s.id,
        driver_id: pilotoId, notes: nota || null, origin: 'site', utm: Object.keys(inicial.utm).length ? inicial.utm : null })
      try { sessionStorage.removeItem(GUARDA) } catch { /* nada guardado */ }
      nav(`/portal/sessions/${r.id}`, { replace: true })
    } catch (e) { setErro((e as PortalError).message) } finally { setIndo(false) }
  }

  const estado = (pronto: boolean, aberto: boolean) => `reserva-passo${pronto ? ' feito' : aberto ? '' : ' fechado'}`
  return <div className="stack" style={{ gap: 16 }}>
    <div><h1 className="h1">{inicial.plano ? 'Join the plan' : 'Book your session'}</h1>
      <p className="muted" style={{ margin: '6px 0 0' }}>{inicial.plano
        ? 'Four quick steps. Your plan is active as soon as the first month is paid and the waiver is signed.'
        : 'Four quick steps. Your spot is confirmed as soon as the invoice is paid and the waiver is signed.'}</p></div>
    <Aviso erro={erro} />
    <ol className="reserva-passos">
      {/* 1 · a sessão (ou o plano, #169) */}
      {inicial.plano ? <li className={estado(passo1, true)}><section className="card" aria-labelledby="r1">
        <div className="reserva-cab"><span className="reserva-num" aria-hidden="true">{passo1 ? '✓' : '1'}</span><h2 className="h2" id="r1">Your plan</h2>
          {passo1 && <button className="btn ghost sm" onClick={() => setPlanoOk(false)}>Change</button>}</div>
        {planos === null ? <div className="state"><span className="spin" /></div>
          : !plano ? <p className="muted" style={{ margin: 0 }}>This plan is not available right now. <a href="/academy/">See the plans</a> or contact us at support@urace.us.</p>
          : passo1 ? <p className="reserva-resumo" style={{ margin: 0 }}>{plano.name} · {plano.months} month{plano.months > 1 ? 's' : ''} · <b>{usd(plano.price)}</b> per month</p>
          : <>
            <div className="reserva-total" aria-live="polite">
              <div><span><b>{plano.name}</b>{plano.description && <span className="small muted"> · {plano.description}</span>}</span><span>{usd(plano.price)}<span className="small muted">/month</span></span></div>
              {plano.sessions_month > 0 && <div className="small muted"><span>{plano.sessions_month} sessions a month · {plano.months} month{plano.months > 1 ? 's' : ''}</span></div>}
              <div className="soma"><span>First month, invoiced today</span><span>{usd(plano.price)}</span></div>
              {plano.months > 1 && <div className="small muted"><span>Then {usd(plano.price)} on the 1st of each of the next {plano.months - 1} months (total {usd(plano.total)}).</span></div>}</div>
            <div><button className="btn primary" onClick={() => setPlanoOk(true)}>Continue</button></div>
          </>}
      </section></li>
      : <li className={estado(passo1, true)}><section className="card" aria-labelledby="r1">
        <div className="reserva-cab"><span className="reserva-num" aria-hidden="true">{passo1 ? '✓' : '1'}</span><h2 className="h2" id="r1">Your session</h2>
          {passo1 && <button className="btn ghost sm" onClick={() => setSessaoOk(false)}>Change</button>}</div>
        {passo1 && s && dia && turno && cfg ? <p className="reserva-resumo" style={{ margin: 0 }}>{s.name} · {dataLonga(dia)} · {PERIODOS[turno]} ({faixa(cfg, turno)}) · <b>{usd(s.price)}</b></p>
          : servicos === null || dias === null ? <div className="state"><span className="spin" /></div>
          : !servicos.length || !abertos.length ? <p className="muted" style={{ margin: 0 }}>No dates open for booking right now. Please check back soon or contact us at support@urace.us.</p>
          : <>
            <fieldset className="reserva-opcoes" style={{ border: 0, padding: 0, margin: 0 }}><legend className="small muted" style={{ marginBottom: 6 }}>Kart and session</legend>
              {servicos.map(x => <label key={x.id} className={`reserva-opcao${servico === x.id ? ' on' : ''}`}>
                <input type="radio" name="servico" checked={servico === x.id} onChange={() => setServico(x.id)} />
                <span className="grow"><b>{x.name}</b>{x.description && <span className="small muted"> · {x.description}</span>}</span><b>{usd(x.price)}</b></label>)}</fieldset>
            <div><div className="small muted" style={{ marginBottom: 6 }} id="r1-dia">Day</div>
              <div className="reserva-dias" role="group" aria-labelledby="r1-dia">{abertos.filter((d, i) => maisDias || i < 8 || d.date === dia).map(d =>
                <button key={d.date} type="button" className="reserva-dia" aria-pressed={dia === d.date} onClick={() => { setDia(d.date); setTurno(t => t && d[t].open ? t : null) }}>
                  {new Date(d.date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}</button>)}
                {!maisDias && abertos.length > 8 && <button type="button" className="reserva-dia" onClick={() => setMaisDias(true)}>More dates…</button>}</div></div>
            {escolhidoDia && cfg && <div><div className="small muted" style={{ marginBottom: 6 }} id="r1-turno">Time</div>
              <div className="reserva-turnos" role="group" aria-labelledby="r1-turno">{(['manha', 'tarde'] as const).map(t =>
                <button key={t} type="button" className="reserva-turno" aria-pressed={turno === t} disabled={!escolhidoDia[t].open} onClick={() => setTurno(t)}>
                  <b>{PERIODOS[t]}</b><span className="small muted">{faixa(cfg, t)}{escolhidoDia[t].open ? ` · ${escolhidoDia[t].spots} spot${escolhidoDia[t].spots === 1 ? '' : 's'} left` : ' · full'}</span></button>)}</div></div>}
            {s && <div className="reserva-total" aria-live="polite">
              <div><span>{s.name}</span><span>{usd(s.price)}</span></div>
              {deposito > 0 && <div><span>Security deposit <span className="small muted">(refundable)</span></span><span>{usd(deposito)}</span></div>}
              <div className="soma"><span>Total</span><span>{usd(s.price + deposito)}</span></div></div>}
            <div><button className="btn primary" disabled={!sessaoPronta} onClick={() => setSessaoOk(true)}>Continue</button></div>
          </>}
      </section></li>}

      {/* 2 · a conta */}
      <li className={estado(passo2, passo1)}><section className="card" aria-labelledby="r2">
        <div className="reserva-cab"><span className="reserva-num" aria-hidden="true">{passo2 ? '✓' : '2'}</span><h2 className="h2" id="r2">Your account</h2></div>
        {!passo1 ? <p className="small muted" style={{ margin: 0 }}>Sign in or create your URACE account. It keeps your drivers, sizes, waivers and bookings.</p>
          : conta ? <div className="reserva-conta-ok"><span>Signed in as <b>{conta.name}</b> <span className="muted">· {conta.email}</span></span>
            <button className="btn ghost sm" onClick={async () => { try { await papi('POST', '/logout') } finally { onConta(null) } }}>Not you?</button>
            {conta.missing.length > 0 && <div className="banner warn" style={{ width: '100%' }}><span className="bi">▲</span><div className="grow">
              Please complete the account holder details (phone and address) in <Link to="/portal/account">Account</Link>, then come back.</div></div>}</div>
          : <ContaNaReserva onConta={onConta} />}
      </section></li>

      {/* 3 · o piloto */}
      <li className={estado(passo3, passo2)}><section className="card" aria-labelledby="r3">
        <div className="reserva-cab"><span className="reserva-num" aria-hidden="true">{passo3 ? '✓' : '3'}</span><h2 className="h2" id="r3">Driver</h2></div>
        {!passo2 || !conta ? <p className="small muted" style={{ margin: 0 }}>Who will drive the kart: your child or children, or you.</p> : <>
          {conta.drivers.length > 0 && <div className="reserva-opcoes" role="radiogroup" aria-labelledby="r3">{conta.drivers.map(x => {
            const b = bloqueioDoPiloto(x)
            return <label key={x.id} className={`reserva-opcao${pilotoId === x.id ? ' on' : ''}`}>
              <input type="radio" name="piloto" checked={pilotoId === x.id} disabled={!!b} onChange={() => setPiloto(x.id)} />
              <span className="grow"><b>{x.name}</b>{x.age != null && <span className="small muted"> · {x.age} years old</span>}
                {b && <span className="small" style={{ display: 'block', color: 'var(--crit)' }}>{b}: <Link to="/portal/drivers">update</Link></span>}</span></label>
          })}</div>}
          {novoPiloto || !conta.drivers.length
            ? <FormPiloto onSalvo={a => { onConta(a); const novo = a.drivers.find(x => !conta.drivers.some(y => y.id === x.id)); if (novo) setPiloto(novo.id) }}
              onFechar={() => setNovoPiloto(false)} />
            : <div><button className="btn sm" onClick={() => setNovoPiloto(true)}>+ Add a driver</button></div>}
        </>}
      </section></li>

      {/* 4 · revisar e pagar */}
      <li className={estado(false, passo3)}><section className="card" aria-labelledby="r4">
        <div className="reserva-cab"><span className="reserva-num" aria-hidden="true">4</span><h2 className="h2" id="r4">{autoSell ? 'Review and pay' : 'Review and request'}</h2></div>
        {plano ? (!passo3 ? <p className="small muted" style={{ margin: 0 }}>{autoSell
          ? 'You get the first month\'s invoice to pay online, and the waiver to sign. The next months are invoiced on the 1st.'
          : 'We confirm your plan and send the invoice and the waiver.'}</p> : <>
          <div className="reserva-total">
            <div><span>{plano.name} · {p?.name}</span><span>{usd(plano.price)}<span className="small muted">/month</span></span></div>
            <div className="small muted"><span>{plano.months} month{plano.months > 1 ? 's' : ''}{plano.sessions_month > 0 ? ` · ${plano.sessions_month} sessions a month` : ''}</span></div>
            <div className="soma"><span>Today (first month)</span><span>{usd(plano.price)}</span></div></div>
          <ul className="reserva-politica">
            {plano.months > 1 && <li>The next {plano.months - 1} month{plano.months > 2 ? 's' : ''} are invoiced on the 1st of each month, {usd(plano.price)} each (total {usd(plano.total)}).</li>}
            <li>Your plan is active as soon as the first month is paid and the waiver is signed. Then you book your sessions here, any time.</li>
            <li>Track fees are paid to the Orlando Kart Center.</li>
          </ul>
          <label className="check"><input type="checkbox" checked={aceite} onChange={e => setAceite(e.target.checked)} /> I agree to the <a href="/legal/eula.html" target="_blank" rel="noreferrer">terms</a> and the plan policy above</label>
          <div><button className="btn primary" disabled={!aceite || indo} onClick={reservar}>{indo ? 'Sending…' : autoSell ? `Join and pay ${usd(plano.price)}` : 'Request this plan'}</button></div>
        </>) : !passo3 || !s || !dia || !turno || !cfg ? <p className="small muted" style={{ margin: 0 }}>{autoSell
          ? 'You get the invoice (session + refundable security deposit) to pay online, and the waiver to sign.'
          : 'We confirm your spot and send the invoice and the waiver.'}</p> : <>
          <div className="reserva-total">
            <div><span>{s.name} · {p?.name}</span><span>{usd(s.price)}</span></div>
            <div className="small muted"><span>{dataLonga(dia)} · {PERIODOS[turno]} ({faixa(cfg, turno)})</span></div>
            {deposito > 0 && <div><span>Security deposit <span className="small muted">(refundable)</span></span><span>{usd(deposito)}</span></div>}
            <div className="soma"><span>Total</span><span>{usd(s.price + deposito)}</span></div></div>
          <ul className="reserva-politica">
            {deposito > 0 && <li>The security deposit is returned within 5 business days after the session if there is no incident.</li>}
            <li>Your spot is confirmed as soon as the invoice is paid and the waiver is signed.</li>
            <li>Track fees are paid to the Orlando Kart Center.</li>
          </ul>
          <Campo rotulo="Anything we should know?" dica="optional"><textarea value={nota} onChange={e => setNota(e.target.value)} maxLength={500} /></Campo>
          <label className="check"><input type="checkbox" checked={aceite} onChange={e => setAceite(e.target.checked)} /> I agree to the <a href="/legal/eula.html" target="_blank" rel="noreferrer">terms</a> and the booking policy above</label>
          <div><button className="btn primary" disabled={!aceite || indo} onClick={reservar}>{indo ? 'Booking…' : autoSell ? `Book and pay ${usd(s.price + deposito)}` : 'Request this session'}</button></div>
        </>}
      </section></li>
    </ol>
  </div>
}

/** Entrar ou criar a conta sem sair da reserva. */
function ContaNaReserva({ onConta }: { onConta: (a: Account) => void }) {
  const [aba, setAba] = useState<'nova' | 'entrar'>('nova')
  return <div className="reserva-conta">
    <div className="reserva-abas" role="tablist" aria-label="Account">
      <button role="tab" type="button" aria-selected={aba === 'nova'} aria-controls="aba-nova" onClick={() => setAba('nova')}>New to URACE</button>
      <button role="tab" type="button" aria-selected={aba === 'entrar'} aria-controls="aba-entrar" onClick={() => setAba('entrar')}>I have an account</button>
    </div>
    {aba === 'nova' ? <div id="aba-nova" role="tabpanel"><CriarConta onConta={onConta} /></div> : <div id="aba-entrar" role="tabpanel"><EntrarNaReserva onConta={onConta} /></div>}
  </div>
}

function EntrarNaReserva({ onConta }: { onConta: (a: Account) => void }) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  async function enviar(e: FormEvent) {
    e.preventDefault(); setErro(null); setIndo(true)
    try { onConta(await papi<Account>('POST', '/login', { email, password: senha })) }
    catch (ex) { setErro((ex as PortalError).message) } finally { setIndo(false) }
  }
  return <form className="stack" onSubmit={enviar} noValidate>
    <Aviso erro={erro} />
    <Campo rotulo="Email"><input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required /></Campo>
    <Campo rotulo="Password"><input type="password" autoComplete="current-password" value={senha} onChange={e => setSenha(e.target.value)} required /></Campo>
    <div><button className="btn primary" disabled={indo || !email || !senha}>{indo ? 'Signing in…' : 'Sign in and continue'}</button></div>
    <p className="small muted" style={{ margin: 0 }}><Link to="/portal/forgot">Forgot your password?</Link> We will keep your session choice.</p>
  </form>
}

function CriarConta({ onConta }: { onConta: (a: Account) => void }) {
  const [f, setF] = useState({ name: '', email: '', password: '', birth_date: '', country: 'US', phone_country: '+1', phone: '',
    address_line1: '', address_line2: '', city: '', state: '', zip: '', accept_terms: false, i_am_driver: false })
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  const muda = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF(x => ({ ...x, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  async function enviar(e: FormEvent) {
    e.preventDefault(); setErro(null); setIndo(true)
    try { onConta(await papi<Account>('POST', '/signup', f)) }
    catch (ex) { setErro((ex as PortalError).message) } finally { setIndo(false) }
  }
  return <form className="stack" onSubmit={enviar} noValidate>
    <p className="small muted" style={{ margin: 0 }}>The account holder is the adult responsible (18 or older): the parent or guardian, or the driver if they are an adult.</p>
    <Aviso erro={erro} />
    <div className="portal-2">
      <Campo rotulo="Full name" obrigatorio><input autoComplete="name" value={f.name} onChange={muda('name')} required /></Campo>
      <Campo rotulo="Date of birth" obrigatorio><input type="date" autoComplete="bday" value={f.birth_date} onChange={muda('birth_date')} required /></Campo>
    </div>
    <div className="portal-2">
      <Campo rotulo="Email" obrigatorio><input type="email" autoComplete="email" value={f.email} onChange={muda('email')} required /></Campo>
      <Campo rotulo="Password" dica="at least 8 characters" obrigatorio><input type="password" autoComplete="new-password" value={f.password} onChange={muda('password')} required minLength={8} /></Campo>
    </div>
    <Endereco f={f} set={setF} />
    <label className="check"><input type="checkbox" checked={f.i_am_driver} onChange={muda('i_am_driver')} /> I am also a driver (I will drive the kart myself)</label>
    <label className="check"><input type="checkbox" checked={f.accept_terms} onChange={muda('accept_terms')} /> I accept the <a href="/legal/eula.html" target="_blank" rel="noreferrer">terms</a> and the <a href="/legal/privacy.html" target="_blank" rel="noreferrer">privacy policy</a></label>
    <div><button className="btn primary" disabled={indo}>{indo ? 'Creating…' : 'Create account and continue'}</button></div>
  </form>
}

/* ------------------------------------------------------------ acompanhar o pedido */
/** As etapas de um pedido: reservado → pagar → waiver → confirmado. Atualiza sozinho enquanto falta algo. */
/** O acompanhamento serve à sessão (#164) e ao plano mensal (#169): o que muda é o resumo e o fim. */
type Resumo = { titulo: string; sub: string; confirmada: boolean; encerrada: boolean; aceita: boolean; status: string
  reservado: string; reservadoSub: string; pagar: string; pagarSub: string; fim: string; fimSub: string; fimOk: string; volta: string; voltaRotulo: string }

function resumoSessao(c: Checkout, cfg: AgendaCfg | null): Resumo {
  const encerrada = c.status === 'cancelada' || c.status === 'recusada'
  return { titulo: c.confirmada ? "You're confirmed!" : encerrada ? 'Your booking' : 'Almost there',
    sub: `${c.service} · ${dataLonga(c.date)} · ${PERIODOS[c.period]}${cfg ? ` (${faixa(cfg, c.period)})` : ''}${c.driver ? ` · ${c.driver}` : ''}`,
    confirmada: c.confirmada, encerrada, aceita: c.aceita, status: c.status, reservado: 'Spot reserved', reservadoSub: 'We are holding it for you.',
    pagar: 'Pay the invoice', pagarSub: 'Session + refundable security deposit. It updates here by itself after you pay.',
    fim: 'Confirmed by itself', fimOk: 'Confirmed', fimSub: 'As soon as the invoice is paid and the waiver is signed. We email you.',
    volta: '/portal/sessions', voltaRotulo: 'My sessions' }
}

function resumoPlano(c: CheckoutPlano): Resumo {
  const mes = (m: string) => new Date(m + '-01T12:00:00').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
  return { titulo: c.ativo ? 'Your plan is active!' : c.status === 'cancelada' ? 'Your plan' : 'Almost there',
    sub: `${c.plan} · ${c.months} month${c.months > 1 ? 's' : ''} · ${usd(c.price)} per month${c.driver ? ` · ${c.driver}` : ''}`,
    confirmada: c.ativo, encerrada: c.status === 'cancelada', aceita: c.aceita, status: c.status,
    reservado: 'Plan chosen', reservadoSub: c.next_months.length ? `The next months (${c.next_months.map(mes).join(', ')}) are invoiced on the 1st, ${usd(c.price)} each.` : 'One month, invoiced today.',
    pagar: 'Pay the first month', pagarSub: 'It updates here by itself after you pay.',
    fim: 'Active by itself', fimOk: 'Active', fimSub: 'As soon as the first month is paid and the waiver is signed. Then book your sessions here.',
    volta: '/portal/book', voltaRotulo: 'Book a session' }
}

export function Acompanhar({ plano = false }: { plano?: boolean }) {
  const { id } = useParams()
  const [c, setC] = useState<Checkout | CheckoutPlano | null>(null)
  const [cfg, setCfg] = useState<AgendaCfg | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const carregar = useCallback(async () => {
    try { setC(await papi<Checkout | CheckoutPlano>('GET', plano ? `/plans/${id}` : `/bookings/${id}`)); setErro(null) }
    catch (e) { setErro((e as PortalError).message) }
  }, [id, plano])
  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { if (plano) return; fetch('/ops/api/vitrine/agenda', { credentials: 'omit' }).then(r => r.json()).then(a => setCfg(a.config)).catch(() => null) }, [plano])
  const r = c ? (plano ? resumoPlano(c as CheckoutPlano) : resumoSessao(c as Checkout, cfg)) : null
  const preparando = !!c && (c.pagamento.estado === 'preparando' || c.waiver.estado === 'preparando')
  useEffect(() => {
    if (!c || !r || r.confirmada || r.encerrada) return
    const t = window.setTimeout(carregar, preparando ? 4000 : 20000)
    return () => window.clearTimeout(t)
  }, [c, r, preparando, carregar])

  if (erro && !c) return <div className="stack"><h1 className="h1">{plano ? 'Your plan' : 'Your booking'}</h1><Aviso erro={erro} /><div><Link className="btn" to={plano ? '/portal/dashboard' : '/portal/sessions'}>{plano ? 'Dashboard' : 'My sessions'}</Link></div></div>
  if (!c || !r) return <div className="state"><span className="spin" /></div>
  const pg = c.pagamento, w = c.waiver
  const pagoOk = pg.estado === 'pago' || pg.estado === 'contrato'
  const waiverOk = w.estado === 'ok'
  const encerrada = r.encerrada
  return <div className="stack" style={{ gap: 16 }}>
    <div><h1 className="h1">{r.titulo}</h1>
      <p className="muted" style={{ margin: '6px 0 0' }}>{r.sub}</p></div>
    {encerrada ? <div className="banner warn"><span className="bi">▲</span><div className="grow">This {plano ? 'plan' : 'booking'} was {r.status === 'cancelada' ? 'cancelled' : 'not accepted'}. <Link to="/portal/book">Book another session</Link></div></div>
      : !r.aceita && !r.confirmada ? <div className="banner info" role="status"><span className="bi">●</span><div className="grow">Request received. {plano ? 'Our team confirms your plan and sends the invoice and the waiver by email.' : 'We are holding your spot: our team confirms it and sends the invoice and the waiver by email.'}</div></div>
      : <ol className="etapas" aria-label="Steps to confirm">
        <li className="etapa ok"><span className="marca" aria-hidden="true">✓</span><div className="corpo"><b>{r.reservado}</b><span className="small muted">{r.reservadoSub}</span></div></li>
        <li className={`etapa${pagoOk ? ' ok' : ' agora'}`}><span className="marca" aria-hidden="true">{pagoOk ? '✓' : '2'}</span><div className="corpo">
          <b>{pg.estado === 'contrato' ? 'Part of your plan' : pagoOk ? 'Paid' : r.pagar}</b>
          {pg.estado === 'pagar' && <>{pg.link ? <div><a className="btn primary" href={pg.link} target="_blank" rel="noopener noreferrer">Pay now{pg.total != null ? ` ${usd(pg.total)}` : ''}</a></div> : null}
            <span className="small muted">Invoice {pg.invoice}{pg.para ? `, also sent to ${pg.para}` : ''}. {r.pagarSub}</span></>}
          {pg.estado === 'preparando' && <span className="small muted"><span className="spin" /> Preparing your invoice… it also goes to your email.</span>}
          {pg.estado === 'equipe' && <span className="small muted">Our team is finishing your invoice and will email it to you shortly. Your spot stays reserved.</span>}</div></li>
        <li className={`etapa${waiverOk ? ' ok' : pagoOk ? ' agora' : ''}`}><span className="marca" aria-hidden="true">{waiverOk ? '✓' : '3'}</span><div className="corpo">
          <b>{waiverOk ? 'Waiver signed' : 'Sign the waiver'}</b>
          {w.estado === 'assinar_aqui' && w.link && <div><Link className="btn primary" to={w.link}>Sign now</Link></div>}
          {w.estado === 'email' && <span className="small muted">Check your email from DocuSign{w.para ? ` (sent to ${w.para})` : ''} and sign it there.</span>}
          {w.estado === 'preparando' && <span className="small muted"><span className="spin" /> Sending the waiver…</span>}
          {w.estado === 'equipe' && <span className="small muted">Our team will email you the waiver shortly.</span>}</div></li>
        <li className={`etapa${r.confirmada ? ' ok' : ''}`}><span className="marca" aria-hidden="true">{r.confirmada ? '✓' : '4'}</span><div className="corpo">
          <b>{r.confirmada ? r.fimOk : r.fim}</b>
          <span className="small muted">{r.confirmada ? (plano ? 'Book your sessions any time. Your URACE QR is on your Dashboard: show it at the shop.' : 'See you at the track! Your URACE QR is on your Dashboard: show it at the shop.') : r.fimSub}</span></div></li>
      </ol>}
    <div className="row wrap etapas-fim" style={{ gap: 8 }}><Link className="btn" to={r.volta}>{r.voltaRotulo}</Link><Link className="btn ghost" to="/portal/dashboard">Dashboard</Link></div>
  </div>
}
