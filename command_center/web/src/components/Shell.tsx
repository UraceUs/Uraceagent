import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useGet, useOnline } from '../api/hooks'
import type { Attention, Dashboard } from '../api/types'
import { Palette } from './Palette'
import { Chip, levelTone, statusTone } from './ui'
import { initials } from './fmt'

const ROLE_PT: Record<string, string> = { ADMIN: 'Administrador', MANAGER: 'Gerente', OPERATOR: 'Operador', VIEWER: 'Leitura' }

function useOutside(ref: React.RefObject<HTMLElement | null>, close: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) close() }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [ref, close])
}

export function Shell() {
  const { user, logout, can } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const online = useOnline()
  const [pal, setPal] = useState(false)
  const [side, setSide] = useState(false)
  const [menu, setMenu] = useState<'none' | 'who' | 'bell'>('none')
  const menuRef = useRef<HTMLDivElement>(null)
  useOutside(menuRef, useCallback(() => setMenu('none'), []))
  // um único GET leve alimenta os contadores do menu e o sino (a cada 60 s)
  const dash = useGet<Dashboard>('/dashboard', 60000)
  useEffect(() => { setSide(false); setMenu('none') }, [loc.pathname])
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPal(p => !p) }
    }
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
  }, [])
  const ask = useCallback((text: string) => nav('/ai', { state: { ask: text } }), [nav])
  const d = dash.data
  const alerts: Attention[] = (d?.needs_attention || []).filter(a => a.level === 'CRITICAL' || a.level === 'HIGH')
  const pend = d?.ai_pending_approval || 0
  const attn = d?.needs_attention_total || 0
  const badInt = (d?.integrations || []).filter(i => i.status === 'ERROR' || i.status === 'DEGRADED').length

  return <div className="app">
    {side && <div className="scrim" onClick={() => setSide(false)} />}
    <aside className={`side${side ? ' open' : ''}`}>
      <div className="brand"><div className="mark"><b>URACE</b><span>Command Center</span></div><small>OPERATIONS · ORLANDO</small></div>
      <nav className="nav" aria-label="Principal">
        <div className="grp">Operação</div>
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/attention">Precisa de atenção {attn > 0 && <span className="n">{attn}</span>}</NavLink>
        <NavLink to="/clients">Clientes</NavLink>
        <div className="grp">Sistemas</div>
        <NavLink to="/asana">Asana</NavLink>
        <NavLink to="/docusign">DocuSign {!!d?.waivers_bounced && <span className="n">{d.waivers_bounced}</span>}</NavLink>
        <NavLink to="/gmail">Gmail {!!d?.emails_attention && <span className="n soft">{d.emails_attention}</span>}</NavLink>
        <NavLink to="/quickbooks">QuickBooks</NavLink>
        <div className="grp">Inteligência</div>
        <NavLink to="/ai" end>AI Command</NavLink>
        <NavLink to="/approvals">Aprovações {pend > 0 && <span className="n">{pend}</span>}</NavLink>
        <NavLink to="/automation">Automação e memória</NavLink>
        <NavLink to="/activity">Atividade da IA</NavLink>
        <div className="grp">Administração</div>
        <NavLink to="/integrations">Integrações {badInt > 0 && <span className="n">{badInt}</span>}</NavLink>
        {can('MANAGER') && <NavLink to="/audit">Auditoria</NavLink>}
        {can('ADMIN') && <NavLink to="/policies">Políticas da IA</NavLink>}
        {can('ADMIN') && <NavLink to="/users">Usuários</NavLink>}
      </nav>
      <div className="foot">{user?.name}<br /><span className="mono" style={{ fontSize: 11 }}>{ROLE_PT[user?.role || ''] || user?.role}</span></div>
    </aside>
    <div className="main">
      <header className="top">
        <button className="iconbtn burger" aria-label="Menu" onClick={() => setSide(s => !s)}>☰</button>
        <div className="search" role="button" tabIndex={0} onClick={() => setPal(true)} onKeyDown={e => e.key === 'Enter' && setPal(true)}>
          <span>⌕</span><span>Buscar ou perguntar à IA…</span><kbd>⌘K</kbd>
        </div>
        <div className="grow" />
        {!online && <Chip tone="crit" dot>Offline</Chip>}
        {online && dash.error?.offline && <Chip tone="warn" dot>Servidor fora</Chip>}
        <div ref={menuRef} style={{ position: 'relative', display: 'flex', gap: 4 }}>
          <button className="iconbtn" aria-label="Notificações" onClick={() => setMenu(m => m === 'bell' ? 'none' : 'bell')}>
            🔔{(alerts.length > 0 || pend > 0) && <span className="dot" />}
          </button>
          <button className="who" onClick={() => setMenu(m => m === 'who' ? 'none' : 'who')} aria-haspopup="menu">
            <span className="avatar">{initials(user?.name)}</span><span className="small ink2">{user?.name?.split(' ')[0]}</span>
          </button>
          {menu === 'bell' && <div className="pop">
            <div className="card-h"><h2 className="h2">Agora</h2><div className="grow" /><NavLink to="/attention" className="small">ver tudo</NavLink></div>
            {pend > 0 && <div className="att"><div className="lv HIGH" /><div className="grow"><div className="ti">{pend} ação(ões) da IA esperando aprovação</div><NavLink to="/approvals" className="small">Revisar</NavLink></div></div>}
            {alerts.length === 0 && pend === 0 && <div className="state"><p>Nada crítico ou alto no momento.</p></div>}
            {alerts.map((a, i) => <div className="att" key={i}><div className={`lv ${a.level}`} /><div className="grow">
              <div className="ti">{a.title}</div><div className="why">{a.why}</div>
              <div className="row" style={{ marginTop: 4 }}><Chip tone={levelTone(a.level)}>{a.level}</Chip>{a.client_id && <NavLink to={`/clients/${a.client_id}`} className="small">abrir cliente</NavLink>}</div>
            </div></div>)}
          </div>}
          {menu === 'who' && <div className="menu" role="menu">
            <div className="mh">{user?.email}<br /><Chip tone={statusTone('ACTIVE')}>{ROLE_PT[user?.role || '']}</Chip></div>
            <hr />
            <button className="mi" onClick={() => nav('/account')}>Minha conta e senha</button>
            <button className="mi" onClick={() => { const r = document.documentElement; r.dataset.theme = r.dataset.theme === 'dark' ? 'light' : 'dark'; try { localStorage.setItem('cc.theme', r.dataset.theme) } catch { /* ignore */ } }}>Alternar tema</button>
            <hr />
            <button className="mi" onClick={() => { nav('/login', { replace: true, state: null }); logout() }}>Sair</button>
          </div>}
        </div>
      </header>
      <main className="page"><Outlet context={{ dash }} /></main>
    </div>
    <Palette open={pal} onClose={() => setPal(false)} ask={ask} />
  </div>
}
