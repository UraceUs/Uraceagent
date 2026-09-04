import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Banner } from '../components/ui'

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
      <div className="mark"><b>URACE</b><span>Command Center</span></div>
      <div><h1>Operação, clientes e IA num só lugar.</h1>
        <p>Asana, DocuSign, Gmail e o agente administrativo, com toda ação registrada e nada executado sem aprovação humana.</p></div>
      <div className="ft">URACE.US INC · Orlando · acesso restrito</div>
    </div>
    <div className="form">
      <form className="box" onSubmit={submit} noValidate>
        <div><div className="h1">Entrar</div><div className="sub small">Use o e-mail cadastrado pelo administrador.</div></div>
        {err && <Banner tone="crit">{err}</Banner>}
        <div className="field"><label htmlFor="email">E-mail</label>
          <input id="email" className="input" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required autoFocus aria-invalid={!!err} /></div>
        <div className="field"><label htmlFor="pw">Senha</label>
          <div className="pwwrap">
            <input id="pw" className="input" type={show ? 'text' : 'password'} autoComplete="current-password" value={pw} onChange={e => setPw(e.target.value)} required aria-invalid={!!err} />
            <button type="button" className="eye" onClick={() => setShow(s => !s)} aria-label={show ? 'Esconder senha' : 'Mostrar senha'} aria-pressed={show} title={show ? 'Esconder' : 'Mostrar'}>{show ? 'Esconder' : 'Mostrar'}</button>
          </div></div>
        <label className="check"><input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} /> Manter conectado por 30 dias</label>
        <button className="btn primary block" disabled={busy || !email || !pw}>{busy ? <span className="spin" /> : 'Entrar'}</button>
        <div className="small muted">Esqueceu a senha? Peça ao administrador para redefinir.</div>
      </form>
    </div>
  </div>
}
