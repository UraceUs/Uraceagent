import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useGet, useOnline } from '../api/hooks'
import type { Attention, Dashboard } from '../api/types'
import { Palette } from './Palette'
import { Chip, Loading, statusTone } from './ui'
import { Icon, type IconName } from './Icon'
import { ago, initials } from './fmt'
import { tr, LOCALE } from '../i18n'
import { Bandeiras } from '../i18n/Bandeiras'

const ROLE_PT: Record<string, string> = { ADMIN: tr("Administrador"), MANAGER: tr("Gerente"), OPERATOR: tr("Operador"), VIEWER: tr("Leitura") }
/** Conta de acesso livre não tem cargo (dono, 17/09) — o painel diz só que ela alcança tudo. */
const CARGO_PT: Record<string, string> = { MECANICO: tr("Mecânico"), COACH: tr("Coach") }
const cargoDe = (u?: { role?: string; free?: boolean; cargo?: string | null } | null) =>
  u?.free ? 'Acesso livre' : u?.cargo ? CARGO_PT[u.cargo] : (ROLE_PT[u?.role || ''] || u?.role || '')

/** Item do menu com ícone de traço à esquerda (padrão SF Symbols).
 *  O rótulo vai em `.lbl` e o contador em `.n` separados: no menu em trilho (18/09) o
 *  primeiro some e o segundo vira bolinha, sem mexer no JSX de cada item. */
function NL({ to, end, icon, n, tone, children }: {
  to: string; end?: boolean; icon: IconName; n?: number; tone?: 'warn' | 'soft'; children: React.ReactNode
}) {
  const rotulo = typeof children === 'string' ? children : undefined
  return <NavLink to={to} end={end} title={rotulo}>
    <Icon name={icon} /><span className="lbl">{children}</span>
    {!!n && <span className={`n${tone ? ' ' + tone : ''}`}>{n > 99 ? '99+' : n}</span>}
  </NavLink>
}
function TB({ to, end, icon, n, children }: { to: string; end?: boolean; icon: IconName; n?: number; children: React.ReactNode }) {
  return <NavLink to={to} end={end} className="tb"><span className="tbi"><Icon name={icon} />{!!n && <i className="n">{n > 99 ? '99+' : n}</i>}</span>{children}</NavLink>
}

/** Largura da página por rota (decisão do dono, 18/09): leitura ganha limite confortável;
 *  quadro, tabela larga, calendário e chat usam a tela inteira; o resto fica no limite padrão. */
function larguraDa(p: string) {
  if (/^\/clients\/[^/]+/.test(p) || p === '/gmail/manual' || p === '/ai/capabilities' || p === '/account') return ' read'
  if (/^\/(crm|sales|asana|gmail|docusign|quickbooks|audit|activity|races|clients)$/.test(p) || p.startsWith('/crm/')) return ' wide'
  return ''
}

function useOutside(ref: React.RefObject<HTMLElement | null>, close: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) close() }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [ref, close])
}

export function Shell() {
  const { user, logout, can, livre, box } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const online = useOnline()
  const [pal, setPal] = useState(false)
  const [side, setSide] = useState(false)
  // menu em trilho no computador (opção C, aprovada em 18/09). Fica guardado por navegador.
  const [trilho, setTrilho] = useState(() => {
    try { return localStorage.getItem('cc.menu') === 'trilho' } catch { return false }
  })
  const alternaTrilho = useCallback(() => setTrilho(v => {
    const n = !v
    try { localStorage.setItem('cc.menu', n ? 'trilho' : 'aberto') } catch { /* ignore */ }
    return n
  }), [])
  const [menu, setMenu] = useState<'none' | 'who'>('none')
  const [clock, setClock] = useState(() => new Date())
  useEffect(() => { const id = setInterval(() => setClock(new Date()), 30000); return () => clearInterval(id) }, [])
  const menuRef = useRef<HTMLDivElement>(null)
  useOutside(menuRef, useCallback(() => setMenu('none'), []))
  // um único GET leve alimenta os contadores do menu e o sino (a cada 60 s)
  const dash = useGet<Dashboard>(box ? null : '/dashboard', 60000)   // o box não lê o painel geral (#92)
  useEffect(() => { setSide(false); setMenu('none') }, [loc.pathname])
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPal(p => !p) }
    }
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
  }, [])
  const ask = useCallback((text: string) => nav('/ai', { state: { ask: text } }), [nav])
  const d = dash.data
  const estoq = useGet<{ repor: unknown[] }>(can('OPERATOR') ? '/estoque' : null, 300000)
  const alerts: Attention[] = (d?.needs_attention || []).filter(a => a.level === 'CRITICAL' || a.level === 'HIGH')
  const crit = (d?.needs_attention || []).filter(a => a.level === 'CRITICAL').length
  const pend = d?.ai_pending_approval || 0
  const attn = d?.needs_attention_total || 0
  // Contador do Estoque no menu: só é buscado por quem pode ver estoque, e sem
  // atrapalhar quem não usa — falha em silêncio, porque contador não derruba menu.
  const repor = estoq.data?.repor?.length || 0
  const bad = (d?.integrations || []).filter(i => i.status !== 'CONNECTED' && i.status !== 'SYNCING')
  const badInt = bad.length
  const nInt = (d?.integrations || []).length
  const lastSync = (d?.last_sync || []).map(s => s.at).filter(Boolean).sort().pop() || null
  const syncAge = lastSync ? Date.now() - new Date(lastSync).getTime() : null
  const syncTone = syncAge === null ? 'crit' : syncAge > 2 * 3600e3 ? 'warn' : 'ok'

  return <div className={`app${trilho ? ' rail' : ''}`}>
    {side && <div className="scrim" onClick={() => setSide(false)} />}
    <aside className={`side${side ? ' open' : ''}`}>
      <div className="brand"><span className="mark-u" aria-hidden="true">{tr("U")}</span><div className="mark"><b>{tr("Command Center")}</b><small>{tr("URACE · Orlando")}</small></div>
        <button className="iconbtn burger" aria-label={tr("Fechar menu")} onClick={() => setSide(false)}><Icon name="x" /></button></div>
      {!box && <div className="search side-search" role="button" tabIndex={0} onClick={() => setPal(true)} onKeyDown={e => e.key === 'Enter' && setPal(true)}><Icon name="search" size={16} /><span>{tr("Buscar ou perguntar")}</span><kbd>{tr("⌘K")}</kbd></div>}
      {box ? <nav className="nav" aria-label={tr("Principal")}>
        {/* mecânico e coach (#92): só o que é do box */}
        <div className="grp">{tr("Meu trabalho")}</div>
        <NL to="/" end icon="home">{tr("Meu dia")}</NL>
        <NL to="/balcao" icon="tag">{tr("Balcão")}</NL>
        <NL to="/checklists" icon="check">{tr("Checklists")}</NL>
        <div className="grp">{tr("Logística")}</div>
        <NL to="/estoque" icon="box">{tr("Estoque")}</NL>
        <NL to="/pedidos" icon="list">{tr("Pedidos")}</NL>
        <div className="grp">{tr("Pessoas")}</div>
        <NL to="/clients" icon="people">{tr("Clientes")}</NL>
        <NL to="/equipe" icon="chat">{tr("Equipe")}</NL>
      </nav> : <nav className="nav" aria-label={tr("Principal")}>
        <div className="grp">{tr("Hoje")}</div>
        <NL to="/" end icon="home">{tr("Hoje")}</NL>
        <NL to="/attention" icon="alert" n={attn} tone={crit ? undefined : 'warn'}>{tr("Precisa de atenção")}</NL>
        {/* Logística (dono, 23/09). "Corridas" saiu de "Hoje" e veio para cá: o mesmo link
            em dois lugares do menu faz a pessoa se perguntar qual dos dois é o certo. */}
        <div className="grp">{tr("Logística")}</div>
        <NL to="/estoque" icon="box" n={repor} tone="warn">{tr("Estoque")}</NL>
        {can('OPERATOR') && <NL to="/balcao" icon="tag">{tr("Balcão")}</NL>}
        <NL to="/races" icon="flag">{tr("Corridas")}</NL>
        <NL to="/pedidos" icon="list">{tr("Pedidos")}</NL>
        <NL to="/compras" icon="cart">{tr("Compras")}</NL>
        <NL to="/planejamento" icon="chart">{tr("Planejamento")}</NL>
        <div className="grp">{tr("Vendas")}</div>
        <NL to="/sales" end icon="target" n={d?.sales_due || 0} tone="warn">{tr("Oportunidades")}</NL>
        <NL to="/sales/agenda" icon="cal">{tr("Agenda de vendas")}</NL>
        <NL to="/crm/chat" icon="chat" n={d?.crm_pending || 0}>{tr("Chat do Kommo")}</NL>
        {can('OPERATOR') && <NL to="/suits" icon="suit">{tr("Suits · Alpha Line")}</NL>}
        <NL to="/site" icon="globe">{tr("Site público")}</NL>
        <div className="grp">{tr("Pessoas")}</div>
        <NL to="/equipe" icon="chat" n={d?.equipe_nao_lidas || 0} tone="warn">{tr("Equipe")}</NL>
        <NL to="/clients" icon="people">{tr("Clientes")}</NL>
        {can('MANAGER') && <NL to="/biblioteca" icon="book">{tr("Biblioteca")}</NL>}
        <NL to="/crm/funil" icon="funnel">{tr("Funil do Kommo")}</NL>
        <div className="grp">{tr("Sistemas")}</div>
        <NL to="/asana" icon="list">{tr("Asana")}</NL>
        <NL to="/docusign" icon="doc" n={d?.waivers_bounced || 0}>{tr("DocuSign")}</NL>
        <NL to="/gmail" icon="mail" n={d?.emails_attention || 0} tone="soft">{tr("Gmail")}</NL>
        <NavLink to="/gmail/manual" className="sub">{tr("Manual dos marcadores")}</NavLink>
        <NL to="/quickbooks" icon="dollar">{tr("QuickBooks")}</NL>
        <div className="grp">{tr("Inteligência")}</div>
        <NL to="/ai" end icon="spark">{tr("AI Command")}</NL>
        <NL to="/approvals" icon="seal" n={pend} tone="warn">{tr("Aprovações")}</NL>
        <NL to="/automation" icon="gear">{tr("Automação e memória")}</NL>
        <NL to="/ai/capabilities" icon="book">{tr("O que a IA pode fazer")}</NL>
        <NL to="/activity" icon="activity">{tr("Atividade da IA")}</NL>
        <div className="grp">{tr("Administração")}</div>
        <NL to="/integrations" icon="plug" n={badInt} tone="warn">{tr("Integrações")}</NL>
        {can('MANAGER') && <NL to="/audit" icon="shield">{tr("Auditoria")}</NL>}
        {can('ADMIN') && <NL to="/policies" icon="key">{tr("Políticas da IA")}</NL>}
        {can('ADMIN') && <NL to="/users" icon="user">{tr("Usuários")}</NL>}
        {livre && <NL to="/cofre" icon="lock">{tr("Cofre")}</NL>}
      </nav>}
      <div className="foot"><span className="avatar">{initials(user?.name)}</span><div className="grow"><div className="truncate" style={{ fontWeight: 600, fontSize: 13 }}>{user?.name}</div><div className="small muted">{cargoDe(user)}</div></div></div>
    </aside>
    <div className="main">
      <div className="topbar">
      <header className="top">
        <button className="iconbtn burger" aria-label={tr("Menu")} onClick={() => setSide(s => !s)}><Icon name="menu" /></button>
        <button className="iconbtn railbtn" aria-label={trilho ? tr("Abrir o menu") : tr("Fechar o menu")} aria-expanded={!trilho}
          title={trilho ? tr("Abrir o menu") : tr("Fechar o menu")} onClick={alternaTrilho}><Icon name="panel" /></button>
        {!box && <div className="search top-search" role="button" tabIndex={0} onClick={() => setPal(true)} onKeyDown={e => e.key === 'Enter' && setPal(true)}>
          <Icon name="search" size={16} /><span>{tr("Buscar ou perguntar à IA…")}</span><kbd>{tr("⌘K")}</kbd>
        </div>}
        {/* Race control: o estado da operação em cápsulas, em toda tela. Cada item leva para onde se resolve. */}
        {!box && <div className="rc" aria-label={tr("Estado da operação")}>
          <button className={`it ${syncTone}`} title={lastSync ? tr("última sincronia: {0}", new Date(lastSync).toLocaleString(LOCALE())) : tr("nenhuma sincronia")} onClick={() => nav('/')}><span className="k">{tr("Espelho")}</span><b>{lastSync ? tr("há {0}", ago(lastSync)) : tr("nunca")}</b></button>
          <button className={`it ${badInt ? 'warn' : 'ok'}`} title={badInt ? bad.map(b => `${b.system}: ${b.status.toLowerCase()}`).join(' · ') : tr("todas respondendo")} onClick={() => nav('/integrations')}><span className="k">{tr("Sistemas")}</span><b>{nInt ? `${nInt - badInt}/${nInt}` : '—'}{badInt > 0 && badInt <= 2 && ` · ${bad.map(b => b.system).join(', ')}`}{badInt > 2 && tr(" · {0} com problema", badInt)}</b></button>
          <button className={`it ${crit ? 'crit' : alerts.length ? 'warn' : 'ok'}`} onClick={() => nav('/attention')}><span className="k">{tr("Atenção")}</span><b>{attn ? tr("{0} item(ns)", attn) : tr("em ordem")}{crit > 0 && tr(" · {0} crítico(s)", crit)}</b></button>
          <button className={`it ${pend ? 'warn' : ''}`} onClick={() => nav(pend ? '/approvals' : '/ai')}><span className="k">{tr("IA")}</span><b>{pend ? tr("{0} esperando você", pend) : tr("nada pendente")}</b></button>
        </div>}
        <div className="grow" />
        <Bandeiras />
        <span className="clock mono small muted" title={tr("hora local")}>{clock.toLocaleDateString(LOCALE(), { weekday: 'short', day: '2-digit', month: '2-digit' })} · {clock.toLocaleTimeString(LOCALE(), { hour: '2-digit', minute: '2-digit' })}</span>
        {!online && <Chip tone="crit" dot>{tr("Offline")}</Chip>}
        {online && dash.error?.offline && <Chip tone="warn" dot>{tr("Servidor fora")}</Chip>}
        <div ref={menuRef} style={{ position: 'relative', display: 'flex', gap: 4 }}>
          <button className="who" onClick={() => setMenu(m => m === 'who' ? 'none' : 'who')} aria-haspopup="menu">
            <span className="avatar">{initials(user?.name)}</span><span className="small ink2">{user?.name?.split(' ')[0]}</span>
          </button>
          {menu === 'who' && <div className="menu" role="menu">
            <div className="mh">{user?.email}<br /><Chip tone={livre ? 'accent' : statusTone('ACTIVE')}>{cargoDe(user)}</Chip></div>
            <hr />
            <button className="mi" onClick={() => nav('/account')}>{tr("Minha conta e senha")}</button>
            <button className="mi" onClick={() => { const r = document.documentElement; r.dataset.theme = r.dataset.theme === 'light' ? 'dark' : 'light'; try { localStorage.setItem('cc.theme', r.dataset.theme) } catch { /* ignore */ } }}>{tr("Alternar tema")}</button>
            <hr />
            <button className="mi" onClick={() => { nav('/login', { replace: true, state: null }); logout() }}>{tr("Sair")}</button>
          </div>}
        </div>
      </header>
      </div>
      <main className={`page${larguraDa(loc.pathname)}`}><div key={loc.pathname.replace(/^(\/(?:compras|crm\/chat|equipe))\/\d+$/, '$1')} className="page-in stack" style={{ gap: 18 }}><Suspense fallback={<Loading />}><Outlet context={{ dash }} /></Suspense></div></main>
    </div>
    <nav className="tabbar" aria-label={tr("Abas")}>
      {box ? <>
        <TB to="/" end icon="home">{tr("Meu dia")}</TB>
        <TB to="/balcao" icon="tag">{tr("Balcão")}</TB>
        <TB to="/checklists" icon="check">{tr("Checklists")}</TB>
        <TB to="/clients" icon="people">{tr("Clientes")}</TB>
      </> : <>
      <TB to="/" end icon="home">{tr("Hoje")}</TB>
      <TB to="/attention" icon="alert" n={attn}>{tr("Atenção")}</TB>
      <TB to="/sales" icon="target" n={d?.sales_due || 0}>{tr("Vendas")}</TB>
      <TB to="/ai" icon="spark" n={pend}>{tr("IA")}</TB>
      </>}
      <button className={`tb${side ? ' active' : ''}`} onClick={() => setSide(s => !s)} aria-label={tr("Mais")}><Icon name="more" />{tr("Mais")}</button>
    </nav>
    {!box && <Palette open={pal} onClose={() => setPal(false)} ask={ask} />}
  </div>
}
