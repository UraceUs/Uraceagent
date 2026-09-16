import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useGet, useOnline } from '../api/hooks'
import type { Attention, Dashboard } from '../api/types'
import { Palette } from './Palette'
import { Chip, statusTone } from './ui'
import { ago, initials } from './fmt'

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
  const [menu, setMenu] = useState<'none' | 'who'>('none')
  const [clock, setClock] = useState(() => new Date())
  useEffect(() => { const id = setInterval(() => setClock(new Date()), 30000); return () => clearInterval(id) }, [])
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
  const crit = (d?.needs_attention || []).filter(a => a.level === 'CRITICAL').length
  const pend = d?.ai_pending_approval || 0
  const attn = d?.needs_attention_total || 0
  const bad = (d?.integrations || []).filter(i => i.status !== 'CONNECTED' && i.status !== 'SYNCING')
  const badInt = bad.length
  const nInt = (d?.integrations || []).length
  const lastSync = (d?.last_sync || []).map(s => s.at).filter(Boolean).sort().pop() || null
  const syncAge = lastSync ? Date.now() - new Date(lastSync).getTime() : null
  const syncTone = syncAge === null ? 'crit' : syncAge > 2 * 3600e3 ? 'warn' : 'ok'

  return <div className="app">
    {side && <div className="scrim" onClick={() => setSide(false)} />}
    <aside className={`side${side ? ' open' : ''}`}>
      <div className="brand"><div className="mark"><b>URACE</b><span>Command Center</span></div><small>OPERATIONS · ORLANDO</small></div>
      <nav className="nav" aria-label="Principal">
        <div className="grp">Operação</div>
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/attention">Precisa de atenção {attn > 0 && <span className={`n${crit ? '' : ' warn'}`}>{attn}</span>}</NavLink>
        <NavLink to="/clients">Clientes</NavLink>
        <NavLink to="/races">Corridas</NavLink>
        <div className="grp">Sistemas</div>
        <NavLink to="/asana">Asana</NavLink>
        <NavLink to="/docusign">DocuSign {!!d?.waivers_bounced && <span className="n">{d.waivers_bounced}</span>}</NavLink>
        <NavLink to="/gmail">Gmail {!!d?.emails_attention && <span className="n soft">{d.emails_attention}</span>}</NavLink>
        <NavLink to="/gmail/manual" className="sub">Manual dos marcadores</NavLink>
        <NavLink to="/quickbooks">QuickBooks</NavLink>
        <div className="grp">CRM · Kommo</div>
        <NavLink to="/crm/chat">Chat {!!d?.crm_pending && <span className="n">{d.crm_pending}</span>}</NavLink>
        <NavLink to="/crm/funil">Funil de vendas</NavLink>
        <div className="grp">Inteligência</div>
        <NavLink to="/ai" end>AI Command</NavLink>
        <NavLink to="/approvals">Aprovações {pend > 0 && <span className="n warn">{pend}</span>}</NavLink>
        <NavLink to="/automation">Automação e memória</NavLink>
        <NavLink to="/activity">Atividade da IA</NavLink>
        <div className="grp">Administração</div>
        <NavLink to="/integrations">Integrações {badInt > 0 && <span className="n warn">{badInt}</span>}</NavLink>
        {can('MANAGER') && <NavLink to="/audit">Auditoria</NavLink>}
        {can('ADMIN') && <NavLink to="/policies">Políticas da IA</NavLink>}
        {can('ADMIN') && <NavLink to="/users">Usuários</NavLink>}
      </nav>
      <div className="foot">{user?.name}<br /><span className="mono" style={{ fontSize: 11 }}>{ROLE_PT[user?.role || ''] || user?.role}</span></div>
    </aside>
    <div className="main">
      <div className="topbar">
      <header className="top">
        <button className="iconbtn burger" aria-label="Menu" onClick={() => setSide(s => !s)}>☰</button>
        <div className="search" role="button" tabIndex={0} onClick={() => setPal(true)} onKeyDown={e => e.key === 'Enter' && setPal(true)}>
          <span>⌕</span><span>Buscar ou perguntar à IA…</span><kbd>⌘K</kbd>
        </div>
        <div className="grow" />
        {!online && <Chip tone="crit" dot>Offline</Chip>}
        {online && dash.error?.offline && <Chip tone="warn" dot>Servidor fora</Chip>}
        <div ref={menuRef} style={{ position: 'relative', display: 'flex', gap: 4 }}>
          <button className="who" onClick={() => setMenu(m => m === 'who' ? 'none' : 'who')} aria-haspopup="menu">
            <span className="avatar">{initials(user?.name)}</span><span className="small ink2">{user?.name?.split(' ')[0]}</span>
          </button>
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
      {/* Race control: o estado da operação em uma linha, em toda tela. Cada item leva para onde se resolve. */}
      <div className="rc" aria-label="Estado da operação">
        <span className={`it link ${syncTone}`} title={lastSync ? `última sincronia: ${new Date(lastSync).toLocaleString('pt-BR')}` : 'nenhuma sincronia'} onClick={() => nav('/')}><span className="k">Espelho</span><span className="g">{syncTone === 'ok' ? '✓' : syncTone === 'warn' ? '▲' : '✕'}</span>{lastSync ? `há ${ago(lastSync)}` : 'nunca'}</span>
        <span className={`it link ${badInt ? 'warn' : 'ok'}`} title={badInt ? bad.map(b => `${b.system}: ${b.status.toLowerCase()}`).join(' · ') : 'todas respondendo'} onClick={() => nav('/integrations')}><span className="k">Sistemas</span><span className="g">{badInt ? '▲' : '✓'}</span>{nInt ? `${nInt - badInt}/${nInt}` : '—'}{badInt > 0 && badInt <= 2 && ` · ${bad.map(b => b.system).join(', ')}`}{badInt > 2 && ` · ${badInt} com problema`}</span>
        <span className={`it link ${crit ? 'crit' : alerts.length ? 'warn' : 'ok'}`} onClick={() => nav('/attention')}><span className="k">Atenção</span><span className="g">{crit ? '✕' : alerts.length ? '▲' : '✓'}</span>{attn ? `${attn} item(ns)` : 'em ordem'}{crit > 0 && ` · ${crit} crítico(s)`}</span>
        <span className={`it link ${pend ? 'warn' : ''}`} onClick={() => nav(pend ? '/approvals' : '/ai')}><span className="k">IA</span><span className="g">{pend ? '○' : '✓'}</span>{pend ? `${pend} esperando você` : 'nada pendente'}</span>
        <span className="it clock" title="hora local"><span className="k">{clock.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' })}</span>{clock.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span>
      </div>
      </div>
      <main className="page"><Outlet context={{ dash }} /></main>
    </div>
    <Palette open={pal} onClose={() => setPal(false)} ask={ask} />
  </div>
}
