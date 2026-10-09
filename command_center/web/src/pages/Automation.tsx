import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { AiEvent, AutomationRule, Learning } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Section, Spinner, statusTone } from '../components/ui'
import { fmtDateTime } from '../components/fmt'
import { useToast } from '../components/Toast'
import { TextoComVoz } from '../components/Voz'
import { tr } from '../i18n'

const RULE_LABEL: Record<string, [string, string]> = {
  novo_servico: [tr("Serviço novo no quadro"), tr("A IA confere a waiver do piloto, prepara a invoice (produto e valor) e propõe as ações. Nada sai sem aprovação.")],
  email_cliente: [tr("E-mail de cliente conhecido"), tr("A IA lê a thread, classifica e propõe um rascunho de resposta. Nunca envia.")],
  waiver_devolvida: [tr("Waiver com e-mail devolvido"), tr("A IA procura o e-mail certo no Asana e no Gmail e propõe a correção e o reenvio.")],
  pagamento_confirmado: [tr("Pagamento confirmado"), tr("Quando o QuickBooks confirma o pagamento, o painel fecha a subtarefa de pagamento da tarefa do serviço no Asana e comenta o que foi pago. Não passa pela IA nem por aprovação.")],
  waiver_na_tarefa: [tr("Waiver junto da tarefa"), tr("A cada serviço novo no quadro, o painel busca a waiver assinada do piloto, guarda o PDF no card do cliente e anexa na tarefa do Asana. Não passa pela IA nem por aprovação.")],
  waiver_assinada: [tr("Waiver assinada"), tr("A IA comenta na tarefa do Asana que a waiver chegou.")],
  mensalidade_dia_1: [tr("Mensalidade no dia 1"), tr("A IA prepara a invoice mensal de cada piloto com plano e deixa para aprovação (aprovar = enviar).")],
  tarefa_vencida: [tr("Serviço vencido no quadro"), tr("A IA confere se aconteceu e move para Finished Services.")],
  lembrete_invoice: [tr("Lembretes de invoice (09:00)"), tr("O gerente escolhe quais invoices em aberto têm lembrete (diário, semanal ou a cada N dias); o disparo é da IA: às 09:00 ela recebe a lista devida e reenvia cada invoice pelo QuickBooks. Invoice paga desliga sozinha.")],
  varredura_clientes: [tr("Varredura dos clientes (06:00)"), tr("Gmail (as duas caixas) e DocuSign de cada cliente ativo, ligando o que achar ao card. Só leitura e espelho.")],
  gmail_triagem: [tr("Triagem do Gmail (07:00, 13:00, 21:00)"), tr("A IA lê cada thread da inbox, aplica os marcadores e move para o marcador principal. O que pede resposta continua em Precisa de atenção.")],
  sondagem_integracoes: [tr("Sondagem das integrações (07:00 e 22:00)"), tr("Uma chamada real por sistema, de manhã e à noite. Fora disso só re-sonda o sistema que falhar durante o uso.")],
}
const KIND_LABEL: Record<string, string> = { 'invoice.paid': tr("pagamento confirmado"), 'task.created': tr("serviço novo"), 'email.received': tr("e-mail de cliente"), 'waiver.bounced': tr("waiver devolvida"), 'waiver.completed': tr("waiver assinada") }

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
    try { await api.post('/ai/learnings', { text: novo }); setNovo(''); toast(tr("Guardado. Entra em todo comando da IA a partir de agora."), 'ok'); learn.reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <>
    <PageHeader title={tr("Automação e memória")} help={<>{tr("Cada mudança vira evento; regra ligada acorda a IA. O que você ensina entra em todo comando.")}</>}>
      {can('OPERATOR') && <button className="btn" onClick={async () => { const r = await api.post<{ disparados: number }>('/ai/events/process'); toast(tr("{0} evento(s) disparado(s).", r.disparados), 'ok'); events.reload() }}>{tr("Processar eventos pendentes")}</button>}</PageHeader>
    <div className="grid g2">
      <Section title={tr("Regras")} count={rules.data?.length}>
        {rules.error ? <ErrorState error={rules.error} retry={rules.reload} /> : !rules.data ? <Loading /> : <div className="stack">{rules.data.map(r => { const [l, d] = RULE_LABEL[r.name] || [r.name, r.actions]; return <div className="act" key={r.id}>
          <div className="grow"><b>{l}</b><div className="small ink2">{d}</div>{r.schedule && <div className="small muted mono">{tr("horários")} {(() => { try { return (JSON.parse(r.schedule) as string[]).join(' · ') } catch { return r.schedule } })()}{r.last_run_at && tr(" · última {0}", r.last_run_at)}</div>}</div>
          <label className="check" title={can('ADMIN') ? '' : tr("só administrador")}><input type="checkbox" disabled={!can('ADMIN')} checked={!!r.enabled} onChange={() => toggle(r)} /> {r.enabled ? tr("ligada") : tr("desligada")}</label>
        </div> })}</div>}
        <Banner tone="info">{tr("Invoice: enquanto o QuickBooks estiver em stand-by, a IA prepara e propõe; o envio de verdade só existe com o QuickBooks conectado, e sempre depois de aprovação (decisão de 04/09).")}</Banner>
      </Section>
      <Section title={tr("Memória da IA")} count={learn.data?.filter(l => l.active).length}>
        {can('OPERATOR') && <div className="stack" style={{ marginBottom: 12 }}><TextoComVoz valor={novo} onChange={setNovo} linhas={2} placeholder={tr("Ensine (ou dite) uma regra geral. Ex.: \"Practice OKC 2T custa $350; Coaching Bushnell 4T custa $600.\"")} /><div className="row"><span className="grow" /><button className="btn primary sm" disabled={busy || !novo.trim()} onClick={ensinar}>{busy ? <Spinner /> : tr("Guardar")}</button></div></div>}
        {!learn.data ? <Loading /> : learn.data.length === 0 ? <Empty>{tr("A IA ainda não aprendeu nada por aqui. Use o balão “Instruir a IA” em Precisa de atenção, ou ensine acima.")}</Empty> :
          <div>{learn.data.map(l => <div className={`att${l.active ? '' : ' dim'}`} key={l.id}><div className={`lv ${l.active ? 'MEDIUM' : 'LOW'}`} /><div className="grow"><div>{l.text}</div><div className="small muted"><Chip tone="outline">{l.scope}</Chip> {l.created_by_name || tr("sistema")} · {fmtDateTime(l.created_at)}{l.source_key && <> {tr("· de um item de atenção")}</>}</div></div>
            {can('MANAGER') && <button className="btn ghost sm" onClick={async () => { await api.post(`/ai/learnings/${l.id}/toggle`); learn.reload() }}>{l.active ? tr("desativar") : tr("reativar")}</button>}</div>)}</div>}
      </Section>
    </div>
    <Section title={tr("Eventos")} count={events.data?.length} tight>
      {events.error && !events.data ? <ErrorState error={events.error} retry={events.reload} /> : !events.data ? <Loading /> : events.data.length === 0 ? <Empty>{tr("Nenhum evento ainda. Eventos aparecem quando a sincronia encontra tarefa nova, e-mail de cliente ou mudança de waiver.")}</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{tr("Quando")}</th><th>{tr("Evento")}</th><th>{tr("Cliente")}</th><th>{tr("O que")}</th><th>{tr("Estado")}</th><th>{tr("IA")}</th></tr></thead><tbody>
          {events.data.map(e => <tr key={e.id}><td className="mono nowrap">{fmtDateTime(e.detected_at)}</td><td><Chip tone="accent">{KIND_LABEL[e.kind] || e.kind}</Chip></td><td>{e.client_id ? <Link to={`/clients?open=${e.client_id}`}>{e.pilot_name || e.client_name}</Link> : <span className="muted">—</span>}</td><td className="small">{e.summary}</td>
            <td><Chip tone={statusTone(e.status === 'SKIPPED' ? 'INACTIVE' : e.status)}>{e.status}</Chip>{e.note && <span className="small muted"> {e.note}</span>}</td>
            <td className="small">{e.command_id ? <Link to={`/ai/${e.command_id}`}>{tr("comando #")}{e.command_id} · {e.command_status}{e.actions ? tr(" · {0} ação(ões)", e.actions) : ''}</Link> : '—'}</td></tr>)}
        </tbody></table></div>}
    </Section>
  </>
}
