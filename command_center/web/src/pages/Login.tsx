/* Login (redesenho aprovado pelo dono em 17/09 — opção B do canvas).
 *
 * Duas metades: a foto da pista à esquerda, cortada na diagonal com a linha vermelha,
 * e o formulário à direita. Preto, branco, vermelho e azul — sem verde, sem teal.
 * A foto real entra em `web/public/pista.jpg`, em preto e branco e com degradê nas beiradas.
 * Enquanto o arquivo não estiver lá, fica um fundo escuro de asfalto — sem desenho nenhum.
 */
import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { destinoOAuth } from '../auth/oauthNext'
import { Banner } from '../components/ui'
import { Icon } from '../components/Icon'
import { Pista } from '../components/Pista'
import { tr } from '../i18n'
import { Bandeiras } from '../i18n/Bandeiras'

export function Login() {
  const { user, ready, login } = useAuth()
  const nav = useNavigate()
  const loc = useLocation() as { state?: { from?: string }; search: string }
  const oauth = destinoOAuth(loc.search)
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [remember, setRemember] = useState(false)
  const [show, setShow] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Já logado e vindo da autorização do conector: volta para ela. É navegação de página
  // inteira porque /ops/oauth/authorize é do servidor, não deste app — e, saindo daqui,
  // é navegação do próprio site, então o cookie de sessão vai junto.
  useEffect(() => { if (ready && user && oauth) window.location.replace(oauth) }, [ready, user, oauth])
  if (ready && user) return oauth ? <div className="login" /> : <Navigate to={loc.state?.from || '/'} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setErr(null); setBusy(true)
    try {
      await login(email.trim(), pw, remember)
      if (oauth) { window.location.assign(oauth); return }
      nav(loc.state?.from || '/', { replace: true })
    }
    catch (ex) {
      const a = ex as ApiError
      setErr(a instanceof ApiError ? (a.offline ? tr("Sem conexão com o servidor.") : a.message) : tr("Falha ao entrar."))
    } finally { setBusy(false) }
  }

  return <div className="login">
    <div className="art">
      <Pista />
      <div className="mark"><span className="mark-u" aria-hidden="true">{tr("U")}</span><b>{tr("URACE")}</b><span>{tr("Command Center")}</span></div>
      <h1>{tr("A operação inteira")}<br />{tr("no mesmo lugar")}</h1>
    </div>
    <i className="corte" aria-hidden="true" />
    <Bandeiras />
    <div className="form">
      <form className="box" onSubmit={submit} noValidate>
        <div>
          <div className="eyebrow">{tr("Acesso restrito")}</div>
          <div className="h1">{tr("Entrar")}</div>
        </div>
        {err && <Banner tone="crit">{err}</Banner>}
        <div className="field"><label htmlFor="email">{tr("E-mail")}</label>
          <input id="email" className="input" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required autoFocus aria-invalid={!!err} /></div>
        <div className="field"><label htmlFor="pw">{tr("Senha")}</label>
          <div className="pwwrap">
            <input id="pw" className="input" type={show ? 'text' : 'password'} autoComplete="current-password" value={pw} onChange={e => setPw(e.target.value)} required aria-invalid={!!err} />
            <button type="button" className="olho" onClick={() => setShow(s => !s)} aria-label={show ? tr("Esconder a senha") : tr("Mostrar a senha")} aria-pressed={show} title={show ? tr("Esconder") : tr("Mostrar")}>
              <Icon name={show ? 'x' : 'eye'} size={17} />
            </button>
          </div></div>
        <label className="check"><input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} /> {tr("Manter conectado por 30 dias")}</label>
        <button className="btn primary block" disabled={busy || !email || !pw}>{busy ? <span className="spin" /> : tr("Entrar")}</button>
        {/* #74: no app, a equipe entra pelo "U" da área do cliente; daqui se volta para ela */}
        <a className="small muted" href="/ops/portal" style={{ textAlign: 'center', padding: '10px 0' }}>{tr("Área do cliente")}</a>
      </form>
    </div>
  </div>
}
