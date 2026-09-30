/* Área do cliente (#40) — hoje em /ops/portal (site interno, para testar); depois no site
 * público. Em inglês: é o idioma do site público (urace.us, en-US). Fora do Shell e da
 * sessão da equipe: tem a própria conta, o próprio login e o próprio cabeçalho. */
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { Agendar } from './Agendar'
import { papi, PortalError, type Account, type Driver } from './api'

type Estado = Account | null | undefined           // undefined = carregando; null = sem sessão

const MEDIDAS: [string, string, 'num' | 'txt'][] = [
  ['height_in', 'Height (in)', 'num'], ['weight_lb', 'Weight (lb)', 'num'], ['chest_in', 'Chest (in)', 'num'],
  ['waist_in', 'Waist (in)', 'num'], ['hips_in', 'Hips (in)', 'num'], ['inseam_in', 'Inseam (in)', 'num'],
  ['sleeve_in', 'Sleeve (in)', 'num'], ['suit_size', 'Suit size', 'txt'], ['helmet_size', 'Helmet size', 'txt'],
  ['glove_size', 'Glove size', 'txt'], ['shoe_size', 'Shoe size (US)', 'txt'],
]
const dataUS = (iso: string | null) => iso ? new Date(iso.length === 10 ? iso + 'T12:00:00' : iso)
  .toLocaleDateString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric' }) : '—'

function Casca({ conta, sair, children }: { conta?: Account | null; sair?: () => void; children: ReactNode }) {
  return <div className="portal">
    <header className="portal-top">
      <Link to="/portal" className="portal-marca"><span className="mark-u" aria-hidden="true">U</span><b>URACE</b><span>Driver area</span></Link>
      <span className="grow" />
      {conta && <><span className="small muted portal-quem">{conta.name}</span><button className="btn ghost sm" onClick={sair}>Sign out</button></>}
    </header>
    <main className="portal-main">{children}</main>
    <footer className="portal-rodape small muted">URACE.US INC · Orlando, FL · <a href="https://urace.us/">urace.us</a></footer>
  </div>
}

function Aviso({ erro }: { erro: string | null }) {
  return erro ? <div className="banner crit" role="alert"><span className="bi" aria-hidden="true">✕</span><div className="grow">{erro}</div></div> : null
}

function Campo({ rotulo, children, dica }: { rotulo: string; children: ReactNode; dica?: string }) {
  return <label className="fld"><span>{rotulo}{dica && <i> · {dica}</i>}</span>{children}</label>
}

/* ------------------------------------------------------------ entrar */
function Entrar({ onEntrou }: { onEntrou: (a: Account) => void }) {
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  async function enviar(e: FormEvent) {
    e.preventDefault(); setErro(null); setIndo(true)
    try { onEntrou(await papi<Account>('POST', '/login', { email, password: senha })) }
    catch (ex) { setErro((ex as PortalError).message) } finally { setIndo(false) }
  }
  return <form className="card card-b portal-caixa stack" onSubmit={enviar} noValidate>
    <h1 className="h1">Sign in</h1>
    <p className="muted" style={{ margin: 0 }}>Manage your drivers, sizes and sessions with URACE.</p>
    <Aviso erro={erro} />
    <Campo rotulo="Email"><input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required autoFocus /></Campo>
    <Campo rotulo="Password"><input type="password" autoComplete="current-password" value={senha} onChange={e => setSenha(e.target.value)} required /></Campo>
    <button className="btn primary" disabled={indo || !email || !senha}>{indo ? 'Signing in…' : 'Sign in'}</button>
    <p className="small" style={{ margin: 0 }}>New to URACE? <Link to="/portal/signup">Create an account</Link></p>
  </form>
}

/* ------------------------------------------------------------ cadastro */
function Cadastro({ onEntrou }: { onEntrou: (a: Account) => void }) {
  const [f, setF] = useState({ name: '', email: '', password: '', birth_date: '', phone: '', address_line1: '', address_line2: '',
    city: '', state: 'FL', zip: '', accept_terms: false, i_am_driver: false })
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  const muda = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF(x => ({ ...x, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  async function enviar(e: FormEvent) {
    e.preventDefault(); setErro(null); setIndo(true)
    try { onEntrou(await papi<Account>('POST', '/signup', f)) }
    catch (ex) { setErro((ex as PortalError).message); window.scrollTo({ top: 0, behavior: 'smooth' }) } finally { setIndo(false) }
  }
  return <form className="card card-b portal-caixa stack" onSubmit={enviar} noValidate>
    <h1 className="h1">Create your account</h1>
    <p className="muted" style={{ margin: 0 }}>The account holder must be <b>18 or older</b>. Parents and guardians: create the account in your name and add your young driver next.</p>
    <Aviso erro={erro} />
    <h2 className="h2">Account holder</h2>
    <Campo rotulo="Full name"><input autoComplete="name" value={f.name} onChange={muda('name')} required /></Campo>
    <div className="portal-2">
      <Campo rotulo="Date of birth"><input type="date" autoComplete="bday" value={f.birth_date} onChange={muda('birth_date')} required /></Campo>
      <Campo rotulo="Phone"><input type="tel" autoComplete="tel" value={f.phone} onChange={muda('phone')} placeholder="(407) 555-0100" /></Campo>
    </div>
    <Campo rotulo="Email"><input type="email" autoComplete="email" value={f.email} onChange={muda('email')} required /></Campo>
    <Campo rotulo="Password" dica="at least 8 characters"><input type="password" autoComplete="new-password" value={f.password} onChange={muda('password')} required minLength={8} /></Campo>
    <h2 className="h2">Address</h2>
    <Campo rotulo="Street address"><input autoComplete="address-line1" value={f.address_line1} onChange={muda('address_line1')} /></Campo>
    <Campo rotulo="Apt, suite (optional)"><input autoComplete="address-line2" value={f.address_line2} onChange={muda('address_line2')} /></Campo>
    <div className="portal-3">
      <Campo rotulo="City"><input autoComplete="address-level2" value={f.city} onChange={muda('city')} /></Campo>
      <Campo rotulo="State"><input autoComplete="address-level1" value={f.state} onChange={muda('state')} maxLength={30} /></Campo>
      <Campo rotulo="ZIP"><input autoComplete="postal-code" inputMode="numeric" value={f.zip} onChange={muda('zip')} maxLength={10} /></Campo>
    </div>
    <label className="check"><input type="checkbox" checked={f.i_am_driver} onChange={muda('i_am_driver')} /> I am also a driver</label>
    <label className="check"><input type="checkbox" checked={f.accept_terms} onChange={muda('accept_terms')} /> I accept the <a href="/legal/eula.html" target="_blank" rel="noreferrer">terms</a> and the <a href="/legal/privacy.html" target="_blank" rel="noreferrer">privacy policy</a></label>
    <button className="btn primary" disabled={indo}>{indo ? 'Creating…' : 'Create account'}</button>
    <p className="small" style={{ margin: 0 }}>Already have an account? <Link to="/portal">Sign in</Link></p>
  </form>
}

/* ------------------------------------------------------------ conta */
function DadosDoResponsavel({ conta, onSalvo }: { conta: Account; onSalvo: (a: Account) => void }) {
  const [f, setF] = useState({ name: conta.name, birth_date: conta.birth_date, phone: conta.phone || '', address_line1: conta.address_line1 || '',
    address_line2: conta.address_line2 || '', city: conta.city || '', state: conta.state || '', zip: conta.zip || '' })
  const [erro, setErro] = useState<string | null>(null)
  const [ok, setOk] = useState(false)
  const muda = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => { setOk(false); setF(x => ({ ...x, [k]: e.target.value })) }
  async function salvar(e: FormEvent) {
    e.preventDefault(); setErro(null)
    try { onSalvo(await papi<Account>('PATCH', '/me', f)); setOk(true) } catch (ex) { setErro((ex as PortalError).message) }
  }
  return <form className="card card-b stack" onSubmit={salvar} noValidate>
    <h2 className="h2">Account holder</h2>
    <Aviso erro={erro} />
    {ok && <div className="banner ok" role="status"><span className="bi">✓</span><div className="grow">Saved.</div></div>}
    <Campo rotulo="Full name"><input value={f.name} onChange={muda('name')} /></Campo>
    <div className="portal-2">
      <Campo rotulo="Date of birth"><input type="date" value={f.birth_date} onChange={muda('birth_date')} /></Campo>
      <Campo rotulo="Phone"><input type="tel" value={f.phone} onChange={muda('phone')} /></Campo>
    </div>
    <Campo rotulo="Email" dica="to change it, contact us"><input value={conta.email} disabled /></Campo>
    <Campo rotulo="Street address"><input value={f.address_line1} onChange={muda('address_line1')} /></Campo>
    <Campo rotulo="Apt, suite"><input value={f.address_line2} onChange={muda('address_line2')} /></Campo>
    <div className="portal-3">
      <Campo rotulo="City"><input value={f.city} onChange={muda('city')} /></Campo>
      <Campo rotulo="State"><input value={f.state} onChange={muda('state')} /></Campo>
      <Campo rotulo="ZIP"><input inputMode="numeric" value={f.zip} onChange={muda('zip')} /></Campo>
    </div>
    <div><button className="btn primary">Save</button></div>
  </form>
}

function FormPiloto({ piloto, onSalvo, onFechar }: { piloto?: Driver; onSalvo: (a: Account) => void; onFechar: () => void }) {
  const [f, setF] = useState({ name: piloto?.name || '', birth_date: piloto?.birth_date || '', email: piloto?.email || '',
    phone: piloto?.phone || '', notes: piloto?.notes || '' })
  const [m, setM] = useState<Record<string, string>>(Object.fromEntries(MEDIDAS.map(([k]) => [k, piloto?.measures?.[k] != null ? String(piloto.measures[k]) : ''])))
  const [erro, setErro] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  async function salvar(e: FormEvent) {
    e.preventDefault(); setErro(null); setIndo(true)
    const corpo = { ...f, measures: Object.fromEntries(Object.entries(m).filter(([, v]) => v.trim())) }
    try { onSalvo(await papi<Account>(piloto ? 'PATCH' : 'POST', piloto ? `/drivers/${piloto.id}` : '/drivers', corpo)); onFechar() }
    catch (ex) { setErro((ex as PortalError).message) } finally { setIndo(false) }
  }
  return <form className="card card-b stack portal-piloto-form" onSubmit={salvar} noValidate>
    <h3 className="h3">{piloto ? `Edit ${piloto.name}` : 'Add a driver'}</h3>
    <Aviso erro={erro} />
    <div className="portal-2">
      <Campo rotulo="Driver's name"><input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required /></Campo>
      <Campo rotulo="Date of birth"><input type="date" value={f.birth_date} onChange={e => setF({ ...f, birth_date: e.target.value })} /></Campo>
    </div>
    <div className="portal-2">
      <Campo rotulo="Email" dica="optional"><input type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></Campo>
      <Campo rotulo="Phone" dica="optional"><input type="tel" value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} /></Campo>
    </div>
    <h3 className="h3">Measurements</h3>
    <p className="small muted" style={{ margin: 0 }}>We use them for suits, seats and kart setup. Update them when your driver grows.</p>
    <div className="portal-medidas">{MEDIDAS.map(([k, rot, tipo]) => <Campo key={k} rotulo={rot}>
      <input inputMode={tipo === 'num' ? 'decimal' : 'text'} value={m[k]} onChange={e => setM({ ...m, [k]: e.target.value })} /></Campo>)}</div>
    <Campo rotulo="Notes" dica="optional"><textarea value={f.notes} onChange={e => setF({ ...f, notes: e.target.value })} /></Campo>
    <div className="row gap wrap"><button className="btn primary" disabled={indo}>{indo ? 'Saving…' : 'Save driver'}</button>
      <button type="button" className="btn ghost" onClick={onFechar}>Cancel</button></div>
  </form>
}

function Pilotos({ conta, onSalvo }: { conta: Account; onSalvo: (a: Account) => void }) {
  const [editando, setEditando] = useState<number | 'novo' | null>(conta.drivers.length ? null : 'novo')
  return <section className="stack">
    <div className="row"><h2 className="h2 grow">Drivers</h2>{editando === null && <button className="btn sm" onClick={() => setEditando('novo')}>+ Add a driver</button>}</div>
    {conta.drivers.map(p => editando === p.id
      ? <FormPiloto key={p.id} piloto={p} onSalvo={onSalvo} onFechar={() => setEditando(null)} />
      : <article className="card card-b portal-piloto" key={p.id}>
        <div className="row"><div className="grow"><h3 className="h3" style={{ margin: 0 }}>{p.name}{p.is_self && <span className="small muted"> · you</span>}</h3>
          <div className="small muted">{p.age != null ? `${p.age} years old` : 'Date of birth not set'}{p.measures_updated_at ? ` · measured ${dataUS(p.measures_updated_at)}` : ''}</div></div>
          <button className="btn ghost sm" onClick={() => setEditando(p.id)}>Edit</button></div>
        {Object.keys(p.measures).length > 0 && <dl className="portal-dl">{MEDIDAS.filter(([k]) => p.measures[k] != null).map(([k, rot]) =>
          <div key={k}><dt>{rot}</dt><dd>{String(p.measures[k])}</dd></div>)}</dl>}
      </article>)}
    {editando === 'novo' && <FormPiloto onSalvo={onSalvo} onFechar={() => setEditando(null)} />}
  </section>
}

function MinhaConta({ conta, setConta }: { conta: Account; setConta: (a: Account) => void }) {
  return <div className="stack" style={{ gap: 20 }}>
    <div><h1 className="h1">My account</h1><p className="muted" style={{ margin: '4px 0 0' }}>Hi, {conta.name.split(' ')[0]}. Book your sessions and keep your drivers and sizes up to date.</p></div>
    <Agendar conta={conta} />
    <Pilotos conta={conta} onSalvo={setConta} />
    <DadosDoResponsavel conta={conta} onSalvo={setConta} />
  </div>
}

/* ------------------------------------------------------------ app */
export function PortalApp() {
  const [conta, setConta] = useState<Estado>(undefined)
  const nav = useNavigate()
  const carregar = useCallback(() => papi<Account>('GET', '/me').then(setConta).catch(() => setConta(null)), [])
  useEffect(() => { carregar() }, [carregar])
  const entrou = (a: Account) => { setConta(a); nav('/portal/account', { replace: true }) }
  async function sair() { try { await papi('POST', '/logout') } finally { setConta(null); nav('/portal', { replace: true }) } }

  if (conta === undefined) return <Casca><div className="state" style={{ minHeight: '40vh' }}><span className="spin" /></div></Casca>
  return <Casca conta={conta} sair={sair}>
    <Routes>
      <Route index element={conta ? <Navigate to="/portal/account" replace /> : <Entrar onEntrou={entrou} />} />
      <Route path="signup" element={conta ? <Navigate to="/portal/account" replace /> : <Cadastro onEntrou={entrou} />} />
      <Route path="account" element={conta ? <MinhaConta conta={conta} setConta={setConta} /> : <Navigate to="/portal" replace />} />
      <Route path="*" element={<Navigate to="/portal" replace />} />
    </Routes>
  </Casca>
}
