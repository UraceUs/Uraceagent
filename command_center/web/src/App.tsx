import { lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { Role } from './api/types'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { telaDoBox } from './auth/telas'
import { Shell } from './components/Shell'
import { PerguntarProvider } from './components/Perguntar'
import { ToastProvider } from './components/Toast'
import { Empty, PageHeader } from './components/ui'
import { Login } from './pages/Login'
import { tr } from './i18n'

// Cada tela é um pedaço próprio do JavaScript (issue #19): o celular baixa o que abre,
// não o painel inteiro. O login fica no pacote inicial — é a primeira coisa que aparece.
const tela = <N extends string>(carregar: () => Promise<Record<N, ComponentType<any>>>, nome: N) =>
  lazy(() => carregar().then(m => ({ default: m[nome] })))
const AICommand = tela(() => import('./pages/AI'), 'AICommand')
const Activity = tela(() => import('./pages/AI'), 'Activity')
const Approvals = tela(() => import('./pages/AI'), 'Approvals')
const AttentionPage = tela(() => import('./pages/Attention'), 'AttentionPage')
const Automation = tela(() => import('./pages/Automation'), 'Automation')
const Capabilities = tela(() => import('./pages/Capabilities'), 'Capabilities')
const Races = tela(() => import('./pages/Races'), 'Races')
const Estoque = tela(() => import('./pages/Estoque'), 'Estoque')
const Balcao = tela(() => import('./pages/Balcao'), 'Balcao')
const MeuDia = tela(() => import('./pages/MeuDia'), 'MeuDia')
const Checklists = tela(() => import('./pages/Checklists'), 'Checklists')
const Checklist = tela(() => import('./pages/Checklists'), 'Checklist')
const Biblioteca = tela(() => import('./pages/Biblioteca'), 'Biblioteca')
const PeloQr = tela(() => import('./pages/Balcao'), 'PeloQr')
const BalcaoRapido = tela(() => import('./pages/BalcaoRapido'), 'BalcaoRapido')
const Planejamento = tela(() => import('./pages/Logistica'), 'Planejamento')
const Compras = tela(() => import('./pages/Compras'), 'Compras')
const Pedidos = tela(() => import('./pages/Compras'), 'Pedidos')
const Client360 = tela(() => import('./pages/Client360'), 'Client360')
const Clients = tela(() => import('./pages/Clients'), 'Clients')
const CRM = tela(() => import('./pages/CRM'), 'CRM')
const Equipe = tela(() => import('./pages/Equipe'), 'Equipe')
const GmailManual = tela(() => import('./pages/GmailManual'), 'GmailManual')
const Dashboard = tela(() => import('./pages/Dashboard'), 'Dashboard')
const AsanaPage = tela(() => import('./pages/Systems'), 'AsanaPage')
const DocuSignPage = tela(() => import('./pages/Systems'), 'DocuSignPage')
const GmailPage = tela(() => import('./pages/Systems'), 'GmailPage')
const QuickBooksPage = tela(() => import('./pages/Systems'), 'QuickBooksPage')
const Account = tela(() => import('./pages/System'), 'Account')
const Cofre = tela(() => import('./pages/Cofre'), 'Cofre')
const Audit = tela(() => import('./pages/System'), 'Audit')
const Integrations = tela(() => import('./pages/System'), 'Integrations')
const Policies = tela(() => import('./pages/System'), 'Policies')
const Users = tela(() => import('./pages/System'), 'Users')
const AgendaVendas = tela(() => import('./pages/Vendas'), 'AgendaVendas')
const Oportunidade = tela(() => import('./pages/Vendas'), 'Oportunidade')
const Oportunidades = tela(() => import('./pages/Vendas'), 'Oportunidades')

const Suits = tela(() => import('./pages/Suits'), 'Suits')
const SuitPedido = tela(() => import('./pages/Suits'), 'SuitPedido')
const SitePublico = tela(() => import('./pages/SitePublico'), 'SitePublico')
const PortalApp = tela(() => import('./portal/Portal'), 'PortalApp')

const PAPEL_PT: Record<string, string> = { ADMIN: tr("administrador"), MANAGER: tr("gerente"), OPERATOR: tr("operador"), VIEWER: tr("leitura") }

function Guard({ min, children }: { min?: Role; children: ReactNode }) {
  const { user, ready, can, box } = useAuth()
  const loc = useLocation()
  if (!ready) return <div className="state" style={{ minHeight: '100vh', justifyContent: 'center' }}><span className="spin" /></div>
  if (!user) return <Navigate to="/login" replace state={loc.pathname === '/login' ? null : { from: loc.pathname + loc.search }} />
  // mecânico e coach (#92): fora das telas do box, a mesma porta fechada
  if ((min && !can(min)) || (box && !telaDoBox(loc.pathname))) return <><PageHeader title={tr("Sem permissão")} />
    <div className="card"><Empty title={tr("Esta área não é do seu acesso")}>{min && !can(min) ? <>{tr("Ela exige acesso de")} {PAPEL_PT[min] || min} {tr("ou acima.")}</> : tr("Ela não faz parte do acesso do box.")} {tr("Fale com o administrador.")}</Empty></div></>
  return <>{children}</>
}

/** /suits/leads é uma aba; /suits/12 é um pedido. */
function SuitsOuPedido() {
  const loc = useLocation()
  return /^\/suits\/\d+\/?$/.test(loc.pathname) ? <SuitPedido /> : <Suits />
}

/** A tela inicial: "Meu dia" para o mecânico e o coach (#92); o painel para os outros. */
function Inicio() {
  const { box } = useAuth()
  return box ? <MeuDia /> : <Dashboard />
}

/** #180: em balcao.urace.us a única tela é o balcão do celular — qualquer endereço abre ele. */
function SoBalcao() {
  return <Routes>
    <Route path="/login" element={<Login />} />
    <Route path="*" element={<Guard><Suspense fallback={null}><BalcaoRapido /></Suspense></Guard>} />
  </Routes>
}

function Rotas() {
  const { user } = useAuth()
  if (user?.so_balcao) return <SoBalcao />
  return <Routes>
        <Route path="/login" element={<Login />} />
        {/* #180: o balcão do celular ocupa a tela inteira, fora do Shell */}
        <Route path="/balcao/rapido" element={<Guard min="OPERATOR"><Suspense fallback={null}><BalcaoRapido /></Suspense></Guard>} />
        {/* área do cliente (#40): fora do Shell e da sessão da equipe */}
        <Route path="/portal/*" element={<Suspense fallback={null}><PortalApp /></Suspense>} />
        <Route element={<Guard><Shell /></Guard>}>
          <Route index element={<Inicio />} />
          <Route path="meu-dia" element={<MeuDia />} />
          <Route path="checklists" element={<Guard min="OPERATOR"><Checklists /></Guard>} />
          <Route path="checklists/:runId" element={<Guard min="OPERATOR"><Checklist /></Guard>} />
          <Route path="attention" element={<AttentionPage />} />
          {/* Logística (dono, 23/09) */}
          <Route path="estoque" element={<Estoque />} />
          <Route path="balcao" element={<Guard min="OPERATOR"><Balcao /></Guard>} />
          <Route path="balcao/:clientId" element={<Guard min="OPERATOR"><Balcao /></Guard>} />
          <Route path="c/:codigo" element={<Guard min="OPERATOR"><PeloQr /></Guard>} />
          <Route path="biblioteca" element={<Guard min="MANAGER"><Biblioteca /></Guard>} />
          <Route path="biblioteca/:aba" element={<Guard min="MANAGER"><Biblioteca /></Guard>} />
          <Route path="pedidos" element={<Pedidos />} />
          <Route path="compras" element={<Compras />} />
          <Route path="compras/:id" element={<Compras />} />
          <Route path="planejamento" element={<Planejamento />} />
          <Route path="clients" element={<Clients />} />
          <Route path="clients/:id" element={<Client360 />} />
          <Route path="asana" element={<AsanaPage />} />
          <Route path="docusign" element={<DocuSignPage />} />
          <Route path="gmail" element={<GmailPage />} />
          <Route path="gmail/manual" element={<GmailManual />} />
          <Route path="quickbooks" element={<QuickBooksPage />} />
          <Route path="crm" element={<Navigate to="/crm/chat" replace />} />
          <Route path="crm/chat" element={<CRM vista="chat" />} />
          <Route path="crm/chat/:lead" element={<CRM vista="chat" />} />
          <Route path="crm/funil" element={<CRM vista="funil" />} />
          <Route path="kommo" element={<Navigate to="/crm/chat" replace />} />
          <Route path="equipe" element={<Equipe />} />
          <Route path="equipe/:canal" element={<Equipe />} />
          <Route path="site" element={<Guard min="OPERATOR"><SitePublico /></Guard>} />
          <Route path="site/:aba" element={<Guard min="OPERATOR"><SitePublico /></Guard>} />
          {/* Suits · Alpha Line (#153): as abas são caminho; o pedido é /suits/12 */}
          <Route path="suits" element={<Guard min="OPERATOR"><Suits /></Guard>} />
          <Route path="suits/:aba" element={<Guard min="OPERATOR"><SuitsOuPedido /></Guard>} />
          <Route path="sales" element={<Guard min="OPERATOR"><Oportunidades /></Guard>} />
          <Route path="sales/agenda" element={<Guard min="OPERATOR"><AgendaVendas /></Guard>} />
          <Route path="sales/:id" element={<Guard min="OPERATOR"><Oportunidade /></Guard>} />
          <Route path="vendas" element={<Navigate to="/sales" replace />} />
          <Route path="races" element={<Races />} />
          <Route path="equipment" element={<Navigate to="/clients?v=pro" replace />} />
          <Route path="tasks" element={<Navigate to="/asana" replace />} />
          <Route path="waivers" element={<Navigate to="/docusign" replace />} />
          <Route path="emails" element={<Navigate to="/gmail" replace />} />
          <Route path="ai" element={<AICommand />} />
          <Route path="ai/capabilities" element={<Capabilities />} />
          <Route path="ai/:id" element={<AICommand />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="activity" element={<Activity />} />
          <Route path="automation" element={<Automation />} />
          <Route path="integrations" element={<Integrations />} />
          <Route path="audit" element={<Guard min="MANAGER"><Audit /></Guard>} />
          <Route path="policies" element={<Guard min="ADMIN"><Policies /></Guard>} />
          <Route path="users" element={<Guard min="ADMIN"><Users /></Guard>} />
          <Route path="account" element={<Account />} />
          <Route path="cofre" element={<Cofre />} />
          <Route path="*" element={<><PageHeader title={tr("Página não encontrada")} /><div className="card"><Empty title={tr("Este endereço não existe")}>{tr("Use o menu ou ⌘K.")}</Empty></div></>} />
        </Route>
      </Routes>
}

export default function App() {
  return <BrowserRouter basename="/ops">
    <AuthProvider><ToastProvider><PerguntarProvider>
      <Rotas />
    </PerguntarProvider></ToastProvider></AuthProvider>
  </BrowserRouter>
}
