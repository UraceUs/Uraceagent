import { useState } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { Loaded } from '../api/hooks'
import type { Dashboard as D } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { AttentionList } from './Attention'
import { Banner, Chip, ErrorState, Kpi, Loading, Section, Spinner, statusTone } from '../components/ui'
import { ago, money } from '../components/fmt'
import { useToast } from '../components/Toast'

export function Dashboard() {
  const { dash } = useOutletContext<{ dash: Loaded<D> }>()
  const { can } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const [syncing, setSyncing] = useState(false)
  const d = dash.data
  if (dash.error && !d) return <ErrorState error={dash.error} retry={dash.reload} />
  if (!d) return <Loading rows={6} />
  const lastSync = d.last_sync.map(s => s.at).filter(Boolean).sort().pop() || null
  const stale = !lastSync || Date.now() - new Date(lastSync).getTime() > 2 * 3600 * 1000

  async function sync() {
    setSyncing(true)
    try { await api.post('/sync'); toast('Espelhos atualizados a partir das fontes.', 'ok'); dash.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setSyncing(false) }
  }

  return <>
    <div className="page-h">
      <div><h1 className="h1">Dashboard</h1><div className="sub small">Dados espelhados das fontes reais. Última sincronia: <b>{lastSync ? ago(lastSync) : 'nunca'}</b>.</div></div>
      <div className="row">
        {can('OPERATOR') && <button className="btn" onClick={sync} disabled={syncing}>{syncing ? <Spinner /> : '↻'} Sincronizar agora</button>}
        {can('OPERATOR') && <button className="btn primary" onClick={() => nav('/ai')}>Perguntar à IA</button>}
      </div>
    </div>
    {stale && <Banner tone="warn"><b>Espelho antigo.</b> {lastSync ? `A última sincronia foi há ${ago(lastSync)}.` : 'Nenhuma sincronia registrada ainda.'} Os números abaixo podem estar defasados.</Banner>}
    <div className="grid g6">
      <Kpi label="Clientes ativos" value={d.active_clients} onClick={() => nav('/clients?status=ACTIVE')} />
      <Kpi label="Serviços hoje" value={d.tasks_due_today} onClick={() => nav('/tasks')} />
      <Kpi label="Vencidos" value={d.overdue_tasks} tone={d.overdue_tasks ? 'warn' : undefined} onClick={() => nav('/tasks')} />
      <Kpi label="Próximos 7 dias" value={d.upcoming_7d} onClick={() => nav('/tasks')} />
      <Kpi label="Waivers abertas" value={d.waivers_open} foot={d.waivers_bounced ? <span style={{ color: 'var(--crit)' }}>{d.waivers_bounced} devolvida(s)</span> : 'nenhuma devolvida'} tone={d.waivers_bounced ? 'crit' : undefined} onClick={() => nav('/waivers')} />
      <Kpi label="E-mails de cliente" value={d.emails_attention} tone={d.emails_attention ? 'warn' : undefined} foot="sem tratamento" onClick={() => nav('/emails')} />
    </div>
    <div className="grid g3">
      <Kpi label="Ações da IA hoje" value={d.ai_actions_today} onClick={() => nav('/activity')} />
      <Kpi label="Esperando aprovação" value={d.ai_pending_approval} tone={d.ai_pending_approval ? 'warn' : undefined} onClick={() => nav('/approvals')} />
      {d.open_invoices === null
        ? <Kpi label="Invoices em aberto" value="—" foot="visível para gerentes" />
        : <Kpi label="Invoices em aberto" value={d.open_invoices.connected ? money(d.open_invoices.total) : '—'}
            foot={d.open_invoices.connected ? `${d.open_invoices.count} aberta(s), ${d.open_invoices.overdue} vencida(s)` : 'QuickBooks em stand-by (não conectado)'} />}
    </div>
    <div className="grid g2" style={{ gridTemplateColumns: 'minmax(0,1.5fr) minmax(0,1fr)' }}>
      <Section title="Precisa de atenção" count={d.needs_attention_total} tight right={<Link to="/attention" className="small">ver tudo</Link>}>
        <AttentionList items={d.needs_attention} />
      </Section>
      <div className="stack">
        <Section title="Integrações" tight right={<Link to="/integrations" className="small">detalhes</Link>}>
          <table className="tbl"><tbody>
            {d.integrations.map(i => <tr key={i.system} className="click" onClick={() => nav('/integrations')}>
              <td style={{ textTransform: 'capitalize' }}>{i.system}</td>
              <td><Chip tone={statusTone(i.status)} dot>{i.status}</Chip></td>
              <td className="right mono small muted">{i.last_success_at ? ago(i.last_success_at) : '—'}</td>
            </tr>)}
          </tbody></table>
        </Section>
        <Section title="Sincronia" tight>
          <table className="tbl"><tbody>
            {d.last_sync.length === 0 && <tr><td className="muted">Nunca sincronizou. Use “Sincronizar agora”.</td></tr>}
            {d.last_sync.map(s => <tr key={s.system}>
              <td style={{ textTransform: 'capitalize' }}>{s.system}</td>
              <td><Chip tone={s.ok ? 'ok' : 'crit'}>{s.ok ? 'ok' : 'falhou'}</Chip></td>
              <td className="small muted truncate" style={{ maxWidth: 200 }} title={s.message || ''}>{s.message}</td>
              <td className="right mono small muted">{ago(s.at)}</td>
            </tr>)}
          </tbody></table>
        </Section>
      </div>
    </div>
  </>
}
