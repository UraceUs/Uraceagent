/* Unir dois clientes à mão (Brian Santiago escrito de dois jeitos) e puxar o histórico
   completo do Asana — pedidos do dono em 09/09. */
import { useEffect, useId, useState } from 'react'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { Client } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Scrim, Spinner } from './ui'
import { usePerguntar } from './Perguntar'
import { useToast } from './Toast'
import { tr } from '../i18n'

type Sug = Client & { why?: string }

export function Picker({ label, value, onPick, exclude, sugestoes }: { label: string; value: Client | null; onPick: (c: Client | null) => void; exclude?: number; sugestoes?: Sug[] }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const id = useId()
  const lista = useGet<Client[]>(q.trim().length >= 2 ? `/clients?q=${encodeURIComponent(q.trim())}` : null)
  const hits = (lista.data || []).filter(c => c.id !== exclude).slice(0, 10)
  if (value) return <div className="field"><label>{label}</label><div className="row wrap"><b>{value.pilot_name || value.name}</b><span className="small muted">{value.pilot_name && value.pilot_name !== value.name ? tr("resp. {0} · ", value.name) : ''}{value.email || tr("sem e-mail")} · {value.phone || tr("sem tel")}</span><button className="btn ghost sm" onClick={() => onPick(null)}>{tr("trocar")}</button></div></div>
  return <div className="field"><label htmlFor={id}>{label}</label>
    <div className="lpick"><input id={id} className="input" value={q} placeholder={tr("Digite o nome do piloto ou do responsável…")} onFocus={() => setOpen(true)} onChange={e => { setQ(e.target.value); setOpen(true) }} />
      {open && (q.trim().length >= 2 || (sugestoes && sugestoes.length > 0)) && <div className="lpick-menu">
        {q.trim().length < 2 && sugestoes?.map(s => <div key={s.id} className="opt" onMouseDown={ev => { ev.preventDefault(); onPick(s); setOpen(false) }}><span className="truncate">✦ {s.pilot_name || s.name}</span><span className="c">{s.why}</span></div>)}
        {q.trim().length >= 2 && (lista.loading && !lista.data ? <div className="small muted" style={{ padding: '6px 10px' }}>{tr("buscando…")}</div> : hits.length === 0 ? <div className="small muted" style={{ padding: '6px 10px' }}>{tr("Nenhum cliente com “")}{q}”.</div> :
          hits.map(c => <div key={c.id} className="opt" onMouseDown={ev => { ev.preventDefault(); onPick(c); setOpen(false) }}><span className="truncate">{c.pilot_name || c.name}{c.pilot_name && c.pilot_name !== c.name ? <span className="muted"> {tr("· resp.")} {c.name}</span> : null}</span><span className="c">{c.email || c.phone || ''}</span></div>))}
      </div>}
    </div></div>
}

/** keep = cliente fixo (aberto no card). Sem keep, escolhe os dois. */
export function UnirModal({ keep, onClose, onDone }: { keep?: Client; onClose: () => void; onDone: (keepId: number) => void }) {
  const perguntar = usePerguntar()
  const toast = useToast()
  const [a, setA] = useState<Client | null>(keep || null)
  const [b, setB] = useState<Client | null>(null)
  const [manter, setManter] = useState<'a' | 'b'>('a')
  const [busy, setBusy] = useState(false)
  const sug = useGet<Sug[]>(keep ? `/clients/${keep.id}/duplicates` : null)
  const ka = manter === 'a' ? a : b; const kb = manter === 'a' ? b : a
  async function unir() {
    if (!ka || !kb) return
    if (!await perguntar({ titulo: tr("Unir \"{0}\" em \"{1}\"?", kb.pilot_name || kb.name, ka.pilot_name || ka.name), texto: tr("Todos os serviços, waivers, e-mails e invoices do segundo passam para o primeiro. O segundo sai da lista (fica guardado e auditado)."), ok: tr("Unir") })) return
    setBusy(true)
    try { const r = await api.post<{ ok: boolean; moved: Record<string, number> }>('/client-merge', { keep_id: ka.id, drop_id: kb.id, reason: 'mesma pessoa (unido à mão)' }); toast(tr("Unidos: {0} serviço(s), {1} waiver(s), {2} e-mail(s), {3} invoice(s) passaram para {4}.", r.moved.tasks, r.moved.waivers, r.moved.emails, r.moved.invoices, ka.pilot_name || ka.name), 'ok'); onDone(ka.id); onClose() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 640 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label={tr("Fechar")}>✕</button>
    <div><h2 className="h1" style={{ fontSize: 22 }}>{tr("Unir dois clientes")}</h2><div className="small ink2">{tr("A mesma pessoa escrita de dois jeitos vira um card só. Nada é apagado dos sistemas de origem.")}</div></div>
    {keep && sug.data && sug.data.length > 0 && !b && <div className="small">{tr("✦ Parece duplicado de:")} {sug.data.map(s => <button key={s.id} className="lchip" style={{ marginRight: 4 }} title={s.why} onClick={() => setB(s)}>{s.pilot_name || s.name}</button>)}</div>}
    <Picker label={keep ? tr("Este cliente") : tr("Cliente 1")} value={a} onPick={setA} exclude={b?.id} />
    <Picker label={keep ? tr("Unir com") : tr("Cliente 2")} value={b} onPick={setB} exclude={a?.id} sugestoes={sug.data || undefined} />
    {a && b && <div className="field"><label>{tr("Qual card fica?")}</label><div className="row wrap">
      <label className="check"><input type="radio" checked={manter === 'a'} onChange={() => setManter('a')} /> {a.pilot_name || a.name} <Chip tone="outline">{a.status}</Chip></label>
      <label className="check"><input type="radio" checked={manter === 'b'} onChange={() => setManter('b')} /> {b.pilot_name || b.name} <Chip tone="outline">{b.status}</Chip></label>
    </div><div className="small muted">{tr("O que faltar no card que fica (e-mail, telefone, nascimento) é completado com o do outro.")}</div></div>}
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onClose}>{tr("Cancelar")}</button><button className="btn primary" disabled={busy || !a || !b} onClick={unir}>{busy ? <Spinner /> : tr("Unir")}</button></div>
  </div></Scrim>
}

interface Full { running: boolean; stage: string | null; done: number; total: number | null; started_at: string | null; result: { ok?: boolean; motivo?: string; tarefas?: number; lidas?: number; clientes_novos?: number; unidos?: number; removidos?: number; candidatos?: number } | null }

/** Botão "Puxar histórico completo do Asana" com progresso. Só gerente/admin. */
export function PuxarHistorico({ onDone }: { onDone: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const [st, setSt] = useState<Full | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmar, setConfirmar] = useState(false)
  useEffect(() => { api.get<Full>('/sync/full').then(setSt).catch(() => undefined) }, [])
  useEffect(() => {
    if (!st?.running) return
    const t = setInterval(async () => { try { const s = await api.get<Full>('/sync/full'); setSt(s); if (!s.running) { clearInterval(t); const r = s.result || {}; toast(r.ok === false ? tr("Histórico parou: {0}", r.motivo) : tr("Histórico puxado: {0} tarefas, {1} clientes novos, {2} unidos sozinhos, {3} par(es) para você decidir.", r.tarefas ?? 0, r.clientes_novos ?? 0, r.unidos ?? 0, r.candidatos ?? 0), r.ok === false ? 'crit' : 'ok'); onDone() } } catch { /* tenta de novo */ } }, 3000)
    return () => clearInterval(t)
  }, [st?.running]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!can('MANAGER')) return null
  async function puxar() {
    setBusy(true); setConfirmar(false)
    try { const r = await api.post<Full & { started: boolean }>('/sync/full'); setSt(r); toast(r.started ? tr("Puxando o histórico do Asana…") : tr("Já tem uma sincronia rodando. Espere ela acabar.")) } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  const r = st?.result
  return <>
    <button className="btn" disabled={busy || !!st?.running} onClick={() => setConfirmar(true)} title={tr("Todas as tarefas de todas as colunas, desde a criação do quadro")}>{st?.running ? <><Spinner /> {st.stage}{st.total ? ` ${st.done}/${st.total}` : ''}</> : tr("⟳ Puxar histórico do Asana")}</button>
    {confirmar && <Scrim onMouseDown={() => setConfirmar(false)}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()}>
      <button className="btn ghost sm close" onClick={() => setConfirmar(false)} aria-label={tr("Fechar")}>✕</button>
      <div><h2 className="h1" style={{ fontSize: 22 }}>{tr("Puxar o histórico completo")}</h2>
        <div className="small ink2">{tr("Lê todas as colunas do quadro U-RACE menos “Matt tasks”, concluídas incluídas, e liga cada serviço à pessoa certa. Pode levar vários minutos; a sincronia normal espera. Nada é apagado no Asana.")}</div></div>
      <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={() => setConfirmar(false)}>{tr("Cancelar")}</button><button className="btn primary" disabled={busy} onClick={puxar}>{busy ? <Spinner /> : tr("Puxar agora")}</button></div>
    </div></Scrim>}
    {r && !st?.running && <Banner tone={r.ok === false ? 'crit' : 'ok'}>{r.ok === false ? tr("Histórico parou: {0}", r.motivo) :
      <>{tr("Histórico puxado:")} <b>{r.tarefas ?? 0}</b> {tr("tarefas,")} <b>{r.clientes_novos ?? 0}</b> {tr("clientes novos,")} <b>{r.unidos ?? 0}</b> {tr("unidos sozinhos,")} <b>{r.removidos ?? 0}</b> {tr("não-clientes removidos,")} <b>{r.candidatos ?? 0}</b> {tr("par(es) para você decidir abaixo.")}</>}</Banner>}
  </>
}
