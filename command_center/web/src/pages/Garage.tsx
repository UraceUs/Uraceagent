/* Equipamentos (catálogo editável de chassis, motores, peças) e Corridas (convites dos Pro Racing Drivers com prévia de custo). */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { Catalog, Chassis, Client, Engine, Part, Race } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, Section, Spinner, statusTone } from '../components/ui'
import { fmtDate, money } from '../components/fmt'
import { useToast } from '../components/Toast'
import { Md } from '../components/Md'

function csrf() { return decodeURIComponent(document.cookie.match(/(?:^|;\s*)cc_csrf=([^;]+)/)?.[1] || '') }

function Linha<T extends { id: number; active: number }>({ item, campos, kind, onSaved, imagem }: { item: T; campos: [keyof T & string, string][]; kind: string; onSaved: () => void; imagem?: boolean }) {
  const { can } = useAuth()
  const toast = useToast()
  const [edit, setEdit] = useState(false)
  const [f, setF] = useState<Record<string, string>>(Object.fromEntries(campos.map(([k]) => [k, String(item[k] ?? '')])))
  const [busy, setBusy] = useState(false)
  async function save() { setBusy(true); try { await api.patch(`/catalog/${kind}/${item.id}`, f); toast('Salvo.', 'ok'); setEdit(false); onSaved() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) } }
  async function toggle() { try { await api.patch(`/catalog/${kind}/${item.id}`, { active: !item.active }); onSaved() } catch (e) { toast((e as ApiError).message, 'crit') } }
  async function img(file: File) { const fd = new FormData(); fd.append('file', file); const r = await fetch(`/ops/api/catalog/${kind}/${item.id}/image`, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-CSRF': csrf() } }); if (!r.ok) toast('Imagem recusada.', 'crit'); else { toast('Imagem salva.', 'ok'); onSaved() } }
  return <tr style={{ opacity: item.active ? 1 : 0.5 }}>
    {imagem && <td>{(item as unknown as { image_path: string | null }).image_path ? <img src={`/ops/api/catalog/${kind}/${item.id}/image?${Date.now()}`} alt="" style={{ height: 44, borderRadius: 3 }} /> : <span className="muted small">sem foto</span>}{can('OPERATOR') && <div><input type="file" accept="image/*" style={{ fontSize: 11, width: 120 }} onChange={e => e.target.files?.[0] && img(e.target.files[0])} /></div>}</td>}
    {campos.map(([k, l]) => <td key={k}>{edit ? <input className="input" style={{ padding: '4px 8px' }} placeholder={l} value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })} /> : (String(item[k] ?? '') || <span className="muted">—</span>)}</td>)}
    <td className="nowrap">{can('OPERATOR') && (edit ? <><button className="btn sm primary" disabled={busy} onClick={save}>{busy ? <Spinner /> : 'Salvar'}</button> <button className="btn ghost sm" onClick={() => setEdit(false)}>cancelar</button></> : <><button className="btn sm" onClick={() => setEdit(true)}>Editar</button> <button className="btn ghost sm" onClick={toggle}>{item.active ? 'desativar' : 'reativar'}</button></>)}</td>
  </tr>
}

function Novo({ kind, campos, onSaved, extra }: { kind: string; campos: [string, string][]; onSaved: () => void; extra?: Record<string, unknown> }) {
  const toast = useToast()
  const [f, setF] = useState<Record<string, string>>(Object.fromEntries(campos.map(([k]) => [k, ''])))
  const [busy, setBusy] = useState(false)
  async function add() { setBusy(true); try { await api.post(`/catalog/${kind}`, { ...f, ...(extra || {}) }); toast('Adicionado.', 'ok'); setF(Object.fromEntries(campos.map(([k]) => [k, '']))); onSaved() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) } }
  return <div className="row wrap" style={{ padding: 10 }}>{campos.map(([k, l]) => <input key={k} className="input" style={{ width: 160, padding: '4px 8px' }} placeholder={l} value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })} />)}<button className="btn sm primary" disabled={busy} onClick={add}>{busy ? <Spinner /> : '+ Adicionar'}</button></div>
}

export function Equipment() {
  const { can } = useAuth()
  const { data, error, reload } = useGet<Catalog>('/catalog')
  const [tab, setTab] = useState<'chassis' | 'engines' | 'parts'>('chassis')
  const [engine, setEngine] = useState<number>(0)
  if (error && !data) return <ErrorState error={error} retry={reload} />
  if (!data) return <Loading />
  const parts = data.parts.filter(p => !engine || p.engine_id === engine)
  return <>
    <div className="page-h"><div><h1 className="h1">Equipamentos</h1><div className="sub small">Catálogo editável de chassis (com medidas de pneu), motores e peças por motor. É a referência do card de cada piloto. Estoque vem depois.</div></div></div>
    <div className="tabs">{([['chassis', `Chassis (${data.chassis.length})`], ['engines', `Motores (${data.engines.length})`], ['parts', `Peças (${data.parts.length})`]] as const).map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}</div>
    {tab === 'chassis' && <Section title="Chassis" tight>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Foto</th><th>Marca</th><th>Modelo</th><th>Tamanho</th><th>Pneu diant.</th><th>Pneu tras.</th><th>Notas</th><th></th></tr></thead><tbody>
        {data.chassis.map(c => <Linha<Chassis> key={c.id} item={c} kind="chassis" imagem onSaved={reload} campos={[['brand', 'Marca'], ['model', 'Modelo'], ['size', 'Tamanho'], ['tire_front', 'Pneu diant.'], ['tire_rear', 'Pneu tras.'], ['notes', 'Notas']]} />)}
      </tbody></table></div>
      {can('OPERATOR') && <Novo kind="chassis" onSaved={reload} campos={[['brand', 'Marca *'], ['model', 'Modelo'], ['size', 'Cadet/Junior/Senior'], ['tire_front', 'Pneu diant.'], ['tire_rear', 'Pneu tras.'], ['notes', 'Notas']]} />}
    </Section>}
    {tab === 'engines' && <Section title="Motores" tight>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Foto</th><th>Marca</th><th>Modelo</th><th>Tempos</th><th>Categoria</th><th>Notas</th><th></th></tr></thead><tbody>
        {data.engines.map(e => <Linha<Engine> key={e.id} item={e} kind="engines" imagem onSaved={reload} campos={[['brand', 'Marca'], ['model', 'Modelo'], ['stroke', '2T/4T'], ['category', 'Categoria'], ['notes', 'Notas']]} />)}
      </tbody></table></div>
      {can('OPERATOR') && <Novo kind="engines" onSaved={reload} campos={[['brand', 'Marca *'], ['model', 'Modelo *'], ['stroke', '2T/4T'], ['category', 'Categoria'], ['notes', 'Notas']]} />}
    </Section>}
    {tab === 'parts' && <Section title="Peças por motor" tight right={<select className="input" style={{ width: 220 }} value={engine} onChange={e => setEngine(Number(e.target.value))}><option value={0}>Todos os motores</option>{data.engines.map(e => <option key={e.id} value={e.id}>{e.brand} {e.model}</option>)}</select>}>
      {parts.length === 0 ? <Empty>Nenhuma peça{engine ? ' para este motor' : ''}. Escolha o motor e adicione abaixo.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Motor</th><th>Peça</th><th>Nº peça</th><th>Preço ref.</th><th>Notas</th><th></th></tr></thead><tbody>
          {parts.map(p => <tr key={p.id} style={{ opacity: p.active ? 1 : 0.5 }}><td className="small">{p.engine_brand} {p.engine_model}</td><td colSpan={4} style={{ padding: 0 }}><table className="tbl" style={{ margin: 0 }}><tbody><Linha<Part> item={p} kind="parts" onSaved={reload} campos={[['name', 'Peça'], ['part_number', 'Nº'], ['price', 'Preço'], ['notes', 'Notas']]} /></tbody></table></td></tr>)}
        </tbody></table></div>}
      {can('OPERATOR') && (engine ? <Novo kind="parts" onSaved={reload} extra={{ engine_id: engine }} campos={[['name', 'Peça *'], ['part_number', 'Nº peça'], ['price', 'Preço ref.'], ['notes', 'Notas']]} /> : <div className="small muted" style={{ padding: 10 }}>Escolha um motor acima para adicionar peças.</div>)}
    </Section>}
    <div className="small muted">Preço de peça de verdade sai da Rate Card e do QuickBooks (15% na peça, decisão de 31/08); o valor aqui é só referência.</div>
  </>
}

export function Races() {
  const { can } = useAuth()
  const toast = useToast()
  const races = useGet<Race[]>('/races', 30000)
  const pros = useGet<Client[]>('/clients?pro=true')
  const [nova, setNova] = useState({ name: '', series: '', track: '', city: '', date_start: '', date_end: '', notes: '' })
  const [busy, setBusy] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  async function criar() { setBusy('nova'); try { await api.post('/races', nova); toast('Corrida criada.', 'ok'); setNova({ name: '', series: '', track: '', city: '', date_start: '', date_end: '', notes: '' }); races.reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) } }
  async function convidar(rid: number, cid: number) { setBusy(`c${rid}`); try { await api.post(`/races/${rid}/invite`, { client_id: cid }); races.reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) } }
  async function estimar(iid: number) { setBusy(`e${iid}`); try { await api.post(`/invites/${iid}/estimate`); toast('A IA está montando a prévia (1 a 3 min). Atualize em instantes.'); setTimeout(races.reload, 60000) } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) } }
  async function status(iid: number, st: string) { try { await api.patch(`/invites/${iid}`, { status: st }); races.reload() } catch (e) { toast((e as ApiError).message, 'crit') } }
  return <>
    <div className="page-h"><div><h1 className="h1">Corridas</h1><div className="sub small">Corridas da coluna RACES do Asana mais as criadas aqui. Convide os ★ Pro Racing Drivers e peça à IA a prévia de custo pela aba Racing team da Rate Card. Prévia não cria invoice.</div></div><button className="btn" onClick={races.reload}>↻</button></div>
    {can('OPERATOR') && <div className="card card-b"><div className="h2" style={{ marginBottom: 8 }}>Nova corrida</div><div className="row wrap">
      <input className="input" style={{ width: 260 }} placeholder="Nome *" value={nova.name} onChange={e => setNova({ ...nova, name: e.target.value })} /><input className="input" style={{ width: 120 }} placeholder="Série" value={nova.series} onChange={e => setNova({ ...nova, series: e.target.value })} /><input className="input" style={{ width: 180 }} placeholder="Pista" value={nova.track} onChange={e => setNova({ ...nova, track: e.target.value })} /><input className="input" style={{ width: 140 }} placeholder="Cidade" value={nova.city} onChange={e => setNova({ ...nova, city: e.target.value })} /><input className="input" type="date" value={nova.date_start} onChange={e => setNova({ ...nova, date_start: e.target.value })} /><input className="input" type="date" value={nova.date_end} onChange={e => setNova({ ...nova, date_end: e.target.value })} /><button className="btn primary" disabled={busy === 'nova' || !nova.name.trim()} onClick={criar}>{busy === 'nova' ? <Spinner /> : '+ Criar'}</button></div></div>}
    {races.error && !races.data ? <ErrorState error={races.error} retry={races.reload} /> : !races.data ? <Loading /> : races.data.length === 0 ? <div className="card"><Empty title="Sem corridas">Sincronize o Asana (coluna RACES) ou crie uma acima.</Empty></div> :
      <div className="stack">{races.data.map(r => <div className="card" key={r.id}>
        <div className="card-h" style={{ cursor: 'pointer' }} onClick={() => setOpen(open === r.id ? null : r.id)}><h2 className="h1" style={{ fontSize: 18 }}>{r.name}</h2>{r.series && <Chip tone="accent">{r.series}</Chip>}<span className="small muted">{[r.track, r.city].filter(Boolean).join(' · ')} {r.date_start && `· ${fmtDate(r.date_start)}${r.date_end ? ` a ${fmtDate(r.date_end)}` : ''}`}</span><div className="grow" /><Chip tone="outline">{r.invites} convidado(s)</Chip><span className="muted">{open === r.id ? '▴' : '▾'}</span></div>
        {open === r.id && <div className="card-b stack">
          {can('OPERATOR') && <div className="row wrap"><span className="small muted">Convidar:</span>{(pros.data || []).filter(p => !r.invited.some(i => i.client_id === p.id)).map(p => <button key={p.id} className="btn sm" disabled={busy === `c${r.id}`} onClick={() => convidar(r.id, p.id)}>★ {p.pilot_name || p.name}</button>)}{(pros.data || []).length === 0 && <span className="small muted">Nenhum Pro Racing Driver marcado ainda (card do cliente → Editar).</span>}</div>}
          {r.invited.length === 0 ? <Empty>Ninguém convidado.</Empty> : r.invited.map(i => <div className="act" key={i.id}>
            <div className="grow"><div className="row wrap"><b>★ {i.pilot_name || i.name}</b><Chip tone={statusTone(i.status === 'confirmed' ? 'COMPLETED' : i.status === 'declined' ? 'REJECTED' : 'PENDING')}>{i.status}</Chip>{i.estimate_status && !i.estimate_text && <Chip tone="warn">prévia: {i.estimate_status}</Chip>}</div>
              {i.estimate_text ? <div className="previa"><div className="cond small muted">Prévia de custo (IA, não é invoice)</div><Md text={i.estimate_text} /></div> : <div className="small muted">Sem prévia ainda.</div>}
              {i.estimate_cmd && <Link className="small" to={`/ai/${i.estimate_cmd}`}>ver a conversa da prévia</Link>}</div>
            {can('OPERATOR') && <div className="row wrap"><button className="btn sm primary" disabled={busy === `e${i.id}`} onClick={() => estimar(i.id)}>{busy === `e${i.id}` ? <Spinner /> : '✦ Prévia de custo'}</button><select className="input" style={{ width: 130, padding: '4px 8px' }} value={i.status} onChange={e => status(i.id, e.target.value)}>{['invited', 'confirmed', 'declined', 'done'].map(s => <option key={s}>{s}</option>)}</select></div>}
          </div>)}
        </div>}
      </div>)}</div>}
    <Banner tone="info">Quando confirmar, a IA pode montar a invoice pela aba Racing team para aprovação. Valores de referência: {money(769)} por piloto é só o Lead and Follow, não corrida.</Banner>
  </>
}
