/* Corridas em calendário — a coluna RACES do Asana, só corridas (sem treinos).
   Convidar coloca o piloto dentro da corrida até a confirmação; nova corrida nasce do
   modelo oficial "New Race" no Asana, com as subtarefas do modelo (decisão do dono, 09/09). */
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { Client, Race } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Scrim, Section, Spinner, statusTone } from '../components/ui'
import { fmtDate, money } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'
import { InserirNoTopo } from '../components/Inserir'
import { Md } from '../components/Md'
import { TextoComVoz } from '../components/Voz'
import { Cartao, CdItem, CdLista, type TomD } from '../components/Cartao'
import { tr } from '../i18n'

const MESES = [tr("janeiro"), tr("fevereiro"), tr("março"), tr("abril"), tr("maio"), tr("junho"), tr("julho"), tr("agosto"), tr("setembro"), tr("outubro"), tr("novembro"), tr("dezembro")]
const DIAS = [tr("dom"), tr("seg"), tr("ter"), tr("qua"), tr("qui"), tr("sex"), tr("sáb")]
const STATUS_LABEL: Record<string, string> = { invited: tr("aguardando confirmação"), confirmed: tr("confirmado"), declined: tr("não vai"), done: tr("correu") }
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const tomSerie = (s: string | null): TomD => { const t = serieTone(s); return t === 'accent' ? 'info' : t }
const serieTone = (s: string | null) => { const t = (s || '').toLowerCase(); return t.includes('skusa') ? 'accent' : t.includes('rok') ? 'info' : t.includes('uspks') ? 'warn' : t.includes('fwt') || t.includes('florida') ? 'ok' : 'neutral' }

function diasDaCorrida(r: Race): string[] {
  if (!r.date_start) return []
  const out: string[] = []
  const a = new Date(r.date_start + 'T12:00:00'); const b = new Date((r.date_end || r.date_start) + 'T12:00:00')
  for (let d = new Date(a); d <= b && out.length < 10; d.setDate(d.getDate() + 1)) out.push(iso(d))
  return out
}

interface TaskDetail { connected: boolean; reason?: string; task?: { notas?: string | null; link?: string | null; subtarefas_lista?: { gid: string; nome: string; concluida: boolean; vence_em: string | null }[] } }

function CorridaModal({ r, pros, onClose, reload }: { r: Race; pros: Client[]; onClose: () => void; reload: () => void }) {
  const { can } = useAuth()
  const perguntar = usePerguntar()
  const toast = useToast()
  const det = useGet<TaskDetail>(r.task_id ? `/tasks/${r.task_id}/detail` : null)
  const [busy, setBusy] = useState<string | null>(null)
  const subs = det.data?.task?.subtarefas_lista || []
  async function convidar(cid: number) { setBusy(`c${cid}`); try { await api.post(`/races/${r.id}/invite`, { client_id: cid }); toast(tr("Piloto colocado na corrida. Fica lá até a confirmação."), 'ok'); reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) } }
  async function estimar(iid: number) { setBusy(`e${iid}`); try { await api.post(`/invites/${iid}/estimate`); toast(tr("A IA está montando a prévia (1 a 3 min).")); setTimeout(reload, 60000) } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) } }
  async function status(iid: number, st: string) { try { await api.patch(`/invites/${iid}`, { status: st }); reload() } catch (e) { toast((e as ApiError).message, 'crit') } }
  async function tirar() { if (!await perguntar({ titulo: tr("Tirar esta corrida do calendário?"), texto: tr("Some do painel. No Asana nada muda."), ok: tr("Tirar"), perigo: true })) return; try { await api.patch(`/races/${r.id}`, { active: false }); reload(); onClose() } catch (e) { toast((e as ApiError).message, 'crit') } }
  const link = r.task?.links?.[0]?.deep_link || det.data?.task?.link
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 900 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label={tr("Fechar")}>✕</button>
    <div><div className="small muted cond">{r.source === 'asana' ? tr("coluna RACES do Asana") : tr("só no painel")}{r.series && <> · {r.series}</>}</div><h2 className="h1" style={{ fontSize: 22 }}>{r.name}</h2>
      <div className="small ink2">{[r.track, r.city].filter(Boolean).join(' · ')}{r.date_start && <> · {fmtDate(r.date_start)}{r.date_end && r.date_end !== r.date_start ? tr(" a {0}", fmtDate(r.date_end)) : ''}</>}{r.task && <> · <Chip tone={statusTone(r.task.status === 'open' ? 'PENDING' : 'COMPLETED')}>{r.task.status}</Chip></>}</div>
      {r.notes && <div className="small" style={{ whiteSpace: 'pre-wrap', marginTop: 6 }}>{r.notes}</div>}</div>
    <div className="row wrap">{link && <a className="btn sm" href={link} target="_blank" rel="noopener noreferrer">{tr("Abrir no Asana ↗")}</a>}{can('OPERATOR') && !r.task_id && <button className="btn ghost sm" onClick={tirar}>{tr("tirar do calendário")}</button>}</div>
    <div className="grid g2">
      <Section title={tr("Pilotos nesta corrida")} count={r.invited.length} tight>
        {/* #312: convidar fica em cima da lista dos pilotos da corrida; o convite é o próprio card do piloto ★ Pro */}
        {can('OPERATOR') && <div className="ins-tight"><InserirNoTopo rotulo={tr("Convidar piloto")} titulo={false} sempre dentro>
          <div className="row wrap"><span className="small muted">{tr("Convidar:")}</span>{pros.filter(p => !r.invited.some(i => i.client_id === p.id)).map(p => <button key={p.id} className="btn sm" disabled={busy === `c${p.id}`} onClick={() => convidar(p.id)}>{busy === `c${p.id}` ? <Spinner /> : `★ ${p.pilot_name || p.name}`}</button>)}{pros.length === 0 && <span className="small muted">{tr("Nenhum ★ Pro Racing Driver ainda (card do cliente → “Tornar Pro”).")}</span>}</div>
        </InserirNoTopo></div>}
        {r.invited.length === 0 ? <Empty>{tr("Ninguém ainda. Convide acima.")}</Empty> : <div className="cd-grade cd-dentro">{r.invited.map(i => {
          const st = i.status === 'confirmed' || i.status === 'done' ? 'ok' : i.status === 'declined' ? 'crit' : 'warn'
          return <Cartao key={i.id} id={`convite-${i.id}`} nivel={3} estado={STATUS_LABEL[i.status] || i.status} tom={st} avatar={i.pilot_name || i.name}
            nome={<Link to={`/clients/${i.client_id}`}>★ {i.pilot_name || i.name}</Link>}
            acoes={can('OPERATOR') ? <>
              <select className="input" aria-label={tr("Situação de {0}", i.pilot_name || i.name)} value={i.status} onChange={e => status(i.id, e.target.value)}>{Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
              <button className="btn" disabled={busy === `e${i.id}`} onClick={() => estimar(i.id)}>{busy === `e${i.id}` ? <Spinner /> : tr("✦ Prévia de custo")}</button></> : null}>
            {(i.estimate_text || i.estimate_status) && <div className="cd-form">
              {i.estimate_status && !i.estimate_text && <Chip tone="warn">{tr("prévia:")} {i.estimate_status}</Chip>}
              {i.estimate_text && <details><summary className="small">{tr("prévia de custo (IA, não é invoice)")}</summary><div className="previa"><Md text={i.estimate_text} /></div>{i.estimate_cmd && <Link className="small" to={`/ai/${i.estimate_cmd}`}>{tr("ver a conversa")}</Link>}</details>}
            </div>}
          </Cartao>
        })}</div>}
      </Section>
      <Section title={tr("Subtarefas da corrida (modelo do Asana)")} count={subs.length} tight>
        {!r.task_id ? <Empty>{tr("Corrida só no painel: sem tarefa no Asana.")}</Empty> : det.loading && !det.data ? <Loading rows={4} /> : det.error ? <ErrorState error={det.error} retry={det.reload} /> : det.data && !det.data.connected ? <Banner tone="warn">{tr("Sem Asana ao vivo:")} {det.data.reason}</Banner> :
          subs.length === 0 ? <Empty>{tr("Sem subtarefas. Corrida criada fora do modelo “New Race”.")}</Empty> : <div>{subs.map(s => <div key={s.gid} className="att"><div className={`lv ${s.concluida ? 'LOW' : 'MEDIUM'}`} /><div className="grow" style={{ textDecoration: s.concluida ? 'line-through' : undefined, color: s.concluida ? 'var(--muted)' : undefined }}>{s.concluida ? '✓ ' : '○ '}{s.nome}{s.vence_em && <span className="small muted mono"> · {fmtDate(s.vence_em)}</span>}</div></div>)}</div>}
        {det.data?.task?.notas && <details style={{ marginTop: 6 }}><summary className="small">{tr("descrição")}</summary><pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--font)', fontSize: 13, margin: 0 }}>{det.data.task.notas}</pre></details>}
      </Section>
    </div>
  </div></Scrim>
}

function NovaCorrida({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const toast = useToast()
  const [f, setF] = useState({ name: '', series: '', track: '', city: '', date_start: '', date_end: '', notes: '', local_only: false })
  const [busy, setBusy] = useState(false)
  async function criar() {
    setBusy(true)
    try { const r = await api.post<{ id: number; task_id: number | null }>('/races', { ...f, local_only: f.local_only || undefined }); toast(r.task_id ? tr("Corrida criada no Asana (coluna RACES) com as subtarefas do modelo.") : tr("Corrida criada só no painel."), 'ok'); onCreated(); onClose() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 640 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label={tr("Fechar")}>✕</button>
    <div><h2 className="h1" style={{ fontSize: 22 }}>{tr("Nova corrida")}</h2><div className="small ink2">{tr("Cria a tarefa no Asana a partir do modelo")} <b>{tr("New Race [Race + City/Track]")}</b>{tr(", na coluna RACES, com as mesmas subtarefas do modelo.")}</div></div>
    <div className="grid g2">
      <div className="field"><label>{tr("Corrida *")}</label><input className="input" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder={tr("ex.: ROK Cup USA Round 5")} /></div>
      <div className="field"><label>{tr("Série")}</label><input className="input" value={f.series} onChange={e => setF({ ...f, series: e.target.value })} placeholder={tr("SKUSA, ROK, USPKS, FWT…")} /></div>
      <div className="field"><label>{tr("Cidade")}</label><input className="input" value={f.city} onChange={e => setF({ ...f, city: e.target.value })} /></div>
      <div className="field"><label>{tr("Pista")}</label><input className="input" value={f.track} onChange={e => setF({ ...f, track: e.target.value })} /></div>
      <div className="field"><label>{tr("Início *")}</label><input className="input" type="date" value={f.date_start} onChange={e => setF({ ...f, date_start: e.target.value })} /></div>
      <div className="field"><label>{tr("Fim")}</label><input className="input" type="date" value={f.date_end} onChange={e => setF({ ...f, date_end: e.target.value })} /></div>
    </div>
    <div className="field"><label>{tr("Observações")}</label><TextoComVoz valor={f.notes} onChange={t => setF({ ...f, notes: t })} linhas={2} placeholder={tr("Dá para ditar")} /></div>
    <label className="check small"><input type="checkbox" checked={f.local_only} onChange={e => setF({ ...f, local_only: e.target.checked })} /> {tr("só no painel (não cria no Asana)")}</label>
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onClose}>{tr("Cancelar")}</button><button className="btn primary" disabled={busy || !f.name.trim() || !f.date_start} onClick={criar}>{busy ? <Spinner /> : tr("Criar corrida")}</button></div>
  </div></Scrim>
}

/** #313: a corrida no cartão D — a série em cima, o nome, a pista, a data no bloco grande e os pilotos convidados. */
function CartaoCorrida({ r, abrir }: { r: Race; abrir: () => void }) {
  const conf = r.invited.filter(i => i.status === 'confirmed' || i.status === 'done').length
  const esperando = r.invited.filter(i => i.status === 'invited').length
  return <Cartao id={`corrida-${r.id}`} abrir={abrir} estado={r.date_start ? (r.series || tr("corrida")) : tr("sem data")}
    tom={!r.date_start ? 'warn' : r.series ? tomSerie(r.series) : 'neutral'} nome={r.name} sub={[[r.track, r.city].filter(Boolean).join(' · ')]}
    grande={r.date_start ? fmtDate(r.date_start) : null} detalhe={r.date_start ? (r.date_end && r.date_end !== r.date_start ? tr("a {0}", fmtDate(r.date_end)) : null)
      : tr("coloque a data na tarefa do Asana para entrar no calendário")}>
    {r.date_start && <CdLista>
      <CdItem tom="neutral" glifo="★" valor={r.invited.length}>{tr("piloto(s)")}</CdItem>
      {conf > 0 && <CdItem tom="ok" valor={conf}>{STATUS_LABEL.confirmed}</CdItem>}
      {esperando > 0 && <CdItem tom="warn" valor={esperando}>{STATUS_LABEL.invited}</CdItem>}
    </CdLista>}
  </Cartao>
}

export function Races() {
  const { can } = useAuth()
  const races = useGet<Race[]>('/races', 30000)
  const pros = useGet<Client[]>('/clients?pro=true', 60000)
  const hoje = new Date()
  const [ym, setYm] = useState({ y: hoje.getFullYear(), m: hoje.getMonth() })
  const [open, setOpen] = useState<number | null>(null)
  const [nova, setNova] = useState(false)
  const porDia = useMemo(() => { const m = new Map<string, Race[]>(); for (const r of races.data || []) for (const d of diasDaCorrida(r)) m.set(d, [...(m.get(d) || []), r]); return m }, [races.data])
  const primeiro = new Date(ym.y, ym.m, 1); const ini = new Date(primeiro); ini.setDate(1 - primeiro.getDay())
  const celulas: Date[] = []; for (let i = 0; i < 42; i++) { const d = new Date(ini); d.setDate(ini.getDate() + i); celulas.push(d) }
  const semSemana6 = celulas.slice(35).every(d => d.getMonth() !== ym.m)
  const cur = (races.data || []).find(r => r.id === open) || null
  const proximas = (races.data || []).filter(r => r.date_start && r.date_start >= iso(hoje)).slice(0, 8)
  const semData = (races.data || []).filter(r => !r.date_start)
  return <>
    <PageHeader title={tr("Corridas")} help={<>{tr("A coluna RACES do Asana, só corridas. Clique numa corrida para convidar os ★ Pro; o piloto fica nela até a confirmação.")}</>}>
      {can('OPERATOR') && <button className="btn primary" onClick={() => setNova(true)}>{tr("+ Nova corrida")}</button>}<button className="btn" onClick={races.reload}>↻</button></PageHeader>
    <div className="cal-h"><button className="btn sm" onClick={() => setYm(ym.m === 0 ? { y: ym.y - 1, m: 11 } : { y: ym.y, m: ym.m - 1 })}>◀</button><h2 className="h1" style={{ fontSize: 20, margin: '0 8px', textTransform: 'capitalize' }}>{MESES[ym.m]} {ym.y}</h2><button className="btn sm" onClick={() => setYm(ym.m === 11 ? { y: ym.y + 1, m: 0 } : { y: ym.y, m: ym.m + 1 })}>▶</button><button className="btn ghost sm" onClick={() => setYm({ y: hoje.getFullYear(), m: hoje.getMonth() })}>{tr("hoje")}</button>
      <span className="grow" /><span className="small muted">{(races.data || []).length} {tr("corrida(s) no calendário")}</span></div>
    {races.error && !races.data ? <ErrorState error={races.error} retry={races.reload} /> : !races.data ? <Loading rows={6} /> :
      <div className="cal">
        {DIAS.map(d => <div key={d} className="cal-d">{d}</div>)}
        {(semSemana6 ? celulas.slice(0, 35) : celulas).map(d => { const k = iso(d); const rs = porDia.get(k) || []; const fora = d.getMonth() !== ym.m; const eHoje = k === iso(hoje); return <div key={k} className={`cal-c${fora ? ' out' : ''}${eHoje ? ' today' : ''}`}>
          <div className="n">{d.getDate()}</div>
          {rs.map(r => { const conf = r.invited.filter(i => i.status === 'confirmed' || i.status === 'done').length; const wait = r.invited.filter(i => i.status === 'invited').length; return <button key={r.id} className={`cal-ev ${serieTone(r.series)}`} title={`${r.name}${r.invited.length ? ` · ${r.invited.map(i => `${i.pilot_name || i.name} (${STATUS_LABEL[i.status] || i.status})`).join(', ')}` : ''}`} onClick={() => setOpen(r.id)}>
            <span className="truncate">{r.name}</span>{r.invited.length > 0 && <span className="c">★{conf}{wait ? `+${wait}?` : ''}</span>}</button> })}
        </div> })}
      </div>}
    <div className="grid g2">
      {/* #313: cada corrida no cartão D; o cartão inteiro abre a corrida */}
      <Section title={tr("Próximas corridas")} count={proximas.length}>{proximas.length === 0 ? <Empty>{tr("Nada marcado daqui para a frente. Sincronize o Asana ou crie uma corrida.")}</Empty>
        : <div className="cd-grade">{proximas.map(r => <CartaoCorrida key={r.id} r={r} abrir={() => setOpen(r.id)} />)}</div>}</Section>
      <Section title={tr("Sem data no Asana")} count={semData.length}>{semData.length === 0 ? <Empty>{tr("Todas as corridas têm data.")}</Empty>
        : <div className="cd-grade">{semData.map(r => <CartaoCorrida key={r.id} r={r} abrir={() => setOpen(r.id)} />)}</div>}</Section>
    </div>
    <Banner tone="info">{tr("Quando confirmar, a IA pode montar a invoice pela aba Racing team para aprovação.")} {money(769)} {tr("por piloto é só o Lead and Follow, não corrida.")}</Banner>
    {cur && <CorridaModal r={cur} pros={pros.data || []} onClose={() => setOpen(null)} reload={races.reload} />}
    {nova && <NovaCorrida onClose={() => setNova(false)} onCreated={races.reload} />}
  </>
}
