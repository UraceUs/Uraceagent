import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useGet, useOnline } from '../api/hooks'
import type { Attention, Dashboard } from '../api/types'
import { Palette } from './Palette'
import { Chip, statusTone } from './ui'
import { Icon, type IconName } from './Icon'
import { ago, initials } from './fmt'

const ROLE_PT: Record<string, string> = { ADMIN: 'Administrador', MANAGER: 'Gerente', OPERATOR: 'Operador', CLOSER: 'Vendas', VIEWER: 'Leitura' }
/** Conta de acesso livre não tem cargo (dono, 17/09) — o painel diz só que ela alcança tudo. */
const cargoDe = (u?: { role?: string; free?: boolean } | null) =>
  u?.free ? 'Acesso livre' : (ROLE_PT[u?.role || ''] || u?.role || '')

/** Item do menu com ícone de traço à esquerda (padrão SF Symbols). */
function NL({ to, end, icon, children }: { to: string; end?: boolean; icon: IconName; children: React.ReactNode }) {
  return <NavLink to={to} end={end}><Icon name={icon} />{children}</NavLink>
}
function TB({ to, end, icon, n, children }: { to: string; end?: boolean; icon: IconName; n?: number; children: React.ReactNode }) {
  return <NavLink to={to} end={end} className="tb"><span className="tbi"><Icon name={icon} />{!!n && <i className="n">{n > 99 ? '99+' : n}</i>}</span>{children}</NavLink>
}

function useOutside(ref: React.RefObject<HTMLElement | null>, close: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) close() }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [ref, close])
}

export function Shell() {
  const { user, logout, can, livre } = useAuth()
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
  // closer só tem a área de vendas; a conta de acesso livre nunca é limitada
  const soVendas = user?.role === 'CLOSER' && !livre
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
      <div className="brand"><span className="mark-u" aria-hidden="true">U</span><div className="mark"><b>Command Center</b><small>URACE · Orlando</small></div>
        <button className="iconbtn burger" aria-label="Fechar menu" onClick={() => setSide(false)}><Icon name="x" /></button></div>
      <div className="search side-search" role="button" tabIndex={0} onClick={() => setPal(true)} onKeyDown={e => e.key === 'Enter' && setPal(true)}><Icon name="search" size={16} /><span>Buscar ou perguntar</span><kbd>⌘K</kbd></div>
      <nav className="nav" aria-label="Principal">
        {soVendas ? <>
          {/* Closer: só a área de vendas. O resto o servidor nem entrega. */}
          <div className="grp">Vendas</div>
          <NL to="/sales" end icon="target">Oportunidades</NL>
          <NL to="/sales/agenda" icon="cal">Agenda de vendas {!!(d?.sales_due || 0) && <span className="n warn">{d?.sales_due}</span>}</NL>
          <NL to="/crm/chat" icon="chat">Chat {!!d?.crm_pending && <span className="n">{d.crm_pending}</span>}</NL>
          <div className="grp">Inteligência</div>
          <NL to="/ai" end icon="spark">Falar com a IA</NL>
          <NL to="/approvals" icon="seal">Esperando você {pend > 0 && <span className="n warn">{pend}</span>}</NL>
          <NL to="/activity" icon="activity">O que a IA fez</NL>
        </> : <>
        <div className="grp">Hoje</div>
        <NL to="/" end icon="home">Hoje</NL>
        <NL to="/attention" icon="alert">Precisa de atenção {attn > 0 && <span className={`n${crit ? '' : ' warn'}`}>{attn}</span>}</NL>
        <NL to="/races" icon="flag">Corridas</NL>
        <div className="grp">Vendas</div>
        <NL to="/sales" end icon="target">Oportunidades {!!(d?.sales_due || 0) && <span className="n warn">{d?.sales_due}</span>}</NL>
        <NL to="/sales/agenda" icon="cal">Agenda de vendas</NL>
        <NL to="/crm/chat" icon="chat">Chat do Kommo {!!d?.crm_pending && <span className="n">{d.crm_pending}</span>}</NL>
        <div className="grp">Pessoas</div>
        <NL to="/clients" icon="people">Clientes</NL>
        <NL to="/crm/funil" icon="funnel">Funil do Kommo</NL>
        <div className="grp">Sistemas</div>
        <NL to="/asana" icon="list">Asana</NL>
        <NL to="/docusign" icon="doc">DocuSign {!!d?.waivers_bounced && <span className="n">{d.waivers_bounced}</span>}</NL>
        <NL to="/gmail" icon="mail">Gmail {!!d?.emails_attention && <span className="n soft">{d.emails_attention}</span>}</NL>
        <NavLink to="/gmail/manual" className="sub">Manual dos marcadores</NavLink>
        <NL to="/quickbooks" icon="dollar">QuickBooks</NL>
        <div className="grp">Inteligência</div>
        <NL to="/ai" end icon="spark">AI Command</NL>
        <NL to="/approvals" icon="seal">Aprovações {pend > 0 && <span className="n warn">{pend}</span>}</NL>
        <NL to="/automation" icon="gear">Automação e memória</NL>
        <NL to="/ai/capabilities" icon="book">O que a IA pode fazer</NL>
        <NL to="/activity" icon="activity">Atividade da IA</NL>
        <div className="grp">Administração</div>
        <NL to="/integrations" icon="plug">Integrações {badInt > 0 && <span className="n warn">{badInt}</span>}</NL>
        {can('MANAGER') && <NL to="/audit" icon="shield">Auditoria</NL>}
        {can('ADMIN') && <NL to="/policies" icon="key">Políticas da IA</NL>}
        {can('ADMIN') && <NL to="/users" icon="user">Usuários</NL>}
        </>}
      </nav>
      <div className="foot"><span className="avatar">{initials(user?.name)}</span><div className="grow"><div className="truncate" style={{ fontWeight: 600, fontSize: 13 }}>{user?.name}</div><div className="small muted">{cargoDe(user)}</div></div></div>
    </aside>
    <div className="main">
      <div className="topbar">
      <header className="top">
        <button className="iconbtn burger" aria-label="Menu" onClick={() => setSide(s => !s)}><Icon name="menu" /></button>
        <div className="search top-search" role="button" tabIndex={0} onClick={() => setPal(true)} onKeyDown={e => e.key === 'Enter' && setPal(true)}>
          <Icon name="search" size={16} /><span>Buscar ou perguntar à IA…</span><kbd>⌘K</kbd>
        </div>
        {/* Race control: o estado da operação em cápsulas, em toda tela. Cada item leva para onde se resolve. */}
        {!soVendas && <div className="rc" aria-label="Estado da operação">
          <button className={`it ${syncTone}`} title={lastSync ? `última sincronia: ${new Date(lastSync).toLocaleString('pt-BR')}` : 'nenhuma sincronia'} onClick={() => nav('/')}><span className="k">Espelho</span><b>{lastSync ? `há ${ago(lastSync)}` : 'nunca'}</b></button>
          <button className={`it ${badInt ? 'warn' : 'ok'}`} title={badInt ? bad.map(b => `${b.system}: ${b.status.toLowerCase()}`).join(' · ') : 'todas respondendo'} onClick={() => nav('/integrations')}><span className="k">Sistemas</span><b>{nInt ? `${nInt - badInt}/${nInt}` : '—'}{badInt > 0 && badInt <= 2 && ` · ${bad.map(b => b.system).join(', ')}`}{badInt > 2 && ` · ${badInt} com problema`}</b></button>
          <button className={`it ${crit ? 'crit' : alerts.length ? 'warn' : 'ok'}`} onClick={() => nav('/attention')}><span className="k">Atenção</span><b>{attn ? `${attn} item(ns)` : 'em ordem'}{crit > 0 && ` · ${crit} crítico(s)`}</b></button>
          <button className={`it ${pend ? 'warn' : ''}`} onClick={() => nav(pend ? '/approvals' : '/ai')}><span className="k">IA</span><b>{pend ? `${pend} esperando você` : 'nada pendente'}</b></button>
        </div>}
        <div className="grow" />
        <span className="clock mono small muted" title="hora local">{clock.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' })} · {clock.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span>
        {!online && <Chip tone="crit" dot>Offline</Chip>}
        {online && dash.error?.offline && <Chip tone="warn" dot>Servidor fora</Chip>}
        <div ref={menuRef} style={{ position: 'relative', display: 'flex', gap: 4 }}>
          <button className="who" onClick={() => setMenu(m => m === 'who' ? 'none' : 'who')} aria-haspopup="menu">
            <span className="avatar">{initials(user?.name)}</span><span className="small ink2">{user?.name?.split(' ')[0]}</span>
          </button>
          {menu === 'who' && <div className="menu" role="menu">
            <div className="mh">{user?.email}<br /><Chip tone={livre ? 'accent' : statusTone('ACTIVE')}>{cargoDe(user)}</Chip></div>
            <hr />
            <button className="mi" onClick={() => nav('/account')}>Minha conta e senha</button>
            <button className="mi" onClick={() => { const r = document.documentElement; r.dataset.theme = r.dataset.theme === 'light' ? 'dark' : 'light'; try { localStorage.setItem('cc.theme', r.dataset.theme) } catch { /* ignore */ } }}>Alternar tema</button>
            <hr />
            <button className="mi" onClick={() => { nav('/login', { replace: true, state: null }); logout() }}>Sair</button>
          </div>}
        </div>
      </header>
      </div>
      <main className="page"><div key={loc.pathname} className="page-in stack" style={{ gap: 18 }}><Outlet context={{ dash }} /></div></main>
    </div>
    <nav className="tabbar" aria-label="Abas">
      {soVendas ? <>
        <TB to="/sales" end icon="target">Vendas</TB>
        <TB to="/sales/agenda" icon="cal" n={d?.sales_due || 0}>Agenda</TB>
        <TB to="/crm/chat" icon="chat" n={d?.crm_pending || 0}>Chat</TB>
        <TB to="/ai" icon="spark">IA</TB>
      </> : <>
        <TB to="/" end icon="home">Hoje</TB>
        <TB to="/attention" icon="alert" n={attn}>Atenção</TB>
        <TB to="/sales" icon="target" n={d?.sales_due || 0}>Vendas</TB>
        <TB to="/ai" icon="spark" n={pend}>IA</TB>
      </>}
      <button className={`tb${side ? ' active' : ''}`} onClick={() => setSide(s => !s)} aria-label="Mais"><Icon name="more" />Mais</button>
    </nav>
    <Palette open={pal} onClose={() => setPal(false)} ask={ask} />
  </div>
}
