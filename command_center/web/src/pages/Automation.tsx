import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { AiEvent, AutomationRule, Learning } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, Section, Spinner, statusTone } from '../components/ui'
import { fmtDateTime } from '../components/fmt'
import { useToast } from '../components/Toast'

const RULE_LABEL: Record<string, [string, string]> = {
  novo_servico: ['Serviço novo no quadro', 'A IA confere a waiver do piloto, prepara a invoice (produto e valor) e propõe as ações. Nada sai sem aprovação.'],
  email_cliente: ['E-mail de cliente conhecido', 'A IA lê a thread, classifica e propõe um rascunho de resposta. Nunca envia.'],
  waiver_devolvida: ['Waiver com e-mail devolvido', 'A IA procura o e-mail certo no Asana e no Gmail e propõe a correção e o reenvio.'],
  waiver_assinada: ['Waiver assinada', 'A IA comenta na tarefa do Asana que a waiver chegou.'],
}
const KIND_LABEL: Record<string, string> = { 'task.created': 'serviço novo', 'email.received': 'e-mail de cliente', 'waiver.bounced': 'waiver devolvida', 'waiver.completed': 'waiver assinada' }

export function Automation() {
  const { can } = useAuth()
  const toast = useToast()
  const rules = useGet<AutomationRule[]>('/automation/rules')
  const events = useGet<AiEvent[]>('/ai/events?limit=100', 30000)
  const learn = useGet<Learning[]>('/ai/learnings?all=1')
  const [novo, setNovo] = useState('')
  const [busy, setBusy] = useState(false)
  async function toggle(r: AutomationRule) {
    try { await api.put(`/automation/rules/${r.name}`, { enabled: !r.enabled }); rules.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function ensinar() {
    if (!novo.trim()) return
    setBusy(true)
    try { await api.post('/ai/learnings', { text: novo }); setNovo(''); toast('Guardado. Entra em todo comando da IA a partir de agora.', 'ok'); learn.reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <>
    <div className="page-h"><div><h1 className="h1">Automação e memória</h1><div className="sub small">A cada sincronia (a cada 15 minutos ou ao clicar), o que mudou vira evento; cada evento com regra ligada acorda a IA, que propõe ações. Aprovar executa. O que você ensina fica na memória e entra em todo comando.</div></div>
      {can('OPERATOR') && <button className="btn" onClick={async () => { const r = await api.post<{ disparados: number }>('/ai/events/process'); toast(`${r.disparados} evento(s) disparado(s).`, 'ok'); events.reload() }}>Processar eventos pendentes</button>}</div>
    <div className="grid g2">
      <Section title="Regras" count={rules.data?.length}>
        {rules.error ? <ErrorState error={rules.error} retry={rules.reload} /> : !rules.data ? <Loading /> : <div className="stack">{rules.data.map(r => { const [l, d] = RULE_LABEL[r.name] || [r.name, r.actions]; return <div className="act" key={r.id}>
          <div className="grow"><b>{l}</b><div className="small ink2">{d}</div></div>
          <label className="check" title={can('ADMIN') ? '' : 'só administrador'}><input type="checkbox" disabled={!can('ADMIN')} checked={!!r.enabled} onChange={() => toggle(r)} /> {r.enabled ? 'ligada' : 'desligada'}</label>
        </div> })}</div>}
        <Banner tone="info">Invoice: enquanto o QuickBooks estiver em stand-by, a IA prepara e propõe; o envio de verdade só existe com o QuickBooks conectado, e sempre depois de aprovação (decisão de 04/09).</Banner>
      </Section>
      <Section title="Memória da IA" count={learn.data?.filter(l => l.active).length}>
        {can('OPERATOR') && <div className="stack" style={{ marginBottom: 12 }}><textarea className="input" rows={2} value={novo} onChange={e => setNovo(e.target.value)} placeholder='Ensine uma regra geral. Ex.: "Practice OKC 2T custa $350; Coaching Bushnell 4T custa $600."' /><div className="row"><span className="grow" /><button className="btn primary sm" disabled={busy || !novo.trim()} onClick={ensinar}>{busy ? <Spinner /> : 'Guardar'}</button></div></div>}
        {!learn.data ? <Loading /> : learn.data.length === 0 ? <Empty>A IA ainda não aprendeu nada por aqui. Use o balão “Instruir a IA” em Precisa de atenção, ou ensine acima.</Empty> :
          <div>{learn.data.map(l => <div className={`att${l.active ? '' : ' dim'}`} key={l.id}><div className={`lv ${l.active ? 'MEDIUM' : 'LOW'}`} /><div className="grow"><div>{l.text}</div><div className="small muted"><Chip tone="outline">{l.scope}</Chip> {l.created_by_name || 'sistema'} · {fmtDateTime(l.created_at)}{l.source_key && <> · de um item de atenção</>}</div></div>
            {can('MANAGER') && <button className="btn ghost sm" onClick={async () => { await api.post(`/ai/learnings/${l.id}/toggle`); learn.reload() }}>{l.active ? 'desativar' : 'reativar'}</button>}</div>)}</div>}
      </Section>
    </div>
    <Section title="Eventos" count={events.data?.length} tight>
      {events.error && !events.data ? <ErrorState error={events.error} retry={events.reload} /> : !events.data ? <Loading /> : events.data.length === 0 ? <Empty>Nenhum evento ainda. Eventos aparecem quando a sincronia encontra tarefa nova, e-mail de cliente ou mudança de waiver.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Quando</th><th>Evento</th><th>Cliente</th><th>O que</th><th>Estado</th><th>IA</th></tr></thead><tbody>
          {events.data.map(e => <tr key={e.id}><td className="mono nowrap">{fmtDateTime(e.detected_at)}</td><td><Chip tone="accent">{KIND_LABEL[e.kind] || e.kind}</Chip></td><td>{e.client_id ? <Link to={`/clients?open=${e.client_id}`}>{e.pilot_name || e.client_name}</Link> : <span className="muted">—</span>}</td><td className="small">{e.summary}</td>
            <td><Chip tone={statusTone(e.status === 'SKIPPED' ? 'INACTIVE' : e.status)}>{e.status}</Chip>{e.note && <span className="small muted"> {e.note}</span>}</td>
            <td className="small">{e.command_id ? <Link to={`/ai/${e.command_id}`}>comando #{e.command_id} · {e.command_status}{e.actions ? ` · ${e.actions} ação(ões)` : ''}</Link> : '—'}</td></tr>)}
        </tbody></table></div>}
    </Section>
  </>
}
