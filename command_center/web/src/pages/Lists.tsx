import { useNavigate } from 'react-router-dom'
import { useGet } from '../api/hooks'
import type { Email, Task, Waiver } from '../api/types'
import { Chip, Empty, ErrorState, Ext, Loading, Section, WAIVER_LABEL, statusTone } from '../components/ui'
import { daysUntil, fmtDate, fmtDateTime } from '../components/fmt'

export function Tasks() {
  const nav = useNavigate()
  const { data, error, loading, reload } = useGet<Task[]>('/tasks?status=open')
  const grp = new Map<string, Task[]>()
  for (const t of data || []) { const k = t.section || '—'; grp.set(k, [...(grp.get(k) || []), t]) }
  return <>
    <div className="page-h"><div><h1 className="h1">Serviços</h1><div className="sub small">Tarefas abertas do quadro U-RACE por coluna do dia. RACES não entra na varredura de waiver.</div></div><button className="btn" onClick={reload}>↻</button></div>
    {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> : grp.size === 0 ? <div className="card"><Empty title="Quadro vazio">Nenhuma tarefa aberta espelhada. Sincronize no Dashboard.</Empty></div> :
      [...grp.entries()].map(([sec, ts]) => <Section key={sec} title={sec} count={ts.length} tight>
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Data</th><th>Serviço</th><th>Cliente</th><th>Responsável</th><th>Subtarefas</th><th></th></tr></thead><tbody>
          {ts.map(t => { const d = daysUntil(t.due_on); return <tr key={t.id} className={t.client_id ? 'click' : ''} onClick={() => t.client_id && nav(`/clients/${t.client_id}`)}>
            <td className="mono nowrap">{fmtDate(t.due_on)} {d !== null && <Chip tone={d < 0 ? 'crit' : d <= 1 ? 'warn' : 'neutral'}>{d < 0 ? `${-d} d atrás` : d === 0 ? 'hoje' : d === 1 ? 'amanhã' : `${d} d`}</Chip>}</td>
            <td>{t.title}</td><td>{t.client_name || <span className="muted">—</span>}</td><td className="small">{t.assignee}</td>
            <td className="mono">{t.subtasks_total ? `${t.subtasks_done ?? 0}/${t.subtasks_total}` : '—'}</td>
            <td onClick={e => e.stopPropagation()}>{t.links?.map(l => <Ext key={l.external_id} href={l.deep_link}>{l.system}</Ext>)}</td></tr> })}
        </tbody></table></div>
      </Section>)}
  </>
}

export function Waivers() {
  const nav = useNavigate()
  const { data, error, loading, reload } = useGet<Waiver[]>('/waivers')
  return <>
    <div className="page-h"><div><h1 className="h1">Waivers</h1><div className="sub small">Envelopes DocuSign (produção). <b>Delivered ≠ assinada.</b> Autoresponded = e-mail devolveu.</div></div><button className="btn" onClick={reload}>↻</button></div>
    <Section title="Envelopes" count={data?.length} tight>
      {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> : (data || []).length === 0 ? <Empty>Nenhum envelope espelhado.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Signatário</th><th>Cliente</th><th>Modelo</th><th>Status</th><th>Enviada</th><th>Assinada</th><th>Expira</th><th></th></tr></thead><tbody>
          {data!.map(w => <tr key={w.id} className={w.client_id ? 'click' : ''} onClick={() => w.client_id && nav(`/clients/${w.client_id}`)}>
            <td>{w.signer_name}<div className="small muted">{w.signer_email}</div></td><td>{w.client_name || <span className="muted">não vinculado</span>}</td><td>{w.template}</td>
            <td><Chip tone={statusTone(w.status)}>{WAIVER_LABEL[w.status || ''] || w.status}</Chip></td>
            <td className="mono">{fmtDate(w.sent_at)}</td><td className="mono">{fmtDate(w.completed_at)}</td><td className="mono">{fmtDate(w.expires_at)}</td>
            <td onClick={e => e.stopPropagation()}>{w.links?.map(l => <Ext key={l.external_id} href={l.deep_link}>abrir</Ext>)}</td></tr>)}
        </tbody></table></div>}
    </Section>
  </>
}

export function Emails() {
  const nav = useNavigate()
  const { data, error, loading, reload } = useGet<Email[]>('/emails')
  return <>
    <div className="page-h"><div><h1 className="h1">E-mails</h1><div className="sub small">Threads das caixas urace@ e support@ classificadas pela triagem. A IA nunca envia e-mail daqui.</div></div><button className="btn" onClick={reload}>↻</button></div>
    <Section title="Threads" count={data?.length} tight>
      {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> : (data || []).length === 0 ? <Empty>Nenhuma thread espelhada.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Quando</th><th>Caixa</th><th>Assunto</th><th>De</th><th>Cliente</th><th>Prioridade</th><th>Intenção</th><th>Tratado</th><th></th></tr></thead><tbody>
          {data!.map(e => <tr key={e.id} className={e.client_id ? 'click' : ''} onClick={() => e.client_id && nav(`/clients/${e.client_id}`)}>
            <td className="mono nowrap">{fmtDateTime(e.last_at)}</td><td>{e.mailbox}@</td><td className="truncate" style={{ maxWidth: 320 }}>{e.subject}</td><td className="small truncate" style={{ maxWidth: 200 }}>{e.sender}</td>
            <td>{e.client_name || <span className="muted">—</span>}</td>
            <td>{e.priority && <Chip tone={e.priority === 'CRITICAL' ? 'crit' : e.priority === 'HIGH' ? 'warn' : 'neutral'}>{e.priority}</Chip>}</td><td className="small">{e.intent}</td>
            <td>{e.handled ? '✓' : <span style={{ color: 'var(--warn)' }}>não</span>}</td>
            <td onClick={ev => ev.stopPropagation()}>{e.links?.map(l => <Ext key={l.external_id} href={l.deep_link}>Gmail</Ext>)}</td></tr>)}
        </tbody></table></div>}
    </Section>
  </>
}
