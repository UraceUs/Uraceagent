import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { Client360 as C360 } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Chip, Empty, ErrorState, Ext, Loading, POLICY_LABEL, Section, WAIVER_LABEL, statusTone } from '../components/ui'
import { daysUntil, fmtDate, fmtDateTime, money } from '../components/fmt'
import { useToast } from '../components/Toast'

function idade(dob?: string | null) {
  if (!dob) return null
  const d = new Date(dob.slice(0, 10) + 'T12:00:00Z'); if (isNaN(d.getTime())) return null
  const h = new Date(); let a = h.getFullYear() - d.getFullYear()
  if (h.getMonth() < d.getMonth() || (h.getMonth() === d.getMonth() && h.getDate() < d.getDate())) a--
  return a
}

const KIND: Record<string, [string, 'ok' | 'warn' | 'crit' | 'info' | '']> = {
  SERVICE: ['Serviço', 'info'], WAIVER_SENT: ['Waiver enviada', 'warn'], WAIVER_SIGNED: ['Waiver assinada', 'ok'], EMAIL: ['E-mail', ''], AI_ACTION: ['Ação da IA', 'info'],
}

export function Client360() {
  const { id } = useParams()
  return <ClientCard id={Number(id)} />
}

/** Card completo do cliente. Em rota, sem onClose; em janela, com onClose. */
export function ClientCard({ id, onClose }: { id: number; onClose?: () => void }) {
  const nav = useNavigate()
  const { can } = useAuth()
  const toast = useToast()
  const { data, error, loading, reload } = useGet<C360>(id ? `/clients/${id}` : null)
  const [tab, setTab] = useState<'timeline' | 'tasks' | 'waivers' | 'emails' | 'invoices' | 'ai'>('timeline')
  const [edit, setEdit] = useState(false)
  const [form, setForm] = useState({ status: '', stage_code: '', notes: '', vip: false })
  const [saving, setSaving] = useState(false)
  const [scanning, setScanning] = useState(false)
  if (error && !data) return <ErrorState error={error} retry={reload} />
  if (loading && !data) return <Loading rows={8} />
  if (!data) return null
  const c = data.client
  const prox = data.tasks.filter(t => t.status === 'open' && t.due_on && (daysUntil(t.due_on) ?? -1) >= 0).sort((a, b) => (a.due_on! < b.due_on! ? -1 : 1))[0]
  const wOk = data.waivers.find(w => w.status === 'completed')
  const wOpen = data.waivers.find(w => w.status === 'sent' || w.status === 'delivered')
  const wBad = data.waivers.find(w => w.status === 'autoresponded')
  const dias = daysUntil(prox?.due_on)
  const risco = !c.vip && prox && !wOk && dias !== null && dias <= 2

  function openEdit() { setForm({ status: c.status, stage_code: c.stage_code || '', notes: c.notes || '', vip: !!c.vip }); setEdit(true) }
  async function save() {
    setSaving(true)
    try {
      const body: Record<string, unknown> = { status: form.status, stage_code: form.stage_code || null, notes: form.notes }
      if (can('MANAGER')) body.vip = form.vip
      await api.patch(`/clients/${c.id}`, body); toast('Cliente atualizado.', 'ok'); setEdit(false); reload()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setSaving(false) }
  }

  return <>
    <div className="page-h">
      <div>
        {!onClose && <div className="small"><a onClick={() => nav(-1)} style={{ cursor: 'pointer' }}>← voltar</a></div>}
        <div className="row wrap"><h1 className="h1">{c.pilot_name || c.name}</h1>{c.pilot_name && <span className="ink2">responsável: <b>{c.name}</b></span>}{!!c.vip && <Chip tone="warn">VIP</Chip>}<Chip tone={statusTone(c.status)}>{c.status}</Chip>{c.source && <Chip tone="outline">{c.source}</Chip>}</div>
        <div className="sub small">{c.pilot_dob && <>Piloto nascido em {fmtDate(c.pilot_dob)}{idade(c.pilot_dob) !== null && <> ({idade(c.pilot_dob)} anos{idade(c.pilot_dob)! < 18 ? ', menor: waiver parental' : ''})</>} · </>}{c.email || 'sem e-mail'}{c.phone && <> · {c.phone}</>}{c.company && <> · {c.company}</>}</div>
      </div>
      <div className="row wrap">
        {data.links.map(l => <Ext key={l.system + l.external_id} href={l.deep_link}>{l.system}</Ext>)}
        {can('OPERATOR') && <button className="btn" disabled={scanning} title="Gmail (urace@ e support@) e DocuSign por e-mail e nome" onClick={async () => { setScanning(true); try { const r = await api.post<{ gmail: number; docusign: number; avisos: string[] }>(`/clients/${c.id}/scan`); toast(r.avisos.length ? `Varredura parcial: ${r.avisos.join('; ')}` : `Achou ${r.gmail} thread(s) de e-mail e ligou ${r.docusign} waiver(s).`, r.avisos.length ? undefined : 'ok'); reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setScanning(false) } }}>{scanning ? <span className="spin" /> : '⌕'} Buscar nas plataformas</button>}
        {can('OPERATOR') && <button className="btn" onClick={openEdit}>Editar</button>}
        {can('OPERATOR') && <button className="btn primary" onClick={() => { onClose?.(); nav('/ai', { state: { ask: `Sobre o cliente ${c.name}${c.pilot_name ? ` (piloto ${c.pilot_name})` : ''}: ` } }) }}>Perguntar à IA</button>}
      </div>
    </div>
    {risco && <div className="banner crit"><b>Serviço em {dias === 0 ? 'HOJE' : `${dias} dia(s)`} sem waiver assinada.</b> {wBad ? `O e-mail ${wBad.signer_email} devolveu: corrija e reenvie.` : wOpen ? `Envelope ${WAIVER_LABEL[wOpen.status!]}; cobre a assinatura.` : 'Nenhum envelope enviado.'}</div>}
    {!!c.vip && <div className="banner info">Cliente VIP: dispensa waiver por decisão do dono (04/09/2026). Nada de cobrança automática.</div>}
    <div className="grid g4">
      <div className="card kpi"><div className="lbl">Próximo serviço</div><div className="val" style={{ fontSize: 22 }}>{prox ? fmtDate(prox.due_on) : '—'}</div><div className="foot truncate">{prox?.title || 'nada agendado'}</div></div>
      <div className="card kpi"><div className="lbl">Waiver</div><div className="val" style={{ fontSize: 22, color: wOk ? 'var(--ok)' : wBad ? 'var(--crit)' : 'var(--warn)' }}>{c.vip ? 'dispensada' : wOk ? 'assinada' : wBad ? 'devolveu' : wOpen ? WAIVER_LABEL[wOpen.status!] : 'nenhuma'}</div><div className="foot">{wOk?.expires_at ? `expira ${fmtDate(wOk.expires_at)}` : wOpen?.expires_at ? `expira ${fmtDate(wOpen.expires_at)}` : ''}</div></div>
      <div className="card kpi"><div className="lbl">Serviços abertos</div><div className="val">{data.tasks.filter(t => t.status === 'open').length}</div><div className="foot">{data.tasks.length} no total</div></div>
      <div className="card kpi"><div className="lbl">E-mails sem tratamento</div><div className="val" style={{ color: data.emails.some(e => !e.handled) ? 'var(--warn)' : undefined }}>{data.emails.filter(e => !e.handled).length}</div><div className="foot">{data.emails.length} threads conhecidas</div></div>
    </div>
    <Section title="Dados do cliente">
      <div className="grid g2">
        <dl className="dl"><dt>Piloto</dt><dd>{c.pilot_name || <span className="muted">— (o próprio)</span>}</dd><dt>Nascimento</dt><dd className="mono">{fmtDate(c.pilot_dob)}</dd>
          <dt>Responsável</dt><dd>{c.name}</dd><dt>Empresa</dt><dd>{c.company || '—'}</dd></dl>
        <dl className="dl"><dt>E-mail</dt><dd>{c.email ? <a href={`mailto:${c.email}`}>{c.email}</a> : '—'}</dd><dt>Telefone</dt><dd>{c.phone ? <a href={`tel:${c.phone}`}>{c.phone}</a> : '—'}</dd>
          <dt>Etapa</dt><dd>{data.stages.find(s => s.code === c.stage_code)?.label || c.stage_code || '—'}</dd><dt>Origem</dt><dd>{c.source || '—'} · desde {fmtDate(c.created_at)}</dd><dt>Varrido</dt><dd className="mono small">{c.scanned_at ? fmtDateTime(c.scanned_at) : 'nunca'}</dd></dl>
      </div>
    </Section>
    {edit && <Section title="Editar cliente">
      <div className="grid g3">
        <div className="field"><label>Status</label><select className="input" value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}>{['ACTIVE', 'NEW', 'PENDING', 'AT_RISK', 'COMPLETED', 'INACTIVE'].map(s => <option key={s}>{s}</option>)}</select></div>
        <div className="field"><label>Etapa</label><select className="input" value={form.stage_code} onChange={e => setForm({ ...form, stage_code: e.target.value })}><option value="">—</option>{data.stages.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}</select></div>
        <div className="field"><label>VIP</label><label className="check"><input type="checkbox" disabled={!can('MANAGER')} checked={form.vip} onChange={e => setForm({ ...form, vip: e.target.checked })} /> dispensa waiver {!can('MANAGER') && <span className="muted">(só gerente)</span>}</label></div>
      </div>
      <div className="field" style={{ marginTop: 12 }}><label>Notas</label><textarea className="input" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></div>
      <div className="row" style={{ marginTop: 12, justifyContent: 'flex-end' }}><button className="btn" onClick={() => setEdit(false)}>Cancelar</button><button className="btn primary" disabled={saving} onClick={save}>{saving ? <span className="spin" /> : 'Salvar'}</button></div>
    </Section>}
    {c.notes && !edit && <div className="card card-b small" style={{ whiteSpace: 'pre-wrap' }}><b>Notas:</b> {c.notes}</div>}
    <div className="tabs">
      {(['timeline', 'tasks', 'waivers', 'emails', 'invoices', 'ai'] as const).map(t => <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
        {{ timeline: 'Linha do tempo', tasks: `Serviços (${data.tasks.length})`, waivers: `Waivers (${data.waivers.length})`, emails: `E-mails (${data.emails.length})`, invoices: data.invoices === null ? 'Invoices 🔒' : `Invoices (${data.invoices.length})`, ai: `IA (${data.ai_actions.length})` }[t]}
      </button>)}
    </div>
    <div className="card card-b">
      {tab === 'timeline' && (data.timeline.length === 0 ? <Empty>Nenhum evento ainda.</Empty> : <div className="tl">{data.timeline.map((e, i) => {
        const [lbl, tone] = KIND[e.kind] || [e.kind, '']
        return <div className="ev" key={i}><div className="d">{fmtDate(e.at)}</div><div className={`p ${tone}`} /><div><span className="small muted cond">{lbl}</span> · {e.title} <Chip tone={statusTone(e.status)}>{e.status}</Chip></div></div>
      })}</div>)}
      {tab === 'tasks' && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Data</th><th>Serviço</th><th>Coluna</th><th>Status</th><th>Subtarefas</th><th></th></tr></thead><tbody>
        {data.tasks.length === 0 && <tr><td colSpan={6}><Empty>Sem serviços vinculados.</Empty></td></tr>}
        {data.tasks.map(t => <tr key={t.id}><td className="mono">{fmtDate(t.due_on)}</td><td>{t.title}</td><td>{t.section}</td><td><Chip tone={statusTone(t.status === 'open' ? 'PENDING' : 'COMPLETED')}>{t.status}</Chip></td><td className="mono">{t.subtasks_total ? `${t.subtasks_done ?? 0}/${t.subtasks_total}` : '—'}</td><td>{t.links?.map(l => <Ext key={l.external_id} href={l.deep_link}>{l.system}</Ext>)}</td></tr>)}
      </tbody></table></div>}
      {tab === 'waivers' && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Signatário</th><th>Modelo</th><th>Status</th><th>Enviada</th><th>Assinada</th><th>Expira</th><th></th></tr></thead><tbody>
        {data.waivers.length === 0 && <tr><td colSpan={7}><Empty>Nenhum envelope para este e-mail.</Empty></td></tr>}
        {data.waivers.map(w => <tr key={w.id}><td>{w.signer_name}<div className="small muted">{w.signer_email}</div></td><td>{w.template}</td><td><Chip tone={statusTone(w.status)}>{WAIVER_LABEL[w.status || ''] || w.status}</Chip></td><td className="mono">{fmtDate(w.sent_at)}</td><td className="mono">{fmtDate(w.completed_at)}</td><td className="mono">{fmtDate(w.expires_at)}</td><td className="nowrap">{w.status === 'completed' && <a className="btn sm" href={`/ops/api/waivers/${w.id}/download`} title="Baixar PDF assinado">⬇ PDF</a>} {w.links?.map(l => <Ext key={l.external_id} href={l.deep_link}>{l.system}</Ext>)}</td></tr>)}
      </tbody></table></div>}
      {tab === 'emails' && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Quando</th><th>Caixa</th><th>Assunto</th><th>De</th><th>Prioridade</th><th>Tratado</th><th></th></tr></thead><tbody>
        {data.emails.length === 0 && <tr><td colSpan={7}><Empty>Nenhum e-mail vinculado.</Empty></td></tr>}
        {data.emails.map(e => <tr key={e.id}><td className="mono">{fmtDateTime(e.last_at)}</td><td>{e.mailbox}@</td><td>{e.subject}</td><td className="small">{e.sender}</td><td>{e.priority && <Chip tone={statusTone(e.priority === 'CRITICAL' ? 'ERROR' : e.priority === 'HIGH' ? 'PENDING' : 'ACTIVE')}>{e.priority}</Chip>}</td><td>{e.handled ? '✓' : <span style={{ color: 'var(--warn)' }}>não</span>}</td><td>{e.links?.map(l => <Ext key={l.external_id} href={l.deep_link}>abrir</Ext>)}</td></tr>)}
      </tbody></table></div>}
      {tab === 'invoices' && (data.invoices === null ? <Empty title="Financeiro restrito">Invoices são visíveis para gerentes e administradores.</Empty> :
        data.invoices.length === 0 ? <Empty>Nenhuma invoice. QuickBooks está em stand-by; nada é inventado aqui.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Nº</th><th>Emitida</th><th>Vence</th><th>Valor</th><th>Saldo</th><th>Status</th></tr></thead><tbody>
          {data.invoices.map(i => <tr key={i.id}><td className="mono">{i.number}</td><td className="mono">{fmtDate(i.issued_on)}</td><td className="mono">{fmtDate(i.due_on)}</td><td className="mono">{money(i.amount)}</td><td className="mono">{money(i.balance)}</td><td><Chip tone={statusTone(i.status)}>{i.status}</Chip></td></tr>)}
        </tbody></table></div>)}
      {tab === 'ai' && (data.ai_actions.length === 0 ? <Empty>A IA ainda não propôs nada para este cliente.</Empty> :
        <div className="acts">{data.ai_actions.map(a => <div className="act" key={a.id}><span className="what">{a.action}</span><Chip tone={statusTone(a.policy)}>{POLICY_LABEL[a.policy]}</Chip><Chip tone={statusTone(a.status)}>{a.status}</Chip><span className="small muted">{fmtDateTime(a.created_at)}</span>{a.reason && <div className="small ink2" style={{ width: '100%' }}>{a.reason}</div>}</div>)}</div>)}
    </div>
  </>
}
