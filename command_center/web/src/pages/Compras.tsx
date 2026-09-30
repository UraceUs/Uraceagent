/* Pedidos internos e Compras (dono, 30/09: "siga com a tela de pedidos e compras").
 *
 * Pedido é de quem precisa: o mecânico pede a peça pelo celular. Compra é de quem gasta: o
 * gerente junta pedidos e o que está abaixo do mínimo numa compra do fornecedor. Receber a
 * compra dá entrada no estoque sozinho — ninguém redigita o que chegou.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { Client } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Chip, Empty, ErrorState, Loading, PageHeader, Scrim, Section } from '../components/ui'
import { Icon } from '../components/Icon'
import { useToast } from '../components/Toast'
import { Picker } from '../components/Unir'

interface Pedido { id: number; item_id: number | null; description: string; qty: number; unit: string; client_id: number | null; cliente: string | null
  needed_by: string | null; urgent: number; notes: string | null; status: string; purchase_id: number | null; pedido_por: string | null; created_at: string }
interface Linha { id: number; item_id: number | null; description: string; qty: number; qty_received: number; unit_cost: number | null; request_id: number | null
  item: string | null; unit: string | null; pedido_por: string | null; cliente: string | null }
interface Compra { id: number; supplier: string; status: string; reference: string | null; ordered_at: string | null; expected_at: string | null; notes: string | null
  criada_por: string | null; created_at: string; linhas: Linha[]; total: number | null; sem_custo: number; atrasada: boolean }
interface Repor { id: number; name: string; unit: string; falta: number; sku: string | null; supplier_url: string | null }
interface Resumo { pedidos_abertos: number; urgentes: number; rascunhos: number; a_caminho: number; atrasadas: number; repor: Repor[] }
interface ItemEst { id: number; name: string; unit: string; nosso: number; cost?: number | null; category: string }
interface Local { code: string; name: string }

const ST_PEDIDO: Record<string, [string, 'warn' | 'info' | 'ok' | 'neutral' | 'accent']> = {
  aberto: ['aberto', 'warn'], comprando: ['comprando', 'info'], chegou: ['chegou', 'accent'], entregue: ['entregue', 'ok'], cancelado: ['cancelado', 'neutral'] }
const ST_COMPRA: Record<string, [string, 'warn' | 'info' | 'ok' | 'neutral' | 'accent']> = {
  rascunho: ['rascunho', 'neutral'], pedida: ['pedida', 'info'], parcial: ['chegou em parte', 'accent'], recebida: ['recebida', 'ok'], cancelada: ['cancelada', 'neutral'] }
const dia = (iso: string | null) => iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : '—'
const usd = (v: number | null | undefined) => v == null ? '—' : `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

/* ============================================================ PEDIDOS */

function NovoPedido({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const est = useGet<{ itens: ItemEst[] }>('/estoque')
  const [modo, setModo] = useState<'estoque' | 'livre'>('estoque')
  const [busca, setBusca] = useState('')
  const [item, setItem] = useState<ItemEst | null>(null)
  const [desc, setDesc] = useState('')
  const [qtd, setQtd] = useState('1')
  const [unidade, setUnidade] = useState('un')
  const [quando, setQuando] = useState('')
  const [urgente, setUrgente] = useState(false)
  const [cliente, setCliente] = useState<Client | null>(null)
  const [nota, setNota] = useState('')
  const [indo, setIndo] = useState(false)
  const achados = (est.data?.itens || []).filter(i => busca.trim().length >= 2 && i.name.toLowerCase().includes(busca.trim().toLowerCase())).slice(0, 8)

  async function salvar() {
    const q = Number(qtd.replace(',', '.'))
    if (!(q > 0)) { toast('Quantidade maior que zero.', 'warn'); return }
    if (modo === 'estoque' ? !item : !desc.trim()) { toast('Diga o que precisa.', 'warn'); return }
    setIndo(true)
    try {
      await api.post('/compras/pedidos', { item_id: modo === 'estoque' ? item!.id : null, description: modo === 'livre' ? desc.trim() : null,
        qty: q, unit: modo === 'livre' ? unidade : null, needed_by: quando || null, urgent: urgente, client_id: cliente?.id ?? null, notes: nota.trim() || null })
      toast('Pedido feito. Quem compra já vê na fila.', 'ok'); onDone(); onClose()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }

  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()}>
    <h3>Novo pedido</h3>
    <div className="seg" style={{ marginBottom: 10 }}>
      <button className={`btn sm${modo === 'estoque' ? '' : ' ghost'}`} onClick={() => setModo('estoque')}>Peça do estoque</button>
      <button className={`btn sm${modo === 'livre' ? '' : ' ghost'}`} onClick={() => setModo('livre')}>Outra coisa</button>
    </div>
    {modo === 'estoque'
      ? item ? <div className="row gap" style={{ alignItems: 'center', marginBottom: 12 }}><b className="grow">{item.name}</b>
          <span className="small muted">tem {item.nosso} {item.unit}</span><button className="btn ghost sm" onClick={() => setItem(null)}>trocar</button></div>
        : <label className="fld"><span>Qual peça</span>
          <input value={busca} onChange={e => setBusca(e.target.value)} placeholder="digite o nome (2 letras)" autoFocus />
          {achados.length > 0 && <div className="tbl">{achados.map(i => <button key={i.id} className="tr" style={{ textAlign: 'left', width: '100%', background: 'none', border: 0, cursor: 'pointer', color: 'inherit' }}
            onClick={() => { setItem(i); setUnidade(i.unit) }}><span className="grow">{i.name}</span><span className="small muted">tem {i.nosso} {i.unit}</span></button>)}</div>}
          {busca.trim().length >= 2 && !achados.length && <span className="small muted">Não está no estoque — use "Outra coisa".</span>}
        </label>
      : <label className="fld"><span>O que precisa</span><input value={desc} onChange={e => setDesc(e.target.value)} placeholder="Fita de freio, chave 10mm…" autoFocus /></label>}
    <div className="row gap wrap">
      <label className="fld grow"><span>Quantidade</span><input type="number" inputMode="decimal" min={0} value={qtd} onChange={e => setQtd(e.target.value)} /></label>
      {modo === 'livre' && <label className="fld grow"><span>Unidade</span><input value={unidade} onChange={e => setUnidade(e.target.value)} /></label>}
      <label className="fld grow"><span>Para quando</span><input type="date" value={quando} onChange={e => setQuando(e.target.value)} /></label>
    </div>
    <label className="check" style={{ margin: '0 0 12px' }}><input type="checkbox" checked={urgente} onChange={e => setUrgente(e.target.checked)} /> Urgente <span className="small muted">(entra em "Precisa de atenção")</span></label>
    <Picker label="Para o kart de (opcional)" value={cliente} onPick={setCliente} />
    <label className="fld"><span>Nota</span><input value={nota} onChange={e => setNota(e.target.value)} placeholder="qual kart, modelo, link" /></label>
    <div className="modal-foot"><button className="btn ghost" onClick={onClose}>Cancelar</button>
      <button className="btn" disabled={indo} onClick={salvar}>{indo ? 'Enviando…' : 'Pedir'}</button></div>
  </div></Scrim>
}

export function Pedidos() {
  const { user, can } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const [filtro, setFiltro] = useState('aberto')
  const lista = useGet<{ pedidos: Pedido[] }>(`/compras/pedidos${filtro ? `?status=${filtro}` : ''}`, 30000)
  const [novo, setNovo] = useState(false)
  const [marcados, setMarcados] = useState<number[]>([])
  const gerente = can('MANAGER')

  async function acao(p: Pedido, qual: 'cancelar' | 'entregue') {
    try { await api.post(`/compras/pedidos/${p.id}/${qual}`); toast(qual === 'cancelar' ? 'Pedido cancelado.' : 'Entregue a quem pediu.', 'ok'); lista.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }

  return <>
    <PageHeader title="Pedidos" help="O que a equipe precisa que se compre. Quem compra vê a fila aqui; quando a compra chega, o pedido avisa.">
      {gerente && marcados.length > 0 && <button className="btn" onClick={() => nav(`/compras?pedidos=${marcados.join(',')}`)}>Comprar {marcados.length} pedido(s)</button>}
      {can('OPERATOR') && <button className="btn primary" onClick={() => setNovo(true)}><Icon name="plus" size={16} /> Novo pedido</button>}
    </PageHeader>
    <div className="seg" style={{ marginBottom: 12 }}>
      {[['aberto', 'Abertos'], ['comprando', 'Comprando'], ['chegou', 'Chegou'], ['entregue', 'Entregues'], ['cancelado', 'Cancelados'], ['', 'Todos']].map(([k, r]) =>
        <button key={k} className={`btn sm${filtro === k ? '' : ' ghost'}`} onClick={() => { setFiltro(k); setMarcados([]) }}>{r}</button>)}
    </div>
    {lista.error && <ErrorState error={lista.error} retry={lista.reload} />}
    {lista.loading && !lista.data && <Loading />}
    {lista.data && (!lista.data.pedidos.length
      ? <Empty title="Nenhum pedido aqui">{filtro === 'aberto' ? <>Precisa de algo? <b>Novo pedido</b>.</> : null}</Empty>
      : <div className="card"><div className="tbl">{lista.data.pedidos.map(p => {
        const [rot, tom] = ST_PEDIDO[p.status] || [p.status, 'neutral']
        return <div className="tr" key={p.id}>
          {gerente && p.status === 'aberto' && <input type="checkbox" aria-label={`comprar ${p.description}`} checked={marcados.includes(p.id)}
            onChange={() => setMarcados(m => m.includes(p.id) ? m.filter(x => x !== p.id) : [...m, p.id])} />}
          <div className="grow">
            <b>{p.qty}× {p.description}</b> {!!p.urgent && <Chip tone="crit">urgente</Chip>}
            <div className="small muted">{p.pedido_por || '—'} · {dia(p.created_at)}{p.cliente ? ` · kart de ${p.cliente}` : ''}{p.needed_by ? ` · até ${dia(p.needed_by)}` : ''}
              {p.purchase_id ? <> · <Link to={`/compras?c=${p.purchase_id}`}>compra #{p.purchase_id}</Link></> : null}{p.notes ? ` · ${p.notes}` : ''}</div>
          </div>
          <Chip tone={tom}>{rot}</Chip>
          {p.status === 'aberto' && (gerente || p.pedido_por === user?.name) && <button className="btn ghost sm" onClick={() => acao(p, 'cancelar')}>cancelar</button>}
          {p.status === 'chegou' && <button className="btn sm" onClick={() => acao(p, 'entregue')}>entreguei</button>}
        </div>
      })}</div></div>)}
    {novo && <NovoPedido onClose={() => setNovo(false)} onDone={lista.reload} />}
  </>
}

/* ============================================================ COMPRAS */

interface LinhaNova { chave: string; item_id: number | null; description: string; qty: string; unit_cost: string; request_id: number | null }
let seq = 0
const nova = (p: Partial<LinhaNova>): LinhaNova => ({ chave: `l${++seq}`, item_id: null, description: '', qty: '1', unit_cost: '', request_id: null, ...p })

function NovaCompra({ inicial, itens, onClose, onDone }: { inicial: LinhaNova[]; itens: ItemEst[]; onClose: () => void; onDone: (id: number) => void }) {
  const toast = useToast()
  const [fornecedor, setFornecedor] = useState('Comet Kart Sales')
  const [linhas, setLinhas] = useState<LinhaNova[]>(inicial.length ? inicial : [nova({})])
  const [ref, setRef] = useState('')
  const [previsao, setPrevisao] = useState('')
  const [pedir, setPedir] = useState(false)
  const [indo, setIndo] = useState(false)
  const total = linhas.reduce((s, l) => s + (Number(l.qty.replace(',', '.')) || 0) * (Number(l.unit_cost.replace(',', '.')) || 0), 0)
  const muda = (k: string, c: Partial<LinhaNova>) => setLinhas(ls => ls.map(l => l.chave === k ? { ...l, ...c } : l))

  async function salvar() {
    const corpo = linhas.filter(l => l.item_id || l.description.trim() || l.request_id).map(l => ({
      item_id: l.item_id, description: l.description.trim() || null, qty: Number(l.qty.replace(',', '.')) || null,
      unit_cost: l.unit_cost.trim() ? Number(l.unit_cost.replace(',', '.')) : null, request_id: l.request_id }))
    if (!corpo.length) { toast('Ponha pelo menos um item.', 'warn'); return }
    setIndo(true)
    try {
      const r = await api.post<{ id: number }>('/compras', { supplier: fornecedor, reference: ref || null, expected_at: previsao || null, pedir, linhas: corpo })
      toast(pedir ? `Compra #${r.id} registrada como pedida.` : `Rascunho #${r.id} salvo.`, 'ok'); onDone(r.id); onClose()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }

  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 720 }} onMouseDown={e => e.stopPropagation()}>
    <h3>Nova compra</h3>
    <label className="fld"><span>Fornecedor</span><input value={fornecedor} onChange={e => setFornecedor(e.target.value)} list="fornecedores" />
      <datalist id="fornecedores"><option value="Comet Kart Sales" /><option value="KartSport (IAME)" /><option value="Tillotson" /><option value="Harbor Freight" /></datalist></label>
    <div className="stack" style={{ gap: 8 }}>
      {linhas.map(l => <div key={l.chave} className="row gap wrap" style={{ alignItems: 'flex-end', paddingBottom: 8, borderBottom: '1px solid var(--glass-line)' }}>
        <label className="fld grow" style={{ flexBasis: 240, margin: 0 }}><span>{l.request_id ? `Pedido #${l.request_id}` : 'Item'}</span>
          <select value={l.item_id ?? ''} onChange={e => { const id = e.target.value ? Number(e.target.value) : null; const it = itens.find(i => i.id === id)
            muda(l.chave, { item_id: id, description: id ? '' : l.description, unit_cost: l.unit_cost || (it?.cost != null ? String(it.cost) : '') }) }}>
            <option value="">— fora do estoque (escreva abaixo) —</option>
            {itens.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
          </select>
          {!l.item_id && <input value={l.description} onChange={e => muda(l.chave, { description: e.target.value })} placeholder="o que é" style={{ marginTop: 6 }} />}
        </label>
        <label className="fld" style={{ width: 90, margin: 0 }}><span>Qtd</span><input type="number" inputMode="decimal" min={0} value={l.qty} onChange={e => muda(l.chave, { qty: e.target.value })} /></label>
        <label className="fld" style={{ width: 120, margin: 0 }}><span>Custo unit.</span><input type="number" inputMode="decimal" min={0} value={l.unit_cost} onChange={e => muda(l.chave, { unit_cost: e.target.value })} placeholder="$" /></label>
        <button className="btn ghost sm" aria-label="tirar item" onClick={() => setLinhas(ls => ls.filter(x => x.chave !== l.chave))}>✕</button>
      </div>)}
      <button className="btn ghost sm" style={{ alignSelf: 'flex-start' }} onClick={() => setLinhas(ls => [...ls, nova({})])}><Icon name="plus" size={14} /> item</button>
    </div>
    <div className="row gap wrap" style={{ marginTop: 12 }}>
      <label className="fld grow"><span>Nº do pedido / rastreio</span><input value={ref} onChange={e => setRef(e.target.value)} /></label>
      <label className="fld grow"><span>Previsão de chegada</span><input type="date" value={previsao} onChange={e => setPrevisao(e.target.value)} /></label>
    </div>
    <label className="check"><input type="checkbox" checked={pedir} onChange={e => setPedir(e.target.checked)} /> Já pedi ao fornecedor <span className="small muted">(senão fica como rascunho)</span></label>
    <div className="modal-foot"><span className="grow small">Total: <b>{usd(total)}</b></span>
      <button className="btn ghost" onClick={onClose}>Cancelar</button>
      <button className="btn" disabled={indo} onClick={salvar}>{indo ? 'Salvando…' : pedir ? 'Registrar compra' : 'Salvar rascunho'}</button></div>
  </div></Scrim>
}

function FichaCompra({ id, gerente, locais, onClose, onDone }: { id: number; gerente: boolean; locais: Local[]; onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const c = useGet<Compra>(`/compras/${id}`)
  const [receber, setReceber] = useState<Record<number, string>>({})
  const [criar, setCriar] = useState<Record<number, boolean>>({})
  const [local, setLocal] = useState(locais[0]?.code || 'sede')
  const [ref, setRef] = useState('')
  const [previsao, setPrevisao] = useState('')
  const [indo, setIndo] = useState(false)
  useEffect(() => {
    if (c.data) setReceber(Object.fromEntries(c.data.linhas.map(l => [l.id, String(Math.max(0, l.qty - l.qty_received))])))
  }, [c.data])
  const recarregar = () => { c.reload(); onDone() }

  async function fazer(caminho: string, corpo: unknown, ok: string) {
    setIndo(true)
    try { await api.post(`/compras/${id}/${caminho}`, corpo); toast(ok, 'ok'); recarregar() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  if (c.error) return <Scrim onMouseDown={onClose}><div className="modal" onMouseDown={e => e.stopPropagation()}><ErrorState error={c.error} retry={c.reload} /></div></Scrim>
  if (!c.data) return <Scrim onMouseDown={onClose}><div className="modal" onMouseDown={e => e.stopPropagation()}><Loading /></div></Scrim>
  const d = c.data
  const [rot, tom] = ST_COMPRA[d.status] || [d.status, 'neutral']
  const aberta = ['rascunho', 'pedida', 'parcial'].includes(d.status)
  const itensReceber = d.linhas.filter(l => l.qty_received < l.qty).map(l => ({ line_id: l.id, qty: Number((receber[l.id] || '0').replace(',', '.')) || 0, criar_item: !!criar[l.id] }))
    .filter(x => x.qty > 0)

  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 720 }} onMouseDown={e => e.stopPropagation()}>
    <h3>Compra #{d.id} · {d.supplier}</h3>
    <div className="row gap wrap" style={{ marginBottom: 10 }}>
      <Chip tone={tom}>{rot}</Chip>{d.atrasada && <Chip tone="crit">atrasada</Chip>}
      {d.reference && <span className="small muted">ref. {d.reference}</span>}
      {d.expected_at && <span className="small muted">previsão {dia(d.expected_at)}</span>}
      {gerente && d.total != null && <span className="small">total <b>{usd(d.total)}</b>{d.sem_custo ? ` + ${d.sem_custo} sem custo` : ''}</span>}
    </div>
    <div className="tbl">{d.linhas.map(l => {
      const falta = l.qty - l.qty_received
      return <div className="tr" key={l.id}>
        <div className="grow"><b>{l.item || l.description}</b>
          <div className="small muted">{l.qty_received}/{l.qty} recebido{gerente && l.unit_cost != null ? ` · ${usd(l.unit_cost)} cada` : ''}
            {l.pedido_por ? ` · pedido por ${l.pedido_por}` : ''}{l.cliente ? ` · kart de ${l.cliente}` : ''}{!l.item_id ? ' · fora do estoque' : ''}</div>
          {aberta && falta > 0 && !l.item_id && <label className="check small"><input type="checkbox" checked={!!criar[l.id]} onChange={e => setCriar(x => ({ ...x, [l.id]: e.target.checked }))} /> criar ficha no estoque ao receber</label>}
        </div>
        {aberta && falta > 0 && <input className="inp" style={{ width: 80, minHeight: 36 }} type="number" inputMode="decimal" min={0} max={falta} aria-label={`quanto chegou de ${l.description}`}
          value={receber[l.id] ?? ''} onChange={e => setReceber(x => ({ ...x, [l.id]: e.target.value }))} />}
        {falta <= 0 && <Chip tone="ok">completo</Chip>}
      </div>
    })}</div>

    {aberta && <div className="row gap wrap" style={{ marginTop: 12, alignItems: 'flex-end' }}>
      {locais.length > 1 && <label className="fld" style={{ margin: 0 }}><span>Chegou em</span>
        <select value={local} onChange={e => setLocal(e.target.value)}>{locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}
      <button className="btn primary" disabled={indo || !itensReceber.length}
        onClick={() => fazer('receber', { local, itens: itensReceber }, 'Recebido: já entrou no estoque.')}>Receber o que chegou</button>
    </div>}

    {gerente && d.status === 'rascunho' && <div className="row gap wrap" style={{ marginTop: 14, alignItems: 'flex-end' }}>
      <label className="fld grow" style={{ margin: 0 }}><span>Nº do pedido / rastreio</span><input value={ref} onChange={e => setRef(e.target.value)} /></label>
      <label className="fld" style={{ margin: 0 }}><span>Previsão</span><input type="date" value={previsao} onChange={e => setPrevisao(e.target.value)} /></label>
      <button className="btn" disabled={indo} onClick={() => fazer('pedida', { reference: ref || null, expected_at: previsao || null }, 'Marcada como pedida.')}>Marcar como pedida</button>
    </div>}

    <div className="modal-foot">
      {gerente && aberta && !d.linhas.some(l => l.qty_received > 0) && <button className="btn ghost" disabled={indo}
        onClick={() => fazer('cancelar', {}, 'Compra cancelada; os pedidos voltaram para a fila.')}>Cancelar compra</button>}
      <span className="grow" />
      <button className="btn ghost" onClick={onClose}>Fechar</button>
    </div>
  </div></Scrim>
}

export function Compras() {
  const { can } = useAuth()
  const gerente = can('MANAGER')
  const [sp, setSp] = useSearchParams()
  const [filtro, setFiltro] = useState<'abertas' | 'recebida' | 'cancelada'>('abertas')
  const lista = useGet<{ compras: Compra[] }>('/compras', 30000)
  const resumo = useGet<Resumo>('/compras/resumo', 30000)
  const pedidosAbertos = useGet<{ pedidos: Pedido[] }>(gerente ? '/compras/pedidos?status=aberto' : null)
  const est = useGet<{ itens: ItemEst[]; locais: Local[] }>('/estoque')
  const [nova_, setNova] = useState<LinhaNova[] | null>(null)
  const [ficha, setFicha] = useState<number | null>(Number(sp.get('c')) || null)
  const [marcadosRepor, setMarcadosRepor] = useState<number[]>([])
  const [marcadosPed, setMarcadosPed] = useState<number[]>([])
  const recarregar = () => { lista.reload(); resumo.reload(); pedidosAbertos.reload() }

  // "Comprar N pedido(s)" da tela de Pedidos chega aqui com ?pedidos=1,2
  useEffect(() => {
    const ids = (sp.get('pedidos') || '').split(',').map(Number).filter(Boolean)
    const abertos = pedidosAbertos.data?.pedidos
    if (ids.length && gerente && abertos) {
      setNova(abertos.filter(p => ids.includes(p.id)).map(p => nova({ request_id: p.id, item_id: p.item_id, description: p.item_id ? '' : p.description, qty: String(p.qty) })))
      sp.delete('pedidos'); setSp(sp, { replace: true })
    }
  }, [sp, setSp, gerente, pedidosAbertos.data])

  const compras = useMemo(() => (lista.data?.compras || []).filter(c =>
    filtro === 'abertas' ? ['rascunho', 'pedida', 'parcial'].includes(c.status) : c.status === filtro), [lista.data, filtro])
  const r = resumo.data

  function comprarSelecionados() {
    const itens = est.data?.itens || []
    const doRepor = (r?.repor || []).filter(x => marcadosRepor.includes(x.id)).map(x => {
      const it = itens.find(i => i.id === x.id)
      return nova({ item_id: x.id, qty: String(x.falta), unit_cost: it?.cost != null ? String(it.cost) : '' })
    })
    const dosPed = (pedidosAbertos.data?.pedidos || []).filter(p => marcadosPed.includes(p.id)).map(p => nova({ request_id: p.id, item_id: p.item_id, description: p.item_id ? '' : p.description, qty: String(p.qty) }))
    setNova([...dosPed, ...doRepor]); setMarcadosRepor([]); setMarcadosPed([])
  }
  const selecionados = marcadosRepor.length + marcadosPed.length

  return <>
    <PageHeader title="Compras" help="O que comprar, o que já foi pedido ao fornecedor e o que chegou. Receber dá entrada no estoque sozinho.">
      {gerente && selecionados > 0 && <button className="btn" onClick={comprarSelecionados}>Comprar {selecionados} selecionado(s)</button>}
      {gerente && <button className="btn primary" onClick={() => setNova([])}><Icon name="plus" size={16} /> Nova compra</button>}
    </PageHeader>

    {r && <div className="est-resumo">
      <Link to="/pedidos"><Chip tone={r.pedidos_abertos ? 'warn' : 'neutral'}>{r.pedidos_abertos} pedido(s) aberto(s)</Chip></Link>
      {!!r.urgentes && <Chip tone="crit">{r.urgentes} urgente(s)</Chip>}
      {!!r.repor.length && <Chip tone="warn">{r.repor.length} abaixo do mínimo</Chip>}
      {!!r.rascunhos && <Chip tone="neutral">{r.rascunhos} rascunho(s)</Chip>}
      <Chip tone="info">{r.a_caminho} a caminho</Chip>
      {!!r.atrasadas && <Chip tone="crit">{r.atrasadas} atrasada(s)</Chip>}
    </div>}

    {gerente && !!pedidosAbertos.data?.pedidos.length && <Section title="Pedidos esperando compra" count={pedidosAbertos.data.pedidos.length}>
      <div className="tbl">{pedidosAbertos.data.pedidos.map(p => <label className="tr" key={p.id} style={{ cursor: 'pointer' }}>
        <input type="checkbox" checked={marcadosPed.includes(p.id)} onChange={() => setMarcadosPed(m => m.includes(p.id) ? m.filter(x => x !== p.id) : [...m, p.id])} />
        <div className="grow"><b>{p.qty}× {p.description}</b> {!!p.urgent && <Chip tone="crit">urgente</Chip>}
          <div className="small muted">{p.pedido_por || '—'}{p.cliente ? ` · kart de ${p.cliente}` : ''}{p.needed_by ? ` · até ${dia(p.needed_by)}` : ''}</div></div>
      </label>)}</div>
    </Section>}

    {!!r?.repor.length && <Section title="Abaixo do mínimo" count={r.repor.length}>
      <div className="tbl">{r.repor.map(x => <label className="tr" key={x.id} style={{ cursor: gerente ? 'pointer' : undefined }}>
        {gerente && <input type="checkbox" checked={marcadosRepor.includes(x.id)} onChange={() => setMarcadosRepor(m => m.includes(x.id) ? m.filter(y => y !== x.id) : [...m, x.id])} />}
        <div className="grow"><b>{x.name}</b>{x.sku && <span className="small muted"> · SKU {x.sku}</span>}</div>
        <span className="small">faltam <b>{x.falta}</b> {x.unit}</span>
        {x.supplier_url && <a className="btn ghost sm" href={x.supplier_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>fornecedor</a>}
      </label>)}</div>
    </Section>}

    <Section title="Compras" count={compras.length} right={<div className="seg">
      {([['abertas', 'Em aberto'], ['recebida', 'Recebidas'], ['cancelada', 'Canceladas']] as const).map(([k, rot]) =>
        <button key={k} className={`btn sm${filtro === k ? '' : ' ghost'}`} onClick={() => setFiltro(k)}>{rot}</button>)}</div>}>
      {lista.error && <ErrorState error={lista.error} retry={lista.reload} />}
      {lista.loading && !lista.data && <Loading />}
      {lista.data && (!compras.length ? <Empty title={filtro === 'abertas' ? 'Nenhuma compra em aberto' : 'Nada aqui'} />
        : <div className="tbl">{compras.map(c => {
          const [rot, tom] = ST_COMPRA[c.status] || [c.status, 'neutral']
          return <div className="tr" key={c.id} role="button" tabIndex={0} style={{ cursor: 'pointer' }} onClick={() => setFicha(c.id)}
            onKeyDown={e => { if (e.key === 'Enter') setFicha(c.id) }}>
            <div className="grow"><b>#{c.id} · {c.supplier}</b>
              <div className="small muted">{c.linhas.length} item(ns){c.reference ? ` · ref. ${c.reference}` : ''}{c.expected_at ? ` · previsão ${dia(c.expected_at)}` : ''} · {c.criada_por || '—'}</div></div>
            {gerente && c.total != null && <span className="small">{usd(c.total)}</span>}
            {c.atrasada && <Chip tone="crit">atrasada</Chip>}
            <Chip tone={tom}>{rot}</Chip>
          </div>
        })}</div>)}
    </Section>

    {nova_ !== null && <NovaCompra inicial={nova_} itens={est.data?.itens || []} onClose={() => setNova(null)} onDone={id => { recarregar(); setFicha(id) }} />}
    {ficha !== null && <FichaCompra id={ficha} gerente={gerente} locais={est.data?.locais || []} onClose={() => { setFicha(null); if (sp.get('c')) { sp.delete('c'); setSp(sp, { replace: true }) } }} onDone={recarregar} />}
  </>
}
