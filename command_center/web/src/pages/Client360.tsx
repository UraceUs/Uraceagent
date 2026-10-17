import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { CatalogoEditor } from './Garage'
import { InserirNoTopo } from '../components/Inserir'
import { Cartao, CdItem, CdLista } from '../components/Cartao'
import { LembreteChip, LembreteModal } from './Systems'
import { PecasDoCliente } from './Estoque'
import { CardIrmao, Picker, UnirModal } from '../components/Unir'
import type { Catalog, Client, Client360 as C360, Monthly, Race, Waiver } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, POLICY_LABEL, Scrim, Section, Status, SysLink, WAIVER_LABEL, statusTone } from '../components/ui'
import { daysUntil, fmtDate, fmtDateTime, money } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'
import { TextoComVoz } from '../components/Voz'
import { ESTADO_PEDIDO } from '../components/pedidoSite'
import { tr, LOCALE } from '../i18n'

function idade(dob?: string | null) {
  if (!dob) return null
  const d = new Date(dob.slice(0, 10) + 'T12:00:00Z'); if (isNaN(d.getTime())) return null
  const h = new Date(); let a = h.getFullYear() - d.getFullYear()
  if (h.getMonth() < d.getMonth() || (h.getMonth() === d.getMonth() && h.getDate() < d.getDate())) a--
  return a
}

const KIND: Record<string, [string, 'ok' | 'warn' | 'crit' | 'info' | '']> = {
  SITE_PAYMENT: [tr("Pagamento no site"), 'ok'], SERVICE: [tr("Serviço"), 'info'], WAIVER_SENT: [tr("Waiver enviada"), 'warn'], WAIVER_SIGNED: [tr("Waiver assinada"), 'ok'], WAIVER_VOIDED: [tr("Waiver anulada"), 'crit'], EMAIL: ['E-mail', ''], AI_ACTION: [tr("Ação da IA"), 'info'], INVOICE: [tr("Invoice"), 'ok'],
}

export function Client360() {
  const { id } = useParams()
  return <ClientCard id={Number(id)} />
}

/** Card completo do cliente. Em rota, sem onClose; em janela, com onClose. */
export function ClientCard({ id, onClose }: { id: number; onClose?: () => void }) {
  const nav = useNavigate()
  const { can: podeBase, box } = useAuth()
  // mecânico e coach (#92): veem o card, não editam nem disparam nada daqui
  const can: typeof podeBase = min => !box && podeBase(min)
  const perguntar = usePerguntar()
  const toast = useToast()
  const { data, error, loading, reload } = useGet<C360>(id ? `/clients/${id}` : null)
  const [tab, setTab] = useState<'timeline' | 'monthly' | 'equip' | 'races' | 'pecas' | 'site' | 'tasks' | 'waivers' | 'emails' | 'invoices' | 'ai'>('timeline')
  const [proBusy, setProBusy] = useState(false)
  const [unir, setUnir] = useState(false)
  const [irmao, setIrmao] = useState(false)
  const monthly = useGet<Monthly>(id && tab === 'monthly' ? `/clients/${id}/monthly` : null)
  const catalog = useGet<Catalog>(id && tab === 'equip' ? '/catalog' : null)
  const corridas = useGet<Race[]>(id && tab === 'races' ? `/races?client_id=${id}&all=true` : null)
  const [edit, setEdit] = useState(false)
  const [form, setForm] = useState({ status: '', stage_code: '', notes: '', vip: false, monthly_plan: '', monthly_note: '', plan_type: '', pro_driver: false })
  const [saving, setSaving] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [selInv, setSelInv] = useState<number[]>([])
  const [lemb, setLemb] = useState(false)
  const [renomear, setRenomear] = useState<number | null>(null)
  const [mover, setMover] = useState<number | null>(null)
  async function restaurar(tid: number) {              // #219: o gerente desfaz a exclusão
    try { await api.post(`/tasks/${tid}/restaurar`); toast(tr("Serviço restaurado."), 'ok'); reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  const [qr, setQr] = useState(false)
  if (error && !data) return <ErrorState error={error} retry={reload} />
  if (loading && !data) return <Loading rows={8} />
  if (!data) return null
  const c = data.client
  const vivos = data.tasks.filter(t => !t.deleted_at)      // #219: o excluído fica no histórico, fora das contas
  const prox = vivos.filter(t => t.status === 'open' && t.due_on && (daysUntil(t.due_on) ?? -1) >= 0).sort((a, b) => (a.due_on! < b.due_on! ? -1 : 1))[0]
  const wOk = data.waivers.find(w => w.status === 'completed' && !w.voided_at)       // #109: a anulada não vale
  const wOpen = data.waivers.find(w => w.status === 'sent' || w.status === 'delivered')
  const wBad = data.waivers.find(w => w.status === 'autoresponded')
  const dias = daysUntil(prox?.due_on)
  const risco = !c.vip && prox && !wOk && dias !== null && dias <= 2

  /* #109: a waiver assinada no próprio sistema não vai para a lixeira; o gerente anula com motivo e ela fica no card */
  async function anularWaiver(w: Waiver) {
    const motivo = await perguntar({ titulo: tr("Anular a waiver de {0}?", w.minor_name || w.signer_name || ''), perigo: true, ok: tr("Anular a waiver"),
      texto: tr("A waiver não é apagada nem muda: continua no card e no backup, marcada como anulada, e deixa de valer. O cliente pode assinar outra. Não se desfaz."),
      campo: tr("Motivo (pelo menos 10 letras)") }) as string | null
    if (motivo === null) return
    try { await api.post(`/waivers/${w.id}/void`, { reason: motivo }); toast(tr("Waiver anulada. Ela continua no card e no backup."), 'ok'); reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }

  async function togglePro() {
    const vai = !c.pro_driver
    if (!await perguntar(vai ? { titulo: tr("Tornar {0} um ★ Pro Racing Driver?", c.pilot_name || c.name), texto: tr("Ele vai para a aba Pro Racing Drivers e o card ganha Equipamento e Corridas."), ok: tr("Tornar Pro") } : { titulo: tr("Tirar {0} de Pro Racing Driver?", c.pilot_name || c.name), ok: tr("Tirar") })) return
    setProBusy(true)
    try { await api.patch(`/clients/${c.id}/profile`, { pro_driver: vai }); toast(vai ? tr("Agora é Pro Racing Driver.") : tr("Saiu de Pro Racing Driver."), 'ok'); if (!vai && (tab === 'equip' || tab === 'races')) setTab('timeline'); reload() }
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
      toast(tr("Cliente atualizado."), 'ok'); setEdit(false); reload()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setSaving(false) }
  }

  const anos = idade(c.pilot_dob)
  const menor = anos !== null && anos < 18
  const ultimo = data.last_service
  const emailsAbertos = data.emails.filter(e => !e.handled).length
  const abertos = vivos.filter(t => t.status === 'open').length
  return <>
    <div className="c360-h">
      <div className="who">
        {!onClose && <div className="small"><a onClick={() => nav(-1)} style={{ cursor: 'pointer' }}>{tr("← voltar")}</a></div>}
        <div className="row wrap" style={{ gap: 10 }}>
          {!!c.pro_driver && <span className="star" title={tr("Pro Racing Driver")}>★</span>}
          <h1 className="h1" style={{ fontSize: 32 }}>{c.pilot_name || c.name}</h1>
          <Status s={c.status} />
          {c.plan_type === 'monthly' && <Chip tone="accent">{tr("Academy Monthly")}</Chip>}{c.plan_type === 'daily' && <Chip tone="outline">{tr("Academy Day")}</Chip>}
          {!!c.vip && <Chip tone="warn">{tr("VIP")}</Chip>}
        </div>
        <div className="meta">
          <span><span className="k">{tr("Client ID")}</span> <b className="mono">{c.id}</b></span>
          {c.pilot_name && c.pilot_name !== c.name && <span><span className="k">{tr("responsável")}</span> <b>{c.name}</b></span>}
          {anos !== null && <span><span className="k">{tr("idade")}</span> <b>{anos}</b>{menor && <Chip tone="warn">{tr("menor · waiver parental")}</Chip>}</span>}
          {c.email ? <span><span className="k">{tr("e-mail")}</span> <a href={`mailto:${c.email}`}>{c.email}</a>{c.email_alt && <> <span className="muted">·</span> <a href={`mailto:${c.email_alt}`}>{c.email_alt}</a></>}</span> : <span className="muted">{tr("sem e-mail")}</span>}
          {c.phone && <span><span className="k">{tr("tel")}</span> <a href={`tel:${c.phone}`}>{c.phone}</a></span>}
          {c.company && <span><span className="k">{tr("empresa")}</span> {c.company}</span>}
          {!!data.irmaos?.length && <span><span className="k">{tr("irmão(s)")}</span> {data.irmaos.map(i => <Link key={i.id} className="lchip" to={`/clients/${i.id}`} title={tr("Card do irmão: cada piloto tem o seu")}>{i.pilot_name || i.name}</Link>)}</span>}
        </div>
      </div>
      <div className="c360-acts">
        {can('OPERATOR') && <button className="btn primary" onClick={() => { onClose?.(); nav('/ai', { state: { ask: `Sobre o cliente ${c.name}${c.pilot_name ? ` (piloto ${c.pilot_name})` : ''}: ` } }) }}>{tr("✦ Perguntar à IA")}</button>}
        {can('MANAGER') && <button className={`btn${c.pro_driver ? '' : ''}`} disabled={proBusy} onClick={togglePro} title={c.pro_driver ? tr("Tirar de Pro Racing Driver") : tr("Vai para a aba Pro Racing Drivers e libera equipamento e corridas")}>{proBusy ? <span className="spin" /> : c.pro_driver ? tr("★ Pro Racing Driver") : tr("☆ Tornar Pro")}</button>}
        {(can('OPERATOR') || box) && <button className="btn" onClick={() => setQr(true)} title={tr("O QR que o mecânico lê no balcão")}>{tr("▣ QR do balcão")}</button>}
        {can('OPERATOR') && <button className="btn" onClick={openEdit}>{tr("Editar")}</button>}
        {can('OPERATOR') && <details className="more"><summary className="btn" title={tr("Mais ações")}>⋯</summary><div className="menu">
          <button className="btn ghost sm" disabled={scanning} onClick={async () => { setScanning(true); try { const r = await api.post<{ gmail: number; docusign: number; avisos: string[] }>(`/clients/${c.id}/scan`); toast(r.avisos.length ? tr("Varredura parcial: {0}", r.avisos.join('; ')) : tr("Achou {0} thread(s) de e-mail e ligou {1} waiver(s).", r.gmail, r.docusign), r.avisos.length ? undefined : 'ok'); reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setScanning(false) } }}>{scanning ? <span className="spin" /> : '⌕'} {tr("Buscar no Gmail e DocuSign")}</button>
          <button className="btn ghost sm" onClick={() => setUnir(true)}>{tr("⧉ Unir com outro card")}</button>
          <button className="btn ghost sm" onClick={() => setIrmao(true)}>{tr("+ Card de irmão")}</button>
        </div></details>}
      </div>
    </div>
    {risco && <Banner tone="crit"><b>{tr("Serviço em")} {dias === 0 ? tr("HOJE") : tr("{0} dia(s)", dias)} {tr("sem waiver assinada.")}</b> {wBad ? tr("O e-mail {0} devolveu: corrija e reenvie.", wBad.signer_email) : wOpen ? tr("Envelope {0}; cobre a assinatura.", WAIVER_LABEL[wOpen.status!]) : tr("Nenhum envelope enviado.")}</Banner>}
    {!!c.vip && <Banner tone="info">{tr("Cliente VIP: dispensa waiver por decisão do dono (04/09/2026). Nada de cobrança automática.")}</Banner>}
    <div className="grid g5 c360-k">
      <div className="card kpi"><div className="lbl">{tr("Próximo serviço")}</div><div className="val" style={{ fontSize: 22 }}>{prox ? fmtDate(prox.due_on) : '—'}</div><div className="foot truncate" title={prox?.title || ''}>{prox ? <>{prox.title} <SysLink links={prox.links} one /></> : tr("nada agendado")}</div></div>
      <div className="card kpi"><div className="lbl">{tr("Último serviço")}</div><div className="val" style={{ fontSize: 22 }}>{ultimo ? fmtDate(ultimo.due_on) : '—'}</div><div className="foot truncate" title={ultimo?.title || ''}>{ultimo ? <>{ultimo.title} <SysLink links={ultimo.links} one /></> : tr("nenhum concluído")}</div></div>
      <div className="card kpi"><div className="lbl">{tr("Waiver")}</div><div className={`val ${wOk || c.vip ? 'ok' : wBad ? 'crit' : 'warn'}`} style={{ fontSize: 22 }}>{c.vip ? tr("dispensada") : wOk ? tr("assinada") : wBad ? tr("devolveu") : wOpen ? WAIVER_LABEL[wOpen.status!] : tr("nenhuma")}</div><div className="foot">{wOk?.expires_at ? <>{tr("vale até")} {fmtDate(wOk.expires_at)} </> : wOpen?.expires_at ? <>{tr("expira")} {fmtDate(wOpen.expires_at)} </> : ''}<SysLink links={(wOk || wOpen || wBad)?.links} one />
        {!wOk && !c.vip && can('OPERATOR') && <button className="btn ghost sm" onClick={() => setTab('waivers')} title={tr("Mandar ao e-mail do card o convite para assinar a waiver")}>{tr("✉ Convite por e-mail")}</button>}</div></div>
      <div className="card kpi"><div className="lbl">{tr("Serviços")}</div><div className="val">{abertos}<span className="of">/{vivos.length}</span></div><div className="foot">{abertos === 1 ? tr("1 aberto") : tr("{0} abertos", abertos)} · {vivos.length - abertos} {tr("concluídos")}</div></div>
      {data.invoices !== null
        ? <div className="card kpi"><div className="lbl">{tr("Em aberto (QBO)")}</div><div className={`val ${(data.open_balance || 0) > 0 ? 'warn' : 'ok'}`} style={{ fontSize: 22 }}>{money(data.open_balance || 0)}</div><div className="foot">{data.invoices.length} {tr("invoice(s) ·")} {emailsAbertos ? <span style={{ color: 'var(--warn)' }}>{emailsAbertos} {tr("e-mail(s) sem resposta")}</span> : tr("e-mails em dia")}</div></div>
        : <div className="card kpi"><div className="lbl">{tr("E-mails")}</div><div className={`val ${emailsAbertos ? 'warn' : ''}`}>{emailsAbertos}</div><div className="foot">{tr("sem resposta ·")} {data.emails.length} {tr("conhecidos")}</div></div>}
    </div>
    <details className="card c360-d"><summary className="card-h" style={{ cursor: 'pointer' }}><h2 className="h2">{tr("Dados completos")}</h2><span className="grow" /><span className="small muted">{c.source || '—'} {tr("· desde")} {fmtDate(c.created_at)}{c.scanned_at && <> {tr("· varrido")} {fmtDateTime(c.scanned_at)}</>}</span></summary>
      <div className="card-b grid g3">
        <dl className="dl"><dt>{tr("Piloto")}</dt><dd>{c.pilot_name || <span className="muted">{tr("o próprio")}</span>}</dd><dt>{tr("Nascimento")}</dt><dd className="mono">{fmtDate(c.pilot_dob)}</dd><dt>{tr("Responsável")}</dt><dd>{c.name}</dd></dl>
        <dl className="dl"><dt>{tr("E-mail")}</dt><dd>{c.email ? <a href={`mailto:${c.email}`}>{c.email}</a> : '—'}{c.email_alt && <div className="small"><a href={`mailto:${c.email_alt}`}>{c.email_alt}</a></div>}</dd><dt>{tr("Telefone")}</dt><dd>{c.phone ? <a href={`tel:${c.phone}`}>{c.phone}</a> : '—'}</dd><dt>{tr("Empresa")}</dt><dd>{c.company || '—'}</dd></dl>
        <dl className="dl"><dt>{tr("Plano mensal")}</dt><dd>{c.monthly_plan || <span className="muted">—</span>}{c.monthly_note && <div className="small muted">{c.monthly_note}</div>}</dd><dt>{tr("Etapa")}</dt><dd>{data.stages.find(s => s.code === c.stage_code)?.label || c.stage_code || '—'}</dd><dt>{tr("Tipo")}</dt><dd>{c.plan_type === 'monthly' ? tr("Academy Monthly") : c.plan_type === 'daily' ? tr("Academy Day") : '—'}{!!c.pro_driver && tr(" · ★ Pro")}</dd></dl>
      </div>
    </details>
    {edit && <Section title={tr("Editar cliente")}>
      <div className="grid g3">
        <div className="field"><label>{tr("Status")}</label><select className="input" value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}>{['ACTIVE', 'NEW', 'PENDING', 'AT_RISK', 'COMPLETED', 'INACTIVE'].map(s => <option key={s}>{s}</option>)}</select></div>
        <div className="field"><label>{tr("Etapa")}</label><select className="input" value={form.stage_code} onChange={e => setForm({ ...form, stage_code: e.target.value })}><option value="">—</option>{data.stages.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}</select></div>
        <div className="field"><label>{tr("VIP")}</label><label className="check"><input type="checkbox" disabled={!can('MANAGER')} checked={form.vip} onChange={e => setForm({ ...form, vip: e.target.checked })} /> {tr("dispensa waiver")} {!can('MANAGER') && <span className="muted">{tr("(só gerente)")}</span>}</label></div>
      </div>
      <div className="grid g2" style={{ marginTop: 12 }}>
        <div className="field"><label>{tr("Tipo de piloto")}</label><select className="input" value={form.plan_type} onChange={e => setForm({ ...form, plan_type: e.target.value })}><option value="">{tr("não definido")}</option><option value="monthly">{tr("Urace Academy Monthly (mensal)")}</option><option value="daily">{tr("Urace Academy Day (diária)")}</option></select></div>
        <div className="field"><label>{tr("★ Pro Racing Driver")}</label><label className="check"><input type="checkbox" disabled={!can('MANAGER')} checked={form.pro_driver} onChange={e => setForm({ ...form, pro_driver: e.target.checked })} /> {tr("pronto para ser convidado para corridas")} {!can('MANAGER') && <span className="muted">{tr("(só gerente)")}</span>}</label></div>
        <div className="field"><label>{tr("Plano mensal (gera a invoice do dia 1)")}</label><select className="input" value={form.monthly_plan} onChange={e => setForm({ ...form, monthly_plan: e.target.value })}><option value="">{tr("sem plano mensal")}</option>{['Academy Baby Kart', 'Academy 4 stroke', 'Academy 2 stroke', 'Academy kart próprio', 'Academy kart próprio + mecânico', 'Contrato 6 meses', 'Contrato 12 meses'].map(x => <option key={x}>{x}</option>)}</select></div>
        <div className="field"><label>{tr("Ajustes do plano")}</label><input className="input" value={form.monthly_note} onChange={e => setForm({ ...form, monthly_note: e.target.value })} placeholder={tr("ex.: 1 sessão extra em setembro; treino fora do OKC")} /></div>
      </div>
      <div className="field" style={{ marginTop: 12 }}><label>{tr("Notas")}</label><TextoComVoz valor={form.notes} onChange={t => setForm({ ...form, notes: t })} linhas={3} placeholder={tr("Dá para ditar")} /></div>
      <div className="row" style={{ marginTop: 12, justifyContent: 'flex-end' }}><button className="btn" onClick={() => setEdit(false)}>{tr("Cancelar")}</button><button className="btn primary" disabled={saving} onClick={save}>{saving ? <span className="spin" /> : tr("Salvar")}</button></div>
    </Section>}
    {c.notes && !edit && <div className="card card-b small" style={{ whiteSpace: 'pre-wrap' }}><b>{tr("Notas:")}</b> {c.notes}</div>}
    <div className="tabs">
      {(['timeline', 'monthly', 'equip', 'races', 'pecas', 'site', 'tasks', 'waivers', 'emails', 'invoices', 'ai'] as const).filter(t => (c.pro_driver || (t !== 'equip' && t !== 'races')) && ((t !== 'pecas' && t !== 'site') || can('OPERATOR') || (box && t === 'pecas'))
        && !(box && ['monthly', 'races', 'site', 'emails', 'invoices', 'ai'].includes(t))).map(t => <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
        {{ timeline: tr("Linha do tempo"), monthly: tr("Mensalidade e contrato"), equip: tr("★ Equipamento"), races: tr("★ Corridas"), pecas: tr("Peças"), site: tr("Conta no site"), tasks: tr("Serviços ({0})", data.tasks.length), waivers: tr("Waivers ({0})", data.waivers.length), emails: tr("E-mails ({0})", data.emails.length), invoices: data.invoices === null ? 'Invoices 🔒' : `Invoices (${data.invoices.length})`, ai: tr("IA ({0})", data.ai_actions.length) }[t]}
      </button>)}
    </div>
    <div className="card card-b">
      {tab === 'timeline' && (data.timeline.length === 0 ? <Empty>{tr("Nenhum evento ainda.")}</Empty> : <div className="tl">{data.timeline.map((e, i) => {
        const [lbl, tone] = KIND[e.kind] || [e.kind, '']
        const mes = (e.at || '').slice(0, 7); const antes = (data.timeline[i - 1]?.at || '').slice(0, 7)
        return <div key={i}>
          {mes !== antes && <div className="tl-m">{mes ? new Date(mes + '-02T12:00:00').toLocaleDateString(LOCALE(), { month: 'long', year: 'numeric' }) : tr("sem data")}</div>}
          <div className="ev"><div className="d">{fmtDate(e.at)}</div><div className={`p ${tone}`} /><div className="b">
            <div className="row wrap" style={{ gap: 8 }}><span className={`kind ${tone}`}>{lbl}</span><span className="t">{e.title}</span><Status s={e.status} label={e.kind === 'SITE_PAYMENT' ? (ESTADO_PEDIDO[e.status || ''] || e.status) : e.kind.startsWith('WAIVER') ? (WAIVER_LABEL[(e.status || '').toLowerCase()] || e.status) : undefined} /><span className="grow" /><SysLink links={e.links} /></div>
            {e.detail && <div className="small muted">{e.detail}</div>}
          </div></div>
        </div>
      })}</div>)}
      {tab === 'monthly' && <Mensalidade id={c.id} m={monthly.data} loading={monthly.loading} reload={monthly.reload} plan={c.plan_type} fin={can('MANAGER')} />}
      {tab === 'equip' && <Equipamento c={c} cat={catalog.data} reload={() => { reload(); catalog.reload() }} />}
      {renomear !== null && <RenomearServico tarefa={data.tasks.find(t => t.id === renomear)!} outras={data.tasks.filter(t => t.id !== renomear)} onClose={() => setRenomear(null)} onDone={reload} />}
      {mover !== null && <MoverServico tarefa={data.tasks.find(t => t.id === mover)!} atual={c} onClose={() => setMover(null)} onDone={reload} />}
      {irmao && <CardIrmao de={c} onClose={() => setIrmao(false)} onDone={id2 => { if (onClose) onClose(); nav(`/clients/${id2}`) }} />}
      {unir && <UnirModal keep={c} onClose={() => setUnir(false)} onDone={(kid) => { if (kid !== c.id) nav(`/clients/${kid}`); else reload() }} />}
      {qr && <QrModal cid={c.id} nome={c.pilot_name || c.name} onClose={() => setQr(false)} />}
      {tab === 'pecas' && <><QrBalcao cid={c.id} nome={c.pilot_name || c.name} /><PecasDoCliente cid={c.id} nome={c.pilot_name || c.name} /></>}
      {tab === 'site' && <ContaNoSite cid={c.id} />}
      {tab === 'races' && <CorridasDoPiloto rs={corridas.data} loading={corridas.loading} cid={c.id} />}
      {tab === 'tasks' && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{tr("Data")}</th><th>{tr("Serviço")}</th><th>{tr("Coluna")}</th><th>{tr("Status")}</th><th>{tr("Subtarefas")}</th><th>{tr("Waiver")}</th><th></th></tr></thead><tbody>
        {data.tasks.length === 0 && <tr><td colSpan={7}><Empty>{tr("Sem serviços vinculados.")}</Empty></td></tr>}
        {data.tasks.map(t => <tr key={t.id} className={t.deleted_at ? 'tr-excluido' : undefined}><td className="mono">{fmtDate(t.due_on)}</td><td>{t.title}
          {t.deleted_at && <div className="small muted">{tr("Excluído por {0} em {1}", t.deleted_by_name || '—', fmtDate(t.deleted_at))}{t.deleted_reason ? ` · ${t.deleted_reason}` : ''}</div>}</td><td>{t.section}</td><td>{t.deleted_at ? <Chip tone="crit">{tr("excluído")}</Chip> : <Status s={t.status} />}</td><td className="mono">{t.subtasks_total ? `${t.subtasks_done ?? 0}/${t.subtasks_total}` : '—'}</td><td className="nowrap">{t.waiver_id ? <a className="btn ghost sm" href={`/ops/api/waivers/${t.waiver_id}/download`} title={tr("A waiver assinada foi anexada nesta tarefa")}>{tr("📎 waiver")}</a> : <span className="muted">—</span>}</td>
          <td className="nowrap"><SysLink links={t.links} />{t.deleted_at ? (can('MANAGER') && <button className="btn ghost sm" onClick={() => restaurar(t.id)}>{tr("Restaurar")}</button>) : <>{can('OPERATOR') && <button className="btn ghost sm" onClick={() => setRenomear(t.id)} title={tr("trocar o nome do serviço (no Asana também)")}>{tr("Renomear")}</button>}{can('MANAGER') && <button className="btn ghost sm" onClick={() => setMover(t.id)} title={tr("este serviço é de outro cliente")}>{tr("Mover")}</button>}</>}</td></tr>)}
      </tbody></table></div>}
      {tab === 'waivers' && can('OPERATOR') && <ConviteWaiver cid={c.id} onMuda={reload} />}
      {tab === 'waivers' && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{tr("Signatário")}</th><th>{tr("Modelo")}</th><th>{tr("Status")}</th><th>{tr("Enviada")}</th><th>{tr("Assinada")}</th><th>{tr("Expira")}</th><th></th></tr></thead><tbody>
        {data.waivers.length === 0 && <tr><td colSpan={7}><Empty>{tr("Nenhum envelope para este e-mail.")}</Empty></td></tr>}
        {data.waivers.map(w => <tr key={w.id}><td>{w.signer_name}<div className="small muted">{w.signer_email}</div></td><td>{w.template}{w.source === 'urace' && <div className="small muted">{tr("área do cliente")}</div>}</td><td>{w.voided_at ? <><Status s="voided" label={tr("anulada")} /><div className="small muted">{tr("por {0} em {1}: {2}", w.voided_by || '—', fmtDate(w.voided_at), w.void_reason || '')}</div></> : <Status s={w.status} label={WAIVER_LABEL[w.status || ''] || w.status} />}</td><td className="mono">{fmtDate(w.sent_at)}</td><td className="mono">{fmtDate(w.completed_at)}</td><td className="mono">{fmtDate(w.expires_at)}</td><td className="nowrap">{w.status === 'completed' && <a className="btn sm" href={`/ops/api/waivers/${w.id}/download`} title={w.source === 'urace' ? tr("PDF assinado na área do cliente (com página de certificado)") : w.pdf_path ? tr("PDF assinado guardado no card") : tr("Baixar PDF assinado do DocuSign")}>{tr("⬇ PDF")}{w.pdf_path ? ' ✓' : ''}</a>} {w.source === 'urace' && w.status === 'completed' && !w.voided_at && can('MANAGER') && <button className="btn sm danger" onClick={() => anularWaiver(w)} title={tr("Tirar de vigor, com motivo: a waiver fica no card e no backup")}>{tr("Anular")}</button>} <SysLink links={w.links} /></td></tr>)}
      </tbody></table></div>}
      {tab === 'emails' && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{tr("Quando")}</th><th>{tr("Caixa")}</th><th>{tr("Assunto")}</th><th>{tr("De")}</th><th>{tr("Prioridade")}</th><th>{tr("Tratado")}</th><th></th></tr></thead><tbody>
        {data.emails.length === 0 && <tr><td colSpan={7}><Empty>{tr("Nenhum e-mail vinculado.")}</Empty></td></tr>}
        {data.emails.map(e => <tr key={e.id}><td className="mono">{fmtDateTime(e.last_at)}</td><td>{e.mailbox}@</td><td>{e.subject}</td><td className="small">{e.sender}</td><td>{e.priority && <Chip tone={statusTone(e.priority === 'CRITICAL' ? 'ERROR' : e.priority === 'HIGH' ? 'PENDING' : 'ACTIVE')}>{e.priority}</Chip>}</td><td>{e.handled ? '✓' : <span style={{ color: 'var(--warn)' }}>{tr("não")}</span>}</td><td><SysLink links={e.links} /></td></tr>)}
      </tbody></table></div>}
      {tab === 'invoices' && (data.invoices === null ? <Empty title={tr("Financeiro restrito")}>{tr("Invoices são visíveis para gerentes e administradores.")}</Empty> :
        data.invoices.length === 0 ? <Empty>{tr("Nenhuma invoice. QuickBooks está em stand-by; nada é inventado aqui.")}</Empty> : <>
        {(() => { const abertas = data.invoices.filter(i => ['open', 'sent', 'overdue'].includes(i.status || '') && (i.balance || 0) > 0); return abertas.length > 0 && can('MANAGER') && <div className="row wrap" style={{ marginBottom: 8 }}><span className="small muted"><b className="ink2">{abertas.length}</b> {tr("em aberto ·")} {money(abertas.reduce((s, i) => s + (i.balance || 0), 0))}</span><span className="grow" /><button className="btn sm" onClick={() => setSelInv(s => s.length === abertas.length ? [] : abertas.map(i => i.id))}>{selInv.length === abertas.length ? tr("desmarcar") : tr("marcar todas em aberto")}</button><button className="btn primary sm" disabled={selInv.length === 0} onClick={() => setLemb(true)}>{tr("⏰ Lembretes")}{selInv.length ? ` (${selInv.length})` : ''}</button></div> })()}
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th></th><th>{tr("Nº")}</th><th>{tr("Emitida")}</th><th>{tr("Vence")}</th><th>{tr("Valor")}</th><th>{tr("Saldo")}</th><th>{tr("Status")}</th><th>{tr("Lembrete")}</th></tr></thead><tbody>
          {data.invoices.map(i => { const aberta = ['open', 'sent', 'overdue'].includes(i.status || '') && (i.balance || 0) > 0; return <tr key={i.id}><td>{aberta && can('MANAGER') && <input type="checkbox" checked={selInv.includes(i.id)} onChange={() => setSelInv(s => s.includes(i.id) ? s.filter(x => x !== i.id) : [...s, i.id])} aria-label={tr("Selecionar {0}", i.doc_number)} />}</td><td className="mono">{i.doc_number}{i.memo && <div className="small muted truncate" style={{ maxWidth: 220 }} title={i.memo}>{i.memo}</div>}</td><td className="mono">{fmtDate(i.issued_on)}</td><td className="mono">{fmtDate(i.due_on)}</td><td className="mono">{money(i.amount)}</td><td className="mono">{money(i.balance)}</td><td><Status s={i.status} /></td><td><LembreteChip i={i} onChange={reload} /></td></tr> })}
        </tbody></table></div>
        {lemb && <LembreteModal invoices={data.invoices.filter(i => selInv.includes(i.id))} onClose={() => setLemb(false)} onDone={() => { reload(); setSelInv([]) }} />}
      </>)}
      {tab === 'ai' && (data.ai_actions.length === 0 ? <Empty>{tr("A IA ainda não propôs nada para este cliente.")}</Empty> :
        <div className="acts">{data.ai_actions.map(a => <div className="act" key={a.id}><span className="what">{a.action}</span><Chip tone={statusTone(a.policy)}>{POLICY_LABEL[a.policy]}</Chip><Chip tone={statusTone(a.status)}>{a.status}</Chip><span className="small muted">{fmtDateTime(a.created_at)}</span>{a.reason && <div className="small ink2" style={{ width: '100%' }}>{a.reason}</div>}</div>)}</div>)}
    </div>
  </>
}


interface Recorrencia { id: number; qbo_id: string | null; name: string | null; amount: number; months: number; start_on: string; end_on: string; email: string | null; status: string; criado_por: string | null; created_at: string; result: string | null; source: string }
interface RecQbo { id: string; nome: string | null; ativa: boolean; total: number | null; inicio: string | null; fim: string | null; proxima: string | null
  ocorrencias: number | null; email: string | null; linhas: { item: string | null; unitario: number | null }[]; vinculada_id: number | null; de_outro_cliente: boolean }
interface NoQbo { conectado: boolean; erro?: string; recorrencias: RecQbo[]; soltas: number }
/** #314: a sessão extra do aluno recorrente — o valor que vale hoje e de onde vem (card, plano ou mensal ÷ sessões). */
interface ExtraMensal { price: number | null; origin: 'card' | 'plano' | 'mensal' | null; math: string | null; item_id: string | null; item_name: string | null }
interface Mensal { monthly_plan: string | null; monthly_amount: number | null; monthly_item_id: string | null; monthly_sessions: number | null; item: { id: string; name: string; price: number | null } | null
  extra_session_price: number | null; extra_item_id: string | null; extra: ExtraMensal
  itens: { id: string; name: string; full_name: string | null; price: number | null }[]; email: string | null; opcoes_meses: number[]; padrao_meses: number; proximo_inicio: string; recorrencias: Recorrencia[]; agendadas: MesAgendado[] }
/** Um mês da mensalidade agendada (#63): criado e enviado pelo QuickBooks no dia 1 às 01:00 (Flórida). */
interface MesAgendado { id: number; month: string; amount: number; email: string | null; send_at: string; status: 'a_enviar' | 'enviada' | 'falhou' | 'cancelada'
  doc_number: string | null; sent_at: string | null; error: string | null; attempts: number; note: string | null }
const MES_ROTULO: Record<MesAgendado['status'], [string, 'ok' | 'warn' | 'crit' | 'neutral']> = { a_enviar: [tr("a enviar"), 'neutral'], enviada: ['enviada', 'ok'], falhou: ['falhou', 'crit'], cancelada: ['cancelada', 'neutral'] }
/** "envia em 01/11 01:00" · "URACE-0021, enviada em …" · "falhou: motivo" — o horário é o da Flórida. */
function situacaoMes(x: MesAgendado) {
  const [dia, hora] = x.send_at.split(' ')
  const quando = `${dia.slice(8, 10)}/${dia.slice(5, 7)} ${hora}`
  if (x.status === 'a_enviar') return `envia em ${quando}`
  if (x.status === 'enviada') return `${x.doc_number ? `${x.doc_number}, ` : ''}${x.sent_at ? `enviada em ${fmtDateTime(x.sent_at)}` : 'enviada'}${x.note ? ` · ${x.note}` : ''}`
  if (x.status === 'falhou') return `${x.error || 'falhou'}${x.attempts < 3 ? ` · tenta de novo (${x.attempts}/3)` : ' · 3 tentativas: confira no QuickBooks'}`
  return tr('não será enviada')
}
const REC_ROTULO: Record<string, [string, 'ok' | 'warn' | 'crit' | 'neutral']> = { active: ['ativa', 'ok'], simulated: [tr("simulação — nada criado"), 'warn'], failed: ['falhou', 'crit'], ended: ['encerrada', 'neutral'] }
const mesAno = (iso: string) => `${iso.slice(5, 7)}/${iso.slice(0, 4)}`
const mesExtenso = (iso: string) => new Date(iso.slice(0, 7) + '-15T12:00:00Z').toLocaleDateString(LOCALE(), { month: 'long', year: 'numeric', timeZone: 'UTC' })
const somaMeses = (iso: string, n: number) => { const b = new Date(iso.slice(0, 7) + '-15T12:00:00Z'); b.setUTCMonth(b.getUTCMonth() + n); return b.toISOString().slice(0, 10) }
/** Valor em dólar como a pessoa digita: "2756,9", "2.756,90", "2,756.90", "$ 450" → número.
 *  O último separador seguido de 1 ou 2 dígitos é o decimal; os outros são milhar. */
function lerDolar(s: string): number | null {
  const t = s.replace(/US\$|\$|\s/g, '')
  if (!t) return null
  const m = t.match(/^(.*)[.,](\d{1,2})$/)
  const inteiro = (m ? m[1] : t).replace(/[.,]/g, '')
  if (!/^\d+$/.test(inteiro) && !(m && inteiro === '')) return NaN
  return Number(`${inteiro || '0'}.${m ? m[2] : '0'}`)
}
const fmtDolar = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** Dono, 29/09: o valor da mensalidade é do cliente ("às vezes um deal diferente"), e vira
 *  invoice recorrente no QuickBooks — padrão 6 meses, ou 12, ou personalizado. Só gerente. */
function ValorERecorrencia({ id, lastAmount }: { id: number; lastAmount: number | null }) {
  const toast = useToast()
  const perguntar = usePerguntar()
  const d = useGet<Mensal>(`/clients/${id}/mensal`)
  const q = useGet<NoQbo>(`/clients/${id}/mensal/qbo`)
  const [valor, setValor] = useState<string | null>(null)
  const [item, setItem] = useState<string | null>(null)
  const [sessoes, setSessoes] = useState<string | null>(null)
  const [extra, setExtra] = useState<string | null>(null)
  const [itemExtra, setItemExtra] = useState<string | null>(null)
  const [meses, setMeses] = useState<number | 'outro'>(6)
  const [outro, setOutro] = useState('3')
  const [inicio, setInicio] = useState<string | null>(null)
  const [salvando, setSalvando] = useState(false)
  if (d.error) return <ErrorState error={d.error} retry={d.reload} />
  if (!d.data) return <Loading rows={2} />
  const m = d.data
  const v = valor ?? (m.monthly_amount != null ? fmtDolar(m.monthly_amount) : '')
  const vNum = lerDolar(v)
  const it = item ?? (m.monthly_item_id || '')
  const ini = inicio ?? m.proximo_inicio
  const nMeses = meses === 'outro' ? Number(outro) : meses
  const ses = sessoes ?? (m.monthly_sessions != null ? String(m.monthly_sessions) : '')
  const sesNum = ses.trim() ? Number(ses) : null
  const ex = extra ?? (m.extra_session_price != null ? fmtDolar(m.extra_session_price) : '')
  const exNum = lerDolar(ex)
  const itEx = itemExtra ?? (m.extra_item_id || '')
  const mudou = (vNum ?? null) !== (m.monthly_amount ?? null) || it !== (m.monthly_item_id || '') || sesNum !== (m.monthly_sessions ?? null)
    || (exNum ?? null) !== (m.extra_session_price ?? null) || itEx !== (m.extra_item_id || '')
  // #314: o que a extra custa sem valor no card — o do plano, ou a conta do mensal ÷ sessões (ex.: 2,756.90 ÷ 4 = 689.23)
  const extraAuto = m.extra.origin === 'card' ? null : m.extra.price == null ? tr("sem mensal: ponha o valor")
    : m.extra.math ? `${m.extra.math} = ${fmtDolar(m.extra.price)}` : tr("do plano: {0}", fmtDolar(m.extra.price))
  const todosItens = [...(m.item && !m.itens.some(x => x.id === m.item!.id) ? [m.item] : []), ...m.itens]
  function escolherItem(id: string) {
    setItem(id)
    // o preço de tabela do item entra no valor — e continua editável (deal próprio)
    const preco = todosItens.find(x => x.id === id)?.price
    if (preco) setValor(fmtDolar(preco))
  }
  const inicios = Array.from({ length: 6 }, (_, k) => { const b = new Date(m.proximo_inicio + 'T12:00:00Z'); b.setUTCMonth(b.getUTCMonth() + k - 1); return b.toISOString().slice(0, 10) })

  async function salvar() {
    const n = vNum
    if (n !== null && (Number.isNaN(n) || n <= 0)) { toast(tr("Valor mensal inválido. Ex.: 2,756.90"), 'warn'); return }
    setSalvando(true)
    if (sesNum !== null && (!Number.isInteger(sesNum) || sesNum < 1 || sesNum > 31)) { toast(tr("Sessões por mês: de 1 a 31."), 'warn'); setSalvando(false); return }
    if (exNum !== null && (Number.isNaN(exNum) || exNum <= 0)) { toast(tr("Valor da sessão extra inválido. Ex.: 689.23"), 'warn'); setSalvando(false); return }
    try { await api.patch(`/clients/${id}/mensal`, { monthly_amount: n, monthly_item_id: it || null, ...(sesNum !== null ? { monthly_sessions: sesNum } : {}),
      extra_session_price: exNum, extra_item_id: itEx || null })
      toast(tr("Mensalidade salva. É ela que vai na invoice do dia 1."), 'ok'); setValor(null); setItem(null); setSessoes(null); setExtra(null); setItemExtra(null); d.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setSalvando(false) }
  }
  const soltas = (q.data?.recorrencias || []).filter(x => x.ativa && !x.vinculada_id && !x.de_outro_cliente)
  const ativaNoPainel = m.recorrencias.find(x => x.status === 'active' && x.end_on >= ini)
  const noQbo = new Map((q.data?.recorrencias || []).map(x => [String(x.id), x]))
  const bloqueio = !q.data ? tr('conferindo o QuickBooks…') : !q.data.conectado ? tr('sem conferir o QuickBooks não dá para criar')
    : soltas.length ? tr('já existe cobrança recorrente no QuickBooks: vincule') : ativaNoPainel ? tr('já existe recorrência ativa') : ''
  async function vincular(x: RecQbo) {
    if (!await perguntar({ titulo: tr("Vincular esta recorrência ao Command Center?"),
      texto: tr("A cobrança continua sendo a do QuickBooks (“{0}”, ${1}), sem criar outra. O valor mensal do card passa a ser ${2}, e o dia 1 do painel não prepara outra invoice para este cliente.", x.nome || x.id, fmtDolar(x.total || 0), fmtDolar(x.total || 0)),
      ok: tr("Vincular") })) return
    setSalvando(true)
    try { await api.post(`/clients/${id}/mensal/vincular`, { qbo_id: x.id }); toast(tr("Vinculada: agora é uma cobrança só, a do QuickBooks."), 'ok'); setValor(null); setItem(null); d.reload(); q.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setSalvando(false) }
  }
  async function recorrencia() {
    if (!Number.isInteger(nMeses) || nMeses < 1 || nMeses > 36) { toast(tr("Escolha de 1 a 36 meses."), 'warn'); return }
    const ultimo = somaMeses(ini, nMeses - 1)
    if (!await perguntar({ titulo: tr("Criar as {0} mensalidade{1}?", nMeses, nMeses > 1 ? 's' : ''),
      texto: tr("Ficam criadas agora, uma por mês, de {0} a {1}: ${2} cada, para {3}. ", mesExtenso(ini), mesExtenso(ultimo), fmtDolar(m.monthly_amount || 0), m.email || 'o e-mail do cliente no QuickBooks') +
             tr("Cada uma é criada e enviada pelo QuickBooks no dia 1 do mês, à 01:00 (Flórida) — o mês que já começou sai em até 15 minutos. ") +
             tr("Este clique aprova todas. O mês que já tem invoice de mensalidade não é cobrado de novo, e dá para cancelar um mês antes de ele sair."),
      ok: tr("Criar e agendar") })) return
    setSalvando(true)
    try {
      const r = await api.post<{ agendadas: MesAgendado[] }>(`/clients/${id}/mensal/recorrencia`, { meses: nMeses, inicio: ini })
      toast(tr("{0} mensalidade{1} agendada{2}: cada uma sai no dia 1 à 01:00.", r.agendadas.length, r.agendadas.length > 1 ? 's' : '', r.agendadas.length > 1 ? 's' : ''), 'ok'); d.reload()
    } catch (e) { toast((e as ApiError).message, 'crit'); d.reload() } finally { setSalvando(false) }
  }
  async function cancelarMes(x: MesAgendado) {
    if (!await perguntar({ titulo: tr("Cancelar a mensalidade de {0}?", mesExtenso(x.month + '-01')),
      texto: tr("Ela não será enviada. Nada é apagado: a linha fica \"cancelada\", com o seu nome."), ok: tr("Cancelar este mês"), perigo: true })) return
    setSalvando(true)
    try { await api.post(`/clients/${id}/mensal/agendadas/${x.id}/cancelar`, {}); toast(tr("Mês cancelado."), 'ok'); d.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setSalvando(false) }
  }
  return <Section title={tr("Valor da mensalidade e recorrência")}>
    {soltas.length > 0 && <div className="banner crit" role="alert" style={{ marginBottom: 14, padding: '14px 16px' }}><div className="grow">
      <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 6 }}>{tr("⚠ Este cliente já tem cobrança recorrente no QuickBooks")}</div>
      <div className="small" style={{ marginBottom: 8 }}>{tr("Para não cobrar duas vezes, não crie outra: vincule a que já existe ao Command Center.")}</div>
      {soltas.map(x => <div key={x.id} className="row wrap" style={{ gap: 10, padding: '6px 0', borderTop: '1px solid var(--glass-line)' }}>
        <div className="grow"><b>{x.nome || tr("recorrência {0}", x.id)}</b> · ${fmtDolar(x.total || 0)} {tr("por mês")}
          <div className="small muted">{tr("desde")} {x.inicio ? mesExtenso(x.inicio) : '?'}{x.fim ? tr(" até {0}", mesExtenso(x.fim)) : x.ocorrencias ? tr(" · {0} vezes", x.ocorrencias) : tr(" · sem fim")}{x.proxima ? tr(" · próxima {0}", fmtDate(x.proxima)) : ''}{x.email ? ` · ${x.email}` : ''}{x.linhas[0]?.item ? ` · ${x.linhas[0].item}` : ''}</div></div>
        <button className="btn primary" disabled={salvando || !!ativaNoPainel} title={ativaNoPainel ? tr("o card já tem outra recorrência ativa") : ''} onClick={() => vincular(x)}>{tr("Vincular ao Command Center")}</button>
      </div>)}
    </div></div>}
    {q.data && !q.data.conectado && <Banner tone="warn">{tr("Não deu para conferir o QuickBooks (")}{q.data.erro}{tr("). Criar recorrência fica bloqueado até conferir — uma cobrança só.")}</Banner>}
    <div className="grid g3">
      <div className="field"><label>{tr("Valor mensal deste cliente")}</label>
        <div className="dolar"><span aria-hidden="true">$</span>
          <input className="input" inputMode="decimal" value={v} onChange={e => setValor(e.target.value)}
                 onBlur={() => { if (vNum !== null && !Number.isNaN(vNum)) setValor(fmtDolar(vNum)) }}
                 placeholder={lastAmount != null ? tr("última: {0}", fmtDolar(lastAmount)) : '0.00'} aria-label={tr("valor mensal em dólar")} /></div>
        {v.trim() !== '' && vNum !== null && Number.isNaN(vNum) && <span className="small" style={{ color: 'var(--crit)' }}>{tr("Valor não entendido. Ex.: 2,756.90")}</span>}</div>
      <div className="field"><label>{tr("Item do QuickBooks")}</label>
        <select className="input" value={it} onChange={e => escolherItem(e.target.value)}>
          <option value="">{tr("escolha…")}</option>
          {todosItens.map(x => <option key={x.id} value={x.id}>{x.name}{x.price ? tr(" (tabela {0})", money(x.price)) : ''}</option>)}
        </select></div>
      <div className="field"><label>{tr("Sessões por mês do contrato")}</label>
        <input className="input" inputMode="numeric" value={ses} onChange={e => setSessoes(e.target.value)} placeholder="4" aria-label={tr("sessões por mês do contrato")} /></div>
      {/* #314 (dono, 16/10): a sessão além do pacote do mês — "o valor do mensal dele dividido … ou então usa aqueles valores" */}
      <div className="field"><label htmlFor={`extra-${id}`}>{tr("Valor da sessão extra")}</label>
        <div className="dolar"><span aria-hidden="true">$</span>
          <input id={`extra-${id}`} className="input" inputMode="decimal" value={ex} onChange={e => setExtra(e.target.value)}
                 onBlur={() => { if (exNum !== null && !Number.isNaN(exNum)) setExtra(fmtDolar(exNum)) }}
                 placeholder={extraAuto || '0.00'} /></div>
        <span className="small muted">{ex.trim() ? tr("combinado com este cliente") : extraAuto ? tr("vazio: {0}", extraAuto) : ''}</span></div>
      <div className="field"><label htmlFor={`item-extra-${id}`}>{tr("Item da sessão extra")}</label>
        <select id={`item-extra-${id}`} className="input" value={itEx} onChange={e => setItemExtra(e.target.value)}>
          <option value="">{m.extra.item_name && !m.extra_item_id ? tr("automático: {0}", m.extra.item_name) : tr("automático (sincronize o QuickBooks)")}</option>
          {todosItens.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select></div>
      <div className="field"><label>{tr("&nbsp;")}</label><button className="btn primary" disabled={salvando || !mudou} onClick={salvar}>{tr("Salvar mensalidade")}</button></div>
    </div>
    <p className="small muted" style={{ marginTop: 6 }}>{tr("Ao escolher o item, o preço de tabela entra no valor; mude se o combinado com o cliente for outro. O que estiver salvo aqui é o valor da invoice de todo dia 1.")}</p>
    <p className="small muted" style={{ marginTop: 4 }}>{tr("Sessão extra (aluno recorrente): acima das sessões do mês, a sessão marcada na área do cliente sai numa invoice do QuickBooks com este valor, sem depósito. Vazio, vale o valor do plano do site ou o mensal ÷ sessões do mês. O cliente vê só \"Included in your plan\" ou \"Extra session\": o contador fica para a equipe.")}</p>
    <div className="row wrap" style={{ gap: 12, marginTop: 14, alignItems: 'flex-end' }}>
      <div className="field"><label>{tr("Recorrência")}</label>
        <div className="row wrap" style={{ gap: 6 }}>
          {m.opcoes_meses.map(n => <button key={n} className={`btn sm${meses === n ? ' primary' : ''}`} onClick={() => setMeses(n)}>{n} {tr("meses")}{n === m.padrao_meses ? tr(" (padrão)") : ''}</button>)}
          <button className={`btn sm${meses === 'outro' ? ' primary' : ''}`} onClick={() => setMeses('outro')}>{tr("Personalizado")}</button>
          {meses === 'outro' && <input className="input" type="number" min={1} max={36} value={outro} onChange={e => setOutro(e.target.value)} style={{ width: 90 }} aria-label={tr("meses")} />}
        </div></div>
      <div className="field"><label>{tr("Primeira mensalidade")}</label>
        <select className="input" value={ini} onChange={e => setInicio(e.target.value)}>{inicios.map(x => <option key={x} value={x}>{tr("dia 1 de")} {mesAno(x)}</option>)}</select></div>
      <button className="btn" disabled={salvando || mudou || !m.monthly_amount || !m.monthly_item_id || !!bloqueio} onClick={recorrencia}
              title={mudou ? tr("salve a mensalidade antes") : !m.monthly_amount || !m.monthly_item_id ? tr("defina valor e item antes") : bloqueio}>{tr("Criar invoice recorrente (todos os meses)")}</button>
      {bloqueio && !soltas.length && <span className="small muted">{bloqueio}</span>}
    </div>
    {m.agendadas.length > 0 && <>
      <h3 className="h3" style={{ marginTop: 16 }}>{tr("Mensalidades agendadas")}</h3>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{tr("Mês")}</th><th>{tr("Valor")}</th><th>{tr("Situação")}</th><th>{tr("Envio")}</th><th></th></tr></thead><tbody>
        {m.agendadas.map(x => <tr key={x.id}><td className="mono">{mesAno(x.month + '-01')}</td><td className="mono">${fmtDolar(x.amount)}</td>
          <td><Chip tone={MES_ROTULO[x.status][1]}>{MES_ROTULO[x.status][0]}</Chip></td>
          <td className="small">{situacaoMes(x)}</td>
          <td>{(x.status === 'a_enviar' || x.status === 'falhou') && <button className="btn sm" disabled={salvando} onClick={() => cancelarMes(x)}>{tr("Cancelar")}</button>}</td></tr>)}
      </tbody></table></div></>}
    {m.recorrencias.length > 0 && <div className="tbl-wrap" style={{ marginTop: 12 }}><table className="tbl"><thead><tr><th>{tr("De")}</th><th>{tr("Até")}</th><th>{tr("Meses")}</th><th>{tr("Valor")}</th><th>{tr("Origem")}</th><th>{tr("Situação")}</th><th>{tr("No QuickBooks")}</th><th>{tr("Criada")}</th></tr></thead><tbody>
      {m.recorrencias.map(x => <tr key={x.id}><td className="mono">{mesAno(x.start_on)}</td><td className="mono">{x.end_on >= '2099' ? tr("sem fim") : mesAno(x.end_on)}</td><td className="mono">{x.months || '—'}</td><td className="mono">${fmtDolar(x.amount)}</td>
        <td className="small">{x.source === 'qbo' ? tr("vinculada do QuickBooks") : tr("criada pelo painel")}</td>
        <td><Chip tone={(REC_ROTULO[x.status] || [x.status, 'neutral'])[1]}>{(REC_ROTULO[x.status] || [x.status])[0]}</Chip></td>
        <td className="small">{!x.qbo_id ? <span className="muted">—</span> : !q.data?.conectado ? <span className="muted">{tr("QBO")} {x.qbo_id}</span>
          : noQbo.get(String(x.qbo_id))?.ativa ? <Chip tone="ok">{tr("vinculada ✓")}</Chip> : noQbo.has(String(x.qbo_id)) ? <Chip tone="warn">{tr("inativa lá")}</Chip> : <Chip tone="crit">{tr("não encontrada lá")}</Chip>}</td>
        <td className="small">{fmtDateTime(x.created_at)}{x.criado_por ? ` · ${x.criado_por}` : ''}</td></tr>)}
    </tbody></table></div>}
  </Section>
}

type TarefaCard = { id: number; title: string; due_on: string | null; section: string | null }

/** Renomear o serviço — no Asana também — e, se quiser, dar o mesmo nome a outros (dono, 29/09). */
function RenomearServico({ tarefa, outras, onClose, onDone }: { tarefa: TarefaCard; outras: TarefaCard[]; onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const [nome, setNome] = useState(tarefa.title)
  const [marcadas, setMarcadas] = useState<number[]>([])
  const [indo, setIndo] = useState(false)
  async function salvar() {
    if (!nome.trim()) { toast(tr("O nome não pode ficar vazio."), 'warn'); return }
    setIndo(true)
    try {
      const r = await api.post<{ renomeados: unknown[]; falhas: { titulo: string; motivo: string }[] }>('/tasks/renomear', { task_ids: [tarefa.id, ...marcadas], nome: nome.trim() })
      if (r.falhas.length) toast(tr("{0} renomeado(s); {1} não: {2}", r.renomeados.length, r.falhas.length, r.falhas[0].motivo), 'warn')
      else toast(r.renomeados.length > 1 ? tr("{0} serviços renomeados, no Asana também.", r.renomeados.length) : tr("Serviço renomeado, no Asana também."), 'ok')
      onDone(); onClose()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 620 }} onMouseDown={e => e.stopPropagation()}>
    <h2 className="h2">{tr("Renomear serviço")}</h2>
    <p className="small muted">{tr("Muda o nome no Asana e aqui. O que está escrito dentro da tarefa (descrição, subtarefas) não muda.")}</p>
    <div className="field"><label>{tr("Nome")}</label><input className="input" value={nome} onChange={e => setNome(e.target.value)} autoFocus /></div>
    {outras.length > 0 && <div className="field" style={{ marginTop: 12 }}><label>{tr("Dar o mesmo nome também a")}</label>
      <div className="tbl" style={{ maxHeight: '38vh', overflow: 'auto' }}>
        {outras.map(t => <label key={t.id} className="check" style={{ padding: '6px 2px' }}>
          <input type="checkbox" checked={marcadas.includes(t.id)} onChange={() => setMarcadas(m => m.includes(t.id) ? m.filter(x => x !== t.id) : [...m, t.id])} />
          <span className="mono small">{fmtDate(t.due_on)}</span> <span>{t.title}</span></label>)}
      </div></div>}
    <div className="row" style={{ marginTop: 14, justifyContent: 'flex-end' }}>
      <button className="btn" onClick={onClose}>{tr("Cancelar")}</button>
      <button className="btn primary" disabled={indo || !nome.trim() || (nome.trim() === tarefa.title && !marcadas.length)} onClick={salvar}>{indo ? <span className="spin" /> : tr("Renomear{0}", marcadas.length ? ` (${marcadas.length + 1})` : '')}</button>
    </div>
  </div></Scrim>
}

/** Levar o serviço para o card do cliente certo. A sincronia do Asana não desfaz. */
function MoverServico({ tarefa, atual, onClose, onDone }: { tarefa: TarefaCard; atual: { id: number; name: string; pilot_name?: string | null }; onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const [dest, setDest] = useState<Client | null>(null)
  const [indo, setIndo] = useState(false)
  async function mover() {
    if (!dest) return
    setIndo(true)
    try { await api.post(`/tasks/${tarefa.id}/cliente`, { client_id: dest.id }); toast(tr("Movido para {0}.", dest.pilot_name || dest.name), 'ok'); onDone(); onClose() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()}>
    <h2 className="h2">{tr("Mover serviço para outro cliente")}</h2>
    <p className="small"><b>{tarefa.title}</b></p>
    <p className="small muted">{tr("Sai do card de")} {atual.pilot_name || atual.name} {tr("e vai para o cliente escolhido. A sincronia do Asana passa a respeitar a sua escolha.")}</p>
    <Picker label={tr("Cliente certo")} value={dest} onPick={setDest} exclude={atual.id} />
    <div className="row" style={{ marginTop: 14, justifyContent: 'flex-end' }}>
      <button className="btn" onClick={onClose}>{tr("Cancelar")}</button>
      <button className="btn primary" disabled={indo || !dest} onClick={mover}>{indo ? <span className="spin" /> : tr("Mover")}</button>
    </div>
  </div></Scrim>
}

/* #312 (revisão): o arquivo escolhido mora aqui dentro do painel. Fechar o painel desmonta este formulário, e o PDF
 * escolhido antes não sobe "escondido" quando o painel abre de novo com o campo vazio. */
function SubirContrato({ id, reload }: { id: number; reload: () => void }) {
  const toast = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const campo = useRef<HTMLInputElement>(null)
  async function upload() {
    if (!file) return
    setBusy(true)
    try {
      const fd = new FormData(); fd.append('file', file); fd.append('title', file.name)
      const csrf = document.cookie.match(/(?:^|;\s*)cc_csrf=([^;]+)/)?.[1] || ''
      const res = await fetch(`/ops/api/clients/${id}/contract`, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-CSRF': decodeURIComponent(csrf) } })
      if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(j.detail || `HTTP ${res.status}`) }
      toast(tr("Contrato guardado."), 'ok'); setFile(null)
      if (campo.current) { campo.current.value = ''; campo.current.focus() }      // o campo fica vazio, como o estado
      reload()
    } catch (e) { toast((e as Error).message, 'crit') } finally { setBusy(false) }
  }
  return <div className="row wrap"><input ref={campo} className="input" type="file" accept=".pdf,image/*" style={{ maxWidth: 360 }} aria-label={tr("PDF do contrato")} onChange={e => setFile(e.target.files?.[0] || null)} /><button className="btn" disabled={!file || busy} onClick={upload}>{busy ? <span className="spin" /> : tr("Subir contrato")}</button></div>
}

function Mensalidade({ id, m, loading, reload, plan, fin }: { id: number; m: Monthly | null; loading: boolean; reload: () => void; plan?: string | null; fin: boolean }) {
  const { can } = useAuth()
  if (loading && !m) return <Loading />
  if (!m) return null
  const mesNome = (k: string) => new Date(k + '-15T12:00:00Z').toLocaleDateString(LOCALE(), { month: 'long', year: 'numeric', timeZone: 'UTC' })
  return <div className="stack">
    {plan !== 'monthly' && <Banner tone="info">{tr("Este piloto não está marcado como Academy Monthly. Marque em Editar → Tipo de piloto para o dia 1 gerar a mensalidade.")}</Banner>}
    <div className="grid g3">
      <div className="card kpi"><div className="lbl">{tr("Última mensalidade")}</div><div className="val" style={{ fontSize: 24 }}>{fin ? (m.last_monthly_amount != null ? money(m.last_monthly_amount) : '—') : '🔒'}</div><div className="foot truncate" title={m.last_monthly_memo || ''}>{m.last_monthly_memo || tr("nenhuma invoice de Academy encontrada")}</div></div>
      <div className="card kpi"><div className="lbl">{tr("Sessões este mês")}</div><div className="val">{m.months[0]?.sessions_used ?? 0}<span className="muted" style={{ fontSize: 18 }}> / {m.sessions_per_month}</span></div>
        <div className="foot">{m.months[0]?.sessions_over ? tr("{0} acima do contrato", m.months[0].sessions_over) : tr("{0} restante(s)", m.months[0]?.sessions_left ?? 0)}{m.sessions_per_month_set ? '' : tr(" · padrão de 4 (defina o do contrato)")} {tr("· zera no dia 1 · só a equipe vê")}</div></div>
      <div className="card kpi"><div className="lbl">{tr("Invoice do mês")}</div><div className={`val ${m.months[0]?.invoice ? 'ok' : 'warn'}`} style={{ fontSize: 22 }}>{m.months[0]?.invoice ? (m.months[0].invoice.status || tr("emitida")) : tr("falta")}</div><div className="foot">{m.months[0]?.invoice?.doc_number || (m.months[0]?.needs_invoice ? tr("a IA monta no dia 1, você aprova") : '')}</div></div>
    </div>
    {fin && <ValorERecorrencia id={id} lastAmount={m.last_monthly_amount} />}
    <Section title={tr("Meses")} tight><div className="tbl-wrap"><table className="tbl"><thead><tr><th>{tr("Mês")}</th><th>{tr("Invoice")}</th><th>{tr("Sessões usadas")}</th><th>{tr("Restantes / não usadas")}</th><th>{tr("Situação")}</th></tr></thead><tbody>
      {m.months.map(x => <tr key={x.month}><td style={{ textTransform: 'capitalize' }}>{mesNome(x.month)}</td>
        <td>{x.invoice ? <><span className="mono">{x.invoice.doc_number}</span> <Chip tone={statusTone(x.invoice.status === 'open' ? 'PENDING' : x.invoice.status)}>{x.invoice.status}</Chip>{fin && x.invoice.amount != null && <span className="mono"> {money(x.invoice.amount)}</span>}<div className="small muted">{x.invoice.memo}</div></> : <span className="muted">—</span>}</td>
        <td className="mono">{x.sessions_used}{x.sessions.length > 0 && <div className="small muted">{x.sessions.map(s => `${fmtDate(s.due_on)}${s.site ? ' (site)' : ''}`).join(' · ')}</div>}</td>
        <td className="mono">{x.closed ? (x.sessions_left ? <Chip tone="warn">{x.sessions_left} {tr("não usada(s)")}</Chip> : '0') : x.sessions_left}{x.sessions_over ? <div className="small">{x.sessions_over} {tr("acima")}</div> : null}</td>
        <td>{x.needs_invoice ? <Chip tone="warn">{tr("falta invoice")}</Chip> : x.invoice ? <Chip tone="ok">{tr("ok")}</Chip> : <span className="muted">{tr("sem uso")}</span>}</td></tr>)}
    </tbody></table></div></Section>
    <Section title={tr("Contrato da Academy")} count={m.contracts.length}>
      {/* #312: subir o contrato fica no topo da seção, antes da lista. O contrato já nasce no card deste cliente. */}
      {can('OPERATOR') && <InserirNoTopo rotulo={tr("Adicionar contrato")} titulo={tr("Subir o PDF do contrato")} nivel={3} dentro>
        <SubirContrato id={id} reload={reload} />
      </InserirNoTopo>}
      {m.contracts.length === 0 ? <div className="small muted">{tr("Nenhum contrato. Use \"Buscar nas plataformas\" para achar no DocuSign (assunto com Academy/contract) ou \"Adicionar contrato\", em cima.")}</div> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{tr("Contrato")}</th><th>{tr("Origem")}</th><th>{tr("Status")}</th><th>{tr("Assinado")}</th><th></th></tr></thead><tbody>
          {m.contracts.map(k => <tr key={k.id}><td>{k.title}</td><td>{k.source === 'docusign' ? tr("DocuSign") : tr("upload ({0})", k.added_by_name || '')}</td><td><Chip tone={statusTone(k.status)}>{k.status || '—'}</Chip></td><td className="mono">{fmtDate(k.signed_at)}</td><td><a className="btn sm" href={`/ops/api/contracts/${k.id}/download`}>{tr("⬇ PDF")}</a></td></tr>)}
        </tbody></table></div>}
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
  async function save() { setBusy(true); try { await api.patch(`/clients/${c.id}/profile`, { chassis_id: f.chassis_id || null, engine_id: f.engine_id || null, equipment_notes: f.equipment_notes }); toast(tr("Equipamento salvo."), 'ok'); reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) } }
  return <div className="stack">
    <div className="grid g2">
      <div className="field"><label>{tr("Chassi")}</label><select className="input" disabled={!can('OPERATOR')} value={f.chassis_id} onChange={e => setF({ ...f, chassis_id: Number(e.target.value) })}><option value={0}>—</option>{cat.chassis.filter(x => x.active).map(x => <option key={x.id} value={x.id}>{x.brand} {x.model || ''} {x.size ? `(${x.size})` : ''}</option>)}</select></div>
      <div className="field"><label>{tr("Motor")}</label><select className="input" disabled={!can('OPERATOR')} value={f.engine_id} onChange={e => setF({ ...f, engine_id: Number(e.target.value) })}><option value={0}>—</option>{cat.engines.filter(x => x.active).map(x => <option key={x.id} value={x.id}>{x.brand} {x.model} {x.stroke ? `· ${x.stroke}` : ''}</option>)}</select></div>
    </div>
    <div className="grid g2">
      {ch && <div className="card card-b"><div className="h2">{tr("Chassi")}</div>{ch.image_path && <img loading="lazy" decoding="async" src={`/ops/api/catalog/chassis/${ch.id}/image`} alt="" style={{ maxHeight: 140, borderRadius: 3, margin: '8px 0' }} />}<dl className="dl"><dt>{tr("Marca")}</dt><dd>{ch.brand} {ch.model}</dd><dt>{tr("Tamanho")}</dt><dd>{ch.size || '—'}</dd><dt>{tr("Pneu diant.")}</dt><dd className="mono">{ch.tire_front || '—'}</dd><dt>{tr("Pneu tras.")}</dt><dd className="mono">{ch.tire_rear || '—'}</dd>{ch.notes && <><dt>{tr("Notas")}</dt><dd className="small">{ch.notes}</dd></>}</dl></div>}
      {en && <div className="card card-b"><div className="h2">{tr("Motor")}</div>{en.image_path && <img loading="lazy" decoding="async" src={`/ops/api/catalog/engines/${en.id}/image`} alt="" style={{ maxHeight: 140, borderRadius: 3, margin: '8px 0' }} />}<dl className="dl"><dt>{tr("Motor")}</dt><dd>{en.brand} {en.model}</dd><dt>{tr("Tempos")}</dt><dd>{en.stroke || '—'}</dd><dt>{tr("Categoria")}</dt><dd>{en.category || '—'}</dd>{en.notes && <><dt>{tr("Notas")}</dt><dd className="small">{en.notes}</dd></>}</dl>
        <div className="h2" style={{ marginTop: 10 }}>{tr("Peças deste motor (")}{parts.length})</div>{parts.length === 0 ? <div className="small muted">{tr("Nenhuma peça cadastrada. Cadastre em Equipamentos.")}</div> : <ul style={{ margin: '4px 0', paddingLeft: 18 }}>{parts.map(p => <li key={p.id} className="small">{p.name}{p.part_number && <span className="mono muted"> {p.part_number}</span>}{p.price != null && <span className="muted"> · {money(p.price)}</span>}</li>)}</ul>}</div>}
    </div>
    <div className="field"><label>{tr("Notas de equipamento")}</label><TextoComVoz valor={f.equipment_notes} onChange={t => setF({ ...f, equipment_notes: t })} linhas={2} disabled={!can('OPERATOR')} placeholder={tr("ajustes, pneus usados, número do chassi, histórico (dá para ditar)")} /></div>
    {can('OPERATOR') && <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn primary" disabled={busy} onClick={save}>{busy ? <span className="spin" /> : tr("Salvar equipamento")}</button></div>}
    <details className="card card-b" style={{ marginTop: 4 }}><summary style={{ cursor: 'pointer' }}><b>{tr("Cadastrar ou editar chassis, motores e peças")}</b> <span className="small muted">{tr("(catálogo, vale para todos os pilotos)")}</span></summary>
      <div style={{ marginTop: 10 }}><CatalogoEditor data={cat} reload={reload} /></div></details>
  </div>
}

function CorridasDoPiloto({ rs, loading, cid }: { rs: Race[] | null; loading: boolean; cid: number }) {
  if (loading && !rs) return <Loading />
  const lista = rs || []
  return <div className="stack">
    {lista.length === 0 ? <Empty title={tr("Nenhuma corrida ainda")}>{tr("Convide este piloto no calendário de")} <Link to="/races">{tr("Corridas")}</Link>.</Empty> : <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{tr("Data")}</th><th>{tr("Corrida")}</th><th>{tr("Onde")}</th><th>{tr("Situação")}</th><th>{tr("Prévia")}</th></tr></thead><tbody>
      {lista.map(r => { const i = r.invited.find(x => x.client_id === cid); return <tr key={r.id}><td className="mono nowrap">{fmtDate(r.date_start)}</td><td><Link to="/races">{r.name}</Link>{!r.active && <span className="small muted"> {tr("(fora do calendário)")}</span>}</td><td className="small">{[r.track, r.city].filter(Boolean).join(' · ') || '—'}</td>
        <td>{i && <Chip tone={statusTone(i.status === 'confirmed' || i.status === 'done' ? 'COMPLETED' : i.status === 'declined' ? 'REJECTED' : 'PENDING')}>{({ invited: tr('aguardando confirmação'), confirmed: tr('confirmado'), declined: tr('não vai'), done: tr('correu') } as Record<string, string>)[i.status] || i.status}</Chip>}</td>
        <td className="small">{i?.estimate_text ? <Link to={i.estimate_cmd ? `/ai/${i.estimate_cmd}` : '/races'}>{tr("ver prévia")}</Link> : <span className="muted">—</span>}</td></tr> })}
    </tbody></table></div>}
    <div className="small muted">{tr("Convidar, confirmar e pedir a prévia de custo é no calendário de")} <Link to="/races">{tr("Corridas")}</Link>.</div>
  </div>
}

/* Conta no site (#42): a conta da área do cliente ligada a este card, os pilotos e as medidas. */
const MEDIDA_PT: Record<string, string> = { height_in: tr("Altura (pol)"), weight_lb: tr("Peso (lb)"), chest_in: tr("Peito (pol)"), waist_in: tr("Cintura (pol)"),
  hips_in: tr("Quadril (pol)"), inseam_in: tr("Entreperna (pol)"), sleeve_in: tr("Braço (pol)"), suit_size: tr("Macacão"), helmet_size: tr("Capacete"), glove_size: tr("Luva"), shoe_size: tr("Sapatilha (US)") }
interface ContaCard { email: string; name: string; phone: string | null; birth_date: string; address_line1: string | null; city: string | null; state: string | null; zip: string | null
  linked_at: string | null; last_login_at: string | null; driver_id: number | null
  drivers: { id: number; name: string; birth_date: string | null; is_self: number; client_id: number | null; measures: Record<string, number | string>; measures_updated_at: string | null }[] }
function ContaNoSite({ cid }: { cid: number }) {
  const d = useGet<{ conta: ContaCard | null }>(`/site/contas/do-cliente/${cid}`)
  if (d.error) return <ErrorState error={d.error} retry={d.reload} />
  if (!d.data) return <Loading />
  const c = d.data.conta
  if (!c) return <Empty title={tr("Sem conta no site")}>{tr("Quando a conta da área do cliente for ligada a este card (Site › Contas de clientes), os pilotos e as medidas aparecem aqui.")}</Empty>
  return <div className="stack">
    <div><b>{c.name}</b> <span className="small muted">· {c.email}{c.phone ? ` · ${c.phone}` : ''}</span>
      <div className="small muted">{[c.address_line1, c.city, c.state, c.zip].filter(Boolean).join(', ') || tr("sem endereço")}{c.last_login_at ? tr(" · último acesso {0}/{1}", c.last_login_at.slice(8, 10), c.last_login_at.slice(5, 7)) : ''}</div></div>
    {/* #313: cada piloto da conta no cartão D, com as medidas na lista */}
    <div className="cd-grade">{c.drivers.map(p => <Cartao key={p.id} id={`piloto-${p.id}`} nivel={2}
      estado={p.id === c.driver_id ? tr("este card") : p.client_id ? `${tr("Client ID")} ${p.client_id}` : tr("sem card")} tom={p.id === c.driver_id ? 'ok' : p.client_id ? 'info' : 'warn'}
      avatar={p.name} nome={p.name}
      sub={[p.is_self ? tr("o próprio responsável") : null,
        `${p.birth_date ? tr("nascimento {0}/{1}/{2}", p.birth_date.slice(8, 10), p.birth_date.slice(5, 7), p.birth_date.slice(0, 4)) : tr("sem nascimento")}${p.measures_updated_at ? tr(" · medido em {0}/{1}", p.measures_updated_at.slice(8, 10), p.measures_updated_at.slice(5, 7)) : ''}`,
        !p.client_id ? tr("Site › Contas de clientes") : null]}
      acoes={p.client_id && p.id !== c.driver_id ? <Link className="btn" to={`/clients/${p.client_id}`}>{tr("Client ID")} {p.client_id}</Link> : null}>
      {Object.keys(p.measures).length > 0 && <CdLista>{Object.entries(p.measures).map(([k, v]) => <CdItem key={k} tom="neutral" valor={String(v)}>{MEDIDA_PT[k] || k}</CdItem>)}</CdLista>}
    </Cartao>)}</div>
  </div>
}

/** #165: o QR à mão, do topo do card (dono, 08/10: "precisa estar lá"). */
function QrModal({ cid, nome, onClose }: { cid: number; nome: string; onClose: () => void }) {
  const src = `/ops/api/balcao/cliente/${cid}/qr.svg`
  return <Scrim onMouseDown={onClose}><div className="modal qr-modal" style={{ maxWidth: 380 }} role="dialog" aria-modal="true" aria-label={tr("QR do balcão de {0}", nome)} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label={tr("Fechar")}>✕</button>
    <h3 className="h3" style={{ margin: 0 }}>{tr("QR do balcão ·")} {nome}</h3>
    <img className="qr-cliente" src={src} alt={tr("QR do balcão de {0}", nome)} width={260} height={260} />
    <p className="small muted" style={{ margin: 0 }}>{tr("O mecânico lê este QR e depois as peças: elas entram na invoice de peças do dia. O cliente tem o mesmo QR na área dele (my.urace.us).")}</p>
    <div className="row wrap" style={{ gap: 8, justifyContent: 'center' }}><a className="btn sm" href={src} target="_blank" rel="noreferrer">{tr("Imprimir")}</a>
      <Link className="btn sm primary" to={`/balcao/${cid}`}>{tr("Abrir no balcão")}</Link></div>
  </div></Scrim>
}

/** #87: o QR do card, para o leitor do balcão. Imprime num cartão ou adesivo; o código é aleatório, não o id. */
function QrBalcao({ cid, nome }: { cid: number; nome: string }) {
  const src = `/ops/api/balcao/cliente/${cid}/qr.svg`
  return <div className="card card-b row wrap" style={{ gap: 14, alignItems: 'center', marginBottom: 12 }}>
    <img className="qr-cliente" src={src} alt={tr("QR do balcão de {0}", nome)} width={160} height={160} />
    <div className="grow stack" style={{ gap: 6 }}>
      <h3 className="h3" style={{ margin: 0 }}>{tr("QR do balcão")}</h3>
      <p className="small muted" style={{ margin: 0 }}>{tr("O mecânico lê este QR e depois as peças: elas entram na invoice de peças do dia de")} {nome}.</p>
      <div className="row wrap" style={{ gap: 8 }}><a className="btn sm" href={src} target="_blank" rel="noreferrer">{tr("Imprimir")}</a>
        <Link className="btn sm ghost" to={`/balcao/${cid}`}>{tr("Abrir no balcão")}</Link></div>
    </div>
  </div>
}

/* #135 (dono, 14/10): convite da waiver por e-mail, para o e-mail do card. Piloto com 18+ assina a
 * própria; menor, o responsável. A tela mostra para quem vai e pede confirmação; sem e-mail (ou sem
 * nascimento, ou com a assinatura nativa desligada) o botão fica desligado e diz por quê. */
interface DestinoConvite { client_id: number; kind: 'adult' | 'parental' | null; signer_name: string | null; email: string | null
  driver_name: string; driver_birth_date: string | null; age: number | null; responsible: string; enabled: boolean
  can_send: boolean; reason: string | null; valid_hours: number; valid_waiver_until: string | null }
interface ConviteFeito { id: number; kind: 'adult' | 'parental'; signer_name: string; email: string; driver_name: string
  created_at: string; created_by: string; created_by_name: string | null; expires_at: string; sent_at: string | null
  opened_at: string | null; used_at: string | null; waiver_id: number | null; revoked_reason: string | null
  status: 'sent' | 'opened' | 'signed' | 'expired' | 'replaced' | 'failed' }
const CONVITE_ST: Record<ConviteFeito['status'], [string, 'ok' | 'warn' | 'crit' | 'info' | 'neutral']> = {
  sent: [tr("enviado"), 'info'], opened: [tr("aberto"), 'warn'], signed: [tr("assinado"), 'ok'], expired: [tr("expirado"), 'crit'],
  replaced: [tr("substituído"), 'neutral'], failed: [tr("não saiu"), 'crit'] }

function ConviteWaiver({ cid, onMuda }: { cid: number; onMuda?: () => void }) {
  const d = useGet<{ destino: DestinoConvite; convites: ConviteFeito[] }>(`/clients/${cid}/waiver-invite`)
  const perguntar = usePerguntar()
  const toast = useToast()
  const [indo, setIndo] = useState(false)
  if (d.error) return <ErrorState error={d.error} retry={d.reload} />
  if (!d.data) return <Loading rows={2} />
  const { destino: x, convites } = d.data
  const aberto = convites.find(c => c.status === 'sent' || c.status === 'opened')
  async function enviar() {
    if (!x.can_send || !x.email) return
    const ok = await perguntar({
      titulo: aberto ? tr("Reenviar o convite da waiver?") : tr("Enviar o convite da waiver por e-mail?"),
      ok: aberto ? tr("Reenviar") : tr("Enviar"),
      texto: <div className="stack" style={{ gap: 6 }}>
        <div>{tr("Para:")} <b>{x.signer_name}</b> · <b className="mono">{x.email}</b></div>
        <div className="small">{x.kind === 'adult'
          ? tr("{0} tem {1} anos: assina a própria waiver (adult).", x.driver_name, x.age ?? '?')
          : tr("{0} tem {1} anos: o responsável assina por ele (parental, pai ou mãe).", x.driver_name, x.age ?? '?')}</div>
        <div className="small muted">{tr("O link é pessoal, vale uma vez e vence em {0} h.", x.valid_hours)}{aberto ? ' ' + tr("O link anterior deixa de valer.") : ''}</div>
        {x.valid_waiver_until && <div className="small" style={{ color: 'var(--warn)' }}>{tr("Este card já tem waiver {0} válida até {1}.", x.kind || '', fmtDate(x.valid_waiver_until))}</div>}
      </div> })
    if (!ok) return
    setIndo(true)
    try { await api.post(`/clients/${cid}/waiver-invite`, { email: x.email }); toast(tr("Convite enviado para {0}.", x.email), 'ok'); d.reload(); onMuda?.() }
    catch (e) { toast((e as ApiError).message, 'crit'); d.reload() } finally { setIndo(false) }
  }
  return <div className="card card-b stack convite-waiver" style={{ gap: 10, marginBottom: 12 }}>
    <div className="row wrap" style={{ gap: 10 }}>
      <h3 className="h3 grow" style={{ margin: 0 }}>{tr("Convite da waiver por e-mail")}</h3>
      <button className="btn primary" disabled={!x.can_send || indo} onClick={enviar}
        title={x.reason || undefined} aria-describedby={x.reason ? `cw-motivo-${cid}` : undefined}>
        {indo ? <span className="spin" /> : '✉'} {aberto ? tr("Reenviar convite da waiver") : tr("Enviar convite da waiver por e-mail")}</button>
    </div>
    {x.can_send
      ? <p className="small muted" style={{ margin: 0 }}>{tr("Vai para")} <b>{x.signer_name}</b> · {x.email} · {x.kind === 'adult' ? tr("adulto: assina a própria") : tr("menor: o responsável assina")}</p>
      : <p className="small" id={`cw-motivo-${cid}`} style={{ margin: 0, color: 'var(--warn)' }}>{x.reason}</p>}
    {convites.length > 0 && <ul className="convites">{convites.map(c => <li key={c.id} className="row wrap" style={{ gap: 8 }}>
      <Chip tone={CONVITE_ST[c.status][1]}>{CONVITE_ST[c.status][0]}</Chip>
      <span className="small">{c.signer_name} · {c.email}</span>
      <span className="small muted">{tr("enviado {0}", fmtDateTime(c.sent_at || c.created_at))}{c.created_by === 'ia' ? tr(" pela IA") : c.created_by_name ? tr(" por {0}", c.created_by_name) : ''}
        {c.opened_at && <> · {tr("aberto {0}", fmtDateTime(c.opened_at))}</>}
        {c.used_at && <> · {tr("assinado {0}", fmtDateTime(c.used_at))}</>}
        {!c.used_at && (c.status === 'sent' || c.status === 'opened') && <> · {tr("vence {0}", fmtDateTime(c.expires_at))}</>}</span>
    </li>)}</ul>}
  </div>
}
