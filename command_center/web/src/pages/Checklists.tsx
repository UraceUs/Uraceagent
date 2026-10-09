/* Checklists (#92): nativos, a partir da planilha Master Checklist.
 * - Checklist: o preenchimento no celular — marcar item, tirar foto (câmera) ou subir do celular.
 * - Checklists: os modelos. Gerente para cima edita: itens, foto obrigatória (no item ou no
 *   checklist inteiro), quando aparece, de quem é. O mecânico e o coach veem os do seu cargo. */
import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Section } from '../components/ui'
import { useToast } from '../components/Toast'
import { tr } from '../i18n'

interface RunItem { id: number; grupo: string | null; text: string; photo_required: number; done: number; por: string | null; note: string | null; fotos: number[] }
interface Run { id: number; title: string; modelo: string; cliente: string | null; run_date: string; status: string; photo_required: number
  itens: RunItem[]; feitos: number; total: number; faltando: string[] }
interface ItemModelo { id: number; grupo: string | null; text: string; photo_required: number; active: number; sort: number }
interface Modelo { id: number; section: string | null; name: string; quando: string; cargo: string; per_kart: number; photo_required: number
  active: number; itens: ItemModelo[] }

const CARGO: Record<string, string> = { MECANICO: tr("Mecânico"), COACH: tr("Coach"), ADM: tr("Administração") }
const QUANDO: [string, string][] = [['treino', tr("Dia de treino / serviço")], ['corrida', tr("Corrida")], ['trimestral', tr("Trimestral")], ['avulso', tr("Avulso")]]

function grupos<T extends { grupo: string | null }>(itens: T[]) {
  const out: [string | null, T[]][] = []
  for (const i of itens) {
    const ult = out[out.length - 1]
    if (ult && ult[0] === i.grupo) ult[1].push(i); else out.push([i.grupo, [i]])
  }
  return out
}

function Foto({ runId, item, aberto, onRun }: { runId: number; item: RunItem; aberto: boolean; onRun: (r: Run) => void }) {
  const toast = useToast()
  const camera = useRef<HTMLInputElement>(null)
  const galeria = useRef<HTMLInputElement>(null)
  const [indo, setIndo] = useState(false)
  async function enviar(f: File | undefined) {
    if (!f) return
    setIndo(true)
    try { const fd = new FormData(); fd.append('arquivo', f); onRun(await api.postForm<Run>(`/checklists/runs/${runId}/itens/${item.id}/foto`, fd)); toast(tr("Foto salva."), 'ok') }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <div className="row wrap" style={{ gap: 6 }}>
    {item.fotos.map(f => <a key={f} href={`/ops/api/checklists/fotos/${f}`} target="_blank" rel="noreferrer">
      <img className="ck-foto" src={`/ops/api/checklists/fotos/${f}`} alt={tr("Foto de {0}", item.text)} loading="lazy" width={56} height={56} /></a>)}
    {aberto && <>
      <input ref={camera} type="file" accept="image/*" capture="environment" hidden aria-label={tr("Tirar foto: {0}", item.text)} onChange={e => enviar(e.target.files?.[0])} />
      <input ref={galeria} type="file" accept="image/*" hidden aria-label={tr("Subir foto: {0}", item.text)} onChange={e => enviar(e.target.files?.[0])} />
      <button type="button" className="btn sm" disabled={indo} onClick={() => camera.current?.click()}>{indo ? <span className="spin" /> : tr("Câmera")}</button>
      <button type="button" className="btn sm ghost" disabled={indo} onClick={() => galeria.current?.click()}>{tr("Do celular")}</button>
    </>}
  </div>
}

export function Checklist() {
  const { runId } = useParams()
  const toast = useToast()
  const nav = useNavigate()
  const l = useGet<Run>(`/checklists/runs/${runId}`)
  const [run, setRun] = useState<Run | null>(null)
  const r = run && String(run.id) === runId ? run : l.data
  const [indo, setIndo] = useState(false)
  if (l.error && !r) return <ErrorState error={l.error} retry={l.reload} />
  if (!r) return <Loading />
  const aberto = r.status === 'aberto'
  async function marcar(i: RunItem) {
    const antes = r!
    // marca na hora (o mecânico está com luva, no sol): se o servidor recusar, volta
    setRun({ ...antes, itens: antes.itens.map(x => x.id === i.id ? { ...x, done: i.done ? 0 : 1 } : x) })
    try { setRun(await api.post<Run>(`/checklists/runs/${antes.id}/itens/${i.id}`, { done: !i.done })) }
    catch (e) { setRun(antes); toast((e as ApiError).message, 'crit') }
  }
  async function concluir() {
    setIndo(true)
    try { setRun(await api.post<Run>(`/checklists/runs/${r!.id}/concluir`)); toast(tr("Checklist concluído."), 'ok'); nav('/') }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <>
    <PageHeader title={r.title} eyebrow={`${r.modelo}${r.cliente ? ` · ${r.cliente}` : ''}`}>
      {aberto ? <Chip tone="warn">{r.feitos}/{r.total}</Chip> : <Chip tone="ok">{tr("completo")}</Chip>}
    </PageHeader>
    {!!r.photo_required && <Banner tone="info">{tr("Este checklist pede pelo menos uma foto.")}</Banner>}
    {grupos(r.itens).map(([g, itens], gi) => <section key={gi} className="stack" style={{ gap: 8 }} aria-label={g || tr("Itens")}>
      {g && <h2 className="h2">{g}</h2>}
      <div className="card"><div className="tbl">{itens.map(i => <div className="tr ck-item" key={i.id}>
        <label className="check ck-marca grow"><input type="checkbox" checked={!!i.done} disabled={!aberto} onChange={() => marcar(i)} />
          <span>{i.text}{!!i.photo_required && <Chip tone={i.fotos.length ? 'ok' : 'warn'}>{tr("foto obrigatória")}</Chip>}
            {i.por && i.done ? <span className="small muted"> · {i.por}</span> : null}</span></label>
        <Foto runId={r.id} item={i} aberto={aberto} onRun={setRun} />
      </div>)}</div></div>
    </section>)}
    {aberto && <div className="stack" style={{ gap: 8 }}>
      {r.faltando.length > 0 && <p className="small muted" style={{ margin: 0 }}>{tr("Falta:")} {r.faltando.slice(0, 4).join('; ')}{r.faltando.length > 4 ? tr(" e mais {0}", r.faltando.length - 4) : ''}.</p>}
      <button className="btn primary block" disabled={indo || r.faltando.length > 0} onClick={concluir}>{indo ? <span className="spin" /> : tr("Concluir checklist")}</button>
    </div>}
    <Link to="/">{tr("Voltar ao Meu dia")}</Link>
  </>
}

function EditarModelo({ m: original, onMudou }: { m: Modelo; onMudou: () => void }) {
  const toast = useToast()
  const [novo, setNovo] = useState('')
  // a marcação aparece na hora; se o servidor recusar, volta (sem esperar a lista recarregar)
  const [ajuste, setAjuste] = useState<Partial<Modelo>>({})
  const [ajusteItem, setAjusteItem] = useState<Record<number, Partial<ItemModelo>>>({})
  const m: Modelo = { ...original, ...ajuste, itens: original.itens.map(i => ({ ...i, ...ajusteItem[i.id] })) }
  async function mudar(campos: Record<string, unknown>) {
    setAjuste(a => ({ ...a, ...campos as Partial<Modelo> }))
    try { await api.patch(`/checklists/modelos/${m.id}`, campos); onMudou() }
    catch (e) { setAjuste(a => { const b = { ...a }; for (const k of Object.keys(campos)) delete b[k as keyof Modelo]; return b }); toast((e as ApiError).message, 'crit') }
  }
  async function item(id: number, campos: Record<string, unknown>) {
    setAjusteItem(a => ({ ...a, [id]: { ...a[id], ...campos as Partial<ItemModelo> } }))
    try { await api.patch(`/checklists/itens/${id}`, campos); onMudou() }
    catch (e) { setAjusteItem(a => { const b = { ...a }; delete b[id]; return b }); toast((e as ApiError).message, 'crit') }
  }
  async function adicionar() {
    try { await api.post(`/checklists/modelos/${m.id}/itens`, { text: novo, grupo: m.itens[m.itens.length - 1]?.grupo ?? null }); setNovo(''); onMudou() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  const quando = new Set(m.quando.split(','))
  return <div className="stack" style={{ gap: 10 }}>
    <div className="row wrap" style={{ gap: 10 }}>
      <label className="fld"><span>{tr("De quem é")}</span><select value={m.cargo} onChange={e => mudar({ cargo: e.target.value })}>
        {Object.entries(CARGO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label className="check"><input type="checkbox" checked={!!m.per_kart} onChange={e => mudar({ per_kart: e.target.checked })} /> {tr("Um por kart")}</label>
      <label className="check"><input type="checkbox" checked={!!m.photo_required} onChange={e => mudar({ photo_required: e.target.checked })} /> {tr("Foto obrigatória no checklist")}</label>
      <label className="check"><input type="checkbox" checked={!!m.active} onChange={e => mudar({ active: e.target.checked })} /> {tr("Ativo")}</label>
    </div>
    <div className="row wrap" style={{ gap: 10 }}><span className="small muted">{tr("Aparece em:")}</span>
      {QUANDO.map(([k, v]) => <label key={k} className="check"><input type="checkbox" checked={quando.has(k)} onChange={e => {
        const n = new Set(quando); if (e.target.checked) n.add(k); else n.delete(k)
        if (n.size) mudar({ quando: [...n].join(',') })
      }} /> {v}</label>)}</div>
    <div className="tbl">{m.itens.map(i => <div className="tr" key={i.id}>
      <span className="grow" style={{ minWidth: 0 }}>{i.grupo && <span className="small muted">{i.grupo} · </span>}
        <input className="input" aria-label={tr("Texto do item")} defaultValue={i.text} onBlur={e => e.target.value.trim() && e.target.value !== i.text && item(i.id, { text: e.target.value })} /></span>
      <label className="check small"><input type="checkbox" checked={!!i.photo_required} onChange={e => item(i.id, { photo_required: e.target.checked })} /> {tr("foto obrigatória")}</label>
      <button className="btn sm ghost" onClick={() => item(i.id, { active: !i.active })}>{i.active ? tr("Tirar") : tr("Voltar")}</button>
    </div>)}</div>
    <div className="row" style={{ gap: 8 }}><input className="input grow" aria-label={tr("Novo item")} placeholder={tr("Novo item")} value={novo} onChange={e => setNovo(e.target.value)} />
      <button className="btn sm" disabled={!novo.trim()} onClick={adicionar}>{tr("Adicionar")}</button></div>
  </div>
}

export function Checklists() {
  const { can, user } = useAuth()
  const gerente = can('MANAGER')
  const toast = useToast()
  const nav = useNavigate()
  const l = useGet<{ modelos: Modelo[]; planilha: string }>(`/checklists/modelos${gerente ? '?todos=true' : ''}`)
  const [aberto, setAberto] = useState<number | null>(null)
  const [indo, setIndo] = useState(false)
  async function importar() {
    setIndo(true)
    try { const r = await api.post<{ novos: string[]; ja_existiam: string[] }>('/checklists/importar'); toast(tr("{0} checklist(s) novo(s) da planilha.", r.novos.length), 'ok'); l.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  async function comecar(m: Modelo) {
    try { const r = await api.post<{ id: number }>('/checklists/runs', { template_id: m.id, ctx: { tipo: 'avulso' } }); nav(`/checklists/${r.id}`) }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!l.data) return <Loading />
  const meus = l.data.modelos.filter(m => gerente || m.cargo === user?.cargo)
  return <>
    <PageHeader title={tr("Checklists")} help={tr("Os checklists de cada atendimento. O dia de cada um está em Meu dia; os trimestrais e avulsos começam aqui.")}>
      {gerente && <button className="btn" disabled={indo} onClick={importar}>{indo ? <span className="spin" /> : tr("Importar da planilha")}</button>}
    </PageHeader>
    {!meus.length ? <div className="card"><Empty title={tr("Nenhum checklist ainda")}>{gerente ? tr("Importe da planilha Master Checklist: ela vira os modelos daqui, e daí em diante você edita aqui.") : tr("O gerente ainda não importou os checklists.")}</Empty></div>
      : <Section title={tr("Modelos")} count={meus.length}><div className="stack" style={{ gap: 10 }}>{meus.map(m => <div key={m.id} className="card card-b stack" style={{ gap: 8 }}>
        <div className="row wrap" style={{ gap: 8 }}>
          <h3 className="h3 grow" style={{ margin: 0 }}>{m.name}</h3>
          <Chip tone="neutral">{CARGO[m.cargo]}</Chip>{!m.active && <Chip tone="neutral">{tr("inativo")}</Chip>}
          {(m.quando.includes('avulso') || m.quando.includes('trimestral')) && !!m.active && <button className="btn sm" onClick={() => comecar(m)}>{tr("Começar hoje")}</button>}
          {gerente && <button className="btn sm ghost" aria-expanded={aberto === m.id} onClick={() => setAberto(a => a === m.id ? null : m.id)}>{aberto === m.id ? tr("Fechar") : tr("Editar")}</button>}
        </div>
        <div className="small muted">{m.section ? `${m.section} · ` : ''}{m.itens.filter(i => i.active).length} {tr("itens ·")} {m.quando.split(',').map(q => QUANDO.find(x => x[0] === q)?.[1] || q).join(', ')}{m.per_kart ? tr(" · um por kart") : ''}</div>
        {gerente && aberto === m.id && <EditarModelo m={m} onMudou={l.reload} />}
      </div>)}</div></Section>}
  </>
}
