/* Catálogo editável de chassis, motores e peças. Vive dentro do card do piloto (aba Equipamento); a página solta saiu em 09/09 a pedido do dono. */
import { useState } from 'react'
import { api, ApiError } from '../api/client'
import type { Catalog, Chassis, Engine, Part } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Empty, Section, Spinner } from '../components/ui'
import { useToast } from '../components/Toast'

function csrf() { return decodeURIComponent(document.cookie.match(/(?:^|;\s*)cc_csrf=([^;]+)/)?.[1] || '') }

export function Linha<T extends { id: number; active: number }>({ item, campos, kind, onSaved, imagem }: { item: T; campos: [keyof T & string, string][]; kind: string; onSaved: () => void; imagem?: boolean }) {
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

export function Novo({ kind, campos, onSaved, extra }: { kind: string; campos: [string, string][]; onSaved: () => void; extra?: Record<string, unknown> }) {
  const toast = useToast()
  const [f, setF] = useState<Record<string, string>>(Object.fromEntries(campos.map(([k]) => [k, ''])))
  const [busy, setBusy] = useState(false)
  async function add() { setBusy(true); try { await api.post(`/catalog/${kind}`, { ...f, ...(extra || {}) }); toast('Adicionado.', 'ok'); setF(Object.fromEntries(campos.map(([k]) => [k, '']))); onSaved() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) } }
  return <div className="row wrap" style={{ padding: 10 }}>{campos.map(([k, l]) => <input key={k} className="input" style={{ width: 160, padding: '4px 8px' }} placeholder={l} value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })} />)}<button className="btn sm primary" disabled={busy} onClick={add}>{busy ? <Spinner /> : '+ Adicionar'}</button></div>
}

export function CatalogoEditor({ data, reload }: { data: Catalog; reload: () => void }) {
  const { can } = useAuth()
  const [tab, setTab] = useState<'chassis' | 'engines' | 'parts'>('chassis')
  const [engine, setEngine] = useState<number>(0)
  const parts = data.parts.filter(p => !engine || p.engine_id === engine)
  return <>
    <div className="small ink2" style={{ marginBottom: 6 }}>Catálogo (vale para todos os pilotos): chassis com medidas de pneu, motores e peças por motor. Estoque vem depois.</div>
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
