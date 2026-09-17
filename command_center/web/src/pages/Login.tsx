/* Login (redesenho aprovado pelo dono em 17/09 — opção B do canvas).
 *
 * Duas metades: a foto da pista à esquerda, cortada na diagonal com a linha vermelha,
 * e o formulário à direita. Preto, branco, vermelho e azul — sem verde, sem teal.
 * A foto real entra em `web/public/pista.jpg`; enquanto não estiver lá, o desenho em
 * preto e branco ocupa o lugar (nada quebra, nada fica em branco).
 */
import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Banner } from '../components/ui'
import { Icon } from '../components/Icon'

/** O lado da pista: a foto quando existe; o desenho quando ainda não foi colocada. */
function Pista() {
  const [semFoto, setSemFoto] = useState(false)
  return <div className="pista" aria-hidden="true">
    {!semFoto && <img className="foto-pista" src={`${import.meta.env.BASE_URL}pista.jpg`} alt="" onError={() => setSemFoto(true)} />}
    {semFoto && <div className="tk">
      <i className="ceu" /><i className="muro" /><i className="box" /><i className="def" /><i className="grama" /><i className="asf" /><i className="sombra" />
      <svg className="kart" viewBox="0 0 200 120" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round">
        <path d="M38 88h124M46 88c0-10 8-18 18-18h72c10 0 18 8 18 18" />
        <rect x="28" y="72" width="22" height="30" rx="6" /><rect x="150" y="72" width="22" height="30" rx="6" />
        <path d="M80 70V52a20 20 0 0 1 40 0v18" /><circle cx="100" cy="40" r="15" /><path d="M86 38h28" />
      </svg>
    </div>}
    <i className="veu" /><i className="brasa" /><i className="grao" />
  </div>
}

export function Login() {
  const { user, ready, login } = useAuth()
  const nav = useNavigate()
  const loc = useLocation() as { state?: { from?: string } }
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [remember, setRemember] = useState(false)
  const [show, setShow] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (ready && user) return <Navigate to={loc.state?.from || '/'} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setErr(null); setBusy(true)
    try { await login(email.trim(), pw, remember); nav(loc.state?.from || '/', { replace: true }) }
    catch (ex) {
      const a = ex as ApiError
      setErr(a instanceof ApiError ? (a.offline ? 'Sem conexão com o servidor.' : a.message) : 'Falha ao entrar.')
    } finally { setBusy(false) }
  }

  return <div className="login">
    <div className="art">
      <Pista />
      <div className="mark"><span className="mark-u" aria-hidden="true">U</span><b>URACE</b><span>Command Center</span></div>
      <h1>A operação inteira<br />no mesmo lugar</h1>
    </div>
    <i className="corte" aria-hidden="true" />
    <div className="form">
      <form className="box" onSubmit={submit} noValidate>
        <div>
          <div className="eyebrow">Acesso restrito</div>
          <div className="h1">Entrar</div>
        </div>
        {err && <Banner tone="crit">{err}</Banner>}
        <div className="field"><label htmlFor="email">E-mail</label>
          <input id="email" className="input" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required autoFocus aria-invalid={!!err} /></div>
        <div className="field"><label htmlFor="pw">Senha</label>
          <div className="pwwrap">
            <input id="pw" className="input" type={show ? 'text' : 'password'} autoComplete="current-password" value={pw} onChange={e => setPw(e.target.value)} required aria-invalid={!!err} />
            <button type="button" className="olho" onClick={() => setShow(s => !s)} aria-label={show ? 'Esconder a senha' : 'Mostrar a senha'} aria-pressed={show} title={show ? 'Esconder' : 'Mostrar'}>
              <Icon name={show ? 'x' : 'eye'} size={17} />
            </button>
          </div></div>
        <label className="check"><input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} /> Manter conectado por 30 dias</label>
        <button className="btn primary block" disabled={busy || !email || !pw}>{busy ? <span className="spin" /> : 'Entrar'}</button>
      </form>
    </div>
  </div>
}
