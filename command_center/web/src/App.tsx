import { type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { Role } from './api/types'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { Shell } from './components/Shell'
import { ToastProvider } from './components/Toast'
import { Empty } from './components/ui'
import { AICommand, Activity, Approvals } from './pages/AI'
import { AttentionPage } from './pages/Attention'
import { Client360 } from './pages/Client360'
import { Clients } from './pages/Clients'
import { Dashboard } from './pages/Dashboard'
import { AsanaPage, DocuSignPage, GmailPage, QuickBooksPage } from './pages/Systems'
import { Login } from './pages/Login'
import { Account, Audit, Integrations, Policies, Users } from './pages/System'

function Guard({ min, children }: { min?: Role; children: ReactNode }) {
  const { user, ready, can } = useAuth()
  const loc = useLocation()
  if (!ready) return <div className="state" style={{ minHeight: '100vh', justifyContent: 'center' }}><span className="spin" /></div>
  if (!user) return <Navigate to="/login" replace state={loc.pathname === '/login' ? null : { from: loc.pathname + loc.search }} />
  if (min && !can(min)) return <div className="card"><Empty title="Sem permissão">Esta área exige papel {min} ou superior. Fale com o administrador.</Empty></div>
  return <>{children}</>
}

export default function App() {
  return <BrowserRouter basename="/ops">
    <AuthProvider><ToastProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Guard><Shell /></Guard>}>
          <Route index element={<Dashboard />} />
          <Route path="attention" element={<AttentionPage />} />
          <Route path="clients" element={<Clients />} />
          <Route path="clients/:id" element={<Client360 />} />
          <Route path="asana" element={<AsanaPage />} />
          <Route path="docusign" element={<DocuSignPage />} />
          <Route path="gmail" element={<GmailPage />} />
          <Route path="quickbooks" element={<QuickBooksPage />} />
          <Route path="tasks" element={<Navigate to="/asana" replace />} />
          <Route path="waivers" element={<Navigate to="/docusign" replace />} />
          <Route path="emails" element={<Navigate to="/gmail" replace />} />
          <Route path="ai" element={<AICommand />} />
          <Route path="ai/:id" element={<AICommand />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="activity" element={<Activity />} />
          <Route path="integrations" element={<Integrations />} />
          <Route path="audit" element={<Guard min="MANAGER"><Audit /></Guard>} />
          <Route path="policies" element={<Guard min="ADMIN"><Policies /></Guard>} />
          <Route path="users" element={<Guard min="ADMIN"><Users /></Guard>} />
          <Route path="account" element={<Account />} />
          <Route path="*" element={<div className="card"><Empty title="Página não encontrada">Use o menu ou ⌘K.</Empty></div>} />
        </Route>
      </Routes>
    </ToastProvider></AuthProvider>
  </BrowserRouter>
}
