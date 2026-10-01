/* Área do cliente (#40, #54) — hoje em /ops/portal (site interno, para testar); depois no
 * site público. Em inglês: é o idioma do site público (urace.us, en-US). Fora do Shell e da
 * sessão da equipe: tem a própria conta, o próprio login e o próprio cabeçalho.
 *
 * Dono, 01/10: o login é o mesmo desenho do Command Center; dentro, um menu com cada
 * seção numa tela (Dashboard, Book a session, My sessions, Drivers, History, Account). */
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { Pista } from '../components/Pista'
import { Agendar, CartaoSessao, Sessoes } from './Agendar'
import { haDias, papi, PortalError, type Account, type Driver, type Painel } from './api'
import { ddiDe, PAISES } from './paises'
import { guardarVisual, visual3d } from './visual'
import '../styles/portal-3d.css'

type Estado = Account | null | undefined           // undefined = carregando; null = sem sessão

// [chave, rótulo, tipo, obrigatória]
const MEDIDAS: [string, string, 'num' | 'txt', boolean][] = [
  ['height_in', 'Height (in)', 'num', true], ['weight_lb', 'Weight (lb)', 'num', true], ['chest_in', 'Chest (in)', 'num', true],
  ['waist_in', 'Waist (in)', 'num', true], ['hips_in', 'Hips (in)', 'num', false], ['inseam_in', 'Inseam (in)', 'num', false],
  ['sleeve_in', 'Sleeve (in)', 'num', false], ['suit_size', 'Suit size', 'txt', false], ['helmet_size', 'Helmet size', 'txt', false],
  ['glove_size', 'Glove size', 'txt', false], ['shoe_size', 'Shoe size (US)', 'txt', false],
]
const ROTULO: Record<string, string> = { name: 'full name', birth_date: 'date of birth', height_in: 'height', weight_lb: 'weight',
  chest_in: 'chest', waist_in: 'waist', hips_in: 'hips', experience: 'karting experience', phone: 'phone',
  address_line1: 'street address', city: 'city', state: 'state', zip: 'ZIP code' }
const MENU: [string, string, string, string][] = [   // rota, rótulo, rótulo curto (celular), ícone
  ['dashboard', 'Dashboard', 'Home', 'home'], ['book', 'Book a session', 'Book', 'cal'], ['sessions', 'My sessions', 'Sessions', 'list'],
  ['drivers', 'Drivers', 'Drivers', 'people'], ['history', 'Service history', 'History', 'clock'], ['account', 'Account', 'Account', 'user'],
]
const dataUS = (iso: string | null) => iso ? new Date(iso.length === 10 ? iso + 'T12:00:00' : iso)
  .toLocaleDateString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric' }) : '—'
const SITUACAO: Record<string, [string, string]> = { ok: ['Measurements up to date', 'ok'], aviso: ['Update measurements soon', 'warn'],
  vencida: ['Measurements expired', 'crit'], faltando: ['Profile incomplete', 'crit'] }

function Aviso({ erro }: { erro: string | null }) {
  return erro ? <div className="banner crit" role="alert"><span className="bi" aria-hidden="true">✕</span><div className="grow">{erro}</div></div> : null
}

function Campo({ rotulo, children, dica, obrigatorio }: { rotulo: string; children: ReactNode; dica?: string; obrigatorio?: boolean }) {
  return <label className="fld"><span>{rotulo}{obrigatorio && <b className="portal-obr" aria-hidden="true"> *</b>}{dica && <i> · {dica}</i>}</span>{children}</label>
}

function Visual({ tresD, mudar }: { tresD: boolean; mudar: (v: boolean) => void }) {
  return <button type="button" className="portal-visual" onClick={() => { guardarVisual(!tresD); mudar(!tresD) }}>
    {tresD ? 'Classic look' : '3D look'}</button>
}

/* ------------------------------------------------------------ fora da conta: o login da equipe */
function CascaLogin({ children, lema }: { children: ReactNode; lema: string }) {
  return <div className="login portal-login">
    <div className="art">
      <Pista />
      <div className="mark"><span className="mark-u" aria-hidden="true">U</span><b>URACE</b><span>Driver area</span></div>
      <p className="lema">{lema}</p>
    </div>
    <i className="corte" aria-hidden="true" />
    <div className="form">{children}</div>
  </div>
}

function Entrar({ onEntrou }: { onEntrou: (a: Account) => void }) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [ver, setVer] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  async function enviar(e: FormEvent) {
    e.preventDefault(); setErro(null); setIndo(true)
    try { onEntrou(await papi<Account>('POST', '/login', { email, password: senha })) }
    catch (ex) { setErro((ex as PortalError).message) } finally { setIndo(false) }
  }
  return <CascaLogin lema="Book, train and race with URACE">
    <form className="box" onSubmit={enviar} noValidate>
      <div><div className="eyebrow">Driver area</div><h1 className="h1">Sign in</h1></div>
      <p className="muted" style={{ margin: 0 }}>Manage your drivers, sizes and sessions with URACE.</p>
      <Aviso erro={erro} />
      <div className="field"><label htmlFor="p-email">Email</label>
        <input id="p-email" className="input" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required autoFocus /></div>
      <div className="field"><label htmlFor="p-pw">Password</label>
        <div className="pwwrap">
          <input id="p-pw" className="input" type={ver ? 'text' : 'password'} autoComplete="current-password" value={senha} onChange={e => setSenha(e.target.value)} required />
          <button type="button" className="olho" onClick={() => setVer(v => !v)} aria-label={ver ? 'Hide password' : 'Show password'} aria-pressed={ver}>
            <Icon name={ver ? 'x' : 'eye'} size={17} /></button>
        </div></div>
      <button className="btn primary block" disabled={indo || !email || !senha}>{indo ? <span className="spin" /> : 'Sign in'}</button>
      <p className="small" style={{ margin: 0 }}>New to URACE? <Link to="/portal/signup">Create an account</Link></p>
    </form>
  </CascaLogin>
}

/* Telefone com código do país, e endereço que muda de formato com o país. */
function Endereco<T extends { country: string; phone_country: string; phone: string; address_line1: string; address_line2: string;
  city: string; state: string; zip: string }>({ f, set }: { f: T; set: (x: T) => void }) {
  const eua = f.country === 'US'
  const m = (k: keyof T) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => set({ ...f, [k]: e.target.value })
  return <>
    <Campo rotulo="Country" obrigatorio><select autoComplete="country" value={f.country}
      onChange={e => set({ ...f, country: e.target.value, phone_country: ddiDe(e.target.value) })}>
      {PAISES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</select></Campo>
    <div className="portal-tel">
      <Campo rotulo="Code"><input aria-label="Country calling code" autoComplete="tel-country-code" value={f.phone_country} onChange={m('phone_country')} maxLength={5} /></Campo>
      <Campo rotulo="Phone" obrigatorio><input type="tel" autoComplete="tel-national" value={f.phone} onChange={m('phone')} placeholder={eua ? '(407) 555-0100' : ''} /></Campo>
    </div>
    <Campo rotulo="Street address" obrigatorio><input autoComplete="address-line1" value={f.address_line1} onChange={m('address_line1')} /></Campo>
    <Campo rotulo="Apt, suite" dica="optional"><input autoComplete="address-line2" value={f.address_line2} onChange={m('address_line2')} /></Campo>
    <div className="portal-3">
      <Campo rotulo="City" obrigatorio><input autoComplete="address-level2" value={f.city} onChange={m('city')} /></Campo>
      <Campo rotulo={eua ? 'State' : 'State / region'} obrigatorio={eua} dica={eua ? undefined : 'optional'}>
        <input autoComplete="address-level1" value={f.state} onChange={m('state')} maxLength={eua ? 2 : 30} placeholder={eua ? 'FL' : ''} /></Campo>
      <Campo rotulo={eua ? 'ZIP' : 'Postal code'} obrigatorio={eua} dica={eua ? undefined : 'optional'}>
        <input autoComplete="postal-code" inputMode={eua ? 'numeric' : 'text'} value={f.zip} onChange={m('zip')} maxLength={eua ? 10 : 12} /></Campo>
    </div>
  </>
}

function Cadastro({ onEntrou }: { onEntrou: (a: Account) => void }) {
  const [f, setF] = useState({ name: '', email: '', password: '', birth_date: '', country: 'US', phone_country: '+1', phone: '',
    address_line1: '', address_line2: '', city: '', state: '', zip: '', accept_terms: false, i_am_driver: false })
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  const muda = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF(x => ({ ...x, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  async function enviar(e: FormEvent) {
    e.preventDefault(); setErro(null); setIndo(true)
    try { onEntrou(await papi<Account>('POST', '/signup', f)) }
    catch (ex) { setErro((ex as PortalError).message); window.scrollTo({ top: 0, behavior: 'smooth' }) } finally { setIndo(false) }
  }
  return <CascaLogin lema="Your driver profile, sizes and sessions in one place">
    <form className="box portal-cadastro" onSubmit={enviar} noValidate>
      <div><div className="eyebrow">Driver area</div><h1 className="h1">Create your account</h1></div>
      <p className="muted" style={{ margin: 0 }}>The <b>account holder</b> is the adult responsible for the account (<b>18 or older</b>): the parent or guardian, or the driver themselves if they are an adult. The <b>driver</b> is the person who will drive the kart. You add drivers next.</p>
      <Aviso erro={erro} />
      <h2 className="h2">Account holder</h2>
      <Campo rotulo="Full name" dica="the parent, guardian or adult driver" obrigatorio><input autoComplete="name" value={f.name} onChange={muda('name')} required /></Campo>
      <Campo rotulo="Date of birth" obrigatorio><input type="date" autoComplete="bday" value={f.birth_date} onChange={muda('birth_date')} required /></Campo>
      <Campo rotulo="Email" obrigatorio><input type="email" autoComplete="email" value={f.email} onChange={muda('email')} required /></Campo>
      <Campo rotulo="Password" dica="at least 8 characters" obrigatorio><input type="password" autoComplete="new-password" value={f.password} onChange={muda('password')} required minLength={8} /></Campo>
      <h2 className="h2">Contact and address</h2>
      <Endereco f={f} set={setF} />
      <label className="check"><input type="checkbox" checked={f.i_am_driver} onChange={muda('i_am_driver')} /> I am also a driver (I will drive the kart myself)</label>
      <label className="check"><input type="checkbox" checked={f.accept_terms} onChange={muda('accept_terms')} /> I accept the <a href="/legal/eula.html" target="_blank" rel="noreferrer">terms</a> and the <a href="/legal/privacy.html" target="_blank" rel="noreferrer">privacy policy</a></label>
      <button className="btn primary block" disabled={indo}>{indo ? 'Creating…' : 'Create account'}</button>
      <p className="small" style={{ margin: 0 }}>Already have an account? <Link to="/portal">Sign in</Link></p>
    </form>
  </CascaLogin>
}

/* ------------------------------------------------------------ dentro da conta */
function Casca({ conta, sair, children }: { conta: Account; sair: () => void; children: ReactNode }) {
  const [tresD, setTresD] = useState(visual3d)
  return <div className={`portal${tresD ? ' p3d' : ''}`}>
    <header className="portal-top">
      <Link to="/portal/dashboard" className="portal-marca"><span className="mark-u" aria-hidden="true">U</span><b>URACE</b><span>Driver area</span></Link>
      <span className="grow" />
      <span className="small muted portal-quem">{conta.name}</span><button className="btn ghost sm" onClick={sair}>Sign out</button>
    </header>
    <div className="portal-corpo">
      <nav className="portal-nav" aria-label="Driver area">
        {MENU.map(([r, rot, curto, ic]) => <NavLink key={r} to={`/portal/${r}`} aria-label={rot} className={({ isActive }) => isActive ? 'on' : ''}>
          <Icon name={ic} size={19} /><span className="longo">{rot}</span><span className="curto" aria-hidden="true">{curto}</span></NavLink>)}
      </nav>
      <main className="portal-main">{children}</main>
    </div>
    <footer className="portal-rodape small muted">URACE.US INC · Orlando, FL · <a href="https://urace.us/">urace.us</a> · <Visual tresD={tresD} mudar={setTresD} /></footer>
  </div>
}

function ChipMedidas({ p }: { p: Driver }) {
  const [rot, tom] = SITUACAO[p.measures_status]
  return <span className={`chip ${tom}`}>{rot}{p.measures_status === 'aviso' && p.measures_days != null ? ` · ${p.measures_days} days` : ''}</span>
}

function Dashboard({ conta }: { conta: Account }) {
  const [d, setD] = useState<Painel | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  useEffect(() => { papi<Painel>('GET', '/dashboard').then(setD).catch(e => setErro((e as PortalError).message)) }, [])
  const atencao = conta.drivers.filter(p => p.measures_status !== 'ok')
  return <div className="stack" style={{ gap: 18 }}>
    <div><h1 className="h1">Dashboard</h1><p className="muted" style={{ margin: '4px 0 0' }}>Hi, {conta.name.split(' ')[0]}. Here is everything about your account.</p></div>
    <Aviso erro={erro} />
    {conta.missing.length > 0 && <div className="banner warn"><span className="bi">▲</span><div className="grow">
      Complete your account: {conta.missing.map(k => ROTULO[k] || k).join(', ')}. <Link to="/portal/account">Go to Account</Link></div></div>}
    {atencao.map(p => <div key={p.id} className={`banner ${p.measures_status === 'aviso' ? 'warn' : 'crit'}`}><span className="bi">▲</span><div className="grow">
      {p.measures_status === 'faltando' ? `${p.name}: please complete the profile (${p.missing.map(k => ROTULO[k] || k).join(', ')}).`
        : p.measures_status === 'vencida' ? `${p.name}: measurements are ${d?.measures_limit_days ?? 60}+ days old. Update them to book.`
        : `${p.name}: measurements are ${p.measures_days} days old. Please review them.`} <Link to="/portal/drivers">Update</Link></div></div>)}
    <div className="portal-kpis">
      <div className="card card-b portal-kpi"><span className="small muted">Next session</span>
        {!d ? <span className="spin" /> : d.next_session ? <CartaoSessao s={d.next_session} cfg={null} /> : <><b>None booked</b><Link className="btn primary sm" to="/portal/book">Book a session</Link></>}</div>
      <div className="card card-b portal-kpi"><span className="small muted">Last session</span>
        <b className="portal-num">{d ? (d.last_session ? haDias(d.days_since_last_session) : '—') : '…'}</b>
        <span className="small muted">{d?.last_session ? dataUS(d.last_session) : 'No sessions yet'}</span></div>
      <div className="card card-b portal-kpi"><span className="small muted">Upcoming</span>
        <b className="portal-num">{d ? d.upcoming : '…'}</b><Link className="small" to="/portal/sessions">My sessions</Link></div>
    </div>
    <section className="stack" aria-labelledby="dash-pil"><div className="row"><h2 className="h2 grow" id="dash-pil">Drivers</h2><Link className="btn sm" to="/portal/drivers">Manage</Link></div>
      {!conta.drivers.length ? <p className="muted small" style={{ margin: 0 }}>No drivers yet. <Link to="/portal/drivers">Add a driver</Link></p>
        : <div className="portal-grade">{conta.drivers.map(p => <article key={p.id} className="card card-b portal-piloto">
          <h3 className="h3" style={{ margin: 0 }}>{p.name}{p.is_self && <span className="small muted"> · you</span>}</h3>
          <div className="small muted">{p.age != null ? `${p.age} years old` : 'Date of birth not set'}</div>
          <div className="small">Last session: <b>{p.last_session ? haDias(p.days_since_last_session) : 'none yet'}</b></div>
          <ChipMedidas p={p} />
        </article>)}</div>}
    </section>
    <section className="stack" aria-labelledby="dash-conta"><h2 className="h2" id="dash-conta">Account holder</h2>
      <div className="card card-b small"><b>{conta.name}</b><div className="muted">{conta.email}{conta.phone ? ` · ${conta.phone}` : ''}</div>
        <div className="muted">{[conta.address_line1, conta.city, conta.state, conta.zip].filter(Boolean).join(', ')}</div>
        <div className="muted">{conta.linked ? 'Connected to your URACE records' : 'Our team will connect this account to your URACE records'}</div></div>
    </section>
  </div>
}

function DadosDoResponsavel({ conta, onSalvo }: { conta: Account; onSalvo: (a: Account) => void }) {
  const [f, setF] = useState({ name: conta.name, birth_date: conta.birth_date, country: conta.country || 'US', phone_country: conta.phone_country || '+1',
    phone: conta.phone || '', address_line1: conta.address_line1 || '', address_line2: conta.address_line2 || '', city: conta.city || '',
    state: conta.state || '', zip: conta.zip || '' })
  const [erro, setErro] = useState<string | null>(null)
  const [ok, setOk] = useState(false)
  const set = (x: typeof f) => { setOk(false); setF(x) }
  async function salvar(e: FormEvent) {
    e.preventDefault(); setErro(null)
    try { onSalvo(await papi<Account>('PATCH', '/me', f)); setOk(true) } catch (ex) { setErro((ex as PortalError).message) }
  }
  return <form className="card card-b stack" onSubmit={salvar} noValidate aria-labelledby="conta-resp">
    <h2 className="h2" id="conta-resp">Account holder</h2>
    <Aviso erro={erro} />
    {ok && <div className="banner ok" role="status"><span className="bi">✓</span><div className="grow">Saved.</div></div>}
    <Campo rotulo="Full name" obrigatorio><input value={f.name} onChange={e => set({ ...f, name: e.target.value })} /></Campo>
    <Campo rotulo="Date of birth" obrigatorio><input type="date" value={f.birth_date} onChange={e => set({ ...f, birth_date: e.target.value })} /></Campo>
    <Campo rotulo="Email" dica="to change it, contact us"><input value={conta.email} disabled /></Campo>
    <Endereco f={f} set={set} />
    <div><button className="btn primary">Save</button></div>
  </form>
}

function TrocarSenha() {
  const [f, setF] = useState({ current_password: '', new_password: '' })
  const [erro, setErro] = useState<string | null>(null)
  const [ok, setOk] = useState(false)
  async function salvar(e: FormEvent) {
    e.preventDefault(); setErro(null); setOk(false)
    try { await papi('POST', '/me/password', f); setOk(true); setF({ current_password: '', new_password: '' }) } catch (ex) { setErro((ex as PortalError).message) }
  }
  return <form className="card card-b stack" onSubmit={salvar} noValidate aria-labelledby="conta-senha">
    <h2 className="h2" id="conta-senha">Password</h2>
    <Aviso erro={erro} />
    {ok && <div className="banner ok" role="status"><span className="bi">✓</span><div className="grow">Password changed. Other devices were signed out.</div></div>}
    <div className="portal-2">
      <Campo rotulo="Current password"><input type="password" autoComplete="current-password" value={f.current_password} onChange={e => setF({ ...f, current_password: e.target.value })} /></Campo>
      <Campo rotulo="New password" dica="at least 8 characters"><input type="password" autoComplete="new-password" value={f.new_password} onChange={e => setF({ ...f, new_password: e.target.value })} /></Campo>
    </div>
    <div><button className="btn" disabled={!f.current_password || !f.new_password}>Change password</button></div>
  </form>
}

function Conta({ conta, setConta }: { conta: Account; setConta: (a: Account) => void }) {
  return <div className="stack" style={{ gap: 18 }}>
    <div><h1 className="h1">Account</h1><p className="muted" style={{ margin: '4px 0 0' }}>The account holder is the adult responsible for the drivers.</p></div>
    <DadosDoResponsavel conta={conta} onSalvo={setConta} />
    <TrocarSenha />
  </div>
}

function FormPiloto({ piloto, onSalvo, onFechar }: { piloto?: Driver; onSalvo: (a: Account) => void; onFechar: () => void }) {
  const [f, setF] = useState({ name: piloto?.name || '', birth_date: piloto?.birth_date || '', email: piloto?.email || '',
    phone: piloto?.phone || '', notes: piloto?.notes || '', social: piloto?.social || '' })
  const [m, setM] = useState<Record<string, string>>(Object.fromEntries(MEDIDAS.map(([k]) => [k, piloto?.measures?.[k] != null ? String(piloto.measures[k]) : ''])))
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  async function salvar(e: FormEvent) {
    e.preventDefault(); setErro(null); setIndo(true)
    const corpo = { ...f, birth_date: f.birth_date || null, measures: Object.fromEntries(Object.entries(m).filter(([, v]) => v.trim())) }
    try { onSalvo(await papi<Account>(piloto ? 'PATCH' : 'POST', piloto ? `/drivers/${piloto.id}` : '/drivers', corpo)); onFechar() }
    catch (ex) { setErro((ex as PortalError).message) } finally { setIndo(false) }
  }
  return <form className="card card-b stack portal-piloto-form" onSubmit={salvar} noValidate>
    <h2 className="h3">{piloto ? `Edit ${piloto.name}` : 'Add a driver'}</h2>
    <Aviso erro={erro} />
    <div className="portal-2">
      <Campo rotulo="Driver's full name" dica="the person who will drive the kart" obrigatorio><input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required /></Campo>
      <Campo rotulo="Date of birth" obrigatorio><input type="date" value={f.birth_date} onChange={e => setF({ ...f, birth_date: e.target.value })} required /></Campo>
    </div>
    <div className="portal-2">
      <Campo rotulo="Email" dica="optional"><input type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></Campo>
      <Campo rotulo="Phone" dica="optional"><input type="tel" value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} /></Campo>
    </div>
    <Campo rotulo="Social media" dica="optional — profile link or @username"><input value={f.social} onChange={e => setF({ ...f, social: e.target.value })} placeholder="@driver or https://instagram.com/driver" /></Campo>
    <h3 className="h3">Measurements</h3>
    <p className="small muted" style={{ margin: 0 }}>We use them for suits, seats and kart setup. Please review them every 30 days: after 60 days the driver can't book until they are updated. Saving confirms they are correct.</p>
    <div className="portal-medidas">{MEDIDAS.filter(x => x[3]).map(([k, rot, tipo]) => <Campo key={k} rotulo={rot} obrigatorio>
      <input inputMode={tipo === 'num' ? 'decimal' : 'text'} value={m[k]} onChange={e => setM({ ...m, [k]: e.target.value })} required /></Campo>)}</div>
    <details className="portal-mais"><summary className="small">More sizes <i>(optional)</i></summary>
      <div className="portal-medidas">{MEDIDAS.filter(x => !x[3]).map(([k, rot, tipo]) => <Campo key={k} rotulo={rot}>
        <input inputMode={tipo === 'num' ? 'decimal' : 'text'} value={m[k]} onChange={e => setM({ ...m, [k]: e.target.value })} /></Campo>)}</div></details>
    <Campo rotulo="Karting experience" obrigatorio><textarea value={f.notes} onChange={e => setF({ ...f, notes: e.target.value })}
      placeholder="Please describe your karting experience: years driving, categories, tracks, races…" required maxLength={1000} /></Campo>
    <div className="row gap wrap"><button className="btn primary" disabled={indo}>{indo ? 'Saving…' : 'Save driver'}</button>
      <button type="button" className="btn ghost" onClick={onFechar}>Cancel</button></div>
  </form>
}

function Pilotos({ conta, onSalvo }: { conta: Account; onSalvo: (a: Account) => void }) {
  const [editando, setEditando] = useState<number | 'novo' | null>(conta.drivers.length ? null : 'novo')
  return <div className="stack" style={{ gap: 18 }}>
    <div className="row"><div className="grow"><h1 className="h1">Drivers</h1><p className="muted" style={{ margin: '4px 0 0' }}>The people who drive the kart: your child or children, or you. The account holder stays the responsible adult.</p></div>
      {editando === null && <button className="btn sm" onClick={() => setEditando('novo')}>+ Add a driver</button>}</div>
    {conta.drivers.map(p => editando === p.id
      ? <FormPiloto key={p.id} piloto={p} onSalvo={onSalvo} onFechar={() => setEditando(null)} />
      : <article className="card card-b portal-piloto" key={p.id}>
        <div className="row wrap"><div className="grow"><h2 className="h3" style={{ margin: 0 }}>{p.name}{p.is_self && <span className="small muted"> · you</span>}</h2>
          <div className="small muted">{p.age != null ? `${p.age} years old` : 'Date of birth not set'}{p.measures_updated_at ? ` · measured ${dataUS(p.measures_updated_at)}` : ''}
            {` · last session ${p.last_session ? haDias(p.days_since_last_session) : 'none yet'}`}</div>
          {p.social && <div className="small">{p.social.startsWith('http') ? <a href={p.social} target="_blank" rel="noreferrer noopener">{p.social}</a> : p.social}</div>}</div>
          <ChipMedidas p={p} />
          <button className="btn ghost sm" onClick={() => setEditando(p.id)}>{p.measures_status === 'ok' ? 'Edit' : 'Update'}</button></div>
        {p.missing.length > 0 && <p className="small" style={{ margin: '8px 0 0' }}>Missing: {p.missing.map(k => ROTULO[k] || k).join(', ')}.</p>}
        {Object.keys(p.measures).length > 0 && <dl className="portal-dl">{MEDIDAS.filter(([k]) => p.measures[k] != null).map(([k, rot]) =>
          <div key={k}><dt>{rot}</dt><dd>{String(p.measures[k])}</dd></div>)}</dl>}
        {p.notes && <p className="small" style={{ margin: '10px 0 0' }}><b>Experience:</b> {p.notes}</p>}
      </article>)}
    {editando === 'novo' && <FormPiloto onSalvo={onSalvo} onFechar={() => setEditando(null)} />}
  </div>
}

/* Histórico de serviços (#42): só aparece depois que a equipe liga a conta ao cliente do
 * site interno — antes disso, a conta de outra pessoa com o mesmo telefone veria o histórico errado. */
function Historico() {
  const [h, setH] = useState<{ linked: boolean; services: { date: string; service: string; status: string }[] } | null>(null)
  useEffect(() => { papi<typeof h>('GET', '/history').then(setH).catch(() => setH({ linked: false, services: [] })) }, [])
  return <div className="stack" style={{ gap: 18 }}>
    <div><h1 className="h1">Service history</h1><p className="muted" style={{ margin: '4px 0 0' }}>Every session and service with URACE.</p></div>
    {!h ? <div className="state"><span className="spin" /></div>
      : !h.linked ? <p className="muted small" style={{ margin: 0 }}>Your history with URACE will show here once our team connects your account to your records.</p>
      : !h.services.length ? <p className="muted small" style={{ margin: 0 }}>No services yet.</p>
      : <div className="card"><div className="tbl">{h.services.map((x, i) => <div className="tr" key={i}>
        <span style={{ width: 92 }} className="small">{dataUS(x.date)}</span><span className="grow">{x.service}</span>
        <span className={`chip ${x.status === 'done' ? 'ok' : 'neutral'}`}>{x.status === 'done' ? 'Done' : 'Scheduled'}</span></div>)}</div></div>}
  </div>
}

/* ------------------------------------------------------------ app */
export function PortalApp() {
  const [conta, setConta] = useState<Estado>(undefined)
  const nav = useNavigate()
  const carregar = useCallback(() => papi<Account>('GET', '/me').then(setConta).catch(() => setConta(null)), [])
  useEffect(() => { carregar() }, [carregar])
  const entrou = (a: Account) => { setConta(a); nav('/portal/dashboard', { replace: true }) }
  async function sair() { try { await papi('POST', '/logout') } finally { setConta(null); nav('/portal', { replace: true }) } }

  if (conta === undefined) return <div className="portal"><div className="state" style={{ minHeight: '60vh' }}><span className="spin" /></div></div>
  if (!conta) return <Routes>
    <Route index element={<Entrar onEntrou={entrou} />} />
    <Route path="signup" element={<Cadastro onEntrou={entrou} />} />
    <Route path="*" element={<Navigate to="/portal" replace />} />
  </Routes>
  return <Casca conta={conta} sair={sair}>
    <Routes>
      <Route index element={<Navigate to="/portal/dashboard" replace />} />
      <Route path="signup" element={<Navigate to="/portal/dashboard" replace />} />
      <Route path="dashboard" element={<Dashboard conta={conta} />} />
      <Route path="book" element={<Agendar conta={conta} />} />
      <Route path="sessions" element={<Sessoes />} />
      <Route path="drivers" element={<Pilotos conta={conta} onSalvo={setConta} />} />
      <Route path="history" element={<Historico />} />
      <Route path="account" element={<Conta conta={conta} setConta={setConta} />} />
      <Route path="*" element={<Navigate to="/portal/dashboard" replace />} />
    </Routes>
  </Casca>
}
