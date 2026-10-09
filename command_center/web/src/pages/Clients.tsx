import { PuxarHistorico, UnirModal } from '../components/Unir'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useGet } from '../api/hooks'
import type { Client } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Progress, Scrim, Section, Spinner, Status, WAIVER_LABEL, statusKind } from '../components/ui'
import { daysUntil, fmtDate } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'
import { ClientCard } from './Client360'
import { TextoComVoz } from '../components/Voz'
import { tr } from '../i18n'

type Par = { a: Client; b: Client; why: string }
type Parecer = { mesma_pessoa: boolean | null; confianca: string; motivo: string }

function Duplicados({ onChanged }: { onChanged: () => void }) {
  const { can } = useAuth()
  const perguntar = usePerguntar()
  const toast = useToast()
  const { data, loading, reload } = useGet<{ pairs: Par[]; merged: { id: number; keep_id: number; drop_name: string; reason: string; merged_by: string; merged_at: string }[] }>('/client-duplicates')
  const [ia, setIa] = useState<Record<string, Parecer> | null>(null)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  async function unir(keep: Client, drop: Client) {
    if (!await perguntar({ titulo: tr("Unir \"{0}\" em \"{1}\"?", drop.pilot_name || drop.name, keep.pilot_name || keep.name), texto: tr("Serviços, waivers e e-mails do segundo passam para o primeiro. O registro unido fica guardado e auditado."), ok: tr("Unir") })) return
    try { await api.post('/client-merge', { keep_id: keep.id, drop_id: drop.id, reason: 'mesma pessoa (revisão humana)' }); toast(tr("Unidos."), 'ok'); reload(); onChanged() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function parecerDaIa() {
    setBusy(true)
    try {
      await api.post('/client-duplicates/ai')
      for (let i = 0; i < 90; i++) {
        await new Promise(r => setTimeout(r, 4000))
        const st = await api.get<{ running: boolean; result: { pareceres?: Record<string, Parecer>; erro?: string } | null }>('/client-duplicates/ai')
        if (!st.running) { if (st.result?.erro) toast(tr("IA falhou: {0}", st.result.erro), 'crit'); else { setIa(st.result?.pareceres || {}); toast(tr("A IA deu o parecer de cada par."), 'ok') } break }
      }
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  const n = data?.pairs.length ?? 0
  if (!loading && n === 0 && !(data?.merged.length)) return null
  return <Section title={tr("Possíveis duplicados")} count={n} right={<div className="row">{n > 0 && can('OPERATOR') && <button className="btn sm" disabled={busy} onClick={parecerDaIa}>{busy ? <Spinner /> : '✦'} {tr("Pedir parecer da IA")}</button>}<button className="btn ghost sm" onClick={() => setOpen(o => !o)}>{open ? tr("esconder") : tr("ver")}</button></div>}>
    {!open ? <div className="small muted">{n} {tr("par(es) com nomes quase iguais esperando decisão")}{data?.merged.length ? tr(" · {0} união(ões) feitas", data.merged.length) : ''}.</div> : <>
      {n === 0 && <div className="small muted">{tr("Nenhum par pendente.")}</div>}
      {(data?.pairs || []).map(p => { const par = ia?.[`${p.a.id}-${p.b.id}`]; return <div className="act" key={`${p.a.id}-${p.b.id}`}>
        <div className="grow"><b>{p.a.pilot_name || p.a.name}</b> <span className="muted small">{p.a.email || tr("sem e-mail")} · {p.a.phone || tr("sem tel")}</span> <span className="muted">{tr("×")}</span> <b>{p.b.pilot_name || p.b.name}</b> <span className="muted small">{p.b.email || tr("sem e-mail")} · {p.b.phone || tr("sem tel")}</span>
          <div className="small muted">{p.why}</div>
          {par && <div className="small" style={{ marginTop: 4 }}><Chip tone={par.mesma_pessoa === true ? 'ok' : par.mesma_pessoa === false ? 'crit' : 'neutral'}>✦ {par.mesma_pessoa === true ? tr("mesma pessoa") : par.mesma_pessoa === false ? tr("pessoas diferentes") : tr("não deu para saber")} · {par.confianca}</Chip> {par.motivo}</div>}</div>
        {can('OPERATOR') && <div className="row"><button className="btn sm primary" onClick={() => unir(p.a, p.b)}>{tr("Unir →")} {p.a.pilot_name || p.a.name}</button><button className="btn sm" onClick={() => unir(p.b, p.a)}>{tr("Unir →")} {p.b.pilot_name || p.b.name}</button></div>}
      </div> })}
      {!!data?.merged.length && <div className="small muted" style={{ marginTop: 10 }}>{tr("Uniões:")} {data.merged.slice(0, 8).map(m => `${m.drop_name} (${m.reason}, ${m.merged_by === 'sync' ? 'automático' : 'à mão'})`).join(' · ')}</div>}
    </>}
  </Section>
}

function NovoCliente({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const toast = useToast()
  const [f, setF] = useState({ name: '', pilot_name: '', pilot_dob: '', email: '', phone: '', company: '', notes: '', vip: false })
  const [busy, setBusy] = useState(false)
  async function save() {
    setBusy(true)
    try { const r = await api.post<{ id: number; created: boolean }>('/clients', f); toast(r.created ? tr("Cliente criado.") : tr("Esse cliente já existia: abrindo o card dele."), 'ok'); onCreated(r.id); onClose() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 640 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose}>✕</button>
    <div><h2 className="h1" style={{ fontSize: 22 }}>{tr("Novo cliente")}</h2><div className="small muted">{tr("O responsável é quem paga e assina. Se já existir alguém com o mesmo e-mail, telefone ou nome, o card existente abre em vez de duplicar.")}</div></div>
    <div className="grid g2">
      <div className="field"><label>{tr("Responsável *")}</label><input className="input" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>
      <div className="field"><label>{tr("Piloto (se for outra pessoa)")}</label><input className="input" value={f.pilot_name} onChange={e => setF({ ...f, pilot_name: e.target.value })} /></div>
      <div className="field"><label>{tr("E-mail")}</label><input className="input" type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></div>
      <div className="field"><label>{tr("Telefone")}</label><input className="input" value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} /></div>
      <div className="field"><label>{tr("Nascimento do piloto")}</label><input className="input" type="date" value={f.pilot_dob} onChange={e => setF({ ...f, pilot_dob: e.target.value })} /></div>
      <div className="field"><label>{tr("Empresa")}</label><input className="input" value={f.company} onChange={e => setF({ ...f, company: e.target.value })} /></div>
    </div>
    <div className="field"><label>{tr("Notas")}</label><TextoComVoz valor={f.notes} onChange={t => setF({ ...f, notes: t })} linhas={2} placeholder={tr("Dá para ditar")} /></div>
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onClose}>{tr("Cancelar")}</button><button className="btn primary" disabled={busy || f.name.trim().length < 2} onClick={save}>{busy ? <Spinner /> : tr("Salvar e abrir o card")}</button></div>
  </div></Scrim>
}

export function Clients() {
  const { can } = useAuth()
  const toast = useToast()
  const [novo, setNovo] = useState(false)
  const [unirManual, setUnirManual] = useState(false)
  const [sp, setSp] = useSearchParams()
  const [q, setQ] = useState(sp.get('q') || '')
  const status = sp.get('status') || ''
  const vip = sp.get('vip') || ''
  const openId = sp.get('open') ? Number(sp.get('open')) : null
  const [scanning, setScanning] = useState(false)
  const aba = sp.get('v') === 'pro' ? 'pro' : 'all'
  useEffect(() => {
    if ((sp.get('q') || '') === q) return
    const t = setTimeout(() => { const n = new URLSearchParams(window.location.search); if (q) n.set('q', q); else n.delete('q'); setSp(n, { replace: true }) }, 250)
    return () => clearTimeout(t)
  }, [q]) // eslint-disable-line react-hooks/exhaustive-deps
  const { data, error, loading, reload } = useGet<Client[]>('/clients' + qs({ q: sp.get('q'), status, vip: vip === '' ? undefined : vip === '1', pro: aba === 'pro' ? true : undefined }))
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n) }
  const open = (id: number | null) => { const n = new URLSearchParams(sp); if (id) n.set('open', String(id)); else n.delete('open'); setSp(n) }
  useEffect(() => {
    if (!openId) return
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape' && !document.querySelector('.modal.ask, .lpick-menu, details.more[open]')) open(null) }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [openId]) // eslint-disable-line react-hooks/exhaustive-deps
  const rows = data || []                                       // ordem do servidor: serviço mais recente primeiro
  const ativos = rows.filter(c => c.status === 'ACTIVE').length
  async function scanAll() {
    setScanning(true)
    try {
      const r = await api.post<{ started: boolean; total: number }>('/client-scan-all')
      toast(r.started ? tr("Varrendo Gmail e DocuSign de todos os clientes ativos. Pode levar vários minutos.") : tr("Já há uma varredura rodando."))
      for (let i = 0; i < 300; i++) {
        await new Promise(res => setTimeout(res, 5000))
        const st = await api.get<{ running: boolean; done: number; total: number; result: { gmail?: number; docusign?: number; erro?: string } | null }>('/client-scan-all')
        if (!st.running) { toast(st.result?.erro ? tr("Varredura falhou: {0}", st.result.erro) : tr("Varredura: {0} threads de e-mail e {1} waivers ligadas.", st.result?.gmail ?? 0, st.result?.docusign ?? 0), st.result?.erro ? 'crit' : 'ok'); break }
      }
      reload()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setScanning(false) }
  }
  return <>
    <Progress on={scanning} />
    <PageHeader title={tr("Clientes")} help={tr("Um card por pessoa, do serviço mais recente para o mais antigo. Ativo = serviço nos últimos 6 meses. Piloto em destaque; o responsável (quem paga e assina) ao lado.")}>
      {can('OPERATOR') && <button className="btn primary" onClick={() => setNovo(true)}>{tr("+ Novo cliente")}</button>}
      {can('OPERATOR') && <details className="more"><summary className="btn" title={tr("Ferramentas: varrer plataformas, unir cards, puxar histórico")}>⋯</summary><div className="menu">
        <button className="btn ghost sm" disabled={scanning} onClick={scanAll} title={tr("Gmail (as duas caixas) e DocuSign de cada cliente ativo")}>{scanning ? <Spinner /> : '⌕'} {tr("Varrer plataformas (")}{ativos} {tr("ativos)")}</button>
        <button className="btn ghost sm" onClick={() => setUnirManual(true)}>{tr("⧉ Unir dois clientes")}</button>
        <PuxarHistorico onDone={reload} />
        <div className="small muted" style={{ padding: '4px 8px', maxWidth: 280 }}>{tr("Puxar histórico lê todas as tarefas de treino do Asana, desde o início, e liga cada uma à pessoa certa; possíveis duplicados aparecem abaixo.")}</div>
      </div></details>}
    </PageHeader>
    <div className="tabs"><button className={aba === 'all' ? 'on' : ''} onClick={() => set('v', '')}>{tr("Todos")}</button><button className={aba === 'pro' ? 'on' : ''} onClick={() => set('v', 'pro')}>{tr("★ Pro Racing Drivers")}</button></div>
    {aba === 'pro' && <Banner tone="info">{tr("Pilotos prontos para competir. No card do cliente, o botão")} <b>{tr("★ Tornar Pro")}</b> {tr("traz ele para cá e libera equipamento e corridas. Convites e prévia de custo ficam no calendário de")} <a href="/ops/races">{tr("Corridas")}</a>.</Banner>}
    <div className="row wrap toolbar-page">
      <input className="input" style={{ maxWidth: 320 }} placeholder={tr("Piloto, responsável ou e-mail")} value={q} onChange={e => setQ(e.target.value)} aria-label={tr("Filtrar")} />
      <select className="input" style={{ width: 190 }} value={status} onChange={e => set('status', e.target.value)} aria-label={tr("Status")}>
        <option value="">{tr("Ativos e inativos")}</option><option value="ACTIVE">{tr("Ativos (6 meses)")}</option><option value="INACTIVE">{tr("Inativos")}</option><option value="NEW">{tr("Novos")}</option><option value="PENDING">{tr("Pendentes")}</option><option value="AT_RISK">{tr("Em risco")}</option><option value="COMPLETED">{tr("Concluídos")}</option><option value="SEPARADO">{tr("Separados (não são clientes)")}</option>
      </select>
      <select className="input" style={{ width: 130 }} value={vip} onChange={e => set('vip', e.target.value)} aria-label={tr("VIP")}>
        <option value="">{tr("VIP e não")}</option><option value="1">{tr("Só VIP")}</option><option value="0">{tr("Sem VIP")}</option>
      </select>
      <div className="grow" /><button className="btn" onClick={reload} aria-label={tr("Atualizar")}>↻</button>
    </div>
    {unirManual && <UnirModal onClose={() => setUnirManual(false)} onDone={() => reload()} />}
    <Duplicados onChanged={reload} />
    <Section title={tr("Clientes")} count={rows.length} tight>
      {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading rows={8} /> :
        rows.length === 0 ? <Empty title={tr("Nenhum cliente")}>{tr("Sem registros com esse filtro. Se a lista está vazia, rode “Sincronizar agora” no Dashboard.")}</Empty> :
        <div className="tbl-wrap"><table className="tbl rsp">
          <thead><tr><th>{tr("Piloto")}</th><th>{tr("Responsável e contato")}</th><th>{tr("Status")}</th><th>{tr("Próximo serviço")}</th><th className="hide-md">{tr("Último")}</th><th>{tr("Waiver")}</th><th>{tr("Serviços")}</th><th>{tr("E-mails")}</th></tr></thead>
          <tbody>{rows.map(c => {
            const dias = daysUntil(c.next_service)
            const w = (c.waiver_status || '').toLowerCase()
            const semWaiver = dias !== null && dias <= 2 && w !== 'completed' && !c.vip
            return <tr key={c.id} className="click" onClick={() => open(c.id)} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') open(c.id) }}>
              <td className="first"><div className="row">{!!c.pro_driver && <span title={tr("Pro Racing Driver")} style={{ color: 'var(--warn)' }}>★</span>}<b>{c.pilot_name || c.name}</b>{!!c.vip && <Chip tone="warn">{tr("VIP")}</Chip>}{c.plan_type === 'monthly' && <Chip tone="accent">{tr("mensal")}</Chip>}{c.plan_type === 'daily' && <Chip tone="outline">{tr("diária")}</Chip>}</div>{!c.pilot_name && <div className="small muted">{tr("piloto é o próprio")}</div>}</td>
              <td data-l={tr("Responsável")}>{c.pilot_name ? c.name : <span className="muted">{tr("o próprio")}</span>}<div className="small muted truncate" style={{ maxWidth: 260 }}>{c.email || tr("sem e-mail")}{c.phone ? ` · ${c.phone}` : ''}</div></td>
              <td data-l={tr("Status")}><Status s={c.status} />{!!c.status_locked && <span className="small muted" title={tr("mudado à mão")}> 🔒</span>}</td>
              <td data-l={tr("Próximo")} className="mono nowrap">{c.next_service ? <><b style={{ color: dias !== null && dias <= 1 ? 'var(--brand)' : undefined }}>{dias === 0 ? tr("HOJE") : dias === 1 ? tr("AMANHÃ") : tr("em {0} d", dias)}</b> <span className="muted small">{fmtDate(c.next_service)}</span></> : <span className="muted">—</span>}</td>
              <td data-l={tr("Último")} className="mono hide-md">{c.last_service ? fmtDate(c.last_service) : <span className="muted">—</span>}</td>
              <td data-l={tr("Waiver")}>{c.vip ? <Chip tone="neutral" glyph="—">{tr("dispensada (VIP)")}</Chip> : w ? <Status s={w} kind={semWaiver ? 'crit' : statusKind(w)} label={WAIVER_LABEL[w] || w} /> : <Status kind={semWaiver ? 'crit' : 'wait'} label={tr("nenhuma")} />}</td>
              <td data-l={tr("Serviços")} className="mono nowrap"><b>{c.open_tasks ?? 0}</b><span className="muted">/{(c.open_tasks ?? 0) + (c.done_tasks ?? 0)}</span> <span className="small muted">{tr("abertos")}</span></td>
              <td data-l={tr("E-mails")} className="mono">{c.emails_open ? <span style={{ color: 'var(--warn)', fontWeight: 700 }}>▲ {c.emails_open} {tr("sem resposta")}</span> : <span className="muted">—</span>}</td>
            </tr>
          })}</tbody>
        </table></div>}
    </Section>
    {novo && <NovoCliente onClose={() => setNovo(false)} onCreated={id => { reload(); open(id) }} />}
    {openId && <Scrim onMouseDown={() => open(null)}>
      <div className="modal" onMouseDown={e => e.stopPropagation()} role="dialog" aria-label={tr("Card do cliente")}>
        <button className="btn ghost sm close" onClick={() => open(null)} aria-label={tr("Fechar")} title={tr("Fechar (Esc)")}>✕</button>
        <ClientCard id={openId} onClose={() => open(null)} />
      </div>
    </Scrim>}
  </>
}
