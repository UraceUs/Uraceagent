import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { CatalogoEditor } from './Garage'
import { UnirModal } from '../components/Unir'
import type { Catalog, Client360 as C360, Monthly, Race } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, POLICY_LABEL, Section, SysLink, WAIVER_LABEL, statusTone } from '../components/ui'
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
  SERVICE: ['Serviço', 'info'], WAIVER_SENT: ['Waiver enviada', 'warn'], WAIVER_SIGNED: ['Waiver assinada', 'ok'], EMAIL: ['E-mail', ''], AI_ACTION: ['Ação da IA', 'info'], INVOICE: ['Invoice', 'ok'],
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
  const [tab, setTab] = useState<'timeline' | 'monthly' | 'equip' | 'races' | 'tasks' | 'waivers' | 'emails' | 'invoices' | 'ai'>('timeline')
  const [proBusy, setProBusy] = useState(false)
  const [unir, setUnir] = useState(false)
  const monthly = useGet<Monthly>(id && tab === 'monthly' ? `/clients/${id}/monthly` : null)
  const catalog = useGet<Catalog>(id && tab === 'equip' ? '/catalog' : null)
  const corridas = useGet<Race[]>(id && tab === 'races' ? `/races?client_id=${id}&all=true` : null)
  const [edit, setEdit] = useState(false)
  const [form, setForm] = useState({ status: '', stage_code: '', notes: '', vip: false, monthly_plan: '', monthly_note: '', plan_type: '', pro_driver: false })
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

  async function togglePro() {
    const vai = !c.pro_driver
    if (!window.confirm(vai ? `Tornar ${c.pilot_name || c.name} um ★ Pro Racing Driver?\n\nEle vai para a aba Pro Racing Drivers e o card ganha Equipamento e Corridas.` : `Tirar ${c.pilot_name || c.name} de Pro Racing Driver?`)) return
    setProBusy(true)
    try { await api.patch(`/clients/${c.id}/profile`, { pro_driver: vai }); toast(vai ? 'Agora é Pro Racing Driver.' : 'Saiu de Pro Racing Driver.', 'ok'); if (!vai && (tab === 'equip' || tab === 'races')) setTab('timeline'); reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setProBusy(false) }
  }
  function openEdit() { setForm({ status: c.status, stage_code: c.stage_code || '', notes: c.notes || '', vip: !!c.vip, monthly_plan: c.monthly_plan || '', monthly_note: c.monthly_note || '', plan_type: c.plan_type || '', pro_driver: !!c.pro_driver }); setEdit(true) }
  async function save() {
    setSaving(true)
    try {
      const body: Record<string, unknown> = { status: form.status, stage_code: form.stage_code || null, notes: form.notes, monthly_plan: form.monthly_plan || null, monthly_note: form.monthly_note || null }
      if (can('MANAGER')) body.vip = form.vip
      await api.patch(`/clients/${c.id}`, body)
      const perfil: Record<string, unknown> = { plan_type: form.plan_type }
      if (can('MANAGER')) perfil.pro_driver = form.pro_driver
      await api.patch(`/clients/${c.id}/profile`, perfil)
      toast('Cliente atualizado.', 'ok'); setEdit(false); reload()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setSaving(false) }
  }

  const anos = idade(c.pilot_dob)
  const menor = anos !== null && anos < 18
  const ultimo = data.last_service
  const emailsAbertos = data.emails.filter(e => !e.handled).length
  const abertos = data.tasks.filter(t => t.status === 'open').length
  return <>
    <div className="c360-h">
      <div className="who">
        {!onClose && <div className="small"><a onClick={() => nav(-1)} style={{ cursor: 'pointer' }}>← voltar</a></div>}
        <div className="row wrap" style={{ gap: 10 }}>
          {!!c.pro_driver && <span className="star" title="Pro Racing Driver">★</span>}
          <h1 className="h1" style={{ fontSize: 32 }}>{c.pilot_name || c.name}</h1>
          <Chip tone={statusTone(c.status)} dot>{c.status}</Chip>
          {c.plan_type === 'monthly' && <Chip tone="accent">Academy Monthly</Chip>}{c.plan_type === 'daily' && <Chip tone="outline">Academy Day</Chip>}
          {!!c.vip && <Chip tone="warn">VIP</Chip>}
        </div>
        <div className="meta">
          {c.pilot_name && c.pilot_name !== c.name && <span><span className="k">responsável</span> <b>{c.name}</b></span>}
          {anos !== null && <span><span className="k">idade</span> <b>{anos}</b>{menor && <Chip tone="warn">menor · waiver parental</Chip>}</span>}
          {c.email ? <span><span className="k">e-mail</span> <a href={`mailto:${c.email}`}>{c.email}</a>{c.email_alt && <> <span className="muted">·</span> <a href={`mailto:${c.email_alt}`}>{c.email_alt}</a></>}</span> : <span className="muted">sem e-mail</span>}
          {c.phone && <span><span className="k">tel</span> <a href={`tel:${c.phone}`}>{c.phone}</a></span>}
          {c.company && <span><span className="k">empresa</span> {c.company}</span>}
        </div>
      </div>
      <div className="c360-acts">
        {can('OPERATOR') && <button className="btn primary" onClick={() => { onClose?.(); nav('/ai', { state: { ask: `Sobre o cliente ${c.name}${c.pilot_name ? ` (piloto ${c.pilot_name})` : ''}: ` } }) }}>✦ Perguntar à IA</button>}
        {can('MANAGER') && <button className={`btn${c.pro_driver ? '' : ''}`} disabled={proBusy} onClick={togglePro} title={c.pro_driver ? 'Tirar de Pro Racing Driver' : 'Vai para a aba Pro Racing Drivers e libera equipamento e corridas'}>{proBusy ? <span className="spin" /> : c.pro_driver ? '★ Pro Racing Driver' : '☆ Tornar Pro'}</button>}
        {can('OPERATOR') && <button className="btn" onClick={openEdit}>Editar</button>}
        {can('OPERATOR') && <details className="more"><summary className="btn" title="Mais ações">⋯</summary><div className="menu">
          <button className="btn ghost sm" disabled={scanning} onClick={async () => { setScanning(true); try { const r = await api.post<{ gmail: number; docusign: number; avisos: string[] }>(`/clients/${c.id}/scan`); toast(r.avisos.length ? `Varredura parcial: ${r.avisos.join('; ')}` : `Achou ${r.gmail} thread(s) de e-mail e ligou ${r.docusign} waiver(s).`, r.avisos.length ? undefined : 'ok'); reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setScanning(false) } }}>{scanning ? <span className="spin" /> : '⌕'} Buscar no Gmail e DocuSign</button>
          <button className="btn ghost sm" onClick={() => setUnir(true)}>⧉ Unir com outro card</button>
        </div></details>}
      </div>
    </div>
    {risco && <div className="banner crit"><b>Serviço em {dias === 0 ? 'HOJE' : `${dias} dia(s)`} sem waiver assinada.</b> {wBad ? `O e-mail ${wBad.signer_email} devolveu: corrija e reenvie.` : wOpen ? `Envelope ${WAIVER_LABEL[wOpen.status!]}; cobre a assinatura.` : 'Nenhum envelope enviado.'}</div>}
    {!!c.vip && <div className="banner info">Cliente VIP: dispensa waiver por decisão do dono (04/09/2026). Nada de cobrança automática.</div>}
    <div className="grid g5 c360-k">
      <div className="card kpi"><div className="lbl">Próximo serviço</div><div className="val" style={{ fontSize: 22 }}>{prox ? fmtDate(prox.due_on) : '—'}</div><div className="foot truncate" title={prox?.title || ''}>{prox ? <>{prox.title} <SysLink links={prox.links} one /></> : 'nada agendado'}</div></div>
      <div className="card kpi"><div className="lbl">Último serviço</div><div className="val" style={{ fontSize: 22 }}>{ultimo ? fmtDate(ultimo.due_on) : '—'}</div><div className="foot truncate" title={ultimo?.title || ''}>{ultimo ? <>{ultimo.title} <SysLink links={ultimo.links} one /></> : 'nenhum concluído'}</div></div>
      <div className="card kpi"><div className="lbl">Waiver</div><div className={`val ${wOk || c.vip ? 'ok' : wBad ? 'crit' : 'warn'}`} style={{ fontSize: 22 }}>{c.vip ? 'dispensada' : wOk ? 'assinada' : wBad ? 'devolveu' : wOpen ? WAIVER_LABEL[wOpen.status!] : 'nenhuma'}</div><div className="foot">{wOk?.expires_at ? <>vale até {fmtDate(wOk.expires_at)} </> : wOpen?.expires_at ? <>expira {fmtDate(wOpen.expires_at)} </> : ''}<SysLink links={(wOk || wOpen || wBad)?.links} one /></div></div>
      <div className="card kpi"><div className="lbl">Serviços</div><div className="val">{abertos}<span className="of">/{data.tasks.length}</span></div><div className="foot">{abertos === 1 ? '1 aberto' : `${abertos} abertos`} · {data.tasks.length - abertos} concluídos</div></div>
      {data.invoices !== null
        ? <div className="card kpi"><div className="lbl">Em aberto (QBO)</div><div className={`val ${(data.open_balance || 0) > 0 ? 'warn' : 'ok'}`} style={{ fontSize: 22 }}>{money(data.open_balance || 0)}</div><div className="foot">{data.invoices.length} invoice(s) · {emailsAbertos ? <span style={{ color: 'var(--warn)' }}>{emailsAbertos} e-mail(s) sem resposta</span> : 'e-mails em dia'}</div></div>
        : <div className="card kpi"><div className="lbl">E-mails</div><div className={`val ${emailsAbertos ? 'warn' : ''}`}>{emailsAbertos}</div><div className="foot">sem resposta · {data.emails.length} conhecidos</div></div>}
    </div>
    <details className="card c360-d"><summary className="card-h" style={{ cursor: 'pointer' }}><h2 className="h2">Dados completos</h2><span className="grow" /><span className="small muted">{c.source || '—'} · desde {fmtDate(c.created_at)}{c.scanned_at && <> · varrido {fmtDateTime(c.scanned_at)}</>}</span></summary>
      <div className="card-b grid g3">
        <dl className="dl"><dt>Piloto</dt><dd>{c.pilot_name || <span className="muted">o próprio</span>}</dd><dt>Nascimento</dt><dd className="mono">{fmtDate(c.pilot_dob)}</dd><dt>Responsável</dt><dd>{c.name}</dd></dl>
        <dl className="dl"><dt>E-mail</dt><dd>{c.email ? <a href={`mailto:${c.email}`}>{c.email}</a> : '—'}{c.email_alt && <div className="small"><a href={`mailto:${c.email_alt}`}>{c.email_alt}</a></div>}</dd><dt>Telefone</dt><dd>{c.phone ? <a href={`tel:${c.phone}`}>{c.phone}</a> : '—'}</dd><dt>Empresa</dt><dd>{c.company || '—'}</dd></dl>
        <dl className="dl"><dt>Plano mensal</dt><dd>{c.monthly_plan || <span className="muted">—</span>}{c.monthly_note && <div className="small muted">{c.monthly_note}</div>}</dd><dt>Etapa</dt><dd>{data.stages.find(s => s.code === c.stage_code)?.label || c.stage_code || '—'}</dd><dt>Tipo</dt><dd>{c.plan_type === 'monthly' ? 'Academy Monthly' : c.plan_type === 'daily' ? 'Academy Day' : '—'}{!!c.pro_driver && ' · ★ Pro'}</dd></dl>
      </div>
    </details>
    {edit && <Section title="Editar cliente">
      <div className="grid g3">
        <div className="field"><label>Status</label><select className="input" value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}>{['ACTIVE', 'NEW', 'PENDING', 'AT_RISK', 'COMPLETED', 'INACTIVE'].map(s => <option key={s}>{s}</option>)}</select></div>
        <div className="field"><label>Etapa</label><select className="input" value={form.stage_code} onChange={e => setForm({ ...form, stage_code: e.target.value })}><option value="">—</option>{data.stages.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}</select></div>
        <div className="field"><label>VIP</label><label className="check"><input type="checkbox" disabled={!can('MANAGER')} checked={form.vip} onChange={e => setForm({ ...form, vip: e.target.checked })} /> dispensa waiver {!can('MANAGER') && <span className="muted">(só gerente)</span>}</label></div>
      </div>
      <div className="grid g2" style={{ marginTop: 12 }}>
        <div className="field"><label>Tipo de piloto</label><select className="input" value={form.plan_type} onChange={e => setForm({ ...form, plan_type: e.target.value })}><option value="">não definido</option><option value="monthly">Urace Academy Monthly (mensal)</option><option value="daily">Urace Academy Day (diária)</option></select></div>
        <div className="field"><label>★ Pro Racing Driver</label><label className="check"><input type="checkbox" disabled={!can('MANAGER')} checked={form.pro_driver} onChange={e => setForm({ ...form, pro_driver: e.target.checked })} /> pronto para ser convidado para corridas {!can('MANAGER') && <span className="muted">(só gerente)</span>}</label></div>
        <div className="field"><label>Plano mensal (gera a invoice do dia 1)</label><select className="input" value={form.monthly_plan} onChange={e => setForm({ ...form, monthly_plan: e.target.value })}><option value="">sem plano mensal</option>{['Academy Baby Kart', 'Academy 4 stroke', 'Academy 2 stroke', 'Academy kart próprio', 'Academy kart próprio + mecânico', 'Contrato 6 meses', 'Contrato 12 meses'].map(x => <option key={x}>{x}</option>)}</select></div>
        <div className="field"><label>Ajustes do plano</label><input className="input" value={form.monthly_note} onChange={e => setForm({ ...form, monthly_note: e.target.value })} placeholder="ex.: 1 sessão extra em setembro; treino fora do OKC" /></div>
      </div>
      <div className="field" style={{ marginTop: 12 }}><label>Notas</label><textarea className="input" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></div>
      <div className="row" style={{ marginTop: 12, justifyContent: 'flex-end' }}><button className="btn" onClick={() => setEdit(false)}>Cancelar</button><button className="btn primary" disabled={saving} onClick={save}>{saving ? <span className="spin" /> : 'Salvar'}</button></div>
    </Section>}
    {c.notes && !edit && <div className="card card-b small" style={{ whiteSpace: 'pre-wrap' }}><b>Notas:</b> {c.notes}</div>}
    <div className="tabs">
      {(['timeline', 'monthly', 'equip', 'races', 'tasks', 'waivers', 'emails', 'invoices', 'ai'] as const).filter(t => c.pro_driver || (t !== 'equip' && t !== 'races')).map(t => <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
        {{ timeline: 'Linha do tempo', monthly: 'Mensalidade e contrato', equip: '★ Equipamento', races: `★ Corridas`, tasks: `Serviços (${data.tasks.length})`, waivers: `Waivers (${data.waivers.length})`, emails: `E-mails (${data.emails.length})`, invoices: data.invoices === null ? 'Invoices 🔒' : `Invoices (${data.invoices.length})`, ai: `IA (${data.ai_actions.length})` }[t]}
      </button>)}
    </div>
    <div className="card card-b">
      {tab === 'timeline' && (data.timeline.length === 0 ? <Empty>Nenhum evento ainda.</Empty> : <div className="tl">{data.timeline.map((e, i) => {
        const [lbl, tone] = KIND[e.kind] || [e.kind, '']
        const mes = (e.at || '').slice(0, 7); const antes = (data.timeline[i - 1]?.at || '').slice(0, 7)
        return <div key={i}>
          {mes !== antes && <div className="tl-m">{mes ? new Date(mes + '-02T12:00:00').toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' }) : 'sem data'}</div>}
          <div className="ev"><div className="d">{fmtDate(e.at)}</div><div className={`p ${tone}`} /><div className="b">
            <div className="row wrap" style={{ gap: 8 }}><span className={`kind ${tone}`}>{lbl}</span><span className="t">{e.title}</span><Chip tone={statusTone(e.status)}>{e.status}</Chip><span className="grow" /><SysLink links={e.links} /></div>
            {e.detail && <div className="small muted">{e.detail}</div>}
          </div></div>
        </div>
      })}</div>)}
      {tab === 'monthly' && <Mensalidade id={c.id} m={monthly.data} loading={monthly.loading} reload={monthly.reload} plan={c.plan_type} fin={can('MANAGER')} />}
      {tab === 'equip' && <Equipamento c={c} cat={catalog.data} reload={() => { reload(); catalog.reload() }} />}
      {unir && <UnirModal keep={c} onClose={() => setUnir(false)} onDone={(kid) => { if (kid !== c.id) nav(`/clients/${kid}`); else reload() }} />}
      {tab === 'races' && <CorridasDoPiloto rs={corridas.data} loading={corridas.loading} cid={c.id} />}
      {tab === 'tasks' && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Data</th><th>Serviço</th><th>Coluna</th><th>Status</th><th>Subtarefas</th><th></th></tr></thead><tbody>
        {data.tasks.length === 0 && <tr><td colSpan={6}><Empty>Sem serviços vinculados.</Empty></td></tr>}
        {data.tasks.map(t => <tr key={t.id}><td className="mono">{fmtDate(t.due_on)}</td><td>{t.title}</td><td>{t.section}</td><td><Chip tone={statusTone(t.status === 'open' ? 'PENDING' : 'COMPLETED')}>{t.status}</Chip></td><td className="mono">{t.subtasks_total ? `${t.subtasks_done ?? 0}/${t.subtasks_total}` : '—'}</td><td><SysLink links={t.links} /></td></tr>)}
      </tbody></table></div>}
      {tab === 'waivers' && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Signatário</th><th>Modelo</th><th>Status</th><th>Enviada</th><th>Assinada</th><th>Expira</th><th></th></tr></thead><tbody>
        {data.waivers.length === 0 && <tr><td colSpan={7}><Empty>Nenhum envelope para este e-mail.</Empty></td></tr>}
        {data.waivers.map(w => <tr key={w.id}><td>{w.signer_name}<div className="small muted">{w.signer_email}</div></td><td>{w.template}</td><td><Chip tone={statusTone(w.status)}>{WAIVER_LABEL[w.status || ''] || w.status}</Chip></td><td className="mono">{fmtDate(w.sent_at)}</td><td className="mono">{fmtDate(w.completed_at)}</td><td className="mono">{fmtDate(w.expires_at)}</td><td className="nowrap">{w.status === 'completed' && <a className="btn sm" href={`/ops/api/waivers/${w.id}/download`} title="Baixar PDF assinado">⬇ PDF</a>} <SysLink links={w.links} /></td></tr>)}
      </tbody></table></div>}
      {tab === 'emails' && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Quando</th><th>Caixa</th><th>Assunto</th><th>De</th><th>Prioridade</th><th>Tratado</th><th></th></tr></thead><tbody>
        {data.emails.length === 0 && <tr><td colSpan={7}><Empty>Nenhum e-mail vinculado.</Empty></td></tr>}
        {data.emails.map(e => <tr key={e.id}><td className="mono">{fmtDateTime(e.last_at)}</td><td>{e.mailbox}@</td><td>{e.subject}</td><td className="small">{e.sender}</td><td>{e.priority && <Chip tone={statusTone(e.priority === 'CRITICAL' ? 'ERROR' : e.priority === 'HIGH' ? 'PENDING' : 'ACTIVE')}>{e.priority}</Chip>}</td><td>{e.handled ? '✓' : <span style={{ color: 'var(--warn)' }}>não</span>}</td><td><SysLink links={e.links} /></td></tr>)}
      </tbody></table></div>}
      {tab === 'invoices' && (data.invoices === null ? <Empty title="Financeiro restrito">Invoices são visíveis para gerentes e administradores.</Empty> :
        data.invoices.length === 0 ? <Empty>Nenhuma invoice. QuickBooks está em stand-by; nada é inventado aqui.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Nº</th><th>Emitida</th><th>Vence</th><th>Valor</th><th>Saldo</th><th>Status</th></tr></thead><tbody>
          {data.invoices.map(i => <tr key={i.id}><td className="mono">{i.doc_number}</td><td className="mono">{fmtDate(i.issued_on)}</td><td className="mono">{fmtDate(i.due_on)}</td><td className="mono">{money(i.amount)}</td><td className="mono">{money(i.balance)}</td><td><Chip tone={statusTone(i.status)}>{i.status}</Chip></td></tr>)}
        </tbody></table></div>)}
      {tab === 'ai' && (data.ai_actions.length === 0 ? <Empty>A IA ainda não propôs nada para este cliente.</Empty> :
        <div className="acts">{data.ai_actions.map(a => <div className="act" key={a.id}><span className="what">{a.action}</span><Chip tone={statusTone(a.policy)}>{POLICY_LABEL[a.policy]}</Chip><Chip tone={statusTone(a.status)}>{a.status}</Chip><span className="small muted">{fmtDateTime(a.created_at)}</span>{a.reason && <div className="small ink2" style={{ width: '100%' }}>{a.reason}</div>}</div>)}</div>)}
    </div>
  </>
}


function Mensalidade({ id, m, loading, reload, plan, fin }: { id: number; m: Monthly | null; loading: boolean; reload: () => void; plan?: string | null; fin: boolean }) {
  const { can } = useAuth()
  const toast = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  async function upload() {
    if (!file) return
    setBusy(true)
    try {
      const fd = new FormData(); fd.append('file', file); fd.append('title', file.name)
      const csrf = document.cookie.match(/(?:^|;\s*)cc_csrf=([^;]+)/)?.[1] || ''
      const res = await fetch(`/ops/api/clients/${id}/contract`, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-CSRF': decodeURIComponent(csrf) } })
      if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(j.detail || `HTTP ${res.status}`) }
      toast('Contrato guardado.', 'ok'); setFile(null); reload()
    } catch (e) { toast((e as Error).message, 'crit') } finally { setBusy(false) }
  }
  if (loading && !m) return <Loading />
  if (!m) return null
  const mesNome = (k: string) => new Date(k + '-15T12:00:00Z').toLocaleDateString('pt-BR', { month: 'long', year: 'numeric', timeZone: 'UTC' })
  return <div className="stack">
    {plan !== 'monthly' && <Banner tone="info">Este piloto não está marcado como Academy Monthly. Marque em Editar → Tipo de piloto para o dia 1 gerar a mensalidade.</Banner>}
    <div className="grid g3">
      <div className="card kpi"><div className="lbl">Última mensalidade</div><div className="val" style={{ fontSize: 24 }}>{fin ? (m.last_monthly_amount != null ? money(m.last_monthly_amount) : '—') : '🔒'}</div><div className="foot truncate" title={m.last_monthly_memo || ''}>{m.last_monthly_memo || 'nenhuma invoice de Academy encontrada'}</div></div>
      <div className="card kpi"><div className="lbl">Sessões este mês</div><div className="val">{m.months[0]?.sessions_used ?? 0}<span className="muted" style={{ fontSize: 18 }}> / {m.sessions_per_month}</span></div><div className="foot">{m.months[0]?.sessions_left ?? 0} restante(s)</div></div>
      <div className="card kpi"><div className="lbl">Invoice do mês</div><div className={`val ${m.months[0]?.invoice ? 'ok' : 'warn'}`} style={{ fontSize: 22 }}>{m.months[0]?.invoice ? (m.months[0].invoice.status || 'emitida') : 'falta'}</div><div className="foot">{m.months[0]?.invoice?.doc_number || (m.months[0]?.needs_invoice ? 'a IA monta no dia 1, você aprova' : '')}</div></div>
    </div>
    <Section title="Meses" tight><div className="tbl-wrap"><table className="tbl"><thead><tr><th>Mês</th><th>Invoice</th><th>Sessões usadas</th><th>Restantes</th><th>Situação</th></tr></thead><tbody>
      {m.months.map(x => <tr key={x.month}><td style={{ textTransform: 'capitalize' }}>{mesNome(x.month)}</td>
        <td>{x.invoice ? <><span className="mono">{x.invoice.doc_number}</span> <Chip tone={statusTone(x.invoice.status === 'open' ? 'PENDING' : x.invoice.status)}>{x.invoice.status}</Chip>{fin && x.invoice.amount != null && <span className="mono"> {money(x.invoice.amount)}</span>}<div className="small muted">{x.invoice.memo}</div></> : <span className="muted">—</span>}</td>
        <td className="mono">{x.sessions_used}{x.sessions.length > 0 && <div className="small muted">{x.sessions.map(s => fmtDate(s.due_on)).join(' · ')}</div>}</td><td className="mono">{x.sessions_left}</td>
        <td>{x.needs_invoice ? <Chip tone="warn">falta invoice</Chip> : x.invoice ? <Chip tone="ok">ok</Chip> : <span className="muted">sem uso</span>}</td></tr>)}
    </tbody></table></div></Section>
    <Section title="Contrato da Academy" count={m.contracts.length}>
      {m.contracts.length === 0 ? <div className="small muted">Nenhum contrato. Use "Buscar nas plataformas" para achar no DocuSign (assunto com Academy/contract) ou suba o PDF abaixo.</div> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Contrato</th><th>Origem</th><th>Status</th><th>Assinado</th><th></th></tr></thead><tbody>
          {m.contracts.map(k => <tr key={k.id}><td>{k.title}</td><td>{k.source === 'docusign' ? 'DocuSign' : `upload (${k.added_by_name || ''})`}</td><td><Chip tone={statusTone(k.status)}>{k.status || '—'}</Chip></td><td className="mono">{fmtDate(k.signed_at)}</td><td><a className="btn sm" href={`/ops/api/contracts/${k.id}/download`}>⬇ PDF</a></td></tr>)}
        </tbody></table></div>}
      {can('OPERATOR') && <div className="row wrap" style={{ marginTop: 10 }}><input className="input" type="file" accept=".pdf,image/*" style={{ maxWidth: 360 }} onChange={e => setFile(e.target.files?.[0] || null)} /><button className="btn" disabled={!file || busy} onClick={upload}>{busy ? <span className="spin" /> : 'Subir contrato'}</button></div>}
    </Section>
  </div>
}

function Equipamento({ c, cat, reload }: { c: { id: number; chassis_id?: number | null; engine_id?: number | null; equipment_notes?: string | null }; cat: Catalog | null; reload: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const [f, setF] = useState({ chassis_id: c.chassis_id || 0, engine_id: c.engine_id || 0, equipment_notes: c.equipment_notes || '' })
  const [busy, setBusy] = useState(false)
  if (!cat) return <Loading />
  const ch = cat.chassis.find(x => x.id === Number(f.chassis_id)); const en = cat.engines.find(x => x.id === Number(f.engine_id))
  const parts = cat.parts.filter(p => p.engine_id === Number(f.engine_id) && p.active)
  async function save() { setBusy(true); try { await api.patch(`/clients/${c.id}/profile`, { chassis_id: f.chassis_id || null, engine_id: f.engine_id || null, equipment_notes: f.equipment_notes }); toast('Equipamento salvo.', 'ok'); reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) } }
  return <div className="stack">
    <div className="grid g2">
      <div className="field"><label>Chassi</label><select className="input" disabled={!can('OPERATOR')} value={f.chassis_id} onChange={e => setF({ ...f, chassis_id: Number(e.target.value) })}><option value={0}>—</option>{cat.chassis.filter(x => x.active).map(x => <option key={x.id} value={x.id}>{x.brand} {x.model || ''} {x.size ? `(${x.size})` : ''}</option>)}</select></div>
      <div className="field"><label>Motor</label><select className="input" disabled={!can('OPERATOR')} value={f.engine_id} onChange={e => setF({ ...f, engine_id: Number(e.target.value) })}><option value={0}>—</option>{cat.engines.filter(x => x.active).map(x => <option key={x.id} value={x.id}>{x.brand} {x.model} {x.stroke ? `· ${x.stroke}` : ''}</option>)}</select></div>
    </div>
    <div className="grid g2">
      {ch && <div className="card card-b"><div className="h2">Chassi</div>{ch.image_path && <img src={`/ops/api/catalog/chassis/${ch.id}/image`} alt="" style={{ maxHeight: 140, borderRadius: 3, margin: '8px 0' }} />}<dl className="dl"><dt>Marca</dt><dd>{ch.brand} {ch.model}</dd><dt>Tamanho</dt><dd>{ch.size || '—'}</dd><dt>Pneu diant.</dt><dd className="mono">{ch.tire_front || '—'}</dd><dt>Pneu tras.</dt><dd className="mono">{ch.tire_rear || '—'}</dd>{ch.notes && <><dt>Notas</dt><dd className="small">{ch.notes}</dd></>}</dl></div>}
      {en && <div className="card card-b"><div className="h2">Motor</div>{en.image_path && <img src={`/ops/api/catalog/engines/${en.id}/image`} alt="" style={{ maxHeight: 140, borderRadius: 3, margin: '8px 0' }} />}<dl className="dl"><dt>Motor</dt><dd>{en.brand} {en.model}</dd><dt>Tempos</dt><dd>{en.stroke || '—'}</dd><dt>Categoria</dt><dd>{en.category || '—'}</dd>{en.notes && <><dt>Notas</dt><dd className="small">{en.notes}</dd></>}</dl>
        <div className="h2" style={{ marginTop: 10 }}>Peças deste motor ({parts.length})</div>{parts.length === 0 ? <div className="small muted">Nenhuma peça cadastrada. Cadastre em Equipamentos.</div> : <ul style={{ margin: '4px 0', paddingLeft: 18 }}>{parts.map(p => <li key={p.id} className="small">{p.name}{p.part_number && <span className="mono muted"> {p.part_number}</span>}{p.price != null && <span className="muted"> · {money(p.price)}</span>}</li>)}</ul>}</div>}
    </div>
    <div className="field"><label>Notas de equipamento</label><textarea className="input" rows={2} disabled={!can('OPERATOR')} value={f.equipment_notes} onChange={e => setF({ ...f, equipment_notes: e.target.value })} placeholder="ajustes, pneus usados, número do chassi, histórico" /></div>
    {can('OPERATOR') && <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn primary" disabled={busy} onClick={save}>{busy ? <span className="spin" /> : 'Salvar equipamento'}</button></div>}
    <details className="card card-b" style={{ marginTop: 4 }}><summary style={{ cursor: 'pointer' }}><b>Cadastrar ou editar chassis, motores e peças</b> <span className="small muted">(catálogo, vale para todos os pilotos)</span></summary>
      <div style={{ marginTop: 10 }}><CatalogoEditor data={cat} reload={reload} /></div></details>
  </div>
}

function CorridasDoPiloto({ rs, loading, cid }: { rs: Race[] | null; loading: boolean; cid: number }) {
  if (loading && !rs) return <Loading />
  const lista = rs || []
  return <div className="stack">
    {lista.length === 0 ? <Empty title="Nenhuma corrida ainda">Convide este piloto no calendário de <Link to="/races">Corridas</Link>.</Empty> : <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Data</th><th>Corrida</th><th>Onde</th><th>Situação</th><th>Prévia</th></tr></thead><tbody>
      {lista.map(r => { const i = r.invited.find(x => x.client_id === cid); return <tr key={r.id}><td className="mono nowrap">{fmtDate(r.date_start)}</td><td><Link to="/races">{r.name}</Link>{!r.active && <span className="small muted"> (fora do calendário)</span>}</td><td className="small">{[r.track, r.city].filter(Boolean).join(' · ') || '—'}</td>
        <td>{i && <Chip tone={statusTone(i.status === 'confirmed' || i.status === 'done' ? 'COMPLETED' : i.status === 'declined' ? 'REJECTED' : 'PENDING')}>{({ invited: 'aguardando confirmação', confirmed: 'confirmado', declined: 'não vai', done: 'correu' } as Record<string, string>)[i.status] || i.status}</Chip>}</td>
        <td className="small">{i?.estimate_text ? <Link to={i.estimate_cmd ? `/ai/${i.estimate_cmd}` : '/races'}>ver prévia</Link> : <span className="muted">—</span>}</td></tr> })}
    </tbody></table></div>}
    <div className="small muted">Convidar, confirmar e pedir a prévia de custo é no calendário de <Link to="/races">Corridas</Link>.</div>
  </div>
}
