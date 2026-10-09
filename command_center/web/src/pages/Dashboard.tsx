import { useState } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { Loaded } from '../api/hooks'
import type { Dashboard as D, SyncStatus } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { AttentionList } from './Attention'
import { Banner, ErrorState, Kpi, Loading, PageHeader, Progress, SYS_NAME, Section, Status, Strip, Thinking } from '../components/ui'
import { ago, money } from '../components/fmt'
import { useToast } from '../components/Toast'
import { tr, LOCALE } from '../i18n'

export function Dashboard() {
  const { dash } = useOutletContext<{ dash: Loaded<D> }>()
  const { can } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const [syncing, setSyncing] = useState(false)
  const [stage, setStage] = useState<string>('')
  const d = dash.data
  if (dash.error && !d) return <ErrorState error={dash.error} retry={dash.reload} />
  if (!d) return <Loading rows={6} />
  const lastSync = d.last_sync.map(s => s.at).filter(Boolean).sort().pop() || null
  const stale = !lastSync || Date.now() - new Date(lastSync).getTime() > 2 * 3600 * 1000

  async function sync() {
    setSyncing(true)
    try {
      const r = await api.post<{ started: boolean; running: boolean }>('/sync')
      toast(r.started ? tr("Sincronia iniciada. O histórico do Asana pode levar alguns minutos.") : tr("Já há uma sincronia rodando."))
      for (let i = 0; i < 240; i++) {                       // até ~20 min, a cada 5 s
        await new Promise(res => setTimeout(res, 5000))
        const st = await api.get<SyncStatus>('/sync')
        if (st.running) { const t0 = st.started_at ? Math.round((Date.now() - new Date(st.started_at).getTime()) / 60000) : 0; setStage(`${st.stage || '…'} · ${t0} min`) }
        if (!st.running) {
          const falhas = Object.entries(st.result || {}).filter(([, v]) => !v.ok)
          toast(falhas.length ? tr("Sincronia terminou com aviso: {0}", falhas.map(([k, v]) => `${k} (${v.motivo})`).join(', ')) : tr("Espelhos atualizados a partir das fontes."), falhas.length ? undefined : 'ok')
          break
        }
      }
      dash.reload()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setSyncing(false); setStage('') }
  }

  const crit = d.needs_attention.filter(a => a.level === 'CRITICAL').length
  const syncPor = new Map(d.last_sync.map(s => [s.system, s]))
  return <>
    <Progress on={syncing} />
    <PageHeader title={tr("Hoje")} eyebrow={new Date().toLocaleDateString(LOCALE(), { weekday: 'long', day: 'numeric', month: 'long' })} help={<>{tr("O que decide está em cima: pista de hoje, o que precisa de gente, o que espera sua aprovação. A IA já tratou o que pôde. Última sincronia:")} <b>{lastSync ? ago(lastSync) : tr("nunca")}</b>.</>}>
      {can('OPERATOR') && <button className="btn" onClick={sync} disabled={syncing} title={tr("Lê Asana, DocuSign, Gmail e QuickBooks de novo")}>{syncing ? <Thinking label={tr("Sincronizando: {0}", stage || '…')} /> : <>{tr("↻ Sincronizar")}</>}</button>}
      {can('OPERATOR') && <button className="btn primary" onClick={() => nav('/ai')}>{tr("✦ Perguntar à IA")}</button>}
    </PageHeader>
    {stale && <Banner tone="warn"><b>{tr("Espelho antigo.")}</b> {lastSync ? tr("A última sincronia foi há {0}.", ago(lastSync)) : tr("Nenhuma sincronia registrada ainda.")} {tr("Os números podem estar defasados — sincronize.")}</Banner>}
    <div className="grid g4k">
      <Kpi lead label={tr("Pista hoje")} value={d.tasks_due_today} foot={d.tasks_due_today ? tr("serviço(s) marcado(s) para hoje") : tr("nada marcado para hoje")} onClick={() => nav('/asana?v=board')} />
      <Kpi lead label={tr("Precisa de gente")} value={d.needs_attention_total} tone={crit ? 'crit' : d.needs_attention_total ? 'warn' : 'ok'} foot={crit ? tr("{0} crítico(s)", crit) : d.needs_attention_total ? tr("nenhum crítico") : tr("tudo em ordem")} onClick={() => nav('/attention')} />
      <Kpi lead label={tr("Esperando você")} value={d.ai_pending_approval} tone={d.ai_pending_approval ? 'warn' : 'ok'} foot={d.ai_pending_approval ? tr("ação(ões) da IA para aprovar") : tr("nenhuma aprovação pendente")} onClick={() => nav('/approvals')} />
      <Kpi lead label={tr("Waivers abertas")} value={d.waivers_open} tone={d.waivers_bounced ? 'crit' : undefined} foot={d.waivers_bounced ? tr("{0} devolvida(s) — e-mail errado", d.waivers_bounced) : tr("nenhuma devolvida")} onClick={() => nav('/docusign')} />
    </div>
    <Strip items={[
      { label: tr("Próximos 7 dias"), value: d.upcoming_7d, onClick: () => nav('/asana?v=cal'), title: tr("serviços na agenda") },
      { label: tr("Vencidos"), value: d.overdue_tasks, tone: d.overdue_tasks ? 'warn' : undefined, onClick: () => nav('/asana?v=board&s=open'), title: tr("a IA confere e move") },
      { label: tr("Clientes ativos"), value: d.active_clients, onClick: () => nav('/clients?status=ACTIVE'), title: tr("serviço nos últimos 6 meses") },
      { label: tr("E-mails sem tratar"), value: d.emails_attention, tone: d.emails_attention ? 'warn' : undefined, onClick: () => nav('/gmail') },
      { label: tr("Ações da IA hoje"), value: d.ai_actions_today, onClick: () => nav('/activity') },
      { label: tr("Invoices em aberto"), value: d.open_invoices === null ? '🔒' : d.open_invoices.connected ? money(d.open_invoices.total) : '—', tone: d.open_invoices?.overdue ? 'warn' : undefined,
        title: d.open_invoices === null ? tr("visível para gerentes") : d.open_invoices?.connected ? tr("{0} aberta(s), {1} vencida(s)", d.open_invoices.count, d.open_invoices.overdue) : tr("QuickBooks não conectado"), onClick: () => nav('/quickbooks') },
    ]} />
    <div className="grid g2" style={{ gridTemplateColumns: 'minmax(0,1.6fr) minmax(0,1fr)' }}>
      <Section title={tr("Precisa de atenção")} count={d.needs_attention_total} tight right={<Link to="/attention" className="small">{tr("ver tudo →")}</Link>}>
        <AttentionList items={d.needs_attention.slice(0, 6)} onChange={dash.reload} />
        {d.needs_attention_total > 6 && <div className="small muted" style={{ padding: '10px 16px' }}><Link to="/attention">{tr("mais")} {d.needs_attention_total - 6} {tr("item(ns) →")}</Link></div>}
      </Section>
      <Section title={tr("Sistemas")} tight right={<Link to="/integrations" className="small">{tr("detalhes →")}</Link>}>
        <div className="tbl-wrap"><table className="tbl"><tbody>
          {d.integrations.map(i => { const s = syncPor.get(i.system); return <tr key={i.system} className="click" onClick={() => nav('/integrations')} tabIndex={0} onKeyDown={e => e.key === 'Enter' && nav('/integrations')}>
            <td><b>{SYS_NAME[i.system] || i.system}</b>{s && s.ok === 0 && <div className="small clamp2" style={{ color: 'var(--crit)' }} title={s.message || ''}>{s.message}</div>}</td>
            <td className="nowrap"><Status s={i.status} /></td>
            <td className="right mono small muted nowrap" title={i.last_success_at ? tr("última resposta {0}", new Date(i.last_success_at).toLocaleString(LOCALE())) : ''}>{i.last_success_at ? ago(i.last_success_at) : '—'}</td>
          </tr> })}
          {d.last_sync.length === 0 && <tr><td className="muted">{tr("Nunca sincronizou. Use “Sincronizar”.")}</td></tr>}
        </tbody></table></div>
      </Section>
    </div>
  </>
}
